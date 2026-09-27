"""Read-only database access: schema introspection for the tables the flow/code touch, and guarded ad-hoc SELECTs.

Drivers are optional and imported lazily:
  mariadb / mysql -> pymysql   (pip install pymysql)
  postgres        -> psycopg2  or pg8000
  sqlite          -> stdlib (used by tests and for local files)
"""
import fnmatch
import os
import re
import sqlite3

from .util import REDACTED, SECRET_NAME, redact_secrets

MASK_COLUMNS = re.compile(r"(?i)pass|pwd|secret|token|ssn|aadhaar|pan_?no|card|cvv|email|phone|mobile|dob|birth|salary|account_?no|iban")
MASK_EXTRA = re.compile(r"(?i)authorization|auth_?(token|header|value|key)|passphrase|private|cert|keystore|truststore|credential")
BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}")


def sensitive_column(name):
    name = str(name)
    return bool(MASK_COLUMNS.search(name) or SECRET_NAME.search(name) or MASK_EXTRA.search(name))


def mask_value(column, value):
    """Masked form of one value read from a database: sensitive columns become ***, secrets inside text are redacted."""
    if value is None:
        return None
    if sensitive_column(column):
        return "***"
    if isinstance(value, str):
        return BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(value))
    return value
READ_ONLY_SQL = re.compile(r"(?is)^\s*(select|with|show|describe|desc|explain)\b")
WRITE_WORDS = re.compile(r"(?i)\b(insert|update|delete|merge|replace|create|alter|drop|truncate|grant|revoke|call|exec|execute|lock|load|into\s+outfile|set\s+global)\b")


class DbError(Exception):
    pass


def connect(cfg):
    kind = (cfg.get("kind") or "mariadb").lower()
    password = cfg.get("password")
    if cfg.get("password_env"):
        password = os.environ.get(cfg["password_env"], password)
    if not password and cfg.get("password_file"):
        try:
            with open(cfg["password_file"], encoding="utf-8") as f:
                password = f.read().strip()
        except OSError as e:
            raise DbError(f"cannot read password_file of {cfg.get('name')}: {e}") from e
    try:
        if kind in ("mariadb", "mysql"):
            try:
                import pymysql
            except ImportError as e:
                raise DbError("MariaDB/MySQL needs the 'pymysql' package: pip install pymysql") from e
            conn = pymysql.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)), user=cfg.get("user"),
                                   password=password or "", database=cfg.get("database"), connect_timeout=int(cfg.get("timeout", 10)),
                                   read_timeout=int(cfg.get("query_timeout", 60)), charset="utf8mb4")
            with conn.cursor() as cur:
                cur.execute("SET SESSION TRANSACTION READ ONLY")
            return conn, "mysql"
        if kind in ("postgres", "postgresql"):
            try:
                import psycopg2
                conn = psycopg2.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)), user=cfg.get("user"),
                                        password=password, dbname=cfg.get("database"), connect_timeout=int(cfg.get("timeout", 10)),
                                        options="-c default_transaction_read_only=on -c statement_timeout=%d" % (int(cfg.get("query_timeout", 60)) * 1000))
            except ImportError:
                try:
                    import pg8000.dbapi as pg8000
                except ImportError as e:
                    raise DbError("PostgreSQL needs 'psycopg2-binary' or 'pg8000': pip install pg8000") from e
                conn = pg8000.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)), user=cfg.get("user"),
                                      password=password, database=cfg.get("database"), timeout=int(cfg.get("timeout", 10)))
                cur = conn.cursor()
                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
            return conn, "postgres"
        if kind == "sqlite":
            return sqlite3.connect(f"file:{cfg['database']}?mode=ro", uri=True), "sqlite"
    except DbError:
        raise
    except Exception as e:  # driver specific connection errors
        raise DbError(f"cannot connect to {cfg.get('name')}: {type(e).__name__}: {e}") from e
    raise DbError(f"unsupported database kind '{kind}'")


def _rows(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _ph(dialect):
    return "?" if dialect == "sqlite" else "%s"


def list_tables(conn, dialect, schemas):
    if dialect == "sqlite":
        return [{"schema": "main", "table": r["name"], "type": r["type"].upper(), "rows": None, "comment": ""}
                for r in _rows(conn, "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
    ph = ",".join([_ph(dialect)] * len(schemas))
    if dialect == "mysql":
        sql = (f"SELECT TABLE_SCHEMA AS s, TABLE_NAME AS t, TABLE_TYPE AS ty, TABLE_ROWS AS n, TABLE_COMMENT AS c "
               f"FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ({ph})")
    else:
        sql = (f"SELECT t.table_schema AS s, t.table_name AS t, t.table_type AS ty, c.reltuples::bigint AS n, "
               f"obj_description(c.oid) AS c FROM information_schema.tables t "
               f"LEFT JOIN pg_catalog.pg_namespace ns ON ns.nspname = t.table_schema "
               f"LEFT JOIN pg_catalog.pg_class c ON c.relname = t.table_name AND c.relnamespace = ns.oid "
               f"WHERE t.table_schema IN ({ph})")
    return [{"schema": r["s"], "table": r["t"], "type": r["ty"], "rows": r["n"], "comment": r["c"] or ""}
            for r in _rows(conn, sql, tuple(schemas))]


def describe_table(conn, dialect, schema, table):
    if dialect == "sqlite":
        cols = [{"name": r["name"], "type": r["type"], "nullable": not r["notnull"], "key": "PRI" if r["pk"] else "",
                 "default": r["dflt_value"], "extra": "", "comment": ""} for r in _rows(conn, f'PRAGMA table_info("{table}")')]
        fks = [{"column": r["from"], "ref": f"{r['table']}.{r['to']}"} for r in _rows(conn, f'PRAGMA foreign_key_list("{table}")')]
        idx = [{"name": r["name"], "unique": bool(r["unique"]),
                "columns": [c["name"] for c in _rows(conn, f'PRAGMA index_info("{r["name"]}")')]}
               for r in _rows(conn, f'PRAGMA index_list("{table}")')]
        idx.sort(key=lambda i: (i["name"].upper() != "PRIMARY", i["name"]))
        return {"columns": cols, "foreign_keys": fks, "indexes": idx}
    p = _ph(dialect)
    if dialect == "mysql":
        cols = _rows(conn, "SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, COLUMN_KEY AS `key`, "
                           "COLUMN_DEFAULT AS `default`, EXTRA AS extra, COLUMN_COMMENT AS comment FROM information_schema.COLUMNS "
                           f"WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} ORDER BY ORDINAL_POSITION", (schema, table))
        fks = _rows(conn, "SELECT COLUMN_NAME AS `column`, CONCAT(REFERENCED_TABLE_NAME,'.',REFERENCED_COLUMN_NAME) AS ref "
                          f"FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} AND REFERENCED_TABLE_NAME IS NOT NULL",
                    (schema, table))
        idx_rows = _rows(conn, "SELECT INDEX_NAME AS name, NON_UNIQUE AS nu, COLUMN_NAME AS col FROM information_schema.STATISTICS "
                               f"WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} ORDER BY INDEX_NAME, SEQ_IN_INDEX", (schema, table))
    else:
        cols = _rows(conn, "SELECT c.column_name AS name, c.data_type || COALESCE('(' || c.character_maximum_length || ')', '') AS type, "
                           "c.is_nullable AS nullable, CASE WHEN k.column_name IS NOT NULL THEN 'PRI' ELSE '' END AS key, "
                           "c.column_default AS default, '' AS extra, '' AS comment FROM information_schema.columns c "
                           "LEFT JOIN (SELECT ku.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage ku "
                           "ON tc.constraint_name = ku.constraint_name AND tc.table_schema = ku.table_schema "
                           f"WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema={p} AND tc.table_name={p}) k ON k.column_name = c.column_name "
                           f"WHERE c.table_schema={p} AND c.table_name={p} ORDER BY c.ordinal_position", (schema, table, schema, table))
        fks = _rows(conn, "SELECT kcu.column_name AS column, ccu.table_name || '.' || ccu.column_name AS ref "
                          "FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
                          "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
                          f"WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema={p} AND tc.table_name={p}", (schema, table))
        idx_rows = _rows(conn, "SELECT i.relname AS name, CASE WHEN ix.indisunique THEN 0 ELSE 1 END AS nu, a.attname AS col "
                               "FROM pg_class t JOIN pg_index ix ON t.oid = ix.indrelid JOIN pg_class i ON i.oid = ix.indexrelid "
                               "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey) JOIN pg_namespace n ON n.oid = t.relnamespace "
                               f"WHERE n.nspname={p} AND t.relname={p}", (schema, table))
    for c in cols:
        c["nullable"] = str(c["nullable"]).upper() in ("YES", "TRUE", "1")
    idx = {}
    for r in idx_rows:
        idx.setdefault(r["name"], {"name": r["name"], "unique": not int(r["nu"]), "columns": []})["columns"].append(r["col"])
    indexes = sorted(idx.values(), key=lambda i: (i["name"].upper() != "PRIMARY", i["name"]))
    return {"columns": cols, "foreign_keys": fks, "indexes": indexes}


def profile_table(conn, dialect, schema, table, columns, max_distinct=20):
    """Distinct values of low-cardinality text columns (e.g. status, source_system). Masked columns are skipped."""
    q = '"' if dialect != "mysql" else "`"
    fq = f"{q}{table}{q}" if dialect == "sqlite" else f"{q}{schema}{q}.{q}{table}{q}"
    out = {}
    for c in columns:
        if sensitive_column(c["name"]) or not re.search(r"(?i)char|text|enum|string", str(c["type"])):
            continue
        rows = _rows(conn, f"SELECT {q}{c['name']}{q} AS v, COUNT(*) AS n FROM {fq} GROUP BY {q}{c['name']}{q} ORDER BY n DESC LIMIT {max_distinct + 1}")
        if 0 < len(rows) <= max_distinct:
            out[c["name"]] = [(mask_value(c["name"], r["v"]), r["n"]) for r in rows]
    return out


def sample_rows(conn, dialect, schema, table, n):
    q = '"' if dialect != "mysql" else "`"
    fq = f"{q}{table}{q}" if dialect == "sqlite" else f"{q}{schema}{q}.{q}{table}{q}"
    rows = _rows(conn, f"SELECT * FROM {fq} LIMIT {int(n)}")
    return [{k: mask_value(k, v) for k, v in r.items()} for r in rows]


def introspect(cfg, wanted_tables, optional_tables=(), log=print):
    """Describe wanted tables (+ optional ones if they exist, + config include patterns) for one database.
    Only wanted tables that do not exist are reported as missing."""
    conn, dialect = connect(cfg)
    try:
        schemas = cfg.get("schemas") or ([cfg["database"]] if dialect == "mysql" else ["public"])
        all_tables = list_tables(conn, dialect, schemas)
        by_name = {}
        for t in all_tables:
            by_name.setdefault(t["table"].lower(), t)
            by_name.setdefault(f"{t['schema']}.{t['table']}".lower(), t)
        patterns = [p.lower().replace("%", "*") for p in cfg.get("include_tables") or []]
        chosen, missing = {}, []
        for name in sorted(set(wanted_tables) | set(optional_tables)):
            t = by_name.get(name.lower()) or by_name.get(name.lower().split(".")[-1])
            if t:
                chosen[(t["schema"], t["table"])] = t
            elif name in wanted_tables and "${" not in name and "#{" not in name:
                missing.append(name)
        for t in all_tables:
            if cfg.get("all_tables") or any(fnmatch.fnmatch(t["table"].lower(), p) for p in patterns):
                chosen[(t["schema"], t["table"])] = t
        max_tables = int(cfg.get("max_tables", 300))
        profile = {p.lower() for p in cfg.get("profile_tables") or []}
        out = []
        for (schema, table), t in sorted(chosen.items())[:max_tables]:
            info = dict(t)
            info.update(describe_table(conn, dialect, schema, table))
            if dialect == "sqlite":
                info["rows"] = _rows(conn, f'SELECT COUNT(*) AS n FROM "{table}"')[0]["n"]
            if table.lower() in profile:
                info["profile"] = profile_table(conn, dialect, schema, table, info["columns"])
            if int(cfg.get("sample_rows", 0)) > 0:
                info["sample"] = sample_rows(conn, dialect, schema, table, cfg["sample_rows"])
            out.append(info)
        log(f"  db {cfg['name']}: {len(all_tables)} tables in {', '.join(schemas)}, documented {len(out)}, missing {len(missing)}")
        return {"name": cfg["name"], "kind": cfg.get("kind"), "dialect": dialect, "schemas": schemas, "tables": out,
                "missing": missing, "table_count": len(all_tables), "all_table_names": sorted(t["table"] for t in all_tables)}
    finally:
        conn.close()


def run_query(cfg, sql, max_rows=200):
    sql = sql.strip().rstrip(";")
    if ";" in sql or not READ_ONLY_SQL.match(sql) or WRITE_WORDS.search(re.sub(r"'[^']*'", "''", sql)):
        raise DbError("only a single read-only SELECT / WITH / SHOW / DESCRIBE / EXPLAIN statement is allowed")
    conn, dialect = connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows)
        if cfg.get("mask", True):
            rows = [tuple(mask_value(c, v) for c, v in zip(cols, r)) for r in rows]
        return cols, rows
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


def matches_jdbc(cfg, jdbc):
    """Does a configured database correspond to a DBCP service's JDBC URL?"""
    if cfg.get("dbcp_services") and jdbc.get("service_name") in cfg["dbcp_services"]:
        return True
    if cfg.get("match_jdbc"):
        return cfg["match_jdbc"].lower() in (jdbc.get("url") or "").lower()
    local = {"localhost", "127.0.0.1", "::1"}
    h1, h2 = (cfg.get("host") or "").lower(), (jdbc.get("host") or "").lower()
    same_host = h1 == h2 or (h1 in local and h2 in local)
    same_db = (cfg.get("database") or "").lower() == (jdbc.get("database") or "").lower()
    port_ok = not jdbc.get("port") or str(jdbc["port"]) == str(cfg.get("port", jdbc["port"]))
    return same_host and same_db and port_ok
