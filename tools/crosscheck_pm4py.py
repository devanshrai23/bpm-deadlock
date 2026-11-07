"""Cross-checks soundness results against pm4py WOFLAN."""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
import pm4py  # noqa: E402
from src.bpmn_parser import load_bpmn  # noqa: E402
from src.transformer import bpmn_to_petri  # noqa: E402
from src.reachability import analyse  # noqa: E402

rows = []
for f in sorted((Path(__file__).resolve().parent.parent / "models").glob("*.bpmn")):
    model = load_bpmn(f)
    model.resources = {}
    for n in model.nodes.values():
        for k in ("acquire", "release", "uses"):
            n.doc.pop(k, None)
    ours = analyse(bpmn_to_petri(model))["sound"]
    bpmn = pm4py.read_bpmn(str(f))
    net, im, fm = pm4py.convert_to_petri_net(bpmn)
    try:
        theirs = pm4py.check_soundness(net, im, fm)[0]
    except Exception as e:  # woflan can refuse some nets
        theirs = f"n/a ({type(e).__name__})"
    rows.append((f.stem, ours, theirs, "OK" if ours == theirs else "DIFF"))

print(f"{'model':28} {'ours':6} {'pm4py':6} match   (control flow only)")
for r in rows:
    print(f"{r[0]:28} {str(r[1]):6} {str(r[2]):6} {r[3]}")
