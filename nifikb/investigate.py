"""One-call ticket investigation: metadata diagnosis + provenance + logs + code messages + learnings + static findings,
merged into a ranked list of likely causes with the evidence under it. Built for smaller models (Gemini Flash): the
tool does the planning, the model explains the result."""
import re
import time
from pathlib import Path

from . import audit as auditmod, diagnose as dg, learnings as lm, logs as lg, metadata as metamod, nifiapi, target as tgt

PRIORITY = {"provenance": 1, "audit": 2, "target": 2.5, "live": 3, "file-log": 4, "structure": 5, "config-change": 6, "instance": 7,
            "processor-log": 8, "learning": 9, "finding": 10, "warning": 11}


def _runtime_ids(store, flow_ids):
    ids = set(flow_ids)
    for fid in flow_ids:
        try:
            row = store.db.execute("SELECT instance_id FROM components WHERE id=?", (fid,)).fetchone()
        except Exception:
            row = None
        if row and row[0]:
            ids.add(row[0])
    return sorted(ids)


def investigate(cfg, store, names, file=None, feed=None, table=None, error_text=None, headers=(), sample_path=None,
                live=False, since_hours=72, record=True):
    key = file or feed or table
    causes, sections, next_checks = [], [], []

    def cause(kind, text):
        causes.append((PRIORITY[kind], len(causes), text, kind))

    # 1. metadata: definition, structure vs file, target, related config, processors, config changes
    diag, proc_ids = None, []
    if key and metamod.settings(cfg) and store.get_meta("metadata_model"):
        diag = dg.metadata_diagnosis(cfg, store, key, list(headers), live=live, sample_path=sample_path)
        sections.append(("Metadata (config tables)", dg.format_text(diag)))
        fixes = [f for d in diag.get("definitions") or [] for f in d.get("fixes") or []]
        if fixes:
            text = "\n".join(f"-- {f['why']} [{f['who']}]" + (f": {f['note']}" if f.get("note") else "") + "\n" + f["sql"] for f in fixes)
            sections.insert(0, ("Proposed fixes (for a human to review and run - never applied automatically)", text))
        proc_ids = [p["id"] for p in diag.get("processors") or []]
        for d in diag.get("definitions") or []:
            for i in d["issues"]:
                if i["severity"] == "error":
                    cause("structure", f"{d['label']}: {i['message']}")
                elif i["severity"] == "warn":
                    cause("warning", f"{d['label']}: {i['message']}")
        for c in diag.get("changed_since_snapshot") or []:
            cause("config-change", f"config row changed since the last snapshot: {c}")
        recent = [c for c in diag.get("recent_changes") or []
                  if time.time() - time.mktime(time.strptime(c["when"], "%Y-%m-%d %H:%M")) < 3 * 86400]
        for c in recent[:5]:
            cause("config-change", f"config row changed {c['when']}: {c['change']}")
        if not diag.get("matches"):
            next_checks.append(f"'{key}' matches no config row" + (f" - did you mean {', '.join(diag['suggestions'][:3])}?"
                                                                   if diag.get("suggestions") else "; try the feed / table / API name"))
    elif key:
        next_checks.append("metadata not configured ([metadata] in nifikb.toml) - no structure / config checks")

    # 2. provenance: where did the FlowFile(s) end up
    api = nifiapi.settings(cfg)
    if file and api:
        try:
            flows = nifiapi.journey(nifiapi.Client(api), filename=Path(file.replace("\\", "/")).name)
            sections.append(("Provenance (what happened to the FlowFile)", nifiapi.format_journey(flows, names, file)))
            for f in flows:
                if f["verdict"].startswith(("DROPPED", "last seen")):
                    cause("provenance", f"FlowFile {str(f['uuid'])[:8]} {f['verdict']}"
                          + (f" [{', '.join(f'{k}={v}' for k, v in list(f['attributes'].items())[:4])}]" if f["attributes"] else ""))
            if not flows:
                cause("provenance", f"no provenance events for '{file}': it never entered NiFi under that name (not picked up: "
                                    "source path / listing / file-name filter) or its events aged out")
        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
            next_checks.append(f"provenance not available: {e}")
    elif file:
        next_checks.append("configure [nifi_api] to see where the FlowFile was dropped (provenance)")

    # 2a. the platform's own load-audit record of this file / definition
    amodel = store.get_meta("audit_model")
    if amodel and (file or diag):
        try:
            ids = [d["id"] for d in (diag or {}).get("definitions") or []]
            fname_a = Path(file.replace("\\", "/")).name if file else None
            rows = auditmod.lookup(cfg, amodel, file=fname_a, link_ids=ids if not fname_a else ())
            if not rows and ids:
                rows = auditmod.lookup(cfg, amodel, link_ids=ids)
            sections.append((f"Load audit ({amodel['table']})", auditmod.format_rows(amodel, rows)))
            file_rows_a = [r for r in rows if fname_a and fname_a.lower() in str(r.get(amodel["file_column"]) or "").lower()]
            if file_rows_a:
                last = file_rows_a[0]
                if auditmod.is_failure(amodel, last):
                    cause("audit", f"load audit: last load FAILED - {auditmod.summarize(amodel, last)}")
                else:
                    cause("warning", f"load audit: last load recorded as {auditmod.summarize(amodel, last)}")
            elif fname_a:
                cause("warning", f"no load-audit row for {fname_a}: the load step never recorded this file")
        except Exception as e:  # DB down etc.: never break the investigation
            next_checks.append(f"load audit not available: {e}")

    # 2a'. the target side: did the load write anything to HDFS / S3, and does the Parquet match the structure
    if diag and tgt.enabled(cfg):
        for d, res in tgt.check_diagnosis(cfg, store.get_meta("metadata_model"), diag, file=file):
            sections.append((f"Target output ({d['label']})", tgt.format_check(res)))
            for sev, kind, msg in res["issues"]:
                if sev == "error":
                    cause("target", f"{d['label']} target: {msg}")
                elif sev == "warn":
                    cause("warning", f"{d['label']} target: {msg}")

    # 2b. live health of the processors involved (stuck queue / invalid / stopped) and of the whole instance (disk, heap)
    if api:
        try:
            h = nifiapi.health(nifiapi.Client(api), versioned=store.versioned_groups())
            involved = set(_runtime_ids(store, proc_ids))
            mine = [p for p in h["problems"] if p.get("component_id") in involved]
            instance = [p for p in h["problems"] if p["kind"] in ("disk", "heap", "cluster")]
            for p in mine:
                cause("live", f"live NiFi: {p['message']}")
            for p in instance:
                cause("instance", f"live NiFi (whole instance): {p['message']}")
            if mine or instance:
                sections.append(("Live NiFi health (problems touching this ticket)", "\n".join(
                    f"[{p['severity']}] {p['kind']}: {p['message']}" for p in mine + instance)))
        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
            next_checks.append(f"live health not available: {e}")

    # 3. logs: errors about this file, and about the processors involved
    lg.index(cfg, store, log=lambda m: None)
    fname = Path(file.replace("\\", "/")).name if file else None
    file_rows = lg.query(store, filename=fname, limit=10) if fname else []
    for r in file_rows:
        if r["level"] in ("ERROR", "FATAL", "WARN"):
            who = names.get(r["component_id"], r["component_type"] or "NiFi")
            cause("file-log", f"{who} logged {r['level']} x{r['n']} for this file: {lg.compact(r['sample'])[:220]}"
                              + (f" - cause: {r['cause']}" if r["cause"] else ""))
    runtime = _runtime_ids(store, proc_ids)
    proc_rows = lg.query(store, component_ids=runtime, since_hours=since_hours, limit=10) if runtime else []
    listed = {(r["component_id"], r["template"]) for r in file_rows}
    proc_rows = [r for r in proc_rows if (r["component_id"], r["template"]) not in listed]  # already ranked as file errors
    for r in proc_rows[:4]:
        if r["level"] in ("ERROR", "FATAL"):
            cause("processor-log", f"{names.get(r['component_id'], r['component_type'])} logged ERROR x{r['n']} "
                                   f"({r['first'][:16]} .. {r['last'][:16]}): {lg.compact(r['sample'])[:180]}"
                                   + (f" - cause: {r['cause']}" if r["cause"] else ""))
    grep_rows = lg.query(store, grep=error_text, limit=10) if error_text else []
    for title, rows in (("Log errors for this file", file_rows), ("Log errors of the processors involved", proc_rows),
                        (f"Log lines containing '{error_text}'", grep_rows)):
        if rows:
            sections.append((title, lg.format_rows(rows, names)))

    # 4. the error text in the custom code (which processor / line raises it)
    if error_text:
        words = [w for w in error_text.replace('"', " ").split() if len(w) > 2][:8]
        hits = [r for r in store.search(" ".join(words), 10) if r["kind"] == "message"] if words else []
        if hits:
            sections.append(("Code that produces this error text", "\n".join(f"{r['title']} -> {r['doc']}: {r['snip']}" for r in hits)))
            cause("processor-log", f"the error text comes from {hits[0]['title']} ({hits[0]['doc']})")

    # 5. learnings
    items = (diag or {}).get("learnings") or []
    if not items:
        terms = [x for x in (key, fname, table, feed) if x] + (error_text.split()[:6] if error_text else [])
        items = dg.learnings_for(cfg, terms)
    for i in items[:3]:
        if i["score"] >= 3:
            cause("learning", f"known issue {i['id']}: {i['title']}")
    if items:
        sections.append(("Team learnings", "\n".join(f"{i['id']} [{i['kind']}] {i['title']}\n  {i['excerpt'][:300]}" for i in items)))

    # 6. static findings on the processors involved
    for f in (diag or {}).get("findings") or []:
        if f["kind"] in ("attribute-unset", "attribute-misnamed", "custom-source-drift", "custom-nar-missing", "bundle-version",
                         "field-mismatch", "missing-table", "unhandled-relationship", "disabled-service"):
            cause("finding", f"{f['kind']} on `{f['component_id'][:8]}`: {f['message']}")
        elif f["kind"] == "dropped-errors":
            cause("warning", f"`{f['component_id'][:8]}` silently drops failures ({f['message'].split(':')[0]}) - errors there leave "
                             "only a log line / provenance DROP")

    causes.sort()
    seen, ranked = set(), []
    for _, _, text, kind in causes:
        if text not in seen:
            seen.add(text)
            ranked.append((kind, text))
    if key and record:
        try:  # remembered for learning suggestions (recurring causes nobody has written down yet)
            store.add_investigation(key, [(k, signature(t), t) for k, t in ranked[:3] if k not in NOT_REMEMBERED])
        except Exception:
            pass  # a read-only / locked KB must not break the investigation
    return {"key": key, "causes": [t for _, t in ranked[:10]], "sections": sections, "next_checks": next_checks}


NOT_REMEMBERED = {"learning", "instance", "warning"}  # already written down / not about the ticket / too weak


def signature(text):
    """A cause without its variable parts (dates, counts, ids, quoted values), so repeats of one problem group together."""
    s = re.sub(r"'[^']*'|`[^`]*`|\"[^\"]*\"", "'…'", text)
    s = re.sub(r"\b[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b[0-9a-f]{8}\b", "#", s)
    s = re.sub(r"\d{4}-\d\d-\d\d[ T]?[\d:.,]*|\d+", "#", s)
    s = re.sub(r"\[[^\]]*=[^\]]*\]", "", s)  # attribute dumps
    return re.sub(r"\s+", " ", s).strip()[:300]


def format_report(r):
    L = [f"# Investigation: {r['key'] or '(no name given)'}", "", "## Most likely causes (ranked; strongest evidence first)"]
    L += [f"{n}. {c}" for n, c in enumerate(r["causes"], 1)] or ["(nothing conclusive found - see the evidence and next checks)"]
    if r["next_checks"]:
        L += ["", "## Next checks"] + [f"- {c}" for c in r["next_checks"]]
    for title, text in r["sections"]:
        L += ["", f"## {title}", text]
    return "\n".join(L)
