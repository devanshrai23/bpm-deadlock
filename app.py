"""BPMN Deadlock Analyzer - Streamlit front end.

Run locally with:  streamlit run app.py
"""
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.evolution import detect_changes, summary as change_summary
from src.petri_net import PetriNet
from src.pipeline import run_pipeline, summary_row
from src.reachability import analyse, marking_text
from src.simulate import run_cases
from src.visualize import bpmn_viewer_html, graph_to_dot, net_to_dot

MODEL_DIR = Path(__file__).parent / "models"

# model file -> short description shown in the sidebar
LOAN_MODELS = {
    "M1_sequential": "M1 · Sequential",
    "M2_parallel": "M2 · Parallel checks",
    "M3_wrong_join": "M3 · Wrong join (P1)",
    "M3_fixed": "M3 · fixed",
    "M4_missing_recovery": "M4 · Missing recovery path (P4)",
    "M4_fixed": "M4 · fixed",
    "M5_resource_deadlock": "M5 · Resource deadlock (P6)",
    "M5_fixed": "M5 · fixed",
    "M6_full_timed": "M6 · Full model with times",
    "C1_complex": "C1 · Complex, five defects",
    "C1_fixed": "C1 · fixed",
}
DEMO_MODELS = {
    "D1_order_fulfilment": "D1 · Order fulfilment",
    "D2_insurance_claim": "D2 · Insurance claim (P1)",
    "D3_leave_request": "D3 · Leave request (P3)",
    "D4_hospital_admission": "D4 · Hospital admission (P6)",
    "D5_purchase_order_loop": "D5 · Purchase order loop (P2)",
}
# hand-corrected version of each faulty model, shown next to the automatic fix
FIXED_VERSION = {
    "M3_wrong_join": "M3_fixed",
    "M4_missing_recovery": "M4_fixed",
    "M5_resource_deadlock": "M5_fixed",
    "C1_complex": "C1_fixed",
}
PATTERNS = {
    "P1": "XOR-split closed by an AND-join",
    "P2": "AND-join at a loop entry",
    "P3": "AND-split closed by an XOR-join",
    "P4": "Element without outgoing flow",
    "P5": "Unreachable element",
    "P6": "Resources taken in opposite order",
}

st.set_page_config(page_title="BPMN Deadlock Analyzer", page_icon="🔁", layout="wide")


# ---------------------------------------------------------------- cached work

@st.cache_data(show_spinner=False)
def load_model(name):
    return (MODEL_DIR / f"{name}.bpmn").read_text(encoding="utf-8")


@st.cache_resource(show_spinner="Analysing the model...", max_entries=40)
def analyse_model(xml):
    # cache_resource keeps the result object as it is (Petri nets are not copied on every rerun)
    return run_pipeline(xml)


@st.cache_data(show_spinner="Simulating cases...", max_entries=20)
def simulate(xml, use_fixed_net, n_cases):
    out = analyse_model(xml)
    net = out["fix"]["net"] if use_fixed_net else out["net"]
    return run_cases(net, n_cases)


@st.cache_data(show_spinner="Analysing all models...")
def results_table():
    names = list(LOAN_MODELS) + list(DEMO_MODELS)
    return pd.DataFrame([summary_row(n, analyse_model(load_model(n))) for n in names])


# ---------------------------------------------------------------- small helpers

def yes_no(flag):
    return "Yes" if flag else "No"


def verdict_text(res):
    return {"sound": "Sound", "unsound": "Not sound"}.get(res["verdict"], "Inconclusive")


def show_bpmn(xml, height=440, highlight=()):
    components.html(bpmn_viewer_html(xml, height - 20, list(highlight)), height=height)


def trace_text(net, trace):
    return " → ".join(net.transitions[t].label for t in trace) or "(start)"


# ---------------------------------------------------------------- sidebar

def sidebar():
    """Returns (name, xml, json_text). Exactly one of xml / json_text is set, or neither."""
    st.sidebar.title("BPMN Deadlock Analyzer")
    st.sidebar.caption("Detect, explain and fix deadlocks in BPMN models using Petri nets.")

    source = st.sidebar.radio("Models", ["Loan approval case study", "Other domains", "Your own file"])
    if source == "Loan approval case study":
        name = st.sidebar.selectbox("Model", list(LOAN_MODELS), index=4, format_func=LOAN_MODELS.get)
        return name, load_model(name), None
    if source == "Other domains":
        name = st.sidebar.selectbox("Model", list(DEMO_MODELS), format_func=DEMO_MODELS.get)
        return name, load_model(name), None

    upload = st.sidebar.file_uploader("BPMN file (.bpmn, .xml) or Petri net (.json)",
                                      type=["bpmn", "xml", "json"])
    pasted = st.sidebar.text_area("or paste BPMN XML here", height=120)
    if upload is not None:
        text = upload.getvalue().decode("utf-8", errors="replace")
        stem = Path(upload.name).stem
        if upload.name.lower().endswith(".json"):
            return stem, None, text
        return stem, text, None
    if pasted.strip():
        return "pasted_model", pasted, None
    return None, None, None


PAGES = ["Process model", "Petri net", "Deadlock detection", "Cause and fix",
         "Token game", "Simulation", "All models", "About"]


# ---------------------------------------------------------------- pages

def page_model(name, xml, out):
    model = out["model"]
    st.subheader("Process model")
    st.caption("Elements that the analysis points to are outlined in red. Scroll to zoom, drag to move.")
    show_bpmn(xml, 460, out["bad_nodes"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Elements**")
        st.dataframe(pd.DataFrame([
            {"ID": n.id, "Type": n.kind, "Name": model.label(n.id),
             "Annotations": "; ".join(f"{k}: {v}" for k, v in n.doc.items())}
            for n in model.nodes.values()]), hide_index=True, width="stretch")
    with right:
        st.markdown("**Sequence flows**")
        st.dataframe(pd.DataFrame([
            {"ID": f.id, "From": model.label(f.src), "To": model.label(f.tgt), "Label": f.name,
             "Annotations": "; ".join(f"{k}: {v}" for k, v in f.doc.items())}
            for f in model.flows.values()]), hide_index=True, width="stretch")
        if model.resources:
            st.markdown("**Shared resources:** " +
                        ", ".join(f"{r} ({n} unit{'s' if n > 1 else ''})" for r, n in model.resources.items()))
    st.download_button("Download BPMN file", xml, file_name=f"{name}.bpmn")


def page_petri_net(name, xml, out):
    net = out["net"]
    places, transitions, arcs = net.size()
    st.subheader("Petri net")
    st.caption(f"{places} places, {transitions} transitions, {arcs} arcs. Circles are places, boxes are "
               "transitions (grey = routing step), dots are tokens. Blue is the start place, green the end "
               "place, yellow a shared resource.")
    st.graphviz_chart(net_to_dot(net), width="stretch")

    if out["mapping_errors"]:
        st.error("The mapping check found problems:\n\n" + "\n".join(f"- {e}" for e in out["mapping_errors"]))
    else:
        st.success("Mapping check passed: every BPMN element and sequence flow has its place in the net.")

    left, right = st.columns(2)
    with left:
        st.markdown("**Places**")
        st.dataframe(pd.DataFrame([
            {"ID": p.id, "Meaning": p.label, "Kind": p.kind,
             "Initial": net.m0.get(p.id, 0), "Final": net.mf.get(p.id, 0)}
            for p in net.places.values()]), hide_index=True, width="stretch")
    with right:
        st.markdown("**Transitions**")
        st.dataframe(pd.DataFrame([
            {"ID": t.id, "Label": t.label, "BPMN element": t.bpmn_id,
             "Inputs": ", ".join(net.pre[t.id]), "Outputs": ", ".join(net.post[t.id])}
            for t in net.transitions.values()]), hide_index=True, width="stretch")
    st.download_button("Download Petri net (JSON)", net.to_json(), file_name=f"{name}_petri_net.json")


def page_detection(name, xml, out):
    net, res = out["net"], out["result"]
    st.subheader("Deadlock detection")
    left, right = st.columns(2)

    with left:
        st.markdown("##### Structural check")
        st.caption("Looks for known error patterns directly in the diagram.")
        if not out["issues"]:
            st.success("No error pattern found.")
        for issue in out["issues"]:
            box = st.error if issue["severity"] == "deadlock" else st.warning
            box(f"**{issue['code']} - {issue['title']}**\n\n{issue['message']}")

    with right:
        st.markdown("##### State-space analysis")
        st.caption(f"Explored {res['states']} reachable states and {res['edges']} firings "
                   f"in {res['time_ms']:.1f} ms.")
        checks = pd.DataFrame([
            {"Property": "Option to complete", "Meaning": "the end can always be reached",
             "Holds": yes_no(res["option_to_complete"])},
            {"Property": "Proper completion", "Meaning": "nothing is left over at the end",
             "Holds": yes_no(res["proper_completion"])},
            {"Property": "No dead transitions", "Meaning": "every step can happen in some run",
             "Holds": yes_no(not res["dead_transitions"])},
            {"Property": "Safeness", "Meaning": "no sequence flow holds two tokens",
             "Holds": yes_no(res["safe"])},
        ])
        st.dataframe(checks, hide_index=True, width="stretch")
        if res["truncated"]:
            st.warning("The state limit was reached, so the result is inconclusive rather than unsound.")
        if res["unsafe_flows"]:
            st.caption("Flows that can hold two tokens: " +
                       ", ".join(net.places[p].label for p in res["unsafe_flows"]))
        if res["dead_transitions"]:
            st.caption(f"{len(res['dead_transitions'])} transitions never fire: " +
                       ", ".join(net.transitions[t].label for t in res["dead_transitions"][:12]) +
                       (" ..." if len(res["dead_transitions"]) > 12 else ""))

    st.markdown("##### Dead states")
    if not res["dead_markings"]:
        st.success("The process always reaches its end correctly.")
    for d in res["dead_markings"][:10]:
        kind = "Deadlock" if d["kind"] == "deadlock" else "Improper completion"
        st.error(f"**{kind}** (state M{d['index']}). Tokens left at: {marking_text(net, d['marking'])}\n\n"
                 f"How to get there: {trace_text(net, d['trace'])}")
    if len(res["dead_markings"]) > 10:
        st.caption(f"Showing 10 of {len(res['dead_markings'])} dead states.")

    with st.expander("Reachability graph (red = dead state, green = correct end)", expanded=res["states"] <= 40):
        if res["states"] > 150:
            st.caption("The graph is large, so only the first 150 states are drawn.")
        st.graphviz_chart(graph_to_dot(net, res), width="stretch")


def page_fix(name, xml, out):
    net, res, fix = out["net"], out["result"], out["fix"]
    st.subheader("Cause and fix")
    if res["sound"]:
        st.success("This model is sound, so there is nothing to fix.")
        return

    st.markdown("##### Why the process gets stuck")
    for k, cause in enumerate(out["causes"][:3], 1):
        with st.container(border=True):
            st.markdown(f"**Dead state {k}** ({cause['kind']}). Tokens at: {cause['tokens']}")
            for w in cause["waiting"]:
                st.markdown(f"- {w['text']}")
            st.caption("Path: " + " → ".join(cause["trace"]))
    if out["causes"]:
        first = out["causes"][0]
        st.caption("The first dead state in the Petri net. The waiting transitions and the places they need are red.")
        st.graphviz_chart(net_to_dot(net, res["dead_markings"][0]["marking"],
                                     red_places=first["highlight_places"],
                                     red_transitions=first["highlight_transitions"]),
                          width="stretch")
    if out["problem_siphons"]:
        st.markdown("**Circular wait.** These places form a siphon that is empty in the dead state. "
                    "Once empty it can never be filled again:")
        for siphon in out["problem_siphons"]:
            st.code("{" + ", ".join(sorted(siphon)) + "}\n" +
                    "\n".join(f"  {p}: {net.places[p].label}" for p in sorted(siphon)))

    if not fix:
        return
    st.markdown("##### Fix")
    for change in fix["changes"]:
        st.info(f"Gateway changed: {change}")
    for m in fix["monitors"]:
        st.info(f"Control place **{m['place']}** added with {m['tokens']} token. "
                f"Taken by: {', '.join(m['takes_from'])}. Given back by: {', '.join(m['gives_back'])}. "
                "This lets only one branch hold the resources at a time.")
    for issue in out["issues"]:
        if not issue.get("auto_fix"):
            st.warning(f"Needs a manual change ({issue['code']}): {issue['fix']}")

    if fix["result"]:
        after = fix["result"]
        st.markdown("##### Re-analysis")
        st.dataframe(pd.DataFrame([
            {"": "Before", "States": res["states"], "Deadlocks": len(res["deadlocks"]),
             "Improper ends": len(res["improper"]), "Sound": yes_no(res["sound"])},
            {"": "After the fix", "States": after["states"], "Deadlocks": len(after["deadlocks"]),
             "Improper ends": len(after["improper"]), "Sound": yes_no(after["sound"])},
        ]), hide_index=True)
        perm = fix.get("permissiveness")
        if perm and perm["good_states"]:
            note = " Nothing that worked before is blocked." if perm["maximally_permissive"] else ""
            st.caption(f"The control place keeps {perm['kept']} of {perm['good_states']} good states.{note}")
        for alt in fix.get("alternatives", []):
            verdict = "sound" if alt["result"]["sound"] else "not sound"
            st.caption(f"Other option: {'; '.join(alt['changes'])} (also {verdict}, "
                       f"{alt['result']['states']} states). Not applied, because it changes the business decision.")
        with st.expander("Petri net after the fix"):
            st.graphviz_chart(net_to_dot(fix["net"]), width="stretch")
        if fix["xml"]:
            st.download_button("Download fixed BPMN", fix["xml"], file_name=f"{name}_fixed.bpmn")

    if name in FIXED_VERSION:
        other = FIXED_VERSION[name]
        other_out = analyse_model(load_model(other))
        r = other_out["result"]
        st.markdown(f"##### Hand-corrected model ({other})")
        show_bpmn(load_model(other), 360)
        ops = change_summary(detect_changes(out["model"], other_out["model"]))
        st.caption(f"{r['states']} states, {len(r['deadlocks'])} deadlocks, {verdict_text(r).lower()}. "
                   f"Changes from the faulty model: {ops['insert']} added, {ops['delete']} removed, "
                   f"{ops['replace']} changed elements.")


def page_token_game(name, xml, out):
    net = out["net"]
    st.subheader("Token game")
    st.caption("Fire the enabled transitions yourself and watch where the case gets stuck.")
    key = f"token_game_{name}"
    if key not in st.session_state:
        st.session_state[key] = {"marking": dict(net.m0), "history": []}
    game = st.session_state[key]
    enabled = net.enabled(game["marking"])

    graph_col, control_col = st.columns([3, 1])
    with control_col:
        st.markdown("**Can fire now**")
        for t in enabled:
            if st.button(net.transitions[t].label, key=f"fire_{t}", width="stretch"):
                game["history"].append(dict(game["marking"]))
                game["marking"] = net.fire(t, game["marking"])
                st.rerun()
        if not enabled:
            reached_end = ({p: n for p, n in game["marking"].items() if n} ==
                           {p: n for p, n in net.mf.items() if n})
            if reached_end:
                st.success("The case finished correctly.")
            else:
                st.error("Stuck: nothing can fire, but the case has not finished.")
        undo, reset = st.columns(2)
        if undo.button("Undo", disabled=not game["history"], width="stretch"):
            game["marking"] = game["history"].pop()
            st.rerun()
        if reset.button("Reset", width="stretch"):
            st.session_state[key] = {"marking": dict(net.m0), "history": []}
            st.rerun()
    with graph_col:
        st.graphviz_chart(net_to_dot(net, game["marking"], enabled=enabled), width="stretch")
        st.caption(f"Steps fired so far: {len(game['history'])}. Enabled transitions are green.")


def page_simulation(name, xml, out):
    fix = out["fix"]
    st.subheader("Simulation")
    st.caption("Runs many cases with the task durations (time:) and branch probabilities (prob:) "
               "written in the BPMN documentation fields.")
    left, right = st.columns([2, 1])
    n_cases = left.slider("Number of cases", 100, 5000, 1000, step=100)
    can_use_fix = bool(fix and fix["net"])
    use_fixed = right.toggle("Use the fixed net", value=False, disabled=not can_use_fix,
                             help=None if can_use_fix else "This model has no automatic fix.")
    net = fix["net"] if use_fixed else out["net"]
    sim = simulate(xml, use_fixed, n_cases)

    has_times = any(t.time > 0 for t in net.transitions.values())
    has_choices = any(":" in t.label for t in net.transitions.values())
    has_probs = any(t.prob != 1.0 for t in net.transitions.values())
    if not has_times:
        st.info("This model has no task durations, so only the completion rate is meaningful.")
    if has_choices and not has_probs:
        st.info("No branch probabilities are given, so each XOR branch is equally likely.")

    show_times = has_times and sim["mean_time"] is not None
    cols = st.columns(4)
    cols[0].metric("Completed", f"{sim['completion_rate']:.0%}")
    cols[1].metric("Stuck cases", sim["stuck"])
    cols[2].metric("Mean cycle time", f"{sim['mean_time']:.1f} min" if show_times else "-")
    cols[3].metric("90th percentile", f"{sim['p90_time']:.0f} min" if show_times else "-")

    if show_times:
        times = pd.Series(sim["times"])
        if times.nunique() > 1:
            hist = times.value_counts(bins=min(20, times.nunique()), sort=False)
            chart = pd.DataFrame({"Cycle time (min)": [round(b.mid) for b in hist.index], "Cases": hist.values})
            st.bar_chart(chart, x="Cycle time (min)", y="Cases")
        else:
            st.caption(f"Every completed case takes {times.iloc[0]:.0f} minutes.")
    with st.expander("How often each step runs per case"):
        st.dataframe(pd.DataFrame(sorted(sim["fire_counts"].items(), key=lambda kv: -kv[1]),
                                  columns=["Step", "Runs per case"]).round(2), hide_index=True)


def page_all_models(*_):
    st.title("All models")
    st.caption("Every model in the repository, analysed with the same settings.")
    table = results_table()
    short = table[["Model", "Places", "Transitions", "States", "Deadlocks", "Improper ends", "Sound",
                   "Safe", "Structural issues", "Sound after fix", "States after fix"]].copy()
    short["States after fix"] = short["States after fix"].map(lambda v: "-" if pd.isna(v) else str(int(v)))
    st.dataframe(short, hide_index=True, width="stretch", height=36 * (len(short) + 1) + 4)
    st.download_button("Download full results (CSV)", table.to_csv(index=False), file_name="results.csv")


def page_about(*_):
    st.title("About")
    st.markdown("""
This tool was built for the Business Process Management course project at IIIT Allahabad.
It takes a BPMN 2.0 model and checks whether every case can finish. When a case can get stuck,
it shows where and why, suggests or applies a fix, and checks the fixed model again.

**How it works**

1. **Process model.** A BPMN file from Camunda Modeler or bpmn.io. Durations, probabilities and
   resources go in the documentation field of an element (`time: 20`, `prob: 0.3`, `acquire: officer`).
2. **Petri net.** Every sequence flow becomes a place and every task a transition.
3. **Detection.** A quick structural check for known error patterns, then a full search of all
   reachable states for deadlocks, improper completion and unsafe flows.
4. **Cause.** For each dead state, which step is waiting and for what. Circular waits on
   resources are traced to an empty siphon.
5. **Fix.** Mismatched gateways are corrected in the BPMN file. Circular waits get a control place.
6. **Re-check.** The fixed model goes through steps 2 and 3 again.
""")
    st.markdown("**Error patterns**")
    st.dataframe(pd.DataFrame([{"Code": c, "Pattern": p} for c, p in PATTERNS.items()]), hide_index=True)
    st.markdown("""
**Based on**

- T. Kräuter et al., *Instantaneous, Comprehensible, and Fixable Soundness Checking of Realistic BPMN Models*, 2024
- Z. Zhang et al., *Collaborative Modeling of BPMN and HCPN*, Information 16(4), 2025
- S. G. Wang et al., *A Refined Siphon-Based Deadlock Prevention Policy for a Class of Petri Nets*, IEEE TSMC: Systems 53(1), 2023
- W. M. P. van der Aalst, *The Application of Petri Nets to Workflow Management*, 1998

**Team:** Devansh Rai, Geethika Gorakala, Abhilasha Sharma

Source code: [github.com/devanshrai23/bpm-deadlock](https://github.com/devanshrai23/bpm-deadlock)
""")


PAGE_FUNCS = dict(zip(PAGES, [page_model, page_petri_net, page_detection, page_fix,
                              page_token_game, page_simulation, page_all_models, page_about]))


# ---------------------------------------------------------------- uploaded Petri net (JSON)

def show_json_net(name, text):
    try:
        net = PetriNet.from_json(text)
    except Exception as err:
        st.error(f"Could not read this Petri net: {err}")
        return
    res = analyse(net)
    st.title(net.name or name)
    st.caption("An uploaded Petri net has no BPMN diagram, so only the net-level analysis is shown here.")
    cols = st.columns(4)
    cols[0].metric("Reachable states", res["states"])
    cols[1].metric("Deadlocks", len(res["deadlocks"]))
    cols[2].metric("Improper ends", len(res["improper"]))
    cols[3].metric("Result", verdict_text(res))
    st.graphviz_chart(net_to_dot(net), width="stretch")
    for d in res["dead_markings"]:
        st.error(f"{d['kind'].capitalize()}: {marking_text(net, d['marking'])}\n\n"
                 f"How to get there: {trace_text(net, d['trace'])}")


# ---------------------------------------------------------------- main

def main():
    name, xml, json_text = sidebar()
    page = st.sidebar.radio("Page", PAGES)
    st.sidebar.divider()
    st.sidebar.caption("BPM course project · IIIT Allahabad")

    if page in ("All models", "About"):   # these pages do not depend on the selected model
        PAGE_FUNCS[page]()
        return
    if json_text is not None:
        show_json_net(name, json_text)
        return
    if xml is None:
        st.info("Choose a model in the sidebar, or upload your own BPMN file.")
        page_about()
        return

    try:
        out = analyse_model(xml)
    except Exception as err:
        st.error(f"Could not read this model. Is it a valid BPMN 2.0 file?\n\n{err}")
        return
    out["bad_nodes"] = sorted({n for i in out["issues"] for n in i["nodes"]} |
                              {n for c in out["causes"] for n in c["bpmn_nodes"]})

    model, res = out["model"], out["result"]
    st.title(model.name or name)
    for warning in model.warnings:
        st.warning(warning)
    cols = st.columns(5)
    cols[0].metric("Reachable states", res["states"])
    cols[1].metric("Deadlocks", len(res["deadlocks"]))
    cols[2].metric("Improper ends", len(res["improper"]))
    cols[3].metric("Error patterns", len(out["issues"]))
    cols[4].metric("Result", verdict_text(res))

    PAGE_FUNCS[page](name, xml, out)


main()
