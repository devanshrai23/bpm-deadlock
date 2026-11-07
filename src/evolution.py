"""BPMN model evolution and atomic change detection."""


def _sig(model, eid):
    if eid in model.nodes:
        n = model.nodes[eid]
        return ("node", n.kind, n.name)
    f = model.flows[eid]
    return ("flow", f.src, f.tgt)


def detect_changes(old, new):
    """List of {op, element, kind, before, after} from model `old` to model `new`."""
    old_ids = set(old.nodes) | set(old.flows)
    new_ids = set(new.nodes) | set(new.flows)
    ops = []
    for eid in sorted(old_ids - new_ids):
        ops.append({"op": "delete", "element": eid, "kind": _sig(old, eid)[0], "before": _sig(old, eid), "after": None})
    for eid in sorted(new_ids - old_ids):
        ops.append({"op": "insert", "element": eid, "kind": _sig(new, eid)[0], "before": None, "after": _sig(new, eid)})
    for eid in sorted(old_ids & new_ids):
        a, b = _sig(old, eid), _sig(new, eid)
        if a != b:
            ops.append({"op": "replace", "element": eid, "kind": a[0], "before": a, "after": b})
    return ops


def summary(ops):
    """e.g. {'insert': 9, 'delete': 1, 'replace': 2}"""
    out = {"insert": 0, "delete": 0, "replace": 0}
    for o in ops:
        out[o["op"]] += 1
    return out
