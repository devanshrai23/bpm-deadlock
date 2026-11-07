"""Generates result tables and report figures."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from src.pipeline import run_pipeline, summary_row  # noqa: E402
from src.simulate import run_cases  # noqa: E402
from src.visualize import net_to_dot, graph_to_dot  # noqa: E402

OUT = ROOT / "results"
FIG = OUT / "figures"
FIG.mkdir(parents=True, exist_ok=True)
ORDER = ["M1_sequential", "M2_parallel", "M3_wrong_join", "M3_fixed", "M4_missing_recovery", "M4_fixed",
         "M5_resource_deadlock", "M5_fixed", "M6_full_timed", "D1_order_fulfilment", "D2_insurance_claim",
         "D3_leave_request", "D4_hospital_admission", "D5_purchase_order_loop", "C1_complex", "C1_fixed"]


def dot(src, name, extra=()):
    subprocess.run(["dot", "-Tpng", "-Gdpi=170", *extra, "-o", str(FIG / f"{name}.png")],
                   input=src.encode(), check=True)


outs = {m: run_pipeline((ROOT / "models" / f"{m}.bpmn").read_text()) for m in ORDER}
df = pd.DataFrame([summary_row(m, outs[m]) for m in ORDER])
df.to_csv(OUT / "results.csv", index=False)
print(df.to_string())

# Petri nets with the deadlock highlighted
for m in ["M3_wrong_join", "M4_missing_recovery", "M5_resource_deadlock", "M2_parallel"]:
    o = outs[m]
    if o["causes"]:
        c = o["causes"][0]
        dot(net_to_dot(o["net"], o["result"]["dead_markings"][0]["marking"],
                       c["highlight_places"], c["highlight_transitions"]), f"pn_{m}_dead")
    else:
        dot(net_to_dot(o["net"]), f"pn_{m}")
dot(net_to_dot(outs["M5_resource_deadlock"]["fix"]["net"]), "pn_M5_monitored")
dot(graph_to_dot(outs["M3_wrong_join"]["net"], outs["M3_wrong_join"]["result"]), "rg_M3_wrong_join")
dot(graph_to_dot(outs["M5_resource_deadlock"]["net"], outs["M5_resource_deadlock"]["result"]), "rg_M5")

# simulation histogram for M6
sim = run_cases(outs["M6_full_timed"]["net"], 1000)
fig, ax = plt.subplots(figsize=(5, 2.6))
ax.hist(sim["times"], bins=25, color="#2563eb", alpha=0.85)
ax.axvline(sim["mean_time"], color="#111827", ls="--", lw=1)
ax.set_xlabel("Cycle time (minutes)")
ax.set_ylabel("Cases")
ax.set_title(f"M6: 1000 cases, {sim['completion_rate']:.0%} complete, mean {sim['mean_time']:.1f} min", fontsize=9)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(FIG / "sim_M6.png", dpi=200)
print("M6 simulation:", {k: v for k, v in sim.items() if k not in ("times", "fire_counts")})

# framework diagram
FRAME = """digraph F { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="#eff6ff", color="#1d4ed8",
fontname="Helvetica", fontsize=11]; edge [color="#374151"];
a [label="1. Process modeling\\n(BPMN 2.0 XML)"]; b [label="2. Petri-net\\nconversion"];
c [label="3. Deadlock detection\\nstructural + reachability"]; d [label="Deadlock?", shape=diamond, fillcolor="white"];
e [label="4. Cause identification\\n(dead marking, siphon)"]; f [label="5. Prevention rule\\n(join fix, recovery, monitor)"];
g [label="6. Verified sound model", fillcolor="#dcfce7", color="#15803d"];
a->b->c->d; d->g [label="no"]; d->e [label="yes"]; e->f; f->b [label="re-analyze", constraint=false]; }"""
dot(FRAME, "framework")

# architecture diagram
ARCH = """digraph A { rankdir=LR; node [shape=box, style="rounded,filled", fillcolor="white", fontname="Helvetica", fontsize=10]; edge [fontname="Helvetica", fontsize=9];
in [label=".bpmn file\\n(Camunda Modeler)", fillcolor="#fef3c7"];
p [label="bpmn_parser"]; t [label="transformer"]; n [label="petri_net"]; s [label="structural"];
r [label="reachability"]; si [label="siphons"]; dg [label="diagnosis"]; pv [label="prevention"]; sm [label="simulate"];
ev [label="evolution"];
ui [label="Streamlit app\\n(app.py + visualize)", fillcolor="#dbeafe"];
in->p->t->n; p->s; n->r->dg; n->si->dg; dg->pv; pv->t [label="fixed model"]; pv->ev; n->sm; s->ui; r->ui; dg->ui; pv->ui; ev->ui; sm->ui; }"""
dot(ARCH, "architecture")
print("figures in", FIG)
