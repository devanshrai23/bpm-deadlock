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
    # complex case: the automatic fixes leave the P4 dead end, which needs a manual redesign
    "C1_complex":           (False, 3, {"P1", "P2", "P3", "P4", "P6"}, False),
    "C1_fixed":             (True, 0, set(), None),
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


# ---- checks taken from the newer literature -------------------------------------------
from src.bpmn_parser import parse_bpmn  # noqa: E402
from src.transformer import bpmn_to_petri, check_mapping  # noqa: E402
from src.evolution import detect_changes, summary  # noqa: E402


@pytest.mark.parametrize("name", EXPECTED)
def test_mapping_correct(name):
    """Zhang et al. 2025, Algorithm 1: every element and connection is mapped."""
    model = parse_bpmn((MODELS / f"{name}.bpmn").read_text())
    assert check_mapping(model, bpmn_to_petri(model)) == []


@pytest.mark.parametrize("name", EXPECTED)
def test_safeness(name):
    """Kraeuter et al. 2024: only D3 (AND-split closed by XOR-join) is unsafe."""
    r = run_pipeline((MODELS / f"{name}.bpmn").read_text())["result"]
    assert r["safe"] == (name != "D3_leave_request")   # C1's P3 is hidden until round 1


@pytest.mark.parametrize("name", ["M5_resource_deadlock", "D4_hospital_admission"])
def test_monitor_maximally_permissive(name):
    """Wang et al. 2023: the monitor keeps every good state and has unit arc weights."""
    pm = run_pipeline((MODELS / f"{name}.bpmn").read_text())["fix"]["permissiveness"]
    assert pm["maximally_permissive"] and pm["unit_weights"]


@pytest.mark.parametrize("name", ["M3_wrong_join", "D2_insurance_claim", "D3_leave_request"])
def test_alternative_split_fix_is_sound(name):
    """Kraeuter et al. 2024: the split-side quick fix is offered and re-verified."""
    alts = run_pipeline((MODELS / f"{name}.bpmn").read_text())["fix"]["alternatives"]
    assert alts and all(a["result"]["sound"] for a in alts)


def test_change_detection_m3():
    """Zhang et al. 2025, Algorithm 2: M3 -> M3_fixed is a single replace."""
    old = parse_bpmn((MODELS / "M3_wrong_join.bpmn").read_text())
    new = parse_bpmn((MODELS / "M3_fixed.bpmn").read_text())
    assert summary(detect_changes(old, new)) == {"insert": 0, "delete": 0, "replace": 1}


def test_truncated_is_inconclusive():
    """A correct model too big for the state limit must not be called unsound."""
    from tools.benchmark_parallel import parallel_model
    r = analyse(bpmn_to_petri(parse_bpmn(parallel_model(15, 1))))
    assert r["truncated"] and r["verdict"] == "inconclusive"


def test_complex_case_rounds():
    """C1 is repaired round by round; each round removes deadlocks and the last one is sound."""
    from tools.complex_case import rounds
    rows, d = rounds()
    assert [r["Deadlocks"] for r in rows] == [3, 2, 1, 0, 0]
    assert [r["Sound"] for r in rows] == ["no", "no", "no", "yes", "yes"]
    assert rows[0]["Dead transitions"] > 0          # defects hidden behind the first ones
    assert d["round3"][3]["maximally_permissive"]   # the control place keeps every good state
