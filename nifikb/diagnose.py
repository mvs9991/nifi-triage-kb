"""Support triage: given headers / a sample payload and optionally a file / table / feed name, explain what the flow
and the metadata expect and what does not match. Returns plain dicts (used by the CLI, --json and the MCP server)."""
import csv
import difflib
import io
import json
import re
import time
from pathlib import Path

from . import db as dbmod, metadata as metamod
from .build import _normalize

SEV_RANK = {"error": 0, "high": 1, "warn": 2, "info": 3}


# ------------------------------------------------------------------------------------------------ inputs
def headers_from_sample(path):
    """Field names from a sample file: JSON (object, array of objects, or an object wrapping a record list) or
    delimited text (header line; delimiter sniffed)."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        try:
            data = json.loads(stripped)
        except ValueError:
            data = [json.loads(line) for line in stripped.splitlines() if line.strip()]  # JSON lines
        return _json_keys(data)
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    try:
        dialect = csv.Sniffer().sniff(first, delimiters=",|\t;~^")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    return [h.strip() for h in next(csv.reader(io.StringIO(first), delimiter=delim)) if h.strip()]


def read_sample(path):
    """{'kind': 'json', 'data': payload} or {'kind': 'csv', 'data': [headers]} - JSON is kept whole so the metadata path
    can apply the feed's root path and compare nested fields."""
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    stripped = text.lstrip()
    if stripped[:1] in "{[":
        try:
            return {"kind": "json", "data": json.loads(stripped)}
        except ValueError:
            return {"kind": "json", "data": [json.loads(line) for line in stripped.splitlines() if line.strip()]}
    return {"kind": "csv", "data": headers_from_sample(path), "path": str(path)}


def _json_keys(data):
    if isinstance(data, list):
        rec = next((x for x in data if isinstance(x, dict)), None)
        return list(rec) if rec else []
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
        if len(lists) == 1 and len(data) <= 5:
            return list(lists[0][0])
        return list(data)
    return []


def split_headers(values):
    return [f for part in values or [] for f in str(part).replace(",", " ").split() if f]


# ------------------------------------------------------------------------------------------------ record-schema path
def record_diagnosis(store, headers, cfg=None):
    """Match headers to the PutDatabaseRecord-style processors whose reader schema is known statically."""
    rows = store.db.execute("SELECT * FROM record_schemas").fetchall()
    result = {"mode": "record", "headers": headers, "best": None, "issues": [], "findings": [], "candidates": []}
    if not rows:
        result["error"] = ("no record-based ingestion points in the KB (no PutDatabaseRecord-style processor with a resolvable "
                           "reader schema + matched table)")
        return result
    scored = []
    for r in rows:
        fields, translate = json.loads(r["fields"]), bool(r["translate"])
        ng = {_normalize(f, translate): f for f in headers}
        ne = {_normalize(f, translate): f for f in fields}
        scored.append((len(set(ng) & set(ne)) / max(len(ne), 1), r, fields, translate, ng, ne))
    scored.sort(key=lambda x: -x[0])
    for score, r, *_ in scored[:5]:
        c = store.db.execute("SELECT name FROM components WHERE id=?", (r["component_id"],)).fetchone()
        result["candidates"].append({"score": round(score, 3), "component_id": r["component_id"], "name": c["name"] if c else "?",
                                     "db": r["db"], "table": r["table_name"]})
    score, r, fields, translate, ng, ne = scored[0]
    if score == 0:
        result["error"] = "no confident match"
        return result
    comp = component_ref(store, r["component_id"])
    result["best"] = dict(comp, score=round(score, 3), db=r["db"], table=r["table_name"], expected_fields=fields)
    issues = result["issues"]
    for n, h in ng.items():
        if n not in ne:
            guess = difflib.get_close_matches(h, fields, n=1)
            issues.append({"severity": "error", "kind": "unknown-header",
                           "message": f"header '{h}' is not one of the expected fields" + (f" (did you mean '{guess[0]}'?)" if guess else "")})
    missing = [ne[n] for n in ne if n not in ng]
    if missing:
        issues.append({"severity": "warn", "kind": "missing-field", "message": f"expected fields not present in your headers: {', '.join(missing)}"})
    dbtab = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=lower(?)", (r["db"], r["table_name"])).fetchone()
    columns = json.loads(dbtab["data"])["columns"] if dbtab else []
    matched = {n: f for n, f in ng.items() if n in ne}
    cols = {_normalize(c["name"], translate): c for c in columns}
    extra = [f for n, f in matched.items() if n not in cols]
    required = [c["name"] for n, c in cols.items() if n not in matched and not c["nullable"] and c.get("default") is None
                and "auto_increment" not in str(c.get("extra", "")).lower() and not str(c.get("default") or "").startswith("nextval")]
    if extra:
        issues.append({"severity": "error", "kind": "column-missing",
                       "message": f"these headers have no matching column in {r['table_name']}: {', '.join(extra)}"})
    if required:
        issues.append({"severity": "error", "kind": "required-column",
                       "message": f"NOT NULL column(s) in {r['table_name']} that nothing supplies: {', '.join(required)}"})
    result["findings"] = findings_for(store, [r["component_id"]])
    if cfg:
        result["learnings"] = learnings_for(cfg, [r["table_name"], comp["name"], comp["short_id"], comp["type"]])
    return result


# ------------------------------------------------------------------------------------------------ metadata path
def metadata_diagnosis(cfg, store, key, headers=(), live=False, sample_path=None):
    """Everything the metadata config tables say about one file / table / feed / API, plus checks and linked processors."""
    m = metamod.settings(cfg)
    model = store.get_meta("metadata_model")
    if not m or not model:
        return {"mode": "metadata", "key": key, "error": "metadata support is not configured: add a [metadata] section to nifikb.toml "
                                                          "and run `python -m nifikb build` (see README)"}
    st = model.get("structure_table")
    targets_live = None
    if live:
        dcfg = metamod.db_config(cfg, m["db"])
        rows_by_table = metamod.fetch_live(dcfg, m, model)
        first = metamod.dossier(model, metamod.Rows(rows_by_table), key)
        ids = [d["id"] for d in first["definitions"]]
        if st:
            rows_by_table[st] = metamod.fetch_structure(dcfg, model, ids)
        names = sorted({str(d["target"]) for d in first["definitions"] if d.get("target")})
        if names and m["target_db"]:
            tcfg = dict(metamod.db_config(cfg, m["target_db"]), include_tables=[], all_tables=False, profile_tables=[],
                        sample_rows=0, max_tables=len(names) + 5)
            res = dbmod.introspect(tcfg, set(), names, log=lambda _m: None)
            targets_live = [{"name": m["target_db"], "tables": res["tables"], "all_table_names": res["all_table_names"]}]
    else:
        rows_by_table = store.get_meta_rows(exclude=st)
        first = metamod.dossier(model, metamod.Rows(rows_by_table), key)
        if st:
            rows_by_table[st] = store.get_structure_rows(st, model["structure_parent"], [d["id"] for d in first["definitions"]])
    rows = metamod.Rows(rows_by_table)
    db_results = targets_live or _target_results(store, model, first)
    sample = read_sample(sample_path) if sample_path else None
    result = metamod.dossier(model, rows, key, headers=headers, db_results=db_results, sample=sample)
    result.update(mode="metadata", live=live, headers=list(headers))
    fetched = store.cached_db_fetched("__metadata__")
    result["snapshot"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(fetched)) if fetched else None
    ids = [d["id"] for d in result["definitions"]]
    result["recent_changes"] = [{"when": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"])), "change": r["change"]}
                                for r in store.meta_changes_for(ids, 15)]
    if live and ids:  # what changed in these rows after the last snapshot (often: "it broke this morning")
        snap = store.get_meta_rows(exclude=st)
        if st:
            snap[st] = store.get_structure_rows(st, model["structure_parent"], ids)
        wanted = {str(i) for i in ids}
        result["changed_since_snapshot"] = [c["change"] for c in metamod.diff_rows(model, snap, rows_by_table)
                                            if c["link"] in wanted][:30]
    result["processors"] = linked_processors(store, model, result)
    result["findings"] = findings_for(store, [p["id"] for p in result["processors"]])
    for d in result["definitions"]:
        d["issues"].sort(key=lambda i: SEV_RANK.get(i["severity"], 9))
    terms = [key, Path(key.replace("\\", "/")).name]
    terms += [x for d in result["definitions"] for x in (d.get("label"), d.get("target"), f"{model.get('definition_table')}:{d.get('id')}")]
    terms += [x for p in result["processors"] for x in (p["name"], p["short_id"], p["type"])]
    terms += [m["table"] for m in result["matches"]]
    result["learnings"] = learnings_for(cfg, terms)
    return result


def learnings_for(cfg, terms):
    from . import learnings as lm
    return [{"id": i["id"], "title": i["title"], "kind": i["kind"], "score": i["score"], "ticket": i.get("ticket"),
             "date": i.get("date"), "excerpt": " ".join(i["body"].split())[:400]} for i in lm.relevant(cfg, terms)]


def _target_results(store, model, pre):
    names = {str(d["target"]).lower().split(".")[-1] for d in pre["definitions"] if d.get("target")}
    tables = []
    for n in names:
        row = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=?", (model["target_db"], n)).fetchone()
        if row:
            tables.append(json.loads(row["data"]))
    return [{"name": model["target_db"], "tables": tables, "all_table_names": store.get_meta(f"db_all_tables:{model['target_db']}", [])}]


def linked_processors(store, model, result, cap=25):
    """Processors tied to this object: configured with one of its identifying values, writing its target table, or
    reading the config tables (the metadata lookup processors)."""
    found = {}

    def add(cid, why):
        if cid in found:
            if why not in found[cid]["why"]:
                found[cid]["why"].append(why)
            return
        if len(found) >= cap:
            return
        ref = component_ref(store, cid)
        if ref:
            found[cid] = dict(ref, why=[why])

    values = set()
    rows = [x["row"] for x in result.get("matches", [])] + [d["row"] for d in result.get("definitions", [])]
    rows += [r for rs in result.get("related", {}).values() for r in rs]
    for r in rows:
        for k, v in r.items():
            if isinstance(v, str) and 4 <= len(v) <= 200 and v != "***" and (
                    metamod.KEY_COL.search(k) or metamod.TARGET_COL.search(k) or re.search(r"(?i)host|url|endpoint|dir|path", k)):
                values.add(v)
    for v in sorted(values):
        q = ("SELECT DISTINCT component_id, display FROM properties WHERE lower(resolved)=lower(?) "
             "OR (length(?) >= 6 AND instr(lower(resolved), lower(?)) > 0) LIMIT 50")
        for p in store.db.execute(q, (v, v, v)):
            add(p["component_id"], f"property '{p['display']}' contains '{v}'")
    for d in result.get("definitions", []):
        if d.get("target"):
            t = str(d["target"]).lower().split(".")[-1]
            for p in store.db.execute("SELECT DISTINCT component_id FROM resources WHERE kind='db_table' AND lower(value) IN (?, ?)",
                                      (t, str(d["target"]).lower())):
                add(p["component_id"], f"writes/reads target table {d['target']}")
    for t in model["tables"]:
        for p in store.db.execute("SELECT DISTINCT component_id FROM resources WHERE kind='db_table' AND lower(value)=lower(?) LIMIT 10", (t,)):
            add(p["component_id"], f"reads config table {t}")
    for fqcn, tables in (store.get_meta("config_table_code") or {}).items():
        for p in store.db.execute("SELECT id FROM components WHERE type=? LIMIT 10", (fqcn,)):
            add(p["id"], f"custom {fqcn.rsplit('.', 1)[-1]} queries {', '.join(tables)} in its code")
    return list(found.values())


# ------------------------------------------------------------------------------------------------ shared
def component_ref(store, cid):
    c = store.db.execute("SELECT id, name, type, group_id, group_path, state FROM components WHERE id=?", (cid,)).fetchone()
    if not c:
        return None
    g = store.db.execute("SELECT doc FROM groups WHERE id=?", (c["group_id"],)).fetchone()
    return {"id": c["id"], "short_id": c["id"][:8], "name": c["name"], "type": (c["type"] or "").rsplit(".", 1)[-1],
            "group": c["group_path"], "state": c["state"], "doc": f"{g['doc']}#c-{c['id'][:8]}" if g else None}


def findings_for(store, component_ids):
    out = []
    for cid in component_ids:
        for f in store.db.execute("SELECT severity, kind, message FROM findings WHERE component_id=?", (cid,)):
            out.append({"component_id": cid, "severity": f["severity"], "kind": f["kind"], "message": f["message"]})
    out.sort(key=lambda f: SEV_RANK.get(f["severity"], 9))
    return out


def has_errors(result):
    issues = list(result.get("issues", [])) + [i for d in result.get("definitions", []) for i in d.get("issues", [])]
    return any(i["severity"] == "error" for i in issues)


# ------------------------------------------------------------------------------------------------ text output
def format_text(result):
    if result["mode"] == "record":
        return _format_record(result)
    return _format_metadata(result)


def _issue_lines(issues, indent="  "):
    marks = {"error": "x", "high": "x", "warn": "!", "info": "-"}
    return [f"{indent}{marks.get(i['severity'], '-')} [{i['severity']}] {i['message']}" for i in issues]


def _learning_lines(r):
    items = r.get("learnings") or []
    if not items:
        return []
    L = ["", "Team learnings that may apply (python -m nifikb learn show <id>):"]
    for i in items:
        L.append(f"  {i['id']} [{i['kind']}] {i['title']}" + (f" (ticket {i['ticket']})" if i.get("ticket") else ""))
        L.append(f"    {i['excerpt'][:300]}")
    return L


def _format_record(r):
    L = []
    if r.get("error"):
        L.append(r["error"] + (";" if r["candidates"] else ""))
        if r["candidates"]:
            L.append("closest ingestion points by name overlap:")
            L += [f"  {c['score']:.0%}  {c['name']} -> {c['db']}.{c['table']}" for c in r["candidates"]]
        return "\n".join(L)
    b = r["best"]
    L.append(f"Best match ({b['score']:.0%} of expected fields present): {b['name']} `{b['short_id']}` -> {b['db']}.{b['table']}  [{b['doc']}]")
    L += _issue_lines(r["issues"])
    if not r["issues"]:
        L.append("  OK all headers map cleanly to the reader schema and table columns")
    if r["findings"]:
        L.append("  known issues already flagged on this processor:")
        L += [f"    [{f['severity']}] {f['kind']}: {f['message']}" for f in r["findings"]]
    L += _learning_lines(r)
    return "\n".join(L)


def _short_row(row, limit=12):
    items = [(k, v) for k, v in row.items() if v not in (None, "")]
    s = ", ".join(f"{k}={v}" for k, v in items[:limit])
    return s + (f", … +{len(items) - limit}" if len(items) > limit else "")


def _format_metadata(r):
    if r.get("error"):
        return r["error"]
    L = [f"Metadata for '{r['key']}'" + (" (live: config rows read just now)" if r.get("live") else
                                         f" (config rows from the snapshot of {r.get('snapshot') or 'the last build'}; "
                                         "use live mode for rows changed since)")]
    if not r["matches"]:
        L.append("  nothing in the config tables matches this name")
        if r.get("suggestions"):
            L.append("  did you mean: " + ", ".join(r["suggestions"]))
        return "\n".join(L)
    L.append("Matched:")
    L += [f"  {x['table']}.{x['column']} ({x['match']}): {_short_row(x['row'])}" for x in r["matches"][:10]]
    for d in r["definitions"]:
        L += ["", f"Definition {d['id']} · {d['label']}" + (f" → target table {d['target']}" if d.get("target") else "")
              + (f" → loads to {d['location']}" if d.get("location") else "")]
        if d["fields"]:
            L.append(f"  structure ({len(d['fields'])} fields): " + ", ".join(
                (f"{f['seq']}:" if f["seq"] is not None else "") + f["name"] + (f" {f['type']}" if f.get("type") else "")
                + (f"({f['length']})" if f.get("length") else "") + ("?" if f.get("nullable") else "")
                for f in d["fields"][:80]) + (" …" if len(d["fields"]) > 80 else ""))
        smp = d.get("sample")
        if smp and smp.get("kind") == "csv" and smp.get("delimiter"):
            L.append(f"  sample: CSV, delimiter {smp['delimiter']!r} ({smp.get('delimiter_source')}), "
                     f"{'with' if smp.get('header') else 'no'} header row, {smp.get('rows', 0)} data rows checked")
        if smp and smp.get("kind") == "json":
            L.append(f"  sample: JSON, record root {smp.get('root') or '(top level)'}, {smp['fields']} "
                     + ("nested field paths compared" if smp.get("paths") else "top-level keys compared") + " (order not checked)")
        L += _issue_lines(d["issues"])
        if not d["issues"]:
            L.append("  OK structure, headers and target table agree")
        from .fixes import format_fixes
        L += format_fixes(d.get("fixes") or [])
    if r.get("changed_since_snapshot"):
        L += ["", f"Config rows changed since the snapshot of {r.get('snapshot') or 'the last build'} (live read):"]
        L += [f"  {c}" for c in r["changed_since_snapshot"]]
    if r.get("recent_changes"):
        L += ["", "Recent config-row changes for this definition (from earlier snapshots, newest first):"]
        L += [f"  {c['when']}  {c['change']}" for c in r["recent_changes"]]
    if r["related"]:
        L += ["", "Related config rows:"]
        for t, rows in r["related"].items():
            for row in rows[:5]:
                L.append(f"  {t}: {_short_row(row)}")
            if len(rows) > 5:
                L.append(f"  {t}: … {len(rows) - 5} more")
    if r.get("processors"):
        L += ["", "Flow processors involved:"]
        for p in r["processors"]:
            L.append(f"  {p['name']} [{p['type']}] `{p['short_id']}` {p['state'] or ''} in {p['group']} — {'; '.join(p['why'][:2])}  [{p['doc']}]")
    if r.get("findings"):
        L += ["", "Known issues on those processors:"]
        L += [f"  [{f['severity']}] {f['component_id'][:8]} {f['kind']}: {f['message']}" for f in r["findings"][:30]]
    L += _learning_lines(r)
    return "\n".join(L)
