"""Runs the whole 6-step framework on one BPMN model.

  1 model   -> 2 Petri net -> 3 detect -> 4 find cause -> 5 fix -> 6 re-check
"""
from .bpmn_parser import parse_bpmn
from .transformer import bpmn_to_petri
from .structural import check
from .reachability import analyse
from .siphons import problem_siphons, minimal_siphons, tokens_in
from .diagnosis import explain
from .prevention import fix_gateways, add_monitors


def run_pipeline(xml_text):
    model = parse_bpmn(xml_text)                       # step 1
    net = bpmn_to_petri(model)                         # step 2
    issues = check(model)                              # step 3a
    result = analyse(net)                              # step 3b
    causes = [explain(net, d) for d in result["dead_markings"][:10]]   # step 4
    psiphons = problem_siphons(net, result["dead_markings"])
    empty_siphons = [S for S in minimal_siphons(net) if tokens_in(net.m0, S) == 0
                     and any(net.postset_of_place(p) for p in S)]

    out = {"model": model, "net": net, "issues": issues, "result": result,
           "causes": causes, "problem_siphons": psiphons, "empty_siphons": empty_siphons,
           "fix": None}

    if result["sound"]:
        return out

    # step 5 - fixes
    fix = {"changes": [], "monitors": [], "xml": None, "net": None, "result": None, "manual": []}
    fixed_xml, changes = fix_gateways(xml_text, issues, {n: model.label(n) for n in model.nodes})
    fixed_net = net
    if changes:
        fix["xml"] = fixed_xml
        fix["changes"] = changes
        fixed_net = bpmn_to_petri(parse_bpmn(fixed_xml))
    fixed_result = analyse(fixed_net)
    # resource deadlocks: add control places until no problem siphon is left
    for _ in range(3):
        ps = problem_siphons(fixed_net, fixed_result["dead_markings"])
        if not ps:
            break
        fixed_net, added = add_monitors(fixed_net, ps)
        fix["monitors"] += added
        fixed_result = analyse(fixed_net)
    fix["manual"] = [i for i in issues if not i.get("auto_fix") and i["code"] in ("P4", "P5")]
    if changes or fix["monitors"]:
        fix["net"], fix["result"] = fixed_net, fixed_result    # step 6
    out["fix"] = fix
    return out


def summary_row(name, out):
    r = out["result"]
    p, t, a = out["net"].size()
    row = {"Model": name, "Places": p, "Transitions": t, "Arcs": a, "States": r["states"],
           "Deadlocks": len(r["deadlocks"]), "Improper ends": len(r["improper"]),
           "Sound": "yes" if r["sound"] else "no",
           "Structural issues": ", ".join(sorted({i["code"] for i in out["issues"]})) or "-",
           "Time (ms)": round(r["time_ms"], 1)}
    fx = out["fix"]
    if fx and fx["result"]:
        fr = fx["result"]
        row["Auto fix"] = "; ".join(fx["changes"] + [f"monitor {m['place']}" for m in fx["monitors"]])
        row["Sound after fix"] = "yes" if fr["sound"] else "no"
        row["States after fix"] = fr["states"]
    else:
        row["Auto fix"] = "-" if r["sound"] else "manual (see fixed model)"
        row["Sound after fix"] = "-"
        row["States after fix"] = None
    return row
