"""MCP server (stdio, JSON-RPC 2.0, stdlib only) exposing the knowledge base to AI agents: Claude Code, Gemini CLI or
any MCP client. Everything is read-only except `build`, which only rewrites the kb/ folder.

    python -m nifikb mcp [--config nifikb.toml]
"""
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

from . import __version__

PROTOCOL = "2025-06-18"

TOOLS = [
    {"name": "investigate",
     "description": ("START HERE FOR ANY SUPPORT TICKET. One call runs every check - metadata config rows vs the file / target, "
                     "provenance (where the FlowFile was dropped and why), NiFi log errors for the file and the processors involved, "
                     "the code line that raises the error text, recent config-row changes, team learnings, static findings - and "
                     "returns a ranked list of likely causes with the evidence. Give whatever the ticket has: file name, feed / API "
                     "name, target table, error text, headers or a sample file."),
     "inputSchema": {"type": "object", "properties": {
         "file": {"type": "string", "description": "file name from the ticket, e.g. SALES_20260926.csv"},
         "feed": {"type": "string", "description": "feed / API / source name"},
         "table": {"type": "string", "description": "target table"},
         "error_text": {"type": "string", "description": "error message quoted in the ticket (a distinctive fragment is enough)"},
         "headers": {"type": "array", "items": {"type": "string"}, "description": "field names sent, in file order"},
         "sample_path": {"type": "string", "description": "path to a sample CSV / JSON file"},
         "live": {"type": "boolean", "default": False, "description": "read the config rows now (they may have changed)"},
         "since_hours": {"type": "number", "default": 72, "description": "hours of processor log errors to include"}}}},
    {"name": "kb_overview",
     "description": "Start here. The knowledge base index: flows (process groups), external systems, issue counts, build time.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "search",
     "description": "Full-text search over processors, properties, SQL, tables, code, labels, metadata definitions and config rows.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 15}},
                     "required": ["query"]}},
    {"name": "show",
     "description": "One component (processor / controller service / port) with all its settings, by name or id prefix; or a process group / custom class.",
     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
    {"name": "trace",
     "description": "Data path downstream from a component (or upstream with upstream=true), across process groups.",
     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "upstream": {"type": "boolean", "default": False},
                                                      "depth": {"type": "integer", "default": 40}}, "required": ["ref"]}},
    {"name": "diagnose",
     "description": ("Support triage. Give the incoming headers / JSON keys and/or a file name, target table, feed or API name. Returns what "
                     "the metadata config tables and the flow expect (structure, order, types, target table), what does not match, "
                     "the related feed/API/server config rows (secrets masked), the processors involved and their known issues."),
     "inputSchema": {"type": "object", "properties": {
         "key": {"type": "string", "description": "file name (e.g. SALES_20260926.csv), target table, feed or API name"},
         "headers": {"type": "array", "items": {"type": "string"}, "description": "incoming field names, in file order"},
         "sample_path": {"type": "string", "description": "path to a sample CSV/JSON file to read the headers from"},
         "live": {"type": "boolean", "default": False, "description": "read the config tables now instead of the last snapshot"},
         "structured": {"type": "boolean", "default": False,
                        "description": "return JSON instead of text (only when you need to post-process; the text has the same facts)"}}}},
    {"name": "issues",
     "description": "Static findings: invalid processors, dropped failures, missing tables, field/column mismatches, metadata drift.",
     "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "severity": {"type": "string"},
                                                      "contains": {"type": "string"}, "limit": {"type": "integer", "default": 100}}}},
    {"name": "read_kb_file",
     "description": "Read a file of the knowledge base, e.g. flows/<group>.md, services.md, metadata.md, db/<name>.md, scripts/<x>.md.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "default": 0},
                                                      "max_chars": {"type": "integer", "default": 60000}}, "required": ["path"]}},
    {"name": "sql",
     "description": "Read-only query (single SELECT/WITH/SHOW/DESCRIBE) against a configured database; sensitive columns are masked.",
     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "db": {"type": "string"},
                                                      "max_rows": {"type": "integer", "default": 100}}, "required": ["query"]}},
    {"name": "build",
     "description": "Refresh the knowledge base from the flow, NARs, code repos and databases (no-op when nothing changed).",
     "inputSchema": {"type": "object", "properties": {"force": {"type": "boolean", "default": False},
                                                      "refresh_db": {"type": "boolean", "default": False}}}},
    {"name": "find_learnings",
     "description": ("Team learnings from earlier tickets (symptom, cause, fix). Give terms (file names, tables, feeds, processor names, "
                     "error words) to get the relevant ones, or none to list the most recent. Check these before concluding a diagnosis."),
     "inputSchema": {"type": "object", "properties": {"terms": {"type": "array", "items": {"type": "string"}},
                                                      "tag": {"type": "string"}, "limit": {"type": "integer", "default": 10},
                                                      "include_retired": {"type": "boolean", "default": False}}}},
    {"name": "get_learning",
     "description": "Full text of one learning by id (from find_learnings, diagnose or search).",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "add_learning",
     "description": ("Record something reusable learned while solving a ticket, so every future session (Claude, Gemini, people) knows it. "
                     "Only for knowledge the KB cannot derive itself: a root cause pattern, a vendor quirk, a fix procedure, a convention, "
                     "a misleading symptom. Not for one-off facts or anything the flow / code / tables already show. Never include "
                     "secrets or personal data (they are redacted anyway). Body in markdown with ## Symptom, ## Cause, ## Fix, "
                     "## How to spot it next time. Search find_learnings first and retire_learning an outdated one instead of duplicating."),
     "inputSchema": {"type": "object", "properties": {
         "title": {"type": "string", "description": "one line, specific: 'SALES feed switches to pipe delimiter at month end'"},
         "body": {"type": "string"},
         "kind": {"type": "string", "enum": ["fix", "pattern", "gotcha", "context", "faq"], "default": "fix"},
         "tags": {"type": "array", "items": {"type": "string"}},
         "applies_to": {"type": "array", "items": {"type": "string"},
                        "description": "file names or patterns (SALES_*.csv), tables, feeds, APIs, processor names or short ids, config rows (OBJ_DEFINITION:12)"},
         "ticket": {"type": "string"}, "author": {"type": "string", "description": "e.g. claude, gemini, or the person"}},
         "required": ["title", "body"]}},
    {"name": "retire_learning",
     "description": "Mark a learning obsolete (kept for history), e.g. after the underlying problem was fixed for good or a better one replaces it.",
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string"}, "replaced_by": {"type": "string"}},
                     "required": ["id"]}},
    {"name": "logs",
     "description": ("Warnings / errors from nifi-app.log and nifi-bootstrap.log, grouped by message shape with counts and the root "
                     "cause (exception). Filter by processor, file name, FlowFile uuid, text, level (LIFECYCLE = NiFi starts / stops / "
                     "crashes) or the last N hours. Most processors log an ERROR before routing a FlowFile to failure."),
     "inputSchema": {"type": "object", "properties": {
         "component": {"type": "string"}, "file": {"type": "string"}, "uuid": {"type": "string"}, "grep": {"type": "string"},
         "level": {"type": "string", "enum": ["WARN", "ERROR", "FATAL", "LIFECYCLE"]}, "since_hours": {"type": "number"},
         "limit": {"type": "integer", "default": 30}}}},
    {"name": "provenance",
     "description": ("Where a FlowFile went and where / why it ended, from NiFi provenance via the REST API: every event of the FlowFiles "
                     "with this file name (or uuid, or a processor's recent events), and a verdict - DROPPED at which processor and why "
                     "(auto-terminated relationship, expired, ...), sent where, or still in flight. Use it for 'file disappeared / "
                     "silently dropped' tickets. Needs [nifi_api] in nifikb.toml."),
     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "uuid": {"type": "string"},
                                                      "component": {"type": "string"}}}},
    {"name": "load_audit",
     "description": "The platform's load-audit rows (status, error message, row count, time) for a file name or a definition id. Needs [audit].",
     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "definition": {"type": "string"},
                                                      "limit": {"type": "integer", "default": 10}}}},
    {"name": "daily_report",
     "description": ("Health report for the last N hours: new error patterns, most frequent errors, NiFi restarts / crashes, failed loads, "
                     "config-row and flow changes, metadata drift, live health. Use for 'what went wrong overnight / is everything ok'."),
     "inputSchema": {"type": "object", "properties": {"hours": {"type": "number", "default": 24}}}},
    {"name": "late_files",
     "description": ("Feeds whose next file is overdue: each feed's usual arrival pattern (every N minutes, daily around HH:MM on "
                     "which weekdays, weekly) is learned from the load-audit history. Use for 'file not received' tickets and "
                     "'is anything missing today'."),
     "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "default": 35}}}},
    {"name": "ticket",
     "description": ("Read a Jira / ServiceNow ticket by id (PROJ-123 / INC0012345), extract the file / feed / table names, error "
                     "text, headers and attached samples, run investigate on them and return the report plus a draft reply. "
                     "Never posts: a person posts with `python -m nifikb ticket <id> --post`."),
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "live": {"type": "boolean", "default": False}},
                     "required": ["id"]}},
    {"name": "check_target_output",
     "description": ("Target side of a load (HDFS / S3 / mounted folder, read-only): the files under the definition's location, "
                     "the output for one input file, zero-byte / stale outputs, and the written Parquet schema vs the structure rows "
                     "(missing columns, type differences). Use for 'loaded but data missing / wrong in Hive / Athena'."),
     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "key": {"type": "string", "description": "feed / table name"},
                                                     "location": {"type": "string"}, "hours": {"type": "number"}}}},
    {"name": "check_new_feed",
     "description": ("Onboarding a new feed / file / API: validate the PROPOSED config rows before anyone inserts them - column names "
                     "and types of the config tables, required columns, duplicate ids / names, whether an existing definition would "
                     "also match the file, structure sequence / types / lengths, the target table, a sample file, and differences "
                     "to a similar existing feed ('like'). Returns problems and INSERT statements for a human to review. "
                     "Give proposal_path (TOML / JSON file) or proposal (object: definition, structure, rows, example_file, sample, like)."),
     "inputSchema": {"type": "object", "properties": {
         "proposal_path": {"type": "string"},
         "proposal": {"type": "object", "description": "{definition: {COL: value}, structure: [{COL: value}], rows: {TABLE: [{COL: value}]}, "
                                                       "example_file, sample, like}"},
         "live": {"type": "boolean", "default": False}}}},
    {"name": "compare",
     "description": ("Compare this environment with another (e.g. 'works in UAT, fails in PROD'): processors / properties / "
                     "parameters of the two flows and the config-table rows of the two databases, optionally for one file / feed. "
                     "env = an [environments.<name>] section; or flow (file path) / db ([[databases]] name)."),
     "inputSchema": {"type": "object", "properties": {"env": {"type": "string"}, "flow": {"type": "string"}, "db": {"type": "string"},
                                                     "key": {"type": "string", "description": "file / feed / table: only its definition"},
                                                     "what": {"type": "string", "enum": ["all", "flow", "config"], "default": "all"}}}},
    {"name": "versions",
     "description": ("Version-controlled process groups: deployed registry version, live state (UP_TO_DATE / LOCALLY_MODIFIED / STALE) "
                     "and the registry's version history (author, time, commit comment). Use for 'what changed before it broke'."),
     "inputSchema": {"type": "object", "properties": {"group": {"type": "string"}, "limit": {"type": "integer", "default": 10}}}},
    {"name": "health",
     "description": ("Live NiFi health (REST API): queues at / near back-pressure, FlowFiles stuck in front of a stopped / invalid / "
                     "disabled processor, invalid processors with NiFi's validation errors, controller services not enabled, full "
                     "content / provenance / FlowFile repositories, high heap, disconnected cluster nodes. Use it for 'nothing is "
                     "being processed' / 'files are delayed' tickets. Needs [nifi_api]."),
     "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number", "default": 80}}}},
    {"name": "bulletins",
     "description": "Current NiFi bulletins (the errors shown in the UI; NiFi keeps them about 5 minutes). Needs [nifi_api].",
     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 50}}}},
    {"name": "doctor",
     "description": "Check the installation (config, NiFi files, repos, databases, metadata roles, KB freshness, agent setup) when results look incomplete.",
     "inputSchema": {"type": "object", "properties": {"offline": {"type": "boolean", "default": False}}}},
]


class Server:
    def __init__(self, config_path=None):
        from .config import load_config
        self.cfg = load_config(config_path)
        self.config_path = self.cfg["_path"]
        self.kb = Path(self.cfg["output"]["dir"])

    # -------------------------------------------------------------------------------------------- tools
    def _cli(self, *argv):
        from . import cli
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rc = cli.main(["--config", self.config_path, *argv])
            except SystemExit as e:  # _store() exits when the KB is not built yet
                rc = 1
                if e.code and not isinstance(e.code, int):
                    print(e.code)
        return buf.getvalue().strip(), bool(rc)

    def _check_new_feed(self, a):
        import tempfile
        if a.get("proposal_path"):
            return self._cli("onboard", a["proposal_path"], *(["--live"] if a.get("live") else []))
        if not isinstance(a.get("proposal"), dict):
            return "give proposal_path or proposal", True
        proposal = dict(a["proposal"])
        for k in ("sample", "structure_csv"):  # relative to where the agent runs, not to the temporary file
            if proposal.get(k):
                proposal[k] = str(Path(proposal[k]).resolve())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "proposal.json"
            path.write_text(json.dumps(proposal), encoding="utf-8")
            return self._cli("onboard", str(path), *(["--live"] if a.get("live") else []))

    def call(self, name, a):
        if name == "kb_overview":
            index = self.kb / "INDEX.md"
            if not index.exists():
                return "Knowledge base not built yet: call the build tool.", True
            from . import learnings as lm
            status, _ = self._cli("status")
            text = index.read_text(encoding="utf-8")
            if len(text) > 30000:
                text = text[:30000] + f"\n\n[… INDEX.md continues: read_kb_file path=INDEX.md offset=30000 — or use search]"
            errors, _ = self._cli("logs", "--level", "ERROR", "--since", "24", "--limit", "5")
            if "no matching" not in errors:
                text += "\n\n# NiFi log errors in the last 24 h of the logs (logs tool for more)\n" + errors
            ctx = lm.context_text(self.cfg)
            recent = lm.load_all(self.cfg, include_obsolete=False)[:15]
            team = ("\n\n# Team context (knowledge/context.md)\n" + ctx) if ctx else \
                "\n\n# Team context\n(knowledge/context.md is still the template - ask the user to fill it in)"
            team += "\n\n# Recent team learnings (find_learnings / get_learning)\n" + (
                "\n".join(lm.format_item(i, full=False) for i in recent) if recent else "(none yet - add_learning after solving a ticket)")
            sugg, _ = self._cli("learn", "suggest")
            if sugg.startswith("- "):
                team += "\n\n# Recurring causes with no learning yet (once one is confirmed in a ticket, add_learning)\n" + sugg
            return f"{status}\n\n{text}{team}", False
        if name == "search":
            return self._cli("search", *str(a["query"]).split(), "--limit", str(int(a.get("limit", 15))))
        if name == "show":
            return self._cli("show", a["ref"])
        if name == "trace":
            return self._cli("trace", a["ref"], "--depth", str(int(a.get("depth", 40))), *(["--up"] if a.get("upstream") else []))
        if name == "diagnose":
            return self._diagnose(a)
        if name == "issues":
            return self._issues(a)
        if name == "read_kb_file":
            return self._read(a)
        if name == "sql":
            return self._cli("sql", a["query"], "--max-rows", str(int(a.get("max_rows", 100))), *(["--db", a["db"]] if a.get("db") else []))
        if name == "build":
            return self._cli("build", *(["--force"] if a.get("force") else []), *(["--refresh-db"] if a.get("refresh_db") else []))
        if name in ("find_learnings", "get_learning", "add_learning", "retire_learning"):
            return self._learning(name, a)
        if name == "investigate":
            argv = ["investigate", "--since", str(a.get("since_hours", 72))]
            for k, flag in (("file", "--file"), ("feed", "--feed"), ("table", "--table"), ("error_text", "--error"),
                            ("sample_path", "--sample")):
                if a.get(k):
                    argv += [flag, str(a[k])]
            if a.get("headers"):
                argv += ["--headers", *[str(h) for h in a["headers"]]]
            if a.get("live"):
                argv.append("--live")
            return self._cli(*argv)
        if name == "logs":
            argv = ["logs", "--limit", str(int(a.get("limit", 30)))]
            for k, flag in (("component", "--component"), ("file", "--file"), ("uuid", "--uuid"), ("grep", "--grep"),
                            ("level", "--level"), ("since_hours", "--since")):
                if a.get(k) not in (None, ""):
                    argv += [flag, str(a[k])]
            return self._cli(*argv)
        if name == "provenance":
            argv = ["provenance"]
            for k in ("file", "uuid", "component"):
                if a.get(k):
                    argv += [f"--{k}", str(a[k])]
            return self._cli(*argv)
        if name == "load_audit":
            argv = ["audit", "--limit", str(int(a.get("limit", 10)))]
            for k in ("file", "definition"):
                if a.get(k):
                    argv += [f"--{k}", str(a[k])]
            return self._cli(*argv)
        if name == "daily_report":
            return self._cli("report", "--hours", str(a.get("hours", 24)))
        if name == "late_files":
            return self._cli("late", "--days", str(int(a.get("days", 35))))
        if name == "ticket":
            return self._cli("ticket", str(a["id"]), *(["--live"] if a.get("live") else []))
        if name == "check_target_output":
            extra = [x for k in ("file", "key", "location", "hours") if a.get(k) for x in (f"--{k}", str(a[k]))]
            return self._cli("target", *extra)
        if name == "check_new_feed":
            return self._check_new_feed(a)
        if name == "compare":
            extra = [x for k in ("env", "flow", "db", "key", "what") if a.get(k) for x in (f"--{k}", str(a[k]))]
            return self._cli("compare", *extra)
        if name == "versions":
            return self._cli("versions", "--limit", str(int(a.get("limit", 10))), *(["--group", a["group"]] if a.get("group") else []))
        if name == "health":
            return self._cli("health", "--threshold", str(a.get("threshold", 80)))
        if name == "bulletins":
            return self._cli("bulletins", "--limit", str(int(a.get("limit", 50))))
        if name == "doctor":
            return self._cli("doctor", *(["--offline"] if a.get("offline") else []))
        return f"unknown tool {name}", True

    def _learning(self, name, a):
        from . import learnings as lm
        from .cli import index_learning
        if name == "find_learnings":
            terms = [str(t) for t in a.get("terms") or [] if t]
            limit = int(a.get("limit", 10))
            if terms:
                items = lm.relevant(self.cfg, terms + [w for t in terms for w in str(t).split()], limit=limit)
            else:
                items = lm.load_all(self.cfg, include_obsolete=bool(a.get("include_retired")))
            if a.get("tag"):
                items = [i for i in items if a["tag"].lower() in i["tags"]]
            items = items[:limit]
            return ("\n\n".join(lm.format_item(i, full=False) + "\n  " + " ".join(i["body"].split())[:300] for i in items)
                    or "no matching learnings"), False
        if name == "get_learning":
            item = lm.get(self.cfg, str(a["id"]))
            return (lm.format_item(item), False) if item else (f"no learning '{a['id']}'", True)
        if name == "add_learning":
            try:
                item, warnings = lm.add(self.cfg, a.get("title"), a.get("body"), kind=a.get("kind") or "fix", tags=a.get("tags") or [],
                                        applies_to=a.get("applies_to") or [], ticket=a.get("ticket"), author=a.get("author"))
            except ValueError as e:
                return f"not saved: {e}", True
            index_learning(self.cfg, item)
            return "\n".join([f"saved {item['id']} ({item['path']})"] + [f"note: {w}" for w in warnings]), False
        try:
            item = lm.retire(self.cfg, str(a["id"]), a.get("reason"), a.get("replaced_by"))
        except ValueError as e:
            return str(e), True
        index_learning(self.cfg, item)
        return f"retired {item['id']}", False

    def _diagnose(self, a):
        from . import diagnose as dg
        from .cli import _store
        headers = [str(h) for h in a.get("headers") or []]
        if a.get("sample_path") and not a.get("key"):
            headers += dg.headers_from_sample(a["sample_path"])
        try:
            store = _store(self.cfg)
        except SystemExit as e:
            return str(e.code), True
        try:
            if a.get("key"):
                result = dg.metadata_diagnosis(self.cfg, store, str(a["key"]), headers, live=bool(a.get("live")),
                                               sample_path=a.get("sample_path"))
            elif headers:
                result = dg.record_diagnosis(store, headers, self.cfg)
            else:
                return "give key (file / table / feed / API name) and/or headers or sample_path", True
        finally:
            store.db.close()
        if a.get("structured"):
            return json.dumps(result, default=str)[:60000], bool(result.get("error"))
        return dg.format_text(result), bool(result.get("error"))

    def _issues(self, a):
        argv = ["issues", "--limit", str(int(a.get("limit", 100)))]
        for k in ("kind", "severity", "contains"):
            if a.get(k):
                argv += [f"--{k}", str(a[k])]
        return self._cli(*argv)

    def _read(self, a):
        target = (self.kb / str(a["path"])).resolve()
        if self.kb.resolve() not in target.parents or target.suffix.lower() != ".md" or not target.is_file():
            return "path must be a .md file inside the knowledge base folder (see kb_overview for the list)", True
        text = target.read_text(encoding="utf-8")
        off, n = int(a.get("offset", 0)), int(a.get("max_chars", 60000))
        chunk = text[off:off + n]
        more = f"\n\n[… {len(text) - off - n} more characters: call again with offset={off + n}]" if off + n < len(text) else ""
        return chunk + more, False

    # -------------------------------------------------------------------------------------------- protocol
    def handle(self, msg):
        method, mid = msg.get("method"), msg.get("id")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTOCOL,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "nifikb", "version": __version__},
                "instructions": ("NiFi flow knowledge base. Start with kb_overview. For ANY support ticket call investigate first with "
                                 "the file / feed / table / error text / headers from the ticket: it returns ranked likely causes "
                                 "(provenance drop, log errors, metadata mismatches, config changes, code line, learnings) with evidence. "
                                 "Use diagnose / provenance / logs / search / show / trace only when that report is not conclusive. "
                                 "After solving a ticket, add_learning when the cause or fix is reusable and not derivable from the KB. "
                                 "Flow, code and databases are read-only; never claim a fix was applied - propose it.")}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
        if method == "tools/call":
            p = msg.get("params") or {}
            try:
                text, is_error = self.call(p.get("name"), p.get("arguments") or {})
            except Exception as e:  # report tool failures to the agent instead of dying
                text, is_error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}", True
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text or "(no output)"}], "isError": is_error}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": mid, "result": {}}
        if mid is None:  # notifications (initialized, cancelled, ...)
            return None
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(config_path=None, stdin=None, stdout=None):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    server = Server(config_path)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            stdout.flush()
            continue
        reply = server.handle(msg)
        if reply is not None:
            stdout.write(json.dumps(reply, default=str) + "\n")
            stdout.flush()
