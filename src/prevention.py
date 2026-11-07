"""Deadlock prevention and correction rules for gateways and resources."""
import xml.etree.ElementTree as ET
from .bpmn_parser import NS
from .siphons import tokens_in

for prefix, uri in {"bpmn": NS, "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
                    "dc": "http://www.omg.org/spec/DD/20100524/DC",
                    "di": "http://www.omg.org/spec/DD/20100524/DI",
                    "camunda": "http://camunda.org/schema/1.0/bpmn",
                    "modeler": "http://camunda.org/schema/modeler/1.0",
                    "xsi": "http://www.w3.org/2001/XMLSchema-instance"}.items():
    ET.register_namespace(prefix, uri)

GATEWAY_TAG = {"xor": "exclusiveGateway", "and": "parallelGateway"}


def fix_gateways(xml_text, issues, labels=None):
    """Apply the automatic gateway fixes. Returns (new_xml, list_of_changes)."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    changes = []
    targets = {}
    for iss in issues:
        af = iss.get("auto_fix")
        if af:
            targets[af["node"]] = af["new_kind"]
    for el in root.iter():
        nid = el.get("id")
        if nid in targets and el.tag.endswith("Gateway"):
            old = el.tag.split("}")[1]
            new = GATEWAY_TAG[targets[nid]]
            if old != new:
                el.tag = f"{{{NS}}}{new}"
                el.attrib.pop("gatewayDirection", None)
                name = (labels or {}).get(nid) or el.get("name") or nid
                changes.append(f"Gateway '{name}': {old} → {new}")
    new_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    return new_xml, changes


def alternative_fixes(issues):
    """The split-side quick fix for each P1/P3 issue (Kraeuter et al.)."""
    alts = []
    for iss in issues:
        if iss["code"] in ("P1", "P3") and iss.get("auto_fix"):
            split = iss["nodes"][0]
            alts.append({**iss, "auto_fix": {"node": split, "new_kind": "and" if iss["code"] == "P1" else "xor"}})
    return alts


def permissiveness(net, result, fixed_net, fixed_result):
    """How much good behaviour a monitor keeps (Wang et al.: maximal permissiveness).

    A state of the original net is GOOD if the final marking can still be
    reached from it.  We project every reachable state of the controlled net onto
    the original places and count how many good states survive.  A controller
    is maximally permissive when it keeps all of them (ratio 1.0).
    """
    from .reachability import key
    bad = {d["index"] for d in result["dead_markings"]} | set(result["livelock_states"])
    good = {key(m) for i, m in enumerate(result["graph"].markings) if i not in bad}
    kept = {key({p: n for p, n in m.items() if p in net.places}) for m in fixed_result["graph"].markings}
    monitor_weights = [w for t in fixed_net.transitions
                       for arcs in (fixed_net.pre[t], fixed_net.post[t])
                       for p, w in arcs.items() if fixed_net.places[p].kind == "monitor"]
    return {"good_states": len(good), "kept": len(good & kept), "ratio": len(good & kept) / max(len(good), 1),
            "maximally_permissive": good <= kept, "unit_weights": all(w == 1 for w in monitor_weights)}


def add_monitors(net, siphons):
    """Add one control place V_S per siphon S so S can never become empty.

    This is the siphon-control step of Wang et al. (IEEE TSMC 2023, stage 2).
    Their stage 1 finds the siphons with mixed-integer programming; we find them
    from the dead markings instead (siphons.problem_siphons).  For our nets every
    resource has one unit, the class Wang et al. study, and all monitor arcs
    then have weight 1, as in their policy.

    For every transition t let d(t) = tokens t puts into S - tokens t takes from S.
    The monitor V_S gets an arc  t -> V_S  of weight d(t) when d(t) > 0
    and an arc  V_S -> t  of weight -d(t) when d(t) < 0,  with
    M0(V_S) = M0(S) - 1.   Then M(V_S) - M(S) stays equal to -1 in every
    reachable marking, so M(S) = M(V_S) + 1 >= 1: S is never emptied.
    """
    fixed = net.copy()
    added = []
    for k, S in enumerate(siphons, 1):
        v = f"V{k}"
        fixed.add_place(v, f"control place V{k} for siphon {{{', '.join(sorted(S))}}}", "monitor")
        for t in fixed.transitions:
            d = sum(fixed.post[t].get(p, 0) for p in S) - sum(fixed.pre[t].get(p, 0) for p in S)
            if d > 0:
                fixed.arc_out(t, v, d)
            elif d < 0:
                fixed.arc_in(v, t, -d)
        tokens = tokens_in(net.m0, S) - 1
        fixed.m0[v] = tokens
        fixed.mf[v] = tokens_in(net.mf, S) - 1
        added.append({"place": v, "siphon": sorted(S), "tokens": tokens,
                      "takes_from": [fixed.transitions[t].label for t in fixed.transitions if v in fixed.pre[t]],
                      "gives_back": [fixed.transitions[t].label for t in fixed.transitions if v in fixed.post[t]]})
    return fixed, added
