"""Streamlit web app - Deadlock Detection and Prevention in Business Process Models.

Run:  streamlit run app.py
"""
from pathlib import Path
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.pipeline import run_pipeline, summary_row
from src.petri_net import PetriNet
from src.reachability import analyse, marking_text
from src.simulate import run_cases
from src.visualize import net_to_dot, graph_to_dot, bpmn_viewer_html
from src.bpmn_parser import parse_bpmn
from src.evolution import detect_changes, summary as change_summary

MODELS = Path(__file__).parent / "models"
st.set_page_config(page_title="BPM Deadlock Analyzer", layout="wide")

LOAN = ["M1_sequential", "M2_parallel", "M3_wrong_join", "M3_fixed", "M4_missing_recovery",
        "M4_fixed", "M5_resource_deadlock", "M5_fixed", "M6_full_timed"]
DEMO = ["D1_order_fulfilment", "D2_insurance_claim", "D3_leave_request",
        "D4_hospital_admission", "D5_purchase_order_loop"]
FIXED_VERSION = {"M3_wrong_join": "M3_fixed", "M4_missing_recovery": "M4_fixed",
                 "M5_resource_deadlock": "M5_fixed"}


@st.cache_data(show_spinner=False)
def read_model(name):
    return (MODELS / f"{name}.bpmn").read_text(encoding="utf-8")


def yn(b):
    return "yes ✅" if b else "no ❌"


def pipeline(xml):
    return run_pipeline(xml)


# ---------------------------------------------------------------- sidebar
st.sidebar.title("BPM Deadlock Analyzer")
st.sidebar.caption("Petri-net based detection and prevention · Loan Approval case study")
source = st.sidebar.radio("Model source", ["Loan approval models", "Demo models", "Upload / paste"])
xml, name = None, None
if source == "Loan approval models":
    name = st.sidebar.selectbox("Model", LOAN, index=4)
    xml = read_model(name)
elif source == "Demo models":
    name = st.sidebar.selectbox("Model", DEMO)
    xml = read_model(name)
else:
    up = st.sidebar.file_uploader("BPMN (.bpmn / .xml) or Petri net (.json)", type=["bpmn", "xml", "json"])
    pasted = st.sidebar.text_area("…or paste BPMN XML", height=120)
    if up is not None:
        text = up.read().decode("utf-8")
        name = up.name
        if up.name.endswith(".json"):
            st.session_state["json_net"] = text
        else:
            xml = text
    elif pasted.strip():
        xml, name = pasted, "pasted model"

step = st.sidebar.radio("Step", ["1 · Process model", "2 · Petri net", "3 · Detect deadlocks",
                                 "4 · Cause & fix", "5 · Token game", "6 · Simulation",
                                 "All models · results"])

# JSON Petri net upload: only the net-level steps make sense
if xml is None and source == "Upload / paste" and st.session_state.get("json_net"):
    net = PetriNet.from_json(st.session_state["json_net"])
    st.title(f"Petri net: {net.name}")
    res = analyse(net)
    c = st.columns(4)
    c[0].metric("Reachable states", res["states"])
    c[1].metric("Deadlocks", len(res["deadlocks"]))
    c[2].metric("Improper ends", len(res["improper"]))
    c[3].metric("Sound", "yes" if res["sound"] else "no")
    st.graphviz_chart(net_to_dot(net))
    for d in res["dead_markings"]:
        st.error(f"{d['kind']}: {marking_text(net, d['marking'])}  ·  trace: "
                 + " → ".join(net.transitions[t].label for t in d["trace"]))
    st.stop()

if xml is None:
    st.title("Deadlock Detection and Prevention in Business Process Models")
    st.info("Pick a model in the sidebar, or upload / paste a BPMN file.")
    st.stop()

try:
    out = pipeline(xml)
except Exception as e:  # bad XML etc.
    st.error(f"Could not read this model: {e}")
    st.stop()

model, net, res, fix = out["model"], out["net"], out["result"], out["fix"]
st.title(model.name)
for w in model.warnings:
    st.warning(w)

status_cols = st.columns(5)
status_cols[0].metric("Reachable states", res["states"])
status_cols[1].metric("Deadlocks", len(res["deadlocks"]))
status_cols[2].metric("Improper ends", len(res["improper"]))
status_cols[3].metric("Structural issues", len(out["issues"]))
status_cols[4].metric("Sound", {"sound": "yes ✅", "unsound": "no ❌"}.get(res["verdict"], "inconclusive ⚠️"))

bad_nodes = sorted({n for i in out["issues"] for n in i["nodes"]} |
                   {n for c in out["causes"] for n in c["bpmn_nodes"]})

# ---------------------------------------------------------------- step 1
if step.startswith("1"):
    st.subheader("Step 1 · Process model (BPMN 2.0)")
    st.caption("Faulty elements found by the analysis are outlined in red.")
    components.html(bpmn_viewer_html(xml, 430, bad_nodes), height=450)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Elements**")
        st.dataframe(pd.DataFrame([{"id": n.id, "type": n.kind, "name": model.label(n.id),
                                    "annotations": "; ".join(f"{k}: {v}" for k, v in n.doc.items())}
                                   for n in model.nodes.values()]), hide_index=True)
    with c2:
        st.markdown("**Sequence flows**")
        st.dataframe(pd.DataFrame([{"id": f.id, "from": model.label(f.src), "to": model.label(f.tgt),
                                    "label": f.name, "annotations": "; ".join(f"{k}: {v}" for k, v in f.doc.items())}
                                   for f in model.flows.values()]), hide_index=True)
        if model.resources:
            st.markdown("**Shared resources**: " + ", ".join(f"{r} = {n}" for r, n in model.resources.items()))
    st.download_button("Download BPMN XML", xml, file_name=f"{name}.bpmn")

# ---------------------------------------------------------------- step 2
elif step.startswith("2"):
    st.subheader("Step 2 · BPMN → Petri net")
    p, t, a = net.size()
    st.caption(f"{p} places · {t} transitions · {a} arcs. Circles are places (conditions), boxes are transitions "
               "(tasks in white, routing in grey), dots are tokens. Blue = source, green = sink, yellow = resource.")
    st.graphviz_chart(net_to_dot(net))
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Places**")
        st.dataframe(pd.DataFrame([{"id": x.id, "meaning": x.label, "kind": x.kind,
                                    "M0": net.m0.get(x.id, 0), "Mf": net.mf.get(x.id, 0)}
                                   for x in net.places.values()]), hide_index=True)
    with c2:
        st.markdown("**Transitions**")
        st.dataframe(pd.DataFrame([{"id": x.id, "label": x.label, "BPMN element": x.bpmn_id,
                                    "inputs": ", ".join(net.pre[x.id]), "outputs": ", ".join(net.post[x.id])}
                                   for x in net.transitions.values()]), hide_index=True)
    if out["mapping_errors"]:
        st.error("Mapping check (Zhang et al., Alg. 1) failed:\n\n" + "\n".join("- " + e for e in out["mapping_errors"]))
    else:
        st.success("Mapping check (Zhang et al., Alg. 1): every BPMN element and connection is mapped.")
    st.download_button("Download Petri net (JSON)", net.to_json(), file_name=f"{name}_petri.json")

# ---------------------------------------------------------------- step 3
elif step.startswith("3"):
    st.subheader("Step 3 · Deadlock detection")
    left, right = st.columns(2)
    with left:
        st.markdown("#### a) Structural check (violation patterns)")
        if not out["issues"]:
            st.success("No structural deadlock pattern found.")
        for i in out["issues"]:
            box = st.error if i["severity"] == "deadlock" else st.warning
            box(f"**{i['code']} · {i['title']}**\n\n{i['message']}")
    with right:
        st.markdown("#### b) State-space analysis (Kräuter et al.)")
        st.write(f"Explored **{res['states']}** markings and **{res['edges']}** firings "
                 f"in {res['time_ms']:.1f} ms.")
        sound_tbl = pd.DataFrame([
            {"Soundness rule": "Option to complete (end always reachable)", "Holds": yn(res["option_to_complete"])},
            {"Soundness rule": "Proper completion (nothing left at the end)", "Holds": yn(res["proper_completion"])},
            {"Soundness rule": "No dead transitions", "Holds": yn(not res["dead_transitions"])},
            {"Soundness rule": "Safeness (no flow holds two tokens)", "Holds": yn(res["safe"])},
        ])
        st.dataframe(sound_tbl, hide_index=True)
        if res["truncated"]:
            st.warning("State limit reached - the verdict is inconclusive, not unsound.")
        if res["unsafe_flows"]:
            st.caption("Unsafe flows: " + ", ".join(net.places[p].label for p in res["unsafe_flows"]))
        if res["dead_transitions"]:
            st.caption("Never fire: " + ", ".join(net.transitions[t].label for t in res["dead_transitions"]))
    if res["dead_markings"]:
        st.markdown("#### Dead markings and witness traces")
        for d in res["dead_markings"][:10]:
            st.error(f"**M{d['index']} · {d['kind']}** - tokens at: {marking_text(net, d['marking'])}\n\n"
                     "Witness trace: " + " → ".join(net.transitions[t].label for t in d["trace"]))
    else:
        st.success("No dead marking other than the correct end state.")
    with st.expander("Reachability graph (red = dead, green = correct end)", expanded=res["states"] <= 40):
        if res["states"] > 150:
            st.caption("Showing the first 150 markings.")
        st.graphviz_chart(graph_to_dot(net, res))

# ---------------------------------------------------------------- step 4
elif step.startswith("4"):
    st.subheader("Step 4 · Cause identification")
    if res["sound"]:
        st.success("This model is sound - nothing to fix.")
    for k, c in enumerate(out["causes"][:3]):
        st.markdown(f"**Dead marking {k + 1} ({c['kind']})** - tokens at: {c['tokens']}")
        for w in c["waiting"]:
            st.write("• " + w["text"])
        st.caption("Path: " + " → ".join(c["trace"]))
    if out["causes"]:
        c = out["causes"][0]
        st.graphviz_chart(net_to_dot(net, c and res["dead_markings"][0]["marking"],
                                     red_places=c["highlight_places"], red_transitions=c["highlight_transitions"]))
    if out["problem_siphons"]:
        st.markdown("**Siphons emptied in the deadlock** (once empty, never refilled):")
        for S in out["problem_siphons"]:
            st.code("{" + ", ".join(sorted(S)) + "}  →  " + ", ".join(net.places[p].label for p in sorted(S)))
    if out["empty_siphons"]:
        st.markdown("**Siphons that start empty** (the transitions needing them can never fire):")
        for S in out["empty_siphons"]:
            st.code("{" + ", ".join(sorted(S)) + "}")

    if fix:
        st.subheader("Step 5 · Prevention rule applied")
        for ch in fix["changes"]:
            st.info("BPMN fix: " + ch)
        for m in fix["monitors"]:
            st.info(f"Control place **{m['place']}** ({m['tokens']} token) added for siphon "
                    f"{{{', '.join(m['siphon'])}}}. It is taken by: {', '.join(m['takes_from'])}; "
                    f"given back by: {', '.join(m['gives_back'])}.")
        for i in out["issues"]:
            if not i.get("auto_fix"):
                st.warning(f"Suggested fix ({i['code']}): {i['fix']}")
        if fix["result"]:
            st.subheader("Step 6 · Re-analysis")
            fr = fix["result"]
            comp = pd.DataFrame([
                {"": "Before", "States": res["states"], "Deadlocks": len(res["deadlocks"]),
                 "Improper ends": len(res["improper"]), "Sound": yn(res["sound"])},
                {"": "After fix", "States": fr["states"], "Deadlocks": len(fr["deadlocks"]),
                 "Improper ends": len(fr["improper"]), "Sound": yn(fr["sound"])}])
            st.dataframe(comp, hide_index=True)
            pm = fix.get("permissiveness")
            if pm:
                st.caption(f"Permissiveness (Wang et al.): the control places keep {pm['kept']} of "
                           f"{pm['good_states']} good states" +
                           (" - maximally permissive." if pm["maximally_permissive"] else "."))
            for a in fix.get("alternatives", []):
                st.info("Alternative quick fix: " + "; ".join(a["changes"]) +
                        f" → {'sound' if a['result']['sound'] else 'unsound'}, {a['result']['states']} states "
                        "(changes the business decision, so it is not applied by default).")
            st.graphviz_chart(net_to_dot(fix["net"]))
            if fix["xml"]:
                st.download_button("Download fixed BPMN", fix["xml"], file_name=f"{name}_autofixed.bpmn")
        if name in FIXED_VERSION:
            other = FIXED_VERSION[name]
            fo = pipeline(read_model(other))
            st.markdown(f"**Hand-corrected model `{other}`** (BPMN-level redesign):")
            components.html(bpmn_viewer_html(read_model(other), 330), height=350)
            st.write(f"States: {fo['result']['states']} · Deadlocks: {len(fo['result']['deadlocks'])} · "
                     f"Sound: {fo['result']['sound']}")
            ops = detect_changes(out["model"], fo["model"])
            cs = change_summary(ops)
            st.caption(f"Evolution operations (Zhang et al., Alg. 2): {cs['insert']} insert, "
                       f"{cs['delete']} delete, {cs['replace']} replace.")

# ---------------------------------------------------------------- token game
elif step.startswith("5"):
    st.subheader("Token game - fire transitions by hand")
    keyname = f"tg_{name}"
    if keyname not in st.session_state:
        st.session_state[keyname] = {"m": dict(net.m0), "log": []}
    tg = st.session_state[keyname]
    en = net.enabled(tg["m"])
    cols = st.columns([3, 1])
    with cols[1]:
        st.markdown("**Enabled transitions**")
        for t in en:
            if st.button(net.transitions[t].label, key=f"fire_{t}"):
                tg["m"] = net.fire(t, tg["m"])
                tg["log"].append(net.transitions[t].label)
                st.rerun()
        if not en:
            final = {p: n for p, n in tg["m"].items() if n} == {p: n for p, n in net.mf.items() if n}
            (st.success if final else st.error)("Correct end reached." if final else "DEADLOCK - nothing can fire.")
        if st.button("Reset"):
            st.session_state[keyname] = {"m": dict(net.m0), "log": []}
            st.rerun()
    with cols[0]:
        st.graphviz_chart(net_to_dot(net, tg["m"], enabled=en))
        st.caption("Fired: " + (" → ".join(tg["log"]) or "nothing yet"))

# ---------------------------------------------------------------- simulation
elif step.startswith("6"):
    st.subheader("Timed simulation (times and branch probabilities)")
    st.caption("Durations come from 'time:' and branch probabilities from 'prob:' in the BPMN documentation fields.")
    n = st.slider("Number of cases", 100, 5000, 1000, 100)
    use_fixed = bool(fix and fix["net"]) and st.checkbox("Simulate the fixed net", value=False)
    sim_net = fix["net"] if use_fixed else net
    sim = run_cases(sim_net, n)
    has_times = any(t.time > 0 for t in sim_net.transitions.values())
    split_labels = {t.bpmn_id for t in sim_net.transitions.values() if ":" in t.label}
    has_probs = any(t.prob != 1.0 for t in sim_net.transitions.values())
    if not has_times:
        st.warning("This model has no task durations ('time:' in the documentation field), so every task takes "
                   "0 minutes and cycle times are not meaningful. Only the completion rate is shown.")
    if split_labels and not has_probs:
        st.info("No branch probabilities ('prob:') are given, so every XOR branch is chosen with equal chance.")
    c = st.columns(4)
    c[0].metric("Completed", f"{sim['completion_rate']:.1%}")
    c[1].metric("Stuck", sim["stuck"])
    show_t = has_times and sim["mean_time"] is not None
    c[2].metric("Mean cycle time (min)", f"{sim['mean_time']:.1f}" if show_t else "-")
    c[3].metric("90th percentile (min)", f"{sim['p90_time']:.1f}" if show_t else "-")
    if show_t:
        times = pd.Series(sim["times"])
        if times.nunique() > 1:
            hist = times.value_counts(bins=min(20, times.nunique()), sort=False)
            st.markdown("**Cycle-time distribution of completed cases**")
            chart = pd.DataFrame({"minutes": [round(iv.mid) for iv in hist.index],   # bin centre, numeric
                                  "cases": hist.values})
            st.bar_chart(chart, x="minutes", y="cases", x_label="Cycle time (minutes)", y_label="Cases")
        else:
            st.caption(f"Every completed case takes {times.iloc[0]:.0f} minutes (the model has no choices).")
    st.markdown("**Average times each task runs per case**")
    st.dataframe(pd.DataFrame(sorted(sim["fire_counts"].items(), key=lambda x: -x[1]),
                              columns=["Transition", "Runs per case"]).round(2), hide_index=True)

# ---------------------------------------------------------------- all models
else:
    st.subheader("Results for all models")
    rows = [summary_row(m, pipeline(read_model(m))) for m in LOAN + DEMO]
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True)
    st.download_button("Download results (CSV)", df.to_csv(index=False), file_name="results.csv")
