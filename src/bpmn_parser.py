"""BPMN 2.0 XML parser for process models and annotations."""
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

# BPMN tag  ->  our simple node kind
KIND = {
    "startEvent": "start", "endEvent": "end",
    "exclusiveGateway": "xor", "eventBasedGateway": "xor",
    "parallelGateway": "and", "inclusiveGateway": "or",
    "intermediateCatchEvent": "task", "intermediateThrowEvent": "task",
    "subProcess": "task", "callActivity": "task",
}


@dataclass
class Node:
    id: str
    kind: str            # start | end | task | xor | and | or
    name: str
    doc: dict = field(default_factory=dict)


@dataclass
class Flow:
    id: str
    src: str
    tgt: str
    name: str = ""
    doc: dict = field(default_factory=dict)


@dataclass
class BpmnModel:
    name: str
    nodes: dict
    flows: dict
    resources: dict
    xml: str
    warnings: list = field(default_factory=list)

    def incoming(self, node_id):
        return [f for f in self.flows.values() if f.tgt == node_id]

    def outgoing(self, node_id):
        return [f for f in self.flows.values() if f.src == node_id]

    def label(self, node_id):
        n = self.nodes[node_id]
        if n.name:
            return n.name
        if n.kind in ("xor", "and", "or"):
            ins, outs = len(self.incoming(node_id)), len(self.outgoing(node_id))
            role = "join" if ins > 1 and outs <= 1 else "split" if outs > 1 and ins <= 1 else "gateway"
            if n.kind == "xor" and role == "join":
                role = "merge"
            return f"{n.kind.upper()}-{role}"
        return n.kind


def parse_doc(text):
    """'time: 20; acquire: officer' -> {'time': '20', 'acquire': 'officer'}"""
    out = {}
    if not text:
        return out
    for part in text.replace("\n", ";").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _local(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def _doc_of(el):
    d = el.find(f"{{{NS}}}documentation")
    return parse_doc(d.text if d is not None else "")


def parse_bpmn(xml_text):
    """Parse BPMN XML text and return a BpmnModel."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    processes = root.findall(f"{{{NS}}}process")
    if not processes:
        raise ValueError("No <bpmn:process> found in this file.")
    # use the first process that actually has a start event
    proc = next((p for p in processes if p.find(f"{{{NS}}}startEvent") is not None), processes[0])

    nodes, flows, warnings = {}, {}, []
    for el in proc:
        tag = _local(el.tag)
        if tag in ("documentation", "extensionElements", "laneSet", "textAnnotation",
                   "association", "dataObject", "dataObjectReference", "dataStoreReference"):
            continue
        if tag == "sequenceFlow":
            flows[el.get("id")] = Flow(el.get("id"), el.get("sourceRef"), el.get("targetRef"),
                                       el.get("name") or "", _doc_of(el))
            continue
        if tag == "boundaryEvent":
            warnings.append(f"Boundary event '{el.get('id')}' is ignored.")
            continue
        kind = KIND.get(tag)
        if kind is None and tag.lower().endswith("task"):
            kind = "task"
        if kind is None:
            warnings.append(f"Element <{tag}> '{el.get('id')}' is not supported and was skipped.")
            continue
        if kind == "or":
            warnings.append(f"Inclusive (OR) gateway '{el.get('id')}': OR-join is approximated as XOR-join.")
        nodes[el.get("id")] = Node(el.get("id"), kind, (el.get("name") or "").strip(), _doc_of(el))

    # drop flows that point at skipped elements
    for fid in [f for f, fl in flows.items() if fl.src not in nodes or fl.tgt not in nodes]:
        warnings.append(f"Sequence flow '{fid}' connects unsupported elements and was skipped.")
        del flows[fid]

    resources = {}
    for item in _doc_of(proc).get("resources", "").split(","):
        if "=" in item:
            r, n = item.split("=", 1)
            resources[r.strip()] = int(n.strip())

    return BpmnModel(proc.get("name") or proc.get("id"), nodes, flows, resources, xml_text, warnings)


def load_bpmn(path):
    with open(path, encoding="utf-8") as fh:
        return parse_bpmn(fh.read())
