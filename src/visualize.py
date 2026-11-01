"""Drawing helpers.

  * net_to_dot      : Petri net as Graphviz DOT text (circles = places,
                      boxes = transitions, dots = tokens). Problem parts in red.
  * graph_to_dot    : reachability graph, dead markings in red, final in green.
  * bpmn_viewer_html: HTML page that draws the BPMN diagram with bpmn-js.

Streamlit draws DOT text in the browser (st.graphviz_chart), so no Graphviz
install is needed to run the app.
"""
import json
from pathlib import Path
from .reachability import key, marking_text

COL = {"source": "#dbeafe", "sink": "#dcfce7", "resource": "#fef3c7",
       "monitor": "#ede9fe", "stuck": "#fee2e2", "flow": "white", "internal": "white"}


def _q(s):
    return '"' + str(s).replace('"', "'") + '"'


def _tokens(n):
    if n == 0:
        return ""
    return "●" * n if n <= 3 else f"●×{n}"


def net_to_dot(net, marking=None, red_places=(), red_transitions=(), enabled=(), short=True):
    m = net.m0 if marking is None else marking
    L = ["digraph PN {", "rankdir=LR; nodesep=0.35; ranksep=0.45;",
         'node [fontname="Helvetica", fontsize=10]; edge [arrowsize=0.6, color="#555555"];']
    for p in net.places.values():
        tok = _tokens(m.get(p.id, 0))
        name = p.label if len(p.label) <= 28 or not short else p.label[:26] + "…"
        color = "#dc2626" if p.id in red_places else "#333333"
        pen = 2.5 if p.id in red_places else 1
        L.append(f'{_q(p.id)} [shape=circle, fixedsize=true, width=0.42, label={_q(tok)}, fontsize=12, '
                 f'xlabel={_q(name)}, style=filled, fillcolor="{COL.get(p.kind, "white")}", '
                 f'color="{color}", penwidth={pen}];')
    for t in net.transitions.values():
        if t.id in red_transitions:
            style = 'style=filled, fillcolor="#fecaca", color="#dc2626", penwidth=2.5'
        elif t.id in enabled:
            style = 'style=filled, fillcolor="#bbf7d0", color="#15803d", penwidth=2'
        elif t.silent:
            style = 'style=filled, fillcolor="#e5e7eb", color="#6b7280"'
        else:
            style = 'style=filled, fillcolor="#f8fafc", color="#111827"'
        L.append(f'{_q(t.id)} [shape=box, height=0.3, label={_q(t.label)}, {style}];')
    for t in net.transitions:
        for p, w in net.pre[t].items():
            L.append(f'{_q(p)} -> {_q(t)}' + (f' [label="{w}"]' if w > 1 else "") + ";")
        for p, w in net.post[t].items():
            L.append(f'{_q(t)} -> {_q(p)}' + (f' [label="{w}"]' if w > 1 else "") + ";")
    L.append("}")
    return "\n".join(L)


def graph_to_dot(net, result, max_nodes=150):
    rg = result["graph"]
    bad = {d["index"]: d["kind"] for d in result["dead_markings"]}
    final = key(net.mf)
    n = min(len(rg.markings), max_nodes)
    L = ["digraph RG {", "rankdir=TB; nodesep=0.25; ranksep=0.35;",
         'node [fontname="Helvetica", fontsize=9, shape=box, style="rounded,filled", fillcolor="white"];',
         'edge [fontname="Helvetica", fontsize=8, color="#666666", arrowsize=0.6];']
    for i in range(n):
        m = rg.markings[i]
        label = f"M{i}\\n" + "\\n".join(f"{p}" + (f"×{c}" if c > 1 else "") for p, c in sorted(m.items()))
        if i in bad:
            style = 'fillcolor="#fecaca", color="#dc2626", penwidth=2'
        elif key(m) == final:
            style = 'fillcolor="#bbf7d0", color="#15803d", penwidth=2'
        elif i == 0:
            style = 'fillcolor="#dbeafe"'
        else:
            style = ""
        L.append(f'"M{i}" [label="{label}" {"," if style else ""}{style}];')
    for a, t, b in rg.edges:
        if a < n and b < n:
            L.append(f'"M{a}" -> "M{b}" [label={_q(net.transitions[t].label[:22])}];')
    L.append("}")
    return "\n".join(L)


STATIC = Path(__file__).resolve().parent.parent / "static"


def bpmn_viewer_html(xml_text, height=420, highlight=()):
    """bpmn-js viewer (bundled in static/, works offline). Faulty elements get a red outline."""
    js = (STATIC / "bpmn-navigated-viewer.production.min.js").read_text(encoding="utf-8")
    css = (STATIC / "bpmn-viewer.css").read_text(encoding="utf-8")
    return f"""
<style>{css}</style>
<div id="canvas" style="height:{height}px;border:1px solid #e5e7eb;border-radius:8px;background:white"></div>
<script>{js}</script>
<style>.hl:not(.djs-connection) .djs-visual > :nth-child(1) {{ stroke:#dc2626 !important; stroke-width:4px !important; fill:#fee2e2 !important; }}</style>
<script>
  const viewer = new BpmnJS({{ container: '#canvas' }});
  viewer.importXML({json.dumps(xml_text)}).then(() => {{
    const canvas = viewer.get('canvas'); canvas.zoom('fit-viewport');
    {json.dumps(list(highlight))}.forEach(id => {{ try {{ canvas.addMarker(id, 'hl'); }} catch(e) {{}} }});
  }}).catch(err => {{ document.getElementById('canvas').innerText = 'Could not draw diagram: ' + err; }});
</script>"""


def marking_label(net, m):
    return marking_text(net, m)
