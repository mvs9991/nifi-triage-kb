"""Proposed fixes for config-side problems, as SQL for a human to review and run (nifikb never runs them).

Each proposal says who should act: often the right fix is the sender correcting the file, not us changing the metadata;
the SQL is then offered only as the alternative."""


def quote(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def _where(key):
    return " AND ".join(f"{c} = {quote(v)}" for c, v in key.items()) or "1 = 0"


def suggest(model, entry):
    st, dt = model.get("structure_table"), model.get("definition_table")
    col = {k: model.get(k) for k in ("structure_field", "structure_type", "structure_length", "structure_nullable", "structure_order",
                                     "structure_parent", "definition_id", "definition_target")}
    fields = {f["name"].lower(): f for f in entry.get("fields") or []}
    out, seen = [], set()

    def add(why, who, sql, note=""):
        if sql and sql not in seen:
            seen.add(sql)
            out.append({"why": why, "who": who, "sql": sql, "note": note})

    required_flag = "'Y'" if model.get("nullable_means_required") else "'N'"
    optional_flag = "'N'" if model.get("nullable_means_required") else "'Y'"
    for i in entry.get("issues") or []:
        d, kind = i.get("data") or {}, i["kind"]
        if kind == "header-name" and st and col["structure_field"]:
            f = fields.get(str(d.get("field", "")).lower())
            if f:
                add(f"header '{d['header']}' vs structure '{f['name']}'", "sender (preferred) or config",
                    f"UPDATE {st} SET {col['structure_field']} = {quote(d['header'])} WHERE {_where(f['key'])};",
                    f"prefer asking the sender to send '{f['name']}'; change the row only if '{d['header']}' is the agreed name "
                    f"(and if {col['structure_field']} is also the target column name, the target column must match)")
        elif kind == "length" and st and col["structure_length"]:
            for name, table_len in d.get("items") or []:
                f = fields.get(name.lower())
                if f:
                    add(f"'{name}' longer in the structure than in {d.get('table')}", "config (or widen the target column)",
                        f"UPDATE {st} SET {col['structure_length']} = {table_len} WHERE {_where(f['key'])};",
                        f"or widen the column instead: ALTER TABLE {d.get('table')} MODIFY {name} VARCHAR({f['length']}) - decide which "
                        "length is right")
        elif kind == "type-mismatch" and st and col["structure_type"]:
            for name, table_type in d.get("items") or []:
                f = fields.get(name.lower())
                if f:
                    add(f"'{name}' type differs from {d.get('table')}", "config",
                        f"UPDATE {st} SET {col['structure_type']} = {quote(str(table_type).split('(')[0].upper())} WHERE {_where(f['key'])};",
                        "check the type name convention used in the structure table before running")
        elif kind == "nullability" and st and col["structure_nullable"]:
            for name, _ in d.get("items") or []:
                f = fields.get(name.lower())
                if f:
                    add(f"'{name}' nullable in the structure but NOT NULL in {d.get('table')}", "config",
                        f"UPDATE {st} SET {col['structure_nullable']} = {required_flag} WHERE {_where(f['key'])};",
                        "use the flag values the table already uses (Y/N, 1/0, ...)")
        elif kind == "required-column" and st and col["structure_parent"] and col["structure_field"]:
            seqs = [f["seq"] for f in entry.get("fields") or [] if f.get("seq") is not None]
            nxt = (max(seqs) if seqs else 0) + 1
            for n, (name, typ) in enumerate(d.get("columns") or []):
                cols = [col["structure_parent"], col["structure_field"]]
                vals = [quote(entry.get("id")), quote(name)]
                for key, val in (("structure_type", quote(str(typ).split("(")[0].upper())), ("structure_order", str(nxt + n)),
                                 ("structure_nullable", required_flag)):
                    if col[key]:
                        cols.append(col[key])
                        vals.append(val)
                add(f"NOT NULL column '{name}' is never supplied", "config (or give the column a default)",
                    f"INSERT INTO {st} ({', '.join(cols)}) VALUES ({', '.join(vals)});",
                    "only if the file really carries this value; if NiFi / the load sets it, give the table column a DEFAULT instead")
        elif kind == "column-missing" and st and col["structure_field"]:
            for name, table_col in d.get("pairs") or []:
                f = fields.get(str(name).lower())
                if f and table_col:
                    add(f"structure field '{name}' has no column; the table has '{table_col}'", "config",
                        f"UPDATE {st} SET {col['structure_field']} = {quote(table_col)} WHERE {_where(f['key'])};",
                        "if the field is really the same column")
        elif kind == "missing-field" and i["severity"] == "error" and st and col["structure_nullable"]:
            f = fields.get(str(d.get("field", "")).lower())
            if f:
                add(f"mandatory field '{f['name']}' missing from the file", "sender (preferred) or config",
                    f"UPDATE {st} SET {col['structure_nullable']} = {optional_flag} WHERE {_where(f['key'])};",
                    "prefer asking the sender to include it; make it optional only if the business agrees")
        elif kind == "target-missing" and dt and col["definition_target"] and d.get("suggestion"):
            add(f"target table '{d['target']}' does not exist", "config",
                f"UPDATE {dt} SET {col['definition_target']} = {quote(d['suggestion'])} WHERE {col['definition_id']} = {quote(entry.get('id'))};",
                "or create the table if the name is right")
        elif kind == "data-delimiter" and dt and d.get("column") and col["definition_id"]:
            add(f"the file uses {d['delimiter']!r}", "sender (preferred) or config",
                f"UPDATE {dt} SET {d['column']} = {quote(d['delimiter'])} WHERE {col['definition_id']} = {quote(entry.get('id'))};",
                "only if the sender changed the format on purpose and will keep it; otherwise ask them to send the agreed delimiter")
    return out


def format_fixes(fixes, indent="  "):
    if not fixes:
        return []
    L = [f"{indent}proposed fixes (review first - nifikb never runs them):"]
    for f in fixes:
        L.append(f"{indent}  -- {f['why']} [{f['who']}]" + (f": {f['note']}" if f.get("note") else ""))
        L.append(f"{indent}  {f['sql']}")
    return L
