"""Generates the BPMN 2.0 XML files (with diagram layout) for all models.

Each model is written as a compact spec: nodes placed on a grid (column, row)
and sequence flows between them.  The script turns the spec into a .bpmn file
that opens in Camunda Modeler or https://demo.bpmn.io.

Run:  python tools/generate_models.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parent.parent / "models"

COL_W, ROW_H, X0, Y0 = 150, 120, 120, 100
SIZE = {"start": (36, 36), "end": (36, 36), "task": (110, 70),
        "xor": (50, 50), "and": (50, 50)}
TAG = {"start": "startEvent", "end": "endEvent", "task": "task",
       "xor": "exclusiveGateway", "and": "parallelGateway"}


def center(n):
    return X0 + n["col"] * COL_W, Y0 + n["row"] * ROW_H


def bounds(n):
    cx, cy = center(n)
    w, h = SIZE[n["type"]]
    return cx - w / 2, cy - h / 2, w, h


def waypoints(s, t, max_row):
    sx, sy = center(s)
    tx, ty = center(t)
    sw, sh = SIZE[s["type"]]
    tw, th = SIZE[t["type"]]
    if t["col"] <= s["col"]:  # back edge: route underneath the diagram
        low = Y0 + max_row * ROW_H + 70
        return [(sx, sy + sh / 2), (sx, low), (tx, low), (tx, ty + th / 2)]
    if s["row"] == t["row"]:
        return [(sx + sw / 2, sy), (tx - tw / 2, ty)]
    if s["type"] in ("xor", "and"):  # split: leave from top/bottom
        y_start = sy + sh / 2 if ty > sy else sy - sh / 2
        return [(sx, y_start), (sx, ty), (tx - tw / 2, ty)]
    if t["type"] in ("xor", "and"):  # join: enter from top/bottom
        y_end = ty - th / 2 if sy < ty else ty + th / 2
        return [(sx + sw / 2, sy), (tx, sy), (tx, y_end)]
    mx = (sx + sw / 2 + tx - tw / 2) / 2
    return [(sx + sw / 2, sy), (mx, sy), (mx, ty), (tx - tw / 2, ty)]


def build(spec):
    pid = "Process_" + spec["key"]
    nodes = {n["id"]: n for n in spec["nodes"]}
    max_row = max(n["row"] for n in spec["nodes"])
    inc = {i: [] for i in nodes}
    out = {i: [] for i in nodes}
    for f in spec["flows"]:
        out[f["src"]].append(f["id"])
        inc[f["tgt"]].append(f["id"])

    L = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" '
         'xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" '
         'xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" '
         'xmlns:di="http://www.omg.org/spec/DD/20100524/DI" '
         f'id="Defs_{spec["key"]}" targetNamespace="http://bpmn.io/schema/bpmn" '
         'exporter="Camunda Modeler" exporterVersion="5.0.0">',
         f'  <bpmn:process id="{pid}" name="{escape(spec["title"])}" isExecutable="false">']
    if spec.get("doc"):
        L.append(f'    <bpmn:documentation>{escape(spec["doc"])}</bpmn:documentation>')
    for n in spec["nodes"]:
        tag = TAG[n["type"]]
        L.append(f'    <bpmn:{tag} id="{n["id"]}" name="{escape(n.get("name", ""))}">')
        if n.get("doc"):
            L.append(f'      <bpmn:documentation>{escape(n["doc"])}</bpmn:documentation>')
        for f in inc[n["id"]]:
            L.append(f'      <bpmn:incoming>{f}</bpmn:incoming>')
        for f in out[n["id"]]:
            L.append(f'      <bpmn:outgoing>{f}</bpmn:outgoing>')
        L.append(f'    </bpmn:{tag}>')
    for f in spec["flows"]:
        name = f' name="{escape(f["name"])}"' if f.get("name") else ""
        if f.get("doc"):
            L.append(f'    <bpmn:sequenceFlow id="{f["id"]}"{name} sourceRef="{f["src"]}" targetRef="{f["tgt"]}">')
            L.append(f'      <bpmn:documentation>{escape(f["doc"])}</bpmn:documentation>')
            L.append('    </bpmn:sequenceFlow>')
        else:
            L.append(f'    <bpmn:sequenceFlow id="{f["id"]}"{name} sourceRef="{f["src"]}" targetRef="{f["tgt"]}" />')
    L.append('  </bpmn:process>')
    L.append(f'  <bpmndi:BPMNDiagram id="Diagram_{spec["key"]}">')
    L.append(f'    <bpmndi:BPMNPlane id="Plane_{spec["key"]}" bpmnElement="{pid}">')
    for n in spec["nodes"]:
        x, y, w, h = bounds(n)
        extra = ' isMarkerVisible="true"' if n["type"] == "xor" else ""
        L.append(f'      <bpmndi:BPMNShape id="{n["id"]}_di" bpmnElement="{n["id"]}"{extra}>')
        L.append(f'        <dc:Bounds x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h}" />')
        if n["type"] != "task" and n.get("name"):
            L.append('        <bpmndi:BPMNLabel>')
            L.append(f'          <dc:Bounds x="{x - 25:.0f}" y="{y - 32:.0f}" width="{w + 50}" height="27" />')
            L.append('        </bpmndi:BPMNLabel>')
        L.append('      </bpmndi:BPMNShape>')
    for f in spec["flows"]:
        L.append(f'      <bpmndi:BPMNEdge id="{f["id"]}_di" bpmnElement="{f["id"]}">')
        pts = waypoints(nodes[f["src"]], nodes[f["tgt"]], max_row)
        for (x, y) in pts:
            L.append(f'        <di:waypoint x="{x:.0f}" y="{y:.0f}" />')
        if f.get("name"):
            (x1, y1), (x2, y2) = pts[0], pts[1]
            if y1 == y2:   # horizontal first segment: label just after the gateway
                lx, ly = x1 + 4, y1
            else:          # vertical first segment: label beside it
                lx, ly = x1 + 4, (y1 + y2) / 2 + 9
            L.append('        <bpmndi:BPMNLabel>')
            L.append(f'          <dc:Bounds x="{lx + 4:.0f}" y="{ly - 18:.0f}" width="70" height="14" />')
            L.append('        </bpmndi:BPMNLabel>')
        L.append('      </bpmndi:BPMNEdge>')
    L.append('    </bpmndi:BPMNPlane>')
    L.append('  </bpmndi:BPMNDiagram>')
    L.append('</bpmn:definitions>')
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------
# helpers to keep the specs short
def S(i, c, r, name="Start"): return dict(id=i, type="start", name=name, col=c, row=r)
def E(i, c, r, name="End"): return dict(id=i, type="end", name=name, col=c, row=r)
# Task durations in minutes (assumed values, the same task gets the same time in every model)
DEFAULT_TIME = {
    "Receive application": 5, "Check eligibility": 10, "Make decision": 15, "Final decision": 15,
    "Notify applicant": 3, "Credit check": 20, "Document check": 15, "Assess risk": 10,
    "Senior officer review": 30, "Automatic scoring": 2, "Put application on hold": 2,
    "Request missing documents": 10, "Mark documents failed": 2, "Approve loan": 5, "Reject loan": 5,
    "Assign loan officer": 2, "Open credit system": 1, "Credit assessment": 25,
    "Assign officer (fraud)": 2, "Open credit system (fraud)": 1, "Fraud check": 20,
    "Receive order": 3, "Pick and pack items": 25, "Process payment": 5, "Ship order": 30,
    "Notify out of stock": 2, "Register claim": 10, "Auto-approve small claim": 2,
    "Assess damage on site": 120, "Pay claim": 15, "Submit leave request": 5, "Manager approval": 60,
    "HR balance check": 20, "Update team calendar": 5, "Triage patient": 15, "Reserve bed": 10,
    "Assign doctor": 10, "Admit to ward": 20, "Assign doctor (tests)": 10, "Reserve bed (tests)": 10,
    "Run bedside tests": 30, "Create care plan": 20, "Create purchase order": 15,
    "Review purchase order": 20, "Send PO to supplier": 5, "Revise purchase order": 15,
}


def T(i, name, c, r, doc=""):
    if "time:" not in doc and name in DEFAULT_TIME:
        doc = f"time: {DEFAULT_TIME[name]}" + (f"; {doc}" if doc else "")
    return dict(id=i, type="task", name=name, col=c, row=r, doc=doc)
def X(i, name, c, r): return dict(id=i, type="xor", name=name, col=c, row=r)
def A(i, name, c, r): return dict(id=i, type="and", name=name, col=c, row=r)


def F(i, s, t, name="", doc=""):
    return dict(id=i, src=s, tgt=t, name=name, doc=doc)


def chain(prefix, ids):
    return [F(f"{prefix}{k}", a, b) for k, (a, b) in enumerate(zip(ids, ids[1:]), 1)]


SPECS = []

# M1 ----------------------------------------------------------------------
SPECS.append(dict(key="M1_sequential", title="M1 Loan approval - sequential", nodes=[
    S("start", 0, 0, "Application received"), T("receive", "Receive application", 1, 0),
    T("eligibility", "Check eligibility", 2, 0), T("decide", "Make decision", 3, 0),
    T("notify", "Notify applicant", 4, 0), E("end", 5, 0, "Done")],
    flows=chain("f", ["start", "receive", "eligibility", "decide", "notify", "end"])))

# M2 ----------------------------------------------------------------------
SPECS.append(dict(key="M2_parallel", title="M2 Loan approval - parallel checks", nodes=[
    S("start", 0, 1, "Application received"), T("receive", "Receive application", 1, 1),
    A("and_split", "", 2, 1), T("credit", "Credit check", 3, 0), T("docs", "Document check", 3, 2),
    A("and_join", "", 4, 1), T("decide", "Make decision", 5, 1), T("notify", "Notify applicant", 6, 1),
    E("end", 7, 1, "Done")],
    flows=[F("f1", "start", "receive"), F("f2", "receive", "and_split"),
           F("f3", "and_split", "credit"), F("f4", "and_split", "docs"),
           F("f5", "credit", "and_join"), F("f6", "docs", "and_join"),
           F("f7", "and_join", "decide"), F("f8", "decide", "notify"), F("f9", "notify", "end")]))


# M3 / M3_fixed -------------------------------------------------------------
def m3(fixed):
    join = X("risk_join", "", 5, 1) if fixed else A("risk_join", "", 5, 1)
    return dict(key="M3_fixed" if fixed else "M3_wrong_join",
                title="M3 Loan approval - risk routing" + (" (fixed)" if fixed else " (AND-join error)"),
                nodes=[S("start", 0, 1, "Application received"), T("receive", "Receive application", 1, 1),
                       T("assess", "Assess risk", 2, 1), X("risk_split", "Risk level?", 3, 1),
                       T("senior", "Senior officer review", 4, 0), T("auto", "Automatic scoring", 4, 2),
                       join, T("decide", "Final decision", 6, 1), T("notify", "Notify applicant", 7, 1),
                       E("end", 8, 1, "Done")],
                flows=[F("f1", "start", "receive"), F("f2", "receive", "assess"), F("f3", "assess", "risk_split"),
                       F("f4", "risk_split", "senior", "High risk"), F("f5", "risk_split", "auto", "Low risk"),
                       F("f6", "senior", "risk_join"), F("f7", "auto", "risk_join"),
                       F("f8", "risk_join", "decide"), F("f9", "decide", "notify"), F("f10", "notify", "end")])


SPECS += [m3(False), m3(True)]

# M4 ----------------------------------------------------------------------
SPECS.append(dict(key="M4_missing_recovery", title="M4 Loan approval - missing documents (no recovery path)", nodes=[
    S("start", 0, 1, "Application received"), T("receive", "Receive application", 1, 1),
    A("and_split", "", 2, 1), T("credit", "Credit check", 3, 0), T("docs", "Document check", 3, 2),
    X("docs_ok", "Documents complete?", 4, 2), T("hold", "Put application on hold", 5, 3),
    A("and_join", "", 6, 1), T("approve", "Approve loan", 7, 1), T("notify", "Notify applicant", 8, 1),
    E("end", 9, 1, "Done")],
    flows=[F("f1", "start", "receive"), F("f2", "receive", "and_split"), F("f3", "and_split", "credit"),
           F("f4", "and_split", "docs"), F("f5", "credit", "and_join"), F("f6", "docs", "docs_ok"),
           F("f7", "docs_ok", "and_join", "Yes"), F("f8", "docs_ok", "hold", "No"),
           F("f9", "and_join", "approve"), F("f10", "approve", "notify"), F("f11", "notify", "end")]))

# M4_fixed ------------------------------------------------------------------
SPECS.append(dict(key="M4_fixed", title="M4 Loan approval - resubmission and coordinated rejection (fixed)", nodes=[
    S("start", 0, 1, "Application received"), T("receive", "Receive application", 1, 1),
    A("and_split", "", 2, 1), T("credit", "Credit check", 4, 0),
    X("loop_join", "", 3, 2), T("docs", "Document check", 4, 2), X("docs_ok", "Documents complete?", 5, 2),
    T("request", "Request missing documents", 6, 3), X("received", "Received in time?", 7, 3),
    T("failed", "Mark documents failed", 8, 3), X("docs_result", "", 9, 2),
    A("and_join", "", 10, 1), T("decide", "Make decision", 11, 1), X("approved", "Approved?", 12, 1),
    T("approve", "Approve loan", 13, 0), T("reject", "Reject loan", 13, 2), X("dec_join", "", 14, 1),
    T("notify", "Notify applicant", 15, 1), E("end", 16, 1, "Done")],
    flows=[F("f1", "start", "receive"), F("f2", "receive", "and_split"), F("f3", "and_split", "credit"),
           F("f4", "and_split", "loop_join"), F("f5", "loop_join", "docs"), F("f6", "docs", "docs_ok"),
           F("f7", "docs_ok", "docs_result", "Yes"), F("f8", "docs_ok", "request", "No"),
           F("f9", "request", "received"), F("f10", "received", "loop_join", "Yes"),
           F("f11", "received", "failed", "No"), F("f12", "failed", "docs_result"),
           F("f13", "credit", "and_join"), F("f14", "docs_result", "and_join"),
           F("f15", "and_join", "decide"), F("f16", "decide", "approved"),
           F("f17", "approved", "approve", "Yes"), F("f18", "approved", "reject", "No"),
           F("f19", "approve", "dec_join"), F("f20", "reject", "dec_join"),
           F("f21", "dec_join", "notify"), F("f22", "notify", "end")]))


# M5 / M5_fixed -------------------------------------------------------------
def m5(fixed):
    if fixed:  # both branches take the officer first, then the credit system
        b1 = T("b_officer", "Assign officer (fraud)", 3, 2, "acquire: officer")
        b2 = T("b_credit", "Open credit system (fraud)", 4, 2, "acquire: credit_system")
        bflows = [F("f6", "and_split", "b_officer"), F("f7", "b_officer", "b_credit"), F("f8", "b_credit", "fraud")]
    else:      # opposite order -> circular wait
        b1 = T("b_credit", "Open credit system (fraud)", 3, 2, "acquire: credit_system")
        b2 = T("b_officer", "Assign officer (fraud)", 4, 2, "acquire: officer")
        bflows = [F("f6", "and_split", "b_credit"), F("f7", "b_credit", "b_officer"), F("f8", "b_officer", "fraud")]
    return dict(key="M5_fixed" if fixed else "M5_resource_deadlock",
                title="M5 Loan approval - shared officer and credit system" + (" (fixed order)" if fixed else ""),
                doc="resources: officer=1, credit_system=1",
                nodes=[S("start", 0, 1, "Application received"), T("receive", "Receive application", 1, 1),
                       A("and_split", "", 2, 1),
                       T("a_officer", "Assign loan officer", 3, 0, "acquire: officer"),
                       T("a_credit", "Open credit system", 4, 0, "acquire: credit_system"),
                       T("assess", "Credit assessment", 5, 0, "release: officer, credit_system"),
                       b1, b2, T("fraud", "Fraud check", 5, 2, "release: officer, credit_system"),
                       A("and_join", "", 6, 1), T("decide", "Make decision", 7, 1),
                       T("notify", "Notify applicant", 8, 1), E("end", 9, 1, "Done")],
                flows=[F("f1", "start", "receive"), F("f2", "receive", "and_split"),
                       F("f3", "and_split", "a_officer"), F("f4", "a_officer", "a_credit"),
                       F("f5", "a_credit", "assess")] + bflows +
                      [F("f9", "assess", "and_join"), F("f10", "fraud", "and_join"),
                       F("f11", "and_join", "decide"), F("f12", "decide", "notify"), F("f13", "notify", "end")])


SPECS += [m5(False), m5(True)]

# M6 ----------------------------------------------------------------------
SPECS.append(dict(key="M6_full_timed", title="M6 Loan approval - full corrected model with times and probabilities",
    doc="resources: officer=1",
    nodes=[S("start", 0, 2, "Application received"), T("receive", "Receive application", 1, 2, "time: 5"),
           A("and_split", "", 2, 2),
           T("credit", "Credit check", 3, 0, "time: 20"), X("risk", "Risk level?", 4, 0),
           T("senior", "Senior officer review", 5, 0, "time: 30; uses: officer"),
           T("auto", "Automatic scoring", 5, 1, "time: 2"), X("risk_join", "", 6, 0),
           X("loop_join", "", 3, 3), T("docs", "Document check", 4, 3, "time: 15"),
           X("docs_ok", "Documents complete?", 5, 3),
           T("request", "Request missing documents", 6, 4, "time: 10"),
           X("received", "Received in time?", 7, 4), T("failed", "Mark documents failed", 8, 4, "time: 2"),
           X("docs_result", "", 9, 3), A("and_join", "", 10, 2),
           T("decide", "Make decision", 11, 2, "time: 15; uses: officer"), X("approved", "Approved?", 12, 2),
           T("approve", "Approve loan", 13, 1, "time: 5"), T("reject", "Reject loan", 13, 3, "time: 5"),
           X("dec_join", "", 14, 2), T("notify", "Notify applicant", 15, 2, "time: 3"), E("end", 16, 2, "Done")],
    flows=[F("f1", "start", "receive"), F("f2", "receive", "and_split"), F("f3", "and_split", "credit"),
           F("f4", "credit", "risk"), F("f5", "risk", "senior", "High", "prob: 0.3"),
           F("f6", "risk", "auto", "Low", "prob: 0.7"), F("f7", "senior", "risk_join"), F("f8", "auto", "risk_join"),
           F("f9", "and_split", "loop_join"), F("f10", "loop_join", "docs"), F("f11", "docs", "docs_ok"),
           F("f12", "docs_ok", "docs_result", "Yes", "prob: 0.75"), F("f13", "docs_ok", "request", "No", "prob: 0.25"),
           F("f14", "request", "received"), F("f15", "received", "loop_join", "Yes", "prob: 0.8"),
           F("f16", "received", "failed", "No", "prob: 0.2"), F("f17", "failed", "docs_result"),
           F("f18", "risk_join", "and_join"), F("f19", "docs_result", "and_join"),
           F("f20", "and_join", "decide"), F("f21", "decide", "approved"),
           F("f22", "approved", "approve", "Yes", "prob: 0.7"), F("f23", "approved", "reject", "No", "prob: 0.3"),
           F("f24", "approve", "dec_join"), F("f25", "reject", "dec_join"),
           F("f26", "dec_join", "notify"), F("f27", "notify", "end")]))

# Demo models ---------------------------------------------------------------
SPECS.append(dict(key="D1_order_fulfilment", title="D1 Order fulfilment (sound)", nodes=[
    S("start", 0, 1, "Order placed"), T("receive", "Receive order", 1, 1), X("stock", "In stock?", 2, 1),
    A("and_split", "", 3, 0), T("pick", "Pick and pack items", 4, 0), T("pay", "Process payment", 4, 2),
    A("and_join", "", 5, 0), T("ship", "Ship order", 6, 0), E("end", 7, 0, "Order shipped"),
    T("oos", "Notify out of stock", 4, 3), E("end2", 7, 3, "Order cancelled")],
    flows=[F("f1", "start", "receive"), F("f2", "receive", "stock"), F("f3", "stock", "and_split", "Yes"),
           F("f4", "stock", "oos", "No"), F("f5", "and_split", "pick"), F("f6", "and_split", "pay"),
           F("f7", "pick", "and_join"), F("f8", "pay", "and_join"), F("f9", "and_join", "ship"),
           F("f10", "ship", "end"), F("f11", "oos", "end2")]))

SPECS.append(dict(key="D2_insurance_claim", title="D2 Insurance claim (XOR-split closed by AND-join)", nodes=[
    S("start", 0, 1, "Claim filed"), T("register", "Register claim", 1, 1), X("size", "Claim size?", 2, 1),
    T("auto", "Auto-approve small claim", 3, 0), T("assess", "Assess damage on site", 3, 2),
    A("join", "", 4, 1), T("pay", "Pay claim", 5, 1), E("end", 6, 1, "Claim closed")],
    flows=[F("f1", "start", "register"), F("f2", "register", "size"), F("f3", "size", "auto", "Small"),
           F("f4", "size", "assess", "Large"), F("f5", "auto", "join"), F("f6", "assess", "join"),
           F("f7", "join", "pay"), F("f8", "pay", "end")]))

SPECS.append(dict(key="D3_leave_request", title="D3 Leave request (AND-split closed by XOR-join: lack of synchronisation)", nodes=[
    S("start", 0, 1, "Request submitted"), T("submit", "Submit leave request", 1, 1), A("split", "", 2, 1),
    T("manager", "Manager approval", 3, 0), T("hr", "HR balance check", 3, 2), X("join", "", 4, 1),
    T("calendar", "Update team calendar", 5, 1), E("end", 6, 1, "Leave booked")],
    flows=[F("f1", "start", "submit"), F("f2", "submit", "split"), F("f3", "split", "manager"),
           F("f4", "split", "hr"), F("f5", "manager", "join"), F("f6", "hr", "join"),
           F("f7", "join", "calendar"), F("f8", "calendar", "end")]))

SPECS.append(dict(key="D4_hospital_admission", title="D4 Hospital admission (bed and doctor taken in opposite order)",
    doc="resources: bed=1, doctor=1", nodes=[
    S("start", 0, 1, "Patient arrives"), T("triage", "Triage patient", 1, 1), A("split", "", 2, 1),
    T("a_bed", "Reserve bed", 3, 0, "acquire: bed"), T("a_doc", "Assign doctor", 4, 0, "acquire: doctor"),
    T("admit", "Admit to ward", 5, 0, "release: bed, doctor"),
    T("b_doc", "Assign doctor (tests)", 3, 2, "acquire: doctor"), T("b_bed", "Reserve bed (tests)", 4, 2, "acquire: bed"),
    T("tests", "Run bedside tests", 5, 2, "release: bed, doctor"), A("join", "", 6, 1),
    T("plan", "Create care plan", 7, 1), E("end", 8, 1, "Admitted")],
    flows=[F("f1", "start", "triage"), F("f2", "triage", "split"), F("f3", "split", "a_bed"),
           F("f4", "a_bed", "a_doc"), F("f5", "a_doc", "admit"), F("f6", "split", "b_doc"),
           F("f7", "b_doc", "b_bed"), F("f8", "b_bed", "tests"), F("f9", "admit", "join"),
           F("f10", "tests", "join"), F("f11", "join", "plan"), F("f12", "plan", "end")]))

SPECS.append(dict(key="D5_purchase_order_loop", title="D5 Purchase order revision loop (AND-join at loop entry)", nodes=[
    S("start", 0, 0, "Need identified"), T("create", "Create purchase order", 1, 0), A("merge", "", 2, 0),
    T("review", "Review purchase order", 3, 0), X("ok", "Approved?", 4, 0), T("send", "Send PO to supplier", 5, 0),
    E("end", 6, 0, "PO sent"), T("revise", "Revise purchase order", 5, 1)],
    flows=[F("f1", "start", "create"), F("f2", "create", "merge"), F("f3", "merge", "review"),
           F("f4", "review", "ok"), F("f5", "ok", "send", "Yes"), F("f6", "send", "end"),
           F("f7", "ok", "revise", "No"), F("f8", "revise", "merge")]))

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for spec in SPECS:
        path = OUT / f"{spec['key']}.bpmn"
        path.write_text(build(spec), encoding="utf-8")
        print("wrote", path.name)
