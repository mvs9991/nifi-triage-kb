"""Command line: build the knowledge base and answer cheap lookups from it.

  python -m nifikb build [--force] [--refresh-db]
  python -m nifikb watch [--interval 30]
  python -m nifikb status
  python -m nifikb search <words...>
  python -m nifikb show <name | id prefix | class>
  python -m nifikb trace <name | id prefix> [--up] [--depth N]
  python -m nifikb sql "SELECT ..." [--db name]
  python -m nifikb diagnose [headers...] [--file NAME] [--sample FILE] [--live] [--json]
  python -m nifikb issues [--kind K] [--contains TEXT]
  python -m nifikb learn add|list|show|for|retire|context   (team learnings in knowledge/)
  python -m nifikb logs [--component C] [--file F] [--uuid U] [--grep T] [--level L] [--since H]
  python -m nifikb provenance --file F | --uuid U | --component C      (NiFi REST API)
  python -m nifikb bulletins
  python -m nifikb late                         (feeds whose file is overdue, from the load-audit history)
  python -m nifikb ticket INC0012345 [--post]    (Jira / ServiceNow: investigate a ticket, draft the reply)
  python -m nifikb target --file F               (HDFS / S3 output + Parquet schema vs structure)
  python -m nifikb onboard proposal.toml [--sample f]   (validate config rows for a new feed)
  python -m nifikb compare --env uat [--key F]  (flow + config rows vs another environment)
  python -m nifikb versions [--group G]         (registry versions: deployed, live state, history)
  python -m nifikb report [--hours 24] [--out f.md] [--html f.html] [--send]
  python -m nifikb health [--threshold 80]      (NiFi API: queues, back-pressure, invalid processors, disks)
  python -m nifikb investigate [--file F] [--feed N] [--table T] [--error TEXT] [--headers ...] [--sample S] [--live]
  python -m nifikb doctor [--offline]
  python -m nifikb eval [--cases evals/cases.toml] [--agent "gemini -p"] [--save results.json]
  python -m nifikb web [--host H] [--port P]   (self-service page for colleagues)
  python -m nifikb mcp                      (MCP server on stdio for AI agents)
  python -m nifikb init [--nifi-home PATH]
"""
import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .build import build
from .config import PROJECT_DIR, load_config, write_template
from .render import tree_lines
from .store import Store


_OPEN_STORES = []  # closed by main(): the MCP server runs many commands in one long-lived process


def _store(cfg):
    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
    if not path.exists():
        sys.exit("Knowledge base not built yet: run `python -m nifikb build`")
    store = Store(str(path))
    _OPEN_STORES.append(store)
    return store


def _close_stores():
    while _OPEN_STORES:
        try:
            _OPEN_STORES.pop().db.close()
        except Exception:  # already closed
            pass


def resolve(store, ref):
    """Find components by id prefix, exact name, or name substring."""
    db = store.db
    rows = db.execute("SELECT * FROM components WHERE id LIKE ? OR lower(name)=lower(?)", (ref + "%", ref)).fetchall() if len(ref) >= 4 else []
    if not rows:
        rows = db.execute("SELECT * FROM components WHERE lower(name)=lower(?)", (ref,)).fetchall()
    if not rows:
        rows = db.execute("SELECT * FROM components WHERE lower(name) LIKE lower(?) AND kind!='FUNNEL'", (f"%{ref}%",)).fetchall()
    return rows


def cmd_build(cfg, args):
    res = build(cfg, force=args.force, refresh_db=args.refresh_db)
    return 0 if res["status"] in ("built", "up-to-date") else 1


def cmd_watch(cfg, args):
    print(f"Watching every {args.interval}s (Ctrl+C to stop)")
    while True:
        try:
            build(cfg, log=lambda m: print(time.strftime("%H:%M:%S"), m) if "up to date" not in m else None)
        except Exception as e:  # keep watching even if one build fails (e.g. flow file mid-write)
            print(time.strftime("%H:%M:%S"), f"build failed: {type(e).__name__}: {e}")
        time.sleep(args.interval)


def cmd_status(cfg, args):
    store = _store(cfg)
    built = store.get_meta("built_at")
    counts = {t: store.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("groups", "components", "connections", "findings", "code_components", "db_tables")}
    print(f"built: {time.strftime('%Y-%m-%d %H:%M', time.localtime(built)) if built else 'never'} from {store.get_meta('flow_file')}")
    print("  " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    for row in store.db.execute("SELECT severity, COUNT(*) n FROM findings GROUP BY severity"):
        print(f"  findings {row['severity']}: {row['n']}")
    return 0


def cmd_search(cfg, args):
    store = _store(cfg)
    rows = store.search(" ".join(args.terms), args.limit)
    if not rows:
        print("no matches")
    for r in rows:
        ref = r["ref"][:8] if r["kind"] in ("processor", "controller_service", "flow", "input_port", "output_port") else r["ref"]
        print(f"[{r['kind']}] {r['title']}  ({ref}) -> {r['doc']}\n    {r['snip']}")
    return 0


def cmd_show(cfg, args):
    store = _store(cfg)
    rows = resolve(store, args.ref)
    if not rows:
        code = store.db.execute("SELECT * FROM code_components WHERE fqcn=? OR fqcn LIKE ?", (args.ref, f"%.{args.ref}")).fetchall()
        group = store.db.execute("SELECT * FROM groups WHERE lower(name)=lower(?) OR id LIKE ?", (args.ref, args.ref + "%")).fetchall()
        target = (code and f"custom-code/{code[0]['fqcn'].rsplit('.', 1)[-1]}.md") or (group and group[0]["doc"])
        if target and (Path(cfg["output"]["dir"]) / target).exists():
            print((Path(cfg["output"]["dir"]) / target).read_text(encoding="utf-8"))
            return 0
        tables = store.db.execute("SELECT db, schema_name, name, doc FROM db_tables WHERE lower(name)=lower(?) "
                                  "OR lower(schema_name || '.' || name)=lower(?)", (args.ref, args.ref)).fetchall()
        for t in tables:
            path = Path(cfg["output"]["dir"]) / (t["doc"] or "")
            if path.is_file():
                print(_table_text(path.read_text(encoding="utf-8"), t["schema_name"], t["name"]))
        if tables:
            return 0
        print(f"nothing named '{args.ref}'")
        return 1
    if len(rows) > 1 and not any(r["id"].startswith(args.ref) for r in rows):
        print(f"{len(rows)} matches, be more specific (or use the id):")
        for r in rows[:30]:
            print(f"  {r['id'][:8]}  {r['name']} [{(r['type'] or r['kind']).rsplit('.', 1)[-1]}] in {r['group_path']}")
        return 1
    r = rows[0]
    print(r["doc"] or f"{r['name']} [{r['kind']}] `{r['id']}` in {r['group_path']}\n{r['facts']}")
    ins = store.db.execute("SELECT c.relationships, s.name, s.id FROM connections c JOIN components s ON s.id=c.source_id WHERE c.dest_id=?", (r["id"],)).fetchall()
    outs = store.db.execute("SELECT c.relationships, d.name, d.id FROM connections c JOIN components d ON d.id=c.dest_id WHERE c.source_id=?", (r["id"],)).fetchall()
    if not r["doc"]:
        for x in ins:
            print(f"  from {x['name']} ({x['id'][:8]}) [{x['relationships']}]")
        for x in outs:
            print(f"  to {x['name']} ({x['id'][:8]}) [{x['relationships']}]")
    return 0


def _table_text(doc, schema, name):
    """A per-table doc as is, or just that table's section of a whole-database doc."""
    heads = {f"## {schema}.{name}", f"## {name}"}
    lines = doc.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip() in heads), None)
    if start is None:
        return doc
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("## ", "Other tables in schema"))), len(lines))
    return "\n".join(lines[start:end]).rstrip()


def cmd_trace(cfg, args):
    store = _store(cfg)
    rows = resolve(store, args.ref)
    if len(rows) != 1 and not (rows and rows[0]["id"].startswith(args.ref)):
        print("need exactly one component; matches:" if rows else f"nothing named '{args.ref}'")
        for r in rows[:30]:
            print(f"  {r['id'][:8]}  {r['name']} in {r['group_path']}")
        return 1
    db = store.db
    group_names = {g["id"]: g["name"] for g in db.execute("SELECT id, name FROM groups")}
    comps = {c["id"]: dict(c, auto_terminated=json.loads(c["auto_term"] or "[]"), group_name=group_names.get(c["group_id"]))
             for c in db.execute("SELECT * FROM components")}
    edges = {}
    for c in db.execute("SELECT * FROM connections"):
        a, b = (c["dest_id"], c["source_id"]) if args.up else (c["source_id"], c["dest_id"])
        edges.setdefault(a, []).append((c["relationships"].split(",") if c["relationships"] else [], b))

    def get(cid):
        c = comps.get(cid)
        if c and args.show_groups and c.get("group_name"):
            c = dict(c, facts=f"{c['facts']} · PG {c['group_name']}".strip(" ·"))
        return c

    for line in tree_lines([rows[0]["id"]], get, lambda x: edges.get(x, []), max_depth=args.depth, upstream=args.up):
        print(line)
    return 0


def cmd_sql(cfg, args):
    from . import db as dbmod
    dbs = cfg.get("databases", [])
    if not dbs:
        print("no [[databases]] configured in nifikb.toml")
        return 1
    dcfg = next((d for d in dbs if d["name"] == args.db), None) if args.db else dbs[0]
    if not dcfg:
        print(f"unknown db '{args.db}'; configured: {', '.join(d['name'] for d in dbs)}")
        return 1
    try:
        cols, rows = dbmod.run_query(dcfg, args.query, args.max_rows)
    except dbmod.DbError as e:
        print(f"error: {e}")
        return 1
    widths = [min(40, max([len(str(c))] + [len(str(r[i])) for r in rows])) for i, c in enumerate(cols)]
    print(" | ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(v)[:40].ljust(w) for v, w in zip(r, widths)))
    print(f"({len(rows)} rows{', truncated' if len(rows) == args.max_rows else ''})")
    return 0


def _csv(value):
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def cmd_learn(cfg, args):
    from . import learnings as lm
    if args.action == "add":
        body = args.body
        if args.body_file:
            body = Path(args.body_file).read_text(encoding="utf-8")
        elif body in (None, "-") and not sys.stdin.isatty():
            body = sys.stdin.read()
        try:
            item, warnings = lm.add(cfg, args.title, body, kind=args.kind, tags=_csv(args.tags), applies_to=_csv(args.applies_to),
                                    ticket=args.ticket, author=args.author)
        except ValueError as e:
            print(f"error: {e}")
            return 1
        index_learning(cfg, item)
        print(f"saved {item['path']}")
        for w in warnings:
            print(f"note: {w}")
        return 0
    if args.action == "list":
        items = [i for i in lm.load_all(cfg, include_obsolete=args.all) if not args.tag or args.tag.lower() in i["tags"]]
        if args.json:
            print(json.dumps([{k: v for k, v in i.items() if k != "body"} for i in items], indent=2))
        else:
            for i in items:
                print(lm.format_item(i, full=False))
            if not items:
                print("no learnings yet - add one with: python -m nifikb learn add --title ... --body ...")
        return 0
    if args.action == "show":
        item = lm.get(cfg, args.id)
        print(lm.format_item(item) if item else f"no learning '{args.id}'")
        return 0 if item else 1
    if args.action == "for":
        items = lm.relevant(cfg, args.terms, limit=args.limit)
        for i in items:
            print(lm.format_item(i, full=args.full))
        if not items:
            print("no matching learnings")
        return 0
    if args.action == "retire":
        try:
            item = lm.retire(cfg, args.id, args.reason, args.replaced_by)
        except ValueError as e:
            print(f"error: {e}")
            return 1
        index_learning(cfg, item)
        print(f"retired {item['id']}")
        return 0
    if args.action == "suggest":
        items = lm.suggestions(cfg, _store(cfg), days=args.days, min_count=args.min_count)
        for line in lm.format_suggestions(items):
            print(f"- {line}")
        if not items:
            print("no recurring, unrecorded causes in the recent investigations")
        return 0
    if args.action == "context":
        path = lm.ensure(cfg) / "context.md"
        print(path.read_text(encoding="utf-8"))
        return 0
    return 1


def runtime_names(store):
    """Runtime (instance) id and flow id -> 'name (Type) in group' for everything in the flow."""
    try:
        rows = store.db.execute("SELECT id, instance_id, name, type, group_path FROM components").fetchall()
    except Exception:  # KB built by an older version: no instance ids yet
        rows = [dict(r, instance_id=None) for r in store.db.execute("SELECT id, name, type, group_path FROM components").fetchall()]
    out = {}
    for r in rows:
        label = f"{r['name']} `{r['id'][:8]}` in {r['group_path']}"
        out[r["id"]] = label
        if r["instance_id"]:
            out[r["instance_id"]] = label
    return out


def component_runtime_ids(store, ref):
    ids = []
    for r in resolve(store, ref):
        ids.append(r["id"])
        try:
            if r["instance_id"]:
                ids.append(r["instance_id"])
        except (IndexError, KeyError):
            pass
    return ids


def cmd_logs(cfg, args):
    from . import logs as lg
    store = _store(cfg)
    lg.index(cfg, store, log=lambda m: None)
    comp_ids = component_runtime_ids(store, args.component) if args.component else []
    if args.component and not comp_ids:
        print(f"no component '{args.component}' in the flow")
        return 1
    rows = lg.query(store, comp_ids, args.file, args.uuid, args.grep, args.level, args.since, args.limit)
    newest = store.db.execute("SELECT MAX(ts), COUNT(*) FROM log_events").fetchone()
    print(f"log index: {newest[1]} warning / error events, newest {newest[0] or '-'} (grouped by message shape, newest first)")
    print(lg.format_rows(rows, runtime_names(store)))
    return 0


def _api(cfg):
    from . import nifiapi
    a = nifiapi.settings(cfg)
    if not a:
        print("NiFi REST API not configured: add [nifi_api] url / username / password_env to nifikb.toml "
              "(meanwhile `python -m nifikb logs --file <name>` shows what the logs say)")
        return None
    return nifiapi.Client(a)


def cmd_provenance(cfg, args):
    from . import nifiapi
    if not (args.file or args.uuid or args.component):
        print("give --file <name>, --uuid <FlowFile uuid> or --component <processor>")
        return 1
    client = _api(cfg)
    if not client:
        return 1
    store = _store(cfg)
    names = runtime_names(store)
    comp = None
    if args.component:
        ids = component_runtime_ids(store, args.component)
        if not ids:
            print(f"no component '{args.component}' in the flow")
            return 1
        comp = ids[-1]  # the runtime (instance) id when known: that is what provenance records
    try:
        flows = nifiapi.journey(client, args.file, args.uuid, comp, max_results=args.max)
    except nifiapi.NiFiApiError as e:
        print(f"error: {e}")
        return 1
    print(nifiapi.format_journey(flows, names, args.file or args.uuid or args.component))
    return 0


def cmd_bulletins(cfg, args):
    from . import nifiapi
    client = _api(cfg)
    if not client:
        return 1
    store = _store(cfg)
    try:
        print(nifiapi.format_bulletins(client.bulletins(args.limit), runtime_names(store)))
    except nifiapi.NiFiApiError as e:
        print(f"error: {e}")
        return 1
    return 0


def cmd_investigate(cfg, args):
    from . import diagnose as dg, investigate as inv
    if not (args.file or args.feed or args.table or args.error):
        print("give at least one of --file, --feed, --table, --error")
        return 1
    store = _store(cfg)
    report = inv.investigate(cfg, store, runtime_names(store), file=args.file, feed=args.feed, table=args.table,
                             error_text=args.error, headers=dg.split_headers(args.headers), sample_path=args.sample,
                             live=args.live, since_hours=args.since)
    print(inv.format_report(report))
    return 0


def cmd_health(cfg, args):
    from . import nifiapi
    client = _api(cfg)
    if not client:
        return 1
    store = _store(cfg)
    try:
        h = nifiapi.health(client, bp_threshold=args.threshold, versioned=store.versioned_groups())
    except nifiapi.NiFiApiError as e:
        print(f"error: {e}")
        return 1
    print(nifiapi.format_health(h, runtime_names(store)))
    return 0


def cmd_audit(cfg, args):
    from . import audit as auditmod
    store = _store(cfg)
    model = store.get_meta("audit_model")
    if not model:
        print("no load-audit table: add [audit] (db, table) to nifikb.toml and run build")
        return 1
    try:
        rows = auditmod.lookup(cfg, model, file=args.file, link_ids=[args.definition] if args.definition else (), limit=args.limit)
    except Exception as e:
        print(f"error: {e}")
        return 1
    print(f"load audit table {model['table']} (file column {model['file_column']}, status {model.get('status_column')}, "
          f"time {model.get('time_column')}):")
    print(auditmod.format_rows(model, rows))
    return 0


def cmd_report(cfg, args):
    from . import report as rp
    store = _store(cfg)
    r = rp.build_report(cfg, store, runtime_names(store), hours=args.hours)
    md = rp.to_markdown(r)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    if args.html:
        Path(args.html).write_text(rp.to_html(r), encoding="utf-8")
    if not args.out and not args.html:
        print(md)
    if args.send:
        try:
            done = rp.send(cfg, r)
        except Exception as e:  # SMTP / webhook failures must be visible
            print(f"error sending the report: {type(e).__name__}: {e}")
            return 1
        print("; ".join(done) if done else "nothing to send: set [report] email_to and / or webhook_url in nifikb.toml")
    return 0


def cmd_eval(cfg, args):
    from . import evals
    path = Path(args.cases or Path(cfg["_path"]).parent / "evals" / "cases.toml")
    if not path.exists():
        print(f"no cases file {path} - copy evals/cases.example.toml to evals/cases.toml and add past tickets")
        return 1
    store = _store(cfg)
    results = evals.run(cfg, store, runtime_names(store), evals.load_cases(path), top=args.top, agent=args.agent)
    print(evals.summary(results))
    if args.save:
        evals.save(results, args.save)
    return 0 if all(r["tools_ok"] and r.get("agent_ok", True) for r in results) else 2


def cmd_versions(cfg, args):
    import datetime as dt
    from . import nifiapi
    store = _store(cfg)
    rows = store.db.execute("SELECT id, instance_id, path, version FROM groups WHERE version IS NOT NULL ORDER BY path").fetchall()
    if args.group:
        rows = [r for r in rows if args.group.lower() in r["path"].lower() or r["id"].startswith(args.group)]
    if not rows:
        print("no version-controlled process groups" + (f" matching '{args.group}'" if args.group else ""))
        return 1
    api = nifiapi.Client(nifiapi.settings(cfg)) if nifiapi.settings(cfg) else None
    reg = nifiapi.RegistryClient(nifiapi.registry_settings(cfg)) if nifiapi.registry_settings(cfg) else None
    for r in rows:
        vc = json.loads(r["version"])
        print(f"{r['path']}: registry flow {vc.get('flow_name') or vc.get('flow')} (bucket {vc.get('bucket')}), deployed v{vc.get('version')}")
        if api:
            try:
                st = api.version_state(r["instance_id"] or r["id"])
                print(f"  live state: {st.get('state')}" + (f" - {st['stateExplanation']}" if st.get("stateExplanation") else ""))
            except nifiapi.NiFiApiError as e:
                print(f"  live state not available: {e}")
        if reg:
            try:
                for v in reg.versions(vc.get("bucket_id") or vc.get("bucket"), vc.get("flow"))[:args.limit]:
                    when = dt.datetime.fromtimestamp((v.get("timestamp") or 0) / 1000).strftime("%Y-%m-%d %H:%M") if v.get("timestamp") else "?"
                    mark = "  <- deployed" if str(v.get("version")) == str(vc.get("version")) else ""
                    print(f"  v{v.get('version')}  {when}  {v.get('author') or '?'}: {v.get('comments') or ''}{mark}")
            except nifiapi.NiFiApiError as e:
                print(f"  registry history not available: {e}")
    if not reg:
        print("(add [registry] url to nifikb.toml for the version history with authors and comments)")
    return 0


def cmd_compare(cfg, args):
    """Environment comparison: this configuration's flow / config tables vs another environment's."""
    from . import compare
    from .build import find_flow_file
    other = {}
    if args.env:
        try:
            other = compare.environment(cfg, args.env)
        except ValueError as e:
            print(e)
            return 2
    right_flow = args.flow or other.get("flow_file")
    right_db = args.db or other.get("db")
    left_db = args.base_db or (cfg.get("metadata") or {}).get("db")
    name = args.env or "other"
    if not right_flow and not right_db:
        print("nothing to compare: give --env (an [environments.<name>] section) or --flow FILE and / or --db NAME")
        return 2
    if right_flow and args.what in ("all", "flow"):
        print(f"## Flow: this environment vs {name} ({right_flow})")
        try:
            lines = compare.compare_flows(cfg, find_flow_file(cfg), right_flow, "here", name, limit=args.limit)
        except (OSError, ValueError) as e:
            lines = [f"cannot read {right_flow}: {e}"]
        print("\n".join(f"- {line}" for line in lines) if lines else "- no differences")
        print()
    if right_db and args.what in ("all", "config"):
        print(f"## Config tables: {left_db} vs {right_db}" + (f" (definition matching '{args.key}')" if args.key else ""))
        try:
            lines = compare.compare_config(cfg, _store(cfg), left_db, right_db, args.key, "here", name)
        except Exception as e:  # driver / connection errors: report, do not crash
            lines = [f"cannot read the config tables: {type(e).__name__}: {e}"]
        print("\n".join(f"- {line}" for line in lines[:args.limit]))
        if len(lines) > args.limit:
            print(f"- … {len(lines) - args.limit} more")
    return 0


def cmd_onboard(cfg, args):
    """New-feed validator: proposed config rows vs the config tables, existing rows, target table and a sample."""
    from . import onboard
    try:
        proposal = onboard.load_proposal(args.proposal)
    except (OSError, ValueError) as e:
        print(f"cannot read the proposal {args.proposal}: {e}")
        return 2
    if args.sample:
        proposal["sample"] = args.sample
    if args.example:
        proposal["example_file"] = args.example
    res = onboard.validate(cfg, _store(cfg), proposal, live=args.live)
    if args.json:
        print(json.dumps(res, indent=1, default=str))
    else:
        print(onboard.format_report(res))
    return 1 if res.get("error") or any(i[0] == "error" for i in res.get("issues", [])) else 0


def cmd_target(cfg, args):
    """Target side: what the load wrote to the definition's HDFS / S3 location, and its Parquet schema vs the structure."""
    from . import diagnose as dg, target
    store = _store(cfg)
    since = time.time() - args.hours * 3600 if args.hours else None
    if args.location:
        fields = []
        if args.key:
            diag = dg.metadata_diagnosis(cfg, store, args.key)
            fields = next((d["fields"] for d in diag.get("definitions") or []), [])
        try:
            print(target.format_check(target.check(cfg, args.location, fields, file=args.file, since=since), args.limit))
        except target.TargetError as e:
            print(e)
            return 1
        return 0
    key = args.key or args.file
    if not key:
        print("give --file / --key (a file, feed or table name) or --location")
        return 2
    diag = dg.metadata_diagnosis(cfg, store, key)
    if diag.get("error"):
        print(diag["error"])
        return 1
    model = store.get_meta("metadata_model")
    results = target.check_diagnosis(cfg, model, diag, file=args.file, since=since)
    if not results:
        print(f"no location for '{key}': the definition has no location column / file target"
              + ("" if target.settings(cfg).get("location_template") else " - set [targets] location_template, e.g. \"s3://lake/raw/{table}/\""))
        return 1
    for d, res in results:
        print(f"## {d['label']} ({model['definition_table']}:{d['id']})")
        print(target.format_check(res, args.limit))
    return 1 if any(i[0] == "error" for _, r in results for i in r["issues"]) else 0


def cmd_ticket(cfg, args):
    """Read a Jira / ServiceNow ticket, investigate what it names, draft a reply (posted only with --post)."""
    import shutil
    from . import investigate as inv, tickets
    try:
        t = tickets.settings(cfg)
    except tickets.TicketError as e:
        print(e)
        return 2
    if not t:
        print("ticket system not configured: add [tickets] kind / url / username / token_env to nifikb.toml")
        return 2
    store = _store(cfg)
    cl = tickets.client(t)
    try:
        ticket = cl.fetch(args.id)
    except tickets.TicketError as e:
        print(f"error: {e}")
        return 1
    facts = tickets.extract(ticket, store, store.get_meta("metadata_model"))
    tmp, samples = (None, []) if args.no_attachments else tickets.fetch_samples(cl, ticket)
    try:
        if not (facts["files"] or facts["feeds"] or facts["tables"] or facts["error"]):
            print(f"# {ticket['id']}: {ticket['title']}")
            print("no file, feed, table or error text found in the ticket - ask the reporter for the file name and the error")
            return 1
        report = inv.investigate(cfg, store, runtime_names(store), file=facts["files"][0] if facts["files"] else None,
                                 feed=facts["feeds"][0] if facts["feeds"] and not facts["files"] else None,
                                 table=facts["tables"][0] if facts["tables"] else None, error_text=facts["error"],
                                 headers=facts["headers"], sample_path=samples[0] if samples else None, live=args.live)
        print(f"# {ticket['id']}: {ticket['title']}" + (f" [{ticket['status']}]" if ticket.get("status") else ""))
        print("extracted: " + "; ".join(f"{k}={v}" for k, v in facts.items() if v)
              + (f"; sample attachment={Path(samples[0]).name}" if samples else ""))
        print()
        print(inv.format_report(report))
        built = store.get_meta("built_at")
        built = time.strftime("%Y-%m-%d %H:%M", time.localtime(built)) if built else None
        draft = tickets.draft_comment(ticket, facts, report, built)
        print()
        print("## Draft reply" + (" (posting)" if args.post else " (not posted - run again with --post to add it to the ticket)"))
        print(draft)
        if args.post:
            try:
                cl.post(ticket, draft)
                print(f"posted to {ticket['id']}")
            except tickets.TicketError as e:
                print(f"posting failed: {e}")
                return 1
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def cmd_late(cfg, args):
    """Feeds whose next file is overdue, judged from their load-audit arrival history."""
    from . import late
    store = _store(cfg)
    try:
        items = late.late_files(cfg, store, days=args.days, min_history=args.min_history)
    except Exception as e:  # DB down, no time column: say so
        print(f"late-file check not available: {e}")
        return 1
    print("\n".join(f"- {line}" for line in late.format_items(items)))
    return 1 if items else 0


def cmd_doctor(cfg, args):
    from . import doctor
    text, fails = doctor.report(doctor.run(cfg, offline=args.offline))
    print(text)
    return 1 if fails else 0


def index_learning(cfg, item):
    """Make a new learning searchable at once (the next build re-indexes everything anyway)."""
    from . import learnings as lm
    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
    if not path.exists():
        return
    store = Store(str(path))
    try:
        store.db.execute("DELETE FROM search WHERE ref = ?", (item["id"],))
        store.insert("search", [d for d in lm.search_docs(cfg) if d["ref"] == item["id"]])
        store.set_meta("build_sig", None)  # learnings changed: the next build re-indexes everything
    finally:
        store.close()


def cmd_issues(cfg, args):
    store = _store(cfg)
    sql, params = "SELECT severity, kind, component_id, location, message FROM findings WHERE 1=1", []
    for col in ("kind", "severity"):
        if getattr(args, col):
            sql += f" AND {col} = ?"
            params.append(getattr(args, col))
    if args.contains:
        sql += " AND message LIKE ?"
        params.append(f"%{args.contains}%")
    sql += " ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'high' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END, kind LIMIT ?"
    params.append(args.limit)
    counts = store.db.execute("SELECT severity, kind, COUNT(*) n FROM findings GROUP BY severity, kind ORDER BY n DESC").fetchall()
    print("counts: " + (", ".join(f"{r['kind']} {r['severity']} x{r['n']}" for r in counts) or "none"))
    rows = store.db.execute(sql, params).fetchall()
    for r in rows:
        print(f"[{r['severity']}] {r['kind']} {(r['component_id'] or '')[:8] or r['location'] or ''}: {r['message']}")
    if not rows:
        print("no matching findings")
    return 0


def cmd_diagnose(cfg, args):
    """Support triage: headers / sample payload (+ optional file, table, feed or API name) -> what the flow and the
    metadata expect, and what does not match."""
    from . import diagnose as dg
    store = _store(cfg)
    headers = dg.split_headers(args.fields)
    if args.key:
        result = dg.metadata_diagnosis(cfg, store, args.key, headers, live=args.live, sample_path=args.sample)
    elif headers or args.sample:
        headers += dg.headers_from_sample(args.sample) if args.sample else []
        result = dg.record_diagnosis(store, headers, cfg)
    else:
        print("give header names, --sample <file>, and/or --file/--table/--feed <name>")
        return 1
    print(json.dumps(result, indent=2, default=str) if args.json else dg.format_text(result))
    if result.get("error") or (result["mode"] == "metadata" and not result.get("matches")):
        return 1
    return 0


def cmd_init(args):
    path = Path(args.config or PROJECT_DIR / "nifikb.toml")
    write_template(path, args.nifi_home)
    print(f"wrote {path}")
    return 0


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    p = argparse.ArgumentParser(prog="nifikb", description=f"NiFi knowledge base {__version__}")
    p.add_argument("--config", help="path to nifikb.toml (default: ./nifikb.toml, $NIFIKB_CONFIG, or next to the package)")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build / refresh the knowledge base (incremental)")
    b.add_argument("--force", action="store_true")
    b.add_argument("--refresh-db", action="store_true", help="re-read database schemas now")
    w = sub.add_parser("watch", help="rebuild whenever the flow, NARs, code or config change")
    w.add_argument("--interval", type=int, default=30)
    sub.add_parser("status")
    s = sub.add_parser("search", help="full-text search over flows, processors, properties, code, tables")
    s.add_argument("terms", nargs="+")
    s.add_argument("--limit", type=int, default=15)
    sh = sub.add_parser("show", help="details of one component / group / custom class")
    sh.add_argument("ref")
    t = sub.add_parser("trace", help="downstream (default) or upstream (--up) path from a component, across groups")
    t.add_argument("ref")
    t.add_argument("--up", action="store_true")
    t.add_argument("--depth", type=int, default=40)
    t.add_argument("--show-groups", action="store_true", help="append the process group of every node")
    q = sub.add_parser("sql", help="read-only query against a configured database")
    q.add_argument("query")
    q.add_argument("--db")
    q.add_argument("--max-rows", type=int, default=100)
    d = sub.add_parser("diagnose", help="match a set of incoming field/header names to the record-ingestion "
                                        "processor they belong to and report mismatches against its target table")
    d.add_argument("fields", nargs="*", help="incoming field/header names, space- or comma-separated")
    d.add_argument("--file", "--table", "--feed", "--key", dest="key",
                   help="file name, target table, feed or API name to look up in the metadata config tables")
    d.add_argument("--sample", help="sample file to take the headers from (CSV/delimited header line, JSON or JSON lines)")
    d.add_argument("--live", action="store_true", help="read the metadata tables now instead of the last build's snapshot")
    d.add_argument("--json", action="store_true", help="machine-readable output (for agents / scripts)")
    iss = sub.add_parser("issues", help="list static findings, filtered")
    iss.add_argument("--kind")
    iss.add_argument("--severity")
    iss.add_argument("--contains", help="substring of the message")
    iss.add_argument("--limit", type=int, default=100)
    from .learnings import KINDS
    lr = sub.add_parser("learn", help="team learnings kept in knowledge/: add, list, show, for, retire, context")
    lsub = lr.add_subparsers(dest="action", required=True)
    la = lsub.add_parser("add", help="record what was learned (symptom, cause, fix, how to spot it)")
    la.add_argument("--title", required=True)
    la.add_argument("--body", help="markdown text; '-' or omitted reads stdin")
    la.add_argument("--body-file")
    la.add_argument("--kind", default="fix", choices=KINDS)
    la.add_argument("--tags", help="comma separated")
    la.add_argument("--applies-to", help="comma separated: file names / patterns, tables, feeds, processor names or ids, config rows")
    la.add_argument("--ticket")
    la.add_argument("--author", help="default: $NIFIKB_AUTHOR or the OS user")
    ll = lsub.add_parser("list")
    ll.add_argument("--tag")
    ll.add_argument("--all", action="store_true", help="include retired ones")
    ll.add_argument("--json", action="store_true")
    ls = lsub.add_parser("show")
    ls.add_argument("id")
    lf = lsub.add_parser("for", help="learnings relevant to file names, tables, feeds, processors ...")
    lf.add_argument("terms", nargs="+")
    lf.add_argument("--limit", type=int, default=5)
    lf.add_argument("--full", action="store_true")
    lre = lsub.add_parser("retire", help="mark a learning obsolete (kept for history)")
    lre.add_argument("id")
    lre.add_argument("--reason")
    lre.add_argument("--replaced-by")
    lsub.add_parser("context", help="print knowledge/context.md (creates the template)")
    lsg = lsub.add_parser("suggest", help="causes that keep coming back in investigations and have no learning yet")
    lsg.add_argument("--days", type=int, default=30)
    lsg.add_argument("--min-count", type=int, default=3)
    lg = sub.add_parser("logs", help="warnings / errors from nifi-app*.log and nifi-bootstrap*.log (indexed incrementally)")
    lg.add_argument("--component", help="processor / service name or id")
    lg.add_argument("--file", help="file name (FlowFile name or anywhere in the message)")
    lg.add_argument("--uuid", help="FlowFile uuid")
    lg.add_argument("--grep", help="text in the message or cause")
    lg.add_argument("--level", choices=["WARN", "ERROR", "FATAL", "LIFECYCLE"])
    lg.add_argument("--since", type=float, help="hours before the newest indexed event")
    lg.add_argument("--limit", type=int, default=30)
    pv = sub.add_parser("provenance", help="where FlowFiles went / were dropped (NiFi REST API, [nifi_api])")
    pv.add_argument("--file", help="file name (filename attribute)")
    pv.add_argument("--uuid", help="FlowFile uuid")
    pv.add_argument("--component", help="processor name or id: its recent events")
    pv.add_argument("--max", type=int, default=500)
    vs = sub.add_parser("versions", help="version-controlled process groups: deployed version, live state, registry history")
    vs.add_argument("--group", help="process group name / path / id prefix")
    vs.add_argument("--limit", type=int, default=10)
    cp = sub.add_parser("compare", help="environment comparison: flow (processors, properties, parameters) and config rows vs UAT / PROD")
    cp.add_argument("--env", help="an [environments.<name>] section of nifikb.toml (flow_file, db)")
    cp.add_argument("--flow", help="the other environment's flow.json.gz / flow.xml.gz")
    cp.add_argument("--db", help="the other environment's [[databases]] name (config tables)")
    cp.add_argument("--base-db", help="this environment's config db (default: [metadata] db)")
    cp.add_argument("--key", help="only the definition matching this file / feed / table")
    cp.add_argument("--what", choices=["all", "flow", "config"], default="all")
    cp.add_argument("--limit", type=int, default=300)
    ob = sub.add_parser("onboard", help="check proposed config rows for a NEW feed before they are inserted (TOML / JSON proposal)")
    ob.add_argument("proposal", help="proposal file: [definition], [[structure]] or structure_csv, [[rows.<TABLE>]] - see README")
    ob.add_argument("--sample", help="sample file of the new feed")
    ob.add_argument("--example", help="a real file name the definition must match")
    ob.add_argument("--live", action="store_true", help="compare with the config rows now instead of the KB snapshot")
    ob.add_argument("--json", action="store_true")
    tg = sub.add_parser("target", help="what a load wrote to HDFS / S3: files, newest output, Parquet schema vs the structure rows")
    tg.add_argument("--file", help="input file name (its definition, and outputs named like it)")
    tg.add_argument("--key", help="feed / table / definition name")
    tg.add_argument("--location", help="list this location directly (s3://…, hdfs://…, /path)")
    tg.add_argument("--hours", type=float, help="warn when nothing was written in the last N hours")
    tg.add_argument("--limit", type=int, default=10)
    tk = sub.add_parser("ticket", help="Jira / ServiceNow ticket: extract file / feed / error, investigate, draft a reply")
    tk.add_argument("id", help="PROJ-123 or INC0012345")
    tk.add_argument("--post", action="store_true", help="add the draft to the ticket (Jira comment / ServiceNow work note)")
    tk.add_argument("--live", action="store_true", help="read the config rows now")
    tk.add_argument("--no-attachments", action="store_true", help="do not download CSV / JSON attachments as samples")
    lt = sub.add_parser("late", help="late / missing files: feeds whose next file is overdue (learned from the load audit)")
    lt.add_argument("--days", type=int, default=35, help="history window (default 35 days)")
    lt.add_argument("--min-history", type=int, default=5, help="arrivals needed before a feed is judged")
    rpt = sub.add_parser("report", help="daily health report: new errors, crashes, failed loads, config / flow changes, drift")
    rpt.add_argument("--hours", type=float, default=24)
    rpt.add_argument("--out", help="write markdown to this file")
    rpt.add_argument("--html", help="write HTML to this file")
    rpt.add_argument("--send", action="store_true", help="e-mail / post it as configured in [report]")
    au = sub.add_parser("audit", help="load-audit rows (status, error, rows, time) of a file or definition ([audit])")
    au.add_argument("--file")
    au.add_argument("--definition", help="definition id (e.g. OBJ_ID)")
    au.add_argument("--limit", type=int, default=10)
    he = sub.add_parser("health", help="live flow health: back-pressure, stuck queues, invalid processors, services, disks (NiFi API)")
    he.add_argument("--threshold", type=float, default=80.0, help="back-pressure warning level in %% (default 80)")
    bl = sub.add_parser("bulletins", help="current NiFi bulletins (errors shown in the UI, last 5 minutes)")
    bl.add_argument("--limit", type=int, default=50)
    iv = sub.add_parser("investigate", help="one-call ticket investigation: metadata + provenance + logs + code + learnings, ranked")
    iv.add_argument("--file", help="file name from the ticket")
    iv.add_argument("--feed", help="feed / API name")
    iv.add_argument("--table", help="target table")
    iv.add_argument("--error", help="error text from the ticket")
    iv.add_argument("--headers", nargs="*", help="headers / field names sent, in file order")
    iv.add_argument("--sample", help="sample file (CSV / JSON)")
    iv.add_argument("--live", action="store_true", help="read the config rows now")
    iv.add_argument("--since", type=float, default=72, help="hours of processor log errors to include (default 72)")
    dr = sub.add_parser("doctor", help="check the installation: config, NiFi files, repos, databases, metadata, agents, KB freshness")
    dr.add_argument("--offline", action="store_true", help="skip database connections")
    ev = sub.add_parser("eval", help="replay past tickets with known causes: do the tools (and the model) find them?")
    ev.add_argument("--cases", help="default evals/cases.toml")
    ev.add_argument("--top", type=int, help="the true cause must be within the top N ranked causes (default: per case, 3)")
    ev.add_argument("--agent", help='model CLI to answer from the report, e.g. "gemini -p" (prompt on stdin, or {prompt_file})')
    ev.add_argument("--save", help="write results as JSON")
    wb = sub.add_parser("web", help="self-service web page for colleagues: investigate, daily report, health, search, learnings")
    wb.add_argument("--host", help="default [web] host or 127.0.0.1")
    wb.add_argument("--port", type=int, help="default [web] port or 8765")
    sub.add_parser("mcp", help="run the MCP server on stdio (for Claude Code, Gemini CLI and other MCP clients)")
    i = sub.add_parser("init", help="write a starter nifikb.toml")
    i.add_argument("--nifi-home", default="D:/Sanjay/nifi-1.27.0")
    args = p.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "web":
        from .web import serve as serve_web
        serve_web(load_config(args.config), args.host, args.port)
        return 0
    if args.cmd == "mcp":
        from .mcp import serve
        for stream in (sys.stdin, sys.stdout):
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, ValueError):
                pass
        serve(args.config)
        return 0
    cfg = load_config(args.config)
    try:
        return {"build": cmd_build, "watch": cmd_watch, "status": cmd_status, "search": cmd_search, "show": cmd_show,
                "trace": cmd_trace, "sql": cmd_sql, "diagnose": cmd_diagnose, "issues": cmd_issues, "learn": cmd_learn,
                "doctor": cmd_doctor, "logs": cmd_logs,
                "provenance": cmd_provenance, "bulletins": cmd_bulletins, "investigate": cmd_investigate,
                "health": cmd_health, "audit": cmd_audit, "report": cmd_report, "eval": cmd_eval,
                "versions": cmd_versions, "compare": cmd_compare,
                "onboard": cmd_onboard, "target": cmd_target,
                "ticket": cmd_ticket, "late": cmd_late}[args.cmd](cfg, args)
    finally:
        _close_stores()
