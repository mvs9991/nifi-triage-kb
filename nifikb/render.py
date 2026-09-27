"""Render the analysis into small, linked markdown files an LLM can read instead of the raw flow."""
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from . import sqlparse
from .analyze import type_short
from .code import spark_label
from .util import REDACTED, SECRET_NAME, URL_RE, clip, md_escape, redact_secrets, short, slugify

SEV_ORDER = {"error": 0, "high": 1, "warn": 2, "info": 3}
SUCCESS_FIRST = ("success", "matched", "original", "output stream", "response", "splits", "merged", "valid")


# ------------------------------------------------------------------------------------ graph tree
def tree_lines(roots, get, edges, doc_of=None, group_id=None, max_depth=40, upstream=False, expanded=None):
    """Indented tree of the data path from each root. `get(cid)` returns a component dict with name/type/kind/state/
    group_id/facts/auto_terminated; `edges(cid)` returns [(relationships list, other id)]. With group_id the tree
    stops where the path leaves that process group."""
    lines = []
    expanded = set() if expanded is None else expanded

    def label(c, brief=False):
        kind = c.get("kind")
        if kind == "FUNNEL":
            base = f"(funnel) `{short(c['id'])}`"
        elif kind in ("INPUT_PORT", "OUTPUT_PORT"):
            base = f"{'⇥ input' if kind == 'INPUT_PORT' else '⇤ output'} port **{c['name']}** `{short(c['id'])}`"
        elif kind and kind.startswith("REMOTE"):
            base = f"remote port **{c['name']}**"
        else:
            base = f"**{c['name']}** [{type_short(c.get('type'))}] `{short(c['id'])}`"
        state = c.get("state")
        if state and state not in ("RUNNING", "ENABLED") and kind == "PROCESSOR":
            base += f" ({state})"
        if not brief and c.get("facts"):
            base += f" — {c['facts']}"
        return base

    def visit(cid, depth, via):
        c = get(cid)
        pad = "  " * depth + "- "
        arrow = ("▶ " if not upstream else "◀ ") if via is None else (f"*{via}* → " if not upstream else f"← *{via}* ")
        if c is None:
            lines.append(pad + arrow + f"? unknown component `{short(cid)}`")
            return
        if group_id and c["group_id"] != group_id:
            where = doc_of(c["group_id"]) if doc_of else None
            gname = c.get("group_name") or short(c["group_id"])
            lines.append(pad + arrow + f"{label(c, True)} in PG **{gname}**" + (f" (see [{where}]({where}))" if where else ""))
            return
        if cid in expanded:
            lines.append(pad + arrow + label(c, True) + " ↑ shown above")
            return
        expanded.add(cid)
        lines.append(pad + arrow + label(c))
        outs = edges(cid)
        if depth >= max_depth and outs:
            lines.append("  " * (depth + 1) + "- … depth limit")
            return
        outs = sorted(outs, key=lambda e: (not any(r in SUCCESS_FIRST for r in e[0]), ",".join(e[0])))
        for rels, other in outs:
            visit(other, depth + 1, ",".join(rels) or "·")
        if not upstream and c.get("auto_terminated"):
            lines.append("  " * (depth + 1) + f"- ✖ auto-terminated: {', '.join(c['auto_terminated'])}")

    for r in roots:
        visit(r, 0, None)
    return lines


class Renderer:
    def __init__(self, an, out_dir, code, db_results, extra):
        self.an, self.flow, self.out, self.code, self.dbs, self.extra = an, an.flow, Path(out_dir), code, db_results, extra
        self.files = {}          # relative path -> content
        self.comp_docs = {}      # component id -> markdown section
        self.group_file = {}
        self.table_file = {}     # (db name, table) -> doc path
        used = set()
        for gid, g in sorted(self.flow.groups.items(), key=lambda kv: (kv[1]["depth"], kv[1]["path"])):
            base = "root" if gid == self.flow.root_id else slugify(g["path"].split(" / ", 1)[-1])
            name, n = base, 2
            while name in used:
                name, n = f"{base}-{n}", n + 1
            used.add(name)
            self.group_file[gid] = f"flows/{name}.md"
        self.custom_file = {t: f"custom-code/{type_short(t)}.md" for t in list(an.custom) + list(code.by_fqcn)}
        self.script_file = {}
        for p in an.scripts:
            self.script_file[p] = f"scripts/{slugify(Path(p).name, 80)}.md"

    # helpers
    def comp(self, cid):
        c = self.flow.components.get(cid) or self.flow.services.get(cid)
        if not c:
            return None
        g = self.flow.groups.get(c["group_id"]) or {}
        return dict(c, facts=self.an.key_facts(c), group_name=g.get("name"))

    def edges(self, cid):
        return [(c["relationships"], d) for c, d in self.an.out_edges[cid]]

    def in_edges(self, cid):
        return [(c["relationships"], s) for c, s in self.an.in_edges[cid]]

    def link(self, cid, frm="flows/x.md"):
        c = self.flow.components.get(cid) or self.flow.services.get(cid)
        if not c:
            return f"`{short(cid)}`"
        target = "services.md" if c["kind"] == "CONTROLLER_SERVICE" else self.group_file.get(c["group_id"], "INDEX.md")
        rel = _rel(frm, target)
        return f"[{md_escape(c['name'])}]({rel}#{_anchor(c)}) `{short(cid)}`"

    def findings_for(self, cid):
        if not hasattr(self, "_findings_idx"):
            self._findings_idx = defaultdict(list)
            for f in self.an.findings:
                self._findings_idx[f["component_id"]].append(f)
        return sorted(self._findings_idx.get(cid, []), key=lambda f: SEV_ORDER.get(f["severity"], 9))

    # ----------------------------------------------------------------------------------- per group
    def render_group(self, gid):
        an, flow = self.an, self.flow
        g = flow.groups[gid]
        me = self.group_file[gid]
        comps = [c for c in flow.components.values() if c["group_id"] == gid]
        procs = sorted((c for c in comps if c["kind"] == "PROCESSOR"), key=lambda c: c["name"].lower())
        states = Counter(c["state"] for c in procs)
        children = sorted((x for x in flow.groups.values() if x["parent_id"] == gid), key=lambda x: x["name"].lower())
        L = [f"# Flow: {g['name']}", ""]
        meta = [f"Path: {g['path']}", f"group `{short(gid)}`"]
        if g.get("parameter_context"):
            meta.append(f"parameter context: {g['parameter_context']}")
        if g.get("versioned"):
            vc = g.get("version_control") or {}
            meta.append(f"version-controlled: flow {vc.get('flow_name') or vc.get('flow') or '?'} v{vc.get('version') or '?'}"
                        + (f" (bucket {vc['bucket']})" if vc.get("bucket") else ""))
        L.append(" · ".join(meta))
        L.append(f"Processors: {len(procs)} ({', '.join(f'{v} {k.lower()}' for k, v in states.most_common())})"
                 f" · tags: {', '.join(an.group_tags(gid, recursive=False)) or '-'}")
        if g["parent_id"]:
            L.append(f"Parent: [{flow.groups[g['parent_id']]['name']}]({_rel(me, self.group_file[g['parent_id']])})")
        if children:
            L.append("Child groups: " + ", ".join(f"[{c['name']}]({_rel(me, self.group_file[c['id']])})" for c in children))
        if g.get("variables"):
            L.append("Variables: " + ", ".join(f"`{k}`=`{REDACTED if SECRET_NAME.search(k) else clip(v, 80)}`" for k, v in sorted(g["variables"].items())))
        notes = [lab["text"] for lab in flow.labels if lab["group_id"] == gid] + ([g["comments"]] if g.get("comments") else [])
        if notes:
            L += ["", "## Notes on the canvas", *[f"- {clip(n, 400)}" for n in notes]]
        roots = [c["id"] for c in an.entry_points(gid)]
        if roots or procs:
            L += ["", "## Data paths", "Read top-down: each `→` is a connection labelled with its relationship(s).", ""]
        expanded = set()
        doc_of = lambda x: _rel(me, self.group_file.get(x, "INDEX.md"))  # noqa: E731
        L += tree_lines(roots, self.comp, self.edges, doc_of=doc_of, group_id=gid, expanded=expanded)
        orphans = [c["id"] for c in procs if c["id"] not in expanded]
        if orphans:
            L += ["", "Only reachable through loops (no clear entry point):"]
            for o in orphans:
                if o not in expanded:
                    L += tree_lines([o], self.comp, self.edges, doc_of=doc_of, group_id=gid, expanded=expanded)
        if procs:
            L += ["", "## Processors"]
            for c in procs:
                L += ["", *self.processor_section(c, me)]
        ports = [c for c in comps if c["kind"] in ("INPUT_PORT", "OUTPUT_PORT")]
        if ports:
            L += ["", "## Ports"]
            for p in sorted(ports, key=lambda p: p["name"]):
                ins = ", ".join(self.link(s, me) for _, s in self.in_edges(p["id"])) or "-"
                outs = ", ".join(self.link(d, me) for _, d in self.edges(p["id"])) or "-"
                L.append(f"- {p['kind'].replace('_', ' ').lower()} **{p['name']}** `{short(p['id'])}`: from {ins} → to {outs}")
        svcs = [s for s in flow.services.values() if s["group_id"] == gid]
        if svcs:
            L += ["", "## Controller services defined here", "Details: [services.md](../services.md)"]
            for s in sorted(svcs, key=lambda s: s["name"]):
                L.append(f"- **{s['name']}** [{type_short(s['type'])}] `{short(s['id'])}` {s.get('state') or ''} — {self.service_summary(s)}")
        self.files[me] = "\n".join(L) + "\n"

    def processor_section(self, c, frm):
        an = self.an
        head = f"### {c['name']}"
        L = [head, f"<a id=\"{_anchor(c)}\"></a>`{c['id']}` · {c['type']}"
             + (f" ({(c['bundle'] or {}).get('artifact')} {(c['bundle'] or {}).get('version')})" if c.get("bundle") else "")]
        sched = [c.get("state") or "?"]
        if c.get("scheduling_strategy") and c["scheduling_strategy"] != "TIMER_DRIVEN" or c.get("scheduling_period") not in (None, "0 sec"):
            sched.append(f"{c.get('scheduling_strategy')} {c.get('scheduling_period')}")
        if c.get("concurrent_tasks") and int(c["concurrent_tasks"]) > 1:
            sched.append(f"{c['concurrent_tasks']} concurrent tasks")
        if c.get("execution_node") == "PRIMARY":
            sched.append("primary node only")
        L.append("- run: " + ", ".join(sched))
        ext = an.ext(c)
        if ext and ext.get("description"):
            L.append(f"- does: {clip(ext['description'], 220)}")
        if c.get("comments"):
            L.append(f"- comment: {clip(c['comments'], 300)}")
        facts = an.props[c["id"]]
        shown = [f for f in facts if not f["default"]]
        for f in shown:
            val = f["resolved"] if f["source"] in ("service",) else f["value"]
            line = f"  - {f['display']}: " + (f"`{clip(val, 300)}`" if val.strip() else repr(val))
            if f["source"] in ("parameter", "expression", "variable", "parameter+expression") and f["resolved"] != f["value"]:
                line += f" ⇒ `{clip(f['resolved'], 200)}`"
            if f["source"] == "service":
                line = f"  - {f['display']}: → {self.link(f['service'], frm) if f['service'] in self.flow.services else val}"
            tags = []
            if f["dynamic"]:
                tags.append("dynamic")
            hard = [r for r in an.res_by_comp[c["id"]] if r["property"] == f["display"] and r["hardcoded"] and r["kind"] not in ("sql",)]
            if hard:
                tags.append("hardcoded " + "/".join(sorted({r["kind"] for r in hard})))
            if tags:
                line += f" _({', '.join(tags)})_"
            L.append(line)
        if shown:
            L.insert(len(L) - len(shown), "- properties" + (f" (non-default; {len(facts) - len(shown)} default hidden)" if len(shown) < len(facts) else "") + ":")
        ins = [f"{self.link(s, frm)} ({','.join(r)})" for r, s in self.in_edges(c["id"])]
        outs = [f"{','.join(r)} → {self.link(d, frm)}" for r, d in self.edges(c["id"])]
        if ins:
            L.append("- from: " + "; ".join(ins))
        if outs:
            L.append("- to: " + "; ".join(outs))
        if c.get("auto_terminated"):
            L.append("- auto-terminated: " + ", ".join(c["auto_terminated"]))
        if an.attrs_read[c["id"]]:
            L.append("- reads attributes: " + ", ".join(sorted(an.attrs_read[c["id"]])))
        if an.attrs_written[c["id"]]:
            L.append("- writes attributes: " + ", ".join(sorted(an.attrs_written[c["id"]])))
        if c["type"] in self.custom_file and (c["type"] in an.custom or c["type"] in self.code.by_fqcn):
            L.append(f"- custom code: [{type_short(c['type'])}]({_rel(frm, self.custom_file[c['type']])})")
        for r in an.res_by_comp[c["id"]]:
            if r["kind"] == "script" and r["value"].strip("\"'") in self.script_file:
                spath = r["value"].strip(chr(34) + chr(39))
                sinfo = (an.scripts.get(spath) or {}).get("index") or {}
                spark = "; ".join(spark_label(x) for x in sinfo.get("spark") or [])
                L.append(f"- script: [{Path(r['value']).name}]({_rel(frm, self.script_file[spath])})"
                         + (f" — submits Spark job: {spark}" if spark else ""))
        for f in self.findings_for(c["id"]):
            L.append(f"- ⚠ {f['severity']}: {f['message']}")
        self.comp_docs[c["id"]] = "\n".join(L)
        return L

    def service_summary(self, s):
        bits = []
        if s["id"] in self.an.jdbc:
            j = self.an.jdbc[s["id"]]
            bits.append(f"{j['url']}" + (f" user={j['user']}" if j.get("user") else ""))
        for f in self.an.props[s["id"]]:
            if not f["default"] and f["source"] != "sensitive" and ("schema" in f["name"].lower() and "strategy" in f["name"].lower()):
                bits.append(f"{f['display']}={f['resolved']}")
        users = self.an.service_users.get(s["id"], [])
        bits.append(f"used by {len(users)}")
        return clip(", ".join(bits), 240)

    # ---------------------------------------------------------------------------------- services
    def render_services(self):
        L = ["# Controller services", ""]
        for s in sorted(self.flow.services.values(), key=lambda s: (s["type"], s["name"])):
            g = self.flow.groups.get(s["group_id"]) or {"path": "(controller level)"}
            L += [f"## {s['name']}", f"<a id=\"{_anchor(s)}\"></a>`{s['id']}` · {s['type']} · {s.get('state')} · scope: {g['path']}"]
            ext = self.an.ext(s)
            if ext and ext.get("description"):
                L.append(f"- does: {clip(ext['description'], 200)}")
            for f in self.an.props[s["id"]]:
                if not f["default"]:
                    shown = f["resolved"] if f["source"] in ("service", "sensitive") else f["value"]
                    extra = f" ⇒ `{clip(f['resolved'], 150)}`" if f["source"] in ("parameter", "expression", "variable") and f["resolved"] != f["value"] else ""
                    L.append(f"  - {f['display']}: `{clip(shown, 400)}`{extra}")
            users = self.an.service_users.get(s["id"], [])
            if users:
                L.append("- used by: " + ", ".join(self.link(u, "services.md") for u in users))
            for f in self.findings_for(s["id"]):
                L.append(f"- ⚠ {f['severity']}: {f['message']}")
            self.comp_docs[s["id"]] = "\n".join(L[L.index(f"## {s['name']}"):])
            L.append("")
        self.files["services.md"] = "\n".join(L) + "\n"

    # ---------------------------------------------------------------------------- external systems
    def render_external(self):
        an = self.an
        kinds = [("jdbc", "Database connections"), ("db_table", "Database tables"), ("sql", "SQL statements"),
                 ("s3_bucket", "S3 buckets"), ("object_key", "S3 object keys"), ("url", "URLs / APIs"), ("host", "Hosts"),
                 ("port", "Ports"), ("topic", "Topics / queues"), ("file_path", "File system paths"), ("script", "Scripts"),
                 ("command", "Commands"), ("email", "Email")]
        L = ["# External systems touched by the flow", "", "`H` = hardcoded literal in the flow (not a parameter/variable/attribute).", ""]
        for kind, title in kinds:
            rows = defaultdict(list)
            for r in an.resources:
                if r["kind"] == kind:
                    rows[r["value"]].append(r)
            if not rows:
                continue
            L += [f"## {title}"]
            for value, rs in sorted(rows.items()):
                users = []
                for r in rs:
                    ref = self.link(r["component_id"], "external-systems.md")
                    if ref not in users:
                        users.append(ref)
                flag = " `H`" if any(r["hardcoded"] for r in rs) else ""
                shown = clip(value, 220) if kind != "sql" else clip(value, 300)
                tables = ""
                if kind == "sql" and rs[0].get("detail"):
                    tables = f" (tables: {', '.join(json.loads(rs[0]['detail']))})"
                L.append(f"- `{shown}`{flag}{tables} — {', '.join(users[:8])}{' …' if len(users) > 8 else ''}")
            L.append("")
        code_tables = defaultdict(list)
        for path, info in self.code.files.items():
            for t in info.get("tables") or []:
                code_tables[t].append(_code_ref(path, None, self.extra))
        if code_tables:
            L.append("## Tables referenced in code / scripts")
            L += [f"- `{t}` — {', '.join(dict.fromkeys(refs))}" for t, refs in sorted(code_tables.items())]
        self.files["external-systems.md"] = "\n".join(L) + "\n"

    # ------------------------------------------------------------------------------------- hardcoded
    def render_hardcoded(self, max_per_kind=150):
        an = self.an
        L = ["# Hardcoded values", "",
             "Literal values that probably belong in a Parameter Context / config. Secrets are always redacted.", "",
             "## In the NiFi flow", ""]
        rows = sorted((r for r in an.resources if r["hardcoded"] and r["kind"] != "command"), key=lambda r: (r["kind"], r["value"]))
        if not rows:
            L.append("None found.")
        by_kind = defaultdict(list)
        for r in rows:
            by_kind[r["kind"]].append(r)
        for kind, rs in by_kind.items():
            L.append(f"### {kind}")
            for r in rs[:max_per_kind]:
                partial = " (partly: mixed with EL/parameter)" if r["source"] not in ("literal", "variable") else " (via variable)" if r["source"] == "variable" else ""
                L.append(f"- `{clip(r['value'], 200)}`{partial} — {self.link(r['component_id'], 'hardcoded.md')} · {r['property']}")
            if len(rs) > max_per_kind:
                L.append(f"- … {len(rs) - max_per_kind} more (`python -m nifikb search {kind}`)")
        secrets = [f for f in an.findings if f["kind"] == "plaintext-secret"]
        if secrets:
            L += ["", "### plain-text secrets in flow properties"] + [f"- {self.link(f['component_id'], 'hardcoded.md')}: {f['message']}" for f in secrets]
        L += ["", "## In code and scripts", ""]
        by_kind = defaultdict(list)
        for path, h in self.code.hardcoded():
            if h["kind"] != "sql":
                by_kind[h["kind"]].append((path, h))
        if not by_kind:
            L.append("None found (or no code indexed yet).")
        for kind in sorted(by_kind, key=lambda k: (k != "secret", k)):
            L.append(f"### {kind}")
            for path, h in by_kind[kind][:max_per_kind]:
                L.append(f"- `{clip(h['value'], 160)}` — {_code_ref(path, h['line'], self.extra)}  `{h['code']}`")
            if len(by_kind[kind]) > max_per_kind:
                L.append(f"- … {len(by_kind[kind]) - max_per_kind} more")
        self.files["hardcoded.md"] = "\n".join(L) + "\n"

    # ---------------------------------------------------------------------------------------- issues
    def render_issues(self, per_kind=150):
        L = ["# Issues and risks", "", "Static checks on the flow, code and database. Severity: error > high > warn > info.", ""]
        items = sorted(self.an.findings, key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["kind"]))
        if not items:
            L.append("No issues found.")
        counts = Counter((f["severity"], f["kind"]) for f in items)
        if counts:
            L += ["| Severity | Kind | Count |", "|---|---|---|"]
            L += [f"| {s} | {k} | {n} |" for (s, k), n in sorted(counts.items(), key=lambda kv: (SEV_ORDER.get(kv[0][0], 9), -kv[1]))]
            L.append("")
            L.append(f"Up to {per_kind} entries per kind are listed; filter all of them with "
                     "`python -m nifikb issues --kind <kind> [--contains <text>]` (MCP tool `issues`).")
        current, shown = None, 0
        for f in items:
            key = (f["severity"], f["kind"])
            if key != current:
                if current and counts[current] > per_kind:
                    L.append(f"- … {counts[current] - per_kind} more `{current[1]}`")
                current, shown = key, 0
                L += ["", f"## {f['severity']}: {f['kind']}"]
            shown += 1
            if shown > per_kind:
                continue
            where = self.link(f["component_id"], "issues.md") if f["component_id"] else (f.get("location") or "")
            L.append(f"- {where}: {f['message']}")
        if current and counts[current] > per_kind:
            L.append(f"- … {counts[current] - per_kind} more `{current[1]}`")
        self.files["issues.md"] = "\n".join(L) + "\n"

    # ------------------------------------------------------------------------------------ custom code
    def render_custom(self):
        an, code = self.an, self.code
        idx = ["# Custom components", "", "| Type | Used by | Source | NAR |", "|---|---|---|---|"]
        types = sorted(set(an.custom) | set(code.by_fqcn))
        for t in types:
            entry = an.custom.get(t, {"used_by": [], "code": code.by_fqcn.get(t, []), "nar": None, "bundle": {}})
            f = self.custom_file[t]
            src = ", ".join(_code_ref(e["path"], e["line"], self.extra) for e in entry["code"]) or "**missing**"
            idx.append(f"| [{type_short(t)}]({f.split('/', 1)[1]}) | {len(entry['used_by'])} | {src} | {entry.get('nar') or (entry.get('bundle') or {}).get('artifact') or '-'} |")
            self.files[f] = self.custom_doc(t, entry, f)
        if not types:
            idx.append("| (none) | | | |")
        self.files["custom-code/INDEX.md"] = "\n".join(idx) + "\n"

    def custom_doc(self, t, entry, me):
        an = self.an
        L = [f"# {type_short(t)}", f"`{t}`", ""]
        ext = self.an.catalog.get(t)
        comp = entry["code"][0]["component"] if entry["code"] else None
        desc = (comp or {}).get("description") or (ext or {}).get("description")
        if desc:
            L.append(f"**Does:** {clip(desc, 600)}")
        if comp:
            L.append(f"Source: {', '.join(_code_ref(e['path'], e['line'], self.extra) for e in entry['code'])} · extends "
                     + (" → ".join(x.rsplit(".", 1)[-1] for x in comp.get("super_chain") or []) or comp.get("extends") or "-")
                     + (f" · input: {comp['input_requirement']}" if comp.get("input_requirement") else ""))
            if comp.get("tags"):
                L.append("Tags: " + ", ".join(comp["tags"]))
            if comp.get("flags"):
                L.append("Annotations: " + ", ".join(f"@{f}" for f in comp["flags"]))
            if comp.get("io"):
                L.append("Talks to / uses: " + ", ".join(comp["io"]))
            L += self._build_lines(comp, entry)
        elif ext:
            L.append(f"Source code not provided; details from NAR `{ext.get('nar')}` manifest.")
        else:
            L.append("**Source code and NAR not found.** Add the repo to `[code] repos` / the NAR to `[nifi] extra_nar_dirs` and rebuild.")
        if ext and ext.get("deployed"):
            L += self._deployed_lines(ext["deployed"], comp)
        props = (comp or {}).get("properties") or [
            {"name": k, "displayName": v["displayName"], "description": v["description"], "default": v["default"],
             "required": v["required"], "sensitive": v["sensitive"], "service": v.get("service_api")}
            for k, v in ((ext or {}).get("properties") or {}).items()]
        if props:
            L += ["", "## Properties", "| Name | Display | Default | Req | Notes |", "|---|---|---|---|---|"]
            for p in props:
                impl = self.code.implementers(p["service"]) if p.get("service") else []
                notes = " ".join(x for x in ["sensitive" if p.get("sensitive") else "", "EL" if p.get("el") else "",
                                             f"service {p['service']}" if p.get("service") else "",
                                             f"(implemented by {', '.join(i.rsplit('.', 1)[-1] for i in impl[:3])})" if impl else "",
                                             f"one of {', '.join(p['allowable'][:8])}" if p.get("allowable") else "",
                                             f"(from {p['from']})" if p.get("from") else "", clip(p.get("description"), 120)] if x)
                L.append(f"| {md_escape(p.get('name'))} | {md_escape(p.get('displayName') or p.get('name'))} | {md_escape(p.get('default'))} | {'Y' if p.get('required') else ''} | {md_escape(notes)} |")
        for d in (comp or {}).get("dynamic_properties") or []:
            L.append(f"- dynamic property {d.get('name') or ''}: {clip(d.get('description'), 160)}")
        rels = (comp or {}).get("relationships") or (ext or {}).get("relationships") or []
        if rels:
            L += ["", "## Relationships"] + [f"- `{r['name']}`: {clip(r.get('description'), 160)}" + (f" (from {r['from']})" if r.get("from") else "")
                                             for r in rels]
        if comp:
            L += ["", "## Attributes"]
            reads, writes = comp.get("reads_at") or {}, comp.get("writes_at") or {}
            if comp.get("reads_attributes"):
                L.append("- reads: " + ", ".join(f"`{a}`" + (f" ({reads[a]})" if a in reads else "") for a in comp["reads_attributes"]))
            if comp.get("writes_attributes"):
                L.append("- writes: " + ", ".join(f"`{a}`" + (f" ({writes[a]})" if a in writes else " (documented)") for a in comp["writes_attributes"]))
            if comp.get("removes_attributes"):
                L.append("- removes: " + ", ".join(f"`{a}`" for a in comp["removes_attributes"]))
            if comp.get("dynamic_writes"):
                L.append("- also writes attributes whose names are computed at runtime (e.g. from database columns)")
            if not (comp.get("reads_attributes") or comp.get("writes_attributes")):
                L.append("- none found in the code")
        for e in entry["code"]:
            info = self.code.files.get(e["path"]) or {}
            if info.get("hardcoded"):
                L += ["", f"## Hardcoded in {Path(e['path']).name}"]
                L += [f"- L{h['line']} {h['kind']}: `{clip(h['value'], 160)}`" + (f" tables={','.join(h['tables'])}" if h.get("tables") else "") for h in info["hardcoded"]]
            if info.get("messages"):
                L += ["", f"## Log / error messages in {Path(e['path']).name} (search a ticket's error text against these)"]
                L += [f"- L{m['line']} {m['level']}: {clip(m['text'], 200)}" for m in info["messages"][:60]]
            if info.get("functions"):
                L.append(f"\nMethods: {', '.join(info['functions'][:40])}")
        if entry["used_by"]:
            L += ["", "## Used in the flow"]
            for cid in entry["used_by"]:
                c = self.flow.components.get(cid) or self.flow.services.get(cid)
                g = self.flow.groups.get(c["group_id"], {})
                configured = ", ".join(f"{f['display']}=`{clip(f['resolved'], 80)}`" for f in an.props[cid] if not f["default"])
                L.append(f"- {self.link(cid, me)} in {g.get('path', '?')} ({c.get('state')}): {configured or 'no properties set'}")
        return "\n".join(L) + "\n"

    def _build_lines(self, comp, entry):
        """Maven module -> NAR module -> deployed NAR -> bundle version the flow runs."""
        L = []
        mod = comp.get("module")
        if mod:
            L.append(f"Maven module: `{mod.get('groupId')}:{mod.get('artifactId')}:{mod.get('version')}` "
                     f"({_code_ref(str(Path(mod['dir']) / 'pom.xml'), None, self.extra)})")
        nars = comp.get("nar_modules") or []
        if nars:
            L.append("Packaged by NAR module: " + ", ".join(f"`{n.get('artifactId')}:{n.get('version')}`" for n in nars))
        bundle = entry.get("bundle") or {}
        if bundle:
            versions = ", ".join(v for v in entry.get("bundle_versions") or [bundle.get("version")] if v)
            deployed = [n for n in self.an.catalog.nars if n.get("artifact") == bundle.get("artifact")]
            dep = ", ".join(f"{n.get('version')} ({Path(n['file']).name})" for n in deployed) if deployed else "**none in lib / extra_nar_dirs**"
            L.append(f"Flow runs bundle `{bundle.get('group')}:{bundle.get('artifact')}:{versions}` · deployed NAR: {dep}")
            src_version = next((n.get("version") for n in nars if n.get("artifactId") == bundle.get("artifact")), None)
            if src_version and bundle.get("version") and src_version != bundle.get("version"):
                L.append(f"⚠ Source version {src_version} ≠ running version {bundle['version']}: the repo may hold changes that are not deployed.")
        if not comp.get("registered"):
            L.append("Not listed in a META-INF/services file.")
        return L

    def _deployed_lines(self, deployed, comp):
        """Facts read from the compiled classes inside the deployed NAR (ground truth of what runs)."""
        strings = self.an.catalog.jar_strings(deployed)
        if not strings:
            return []
        L = ["", f"## Deployed NAR (compiled classes in `{deployed['jar']}`)"]
        drift = (self.an.custom.get(comp["fqcn"]) or {}).get("drift") if comp else None
        if drift:
            L.append("⚠ In the repo source but **not in the deployed build**: " + ", ".join(drift[:20]))
        elif comp:
            L.append("Source matches the deployed build (all property, relationship and attribute names found).")
        sql = sorted({s for s in strings if sqlparse.looks_like_sql(s)})
        tables = sorted({t for s in sql for t in sqlparse.tables(s) if "{" not in t})
        if tables:
            L.append("Tables in its SQL: " + ", ".join(f"`{t}`" for t in tables[:40]))
        for s in sql[:15]:
            L.append(f"- SQL: `{clip(redact_secrets(s), 200)}`")
        urls = sorted({m.group(0) for s in strings for m in URL_RE.finditer(s)})
        if urls:
            L.append("URLs: " + ", ".join(f"`{u}`" for u in urls[:20]))
        return L

    # ---------------------------------------------------------------------------------------- scripts
    def render_scripts(self):
        idx = ["# Scripts called by the flow", ""]
        for path, entry in sorted(self.an.scripts.items()):
            f = self.script_file[path]
            info = entry.get("index")
            if entry["exists"]:
                status = "indexed"
            elif entry.get("repo_match"):
                status = f"not at this path here; indexed from repo match `{_code_ref(entry['repo_match'], None, self.extra).strip('`')}`"
            else:
                status = "file not found on this machine or in repos"
            idx.append(f"- [{Path(path).name}]({f.split('/', 1)[1]}) — {status} — used by {', '.join(self.link(u, 'scripts/INDEX.md') for u in entry['used_by'])}")
            L = [f"# Script {Path(path).name}", f"Path: `{path}` ({status})", ""]
            L.append("Called by: " + ", ".join(self.link(u, f) for u in entry["used_by"]))
            for u in entry["used_by"]:
                c = self.flow.components[u]
                cmd = [x for x in self.an.props[u] if "command" in x["kinds"]]
                if cmd:
                    L.append(f"- {c['name']}: " + " ".join(f"`{clip(x['resolved'], 200)}`" for x in cmd))
            if info:
                L += ["", f"Language: {info['lang']}, {info['lines']} lines"]
                if info.get("imports"):
                    L.append("Imports: " + ", ".join(info["imports"]))
                if info.get("functions"):
                    L.append("Functions: " + ", ".join(info["functions"]))
                if info.get("tables"):
                    L.append("Tables: " + ", ".join(info["tables"]))
                if info.get("spark"):
                    L += ["", "## Spark jobs submitted (Spark itself is not analysed)"]
                    L += [f"- L{x['line']}: {spark_label(x)}" + (f" · name `{x['name']}`" if x.get("name") else "")
                          + (f" · args `{' '.join(x['args'])}`" if x.get("args") else "") for x in info["spark"]]
                if info.get("hardcoded"):
                    L += ["", "## Hardcoded"] + [f"- L{h['line']} {h['kind']}: `{clip(h['value'], 160)}` — `{h['code']}`" for h in info["hardcoded"]]
                preview = self.extra.get("script_previews", {}).get(path)
                if preview:
                    L += ["", "## Source (secrets redacted)", "```" + {"python": "python", "shell": "bash"}.get(info["lang"], ""), preview, "```"]
            self.files[f] = "\n".join(L) + "\n"
        if self.an.scripts:
            self.files["scripts/INDEX.md"] = "\n".join(idx) + "\n"

    # ------------------------------------------------------------------------------------------- DB
    def render_db(self):
        an = self.an
        idx = ["# Databases", ""]
        for sid, j in sorted(an.jdbc.items(), key=lambda kv: self.flow.services[kv[0]]["name"]):
            matched = next((d for d in self.dbs if sid in d.get("services", [])), None)
            tables = sorted(an.tables_by_service().get(sid, {}).keys())
            idx.append(f"- DBCP {self.link(sid, 'db/INDEX.md')} → `{j['url']}` · tables used: {', '.join(tables) or '-'} · "
                       + (f"documented in [{matched['name']}]({slugify(matched['name'])}.md)" if matched else "**no read-only connection configured** (add a [[databases]] entry)"))
        for d in self.dbs:
            f = f"db/{slugify(d['name'])}.md"
            if d.get("error") and not d.get("tables"):
                idx.append(f"- {d['name']}: ⚠ {d['error']}")
                continue
            idx.append(f"- [{d['name']}]({f.split('/', 1)[1]}): {d.get('dialect')} · {len(d.get('tables', []))} tables documented of {d.get('table_count')}"
                       + (f" · ⚠ {d['error']} (showing cached schema)" if d.get("error") else ""))
            self.files[f] = self.db_doc(d, f)
        if not an.jdbc and not self.dbs:
            idx.append("No database connections in the flow and none configured.")
        self.files["db/INDEX.md"] = "\n".join(idx) + "\n"

    SPLIT_TABLES = 60  # above this many tables a database doc becomes an index + one file per table

    def db_doc(self, d, me):
        an = self.an
        users = defaultdict(list)
        for sid in d.get("services", []):
            for t, cids in an.tables_by_service().get(sid, {}).items():
                users[t.split(".")[-1].lower()] += cids
        code_users = defaultdict(list)
        for path, info in self.code.files.items():
            for t in info.get("tables") or []:
                code_users[t.split(".")[-1].lower()].append(path)
        L = [f"# Database {d['name']}", f"{d.get('dialect')} · schemas {', '.join(d.get('schemas', []))} · fetched {d.get('fetched', '')}", ""]
        if d.get("missing"):
            L.append("⚠ Tables referenced by the flow but **not found** in this database: " + ", ".join(d["missing"]))
        for chk in [c for c in an.field_checks if c.get("db") == d["name"]]:
            L.append(f"- field check {self.link(chk['component_id'], me)} → {chk['table']}: {chk['message']}")
        tables = d.get("tables", [])
        split = len(tables) > self.SPLIT_TABLES
        if split:
            folder, used = me[:-3], set()
            L += ["", f"{len(tables)} tables — one file per table under `{folder}/` (or `python -m nifikb show <table>`).", "",
                  "| Table | Rows | Cols | Used by flow | Doc |", "|---|---|---|---|---|"]
        for t in tables:
            name = t["table"]
            if split:
                slug = slugify(name)
                while slug in used:
                    slug += "-x"
                used.add(slug)
                path = f"{folder}/{slug}.md"
                self.table_file[(d["name"], name)] = path
                title = f"# {d['name']}: {t['schema']}.{name}" if d.get("dialect") != "sqlite" else f"# {d['name']}: {name}"
                self.files[path] = "\n".join([title, f"[← database {d['name']}](../{me.rsplit('/', 1)[-1]})"]
                                             + self.table_section(t, users, code_users, path)[1:]) + "\n"
                n_users = len(set(users.get(name.lower(), [])))
                L.append(f"| {md_escape(name)} | {t['rows'] if t.get('rows') is not None else ''} | {len(t.get('columns', []))} | "
                         f"{n_users or ''} | [{slug}.md]({folder.rsplit('/', 1)[-1]}/{slug}.md) |")
            else:
                self.table_file[(d["name"], name)] = me
                L += [""] + self.table_section(t, users, code_users, me)
        others = sorted(set(d.get("all_table_names", [])) - {t["table"] for t in tables})
        if others:
            L += ["", f"Other tables in schema (not referenced; add to include_tables to document): {clip(', '.join(others), 1500)}"]
        return "\n".join(L) + "\n"

    def table_section(self, t, users, code_users, me):
        name = t["table"]
        L = [f"## {t['schema']}.{name}" if t.get("schema") not in (None, "main") else f"## {name}"]
        meta = [t.get("type") or "", f"~{t['rows']} rows" if t.get("rows") is not None else ""]
        if t.get("comment"):
            meta.append(clip(t["comment"], 150))
        L.append(" · ".join(m for m in meta if m))
        u = users.get(name.lower(), [])
        if u:
            L.append("Used by flow: " + ", ".join(self.link(x, me) for x in dict.fromkeys(u)))
        cu = code_users.get(name.lower(), [])
        if cu:
            L.append("Used in code: " + ", ".join(_code_ref(p, None, self.extra) for p in dict.fromkeys(cu)))
        L += ["| Column | Type | Null | Key | Default | Extra |", "|---|---|---|---|---|---|"]
        for c in t.get("columns", []):
            L.append(f"| {c['name']} | {md_escape(str(c['type']))} | {'Y' if c['nullable'] else 'N'} | {c.get('key') or ''} | "
                     f"{md_escape(clip(str(c['default']), 40)) if c.get('default') is not None else ''} | {md_escape(c.get('extra') or c.get('comment') or '')} |")
        if t.get("foreign_keys"):
            L.append("FKs: " + ", ".join(f"{fk['column']}→{fk['ref']}" for fk in t["foreign_keys"]))
        if t.get("indexes"):
            L.append("Indexes: " + ", ".join(f"{i['name']}({','.join(i['columns'])}){' unique' if i['unique'] else ''}" for i in t["indexes"]))
        for col, vals in (t.get("profile") or {}).items():
            L.append(f"- values of `{col}`: " + ", ".join(f"{v}×{n}" for v, n in vals))
        if t.get("sample"):
            L.append("Sample (masked): `" + clip(json.dumps(t["sample"][:3], default=str), 600) + "`")
        return L

    # ------------------------------------------------------------------------------------ INDEX etc.
    def render_index(self):
        an, flow = self.an, self.flow
        procs = [c for c in flow.components.values() if c["kind"] == "PROCESSOR"]
        states = Counter(c["state"] for c in procs)
        sev = Counter(f["severity"] for f in an.findings)
        L = ["# NiFi knowledge base", "",
             f"Built {time.strftime('%Y-%m-%d %H:%M')} from `{flow.source}` ({flow.format}, NiFi {flow.nifi_version() or '?'}). "
             "Do not read the raw flow file; everything is here.", "",
             "## Summary",
             f"- {len(flow.groups)} process groups · {len(procs)} processors ({', '.join(f'{v} {k.lower()}' for k, v in states.most_common())}) · "
             f"{len(flow.connections)} connections · {len(flow.services)} controller services · {len(flow.param_contexts)} parameter contexts",
             f"- custom components: {len(an.custom)} used in flow, {len(self.code.by_fqcn)} found in code · scripts called: {len(an.scripts)}"
             f" · code files indexed: {len(self.code.files)}",
             f"- issues: {', '.join(f'{v} {k}' for k, v in sorted(sev.items(), key=lambda kv: SEV_ORDER.get(kv[0], 9))) or 'none'} → [issues.md](issues.md)",
             *([f"- metadata: {self.extra['metadata_summary']} → [metadata.md](metadata.md)"] if self.extra.get("metadata_summary") else []),
             "", "## Flows (process groups)", "| Flow | Procs | Running | Tags | Starts with → ends in | Doc |", "|---|---|---|---|---|---|"]
        for gid, g in sorted(flow.groups.items(), key=lambda kv: kv[1]["path"]):
            gp = [c for c in procs if c["group_id"] == gid]
            if not gp and not any(c["group_id"] == gid for c in flow.components.values()) and gid != flow.root_id:
                continue
            running = sum(1 for c in gp if c["state"] == "RUNNING")
            starts = [f"{type_short(c['type']) or c['kind'].lower()}" for c in an.entry_points(gid)][:4]
            ends = []
            for c in gp:
                if not self.edges(c["id"]) or type_short(c["type"]).startswith(("Put", "Publish", "Send", "Post")):
                    facts = [r["value"] for r in an.res_by_comp[c["id"]] if r["kind"] in ("db_table", "s3_bucket", "topic", "url")]
                    item = type_short(c["type"]) + (f"({facts[0]})" if facts else "")
                    if item not in ends:
                        ends.append(item)
            indent = "&nbsp;&nbsp;" * g["depth"]
            L.append(f"| {indent}{md_escape(g['name'])} | {len(gp)} | {running} | {', '.join(an.group_tags(gid, False))} | "
                     f"{md_escape(', '.join(dict.fromkeys(starts)) or '-')} → {md_escape(', '.join(ends[:4]) or '-')} | [{self.group_file[gid]}]({self.group_file[gid]}) |")
        links = Counter()
        for c in flow.connections:
            s, d = flow.components.get(c["source_id"]), flow.components.get(c["dest_id"])
            if s and d and s["group_id"] != d["group_id"]:
                links[(flow.groups[s["group_id"]]["name"], s["name"], flow.groups[d["group_id"]]["name"], d["name"])] += 1
        if links:
            L += ["", "## Links between groups"] + [f"- {a} ({ap}) → {b} ({bp})" for (a, ap, b, bp) in sorted(links)]
        tables = an.tables_by_service()
        ext = [("Databases", [f"{flow.services[s]['name']} `{an.jdbc[s]['url']}` → tables: {', '.join(sorted(tables.get(s, {})) ) or '-'}" for s in an.jdbc])]
        for kind, title in (("s3_bucket", "S3 buckets"), ("url", "URLs / APIs"), ("host", "Hosts"), ("topic", "Topics"), ("file_path", "File paths")):
            vals = sorted({r["value"] for r in an.resources if r["kind"] == kind})
            if vals:
                ext.append((title, [clip(", ".join(f"`{v}`" for v in vals), 600)]))
        L += ["", "## External systems (details: [external-systems.md](external-systems.md), hardcoded: [hardcoded.md](hardcoded.md))"]
        for title, vals in ext:
            if vals:
                L.append(f"- **{title}**: " + "; ".join(vals))
        if flow.param_contexts:
            L += ["", "## Parameter contexts"]
            for name, ctx in sorted(flow.param_contexts.items()):
                ps = ", ".join(f"{k}{'(sensitive)' if v['sensitive'] else '=' + (REDACTED if SECRET_NAME.search(k) else repr(clip(v['value'] or '', 60)))}"
                               for k, v in sorted(ctx["params"].items()))
                L.append(f"- **{name}**{' inherits ' + ', '.join(ctx['inherits']) if ctx['inherits'] else ''}: {clip(ps, 900)}")
        L += ["", "## Files in this knowledge base",
              "- `flows/*.md` — one per process group: data-path tree, processors with non-default settings, services",
              "- `services.md` · `external-systems.md` · `hardcoded.md` · `issues.md` · `CHANGELOG.md` · `nifi-instance.md`",
              "- `custom-code/` — custom processors (source + NAR docs) · `scripts/` — scripts the flow executes · `db/` — table schemas"]
        if self.extra.get("metadata"):
            L.append("- `metadata.md` — config tables that drive the flow (definitions, structures, feed / API / server config) and their drift")
        L.append(f"- Team knowledge (not generated, kept across builds): `{Path(self.extra.get('knowledge_dir') or 'knowledge').name}/context.md` "
                 f"and {self.extra.get('learnings', 0)} active learning(s) in `learnings/` — `python -m nifikb learn list` / `learn add`")
        L.append("- CLI (cheap lookups, run from the nifi-kb folder): `python -m nifikb search <words>` · `show <name|id>` · "
                 "`trace <name|id> [--up]` · `diagnose [--file <name>] <headers…>` · `sql \"SELECT …\"` · `build`")
        self.files["INDEX.md"] = "\n".join(L) + "\n"

    def render_instance(self, props, nars, catalog):
        keys = ["nifi.web.https.host", "nifi.web.https.port", "nifi.web.http.port", "nifi.cluster.is.node", "nifi.zookeeper.connect.string",
                "nifi.flow.configuration.file", "nifi.flow.configuration.json.file", "nifi.flow.configuration.archive.dir",
                "nifi.content.repository.directory.default", "nifi.flowfile.repository.directory", "nifi.provenance.repository.directory.default",
                "nifi.provenance.repository.max.storage.time", "nifi.nar.library.autoload.directory", "nifi.remote.input.socket.port",
                "nifi.security.user.login.identity.provider", "nifi.variable.registry.properties"]
        L = ["# NiFi instance", ""]
        for k in keys:
            if k in props:
                L.append(f"- `{k}` = `{props[k]}`")
        custom = [n for n in nars if n.get("group") and not n["group"].startswith("org.apache.nifi")]
        L += ["", f"NARs loaded: {len(nars)} ({len(catalog.types)} component types). Custom NARs: "
              + (", ".join(f"{n['artifact']} {n.get('version') or ''} ({n.get('group')})" for n in custom) or "none found")]
        L += ["", "## Types used by this flow"]
        used = Counter(c["type"] for c in list(self.flow.components.values()) + list(self.flow.services.values()) if c.get("type"))
        for t, n in sorted(used.items()):
            e = catalog.get(t)
            L.append(f"- {type_short(t)} ×{n}" + (f" — {clip(e['description'], 140)}" if e and e.get("description") else ""))
        self.files["nifi-instance.md"] = "\n".join(L) + "\n"

    def render_changelog(self, rows):
        L = ["# Change log", "", "Differences detected between knowledge-base builds (newest first): flow components and, prefixed "
             "`config`, rows of the metadata config tables (compared at each metadata refresh; secret columns are not compared).", ""]
        last = None
        for r in rows:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"]))
            if ts != last:
                L += ["", f"## {ts}"]
                last = ts
            L.append(f"- {r['change']}")
        if not rows:
            L.append("No changes recorded yet (first build).")
        self.files["CHANGELOG.md"] = "\n".join(L) + "\n"

    def render_all(self, instance_props, changes):
        for gid in self.flow.groups:
            self.render_group(gid)
        self.render_services()
        self.render_external()
        self.render_hardcoded()
        self.render_issues()
        self.render_custom()
        self.render_scripts()
        self.render_db()
        self.render_instance(instance_props, self.an.catalog.nars, self.an.catalog)
        self.render_changelog(changes)
        self.render_index()
        return self.files


def _anchor(c):
    return f"c-{short(c['id'])}"


def _rel(frm, to):
    depth = frm.count("/")
    return ("../" * depth) + to


def _code_ref(path, line, extra):
    base = extra.get("code_roots", [])
    shown = path
    for root in base:
        try:
            shown = str(Path(path).relative_to(root))
            break
        except ValueError:
            continue
    return f"`{shown}{':' + str(line) if line else ''}`"


def _reachable(roots, edges):
    seen, stack = set(), list(roots)
    while stack:
        x = stack.pop()
        if x in seen:
            continue
        seen.add(x)
        stack.extend(d for _, d in edges(x))
    return seen
