"""Step 4 (resources) - siphons (definition as in Wang et al., IEEE TSMC 2023).

A non-empty set of places S is a SIPHON if every transition that puts a
token into S also takes a token from S       ( pre-set(S) is a subset of post-set(S) ).
So once a siphon is empty it can never get a token again, and every
transition that needs one of its places is dead for ever.  An empty siphon
is the classic signature of a resource (circular-wait) deadlock.

Wang et al. find the emptiable siphons with mixed-integer programming, so that
neither all siphons nor the reachability graph are needed.  Our nets are small,
so we enumerate minimal siphons and keep those that are empty in a dead marking
found by the state-space analysis.  Replacing this step with their MIP is
future work for large models.
"""


def preset(net, S):
    return {t for t in net.transitions if any(p in S for p in net.post[t])}


def postset(net, S):
    return {t for t in net.transitions if any(p in S for p in net.pre[t])}


def is_siphon(net, S):
    return bool(S) and preset(net, S) <= postset(net, S)


def minimal_siphons(net, exclude=("i",), limit=200):
    """Find minimal siphons by growing a set place by place.

    Starting from one place, while some transition t feeds S without taking
    from S, we must add one of t's input places (one branch per choice).
    Siphons that would need an excluded place (the source 'i', which empties
    by design in every workflow net) are skipped.
    """
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
    """Minimal siphons that start marked but are empty in some dead marking."""
    out = []
    for S in minimal_siphons(net):
        if tokens_in(net.m0, S) == 0:
            continue
        if any(tokens_in(d["marking"], S) == 0 for d in dead_markings):
            out.append(S)
    return out
