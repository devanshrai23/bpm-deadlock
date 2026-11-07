from dataclasses import dataclass, field
import copy
import json


@dataclass
class Place:
    id: str
    label: str
    kind: str = "flow"     # source | sink | flow | internal | resource | stuck | monitor


@dataclass
class Transition:
    id: str
    label: str
    bpmn_id: str = ""
    time: float = 0.0      # duration used by the simulation
    prob: float = 1.0      # branch weight used by the simulation
    silent: bool = False   # routing transition (gateway / event), not a real task


@dataclass
class PetriNet:
    name: str
    places: dict = field(default_factory=dict)        # id -> Place
    transitions: dict = field(default_factory=dict)   # id -> Transition
    pre: dict = field(default_factory=dict)           # t -> {p: weight}  (input arcs)
    post: dict = field(default_factory=dict)          # t -> {p: weight}  (output arcs)
    m0: dict = field(default_factory=dict)
    mf: dict = field(default_factory=dict)

    # ---- building -------------------------------------------------------
    def add_place(self, pid, label, kind="flow"):
        if pid not in self.places:
            self.places[pid] = Place(pid, label, kind)
        return pid

    def add_transition(self, tid, label, **kw):
        base, k = tid, 2
        while tid in self.transitions:       # keep ids unique
            tid, k = f"{base}_{k}", k + 1
        self.transitions[tid] = Transition(tid, label, **kw)
        self.pre[tid], self.post[tid] = {}, {}
        return tid

    def arc_in(self, p, t, w=1):           # place -> transition
        self.pre[t][p] = self.pre[t].get(p, 0) + w

    def arc_out(self, t, p, w=1):          # transition -> place
        self.post[t][p] = self.post[t].get(p, 0) + w

    # ---- firing rule ----------------------------------------------------
    def is_enabled(self, t, m):
        return all(m.get(p, 0) >= w for p, w in self.pre[t].items())

    def enabled(self, m):
        """All transitions that can fire in marking m."""
        return [t for t in self.transitions if self.is_enabled(t, m)]

    def fire(self, t, m):
        """Fire t in m and return the new marking (m is not changed)."""
        if not self.is_enabled(t, m):
            raise ValueError(f"{t} is not enabled")
        new = dict(m)
        for p, w in self.pre[t].items():
            new[p] -= w
        for p, w in self.post[t].items():
            new[p] = new.get(p, 0) + w
        return {p: n for p, n in new.items() if n}

    # ---- helpers --------------------------------------------------------
    def preset_of_place(self, p):     # transitions that put tokens into p
        return [t for t in self.transitions if p in self.post[t]]

    def postset_of_place(self, p):    # transitions that take tokens from p
        return [t for t in self.transitions if p in self.pre[t]]

    def copy(self):
        return copy.deepcopy(self)

    def size(self):
        arcs = sum(len(v) for v in self.pre.values()) + sum(len(v) for v in self.post.values())
        return len(self.places), len(self.transitions), arcs

    def to_json(self):
        return json.dumps({
            "name": self.name,
            "places": [{"id": p.id, "label": p.label, "kind": p.kind} for p in self.places.values()],
            "transitions": [{"id": t.id, "label": t.label, "time": t.time, "prob": t.prob}
                            for t in self.transitions.values()],
            "arcs": [[p, t, w] for t in self.pre for p, w in self.pre[t].items()] +
                    [[t, p, w] for t in self.post for p, w in self.post[t].items()],
            "initial_marking": self.m0, "final_marking": self.mf}, indent=2)

    @staticmethod
    def from_json(text):
        d = json.loads(text)
        net = PetriNet(d.get("name", "net"))
        for p in d["places"]:
            p = p if isinstance(p, dict) else {"id": p, "label": p}
            net.add_place(p["id"], p.get("label", p["id"]), p.get("kind", "flow"))
        for t in d["transitions"]:
            t = t if isinstance(t, dict) else {"id": t, "label": t}
            net.add_transition(t["id"], t.get("label", t["id"]), time=t.get("time", 0), prob=t.get("prob", 1))
        for a in d["arcs"]:
            src, dst, w = (a + [1])[:3]
            if src in net.places:
                net.arc_in(src, dst, w)
            else:
                net.arc_out(src, dst, w)
        net.m0 = dict(d["initial_marking"])
        net.mf = dict(d["final_marking"])
        return net
