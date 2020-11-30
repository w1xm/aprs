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
        'txt': 'text/plain',
        'html': 'text/html',
    }[format])
    print()

dot = io.StringIO()
for l in str(nw).splitlines():
    print("//", l, file=dot)

print(nw.generateGraph(), file=dot)
if format == 'txt':
    # Raw DOT file
    print(dot.getvalue())
elif format == 'html':
    # Cytoscape library
    import pydot
    import json
    g, = pydot.graph_from_dot_data(dot.getvalue())
    data = {'nodes': [], 'edges': []}
    def label(t):
        return val(t) or ''
    def val(t):
        if not t:
            return None
        if t.startswith('"'):
            return eval(t)
        return t
    for sg in g.get_subgraphs():
        data['nodes'].append({
            'data': {
                'id': sg.get_name(),
                'content': label(sg.get_label()),
            },
            'classes': 'subgraph',
        })
        for n in sg.get_nodes():
            data['nodes'].append({
                'data': {
                    'id': n.get_name(),
                    'parent': sg.get_name(),
                    'content': label(n.get_label()),
                },
            })
        for n1 in sg.get_nodes():
            for n2 in sg.get_nodes():
                if n1 == n2:
                    continue
                data['edges'].append({
                    'data': {'source': n1.get_name(), 'target': n2.get_name()},
                    'classes': 'subgraph-edge',
                })
    for n in g.get_nodes():
        if n.get_name() == 'node':
            continue
        data['nodes'].append({
            'data': {
                'id': n.get_name(),
                'content': label(n.get_label()),
                'shape': val(n.get_shape()),
            },
        })
    for e in g.get_edges():
        data['edges'].append({
            'data': {
                'source': e.get_source(),
                'target': e.get_destination(),
                'label': label(e.get_label()),
                'taillabel': label(e.get_taillabel()),
                'headlabel': label(e.get_headlabel()),
            },
        })
    print("""
<!DOCTYPE html>
<html>
<head>
<title>OSPF Network State</title>
<style type="text/css">
body {
  font: 14px helvetica neue, helvetica, arial, sans-serif;
}

#cy {
  height: 100%;
  width: 100%;
  position: absolute;
  left: 0;
  top: 0;
}
</style>
<meta name="viewport" content="user-scalable=no, initial-scale=1.0, minimum-scale=1.0, maximum-scale=1.0, minimal-ui">
<script src="https://unpkg.com/cytoscape/dist/cytoscape.min.js"></script>
<script src="https://unpkg.com/layout-base/layout-base.js"></script>
<script src="https://unpkg.com/cose-base/cose-base.js"></script>
<script src="https://unpkg.com/cytoscape-cose-bilkent/cytoscape-cose-bilkent.js"></script>
<script src="https://unpkg.com/cytoscape-expand-collapse/cytoscape-expand-collapse.js"></script> 
</head>
<body>
<div id="cy"></div>
<script type="application/javascript">
var cy = window.cy = cytoscape({
  container: document.getElementById('cy'),

  ready: function(){
    var api = this.expandCollapse({
      layoutBy: {
        name: "cose-bilkent",
        animate: "end",
        randomize: false,
        fit: true,
        packComponents: false,
        gravity: 0.25,
        gravityRange: 3.8,
        gravityCompound: 1,
        gravityRangeCompound: 1.5,
        numIter: 2500,
        nodeSeparation: 50,
        idealEdgeLength: 150,
      },
      fisheye: true,
      animate: false,
      undoable: false
    });
    api.collapseAll();
  },

  boxSelectionEnabled: false,

  style: [
    {
      selector: 'node[content]',
      'css': {
        'content': 'data(content)',
      }
    },
    {
      selector: 'edge[label]',
      'style': {
        'label': 'data(label)',
      }
    },
    {
      selector: 'edge[taillabel]',
      'style': {
        'source-label': 'data(taillabel)',
        'target-label': 'data(headlabel)',
      }
    },
    {
      selector: 'node',
      'style': {
        'shape': 'round-rectangle',
        'width': 130,
        'height': 40,
        'text-valign': 'center',
        'text-halign': 'center',
        'text-wrap': 'wrap',
        'background-opacity': 0,
        'border-style': 'solid',
        'border-width': '1',
      }
    },
    {
      selector: 'node[shape="octagon"]',
      css: {
        shape: 'round-octagon',
      },
    },
    {
      selector: 'node[shape="plaintext"]',
      css: {
        'border-width': 0,
      },
    },
    {
      selector: '.subgraph',
      css: {
        'shape': 'rectangle',
      },
    },
    {
      selector: ':parent',
      css: {
        'text-valign': 'top',
        'text-halign': 'center',
      }
    },
    {
      selector: 'edge',
      css: {
        'curve-style': 'bezier',
        'source-text-offset': 20,
        'target-text-offset': 20,
      }
    },
    {
    selector: '.subgraph-edge',
    css: {
    'display': 'none',
    },
    },
  ],
elements: """)
    print(json.dumps(data, indent=' '))
    print(""",
});
</script>
</body>
</html>
""")

else:
    # Render
    import graphviz
    src = graphviz.Source(dot.getvalue())
    sys.stdout.flush()
    sys.stdout.buffer.write(src.pipe(format=format))
