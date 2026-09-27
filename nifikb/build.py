"""Build / incrementally refresh the knowledge base."""
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from . import __version__, audit as auditmod, db as dbmod, learnings as learnmod, logs as logmod, metadata as metamod
from .analyze import Analysis, type_short
from .catalog import PARSER_VERSION as NAR_PARSER_VERSION, Catalog, find_nars, read_nar
from .code import PARSER_VERSION as CODE_PARSER_VERSION, CodeIndex, index_file, iter_code_files
from .flow import load_flow
from .render import Renderer
from .store import Store
from .util import REDACTED, clip, file_sig, redact_secrets, sha1_file, short, slugify, write_if_changed

GENERATED_DIRS = ("flows", "custom-code", "scripts", "db")


def _h(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def find_flow_file(cfg):
    nifi = cfg["nifi"]
    if nifi.get("flow_file"):
        return Path(nifi["flow_file"])
    home = Path(nifi["home"])
    for name in ("conf/flow.json.gz", "conf/flow.xml.gz", "flow.json.gz", "flow.xml.gz"):
        if (home / name).is_file():
            return home / name
    raise FileNotFoundError(f"no flow.json.gz / flow.xml.gz under {home} (set [nifi] flow_file)")


def read_nifi_properties(cfg):
    home = cfg["nifi"].get("home")
    path = Path(home) / "conf" / "nifi.properties" if home else None
    props = {}
    if path and path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                props[k.strip()] = REDACTED if re.search(r"(?i)pass|secret|key$", k) and v.strip() else v.strip()
    return props


def build(cfg, force=False, refresh_db=False, log=print):
    out = Path(cfg["output"]["dir"])
    out.mkdir(parents=True, exist_ok=True)
    store = Store(str(out / "kb.sqlite"))
    try:
        return _build(cfg, store, out, force, refresh_db, log)
    finally:
        store.close()


def _build(cfg, store, out, force, refresh_db, log):
    t0 = time.time()
    flow_path = find_flow_file(cfg)
    nar_dirs = [Path(cfg["nifi"]["home"]) / d for d in ("lib", "extensions")] if cfg["nifi"].get("home") else []
    nar_dirs += [Path(d) for d in cfg["nifi"].get("extra_nar_dirs", [])]
    nar_files = find_nars(nar_dirs)
    repos = [Path(r) for r in cfg["code"].get("repos", [])]
    code_files = list(iter_code_files(repos))
    referenced = [Path(p) for p in store.get_meta("referenced_scripts", []) if Path(p).is_file()]
    sources = {
        "flow": sha1_file(flow_path),
        "nars": _h([(str(p), file_sig(p)) for p in nar_files]),
        "code": _h([(str(p), file_sig(p)) for p in code_files + referenced]),
        "config": _h({k: v for k, v in cfg.items() if k != "_path"}),
        "knowledge": _h([(str(p), file_sig(p)) for p in sorted(Path(cfg["knowledge"]["dir"]).rglob("*.md"))]
                        if Path(cfg["knowledge"]["dir"]).is_dir() else []),
        # any change to nifikb itself (an upgrade, a fix) regenerates the KB, not only a version bump
        "version": f"{__version__}/{CODE_PARSER_VERSION}/{NAR_PARSER_VERSION}/"
                   + _h([(p.name, file_sig(p)) for p in sorted(Path(__file__).parent.glob("*.py"))]),
    }
    build_sig = _h(sources)
    db_due = refresh_db or _db_due(cfg, store)
    meta_due = refresh_db or _meta_due(cfg, store)
    if not force and build_sig == store.get_meta("build_sig") and not db_due and not meta_due and (out / "INDEX.md").exists():
        log(f"Knowledge base is up to date ({out}). Use --force to rebuild.")
        return {"status": "up-to-date", "out": str(out)}

    log(f"Reading flow {flow_path}")
    flow = load_flow(flow_path)

    catalog, nar_keep = Catalog(), []
    for p in nar_files:
        key, sig = str(p), f"{file_sig(p)}:{NAR_PARSER_VERSION}"
        data = store.cached("cache_nar", key, sig)
        if data is None:
            try:
                data = read_nar(p)
            except Exception as e:  # corrupt / partial NAR
                log(f"  skip NAR {p.name}: {e}")
                continue
            store.put_cache("cache_nar", key, sig, data)
        catalog.add(data)
        nar_keep.append(key)
    store.prune_cache("cache_nar", nar_keep)
    log(f"  {len(nar_files)} NARs, {len(catalog.types)} component types")

    code, code_keep, parsed = CodeIndex(), [], 0

    def index_cached(p):
        nonlocal parsed
        key, sig = str(p), f"{file_sig(p)}:{CODE_PARSER_VERSION}"
        data = store.cached("cache_code", key, sig)
        if data is None:
            data = index_file(p)
            store.put_cache("cache_code", key, sig, data)
            parsed += 1
        code_keep.append(key)
        return data

    for p in code_files:
        try:
            code.add(index_cached(p))
        except OSError as e:
            log(f"  skip {p}: {e}")
    code.finalize()
    log(f"  code: {len(code_files)} files ({parsed} re-parsed), {len(code.by_fqcn)} NiFi components, {len(code.modules)} maven modules")

    an = Analysis(flow, catalog, code, cfg).run()
    previews = {}
    for path, entry in an.scripts.items():
        target = Path(path) if entry["exists"] else (Path(entry["repo_match"]) if entry.get("repo_match") else None)
        if target and target.is_file():
            entry["index"] = code.files.get(str(target)) or index_cached(target)
            text = target.read_text(encoding="utf-8", errors="replace")
            if len(text) < 6000:
                previews[path] = "\n".join(redact_secrets(ln) for ln in text.splitlines())
    store.prune_cache("cache_code", code_keep)
    store.set_meta("referenced_scripts", [p for p, e in an.scripts.items() if e["exists"]])

    db_results = _databases(cfg, an, code, store, db_due, log)
    meta = _metadata(cfg, an, store, db_results, db_due or meta_due, log, schemas_due=db_due)
    asettings = auditmod.settings(cfg)
    audit_model = auditmod.detect(asettings, next((d for d in db_results if d["name"] == asettings["db"]), None)) if asettings else None
    store.set_meta("audit_model", audit_model)
    if asettings:
        log(f"  audit: {'table ' + audit_model['table'] if audit_model else 'no load-audit table found - set [audit] table'}")
    _field_checks(an, db_results)

    instance = read_nifi_properties(cfg)
    snapshot = _snapshot(an)
    previous = store.last_snapshot()
    changes = _diff(previous, snapshot) if previous else []
    if changes:
        store.add_changes(changes)
        log(f"  {len(changes)} flow change(s) since last build")
    if previous is None or changes:
        store.add_snapshot(sources["flow"], snapshot)

    renderer = Renderer(an, out, code, db_results, {"code_roots": [str(r) for r in repos], "script_previews": previews,
                                                     "metadata": bool(meta), "learnings": len(learnmod.load_all(cfg, False)),
                                                     "metadata_summary": (f"{len(meta['model']['tables'])} config tables · {meta['checked']} "
                                                                          f"definitions checked · {len(meta['drift'])} with drift") if meta else None,
                                                     "knowledge_dir": cfg["knowledge"]["dir"]})
    files = renderer.render_all(instance, store.changes())
    files["README.md"] = _readme(cfg)
    if meta:
        meta["code_map"] = _config_table_code(meta, code, catalog)
        files["metadata.md"] = metamod.render(meta["model"], meta["rows"], meta["drift"], meta["checked"], meta["code_map"])
    written = sum(write_if_changed(out / rel, content) for rel, content in files.items())
    if not meta and (out / "metadata.md").exists():
        (out / "metadata.md").unlink()
    for d in GENERATED_DIRS:
        for f in (out / d).rglob("*.md") if (out / d).exists() else []:
            if f.relative_to(out).as_posix() not in files:
                f.unlink()
        for sub in sorted((p for p in (out / d).rglob("*") if p.is_dir()), reverse=True) if (out / d).exists() else []:
            if not any(sub.iterdir()):
                sub.rmdir()
    _store_facts(store, an, renderer, code, db_results, meta, cfg)
    try:
        logmod.index(cfg, store, log)
    except Exception as e:  # never fail a build because of a log file
        log(f"  ⚠ logs: {type(e).__name__}: {e}")
    # Scripts referenced by the flow are only known after analysis; sign them now so the next run can compare.
    referenced = [Path(p) for p in store.get_meta("referenced_scripts", []) if Path(p).is_file()]
    sources["code"] = _h([(str(p), file_sig(p)) for p in code_files + referenced])
    store.set_meta("build_sig", _h(sources))
    store.set_meta("built_at", time.time())
    store.set_meta("flow_file", str(flow_path))
    log(f"Knowledge base written to {out}: {len(files)} files ({written} changed), "
        f"{len(an.findings)} findings, {time.time() - t0:.1f}s")
    return {"status": "built", "out": str(out), "files": len(files), "changed": written, "findings": len(an.findings),
            "changes": changes}


# ------------------------------------------------------------------------------------------ databases
def _db_due(cfg, store):
    hours = float(cfg.get("db_refresh_hours", 24))
    for d in cfg.get("databases", []):
        row = store.db.execute("SELECT fetched FROM cache_db WHERE name=?", (d["name"],)).fetchone()
        if not row or time.time() - row["fetched"] > hours * 3600:
            return True
    return False


def _meta_due(cfg, store):
    """Config rows change more often than schemas: re-read them every [metadata] refresh_hours (default 1)."""
    m = cfg.get("metadata")
    if not m:
        return False
    row = store.db.execute("SELECT fetched FROM cache_db WHERE name='__metadata__'").fetchone()
    return not row or time.time() - row["fetched"] > float(m.get("refresh_hours", 1)) * 3600


def _databases(cfg, an, code, store, due, log):
    results = []
    tables_by_service = an.tables_by_service()
    code_tables = {t for info in code.files.values() for t in info.get("tables") or []}
    for s in an.scripts.values():
        if s.get("index"):
            code_tables |= set(s["index"].get("tables") or [])
    msettings = metamod.settings(cfg)
    asettings = auditmod.settings(cfg)
    for dcfg in cfg.get("databases", []):
        if msettings and dcfg["name"] == msettings["db"]:
            dcfg = dict(dcfg, include_tables=list(dcfg.get("include_tables") or []) + metamod.table_patterns(msettings))
        if asettings and dcfg["name"] == asettings["db"]:
            dcfg = dict(dcfg, include_tables=list(dcfg.get("include_tables") or []) + auditmod.patterns(asettings))
        services = [sid for sid, j in an.jdbc.items()
                    if dbmod.matches_jdbc(dcfg, dict(j, service_name=an.flow.services[sid]["name"]))]
        wanted = {t for sid in services for t in tables_by_service.get(sid, {})}
        sig = _h([dcfg, sorted(wanted), sorted(code_tables)])
        cached, fetched = store.cached_db(dcfg["name"], sig)
        data, error = cached, None
        if due or cached is None:
            try:
                data = dbmod.introspect(dcfg, wanted, code_tables, log=log)
                data["fetched"] = time.strftime("%Y-%m-%d %H:%M")
                store.put_db(dcfg["name"], sig, data)
            except dbmod.DbError as e:
                error = str(e)
                log(f"  ⚠ {e}" + (" - using cached schema" if cached else ""))
                an.findings.append({"severity": "warn", "kind": "db-unreachable", "component_id": None,
                                    "message": f"database '{dcfg['name']}': {error}", "location": dcfg["name"]})
        entry = dict(data or {"name": dcfg["name"], "tables": [], "missing": []})
        entry.update(name=dcfg["name"], services=services, error=error)
        for t in entry.get("missing", []):
            users = [cid for sid in services for cid in tables_by_service.get(sid, {}).get(t, [])]
            an.findings.append({"severity": "error", "kind": "missing-table", "component_id": users[0] if users else None,
                                "message": f"table '{t}' is written/read by the flow but does not exist in database '{dcfg['name']}'",
                                "location": dcfg["name"]})
        results.append(entry)
    return results


def _metadata(cfg, an, store, db_results, due, log, schemas_due=True):
    """Config tables that drive a metadata-driven flow: discover roles, snapshot rows, describe target tables, lint."""
    m = metamod.settings(cfg)
    if not m:
        return None
    meta_db = next((d for d in db_results if d["name"] == m["db"]), {})
    model = metamod.discover(m, meta_db)
    sig = _h([m, {t: i["columns"] for t, i in model["tables"].items()}])
    cached, _ = store.cached_db("__metadata__", sig)
    rows_by_table, targets = None, None
    if model["tables"] and (due or cached is None):
        try:
            rows_by_table = metamod.fetch_rows(metamod.db_config(cfg, m["db"]), m, model, log)
            old_targets = (cached or store.cached_db_any("__metadata__") or {}).get("targets")
            targets = (_metadata_targets(cfg, m, model, metamod.Rows(rows_by_table), db_results, log)
                       if schemas_due or not old_targets else old_targets)  # target schemas follow db_refresh_hours
            previous = store.get_meta_rows()
            store.put_meta_rows(rows_by_table)
            store.put_db("__metadata__", sig, {"targets": targets})
            if previous:  # first snapshot: nothing to compare
                changes = metamod.diff_rows(model, previous, rows_by_table)
                if changes:
                    store.add_meta_changes(changes)
                    store.add_changes([f"config {c['change']}" for c in changes[:500]]
                                      + ([f"config … {len(changes) - 500} more row changes (python -m nifikb diagnose --file <name> "
                                          "shows those of one definition)"] if len(changes) > 500 else []))
                    log(f"  metadata: {len(changes)} config row change(s) since the last snapshot")
        except dbmod.DbError as e:
            rows_by_table = None
            log(f"  ⚠ metadata: {e} - using the last snapshot")
            an.findings.append({"severity": "warn", "kind": "db-unreachable", "component_id": None, "location": m["db"],
                                "message": f"metadata config tables could not be read: {e} (using the last snapshot)"})
    if rows_by_table is None:
        rows_by_table = store.get_meta_rows()
        targets = (cached or store.cached_db_any("__metadata__") or {}).get("targets") or {"tables": [], "all_table_names": []}
    if not model["tables"]:
        log(f"  ⚠ metadata: no config tables matched {m['tables']} in database '{m['db']}'")
    tdb = next((d for d in db_results if d["name"] == m["target_db"]), None)
    if tdb is not None:
        have = {t["table"].lower() for t in tdb.get("tables", [])}
        tdb["tables"] = tdb.get("tables", []) + [t for t in targets["tables"] if t["table"].lower() not in have]
        if not tdb.get("all_table_names"):
            tdb["all_table_names"] = targets.get("all_table_names") or []
    rows = metamod.Rows(rows_by_table)
    drift, checked = metamod.lint(model, rows, db_results)
    an.findings.extend(drift)
    if checked:
        log(f"  metadata: {checked} definitions checked against target tables, {len(drift)} with problems")
    return {"model": model, "rows": rows, "drift": drift, "checked": checked, "settings": m}


def _metadata_targets(cfg, m, model, rows, db_results, log):
    """Describe the target tables named in the definition rows that the flow itself does not reference."""
    dt, col = model.get("definition_table"), model.get("definition_target")
    tdb = next((d for d in db_results if d["name"] == m["target_db"]), {})
    if not dt or not col or not m["target_db"]:
        return {"tables": [], "all_table_names": tdb.get("all_table_names") or []}
    names = sorted({str(r[col]).strip() for r in rows.table(dt) if r.get(col) and "${" not in str(r[col])
                    and metamod.table_target(model, r[col])})
    have = {t["table"].lower() for t in tdb.get("tables", [])}
    todo = [n for n in names if n.lower().split(".")[-1] not in have]
    if not todo:
        return {"tables": [], "all_table_names": tdb.get("all_table_names") or []}
    tcfg = dict(metamod.db_config(cfg, m["target_db"]), include_tables=[], all_tables=False, profile_tables=[], sample_rows=0,
                max_tables=len(todo) + 10)
    res = dbmod.introspect(tcfg, set(), todo, log=lambda msg: log(msg.replace("  db ", "  metadata target tables, db ")))
    return {"tables": res["tables"], "all_table_names": res["all_table_names"]}


def _normalize(name, translate):
    return re.sub(r"_", "", name).upper() if translate else name


def _field_checks(an, db_results):
    """PutDatabaseRecord: compare incoming record fields with the target table's columns."""
    for comp in an.flow.components.values():
        if type_short(comp["type"]) != "PutDatabaseRecord":
            continue
        sid = an.db_service_of(comp)
        db = next((d for d in db_results if sid in d.get("services", [])), None)
        props = {f["name"]: f["resolved"] for f in an.props[comp["id"]]}
        table = (props.get("put-db-record-table-name") or "").lower()
        if not db or not table or "${" in table:
            continue
        t = next((x for x in db.get("tables", []) if x["table"].lower() == table.split(".")[-1]), None)
        fields, origin = an.record_fields(comp)
        if not t or not fields:
            continue
        translate = props.get("put-db-record-translate-field-names", "true") != "false"
        cols = {_normalize(c["name"], translate): c for c in t["columns"]}
        norm_fields = {_normalize(f, translate): f for f in fields}
        extra = [f for n, f in norm_fields.items() if n not in cols]
        required = [c["name"] for n, c in cols.items() if n not in norm_fields and not c["nullable"]
                    and c.get("default") is None and "auto_increment" not in str(c.get("extra", "")).lower()
                    and not str(c.get("default") or "").startswith("nextval")]
        msg = []
        if extra:
            behavior = props.get("put-db-record-unmatched-field-behavior", "Ignore Unmatched Fields")
            msg.append(f"record fields with no column: {', '.join(extra)} ({behavior})")
        if required:
            msg.append(f"NOT NULL columns never supplied: {', '.join(required)}")
        message = "; ".join(msg) or f"all {len(fields)} fields map to columns"
        an.field_checks.append({"component_id": comp["id"], "db": db["name"], "table": table, "message": f"{message} (fields from {origin})",
                                "fields": fields, "translate": translate})
        if msg:
            sev = "error" if extra and "Fail" in props.get("put-db-record-unmatched-field-behavior", "") else "warn"
            an.findings.append({"severity": sev, "kind": "field-mismatch", "component_id": comp["id"],
                                "message": f"{table}: {message} (fields from {origin})", "location": db["name"]})


# ------------------------------------------------------------------------------------ snapshot / diff
def _snapshot(an):
    comps = {}
    for c in list(an.flow.components.values()) + list(an.flow.services.values()):
        if c.get("placeholder"):
            continue
        comps[c["id"]] = {"n": c["name"], "t": type_short(c["type"]) or c["kind"].lower(), "g": (an.flow.groups.get(c["group_id"]) or {}).get("path", ""),
                          "s": c.get("state"), "p": {f["display"]: clip(f["value"], 200) for f in an.props[c["id"]]},
                          "sch": f"{c.get('scheduling_strategy')} {c.get('scheduling_period')}" if c["kind"] == "PROCESSOR" else None,
                          "at": c.get("auto_terminated")}
    conns = sorted({f"{c['source_id']}|{','.join(c['relationships'])}|{c['dest_id']}" for c in an.flow.connections})
    versions = {gid: {"n": g["path"], "v": (g.get("version_control") or {}).get("version")}
                for gid, g in an.flow.groups.items() if g.get("version_control")}
    return {"c": comps, "e": conns, "g": versions}


def _diff(old, new):
    out = []
    oc, nc = old["c"], new["c"]

    def name(cid, snap):
        c = snap["c"].get(cid)
        return f"{c['n']} [{c['t']}] `{short(cid)}` in {c['g']}" if c else f"`{short(cid)}`"

    for cid in sorted(set(nc) - set(oc)):
        out.append(f"added {name(cid, new)}")
    for cid in sorted(set(oc) - set(nc)):
        out.append(f"removed {name(cid, old)}")
    for cid in sorted(set(nc) & set(oc)):
        a, b = oc[cid], nc[cid]
        if a["s"] != b["s"]:
            out.append(f"{name(cid, new)}: state {a['s']} → {b['s']}")
        if a["n"] != b["n"]:
            out.append(f"{name(cid, new)}: renamed from '{a['n']}'")
        if a.get("sch") != b.get("sch"):
            out.append(f"{name(cid, new)}: schedule {a.get('sch')} → {b.get('sch')}")
        if a.get("at") != b.get("at"):
            out.append(f"{name(cid, new)}: auto-terminated {a.get('at')} → {b.get('at')}")
        for k in sorted(set(a["p"]) | set(b["p"])):
            if a["p"].get(k) != b["p"].get(k):
                out.append(f"{name(cid, new)}: '{k}' `{a['p'].get(k)}` → `{b['p'].get(k)}`")
    snap_names = {**old["c"], **new["c"]}

    def edge(e):
        s, rel, d = e.split("|")
        return f"{snap_names.get(s, {}).get('n', short(s))} -{rel}→ {snap_names.get(d, {}).get('n', short(d))}"

    for gid, g in sorted((new.get("g") or {}).items()):
        before = (old.get("g") or {}).get(gid)
        if before and before.get("v") != g.get("v"):
            out.append(f"process group {g['n']}: registry version {before.get('v')} → {g.get('v')}")
        elif not before and old.get("g") is not None:
            out.append(f"process group {g['n']}: now version-controlled (v{g.get('v')})")
    for e in sorted(set(new["e"]) - set(old["e"])):
        out.append(f"connection added: {edge(e)}")
    for e in sorted(set(old["e"]) - set(new["e"])):
        out.append(f"connection removed: {edge(e)}")
    return out


# --------------------------------------------------------------------------------------- sqlite facts
def _config_table_code(meta, code, catalog=None, depth=2):
    """{custom component class: [config tables its source mentions]}. Follows the classes the component's source refers
    to (e.g. processor -> service -> DAO) and matches table names as words, so constants and dynamically built SQL count."""
    tables = sorted(meta["model"]["tables"], key=len, reverse=True)
    if not tables:
        return {}
    rx = re.compile(r"(?i)(?<![\w$])(" + "|".join(re.escape(t) for t in tables) + r")(?![\w$])")
    canon = {t.lower(): t for t in tables}
    by_stem = {}
    for path, info in code.files.items():
        if info.get("lang") in ("java", "groovy", "kotlin", "scala", "python"):
            by_stem.setdefault(Path(path).stem, []).append(path)
    texts = {}

    def text(path):
        if path not in texts:
            try:
                texts[path] = Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                texts[path] = ""
        return texts[path]

    out = {}
    for fqcn, entries in code.components():
        seen, frontier, found = set(), [e["path"] for e in entries], set()
        for _ in range(depth + 1):
            nxt = []
            for path in frontier:
                if path in seen:
                    continue
                seen.add(path)
                src = text(path)
                found |= {canon[m.lower()] for m in rx.findall(src)}
                idents = set(re.findall(r"\b[A-Z][A-Za-z0-9_]+\b", src))
                nxt += [p for stem in idents & by_stem.keys() for p in by_stem[stem]]
            frontier = nxt
        if found:
            out[fqcn] = sorted(found)
    for t, ext in (catalog.types.items() if catalog else []):
        # no source: fall back to the deployed jar's string literals (jar-wide, so less precise than source)
        if ext.get("deployed") and t not in code.by_fqcn:
            found = {canon[m.lower()] for s in catalog.jar_strings(ext["deployed"]) for m in rx.findall(s)}
            if found:
                out[t] = sorted(found)
    return out


def _metadata_docs(meta):
    """Search entries: one per definition (keys, target, field names) and one per row of the other config tables."""
    docs, model, rows = [], meta["model"], meta["rows"]
    dt, st = model.get("definition_table"), model.get("structure_table")
    for table in model["tables"]:
        if table == st:
            continue
        pk = model["tables"][table]["pk"]
        for r in rows.table(table):
            ident = ":".join(str(r.get(c)) for c in pk) if pk else ""
            values = " ".join(str(v) for v in r.values() if v not in (None, "***") and not isinstance(v, bool))
            if table == dt:
                fields = metamod.structure_of(model, rows, r)
                target = r.get(model.get("definition_target")) if model.get("definition_target") else ""
                docs.append({"kind": "metadata", "ref": f"{table}:{r.get(model.get('definition_id'))}",
                             "title": f"{metamod.definition_label(model, r)} → {target or '?'}",
                             "body": clip(values, 2000) + " " + " ".join(f["name"] for f in fields), "doc": "metadata.md"})
            else:
                docs.append({"kind": "config", "ref": f"{table}:{ident}", "title": f"{table} {ident}".strip(),
                             "body": clip(values, 2000), "doc": "metadata.md"})
    return docs


def _store_facts(store, an, renderer, code, db_results, meta=None, cfg=None):
    store.reset_derived()
    flow = an.flow
    groups, comps, props, docs = [], [], [], []
    for gid, g in flow.groups.items():
        groups.append({"id": gid, "name": g["name"], "parent_id": g["parent_id"], "path": g["path"], "doc": renderer.group_file[gid],
                       "tags": ",".join(an.group_tags(gid, False)), "instance_id": g.get("instance_id"),
                       "version": json.dumps(g.get("version_control")) if g.get("version_control") else None})
        labels = " ".join(lab["text"] for lab in flow.labels if lab["group_id"] == gid)
        docs.append({"kind": "flow", "ref": gid, "title": g["path"], "body": f"{labels} {g.get('comments', '')} {' '.join(an.group_tags(gid))}",
                     "doc": renderer.group_file[gid]})
    for c in list(flow.components.values()) + list(flow.services.values()):
        doc = renderer.group_file.get(c["group_id"], "INDEX.md") if c["kind"] != "CONTROLLER_SERVICE" else "services.md"
        facts = an.key_facts(c, 400)
        comps.append({"id": c["id"], "kind": c["kind"], "name": c["name"], "type": c["type"], "group_id": c["group_id"],
                      "group_path": (flow.groups.get(c["group_id"]) or {}).get("path", "(controller)"), "state": c.get("state"),
                      "custom": int(an.is_custom(c)), "facts": facts, "auto_term": json.dumps(c.get("auto_terminated") or []),
                      "doc": renderer.comp_docs.get(c["id"], ""), "instance_id": c.get("instance_id")})
        body = []
        for f in an.props[c["id"]]:
            props.append({"component_id": c["id"], "name": f["name"], "display": f["display"], "value": f["value"], "resolved": f["resolved"],
                          "source": f["source"], "is_default": int(f["default"]), "kinds": ",".join(f["kinds"])})
            if not f["default"]:
                body.append(f"{f['display']}={f['resolved']}")
        if c["kind"] in ("PROCESSOR", "CONTROLLER_SERVICE", "INPUT_PORT", "OUTPUT_PORT"):
            docs.append({"kind": c["kind"].lower(), "ref": c["id"], "title": f"{c['name']} [{type_short(c['type'])}]",
                         "body": f"{c['type']} {facts} {c.get('comments', '')} " + " ".join(body), "doc": doc})
    store.insert("groups", groups)
    store.insert("components", comps)
    store.insert("properties", props)
    store.insert("connections", [{"id": c["id"], "source_id": c["source_id"], "dest_id": c["dest_id"], "relationships": ",".join(c["relationships"]),
                                  "group_id": c["group_id"], "name": c["name"]} for c in flow.connections])
    store.insert("resources", [{"kind": r["kind"], "value": r["value"], "component_id": r["component_id"], "property": r["property"],
                                "source": r["source"], "hardcoded": int(r["hardcoded"]), "raw": r["raw"]} for r in an.resources])
    store.insert("findings", [{"severity": f["severity"], "kind": f["kind"], "component_id": f["component_id"], "message": f["message"],
                               "location": f.get("location")} for f in an.findings])
    for fqcn, entries in code.components():
        for e in entries:
            store.insert("code_components", [{"fqcn": fqcn, "path": e["path"], "line": e["line"], "data": json.dumps(e["component"])}])
            comp = e["component"]
            docs.append({"kind": "code", "ref": fqcn, "title": fqcn,
                         "body": f"{comp.get('description', '')} {' '.join(comp.get('tags', []))} "
                                 + " ".join(f"{p.get('name')} {p.get('displayName') or ''}" for p in comp.get("properties") or []),
                         "doc": renderer.custom_file.get(fqcn, "custom-code/INDEX.md")})
    fqcn_of = {e["path"]: fqcn for fqcn, entries in code.components() for e in entries}
    for path, info in code.files.items():
        doc = renderer.custom_file.get(fqcn_of.get(path), "hardcoded.md")
        for m in info.get("messages") or []:  # a ticket's error text finds the code line that produces it
            docs.append({"kind": "message", "ref": f"{Path(path).name}:{m['line']}", "title": f"{m['level']} in {Path(path).name}:{m['line']}",
                         "body": m["text"], "doc": doc})
        if info.get("hardcoded") or info.get("tables") or info.get("spark"):
            docs.append({"kind": "file", "ref": path, "title": Path(path).name,
                         "body": " ".join(h["value"] for h in info.get("hardcoded", [])) + " " + " ".join(info.get("tables", []))
                         + " " + " ".join(f"spark-submit {x.get('class') or ''} {(x.get('class') or '').rsplit('.', 1)[-1]} "
                                          f"{x.get('app') or ''} {Path(x.get('app') or 'x').name} {x.get('name') or ''}"
                                          for x in info.get("spark") or []),
                         "doc": "hardcoded.md"})
    for d in db_results:
        store.set_meta(f"db_all_tables:{d['name']}", d.get("all_table_names") or [])
        for t in d.get("tables", []):
            doc = renderer.table_file.get((d["name"], t["table"]), f"db/{slugify(d['name'])}.md")
            store.insert("db_tables", [{"db": d["name"], "schema_name": t["schema"], "name": t["table"], "data": json.dumps(t, default=str),
                                        "doc": doc}])
            docs.append({"kind": "table", "ref": f"{d['name']}.{t['table']}", "title": t["table"],
                         "body": " ".join(c["name"] for c in t.get("columns", [])) + " " + (t.get("comment") or ""), "doc": doc})
    if meta:
        docs += _metadata_docs(meta)
    store.set_meta("metadata_model", meta["model"] if meta else None)
    store.set_meta("config_table_code", meta.get("code_map", {}) if meta else {})
    if cfg:
        docs += learnmod.search_docs(cfg)
    store.insert("search", docs)
    store.insert("record_schemas", [{"component_id": c["component_id"], "db": c["db"], "table_name": c["table"],
                                     "fields": json.dumps(c["fields"]), "translate": int(c["translate"])} for c in an.field_checks])


def _readme(cfg):
    return f"""# NiFi knowledge base (generated)

Start with [INDEX.md](INDEX.md). Generated by `nifikb` {__version__}; do not edit by hand — rebuild instead:

    python -m nifikb build            # incremental: no-op when nothing changed
    python -m nifikb build --force    # full rebuild
    python -m nifikb watch            # rebuild automatically when the flow / code changes

Config: `{cfg.get('_path', 'nifikb.toml')}`
"""


def clean(out):
    for d in GENERATED_DIRS:
        shutil.rmtree(Path(out) / d, ignore_errors=True)
