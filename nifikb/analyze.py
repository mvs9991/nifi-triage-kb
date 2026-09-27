"""Turn a parsed Flow + NAR catalog + code index into facts: resolved properties, external resources,
hardcoded values, lint findings, flow tags and the connection graph."""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

from . import sqlparse
from .util import (EL_REF_RE, EL_VAR_RE, JDBC_RE, PARAM_RE, REDACTED, SECRET_NAME, UNIX_PATH_RE, URL_RE,
                   WIN_PATH_RE, clip, short)

EL_FUNCS = {"now", "uuid", "UUID", "hostname", "ip", "nextInt", "random", "literal", "thread", "getStateValue", "anyAttribute",
            "allAttributes", "anyMatchingAttribute", "allMatchingAttributes", "anyDelineatedValue", "allDelineatedValues",
            "getUri", "math", "toRadians"}
CORE_ATTRS = {"filename", "path", "absolute.path", "uuid", "mime.type", "fileSize", "entryDate", "lineageStartDate"}

# (resource kind, regex on "<raw name> <display name>")
NAME_RULES = [
    ("db_table", re.compile(r"(?i)table[ _-]?name|table-name|db-fetch-table|put-db-record-table|\btable\b(?!.*(?:cache|schema|columns|count))")),
    ("sql", re.compile(r"(?i)\bsql\b|query|statement|sql-select|sql-pre|sql-post|putsql")),
    ("s3_bucket", re.compile(r"(?i)\bbucket\b")),
    ("object_key", re.compile(r"(?i)object key|^key\b|prefix")),
    ("file_path", re.compile(r"(?i)director|path|file to fetch|folder|\bfile\b|filename|location")),
    ("host", re.compile(r"(?i)host|server|bootstrap|broker|endpoint|address")),
    ("port", re.compile(r"(?i)\bport\b|listening port")),
    ("topic", re.compile(r"(?i)topic|queue name|destination name|subject|channel")),
    ("command", re.compile(r"(?i)command|script file|script body|module directory|executable")),
    ("email", re.compile(r"(?i)^(to|from|cc|bcc)$|recipient|sender|email")),
]
SQL_NAME_EXCLUDE = re.compile(r"(?i)timeout|size|fetch|max|cache|type|columns|strategy|column|rows|batch|translate|normaliz|quote|output|format")
SQL_TABLE_EXCLUDE = re.compile(r"(?i)schema-cache|cache-size|column|strategy|translat|behavior|quot")
SCRIPT_EXT = re.compile(r"[^\s\"';|&]+\.(?:py|groovy|sh|bash|js|rb|jar|ps1|bat|cmd|sql|jython|clj|lua)\b", re.I)

TAG_RULES = [
    ("api-in", re.compile(r"ListenHTTP|HandleHttpRequest|ListenTCP|ListenUDP|ListenSyslog|ListenWebSocket")),
    ("api-call", re.compile(r"InvokeHTTP|GetHTTP|PostHTTP|InvokeAWSGatewayApi|ConnectWebSocket")),
    ("s3", re.compile(r"S3")), ("azure", re.compile(r"Azure|ADLS")), ("gcs", re.compile(r"GCS|BigQuery|PubSub")),
    ("sftp/ftp", re.compile(r"SFTP|FTP")), ("local-file", re.compile(r"\b(GetFile|ListFile|FetchFile|PutFile|TailFile)\b")),
    ("hdfs", re.compile(r"HDFS")), ("kafka", re.compile(r"Kafka")), ("jms", re.compile(r"JMS|AMQP|MQTT")),
    ("db-write", re.compile(r"PutDatabaseRecord|PutSQL|ConvertJSONToSQL|PutMongo|PutElasticsearch|PutCassandra|PutHive")),
    ("db-read", re.compile(r"ExecuteSQL|QueryDatabaseTable|GenerateTableFetch|ListDatabaseTables|GetMongo|LookupRecord|DatabaseRecordLookup")),
    ("json", re.compile(r"(?i)json|jolt")), ("csv", re.compile(r"CSV")), ("xml", re.compile(r"XML|XPath|XQuery")),
    ("avro", re.compile(r"Avro")), ("parquet", re.compile(r"Parquet")),
    ("script", re.compile(r"ExecuteStreamCommand|ExecuteProcess|ExecuteScript|ExecuteGroovyScript|InvokeScripted|ExecutePython")),
    ("email", re.compile(r"PutEmail|ConsumeIMAP|ConsumePOP3")), ("archive/zip", re.compile(r"CompressContent|UnpackContent|MergeContent")),
    ("routing", re.compile(r"RouteOnAttribute|RouteOnContent|RouteText|QueryRecord|PartitionRecord")),
]
WRITES_ATTR_PROCS = ("UpdateAttribute", "EvaluateJsonPath", "EvaluateXPath", "EvaluateXQuery", "ExtractText", "ExtractGrok",
                     "GenerateFlowFile", "LookupAttribute")
# Properties whose literal value names an attribute the processor writes (ExecuteStreamCommand "Output Destination Attribute", ...)
ATTR_NAME_PROP = re.compile(r"(?i)(destination|output|result|target|response|put\s+cache\s+value\s+in).*attribute|attribute[\s._-]*name")
# Processors whose written attribute names cannot be known statically (scripts, HTTP / message headers)
UNKNOWN_WRITERS = {"ExecuteScript", "ExecuteGroovyScript", "InvokeScriptedProcessor", "ScriptedTransformRecord", "ExecuteClojure",
                   "InvokeHTTP", "HandleHttpRequest", "ListenHTTP", "GetHTTP", "ConsumeJMS", "ConsumeMQTT", "ConsumeAMQP", "ConsumeGCPubSub",
                   "ExtractEmailHeaders", "ExtractHL7Attributes", "ConsumeAzureEventHub", "GetSQS", "ConsumeKinesisStream"}
DYNAMIC_REL_PROCS = ("RouteOnAttribute", "RouteOnContent", "RouteText", "QueryRecord", "PartitionRecord", "RouteHL7")


def type_short(t):
    return (t or "").rsplit(".", 1)[-1]


class Analysis:
    def __init__(self, flow, catalog, code_index, config=None):
        self.flow, self.catalog, self.code, self.config = flow, catalog, code_index, config or {}
        self.props = defaultdict(list)       # component id -> [property facts]
        self.resources = []                  # {kind, value, component_id, source, detail}
        self.findings = []                   # {severity, kind, component_id, message, location}
        self.attrs_written = defaultdict(set)
        self.attrs_read = defaultdict(set)
        self.attr_reads = defaultdict(list)  # component id -> [(attribute, where, from a default value)]
        self.out_edges = defaultdict(list)   # id -> [(connection, dest_id)]
        self.in_edges = defaultdict(list)
        self.custom = {}                     # type -> {code: [...], nar: ..., used_by: [...]}
        self.scripts = {}                    # resolved script path -> {used_by, exists, index}
        self.field_checks = []               # PutDatabaseRecord record fields vs. table columns (filled by db step)
        self.jdbc = {}                       # service id -> parsed jdbc info
        self.service_users = {}              # service id -> [component ids referencing it]
        self.res_by_comp = defaultdict(list)  # component id -> [resources]
        self.children = defaultdict(list)    # group id -> child group ids
        self._memo = {}

    # ---------------------------------------------------------------------------------------- driver
    def run(self):
        for gid, g in self.flow.groups.items():
            if g["parent_id"]:
                self.children[g["parent_id"]].append(gid)
        for c in self.flow.connections:
            self.out_edges[c["source_id"]].append((c, c["dest_id"]))
            self.in_edges[c["dest_id"]].append((c, c["source_id"]))
        for comp in list(self.flow.components.values()) + list(self.flow.services.values()):
            self._analyze_properties(comp)
        for comp in self.flow.components.values():
            if comp["kind"] == "PROCESSOR":
                self._lint_processor(comp)
        self._lint_services()
        self._lint_secret_config()
        self._custom_components()
        self._attribute_lineage()
        self._parse_jdbc()
        return self

    # ------------------------------------------------------------------------------------ properties
    def ext(self, comp):
        """Extension info for a component: the NAR manifest, or - for custom NARs built without docs - what the Java
        source says (property display names, defaults, sensitivity, services, relationships, attributes)."""
        t = comp.get("type")
        if not t:
            return None
        e = self.catalog.get(t)
        if e and e.get("has_manifest"):
            return e
        code = self.code.by_fqcn.get(t)
        if not code:
            return e
        key = ("code_ext", t)
        if key not in self._memo:
            c = code[0]["component"]
            self._memo[key] = {
                "type": t, "kind": c["kind"], "description": c.get("description") or "", "tags": c.get("tags") or [],
                "properties": {p["name"]: {"displayName": p.get("displayName") or p["name"], "description": p.get("description") or "",
                                           "default": p.get("default"), "required": p.get("required"), "sensitive": p.get("sensitive"),
                                           "el_scope": "FLOWFILE_ATTRIBUTES" if p.get("el") else None, "service_api": p.get("service"),
                                           "allowable": {v: v for v in p.get("allowable") or []}}
                               for p in c.get("properties") or []},
                "relationships": [{"name": r["name"], "description": r.get("description") or "", "auto_terminated": False}
                                  for r in c.get("relationships") or []],
                "dynamic_relationships": False, "dynamic_properties": bool(c.get("dynamic_properties")),
                "reads_attributes": c.get("reads_attributes") or [], "writes_attributes": c.get("writes_attributes") or [],
                "input_requirement": c.get("input_requirement"), "has_manifest": False, "from_code": True,
                "nar": (e or {}).get("nar"), "nar_group": (e or {}).get("nar_group"),
            }
        return self._memo[key]

    def variables(self, group_id):
        out = {}
        for gid in reversed(self.flow.group_chain(group_id)):
            out.update(self.flow.groups[gid].get("variables") or {})
        return out

    def params(self, group_id):
        g = self.flow.groups.get(group_id) or {}
        out, seen = {}, set()

        def walk(ctx_name):
            if not ctx_name or ctx_name in seen or ctx_name not in self.flow.param_contexts:
                return
            seen.add(ctx_name)
            ctx = self.flow.param_contexts[ctx_name]
            for k, v in ctx["params"].items():
                out.setdefault(k, v)
            for inherited in ctx["inherits"]:
                walk(inherited)

        walk(g.get("parameter_context"))
        return out

    def resolve(self, value, group_id):
        """Substitute #{params} and ${variables}; runtime attributes stay as ${...}."""
        params, variables = self.params(group_id), self.variables(group_id)

        def p(m):
            name = (m.group(1) or m.group(2)).strip()
            if name not in params:
                return m.group(0)
            v = params[name]
            if v["sensitive"]:
                return "<sensitive>"
            if SECRET_NAME.search(name):
                return REDACTED
            return v["value"] if v["value"] is not None else m.group(0)

        def var(m):
            if m.group(1) not in variables:
                return m.group(0)
            return REDACTED if SECRET_NAME.search(m.group(1)) else variables[m.group(1)]

        out = PARAM_RE.sub(p, value)
        out = EL_VAR_RE.sub(var, out)
        return out

    def _analyze_properties(self, comp):
        ext = self.ext(comp)
        descs = (ext or {}).get("properties", {})
        gid = comp["group_id"]
        variables = self.variables(gid)
        tshort = type_short(comp["type"])
        for name, value in comp["properties"].items():
            if value is None:
                continue
            d = descs.get(name)
            display = d["displayName"] if d else name
            dynamic = bool(ext and ext.get("has_manifest") and d is None)
            fact = {"name": name, "display": display, "value": value, "resolved": value, "source": "literal",
                    "default": False, "dynamic": dynamic, "service": None, "kinds": []}
            if value.startswith("enc{") or (d and d["sensitive"]):
                fact.update(value="<encrypted>" if value.startswith("enc{") else REDACTED, resolved=REDACTED, source="sensitive")
                self.props[comp["id"]].append(fact)
                continue
            service_id = self.flow.resolve_id(value)
            if (d and d.get("service_api")) or service_id in self.flow.services:
                svc = self.flow.services.get(service_id)
                fact.update(source="service", service=service_id, resolved=svc["name"] if svc else f"<missing service {value}>")
                if not svc and not PARAM_RE.search(value):
                    self._finding("error", "missing-service", comp, f"Property '{display}' points to controller service {value} which is not in the flow")
                self.props[comp["id"]].append(fact)
                continue
            if d and d.get("default") is not None and d["default"] == value:
                fact["default"] = True
            if d and d.get("allowable") and value in d["allowable"] and d["allowable"][value] not in (None, value):
                fact["resolved"] = f"{value} ({d['allowable'][value]})"
            has_param, has_el = bool(PARAM_RE.search(value)), "${" in value
            if has_param or has_el:
                fact["resolved"] = self.resolve(value, gid)
                fact["source"] = "parameter" if has_param and not has_el else "expression" if has_el and not has_param else "parameter+expression"
                refs = {m.group(1) for m in EL_REF_RE.finditer(value)}
                guarded = set(re.findall(r"\$\{\s*([\w.\-]+)\s*:\s*(?:isEmpty|isNull|notNull|replaceNull|replaceEmpty)\b", value))
                for ref in refs:
                    if ref not in variables and ref not in EL_FUNCS:
                        self.attrs_read[comp["id"]].add(ref)
                        self.attr_reads[comp["id"]].append((ref, display, fact["default"] or ref in guarded))
                if refs and all(r in variables for r in refs) and not has_param:
                    fact["source"] = "variable"
            elif SECRET_NAME.search(f"{name} {display}") and len(value) > 1 and not (d and d["allowable"]) and value.lower() not in ("true", "false", "none"):
                fact.update(value=REDACTED, resolved=REDACTED)
                self._finding("high", "plaintext-secret", comp, f"Property '{display}' holds a plain-text secret (not a sensitive property or parameter)")
            if dynamic and tshort in WRITES_ATTR_PROCS:
                self.attrs_written[comp["id"]].add(name)
            self._extract_resources(comp, fact)
            self.props[comp["id"]].append(fact)
        cid = comp["id"]
        if ext:
            for a in ext.get("writes_attributes") or []:
                self.attrs_written[cid].add(a)
        code = self.code.by_fqcn.get(comp.get("type") or "")
        if code:  # what the Java code really does, beyond the documented @WritesAttribute / @ReadsAttribute
            c = code[0]["component"]
            self.attrs_written[cid] |= set(c.get("writes_attributes") or [])
            for a in c.get("reads_attributes") or []:
                self.attrs_read[cid].add(a)
                self.attr_reads[cid].append((a, f"code {(c.get('reads_at') or {}).get(a, '')}".strip(), False))
        for f in self.props[cid]:
            if ATTR_NAME_PROP.search(f"{f['name']} {f['display']}") and f["source"] == "literal" and re.fullmatch(r"[\w.\-]+", f["resolved"] or ""):
                self.attrs_written[cid].add(f["resolved"])
        if tshort == "UpdateAttribute" and comp.get("annotation_data"):  # Advanced-UI rules
            self.attrs_written[cid] |= set(re.findall(r"<attribute>\s*([^<]+?)\s*</attribute>", comp["annotation_data"]))
            for m in EL_REF_RE.finditer(comp["annotation_data"]):
                if m.group(1) not in variables and m.group(1) not in EL_FUNCS:
                    self.attrs_read[cid].add(m.group(1))
                    self.attr_reads[cid].append((m.group(1), "advanced rules", False))

    def _extract_resources(self, comp, fact):
        label = f"{fact['name']} {fact['display']}"
        raw, resolved = fact["value"], fact["resolved"]
        literal_part = PARAM_RE.sub("", EL_REF_RE.sub("", raw))
        is_hardcoded = fact["source"] in ("literal", "variable") or bool(
            re.search(r"[A-Za-z]:\\|/[\w.-]+/|://|\.(?:com|net|org|csv|json|xml|py|sql)\b", literal_part))
        kinds = []

        def add(kind, value, detail=None):
            value = clip(value, 300)
            kinds.append(kind)
            res = {"kind": kind, "value": value, "component_id": comp["id"], "property": fact["display"],
                   "source": fact["source"], "hardcoded": is_hardcoded and fact["source"] != "sensitive",
                   "raw": clip(raw, 300), "detail": detail}
            self.resources.append(res)
            self.res_by_comp[comp["id"]].append(res)

        for m in JDBC_RE.finditer(resolved):
            add("jdbc", m.group(0))
        for m in URL_RE.finditer(resolved):
            add("url", m.group(0))
        for kind, rx in NAME_RULES:
            if not rx.search(label) or fact["default"]:
                continue
            if kind == "sql":
                if SQL_NAME_EXCLUDE.search(label) or not sqlparse.looks_like_sql(resolved):
                    continue
                add("sql", resolved, detail=json.dumps(sqlparse.tables(resolved)))
                for t in sqlparse.tables(resolved):
                    add("db_table", t, detail="from SQL")
            elif kind == "db_table":
                if SQL_TABLE_EXCLUDE.search(label) or sqlparse.looks_like_sql(resolved) or len(resolved) > 200                         or resolved.lower() in ("true", "false") or resolved.strip().isdigit():
                    continue
                for t in re.split(r"\s*,\s*", resolved):
                    if t and re.fullmatch(r"[\w$#{}.\-`\"\[\]<> ]+", t):
                        add("db_table", t.strip("`\"[]").lower())
            elif kind == "file_path":
                if WIN_PATH_RE.search(resolved) or UNIX_PATH_RE.search(resolved) or re.search(r"[\\/]", literal_part) or re.match(r"^\.{0,2}/", resolved):
                    add("file_path", resolved)
            elif kind == "port":
                if resolved.strip().isdigit():
                    add("port", resolved.strip())
            elif kind == "host":
                if re.fullmatch(r"[\w.\-:,${}#' ]+", resolved) and not resolved.strip().isdigit() and resolved.lower() not in ("true", "false"):
                    add("host", resolved)
            elif kind == "command":
                add("command", resolved)
                for s in SCRIPT_EXT.findall(resolved):
                    add("script", s)
            elif kind == "s3_bucket" and "S3" in comp["type"] or kind in ("topic", "email") \
                    or kind == "object_key" and "S3" in comp["type"] and fact["source"] != "expression":
                add(kind, resolved)
        fact["kinds"] = sorted(set(kinds))

    # ------------------------------------------------------------------------------------------ lint
    def _finding(self, severity, kind, comp, message, location=None):
        self.findings.append({"severity": severity, "kind": kind, "component_id": comp["id"] if comp else None,
                              "message": message, "location": location})

    def relationships(self, comp):
        ext = self.ext(comp)
        if not ext or not ext.get("has_manifest"):
            return None
        rels = {r["name"] for r in ext["relationships"]}
        if ext.get("dynamic_relationships") or type_short(comp["type"]) in DYNAMIC_REL_PROCS:
            rels |= {f["name"] for f in self.props[comp["id"]] if f["dynamic"]}
        return rels

    def _lint_processor(self, comp):
        rels = self.relationships(comp)
        connected = {r for c, _ in self.out_edges[comp["id"]] for r in c["relationships"]}
        if rels is not None:
            loose = sorted(rels - connected - set(comp["auto_terminated"]))
            if loose and comp["state"] != "DISABLED":
                self._finding("error", "unhandled-relationship", comp,
                              f"Relationship(s) {', '.join(loose)} neither connected nor auto-terminated -> processor is INVALID and will not run")
        dropped = sorted(set(comp["auto_terminated"]) & {"failure", "retry", "invalid", "not.found", "permission.denied", "comms.failure",
                                                         "unmatched", "no retry", "timeout", "nonzero status"})
        if dropped and comp["state"] != "DISABLED":
            self._finding("warn", "dropped-errors", comp, f"{', '.join(dropped)} auto-terminated: failed FlowFiles are silently dropped (no retry/alert)")
        for c, dst in self.out_edges[comp["id"]]:
            target = self.flow.components.get(dst)
            if target and target.get("state") == "DISABLED" and comp["state"] != "DISABLED":
                self._finding("info", "disabled-downstream", comp, f"Routes '{','.join(c['relationships'])}' to DISABLED processor '{target['name']}' ({short(dst)}); data will queue up")
        if comp["type"] and not self.catalog.get(comp["type"]) and self.catalog.types:
            if (comp["bundle"].get("group") or "").startswith("org.apache.nifi"):
                self._finding("warn", "unknown-type", comp, f"Type {comp['type']} not found in any NAR (missing bundle / version mismatch?)")
        ext = self.ext(comp)
        if ext and ext.get("input_requirement") == "INPUT_REQUIRED" and not self.in_edges[comp["id"]] and comp["state"] != "DISABLED":
            self._finding("warn", "no-input", comp, "Processor requires input but has no incoming connection")

    def _lint_services(self):
        used = defaultdict(list)
        for cid, facts in self.props.items():
            for f in facts:
                if f["service"]:
                    used[f["service"]].append(cid)
        self.service_users = used
        for sid, svc in self.flow.services.items():
            users = [self._comp(u) for u in used.get(sid, [])]
            active_users = [u for u in users if u and u.get("state") in ("RUNNING", "ENABLED")]
            if svc.get("state") == "DISABLED" and active_users:
                self._finding("error", "disabled-service", svc, f"Service is DISABLED but used by running component(s): {', '.join(u['name'] for u in active_users)}")

    def _lint_secret_config(self):
        for name, ctx in self.flow.param_contexts.items():
            for pname, p in ctx["params"].items():
                if SECRET_NAME.search(pname) and not p["sensitive"] and p.get("value"):
                    self.findings.append({"severity": "high", "kind": "plaintext-secret", "component_id": None, "location": f"parameter context {name}",
                                          "message": f"parameter '{pname}' in context '{name}' looks like a secret but is not marked sensitive"})
        for gid, g in self.flow.groups.items():
            for vname, v in (g.get("variables") or {}).items():
                if SECRET_NAME.search(vname) and v:
                    self.findings.append({"severity": "high", "kind": "plaintext-secret", "component_id": None, "location": f"variables of {g['path']}",
                                          "message": f"variable '{vname}' in '{g['path']}' holds a plain-text secret"})

    def _comp(self, cid):
        return self.flow.components.get(cid) or self.flow.services.get(cid)

    # --------------------------------------------------------------------------- custom code & scripts
    def is_custom(self, comp):
        group = (comp.get("bundle") or {}).get("group") or ""
        t = comp.get("type") or ""
        if comp["kind"] not in ("PROCESSOR", "CONTROLLER_SERVICE") or not t:
            return False
        return (group and not group.startswith("org.apache.nifi")) or (not group and not t.startswith("org.apache.nifi"))

    def _custom_components(self):
        deployed = defaultdict(set)  # NAR artifact -> versions present in lib / extra dirs
        for n in self.catalog.nars:
            deployed[n.get("artifact")].add(n.get("version"))
        for comp in list(self.flow.components.values()) + list(self.flow.services.values()):
            if self.is_custom(comp) or comp["type"] in self.code.by_fqcn:
                cat = self.catalog.get(comp["type"])
                entry = self.custom.setdefault(comp["type"], {"type": comp["type"], "used_by": [], "code": self.code.by_fqcn.get(comp["type"], []),
                                                              "nar": (cat or {}).get("nar"), "bundle": comp["bundle"], "bundle_versions": []})
                entry["used_by"].append(comp["id"])
                bundle = comp["bundle"] or {}
                if bundle.get("version") not in entry["bundle_versions"]:
                    entry["bundle_versions"].append(bundle.get("version"))
                first = comp["id"] == entry["used_by"][0]
                if not first:
                    continue
                if not entry["code"]:
                    self._finding("warn", "custom-code-missing", comp,
                                  f"Custom type {comp['type']} ({bundle.get('artifact')}) - source code not found in configured repos"
                                  + ("" if entry["nar"] else "; NAR not found either"))
                elif not cat and self.catalog.types:
                    self._finding("error", "custom-nar-missing", comp,
                                  f"Custom type {comp['type']} has source code but no NAR in lib / extra_nar_dirs provides it "
                                  f"(bundle {bundle.get('artifact')} {bundle.get('version')}) -> NiFi shows it as a ghost processor")
                if cat and bundle.get("artifact") in deployed and bundle.get("version") not in deployed[bundle["artifact"]]:
                    self._finding("warn", "bundle-version", comp,
                                  f"Flow uses {bundle['artifact']} {bundle.get('version')} but lib has {', '.join(sorted(v or '?' for v in deployed[bundle['artifact']]))}")
                src = (entry["code"][0]["component"] if entry["code"] else {})
                if src and not src.get("registered") and any(Path(p).name.startswith("org.apache.nifi.") for p in self._service_files(src)):
                    self._finding("warn", "custom-not-registered", comp,
                                  f"{comp['type']} is not listed in its module's META-INF/services file -> NiFi will not load it from a new build")
                dep = (cat or {}).get("deployed")
                strings = self.catalog.jar_strings(dep) if dep and src else set()
                if strings:
                    mod = (src.get("module") or {}).get("dir") or str(Path(entry["code"][0]["path"]).parent)
                    own_file = Path(entry["code"][0]["path"]).name
                    missing = [f"property '{p['name']}'" for p in src.get("properties") or []
                               if p.get("name") and str(p.get("path", "")).startswith(mod) and p["name"] not in strings]
                    missing += [f"relationship '{r['name']}'" for r in src.get("relationships") or []
                                if r.get("name") and str(r.get("path", "")).startswith(mod) and r["name"] not in strings]
                    missing += [f"attribute '{a}'" for a, at in (src.get("writes_at") or {}).items()
                                if at.split(":")[0] == own_file and a not in strings]
                    entry["drift"] = missing
                    if missing:
                        self._finding("warn", "custom-source-drift", comp,
                                      f"repo source of {type_short(comp['type'])} has {', '.join(missing[:6])}"
                                      + (f" (+{len(missing) - 6} more)" if len(missing) > 6 else "")
                                      + f" that the deployed NAR ({Path(dep['jar']).name}) does not contain - the running build is not this source")
            if comp["kind"] == "PROCESSOR":
                self._link_scripts(comp)

    def _service_files(self, src):
        """META-INF/services files in the component's Maven module."""
        mod = (src.get("module") or {}).get("dir")
        if not mod:
            return []
        return [p for p, info in self.code.files.items() if info.get("lang") == "services" and p.startswith(mod)]

    # ------------------------------------------------------------------------------------ attribute lineage
    def unknown_writer(self, comp):
        """True when the attributes this component may add cannot be known statically."""
        kind, tshort = comp["kind"], type_short(comp.get("type") or "")
        if kind == "REMOTE_OUTPUT_PORT" or (kind == "INPUT_PORT" and comp["group_id"] == self.flow.root_id):
            return True
        if kind != "PROCESSOR":
            return False
        if tshort in UNKNOWN_WRITERS:
            return True
        if any(re.search(r"(?i)header.*attribute|attributes?.*header", f"{f['name']} {f['display']}") and f["resolved"]
               for f in self.props[comp["id"]]):
            return True
        if tshort == "UpdateAttribute" and not any(f["dynamic"] for f in self.props[comp["id"]]) and not comp.get("annotation_data"):
            return not self.catalog.get(comp["type"])  # rules not visible and no manifest to tell dynamic properties apart
        code = self.code.by_fqcn.get(comp.get("type") or "")
        if code:
            return bool(code[0]["component"].get("dynamic_writes"))
        if self.is_custom(comp):
            return True  # custom without source: documented attributes only
        return not self.catalog.get(comp["type"])

    def _attribute_lineage(self):
        """Forward data-flow over the graph: which attributes can have been set before each component, and whether an
        unknown writer is upstream. A property reading ${x} with x never set upstream is a classic metadata bug."""
        nodes = [c for c in self.flow.components.values()]
        written = {c["id"]: set(self.attrs_written[c["id"]]) for c in nodes}
        unknown = {c["id"]: self.unknown_writer(c) for c in nodes}
        avail = {c["id"]: set() for c in nodes}
        unk_in = {c["id"]: False for c in nodes}
        work = list(avail)
        queued = set(work)
        while work:
            cid = work.pop()
            queued.discard(cid)
            out_set = avail[cid] | written.get(cid, set())
            out_unk = unk_in[cid] or unknown.get(cid, False)
            for _, dst in self.out_edges[cid]:
                if dst not in avail:
                    continue
                if not out_set <= avail[dst] or (out_unk and not unk_in[dst]):
                    avail[dst] |= out_set
                    unk_in[dst] = unk_in[dst] or out_unk
                    if dst not in queued:
                        queued.add(dst)
                        work.append(dst)
        self.attrs_available, self.unknown_upstream = avail, unk_in
        services_reads = self._service_reads()
        for c in nodes:
            if c["kind"] != "PROCESSOR" or c.get("state") == "DISABLED":
                continue
            reads = [(a, where) for a, where, is_default in self.attr_reads[c["id"]] if not is_default]
            reads += services_reads.get(c["id"], [])
            if not self.in_edges[c["id"]]:
                continue  # source processor: its ${attr} references cannot come from FlowFiles
            have = avail[c["id"]]
            missing = {}
            for a, where in reads:
                if a in CORE_ATTRS or a in have or any(a.startswith(h + ".") for h in have):
                    continue
                missing.setdefault(a, where)
            for a, where in sorted(missing.items()):
                near = self._near(a, have)
                if near:
                    self._finding("warn", "attribute-misnamed", c,
                                  f"reads ${{{a}}} ({where}) but upstream only sets '{near}' - likely a naming mismatch")
                elif not unk_in[c["id"]]:
                    self._finding("warn", "attribute-unset", c,
                                  f"reads ${{{a}}} ({where}) but no upstream processor sets it - the expression evaluates to empty")

    def _service_reads(self):
        """Attributes read by controller services, charged to the processors using them (e.g. reader 'Schema Name' ${schema.name})."""
        out = defaultdict(list)
        for sid, svc in self.flow.services.items():
            reads = [(a, f"service {svc['name']}: {where}") for a, where, is_default in self.attr_reads[sid] if not is_default]
            props = {f["name"]: f["resolved"] for f in self.props[sid]}
            if props.get("schema-access-strategy") == "schema-name" and not any(a == "schema.name" for a, _ in reads):
                reads.append(("schema.name", f"service {svc['name']}: Schema Name (default)"))
            for user in self.service_users.get(sid, []):
                out[user] += reads
        return out

    @staticmethod
    def _near(name, candidates):
        squash = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
        for c in candidates:
            if squash(c) == squash(name):
                return c
        import difflib
        close = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.85)
        return close[0] if close else None

    def _link_scripts(self, comp):
        for r in [r for r in self.res_by_comp[comp["id"]] if r["kind"] == "script"]:
            path = r["value"].strip("\"'")
            p = Path(path)
            entry = self.scripts.setdefault(path, {"path": path, "used_by": [], "exists": p.is_file(), "index": None})
            entry["used_by"].append(comp["id"])
            if not entry["exists"]:
                matches = self.code.by_basename.get(p.name.lower(), [])
                if matches:
                    entry["repo_match"] = matches[0]

    # ------------------------------------------------------------------------------------------ jdbc
    def _parse_jdbc(self):
        for sid, svc in self.flow.services.items():
            for f in self.props[sid]:
                m = re.match(r"jdbc:(\w+)(?::\w+)*://(?:[^@/]*@)?([^:/;?,]+)(?::(\d+))?(?:/([^;?]*))?", f["resolved"] or "", re.I)
                if m:
                    self.jdbc[sid] = {"vendor": m.group(1).lower(), "host": m.group(2).lower(), "port": m.group(3),
                                      "database": (m.group(4) or "").split("/")[0], "url": f["resolved"],
                                      "user": next((p["resolved"] for p in self.props[sid] if re.search(r"(?i)user", p["display"])), None)}

    def db_service_of(self, comp):
        for f in self.props[comp["id"]]:
            if f["service"] and f["service"] in self.jdbc:
                return f["service"]
        return None

    def tables_by_service(self):
        """{service id or None: {table: [component ids]}} for every table the flow touches."""
        if "tables" in self._memo:
            return self._memo["tables"]
        out = self._memo["tables"] = defaultdict(lambda: defaultdict(list))
        for r in self.resources:
            if r["kind"] == "db_table":
                comp = self.flow.components.get(r["component_id"])
                sid = self.db_service_of(comp) if comp else None
                out[sid][r["value"]].append(r["component_id"])
        return out

    def record_fields(self, comp):
        """Field names a PutDatabaseRecord-style processor will send (best effort) + where they came from."""
        reader = next((self.flow.services.get(f["service"]) for f in self.props[comp["id"]]
                       if f["service"] and re.search(r"(?i)reader", f["display"] + f["name"])), None)
        if not reader:
            return None, None
        rp = {f["name"]: f["resolved"] for f in self.props[reader["id"]]}
        strategy = rp.get("schema-access-strategy", "")
        text = rp.get("schema-text", "")
        if strategy == "schema-text-property" and text and "${" not in text:
            try:
                return [f["name"] for f in json.loads(text).get("fields", [])], f"schema text of {reader['name']}"
            except ValueError:
                return None, None
        if strategy == "csv-header-derived":
            for src in self._upstream_files(comp["id"]):
                try:
                    with open(src, newline="", encoding="utf-8-sig") as fh:
                        header = next(csv.reader(fh, delimiter=rp.get("Value Separator", ",")[:1] or ","))
                    return [h.strip() for h in header], f"CSV header of {src}"
                except (OSError, StopIteration, UnicodeDecodeError):
                    continue
        return None, None

    def _upstream_files(self, cid, depth=0, seen=None):
        seen = seen or set()
        if depth > 6 or cid in seen:
            return []
        seen.add(cid)
        out = []
        for _, src in self.in_edges[cid]:
            for r in self.res_by_comp[src]:
                if r["kind"] == "file_path" and Path(r["value"]).is_file():
                    out.append(r["value"])
            out.extend(self._upstream_files(src, depth + 1, seen))
        return out

    # ----------------------------------------------------------------------------------------- tags
    def group_tags(self, group_id, recursive=True):
        if "own_tags" not in self._memo:
            own = self._memo["own_tags"] = defaultdict(set)
            for comp in list(self.flow.components.values()) + list(self.flow.services.values()):
                if comp["type"]:
                    for tag, rx in TAG_RULES:
                        if rx.search(type_short(comp["type"])):
                            own[comp["group_id"]].add(tag)
                    if self.is_custom(comp):
                        own[comp["group_id"]].add("custom")
        own = self._memo["own_tags"]
        gids = {group_id} | (self.descendants(group_id) if recursive else set())
        return sorted(set().union(*(own[g] for g in gids)))

    def descendants(self, group_id):
        out, stack = set(), [group_id]
        while stack:
            for child in self.children[stack.pop()]:
                if child not in out:
                    out.add(child)
                    stack.append(child)
        return out

    def entry_points(self, group_id=None):
        """Where data enters: processors without incoming connections, input ports, remote output ports.
        With group_id, the group's own input ports count too (they are fed from the parent group)."""
        out = []
        for comp in self.flow.components.values():
            if group_id and comp["group_id"] != group_id:
                continue
            if group_id and comp["kind"] == "INPUT_PORT":
                out.append(comp)
                continue
            incoming = [s for _, s in self.in_edges[comp["id"]] if s != comp["id"]]
            if not incoming and comp["kind"] in ("PROCESSOR", "INPUT_PORT", "REMOTE_OUTPUT_PORT"):
                out.append(comp)
        return sorted(out, key=lambda c: (c["kind"] != "PROCESSOR", c["name"]))

    def key_facts(self, comp, limit=150):
        """One-line summary of what a component touches (tables, buckets, urls, paths, commands)."""
        bits = []
        order = ["db_table", "s3_bucket", "object_key", "url", "jdbc", "host", "port", "topic", "file_path", "script", "command", "email"]
        rs = self.res_by_comp[comp["id"]]
        for kind in order:
            vals = []
            for r in rs:
                if r["kind"] == kind and r["value"] not in vals and not (kind == "command" and any(x["kind"] == "script" for x in rs)):
                    vals.append(r["value"])
            if vals:
                bits.append(f"{kind.replace('db_', '').replace('s3_', '')}={'; '.join(vals)}")
        for f in self.props[comp["id"]]:
            if re.search(r"(?i)statement[ -]type|http method|^method$|completion strategy|conflict", f["display"] + " " + f["name"]) and not f["default"]:
                bits.append(f"{f['display']}={f['resolved']}")
            elif f["service"] and re.search(r"(?i)dbcp|connection pool|database", f["display"]) and f["resolved"]:
                bits.append(f"db={f['resolved']}")
        if comp["kind"] == "PROCESSOR" and comp["scheduling_strategy"] == "CRON_DRIVEN":
            bits.append(f"cron='{comp['scheduling_period']}'")
        elif comp["kind"] == "PROCESSOR" and not self.in_edges[comp["id"]] and comp["scheduling_period"] not in (None, "0 sec"):
            bits.append(f"every {comp['scheduling_period']}")
        return clip(", ".join(bits), limit)
