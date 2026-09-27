"""`nifikb doctor`: one command that checks an installation end to end (first thing to run on a new machine)."""
import json
import shutil
import sys
import time
from pathlib import Path

from .config import PROJECT_DIR

OK, WARN, FAIL = "OK  ", "WARN", "FAIL"


def run(cfg, offline=False):
    checks = []

    def add(status, label, detail=""):
        checks.append((status, label, detail))

    add(OK if sys.version_info >= (3, 11) else FAIL, "python", f"{sys.version.split()[0]} ({sys.executable})"
        + ("" if sys.version_info >= (3, 11) else " - needs 3.11+"))
    add(OK, "config", cfg["_path"])
    _nifi(cfg, add)
    _code(cfg, add)
    _databases(cfg, add, offline)
    _metadata(cfg, add)
    _kb(cfg, add)
    _audit(cfg, add)
    _logs(cfg, add)
    _nifi_api(cfg, add, offline)
    _optional(cfg, add)
    _agents(cfg, add)
    _knowledge(cfg, add)
    return checks


def _nifi(cfg, add):
    from .build import find_flow_file
    from .catalog import find_nars
    try:
        flow = find_flow_file(cfg)
        add(OK, "flow file", f"{flow} ({flow.stat().st_size / 1e6:.1f} MB, modified {time.strftime('%Y-%m-%d %H:%M', time.localtime(flow.stat().st_mtime))})")
    except FileNotFoundError as e:
        add(FAIL, "flow file", str(e))
    home = cfg["nifi"].get("home")
    dirs = [Path(home) / d for d in ("lib", "extensions")] if home else []
    for d in cfg["nifi"].get("extra_nar_dirs", []):
        add(OK if Path(d).is_dir() else FAIL, "extra NAR dir", d)
        dirs.append(Path(d))
    nars = find_nars(dirs)
    add(OK if nars else WARN, "NARs", f"{len(nars)} found" + ("" if nars else " - no property defaults / docs; set [nifi] home or extra_nar_dirs"))


def _code(cfg, add):
    repos = cfg["code"].get("repos", [])
    if not repos:
        add(WARN, "code repos", "none configured - custom processors will only have NAR docs (set [code] repos to the Bitbucket clones)")
    for r in repos:
        p = Path(r)
        if not p.exists():
            add(FAIL, "code repo", f"{r} does not exist")
            continue
        java = sum(1 for _ in p.rglob("*.java"))
        poms = sum(1 for _ in p.rglob("pom.xml"))
        svc = sum(1 for _ in p.rglob("META-INF/services/org.apache.nifi.*"))
        other = sum(1 for ext in ("*.py", "*.groovy", "*.scala", "*.sh", "*.sql") for _ in p.rglob(ext))
        add(OK, "code repo", f"{r}: {java} Java, {poms} pom.xml, {svc} NiFi service registrations, {other} scripts/other")


def _databases(cfg, add, offline):
    from . import db as dbmod
    import os
    if not cfg.get("databases"):
        add(WARN, "databases", "none configured - no table schemas, no metadata checks (add a [[databases]] block)")
    for d in cfg.get("databases", []):
        kind = (d.get("kind") or "mariadb").lower()
        label = f"database {d['name']}"
        driver = {"mariadb": "pymysql", "mysql": "pymysql", "postgres": "pg8000", "postgresql": "pg8000"}.get(kind)
        if driver:
            try:
                __import__(driver)
            except ImportError:
                if kind.startswith("postgres"):
                    try:
                        __import__("psycopg2")
                        driver = None
                    except ImportError:
                        pass
                if driver:
                    add(FAIL, label, f"driver missing: pip install {driver}")
                    continue
        if d.get("password_env") and not os.environ.get(d["password_env"]) and not d.get("password_file"):
            add(WARN, label, f"environment variable {d['password_env']} is not set in this shell")
        if d.get("password_file"):
            pf = Path(d["password_file"])
            if not pf.is_file():
                add(FAIL, label, f"password_file {pf} not found")
                continue
            if os.name == "posix" and pf.stat().st_mode & 0o077:
                add(WARN, label, f"password_file {pf} is readable by others: chmod 600 {pf}")
        if offline:
            continue
        try:
            conn, dialect = dbmod.connect(d)
        except dbmod.DbError as e:
            add(FAIL, label, str(e))
            continue
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchall()
            detail = f"{kind} connected as {d.get('user') or '-'}"
            status = OK
            if dialect == "mysql":
                cur.execute("SHOW GRANTS")
                grants = " ".join(g for g in (str(r[0]) for r in cur.fetchall()) if _grant_covers(g, d.get("database"))).upper()
                if any(w in grants for w in ("ALL PRIVILEGES", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER")):
                    status, detail = WARN, detail + " - this user can WRITE; use a SELECT-only user (sessions are read-only anyway)"
                else:
                    detail += ", read-only grants"
            add(status, label, detail)
        except Exception as e:  # driver specific
            add(FAIL, label, f"{type(e).__name__}: {e}")
        finally:
            conn.close()


def _grant_covers(grant, database):
    """Does a MySQL/MariaDB GRANT line apply to the configured database (or to all databases)?"""
    import fnmatch
    import re
    m = re.search(r"\bON\s+(?:TABLE\s+)?`?([^`.\s]+|\*)`?\.", grant, re.I)
    if not m:
        return False
    target = m.group(1)
    if target == "*":
        return True
    pattern = target.replace("\\_", "\0").replace("%", "*").replace("_", "?").replace("\0", "_")
    return bool(database) and fnmatch.fnmatch(database.lower(), pattern.lower())


def _metadata(cfg, add):
    from . import metadata as metamod
    try:
        m = metamod.settings(cfg)
    except ValueError as e:
        add(FAIL, "metadata", str(e))
        return
    if not m:
        add(WARN, "metadata", "[metadata] not configured - no OBJ_* definition / structure checks and no `diagnose --file`")
        return
    model = _store_meta(cfg, "metadata_model")
    if not model:
        add(WARN, "metadata", f"configured (db '{m['db']}') - run build to detect the config tables")
        return
    missing = [r for r in ("definition_table", "structure_table") if not model.get(r)]
    detail = (f"{len(model['tables'])} config tables, definition {model.get('definition_table')}, structure {model.get('structure_table')}, "
              f"{len(model['relations'])} relations")
    if missing:
        add(WARN, "metadata", detail + f" - not detected: {', '.join(missing)} (set them in [metadata])")
    elif model.get("guessed"):
        add(OK, "metadata", detail + f" - auto-detected {', '.join(model['guessed'])}: confirm in kb/metadata.md")
    else:
        add(OK, "metadata", detail)


def _store_meta(cfg, key):
    import sqlite3
    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
    if not path.exists():
        return None
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None
    except sqlite3.Error:
        return None
    finally:
        db.close()


def _kb(cfg, add):
    from .build import find_flow_file
    built = _store_meta(cfg, "built_at")
    if not built:
        add(FAIL, "knowledge base", "not built yet: python -m nifikb build")
        return
    age_h = (time.time() - built) / 3600
    detail = f"built {time.strftime('%Y-%m-%d %H:%M', time.localtime(built))} ({age_h:.1f} h ago)"
    try:
        stale = find_flow_file(cfg).stat().st_mtime > built
    except FileNotFoundError:
        stale = False
    if stale:
        add(WARN, "knowledge base", detail + " - the flow changed since: run build (or schedule it)")
    else:
        add(OK if age_h < 48 else WARN, "knowledge base", detail + ("" if age_h < 48 else " - older than 2 days: schedule `build`"))


def _audit(cfg, add):
    from . import audit as auditmod
    try:
        a = auditmod.settings(cfg)
    except ValueError as e:
        add(FAIL, "load audit", str(e))
        return
    if not a:
        add(WARN, "load audit", "[audit] not configured - investigate cannot show the last load status of a file")
        return
    m = _store_meta(cfg, "audit_model")
    if not m:
        add(WARN, "load audit", f"no audit table found in '{a['db']}' - set [audit] table (then build)")
    else:
        add(OK, "load audit", f"{m['table']}: file {m['file_column']}, status {m.get('status_column')}, time {m.get('time_column')}, "
                              f"error {m.get('error_column')}" + (f" (guessed: {', '.join(m['guessed'])})" if m.get("guessed") else ""))


def _logs(cfg, add):
    from . import logs as lg
    s = lg.settings(cfg)
    if not s["enabled"]:
        add(WARN, "logs", "no log directory (set [logs] dirs, or [nifi] home) - errors from nifi-app.log are not available")
        return
    missing = [d for d in s["dirs"] if not Path(d).is_dir()]
    files = lg.log_files(s)
    if missing:
        add(FAIL if not files else WARN, "logs", f"directory not found: {', '.join(missing)}")
    if files:
        newest = max(files, key=lambda f: f.stat().st_mtime)
        events = _store_count(cfg, "SELECT COUNT(*) FROM log_events")
        add(OK, "logs", f"{len(files)} file(s), newest {newest.name} modified "
                         f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(newest.stat().st_mtime))}; {events} warning / error events indexed")
    elif not missing:
        add(WARN, "logs", f"no files matching {', '.join(s['patterns'])} in {', '.join(s['dirs'])}")


def _store_count(cfg, sql):
    import sqlite3
    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
    if not path.exists():
        return 0
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return db.execute(sql).fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        db.close()


def _nifi_api(cfg, add, offline):
    from . import nifiapi
    a = nifiapi.settings(cfg)
    if not a:
        add(WARN, "NiFi API", "[nifi_api] not configured - no provenance ('where was my file dropped') and no live bulletins")
        return
    if offline:
        add(OK, "NiFi API", f"{a['url']} (not contacted: --offline)")
        return
    try:
        about = nifiapi.Client(a).about()
        add(OK, "NiFi API", f"{a['url']} - {about.get('title', 'NiFi')} {about.get('version', '')}".strip())
    except (nifiapi.NiFiApiError, OSError, ValueError) as e:
        add(FAIL, "NiFi API", str(e))


def _optional(cfg, add):
    """[targets], [tickets], [environments.*], [registry]: configuration that can be checked without contacting anything."""
    import os
    if "targets" in cfg:
        t = cfg["targets"] or {}
        tools = []
        if t.get("hdfs_url"):
            tools.append(f"WebHDFS {t['hdfs_url']}" + (" (kerberos via curl)" if t.get("kerberos") else ""))
            if t.get("kerberos") and not shutil.which(t.get("curl", "curl")):
                add(FAIL, "targets", "kerberos = true needs curl on the PATH")
        elif shutil.which("hdfs") or t.get("hdfs_cli"):
            tools.append("hdfs CLI")
        if t.get("s3_cli"):
            tools.append("S3 via configured CLI")
        else:
            try:
                import boto3  # noqa: F401
                tools.append("S3 via boto3")
            except ImportError:
                tools.append("S3 via aws CLI" if shutil.which("aws") else "no S3 access (install the aws CLI or boto3)")
        add(OK, "targets", ", ".join(tools + ["local / mounted folders"])
            + (f"; location_template {t['location_template']}" if t.get("location_template") else ""))
    tk = cfg.get("tickets")
    if tk:
        secret = next((k for k in ("token", "password") if tk.get(f"{k}_env") and os.environ.get(tk[f"{k}_env"]) or tk.get(f"{k}_file")), None)
        if tk.get("kind") not in ("jira", "servicenow") or not tk.get("url"):
            add(FAIL, "tickets", "[tickets] needs kind = \"jira\" | \"servicenow\" and url")
        elif not secret:
            add(WARN, "tickets", f"{tk['kind']} {tk['url']}: no credential (set token_env / password_env or *_file)")
        else:
            add(OK, "tickets", f"{tk['kind']} {tk['url']} (posting only with `ticket <id> --post`)")
    dbs = {d["name"] for d in cfg.get("databases", [])}
    for name, env in (cfg.get("environments") or {}).items():
        problems = []
        if env.get("flow_file") and not Path(env["flow_file"]).exists():
            problems.append(f"flow_file {env['flow_file']} not found")
        if env.get("db") and env["db"] not in dbs:
            problems.append(f"db '{env['db']}' is not a [[databases]] name")
        add(FAIL if problems else OK, f"environment {name}", "; ".join(problems) or
            ", ".join(x for x in (env.get("flow_file"), env.get("db")) if x))


def _agents(cfg, add):
    root = Path(cfg["_path"]).parent
    for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
        if not (root / f).exists():
            add(WARN, "agent instructions", f"{f} missing next to nifikb.toml")
    texts = {f: (root / f).read_text(encoding="utf-8").replace("\r\n", "\n") for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md") if (root / f).exists()}
    if len(set(texts.values())) > 1:
        add(WARN, "agent instructions", "CLAUDE.md / GEMINI.md / AGENTS.md differ - copy the edited one over the others")
    elif texts:
        add(OK, "agent instructions", ", ".join(texts))
    for f, kind in ((".mcp.json", "Claude Code MCP"), (".gemini/settings.json", "Gemini CLI MCP")):
        p = root / f
        if not p.exists():
            add(WARN, kind, f"{f} missing")
            continue
        try:
            server = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["nifikb"]
        except (ValueError, KeyError) as e:
            add(FAIL, kind, f"{f}: no mcpServers.nifikb entry ({e})")
            continue
        cmd = server.get("command", "")
        found = shutil.which(cmd)
        if not found:
            alt = next((c for c in ("py", "python3", "python") if shutil.which(c)), None)
            add(FAIL, kind, f"{f}: command '{cmd}' not on PATH" + (f" - change it to '{alt}'" if alt else ""))
        else:
            add(OK, kind, f"{f} -> {cmd} {' '.join(server.get('args', []))}")
    if root.resolve() != PROJECT_DIR.resolve() and not (root / "nifikb").is_dir():
        add(WARN, "MCP working dir", f"the agents start `python -m nifikb` in {root}; the nifikb package lives in {PROJECT_DIR}")


def _knowledge(cfg, add):
    from . import learnings as lm
    r = lm.ensure(cfg)
    items = lm.load_all(cfg, include_obsolete=False)
    add(OK, "learnings", f"{len(items)} active in {r / 'learnings'}")
    if not lm.context_text(cfg):
        add(WARN, "team context", f"{r / 'context.md'} is still the template - fill in environments, owners, conventions")
    else:
        add(OK, "team context", str(r / "context.md"))


def report(checks):
    lines = [f"[{s}] {label}: {detail}" for s, label, detail in checks]
    fails = sum(1 for s, _, _ in checks if s == FAIL)
    warns = sum(1 for s, _, _ in checks if s == WARN)
    lines.append(f"\n{fails} problem(s), {warns} warning(s)")
    return "\n".join(lines), fails
