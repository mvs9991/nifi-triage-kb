"""Self-service web page for colleagues (stdlib only): investigate a file / feed / table / error, daily report, live health,
search, team learnings. Read-only. `python -m nifikb web` - configure host / port / login in [web] of nifikb.toml.

Security: binds to 127.0.0.1 unless [web] host is set; optional HTTP basic login (one shared user, password from an env var
or file); every value is HTML-escaped; uploads are size-limited, written to a temp file and deleted after use."""
import base64
import email.parser
import email.policy
import hmac
import html
import os
import re
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__

MAX_UPLOAD = 20 * 1024 * 1024
STYLE = """body{font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1f2328;margin:0}
header{background:#1f4e79;color:#fff;padding:10px 20px}header a{color:#fff;margin-right:16px;text-decoration:none}
main{padding:16px 20px;max-width:1200px}label{display:block;margin-top:8px;font-weight:600}
input[type=text],textarea{width:100%;max-width:700px;padding:6px;font:inherit}textarea{height:60px}
button{margin-top:12px;padding:7px 18px;background:#1f4e79;color:#fff;border:0;border-radius:4px;cursor:pointer}
pre{background:#f6f8fa;padding:10px;overflow-x:auto;white-space:pre-wrap;font-size:12.5px;border:1px solid #d0d7de}
ol li{margin:4px 0}.hint{color:#57606a;font-size:12.5px}h2{margin-top:24px;border-bottom:1px solid #d0d7de}"""


def _page(title, body):
    nav = "".join(f'<a href="{u}">{t}</a>' for u, t in (("/", "Investigate"), ("/report", "Daily report"), ("/health", "Live health"),
                                                         ("/search", "Search"), ("/learnings", "Learnings")))
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)} - nifikb</title><style>{STYLE}</style>"
            f"</head><body><header><b>NiFi support</b> &nbsp; {nav}</header><main>{body}</main></body></html>").encode("utf-8")


def _md_to_html(text):
    """Render nifikb's markdown-like reports: #/## headings, numbered causes as a list, the rest preformatted."""
    out, pre, ol = [], [], []

    def flush():
        if ol:
            out.append("<ol>" + "".join(f"<li>{html.escape(x)}</li>" for x in ol) + "</ol>")
            ol.clear()
        if pre:
            out.append("<pre>" + html.escape("\n".join(pre)) + "</pre>")
            pre.clear()

    for line in text.splitlines():
        if line.startswith("## ") or line.startswith("# "):
            flush()
            out.append(("<h2>" if line.startswith("## ") else "<h1>") + html.escape(line.lstrip("# ")) + ("</h2>" if line.startswith("## ") else "</h1>"))
        elif re.match(r"^\d+\. ", line) and not pre:
            ol.append(line.split(". ", 1)[1])
        elif line.strip() or pre:
            if ol:
                flush()
            pre.append(line)
    flush()
    return "".join(out)


def _form(values=None):
    v = {k: html.escape(values.get(k, "")) for k in ("file", "feed", "table", "error", "headers")} if values else dict.fromkeys(
        ("file", "feed", "table", "error", "headers"), "")
    return f"""<h1>Investigate a problem</h1>
<p class="hint">Fill in what the ticket gives - any one field is enough. The answer lists the most likely causes first, with evidence.</p>
<form method="post" action="/investigate" enctype="multipart/form-data">
<label>File name</label><input type="text" name="file" value="{v['file']}" placeholder="SALES_20260926.csv">
<label>Feed / API name</label><input type="text" name="feed" value="{v['feed']}">
<label>Target table</label><input type="text" name="table" value="{v['table']}">
<label>Error text</label><input type="text" name="error" value="{v['error']}" placeholder="a distinctive part of the error message">
<label>Headers / field names sent (in file order, comma separated)</label><textarea name="headers">{v['headers']}</textarea>
<label>Sample file (CSV / JSON, max 20 MB)</label><input type="file" name="sample">
<label><input type="checkbox" name="live" value="1"> read the config tables now (if they may have changed)</label>
<button type="submit">Investigate</button></form>"""


class App:
    def __init__(self, cfg):
        from .config import load_config
        self.cfg = cfg if isinstance(cfg, dict) else load_config(cfg)
        w = self.cfg.get("web") or {}
        self.user = w.get("user")
        self.password = (os.environ.get(w["password_env"]) if w.get("password_env") else None) or \
            (Path(w["password_file"]).read_text(encoding="utf-8").strip() if w.get("password_file") else None)
        self.lock = threading.Lock()

    def store(self):
        from .cli import _store
        return _store(self.cfg)

    def names(self, store):
        from .cli import runtime_names
        return runtime_names(store)

    # ------------------------------------------------------------------------------------------ pages
    def investigate(self, fields, sample_bytes=None, sample_name=None):
        from . import diagnose as dg, investigate as inv
        tmp = None
        try:
            if sample_bytes:
                suffix = Path(sample_name or "sample.csv").suffix or ".csv"
                fd, tmp = tempfile.mkstemp(suffix=suffix)
                with os.fdopen(fd, "wb") as f:
                    f.write(sample_bytes)
            store = self.store()
            try:
                r = inv.investigate(self.cfg, store, self.names(store), file=fields.get("file") or None, feed=fields.get("feed") or None,
                                    table=fields.get("table") or None, error_text=fields.get("error") or None,
                                    headers=dg.split_headers([fields.get("headers", "")]), sample_path=tmp, live=bool(fields.get("live")))
            finally:
                store.db.close()
            return inv.format_report(r)
        finally:
            if tmp:
                os.unlink(tmp)

    def report(self):
        from . import report as rp
        store = self.store()
        try:
            return rp.to_markdown(rp.build_report(self.cfg, store, self.names(store)))
        finally:
            store.db.close()

    def health(self):
        from . import nifiapi
        if not nifiapi.settings(self.cfg):
            return "NiFi REST API not configured ([nifi_api] in nifikb.toml)."
        store = self.store()
        try:
            return nifiapi.format_health(nifiapi.health(nifiapi.Client(nifiapi.settings(self.cfg)), versioned=store.versioned_groups()),
                                         self.names(store))
        except nifiapi.NiFiApiError as e:
            return f"error: {e}"
        finally:
            store.db.close()

    def search(self, q):
        store = self.store()
        try:
            rows = store.search(q, 30) if q else []
            return "\n".join(f"[{r['kind']}] {r['title']}  -> {r['doc']}\n    {r['snip']}" for r in rows) or ("no matches" if q else "")
        finally:
            store.db.close()

    def learnings(self):
        from . import learnings as lm
        items = lm.load_all(self.cfg, include_obsolete=False)
        return "\n\n".join(lm.format_item(i) for i in items) or "no team learnings yet"


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"nifikb/{__version__}"

        def log_message(self, fmt, *args):
            pass

        def _auth(self):
            if not app.user or not app.password:
                return True
            head = self.headers.get("Authorization", "")
            if head.startswith("Basic "):
                try:
                    user, _, pw = base64.b64decode(head[6:]).decode("utf-8").partition(":")
                except (ValueError, UnicodeDecodeError):
                    return False
                if hmac.compare_digest(user, app.user) and hmac.compare_digest(pw, app.password):
                    return True
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="nifikb"')
            self.end_headers()
            return False

        def _send(self, body, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._auth():
                return
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            try:
                if url.path == "/":
                    return self._send(_page("Investigate", _form()))
                if url.path == "/report":
                    return self._send(_page("Daily report", _md_to_html(app.report())))
                if url.path == "/health":
                    return self._send(_page("Live health", "<h1>Live NiFi health</h1><pre>" + html.escape(app.health()) + "</pre>"))
                if url.path == "/search":
                    term = (q.get("q") or [""])[0]
                    body = (f"<h1>Search</h1><form><input type='text' name='q' value='{html.escape(term, quote=True)}'>"
                            f"<button>Search</button></form><pre>{html.escape(app.search(term))}</pre>")
                    return self._send(_page("Search", body))
                if url.path == "/learnings":
                    return self._send(_page("Learnings", "<h1>Team learnings</h1><pre>" + html.escape(app.learnings()) + "</pre>"))
                self._send(_page("Not found", "<p>Not found</p>"), 404)
            except Exception as e:  # show the problem instead of a dropped connection
                self._send(_page("Error", f"<pre>{html.escape(type(e).__name__ + ': ' + str(e))}</pre>"), 500)

        def do_POST(self):
            if not self._auth():
                return
            if urllib.parse.urlparse(self.path).path != "/investigate":
                return self._send(_page("Not found", "<p>Not found</p>"), 404)
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD + 100_000:
                return self._send(_page("Too large", "<p>The upload is larger than 20 MB.</p>"), 413)
            body = self.rfile.read(length)
            fields, sample, sample_name = {}, None, None
            ctype = self.headers.get("Content-Type", "")
            if ctype.startswith("multipart/form-data"):
                msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
                    f"Content-Type: {ctype}\r\n\r\n".encode() + body)
                for part in msg.iter_parts():
                    name = part.get_param("name", header="content-disposition")
                    payload = part.get_payload(decode=True) or b""
                    if name == "sample":
                        if payload:
                            sample, sample_name = payload, part.get_filename()
                    elif name:
                        fields[name] = payload.decode("utf-8", "replace").strip()
            else:
                fields = {k: v[0].strip() for k, v in urllib.parse.parse_qs(body.decode("utf-8", "replace")).items()}
            if not any(fields.get(k) for k in ("file", "feed", "table", "error")):
                return self._send(_page("Investigate", "<p><b>Give at least a file, feed, table or error text.</b></p>" + _form(fields)))
            try:
                report = app.investigate(fields, sample, sample_name)
                self._send(_page("Investigation", _form(fields) + "<hr>" + _md_to_html(report)))
            except Exception as e:
                self._send(_page("Error", _form(fields) + f"<pre>{html.escape(type(e).__name__ + ': ' + str(e))}</pre>"), 500)
    return Handler


def serve(cfg, host=None, port=None):
    app = App(cfg)
    w = app.cfg.get("web") or {}
    host = host or w.get("host", "127.0.0.1")
    port = int(port or w.get("port", 8765))
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"nifikb web on http://{host}:{server.server_address[1]}/" + ("" if app.user else "  (no login configured: [web] user + password_env)"))
    server.serve_forever()
