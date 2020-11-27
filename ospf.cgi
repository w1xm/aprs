#!/usr/bin/env python3

import cgi
import os
import routeros_api

import ospf

form = cgi.FieldStorage()

password = form.getfirst('password')
if form.getfirst('resolve'):
    ospf.resolve_router_hostnames = True

connection = routeros_api.RouterOsApiPool('w1xm-21.mit.edu', username='admin', password=password, plaintext_login=True)
api = connection.get_api()
lsas = api.get_resource('/routing/ospf/lsa').get()

nw = ospf.NetworkModel()
for l in lsas:
    try:
        nw.injectLSA(ospf.parse_mikrotik_lsa(l))
    except:
        print(l)
        raise
if 'GATEWAY_INTERFACE' in os.environ:
    print('Content-type: text/plain')
    print()
for l in str(nw).splitlines():
    print("#", l)
print(nw.generateGraph())
