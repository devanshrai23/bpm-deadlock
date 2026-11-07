def _forward(model, start_flow, stop_nodes):
    seen, stack = set(), [start_flow]
    while stack:
        fid = stack.pop()
        if fid in seen:
            continue
        seen.add(fid)
        tgt = model.flows[fid].tgt
        if tgt in stop_nodes:
            continue
        stack.extend(f.id for f in model.outgoing(tgt))
    return seen


def _split_join_mismatch(model, split_kinds, join_kind, code, severity, title, explain, fix):
    issues = []
    joins = [n for n in model.nodes.values() if n.kind == join_kind and len(model.incoming(n.id)) > 1]
    splits = [n for n in model.nodes.values() if n.kind in split_kinds and len(model.outgoing(n.id)) > 1]
    for x in splits:
        branches = model.outgoing(x.id)
        for j in joins:
            inc = [f.id for f in model.incoming(j.id)]
            reach = {b.id: _forward(model, b.id, {j.id, x.id}) for b in branches}
            hit = False
            for a in inc:
                for b in inc:
                    if a == b:
                        continue
                    # one branch of x reaches a but not b, another reaches b but not a
                    if any(a in reach[k1] and b not in reach[k1] for k1 in reach) and \
                       any(b in reach[k2] and a not in reach[k2] for k2 in reach):
                        hit = True
            if hit:
                issues.append({"code": code, "severity": severity, "title": title,
                               "nodes": [x.id, j.id],
                               "message": explain.format(split=model.label(x.id), join=model.label(j.id)),
                               "fix": fix.format(split=model.label(x.id), join=model.label(j.id)),
                               "auto_fix": {"node": j.id, "new_kind": "xor" if join_kind == "and" else "and"}})
    return issues


def _and_join_loops(model):
    issues = []
    for j in model.nodes.values():
        if j.kind != "and" or len(model.incoming(j.id)) < 2:
            continue
        outs = model.outgoing(j.id)
        for f in model.incoming(j.id):
            if any(f.id in _forward(model, o.id, {j.id}) for o in outs):
                issues.append({"code": "P2", "severity": "deadlock", "title": "AND-join at a loop entry",
                               "nodes": [j.id],
                               "message": f"'{model.label(j.id)}' waits for the loop-back flow "
                                          f"'{f.name or f.id}', which can only arrive after the join itself has fired.",
                               "fix": f"Use an XOR-join (merge) at '{model.label(j.id)}'.",
                               "auto_fix": {"node": j.id, "new_kind": "xor"}})
                break
    return issues


def _dead_ends(model):
    return [{"code": "P4", "severity": "deadlock", "title": "Dead end (no outgoing flow)",
             "nodes": [n.id],
             "message": f"'{model.label(n.id)}' has no outgoing flow, so its token never reaches the end. "
                        "Any join waiting for this path waits for ever.",
             "fix": "Add a recovery path (e.g. resubmission loop) or route it to a coordinated rejection.",
             "auto_fix": None}
            for n in model.nodes.values() if n.kind != "end" and not model.outgoing(n.id)]


def _unreachable(model):
    starts = [n.id for n in model.nodes.values() if n.kind == "start"]
    seen, stack = set(starts), list(starts)
    while stack:
        for f in model.outgoing(stack.pop()):
            if f.tgt not in seen:
                seen.add(f.tgt)
                stack.append(f.tgt)
    return [{"code": "P5", "severity": "warning", "title": "Unreachable element", "nodes": [n.id],
             "message": f"'{model.label(n.id)}' cannot be reached from the start event.",
             "fix": "Connect it to the flow or delete it.", "auto_fix": None}
            for n in model.nodes.values() if n.id not in seen]


def _resource_order(model):
    def res(n, k):
        return [r.strip() for r in n.doc.get(k, "").split(",") if r.strip()]

    order = {}   # (held, taken) -> node id where it happens
    starts = [n.id for n in model.nodes.values() if n.kind == "start"]
    stack = [(s, frozenset()) for s in starts]
    seen = set()
    while stack:
        nid, held = stack.pop()
        if (nid, held) in seen:
            continue
        seen.add((nid, held))
        n = model.nodes[nid]
        for r in res(n, "acquire"):
            for h in held:
                order.setdefault((h, r), nid)
            held = held | {r}
        held = held - set(res(n, "release"))
        for f in model.outgoing(nid):
            stack.append((f.tgt, held))
    issues, done = [], set()
    for (a, b), where in order.items():
        if (b, a) in order and frozenset((a, b)) not in done:
            done.add(frozenset((a, b)))
            other = order[(b, a)]
            issues.append({"code": "P6", "severity": "deadlock", "title": "Resources taken in opposite order",
                           "nodes": [where, other],
                           "message": f"One path holds '{a}' and then requests '{b}' (at '{model.label(where)}'), "
                                      f"another holds '{b}' and then requests '{a}' (at '{model.label(other)}'). "
                                      "If both run together each waits for the other (circular wait).",
                           "fix": f"Take '{a}' and '{b}' in the same order on every path, or add a "
                                  "siphon control place (see Fix step).",
                           "auto_fix": None})
    return issues


def check(model):
    issues = []
    issues += _split_join_mismatch(
        model, ("xor", "or"), "and", "P1", "deadlock", "XOR-split closed by AND-join",
        "'{split}' starts only ONE of its branches, but '{join}' waits for ALL of them.",
        "Replace '{join}' by an XOR-join (merge).")
    issues += _and_join_loops(model)
    issues += _split_join_mismatch(
        model, ("and",), "xor", "P3", "improper completion", "AND-split closed by XOR-join",
        "'{split}' starts ALL its branches, but '{join}' lets each one through on its own, "
        "so the rest of the process runs more than once.",
        "Replace '{join}' by an AND-join (synchronise).")
    issues += _dead_ends(model)
    issues += _unreachable(model)
    issues += _resource_order(model)
    return issues
