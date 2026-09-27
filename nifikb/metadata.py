"""Metadata-driven ingestion: the company config tables that drive the flow (e.g. OBJ_DEFINITION = one row per
file/object, OBJ_STRUCTURE = one row per column, SOURCE_FEED_CONFIG, NIFI_JSON_API_CONFIG, ...).

- discover(): finds the config tables, how they relate (declared FKs, shared id columns, config overrides) and which
  table plays the "definition" / "structure" role. Everything is auto-detected and can be overridden in [metadata].
- fetch_rows(): read-only, masked snapshot of the config tables (stored in kb.sqlite for offline lookups).
- lint(): OBJ_STRUCTURE-style definitions vs. the real target tables (missing columns, types, lengths, NOT NULL).
- dossier(): everything the metadata says about one file / table / feed / API, plus header checks.
"""
import difflib
import json
import re
from collections import defaultdict
from pathlib import PurePath

from . import db as dbmod

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")

FIELD_COL = re.compile(r"(?i)^(src_|source_|tgt_|target_|stg_)?(col|column|field|attr|attribute|element)_?(name|nm)?$")
TYPE_COL = re.compile(r"(?i)^((col|column|field|attr|src|tgt|target)_?)?(data_?type|d_?type|type)(_?(name|nm|cd|code))?$")
ORDER_COL = re.compile(r"(?i)(^|_)(seq|sequence|seq_?no|seq_?num|order|ordinal|position|pos|col_?no|col_?num|field_?no|col_?order|col_?seq|col_?pos|field_?seq)(_?no|_?num)?$")
PATH_COL = re.compile(r"(?i)(^|_)(json_?path|src_?path|source_?path|x_?path|field_?path|path|jsonpath|json_?key)$")
LENGTH_COL = re.compile(r"(?i)(^|_)(length|len|size|width|max_?len|col_?len|col_?length|field_?length)$")
NULL_COL = re.compile(r"(?i)(^|_)(is_?)?(nullable|null|optional|nullability)(_?(flag|ind|yn|fl|allowed))?$")
REQUIRED_COL = re.compile(r"(?i)(^|_)(is_?)?(mandatory|required|not_?null|mand|req)(_?(flag|ind|yn|fl))?$")
KEY_COL = re.compile(r"(?i)(file|table|tbl|obj|object|feed|entity|source|src|target|tgt|dataset|interface|api|endpoint|job|flow|process)"
                     r"_?(name|nm|pattern|mask|prefix|code|cd|key)?$")
LOCATION_COL = re.compile(r"(?i)^(hdfs|s3|tgt|target|dest|destination|output|landing|parquet|load)_?"
                          r"(path|dir|directory|location|bucket|prefix|folder|uri|key)$")
FILE_TARGET = re.compile(r"(?i)^[a-z][a-z0-9+.-]*://|[\\/]")  # s3://, hdfs://, /data/..., C:\... = a location, not a table
TARGET_COL = re.compile(r"(?i)^(tgt|target|dest|destination|stg|stage|staging|load|landing|db)?_?(table|tbl)_?(name|nm)?$")
FILE_COL = re.compile(r"(?i)file")
GENERIC_ID = {"id", "seq", "name", "type", "status", "code", "value", "created_by", "updated_by", "created_dt", "updated_dt"}
DATE_RUN = re.compile(r"(?<![A-Za-z])(?:YYYY|YY|MM|DD|HH24|HH|MI|SS)+(?![A-Za-z])")

ROLE_KEYS = ("definition_table", "definition_id", "definition_target", "structure_table", "structure_parent",
             "structure_field", "structure_type", "structure_order", "structure_length", "structure_nullable", "structure_path",
             "definition_location")


# ------------------------------------------------------------------------------------------------ config
def settings(cfg):
    """Normalised [metadata] section, or None when metadata support is not configured."""
    m = cfg.get("metadata")
    if not m:
        return None
    dbs = cfg.get("databases", [])
    if not dbs:
        raise ValueError("[metadata] needs a [[databases]] entry for the database that holds the config tables")
    out = dict(m)
    out.setdefault("db", dbs[0]["name"])
    out.setdefault("target_db", out["db"])
    if str(out["target_db"]).lower() in ("", "none", "off", "false"):
        out["target_db"] = None  # loads go to files (HDFS / S3 / Parquet): no target-table checks
    out.setdefault("tables", ["OBJ_%", "%_CONFIG", "%_CONFIG_%", "%_DEFINITION", "%_STRUCTURE", "%_METADATA%"])
    out.setdefault("snapshot_max_rows", 20000)
    out.setdefault("structure_max_rows", 2000000)
    out.setdefault("relations", [])
    for name in [n for n in (out["db"], out["target_db"]) if n]:
        if not any(d["name"] == name for d in dbs):
            raise ValueError(f"[metadata] refers to database '{name}' but no [[databases]] entry has that name")
    for k in ROLE_KEYS:
        v = out.get(k)
        if v and not IDENT.match(v):
            raise ValueError(f"[metadata] {k} = {v!r} is not a plain table/column name")
    for k in out.get("definition_keys") or []:
        if not IDENT.match(k):
            raise ValueError(f"[metadata] definition_keys entry {k!r} is not a plain column name")
    for r in out["relations"]:
        for side in ("child", "parent"):
            parts = str(r.get(side, "")).split(".")
            if len(parts) != 2 or not all(IDENT.match(p) for p in parts):
                raise ValueError(f"[metadata] relation {side} must look like TABLE.COLUMN, got {r.get(side)!r}")
    return out


def db_config(cfg, name):
    return next(d for d in cfg["databases"] if d["name"] == name)


# ------------------------------------------------------------------------------------------------ helpers
def truthy(v):
    return str(v).strip().upper() in ("Y", "YES", "TRUE", "T", "1")


def norm(v):
    return "" if v is None else str(v).strip().lower()


def type_family(t):
    t = str(t or "").lower()
    if not t:
        return None
    if re.search(r"bool|^bit\b", t):
        return "bool"
    if re.search(r"date|time", t):
        return "temporal"
    if re.search(r"int|dec|num|float|double|real|money|serial|long|short|byte", t):
        return "numeric"
    if re.search(r"char|text|string|clob|json|xml|uuid|enum|str", t):
        return "string"
    return None


def str_length(t):
    m = re.search(r"(?i)char\s*\(\s*(\d+)", str(t or ""))
    return int(m.group(1)) if m else None


def as_int(v):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def pattern_regex(value):
    """A stored file name / pattern ('SALES_*.csv', 'SALES_%', 'SALES_YYYYMMDD.csv', 'SALES_\\d{8}.csv', '${x}.csv')."""
    v = str(value or "").strip()
    if not v:
        return None
    if re.search(r"\\[dwsDWS]|\.\*|\.\+|\[[^\]]+\]|\{\d", v):
        try:
            return re.compile(v + r"\Z", re.I)
        except re.error:
            pass
    out, pos = [], 0
    for m in re.finditer(r"\$\{[^}]*\}|#\{[^}]*\}|\*|\?|%|" + DATE_RUN.pattern, v):
        out.append(re.escape(v[pos:m.start()]))
        tok = m.group(0)
        if tok in ("*", "%") or tok.startswith(("${", "#{")):
            out.append(".*")
        elif tok == "?":
            out.append(".")
        else:
            out.append(r"\d{%d}" % len(tok.replace("HH24", "HH")))
        pos = m.end()
    out.append(re.escape(v[pos:]))
    if len(out) == 1:
        return None
    return re.compile("".join(out) + r"\Z", re.I)


def mask_row(row):
    out = {}
    for k, v in row.items():
        if isinstance(v, (bytes, bytearray)):
            v = f"<{len(v)} bytes>"
        elif v is not None and not isinstance(v, (str, int, float, bool)):
            v = str(v)
        out[k] = dbmod.mask_value(k, v)
    return out


# ------------------------------------------------------------------------------------------------ discovery
def _pick(cols, rx, prefer=None, exclude=()):
    hits = [c for c in cols if rx.search(c) and c not in exclude]
    if prefer:
        hits.sort(key=lambda c: (not re.search(prefer, c, re.I), len(c)))
    return hits[0] if hits else None


def _pk(t):
    pk = [c["name"] for c in t["columns"] if c.get("key") == "PRI"]
    if not pk:
        idx = next((i for i in t.get("indexes", []) if i["name"].upper() == "PRIMARY" or i["name"].lower().endswith("_pkey")), None)
        pk = idx["columns"] if idx else []
    return pk


def table_patterns(m):
    """LIKE/glob patterns + explicit names that select the config tables (lower case, glob syntax)."""
    pats = [p.lower().replace("%", "*") for p in m["tables"]]
    pats += [m[k].lower() for k in ("definition_table", "structure_table") if m.get(k)]
    pats += [r[s].split(".")[0].lower() for r in m["relations"] for s in ("child", "parent")]
    return pats


def discover(m, db_result):
    """Config tables, relations and roles from the documented schema of the metadata database."""
    import fnmatch
    patterns = table_patterns(m)
    tables = {}
    for t in db_result.get("tables", []):
        name = t["table"].lower()
        if any(fnmatch.fnmatch(name, p) for p in patterns):
            tables[name] = t
    names = {n: t["table"] for n, t in tables.items()}

    relations, seen = [], set()

    def add(child, ccol, parent, pcol, source):
        key = (child.lower(), ccol.lower(), parent.lower(), pcol.lower())
        if key in seen or child.lower() == parent.lower():
            return
        seen.add(key)
        relations.append({"child": names.get(child.lower(), child), "child_column": ccol,
                          "parent": names.get(parent.lower(), parent), "parent_column": pcol, "source": source})

    for r in m["relations"]:
        (c, cc), (p, pc) = r["child"].split("."), r["parent"].split(".")
        add(c, cc, p, pc, "config")
    for n, t in tables.items():
        for fk in t.get("foreign_keys", []):
            ref_t, _, ref_c = str(fk["ref"]).rpartition(".")
            if ref_t.lower() in tables:
                add(t["table"], fk["column"], ref_t, ref_c, "foreign key")
    pk_owner = defaultdict(list)
    for n, t in tables.items():
        pk = _pk(t)
        if len(pk) == 1 and pk[0].lower() not in GENERIC_ID and len(pk[0]) > 2:
            pk_owner[pk[0].lower()].append(t["table"])
    for n, t in tables.items():
        for c in t["columns"]:
            owners = [o for o in pk_owner.get(c["name"].lower(), []) if o.lower() != n]
            if len(owners) == 1 and c["name"] not in _pk(t):
                add(t["table"], c["name"], owners[0], c["name"], "shared column name")

    model = {"db": m["db"], "target_db": m["target_db"], "tables": {t["table"]: {
        "columns": [c["name"] for c in t["columns"]], "pk": _pk(t), "rows": t.get("rows"), "comment": t.get("comment") or "",
        "schema": t.get("schema")} for t in tables.values()}, "relations": relations}
    model.update(_roles(m, tables, relations))
    return model


def _roles(m, tables, relations):
    """Which table is the definition (one row per file/object) and which the structure (one row per column)."""
    by_lower = {n: t for n, t in tables.items()}
    roles, guessed = {}, []

    def cols(table):
        t = by_lower.get(str(table).lower())
        return [c["name"] for c in t["columns"]] if t else []

    st = m.get("structure_table")
    if not st:
        best = None
        for n, t in tables.items():
            cs = [c["name"] for c in t["columns"]]
            score = bool(_pick(cs, FIELD_COL)) * 3 + bool(_pick(cs, ORDER_COL)) + bool(_pick(cs, TYPE_COL))
            has_parent = any(r["child"].lower() == n for r in relations)
            if _pick(cs, FIELD_COL) and score >= 4 and has_parent and (best is None or score > best[0]):
                best = (score, t["table"])
        st = best[1] if best else None
        if st:
            guessed.append("structure_table")
    if st and str(st).lower() in by_lower:
        st = by_lower[str(st).lower()]["table"]
        scols = cols(st)
        parent_rel = next((r for r in relations if r["child"].lower() == st.lower()
                           and (not m.get("definition_table") or r["parent"].lower() == m["definition_table"].lower())
                           and (not m.get("structure_parent") or r["child_column"].lower() == m["structure_parent"].lower())), None)
        roles["structure_table"] = st
        for key, rx, prefer in (("structure_field", FIELD_COL, r"col|field"), ("structure_type", TYPE_COL, r"data"),
                                ("structure_order", ORDER_COL, r"seq|order|pos"), ("structure_length", LENGTH_COL, r"len"),
                                ("structure_path", PATH_COL, r"json"),
                                ("structure_nullable", None, None)):
            if m.get(key):
                roles[key] = m[key]
                continue
            if key == "structure_nullable":
                val = _pick(scols, NULL_COL) or _pick(scols, REQUIRED_COL)
            else:
                val = _pick(scols, rx, prefer, exclude=[roles.get("structure_field")] if key != "structure_field" else ())
            if val:
                roles[key] = val
                guessed.append(key)
        if roles.get("structure_nullable"):
            roles["nullable_means_required"] = bool(REQUIRED_COL.search(roles["structure_nullable"]))
        roles["structure_parent"] = m.get("structure_parent") or (parent_rel["child_column"] if parent_rel else None)
        dt = m.get("definition_table") or (parent_rel["parent"] if parent_rel else None)
        if dt and not m.get("definition_table"):
            guessed.append("definition_table")
        if dt and str(dt).lower() in by_lower:
            dt = by_lower[str(dt).lower()]["table"]
            roles["definition_table"] = dt
            dcols = cols(dt)
            roles["definition_id"] = m.get("definition_id") or (parent_rel["parent_column"] if parent_rel and parent_rel["parent"] == dt
                                                                else (_pk(by_lower[dt.lower()]) or [None])[0])
            roles["definition_keys"] = m.get("definition_keys") or [c for c in dcols if KEY_COL.search(c) and c != roles["definition_id"]][:6]
            roles["definition_target"] = m.get("definition_target") or _pick(dcols, TARGET_COL, r"tgt|target|dest|stg")
            roles["definition_location"] = m.get("definition_location") or _pick(dcols, LOCATION_COL, r"hdfs|s3|tgt|target")
            for k in ("definition_id", "definition_keys", "definition_target", "definition_location"):
                if not m.get(k) and roles.get(k):
                    guessed.append(k)
    roles["guessed"] = guessed
    return roles


# ------------------------------------------------------------------------------------------------ rows
def _fq(dialect, schema, table):
    q = '"' if dialect != "mysql" else "`"
    return f"{q}{table}{q}" if dialect == "sqlite" or not schema else f"{q}{schema}{q}.{q}{table}{q}"


def fetch_rows(dcfg, m, model, log=print):
    """Masked rows of every config table (structure table capped separately). Returns {table: [row dict]}."""
    conn, dialect = dbmod.connect(dcfg)
    out = {}
    try:
        for table, info in model["tables"].items():
            limit = int(m["structure_max_rows"] if table == model.get("structure_table") else m["snapshot_max_rows"])
            if limit <= 0:
                continue
            order = ""
            if table == model.get("structure_table") and model.get("structure_parent"):
                q = '"' if dialect != "mysql" else "`"
                order = f" ORDER BY {q}{model['structure_parent']}{q}" + (f", {q}{model['structure_order']}{q}" if model.get("structure_order") else "")
            rows = dbmod._rows(conn, f"SELECT * FROM {_fq(dialect, info.get('schema'), table)}{order} LIMIT {limit + 1}")
            if len(rows) > limit:
                log(f"  ⚠ metadata: {table} has more than {limit} rows, snapshot truncated (raise snapshot_max_rows / structure_max_rows)")
                rows = rows[:limit]
            out[table] = [mask_row(r) for r in rows]
        log(f"  metadata: {len(out)} config tables, {sum(len(v) for v in out.values())} rows snapshotted")
        return out
    finally:
        conn.close()


def fetch_live(dcfg, m, model):
    """Fresh masked rows of every config table except the (large) structure table."""
    conn, dialect = dbmod.connect(dcfg)
    try:
        return {t: [mask_row(r) for r in dbmod._rows(conn, f"SELECT * FROM {_fq(dialect, i.get('schema'), t)} LIMIT {int(m['snapshot_max_rows'])}")]
                for t, i in model["tables"].items() if t != model.get("structure_table")}
    finally:
        conn.close()


def fetch_structure(dcfg, model, ids):
    """Fresh structure rows for a few definition ids."""
    st, parent = model.get("structure_table"), model.get("structure_parent")
    ids = [i for i in ids if i is not None]
    if not st or not parent or not ids:
        return []
    conn, dialect = dbmod.connect(dcfg)
    try:
        q = '"' if dialect != "mysql" else "`"
        ph = ",".join([dbmod._ph(dialect)] * len(ids))
        return [mask_row(r) for r in dbmod._rows(conn, f"SELECT * FROM {_fq(dialect, model['tables'][st].get('schema'), st)} "
                                                       f"WHERE {q}{parent}{q} IN ({ph})", tuple(ids))]
    finally:
        conn.close()


class Rows:
    """Row access over a {table: rows} snapshot with lazy per-column indexes."""

    def __init__(self, rows_by_table):
        self.data = rows_by_table
        self._idx = {}

    def table(self, name):
        return self.data.get(name, [])

    def where(self, table, column, value):
        key = (table, column)
        if key not in self._idx:
            idx = defaultdict(list)
            for r in self.data.get(table, []):
                idx[norm(r.get(column))].append(r)
            self._idx[key] = idx
        return self._idx[key].get(norm(value), [])


# ------------------------------------------------------------------------------------------------ objects + checks
def definition_label(model, row):
    for k in model.get("definition_keys") or []:
        if row.get(k):
            return str(row[k])
    return str(row.get(model.get("definition_id")))


def structure_of(model, rows, def_row):
    """Ordered field list of one definition row."""
    st, parent = model.get("structure_table"), model.get("structure_parent")
    if not st or not parent:
        return []
    fields = []
    pk = (model["tables"].get(st) or {}).get("pk") or []
    for r in rows.where(st, parent, def_row.get(model["definition_id"])):
        name = r.get(model.get("structure_field"))
        if name is None:
            continue
        nullable = None
        if model.get("structure_nullable") and r.get(model["structure_nullable"]) is not None:
            flag = truthy(r[model["structure_nullable"]])
            nullable = not flag if model.get("nullable_means_required") else flag
        fields.append({"name": str(name), "type": r.get(model.get("structure_type")) if model.get("structure_type") else None,
                       "seq": as_int(r.get(model["structure_order"])) if model.get("structure_order") else None,
                       "length": as_int(r.get(model["structure_length"])) if model.get("structure_length") else None,
                       "nullable": nullable,
                       "path": r.get(model["structure_path"]) if model.get("structure_path") else None,
                       "key": {c: r.get(c) for c in pk} if pk else {model["structure_parent"]: r.get(model["structure_parent"]),
                                                                    model["structure_field"]: name}})
    fields.sort(key=lambda f: (f["seq"] is None, f["seq"] if f["seq"] is not None else 0))
    return fields


def json_path(name):
    """'$.data[*].customer.name', '/data/customer/name', 'data.customer.name' -> 'data.customer.name'."""
    s = re.sub(r"\[[^\]]*\]", "", str(name).strip())
    s = re.sub(r"^\$\.?", "", s).replace("/", ".")
    return re.sub(r"\.{2,}", ".", s).strip(".")


def is_path_structure(fields):
    return any(re.search(r"[.$/\[]", f["name"]) for f in fields)


def check_headers(fields, headers, ordered=True, paths=False, root=None):
    """Incoming headers / JSON keys vs. the structure rows of one definition. With paths=True (a JSON sample checked
    against structure rows holding JSON paths) both sides are compared as dotted paths below the record root and the
    order is not checked."""
    if paths:
        prefix = json_path(root) + "." if root and json_path(root) else ""
        fields = [dict(f, name=json_path(f["name"])[len(prefix):] if prefix and json_path(f["name"]).startswith(prefix)
                       else json_path(f["name"])) for f in fields]
        headers = [json_path(h) for h in headers]
        ordered = False
    return _check_headers(fields, headers, ordered)


def _check_headers(fields, headers, ordered):
    issues = []
    expected = {f["name"].lower(): f for f in fields}
    seen, dups = set(), []
    for h in headers:
        if h.lower() in seen:
            dups.append(h)
        seen.add(h.lower())
    if dups:
        issues.append({"severity": "error", "kind": "duplicate-header", "message": f"duplicate header(s): {', '.join(dups)}"})
    squash = {re.sub(r"[^a-z0-9]", "", k): f["name"] for k, f in expected.items()}
    for h in headers:
        if h.lower() in expected:
            continue
        near = squash.get(re.sub(r"[^a-z0-9]", "", h.lower()))
        if near:
            issues.append({"severity": "error", "kind": "header-name", "message": f"header '{h}' differs from '{near}' only by case/underscores/spaces",
                           "data": {"field": near, "header": h}})
            continue
        guess = difflib.get_close_matches(h.lower(), list(expected), n=1, cutoff=0.6)
        issues.append({"severity": "error", "kind": "unknown-header",
                       "message": f"header '{h}' is not in the structure" + (f" (did you mean '{expected[guess[0]]['name']}'?)" if guess else "")})
    given = {h.lower() for h in headers}
    squashed_given = {re.sub(r"[^a-z0-9]", "", h.lower()) for h in headers}
    missing = [f for f in fields if f["name"].lower() not in given and re.sub(r"[^a-z0-9]", "", f["name"].lower()) not in squashed_given]
    for f in missing:
        sev = "warn" if f["nullable"] else "error"
        issues.append({"severity": sev, "kind": "missing-field",
                       "message": f"structure field '{f['name']}'" + (f" (seq {f['seq']})" if f["seq"] is not None else "")
                                  + " is not in the headers" + (" (nullable)" if f["nullable"] else ""),
                       "data": {"field": f["name"]}})
    exp_order = [f["name"].lower() for f in fields if f["name"].lower() in given]
    got_order = [h.lower() for h in headers if h.lower() in expected]
    if ordered and exp_order and got_order != exp_order and len(set(got_order)) == len(got_order):
        first = next(i for i, (g, e) in enumerate(zip(got_order, exp_order)) if g != e)
        window = slice(first, first + 4)
        issues.append({"severity": "warn", "kind": "field-order",
                       "message": "header order differs from the structure sequence: headers "
                                  + ", ".join(expected[g]["name"] for g in got_order[window]) + " … vs structure "
                                  + ", ".join(expected[e]["name"] for e in exp_order[window]) + " … (breaks positional / headerless loads)"})
    return issues


def check_target(fields, table_info, target, known_tables=None):
    """Structure rows of one definition vs. the real target table."""
    if not target:
        return []
    if table_info is None:
        if known_tables is not None and target.lower().split(".")[-1] not in known_tables:
            near = difflib.get_close_matches(target.lower().split(".")[-1], sorted(known_tables), n=1, cutoff=0.9)  # typos only
            return [{"severity": "error", "kind": "target-missing",
                     "message": f"target table '{target}' does not exist in the target database" + (f" (did you mean '{near[0]}'?)" if near else ""),
                     "data": {"target": target, "suggestion": near[0] if near else None}}]
        return [{"severity": "info", "kind": "target-undocumented", "message": f"target table '{target}' is not documented (no schema to compare)"}]
    issues = []
    cols = {c["name"].lower(): c for c in table_info["columns"]}
    names = {f["name"].lower() for f in fields}
    extra = [f["name"] for f in fields if f["name"].lower() not in cols]
    if extra:
        guess = {e: difflib.get_close_matches(e.lower(), list(cols), n=1, cutoff=0.75) for e in extra[:15]}
        issues.append({"severity": "error", "kind": "column-missing",
                       "message": f"structure field(s) with no column in {table_info['table']}: "
                                  + ", ".join(e + (f" (table has '{cols[g[0]]['name']}')" if g else "") for e, g in guess.items())
                                  + (f", … +{len(extra) - 15} more" if len(extra) > 15 else ""),
                       "data": {"pairs": [(e, cols[g[0]]["name"] if g else None) for e, g in guess.items()]}})
    required = [c["name"] for n, c in cols.items() if n not in names and not c["nullable"] and c.get("default") is None
                and "auto_increment" not in str(c.get("extra") or "").lower() and not str(c.get("default") or "").startswith("nextval")]
    if required:
        issues.append({"severity": "error", "kind": "required-column",
                       "message": f"NOT NULL column(s) of {table_info['table']} not in the structure: {', '.join(required[:15])}"
                                  + (f", … +{len(required) - 15} more" if len(required) > 15 else ""),
                       "data": {"columns": [(n, cols[n.lower()]["type"]) for n in required[:15]]}})
    per_kind = defaultdict(list)  # one issue per kind, with the field details, keeps wide tables readable
    per_data = defaultdict(list)
    for f in fields:
        c = cols.get(f["name"].lower())
        if not c:
            continue
        ff, cf = type_family(f["type"]), type_family(c["type"])
        if ff and cf and ff != cf:
            sev = "warn" if "string" in (ff, cf) else "error"
            per_kind[("type-mismatch", sev)].append(f"'{f['name']}' is {f['type']} in the structure but {c['type']} in {table_info['table']}")
            per_data[("type-mismatch", sev)].append((f["name"], c["type"]))
        tl = str_length(c["type"])
        if f.get("length") and tl and f["length"] > tl:
            per_kind[("length", "warn")].append(f"'{f['name']}' length {f['length']} in the structure > {c['type']} in {table_info['table']}")
            per_data[("length", "warn")].append((f["name"], tl))
        if f.get("nullable") and not c["nullable"] and c.get("default") is None:
            per_kind[("nullability", "warn")].append(f"'{f['name']}' is nullable in the structure but NOT NULL in {table_info['table']}")
            per_data[("nullability", "warn")].append((f["name"], None))
    labels = {"type-mismatch": "type differs", "length": "longer than the target column (truncation / load error)",
              "nullability": "nullable vs NOT NULL"}
    for (kind, sev), details in sorted(per_kind.items(), key=lambda kv: kv[0][1] != "error"):
        shown = "; ".join(details[:6]) + (f"; … +{len(details) - 6} more" if len(details) > 6 else "")
        prefix = f"{labels[kind]} for {len(details)} fields: " if len(details) > 1 else ""
        issues.append({"severity": sev, "kind": kind, "message": prefix + shown + ("" if prefix or kind != "length" else " (truncation / load error)"),
                       "data": {"items": per_data[(kind, sev)], "table": table_info["table"]}})
    seqs = [f["seq"] for f in fields if f["seq"] is not None]
    if len(seqs) != len(set(seqs)):
        dup = sorted({s for s in seqs if seqs.count(s) > 1})
        issues.append({"severity": "error", "kind": "duplicate-seq", "message": f"duplicate sequence number(s) in the structure: {dup}"})
    lower = [f["name"].lower() for f in fields]
    if len(lower) != len(set(lower)):
        issues.append({"severity": "error", "kind": "duplicate-field",
                       "message": f"duplicate field name(s) in the structure: {sorted({n for n in lower if lower.count(n) > 1})}"})
    return issues


def table_target(model, target):
    """Is this definition's target a database table we can check (not a file location, and a target database is set)?"""
    return bool(model.get("target_db")) and not FILE_TARGET.search(str(target))


def target_index(db_results, target_db):
    """{lower table name: table info} + set of all table names, for the target database."""
    d = next((x for x in db_results if x["name"] == target_db), None)
    if not d:
        return {}, None
    idx = {}
    for t in d.get("tables", []):
        idx[t["table"].lower()] = t
        idx[f"{t['schema']}.{t['table']}".lower()] = t
    known = {n.lower() for n in d.get("all_table_names", [])} or None
    return idx, known


def lint(model, rows, db_results):
    """One finding per definition row whose structure disagrees with its target table (or is empty)."""
    findings, checked = [], 0
    dt = model.get("definition_table")
    if not dt or not model.get("structure_table"):
        return findings, checked
    idx, known = target_index(db_results, model["target_db"])
    for d in rows.table(dt):
        checked += 1
        fields = structure_of(model, rows, d)
        label = definition_label(model, d)
        target = d.get(model.get("definition_target")) if model.get("definition_target") else None
        issues = []
        if not fields:
            issues.append({"severity": "warn", "kind": "no-structure", "message": f"no {model['structure_table']} rows"})
        elif target and table_target(model, target):
            issues += [i for i in check_target(fields, idx.get(str(target).lower()), str(target), known) if i["severity"] != "info"]
        if issues:
            sev = "error" if any(i["severity"] == "error" for i in issues) else "warn"
            findings.append({"severity": sev, "kind": "metadata-drift", "component_id": None,
                             "location": f"{dt}:{d.get(model['definition_id'])}",
                             "message": f"{label}" + (f" → {target}" if target else "") + ": " + "; ".join(i["message"] for i in issues)})
    return findings, checked


# ------------------------------------------------------------------------------------------------ lookup
def match_rows(model, rows, key):
    """Rows of any config table whose identifying columns equal / pattern-match `key` (a file name, table, feed, API...)."""
    base = PurePath(key.replace("\\", "/")).name if ("/" in key or "\\" in key) else key
    want = {norm(key), norm(base)}
    exact, pattern, candidates = [], [], set()
    struct = model.get("structure_table")
    for table, info in model["tables"].items():
        if table == struct:
            continue
        cols = [c for c in info["columns"] if KEY_COL.search(c) or TARGET_COL.search(c) or c in (model.get("definition_keys") or [])
                or c in info["pk"] or re.search(r"(?i)name|url|host|path|dir|pattern", c)]
        for r in rows.table(table):
            for c in cols:
                v = r.get(c)
                if v is None or v == "***" or isinstance(v, (int, float)) and c not in info["pk"]:
                    continue
                nv = norm(v)
                if not nv:
                    continue
                if nv in want:
                    exact.append({"table": table, "column": c, "row": r, "match": "exact"})
                    break
                if isinstance(v, str) and len(v) <= 300:
                    candidates.add(str(v))
                    if FILE_COL.search(c) or c in (model.get("definition_keys") or []):
                        rx = pattern_regex(v)
                        if rx and (rx.match(base) or rx.match(key)):
                            pattern.append({"table": table, "column": c, "row": r, "match": f"pattern '{v}'"})
                            break
    hits = exact or pattern
    return hits, ([] if hits else suggest(base, candidates))


def _shape(s):
    """'SALES_20260926.csv' and 'SALES_YYYYMMDD.csv' / 'SALES_*.csv' both become 'sales_#.csv' for fuzzy comparison."""
    s = DATE_RUN.sub("#", str(s))
    s = re.sub(r"\$\{[^}]*\}|#\{[^}]*\}|[*%?]+|\d+", "#", s)
    return re.sub("#+", "#", s).lower()


def suggest(key, candidates, n=6):
    shaped = defaultdict(list)
    for c in candidates:
        shaped[_shape(c)].append(c)
    out = []
    for s in difflib.get_close_matches(_shape(key), list(shaped), n=n, cutoff=0.6):
        out += shaped[s]
    for c in difflib.get_close_matches(key, sorted(candidates), n=n, cutoff=0.6):
        if c not in out:
            out.append(c)
    return out[:n]


def related(model, rows, table, row, depth=2, cap=50, _seen=None):
    """Rows linked to one row through the discovered relations (parents and children), breadth-first."""
    seen = _seen if _seen is not None else set()
    out = defaultdict(list)
    frontier = [(table, row)]
    seen.add((table, json.dumps(row, sort_keys=True, default=str)))
    for _ in range(depth):
        nxt = []
        for t, r in frontier:
            for rel in model["relations"]:
                if rel["child"] == t and rel["parent"] != model.get("structure_table"):
                    targets = rows.where(rel["parent"], rel["parent_column"], r.get(rel["child_column"]))
                    tt = rel["parent"]
                elif rel["parent"] == t and rel["child"] != model.get("structure_table"):
                    targets = rows.where(rel["child"], rel["child_column"], r.get(rel["parent_column"]))
                    tt = rel["child"]
                else:
                    continue
                if r.get(rel["child_column"] if rel["child"] == t else rel["parent_column"]) is None:
                    continue
                for x in targets[:cap]:
                    k = (tt, json.dumps(x, sort_keys=True, default=str))
                    if k in seen:
                        continue
                    seen.add(k)
                    out[tt].append(x)
                    nxt.append((tt, x))
        frontier = nxt
    return dict(out)


ROOT_COL = re.compile(r"(?i)root|json_?path|record_?path|data_?path")


def json_record(data, root=None):
    """The first record of a JSON payload, below root ('$.data', 'data.items', '$.response.rows[*]')."""
    node = data
    for part in [p for p in re.split(r"\.|/|\[[^\]]*\]", re.sub(r"^\$", "", root or "")) if p]:
        if isinstance(node, list):
            node = next((x for x in node if isinstance(x, dict)), {})
        node = node.get(part, {}) if isinstance(node, dict) else {}
    if isinstance(node, list):
        node = next((x for x in node if isinstance(x, dict)), {})
    return node if isinstance(node, dict) else {}


def flatten_keys(record, prefix=""):
    """{'a': {'b': 1}, 'c': [{'d': 2}]} -> ['a.b', 'c.d'] (arrays of objects: their first element)."""
    out = []
    for k, v in record.items():
        p = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict) and v:
            out += flatten_keys(v, p)
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            out += flatten_keys(v[0], p)
        else:
            out.append(p)
    return out


def root_path_for(model, def_row, related_rows):
    """The JSON root path configured for a definition: a root / json_path column on it or on a row linked to it."""
    links = _link_columns(model)
    ident = str(def_row.get(model.get("definition_id")))
    candidates = [def_row] + [r for t, rs in related_rows.items() for r in rs if links.get(t) and str(r.get(links[t])) == ident]
    for r in candidates:
        for c, v in r.items():
            if ROOT_COL.search(c) and isinstance(v, str) and v.strip() and v != "***":
                return v.strip()
    return None


def _sample_check(model, fields, def_row, related_rows, headers, sample):
    """Header issues for one definition, given explicit headers and / or a parsed sample ({kind, data}). The sample's own
    header / keys win over typed headers (a ticket often gives both, for the same file)."""
    from . import content
    if not sample:
        return check_headers(fields, list(headers)) if headers else [], None
    if sample["kind"] != "json":
        if not sample.get("path") or not fields:
            return check_headers(fields, list(sample["data"] or headers)), {"kind": sample["kind"], "fields": len(sample["data"])}
        data_issues, info = content.validate_csv(fields, sample["path"], model, def_row, related_rows)
        header = info.get("header_row")
        issues = check_headers(fields, list(header)) if header else (check_headers(fields, list(headers)) if headers else [])
        info.update(kind="csv", fields=len(header) if header else len(fields))
        return issues + data_issues, info
    root = root_path_for(model, def_row, related_rows)
    record = json_record(sample["data"], root)
    all_fields = fields
    if any(f.get("path") for f in fields):  # structure rows carry a JSON path per column: compare the payload to those
        fields = [dict(f, name=f["path"]) for f in fields if f.get("path")]
    paths = is_path_structure(fields)
    keys = flatten_keys(record) if paths else list(record)
    info = {"kind": "json", "root": root, "fields": len(keys), "paths": paths}
    if not record:
        return [{"severity": "error", "kind": "json-root", "message": f"no JSON record found in the sample below root path "
                                                                        f"'{root or '(top level)'}' - wrong root path or payload shape"}], info
    issues = check_headers(fields, list(keys or headers), ordered=False, paths=paths, root=root)
    data_issues, dinfo = content.validate_json(all_fields, content.json_records(sample["data"], root), root)
    info.update(dinfo)
    return issues + data_issues, info


def dossier(model, rows, key, headers=(), db_results=None, sample=None):
    """Everything the metadata knows about one file / table / feed / API, with checks."""
    hits, suggestions = match_rows(model, rows, key)
    result = {"key": key, "matches": [], "definitions": [], "related": {}, "suggestions": suggestions}
    seen, dt = set(), model.get("definition_table")
    idx, known = target_index(db_results or [], model.get("target_db"))
    def_rows = []
    for h in hits[:20]:
        result["matches"].append({"table": h["table"], "column": h["column"], "match": h["match"], "row": h["row"]})
        if h["table"] == dt:
            def_rows.append(h["row"])
        for t, rs in related(model, rows, h["table"], h["row"], _seen=seen).items():
            result["related"].setdefault(t, []).extend(rs)
            if t == dt:
                def_rows.extend(rs)
    uniq = {}
    for d in def_rows:
        uniq.setdefault(norm(d.get(model.get("definition_id"))), d)
    for d in list(uniq.values())[:10]:
        fields = structure_of(model, rows, d)
        target = d.get(model.get("definition_target")) if model.get("definition_target") else None
        location = d.get(model.get("definition_location")) if model.get("definition_location") else None
        if target and not table_target(model, target):
            location, target = location or target, None  # e.g. an HDFS / S3 path in the target column
        entry = {"id": d.get(model.get("definition_id")), "label": definition_label(model, d), "row": d, "target": target,
                 "location": location, "fields": fields, "issues": []}
        linked = {t: list(rs) for t, rs in result["related"].items()}
        for mt in result["matches"]:  # rows matched directly (e.g. the API row itself) belong to the definition too
            linked.setdefault(mt["table"], []).append(mt["row"])
        issues, entry["sample"] = _sample_check(model, fields, d, linked, headers, sample)
        entry["issues"] += issues
        if target:
            entry["issues"] += check_target(fields, idx.get(str(target).lower()), str(target), known)
        if not fields and model.get("structure_table"):
            entry["issues"].append({"severity": "error", "kind": "no-structure", "message": f"no {model['structure_table']} rows for this definition"})
        from . import fixes
        entry["fixes"] = fixes.suggest(model, entry)
        result["definitions"].append(entry)
    if dt in result["related"]:
        del result["related"][dt]
    return result


# ------------------------------------------------------------------------------------------------ change tracking
def _link_columns(model):
    """table -> column holding the definition id the row belongs to."""
    dt, st = model.get("definition_table"), model.get("structure_table")
    links = {}
    if dt and model.get("definition_id"):
        links[dt] = model["definition_id"]
    if st and model.get("structure_parent"):
        links[st] = model["structure_parent"]
    for rel in model.get("relations") or []:
        if rel["parent"] == dt and rel["child"] not in links:
            links[rel["child"]] = rel["child_column"]
    return links


def _short(v):
    s = "∅" if v is None else str(v)
    return s if len(s) <= 60 else s[:59] + "…"


def diff_rows(model, old, new, tables=None):
    """Row-level changes between two masked snapshots of the config tables: [{tbl, pk, link, change}].
    Rows are matched by primary key (tables without one only report added / removed rows). Masked values stay '***',
    so a changed secret is never revealed (and not reported)."""
    links = _link_columns(model)
    st, field = model.get("structure_table"), model.get("structure_field")
    out = []
    for t, info in model["tables"].items():
        if tables and t not in tables:
            continue
        if t not in old or t not in new:
            continue  # table newly tracked or not snapshotted: nothing to compare
        pk, link_col = info.get("pk") or [], links.get(t)

        def key(r):
            return "|".join(str(r.get(c)) for c in pk) if pk else json.dumps(r, sort_keys=True, default=str)

        def label(r):
            bits = [f"{link_col}={r.get(link_col)}"] if link_col and t != model.get("definition_table") else []
            if t == st and field and r.get(field) is not None:
                bits.append(str(r[field]))
            elif t == model.get("definition_table"):
                bits.append(definition_label(model, r))
            return f"{t}:{key(r) if pk else '?'}" + (f" ({', '.join(bits)})" if bits else "")

        o, n = {key(r): r for r in old[t]}, {key(r): r for r in new[t]}
        for k in sorted(set(n) - set(o)):
            r = n[k]
            out.append({"tbl": t, "pk": k if pk else None, "link": str(r.get(link_col)) if link_col else None,
                        "change": f"{label(r)} added: " + ", ".join(f"{c}={_short(v)}" for c, v in list(r.items())[:8] if v is not None)})
        for k in sorted(set(o) - set(n)):
            r = o[k]
            out.append({"tbl": t, "pk": k if pk else None, "link": str(r.get(link_col)) if link_col else None,
                        "change": f"{label(r)} removed"})
        if pk:
            for k in sorted(set(o) & set(n)):
                a, b = o[k], n[k]
                diffs = [f"{c} {_short(a.get(c))} → {_short(b.get(c))}" for c in sorted(set(a) | set(b))
                         if a.get(c) != b.get(c) and a.get(c) != "***" and b.get(c) != "***"]
                if diffs:
                    out.append({"tbl": t, "pk": k, "link": str(b.get(link_col)) if link_col else None,
                                "change": f"{label(b)}: " + "; ".join(diffs)})
    return out


# ------------------------------------------------------------------------------------------------ render
def render(model, rows, drift, checked, code_map=None):
    L = ["# Metadata (config tables)", "",
         f"Config tables in database `{model['db']}` that drive the flow. Rows are snapshotted (secrets masked) into `kb.sqlite`.",
         "Look up one file / table / feed / API: `python -m nifikb diagnose --file <name> [headers...]` (add `--live` for fresh rows).", ""]
    if model.get("guessed"):
        L.append(f"Auto-detected (check, and override in `[metadata]` of nifikb.toml if wrong): {', '.join(model['guessed'])}")
        L.append("")
    L.append("## Roles")
    if model.get("definition_table"):
        L.append(f"- definition table: `{model['definition_table']}` · id `{model.get('definition_id')}` · lookup keys "
                 f"{', '.join(f'`{k}`' for k in model.get('definition_keys') or []) or '(none)'} · target table column `{model.get('definition_target') or '(none)'}`"
                 + (f" · location column `{model['definition_location']}`" if model.get("definition_location") else "")
                 + ("" if model.get("target_db") else " · target checks off (loads go to files: target_db = none)"))
    else:
        L.append("- definition table: **not detected** (set `definition_table` in `[metadata]`)")
    if model.get("structure_table"):
        L.append(f"- structure table: `{model['structure_table']}` · parent `{model.get('structure_parent')}` · field `{model.get('structure_field')}` · "
                 f"type `{model.get('structure_type') or '-'}` · order `{model.get('structure_order') or '-'}` · length `{model.get('structure_length') or '-'}` · "
                 f"nullable `{model.get('structure_nullable') or '-'}`" + (" (flag means required)" if model.get("nullable_means_required") else "")
                 + (f" · JSON path `{model['structure_path']}`" if model.get("structure_path") else ""))
    else:
        L.append("- structure table: **not detected** (set `structure_table` / `structure_field` / `structure_parent` in `[metadata]`)")
    L += ["", "## Config tables", "| Table | Rows | Primary key | Columns |", "|---|---|---|---|"]
    for t, info in sorted(model["tables"].items()):
        n, in_db = len(rows.table(t)), info.get("rows")
        cols = ", ".join(info["columns"])
        count = f"{n}" if in_db is None or in_db == n else f"{n} (~{in_db} in db)"
        L.append(f"| {t} | {count} | {', '.join(info['pk']) or '-'} | {cols if len(cols) < 400 else cols[:399] + '…'} |")
    L += ["", "## Relations", ""]
    for r in model["relations"] or []:
        L.append(f"- `{r['child']}.{r['child_column']}` → `{r['parent']}.{r['parent_column']}` ({r['source']})")
    if not model["relations"]:
        L.append("- none found (declare them with `[[metadata.relations]]`)")
    L += ["", "## Custom code that reads these tables", ""]
    for fqcn, tables in sorted((code_map or {}).items()):
        L.append(f"- `{fqcn}` ([doc](custom-code/{fqcn.rsplit('.', 1)[-1]}.md)): {', '.join(tables)}")
    if not code_map:
        L.append("- none found in the configured code repos (add the custom processor repos to `[code] repos`)")
    L += ["", f"## Definitions vs. target tables ({checked} checked, {len(drift)} with problems)", ""]
    errors = [f for f in drift if f["severity"] == "error"]
    for f in (errors + [f for f in drift if f["severity"] != "error"])[:150]:
        L.append(f"- **{f['severity']}** `{f['location']}` {f['message']}")
    if len(drift) > 150:
        L.append(f"- … {len(drift) - 150} more: `python -m nifikb issues --kind metadata-drift`")
    if not drift and checked:
        L.append("- all definitions match their target tables")
    dt = model.get("definition_table")
    if dt and rows.table(dt) and len(rows.table(dt)) <= 500:
        L += ["", "## All definitions", "| Id | Keys | Target | Fields |", "|---|---|---|---|"]
        for d in rows.table(dt):
            keys = " · ".join(f"{k}={d.get(k)}" for k in model.get("definition_keys") or [] if d.get(k) is not None)
            L.append(f"| {d.get(model.get('definition_id'))} | {keys} | {d.get(model.get('definition_target')) if model.get('definition_target') else ''} | "
                     f"{len(structure_of(model, rows, d))} |")
    return "\n".join(L) + "\n"
