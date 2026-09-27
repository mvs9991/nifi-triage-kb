"""New-feed validator: check proposed config rows (definition, structure, feed / API / server rows) before anyone inserts
them - against the config tables' own schema, the existing rows, the target table, an example file name and a sample.

The proposal is a TOML (or JSON) file with the rows in the config tables' own column names:

    example_file = "INVOICE_20260927.csv"   # a real file name the definition must match
    sample = "INVOICE_20260927.csv"         # optional: sample file for content checks
    like = "SALES_YYYYMMDD.csv"             # optional: an existing, similar feed to compare with
    structure_csv = "invoice_columns.csv"   # optional: structure rows as CSV (header = column names), instead of [[structure]]

    [definition]
    FILE_NAME = "INVOICE_YYYYMMDD.csv"
    TABLE_NAME = "stg_invoice"

    [[structure]]
    COL_NAME = "INV_NO"
    DATA_TYPE = "INTEGER"
    COL_SEQ = 1

    [[rows.SOURCE_FEED_CONFIG]]
    FEED_NAME = "erp_invoice_feed"

Nothing is written anywhere: the result lists problems and INSERT statements for a human to review and run."""
import csv
import difflib
import json
import re
import tomllib
from pathlib import Path

from . import db as dbmod, metadata as metamod
from .fixes import quote

NEW_ID = "<new id>"
INT_TYPES = re.compile(r"(?i)^(tiny|small|medium|big)?int(eger)?\b|^number\(\d+\)$|^serial")
NUM_TYPES = re.compile(r"(?i)^(decimal|numeric|number|float|double|real)")
KNOWN_TYPES = re.compile(r"(?i)^(var)?char|^n?varchar|^string|^text|^clob|^(tiny|small|medium|big)?int|^integer|^long|^short|^byte|"
                         r"^decimal|^numeric|^number|^float|^double|^real|^bool|^bit|^date|^time|^timestamp|^datetime|^binary|"
                         r"^varbinary|^blob|^json|^array|^struct|^map|^uuid")


def load_proposal(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text) if path.suffix.lower() == ".json" else tomllib.loads(text)
    base = path.parent
    for k in ("sample", "structure_csv"):
        if data.get(k) and not Path(data[k]).is_absolute():
            data[k] = str((base / data[k]).resolve())
    if data.get("structure_csv"):
        with open(data["structure_csv"], newline="", encoding="utf-8-sig") as f:
            data["structure"] = [{k: (v if v != "" else None) for k, v in r.items() if k} for r in csv.DictReader(f)]
    return data


def _schema(store, db, table, model):
    """Column details of a config table ({lower name: column}) from the documented schema, or names only."""
    row = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=?", (db, table.lower())).fetchone()
    if row:
        return {c["name"].lower(): c for c in json.loads(row["data"])["columns"]}
    return {c.lower(): {"name": c, "type": None, "nullable": True, "default": None} for c in model["tables"][table]["columns"]}


def _real_table(model, name):
    return next((t for t in model["tables"] if t.lower() == str(name).lower()), None)


def _check_row(table, row, schema, pk, existing, label):
    """Column names, required columns, value types / lengths and primary-key collisions of one proposed row.
    Returns (row with the table's own column spelling, issues)."""
    issues, fixed = [], {}
    for k, v in row.items():
        c = schema.get(k.lower())
        if not c:
            near = difflib.get_close_matches(k.lower(), list(schema), n=1, cutoff=0.7)
            issues.append(("error", "unknown-column", f"{label}: {table} has no column '{k}'"
                           + (f" (did you mean '{schema[near[0]]['name']}'?)" if near else "")))
            continue
        fixed[c["name"]] = v
        if v is None or v == NEW_ID or not c.get("type"):
            continue
        t = str(c["type"])
        if INT_TYPES.search(t) and not re.fullmatch(r"-?\d+", str(v).strip()):
            issues.append(("error", "value-type", f"{label}: {c['name']} = {quote(v)} is not an integer ({t})"))
        elif NUM_TYPES.search(t) and not re.fullmatch(r"-?\d+(\.\d+)?", str(v).strip()):
            issues.append(("error", "value-type", f"{label}: {c['name']} = {quote(v)} is not a number ({t})"))
        n = metamod.str_length(t)
        if n and len(str(v)) > n:
            issues.append(("error", "value-length", f"{label}: {c['name']} is {len(str(v))} characters, the column allows {n} ({t})"))
        if dbmod.sensitive_column(c["name"]) and v not in ("***", "", None):
            issues.append(("warn", "secret-in-proposal", f"{label}: {c['name']} holds a secret - leave it out of the proposal "
                                                          "and let the DBA set it"))
            fixed[c["name"]] = "***"
    have = {k.lower() for k in fixed}
    for n, c in schema.items():
        if n in have or c.get("nullable", True) or c.get("default") is not None:
            continue
        if "auto_increment" in str(c.get("extra") or "").lower() or str(c.get("default") or "").startswith("nextval"):
            continue
        if n in [p.lower() for p in pk] and len(pk) == 1 and "int" in str(c.get("type") or "").lower():
            issues.append(("info", "id-not-given", f"{label}: {c['name']} not given - fine if the database generates it, "
                                                   "otherwise pick the next free id"))
            continue
        issues.append(("error", "required-column", f"{label}: {table}.{c['name']} is NOT NULL and has no default, but is not set"))
    if pk and all(fixed.get(p) is not None for p in pk):
        key = "|".join(str(fixed[p]) for p in pk)
        if key in existing:
            issues.append(("error", "duplicate-key", f"{label}: {table}:{key} already exists"))
    return fixed, issues


def _structure_checks(fields, model):
    issues = []
    seqs = [f["seq"] for f in fields if f["seq"] is not None]
    if model.get("structure_order"):
        missing = [f["name"] for f in fields if f["seq"] is None]
        if missing:
            issues.append(("error", "missing-seq", f"no {model['structure_order']} for: {', '.join(missing[:10])}"))
        dup = sorted({s for s in seqs if seqs.count(s) > 1})
        if dup:
            issues.append(("error", "duplicate-seq", f"duplicate {model['structure_order']} value(s): {dup}"))
        if seqs and sorted(set(seqs)) != list(range(min(seqs), min(seqs) + len(set(seqs)))):
            issues.append(("warn", "seq-gap", f"{model['structure_order']} has gaps: {sorted(set(seqs))} (files are read by position)"))
    names = [f["name"].lower() for f in fields]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        issues.append(("error", "duplicate-field", f"duplicate field name(s): {dup}"))
    for f in fields:
        if f["name"] != f["name"].strip():
            issues.append(("error", "field-whitespace", f"field '{f['name']}' has leading / trailing blanks"))
        if model.get("structure_type"):
            if not f["type"]:
                issues.append(("error", "missing-type", f"no {model['structure_type']} for '{f['name']}'"))
            elif not KNOWN_TYPES.search(str(f["type"]).strip()):
                issues.append(("warn", "unknown-type", f"'{f['name']}': type '{f['type']}' is not a usual type name"))
            elif metamod.type_family(f["type"]) == "string" and model.get("structure_length") and not f.get("length") \
                    and not metamod.str_length(f["type"]) and not re.search(r"(?i)text|clob|string", str(f["type"])):
                issues.append(("warn", "missing-length", f"'{f['name']}' is {f['type']} without a length"))
    return issues


def validate(cfg, store, proposal, live=False):
    """Check a proposal (see the module doc). Returns {issues: [(severity, kind, message)], inserts: [sql], ...}."""
    from .diagnose import _target_results, read_sample
    m = metamod.settings(cfg)
    model = store.get_meta("metadata_model")
    if not m or not model or not model.get("definition_table"):
        return {"error": "metadata is not configured or no definition table was detected ([metadata] in nifikb.toml, then build)"}
    dt, st = model["definition_table"], model.get("structure_table")
    did, parent = model.get("definition_id"), model.get("structure_parent")
    if live:
        dcfg = metamod.db_config(cfg, m["db"])
        rows_by_table = metamod.fetch_live(dcfg, m, model)
    else:
        rows_by_table = store.get_meta_rows(exclude=st)
    rows = metamod.Rows(rows_by_table)
    issues, inserts = [], []

    def pk_set(table):
        pk = model["tables"][table].get("pk") or []
        return pk, {"|".join(str(r.get(p)) for p in pk) for r in rows.table(table)} if pk else set()

    # ---- the definition row
    definition = dict(proposal.get("definition") or {})
    if not definition:
        return {"error": f"the proposal has no [definition] section (one {dt} row)"}
    pk, existing = pk_set(dt)
    drow, found = _check_row(dt, definition, _schema(store, m["db"], dt, model), pk, existing, "definition")
    issues += found
    new_id = drow.get(did) if did else None
    link_value = new_id if new_id is not None else NEW_ID
    drow_for_checks = dict(drow, **({did: link_value} if did else {}))
    label = metamod.definition_label(model, drow_for_checks)

    # names: does the definition match the example file, and would any existing definition match it too?
    keys = [k for k in model.get("definition_keys") or [] if drow.get(k)]
    if not keys:
        issues.append(("error", "no-key", f"none of the matching columns {model.get('definition_keys')} is set - the flow cannot find this definition"))
    example = proposal.get("example_file") or (Path(proposal["sample"]).name if proposal.get("sample") else None)
    if example:
        rx = [(k, metamod.pattern_regex(drow[k])) for k in keys if metamod.FILE_COL.search(k) or len(keys) == 1]
        if rx and not any(r and (r.match(example) or metamod.norm(drow[k]) == metamod.norm(example)) for k, r in rx):
            issues.append(("error", "pattern-mismatch", f"{', '.join(f'{k} {quote(drow[k])}' for k, _ in rx)} does not match the example "
                                                        f"file '{example}' - the flow would not pick it up"))
        hits, _ = metamod.match_rows(model, rows, example)
        clash = sorted({str(h["row"].get(did)) for h in hits if h["table"] == dt and str(h["row"].get(did)) != str(new_id)})
        if clash:
            issues.append(("error", "ambiguous-match", f"'{example}' already matches existing {dt} row(s) {', '.join(f'{dt}:{c}' for c in clash)} "
                                                       "- two definitions for one file"))
    for k in keys:
        if k == model.get("definition_target"):
            continue  # many definitions may load one table
        same = [r for r in rows.table(dt) if metamod.norm(r.get(k)) == metamod.norm(drow[k]) and str(r.get(did)) != str(new_id)]
        if same:
            issues.append(("error", "duplicate-name", f"{k} {quote(drow[k])} is already used by {dt}:{same[0].get(did)}"))
    inserts.append(_insert(dt, drow))

    # ---- structure rows
    fields = []
    if st:
        srows = []
        spk, sexisting = pk_set(st)
        sschema = _schema(store, m["db"], st, model)
        for i, r in enumerate(proposal.get("structure") or [], 1):
            r = dict(r)
            if parent and not any(k.lower() == parent.lower() for k in r):
                r[parent] = link_value
            fixed, found = _check_row(st, r, sschema, spk, sexisting, f"{st} row {i}")
            issues += found
            if parent and str(fixed.get(parent)) not in (str(link_value),):
                issues.append(("error", "wrong-parent", f"{st} row {i}: {parent} = {quote(fixed.get(parent))}, the definition is {quote(link_value)}"))
            srows.append(fixed)
        if not srows:
            issues.append(("error", "no-structure", f"no {st} rows in the proposal - the flow would have no column list"))
        fields = metamod.structure_of(model, metamod.Rows({st: srows}), drow_for_checks)
        issues += _structure_checks(fields, model)
        inserts += [_insert(st, r) for r in srows]

    # ---- related rows (feed / API / server config)
    links = metamod._link_columns(model)
    linked = {}
    for table, rs in (proposal.get("rows") or {}).items():
        real = _real_table(model, table)
        if not real:
            issues.append(("error", "unknown-table", f"'{table}' is not one of the config tables ({', '.join(sorted(model['tables']))})"))
            continue
        rpk, rexisting = pk_set(real)
        rschema = _schema(store, m["db"], real, model)
        for i, r in enumerate(rs if isinstance(rs, list) else [rs], 1):
            r = dict(r)
            lc = links.get(real)
            if lc and not any(k.lower() == lc.lower() for k in r):
                r[lc] = link_value
            fixed, found = _check_row(real, r, rschema, rpk, rexisting, f"{real} row {i}")
            issues += found
            linked.setdefault(real, []).append(fixed)
            inserts.append(_insert(real, fixed))

    # ---- compared with a similar, existing feed
    if proposal.get("like"):
        issues += _compare_like(model, rows, proposal["like"], drow, fields, linked, links, store, m)

    # ---- target
    target = drow.get(model.get("definition_target")) if model.get("definition_target") else None
    if target and metamod.table_target(model, target) and fields:
        db_results = _target_results(store, model, {"definitions": [{"target": target}]})
        idx, known = metamod.target_index(db_results, model["target_db"])
        for i in metamod.check_target(fields, idx.get(str(target).lower()), str(target), known):
            issues.append((i["severity"], i["kind"], f"target {target}: {i['message']}"))
    elif target and not metamod.table_target(model, target):
        issues.append(("info", "file-target", f"loads to {target} (a file location - not checked against a table)"))
    elif model.get("definition_target") and not target:
        issues.append(("warn", "no-target", f"{model['definition_target']} is not set"))

    # ---- sample content
    sample_info = None
    if proposal.get("sample") and not Path(proposal["sample"]).is_file():
        issues.append(("warn", "sample-missing", f"sample file {proposal['sample']} not found - content not checked"))
    elif proposal.get("sample") and fields:
        sample = read_sample(proposal["sample"])
        found, sample_info = metamod._sample_check(model, fields, drow_for_checks, linked, [], sample)
        issues += [(i["severity"], i["kind"], f"sample: {i['message']}") for i in found]
    rank = {"error": 0, "warn": 1, "info": 2}
    issues.sort(key=lambda x: rank.get(x[0], 3))
    return {"label": label, "definition": drow, "fields": fields, "issues": issues, "inserts": inserts, "sample": sample_info,
            "live": live, "id_given": new_id is not None}


def _compare_like(model, rows, like, drow, fields, linked, links, store, m):
    dt, did = model["definition_table"], model.get("definition_id")
    tmpl = metamod.dossier(model, rows, like)["definitions"]
    if not tmpl:
        return [("warn", "like-not-found", f"'{like}' matches no existing definition to compare with")]
    t = tmpl[0]
    out = []
    unset = [c for c, v in t["row"].items() if v not in (None, "") and c != did and drow.get(c) in (None, "")]
    if unset:
        out.append(("warn", "like-columns", f"{dt}:{t['id']} ({t['label']}) sets {', '.join(unset)} - the proposal leaves them empty"))
    st = model.get("structure_table")
    if st:
        struct = store.get_structure_rows(st, model["structure_parent"], [t["id"]])
        tfields = metamod.structure_of(model, metamod.Rows({st: struct}), t["row"])
        attrs = {"structure_type": "type", "structure_length": "length", "structure_nullable": "nullable", "structure_path": "path"}
        tset = {model[role] for role in attrs if model.get(role) and any(r.get(model[role]) not in (None, "") for r in struct)}
        pset = {model[role] for role, attr in attrs.items() if model.get(role) and any(f.get(attr) not in (None, "") for f in fields)}
        missing = sorted(tset - pset)
        if tfields and missing:
            out.append(("warn", "like-structure", f"the structure rows of {t['label']} fill {', '.join(missing)} - the proposal does not"))
    for table, col in links.items():
        if table in (dt, st):
            continue
        has = [r for r in rows.table(table) if str(r.get(col)) == str(t["id"])]
        if has and not linked.get(table):
            out.append(("warn", "like-related", f"{t['label']} has {len(has)} {table} row(s) - the proposal has none"))
    return out


def _insert(table, row):
    cols = [c for c, v in row.items() if v is not None]
    vals = ["/* set by DBA */ NULL" if row[c] == "***" else "/* new id */ NULL" if row[c] == NEW_ID else quote(row[c]) for c in cols]
    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)});"


def format_report(res):
    if res.get("error"):
        return res["error"]
    errors = sum(1 for i in res["issues"] if i[0] == "error")
    warns = sum(1 for i in res["issues"] if i[0] == "warn")
    L = [f"# New feed check: {res['label']} ({len(res['fields'])} structure fields) - "
         + ("READY to insert" if not errors else f"{errors} error(s) to fix first") + (f", {warns} warning(s)" if warns else "")
         + (" [config rows read live]" if res["live"] else " [compared with the KB snapshot]")]
    if res["issues"]:
        L.append("")
        L += [f"- {sev.upper()} {kind}: {msg}" for sev, kind, msg in res["issues"]]
    if res.get("sample"):
        s = res["sample"]
        L.append("")
        L.append("sample: " + ", ".join(f"{k}={v}" for k, v in s.items() if k in ("kind", "fields", "rows", "delimiter", "root", "records")))
    L.append("")
    L.append("## INSERT statements (review first - nifikb never runs them)")
    if not res["id_given"]:
        L.append("-- the definition id is not given: after the first INSERT, put the generated id where it says /* new id */")
    L += res["inserts"]
    return "\n".join(L)
