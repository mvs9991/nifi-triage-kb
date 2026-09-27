"""Minimal SQL helpers: detect SQL text and pull out the table names it reads or writes."""
import re

_SQL_START = re.compile(r"^\s*(?:\(|/\*.*?\*/\s*)*(select|insert|update|delete|merge|with|upsert|replace|create|alter|truncate|drop|call|exec)\b", re.I | re.S)
_SQL_SHAPE = re.compile(r"(?is)\bselect\b.+\bfrom\b|\binsert\s+(?:ignore\s+)?into\b|\bupdate\b\s+\S+\s+set\b|\bdelete\s+from\b|\bmerge\s+into\b"
                        r"|\b(?:create|alter|drop|truncate)\s+table\b|\breplace\s+into\b")
_TABLE_REF = re.compile(
    r"(?is)\b(?P<kw>from|join|into|update|merge\s+into|delete\s+from|truncate(?:\s+table)?|(?:create|alter|drop)\s+table(?:\s+if\s+(?:not\s+)?exists)?|using)"
    r"\s+(?P<name>(?:[`\"\[]?[\w$#{}.\-]+[`\"\]]?\.){0,2}[`\"\[]?[\w$#{}\-]+[`\"\]]?)"
)
_NOT_TABLES = {"select", "set", "values", "where", "lateral", "unnest", "dual", "as", "on", "table", "only", "the",
               "a", "an", "ignore", "if", "exists", "not"}


def looks_like_sql(text):
    text = (text or "").strip()
    return len(text) > 12 and bool(_SQL_START.match(text)) and bool(_SQL_SHAPE.search(text))


def tables(sql):
    """Table names referenced by a SQL string (lower-cased, quotes stripped, EL placeholders kept)."""
    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql or "", flags=re.S)
    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
    ctes = {m.lower() for m in re.findall(r"(?i)(?:\bwith|,)\s*(\w+)\s+as\s*\(", sql)}
    out = []
    for m in _TABLE_REF.finditer(sql):
        name = re.sub(r"[`\"\[\]]", "", m.group("name")).strip(".").lower()
        if not name or name in _NOT_TABLES or name in ctes or name.startswith("(") or name.isdigit():
            continue
        if m.group("kw").lower() == "using" and not re.search(r"(?i)merge", sql):
            continue
        if name not in out:
            out.append(name)
    return out
