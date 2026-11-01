"""Step 2 - map a BPMN model onto a Petri net (workflow net).

Mapping rules (after Mutarraf et al. 2018 / Dijkman et al.):

  BPMN element            Petri net pattern
  ----------------------  ---------------------------------------------------
  sequence flow           one place
  start event             source place 'i' (1 token) + transition i -> out
  end event               transition in -> sink place 'o'
  task                    one transition  in -> out
  AND gateway             one transition  (all inputs -> all outputs)
  XOR split               one transition per outgoing branch
  XOR join                one transition per incoming branch
  OR split                one transition per non-empty subset of branches
  resource                a place holding the free units (e.g. officer = 1)

Initial marking M0 = i + free resources.  Final marking Mf = o + free resources.
"""
from itertools import combinations
from .petri_net import PetriNet


def _flow_place(net, model, f):
    label = f"{model.label(f.src)} → {model.label(f.tgt)}" + (f" [{f.name}]" if f.name else "")
    return net.add_place("p_" + f.id, label, "flow")


def _resources_of(node, key):
    return [r.strip() for r in node.doc.get(key, "").split(",") if r.strip()]


def bpmn_to_petri(model):
    """Return a PetriNet for the given BpmnModel."""
    net = PetriNet(model.name)
    net.add_place("i", "start (source)", "source")
    net.add_place("o", "end (sink)", "sink")
    for r in model.resources:
        net.add_place("r_" + r, f"{r} (free)", "resource")

    fp = {f.id: _flow_place(net, model, f) for f in model.flows.values()}

    for n in model.nodes.values():
        ins = [fp[f.id] for f in model.incoming(n.id)]
        outs_flows = model.outgoing(n.id)
        outs = [fp[f.id] for f in outs_flows]
        label = model.label(n.id)

        if n.kind == "start":
            t = net.add_transition("t_" + n.id, label, bpmn_id=n.id, silent=True)
            net.arc_in("i", t)
            for p in outs:
                net.arc_out(t, p)
            continue

        if n.kind == "end":
            for k, p in enumerate(ins or [None]):
                t = net.add_transition(f"t_{n.id}" + (f"_{k}" if len(ins) > 1 else ""), label,
                                       bpmn_id=n.id, silent=True)
                if p:
                    net.arc_in(p, t)
                net.arc_out(t, "o")
            continue

        # a node with no outgoing flow (and not an end event) is a dead end:
        # its token goes into a "stuck" place that nothing ever consumes.
        if not outs:
            outs = [net.add_place("stuck_" + n.id, f"after '{label}' (no outgoing flow)", "stuck")]

        if n.kind == "task":
            src = ins
            if len(ins) > 1:   # several incoming flows into a task = implicit XOR-merge
                m = net.add_place("m_" + n.id, f"before '{label}'", "internal")
                for k, p in enumerate(ins):
                    tm = net.add_transition(f"t_{n.id}_merge{k}", f"merge into {label}", bpmn_id=n.id, silent=True)
                    net.arc_in(p, tm)
                    net.arc_out(tm, m)
                src = [m]
            t = net.add_transition("t_" + n.id, label, bpmn_id=n.id, time=float(n.doc.get("time", 0)))
            for p in src:
                net.arc_in(p, t)
            for p in outs:
                net.arc_out(t, p)
            for r in _resources_of(n, "acquire") + _resources_of(n, "uses"):
                net.add_place("r_" + r, f"{r} (free)", "resource")
                net.arc_in("r_" + r, t)
            for r in _resources_of(n, "release") + _resources_of(n, "uses"):
                net.add_place("r_" + r, f"{r} (free)", "resource")
                net.arc_out(t, "r_" + r)
            continue

        if n.kind == "and":
            t = net.add_transition("t_" + n.id, label, bpmn_id=n.id, silent=True)
            for p in ins:
                net.arc_in(p, t)
            for p in outs:
                net.arc_out(t, p)
            continue

        # XOR / OR gateway
        src = ins
        if len(ins) > 1 and len(outs) > 1:   # mixed gateway: merge first, then split
            m = net.add_place("m_" + n.id, f"inside '{label}'", "internal")
            for k, p in enumerate(ins):
                tj = net.add_transition(f"t_{n.id}_in{k}", f"{label} (merge)", bpmn_id=n.id, silent=True)
                net.arc_in(p, tj)
                net.arc_out(tj, m)
            src = [m]
        if len(src) > 1:                     # pure join: one transition per incoming branch
            for k, p in enumerate(src):
                tj = net.add_transition(f"t_{n.id}_in{k}", f"{label} (merge)", bpmn_id=n.id, silent=True)
                net.arc_in(p, tj)
                for q in outs:
                    net.arc_out(tj, q)
            continue
        if n.kind == "or" and len(outs) > 1:  # OR split: any non-empty subset of branches
            for size in range(1, len(outs) + 1):
                for combo in combinations(range(len(outs)), size):
                    names = "+".join(outs_flows[c].name or outs_flows[c].id for c in combo)
                    t = net.add_transition(f"t_{n.id}_or{'_'.join(map(str, combo))}", f"{label}: {names}",
                                           bpmn_id=n.id, silent=True)
                    for p in src:
                        net.arc_in(p, t)
                    for c in combo:
                        net.arc_out(t, outs[c])
            continue
        # XOR split (or a gateway with one in / one out)
        for k, p_out in enumerate(outs):
            fl = outs_flows[k] if k < len(outs_flows) else None
            branch = (fl.name or fl.id) if fl else "stuck"
            t = net.add_transition(f"t_{n.id}_out{k}", f"{label}: {branch}" if len(outs) > 1 else label,
                                   bpmn_id=n.id, silent=True,
                                   prob=float(fl.doc.get("prob", 1)) if fl else 1.0)
            for p in src:
                net.arc_in(p, t)
            net.arc_out(t, p_out)

    net.m0 = {"i": 1}
    net.mf = {"o": 1}
    for p in net.places.values():
        if p.kind == "resource":
            r = p.id[2:]
            units = model.resources.get(r, 1)
            net.m0[p.id] = units
            net.mf[p.id] = units
    return net
