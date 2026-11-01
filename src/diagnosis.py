"""Step 4 - explain WHY a dead marking is stuck.

For a dead marking we list
  * where the tokens are (what has already happened), and
  * which transitions are waiting, and for which empty input place.
We then map those transitions back to BPMN elements so the user sees the
faulty gateway / task in the diagram.
"""
from .reachability import marking_text


def explain(net, dead):
    """dead = one entry of analyse(net)['dead_markings']"""
    m = dead["marking"]
    waiting = []
    for p, n in m.items():
        if not n or net.places[p].kind in ("resource", "sink"):
            continue
        consumers = net.postset_of_place(p)
        if not consumers:
            waiting.append({"place": p, "transition": None, "missing": [],
                            "text": f"Token in '{net.places[p].label}' but no transition ever takes it "
                                    "(dead end)."})
        for t in consumers:
            missing = [q for q, w in net.pre[t].items() if m.get(q, 0) < w]
            if missing:
                names = ", ".join(f"'{net.places[q].label}'" for q in missing)
                waiting.append({"place": p, "transition": t, "missing": missing,
                                "text": f"'{net.transitions[t].label}' has a token in "
                                        f"'{net.places[p].label}' but is still waiting for {names}."})
    bpmn_nodes = sorted({net.transitions[w["transition"]].bpmn_id for w in waiting if w["transition"]})
    trace = [net.transitions[t].label for t in dead["trace"]]
    return {
        "kind": dead["kind"],
        "tokens": marking_text(net, m),
        "waiting": waiting,
        "bpmn_nodes": bpmn_nodes,
        "trace": trace,
        "highlight_places": [w["place"] for w in waiting] + [q for w in waiting for q in w["missing"]],
        "highlight_transitions": [w["transition"] for w in waiting if w["transition"]],
    }
