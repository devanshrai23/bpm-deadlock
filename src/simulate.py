"""Step 6 (extra) - timed simulation with branch probabilities (our extension).

None of the three main papers we build on handles time; Zhang et al. (2025) name
timed Petri nets as future work.  We add durations and branch probabilities.

Each task transition has a duration ('time: 20' in the BPMN documentation)
and each XOR branch a probability ('prob: 0.3').  We play many cases:

  * all enabled transitions start at the current time; when several compete
    for the same token (an XOR choice) one is drawn using the probabilities;
  * a started transition takes its input tokens at once and gives its output
    tokens when it finishes (now + duration) - so a resource stays busy
    for the whole task;
  * the case ends when nothing is enabled and nothing is running.
"""
import heapq
import random
import statistics


def run_case(net, rng, max_steps=5000):
    m = {p: n for p, n in net.m0.items() if n}
    now, running, steps, fired = 0.0, [], 0, []
    while steps < max_steps:
        steps += 1
        enabled = net.enabled(m)
        if enabled:
            weights = [max(net.transitions[t].prob, 1e-9) for t in enabled]
            t = rng.choices(enabled, weights=weights)[0]
            for p, w in net.pre[t].items():
                m[p] -= w
            heapq.heappush(running, (now + net.transitions[t].time, steps, t))
            fired.append(t)
            continue
        if not running:
            break
        now, _, t = heapq.heappop(running)
        for p, w in net.post[t].items():
            m[p] = m.get(p, 0) + w
    m = {p: n for p, n in m.items() if n}
    done = m == {p: n for p, n in net.mf.items() if n}
    return {"completed": done, "time": now, "fired": fired, "end_marking": m}


def run_cases(net, n=1000, seed=42):
    rng = random.Random(seed)
    runs = [run_case(net, rng) for _ in range(n)]
    ok = [r["time"] for r in runs if r["completed"]]
    counts = {}
    for r in runs:
        for t in r["fired"]:
            counts[t] = counts.get(t, 0) + 1
    return {
        "cases": n,
        "completed": len(ok),
        "stuck": n - len(ok),
        "completion_rate": len(ok) / n,
        "mean_time": statistics.mean(ok) if ok else None,
        "median_time": statistics.median(ok) if ok else None,
        "p90_time": sorted(ok)[int(0.9 * (len(ok) - 1))] if ok else None,
        "times": ok,
        "fire_counts": {net.transitions[t].label: c / n for t, c in counts.items()},
    }
