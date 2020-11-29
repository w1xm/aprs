#!/usr/bin/env python3

import cgi
import cgitb
import io
import os
import sys
import routeros_api

import ospf

form = cgi.FieldStorage()

password = form.getfirst('password')
if form.getfirst('resolve'):
    ospf.resolve_router_hostnames = True

format = form.getfirst('format', 'txt')

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
    print('Content-type: ' + {
        'png': 'image/png',
        'svg': 'image/svg+xml',
        'txt': 'text/plain'}[format])
    print()

dot = io.StringIO()
for l in str(nw).splitlines():
    print("//", l, file=dot)

print(nw.generateGraph(), file=dot)
if format == 'txt':
    # Raw DOT file
    print(dot.getvalue())
else:
    # Render
    import graphviz
    src = graphviz.Source(dot.getvalue())
    sys.stdout.flush()
    sys.stdout.buffer.write(src.pipe(format=format))
