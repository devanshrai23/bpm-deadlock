"""Expected result for every model.  Run:  python -m pytest -q"""
from pathlib import Path
import pytest
from src.pipeline import run_pipeline
from src.petri_net import PetriNet
from src.reachability import analyse

MODELS = Path(__file__).resolve().parent.parent / "models"

# model: (sound?, number of deadlocks, structural pattern found, sound after auto-fix)
EXPECTED = {
    "M1_sequential":        (True, 0, set(), None),
    "M2_parallel":          (True, 0, set(), None),
    "M3_wrong_join":        (False, 2, {"P1"}, True),
    "M3_fixed":             (True, 0, set(), None),
    "M4_missing_recovery":  (False, 1, {"P4"}, None),
    "M4_fixed":             (True, 0, set(), None),
    "M5_resource_deadlock": (False, 1, {"P6"}, True),
    "M5_fixed":             (True, 0, set(), None),
    "M6_full_timed":        (True, 0, set(), None),
    "D1_order_fulfilment":  (True, 0, set(), None),
    "D2_insurance_claim":   (False, 2, {"P1"}, True),
    "D3_leave_request":     (False, 0, {"P3"}, True),
    "D4_hospital_admission": (False, 1, {"P6"}, True),
    "D5_purchase_order_loop": (False, 1, {"P2"}, True),
}


@pytest.mark.parametrize("name", EXPECTED)
def test_model(name):
    sound, deadlocks, patterns, sound_after = EXPECTED[name]
    out = run_pipeline((MODELS / f"{name}.bpmn").read_text())
    r = out["result"]
    assert r["sound"] == sound
    assert len(r["deadlocks"]) == deadlocks
    assert {i["code"] for i in out["issues"]} == patterns
    if sound_after is not None:
        assert out["fix"]["result"]["sound"] == sound_after


def test_firing_rule():
    net = PetriNet.from_json('{"places":["a","b"],"transitions":["t"],"arcs":[["a","t"],["t","b"]],'
                             '"initial_marking":{"a":1},"final_marking":{"b":1}}')
    assert net.enabled({"a": 1}) == ["t"]
    assert net.fire("t", {"a": 1}) == {"b": 1}
    assert analyse(net)["sound"]


def test_json_round_trip():
    out = run_pipeline((MODELS / "M2_parallel.bpmn").read_text())
    again = PetriNet.from_json(out["net"].to_json())
    assert analyse(again)["states"] == out["result"]["states"]
