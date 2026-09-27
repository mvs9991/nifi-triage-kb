"""Small shared helpers: ids, slugs, redaction, and the regexes used to spot hardcoded values."""
import hashlib
import os
import re
from pathlib import Path

REDACTED = "<redacted>"

SECRET_NAME = re.compile(r"(?i)(pass(word|wd)?|pwd|secret|api[_\- ]?key|access[_\- ]?key|private[_\- ]?key|token|credential)")
URL_RE = re.compile(r"\b(?:https?|ftps?|sftp|s3a?|s3n|hdfs|wss?|gs|abfss?|wasbs?)://[^\s\"'<>`)]+", re.I)
JDBC_RE = re.compile(r"\bjdbc:[a-z0-9]+:[^\s\"'<>`]+", re.I)
IP_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
HOST_RE = re.compile(r"(?<![\w.@/-])(?:[a-z0-9-]+\.)+(?:com|net|org|io|local|internal|corp|lan|intra|cloud|in|co|aws)(?![\w.-])", re.I)
WIN_PATH_RE = re.compile(r"(?:(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|\\\\[\w.-]+\\)[^\"'<>|*?\r\n]*")
UNIX_PATH_RE = re.compile(r"(?<![\w.:/$}])/(?:opt|data|home|tmp|var|mnt|srv|app|apps|usr|etc|nifi|shared|export|landing|archive|inbound|outbound)(?:/[\w.${}#@ -]*)*", re.I)
# Captures the literal assigned to something that looks like a secret: password = "x", "pwd": "x", pass: 'x'
SECRET_ASSIGN_RE = re.compile(
    r"(?i)([\w.\-]*(?:pass(?:word|wd)?|pwd|secret|api[_-]?key|access[_-]?key|token)[\w.\-]*)[\"']?\s*(?:=|:|,|\()\s*[\"']([^\"']{2,})[\"']"
)

EL_VAR_RE = re.compile(r"\$\{\s*([A-Za-z_][\w.\-]*)\s*\}")
EL_REF_RE = re.compile(r"\$\{\s*([A-Za-z_][\w.\-]*)\s*(?=[:}])")
PARAM_RE = re.compile(r"#\{\s*(?:'([^']+)'|([^}]+?))\s*\}")


def short(i):
    return (i or "")[:8]


def slugify(text, maxlen=60):
    s = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
    return (s[:maxlen].rstrip("-")) or "unnamed"


def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()


def sha1_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_sig(path):
    st = os.stat(path)
    return f"{st.st_size}:{int(st.st_mtime)}"


def redact_secrets(text):
    """Replace literal secret values (password = "x") in a line of code or config."""
    return SECRET_ASSIGN_RE.sub(lambda m: m.group(0).replace(m.group(2), REDACTED), text)


def clip(text, n=160):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def md_escape(text):
    return (text or "").replace("|", "\\|").replace("\n", " ")


def write_if_changed(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True
