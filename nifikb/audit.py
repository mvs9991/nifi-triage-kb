"""Load-audit table: the platform's own record of each file load (status, error, rows, time) - usually the fastest route
to "what happened to file X". Configured in [audit]; columns are auto-detected and can be overridden."""
import re

from . import db as dbmod

FILE_COL = re.compile(r"(?i)file_?(name|nm)?$|^file|src_?file|source_?file|object_?name|obj_?name")
STATUS_COL = re.compile(r"(?i)(^|_)(status|state|result|outcome|load_?status|job_?status)(_?(cd|code|desc))?$")
TIME_COL = re.compile(r"(?i)(^|_)(ts|timestamp|time|date|dt|dttm|created|updated|load_?ts|start_?ts|end_?ts|insert_?ts|run_?ts)"
                      r"(_?(on|at|ts|dt|time))?$")
ERROR_COL = re.compile(r"(?i)err|message|msg|reason|remark|comment|exception")
ROWS_COL = re.compile(r"(?i)(row|record|rec)_?(count|cnt|num)|(count|cnt)$|rows")
LINK_COL = re.compile(r"(?i)^(obj|object|def|definition|feed)_?id$")
TABLE_NAME = re.compile(r"(?i)audit|load_?log|file_?log|process_?log|job_?log|file_?status|ingest(ion)?_?log|load_?hist|run_?log")
FAIL_WORDS = re.compile(r"(?i)fail|error|reject|abort|invalid|exception|^e$|^f$|^x$")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


def settings(cfg):
    a = cfg.get("audit")
    if not a:
        return None
    a = dict(a)
    dbs = cfg.get("databases", [])
    a.setdefault("db", (cfg.get("metadata") or {}).get("db") or (dbs[0]["name"] if dbs else None))
    if not any(d["name"] == a["db"] for d in dbs):
        raise ValueError(f"[audit] db = {a['db']!r} is not a [[databases]] name")
    for k in ("table", "file_column", "status_column", "time_column", "error_column", "rows_column", "link_column"):
        if a.get(k) and not IDENT.match(a[k]):
            raise ValueError(f"[audit] {k} = {a[k]!r} is not a plain table / column name")
    return a


def patterns(a):
    """Include patterns so the audit table gets documented (and its columns known) by the normal DB step."""
    return [a["table"].lower()] if a.get("table") else ["*audit*", "*load_log*", "*file_log*", "*process_log*", "*job_log*",
                                                          "*file_status*", "*ingest*log*", "*load_hist*", "*run_log*"]


def detect(a, db_result):
    """{table, schema, columns...} for the audit table, from the documented tables of its database."""
    tables = db_result.get("tables", []) if db_result else []
    cands = [t for t in tables if (a.get("table") and t["table"].lower() == a["table"].lower())
             or (not a.get("table") and TABLE_NAME.search(t["table"]))]
    best = None
    for t in cands:
        cols = [c["name"] for c in t["columns"]]
        pick = lambda rx, key: a.get(key) or next((c for c in cols if rx.search(c)), None)
        found = {"file_column": pick(FILE_COL, "file_column"), "status_column": pick(STATUS_COL, "status_column"),
                 "time_column": pick(TIME_COL, "time_column"), "error_column": pick(ERROR_COL, "error_column"),
                 "rows_column": pick(ROWS_COL, "rows_column"), "link_column": pick(LINK_COL, "link_column")}
        score = sum(1 for v in found.values() if v) + (3 if found["file_column"] else 0)
        if found["file_column"] and (best is None or score > best[0]):
            best = (score, dict(found, table=t["table"], schema=t.get("schema"),
                                guessed=[k for k, v in found.items() if v and not a.get(k)]))
    return best[1] if best else None


def _fq(dialect, schema, table):
    q = '"' if dialect != "mysql" else "`"
    return f"{q}{table}{q}" if dialect == "sqlite" or not schema else f"{q}{schema}{q}.{q}{table}{q}"


def lookup(cfg, model, file=None, link_ids=(), limit=10):
    """Latest audit rows for a file name (exact or contained, e.g. with a path) and / or definition ids."""
    a = settings(cfg)
    dcfg = next(d for d in cfg["databases"] if d["name"] == a["db"])
    conn, dialect = dbmod.connect(dcfg)
    try:
        q = '"' if dialect != "mysql" else "`"
        p = dbmod._ph(dialect)
        where, params = [], []
        if file:
            where.append(f"({q}{model['file_column']}{q} = {p} OR {q}{model['file_column']}{q} LIKE {p})")
            params += [file, f"%{file}"]
        if link_ids and model.get("link_column"):
            where.append(f"{q}{model['link_column']}{q} IN ({','.join([p] * len(link_ids))})")
            params += list(link_ids)
        if not where:
            return []
        order = f" ORDER BY {q}{model['time_column']}{q} DESC" if model.get("time_column") else ""
        sql = f"SELECT * FROM {_fq(dialect, model.get('schema'), model['table'])} WHERE {' OR '.join(where)}{order} LIMIT {int(limit)}"
        rows = dbmod._rows(conn, sql, tuple(params))
        return [{k: dbmod.mask_value(k, v) for k, v in r.items()} for r in rows]
    finally:
        conn.close()


def is_failure(model, row):
    v = row.get(model.get("status_column"))
    return bool(v is not None and FAIL_WORDS.search(str(v)))


def summarize(model, row):
    get = lambda k: row.get(model.get(k)) if model.get(k) else None
    parts = [f"{get('file_column')}", f"status {get('status_column')}" if get("status_column") is not None else "",
             f"at {get('time_column')}" if get("time_column") is not None else "",
             f"{get('rows_column')} rows" if get("rows_column") is not None else "",
             f"error: {str(get('error_column'))[:200]}" if get("error_column") not in (None, "") else ""]
    return ", ".join(x for x in parts if x)


def format_rows(model, rows):
    if not rows:
        return "no load-audit rows for this file / feed"
    return "\n".join(("x " if is_failure(model, r) else "  ") + summarize(model, r) for r in rows)
