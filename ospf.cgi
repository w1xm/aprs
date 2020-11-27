#!/usr/bin/env python3

import cgi
import os
import routeros_api

import ospf

form = cgi.FieldStorage()

password = form.getfirst('password')
if form.getfirst('resolve'):
    ospf.resolve_router_hostnames = True

return_png = False
if form.getfirst('png'):
    # If set, render to PNG. Otherwise, return raw DOT file
    return_png = True

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
    print('Content-type: ' + 'image/png' if return_png else 'text/plain')
    print()
if not return_png:
    for l in str(nw).splitlines():
        print("//", l)

dot_data = nw.generateGraph()
if return_png:
    # Render
    import graphviz
    src = graphviz.Source(dot_data)
    print(src.pipe(format="png"))
else:
    # Raw DOT file
    print(dot_data)
