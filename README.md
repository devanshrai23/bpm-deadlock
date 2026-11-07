# Deadlock Detection and Prevention in Business Process Models Using Petri Nets

BPM project, IIIT Allahabad: Devansh Rai (IIB2024006), Geethika Gorakala (IIB2024024), Abhilasha Sharma (IIB2024501)

This tool takes a BPMN 2.0 model, turns it into a Petri net, finds deadlocks, explains why they happen, fixes them, and checks the fixed model again.

## 1. Setup (5 minutes)

You need Python 3.10 or newer.

```bash
cd bpm-deadlock
python -m venv venv
# Windows:  venv\Scripts\activate        Mac/Linux:  source venv/bin/activate
pip install -r requirements.txt
python -m pytest -q          # should print: 51 passed
streamlit run app.py         # opens http://localhost:8501
```

The app works offline. The BPMN viewer is bundled in `static/`, and the Petri nets are drawn in the browser.

## 2. The models (dataset)

All the models are BPMN 2.0 XML files in `models/`, with diagram layout included.

| File | What it shows | Expected result |
|---|---|---|
| M1_sequential | Simple sequence | sound |
| M2_parallel | Credit and document checks in parallel (AND/AND) | sound |
| M3_wrong_join | XOR-split "Risk level?" closed by an AND-join | 2 deadlocks (P1) |
| M3_fixed | Same model with an XOR-join | sound |
| M4_missing_recovery | Documents missing, "on hold" path goes nowhere | 1 deadlock (P4) |
| M4_fixed | Resubmission loop and coordinated rejection | sound |
| M5_resource_deadlock | Officer and credit system taken in opposite order | 1 deadlock (P6, siphon) |
| M5_fixed | Both branches take the officer first | sound |
| M6_full_timed | Full corrected model with times and probabilities | sound; 1000/1000 cases complete |
| D1_order_fulfilment | Demo, correct model | sound |
| D2_insurance_claim | Demo, XOR-split with AND-join | 2 deadlocks |
| D3_leave_request | Demo, AND-split with XOR-join | improper completion |
| D4_hospital_admission | Demo, bed and doctor circular wait | 1 deadlock |
| D5_purchase_order_loop | Demo, AND-join at a loop entry | 1 deadlock |

Extra information goes in the standard BPMN **documentation** field (Camunda Modeler: select the element, then Properties panel, then General, then Documentation):

- process: `resources: officer=1, credit_system=1`
- task: `time: 20; acquire: officer` / `release: officer` / `uses: officer`
- sequence flow: `prob: 0.3`

**Viewing a diagram in Camunda:**

- **Camunda Modeler:** File → Open, then pick a `.bpmn` file.
- **Paste the XML:** go to https://demo.bpmn.io, choose "Open" and pick the file. Or, in Camunda Modeler, open the **XML** tab at the bottom of the window, paste the XML, and switch back to the diagram.
- **In our app:** choose Model source → "Upload / paste" and paste the XML.

To regenerate every file: `python tools/generate_models.py`.

## 3. How the code works (for the viva)

| Step | Module | Input → output | Key function: what it does |
|---|---|---|---|
| 1 Model | `src/bpmn_parser.py` | .bpmn XML → nodes, flows | `parse_bpmn()` reads every event, task, gateway and arrow, plus the documentation notes |
| 2 Petri net | `src/transformer.py` | BPMN model → Petri net | `bpmn_to_petri()`: each flow becomes a place, each task a transition; AND = one transition, XOR = one transition per branch (rules of Zhang et al.); `check_mapping()` is their Algorithm 1 |
| | `src/petri_net.py` | places, transitions, arcs | `enabled(m)`: t can fire if all its input places have tokens; `fire(t, m)`: moves the tokens |
| 3a Detect | `src/structural.py` | BPMN graph → patterns P1–P6 | `check()`: fast search for the violation causes listed by Kräuter et al., points at the bad gateway |
| 3b Detect | `src/reachability.py` | net → all reachable markings | `analyse()`: BFS over all states (Kräuter et al.). A state where nothing can fire and the end is not reached is a deadlock. Also checks the three soundness rules and safeness; a run that hits the state limit is *inconclusive* |
| 4 Cause | `src/diagnosis.py` | dead marking → explanation | `explain()`: "AND-join has a token from Credit check but is still waiting for Documents complete" |
| | `src/siphons.py` | net → siphons | `minimal_siphons()`: place sets that, once empty, never refill (resource deadlocks) |
| 5 Fix | `src/prevention.py` | issue → fixed model | `fix_gateways()` changes the wrong join; `alternative_fixes()` offers the split-side quick fix (Kräuter et al.); `add_monitors()` adds a siphon control place and `permissiveness()` checks no good state is lost (Wang et al.) |
| 6 Verify | `src/pipeline.py`, `src/evolution.py` | runs 1→6 | `run_pipeline()` re-analyses the fixed model; `detect_changes()` lists the insert/delete/replace operations between two versions (Zhang et al., Alg. 2) |
| Extra | `src/simulate.py` | net + times + probabilities | `run_cases()`: simulates 1000 timed cases |
| UI | `app.py`, `src/visualize.py` | — | Streamlit pages and the DOT drawings |

## 4. Demo script (about 8 minutes)

1. **M1** → step 1, then step 3: sound baseline.
2. **M4** → step 1 (faulty task shown in red) → step 2 (Petri net) → step 3 (deadlock and witness trace) → step 4 (cause, suggested fix, M4_fixed shown and sound).
3. **M3** → step 4: automatic fix, AND-join → XOR-join, before/after table.
4. **M5** → step 3 (P6 found) → step 4 (siphon, control place V1, sound after the fix).
5. **M4** → step 5, token game: click Credit check, Document check, "No" … and show that it gets stuck.
6. **M6** → step 6, simulation: 100% complete, mean cycle time about 62 minutes.
7. **All models · results**: the full results table.

## 5. Other files

- `report/report.tex`: IEEE report. On Overleaf: New Project → Upload Project → upload `report.zip` (the IEEEtran class is built in), then Recompile. `report/report.pdf` is a preview compiled without IEEEtran.
- `results/results.csv`, `results/figures/`: tables and figures used in the report (`python tools/make_figures.py`, needs Graphviz).
- `tools/crosscheck_pm4py.py`: compares our soundness results with pm4py (all 14 match).
- `tools/screenshots.py`: takes app screenshots (needs Playwright).

## 5. Papers the method is based on

| Paper | What we use |
|---|---|
| T. Kräuter et al., *Instantaneous, Comprehensible, and Fixable Soundness Checking of Realistic BPMN Models*, arXiv:2407.03965, 2024 | state-space soundness + safeness check, violation causes (patterns), quick fixes with alternatives, parallel-branch benchmark (`python tools/benchmark_parallel.py`) |
| Z. Zhang et al., *Collaborative Modeling of BPMN and HCPN*, Information 16(4):323, 2025 | BPMN→Petri net element rules, mapping-correctness check (Alg. 1), insert/delete/replace change detection (Alg. 2) |
| S. G. Wang et al., *A Refined Siphon-Based Deadlock Prevention Policy for a Class of Petri Nets*, IEEE TSMC: Systems 53(1):191–203, 2023 | one unit-weight monitor per problem siphon, maximal permissiveness as the quality measure |
