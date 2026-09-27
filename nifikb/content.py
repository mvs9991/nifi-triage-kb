"""Content validation of a sample file against the structure rows: not only the header, every row.

Most "metadata" tickets are data-vs-metadata problems: a delimiter inside a value shifting the columns, an empty
mandatory field, text in a numeric column, a date in another format, a value longer than the column, a file that is not
UTF-8. This reads a sample (CSV / delimited text or JSON) and reports each problem with counts and the first examples.
"""
import csv
import io
import re
from datetime import datetime
from pathlib import Path

from . import metadata as metamod

DELIM_COL = re.compile(r"(?i)delim|separator|(^|_)sep$|field_?sep")
DELIM_NAMES = {"TAB": "\t", "\\T": "\t", "PIPE": "|", "COMMA": ",", "SEMICOLON": ";", "CARET": "^", "TILDE": "~", "SPACE": " "}
DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f", "%Y/%m/%d",
                "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%m/%d/%Y %H:%M", "%d.%m.%Y", "%Y%m%d", "%Y%m%d%H%M%S", "%d-%b-%Y", "%d-%b-%y",
                "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")
NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
INT_RE = re.compile(r"^[+-]?\d+$")
MAX_ROWS = 20000
EXAMPLES = 3


def delimiter_for(model, def_row, related_rows, sample_text):
    """The configured delimiter (a DELIMITER-like column on the definition or a linked row), else sniffed."""
    for r in [def_row] + [x for rs in (related_rows or {}).values() for x in rs]:
        for c, v in r.items():
            if DELIM_COL.search(c) and isinstance(v, str) and v:
                v = DELIM_NAMES.get(v.strip().upper(), v)
                v = {"\\t": "\t", "\\u0001": "\x01", "\\x01": "\x01"}.get(v, v)
                return v, f"configured in {c}"
    try:
        return csv.Sniffer().sniff(sample_text[:20000], delimiters=",|\t;~^").delimiter, "detected"
    except csv.Error:
        return ",", "default"


def read_text(path):
    """(text, notes): UTF-8 with a fallback, noting a BOM, non-UTF-8 bytes and mixed line endings."""
    raw = Path(path).read_bytes()[:50_000_000]
    notes = []
    if raw.startswith(b"\xef\xbb\xbf"):
        notes.append({"severity": "warn", "kind": "data-encoding",
                      "message": "file starts with a UTF-8 byte-order mark (BOM): the first header can become '\\ufeffNAME' and not match"})
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        text = raw.decode("cp1252", errors="replace")
        notes.append({"severity": "error", "kind": "data-encoding",
                      "message": f"file is not valid UTF-8 (first bad byte at offset {e.start}); it looks like Windows-1252 / Latin-1 - "
                                 "accented characters will be garbled or rejected"})
    crlf, lf = raw.count(b"\r\n"), raw.count(b"\n")
    if crlf and lf - crlf > 1:
        notes.append({"severity": "warn", "kind": "data-encoding", "message": f"mixed line endings ({crlf} CRLF, {lf - crlf} LF)"})
    return text, notes


def _is_date(v):
    v = v.strip()
    for fmt in DATE_FORMATS:
        try:
            datetime.strptime(v, fmt)
            return True
        except ValueError:
            continue
    return False


class _Col:
    def __init__(self, field):
        self.f = field
        self.problems = {}  # kind -> [count, examples]

    def hit(self, kind, row_no, value):
        entry = self.problems.setdefault(kind, [0, []])
        entry[0] += 1
        if len(entry[1]) < EXAMPLES:
            entry[1].append(f"row {row_no}: {str(value)[:40]!r}")

    def check(self, row_no, value):
        f = self.f
        v = "" if value is None else str(value)
        if v.strip() == "":
            if f.get("nullable") is False:
                self.hit("data-mandatory", row_no, v)
            return
        family = metamod.type_family(f.get("type"))
        if family == "numeric":
            s = v.strip().replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", v.strip()) else v.strip()
            if not NUMBER_RE.match(s):
                self.hit("data-type", row_no, v)
            elif re.search(r"(?i)int|long|short|byte|serial", str(f.get("type"))) and not INT_RE.match(s):
                self.hit("data-type", row_no, v)
        elif family == "temporal" and not _is_date(v):
            self.hit("data-date", row_no, v)
        elif family == "bool" and v.strip().lower() not in ("true", "false", "0", "1", "y", "n", "yes", "no", "t", "f"):
            self.hit("data-type", row_no, v)
        if f.get("length") and len(v) > f["length"]:
            self.hit("data-length", row_no, v)

    def issues(self, total):
        labels = {"data-mandatory": ("error", "is empty but mandatory"), "data-type": ("error", f"is not a valid {self.f.get('type')}"),
                  "data-date": ("error", f"is not a recognisable date / time ({self.f.get('type')})"),
                  "data-length": ("error", f"is longer than {self.f.get('length')} characters")}
        out = []
        for kind, (n, ex) in self.problems.items():
            sev, what = labels[kind]
            out.append({"severity": sev, "kind": kind,
                        "message": f"'{self.f['name']}' {what} in {n} of {total} rows (e.g. {'; '.join(ex)})"})
        return out


def _rows(text, delim, max_rows):
    out = []
    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim)):
        if i > max_rows:
            break
        if row and any(c.strip() for c in row):
            out.append((i + 1, row))
    return out


def validate_csv(fields, path, model=None, def_row=None, related=None, max_rows=MAX_ROWS):
    text, issues = read_text(path)
    delim, how = delimiter_for(model or {}, def_row or {}, related, text)
    rows = _rows(text, delim, max_rows)
    if rows and len(rows[0][1]) == 1 and len(fields) > 1:  # wrong delimiter: find the one the file really uses
        for cand in ",|\t;~^\x01":
            if cand != delim and len(rows[0][1][0].split(cand)) >= 2:
                issues.append({"severity": "error", "kind": "data-delimiter",
                               "message": f"the file is delimited by {cand!r}, but the delimiter is {delim!r} ({how}) - every row "
                                          "reads as a single column. Checked below with the file's own delimiter.",
                               "data": {"delimiter": cand, "column": how[len("configured in "):] if how.startswith("configured in ") else None}})
                delim, how, rows = cand, "found in the file", _rows(text, cand, max_rows)
                break
    if not rows:
        return issues + [{"severity": "error", "kind": "data-empty", "message": "the sample has no rows"}], {"delimiter": delim}
    names = {f["name"].lower(): f for f in fields}
    squash = {re.sub(r"[^a-z0-9]", "", k): f for k, f in names.items()}
    header = rows[0][1]
    matched = sum(1 for h in header if h.strip().lower() in names or re.sub(r"[^a-z0-9]", "", h.lower()) in squash)
    has_header = matched >= max(1, len(header) // 2)
    info = {"delimiter": delim, "delimiter_source": how, "header": has_header, "rows": len(rows) - (1 if has_header else 0),
            "header_row": [h.strip() for h in header] if has_header else None}
    if has_header:
        cols = [names.get(h.strip().lower()) or squash.get(re.sub(r"[^a-z0-9]", "", h.lower())) for h in header]
        data, width = rows[1:], len(header)
    else:
        ordered = sorted(fields, key=lambda f: (f["seq"] is None, f["seq"] or 0))
        cols, data, width = ordered, rows, len(ordered)
        if len(header) != len(ordered):
            issues.append({"severity": "error", "kind": "data-width",
                           "message": f"no header row and {len(header)} columns in row 1, but the structure has {len(ordered)} fields"})
    bad_width, examples = 0, []
    checkers = [_Col(f) if f else None for f in cols]
    for row_no, row in data:
        if len(row) != width:
            bad_width += 1
            if len(examples) < EXAMPLES:
                examples.append(f"row {row_no} has {len(row)}")
            continue
        for chk, value in zip(checkers, row):
            if chk:
                chk.check(row_no, value)
    if bad_width:
        issues.append({"severity": "error", "kind": "data-width",
                       "message": f"{bad_width} of {len(data)} rows do not have {width} columns ({'; '.join(examples)}) - a delimiter or "
                                  "line break inside a value, or unbalanced quotes"})
    for chk in checkers:
        if chk:
            issues += chk.issues(len(data))
    return issues, info


def validate_json(fields, records, root=None, max_rows=MAX_ROWS):
    """records: the list below the root path. Fields compared by (dotted) path relative to the root."""
    issues, total = [], 0
    prefix = metamod.json_path(root) + "." if root and metamod.json_path(root) else ""

    def rel(f):
        p = metamod.json_path(f.get("path") or f["name"])
        return p[len(prefix):] if prefix and p.startswith(prefix) else p

    checkers = {rel(f): _Col(f) for f in fields}
    missing = {k: 0 for k in checkers}
    for i, rec in enumerate(records[:max_rows], 1):
        if not isinstance(rec, dict):
            continue
        total += 1
        flat = _flatten_values(rec)
        for path, chk in checkers.items():
            key = next((k for k in flat if k.lower() == path.lower() or k.lower().endswith("." + path.lower())), None)
            if key is None:
                missing[path] += 1
                if chk.f.get("nullable") is False:
                    chk.hit("data-mandatory", i, "<missing>")
                continue
            chk.check(i, flat[key])
    for path, n in missing.items():
        if 0 < n < total and checkers[path].f.get("nullable") is not False:
            issues.append({"severity": "warn", "kind": "data-missing", "message": f"'{path}' is missing in {n} of {total} records"})
    for chk in checkers.values():
        issues += chk.issues(total)
    return issues, {"records": total}


def _flatten_values(rec, prefix=""):
    out = {}
    for k, v in rec.items():
        p = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten_values(v, p))
        elif isinstance(v, list) and v and isinstance(v[0], dict):
            out.update(_flatten_values(v[0], p))
        else:
            out[p] = v
    return out


def json_records(data, root):
    """All records below the root path (not only the first)."""
    node = data
    for part in [p for p in re.split(r"\.|/|\[[^\]]*\]", re.sub(r"^\$", "", root or "")) if p]:
        if isinstance(node, list):
            node = next((x for x in node if isinstance(x, dict)), {})
        node = node.get(part, {}) if isinstance(node, dict) else {}
    if isinstance(node, list):
        return [x for x in node if isinstance(x, dict)]
    return [node] if isinstance(node, dict) and node else []
