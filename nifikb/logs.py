"""NiFi logs (nifi-app*.log, nifi-bootstrap*.log): an incremental, compact index of what went wrong.

The logs are huge and always growing, so:
- files are read incrementally (byte offset per file; rotation / truncation detected by a head fingerprint);
  rolled files (nifi-app_2026-09-26_10.0.log, *.gz) are read once; a first run reads at most `initial_tail_mb` of each;
- only WARN / ERROR / FATAL lines are kept (plus lifecycle lines of the bootstrap log: starts, stops, restarts, crashes),
  with their exception / root cause taken from the stack trace that follows;
- each event is tied to the processor / service (runtime id -> flow component), the FlowFile uuid and file name, and a
  message template (variable parts removed) so thousands of identical errors collapse into one line with a count;
- events older than `keep_days` (relative to the newest one) are pruned; duplicates are ignored.
"""
import fnmatch
import gzip
import hashlib
import re
import time
from pathlib import Path

from .db import BEARER_RE
from .util import REDACTED, redact_secrets

UNQUOTED_SECRET_RE = re.compile(r"(?i)\b(pass(?:word|wd)?|pwd|secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*(?!<redacted>)[^\s,;&'\"]+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def scrub(text):
    """Secrets, bearer tokens and e-mail addresses out of a log message (error messages often quote data values)."""
    text = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(text))
    text = UNQUOTED_SECRET_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    return EMAIL_RE.sub("<email>", text)

LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) (TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+\[(.*?)\] (\S+) ?(.*)$")
COMP_RE = re.compile(r"\b([A-Z][\w$]*)\[id=([\w-]+)\]")
SERVICE_RE = re.compile(r"service=([A-Z][\w$]*)\[id=([\w-]+)\]")
FF_START = "StandardFlowFileRecord["
CAUSE_RE = re.compile(r"^(?:Caused by: )?((?:[a-z_$][\w$]*\.)+[A-Z][\w$]*(?:Exception|Error|Throwable|Failure)[\w$]*)(?::\s*(.*))?$")
LIFECYCLE_RE = re.compile(r"(?i)launched apache nifi|started apache nifi|apache nifi (?:is|has) (?:stopped|shut down|started)|"
                          r"nifi pid|stopping apache nifi|restart(?:ing)? apache nifi|nifi (?:has )?died|process .{0,40} died|"
                          r"terminated|outofmemory|hs_err|killing|not running|"
                          r"graceful shutdown|failed to start|shutdown hook")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
DEFAULT_PATTERNS = ("nifi-app*.log*", "nifi-bootstrap*.log*")


def settings(cfg):
    lg = dict(cfg.get("logs") or {})
    home = cfg["nifi"].get("home")
    dirs = lg.get("dirs") or ([str(Path(home) / "logs")] if home else [])
    return {"dirs": dirs, "patterns": lg.get("files") or list(DEFAULT_PATTERNS), "keep_days": float(lg.get("keep_days", 14)),
            "initial_tail_mb": float(lg.get("initial_tail_mb", 200)), "enabled": lg.get("enabled", True) and bool(dirs)}


def log_files(s):
    out = []
    for d in s["dirs"]:
        p = Path(d)
        if p.is_dir():
            out += [f for f in sorted(p.iterdir()) if f.is_file() and any(fnmatch.fnmatch(f.name, pat) for pat in s["patterns"])]
    return out


# ---------------------------------------------------------------------------------------------- parsing
def _flowfile(msg):
    """(uuid, file name, message with the FlowFile record replaced by <flowfile>) - the record nests brackets."""
    i = msg.find(FF_START)
    if i < 0:
        return None, None, msg
    depth, j = 0, i + len(FF_START) - 1
    while j < len(msg):
        if msg[j] == "[":
            depth += 1
        elif msg[j] == "]":
            depth -= 1
            if depth == 0:
                break
        j += 1
    rec = msg[i:j + 1]
    uuid = re.search(r"uuid=([0-9a-f-]{36})", rec)
    name = re.search(r",name=(.*?),size=", rec)
    fname = name.group(1) if name else None
    if fname and UUID_RE.fullmatch(fname):
        fname = None  # FlowFiles created inside NiFi are named after their uuid: not a file name
    return (uuid.group(1) if uuid else None, fname, msg[:i] + "<flowfile>" + msg[j + 1:])


def compact(msg):
    """Message with the FlowFile record shortened to FlowFile[uuid8, name]."""
    uuid, fname, stripped = _flowfile(msg)
    if not uuid:
        return msg
    return stripped.replace("<flowfile>", f"FlowFile[{uuid[:8]}" + (f", {fname}]" if fname else "]"))


def template(msg):
    """Stable shape of a message: ids, numbers, quoted values and paths replaced."""
    t = UUID_RE.sub("<id>", msg)
    t = re.sub(r"'[^']{0,200}'|\"[^\"]{0,200}\"", "<v>", t)
    t = re.sub(r"(?:[A-Za-z]:)?[\\/][^\s,;\]]+", "<path>", t)
    t = re.sub(r"\b\d+(?:[.,]\d+)*\b", "<n>", t)
    return re.sub(r"\s+", " ", t)[:300]


def parse_lines(lines, source, bootstrap=False):
    """Yield events from an iterable of (line_no, text)."""
    ev, cont = None, 0
    for no, line in lines:
        line = line.rstrip("\r\n")
        m = LINE_RE.match(line)
        if m:
            if ev:
                yield ev
            ev, cont = None, 0
            ts, ms, level, thread, logger, msg = m.groups()
            keep = level in ("WARN", "ERROR", "FATAL") or (bootstrap and LIFECYCLE_RE.search(msg))
            if not keep:
                continue
            uuid, fname, stripped = _flowfile(msg)
            comp = SERVICE_RE.search(msg) or COMP_RE.search(msg)
            ev = {"ts": f"{ts}.{ms}", "epoch": time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")) + int(ms) / 1000,
                  "level": level if not (bootstrap and level == "INFO") else "LIFECYCLE", "thread": thread[:80],
                  "logger": logger, "component_type": comp.group(1) if comp else None,
                  "component_id": comp.group(2) if comp else None, "flowfile_uuid": uuid, "filename": fname,
                  "message": scrub(msg)[:2000], "cause": None, "file": source, "line": no}
            ev["template"] = template(COMP_RE.sub(lambda x: x.group(1), stripped))
        elif ev and cont < 60:
            cont += 1
            c = CAUSE_RE.match(line.strip())
            if c and not line.lstrip().startswith("at "):
                ev["cause"] = scrub(f"{c.group(1).rsplit('.', 1)[-1]}: {c.group(2) or ''}".strip(": "))[:600]
    if ev:
        yield ev


def _head(path):
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rb") as f:
            return hashlib.sha1(f.read(4096)).hexdigest()
    except OSError:
        return ""


def _read(path, start):
    """(line_no, text) from byte offset `start` (whole file for .gz); returns the iterator and a callable end offset."""
    if path.suffix == ".gz":
        f = gzip.open(path, "rt", encoding="utf-8", errors="replace")
    else:
        f = open(path, "rb")
        f.seek(start)
        if start:
            f.readline()  # we may have landed mid-line
    state = {"end": start}

    def gen():
        with f:
            for i, raw in enumerate(f, 1):
                yield i, raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
            if not isinstance(f, gzip.GzipFile) and hasattr(f, "tell"):
                try:
                    state["end"] = f.tell()
                except (OSError, ValueError):
                    pass
    return gen(), state


# ---------------------------------------------------------------------------------------------- indexing
def index(cfg, store, log=print):
    """Bring the log index up to date. Returns (files read, events added)."""
    s = settings(cfg)
    if not s["enabled"]:
        return 0, 0
    files, added = 0, 0
    for path in log_files(s):
        st = path.stat()
        head = _head(path)
        row = store.db.execute("SELECT sig, offset, head FROM log_files WHERE path=?", (str(path),)).fetchone()
        rolled = path.suffix == ".gz" or re.search(r"_\d{4}-\d{2}-\d{2}", path.name)
        sig = f"{st.st_size}:{int(st.st_mtime)}"
        if row and (row["sig"] == sig or (rolled and row["head"] == head)):
            continue  # unchanged, or a rolled file already read
        if rolled and time.time() - st.st_mtime > s["keep_days"] * 86400 * 4 and not row:
            continue  # very old rolled file
        start = 0
        if row and not rolled and row["head"] == head and st.st_size >= row["offset"]:
            start = row["offset"]  # the same file grew: read only the new part
        elif not row and path.suffix != ".gz" and st.st_size > s["initial_tail_mb"] * 1e6:
            start = int(st.st_size - s["initial_tail_mb"] * 1e6)  # first run on a huge file: its tail only
        lines, state = _read(path, start)
        events = list(parse_lines(lines, path.name, bootstrap="bootstrap" in path.name))
        added += store.add_log_events(events)
        end = state["end"] if path.suffix != ".gz" else st.st_size
        store.db.execute("INSERT OR REPLACE INTO log_files(path, sig, offset, head) VALUES(?,?,?,?)", (str(path), sig, end or st.st_size, head))
        files += 1
    store.prune_log_events(s["keep_days"])
    store.db.commit()
    if files:
        log(f"  logs: {files} file(s) read, {added} new warning / error event(s)")
    return files, added


# ---------------------------------------------------------------------------------------------- queries
def query(store, component_ids=(), filename=None, uuid=None, grep=None, level=None, since_hours=None, limit=50):
    where, params = [], []
    if component_ids:
        where.append(f"component_id IN ({','.join('?' * len(component_ids))})")
        params += list(component_ids)
    if filename:
        where.append("(filename = ? OR message LIKE ?)")
        params += [filename, f"%{filename}%"]
    if uuid:
        where.append("flowfile_uuid = ?")
        params.append(uuid)
    if grep:
        where.append("(message LIKE ? OR cause LIKE ?)")
        params += [f"%{grep}%", f"%{grep}%"]
    if level:
        where.append("level = ?")
        params.append(level.upper())
    if since_hours:
        newest = store.db.execute("SELECT MAX(epoch) FROM log_events").fetchone()[0] or time.time()
        where.append("epoch >= ?")
        params.append(newest - float(since_hours) * 3600)  # relative to the newest event: works on copied / old logs too
    sql = ("SELECT template, level, component_type, component_id, COUNT(*) n, MIN(ts) first, MAX(ts) last, "
           "MAX(cause) cause, MAX(message) sample, GROUP_CONCAT(DISTINCT filename) files, MAX(flowfile_uuid) uuid "
           "FROM log_events" + (" WHERE " + " AND ".join(where) if where else "")
           + " GROUP BY template, level, component_id ORDER BY MAX(epoch) DESC LIMIT ?")
    return store.db.execute(sql, (*params, limit)).fetchall()


def format_rows(rows, names=None):
    names = names or {}
    if not rows:
        return "no matching warnings / errors in the indexed logs"
    L = []
    for r in rows:
        who = r["component_type"] or ""
        if r["component_id"]:
            flow = names.get(r["component_id"])
            who += f" `{r['component_id'][:8]}`" + (f" ({flow})" if flow else "")
        files = [f for f in (r["files"] or "").split(",") if f][:3]
        L.append(f"[{r['level']}] x{r['n']} {r['first'][:16]} .. {r['last'][:16]}  {who}".rstrip())
        L.append(f"    {compact(r['sample'])[:400]}")
        if r["cause"]:
            L.append(f"    cause: {r['cause']}")
        if files:
            L.append(f"    files: {', '.join(files)}")
    return "\n".join(L)
