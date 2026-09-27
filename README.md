# nifikb — NiFi knowledge base and support-triage tools for AI assistants

Reads a NiFi install (flow + NARs), your custom processor / script / Spark repos, the (read-only) databases, and the
**metadata config tables that drive a metadata-driven flow** (e.g. `OBJ_DEFINITION`, `OBJ_STRUCTURE`,
`SOURCE_FEED_CONFIG`, `NIFI_JSON_API_CONFIG`). It writes a compact, linked markdown knowledge base plus a searchable
SQLite index, and exposes triage tools over the CLI and an MCP server. An AI assistant (Claude Code, Gemini CLI, …)
calls these tools instead of re-reading multi-MB flow files, so answers are cheap in tokens and verifiable.

No required dependencies (Python 3.11+ standard library). Optional DB drivers:
`pip install pymysql` (MariaDB/MySQL), `pip install pg8000` (PostgreSQL).

## What it does

- **Flow**: every process group as a data-path tree (crosses groups through ports), processors with only non-default
  settings (defaults come from the NAR manifests), parameters / variables resolved, attributes read / written.
- **Custom Java NARs**: custom processors and controller services from source — class hierarchies (properties and
  relationships declared in your abstract base classes), constants resolved across files, `AllowableValue`s, attributes
  read / written with `file:line` (incl. `putAllAttributes` maps and `CoreAttributes`), what the code talks to (JDBC, SFTP,
  HTTP, S3, Kafka, …), log / exception messages (a ticket's error text finds the code line), `META-INF/services`
  registration, and Maven module → NAR module → deployed NAR → version the flow runs. The deployed NAR's compiled
  classes are read too (constant pool, no JDK needed): they show when the repo source differs from what actually runs,
  and give SQL / tables / URLs even when source is missing. NARs built without docs get their property metadata from source.
- **Attribute lineage**: follows FlowFile attributes through the whole graph (standard processors from their manifests,
  custom ones from their code, UpdateAttribute incl. Advanced rules) and flags `${x}` reads that nothing upstream sets,
  or sets under another name (`tableName` vs `table_name`).
- **Scripts and other code**: scripts the flow executes, SQL / tables / hardcoded values in Groovy, Scala, Python, shell.
- **Databases**: columns, keys, indexes, FKs, row estimates for the tables the flow / code use; missing tables and
  record-field / column mismatches. Large schemas are split into one file per table.
- **Metadata config tables** (`[metadata]`): auto-detects the definition table (one row per file), the structure table
  (one row per column: name, type, sequence, length, mandatory) and how the feed / API / server config tables relate
  (declared FKs + shared id columns). Takes a masked snapshot, checks every definition against its real target table
  (missing / NOT NULL columns, types, lengths, nullability, duplicate sequences) and links the custom processors whose
  code reads those tables.
- **Triage**: `diagnose` — give a file name (patterns like `SALES_YYYYMMDD.csv`, `*`, `%`, regex are understood), a
  table, feed or API name and/or the headers / a sample file, and get the expected structure, what does not match
  (unknown / renamed / missing headers, wrong order, structure vs table drift), the related feed / API / server config,
  the processors involved and their known issues.
- **Config-row history**: every metadata refresh (hourly by default) records which `OBJ_*` / config rows changed;
  shown in `CHANGELOG.md` and per definition in `diagnose` ("worked yesterday" tickets).
- **JSON / API payloads**: `diagnose --sample payload.json` applies the feed's configured root path (e.g. `$.data`) and
  compares nested fields against the structure's JSON paths.
- **NiFi logs**: `nifi-app*.log` / `nifi-bootstrap*.log` indexed incrementally (only warnings / errors, with the root
  cause from the stack trace, tied to the processor, FlowFile and file name, grouped by message shape) — `logs`.
- **Provenance** (optional, NiFi REST API, read-only): where a FlowFile went and where / why it was DROPPED (auto-terminated
  relationship, expired, …) — the answer to "file silently disappeared" — `provenance`, plus live `bulletins`.
- **`investigate`**: one call per ticket runs all of the above and returns ranked likely causes with evidence and
  proposed fix SQL for a human to review (made for smaller models such as Gemini Flash). A sample file's content is
  checked too: real vs configured delimiter, column count, mandatory / type / date / length per column, encoding.
- **Load audit** (`[audit]`): the platform's own record of each load (status, error, rows) in every investigation, and
  **late files**: each feed's usual arrival pattern is learned from it, overdue feeds are flagged (`late`).
- **Target side** (`[targets]`, read-only): what a load wrote to HDFS (WebHDFS / Kerberos / `hdfs` CLI), S3 (`aws` CLI /
  boto3) or a mounted folder, and the written **Parquet schema vs the structure rows** (footer decoded without pyarrow).
- **Ticket systems** (`[tickets]`): `ticket INC0012345` / `ticket PROJ-123` reads a ServiceNow / Jira ticket, extracts
  file / feed / table / error / headers and attached samples, investigates and drafts a reply (posted only with `--post`).
- **Onboarding** (`onboard proposal.toml`): checks proposed config rows for a new feed before anyone inserts them.
- **Environments** (`compare --env uat`): flow and config-row differences between UAT and PROD.
- **Live NiFi** (`health`, `versions`): back-pressure, stuck queues, invalid processors, disks; NiFi Registry versions.
- **Daily report** (`report --send`): errors, crashes, failed / late loads, config / flow changes, drift and recurring
  causes nobody has written down yet, by e-mail or Teams / Slack webhook; a self-service **web page** (`web`) for
  colleagues; an **eval** harness that replays past tickets through the tools (and the model).
- **HDFS / S3 loads**: definitions whose target is a location are shown as "loads to …" (`target_db = "none"` switches
  table checks off); **Spark**: `spark-submit` in scripts run by ExecuteStreamCommand is detected and named.
- **Lint**: invalid processors, silently dropped failures, disabled services in use, missing code, metadata drift.
- **Team learnings** (`knowledge/`): what people and agents learn while fixing tickets (symptom, cause, fix, how to spot
  it), one markdown file each, redacted, searchable at once and surfaced automatically by `diagnose` for matching files,
  tables, feeds and processors; plus `knowledge/context.md`, curated team context every agent session starts with.
- **Agents**: MCP server with 27 tools, one playbook for Claude Code / Gemini CLI / others (`CLAUDE.md` = `GEMINI.md` =
  `AGENTS.md`), `/triage` and `/learn` commands for both CLIs, and `doctor` to check an installation.
- **Secrets**: sensitive columns, secrets in code, JSON bodies and auth headers are masked everywhere (KB files,
  `kb.sqlite`, learnings, CLI and MCP output). Databases are only ever read.

Start with [HANDOFF.md](HANDOFF.md) for the full picture (architecture, rollout, maintenance, limitations).

## Setup

1. `python -m nifikb init --nifi-home <path>` (or edit `nifikb.toml`):
   - `[nifi] home` — NiFi install dir (reads `conf/flow.json.gz` or `conf/flow.xml.gz`, `lib/*.nar`, `conf/nifi.properties`)
   - `[nifi] extra_nar_dirs` — folders with custom NARs that are not in `<home>/lib`
   - `[code] repos` — Bitbucket clones: custom processors (incl. the metadata processor), scripts, Spark jobs
   - `[[databases]]` — read-only connections; password from an environment variable (`password_env`)
   - `[logs]` — NiFi's log folder (default `<home>/logs`); `[nifi_api]` — URL + read-only user for provenance
   - `[metadata]` — `db = "<the [[databases]] name holding the config tables>"`, `target_db = "none"` when loads go to
     HDFS / S3; everything else is auto-detected
   - optional: `[audit]`, `[targets]`, `[tickets]`, `[environments.<name>]`, `[registry]`, `[report]`, `[web]` — the
     template explains each one; [HANDOFF.md](HANDOFF.md) section 6 lists every key
   `nifikb.toml` is the only file to edit; passwords come from `password_env` or `password_file`, never the file itself.
2. `python -m nifikb build`
3. `python -m nifikb doctor` — fix every FAIL.
4. Open this folder in Claude Code or Gemini CLI. Both pick up the MCP server (`.mcp.json`, `.gemini/settings.json`)
   and the instructions (`CLAUDE.md` / `GEMINI.md` / `AGENTS.md`, identical copies with the triage playbook); use
   `/triage <ticket>` and `/learn`.
5. Check `kb/metadata.md`: it lists which metadata roles were auto-detected. Override any wrong guess in `[metadata]`.
6. Fill in `knowledge/context.md` (environments, owners, conventions).

Keep it fresh with `python -m nifikb watch` (polls every 30 s), a scheduled task, or `build` before a session —
unchanged inputs make it a no-op; NAR and code parsing is cached per file; database schemas and the metadata snapshot
are re-read every `db_refresh_hours` (or `build --refresh-db`; `diagnose --live` reads the config tables on demand).

## Commands

```
python -m nifikb build [--force] [--refresh-db]
python -m nifikb investigate [--file F] [--feed N] [--table T] [--error TEXT] [--headers …] [--sample S] [--live]
python -m nifikb diagnose [headers…] [--file|--table|--feed NAME] [--sample FILE] [--live] [--json]
python -m nifikb logs [--component C] [--file F] [--uuid U] [--grep T] [--level ERROR|LIFECYCLE] [--since H]
python -m nifikb provenance --file F | --uuid U | --component C      python -m nifikb bulletins
python -m nifikb search <words>          python -m nifikb show <name | id | table>
python -m nifikb trace <name | id> [--up]  python -m nifikb issues [--kind K] [--contains TEXT]
python -m nifikb sql "SELECT …"          python -m nifikb status
python -m nifikb ticket <id> [--post]    python -m nifikb late [--days 35]
python -m nifikb audit --file F          python -m nifikb target --file F | --key K | --location L
python -m nifikb health                  python -m nifikb versions [--group G]
python -m nifikb compare --env uat [--key F] [--what flow|config]
python -m nifikb onboard proposal.toml [--sample S] [--live]   # see examples/new-feed.example.toml
python -m nifikb report [--hours 24] [--html F] [--send]        python -m nifikb web
python -m nifikb eval [--agent "gemini -p"]                     # replay evals/cases.toml
python -m nifikb learn add|list|show|for|retire|context|suggest  # team learnings in knowledge/
python -m nifikb doctor [--offline]       # check the installation
python -m nifikb mcp                      # MCP server on stdio (started by the agents, not by hand)
```

Example: `python -m nifikb diagnose --file /landing/pos/SALES_20260926.csv --sample SALES_20260926.csv`

## Office rollout checklist

- [ ] `python ops/package.py` here, copy `dist/nifi-kb-<version>.zip` to the office laptop, unzip (no downloads allowed there? `python ops/bundle.py` makes one paste-able text file instead, see HANDOFF.md section 4); `python -m unittest discover -s tests` (all green; live DB tests skipped)
- [ ] `python -m nifikb init --nifi-home <NiFi dir>` or edit `nifikb.toml`
- [ ] Custom NARs: already in `<nifi>/lib`, or list their folder in `extra_nar_dirs`
- [ ] Clone the Bitbucket repos (custom processors incl. the metadata processor, scripts, Spark jobs) and list them in `[code] repos`
- [ ] Ask the DBA for a read-only MariaDB user; add a `[[databases]]` block; `set NIFIKB_DB_PASSWORD=...`; `pip install pymysql`
- [ ] Add `[metadata]` with `db = "<that database's name>"` (and `target_db` if the load tables live in another database)
- [ ] `python -m nifikb build`, then check `kb/INDEX.md`, `kb/metadata.md` (detected roles + drift) and `kb/issues.md`
- [ ] Try a real past ticket: `python -m nifikb investigate --file <file name> --sample <the file>` (or `ticket <id>`)
- [ ] Optional: `[audit]` (load-audit table), `[targets]` (HDFS / S3 access), `[tickets]` (Jira / ServiceNow user), `[environments.uat]`
- [ ] Confirm with your security team that the KB (configuration, masked config rows — no secrets) may be sent to your AI provider
- [ ] `python -m nifikb doctor` shows no FAIL; fill in `knowledge/context.md`
- [ ] Schedule the refresh and the daily report: `powershell -ExecutionPolicy Bypass -File ops\register-schedule.ps1 -EveryMinutes 60 -ReportAt 08:00`
- [ ] Commit the folder to git (`kb/` is ignored; `knowledge/` is shared by the team)

## Tests

`python -m unittest discover -s tests -v` — unit tests plus end-to-end builds over a nested multi-group fixture (custom
NAR, Java processors, scripts, SQLite metadata DB with definition / structure / feed / API config tables), the MCP
server over stdio, simulated NiFi / Registry / WebHDFS / Jira / ServiceNow APIs, a fake `aws` CLI, a real Parquet file,
and, when present, the real local NiFi install.
Set `NIFIKB_TEST_MARIADB=host:port:user:password` (an admin user; the test creates and drops its own database and a
read-only user) to also run the live MariaDB tests.
