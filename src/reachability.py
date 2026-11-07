"""Step 3b - state-space (reachability) analysis.

Following Kraeuter et al. (BPM 2024) we explore the whole state space with a
breadth-first search and check every property on the way.  Like their
"pragmatic encoding", a task is ONE transition (no separate start/end), which
keeps the state space small: for n parallel branches of length m we get
(m+1)^n + 4 states, against (m+1)^n + 3 in their Rust tool.

A marking M is DEAD if no transition is enabled in it.
  * dead and M == Mf                -> normal completion
  * dead, sink 'o' empty            -> DEADLOCK (the case is stuck)
  * dead, sink 'o' marked, M != Mf  -> IMPROPER COMPLETION (tokens left behind)

Soundness of a workflow net (van der Aalst) is also checked:
  1. option to complete : Mf can be reached from every reachable marking
  2. proper completion  : no reachable marking puts a token in 'o' with others left over
  3. no dead transitions: every transition fires in at least one run

Safeness (Kraeuter et al.) is checked as well: no sequence flow may ever hold
two tokens.  An unsafe flow points at a missing synchronisation (e.g. an
AND-split closed by an XOR-join).  It is reported separately and does not
change the soundness verdict.

If the search hits MAX_STATES (or a place exceeds UNBOUNDED_LIMIT) the verdict
is "inconclusive", not "unsound": the part we did not explore may be fine.
"""
from collections import deque
from dataclasses import dataclass, field
import time

MAX_STATES = 20000
UNBOUNDED_LIMIT = 50   # tokens in one place above this -> treat as unbounded


def key(m):
    """A marking as a hashable, sorted tuple (zero places left out)."""
    return tuple(sorted((p, n) for p, n in m.items() if n))


@dataclass
class ReachabilityGraph:
    markings: list = field(default_factory=list)   # index -> marking dict
    edges: list = field(default_factory=list)      # (from_idx, transition_id, to_idx)
    parent: dict = field(default_factory=dict)     # idx -> (prev_idx, transition_id)
    truncated: bool = False
    unbounded: bool = False
    cut: set = field(default_factory=set)          # states whose successors were not explored

    def succ(self):
        s = {i: [] for i in range(len(self.markings))}
        for a, t, b in self.edges:
            s[a].append((t, b))
        return s

    def trace_to(self, idx):
        """Firing sequence (list of transition ids) from M0 to marking idx."""
        seq = []
        while idx in self.parent:
            idx, t = self.parent[idx]
            seq.append(t)
        return list(reversed(seq))


def build_graph(net, max_states=MAX_STATES):
    rg = ReachabilityGraph()
    index = {}
    m0 = {p: n for p, n in net.m0.items() if n}
    rg.markings.append(m0)
    index[key(m0)] = 0
    queue = deque([0])
    while queue:
        i = queue.popleft()
        m = rg.markings[i]
        for t in net.enabled(m):
            m2 = net.fire(t, m)
            k = key(m2)
            if k not in index:
                if len(rg.markings) >= max_states:
                    rg.truncated = True
                    rg.cut.add(i)
                    continue
                if any(n > UNBOUNDED_LIMIT for n in m2.values()):
                    rg.unbounded = True
                    rg.cut.add(i)
                    continue
                index[k] = len(rg.markings)
                rg.markings.append(m2)
                rg.parent[index[k]] = (i, t)
                queue.append(index[k])
            rg.edges.append((i, t, index[k]))
    return rg


def classify(net, m):
    if key(m) == key(net.mf):
        return "final"
    return "improper completion" if m.get("o", 0) >= 1 else "deadlock"


def analyse(net, max_states=MAX_STATES):
    """Run the full reachability analysis and return a result dict."""
    t0 = time.perf_counter()
    rg = build_graph(net, max_states)
    succ = rg.succ()
    final_key = key(net.mf)

    dead = [i for i, out in succ.items() if not out and i not in rg.cut]
    problems = []
    for i in dead:
        kind = classify(net, rg.markings[i])
        if kind != "final":
            problems.append({"index": i, "kind": kind, "marking": rg.markings[i],
                             "trace": rg.trace_to(i)})

    # option to complete: reverse search from the final marking
    finals = [i for i, m in enumerate(rg.markings) if key(m) == final_key]
    can_finish = set(finals)
    rev = {i: [] for i in range(len(rg.markings))}
    for a, _, b in rg.edges:
        rev[b].append(a)
    q = deque(finals)
    while q:
        b = q.popleft()
        for a in rev[b]:
            if a not in can_finish:
                can_finish.add(a)
                q.append(a)
    dead_set = set(dead)
    livelocks = [i for i in range(len(rg.markings)) if i not in can_finish and i not in dead_set]

    proper = not any(m.get("o", 0) >= 1 and key(m) != final_key for m in rg.markings)
    fired = {t for _, t, _ in rg.edges}
    dead_transitions = [t for t in net.transitions if t not in fired]

    option_to_complete = len(can_finish) == len(rg.markings) and not rg.truncated
    sound = option_to_complete and proper and not dead_transitions and not rg.unbounded
    unsafe_flows = sorted({p for m in rg.markings for p, n in m.items()
                           if n > 1 and net.places[p].kind == "flow"})
    if rg.truncated and not problems:
        verdict = "inconclusive"
    else:
        verdict = "sound" if sound else "unsound"
    return {
        "graph": rg,
        "states": len(rg.markings),
        "edges": len(rg.edges),
        "dead_markings": problems,
        "deadlocks": [p for p in problems if p["kind"] == "deadlock"],
        "improper": [p for p in problems if p["kind"] == "improper completion"],
        "livelock_states": livelocks,
        "option_to_complete": option_to_complete,
        "proper_completion": proper,
        "dead_transitions": dead_transitions,
        "final_reachable": bool(finals),
        "sound": sound,
        "verdict": verdict,
        "safe": not unsafe_flows,
        "unsafe_flows": unsafe_flows,
        "truncated": rg.truncated,
        "unbounded": rg.unbounded,
        "time_ms": (time.perf_counter() - t0) * 1000,
    }


def marking_text(net, m):
    return ", ".join(f"{net.places[p].label}" + (f" ×{n}" if n > 1 else "")
                     for p, n in sorted(m.items()) if n) or "(empty)"
