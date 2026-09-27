# nifi-kb 0.5.0 - paste bundle, part 3 of 5 - 8 files. Save as nifi-kb-0.5.0-bundle-part3of5.py, then run:  python nifi-kb-0.5.0-bundle-part3of5.py
"""nifi-kb paste bundle: recreates the nifi-kb folder from this single file (for machines where files cannot be
downloaded, only text pasted).

    python <this file> [target folder]        default target: a folder "nifi-kb" next to this file

Everything below the DATA line is the content of the files, stored as comment lines ("#|" + the line) so the whole file
stays plain, readable text and valid Python. Each file's hash is checked; a file whose paste was damaged is NOT written
and is listed, so only that part needs pasting again. Your own nifikb.toml and knowledge/ files are never overwritten.
Standard library only; Python 3.8+ can unpack, nifi-kb itself needs 3.11+.
"""
import base64
import hashlib
import sys
from pathlib import Path, PurePosixPath

KEEP = ("nifikb.toml", "knowledge/")  # yours after the first unpack: never overwritten
DATA_LINE = "# ==== DATA ===="


def text_hash(text):
    """Hash that survives a copy / paste: line endings and trailing blanks do not count."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


def safe_path(rel):
    p = PurePosixPath(rel)
    if p.is_absolute() or ".." in p.parts or ":" in rel or not rel:
        raise ValueError(f"unsafe path in bundle: {rel!r}")
    return p


def parse(lines):
    """[(kind, path, mode, hash, content lines or source path)], (part, parts, count) from the END line or None."""
    entries, current, end, seen_data = [], None, None, False
    for n, raw in enumerate(lines, 1):
        line = raw.rstrip("\r\n")
        if not seen_data:
            seen_data = line.strip() == DATA_LINE
            continue
        if line.startswith("#|"):
            if current is None:
                raise ValueError(f"line {n}: content before any file header")
            current[4].append(line[2:])
        elif line.startswith("#@@ FILE "):
            _, _, path, mode, digest = line.split(" ")[:5]
            current = ["file", path, mode, digest, []]
            entries.append(current)
        elif line.startswith("#@@ COPY "):
            _, _, path, source = line.split(" ")[:4]
            entries.append(["copy", path, None, None, source])
            current = None
        elif line.startswith("#@@ END "):
            bits = line.split()
            end = (int(bits[3]), int(bits[5]), int(bits[7]))  # "#@@ END part 1 of 3 files 42"
            current = None
        elif line.strip() in ("", "#"):
            continue  # an editor added or trimmed an empty line
        else:
            raise ValueError(f"line {n} is not part of the bundle (damaged paste?): {line[:60]!r}")
    if not seen_data:
        raise ValueError(f"no '{DATA_LINE}' line - this is not a complete nifi-kb bundle")
    return entries, end


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    me = Path(__file__).resolve()
    target = Path(argv[0]).resolve() if argv else me.parent / "nifi-kb"
    with open(me, encoding="utf-8-sig") as f:
        entries, end = parse(f.readlines())
    files = [e for e in entries if e[0] == "file"]
    if end is None:
        print("ERROR: the bundle is incomplete (its last line '#@@ END ...' is missing) - the paste was cut off. "
              "Copy the whole file again (Ctrl+A in the source view).")
        return 2
    part, parts, count = end
    if count != len(files) + sum(1 for e in entries if e[0] == "copy"):
        print(f"ERROR: expected {count} files in this part, found {len(entries)} - the paste lost lines; copy it again.")
        return 2
    written, kept, bad = [], [], []
    contents = {}
    for kind, rel, mode, digest, body in entries:
        path = safe_path(rel)
        if kind == "copy":
            if body not in contents:
                bad.append(f"{rel} (copy of {body}, which is not in this part or was damaged)")
                continue
            data = contents[body]
        elif mode == "b":
            data = base64.b64decode("".join(body))
            if hashlib.sha256(data).hexdigest()[:16] != digest:
                bad.append(rel)
                continue
        else:
            text = "\n".join(body) + ("\n" if mode in ("t", "tc") else "")
            if text_hash(text) != digest:
                bad.append(rel)
                continue
            data = (text.replace("\n", "\r\n") if mode in ("tc", "tcn") else text).encode("utf-8")
        contents[rel] = data
        dest = target / Path(*path.parts)
        if dest.exists() and (rel == KEEP[0] or rel.startswith(KEEP[1])) and rel != "knowledge/README.md":
            kept.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        written.append(rel)
    print(f"part {part} of {parts}: {len(written)} files written to {target}" + (f", {len(kept)} of yours kept ({', '.join(kept)})" if kept else ""))
    if bad:
        print(f"ERROR: {len(bad)} file(s) damaged in the paste and NOT written - copy this part again:")
        for b in bad:
            print(f"  {b}")
        return 1
    if part == parts:
        print("Next: cd into the folder, then  python -m unittest discover -s tests  (expect OK),  edit nifikb.toml,  "
              "python -m nifikb build,  python -m nifikb doctor  - see HANDOFF.md section 4.")
    else:
        print(f"Now unpack part {part + 1} of {parts} the same way (into the same folder).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# ==== DATA ====
#@@ FILE nifikb/mcp.py tc 8df9e4208c4e1fd7
#|"""MCP server (stdio, JSON-RPC 2.0, stdlib only) exposing the knowledge base to AI agents: Claude Code, Gemini CLI or
#|any MCP client. Everything is read-only except `build`, which only rewrites the kb/ folder.
#|
#|    python -m nifikb mcp [--config nifikb.toml]
#|"""
#|import contextlib
#|import io
#|import json
#|import sys
#|import traceback
#|from pathlib import Path
#|
#|from . import __version__
#|
#|PROTOCOL = "2025-06-18"
#|
#|TOOLS = [
#|    {"name": "investigate",
#|     "description": ("START HERE FOR ANY SUPPORT TICKET. One call runs every check - metadata config rows vs the file / target, "
#|                     "provenance (where the FlowFile was dropped and why), NiFi log errors for the file and the processors involved, "
#|                     "the code line that raises the error text, recent config-row changes, team learnings, static findings - and "
#|                     "returns a ranked list of likely causes with the evidence. Give whatever the ticket has: file name, feed / API "
#|                     "name, target table, error text, headers or a sample file."),
#|     "inputSchema": {"type": "object", "properties": {
#|         "file": {"type": "string", "description": "file name from the ticket, e.g. SALES_20260926.csv"},
#|         "feed": {"type": "string", "description": "feed / API / source name"},
#|         "table": {"type": "string", "description": "target table"},
#|         "error_text": {"type": "string", "description": "error message quoted in the ticket (a distinctive fragment is enough)"},
#|         "headers": {"type": "array", "items": {"type": "string"}, "description": "field names sent, in file order"},
#|         "sample_path": {"type": "string", "description": "path to a sample CSV / JSON file"},
#|         "live": {"type": "boolean", "default": False, "description": "read the config rows now (they may have changed)"},
#|         "since_hours": {"type": "number", "default": 72, "description": "hours of processor log errors to include"}}}},
#|    {"name": "kb_overview",
#|     "description": "Start here. The knowledge base index: flows (process groups), external systems, issue counts, build time.",
#|     "inputSchema": {"type": "object", "properties": {}}},
#|    {"name": "search",
#|     "description": "Full-text search over processors, properties, SQL, tables, code, labels, metadata definitions and config rows.",
#|     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 15}},
#|                     "required": ["query"]}},
#|    {"name": "show",
#|     "description": "One component (processor / controller service / port) with all its settings, by name or id prefix; or a process group / custom class.",
#|     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]}},
#|    {"name": "trace",
#|     "description": "Data path downstream from a component (or upstream with upstream=true), across process groups.",
#|     "inputSchema": {"type": "object", "properties": {"ref": {"type": "string"}, "upstream": {"type": "boolean", "default": False},
#|                                                      "depth": {"type": "integer", "default": 40}}, "required": ["ref"]}},
#|    {"name": "diagnose",
#|     "description": ("Support triage. Give the incoming headers / JSON keys and/or a file name, target table, feed or API name. Returns what "
#|                     "the metadata config tables and the flow expect (structure, order, types, target table), what does not match, "
#|                     "the related feed/API/server config rows (secrets masked), the processors involved and their known issues."),
#|     "inputSchema": {"type": "object", "properties": {
#|         "key": {"type": "string", "description": "file name (e.g. SALES_20260926.csv), target table, feed or API name"},
#|         "headers": {"type": "array", "items": {"type": "string"}, "description": "incoming field names, in file order"},
#|         "sample_path": {"type": "string", "description": "path to a sample CSV/JSON file to read the headers from"},
#|         "live": {"type": "boolean", "default": False, "description": "read the config tables now instead of the last snapshot"},
#|         "structured": {"type": "boolean", "default": False,
#|                        "description": "return JSON instead of text (only when you need to post-process; the text has the same facts)"}}}},
#|    {"name": "issues",
#|     "description": "Static findings: invalid processors, dropped failures, missing tables, field/column mismatches, metadata drift.",
#|     "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "severity": {"type": "string"},
#|                                                      "contains": {"type": "string"}, "limit": {"type": "integer", "default": 100}}}},
#|    {"name": "read_kb_file",
#|     "description": "Read a file of the knowledge base, e.g. flows/<group>.md, services.md, metadata.md, db/<name>.md, scripts/<x>.md.",
#|     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer", "default": 0},
#|                                                      "max_chars": {"type": "integer", "default": 60000}}, "required": ["path"]}},
#|    {"name": "sql",
#|     "description": "Read-only query (single SELECT/WITH/SHOW/DESCRIBE) against a configured database; sensitive columns are masked.",
#|     "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "db": {"type": "string"},
#|                                                      "max_rows": {"type": "integer", "default": 100}}, "required": ["query"]}},
#|    {"name": "build",
#|     "description": "Refresh the knowledge base from the flow, NARs, code repos and databases (no-op when nothing changed).",
#|     "inputSchema": {"type": "object", "properties": {"force": {"type": "boolean", "default": False},
#|                                                      "refresh_db": {"type": "boolean", "default": False}}}},
#|    {"name": "find_learnings",
#|     "description": ("Team learnings from earlier tickets (symptom, cause, fix). Give terms (file names, tables, feeds, processor names, "
#|                     "error words) to get the relevant ones, or none to list the most recent. Check these before concluding a diagnosis."),
#|     "inputSchema": {"type": "object", "properties": {"terms": {"type": "array", "items": {"type": "string"}},
#|                                                      "tag": {"type": "string"}, "limit": {"type": "integer", "default": 10},
#|                                                      "include_retired": {"type": "boolean", "default": False}}}},
#|    {"name": "get_learning",
#|     "description": "Full text of one learning by id (from find_learnings, diagnose or search).",
#|     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
#|    {"name": "add_learning",
#|     "description": ("Record something reusable learned while solving a ticket, so every future session (Claude, Gemini, people) knows it. "
#|                     "Only for knowledge the KB cannot derive itself: a root cause pattern, a vendor quirk, a fix procedure, a convention, "
#|                     "a misleading symptom. Not for one-off facts or anything the flow / code / tables already show. Never include "
#|                     "secrets or personal data (they are redacted anyway). Body in markdown with ## Symptom, ## Cause, ## Fix, "
#|                     "## How to spot it next time. Search find_learnings first and retire_learning an outdated one instead of duplicating."),
#|     "inputSchema": {"type": "object", "properties": {
#|         "title": {"type": "string", "description": "one line, specific: 'SALES feed switches to pipe delimiter at month end'"},
#|         "body": {"type": "string"},
#|         "kind": {"type": "string", "enum": ["fix", "pattern", "gotcha", "context", "faq"], "default": "fix"},
#|         "tags": {"type": "array", "items": {"type": "string"}},
#|         "applies_to": {"type": "array", "items": {"type": "string"},
#|                        "description": "file names or patterns (SALES_*.csv), tables, feeds, APIs, processor names or short ids, config rows (OBJ_DEFINITION:12)"},
#|         "ticket": {"type": "string"}, "author": {"type": "string", "description": "e.g. claude, gemini, or the person"}},
#|         "required": ["title", "body"]}},
#|    {"name": "retire_learning",
#|     "description": "Mark a learning obsolete (kept for history), e.g. after the underlying problem was fixed for good or a better one replaces it.",
#|     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string"}, "replaced_by": {"type": "string"}},
#|                     "required": ["id"]}},
#|    {"name": "logs",
#|     "description": ("Warnings / errors from nifi-app.log and nifi-bootstrap.log, grouped by message shape with counts and the root "
#|                     "cause (exception). Filter by processor, file name, FlowFile uuid, text, level (LIFECYCLE = NiFi starts / stops / "
#|                     "crashes) or the last N hours. Most processors log an ERROR before routing a FlowFile to failure."),
#|     "inputSchema": {"type": "object", "properties": {
#|         "component": {"type": "string"}, "file": {"type": "string"}, "uuid": {"type": "string"}, "grep": {"type": "string"},
#|         "level": {"type": "string", "enum": ["WARN", "ERROR", "FATAL", "LIFECYCLE"]}, "since_hours": {"type": "number"},
#|         "limit": {"type": "integer", "default": 30}}}},
#|    {"name": "provenance",
#|     "description": ("Where a FlowFile went and where / why it ended, from NiFi provenance via the REST API: every event of the FlowFiles "
#|                     "with this file name (or uuid, or a processor's recent events), and a verdict - DROPPED at which processor and why "
#|                     "(auto-terminated relationship, expired, ...), sent where, or still in flight. Use it for 'file disappeared / "
#|                     "silently dropped' tickets. Needs [nifi_api] in nifikb.toml."),
#|     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "uuid": {"type": "string"},
#|                                                      "component": {"type": "string"}}}},
#|    {"name": "load_audit",
#|     "description": "The platform's load-audit rows (status, error message, row count, time) for a file name or a definition id. Needs [audit].",
#|     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "definition": {"type": "string"},
#|                                                      "limit": {"type": "integer", "default": 10}}}},
#|    {"name": "daily_report",
#|     "description": ("Health report for the last N hours: new error patterns, most frequent errors, NiFi restarts / crashes, failed loads, "
#|                     "config-row and flow changes, metadata drift, live health. Use for 'what went wrong overnight / is everything ok'."),
#|     "inputSchema": {"type": "object", "properties": {"hours": {"type": "number", "default": 24}}}},
#|    {"name": "late_files",
#|     "description": ("Feeds whose next file is overdue: each feed's usual arrival pattern (every N minutes, daily around HH:MM on "
#|                     "which weekdays, weekly) is learned from the load-audit history. Use for 'file not received' tickets and "
#|                     "'is anything missing today'."),
#|     "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "default": 35}}}},
#|    {"name": "ticket",
#|     "description": ("Read a Jira / ServiceNow ticket by id (PROJ-123 / INC0012345), extract the file / feed / table names, error "
#|                     "text, headers and attached samples, run investigate on them and return the report plus a draft reply. "
#|                     "Never posts: a person posts with `python -m nifikb ticket <id> --post`."),
#|     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}, "live": {"type": "boolean", "default": False}},
#|                     "required": ["id"]}},
#|    {"name": "check_target_output",
#|     "description": ("Target side of a load (HDFS / S3 / mounted folder, read-only): the files under the definition's location, "
#|                     "the output for one input file, zero-byte / stale outputs, and the written Parquet schema vs the structure rows "
#|                     "(missing columns, type differences). Use for 'loaded but data missing / wrong in Hive / Athena'."),
#|     "inputSchema": {"type": "object", "properties": {"file": {"type": "string"}, "key": {"type": "string", "description": "feed / table name"},
#|                                                     "location": {"type": "string"}, "hours": {"type": "number"}}}},
#|    {"name": "check_new_feed",
#|     "description": ("Onboarding a new feed / file / API: validate the PROPOSED config rows before anyone inserts them - column names "
#|                     "and types of the config tables, required columns, duplicate ids / names, whether an existing definition would "
#|                     "also match the file, structure sequence / types / lengths, the target table, a sample file, and differences "
#|                     "to a similar existing feed ('like'). Returns problems and INSERT statements for a human to review. "
#|                     "Give proposal_path (TOML / JSON file) or proposal (object: definition, structure, rows, example_file, sample, like)."),
#|     "inputSchema": {"type": "object", "properties": {
#|         "proposal_path": {"type": "string"},
#|         "proposal": {"type": "object", "description": "{definition: {COL: value}, structure: [{COL: value}], rows: {TABLE: [{COL: value}]}, "
#|                                                       "example_file, sample, like}"},
#|         "live": {"type": "boolean", "default": False}}}},
#|    {"name": "compare",
#|     "description": ("Compare this environment with another (e.g. 'works in UAT, fails in PROD'): processors / properties / "
#|                     "parameters of the two flows and the config-table rows of the two databases, optionally for one file / feed. "
#|                     "env = an [environments.<name>] section; or flow (file path) / db ([[databases]] name)."),
#|     "inputSchema": {"type": "object", "properties": {"env": {"type": "string"}, "flow": {"type": "string"}, "db": {"type": "string"},
#|                                                     "key": {"type": "string", "description": "file / feed / table: only its definition"},
#|                                                     "what": {"type": "string", "enum": ["all", "flow", "config"], "default": "all"}}}},
#|    {"name": "versions",
#|     "description": ("Version-controlled process groups: deployed registry version, live state (UP_TO_DATE / LOCALLY_MODIFIED / STALE) "
#|                     "and the registry's version history (author, time, commit comment). Use for 'what changed before it broke'."),
#|     "inputSchema": {"type": "object", "properties": {"group": {"type": "string"}, "limit": {"type": "integer", "default": 10}}}},
#|    {"name": "health",
#|     "description": ("Live NiFi health (REST API): queues at / near back-pressure, FlowFiles stuck in front of a stopped / invalid / "
#|                     "disabled processor, invalid processors with NiFi's validation errors, controller services not enabled, full "
#|                     "content / provenance / FlowFile repositories, high heap, disconnected cluster nodes. Use it for 'nothing is "
#|                     "being processed' / 'files are delayed' tickets. Needs [nifi_api]."),
#|     "inputSchema": {"type": "object", "properties": {"threshold": {"type": "number", "default": 80}}}},
#|    {"name": "bulletins",
#|     "description": "Current NiFi bulletins (the errors shown in the UI; NiFi keeps them about 5 minutes). Needs [nifi_api].",
#|     "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 50}}}},
#|    {"name": "doctor",
#|     "description": "Check the installation (config, NiFi files, repos, databases, metadata roles, KB freshness, agent setup) when results look incomplete.",
#|     "inputSchema": {"type": "object", "properties": {"offline": {"type": "boolean", "default": False}}}},
#|]
#|
#|
#|class Server:
#|    def __init__(self, config_path=None):
#|        from .config import load_config
#|        self.cfg = load_config(config_path)
#|        self.config_path = self.cfg["_path"]
#|        self.kb = Path(self.cfg["output"]["dir"])
#|
#|    # -------------------------------------------------------------------------------------------- tools
#|    def _cli(self, *argv):
#|        from . import cli
#|        buf = io.StringIO()
#|        with contextlib.redirect_stdout(buf):
#|            try:
#|                rc = cli.main(["--config", self.config_path, *argv])
#|            except SystemExit as e:  # _store() exits when the KB is not built yet
#|                rc = 1
#|                if e.code and not isinstance(e.code, int):
#|                    print(e.code)
#|        return buf.getvalue().strip(), bool(rc)
#|
#|    def _check_new_feed(self, a):
#|        import tempfile
#|        if a.get("proposal_path"):
#|            return self._cli("onboard", a["proposal_path"], *(["--live"] if a.get("live") else []))
#|        if not isinstance(a.get("proposal"), dict):
#|            return "give proposal_path or proposal", True
#|        proposal = dict(a["proposal"])
#|        for k in ("sample", "structure_csv"):  # relative to where the agent runs, not to the temporary file
#|            if proposal.get(k):
#|                proposal[k] = str(Path(proposal[k]).resolve())
#|        with tempfile.TemporaryDirectory() as tmp:
#|            path = Path(tmp) / "proposal.json"
#|            path.write_text(json.dumps(proposal), encoding="utf-8")
#|            return self._cli("onboard", str(path), *(["--live"] if a.get("live") else []))
#|
#|    def call(self, name, a):
#|        if name == "kb_overview":
#|            index = self.kb / "INDEX.md"
#|            if not index.exists():
#|                return "Knowledge base not built yet: call the build tool.", True
#|            from . import learnings as lm
#|            status, _ = self._cli("status")
#|            text = index.read_text(encoding="utf-8")
#|            if len(text) > 30000:
#|                text = text[:30000] + f"\n\n[… INDEX.md continues: read_kb_file path=INDEX.md offset=30000 — or use search]"
#|            errors, _ = self._cli("logs", "--level", "ERROR", "--since", "24", "--limit", "5")
#|            if "no matching" not in errors:
#|                text += "\n\n# NiFi log errors in the last 24 h of the logs (logs tool for more)\n" + errors
#|            ctx = lm.context_text(self.cfg)
#|            recent = lm.load_all(self.cfg, include_obsolete=False)[:15]
#|            team = ("\n\n# Team context (knowledge/context.md)\n" + ctx) if ctx else \
#|                "\n\n# Team context\n(knowledge/context.md is still the template - ask the user to fill it in)"
#|            team += "\n\n# Recent team learnings (find_learnings / get_learning)\n" + (
#|                "\n".join(lm.format_item(i, full=False) for i in recent) if recent else "(none yet - add_learning after solving a ticket)")
#|            sugg, _ = self._cli("learn", "suggest")
#|            if sugg.startswith("- "):
#|                team += "\n\n# Recurring causes with no learning yet (once one is confirmed in a ticket, add_learning)\n" + sugg
#|            return f"{status}\n\n{text}{team}", False
#|        if name == "search":
#|            return self._cli("search", *str(a["query"]).split(), "--limit", str(int(a.get("limit", 15))))
#|        if name == "show":
#|            return self._cli("show", a["ref"])
#|        if name == "trace":
#|            return self._cli("trace", a["ref"], "--depth", str(int(a.get("depth", 40))), *(["--up"] if a.get("upstream") else []))
#|        if name == "diagnose":
#|            return self._diagnose(a)
#|        if name == "issues":
#|            return self._issues(a)
#|        if name == "read_kb_file":
#|            return self._read(a)
#|        if name == "sql":
#|            return self._cli("sql", a["query"], "--max-rows", str(int(a.get("max_rows", 100))), *(["--db", a["db"]] if a.get("db") else []))
#|        if name == "build":
#|            return self._cli("build", *(["--force"] if a.get("force") else []), *(["--refresh-db"] if a.get("refresh_db") else []))
#|        if name in ("find_learnings", "get_learning", "add_learning", "retire_learning"):
#|            return self._learning(name, a)
#|        if name == "investigate":
#|            argv = ["investigate", "--since", str(a.get("since_hours", 72))]
#|            for k, flag in (("file", "--file"), ("feed", "--feed"), ("table", "--table"), ("error_text", "--error"),
#|                            ("sample_path", "--sample")):
#|                if a.get(k):
#|                    argv += [flag, str(a[k])]
#|            if a.get("headers"):
#|                argv += ["--headers", *[str(h) for h in a["headers"]]]
#|            if a.get("live"):
#|                argv.append("--live")
#|            return self._cli(*argv)
#|        if name == "logs":
#|            argv = ["logs", "--limit", str(int(a.get("limit", 30)))]
#|            for k, flag in (("component", "--component"), ("file", "--file"), ("uuid", "--uuid"), ("grep", "--grep"),
#|                            ("level", "--level"), ("since_hours", "--since")):
#|                if a.get(k) not in (None, ""):
#|                    argv += [flag, str(a[k])]
#|            return self._cli(*argv)
#|        if name == "provenance":
#|            argv = ["provenance"]
#|            for k in ("file", "uuid", "component"):
#|                if a.get(k):
#|                    argv += [f"--{k}", str(a[k])]
#|            return self._cli(*argv)
#|        if name == "load_audit":
#|            argv = ["audit", "--limit", str(int(a.get("limit", 10)))]
#|            for k in ("file", "definition"):
#|                if a.get(k):
#|                    argv += [f"--{k}", str(a[k])]
#|            return self._cli(*argv)
#|        if name == "daily_report":
#|            return self._cli("report", "--hours", str(a.get("hours", 24)))
#|        if name == "late_files":
#|            return self._cli("late", "--days", str(int(a.get("days", 35))))
#|        if name == "ticket":
#|            return self._cli("ticket", str(a["id"]), *(["--live"] if a.get("live") else []))
#|        if name == "check_target_output":
#|            extra = [x for k in ("file", "key", "location", "hours") if a.get(k) for x in (f"--{k}", str(a[k]))]
#|            return self._cli("target", *extra)
#|        if name == "check_new_feed":
#|            return self._check_new_feed(a)
#|        if name == "compare":
#|            extra = [x for k in ("env", "flow", "db", "key", "what") if a.get(k) for x in (f"--{k}", str(a[k]))]
#|            return self._cli("compare", *extra)
#|        if name == "versions":
#|            return self._cli("versions", "--limit", str(int(a.get("limit", 10))), *(["--group", a["group"]] if a.get("group") else []))
#|        if name == "health":
#|            return self._cli("health", "--threshold", str(a.get("threshold", 80)))
#|        if name == "bulletins":
#|            return self._cli("bulletins", "--limit", str(int(a.get("limit", 50))))
#|        if name == "doctor":
#|            return self._cli("doctor", *(["--offline"] if a.get("offline") else []))
#|        return f"unknown tool {name}", True
#|
#|    def _learning(self, name, a):
#|        from . import learnings as lm
#|        from .cli import index_learning
#|        if name == "find_learnings":
#|            terms = [str(t) for t in a.get("terms") or [] if t]
#|            limit = int(a.get("limit", 10))
#|            if terms:
#|                items = lm.relevant(self.cfg, terms + [w for t in terms for w in str(t).split()], limit=limit)
#|            else:
#|                items = lm.load_all(self.cfg, include_obsolete=bool(a.get("include_retired")))
#|            if a.get("tag"):
#|                items = [i for i in items if a["tag"].lower() in i["tags"]]
#|            items = items[:limit]
#|            return ("\n\n".join(lm.format_item(i, full=False) + "\n  " + " ".join(i["body"].split())[:300] for i in items)
#|                    or "no matching learnings"), False
#|        if name == "get_learning":
#|            item = lm.get(self.cfg, str(a["id"]))
#|            return (lm.format_item(item), False) if item else (f"no learning '{a['id']}'", True)
#|        if name == "add_learning":
#|            try:
#|                item, warnings = lm.add(self.cfg, a.get("title"), a.get("body"), kind=a.get("kind") or "fix", tags=a.get("tags") or [],
#|                                        applies_to=a.get("applies_to") or [], ticket=a.get("ticket"), author=a.get("author"))
#|            except ValueError as e:
#|                return f"not saved: {e}", True
#|            index_learning(self.cfg, item)
#|            return "\n".join([f"saved {item['id']} ({item['path']})"] + [f"note: {w}" for w in warnings]), False
#|        try:
#|            item = lm.retire(self.cfg, str(a["id"]), a.get("reason"), a.get("replaced_by"))
#|        except ValueError as e:
#|            return str(e), True
#|        index_learning(self.cfg, item)
#|        return f"retired {item['id']}", False
#|
#|    def _diagnose(self, a):
#|        from . import diagnose as dg
#|        from .cli import _store
#|        headers = [str(h) for h in a.get("headers") or []]
#|        if a.get("sample_path") and not a.get("key"):
#|            headers += dg.headers_from_sample(a["sample_path"])
#|        try:
#|            store = _store(self.cfg)
#|        except SystemExit as e:
#|            return str(e.code), True
#|        try:
#|            if a.get("key"):
#|                result = dg.metadata_diagnosis(self.cfg, store, str(a["key"]), headers, live=bool(a.get("live")),
#|                                               sample_path=a.get("sample_path"))
#|            elif headers:
#|                result = dg.record_diagnosis(store, headers, self.cfg)
#|            else:
#|                return "give key (file / table / feed / API name) and/or headers or sample_path", True
#|        finally:
#|            store.db.close()
#|        if a.get("structured"):
#|            return json.dumps(result, default=str)[:60000], bool(result.get("error"))
#|        return dg.format_text(result), bool(result.get("error"))
#|
#|    def _issues(self, a):
#|        argv = ["issues", "--limit", str(int(a.get("limit", 100)))]
#|        for k in ("kind", "severity", "contains"):
#|            if a.get(k):
#|                argv += [f"--{k}", str(a[k])]
#|        return self._cli(*argv)
#|
#|    def _read(self, a):
#|        target = (self.kb / str(a["path"])).resolve()
#|        if self.kb.resolve() not in target.parents or target.suffix.lower() != ".md" or not target.is_file():
#|            return "path must be a .md file inside the knowledge base folder (see kb_overview for the list)", True
#|        text = target.read_text(encoding="utf-8")
#|        off, n = int(a.get("offset", 0)), int(a.get("max_chars", 60000))
#|        chunk = text[off:off + n]
#|        more = f"\n\n[… {len(text) - off - n} more characters: call again with offset={off + n}]" if off + n < len(text) else ""
#|        return chunk + more, False
#|
#|    # -------------------------------------------------------------------------------------------- protocol
#|    def handle(self, msg):
#|        method, mid = msg.get("method"), msg.get("id")
#|        if method == "initialize":
#|            return {"jsonrpc": "2.0", "id": mid, "result": {
#|                "protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTOCOL,
#|                "capabilities": {"tools": {"listChanged": False}},
#|                "serverInfo": {"name": "nifikb", "version": __version__},
#|                "instructions": ("NiFi flow knowledge base. Start with kb_overview. For ANY support ticket call investigate first with "
#|                                 "the file / feed / table / error text / headers from the ticket: it returns ranked likely causes "
#|                                 "(provenance drop, log errors, metadata mismatches, config changes, code line, learnings) with evidence. "
#|                                 "Use diagnose / provenance / logs / search / show / trace only when that report is not conclusive. "
#|                                 "After solving a ticket, add_learning when the cause or fix is reusable and not derivable from the KB. "
#|                                 "Flow, code and databases are read-only; never claim a fix was applied - propose it.")}}
#|        if method == "tools/list":
#|            return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
#|        if method == "tools/call":
#|            p = msg.get("params") or {}
#|            try:
#|                text, is_error = self.call(p.get("name"), p.get("arguments") or {})
#|            except Exception as e:  # report tool failures to the agent instead of dying
#|                text, is_error = f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}", True
#|            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text or "(no output)"}], "isError": is_error}}
#|        if method == "ping":
#|            return {"jsonrpc": "2.0", "id": mid, "result": {}}
#|        if mid is None:  # notifications (initialized, cancelled, ...)
#|            return None
#|        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
#|
#|
#|def serve(config_path=None, stdin=None, stdout=None):
#|    stdin = stdin or sys.stdin
#|    stdout = stdout or sys.stdout
#|    server = Server(config_path)
#|    for line in stdin:
#|        line = line.strip()
#|        if not line:
#|            continue
#|        try:
#|            msg = json.loads(line)
#|        except ValueError:
#|            stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
#|            stdout.flush()
#|            continue
#|        reply = server.handle(msg)
#|        if reply is not None:
#|            stdout.write(json.dumps(reply, default=str) + "\n")
#|            stdout.flush()
#@@ FILE nifikb/metadata.py t 17701ff578ce81a7
#|"""Metadata-driven ingestion: the company config tables that drive the flow (e.g. OBJ_DEFINITION = one row per
#|file/object, OBJ_STRUCTURE = one row per column, SOURCE_FEED_CONFIG, NIFI_JSON_API_CONFIG, ...).
#|
#|- discover(): finds the config tables, how they relate (declared FKs, shared id columns, config overrides) and which
#|  table plays the "definition" / "structure" role. Everything is auto-detected and can be overridden in [metadata].
#|- fetch_rows(): read-only, masked snapshot of the config tables (stored in kb.sqlite for offline lookups).
#|- lint(): OBJ_STRUCTURE-style definitions vs. the real target tables (missing columns, types, lengths, NOT NULL).
#|- dossier(): everything the metadata says about one file / table / feed / API, plus header checks.
#|"""
#|import difflib
#|import json
#|import re
#|from collections import defaultdict
#|from pathlib import PurePath
#|
#|from . import db as dbmod
#|
#|IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
#|
#|FIELD_COL = re.compile(r"(?i)^(src_|source_|tgt_|target_|stg_)?(col|column|field|attr|attribute|element)_?(name|nm)?$")
#|TYPE_COL = re.compile(r"(?i)^((col|column|field|attr|src|tgt|target)_?)?(data_?type|d_?type|type)(_?(name|nm|cd|code))?$")
#|ORDER_COL = re.compile(r"(?i)(^|_)(seq|sequence|seq_?no|seq_?num|order|ordinal|position|pos|col_?no|col_?num|field_?no|col_?order|col_?seq|col_?pos|field_?seq)(_?no|_?num)?$")
#|PATH_COL = re.compile(r"(?i)(^|_)(json_?path|src_?path|source_?path|x_?path|field_?path|path|jsonpath|json_?key)$")
#|LENGTH_COL = re.compile(r"(?i)(^|_)(length|len|size|width|max_?len|col_?len|col_?length|field_?length)$")
#|NULL_COL = re.compile(r"(?i)(^|_)(is_?)?(nullable|null|optional|nullability)(_?(flag|ind|yn|fl|allowed))?$")
#|REQUIRED_COL = re.compile(r"(?i)(^|_)(is_?)?(mandatory|required|not_?null|mand|req)(_?(flag|ind|yn|fl))?$")
#|KEY_COL = re.compile(r"(?i)(file|table|tbl|obj|object|feed|entity|source|src|target|tgt|dataset|interface|api|endpoint|job|flow|process)"
#|                     r"_?(name|nm|pattern|mask|prefix|code|cd|key)?$")
#|LOCATION_COL = re.compile(r"(?i)^(hdfs|s3|tgt|target|dest|destination|output|landing|parquet|load)_?"
#|                          r"(path|dir|directory|location|bucket|prefix|folder|uri|key)$")
#|FILE_TARGET = re.compile(r"(?i)^[a-z][a-z0-9+.-]*://|[\\/]")  # s3://, hdfs://, /data/..., C:\... = a location, not a table
#|TARGET_COL = re.compile(r"(?i)^(tgt|target|dest|destination|stg|stage|staging|load|landing|db)?_?(table|tbl)_?(name|nm)?$")
#|FILE_COL = re.compile(r"(?i)file")
#|GENERIC_ID = {"id", "seq", "name", "type", "status", "code", "value", "created_by", "updated_by", "created_dt", "updated_dt"}
#|DATE_RUN = re.compile(r"(?<![A-Za-z])(?:YYYY|YY|MM|DD|HH24|HH|MI|SS)+(?![A-Za-z])")
#|
#|ROLE_KEYS = ("definition_table", "definition_id", "definition_target", "structure_table", "structure_parent",
#|             "structure_field", "structure_type", "structure_order", "structure_length", "structure_nullable", "structure_path",
#|             "definition_location")
#|
#|
#|# ------------------------------------------------------------------------------------------------ config
#|def settings(cfg):
#|    """Normalised [metadata] section, or None when metadata support is not configured."""
#|    m = cfg.get("metadata")
#|    if not m:
#|        return None
#|    dbs = cfg.get("databases", [])
#|    if not dbs:
#|        raise ValueError("[metadata] needs a [[databases]] entry for the database that holds the config tables")
#|    out = dict(m)
#|    out.setdefault("db", dbs[0]["name"])
#|    out.setdefault("target_db", out["db"])
#|    if str(out["target_db"]).lower() in ("", "none", "off", "false"):
#|        out["target_db"] = None  # loads go to files (HDFS / S3 / Parquet): no target-table checks
#|    out.setdefault("tables", ["OBJ_%", "%_CONFIG", "%_CONFIG_%", "%_DEFINITION", "%_STRUCTURE", "%_METADATA%"])
#|    out.setdefault("snapshot_max_rows", 20000)
#|    out.setdefault("structure_max_rows", 2000000)
#|    out.setdefault("relations", [])
#|    for name in [n for n in (out["db"], out["target_db"]) if n]:
#|        if not any(d["name"] == name for d in dbs):
#|            raise ValueError(f"[metadata] refers to database '{name}' but no [[databases]] entry has that name")
#|    for k in ROLE_KEYS:
#|        v = out.get(k)
#|        if v and not IDENT.match(v):
#|            raise ValueError(f"[metadata] {k} = {v!r} is not a plain table/column name")
#|    for k in out.get("definition_keys") or []:
#|        if not IDENT.match(k):
#|            raise ValueError(f"[metadata] definition_keys entry {k!r} is not a plain column name")
#|    for r in out["relations"]:
#|        for side in ("child", "parent"):
#|            parts = str(r.get(side, "")).split(".")
#|            if len(parts) != 2 or not all(IDENT.match(p) for p in parts):
#|                raise ValueError(f"[metadata] relation {side} must look like TABLE.COLUMN, got {r.get(side)!r}")
#|    return out
#|
#|
#|def db_config(cfg, name):
#|    return next(d for d in cfg["databases"] if d["name"] == name)
#|
#|
#|# ------------------------------------------------------------------------------------------------ helpers
#|def truthy(v):
#|    return str(v).strip().upper() in ("Y", "YES", "TRUE", "T", "1")
#|
#|
#|def norm(v):
#|    return "" if v is None else str(v).strip().lower()
#|
#|
#|def type_family(t):
#|    t = str(t or "").lower()
#|    if not t:
#|        return None
#|    if re.search(r"bool|^bit\b", t):
#|        return "bool"
#|    if re.search(r"date|time", t):
#|        return "temporal"
#|    if re.search(r"int|dec|num|float|double|real|money|serial|long|short|byte", t):
#|        return "numeric"
#|    if re.search(r"char|text|string|clob|json|xml|uuid|enum|str", t):
#|        return "string"
#|    return None
#|
#|
#|def str_length(t):
#|    m = re.search(r"(?i)char\s*\(\s*(\d+)", str(t or ""))
#|    return int(m.group(1)) if m else None
#|
#|
#|def as_int(v):
#|    try:
#|        return int(float(str(v).strip()))
#|    except (TypeError, ValueError):
#|        return None
#|
#|
#|def pattern_regex(value):
#|    """A stored file name / pattern ('SALES_*.csv', 'SALES_%', 'SALES_YYYYMMDD.csv', 'SALES_\\d{8}.csv', '${x}.csv')."""
#|    v = str(value or "").strip()
#|    if not v:
#|        return None
#|    if re.search(r"\\[dwsDWS]|\.\*|\.\+|\[[^\]]+\]|\{\d", v):
#|        try:
#|            return re.compile(v + r"\Z", re.I)
#|        except re.error:
#|            pass
#|    out, pos = [], 0
#|    for m in re.finditer(r"\$\{[^}]*\}|#\{[^}]*\}|\*|\?|%|" + DATE_RUN.pattern, v):
#|        out.append(re.escape(v[pos:m.start()]))
#|        tok = m.group(0)
#|        if tok in ("*", "%") or tok.startswith(("${", "#{")):
#|            out.append(".*")
#|        elif tok == "?":
#|            out.append(".")
#|        else:
#|            out.append(r"\d{%d}" % len(tok.replace("HH24", "HH")))
#|        pos = m.end()
#|    out.append(re.escape(v[pos:]))
#|    if len(out) == 1:
#|        return None
#|    return re.compile("".join(out) + r"\Z", re.I)
#|
#|
#|def mask_row(row):
#|    out = {}
#|    for k, v in row.items():
#|        if isinstance(v, (bytes, bytearray)):
#|            v = f"<{len(v)} bytes>"
#|        elif v is not None and not isinstance(v, (str, int, float, bool)):
#|            v = str(v)
#|        out[k] = dbmod.mask_value(k, v)
#|    return out
#|
#|
#|# ------------------------------------------------------------------------------------------------ discovery
#|def _pick(cols, rx, prefer=None, exclude=()):
#|    hits = [c for c in cols if rx.search(c) and c not in exclude]
#|    if prefer:
#|        hits.sort(key=lambda c: (not re.search(prefer, c, re.I), len(c)))
#|    return hits[0] if hits else None
#|
#|
#|def _pk(t):
#|    pk = [c["name"] for c in t["columns"] if c.get("key") == "PRI"]
#|    if not pk:
#|        idx = next((i for i in t.get("indexes", []) if i["name"].upper() == "PRIMARY" or i["name"].lower().endswith("_pkey")), None)
#|        pk = idx["columns"] if idx else []
#|    return pk
#|
#|
#|def table_patterns(m):
#|    """LIKE/glob patterns + explicit names that select the config tables (lower case, glob syntax)."""
#|    pats = [p.lower().replace("%", "*") for p in m["tables"]]
#|    pats += [m[k].lower() for k in ("definition_table", "structure_table") if m.get(k)]
#|    pats += [r[s].split(".")[0].lower() for r in m["relations"] for s in ("child", "parent")]
#|    return pats
#|
#|
#|def discover(m, db_result):
#|    """Config tables, relations and roles from the documented schema of the metadata database."""
#|    import fnmatch
#|    patterns = table_patterns(m)
#|    tables = {}
#|    for t in db_result.get("tables", []):
#|        name = t["table"].lower()
#|        if any(fnmatch.fnmatch(name, p) for p in patterns):
#|            tables[name] = t
#|    names = {n: t["table"] for n, t in tables.items()}
#|
#|    relations, seen = [], set()
#|
#|    def add(child, ccol, parent, pcol, source):
#|        key = (child.lower(), ccol.lower(), parent.lower(), pcol.lower())
#|        if key in seen or child.lower() == parent.lower():
#|            return
#|        seen.add(key)
#|        relations.append({"child": names.get(child.lower(), child), "child_column": ccol,
#|                          "parent": names.get(parent.lower(), parent), "parent_column": pcol, "source": source})
#|
#|    for r in m["relations"]:
#|        (c, cc), (p, pc) = r["child"].split("."), r["parent"].split(".")
#|        add(c, cc, p, pc, "config")
#|    for n, t in tables.items():
#|        for fk in t.get("foreign_keys", []):
#|            ref_t, _, ref_c = str(fk["ref"]).rpartition(".")
#|            if ref_t.lower() in tables:
#|                add(t["table"], fk["column"], ref_t, ref_c, "foreign key")
#|    pk_owner = defaultdict(list)
#|    for n, t in tables.items():
#|        pk = _pk(t)
#|        if len(pk) == 1 and pk[0].lower() not in GENERIC_ID and len(pk[0]) > 2:
#|            pk_owner[pk[0].lower()].append(t["table"])
#|    for n, t in tables.items():
#|        for c in t["columns"]:
#|            owners = [o for o in pk_owner.get(c["name"].lower(), []) if o.lower() != n]
#|            if len(owners) == 1 and c["name"] not in _pk(t):
#|                add(t["table"], c["name"], owners[0], c["name"], "shared column name")
#|
#|    model = {"db": m["db"], "target_db": m["target_db"], "tables": {t["table"]: {
#|        "columns": [c["name"] for c in t["columns"]], "pk": _pk(t), "rows": t.get("rows"), "comment": t.get("comment") or "",
#|        "schema": t.get("schema")} for t in tables.values()}, "relations": relations}
#|    model.update(_roles(m, tables, relations))
#|    return model
#|
#|
#|def _roles(m, tables, relations):
#|    """Which table is the definition (one row per file/object) and which the structure (one row per column)."""
#|    by_lower = {n: t for n, t in tables.items()}
#|    roles, guessed = {}, []
#|
#|    def cols(table):
#|        t = by_lower.get(str(table).lower())
#|        return [c["name"] for c in t["columns"]] if t else []
#|
#|    st = m.get("structure_table")
#|    if not st:
#|        best = None
#|        for n, t in tables.items():
#|            cs = [c["name"] for c in t["columns"]]
#|            score = bool(_pick(cs, FIELD_COL)) * 3 + bool(_pick(cs, ORDER_COL)) + bool(_pick(cs, TYPE_COL))
#|            has_parent = any(r["child"].lower() == n for r in relations)
#|            if _pick(cs, FIELD_COL) and score >= 4 and has_parent and (best is None or score > best[0]):
#|                best = (score, t["table"])
#|        st = best[1] if best else None
#|        if st:
#|            guessed.append("structure_table")
#|    if st and str(st).lower() in by_lower:
#|        st = by_lower[str(st).lower()]["table"]
#|        scols = cols(st)
#|        parent_rel = next((r for r in relations if r["child"].lower() == st.lower()
#|                           and (not m.get("definition_table") or r["parent"].lower() == m["definition_table"].lower())
#|                           and (not m.get("structure_parent") or r["child_column"].lower() == m["structure_parent"].lower())), None)
#|        roles["structure_table"] = st
#|        for key, rx, prefer in (("structure_field", FIELD_COL, r"col|field"), ("structure_type", TYPE_COL, r"data"),
#|                                ("structure_order", ORDER_COL, r"seq|order|pos"), ("structure_length", LENGTH_COL, r"len"),
#|                                ("structure_path", PATH_COL, r"json"),
#|                                ("structure_nullable", None, None)):
#|            if m.get(key):
#|                roles[key] = m[key]
#|                continue
#|            if key == "structure_nullable":
#|                val = _pick(scols, NULL_COL) or _pick(scols, REQUIRED_COL)
#|            else:
#|                val = _pick(scols, rx, prefer, exclude=[roles.get("structure_field")] if key != "structure_field" else ())
#|            if val:
#|                roles[key] = val
#|                guessed.append(key)
#|        if roles.get("structure_nullable"):
#|            roles["nullable_means_required"] = bool(REQUIRED_COL.search(roles["structure_nullable"]))
#|        roles["structure_parent"] = m.get("structure_parent") or (parent_rel["child_column"] if parent_rel else None)
#|        dt = m.get("definition_table") or (parent_rel["parent"] if parent_rel else None)
#|        if dt and not m.get("definition_table"):
#|            guessed.append("definition_table")
#|        if dt and str(dt).lower() in by_lower:
#|            dt = by_lower[str(dt).lower()]["table"]
#|            roles["definition_table"] = dt
#|            dcols = cols(dt)
#|            roles["definition_id"] = m.get("definition_id") or (parent_rel["parent_column"] if parent_rel and parent_rel["parent"] == dt
#|                                                                else (_pk(by_lower[dt.lower()]) or [None])[0])
#|            roles["definition_keys"] = m.get("definition_keys") or [c for c in dcols if KEY_COL.search(c) and c != roles["definition_id"]][:6]
#|            roles["definition_target"] = m.get("definition_target") or _pick(dcols, TARGET_COL, r"tgt|target|dest|stg")
#|            roles["definition_location"] = m.get("definition_location") or _pick(dcols, LOCATION_COL, r"hdfs|s3|tgt|target")
#|            for k in ("definition_id", "definition_keys", "definition_target", "definition_location"):
#|                if not m.get(k) and roles.get(k):
#|                    guessed.append(k)
#|    roles["guessed"] = guessed
#|    return roles
#|
#|
#|# ------------------------------------------------------------------------------------------------ rows
#|def _fq(dialect, schema, table):
#|    q = '"' if dialect != "mysql" else "`"
#|    return f"{q}{table}{q}" if dialect == "sqlite" or not schema else f"{q}{schema}{q}.{q}{table}{q}"
#|
#|
#|def fetch_rows(dcfg, m, model, log=print):
#|    """Masked rows of every config table (structure table capped separately). Returns {table: [row dict]}."""
#|    conn, dialect = dbmod.connect(dcfg)
#|    out = {}
#|    try:
#|        for table, info in model["tables"].items():
#|            limit = int(m["structure_max_rows"] if table == model.get("structure_table") else m["snapshot_max_rows"])
#|            if limit <= 0:
#|                continue
#|            order = ""
#|            if table == model.get("structure_table") and model.get("structure_parent"):
#|                q = '"' if dialect != "mysql" else "`"
#|                order = f" ORDER BY {q}{model['structure_parent']}{q}" + (f", {q}{model['structure_order']}{q}" if model.get("structure_order") else "")
#|            rows = dbmod._rows(conn, f"SELECT * FROM {_fq(dialect, info.get('schema'), table)}{order} LIMIT {limit + 1}")
#|            if len(rows) > limit:
#|                log(f"  ⚠ metadata: {table} has more than {limit} rows, snapshot truncated (raise snapshot_max_rows / structure_max_rows)")
#|                rows = rows[:limit]
#|            out[table] = [mask_row(r) for r in rows]
#|        log(f"  metadata: {len(out)} config tables, {sum(len(v) for v in out.values())} rows snapshotted")
#|        return out
#|    finally:
#|        conn.close()
#|
#|
#|def fetch_live(dcfg, m, model):
#|    """Fresh masked rows of every config table except the (large) structure table."""
#|    conn, dialect = dbmod.connect(dcfg)
#|    try:
#|        return {t: [mask_row(r) for r in dbmod._rows(conn, f"SELECT * FROM {_fq(dialect, i.get('schema'), t)} LIMIT {int(m['snapshot_max_rows'])}")]
#|                for t, i in model["tables"].items() if t != model.get("structure_table")}
#|    finally:
#|        conn.close()
#|
#|
#|def fetch_structure(dcfg, model, ids):
#|    """Fresh structure rows for a few definition ids."""
#|    st, parent = model.get("structure_table"), model.get("structure_parent")
#|    ids = [i for i in ids if i is not None]
#|    if not st or not parent or not ids:
#|        return []
#|    conn, dialect = dbmod.connect(dcfg)
#|    try:
#|        q = '"' if dialect != "mysql" else "`"
#|        ph = ",".join([dbmod._ph(dialect)] * len(ids))
#|        return [mask_row(r) for r in dbmod._rows(conn, f"SELECT * FROM {_fq(dialect, model['tables'][st].get('schema'), st)} "
#|                                                       f"WHERE {q}{parent}{q} IN ({ph})", tuple(ids))]
#|    finally:
#|        conn.close()
#|
#|
#|class Rows:
#|    """Row access over a {table: rows} snapshot with lazy per-column indexes."""
#|
#|    def __init__(self, rows_by_table):
#|        self.data = rows_by_table
#|        self._idx = {}
#|
#|    def table(self, name):
#|        return self.data.get(name, [])
#|
#|    def where(self, table, column, value):
#|        key = (table, column)
#|        if key not in self._idx:
#|            idx = defaultdict(list)
#|            for r in self.data.get(table, []):
#|                idx[norm(r.get(column))].append(r)
#|            self._idx[key] = idx
#|        return self._idx[key].get(norm(value), [])
#|
#|
#|# ------------------------------------------------------------------------------------------------ objects + checks
#|def definition_label(model, row):
#|    for k in model.get("definition_keys") or []:
#|        if row.get(k):
#|            return str(row[k])
#|    return str(row.get(model.get("definition_id")))
#|
#|
#|def structure_of(model, rows, def_row):
#|    """Ordered field list of one definition row."""
#|    st, parent = model.get("structure_table"), model.get("structure_parent")
#|    if not st or not parent:
#|        return []
#|    fields = []
#|    pk = (model["tables"].get(st) or {}).get("pk") or []
#|    for r in rows.where(st, parent, def_row.get(model["definition_id"])):
#|        name = r.get(model.get("structure_field"))
#|        if name is None:
#|            continue
#|        nullable = None
#|        if model.get("structure_nullable") and r.get(model["structure_nullable"]) is not None:
#|            flag = truthy(r[model["structure_nullable"]])
#|            nullable = not flag if model.get("nullable_means_required") else flag
#|        fields.append({"name": str(name), "type": r.get(model.get("structure_type")) if model.get("structure_type") else None,
#|                       "seq": as_int(r.get(model["structure_order"])) if model.get("structure_order") else None,
#|                       "length": as_int(r.get(model["structure_length"])) if model.get("structure_length") else None,
#|                       "nullable": nullable,
#|                       "path": r.get(model["structure_path"]) if model.get("structure_path") else None,
#|                       "key": {c: r.get(c) for c in pk} if pk else {model["structure_parent"]: r.get(model["structure_parent"]),
#|                                                                    model["structure_field"]: name}})
#|    fields.sort(key=lambda f: (f["seq"] is None, f["seq"] if f["seq"] is not None else 0))
#|    return fields
#|
#|
#|def json_path(name):
#|    """'$.data[*].customer.name', '/data/customer/name', 'data.customer.name' -> 'data.customer.name'."""
#|    s = re.sub(r"\[[^\]]*\]", "", str(name).strip())
#|    s = re.sub(r"^\$\.?", "", s).replace("/", ".")
#|    return re.sub(r"\.{2,}", ".", s).strip(".")
#|
#|
#|def is_path_structure(fields):
#|    return any(re.search(r"[.$/\[]", f["name"]) for f in fields)
#|
#|
#|def check_headers(fields, headers, ordered=True, paths=False, root=None):
#|    """Incoming headers / JSON keys vs. the structure rows of one definition. With paths=True (a JSON sample checked
#|    against structure rows holding JSON paths) both sides are compared as dotted paths below the record root and the
#|    order is not checked."""
#|    if paths:
#|        prefix = json_path(root) + "." if root and json_path(root) else ""
#|        fields = [dict(f, name=json_path(f["name"])[len(prefix):] if prefix and json_path(f["name"]).startswith(prefix)
#|                       else json_path(f["name"])) for f in fields]
#|        headers = [json_path(h) for h in headers]
#|        ordered = False
#|    return _check_headers(fields, headers, ordered)
#|
#|
#|def _check_headers(fields, headers, ordered):
#|    issues = []
#|    expected = {f["name"].lower(): f for f in fields}
#|    seen, dups = set(), []
#|    for h in headers:
#|        if h.lower() in seen:
#|            dups.append(h)
#|        seen.add(h.lower())
#|    if dups:
#|        issues.append({"severity": "error", "kind": "duplicate-header", "message": f"duplicate header(s): {', '.join(dups)}"})
#|    squash = {re.sub(r"[^a-z0-9]", "", k): f["name"] for k, f in expected.items()}
#|    for h in headers:
#|        if h.lower() in expected:
#|            continue
#|        near = squash.get(re.sub(r"[^a-z0-9]", "", h.lower()))
#|        if near:
#|            issues.append({"severity": "error", "kind": "header-name", "message": f"header '{h}' differs from '{near}' only by case/underscores/spaces",
#|                           "data": {"field": near, "header": h}})
#|            continue
#|        guess = difflib.get_close_matches(h.lower(), list(expected), n=1, cutoff=0.6)
#|        issues.append({"severity": "error", "kind": "unknown-header",
#|                       "message": f"header '{h}' is not in the structure" + (f" (did you mean '{expected[guess[0]]['name']}'?)" if guess else "")})
#|    given = {h.lower() for h in headers}
#|    squashed_given = {re.sub(r"[^a-z0-9]", "", h.lower()) for h in headers}
#|    missing = [f for f in fields if f["name"].lower() not in given and re.sub(r"[^a-z0-9]", "", f["name"].lower()) not in squashed_given]
#|    for f in missing:
#|        sev = "warn" if f["nullable"] else "error"
#|        issues.append({"severity": sev, "kind": "missing-field",
#|                       "message": f"structure field '{f['name']}'" + (f" (seq {f['seq']})" if f["seq"] is not None else "")
#|                                  + " is not in the headers" + (" (nullable)" if f["nullable"] else ""),
#|                       "data": {"field": f["name"]}})
#|    exp_order = [f["name"].lower() for f in fields if f["name"].lower() in given]
#|    got_order = [h.lower() for h in headers if h.lower() in expected]
#|    if ordered and exp_order and got_order != exp_order and len(set(got_order)) == len(got_order):
#|        first = next(i for i, (g, e) in enumerate(zip(got_order, exp_order)) if g != e)
#|        window = slice(first, first + 4)
#|        issues.append({"severity": "warn", "kind": "field-order",
#|                       "message": "header order differs from the structure sequence: headers "
#|                                  + ", ".join(expected[g]["name"] for g in got_order[window]) + " … vs structure "
#|                                  + ", ".join(expected[e]["name"] for e in exp_order[window]) + " … (breaks positional / headerless loads)"})
#|    return issues
#|
#|
#|def check_target(fields, table_info, target, known_tables=None):
#|    """Structure rows of one definition vs. the real target table."""
#|    if not target:
#|        return []
#|    if table_info is None:
#|        if known_tables is not None and target.lower().split(".")[-1] not in known_tables:
#|            near = difflib.get_close_matches(target.lower().split(".")[-1], sorted(known_tables), n=1, cutoff=0.9)  # typos only
#|            return [{"severity": "error", "kind": "target-missing",
#|                     "message": f"target table '{target}' does not exist in the target database" + (f" (did you mean '{near[0]}'?)" if near else ""),
#|                     "data": {"target": target, "suggestion": near[0] if near else None}}]
#|        return [{"severity": "info", "kind": "target-undocumented", "message": f"target table '{target}' is not documented (no schema to compare)"}]
#|    issues = []
#|    cols = {c["name"].lower(): c for c in table_info["columns"]}
#|    names = {f["name"].lower() for f in fields}
#|    extra = [f["name"] for f in fields if f["name"].lower() not in cols]
#|    if extra:
#|        guess = {e: difflib.get_close_matches(e.lower(), list(cols), n=1, cutoff=0.75) for e in extra[:15]}
#|        issues.append({"severity": "error", "kind": "column-missing",
#|                       "message": f"structure field(s) with no column in {table_info['table']}: "
#|                                  + ", ".join(e + (f" (table has '{cols[g[0]]['name']}')" if g else "") for e, g in guess.items())
#|                                  + (f", … +{len(extra) - 15} more" if len(extra) > 15 else ""),
#|                       "data": {"pairs": [(e, cols[g[0]]["name"] if g else None) for e, g in guess.items()]}})
#|    required = [c["name"] for n, c in cols.items() if n not in names and not c["nullable"] and c.get("default") is None
#|                and "auto_increment" not in str(c.get("extra") or "").lower() and not str(c.get("default") or "").startswith("nextval")]
#|    if required:
#|        issues.append({"severity": "error", "kind": "required-column",
#|                       "message": f"NOT NULL column(s) of {table_info['table']} not in the structure: {', '.join(required[:15])}"
#|                                  + (f", … +{len(required) - 15} more" if len(required) > 15 else ""),
#|                       "data": {"columns": [(n, cols[n.lower()]["type"]) for n in required[:15]]}})
#|    per_kind = defaultdict(list)  # one issue per kind, with the field details, keeps wide tables readable
#|    per_data = defaultdict(list)
#|    for f in fields:
#|        c = cols.get(f["name"].lower())
#|        if not c:
#|            continue
#|        ff, cf = type_family(f["type"]), type_family(c["type"])
#|        if ff and cf and ff != cf:
#|            sev = "warn" if "string" in (ff, cf) else "error"
#|            per_kind[("type-mismatch", sev)].append(f"'{f['name']}' is {f['type']} in the structure but {c['type']} in {table_info['table']}")
#|            per_data[("type-mismatch", sev)].append((f["name"], c["type"]))
#|        tl = str_length(c["type"])
#|        if f.get("length") and tl and f["length"] > tl:
#|            per_kind[("length", "warn")].append(f"'{f['name']}' length {f['length']} in the structure > {c['type']} in {table_info['table']}")
#|            per_data[("length", "warn")].append((f["name"], tl))
#|        if f.get("nullable") and not c["nullable"] and c.get("default") is None:
#|            per_kind[("nullability", "warn")].append(f"'{f['name']}' is nullable in the structure but NOT NULL in {table_info['table']}")
#|            per_data[("nullability", "warn")].append((f["name"], None))
#|    labels = {"type-mismatch": "type differs", "length": "longer than the target column (truncation / load error)",
#|              "nullability": "nullable vs NOT NULL"}
#|    for (kind, sev), details in sorted(per_kind.items(), key=lambda kv: kv[0][1] != "error"):
#|        shown = "; ".join(details[:6]) + (f"; … +{len(details) - 6} more" if len(details) > 6 else "")
#|        prefix = f"{labels[kind]} for {len(details)} fields: " if len(details) > 1 else ""
#|        issues.append({"severity": sev, "kind": kind, "message": prefix + shown + ("" if prefix or kind != "length" else " (truncation / load error)"),
#|                       "data": {"items": per_data[(kind, sev)], "table": table_info["table"]}})
#|    seqs = [f["seq"] for f in fields if f["seq"] is not None]
#|    if len(seqs) != len(set(seqs)):
#|        dup = sorted({s for s in seqs if seqs.count(s) > 1})
#|        issues.append({"severity": "error", "kind": "duplicate-seq", "message": f"duplicate sequence number(s) in the structure: {dup}"})
#|    lower = [f["name"].lower() for f in fields]
#|    if len(lower) != len(set(lower)):
#|        issues.append({"severity": "error", "kind": "duplicate-field",
#|                       "message": f"duplicate field name(s) in the structure: {sorted({n for n in lower if lower.count(n) > 1})}"})
#|    return issues
#|
#|
#|def table_target(model, target):
#|    """Is this definition's target a database table we can check (not a file location, and a target database is set)?"""
#|    return bool(model.get("target_db")) and not FILE_TARGET.search(str(target))
#|
#|
#|def target_index(db_results, target_db):
#|    """{lower table name: table info} + set of all table names, for the target database."""
#|    d = next((x for x in db_results if x["name"] == target_db), None)
#|    if not d:
#|        return {}, None
#|    idx = {}
#|    for t in d.get("tables", []):
#|        idx[t["table"].lower()] = t
#|        idx[f"{t['schema']}.{t['table']}".lower()] = t
#|    known = {n.lower() for n in d.get("all_table_names", [])} or None
#|    return idx, known
#|
#|
#|def lint(model, rows, db_results):
#|    """One finding per definition row whose structure disagrees with its target table (or is empty)."""
#|    findings, checked = [], 0
#|    dt = model.get("definition_table")
#|    if not dt or not model.get("structure_table"):
#|        return findings, checked
#|    idx, known = target_index(db_results, model["target_db"])
#|    for d in rows.table(dt):
#|        checked += 1
#|        fields = structure_of(model, rows, d)
#|        label = definition_label(model, d)
#|        target = d.get(model.get("definition_target")) if model.get("definition_target") else None
#|        issues = []
#|        if not fields:
#|            issues.append({"severity": "warn", "kind": "no-structure", "message": f"no {model['structure_table']} rows"})
#|        elif target and table_target(model, target):
#|            issues += [i for i in check_target(fields, idx.get(str(target).lower()), str(target), known) if i["severity"] != "info"]
#|        if issues:
#|            sev = "error" if any(i["severity"] == "error" for i in issues) else "warn"
#|            findings.append({"severity": sev, "kind": "metadata-drift", "component_id": None,
#|                             "location": f"{dt}:{d.get(model['definition_id'])}",
#|                             "message": f"{label}" + (f" → {target}" if target else "") + ": " + "; ".join(i["message"] for i in issues)})
#|    return findings, checked
#|
#|
#|# ------------------------------------------------------------------------------------------------ lookup
#|def match_rows(model, rows, key):
#|    """Rows of any config table whose identifying columns equal / pattern-match `key` (a file name, table, feed, API...)."""
#|    base = PurePath(key.replace("\\", "/")).name if ("/" in key or "\\" in key) else key
#|    want = {norm(key), norm(base)}
#|    exact, pattern, candidates = [], [], set()
#|    struct = model.get("structure_table")
#|    for table, info in model["tables"].items():
#|        if table == struct:
#|            continue
#|        cols = [c for c in info["columns"] if KEY_COL.search(c) or TARGET_COL.search(c) or c in (model.get("definition_keys") or [])
#|                or c in info["pk"] or re.search(r"(?i)name|url|host|path|dir|pattern", c)]
#|        for r in rows.table(table):
#|            for c in cols:
#|                v = r.get(c)
#|                if v is None or v == "***" or isinstance(v, (int, float)) and c not in info["pk"]:
#|                    continue
#|                nv = norm(v)
#|                if not nv:
#|                    continue
#|                if nv in want:
#|                    exact.append({"table": table, "column": c, "row": r, "match": "exact"})
#|                    break
#|                if isinstance(v, str) and len(v) <= 300:
#|                    candidates.add(str(v))
#|                    if FILE_COL.search(c) or c in (model.get("definition_keys") or []):
#|                        rx = pattern_regex(v)
#|                        if rx and (rx.match(base) or rx.match(key)):
#|                            pattern.append({"table": table, "column": c, "row": r, "match": f"pattern '{v}'"})
#|                            break
#|    hits = exact or pattern
#|    return hits, ([] if hits else suggest(base, candidates))
#|
#|
#|def _shape(s):
#|    """'SALES_20260926.csv' and 'SALES_YYYYMMDD.csv' / 'SALES_*.csv' both become 'sales_#.csv' for fuzzy comparison."""
#|    s = DATE_RUN.sub("#", str(s))
#|    s = re.sub(r"\$\{[^}]*\}|#\{[^}]*\}|[*%?]+|\d+", "#", s)
#|    return re.sub("#+", "#", s).lower()
#|
#|
#|def suggest(key, candidates, n=6):
#|    shaped = defaultdict(list)
#|    for c in candidates:
#|        shaped[_shape(c)].append(c)
#|    out = []
#|    for s in difflib.get_close_matches(_shape(key), list(shaped), n=n, cutoff=0.6):
#|        out += shaped[s]
#|    for c in difflib.get_close_matches(key, sorted(candidates), n=n, cutoff=0.6):
#|        if c not in out:
#|            out.append(c)
#|    return out[:n]
#|
#|
#|def related(model, rows, table, row, depth=2, cap=50, _seen=None):
#|    """Rows linked to one row through the discovered relations (parents and children), breadth-first."""
#|    seen = _seen if _seen is not None else set()
#|    out = defaultdict(list)
#|    frontier = [(table, row)]
#|    seen.add((table, json.dumps(row, sort_keys=True, default=str)))
#|    for _ in range(depth):
#|        nxt = []
#|        for t, r in frontier:
#|            for rel in model["relations"]:
#|                if rel["child"] == t and rel["parent"] != model.get("structure_table"):
#|                    targets = rows.where(rel["parent"], rel["parent_column"], r.get(rel["child_column"]))
#|                    tt = rel["parent"]
#|                elif rel["parent"] == t and rel["child"] != model.get("structure_table"):
#|                    targets = rows.where(rel["child"], rel["child_column"], r.get(rel["parent_column"]))
#|                    tt = rel["child"]
#|                else:
#|                    continue
#|                if r.get(rel["child_column"] if rel["child"] == t else rel["parent_column"]) is None:
#|                    continue
#|                for x in targets[:cap]:
#|                    k = (tt, json.dumps(x, sort_keys=True, default=str))
#|                    if k in seen:
#|                        continue
#|                    seen.add(k)
#|                    out[tt].append(x)
#|                    nxt.append((tt, x))
#|        frontier = nxt
#|    return dict(out)
#|
#|
#|ROOT_COL = re.compile(r"(?i)root|json_?path|record_?path|data_?path")
#|
#|
#|def json_record(data, root=None):
#|    """The first record of a JSON payload, below root ('$.data', 'data.items', '$.response.rows[*]')."""
#|    node = data
#|    for part in [p for p in re.split(r"\.|/|\[[^\]]*\]", re.sub(r"^\$", "", root or "")) if p]:
#|        if isinstance(node, list):
#|            node = next((x for x in node if isinstance(x, dict)), {})
#|        node = node.get(part, {}) if isinstance(node, dict) else {}
#|    if isinstance(node, list):
#|        node = next((x for x in node if isinstance(x, dict)), {})
#|    return node if isinstance(node, dict) else {}
#|
#|
#|def flatten_keys(record, prefix=""):
#|    """{'a': {'b': 1}, 'c': [{'d': 2}]} -> ['a.b', 'c.d'] (arrays of objects: their first element)."""
#|    out = []
#|    for k, v in record.items():
#|        p = f"{prefix}.{k}" if prefix else str(k)
#|        if isinstance(v, dict) and v:
#|            out += flatten_keys(v, p)
#|        elif isinstance(v, list) and v and isinstance(v[0], dict):
#|            out += flatten_keys(v[0], p)
#|        else:
#|            out.append(p)
#|    return out
#|
#|
#|def root_path_for(model, def_row, related_rows):
#|    """The JSON root path configured for a definition: a root / json_path column on it or on a row linked to it."""
#|    links = _link_columns(model)
#|    ident = str(def_row.get(model.get("definition_id")))
#|    candidates = [def_row] + [r for t, rs in related_rows.items() for r in rs if links.get(t) and str(r.get(links[t])) == ident]
#|    for r in candidates:
#|        for c, v in r.items():
#|            if ROOT_COL.search(c) and isinstance(v, str) and v.strip() and v != "***":
#|                return v.strip()
#|    return None
#|
#|
#|def _sample_check(model, fields, def_row, related_rows, headers, sample):
#|    """Header issues for one definition, given explicit headers and / or a parsed sample ({kind, data}). The sample's own
#|    header / keys win over typed headers (a ticket often gives both, for the same file)."""
#|    from . import content
#|    if not sample:
#|        return check_headers(fields, list(headers)) if headers else [], None
#|    if sample["kind"] != "json":
#|        if not sample.get("path") or not fields:
#|            return check_headers(fields, list(sample["data"] or headers)), {"kind": sample["kind"], "fields": len(sample["data"])}
#|        data_issues, info = content.validate_csv(fields, sample["path"], model, def_row, related_rows)
#|        header = info.get("header_row")
#|        issues = check_headers(fields, list(header)) if header else (check_headers(fields, list(headers)) if headers else [])
#|        info.update(kind="csv", fields=len(header) if header else len(fields))
#|        return issues + data_issues, info
#|    root = root_path_for(model, def_row, related_rows)
#|    record = json_record(sample["data"], root)
#|    all_fields = fields
#|    if any(f.get("path") for f in fields):  # structure rows carry a JSON path per column: compare the payload to those
#|        fields = [dict(f, name=f["path"]) for f in fields if f.get("path")]
#|    paths = is_path_structure(fields)
#|    keys = flatten_keys(record) if paths else list(record)
#|    info = {"kind": "json", "root": root, "fields": len(keys), "paths": paths}
#|    if not record:
#|        return [{"severity": "error", "kind": "json-root", "message": f"no JSON record found in the sample below root path "
#|                                                                        f"'{root or '(top level)'}' - wrong root path or payload shape"}], info
#|    issues = check_headers(fields, list(keys or headers), ordered=False, paths=paths, root=root)
#|    data_issues, dinfo = content.validate_json(all_fields, content.json_records(sample["data"], root), root)
#|    info.update(dinfo)
#|    return issues + data_issues, info
#|
#|
#|def dossier(model, rows, key, headers=(), db_results=None, sample=None):
#|    """Everything the metadata knows about one file / table / feed / API, with checks."""
#|    hits, suggestions = match_rows(model, rows, key)
#|    result = {"key": key, "matches": [], "definitions": [], "related": {}, "suggestions": suggestions}
#|    seen, dt = set(), model.get("definition_table")
#|    idx, known = target_index(db_results or [], model.get("target_db"))
#|    def_rows = []
#|    for h in hits[:20]:
#|        result["matches"].append({"table": h["table"], "column": h["column"], "match": h["match"], "row": h["row"]})
#|        if h["table"] == dt:
#|            def_rows.append(h["row"])
#|        for t, rs in related(model, rows, h["table"], h["row"], _seen=seen).items():
#|            result["related"].setdefault(t, []).extend(rs)
#|            if t == dt:
#|                def_rows.extend(rs)
#|    uniq = {}
#|    for d in def_rows:
#|        uniq.setdefault(norm(d.get(model.get("definition_id"))), d)
#|    for d in list(uniq.values())[:10]:
#|        fields = structure_of(model, rows, d)
#|        target = d.get(model.get("definition_target")) if model.get("definition_target") else None
#|        location = d.get(model.get("definition_location")) if model.get("definition_location") else None
#|        if target and not table_target(model, target):
#|            location, target = location or target, None  # e.g. an HDFS / S3 path in the target column
#|        entry = {"id": d.get(model.get("definition_id")), "label": definition_label(model, d), "row": d, "target": target,
#|                 "location": location, "fields": fields, "issues": []}
#|        linked = {t: list(rs) for t, rs in result["related"].items()}
#|        for mt in result["matches"]:  # rows matched directly (e.g. the API row itself) belong to the definition too
#|            linked.setdefault(mt["table"], []).append(mt["row"])
#|        issues, entry["sample"] = _sample_check(model, fields, d, linked, headers, sample)
#|        entry["issues"] += issues
#|        if target:
#|            entry["issues"] += check_target(fields, idx.get(str(target).lower()), str(target), known)
#|        if not fields and model.get("structure_table"):
#|            entry["issues"].append({"severity": "error", "kind": "no-structure", "message": f"no {model['structure_table']} rows for this definition"})
#|        from . import fixes
#|        entry["fixes"] = fixes.suggest(model, entry)
#|        result["definitions"].append(entry)
#|    if dt in result["related"]:
#|        del result["related"][dt]
#|    return result
#|
#|
#|# ------------------------------------------------------------------------------------------------ change tracking
#|def _link_columns(model):
#|    """table -> column holding the definition id the row belongs to."""
#|    dt, st = model.get("definition_table"), model.get("structure_table")
#|    links = {}
#|    if dt and model.get("definition_id"):
#|        links[dt] = model["definition_id"]
#|    if st and model.get("structure_parent"):
#|        links[st] = model["structure_parent"]
#|    for rel in model.get("relations") or []:
#|        if rel["parent"] == dt and rel["child"] not in links:
#|            links[rel["child"]] = rel["child_column"]
#|    return links
#|
#|
#|def _short(v):
#|    s = "∅" if v is None else str(v)
#|    return s if len(s) <= 60 else s[:59] + "…"
#|
#|
#|def diff_rows(model, old, new, tables=None):
#|    """Row-level changes between two masked snapshots of the config tables: [{tbl, pk, link, change}].
#|    Rows are matched by primary key (tables without one only report added / removed rows). Masked values stay '***',
#|    so a changed secret is never revealed (and not reported)."""
#|    links = _link_columns(model)
#|    st, field = model.get("structure_table"), model.get("structure_field")
#|    out = []
#|    for t, info in model["tables"].items():
#|        if tables and t not in tables:
#|            continue
#|        if t not in old or t not in new:
#|            continue  # table newly tracked or not snapshotted: nothing to compare
#|        pk, link_col = info.get("pk") or [], links.get(t)
#|
#|        def key(r):
#|            return "|".join(str(r.get(c)) for c in pk) if pk else json.dumps(r, sort_keys=True, default=str)
#|
#|        def label(r):
#|            bits = [f"{link_col}={r.get(link_col)}"] if link_col and t != model.get("definition_table") else []
#|            if t == st and field and r.get(field) is not None:
#|                bits.append(str(r[field]))
#|            elif t == model.get("definition_table"):
#|                bits.append(definition_label(model, r))
#|            return f"{t}:{key(r) if pk else '?'}" + (f" ({', '.join(bits)})" if bits else "")
#|
#|        o, n = {key(r): r for r in old[t]}, {key(r): r for r in new[t]}
#|        for k in sorted(set(n) - set(o)):
#|            r = n[k]
#|            out.append({"tbl": t, "pk": k if pk else None, "link": str(r.get(link_col)) if link_col else None,
#|                        "change": f"{label(r)} added: " + ", ".join(f"{c}={_short(v)}" for c, v in list(r.items())[:8] if v is not None)})
#|        for k in sorted(set(o) - set(n)):
#|            r = o[k]
#|            out.append({"tbl": t, "pk": k if pk else None, "link": str(r.get(link_col)) if link_col else None,
#|                        "change": f"{label(r)} removed"})
#|        if pk:
#|            for k in sorted(set(o) & set(n)):
#|                a, b = o[k], n[k]
#|                diffs = [f"{c} {_short(a.get(c))} → {_short(b.get(c))}" for c in sorted(set(a) | set(b))
#|                         if a.get(c) != b.get(c) and a.get(c) != "***" and b.get(c) != "***"]
#|                if diffs:
#|                    out.append({"tbl": t, "pk": k, "link": str(b.get(link_col)) if link_col else None,
#|                                "change": f"{label(b)}: " + "; ".join(diffs)})
#|    return out
#|
#|
#|# ------------------------------------------------------------------------------------------------ render
#|def render(model, rows, drift, checked, code_map=None):
#|    L = ["# Metadata (config tables)", "",
#|         f"Config tables in database `{model['db']}` that drive the flow. Rows are snapshotted (secrets masked) into `kb.sqlite`.",
#|         "Look up one file / table / feed / API: `python -m nifikb diagnose --file <name> [headers...]` (add `--live` for fresh rows).", ""]
#|    if model.get("guessed"):
#|        L.append(f"Auto-detected (check, and override in `[metadata]` of nifikb.toml if wrong): {', '.join(model['guessed'])}")
#|        L.append("")
#|    L.append("## Roles")
#|    if model.get("definition_table"):
#|        L.append(f"- definition table: `{model['definition_table']}` · id `{model.get('definition_id')}` · lookup keys "
#|                 f"{', '.join(f'`{k}`' for k in model.get('definition_keys') or []) or '(none)'} · target table column `{model.get('definition_target') or '(none)'}`"
#|                 + (f" · location column `{model['definition_location']}`" if model.get("definition_location") else "")
#|                 + ("" if model.get("target_db") else " · target checks off (loads go to files: target_db = none)"))
#|    else:
#|        L.append("- definition table: **not detected** (set `definition_table` in `[metadata]`)")
#|    if model.get("structure_table"):
#|        L.append(f"- structure table: `{model['structure_table']}` · parent `{model.get('structure_parent')}` · field `{model.get('structure_field')}` · "
#|                 f"type `{model.get('structure_type') or '-'}` · order `{model.get('structure_order') or '-'}` · length `{model.get('structure_length') or '-'}` · "
#|                 f"nullable `{model.get('structure_nullable') or '-'}`" + (" (flag means required)" if model.get("nullable_means_required") else "")
#|                 + (f" · JSON path `{model['structure_path']}`" if model.get("structure_path") else ""))
#|    else:
#|        L.append("- structure table: **not detected** (set `structure_table` / `structure_field` / `structure_parent` in `[metadata]`)")
#|    L += ["", "## Config tables", "| Table | Rows | Primary key | Columns |", "|---|---|---|---|"]
#|    for t, info in sorted(model["tables"].items()):
#|        n, in_db = len(rows.table(t)), info.get("rows")
#|        cols = ", ".join(info["columns"])
#|        count = f"{n}" if in_db is None or in_db == n else f"{n} (~{in_db} in db)"
#|        L.append(f"| {t} | {count} | {', '.join(info['pk']) or '-'} | {cols if len(cols) < 400 else cols[:399] + '…'} |")
#|    L += ["", "## Relations", ""]
#|    for r in model["relations"] or []:
#|        L.append(f"- `{r['child']}.{r['child_column']}` → `{r['parent']}.{r['parent_column']}` ({r['source']})")
#|    if not model["relations"]:
#|        L.append("- none found (declare them with `[[metadata.relations]]`)")
#|    L += ["", "## Custom code that reads these tables", ""]
#|    for fqcn, tables in sorted((code_map or {}).items()):
#|        L.append(f"- `{fqcn}` ([doc](custom-code/{fqcn.rsplit('.', 1)[-1]}.md)): {', '.join(tables)}")
#|    if not code_map:
#|        L.append("- none found in the configured code repos (add the custom processor repos to `[code] repos`)")
#|    L += ["", f"## Definitions vs. target tables ({checked} checked, {len(drift)} with problems)", ""]
#|    errors = [f for f in drift if f["severity"] == "error"]
#|    for f in (errors + [f for f in drift if f["severity"] != "error"])[:150]:
#|        L.append(f"- **{f['severity']}** `{f['location']}` {f['message']}")
#|    if len(drift) > 150:
#|        L.append(f"- … {len(drift) - 150} more: `python -m nifikb issues --kind metadata-drift`")
#|    if not drift and checked:
#|        L.append("- all definitions match their target tables")
#|    dt = model.get("definition_table")
#|    if dt and rows.table(dt) and len(rows.table(dt)) <= 500:
#|        L += ["", "## All definitions", "| Id | Keys | Target | Fields |", "|---|---|---|---|"]
#|        for d in rows.table(dt):
#|            keys = " · ".join(f"{k}={d.get(k)}" for k in model.get("definition_keys") or [] if d.get(k) is not None)
#|            L.append(f"| {d.get(model.get('definition_id'))} | {keys} | {d.get(model.get('definition_target')) if model.get('definition_target') else ''} | "
#|                     f"{len(structure_of(model, rows, d))} |")
#|    return "\n".join(L) + "\n"
#@@ FILE nifikb/nifiapi.py tc c3de415740069901
#|"""Read-only NiFi REST API client: provenance (where did a FlowFile go / get dropped), bulletins, about.
#|
#|Provenance answers the question the logs often cannot: a FlowFile routed to an auto-terminated relationship, expired in a
#|queue, or emptied by a user leaves no log line, but it does leave a DROP event naming the processor and the reason
#|("Auto-Terminated by failure Relationship", "FlowFile Expired", ...). The API is the only practical way to query it
#|(the provenance repository files are a Lucene index that must not be read while NiFi runs).
#|
#|Calls made: POST /access/token (login), POST + GET + DELETE /provenance (a temporary query, deleted after reading),
#|GET /provenance-events/{id}, GET /flow/bulletin-board, GET /flow/about. Nothing in the flow is changed.
#|The NiFi user needs the "query provenance" and "view provenance" policies (read-only otherwise).
#|"""
#|import json
#|import os
#|import ssl
#|import time
#|import urllib.error
#|import urllib.parse
#|import urllib.request
#|from pathlib import Path
#|
#|from .db import mask_value
#|
#|INTERESTING_ATTR = ("error", "reason", "fail", "exception", "status", "code", "message", "retry", "table", "schema", "path",
#|                    "filename", "directory", "bucket", "key", "fragment")
#|
#|
#|class NiFiApiError(Exception):
#|    pass
#|
#|
#|def settings(cfg):
#|    a = cfg.get("nifi_api") or {}
#|    if not a.get("url"):
#|        return None
#|    return a
#|
#|
#|def _secret(a, key):
#|    if a.get(f"{key}_env") and os.environ.get(a[f"{key}_env"]):
#|        return os.environ[a[f"{key}_env"]]
#|    if a.get(f"{key}_file"):
#|        return Path(a[f"{key}_file"]).read_text(encoding="utf-8").strip()
#|    return a.get(key)
#|
#|
#|class Client:
#|    def __init__(self, a):
#|        self.base = a["url"].rstrip("/")
#|        if not self.base.endswith("/nifi-api"):
#|            self.base += "/nifi-api"
#|        self.a = a
#|        self.timeout = float(a.get("timeout", 30))
#|        self.token = _secret(a, "token")
#|        self.ctx = None
#|        if self.base.startswith("https"):
#|            if a.get("verify_ssl", True) is False:
#|                self.ctx = ssl._create_unverified_context()  # explicit opt-in in nifikb.toml
#|            else:
#|                self.ctx = ssl.create_default_context(cafile=a.get("ca_cert") or None)
#|            if a.get("client_cert"):
#|                self.ctx.load_cert_chain(a["client_cert"], a.get("client_key"), _secret(a, "client_key_password"))
#|
#|    # ------------------------------------------------------------------------------------------- http
#|    def _call(self, method, path, body=None, form=None, auth=True):
#|        headers = {"Accept": "application/json"}
#|        data = None
#|        if form is not None:
#|            data = urllib.parse.urlencode(form).encode()
#|            headers["Content-Type"] = "application/x-www-form-urlencoded"
#|        elif body is not None:
#|            data = json.dumps(body).encode()
#|            headers["Content-Type"] = "application/json"
#|        if auth:
#|            if not self.token and self.a.get("username"):
#|                self.login()
#|            if self.token:
#|                headers["Authorization"] = f"Bearer {self.token}"
#|        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
#|        try:
#|            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
#|                raw = r.read().decode("utf-8", "replace")
#|        except urllib.error.HTTPError as e:
#|            detail = e.read().decode("utf-8", "replace")[:300]
#|            hint = {401: "authentication failed - check [nifi_api] username / password / token",
#|                    403: "the NiFi user lacks a policy: needs 'query provenance' (global) and 'view provenance' on the process groups",
#|                    404: "not found - check [nifi_api] url (it should end with /nifi-api)"}.get(e.code, "")
#|            raise NiFiApiError(f"HTTP {e.code} on {method} {path}: {detail} {hint}".strip()) from e
#|        except (urllib.error.URLError, OSError) as e:
#|            raise NiFiApiError(f"cannot reach {self.base}: {e}") from e
#|        if not raw:
#|            return None
#|        try:
#|            return json.loads(raw)
#|        except ValueError:
#|            return raw
#|
#|    def login(self):
#|        password = _secret(self.a, "password")
#|        if not password:
#|            raise NiFiApiError("[nifi_api] username is set but no password (password_env / password_file)")
#|        tok = self._call("POST", "/access/token", form={"username": self.a["username"], "password": password}, auth=False)
#|        self.token = tok if isinstance(tok, str) else None
#|        if not self.token:
#|            raise NiFiApiError("login returned no token")
#|
#|    # ------------------------------------------------------------------------------------------- API
#|    def about(self):
#|        return (self._call("GET", "/flow/about") or {}).get("about", {})
#|
#|    def bulletins(self, limit=100, source_id=None):
#|        q = f"?limit={int(limit)}" + (f"&sourceId={urllib.parse.quote(source_id)}" if source_id else "")
#|        board = (self._call("GET", "/flow/bulletin-board" + q) or {}).get("bulletinBoard", {})
#|        return [b.get("bulletin") or {} for b in board.get("bulletins", []) if b.get("bulletin")]
#|
#|    def search(self, terms, max_results=500, wait=60):
#|        """Run a provenance query ({'Filename': x} / {'FlowFileUUID': u} / {'ProcessorID': id}) and return its events."""
#|        body = {"provenance": {"request": {"maxResults": int(max_results), "summarize": True, "incrementalResults": False,
#|                                           "searchTerms": {k: {"value": v, "inverse": False} for k, v in terms.items()}}}}
#|        try:
#|            res = self._call("POST", "/provenance", body=body)
#|        except NiFiApiError as e:
#|            if "HTTP 400" not in str(e):
#|                raise
#|            body["provenance"]["request"]["searchTerms"] = dict(terms)  # NiFi < 1.13 takes plain strings
#|            res = self._call("POST", "/provenance", body=body)
#|        prov = (res or {}).get("provenance", {})
#|        qid = prov.get("id")
#|        deadline = time.time() + wait
#|        try:
#|            while not prov.get("finished") and time.time() < deadline:
#|                time.sleep(0.5)
#|                prov = (self._call("GET", f"/provenance/{qid}") or {}).get("provenance", {})
#|        finally:
#|            if qid:
#|                try:
#|                    self._call("DELETE", f"/provenance/{qid}")
#|                except NiFiApiError:
#|                    pass
#|        return (prov.get("results") or {}).get("provenanceEvents") or []
#|
#|    def event(self, event_id):
#|        return (self._call("GET", f"/provenance-events/{event_id}") or {}).get("provenanceEvent", {})
#|
#|    def pg_status(self, group="root"):
#|        return (self._call("GET", f"/flow/process-groups/{group}/status?recursive=true") or {}).get("processGroupStatus", {})
#|
#|    def controller_status(self):
#|        return (self._call("GET", "/flow/status") or {}).get("controllerStatus", {})
#|
#|    def system_diagnostics(self):
#|        return (self._call("GET", "/system-diagnostics") or {}).get("systemDiagnostics", {}).get("aggregateSnapshot", {})
#|
#|    def services(self, group="root"):
#|        res = self._call("GET", f"/flow/process-groups/{group}/controller-services?includeAncestorGroups=false&includeDescendantGroups=true")
#|        return [s.get("component") or {} for s in (res or {}).get("controllerServices", [])]
#|
#|    def processor(self, pid):
#|        return ((self._call("GET", f"/processors/{pid}") or {}).get("component") or {})
#|
#|    def version_state(self, group_instance_id):
#|        """VersionControlInformation of one process group: state UP_TO_DATE / LOCALLY_MODIFIED / STALE / ... + version."""
#|        return (self._call("GET", f"/versions/process-groups/{group_instance_id}") or {}).get("versionControlInformation") or {}
#|
#|    def cluster(self):
#|        try:
#|            return (self._call("GET", "/flow/cluster/summary") or {}).get("clusterSummary", {})
#|        except NiFiApiError:
#|            return {}
#|
#|
#|# ------------------------------------------------------------------------------------------- health
#|def _num(v):
#|    try:
#|        return int(str(v).split()[0].replace(",", "")) if v not in (None, "") else 0
#|    except ValueError:
#|        return 0
#|
#|
#|def _pct(v):
#|    try:
#|        return float(str(v).rstrip("%")) if v not in (None, "") else 0.0
#|    except ValueError:
#|        return 0.0
#|
#|
#|def _walk(snapshot, path=""):
#|    """Yield (group path, snapshot) for a recursive process-group status snapshot."""
#|    name = snapshot.get("name") or "root"
#|    here = f"{path}/{name}" if path else name
#|    yield here, snapshot
#|    for child in snapshot.get("processGroupStatusSnapshots") or []:
#|        yield from _walk(child.get("processGroupStatusSnapshot") or {}, here)
#|
#|
#|VERSION_PROBLEMS = {"LOCALLY_MODIFIED": ("warn", "changed in NiFi but not committed to the registry"),
#|                    "STALE": ("warn", "a newer version exists in the registry but is not deployed"),
#|                    "LOCALLY_MODIFIED_AND_STALE": ("warn", "changed in NiFi AND a newer registry version is not deployed"),
#|                    "SYNC_FAILURE": ("error", "cannot sync with the registry")}
#|
#|
#|def version_problems(client, groups):
#|    """groups: [(instance id, path)] of version-controlled process groups -> problems for the ones not UP_TO_DATE."""
#|    out = []
#|    for gid, path in groups:
#|        try:
#|            vci = client.version_state(gid)
#|        except NiFiApiError:
#|            continue
#|        state = vci.get("state")
#|        if state in VERSION_PROBLEMS:
#|            sev, what = VERSION_PROBLEMS[state]
#|            out.append({"severity": sev, "kind": "version-state", "component_id": gid,
#|                        "message": f"process group {path} (registry flow {vci.get('flowName') or vci.get('flowId')}, v{vci.get('version')}): "
#|                                   f"{what}" + (f" - {vci['stateExplanation']}" if vci.get("stateExplanation") else "")})
#|    return out
#|
#|
#|def health(client, bp_threshold=80.0, disk_threshold=85.0, versioned=()):
#|    """Live problems: back-pressure, queues stuck in front of stopped / invalid / disabled processors, invalid processors
#|    (with NiFi's validation errors), services not enabled, full repositories, high heap, disconnected nodes."""
#|    problems, stats = [], {}
#|
#|    def add(sev, kind, msg, cid=None):
#|        problems.append({"severity": sev, "kind": kind, "message": msg, "component_id": cid})
#|
#|    root = (client.pg_status() or {}).get("aggregateSnapshot") or {}
#|    procs, conns = {}, []
#|    for gpath, snap in _walk(root):
#|        for p in snap.get("processorStatusSnapshots") or []:
#|            ps = p.get("processorStatusSnapshot") or {}
#|            procs[ps.get("id")] = dict(ps, group=gpath)
#|        for c in snap.get("connectionStatusSnapshots") or []:
#|            conns.append(dict(c.get("connectionStatusSnapshot") or {}, group=gpath))
#|    stats.update(processors=len(procs), connections=len(conns),
#|                 queued=sum(_num(c.get("queuedCount")) for c in conns))
#|    for c in conns:
#|        count, pct_n, pct_b = _num(c.get("queuedCount")), _pct(c.get("percentUseCount")), _pct(c.get("percentUseBytes"))
#|        where = f"{c.get('sourceName')} → {c.get('destinationName')} in {c.get('group')}"
#|        dest = procs.get(c.get("destinationId")) or {}
#|        if max(pct_n, pct_b) >= bp_threshold:
#|            add("error" if max(pct_n, pct_b) >= 100 else "warn", "back-pressure",
#|                f"queue {where} is at {max(pct_n, pct_b):.0f}% of its back-pressure threshold ({c.get('queued') or count}) - "
#|                "upstream processors slow down / stop", c.get("destinationId"))
#|        if count and dest.get("runStatus") in ("Stopped", "Invalid", "Disabled"):
#|            add("error", "stuck-queue", f"{count} FlowFile(s) waiting in {where}: the destination processor is {dest['runStatus'].upper()}",
#|                c.get("destinationId"))
#|    for pid, p in procs.items():
#|        if p.get("runStatus") == "Invalid":
#|            errors = []
#|            try:
#|                errors = client.processor(pid).get("validationErrors") or []
#|            except NiFiApiError:
#|                pass
#|            add("error", "invalid-processor", f"{p.get('name')} ({p.get('type')}) in {p.get('group')} is INVALID"
#|                + (f": {'; '.join(errors)[:400]}" if errors else ""), pid)
#|    try:
#|        for s in client.services():
#|            if s.get("state") not in ("ENABLED", None):
#|                add("warn" if s.get("state") == "DISABLED" else "error", "service-not-enabled",
#|                    f"controller service {s.get('name')} is {s.get('state')}"
#|                    + (f": {'; '.join(s.get('validationErrors') or [])[:300]}" if s.get("validationErrors") else ""), s.get("id"))
#|    except NiFiApiError:
#|        pass
#|    diag = client.system_diagnostics() or {}
#|    heap = _pct(diag.get("heapUtilization"))
#|    if heap >= disk_threshold:
#|        add("warn", "heap", f"JVM heap at {heap:.0f}% - NiFi may pause / slow down (OutOfMemory risk)")
#|    for label, key in (("content repository", "contentRepositoryStorageUsage"), ("provenance repository", "provenanceRepositoryStorageUsage"),
#|                       ("FlowFile repository", "flowFileRepositoryStorageUsage")):
#|        usage = diag.get(key)
#|        for u in (usage if isinstance(usage, list) else [usage] if usage else []):
#|            pct = _pct(u.get("utilization"))
#|            if pct >= disk_threshold:
#|                add("error" if pct >= 95 else "warn", "disk", f"{label} {u.get('identifier') or ''} at {pct:.0f}% "
#|                    f"({u.get('usedSpace', '?')} of {u.get('totalSpace', '?')}) - NiFi stops accepting data when full".replace("  ", " "))
#|    stats.update(heap=diag.get("heapUtilization"))
#|    problems += version_problems(client, versioned)
#|    cluster = client.cluster()
#|    if cluster.get("clustered") and cluster.get("connectedNodeCount", 0) < cluster.get("totalNodeCount", 0):
#|        add("error", "cluster", f"only {cluster['connectedNodeCount']} of {cluster['totalNodeCount']} cluster nodes connected")
#|    sev_rank = {"error": 0, "warn": 1}
#|    problems.sort(key=lambda p: sev_rank.get(p["severity"], 2))
#|    return {"problems": problems, "stats": stats}
#|
#|
#|def format_health(h, names=None):
#|    names = names or {}
#|    s = h["stats"]
#|    L = [f"Live NiFi health: {s.get('processors', 0)} processors, {s.get('connections', 0)} connections, "
#|         f"{s.get('queued', 0)} FlowFiles queued, heap {s.get('heap') or '?'}"]
#|    if not h["problems"]:
#|        L.append("no problems: no back-pressure, no stuck queues, no invalid processors, services enabled, repositories below threshold")
#|    for p in h["problems"]:
#|        cid = p.get("component_id") or ""
#|        L.append(f"[{p['severity']}] {p['kind']}: {p['message']}" + (f"  ({names[cid]})" if cid in names else ""))
#|    return "\n".join(L)
#|
#|
#|class RegistryClient(Client):
#|    """Read-only NiFi Registry client: version history (who changed a versioned flow when, with the commit comment)."""
#|
#|    def __init__(self, r):
#|        r = dict(r)
#|        url = r["url"].rstrip("/")
#|        r["url"] = url if url.endswith("/nifi-registry-api") else url + "/nifi-registry-api"
#|        super().__init__(r)
#|        self.base = r["url"]
#|
#|    def login(self):
#|        password = _secret(self.a, "password")
#|        if not password:
#|            raise NiFiApiError("[registry] username is set but no password (password_env / password_file)")
#|        basic = __import__("base64").b64encode(f"{self.a['username']}:{password}".encode()).decode()
#|        req = urllib.request.Request(self.base + "/access/token/login", data=b"", method="POST", headers={"Authorization": f"Basic {basic}"})
#|        try:
#|            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
#|                self.token = r.read().decode().strip()
#|        except urllib.error.HTTPError as e:
#|            raise NiFiApiError(f"registry login failed: HTTP {e.code}") from e
#|        except (urllib.error.URLError, OSError) as e:
#|            raise NiFiApiError(f"cannot reach {self.base}: {e}") from e
#|
#|    def versions(self, bucket, flow):
#|        res = self._call("GET", f"/buckets/{bucket}/flows/{flow}/versions") or []
#|        return sorted(res, key=lambda v: v.get("version") or 0, reverse=True)
#|
#|
#|def registry_settings(cfg):
#|    r = cfg.get("registry") or {}
#|    return r if r.get("url") else None
#|
#|
#|# ------------------------------------------------------------------------------------------- journey
#|def journey(client, filename=None, uuid=None, component_id=None, max_results=500, follow=20):
#|    """Every provenance event of the FlowFiles with this file name / uuid (and their children), grouped per FlowFile,
#|    with a verdict: where each one ended (dropped where and why, sent where, or still in flight)."""
#|    if filename:
#|        terms = {"Filename": filename}
#|    elif uuid:
#|        terms = {"FlowFileUUID": uuid}
#|    elif component_id:
#|        terms = {"ProcessorID": component_id}
#|    else:
#|        raise ValueError("give a file name, FlowFile uuid or processor id")
#|    events = client.search(terms, max_results)
#|    seen = {e.get("eventId") for e in events}
#|    uuids = {e.get("flowFileUuid") for e in events}
#|    for _ in range(2):  # follow FORK / CLONE / split children a little way
#|        children = [c for e in events for c in (e.get("childUuids") or []) if c not in uuids][:follow]
#|        for c in children:
#|            uuids.add(c)
#|            for e in client.search({"FlowFileUUID": c}, max_results):
#|                if e.get("eventId") not in seen:
#|                    seen.add(e.get("eventId"))
#|                    events.append(e)
#|    events.sort(key=lambda e: (int(e.get("eventId") or 0)))
#|    flows = {}
#|    for e in events:
#|        flows.setdefault(e.get("flowFileUuid"), []).append(e)
#|    out = []
#|    for ff, evs in flows.items():
#|        last = evs[-1]
#|        kind = last.get("eventType")
#|        if kind == "DROP":
#|            verdict = f"DROPPED at {last.get('componentName')} ({last.get('componentType')}): {last.get('details') or 'no reason given'}"
#|        elif kind in ("SEND", "REMOTE_INVOCATION", "UPLOAD"):
#|            verdict = f"sent by {last.get('componentName')} to {last.get('transitUri') or '?'}"
#|        elif any(c for c in (last.get("childUuids") or [])) and kind in ("FORK", "CLONE", "JOIN"):
#|            verdict = f"split / cloned by {last.get('componentName')} into {len(last['childUuids'])} FlowFile(s)"
#|        else:
#|            verdict = (f"last seen at {last.get('componentName')} ({kind}) - still queued / in flight, or older events were "
#|                       "aged out of provenance")
#|        attrs = {}
#|        if kind == "DROP" and last.get("id"):
#|            try:
#|                detail = client.event(last["id"])
#|                for a in detail.get("attributes") or []:
#|                    name = a.get("name", "")
#|                    if any(w in name.lower() for w in INTERESTING_ATTR) or a.get("value") != a.get("previousValue"):
#|                        attrs[name] = mask_value(name, a.get("value"))
#|            except NiFiApiError:
#|                pass
#|        out.append({"uuid": ff, "events": evs, "verdict": verdict, "attributes": dict(list(attrs.items())[:25])})
#|    return out
#|
#|
#|def format_journey(flows, names=None, key=""):
#|    names = names or {}
#|    if not flows:
#|        return (f"no provenance events for {key} - the file never entered NiFi under this name, or its events were aged out of "
#|                "provenance (check nifi.provenance.repository.max.storage.time)")
#|    L = []
#|    for f in flows:
#|        L.append(f"FlowFile {str(f['uuid'])[:8]}: {f['verdict']}")
#|        for e in f["events"][-40:]:
#|            cid = e.get("componentId") or ""
#|            flow = names.get(cid)
#|            extra = " ".join(x for x in [f"-> {e['relationship']}" if e.get("relationship") else "",
#|                                         e.get("details") or "", e.get("transitUri") or ""] if x)
#|            L.append(f"  {e.get('eventTime', '')[:23]}  {e.get('eventType', ''):<18} {e.get('componentName', '')} `{cid[:8]}`"
#|                     + (f" ({flow})" if flow else "") + (f"  {extra}" if extra else ""))
#|        if f["attributes"]:
#|            L.append("  attributes at the drop: " + ", ".join(f"{k}={str(v)[:80]}" for k, v in f["attributes"].items()))
#|    return "\n".join(L)
#|
#|
#|def format_bulletins(bulletins, names=None):
#|    names = names or {}
#|    if not bulletins:
#|        return "no bulletins (NiFi keeps them for 5 minutes)"
#|    L = []
#|    for b in bulletins:
#|        sid = b.get("sourceId") or ""
#|        L.append(f"[{b.get('level')}] {b.get('timestamp', '')} {b.get('sourceName', '')} `{sid[:8]}`"
#|                 + (f" ({names[sid]})" if sid in names else "") + f": {str(b.get('message', ''))[:400]}")
#|    return "\n".join(L)
#@@ FILE nifikb/onboard.py tc 6e16c8e060cf48bf
#|"""New-feed validator: check proposed config rows (definition, structure, feed / API / server rows) before anyone inserts
#|them - against the config tables' own schema, the existing rows, the target table, an example file name and a sample.
#|
#|The proposal is a TOML (or JSON) file with the rows in the config tables' own column names:
#|
#|    example_file = "INVOICE_20260927.csv"   # a real file name the definition must match
#|    sample = "INVOICE_20260927.csv"         # optional: sample file for content checks
#|    like = "SALES_YYYYMMDD.csv"             # optional: an existing, similar feed to compare with
#|    structure_csv = "invoice_columns.csv"   # optional: structure rows as CSV (header = column names), instead of [[structure]]
#|
#|    [definition]
#|    FILE_NAME = "INVOICE_YYYYMMDD.csv"
#|    TABLE_NAME = "stg_invoice"
#|
#|    [[structure]]
#|    COL_NAME = "INV_NO"
#|    DATA_TYPE = "INTEGER"
#|    COL_SEQ = 1
#|
#|    [[rows.SOURCE_FEED_CONFIG]]
#|    FEED_NAME = "erp_invoice_feed"
#|
#|Nothing is written anywhere: the result lists problems and INSERT statements for a human to review and run."""
#|import csv
#|import difflib
#|import json
#|import re
#|import tomllib
#|from pathlib import Path
#|
#|from . import db as dbmod, metadata as metamod
#|from .fixes import quote
#|
#|NEW_ID = "<new id>"
#|INT_TYPES = re.compile(r"(?i)^(tiny|small|medium|big)?int(eger)?\b|^number\(\d+\)$|^serial")
#|NUM_TYPES = re.compile(r"(?i)^(decimal|numeric|number|float|double|real)")
#|KNOWN_TYPES = re.compile(r"(?i)^(var)?char|^n?varchar|^string|^text|^clob|^(tiny|small|medium|big)?int|^integer|^long|^short|^byte|"
#|                         r"^decimal|^numeric|^number|^float|^double|^real|^bool|^bit|^date|^time|^timestamp|^datetime|^binary|"
#|                         r"^varbinary|^blob|^json|^array|^struct|^map|^uuid")
#|
#|
#|def load_proposal(path):
#|    path = Path(path)
#|    text = path.read_text(encoding="utf-8-sig")
#|    data = json.loads(text) if path.suffix.lower() == ".json" else tomllib.loads(text)
#|    base = path.parent
#|    for k in ("sample", "structure_csv"):
#|        if data.get(k) and not Path(data[k]).is_absolute():
#|            data[k] = str((base / data[k]).resolve())
#|    if data.get("structure_csv"):
#|        with open(data["structure_csv"], newline="", encoding="utf-8-sig") as f:
#|            data["structure"] = [{k: (v if v != "" else None) for k, v in r.items() if k} for r in csv.DictReader(f)]
#|    return data
#|
#|
#|def _schema(store, db, table, model):
#|    """Column details of a config table ({lower name: column}) from the documented schema, or names only."""
#|    row = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=?", (db, table.lower())).fetchone()
#|    if row:
#|        return {c["name"].lower(): c for c in json.loads(row["data"])["columns"]}
#|    return {c.lower(): {"name": c, "type": None, "nullable": True, "default": None} for c in model["tables"][table]["columns"]}
#|
#|
#|def _real_table(model, name):
#|    return next((t for t in model["tables"] if t.lower() == str(name).lower()), None)
#|
#|
#|def _check_row(table, row, schema, pk, existing, label):
#|    """Column names, required columns, value types / lengths and primary-key collisions of one proposed row.
#|    Returns (row with the table's own column spelling, issues)."""
#|    issues, fixed = [], {}
#|    for k, v in row.items():
#|        c = schema.get(k.lower())
#|        if not c:
#|            near = difflib.get_close_matches(k.lower(), list(schema), n=1, cutoff=0.7)
#|            issues.append(("error", "unknown-column", f"{label}: {table} has no column '{k}'"
#|                           + (f" (did you mean '{schema[near[0]]['name']}'?)" if near else "")))
#|            continue
#|        fixed[c["name"]] = v
#|        if v is None or v == NEW_ID or not c.get("type"):
#|            continue
#|        t = str(c["type"])
#|        if INT_TYPES.search(t) and not re.fullmatch(r"-?\d+", str(v).strip()):
#|            issues.append(("error", "value-type", f"{label}: {c['name']} = {quote(v)} is not an integer ({t})"))
#|        elif NUM_TYPES.search(t) and not re.fullmatch(r"-?\d+(\.\d+)?", str(v).strip()):
#|            issues.append(("error", "value-type", f"{label}: {c['name']} = {quote(v)} is not a number ({t})"))
#|        n = metamod.str_length(t)
#|        if n and len(str(v)) > n:
#|            issues.append(("error", "value-length", f"{label}: {c['name']} is {len(str(v))} characters, the column allows {n} ({t})"))
#|        if dbmod.sensitive_column(c["name"]) and v not in ("***", "", None):
#|            issues.append(("warn", "secret-in-proposal", f"{label}: {c['name']} holds a secret - leave it out of the proposal "
#|                                                          "and let the DBA set it"))
#|            fixed[c["name"]] = "***"
#|    have = {k.lower() for k in fixed}
#|    for n, c in schema.items():
#|        if n in have or c.get("nullable", True) or c.get("default") is not None:
#|            continue
#|        if "auto_increment" in str(c.get("extra") or "").lower() or str(c.get("default") or "").startswith("nextval"):
#|            continue
#|        if n in [p.lower() for p in pk] and len(pk) == 1 and "int" in str(c.get("type") or "").lower():
#|            issues.append(("info", "id-not-given", f"{label}: {c['name']} not given - fine if the database generates it, "
#|                                                   "otherwise pick the next free id"))
#|            continue
#|        issues.append(("error", "required-column", f"{label}: {table}.{c['name']} is NOT NULL and has no default, but is not set"))
#|    if pk and all(fixed.get(p) is not None for p in pk):
#|        key = "|".join(str(fixed[p]) for p in pk)
#|        if key in existing:
#|            issues.append(("error", "duplicate-key", f"{label}: {table}:{key} already exists"))
#|    return fixed, issues
#|
#|
#|def _structure_checks(fields, model):
#|    issues = []
#|    seqs = [f["seq"] for f in fields if f["seq"] is not None]
#|    if model.get("structure_order"):
#|        missing = [f["name"] for f in fields if f["seq"] is None]
#|        if missing:
#|            issues.append(("error", "missing-seq", f"no {model['structure_order']} for: {', '.join(missing[:10])}"))
#|        dup = sorted({s for s in seqs if seqs.count(s) > 1})
#|        if dup:
#|            issues.append(("error", "duplicate-seq", f"duplicate {model['structure_order']} value(s): {dup}"))
#|        if seqs and sorted(set(seqs)) != list(range(min(seqs), min(seqs) + len(set(seqs)))):
#|            issues.append(("warn", "seq-gap", f"{model['structure_order']} has gaps: {sorted(set(seqs))} (files are read by position)"))
#|    names = [f["name"].lower() for f in fields]
#|    dup = sorted({n for n in names if names.count(n) > 1})
#|    if dup:
#|        issues.append(("error", "duplicate-field", f"duplicate field name(s): {dup}"))
#|    for f in fields:
#|        if f["name"] != f["name"].strip():
#|            issues.append(("error", "field-whitespace", f"field '{f['name']}' has leading / trailing blanks"))
#|        if model.get("structure_type"):
#|            if not f["type"]:
#|                issues.append(("error", "missing-type", f"no {model['structure_type']} for '{f['name']}'"))
#|            elif not KNOWN_TYPES.search(str(f["type"]).strip()):
#|                issues.append(("warn", "unknown-type", f"'{f['name']}': type '{f['type']}' is not a usual type name"))
#|            elif metamod.type_family(f["type"]) == "string" and model.get("structure_length") and not f.get("length") \
#|                    and not metamod.str_length(f["type"]) and not re.search(r"(?i)text|clob|string", str(f["type"])):
#|                issues.append(("warn", "missing-length", f"'{f['name']}' is {f['type']} without a length"))
#|    return issues
#|
#|
#|def validate(cfg, store, proposal, live=False):
#|    """Check a proposal (see the module doc). Returns {issues: [(severity, kind, message)], inserts: [sql], ...}."""
#|    from .diagnose import _target_results, read_sample
#|    m = metamod.settings(cfg)
#|    model = store.get_meta("metadata_model")
#|    if not m or not model or not model.get("definition_table"):
#|        return {"error": "metadata is not configured or no definition table was detected ([metadata] in nifikb.toml, then build)"}
#|    dt, st = model["definition_table"], model.get("structure_table")
#|    did, parent = model.get("definition_id"), model.get("structure_parent")
#|    if live:
#|        dcfg = metamod.db_config(cfg, m["db"])
#|        rows_by_table = metamod.fetch_live(dcfg, m, model)
#|    else:
#|        rows_by_table = store.get_meta_rows(exclude=st)
#|    rows = metamod.Rows(rows_by_table)
#|    issues, inserts = [], []
#|
#|    def pk_set(table):
#|        pk = model["tables"][table].get("pk") or []
#|        return pk, {"|".join(str(r.get(p)) for p in pk) for r in rows.table(table)} if pk else set()
#|
#|    # ---- the definition row
#|    definition = dict(proposal.get("definition") or {})
#|    if not definition:
#|        return {"error": f"the proposal has no [definition] section (one {dt} row)"}
#|    pk, existing = pk_set(dt)
#|    drow, found = _check_row(dt, definition, _schema(store, m["db"], dt, model), pk, existing, "definition")
#|    issues += found
#|    new_id = drow.get(did) if did else None
#|    link_value = new_id if new_id is not None else NEW_ID
#|    drow_for_checks = dict(drow, **({did: link_value} if did else {}))
#|    label = metamod.definition_label(model, drow_for_checks)
#|
#|    # names: does the definition match the example file, and would any existing definition match it too?
#|    keys = [k for k in model.get("definition_keys") or [] if drow.get(k)]
#|    if not keys:
#|        issues.append(("error", "no-key", f"none of the matching columns {model.get('definition_keys')} is set - the flow cannot find this definition"))
#|    example = proposal.get("example_file") or (Path(proposal["sample"]).name if proposal.get("sample") else None)
#|    if example:
#|        rx = [(k, metamod.pattern_regex(drow[k])) for k in keys if metamod.FILE_COL.search(k) or len(keys) == 1]
#|        if rx and not any(r and (r.match(example) or metamod.norm(drow[k]) == metamod.norm(example)) for k, r in rx):
#|            issues.append(("error", "pattern-mismatch", f"{', '.join(f'{k} {quote(drow[k])}' for k, _ in rx)} does not match the example "
#|                                                        f"file '{example}' - the flow would not pick it up"))
#|        hits, _ = metamod.match_rows(model, rows, example)
#|        clash = sorted({str(h["row"].get(did)) for h in hits if h["table"] == dt and str(h["row"].get(did)) != str(new_id)})
#|        if clash:
#|            issues.append(("error", "ambiguous-match", f"'{example}' already matches existing {dt} row(s) {', '.join(f'{dt}:{c}' for c in clash)} "
#|                                                       "- two definitions for one file"))
#|    for k in keys:
#|        if k == model.get("definition_target"):
#|            continue  # many definitions may load one table
#|        same = [r for r in rows.table(dt) if metamod.norm(r.get(k)) == metamod.norm(drow[k]) and str(r.get(did)) != str(new_id)]
#|        if same:
#|            issues.append(("error", "duplicate-name", f"{k} {quote(drow[k])} is already used by {dt}:{same[0].get(did)}"))
#|    inserts.append(_insert(dt, drow))
#|
#|    # ---- structure rows
#|    fields = []
#|    if st:
#|        srows = []
#|        spk, sexisting = pk_set(st)
#|        sschema = _schema(store, m["db"], st, model)
#|        for i, r in enumerate(proposal.get("structure") or [], 1):
#|            r = dict(r)
#|            if parent and not any(k.lower() == parent.lower() for k in r):
#|                r[parent] = link_value
#|            fixed, found = _check_row(st, r, sschema, spk, sexisting, f"{st} row {i}")
#|            issues += found
#|            if parent and str(fixed.get(parent)) not in (str(link_value),):
#|                issues.append(("error", "wrong-parent", f"{st} row {i}: {parent} = {quote(fixed.get(parent))}, the definition is {quote(link_value)}"))
#|            srows.append(fixed)
#|        if not srows:
#|            issues.append(("error", "no-structure", f"no {st} rows in the proposal - the flow would have no column list"))
#|        fields = metamod.structure_of(model, metamod.Rows({st: srows}), drow_for_checks)
#|        issues += _structure_checks(fields, model)
#|        inserts += [_insert(st, r) for r in srows]
#|
#|    # ---- related rows (feed / API / server config)
#|    links = metamod._link_columns(model)
#|    linked = {}
#|    for table, rs in (proposal.get("rows") or {}).items():
#|        real = _real_table(model, table)
#|        if not real:
#|            issues.append(("error", "unknown-table", f"'{table}' is not one of the config tables ({', '.join(sorted(model['tables']))})"))
#|            continue
#|        rpk, rexisting = pk_set(real)
#|        rschema = _schema(store, m["db"], real, model)
#|        for i, r in enumerate(rs if isinstance(rs, list) else [rs], 1):
#|            r = dict(r)
#|            lc = links.get(real)
#|            if lc and not any(k.lower() == lc.lower() for k in r):
#|                r[lc] = link_value
#|            fixed, found = _check_row(real, r, rschema, rpk, rexisting, f"{real} row {i}")
#|            issues += found
#|            linked.setdefault(real, []).append(fixed)
#|            inserts.append(_insert(real, fixed))
#|
#|    # ---- compared with a similar, existing feed
#|    if proposal.get("like"):
#|        issues += _compare_like(model, rows, proposal["like"], drow, fields, linked, links, store, m)
#|
#|    # ---- target
#|    target = drow.get(model.get("definition_target")) if model.get("definition_target") else None
#|    if target and metamod.table_target(model, target) and fields:
#|        db_results = _target_results(store, model, {"definitions": [{"target": target}]})
#|        idx, known = metamod.target_index(db_results, model["target_db"])
#|        for i in metamod.check_target(fields, idx.get(str(target).lower()), str(target), known):
#|            issues.append((i["severity"], i["kind"], f"target {target}: {i['message']}"))
#|    elif target and not metamod.table_target(model, target):
#|        issues.append(("info", "file-target", f"loads to {target} (a file location - not checked against a table)"))
#|    elif model.get("definition_target") and not target:
#|        issues.append(("warn", "no-target", f"{model['definition_target']} is not set"))
#|
#|    # ---- sample content
#|    sample_info = None
#|    if proposal.get("sample") and not Path(proposal["sample"]).is_file():
#|        issues.append(("warn", "sample-missing", f"sample file {proposal['sample']} not found - content not checked"))
#|    elif proposal.get("sample") and fields:
#|        sample = read_sample(proposal["sample"])
#|        found, sample_info = metamod._sample_check(model, fields, drow_for_checks, linked, [], sample)
#|        issues += [(i["severity"], i["kind"], f"sample: {i['message']}") for i in found]
#|    rank = {"error": 0, "warn": 1, "info": 2}
#|    issues.sort(key=lambda x: rank.get(x[0], 3))
#|    return {"label": label, "definition": drow, "fields": fields, "issues": issues, "inserts": inserts, "sample": sample_info,
#|            "live": live, "id_given": new_id is not None}
#|
#|
#|def _compare_like(model, rows, like, drow, fields, linked, links, store, m):
#|    dt, did = model["definition_table"], model.get("definition_id")
#|    tmpl = metamod.dossier(model, rows, like)["definitions"]
#|    if not tmpl:
#|        return [("warn", "like-not-found", f"'{like}' matches no existing definition to compare with")]
#|    t = tmpl[0]
#|    out = []
#|    unset = [c for c, v in t["row"].items() if v not in (None, "") and c != did and drow.get(c) in (None, "")]
#|    if unset:
#|        out.append(("warn", "like-columns", f"{dt}:{t['id']} ({t['label']}) sets {', '.join(unset)} - the proposal leaves them empty"))
#|    st = model.get("structure_table")
#|    if st:
#|        struct = store.get_structure_rows(st, model["structure_parent"], [t["id"]])
#|        tfields = metamod.structure_of(model, metamod.Rows({st: struct}), t["row"])
#|        attrs = {"structure_type": "type", "structure_length": "length", "structure_nullable": "nullable", "structure_path": "path"}
#|        tset = {model[role] for role in attrs if model.get(role) and any(r.get(model[role]) not in (None, "") for r in struct)}
#|        pset = {model[role] for role, attr in attrs.items() if model.get(role) and any(f.get(attr) not in (None, "") for f in fields)}
#|        missing = sorted(tset - pset)
#|        if tfields and missing:
#|            out.append(("warn", "like-structure", f"the structure rows of {t['label']} fill {', '.join(missing)} - the proposal does not"))
#|    for table, col in links.items():
#|        if table in (dt, st):
#|            continue
#|        has = [r for r in rows.table(table) if str(r.get(col)) == str(t["id"])]
#|        if has and not linked.get(table):
#|            out.append(("warn", "like-related", f"{t['label']} has {len(has)} {table} row(s) - the proposal has none"))
#|    return out
#|
#|
#|def _insert(table, row):
#|    cols = [c for c, v in row.items() if v is not None]
#|    vals = ["/* set by DBA */ NULL" if row[c] == "***" else "/* new id */ NULL" if row[c] == NEW_ID else quote(row[c]) for c in cols]
#|    return f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(vals)});"
#|
#|
#|def format_report(res):
#|    if res.get("error"):
#|        return res["error"]
#|    errors = sum(1 for i in res["issues"] if i[0] == "error")
#|    warns = sum(1 for i in res["issues"] if i[0] == "warn")
#|    L = [f"# New feed check: {res['label']} ({len(res['fields'])} structure fields) - "
#|         + ("READY to insert" if not errors else f"{errors} error(s) to fix first") + (f", {warns} warning(s)" if warns else "")
#|         + (" [config rows read live]" if res["live"] else " [compared with the KB snapshot]")]
#|    if res["issues"]:
#|        L.append("")
#|        L += [f"- {sev.upper()} {kind}: {msg}" for sev, kind, msg in res["issues"]]
#|    if res.get("sample"):
#|        s = res["sample"]
#|        L.append("")
#|        L.append("sample: " + ", ".join(f"{k}={v}" for k, v in s.items() if k in ("kind", "fields", "rows", "delimiter", "root", "records")))
#|    L.append("")
#|    L.append("## INSERT statements (review first - nifikb never runs them)")
#|    if not res["id_given"]:
#|        L.append("-- the definition id is not given: after the first INSERT, put the generated id where it says /* new id */")
#|    L += res["inserts"]
#|    return "\n".join(L)
#@@ FILE nifikb/render.py tc 9714b3c3a73713a4
#|"""Render the analysis into small, linked markdown files an LLM can read instead of the raw flow."""
#|import json
#|import time
#|from collections import Counter, defaultdict
#|from pathlib import Path
#|
#|from . import sqlparse
#|from .analyze import type_short
#|from .code import spark_label
#|from .util import REDACTED, SECRET_NAME, URL_RE, clip, md_escape, redact_secrets, short, slugify
#|
#|SEV_ORDER = {"error": 0, "high": 1, "warn": 2, "info": 3}
#|SUCCESS_FIRST = ("success", "matched", "original", "output stream", "response", "splits", "merged", "valid")
#|
#|
#|# ------------------------------------------------------------------------------------ graph tree
#|def tree_lines(roots, get, edges, doc_of=None, group_id=None, max_depth=40, upstream=False, expanded=None):
#|    """Indented tree of the data path from each root. `get(cid)` returns a component dict with name/type/kind/state/
#|    group_id/facts/auto_terminated; `edges(cid)` returns [(relationships list, other id)]. With group_id the tree
#|    stops where the path leaves that process group."""
#|    lines = []
#|    expanded = set() if expanded is None else expanded
#|
#|    def label(c, brief=False):
#|        kind = c.get("kind")
#|        if kind == "FUNNEL":
#|            base = f"(funnel) `{short(c['id'])}`"
#|        elif kind in ("INPUT_PORT", "OUTPUT_PORT"):
#|            base = f"{'⇥ input' if kind == 'INPUT_PORT' else '⇤ output'} port **{c['name']}** `{short(c['id'])}`"
#|        elif kind and kind.startswith("REMOTE"):
#|            base = f"remote port **{c['name']}**"
#|        else:
#|            base = f"**{c['name']}** [{type_short(c.get('type'))}] `{short(c['id'])}`"
#|        state = c.get("state")
#|        if state and state not in ("RUNNING", "ENABLED") and kind == "PROCESSOR":
#|            base += f" ({state})"
#|        if not brief and c.get("facts"):
#|            base += f" — {c['facts']}"
#|        return base
#|
#|    def visit(cid, depth, via):
#|        c = get(cid)
#|        pad = "  " * depth + "- "
#|        arrow = ("▶ " if not upstream else "◀ ") if via is None else (f"*{via}* → " if not upstream else f"← *{via}* ")
#|        if c is None:
#|            lines.append(pad + arrow + f"? unknown component `{short(cid)}`")
#|            return
#|        if group_id and c["group_id"] != group_id:
#|            where = doc_of(c["group_id"]) if doc_of else None
#|            gname = c.get("group_name") or short(c["group_id"])
#|            lines.append(pad + arrow + f"{label(c, True)} in PG **{gname}**" + (f" (see [{where}]({where}))" if where else ""))
#|            return
#|        if cid in expanded:
#|            lines.append(pad + arrow + label(c, True) + " ↑ shown above")
#|            return
#|        expanded.add(cid)
#|        lines.append(pad + arrow + label(c))
#|        outs = edges(cid)
#|        if depth >= max_depth and outs:
#|            lines.append("  " * (depth + 1) + "- … depth limit")
#|            return
#|        outs = sorted(outs, key=lambda e: (not any(r in SUCCESS_FIRST for r in e[0]), ",".join(e[0])))
#|        for rels, other in outs:
#|            visit(other, depth + 1, ",".join(rels) or "·")
#|        if not upstream and c.get("auto_terminated"):
#|            lines.append("  " * (depth + 1) + f"- ✖ auto-terminated: {', '.join(c['auto_terminated'])}")
#|
#|    for r in roots:
#|        visit(r, 0, None)
#|    return lines
#|
#|
#|class Renderer:
#|    def __init__(self, an, out_dir, code, db_results, extra):
#|        self.an, self.flow, self.out, self.code, self.dbs, self.extra = an, an.flow, Path(out_dir), code, db_results, extra
#|        self.files = {}          # relative path -> content
#|        self.comp_docs = {}      # component id -> markdown section
#|        self.group_file = {}
#|        self.table_file = {}     # (db name, table) -> doc path
#|        used = set()
#|        for gid, g in sorted(self.flow.groups.items(), key=lambda kv: (kv[1]["depth"], kv[1]["path"])):
#|            base = "root" if gid == self.flow.root_id else slugify(g["path"].split(" / ", 1)[-1])
#|            name, n = base, 2
#|            while name in used:
#|                name, n = f"{base}-{n}", n + 1
#|            used.add(name)
#|            self.group_file[gid] = f"flows/{name}.md"
#|        self.custom_file = {t: f"custom-code/{type_short(t)}.md" for t in list(an.custom) + list(code.by_fqcn)}
#|        self.script_file = {}
#|        for p in an.scripts:
#|            self.script_file[p] = f"scripts/{slugify(Path(p).name, 80)}.md"
#|
#|    # helpers
#|    def comp(self, cid):
#|        c = self.flow.components.get(cid) or self.flow.services.get(cid)
#|        if not c:
#|            return None
#|        g = self.flow.groups.get(c["group_id"]) or {}
#|        return dict(c, facts=self.an.key_facts(c), group_name=g.get("name"))
#|
#|    def edges(self, cid):
#|        return [(c["relationships"], d) for c, d in self.an.out_edges[cid]]
#|
#|    def in_edges(self, cid):
#|        return [(c["relationships"], s) for c, s in self.an.in_edges[cid]]
#|
#|    def link(self, cid, frm="flows/x.md"):
#|        c = self.flow.components.get(cid) or self.flow.services.get(cid)
#|        if not c:
#|            return f"`{short(cid)}`"
#|        target = "services.md" if c["kind"] == "CONTROLLER_SERVICE" else self.group_file.get(c["group_id"], "INDEX.md")
#|        rel = _rel(frm, target)
#|        return f"[{md_escape(c['name'])}]({rel}#{_anchor(c)}) `{short(cid)}`"
#|
#|    def findings_for(self, cid):
#|        if not hasattr(self, "_findings_idx"):
#|            self._findings_idx = defaultdict(list)
#|            for f in self.an.findings:
#|                self._findings_idx[f["component_id"]].append(f)
#|        return sorted(self._findings_idx.get(cid, []), key=lambda f: SEV_ORDER.get(f["severity"], 9))
#|
#|    # ----------------------------------------------------------------------------------- per group
#|    def render_group(self, gid):
#|        an, flow = self.an, self.flow
#|        g = flow.groups[gid]
#|        me = self.group_file[gid]
#|        comps = [c for c in flow.components.values() if c["group_id"] == gid]
#|        procs = sorted((c for c in comps if c["kind"] == "PROCESSOR"), key=lambda c: c["name"].lower())
#|        states = Counter(c["state"] for c in procs)
#|        children = sorted((x for x in flow.groups.values() if x["parent_id"] == gid), key=lambda x: x["name"].lower())
#|        L = [f"# Flow: {g['name']}", ""]
#|        meta = [f"Path: {g['path']}", f"group `{short(gid)}`"]
#|        if g.get("parameter_context"):
#|            meta.append(f"parameter context: {g['parameter_context']}")
#|        if g.get("versioned"):
#|            vc = g.get("version_control") or {}
#|            meta.append(f"version-controlled: flow {vc.get('flow_name') or vc.get('flow') or '?'} v{vc.get('version') or '?'}"
#|                        + (f" (bucket {vc['bucket']})" if vc.get("bucket") else ""))
#|        L.append(" · ".join(meta))
#|        L.append(f"Processors: {len(procs)} ({', '.join(f'{v} {k.lower()}' for k, v in states.most_common())})"
#|                 f" · tags: {', '.join(an.group_tags(gid, recursive=False)) or '-'}")
#|        if g["parent_id"]:
#|            L.append(f"Parent: [{flow.groups[g['parent_id']]['name']}]({_rel(me, self.group_file[g['parent_id']])})")
#|        if children:
#|            L.append("Child groups: " + ", ".join(f"[{c['name']}]({_rel(me, self.group_file[c['id']])})" for c in children))
#|        if g.get("variables"):
#|            L.append("Variables: " + ", ".join(f"`{k}`=`{REDACTED if SECRET_NAME.search(k) else clip(v, 80)}`" for k, v in sorted(g["variables"].items())))
#|        notes = [lab["text"] for lab in flow.labels if lab["group_id"] == gid] + ([g["comments"]] if g.get("comments") else [])
#|        if notes:
#|            L += ["", "## Notes on the canvas", *[f"- {clip(n, 400)}" for n in notes]]
#|        roots = [c["id"] for c in an.entry_points(gid)]
#|        if roots or procs:
#|            L += ["", "## Data paths", "Read top-down: each `→` is a connection labelled with its relationship(s).", ""]
#|        expanded = set()
#|        doc_of = lambda x: _rel(me, self.group_file.get(x, "INDEX.md"))  # noqa: E731
#|        L += tree_lines(roots, self.comp, self.edges, doc_of=doc_of, group_id=gid, expanded=expanded)
#|        orphans = [c["id"] for c in procs if c["id"] not in expanded]
#|        if orphans:
#|            L += ["", "Only reachable through loops (no clear entry point):"]
#|            for o in orphans:
#|                if o not in expanded:
#|                    L += tree_lines([o], self.comp, self.edges, doc_of=doc_of, group_id=gid, expanded=expanded)
#|        if procs:
#|            L += ["", "## Processors"]
#|            for c in procs:
#|                L += ["", *self.processor_section(c, me)]
#|        ports = [c for c in comps if c["kind"] in ("INPUT_PORT", "OUTPUT_PORT")]
#|        if ports:
#|            L += ["", "## Ports"]
#|            for p in sorted(ports, key=lambda p: p["name"]):
#|                ins = ", ".join(self.link(s, me) for _, s in self.in_edges(p["id"])) or "-"
#|                outs = ", ".join(self.link(d, me) for _, d in self.edges(p["id"])) or "-"
#|                L.append(f"- {p['kind'].replace('_', ' ').lower()} **{p['name']}** `{short(p['id'])}`: from {ins} → to {outs}")
#|        svcs = [s for s in flow.services.values() if s["group_id"] == gid]
#|        if svcs:
#|            L += ["", "## Controller services defined here", "Details: [services.md](../services.md)"]
#|            for s in sorted(svcs, key=lambda s: s["name"]):
#|                L.append(f"- **{s['name']}** [{type_short(s['type'])}] `{short(s['id'])}` {s.get('state') or ''} — {self.service_summary(s)}")
#|        self.files[me] = "\n".join(L) + "\n"
#|
#|    def processor_section(self, c, frm):
#|        an = self.an
#|        head = f"### {c['name']}"
#|        L = [head, f"<a id=\"{_anchor(c)}\"></a>`{c['id']}` · {c['type']}"
#|             + (f" ({(c['bundle'] or {}).get('artifact')} {(c['bundle'] or {}).get('version')})" if c.get("bundle") else "")]
#|        sched = [c.get("state") or "?"]
#|        if c.get("scheduling_strategy") and c["scheduling_strategy"] != "TIMER_DRIVEN" or c.get("scheduling_period") not in (None, "0 sec"):
#|            sched.append(f"{c.get('scheduling_strategy')} {c.get('scheduling_period')}")
#|        if c.get("concurrent_tasks") and int(c["concurrent_tasks"]) > 1:
#|            sched.append(f"{c['concurrent_tasks']} concurrent tasks")
#|        if c.get("execution_node") == "PRIMARY":
#|            sched.append("primary node only")
#|        L.append("- run: " + ", ".join(sched))
#|        ext = an.ext(c)
#|        if ext and ext.get("description"):
#|            L.append(f"- does: {clip(ext['description'], 220)}")
#|        if c.get("comments"):
#|            L.append(f"- comment: {clip(c['comments'], 300)}")
#|        facts = an.props[c["id"]]
#|        shown = [f for f in facts if not f["default"]]
#|        for f in shown:
#|            val = f["resolved"] if f["source"] in ("service",) else f["value"]
#|            line = f"  - {f['display']}: " + (f"`{clip(val, 300)}`" if val.strip() else repr(val))
#|            if f["source"] in ("parameter", "expression", "variable", "parameter+expression") and f["resolved"] != f["value"]:
#|                line += f" ⇒ `{clip(f['resolved'], 200)}`"
#|            if f["source"] == "service":
#|                line = f"  - {f['display']}: → {self.link(f['service'], frm) if f['service'] in self.flow.services else val}"
#|            tags = []
#|            if f["dynamic"]:
#|                tags.append("dynamic")
#|            hard = [r for r in an.res_by_comp[c["id"]] if r["property"] == f["display"] and r["hardcoded"] and r["kind"] not in ("sql",)]
#|            if hard:
#|                tags.append("hardcoded " + "/".join(sorted({r["kind"] for r in hard})))
#|            if tags:
#|                line += f" _({', '.join(tags)})_"
#|            L.append(line)
#|        if shown:
#|            L.insert(len(L) - len(shown), "- properties" + (f" (non-default; {len(facts) - len(shown)} default hidden)" if len(shown) < len(facts) else "") + ":")
#|        ins = [f"{self.link(s, frm)} ({','.join(r)})" for r, s in self.in_edges(c["id"])]
#|        outs = [f"{','.join(r)} → {self.link(d, frm)}" for r, d in self.edges(c["id"])]
#|        if ins:
#|            L.append("- from: " + "; ".join(ins))
#|        if outs:
#|            L.append("- to: " + "; ".join(outs))
#|        if c.get("auto_terminated"):
#|            L.append("- auto-terminated: " + ", ".join(c["auto_terminated"]))
#|        if an.attrs_read[c["id"]]:
#|            L.append("- reads attributes: " + ", ".join(sorted(an.attrs_read[c["id"]])))
#|        if an.attrs_written[c["id"]]:
#|            L.append("- writes attributes: " + ", ".join(sorted(an.attrs_written[c["id"]])))
#|        if c["type"] in self.custom_file and (c["type"] in an.custom or c["type"] in self.code.by_fqcn):
#|            L.append(f"- custom code: [{type_short(c['type'])}]({_rel(frm, self.custom_file[c['type']])})")
#|        for r in an.res_by_comp[c["id"]]:
#|            if r["kind"] == "script" and r["value"].strip("\"'") in self.script_file:
#|                spath = r["value"].strip(chr(34) + chr(39))
#|                sinfo = (an.scripts.get(spath) or {}).get("index") or {}
#|                spark = "; ".join(spark_label(x) for x in sinfo.get("spark") or [])
#|                L.append(f"- script: [{Path(r['value']).name}]({_rel(frm, self.script_file[spath])})"
#|                         + (f" — submits Spark job: {spark}" if spark else ""))
#|        for f in self.findings_for(c["id"]):
#|            L.append(f"- ⚠ {f['severity']}: {f['message']}")
#|        self.comp_docs[c["id"]] = "\n".join(L)
#|        return L
#|
#|    def service_summary(self, s):
#|        bits = []
#|        if s["id"] in self.an.jdbc:
#|            j = self.an.jdbc[s["id"]]
#|            bits.append(f"{j['url']}" + (f" user={j['user']}" if j.get("user") else ""))
#|        for f in self.an.props[s["id"]]:
#|            if not f["default"] and f["source"] != "sensitive" and ("schema" in f["name"].lower() and "strategy" in f["name"].lower()):
#|                bits.append(f"{f['display']}={f['resolved']}")
#|        users = self.an.service_users.get(s["id"], [])
#|        bits.append(f"used by {len(users)}")
#|        return clip(", ".join(bits), 240)
#|
#|    # ---------------------------------------------------------------------------------- services
#|    def render_services(self):
#|        L = ["# Controller services", ""]
#|        for s in sorted(self.flow.services.values(), key=lambda s: (s["type"], s["name"])):
#|            g = self.flow.groups.get(s["group_id"]) or {"path": "(controller level)"}
#|            L += [f"## {s['name']}", f"<a id=\"{_anchor(s)}\"></a>`{s['id']}` · {s['type']} · {s.get('state')} · scope: {g['path']}"]
#|            ext = self.an.ext(s)
#|            if ext and ext.get("description"):
#|                L.append(f"- does: {clip(ext['description'], 200)}")
#|            for f in self.an.props[s["id"]]:
#|                if not f["default"]:
#|                    shown = f["resolved"] if f["source"] in ("service", "sensitive") else f["value"]
#|                    extra = f" ⇒ `{clip(f['resolved'], 150)}`" if f["source"] in ("parameter", "expression", "variable") and f["resolved"] != f["value"] else ""
#|                    L.append(f"  - {f['display']}: `{clip(shown, 400)}`{extra}")
#|            users = self.an.service_users.get(s["id"], [])
#|            if users:
#|                L.append("- used by: " + ", ".join(self.link(u, "services.md") for u in users))
#|            for f in self.findings_for(s["id"]):
#|                L.append(f"- ⚠ {f['severity']}: {f['message']}")
#|            self.comp_docs[s["id"]] = "\n".join(L[L.index(f"## {s['name']}"):])
#|            L.append("")
#|        self.files["services.md"] = "\n".join(L) + "\n"
#|
#|    # ---------------------------------------------------------------------------- external systems
#|    def render_external(self):
#|        an = self.an
#|        kinds = [("jdbc", "Database connections"), ("db_table", "Database tables"), ("sql", "SQL statements"),
#|                 ("s3_bucket", "S3 buckets"), ("object_key", "S3 object keys"), ("url", "URLs / APIs"), ("host", "Hosts"),
#|                 ("port", "Ports"), ("topic", "Topics / queues"), ("file_path", "File system paths"), ("script", "Scripts"),
#|                 ("command", "Commands"), ("email", "Email")]
#|        L = ["# External systems touched by the flow", "", "`H` = hardcoded literal in the flow (not a parameter/variable/attribute).", ""]
#|        for kind, title in kinds:
#|            rows = defaultdict(list)
#|            for r in an.resources:
#|                if r["kind"] == kind:
#|                    rows[r["value"]].append(r)
#|            if not rows:
#|                continue
#|            L += [f"## {title}"]
#|            for value, rs in sorted(rows.items()):
#|                users = []
#|                for r in rs:
#|                    ref = self.link(r["component_id"], "external-systems.md")
#|                    if ref not in users:
#|                        users.append(ref)
#|                flag = " `H`" if any(r["hardcoded"] for r in rs) else ""
#|                shown = clip(value, 220) if kind != "sql" else clip(value, 300)
#|                tables = ""
#|                if kind == "sql" and rs[0].get("detail"):
#|                    tables = f" (tables: {', '.join(json.loads(rs[0]['detail']))})"
#|                L.append(f"- `{shown}`{flag}{tables} — {', '.join(users[:8])}{' …' if len(users) > 8 else ''}")
#|            L.append("")
#|        code_tables = defaultdict(list)
#|        for path, info in self.code.files.items():
#|            for t in info.get("tables") or []:
#|                code_tables[t].append(_code_ref(path, None, self.extra))
#|        if code_tables:
#|            L.append("## Tables referenced in code / scripts")
#|            L += [f"- `{t}` — {', '.join(dict.fromkeys(refs))}" for t, refs in sorted(code_tables.items())]
#|        self.files["external-systems.md"] = "\n".join(L) + "\n"
#|
#|    # ------------------------------------------------------------------------------------- hardcoded
#|    def render_hardcoded(self, max_per_kind=150):
#|        an = self.an
#|        L = ["# Hardcoded values", "",
#|             "Literal values that probably belong in a Parameter Context / config. Secrets are always redacted.", "",
#|             "## In the NiFi flow", ""]
#|        rows = sorted((r for r in an.resources if r["hardcoded"] and r["kind"] != "command"), key=lambda r: (r["kind"], r["value"]))
#|        if not rows:
#|            L.append("None found.")
#|        by_kind = defaultdict(list)
#|        for r in rows:
#|            by_kind[r["kind"]].append(r)
#|        for kind, rs in by_kind.items():
#|            L.append(f"### {kind}")
#|            for r in rs[:max_per_kind]:
#|                partial = " (partly: mixed with EL/parameter)" if r["source"] not in ("literal", "variable") else " (via variable)" if r["source"] == "variable" else ""
#|                L.append(f"- `{clip(r['value'], 200)}`{partial} — {self.link(r['component_id'], 'hardcoded.md')} · {r['property']}")
#|            if len(rs) > max_per_kind:
#|                L.append(f"- … {len(rs) - max_per_kind} more (`python -m nifikb search {kind}`)")
#|        secrets = [f for f in an.findings if f["kind"] == "plaintext-secret"]
#|        if secrets:
#|            L += ["", "### plain-text secrets in flow properties"] + [f"- {self.link(f['component_id'], 'hardcoded.md')}: {f['message']}" for f in secrets]
#|        L += ["", "## In code and scripts", ""]
#|        by_kind = defaultdict(list)
#|        for path, h in self.code.hardcoded():
#|            if h["kind"] != "sql":
#|                by_kind[h["kind"]].append((path, h))
#|        if not by_kind:
#|            L.append("None found (or no code indexed yet).")
#|        for kind in sorted(by_kind, key=lambda k: (k != "secret", k)):
#|            L.append(f"### {kind}")
#|            for path, h in by_kind[kind][:max_per_kind]:
#|                L.append(f"- `{clip(h['value'], 160)}` — {_code_ref(path, h['line'], self.extra)}  `{h['code']}`")
#|            if len(by_kind[kind]) > max_per_kind:
#|                L.append(f"- … {len(by_kind[kind]) - max_per_kind} more")
#|        self.files["hardcoded.md"] = "\n".join(L) + "\n"
#|
#|    # ---------------------------------------------------------------------------------------- issues
#|    def render_issues(self, per_kind=150):
#|        L = ["# Issues and risks", "", "Static checks on the flow, code and database. Severity: error > high > warn > info.", ""]
#|        items = sorted(self.an.findings, key=lambda f: (SEV_ORDER.get(f["severity"], 9), f["kind"]))
#|        if not items:
#|            L.append("No issues found.")
#|        counts = Counter((f["severity"], f["kind"]) for f in items)
#|        if counts:
#|            L += ["| Severity | Kind | Count |", "|---|---|---|"]
#|            L += [f"| {s} | {k} | {n} |" for (s, k), n in sorted(counts.items(), key=lambda kv: (SEV_ORDER.get(kv[0][0], 9), -kv[1]))]
#|            L.append("")
#|            L.append(f"Up to {per_kind} entries per kind are listed; filter all of them with "
#|                     "`python -m nifikb issues --kind <kind> [--contains <text>]` (MCP tool `issues`).")
#|        current, shown = None, 0
#|        for f in items:
#|            key = (f["severity"], f["kind"])
#|            if key != current:
#|                if current and counts[current] > per_kind:
#|                    L.append(f"- … {counts[current] - per_kind} more `{current[1]}`")
#|                current, shown = key, 0
#|                L += ["", f"## {f['severity']}: {f['kind']}"]
#|            shown += 1
#|            if shown > per_kind:
#|                continue
#|            where = self.link(f["component_id"], "issues.md") if f["component_id"] else (f.get("location") or "")
#|            L.append(f"- {where}: {f['message']}")
#|        if current and counts[current] > per_kind:
#|            L.append(f"- … {counts[current] - per_kind} more `{current[1]}`")
#|        self.files["issues.md"] = "\n".join(L) + "\n"
#|
#|    # ------------------------------------------------------------------------------------ custom code
#|    def render_custom(self):
#|        an, code = self.an, self.code
#|        idx = ["# Custom components", "", "| Type | Used by | Source | NAR |", "|---|---|---|---|"]
#|        types = sorted(set(an.custom) | set(code.by_fqcn))
#|        for t in types:
#|            entry = an.custom.get(t, {"used_by": [], "code": code.by_fqcn.get(t, []), "nar": None, "bundle": {}})
#|            f = self.custom_file[t]
#|            src = ", ".join(_code_ref(e["path"], e["line"], self.extra) for e in entry["code"]) or "**missing**"
#|            idx.append(f"| [{type_short(t)}]({f.split('/', 1)[1]}) | {len(entry['used_by'])} | {src} | {entry.get('nar') or (entry.get('bundle') or {}).get('artifact') or '-'} |")
#|            self.files[f] = self.custom_doc(t, entry, f)
#|        if not types:
#|            idx.append("| (none) | | | |")
#|        self.files["custom-code/INDEX.md"] = "\n".join(idx) + "\n"
#|
#|    def custom_doc(self, t, entry, me):
#|        an = self.an
#|        L = [f"# {type_short(t)}", f"`{t}`", ""]
#|        ext = self.an.catalog.get(t)
#|        comp = entry["code"][0]["component"] if entry["code"] else None
#|        desc = (comp or {}).get("description") or (ext or {}).get("description")
#|        if desc:
#|            L.append(f"**Does:** {clip(desc, 600)}")
#|        if comp:
#|            L.append(f"Source: {', '.join(_code_ref(e['path'], e['line'], self.extra) for e in entry['code'])} · extends "
#|                     + (" → ".join(x.rsplit(".", 1)[-1] for x in comp.get("super_chain") or []) or comp.get("extends") or "-")
#|                     + (f" · input: {comp['input_requirement']}" if comp.get("input_requirement") else ""))
#|            if comp.get("tags"):
#|                L.append("Tags: " + ", ".join(comp["tags"]))
#|            if comp.get("flags"):
#|                L.append("Annotations: " + ", ".join(f"@{f}" for f in comp["flags"]))
#|            if comp.get("io"):
#|                L.append("Talks to / uses: " + ", ".join(comp["io"]))
#|            L += self._build_lines(comp, entry)
#|        elif ext:
#|            L.append(f"Source code not provided; details from NAR `{ext.get('nar')}` manifest.")
#|        else:
#|            L.append("**Source code and NAR not found.** Add the repo to `[code] repos` / the NAR to `[nifi] extra_nar_dirs` and rebuild.")
#|        if ext and ext.get("deployed"):
#|            L += self._deployed_lines(ext["deployed"], comp)
#|        props = (comp or {}).get("properties") or [
#|            {"name": k, "displayName": v["displayName"], "description": v["description"], "default": v["default"],
#|             "required": v["required"], "sensitive": v["sensitive"], "service": v.get("service_api")}
#|            for k, v in ((ext or {}).get("properties") or {}).items()]
#|        if props:
#|            L += ["", "## Properties", "| Name | Display | Default | Req | Notes |", "|---|---|---|---|---|"]
#|            for p in props:
#|                impl = self.code.implementers(p["service"]) if p.get("service") else []
#|                notes = " ".join(x for x in ["sensitive" if p.get("sensitive") else "", "EL" if p.get("el") else "",
#|                                             f"service {p['service']}" if p.get("service") else "",
#|                                             f"(implemented by {', '.join(i.rsplit('.', 1)[-1] for i in impl[:3])})" if impl else "",
#|                                             f"one of {', '.join(p['allowable'][:8])}" if p.get("allowable") else "",
#|                                             f"(from {p['from']})" if p.get("from") else "", clip(p.get("description"), 120)] if x)
#|                L.append(f"| {md_escape(p.get('name'))} | {md_escape(p.get('displayName') or p.get('name'))} | {md_escape(p.get('default'))} | {'Y' if p.get('required') else ''} | {md_escape(notes)} |")
#|        for d in (comp or {}).get("dynamic_properties") or []:
#|            L.append(f"- dynamic property {d.get('name') or ''}: {clip(d.get('description'), 160)}")
#|        rels = (comp or {}).get("relationships") or (ext or {}).get("relationships") or []
#|        if rels:
#|            L += ["", "## Relationships"] + [f"- `{r['name']}`: {clip(r.get('description'), 160)}" + (f" (from {r['from']})" if r.get("from") else "")
#|                                             for r in rels]
#|        if comp:
#|            L += ["", "## Attributes"]
#|            reads, writes = comp.get("reads_at") or {}, comp.get("writes_at") or {}
#|            if comp.get("reads_attributes"):
#|                L.append("- reads: " + ", ".join(f"`{a}`" + (f" ({reads[a]})" if a in reads else "") for a in comp["reads_attributes"]))
#|            if comp.get("writes_attributes"):
#|                L.append("- writes: " + ", ".join(f"`{a}`" + (f" ({writes[a]})" if a in writes else " (documented)") for a in comp["writes_attributes"]))
#|            if comp.get("removes_attributes"):
#|                L.append("- removes: " + ", ".join(f"`{a}`" for a in comp["removes_attributes"]))
#|            if comp.get("dynamic_writes"):
#|                L.append("- also writes attributes whose names are computed at runtime (e.g. from database columns)")
#|            if not (comp.get("reads_attributes") or comp.get("writes_attributes")):
#|                L.append("- none found in the code")
#|        for e in entry["code"]:
#|            info = self.code.files.get(e["path"]) or {}
#|            if info.get("hardcoded"):
#|                L += ["", f"## Hardcoded in {Path(e['path']).name}"]
#|                L += [f"- L{h['line']} {h['kind']}: `{clip(h['value'], 160)}`" + (f" tables={','.join(h['tables'])}" if h.get("tables") else "") for h in info["hardcoded"]]
#|            if info.get("messages"):
#|                L += ["", f"## Log / error messages in {Path(e['path']).name} (search a ticket's error text against these)"]
#|                L += [f"- L{m['line']} {m['level']}: {clip(m['text'], 200)}" for m in info["messages"][:60]]
#|            if info.get("functions"):
#|                L.append(f"\nMethods: {', '.join(info['functions'][:40])}")
#|        if entry["used_by"]:
#|            L += ["", "## Used in the flow"]
#|            for cid in entry["used_by"]:
#|                c = self.flow.components.get(cid) or self.flow.services.get(cid)
#|                g = self.flow.groups.get(c["group_id"], {})
#|                configured = ", ".join(f"{f['display']}=`{clip(f['resolved'], 80)}`" for f in an.props[cid] if not f["default"])
#|                L.append(f"- {self.link(cid, me)} in {g.get('path', '?')} ({c.get('state')}): {configured or 'no properties set'}")
#|        return "\n".join(L) + "\n"
#|
#|    def _build_lines(self, comp, entry):
#|        """Maven module -> NAR module -> deployed NAR -> bundle version the flow runs."""
#|        L = []
#|        mod = comp.get("module")
#|        if mod:
#|            L.append(f"Maven module: `{mod.get('groupId')}:{mod.get('artifactId')}:{mod.get('version')}` "
#|                     f"({_code_ref(str(Path(mod['dir']) / 'pom.xml'), None, self.extra)})")
#|        nars = comp.get("nar_modules") or []
#|        if nars:
#|            L.append("Packaged by NAR module: " + ", ".join(f"`{n.get('artifactId')}:{n.get('version')}`" for n in nars))
#|        bundle = entry.get("bundle") or {}
#|        if bundle:
#|            versions = ", ".join(v for v in entry.get("bundle_versions") or [bundle.get("version")] if v)
#|            deployed = [n for n in self.an.catalog.nars if n.get("artifact") == bundle.get("artifact")]
#|            dep = ", ".join(f"{n.get('version')} ({Path(n['file']).name})" for n in deployed) if deployed else "**none in lib / extra_nar_dirs**"
#|            L.append(f"Flow runs bundle `{bundle.get('group')}:{bundle.get('artifact')}:{versions}` · deployed NAR: {dep}")
#|            src_version = next((n.get("version") for n in nars if n.get("artifactId") == bundle.get("artifact")), None)
#|            if src_version and bundle.get("version") and src_version != bundle.get("version"):
#|                L.append(f"⚠ Source version {src_version} ≠ running version {bundle['version']}: the repo may hold changes that are not deployed.")
#|        if not comp.get("registered"):
#|            L.append("Not listed in a META-INF/services file.")
#|        return L
#|
#|    def _deployed_lines(self, deployed, comp):
#|        """Facts read from the compiled classes inside the deployed NAR (ground truth of what runs)."""
#|        strings = self.an.catalog.jar_strings(deployed)
#|        if not strings:
#|            return []
#|        L = ["", f"## Deployed NAR (compiled classes in `{deployed['jar']}`)"]
#|        drift = (self.an.custom.get(comp["fqcn"]) or {}).get("drift") if comp else None
#|        if drift:
#|            L.append("⚠ In the repo source but **not in the deployed build**: " + ", ".join(drift[:20]))
#|        elif comp:
#|            L.append("Source matches the deployed build (all property, relationship and attribute names found).")
#|        sql = sorted({s for s in strings if sqlparse.looks_like_sql(s)})
#|        tables = sorted({t for s in sql for t in sqlparse.tables(s) if "{" not in t})
#|        if tables:
#|            L.append("Tables in its SQL: " + ", ".join(f"`{t}`" for t in tables[:40]))
#|        for s in sql[:15]:
#|            L.append(f"- SQL: `{clip(redact_secrets(s), 200)}`")
#|        urls = sorted({m.group(0) for s in strings for m in URL_RE.finditer(s)})
#|        if urls:
#|            L.append("URLs: " + ", ".join(f"`{u}`" for u in urls[:20]))
#|        return L
#|
#|    # ---------------------------------------------------------------------------------------- scripts
#|    def render_scripts(self):
#|        idx = ["# Scripts called by the flow", ""]
#|        for path, entry in sorted(self.an.scripts.items()):
#|            f = self.script_file[path]
#|            info = entry.get("index")
#|            if entry["exists"]:
#|                status = "indexed"
#|            elif entry.get("repo_match"):
#|                status = f"not at this path here; indexed from repo match `{_code_ref(entry['repo_match'], None, self.extra).strip('`')}`"
#|            else:
#|                status = "file not found on this machine or in repos"
#|            idx.append(f"- [{Path(path).name}]({f.split('/', 1)[1]}) — {status} — used by {', '.join(self.link(u, 'scripts/INDEX.md') for u in entry['used_by'])}")
#|            L = [f"# Script {Path(path).name}", f"Path: `{path}` ({status})", ""]
#|            L.append("Called by: " + ", ".join(self.link(u, f) for u in entry["used_by"]))
#|            for u in entry["used_by"]:
#|                c = self.flow.components[u]
#|                cmd = [x for x in self.an.props[u] if "command" in x["kinds"]]
#|                if cmd:
#|                    L.append(f"- {c['name']}: " + " ".join(f"`{clip(x['resolved'], 200)}`" for x in cmd))
#|            if info:
#|                L += ["", f"Language: {info['lang']}, {info['lines']} lines"]
#|                if info.get("imports"):
#|                    L.append("Imports: " + ", ".join(info["imports"]))
#|                if info.get("functions"):
#|                    L.append("Functions: " + ", ".join(info["functions"]))
#|                if info.get("tables"):
#|                    L.append("Tables: " + ", ".join(info["tables"]))
#|                if info.get("spark"):
#|                    L += ["", "## Spark jobs submitted (Spark itself is not analysed)"]
#|                    L += [f"- L{x['line']}: {spark_label(x)}" + (f" · name `{x['name']}`" if x.get("name") else "")
#|                          + (f" · args `{' '.join(x['args'])}`" if x.get("args") else "") for x in info["spark"]]
#|                if info.get("hardcoded"):
#|                    L += ["", "## Hardcoded"] + [f"- L{h['line']} {h['kind']}: `{clip(h['value'], 160)}` — `{h['code']}`" for h in info["hardcoded"]]
#|                preview = self.extra.get("script_previews", {}).get(path)
#|                if preview:
#|                    L += ["", "## Source (secrets redacted)", "```" + {"python": "python", "shell": "bash"}.get(info["lang"], ""), preview, "```"]
#|            self.files[f] = "\n".join(L) + "\n"
#|        if self.an.scripts:
#|            self.files["scripts/INDEX.md"] = "\n".join(idx) + "\n"
#|
#|    # ------------------------------------------------------------------------------------------- DB
#|    def render_db(self):
#|        an = self.an
#|        idx = ["# Databases", ""]
#|        for sid, j in sorted(an.jdbc.items(), key=lambda kv: self.flow.services[kv[0]]["name"]):
#|            matched = next((d for d in self.dbs if sid in d.get("services", [])), None)
#|            tables = sorted(an.tables_by_service().get(sid, {}).keys())
#|            idx.append(f"- DBCP {self.link(sid, 'db/INDEX.md')} → `{j['url']}` · tables used: {', '.join(tables) or '-'} · "
#|                       + (f"documented in [{matched['name']}]({slugify(matched['name'])}.md)" if matched else "**no read-only connection configured** (add a [[databases]] entry)"))
#|        for d in self.dbs:
#|            f = f"db/{slugify(d['name'])}.md"
#|            if d.get("error") and not d.get("tables"):
#|                idx.append(f"- {d['name']}: ⚠ {d['error']}")
#|                continue
#|            idx.append(f"- [{d['name']}]({f.split('/', 1)[1]}): {d.get('dialect')} · {len(d.get('tables', []))} tables documented of {d.get('table_count')}"
#|                       + (f" · ⚠ {d['error']} (showing cached schema)" if d.get("error") else ""))
#|            self.files[f] = self.db_doc(d, f)
#|        if not an.jdbc and not self.dbs:
#|            idx.append("No database connections in the flow and none configured.")
#|        self.files["db/INDEX.md"] = "\n".join(idx) + "\n"
#|
#|    SPLIT_TABLES = 60  # above this many tables a database doc becomes an index + one file per table
#|
#|    def db_doc(self, d, me):
#|        an = self.an
#|        users = defaultdict(list)
#|        for sid in d.get("services", []):
#|            for t, cids in an.tables_by_service().get(sid, {}).items():
#|                users[t.split(".")[-1].lower()] += cids
#|        code_users = defaultdict(list)
#|        for path, info in self.code.files.items():
#|            for t in info.get("tables") or []:
#|                code_users[t.split(".")[-1].lower()].append(path)
#|        L = [f"# Database {d['name']}", f"{d.get('dialect')} · schemas {', '.join(d.get('schemas', []))} · fetched {d.get('fetched', '')}", ""]
#|        if d.get("missing"):
#|            L.append("⚠ Tables referenced by the flow but **not found** in this database: " + ", ".join(d["missing"]))
#|        for chk in [c for c in an.field_checks if c.get("db") == d["name"]]:
#|            L.append(f"- field check {self.link(chk['component_id'], me)} → {chk['table']}: {chk['message']}")
#|        tables = d.get("tables", [])
#|        split = len(tables) > self.SPLIT_TABLES
#|        if split:
#|            folder, used = me[:-3], set()
#|            L += ["", f"{len(tables)} tables — one file per table under `{folder}/` (or `python -m nifikb show <table>`).", "",
#|                  "| Table | Rows | Cols | Used by flow | Doc |", "|---|---|---|---|---|"]
#|        for t in tables:
#|            name = t["table"]
#|            if split:
#|                slug = slugify(name)
#|                while slug in used:
#|                    slug += "-x"
#|                used.add(slug)
#|                path = f"{folder}/{slug}.md"
#|                self.table_file[(d["name"], name)] = path
#|                title = f"# {d['name']}: {t['schema']}.{name}" if d.get("dialect") != "sqlite" else f"# {d['name']}: {name}"
#|                self.files[path] = "\n".join([title, f"[← database {d['name']}](../{me.rsplit('/', 1)[-1]})"]
#|                                             + self.table_section(t, users, code_users, path)[1:]) + "\n"
#|                n_users = len(set(users.get(name.lower(), [])))
#|                L.append(f"| {md_escape(name)} | {t['rows'] if t.get('rows') is not None else ''} | {len(t.get('columns', []))} | "
#|                         f"{n_users or ''} | [{slug}.md]({folder.rsplit('/', 1)[-1]}/{slug}.md) |")
#|            else:
#|                self.table_file[(d["name"], name)] = me
#|                L += [""] + self.table_section(t, users, code_users, me)
#|        others = sorted(set(d.get("all_table_names", [])) - {t["table"] for t in tables})
#|        if others:
#|            L += ["", f"Other tables in schema (not referenced; add to include_tables to document): {clip(', '.join(others), 1500)}"]
#|        return "\n".join(L) + "\n"
#|
#|    def table_section(self, t, users, code_users, me):
#|        name = t["table"]
#|        L = [f"## {t['schema']}.{name}" if t.get("schema") not in (None, "main") else f"## {name}"]
#|        meta = [t.get("type") or "", f"~{t['rows']} rows" if t.get("rows") is not None else ""]
#|        if t.get("comment"):
#|            meta.append(clip(t["comment"], 150))
#|        L.append(" · ".join(m for m in meta if m))
#|        u = users.get(name.lower(), [])
#|        if u:
#|            L.append("Used by flow: " + ", ".join(self.link(x, me) for x in dict.fromkeys(u)))
#|        cu = code_users.get(name.lower(), [])
#|        if cu:
#|            L.append("Used in code: " + ", ".join(_code_ref(p, None, self.extra) for p in dict.fromkeys(cu)))
#|        L += ["| Column | Type | Null | Key | Default | Extra |", "|---|---|---|---|---|---|"]
#|        for c in t.get("columns", []):
#|            L.append(f"| {c['name']} | {md_escape(str(c['type']))} | {'Y' if c['nullable'] else 'N'} | {c.get('key') or ''} | "
#|                     f"{md_escape(clip(str(c['default']), 40)) if c.get('default') is not None else ''} | {md_escape(c.get('extra') or c.get('comment') or '')} |")
#|        if t.get("foreign_keys"):
#|            L.append("FKs: " + ", ".join(f"{fk['column']}→{fk['ref']}" for fk in t["foreign_keys"]))
#|        if t.get("indexes"):
#|            L.append("Indexes: " + ", ".join(f"{i['name']}({','.join(i['columns'])}){' unique' if i['unique'] else ''}" for i in t["indexes"]))
#|        for col, vals in (t.get("profile") or {}).items():
#|            L.append(f"- values of `{col}`: " + ", ".join(f"{v}×{n}" for v, n in vals))
#|        if t.get("sample"):
#|            L.append("Sample (masked): `" + clip(json.dumps(t["sample"][:3], default=str), 600) + "`")
#|        return L
#|
#|    # ------------------------------------------------------------------------------------ INDEX etc.
#|    def render_index(self):
#|        an, flow = self.an, self.flow
#|        procs = [c for c in flow.components.values() if c["kind"] == "PROCESSOR"]
#|        states = Counter(c["state"] for c in procs)
#|        sev = Counter(f["severity"] for f in an.findings)
#|        L = ["# NiFi knowledge base", "",
#|             f"Built {time.strftime('%Y-%m-%d %H:%M')} from `{flow.source}` ({flow.format}, NiFi {flow.nifi_version() or '?'}). "
#|             "Do not read the raw flow file; everything is here.", "",
#|             "## Summary",
#|             f"- {len(flow.groups)} process groups · {len(procs)} processors ({', '.join(f'{v} {k.lower()}' for k, v in states.most_common())}) · "
#|             f"{len(flow.connections)} connections · {len(flow.services)} controller services · {len(flow.param_contexts)} parameter contexts",
#|             f"- custom components: {len(an.custom)} used in flow, {len(self.code.by_fqcn)} found in code · scripts called: {len(an.scripts)}"
#|             f" · code files indexed: {len(self.code.files)}",
#|             f"- issues: {', '.join(f'{v} {k}' for k, v in sorted(sev.items(), key=lambda kv: SEV_ORDER.get(kv[0], 9))) or 'none'} → [issues.md](issues.md)",
#|             *([f"- metadata: {self.extra['metadata_summary']} → [metadata.md](metadata.md)"] if self.extra.get("metadata_summary") else []),
#|             "", "## Flows (process groups)", "| Flow | Procs | Running | Tags | Starts with → ends in | Doc |", "|---|---|---|---|---|---|"]
#|        for gid, g in sorted(flow.groups.items(), key=lambda kv: kv[1]["path"]):
#|            gp = [c for c in procs if c["group_id"] == gid]
#|            if not gp and not any(c["group_id"] == gid for c in flow.components.values()) and gid != flow.root_id:
#|                continue
#|            running = sum(1 for c in gp if c["state"] == "RUNNING")
#|            starts = [f"{type_short(c['type']) or c['kind'].lower()}" for c in an.entry_points(gid)][:4]
#|            ends = []
#|            for c in gp:
#|                if not self.edges(c["id"]) or type_short(c["type"]).startswith(("Put", "Publish", "Send", "Post")):
#|                    facts = [r["value"] for r in an.res_by_comp[c["id"]] if r["kind"] in ("db_table", "s3_bucket", "topic", "url")]
#|                    item = type_short(c["type"]) + (f"({facts[0]})" if facts else "")
#|                    if item not in ends:
#|                        ends.append(item)
#|            indent = "&nbsp;&nbsp;" * g["depth"]
#|            L.append(f"| {indent}{md_escape(g['name'])} | {len(gp)} | {running} | {', '.join(an.group_tags(gid, False))} | "
#|                     f"{md_escape(', '.join(dict.fromkeys(starts)) or '-')} → {md_escape(', '.join(ends[:4]) or '-')} | [{self.group_file[gid]}]({self.group_file[gid]}) |")
#|        links = Counter()
#|        for c in flow.connections:
#|            s, d = flow.components.get(c["source_id"]), flow.components.get(c["dest_id"])
#|            if s and d and s["group_id"] != d["group_id"]:
#|                links[(flow.groups[s["group_id"]]["name"], s["name"], flow.groups[d["group_id"]]["name"], d["name"])] += 1
#|        if links:
#|            L += ["", "## Links between groups"] + [f"- {a} ({ap}) → {b} ({bp})" for (a, ap, b, bp) in sorted(links)]
#|        tables = an.tables_by_service()
#|        ext = [("Databases", [f"{flow.services[s]['name']} `{an.jdbc[s]['url']}` → tables: {', '.join(sorted(tables.get(s, {})) ) or '-'}" for s in an.jdbc])]
#|        for kind, title in (("s3_bucket", "S3 buckets"), ("url", "URLs / APIs"), ("host", "Hosts"), ("topic", "Topics"), ("file_path", "File paths")):
#|            vals = sorted({r["value"] for r in an.resources if r["kind"] == kind})
#|            if vals:
#|                ext.append((title, [clip(", ".join(f"`{v}`" for v in vals), 600)]))
#|        L += ["", "## External systems (details: [external-systems.md](external-systems.md), hardcoded: [hardcoded.md](hardcoded.md))"]
#|        for title, vals in ext:
#|            if vals:
#|                L.append(f"- **{title}**: " + "; ".join(vals))
#|        if flow.param_contexts:
#|            L += ["", "## Parameter contexts"]
#|            for name, ctx in sorted(flow.param_contexts.items()):
#|                ps = ", ".join(f"{k}{'(sensitive)' if v['sensitive'] else '=' + (REDACTED if SECRET_NAME.search(k) else repr(clip(v['value'] or '', 60)))}"
#|                               for k, v in sorted(ctx["params"].items()))
#|                L.append(f"- **{name}**{' inherits ' + ', '.join(ctx['inherits']) if ctx['inherits'] else ''}: {clip(ps, 900)}")
#|        L += ["", "## Files in this knowledge base",
#|              "- `flows/*.md` — one per process group: data-path tree, processors with non-default settings, services",
#|              "- `services.md` · `external-systems.md` · `hardcoded.md` · `issues.md` · `CHANGELOG.md` · `nifi-instance.md`",
#|              "- `custom-code/` — custom processors (source + NAR docs) · `scripts/` — scripts the flow executes · `db/` — table schemas"]
#|        if self.extra.get("metadata"):
#|            L.append("- `metadata.md` — config tables that drive the flow (definitions, structures, feed / API / server config) and their drift")
#|        L.append(f"- Team knowledge (not generated, kept across builds): `{Path(self.extra.get('knowledge_dir') or 'knowledge').name}/context.md` "
#|                 f"and {self.extra.get('learnings', 0)} active learning(s) in `learnings/` — `python -m nifikb learn list` / `learn add`")
#|        L.append("- CLI (cheap lookups, run from the nifi-kb folder): `python -m nifikb search <words>` · `show <name|id>` · "
#|                 "`trace <name|id> [--up]` · `diagnose [--file <name>] <headers…>` · `sql \"SELECT …\"` · `build`")
#|        self.files["INDEX.md"] = "\n".join(L) + "\n"
#|
#|    def render_instance(self, props, nars, catalog):
#|        keys = ["nifi.web.https.host", "nifi.web.https.port", "nifi.web.http.port", "nifi.cluster.is.node", "nifi.zookeeper.connect.string",
#|                "nifi.flow.configuration.file", "nifi.flow.configuration.json.file", "nifi.flow.configuration.archive.dir",
#|                "nifi.content.repository.directory.default", "nifi.flowfile.repository.directory", "nifi.provenance.repository.directory.default",
#|                "nifi.provenance.repository.max.storage.time", "nifi.nar.library.autoload.directory", "nifi.remote.input.socket.port",
#|                "nifi.security.user.login.identity.provider", "nifi.variable.registry.properties"]
#|        L = ["# NiFi instance", ""]
#|        for k in keys:
#|            if k in props:
#|                L.append(f"- `{k}` = `{props[k]}`")
#|        custom = [n for n in nars if n.get("group") and not n["group"].startswith("org.apache.nifi")]
#|        L += ["", f"NARs loaded: {len(nars)} ({len(catalog.types)} component types). Custom NARs: "
#|              + (", ".join(f"{n['artifact']} {n.get('version') or ''} ({n.get('group')})" for n in custom) or "none found")]
#|        L += ["", "## Types used by this flow"]
#|        used = Counter(c["type"] for c in list(self.flow.components.values()) + list(self.flow.services.values()) if c.get("type"))
#|        for t, n in sorted(used.items()):
#|            e = catalog.get(t)
#|            L.append(f"- {type_short(t)} ×{n}" + (f" — {clip(e['description'], 140)}" if e and e.get("description") else ""))
#|        self.files["nifi-instance.md"] = "\n".join(L) + "\n"
#|
#|    def render_changelog(self, rows):
#|        L = ["# Change log", "", "Differences detected between knowledge-base builds (newest first): flow components and, prefixed "
#|             "`config`, rows of the metadata config tables (compared at each metadata refresh; secret columns are not compared).", ""]
#|        last = None
#|        for r in rows:
#|            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"]))
#|            if ts != last:
#|                L += ["", f"## {ts}"]
#|                last = ts
#|            L.append(f"- {r['change']}")
#|        if not rows:
#|            L.append("No changes recorded yet (first build).")
#|        self.files["CHANGELOG.md"] = "\n".join(L) + "\n"
#|
#|    def render_all(self, instance_props, changes):
#|        for gid in self.flow.groups:
#|            self.render_group(gid)
#|        self.render_services()
#|        self.render_external()
#|        self.render_hardcoded()
#|        self.render_issues()
#|        self.render_custom()
#|        self.render_scripts()
#|        self.render_db()
#|        self.render_instance(instance_props, self.an.catalog.nars, self.an.catalog)
#|        self.render_changelog(changes)
#|        self.render_index()
#|        return self.files
#|
#|
#|def _anchor(c):
#|    return f"c-{short(c['id'])}"
#|
#|
#|def _rel(frm, to):
#|    depth = frm.count("/")
#|    return ("../" * depth) + to
#|
#|
#|def _code_ref(path, line, extra):
#|    base = extra.get("code_roots", [])
#|    shown = path
#|    for root in base:
#|        try:
#|            shown = str(Path(path).relative_to(root))
#|            break
#|        except ValueError:
#|            continue
#|    return f"`{shown}{':' + str(line) if line else ''}`"
#|
#|
#|def _reachable(roots, edges):
#|    seen, stack = set(), list(roots)
#|    while stack:
#|        x = stack.pop()
#|        if x in seen:
#|            continue
#|        seen.add(x)
#|        stack.extend(d for _, d in edges(x))
#|    return seen
#@@ FILE nifikb/report.py tc d20cbf915c790d00
#|"""Daily health report: what went wrong or changed in the last N hours, before anyone raises a ticket.
#|
#|Sections: live NiFi health, new error patterns (first seen in the window), top recurring errors, NiFi restarts / crashes,
#|failed loads (load-audit table), config-row changes, flow changes, metadata drift. Output as markdown / HTML; optional
#|delivery by e-mail (SMTP) or a Teams / Slack incoming webhook - only with an explicit --send and a [report] section.
#|"""
#|import html
#|import json
#|import os
#|import smtplib
#|import time
#|import urllib.request
#|from email.message import EmailMessage
#|from pathlib import Path
#|
#|from . import audit as auditmod, logs as lg, nifiapi
#|
#|
#|def build_report(cfg, store, names, hours=24.0):
#|    lg.index(cfg, store, log=lambda m: None)
#|    now = time.time()
#|    newest_log = store.db.execute("SELECT MAX(epoch) FROM log_events").fetchone()[0] or now
#|    since_log = newest_log - hours * 3600  # logs copied from elsewhere may be older than "now"
#|    since = now - hours * 3600
#|    sec = []
#|    stats = {}
#|
#|    api = nifiapi.settings(cfg)
#|    if api:
#|        try:
#|            h = nifiapi.health(nifiapi.Client(api), versioned=store.versioned_groups())
#|            stats["live problems"] = len(h["problems"])
#|            sec.append(("Live NiFi health", [f"**{p['severity']}** {p['kind']}: {p['message']}" + (f" ({names[p['component_id']]})"
#|                                             if p.get("component_id") in names else "") for p in h["problems"]]
#|                        or ["no problems (no back-pressure, stuck queues, invalid processors; repositories fine)"]))
#|        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
#|            sec.append(("Live NiFi health", [f"not available: {e}"]))
#|
#|    new = store.db.execute(
#|        "SELECT template, level, component_id, component_type, COUNT(*) n, MIN(ts) first, MAX(cause) cause, MAX(message) sample "
#|        "FROM log_events WHERE level IN ('ERROR','FATAL') GROUP BY template, component_id HAVING MIN(epoch) >= ? ORDER BY n DESC LIMIT 15",
#|        (since_log,)).fetchall()
#|    stats["new error patterns"] = len(new)
#|    sec.append(("New error patterns (first seen in this window)", [
#|        f"x{r['n']} {names.get(r['component_id'], r['component_type'] or 'NiFi')}: {lg.compact(r['sample'])[:220]}"
#|        + (f" — cause: {r['cause'][:160]}" if r["cause"] else "") for r in new] or ["none"]))
#|    top = store.db.execute(
#|        "SELECT template, component_id, component_type, COUNT(*) n, MAX(cause) cause, MAX(message) sample FROM log_events "
#|        "WHERE level IN ('ERROR','FATAL') AND epoch >= ? GROUP BY template, component_id ORDER BY n DESC LIMIT 10", (since_log,)).fetchall()
#|    stats["errors logged"] = sum(r["n"] for r in top)
#|    sec.append(("Most frequent errors", [f"x{r['n']} {names.get(r['component_id'], r['component_type'] or 'NiFi')}: "
#|                                          f"{lg.compact(r['sample'])[:200]}" + (f" — cause: {r['cause'][:140]}" if r["cause"] else "")
#|                                          for r in top] or ["none"]))
#|    life = store.db.execute("SELECT ts, message FROM log_events WHERE (level = 'LIFECYCLE' OR (file LIKE '%bootstrap%' AND level IN "
#|                            "('WARN','ERROR','FATAL'))) AND epoch >= ? ORDER BY epoch", (since_log,)).fetchall()
#|    if life:
#|        sec.append(("NiFi lifecycle (bootstrap log: starts, stops, crashes, warnings)", [f"{r['ts'][:19]} {r['message'][:200]}" for r in life]))
#|
#|    amodel = store.get_meta("audit_model")
#|    if amodel and amodel.get("time_column"):
#|        try:
#|            rows = failed_loads(cfg, amodel, since)
#|            stats["failed loads"] = len(rows)
#|            sec.append(("Failed loads (load audit)", [auditmod.summarize(amodel, r) for r in rows[:30]] or ["none"]))
#|        except Exception as e:  # DB unreachable etc.
#|            sec.append(("Failed loads (load audit)", [f"not available: {e}"]))
#|
#|    changes = store.db.execute("SELECT ts, change FROM meta_changes WHERE ts >= ? ORDER BY ts DESC LIMIT 40", (since,)).fetchall()
#|    stats["config row changes"] = len(changes)
#|    if changes:
#|        sec.append(("Config-row changes", [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['ts']))} {r['change']}" for r in changes]))
#|    flow = store.db.execute("SELECT ts, change FROM changelog WHERE ts >= ? AND change NOT LIKE 'config %' ORDER BY ts DESC LIMIT 40",
#|                            (since,)).fetchall()
#|    if flow:
#|        sec.append(("Flow changes", [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['ts']))} {r['change']}" for r in flow]))
#|    drift = store.db.execute("SELECT severity, message FROM findings WHERE kind = 'metadata-drift' ORDER BY severity").fetchall()
#|    stats["definitions with drift"] = len(drift)
#|    if drift:
#|        sec.append(("Metadata drift (definitions that disagree with their target)",
#|                    [f"**{r['severity']}** {r['message'][:220]}" for r in drift[:15]] + ([f"… {len(drift) - 15} more"] if len(drift) > 15 else [])))
#|    for name, fn in (("Late / missing files", late_files_section), ("Suggested learnings", learning_suggestions_section)):
#|        try:
#|            lines = fn(cfg, store)
#|        except Exception as e:  # optional sections must never break the report
#|            lines = [f"not available: {e}"]
#|        if lines:
#|            sec.append((name, lines))
#|    return {"title": f"NiFi daily report — last {hours:g} h — {time.strftime('%Y-%m-%d %H:%M')}", "stats": stats, "sections": sec}
#|
#|
#|def late_files_section(cfg, store):
#|    from . import late
#|    items = late.late_files(cfg, store)
#|    return late.format_items(items)[:40] if items else []
#|
#|
#|def learning_suggestions_section(cfg, store):
#|    from . import learnings as lm
#|    return lm.format_suggestions(lm.suggestions(cfg, store))
#|
#|
#|def failed_loads(cfg, model, since):
#|    from . import db as dbmod
#|    a = auditmod.settings(cfg)
#|    dcfg = next(d for d in cfg["databases"] if d["name"] == a["db"])
#|    conn, dialect = dbmod.connect(dcfg)
#|    try:
#|        q = '"' if dialect != "mysql" else "`"
#|        p = dbmod._ph(dialect)
#|        sql = (f"SELECT * FROM {auditmod._fq(dialect, model.get('schema'), model['table'])} WHERE {q}{model['time_column']}{q} >= {p} "
#|               f"ORDER BY {q}{model['time_column']}{q} DESC LIMIT 500")
#|        rows = dbmod._rows(conn, sql, (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since)),))
#|        return [{k: dbmod.mask_value(k, v) for k, v in r.items()} for r in rows if auditmod.is_failure(model, r)]
#|    finally:
#|        conn.close()
#|
#|
#|def to_markdown(r):
#|    L = [f"# {r['title']}", "", " · ".join(f"{k}: **{v}**" for k, v in r["stats"].items())]
#|    for title, lines in r["sections"]:
#|        L += ["", f"## {title}"] + [f"- {x}" for x in lines]
#|    return "\n".join(L) + "\n"
#|
#|
#|def to_html(r):
#|    def inline(t):
#|        t = html.escape(t)
#|        parts = t.split("**")
#|        return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))
#|    body = [f"<h1>{html.escape(r['title'])}</h1>", "<p>" + " · ".join(f"{html.escape(k)}: <b>{v}</b>" for k, v in r["stats"].items()) + "</p>"]
#|    for title, lines in r["sections"]:
#|        body.append(f"<h2>{html.escape(title)}</h2><ul>" + "".join(f"<li>{inline(x)}</li>" for x in lines) + "</ul>")
#|    style = ("body{font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#222;max-width:1100px;margin:20px}"
#|             "h1{font-size:20px}h2{font-size:16px;margin-top:22px;border-bottom:1px solid #ddd}li{margin:3px 0}")
#|    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(r['title'])}</title><style>{style}</style></head>" \
#|           f"<body>{''.join(body)}</body></html>"
#|
#|
#|def _secret(c, key):
#|    if c.get(f"{key}_env") and os.environ.get(c[f"{key}_env"]):
#|        return os.environ[c[f"{key}_env"]]
#|    if c.get(f"{key}_file"):
#|        return Path(c[f"{key}_file"]).read_text(encoding="utf-8").strip()
#|    return c.get(key)
#|
#|
#|def send(cfg, r):
#|    """Deliver per [report]: email (SMTP) and / or webhook (Teams / Slack incoming webhook). Returns what was done."""
#|    c = cfg.get("report") or {}
#|    done = []
#|    if c.get("email_to"):
#|        msg = EmailMessage()
#|        msg["Subject"] = r["title"]
#|        msg["From"] = c.get("email_from", "nifikb@localhost")
#|        msg["To"] = ", ".join(c["email_to"]) if isinstance(c["email_to"], list) else c["email_to"]
#|        msg.set_content(to_markdown(r))
#|        msg.add_alternative(to_html(r), subtype="html")
#|        with smtplib.SMTP(c.get("smtp_host", "localhost"), int(c.get("smtp_port", 25)), timeout=30) as s:
#|            if c.get("smtp_starttls"):
#|                s.starttls()
#|            if c.get("smtp_user"):
#|                s.login(c["smtp_user"], _secret(c, "smtp_password") or "")
#|            s.send_message(msg)
#|        done.append(f"e-mailed to {msg['To']}")
#|    url = _secret(c, "webhook_url")
#|    if url:
#|        text = to_markdown(r)
#|        payload = {"text": text[:25000]}
#|        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
#|        with urllib.request.urlopen(req, timeout=30):
#|            pass
#|        done.append("posted to the webhook")
#|    return done
#@@ FILE nifikb/sqlparse.py t 681ba07d0ca44487
#|"""Minimal SQL helpers: detect SQL text and pull out the table names it reads or writes."""
#|import re
#|
#|_SQL_START = re.compile(r"^\s*(?:\(|/\*.*?\*/\s*)*(select|insert|update|delete|merge|with|upsert|replace|create|alter|truncate|drop|call|exec)\b", re.I | re.S)
#|_SQL_SHAPE = re.compile(r"(?is)\bselect\b.+\bfrom\b|\binsert\s+(?:ignore\s+)?into\b|\bupdate\b\s+\S+\s+set\b|\bdelete\s+from\b|\bmerge\s+into\b"
#|                        r"|\b(?:create|alter|drop|truncate)\s+table\b|\breplace\s+into\b")
#|_TABLE_REF = re.compile(
#|    r"(?is)\b(?P<kw>from|join|into|update|merge\s+into|delete\s+from|truncate(?:\s+table)?|(?:create|alter|drop)\s+table(?:\s+if\s+(?:not\s+)?exists)?|using)"
#|    r"\s+(?P<name>(?:[`\"\[]?[\w$#{}.\-]+[`\"\]]?\.){0,2}[`\"\[]?[\w$#{}\-]+[`\"\]]?)"
#|)
#|_NOT_TABLES = {"select", "set", "values", "where", "lateral", "unnest", "dual", "as", "on", "table", "only", "the",
#|               "a", "an", "ignore", "if", "exists", "not"}
#|
#|
#|def looks_like_sql(text):
#|    text = (text or "").strip()
#|    return len(text) > 12 and bool(_SQL_START.match(text)) and bool(_SQL_SHAPE.search(text))
#|
#|
#|def tables(sql):
#|    """Table names referenced by a SQL string (lower-cased, quotes stripped, EL placeholders kept)."""
#|    sql = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql or "", flags=re.S)
#|    sql = re.sub(r"'(?:[^']|'')*'", "''", sql)
#|    ctes = {m.lower() for m in re.findall(r"(?i)(?:\bwith|,)\s*(\w+)\s+as\s*\(", sql)}
#|    out = []
#|    for m in _TABLE_REF.finditer(sql):
#|        name = re.sub(r"[`\"\[\]]", "", m.group("name")).strip(".").lower()
#|        if not name or name in _NOT_TABLES or name in ctes or name.startswith("(") or name.isdigit():
#|            continue
#|        if m.group("kw").lower() == "using" and not re.search(r"(?i)merge", sql):
#|            continue
#|        if name not in out:
#|            out.append(name)
#|    return out
#@@ FILE nifikb/store.py tc 4e7964692bd34115
#|"""SQLite store: caches (NAR + code parse results), searchable facts, flow snapshots and the change log."""
#|import json
#|import sqlite3
#|import time
#|
#|PERSISTENT = """
#|CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
#|CREATE TABLE IF NOT EXISTS cache_nar(path TEXT PRIMARY KEY, sig TEXT, data TEXT);
#|CREATE TABLE IF NOT EXISTS cache_code(path TEXT PRIMARY KEY, sig TEXT, data TEXT);
#|CREATE TABLE IF NOT EXISTS cache_db(name TEXT PRIMARY KEY, sig TEXT, fetched REAL, data TEXT);
#|CREATE TABLE IF NOT EXISTS snapshot(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, flow_sig TEXT, data TEXT);
#|CREATE TABLE IF NOT EXISTS changelog(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, change TEXT);
#|CREATE TABLE IF NOT EXISTS meta_rows(tbl TEXT, data TEXT);
#|CREATE INDEX IF NOT EXISTS ix_meta_rows ON meta_rows(tbl);
#|CREATE TABLE IF NOT EXISTS meta_changes(ts REAL, tbl TEXT, pk TEXT, link TEXT, change TEXT);
#|CREATE INDEX IF NOT EXISTS ix_meta_changes ON meta_changes(link);
#|CREATE TABLE IF NOT EXISTS log_files(path TEXT PRIMARY KEY, sig TEXT, offset INTEGER, head TEXT);
#|CREATE TABLE IF NOT EXISTS log_events(hash TEXT PRIMARY KEY, ts TEXT, epoch REAL, level TEXT, thread TEXT, logger TEXT,
#|    component_type TEXT, component_id TEXT, flowfile_uuid TEXT, filename TEXT, message TEXT, cause TEXT, template TEXT, file TEXT, line INTEGER);
#|CREATE INDEX IF NOT EXISTS ix_log_comp ON log_events(component_id);
#|CREATE INDEX IF NOT EXISTS ix_log_file ON log_events(filename);
#|CREATE INDEX IF NOT EXISTS ix_log_uuid ON log_events(flowfile_uuid);
#|CREATE INDEX IF NOT EXISTS ix_log_epoch ON log_events(epoch);
#|CREATE TABLE IF NOT EXISTS investigations(ts REAL, key TEXT, rank INTEGER, kind TEXT, signature TEXT, cause TEXT);
#|CREATE INDEX IF NOT EXISTS ix_inv_ts ON investigations(ts);
#|"""
#|DERIVED = """
#|DROP TABLE IF EXISTS components; DROP TABLE IF EXISTS properties; DROP TABLE IF EXISTS connections;
#|DROP TABLE IF EXISTS resources; DROP TABLE IF EXISTS findings; DROP TABLE IF EXISTS code_components;
#|DROP TABLE IF EXISTS db_tables; DROP TABLE IF EXISTS search; DROP TABLE IF EXISTS groups;
#|DROP TABLE IF EXISTS record_schemas;
#|CREATE TABLE groups(id TEXT PRIMARY KEY, name TEXT, parent_id TEXT, path TEXT, doc TEXT, tags TEXT, instance_id TEXT, version TEXT);
#|CREATE TABLE components(id TEXT PRIMARY KEY, kind TEXT, name TEXT, type TEXT, group_id TEXT, group_path TEXT, state TEXT,
#|                        custom INTEGER, facts TEXT, auto_term TEXT, doc TEXT, instance_id TEXT);
#|CREATE TABLE properties(component_id TEXT, name TEXT, display TEXT, value TEXT, resolved TEXT, source TEXT, is_default INTEGER, kinds TEXT);
#|CREATE TABLE connections(id TEXT, source_id TEXT, dest_id TEXT, relationships TEXT, group_id TEXT, name TEXT);
#|CREATE TABLE resources(kind TEXT, value TEXT, component_id TEXT, property TEXT, source TEXT, hardcoded INTEGER, raw TEXT);
#|CREATE TABLE findings(severity TEXT, kind TEXT, component_id TEXT, message TEXT, location TEXT);
#|CREATE TABLE code_components(fqcn TEXT, path TEXT, line INTEGER, data TEXT);
#|CREATE TABLE db_tables(db TEXT, schema_name TEXT, name TEXT, data TEXT, doc TEXT);
#|CREATE TABLE record_schemas(component_id TEXT, db TEXT, table_name TEXT, fields TEXT, translate INTEGER);
#|CREATE VIRTUAL TABLE search USING fts5(kind, ref, title, body, doc UNINDEXED, tokenize='unicode61 remove_diacritics 2 tokenchars ''._-''');
#|"""
#|
#|
#|class Store:
#|    def __init__(self, path):
#|        self.path = path
#|        self.db = sqlite3.connect(path)
#|        self.db.row_factory = sqlite3.Row
#|        self.db.execute("PRAGMA secure_delete=ON")  # replaced snapshots must not linger in free pages
#|        self.db.executescript(PERSISTENT)
#|
#|    def close(self):
#|        self.db.commit()
#|        self.db.close()
#|
#|    # meta
#|    def get_meta(self, key, default=None):
#|        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
#|        return json.loads(row[0]) if row else default
#|
#|    def set_meta(self, key, value):
#|        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, json.dumps(value)))
#|
#|    # caches
#|    def cached(self, table, key, sig):
#|        row = self.db.execute(f"SELECT sig, data FROM {table} WHERE path=?", (key,)).fetchone()
#|        return json.loads(row["data"]) if row and row["sig"] == sig else None
#|
#|    def put_cache(self, table, key, sig, data):
#|        self.db.execute(f"INSERT OR REPLACE INTO {table}(path, sig, data) VALUES(?,?,?)", (key, sig, json.dumps(data)))
#|
#|    def prune_cache(self, table, keep):
#|        keep = set(keep)
#|        for row in self.db.execute(f"SELECT path FROM {table}").fetchall():
#|            if row["path"] not in keep:
#|                self.db.execute(f"DELETE FROM {table} WHERE path=?", (row["path"],))
#|
#|    def cached_db(self, name, sig):
#|        row = self.db.execute("SELECT sig, fetched, data FROM cache_db WHERE name=?", (name,)).fetchone()
#|        return (json.loads(row["data"]), row["fetched"]) if row and row["sig"] == sig else (None, None)
#|
#|    def cached_db_fetched(self, name):
#|        row = self.db.execute("SELECT fetched FROM cache_db WHERE name=?", (name,)).fetchone()
#|        return row["fetched"] if row else None
#|
#|    def cached_db_any(self, name):
#|        row = self.db.execute("SELECT data FROM cache_db WHERE name=?", (name,)).fetchone()
#|        return json.loads(row["data"]) if row else None
#|
#|    def put_db(self, name, sig, data):
#|        self.db.execute("INSERT OR REPLACE INTO cache_db VALUES(?,?,?,?)", (name, sig, time.time(), json.dumps(data, default=str)))
#|
#|    # metadata config-table rows (masked), replaced as a whole on every metadata refresh
#|    def put_meta_rows(self, rows_by_table):
#|        self.db.execute("DELETE FROM meta_rows")
#|        for table, rows in rows_by_table.items():
#|            self.db.executemany("INSERT INTO meta_rows(tbl, data) VALUES(?,?)", [(table, json.dumps(r, default=str)) for r in rows])
#|
#|    def get_meta_rows(self, exclude=None):
#|        out = {}
#|        for row in self.db.execute("SELECT tbl, data FROM meta_rows WHERE tbl IS NOT ? ORDER BY rowid", (exclude,)):
#|            out.setdefault(row["tbl"], []).append(json.loads(row["data"]))
#|        return out
#|
#|    def get_structure_rows(self, table, parent_column, ids):
#|        """Snapshot rows of the structure table whose parent column is one of ids (compared as text)."""
#|        ids = [str(i) for i in ids if i is not None]
#|        if not ids:
#|            return []
#|        path = '$."' + parent_column.replace('"', '\\"') + '"'
#|        sql = (f"SELECT data FROM meta_rows WHERE tbl=? AND CAST(json_extract(data, ?) AS TEXT) IN ({','.join('?' * len(ids))}) "
#|               "ORDER BY rowid")
#|        return [json.loads(r["data"]) for r in self.db.execute(sql, (table, path, *ids))]
#|
#|    def add_meta_changes(self, changes, ts=None, keep=50000):
#|        ts = ts or time.time()
#|        self.db.executemany("INSERT INTO meta_changes(ts, tbl, pk, link, change) VALUES(?,?,?,?,?)",
#|                            [(ts, c["tbl"], c["pk"], c["link"], c["change"]) for c in changes])
#|        self.db.execute("DELETE FROM meta_changes WHERE rowid NOT IN (SELECT rowid FROM meta_changes ORDER BY ts DESC LIMIT ?)", (keep,))
#|
#|    def meta_changes_for(self, links, limit=20):
#|        links = [str(x) for x in links if x is not None]
#|        if not links:
#|            return []
#|        return self.db.execute(f"SELECT ts, tbl, pk, change FROM meta_changes WHERE link IN ({','.join('?' * len(links))}) "
#|                               "ORDER BY ts DESC, rowid DESC LIMIT ?", (*links, limit)).fetchall()
#|
#|    def add_investigation(self, key, entries, ts=None, keep=20000):
#|        """The ranked causes of one investigation [(kind, signature, text)] - the memory behind learning suggestions."""
#|        ts = ts or time.time()
#|        self.db.executemany("INSERT INTO investigations(ts, key, rank, kind, signature, cause) VALUES(?,?,?,?,?,?)",
#|                            [(ts, key, n, kind, sig, text) for n, (kind, sig, text) in enumerate(entries, 1)])
#|        self.db.execute("DELETE FROM investigations WHERE rowid NOT IN (SELECT rowid FROM investigations ORDER BY ts DESC LIMIT ?)", (keep,))
#|        self.db.commit()
#|
#|    def investigations_since(self, ts):
#|        return self.db.execute("SELECT ts, key, rank, kind, signature, cause FROM investigations WHERE ts >= ? ORDER BY ts", (ts,)).fetchall()
#|
#|    def versioned_groups(self):
#|        """[(runtime instance id, path)] of version-controlled process groups (empty for KBs built by older versions)."""
#|        try:
#|            return [(r["instance_id"] or r["id"], r["path"]) for r in
#|                    self.db.execute("SELECT id, instance_id, path FROM groups WHERE version IS NOT NULL")]
#|        except sqlite3.Error:
#|            return []
#|
#|    # NiFi log events (see logs.py)
#|    def add_log_events(self, events):
#|        import hashlib
#|        rows = []
#|        for e in events:
#|            h = hashlib.sha1(f"{e['ts']}|{e['thread']}|{e['message'][:300]}".encode("utf-8", "replace")).hexdigest()
#|            rows.append((h, e["ts"], e["epoch"], e["level"], e["thread"], e["logger"], e["component_type"], e["component_id"],
#|                         e["flowfile_uuid"], e["filename"], e["message"], e["cause"], e["template"], e["file"], e["line"]))
#|        before = self.db.total_changes
#|        self.db.executemany("INSERT OR IGNORE INTO log_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
#|        return self.db.total_changes - before
#|
#|    def prune_log_events(self, keep_days):
#|        newest = self.db.execute("SELECT MAX(epoch) FROM log_events").fetchone()[0]
#|        if newest:
#|            self.db.execute("DELETE FROM log_events WHERE epoch < ?", (newest - keep_days * 86400,))
#|
#|    # snapshots + change log
#|    def last_snapshot(self):
#|        row = self.db.execute("SELECT data FROM snapshot ORDER BY id DESC LIMIT 1").fetchone()
#|        return json.loads(row["data"]) if row else None
#|
#|    def add_snapshot(self, flow_sig, data, keep=20):
#|        self.db.execute("INSERT INTO snapshot(ts, flow_sig, data) VALUES(?,?,?)", (time.time(), flow_sig, json.dumps(data)))
#|        self.db.execute("DELETE FROM snapshot WHERE id NOT IN (SELECT id FROM snapshot ORDER BY id DESC LIMIT ?)", (keep,))
#|
#|    def add_changes(self, changes, ts=None):
#|        ts = ts or time.time()
#|        self.db.executemany("INSERT INTO changelog(ts, change) VALUES(?,?)", [(ts, c) for c in changes])
#|
#|    def changes(self, limit=300):
#|        return self.db.execute("SELECT ts, change FROM changelog ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
#|
#|    # derived facts
#|    def reset_derived(self):
#|        self.db.executescript(DERIVED)
#|
#|    def insert(self, table, rows):
#|        rows = list(rows)
#|        if rows:
#|            cols = list(rows[0].keys())
#|            self.db.executemany(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
#|                                [tuple(r[c] for c in cols) for r in rows])
#|
#|    def search(self, query, limit=20):
#|        terms = [t for t in query.replace('"', " ").split() if t]
#|        if not terms:
#|            return []
#|        fts = " ".join(f'"{t}"*' for t in terms)
#|        try:
#|            return self.db.execute(
#|                "SELECT kind, ref, title, snippet(search, 3, '[', ']', '…', 12) AS snip, doc, bm25(search, 2.0, 5.0, 10.0, 1.0) AS score "
#|                "FROM search WHERE search MATCH ? ORDER BY score LIMIT ?", (fts, limit)).fetchall()
#|        except sqlite3.OperationalError:
#|            like = f"%{query}%"
#|            return self.db.execute("SELECT kind, ref, title, substr(body,1,160) AS snip, doc, 0 AS score FROM search "
#|                                   "WHERE title LIKE ? OR body LIKE ? LIMIT ?", (like, like, limit)).fetchall()
#@@ END part 3 of 5 files 8
