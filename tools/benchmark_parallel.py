"""Parallel-branch benchmark of Kraeuter et al. (BPM 2024, Fig. 4 / Table 1).

A start event, an AND-split into n branches of m tasks each, an AND-join and an
end event.  The state space grows as (m+1)^n, the worst case for state-space
exploration.  Run:  python tools/benchmark_parallel.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.bpmn_parser import parse_bpmn  # noqa: E402
from src.transformer import bpmn_to_petri  # noqa: E402
from src.reachability import analyse  # noqa: E402

# (branches, length): states reported by Kraeuter et al., Table 1
PAPER = {(5, 1): 35, (10, 1): 1027, (15, 1): 32771, (16, 1): 65539, (5, 3): 1027, (5, 5): 7779,
         (3, 10): 1334, (3, 20): 9264}


def parallel_model(n, m):
    els = ['<startEvent id="s"/>', '<parallelGateway id="split"/>', '<parallelGateway id="join"/>',
           '<endEvent id="e"/>']
    flows = [("s", "split"), ("join", "e")]
    for b in range(n):
        prev = "split"
        for k in range(m):
            tid = f"t{b}_{k}"
            els.append(f'<task id="{tid}" name="Task {b + 1}.{k + 1}"/>')
            flows.append((prev, tid))
            prev = tid
        flows.append((prev, "join"))
    fl = "".join(f'<sequenceFlow id="f{i}" sourceRef="{a}" targetRef="{b}"/>' for i, (a, b) in enumerate(flows))
    return ('<?xml version="1.0" encoding="UTF-8"?><definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"'
            f' id="d"><process id="p">{"".join(els)}{fl}</process></definitions>')


if __name__ == "__main__":
    print(f"{'branches':>8} {'length':>6} {'our states':>10} {'paper':>7} {'time (ms)':>9}  verdict")
    for (n, m), theirs in PAPER.items():
        net = bpmn_to_petri(parse_bpmn(parallel_model(n, m)))
        t0 = time.perf_counter()
        r = analyse(net)
        ms = (time.perf_counter() - t0) * 1000
        print(f"{n:>8} {m:>6} {r['states']:>10} {theirs:>7} {ms:>9.0f}  {r['verdict']}")
