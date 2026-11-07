def preset(net, S):
    return {t for t in net.transitions if any(p in S for p in net.post[t])}

def postset(net, S):
    return {t for t in net.transitions if any(p in S for p in net.pre[t])}

def is_siphon(net, S):
    return bool(S) and preset(net, S) <= postset(net, S)

def minimal_siphons(net, exclude=("i",), limit=200):
    exclude = set(exclude)
    found = []

    def grow(S, depth=0):
        if len(found) >= limit or depth > len(net.places):
            return
        bad = next((t for t in preset(net, S) if not any(p in S for p in net.pre[t])), None)
        if bad is None:
            fs = frozenset(S)
            if not any(f <= fs for f in found):
                found[:] = [f for f in found if not fs <= f] + [fs]
            return
        for p in sorted(net.pre[bad]):
            if p not in exclude:
                grow(S | {p}, depth + 1)

    for p in sorted(net.places):
        if p not in exclude:
            grow({p})
    return sorted([set(s) for s in found], key=lambda s: (len(s), sorted(s)))


def tokens_in(m, S):
    return sum(m.get(p, 0) for p in S)


def problem_siphons(net, dead_markings):
    out = []
    for S in minimal_siphons(net):
        if tokens_in(net.m0, S) == 0:
            continue
        if any(tokens_in(d["marking"], S) == 0 for d in dead_markings):
            out.append(S)
    return out
