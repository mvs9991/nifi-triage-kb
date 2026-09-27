"""Ticket systems (Jira, ServiceNow): read a ticket, pull the facts investigate needs out of it (file names, feed / table
names known to the config tables, error text, header lines, attached samples), run the investigation and draft a reply.

Reading is all it does by default. A comment is posted only by a person running `ticket <id> --post` (never by an agent
through MCP), after secrets and e-mail addresses are scrubbed; ServiceNow gets a work note (internal), not a customer
comment, unless [tickets] note_field says otherwise."""
import base64
import json
import os
import re
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import metadata as metamod
from .logs import scrub

FILE_RE = re.compile(r"(?<![\w/\\.-])([\w][\w.\-]*\.(?:csv|txt|dat|json|jsonl|xml|gz|zip|parquet|psv|tsv|xlsx?|avro|orc))\b", re.I)
ERROR_RE = re.compile(r"(?i)\b(error|exception|failed|failure|failing|cannot|can't|unable|invalid|mismatch|not found|refused|timed? ?out|"
                      r"violat|duplicate|truncat|denied|rejected)\b")
HEADER_HINT = re.compile(r"(?i)^\s*(headers?|columns?|fields?|keys?)\s*(?:are|sent|used|:|=|-)+\s*(.+)$")
SAMPLE_EXT = re.compile(r"(?i)\.(csv|txt|dat|json|jsonl|psv|tsv)$")
MAX_ATTACHMENT = 5 * 1024 * 1024


class TicketError(Exception):
    pass


def settings(cfg):
    t = cfg.get("tickets") or {}
    if not t.get("url") or not t.get("kind"):
        return None
    if t["kind"] not in ("jira", "servicenow"):
        raise TicketError("[tickets] kind must be 'jira' or 'servicenow'")
    return t


def _secret(t, key):
    if t.get(f"{key}_env") and os.environ.get(t[f"{key}_env"]):
        return os.environ[t[f"{key}_env"]]
    if t.get(f"{key}_file"):
        return Path(t[f"{key}_file"]).read_text(encoding="utf-8").strip()
    return None


class _Http:
    def __init__(self, t):
        self.t = t
        self.base = t["url"].rstrip("/")
        self.timeout = float(t.get("timeout", 30))
        self.ctx = ssl.create_default_context(cafile=t.get("ca_cert") or None) if self.base.startswith("https") else None
        token, password = _secret(t, "token"), _secret(t, "password")
        if t.get("username") and (password or token):
            raw = f"{t['username']}:{password or token}".encode()
            self.auth = "Basic " + base64.b64encode(raw).decode()  # Jira Cloud (e-mail + API token), ServiceNow basic
        elif token:
            self.auth = f"Bearer {token}"  # Jira Server / DC personal access token, ServiceNow OAuth token
        else:
            self.auth = None

    def call(self, method, path, body=None, raw=False):
        headers = {"Accept": "application/json"}
        if self.auth:
            headers["Authorization"] = self.auth
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        url = path if path.startswith("http") else self.base + path
        if not url.startswith(self.base):
            raise TicketError(f"refusing to follow a link outside {self.base}")  # attachment URLs must stay on the ticket host
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                if raw:
                    return r.read(MAX_ATTACHMENT + 1)
                text = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            hint = {401: "authentication failed - check [tickets] username / token_env / password_env",
                    403: "the ticket user lacks permission", 404: "ticket not found"}.get(e.code, "")
            raise TicketError(f"HTTP {e.code} on {method} {path.split('?')[0]}: {hint}".strip()) from e
        except (urllib.error.URLError, OSError) as e:
            raise TicketError(f"cannot reach {self.base}: {e}") from e
        return json.loads(text) if text.strip() else None


def _adf_text(node):
    """Jira Cloud v3 'Atlassian document format' -> plain text (v2 returns plain strings already)."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        sep = "\n" if node.get("type") in ("paragraph", "heading", "codeBlock", "listItem", "doc") else ""
        return sep.join(_adf_text(c) for c in node.get("content") or [])
    if isinstance(node, list):
        return "\n".join(_adf_text(c) for c in node)
    return ""


class Jira:
    def __init__(self, t):
        self.http, self.t = _Http(t), t

    def fetch(self, key):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", key):
            raise TicketError(f"'{key}' does not look like a Jira key (PROJ-123)")
        d = self.http.call("GET", f"/rest/api/2/issue/{key}?fields=summary,description,comment,created,status,attachment")
        f = d.get("fields") or {}
        comments = [_adf_text(c.get("body")) for c in ((f.get("comment") or {}).get("comments") or [])]
        atts = [{"name": a.get("filename"), "size": a.get("size") or 0, "url": a.get("content")} for a in f.get("attachment") or []]
        return {"id": d.get("key", key), "title": f.get("summary") or "", "description": _adf_text(f.get("description")) or "",
                "comments": comments, "created": f.get("created"), "status": ((f.get("status") or {}).get("name")),
                "attachments": atts, "ref": d.get("key", key)}

    def download(self, att):
        return self.http.call("GET", att["url"], raw=True)

    def post(self, ticket, text):
        self.http.call("POST", f"/rest/api/2/issue/{ticket['ref']}/comment", {"body": text})


class ServiceNow:
    def __init__(self, t):
        self.http, self.t = _Http(t), t
        self.table = t.get("table", "incident")

    def fetch(self, number):
        if not re.fullmatch(r"[A-Za-z]{2,8}\d+", number):
            raise TicketError(f"'{number}' does not look like a ServiceNow number (INC0012345)")
        q = urllib.parse.urlencode({"sysparm_query": f"number={number}", "sysparm_limit": 1, "sysparm_display_value": "true",
                                    "sysparm_fields": "sys_id,number,short_description,description,comments,work_notes,sys_created_on,state"})
        rows = (self.http.call("GET", f"/api/now/table/{self.table}?{q}") or {}).get("result") or []
        if not rows:
            raise TicketError(f"{number} not found in {self.table}")
        r = rows[0]
        q = urllib.parse.urlencode({"sysparm_query": f"table_sys_id={r['sys_id']}", "sysparm_limit": 20})
        atts = [{"name": a.get("file_name"), "size": int(a.get("size_bytes") or 0), "url": f"/api/now/attachment/{a['sys_id']}/file"}
                for a in (self.http.call("GET", f"/api/now/attachment?{q}") or {}).get("result") or []]
        comments = [c for c in (r.get("comments"), r.get("work_notes")) if c]
        return {"id": r.get("number", number), "title": r.get("short_description") or "", "description": r.get("description") or "",
                "comments": comments, "created": r.get("sys_created_on"), "status": r.get("state"), "attachments": atts,
                "ref": r["sys_id"]}

    def download(self, att):
        return self.http.call("GET", att["url"], raw=True)

    def post(self, ticket, text):
        self.http.call("PATCH", f"/api/now/table/{self.table}/{ticket['ref']}", {self.t.get("note_field", "work_notes"): text})


def client(t):
    return Jira(t) if t["kind"] == "jira" else ServiceNow(t)


# ------------------------------------------------------------------------------------------------ facts
def _known_names(store, model):
    """Normalised identifying values of the config rows (file patterns, feeds, APIs, tables) -> original value."""
    known = {}
    if not model:
        return known
    rows = store.get_meta_rows(exclude=model.get("structure_table"))
    for table, rs in rows.items():
        info = model["tables"].get(table) or {}
        cols = [c for c in info.get("columns") or [] if metamod.KEY_COL.search(c) or metamod.TARGET_COL.search(c)
                or c in (model.get("definition_keys") or [])]
        for r in rs:
            for c in cols:
                v = r.get(c)
                if isinstance(v, str) and 3 <= len(v) <= 120 and v != "***" and not re.search(r"\s", v):
                    known.setdefault(metamod.norm(v), v)
    return known


def extract(ticket, store=None, model=None):
    """{files, feeds, tables, error, headers} from the ticket text (title, description, comments)."""
    text = "\n".join([ticket.get("title") or "", ticket.get("description") or ""] + list(ticket.get("comments") or []))
    files = []
    for m in FILE_RE.finditer(text):
        if m.group(1) not in files:
            files.append(m.group(1))
    known = _known_names(store, model) if store is not None else {}
    feeds, tables = [], []
    for tok in re.findall(r"[A-Za-z][\w.\-]{2,}", text):
        v = known.get(metamod.norm(tok))
        if v and v not in feeds and v not in tables and tok not in files:
            (tables if metamod.norm(v).startswith(("stg_", "tgt_", "dim_", "fact_", "raw_")) else feeds).append(v)
    headers, candidates = [], []
    title = (ticket.get("title") or "").strip()
    for n, line in enumerate(text.splitlines()):
        s = line.strip()
        h = HEADER_HINT.match(s)
        if h and not headers:
            parts = [p.strip().strip("'\"`") for p in re.split(r"[,|;\t]", h.group(2)) if p.strip()]
            if len(parts) >= 2:
                headers = parts
                continue
        if (ERROR_RE.search(s) or re.search(r"\w(Exception|Error)\b", s)) and 10 <= len(s) <= 500 and not h:
            # the most specific line wins: an exception class or "Error: ..." beats a summary like "load failed"
            score = 3 * bool(re.search(r"\w(Exception|Error)\b", s)) + (":" in s) - (s == title)
            candidates.append((-score, n, re.sub(r"(?i)^error\s*:\s*", "", s)))
    error = min(candidates)[2] if candidates else None
    if not headers:  # a pasted header line: 3+ identifier-like tokens split by one delimiter
        for line in text.splitlines():
            s = line.strip()
            for d in (",", "|", ";", "\t"):
                parts = [p.strip() for p in s.split(d)]
                if len(parts) >= 3 and all(re.fullmatch(r"[A-Za-z_][\w .\-]{0,60}", p) for p in parts) and s.count(" ") < len(parts) * 2:
                    headers = parts
                    break
            if headers:
                break
    error_words = error
    if error and len(error) > 200:
        error_words = error[:200]
    return {"files": files[:5], "feeds": feeds[:5], "tables": tables[:5], "error": error_words, "headers": headers}


def fetch_samples(cl, ticket, max_files=2):
    """Download small CSV / JSON attachments to a temp folder (the caller removes it). Returns (dir, [paths])."""
    wanted = [a for a in ticket.get("attachments") or [] if a.get("name") and SAMPLE_EXT.search(a["name"])
              and 0 < (a.get("size") or 1) <= MAX_ATTACHMENT][:max_files]
    if not wanted:
        return None, []
    tmp = tempfile.mkdtemp(prefix="nifikb-ticket-")
    paths = []
    for a in wanted:
        try:
            data = cl.download(a)
        except TicketError:
            continue
        if data is None or len(data) > MAX_ATTACHMENT:
            continue
        p = Path(tmp) / re.sub(r"[^\w.\-]", "_", a["name"])
        p.write_bytes(data)
        paths.append(str(p))
    return tmp, paths


def draft_comment(ticket, facts, report, kb_built=None):
    """A short reply for the ticket: likely causes, proposed fixes, what was checked. Scrubbed of secrets / e-mails."""
    L = [f"Automated first analysis (nifikb) for {ticket['id']} - please verify before acting."]
    looked = [f"file {', '.join(facts['files'])}" if facts["files"] else None, f"feed {', '.join(facts['feeds'])}" if facts["feeds"] else None,
              f"table {', '.join(facts['tables'])}" if facts["tables"] else None, "the error text" if facts["error"] else None,
              f"{len(facts['headers'])} headers" if facts["headers"] else None]
    L.append("Checked: " + ", ".join(x for x in looked if x) + (f" (knowledge base built {kb_built})" if kb_built else ""))
    L.append("")
    if report["causes"]:
        L.append("Most likely causes:")
        L += [f"{n}. {c}" for n, c in enumerate(report["causes"][:5], 1)]
    else:
        L.append("No conclusive cause found yet - the support team will look further.")
    fixes = next((text for title, text in report["sections"] if title.startswith("Proposed fixes")), None)
    if fixes:
        L += ["", "Proposed config fix (to be reviewed and run by the platform team):", fixes]
    if report.get("next_checks"):
        L += ["", "Still open: " + "; ".join(report["next_checks"][:3])]
    return scrub("\n".join(L))
