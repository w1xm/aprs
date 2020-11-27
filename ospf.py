#!/usr/bin/env python3
import io
import socket
import sys
import datetime
import netaddr
import struct 
import binascii

resolve_router_hostnames = False

OSPF_TYPE = ["Invalid","Hello","DBD","LSR","LSU","LSA"]

def safeIPAddr(ip):
  return str(ip).replace('.', '_')


def destNW(ip, networks):
  for nw in networks:
    if (ip & networks[nw].netmask) == nw:
      return nw
  return None

def parse_body(body):
    for line in body.splitlines():
        yield {i[0]: i[1] if len(i) > 1 else None for i in (x.split('=', 1) for x in line.strip().split())}

def parse_mikrotik_lsa(lsa):
    return {
        'router': Mikrotik_LSA_Router,
        'network': Mikrotik_LSA_Network,
        'as-external': Mikrotik_LSA_External,
    }[lsa['type']](lsa)

class Mikrotik_LSA_Header(object):
    def __init__(self, lsa):
        self.area = lsa['area']
        self.age = int(lsa['age'])
        self.options = lsa['options']
        self.type = {'router': 1, 'network': 2, 'as-external': 5}.get(lsa['type'])
        self.lsid = netaddr.IPAddress(lsa['id'])
        self.advrouter = netaddr.IPAddress(lsa['originator'])
        self.seq = int(lsa['sequence-number'], 16)

class OSPF_LSA_Header(object):
  def __init__(self, data):
    self.age = mkNetInt(data[0:2])
    self.options = ord(data[2])
    self.type = ord(data[3])
    self.lsid = netaddr.IPAddress(socket.inet_ntoa(data[4:8]))
    self.advrouter = netaddr.IPAddress(socket.inet_ntoa(data[8:12]))
    self.seq = mkNetInt(data[12:16])

class Mikrotik_LSA_Router(Mikrotik_LSA_Header):
    class Link(object):
        def __init__(self, body):
            self.id = netaddr.IPAddress(body['id'])
            self.data = netaddr.IPAddress(body['data'])
            self.type = {'Point-To-Point': 1, 'Transit': 2, 'Stub': 3, 'Virtual': 4}.get(body['link-type'], 0)
            self.link_type = body['link-type']
            self.metric = int(body['metric'])
        def __str__(self):
            return '%s (%d): %s [%s], %d' % (self.link_type, self.type, self.id, self.data, self.metric)

    def __init__(self, lsa):
        super().__init__(lsa)
        self.links = []
        for args in parse_body(lsa['body']):
            if 'flags' in args:
                self.flags = args['flags']
            else:
                self.links.append(self.Link(args))

    def __str__(self):
        return ', '.join([str(self.lsid), str(self.advrouter), '\n[ '+'\n  '.join([str(l) for l in self.links])+'\n]'])

class OSPF_LSA_Router(OSPF_LSA_Header):
  class Link(object):
    linkTypes = { 1: 'p2p to router', 2: 'transit n/w', 3: 'stub n/w', 4: 'virtual link' }
    def __init__(self, data):
      self.id = netaddr.IPAddress(socket.inet_ntoa(data[0:4]))
      self.data = netaddr.IPAddress(socket.inet_ntoa(data[4:8]))
      self.type = ord(data[8])
      self.metric = mkNetInt(data[10:12])
    def __str__(self):
      return '%s (%d): %s [%s], %d' % (self.linkTypes[self.type], self.type, self.id, self.data, self.metric)

  def __init__(self, data):
    OSPF_LSA_Header.__init__(self, data)
    self.links=[]
    l = data[24:]
    while len(l) > 0:
      self.links.append(self.Link(l[0:12]))
      l = l[12:]

  def __str__(self):
    return ', '.join([str(self.lsid), str(self.advrouter), '\n[ '+'\n  '.join([str(l) for l in self.links])+'\n]'])

class Mikrotik_LSA_Network(Mikrotik_LSA_Header):
    def __init__(self, lsa):
        super().__init__(lsa)
        args = {}
        for line in parse_body(lsa['body']):
            args.update(line)
        self.netmask = netaddr.IPAddress(args['netmask'])
        self.attached = []
        raise NotImplementedError("todo: parse attached")

    def __str__(self):
        return ', '.join([str(self.lsid), str(self.advrouter), str(self.netmask), '{'+', '.join([str(a) for a in self.attached])+'}'])


class OSPF_LSA_Network(OSPF_LSA_Header):
  def __init__(self, data):
    OSPF_LSA_Header.__init__(self, data)
    self.netmask = netaddr.IPAddress(socket.inet_ntoa(data[20:24]))
    data = data[24:]
    self.attached = []
    while len(data) > 0:
      self.attached.append(netaddr.IPAddress(socket.inet_ntoa(data[0:4])))
      data = data[4:]

  def __str__(self):
    return ', '.join([str(self.lsid), str(self.advrouter), str(self.netmask), '{'+', '.join([str(a) for a in self.attached])+'}'])

class Mikrotik_LSA_External(Mikrotik_LSA_Header):
    def __init__(self, lsa):
        super().__init__(lsa)
        args = {}
        for line in parse_body(lsa['body']):
            args.update(line)
        self.netmask = netaddr.IPAddress(args['netmask'])
        self.forwarding_address = netaddr.IPAddress(args['forwarding-address'])
        self.metric = int(args['metric'])
        self.route_tag = int(args['route-tag'], 16)

class OSPF_LSA_External(OSPF_LSA_Header):
  def __init__(self, data):
    OSPF_LSA_Header.__init__(self, data)
    self.netmask = netaddr.IPAddress(socket.inet_ntoa(data[20:24]))
    self.metric = mkNetInt(data[24:28]) & 0x00ffffff
    

class OSPF_LS_Update(object):
  lsTypes = { 1: ('Router-LSAs', OSPF_LSA_Router), 2: ('Network-LSAs', OSPF_LSA_Network), 5: ('AS-external-LSAs', OSPF_LSA_External) }
  def __init__(self, data):
    self.routerID = netaddr.IPAddress(socket.inet_ntoa(data[4:8]))
    self.areaID = netaddr.IPAddress(socket.inet_ntoa(data[8:12]))
    self.lsa = []

    numLSAs = mkNetInt(data[24:28])
    lsas = data[28:]
    for i in range(numLSAs):
      lsaLen = mkNetInt(lsas[18:20])
      lsType = ord(lsas[3])
      if lsType in self.lsTypes:
        self.lsa.append(self.lsTypes[lsType][1](lsas[0:lsaLen]))
      lsas=lsas[lsaLen:]


class NetworkModel(object):
    def __init__(self):
        self.extnetworks={}
        self.networks={}
        self.routers={}
        self.changed = False

    def injectLSA(self, lsa):
        if lsa.type == 2:
            network = lsa.lsid & lsa.netmask
            if network not in self.networks or lsa.seq > self.networks[network].seq:
                self.networks[network] = lsa
                self.changed = True
                #        print("Network Update: ", lsa)
            else:
                print("// N/W lsa is old", lsa)
        elif lsa.type == 1:
            if lsa.lsid not in self.routers or lsa.seq > self.routers[lsa.lsid].seq:
                self.routers[lsa.lsid] = lsa
                self.changed = True
                #        print("Router Update: ", lsa)
            else:
                print("// Router lsa is old", lsa)
        elif lsa.type == 5:
            network = lsa.lsid & lsa.netmask
            if lsa.advrouter not in self.extnetworks:
                self.extnetworks[lsa.advrouter] = {}
            if network not in self.extnetworks[lsa.advrouter] or lsa.seq > self.extnetworks[lsa.advrouter][network].seq:
                self.extnetworks[lsa.advrouter][network] = lsa
                self.changed = True
                #        print("Extern update: ", lsa)
            else:
                print("// Extern LSA is old")
        else:
            print("// Unknown LSA!", lsa.type)

    def __str__(self):
        out = io.StringIO()
        print("Router Debug:", file=out)
        for i in self.routers:
            print(i, self.routers[i], file=out)
        print('-'*30, file=out)
        print("Network Debug:", file=out)
        for i in self.networks:
            print(i, self.networks[i], file=out)
        print('-'*30, file=out)
        print("External Debug:", file=out)
        for i in self.extnetworks:
            print(i, self.extnetworks[i], file=out)
        return out.getvalue()


    def generateGraph(self):
        out = []
        out.append('graph ospf_nw {')
        out.append('  layout=fdp;')
        out.append('  splines=true;')
        out.append('  label="Generated: %s";' % str(datetime.datetime.utcnow()))
        out.append('  node [shape="box",style="rounded"];')

        nodes = set()
        links = []

        p2pnwset = netaddr.IPSet()

        p2pnw = {}
        p2plink = {}

        for r, router in self.routers.items():
            out.append('  subgraph cluster_%s {' % safeIPAddr(r))

            label = r
            if resolve_router_hostnames:
                try:
                    label = '%s\\n(%s)' % (socket.gethostbyaddr(str(r))[0].split('.')[0], r)
                except:
                    print('// Could not get hostname for router %s' % r)

            out.append('    label = "%s";' % label)
            rnodes = set()
            for iface in router.links:
                if iface.type == 2:    # transit n/w
                    rnodes.add('    N%s [label="%s"];' % (safeIPAddr(iface.data), iface.data ))
                elif iface.type == 1:    # p2p n/w
                    rnodes.add('    N%s [label="%s"];' % (safeIPAddr(iface.data), iface.data ))
                    p2pnwset.add(iface.data)
                    p2pnw[iface.data] = router
                    p2plink['%s_%s' % (iface.data, r)] = iface
            out += list(rnodes)
            out.append('  }')

        for nw in self.networks:
            out.append('  nw_%s [shape="plaintext",label="%s/%s"];' % (safeIPAddr(nw), nw, self.networks[nw].netmask.bin.count('1') ))

        print("#", p2pnw)

        for r, router in self.routers.items():
            for iface in router.links:
                if iface.type == 2:    # transit n/w
                    links.append('  N%s -- nw_%s [label="%s"];' % (safeIPAddr(iface.data), safeIPAddr(destNW(iface.data, self.networks)), iface.metric))
                elif iface.type == 3:    # stub n/w
                    network = netaddr.IPNetwork("%s/%s" % (iface.id, iface.data))
                    # iface.id is the network address, iface.data is the subnet mask
                    ptp_ips = p2pnwset & netaddr.IPSet(network)
                    if ptp_ips:
                        localiface = [iface for iface in router.links if netaddr.IPSet([iface.data]) & netaddr.IPSet(network)][0]
                        routers = [p2pnw[ip] for ip in ptp_ips]
                        remote = [r for r in routers if r != router][0]
                        remoteiface = [iface for iface in remote.links if netaddr.IPSet([iface.data]) & netaddr.IPSet(network)][0]
                        ids = [router.lsid, remote.lsid]
                        p2psorted = sorted(ids)
                        #nodes.add('  ptp_%s_%s [shape="plaintext",label="Tunnel"];' % (safeIPAddr(p2psorted[0]), safeIPAddr(p2psorted[1])))
                        if p2psorted[0] == r:
                            links.append('  N%s -- N%s [taillabel="%s",headlabel="%s"];' % (safeIPAddr(str(localiface.data)), safeIPAddr(str(remoteiface.data)), iface.metric, remoteiface.metric))
                        #links.append('  N%s -- ptp_%s_%s [label="%s"];' % (safeIPAddr(str(localiface.data)), safeIPAddr(p2psorted[0]), safeIPAddr(p2psorted[1]), iface.metric))

                    #if (str(iface.id) not in p2pnw) or (str(p2pnw[str(iface.id)]) == str(r)) or ('%s_%s' % (p2pnw[str(iface.id)], r) not in p2plink):
                    else:
                        nodes.add('  stub_%s [shape="doubleoctagon",label="%s/%s"];' % (safeIPAddr(iface.id), iface.id, iface.data.bin.count('1')))
                        links.append('  cluster_%s -- stub_%s [label="%s"];' % (safeIPAddr(r), safeIPAddr(iface.id), iface.metric))
                    #else:
                    #    remoteid = p2pnw[str(iface.id)]
                    #    p2psorted = sorted([remoteid, str(r)])
                    #    p2plocalip = p2plink['%s_%s' % (remoteid, r)]
                    #    nodes.add('  ptp_%s_%s [shape="plaintext",label="Tunnel"];' % (safeIPAddr(p2psorted[0]), safeIPAddr(p2psorted[1])))
                    #    links.append('  N%s -- ptp_%s_%s [label="%s"];' % (safeIPAddr(p2plocalip), safeIPAddr(p2psorted[0]), safeIPAddr(p2psorted[1]), iface.metric))

            if r in self.extnetworks:
                for extnet in self.extnetworks[r]:
                    nodes.add('  extnet_%s [shape="octagon",label="%s/%s"];' % (safeIPAddr(extnet), extnet, self.extnetworks[r][extnet].netmask.bin.count('1')))
                    links.append('  cluster_%s -- extnet_%s [label="%s"];' % (safeIPAddr(r), safeIPAddr(extnet), self.extnetworks[r][extnet].metric))

        out += list(nodes) + links

        out.append('}')
        out.append('')
        self.changed = False
        return '\n'.join(out)

nw = NetworkModel()

def processPacket(data):
  z=OSPF_LS_Update(data)
  for l in z.lsa:
    nw.injectLSA(l)

  if nw.changed:
    if graphFile:
      f=open(graphFile, 'w')
      f.write(nw.generateGraph())
      f.close()
    else:
      print(nw.generateGraph())

graphFile = None

if __name__ == '__main__':
    import pcap
    import dpkt

    if len(sys.argv) == 2:
        graphFile = sys.argv[1]

    print("Output file:", graphFile)

  
    sock = pcap.pcap(name=None, promisc=True, immediate=True)
    sock.setfilter("proto 89")
    print("Listener started")
    try:
        for timestamp, data in sock:
            eth=dpkt.ethernet.Ethernet(data)
            ip=eth.data
            if not isinstance(ip.data, dpkt.ospf.OSPF):
                print("Invalid OSPF Packet")
                continue 
            ospf = ip.data
            # Only process actual update packets
            if OSPF_TYPE[ospf.type] == "LSU":    
                print(timestamp, "src: ", socket.inet_ntoa(ip.src), "\tRouter: ", str(netaddr.IPAddress(ospf.router)), "\tArea: ", ospf.area, "\tType: ", OSPF_TYPE[ospf.type])
                processPacket(data[34:])
#      else 
#        print(timestamp, "src: ", socket.inet_ntoa(ip.src), "\tRouter: ", str(netaddr.IPAddress(ospf.router)), "\tArea: ", ospf.area, "\tType: ", OSPF_TYPE[ospf.type])
    except KeyboardInterrupt:
        sys.exit()  
