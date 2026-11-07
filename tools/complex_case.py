"""Iterative round-by-round repair evaluation on complex model C1."""
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.bpmn_parser import parse_bpmn, NS  # noqa: E402
from src.transformer import bpmn_to_petri, check_mapping  # noqa: E402
from src.structural import check  # noqa: E402
from src.reachability import analyse  # noqa: E402
from src.siphons import problem_siphons  # noqa: E402
from src.prevention import fix_gateways, add_monitors, permissiveness  # noqa: E402
from src.evolution import detect_changes, summary  # noqa: E402

MODELS = ROOT / "models"


def redesign_dead_end(xml_text):
    """Round 2 (manual, a business decision): connect 'Refer to manager' via a
    new task 'Manager decision' to the merge of the normal outcomes."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    proc = root.find(f"{{{NS}}}process")
    task = ET.SubElement(proc, f"{{{NS}}}task", id="manager", name="Manager decision")
    ET.SubElement(task, f"{{{NS}}}documentation").text = "time: 30"
    ET.SubElement(proc, f"{{{NS}}}sequenceFlow", id="f36", sourceRef="refer", targetRef="manager")
    ET.SubElement(proc, f"{{{NS}}}sequenceFlow", id="f37", sourceRef="manager", targetRef="dec_join")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def _row(rnd, action, model, net, res, issues):
    p, t, a = net.size()
    return {"Round": rnd, "Action": action, "Places": p, "Transitions": t, "States": res["states"],
            "Deadlocks": len(res["deadlocks"]), "Improper ends": len(res["improper"]),
            "Dead transitions": len(res["dead_transitions"]), "Safe": "yes" if res["safe"] else "no",
            "Sound": "yes" if res["sound"] else "no",
            "Structural issues": ", ".join(sorted({i["code"] for i in issues})) if issues is not None else "-",
            "Mapping errors": len(check_mapping(model, net)) if model is not None else "-"}


def rounds():
    """Run the whole iterative process. Returns (rows, details)."""
    xml0 = (MODELS / "C1_complex.bpmn").read_text()
    m0 = parse_bpmn(xml0)
    n0 = bpmn_to_petri(m0)
    r0 = analyse(n0)
    i0 = check(m0)
    rows = [_row(0, "Original model (five defects)", m0, n0, r0, i0)]

    # round 1: gateway quick fixes
    xml1, changes = fix_gateways(xml0, i0, {n: m0.label(n) for n in m0.nodes})
    m1 = parse_bpmn(xml1)
    n1 = bpmn_to_petri(m1)
    r1 = analyse(n1)
    rows.append(_row(1, "Quick fixes: risk join and loop entry AND -> XOR (P1, P2); notification merge XOR -> AND (P3)",
                     m1, n1, r1, check(m1)))

    # round 2: manual redesign of the dead end
    xml2 = redesign_dead_end(xml1)
    m2 = parse_bpmn(xml2)
    n2 = bpmn_to_petri(m2)
    r2 = analyse(n2)
    rows.append(_row(2, "Redesign P4: Refer to manager -> Manager decision -> outcome merge", m2, n2, r2, check(m2)))

    # round 3: siphon control place
    siph = problem_siphons(n2, r2["dead_markings"])
    n3, monitors = add_monitors(n2, siph)
    r3 = analyse(n3)
    perm = permissiveness(n2, r2, n3, r3)
    rows.append(_row(3, f"Control place V1 for siphon {{{', '.join(sorted(siph[0]))}}}", None, n3, r3, None))

    # final: hand-corrected BPMN model
    xmlf = (MODELS / "C1_fixed.bpmn").read_text()
    mf = parse_bpmn(xmlf)
    nf = bpmn_to_petri(mf)
    rf = analyse(nf)
    rows.append(_row("final", "C1_fixed: all five repaired in BPMN (same resource order on both branches)",
                     mf, nf, rf, check(mf)))

    details = {"original": (m0, n0, r0, i0), "round1": (n1, r1, changes), "round2": (n2, r2),
               "round3": (n3, r3, monitors, perm, siph), "final": (mf, nf, rf),
               "changes_total": summary(detect_changes(m0, mf))}
    return rows, details


if __name__ == "__main__":
    import pandas as pd
    from src.reachability import marking_text
    from src.diagnosis import explain
    from src.visualize import net_to_dot

    rows, d = rounds()
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "complex_case.csv", index=False)
    print(df.drop(columns=["Action"]).to_string(index=False))
    for r in rows:
        print(f"  round {r['Round']}: {r['Action']}")

    m0, n0, r0, i0 = d["original"]
    print("\nStructural issues in the original model:")
    for i in i0:
        print(f"  {i['code']}: {i['message']}")
    print("\nDead markings of the original model:")
    for k, dm in enumerate(r0["dead_markings"]):
        print(f"  D{k + 1}: {marking_text(n0, dm['marking'])}")
        print("      trace:", " -> ".join(n0.transitions[t].label for t in dm["trace"]))
    for name in ("round1", "round2"):
        net, res = d[name][0], d[name][1]
        print(f"\nDead markings after {name}:")
        for dm in res["dead_markings"]:
            print("  ", marking_text(net, dm["marking"]))
            print("      trace:", " -> ".join(net.transitions[t].label for t in dm["trace"]))
    n3, r3, mon, perm, siph = d["round3"]
    print("\nMonitor:", mon)
    print("Permissiveness of V1:", perm)
    print("Change operations C1_complex -> C1_fixed:", d["changes_total"])

    # figures: Petri net of the original model with its first dead marking highlighted, and with the monitor
    fig = ROOT / "results" / "figures"
    c = explain(n0, r0["dead_markings"][0])
    # for the report: only the part up to the main AND-join, where all three deadlocks occur
    after = {"decide", "outcome", "approve", "reject", "refer", "dec_join", "notify_split", "email", "sms",
             "notify_join", "archive", "end"}
    part = n0.copy()
    for t in [t for t, tr in part.transitions.items() if tr.bpmn_id in after]:
        del part.transitions[t], part.pre[t], part.post[t]
    used = {p for t in part.transitions for p in (*part.pre[t], *part.post[t])}
    for p in [p for p in part.places if p not in used]:
        del part.places[p]
    if shutil.which("dot"):
        for src, out in [(net_to_dot(n0, r0["dead_markings"][0]["marking"], c["highlight_places"],
                                     c["highlight_transitions"]), "pn_C1_complex_dead"),
                         (net_to_dot(part, r0["dead_markings"][0]["marking"], c["highlight_places"],
                                     c["highlight_transitions"]), "pn_C1_complex_dead_part"),
                         (net_to_dot(n3), "pn_C1_round3_monitored")]:
            subprocess.run(["dot", "-Tpng", "-Gdpi=170", "-o", str(fig / f"{out}.png")], input=src.encode(), check=True)
        print("figures written to", fig)
    else:
        print("Graphviz 'dot' not installed; skipped figure generation.")
