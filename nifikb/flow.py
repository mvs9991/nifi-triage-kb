"""Load a NiFi flow into one normalized model.

Supported inputs:
  * conf/flow.json.gz            (NiFi 1.16+ / 2.x)
  * conf/flow.xml.gz             (NiFi 1.x, older installs only have this one)
  * exported flow definitions    ("Download flow definition" / NiFi Registry snapshot JSON)
"""
import gzip
import json
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

NODE_KINDS = ("PROCESSOR", "INPUT_PORT", "OUTPUT_PORT", "FUNNEL", "REMOTE_INPUT_PORT", "REMOTE_OUTPUT_PORT")


class Flow:
    def __init__(self, source, fmt):
        self.source = str(source)
        self.format = fmt
        self.root_id = None
        self.groups = {}          # id -> {id, name, parent_id, comments, variables, parameter_context, path}
        self.components = {}      # id -> processor / port / funnel / remote port
        self.services = {}        # id -> controller service
        self.connections = []     # {id, name, source_id, dest_id, relationships, group_id, ...}
        self.labels = []          # {group_id, text}
        self.param_contexts = {}  # name -> {params: {name: {value, sensitive, description}}, inherits: [names]}
        self.reporting_tasks = []
        self.aliases = {}         # instance id / versioned id -> canonical id

    def resolve_id(self, ident):
        return self.aliases.get(ident, ident)

    def alias(self, other, canonical):
        if other and other != canonical:
            self.aliases[other] = canonical

    def group_chain(self, group_id):
        """Group ids from the given group up to the root."""
        chain = []
        while group_id and group_id in self.groups and group_id not in chain:
            chain.append(group_id)
            group_id = self.groups[group_id]["parent_id"]
        return chain

    def nifi_version(self):
        versions = Counter(
            c["bundle"].get("version")
            for c in list(self.components.values()) + list(self.services.values())
            if c.get("bundle", {}).get("group") == "org.apache.nifi" and c["bundle"].get("version")
        )
        return versions.most_common(1)[0][0] if versions else None

    def finish(self):
        for gid, g in self.groups.items():
            names = [self.groups[x]["name"] for x in reversed(self.group_chain(gid))]
            g["path"] = " / ".join(names)
            g["depth"] = len(names) - 1
        # Connections can point at components we did not see (remote ports of old exports, broken flows).
        for c in self.connections:
            for end in ("source", "dest"):
                cid = c[f"{end}_id"] = self.resolve_id(c[f"{end}_id"])
                if cid not in self.components:
                    self.components[cid] = _component(
                        cid, None, c.get(f"{end}_type") or "UNKNOWN", c.get(f"{end}_name") or "?", None, {},
                        c.get(f"{end}_group_id") or c["group_id"], placeholder=True)
        return self


def _component(cid, instance_id, kind, name, ctype, bundle, group_id, **extra):
    comp = {
        "id": cid, "instance_id": instance_id, "kind": kind, "name": name or "", "type": ctype or "",
        "bundle": bundle or {}, "group_id": group_id, "properties": {}, "state": None,
        "scheduling_strategy": None, "scheduling_period": None, "concurrent_tasks": None,
        "auto_terminated": [], "comments": "", "execution_node": None, "placeholder": False,
    }
    comp.update(extra)
    return comp


def load_flow(path):
    path = Path(path)
    data = path.read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    text = data.decode("utf-8-sig")
    if text.lstrip().startswith("<"):
        return _load_xml(path, ET.fromstring(text)).finish()
    return _load_json(path, json.loads(text)).finish()


# ----------------------------------------------------------------------------------------------- JSON

def _load_json(path, doc):
    if "rootGroup" in doc:
        flow, root, contexts = Flow(path, "flow.json"), doc["rootGroup"], doc.get("parameterContexts") or []
        for cs in doc.get("controllerServices") or []:
            _json_service(flow, cs, None)
        flow.reporting_tasks = [
            {"name": r.get("name"), "type": r.get("type"), "properties": r.get("properties") or {}}
            for r in doc.get("reportingTasks") or []
        ]
    elif "flowContents" in doc:
        flow, root, contexts = Flow(path, "flow-definition"), doc["flowContents"], doc.get("parameterContexts") or {}
    else:
        raise ValueError(f"{path}: not a NiFi flow (no rootGroup / flowContents)")
    if isinstance(contexts, dict):
        contexts = list(contexts.values())
    for pc in contexts:
        flow.param_contexts[pc["name"]] = {
            "params": {
                p["name"]: {"value": p.get("value"), "sensitive": bool(p.get("sensitive")), "description": p.get("description")}
                for p in pc.get("parameters") or []
            },
            "inherits": list(pc.get("inheritedParameterContexts") or []),
            "description": pc.get("description"),
        }
    _json_group(flow, root, None)
    flow.root_id = root.get("identifier")
    return flow


def _json_vc(c):
    if not c:
        return None
    return {"registry": c.get("registryUrl") or c.get("registryId") or c.get("storageLocation"), "bucket": c.get("bucketId"),
            "flow": c.get("flowId"), "flow_name": c.get("flowName"), "version": c.get("version"), "latest": c.get("latest")}


def _xml_vc(el):
    if el is None:
        return None
    return {"registry": _t(el, "registryId"), "bucket": _t(el, "bucketName") or _t(el, "bucketId"), "bucket_id": _t(el, "bucketId"),
            "flow": _t(el, "flowId"), "flow_name": _t(el, "flowName"), "version": _t(el, "version")}


def _json_group(flow, g, parent_id):
    gid = g.get("identifier")
    flow.alias(g.get("instanceIdentifier"), gid)
    flow.groups[gid] = {
        "id": gid, "name": g.get("name") or "NiFi Flow", "parent_id": parent_id, "comments": g.get("comments") or "",
        "variables": dict(g.get("variables") or {}), "parameter_context": g.get("parameterContextName"),
        "versioned": bool(g.get("versionedFlowCoordinates")), "instance_id": g.get("instanceIdentifier") or gid,
        "version_control": _json_vc(g.get("versionedFlowCoordinates")),
    }
    for p in g.get("processors") or []:
        _json_component(flow, p, "PROCESSOR", gid)
    for p in g.get("inputPorts") or []:
        _json_component(flow, p, "INPUT_PORT", gid)
    for p in g.get("outputPorts") or []:
        _json_component(flow, p, "OUTPUT_PORT", gid)
    for f in g.get("funnels") or []:
        _json_component(flow, f, "FUNNEL", gid)
    for rpg in g.get("remoteProcessGroups") or []:
        target = rpg.get("targetUris") or rpg.get("targetUri") or ""
        for kind, key in (("REMOTE_INPUT_PORT", "inputPorts"), ("REMOTE_OUTPUT_PORT", "outputPorts")):
            for port in rpg.get(key) or []:
                comp = _json_component(flow, port, kind, gid)
                comp["name"] = f"{rpg.get('name') or target} :: {port.get('name')}"
                comp["type"] = f"remote site-to-site {target}"
    for cs in g.get("controllerServices") or []:
        _json_service(flow, cs, gid)
    for c in g.get("connections") or []:
        src, dst = c.get("source") or {}, c.get("destination") or {}
        flow.alias(c.get("instanceIdentifier"), c.get("identifier"))
        flow.connections.append({
            "id": c.get("identifier"), "name": c.get("name") or "", "group_id": gid,
            "source_id": src.get("id"), "source_type": src.get("type"), "source_name": src.get("name"), "source_group_id": src.get("groupId"),
            "dest_id": dst.get("id"), "dest_type": dst.get("type"), "dest_name": dst.get("name"), "dest_group_id": dst.get("groupId"),
            "relationships": sorted(c.get("selectedRelationships") or []),
            "backpressure": f"{c.get('backPressureObjectThreshold')} / {c.get('backPressureDataSizeThreshold')}",
            "expiration": c.get("flowFileExpiration"), "prioritizers": c.get("prioritizers") or [],
            "load_balance": c.get("loadBalanceStrategy"),
        })
    for label in g.get("labels") or []:
        if (label.get("label") or "").strip():
            flow.labels.append({"group_id": gid, "text": label["label"].strip()})
    for child in g.get("processGroups") or []:
        _json_group(flow, child, gid)


def _json_component(flow, p, kind, gid):
    cid = p.get("identifier")
    flow.alias(p.get("instanceIdentifier"), cid)
    comp = _component(
        cid, p.get("instanceIdentifier"), kind, p.get("name") or ("funnel" if kind == "FUNNEL" else ""), p.get("type"),
        p.get("bundle"), gid,
        properties={k: v for k, v in (p.get("properties") or {}).items() if v is not None},
        state="STOPPED" if p.get("scheduledState") == "ENABLED" else p.get("scheduledState"), scheduling_strategy=p.get("schedulingStrategy"),
        scheduling_period=p.get("schedulingPeriod"), concurrent_tasks=p.get("concurrentlySchedulableTaskCount"),
        auto_terminated=sorted(p.get("autoTerminatedRelationships") or []), comments=p.get("comments") or "",
        execution_node=p.get("executionNode"), annotation_data=p.get("annotationData") or "",
    )
    flow.components[cid] = comp
    return comp


def _json_service(flow, cs, gid):
    sid = cs.get("identifier")
    flow.alias(cs.get("instanceIdentifier"), sid)
    flow.services[sid] = _component(
        sid, cs.get("instanceIdentifier"), "CONTROLLER_SERVICE", cs.get("name"), cs.get("type"), cs.get("bundle"), gid,
        properties={k: v for k, v in (cs.get("properties") or {}).items() if v is not None},
        state=cs.get("scheduledState"), comments=cs.get("comments") or "",
    )


# ------------------------------------------------------------------------------------------------ XML

def _t(el, tag, default=None):
    child = el.find(tag)
    return child.text if child is not None and child.text is not None else default


def _props(el):
    return {_t(p, "name"): _t(p, "value") for p in el.findall("property") if _t(p, "value") is not None}


def _bundle(el):
    b = el.find("bundle")
    return {"group": _t(b, "group"), "artifact": _t(b, "artifact"), "version": _t(b, "version")} if b is not None else {}


def _load_xml(path, root_el):
    flow = Flow(path, "flow.xml")
    ctx_names = {}
    for pc in root_el.findall("./parameterContexts/parameterContext"):
        name = _t(pc, "name")
        ctx_names[_t(pc, "id")] = name
        flow.param_contexts[name] = {
            "params": {
                _t(p, "name"): {"value": _t(p, "value"), "sensitive": _t(p, "sensitive") == "true", "description": _t(p, "description")}
                for p in pc.findall("parameter")
            },
            "inherits": [x.text for x in pc.findall("inheritedParameterContextId") if x.text],
            "description": _t(pc, "description"),
        }
    for ctx in flow.param_contexts.values():
        ctx["inherits"] = [ctx_names.get(i, i) for i in ctx["inherits"]]
    rg = root_el.find("rootGroup")
    _xml_group(flow, rg, None, ctx_names)
    flow.root_id = _t(rg, "id")
    for cs in root_el.findall("./controllerServices/controllerService"):
        _xml_service(flow, cs, None)
    for rt in root_el.findall("./reportingTasks/reportingTask"):
        flow.reporting_tasks.append({"name": _t(rt, "name"), "type": _t(rt, "class"), "properties": _props(rt)})
    return flow


def _xml_group(flow, g, parent_id, ctx_names):
    gid = _t(g, "id")
    flow.alias(_t(g, "versionedComponentId"), gid)
    flow.groups[gid] = {
        "id": gid, "name": _t(g, "name") or "NiFi Flow", "parent_id": parent_id, "comments": _t(g, "comment", ""),
        "variables": {v.get("name"): v.get("value") for v in g.findall("variable")},
        "parameter_context": ctx_names.get(_t(g, "parameterContextId")), "versioned": g.find("versionControlInformation") is not None,
        "instance_id": gid, "version_control": _xml_vc(g.find("versionControlInformation")),
    }
    for p in g.findall("processor"):
        pid = _t(p, "id")
        flow.alias(_t(p, "versionedComponentId"), pid)
        flow.components[pid] = _component(
            pid, pid, "PROCESSOR", _t(p, "name"), _t(p, "class"), _bundle(p), gid, properties=_props(p),
            state=_t(p, "scheduledState"), scheduling_strategy=_t(p, "schedulingStrategy"),
            scheduling_period=_t(p, "schedulingPeriod"), concurrent_tasks=int(_t(p, "maxConcurrentTasks", "1")),
            auto_terminated=sorted(x.text for x in p.findall("autoTerminatedRelationship") if x.text),
            comments=_t(p, "comment", ""), execution_node=_t(p, "executionNode"), annotation_data=_t(p, "annotationData", ""),
        )
    for tag, kind in (("inputPort", "INPUT_PORT"), ("outputPort", "OUTPUT_PORT"), ("funnel", "FUNNEL")):
        for p in g.findall(tag):
            pid = _t(p, "id")
            flow.alias(_t(p, "versionedComponentId"), pid)
            flow.components[pid] = _component(pid, pid, kind, _t(p, "name", "funnel" if kind == "FUNNEL" else ""), None, {}, gid,
                                              state=_t(p, "scheduledState"), comments=_t(p, "comments", ""))
    for rpg in g.findall("remoteProcessGroup"):
        target = _t(rpg, "urls") or _t(rpg, "url") or ""
        for tag, kind in (("inputPort", "REMOTE_INPUT_PORT"), ("outputPort", "REMOTE_OUTPUT_PORT")):
            for port in rpg.findall(tag):
                pid = _t(port, "id")
                flow.alias(_t(port, "versionedComponentId"), pid)
                flow.components[pid] = _component(pid, pid, kind, f"{_t(rpg, 'name') or target} :: {_t(port, 'name')}",
                                                  f"remote site-to-site {target}", {}, gid)
    for cs in g.findall("controllerService"):
        _xml_service(flow, cs, gid)
    for c in g.findall("connection"):
        flow.alias(_t(c, "versionedComponentId"), _t(c, "id"))
        flow.connections.append({
            "id": _t(c, "id"), "name": _t(c, "name", ""), "group_id": gid,
            "source_id": _t(c, "sourceId"), "source_type": _t(c, "sourceType"), "source_name": None, "source_group_id": _t(c, "sourceGroupId"),
            "dest_id": _t(c, "destinationId"), "dest_type": _t(c, "destinationType"), "dest_name": None, "dest_group_id": _t(c, "destinationGroupId"),
            "relationships": sorted(x.text for x in c.findall("relationship") if x.text),
            "backpressure": f"{_t(c, 'maxWorkQueueSize')} / {_t(c, 'maxWorkQueueDataSize')}",
            "expiration": _t(c, "flowFileExpiration"),
            "prioritizers": [x.text for x in c.findall("queuePrioritizerClass") if x.text],
            "load_balance": _t(c, "loadBalanceStrategy"),
        })
    for label in g.findall("label"):
        if (_t(label, "value") or "").strip():
            flow.labels.append({"group_id": gid, "text": _t(label, "value").strip()})
    for child in g.findall("processGroup"):
        _xml_group(flow, child, gid, ctx_names)


def _xml_service(flow, cs, gid):
    sid = _t(cs, "id")
    flow.alias(_t(cs, "versionedComponentId"), sid)
    flow.services[sid] = _component(
        sid, sid, "CONTROLLER_SERVICE", _t(cs, "name"), _t(cs, "class"), _bundle(cs), gid, properties=_props(cs),
        state="ENABLED" if _t(cs, "enabled") == "true" else "DISABLED", comments=_t(cs, "comment", ""),
    )
