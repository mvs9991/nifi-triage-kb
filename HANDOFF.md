# nifikb — handoff

For whoever runs, uses or develops this next: the team, a new maintainer, or an AI agent picking the project up.
Last updated 2026-09-27 (version 0.5.0). The day-to-day agent instructions are in `CLAUDE.md` (identical copies:
`GEMINI.md`, `AGENTS.md`); setup details are in `README.md`; this file explains the whole picture.

## 1. What it is and why

Our NiFi platform runs thousands of processors across many ETL flows, and ingestion is **metadata-driven**. Custom Java
processors (packaged as NARs in NiFi's `lib`) read config tables at runtime:
- `OBJ_DEFINITION`: one row per file / object, with file name, target table, delimiter and so on;
- `OBJ_STRUCTURE`: one row per column, with name, type, sequence, length and mandatory flag;
- `SOURCE_FEED_CONFIG`: SFTP / SSH servers;
- `NIFI_JSON_API_CONFIG`: APIs.

The config tables live in MariaDB; loads are written to HDFS / S3 (PutParquet, PutS3Object); Spark jobs are submitted by
scripts run from ExecuteStreamCommand. At the office the agent will be **Gemini CLI with a Flash model**, so the tools
do the planning (`investigate`) and the model mainly explains the result.

Most support tickets are metadata problems. Answering them by hand means reading the flow, the Java code and several
tables. That is slow, and too big for an AI to re-read on every question.

`nifikb` digests all of it once into a compact knowledge base and gives AI agents (Opus in Claude Code, Gemini CLI, …)
a set of deterministic tools to answer from. The agents reason; the tools supply verified facts with ids, `TABLE:id`
and `file:line`. What the team learns while fixing tickets is stored as **learnings** that every agent and person
shares.

## 2. Status

| Area | State |
|---|---|
| Flow digestion (JSON + XML flows, nested groups, ports, parameters, variables, controller services) | done, tested; real local NiFi 1.27 install builds cleanly |
| NAR catalog (manifests, defaults, relationships, attributes) | done, tested on 134 real NARs |
| Custom Java NARs: source parsing (base classes, constants, attribute maps, messages, I/O), Maven module → NAR → version, deployed-bytecode drift | done, tested with fixture code modelled on typical company code — **not yet run on the real Bitbucket repos** |
| Metadata config tables: auto-detected roles and relations, masked snapshot, definition-vs-target drift, `diagnose --file/--feed/--table` | done, tested on SQLite + live MariaDB — **real office column names never seen**; roles are auto-detected and overridable |
| Attribute lineage (`${x}` read but never set / misnamed upstream) | done, tested; no false positives on the real local flow |
| Config-row change history (per-row diff at every metadata refresh; `CHANGELOG.md`; `diagnose` shows a definition's recent changes and, live, changes since the snapshot) | done, tested; refresh interval `[metadata] refresh_hours` (default 1 h) |
| JSON / API payloads (`--sample` with the feed's root path, nested fields compared as paths, `structure_path` role) | done, tested on fixtures |
| NiFi logs (`nifi-app*.log`, `nifi-bootstrap*.log`): incremental index of warnings / errors with root cause, runtime id → flow component, file name / FlowFile uuid, grouping, rotation, retention; `logs` tool | done, tested on the real sandbox logs (4 MB, 95 events in 0.07 s) |
| Provenance + bulletins through the NiFi REST API (`[nifi_api]`, read-only): where a FlowFile was DROPPED and why | done, tested against a **simulated** NiFi API (no JDK on the sandbox, NiFi could not run) — first real test at the office |
| `investigate`: one call, ranked likely causes (provenance, file log errors, metadata, config changes, code line, learnings, findings) | done, tested |
| HDFS / S3 targets (`target_db = "none"`, locations recognised, `definition_location` role) | done, tested |
| Spark: `spark-submit` in scripts detected (class / jar / name / master) and shown on the ExecuteStreamCommand | done, tested; Spark code itself not analysed |
| Sample content checks (`--sample`): configured vs real delimiter, width, mandatory, type, date, length, encoding / BOM; JSON records per path | done, tested on fixtures and a real 2,823-row CSV |
| Proposed fix SQL (UPDATE / INSERT for the config rows, for a human to review) in `diagnose` / `investigate` | done, tested; never executed |
| Load audit (`[audit]`, auto-detected table / columns): last load of a file in `investigate`, `load_audit` tool | done, tested (SQLite + MariaDB) |
| Late / missing files: each feed's arrival pattern (intra-day / daily at HH:MM on weekdays / weekly) learned from the load audit; `late`, daily report | done, tested |
| Target side (`[targets]`): what a load wrote to HDFS (WebHDFS, Kerberos via curl, or the `hdfs` CLI) / S3 (boto3 or the `aws` CLI) / a mounted folder; **Parquet schema read from the file footer (stdlib)** vs the structure; part of `investigate` | done, tested with a fake WebHDFS and a fake `aws` CLI; the Parquet decoder was verified against pyarrow-written files (format 1.0 + 2.6, nested, decimal) |
| Live health (`health`): back-pressure, stuck queues, invalid processors, services, heap, disk, cluster, registry state | done, tested against a simulated NiFi API |
| NiFi Registry (`versions`, `[registry]`): deployed version per process group, live state, history (author, comment); version changes in `CHANGELOG.md` | done, tested against a simulated API |
| Environment comparison (`compare --env uat`): processors / properties / parameters of two flows + config rows of two databases | done, tested |
| New-feed validator (`onboard proposal.toml`): proposed config rows vs the config tables' schema, existing rows, file patterns, structure, target, sample, a similar feed; prints INSERTs to review | done, tested; also run against the sandbox MariaDB |
| Ticket systems (`ticket <id>`, `[tickets]`): Jira (Cloud / Server) and ServiceNow; facts + attached samples → `investigate` → draft reply; posts only with `--post` (never from an agent) | done, tested against fake Jira / ServiceNow APIs |
| Daily report (`report`, markdown / HTML, e-mail via SMTP, Teams / Slack webhook): new errors, crashes, failed / late loads, config and flow changes, drift, recurring causes | done, tested (fake SMTP + webhook) |
| Learning suggestions: recurring top causes across investigations that no learning covers (`learn suggest`, `kb_overview`, daily report) | done, tested |
| Self-service web page (`web`): investigate with upload, report, health, search, learnings; basic auth | done, tested |
| Evaluation harness (`eval`): replays past tickets with known causes, optionally through the model CLI (`--agent "gemini -p"`) | done, tested; fill `evals/cases.toml` with real tickets |
| Single config file `nifikb.toml` (sections in reading order; secrets via env var or `password_file`) | done |
| Databases | MariaDB / MySQL, PostgreSQL, SQLite. Oracle / SQL Server not supported |
| Agent layer: MCP server (27 tools), CLAUDE / GEMINI / AGENTS.md, `/triage` and `/learn` commands, Claude Code settings | done, MCP tested over stdio |
| Team learnings (`knowledge/`) | done, tested (CLI, MCP, redaction, relevance, search, diagnose) |
| Scale | office-sized synthetic flow (6,000 processors, 300 services, 127k metadata rows, 3,000 target tables): full build ≈ 10 s, no-op rebuild instant, `diagnose` < 1 s |
| Tests | 107 in `tests/` (4 need a live MariaDB: `NIFIKB_TEST_MARIADB=host:port:admin:password`) — all green |

Development so far happened on a personal sandbox (`D:\Sanjay`: NiFi 1.27 with a sample sales flow, a local MariaDB
`testDB` seeded with demo `OBJ_*` tables). **Nothing has run against the office environment yet** — section 4 is the plan.

## 3. How it works

```
 NiFi install ──┐   flow.json.gz / flow.xml.gz, lib/*.nar, nifi.properties, logs/nifi-app*.log, nifi-bootstrap*.log
 NiFi REST API ─┤   (optional, live) provenance events, bulletins, health; NiFi Registry: versions
 Ticket system ─┤   (optional) Jira / ServiceNow tickets in, draft replies out (posted only by a person)
 HDFS / S3 ─────┤   (optional, read-only) listings of load targets + Parquet footers
 Bitbucket ─────┤   Java processors / services, poms, META-INF/services, scripts, Spark code
 Databases ─────┤   read-only: schemas of the tables the flow and code use, OBJ_* config rows (masked)
 knowledge/ ────┘   team context + learnings (written by people and agents)
        │
        ▼  python -m nifikb build   (incremental: unchanged inputs = no-op; NAR / code parses cached per file)
 kb/  (generated, never edit)                       kb/kb.sqlite (search index, facts, snapshots, caches)
   INDEX.md, flows/*.md, services.md, metadata.md,  ◄── CLI (python -m nifikb …) and MCP server (python -m nifikb mcp)
   custom-code/*.md, scripts/*.md, db/**, issues.md,        ▲
   external-systems.md, hardcoded.md, CHANGELOG.md           │ tools: investigate, ticket, kb_overview, diagnose, logs, provenance,
                                                             │ late_files, check_target_output, load_audit, health, versions, compare,
                                                             │ check_new_feed, daily_report, search, show, trace, issues, sql, learnings …
                                                    Claude Code (.mcp.json, CLAUDE.md) · Gemini CLI (.gemini/, GEMINI.md)
```

### Modules (`nifikb/`)

| Module | Responsibility |
|---|---|
| `flow.py` | load flow.json / flow.xml into groups, components, services, connections, parameter contexts |
| `catalog.py` | read NARs: extension manifests, service files, **string literals of custom NARs' compiled classes** (constant pool) |
| `code.py` | index source files: Java classes / hierarchies / constants / properties / relationships / attributes / messages / I/O, poms, services, scripts, hardcoded values, SQL tables; `CodeIndex.finalize()` resolves across files |
| `analyze.py` | properties (resolved, defaults, secrets), resources, lint, custom components (drift, versions, registration), **attribute lineage** |
| `db.py` | read-only DB access (sessions forced read-only), introspection, guarded ad-hoc SELECT, masking |
| `metadata.py` | config tables: role / relation discovery, snapshot, structure checks, drift lint, file-pattern matching, dossiers |
| `diagnose.py` | triage engine behind `diagnose` (record-schema path and metadata path) + relevant learnings |
| `investigate.py` | one-call investigation: runs all checks and ranks the likely causes |
| `logs.py` | incremental NiFi log index: parsing, root causes, grouping, rotation, retention, queries |
| `nifiapi.py` | read-only NiFi REST client: login, provenance query lifecycle, FlowFile journeys, bulletins, health, registry versions |
| `content.py` · `fixes.py` | sample content validation (CSV / JSON) · proposed fix SQL for config rows |
| `audit.py` · `late.py` | load-audit table (detection, lookups) · arrival patterns and overdue feeds |
| `target.py` | HDFS / S3 / local listings of load targets, Parquet footer decoder, schema vs structure |
| `tickets.py` | Jira / ServiceNow clients, fact extraction, attachments, draft reply |
| `compare.py` · `onboard.py` | environment comparison · new-feed proposal validator |
| `report.py` · `web.py` · `evals.py` | daily report + delivery · self-service web page · ticket replay harness |
| `learnings.py` | `knowledge/`: parse / write / redact / relevance / search entries; recurring-cause suggestions |
| `render.py` | all markdown in `kb/` |
| `build.py` | orchestration, caching, change log, search index (`_store_facts`) |
| `store.py` | SQLite schema: persistent caches + derived facts + FTS5 search |
| `cli.py` · `mcp.py` · `doctor.py` | command line, MCP server (stdio JSON-RPC, stdlib only), installation check |

Design choices worth keeping:
- **Standard library only.** The only optional dependencies are DB drivers (and boto3, if present, for S3). It must run
  on a locked-down office laptop. Even the Parquet schema is decoded without pyarrow.
- **Deterministic tools, model does the reasoning.** Matching follows NiFi's own rules (e.g. PutDatabaseRecord's
  field-name translation), so results can be explained and trusted.
- **No vector search.** The FTS5 index plus structured lookups keep token use low, and agents query rather than read.
- **Read-only by construction.** DB sessions are forced read-only, `sql` accepts only a single SELECT, HDFS / S3 are
  only listed and a Parquet footer read, and agents only write learnings. Proposed SQL (fixes, new feeds) is printed,
  never run. The only outward write is `ticket <id> --post`, run by a person.
- **Secrets never stored.** Sensitive columns, secret-named constants, passwords in text, bearer tokens and NiFi
  sensitive properties are masked before anything is written. `kb.sqlite` uses `secure_delete`.

## 4. Office rollout (step by step)

Two ways to run it: on the **office laptop** with local copies of the repos and the NiFi folder, or on a **Linux
server** next to NiFi (then logs and `conf/` are read in place; use `python3`, `password_file`, `ops/build.sh` + cron).

1. On this machine run `python ops/package.py` and copy `dist/nifi-kb-<version>.zip` to the office laptop (clean: no `kb/`,
   no caches, a fresh `nifikb.toml` template; this sandbox's config is included as `nifikb.toml.sandbox` for reference).
   Unzip it. Python 3.11+ is needed: `python --version` or `py --version`.
   **No downloads allowed on the laptop?** Run `python ops/bundle.py` (optionally `--max-kb 200` to split it into parts)
   instead. It writes the same content as one plain-text Python file per part (`dist/nifi-kb-<version>-bundle*.py`).
   Open it anywhere you can read text on the laptop (e.g. the file view of a git repo in the browser, or an e-mail), copy
   all of it, paste it into a new file with the same name, save as UTF-8, and run `python <file>`. It recreates the
   `nifi-kb` folder next to it and checks every file's hash, so a cut-off or damaged paste is reported instead of
   producing broken files. Unpacking again later (an upgrade) never overwrites your `nifikb.toml` or `knowledge/`.
   Check with IT / security that bringing the tool in this way is allowed — it is only source code and docs.
2. `pip install pymysql` (MariaDB / MySQL) — `pg8000` for PostgreSQL.
3. `python -m unittest discover -s tests` — should end with `OK (skipped=4)`.
4. Edit `nifikb.toml` (or start from `python -m nifikb init --nifi-home <NiFi dir>`):
   - `[nifi] home` = the NiFi install folder (the flow is read from `conf/`, NARs from `lib/`). If the laptop has no NiFi
     install, copy `conf/flow.json.gz` and the custom NARs over, and use `flow_file` + `extra_nar_dirs`.
   - `[code] repos` = the Bitbucket clones: all custom NAR projects (Maven, incl. the metadata processor), scripts, Spark jobs.
   - `[logs] dirs` = NiFi's `logs/` folder (default `<home>/logs`). With a NiFi cluster, list each node's log folder.
   - `[nifi_api]` = NiFi URL + a read-only user with the policies **query provenance** and **view provenance**
     (for "where was my file dropped"). Optional but strongly recommended.
   - `[[databases]]` = the MariaDB holding the config tables, with a **read-only** user from the DBA. Password via
     `password_env` (`setx NIFIKB_DB_PASSWORD "…"` on Windows) or `password_file` (a file with `chmod 600` on Linux).
   - `[metadata] db = "<name of that block>"` and **`target_db = "none"`** — loads go to HDFS / S3, not to tables.
5. `python -m nifikb build`, then `python -m nifikb doctor`, and fix everything marked FAIL.
6. Check `kb/metadata.md`. It lists which columns were **guessed** as the definition id, lookup keys, target table and
   the structure's field / type / sequence / length / mandatory columns. Correct any wrong guess in `[metadata]` and rebuild.
7. Check `kb/custom-code/INDEX.md`. Every custom processor used in the flow should show its source, and its "Deployed NAR"
   section should say whether the repo matches what runs. Then run `python -m nifikb issues --kind custom-source-drift`.
8. Optional, each one adds a check to `investigate` (all read-only; `doctor` verifies them):
   - `[audit]` — the per-file load-audit table (auto-detected; check `doctor` → load audit). Also enables `late`.
   - `[targets]` — HDFS (`hdfs_url` for WebHDFS, `kerberos = true` with a `kinit` ticket, or the `hdfs` CLI) and S3
     (`aws` CLI profile or boto3). If `OBJ_DEFINITION` has no location column, set `location_template`.
   - `[tickets]` — Jira or ServiceNow with an integration user; try `python -m nifikb ticket <id>` (no `--post`).
   - `[environments.uat]` — a copy of UAT's flow file + a `[[databases]]` entry for UAT's config tables.
   - `[registry]`, `[report]` (SMTP / webhook), `[web]` (login) — see section 6.
9. Fill in `knowledge/context.md`: environments, owners, conventions, quirks.
10. Replay 3–5 real past tickets with `/triage` in Claude Code or Gemini CLI and compare with what actually happened.
    Save the lessons with `/learn`. Put them in `evals/cases.toml` (from `cases.example.toml`) and run
    `python -m nifikb eval --agent "gemini -p"` after every upgrade.
11. Schedule the refresh and the daily report: Windows
    `powershell -ExecutionPolicy Bypass -File ops\register-schedule.ps1 -EveryMinutes 60 -ReportAt 08:00`;
    Linux `crontab -e` → `*/30 * * * * sh /opt/nifi-kb/ops/build.sh` and `0 8 * * * sh /opt/nifi-kb/ops/report.sh`.
12. **Security review before any AI use.** The KB contains configuration (hosts, paths, table and column names) and
    masked config rows, and warning / error log lines (secrets, tokens and e-mail addresses masked; kept `keep_days`),
    but no secrets. Confirm with the security team that sending this to your AI provider is allowed.
13. Commit the folder to git (the `.gitignore` excludes `kb/`) so `knowledge/` is shared by the team.

## 5. Daily use

- **Claude Code** (Opus recommended): open the folder. `.mcp.json` starts the MCP server, `.claude/settings.json` allows
  the `nifikb` tools, and `CLAUDE.md` holds the playbook. Use `/triage <ticket>` and `/learn`.
- **Gemini CLI (Flash):** open the folder. `.gemini/settings.json` starts the same MCP server and `GEMINI.md` holds the
  same playbook, which starts every ticket with `investigate`. Use `/triage` and `/learn`.
- **No agent:** use the CLI directly, e.g.
  `python -m nifikb investigate --file SALES_20260926.csv --error "Structure mismatch"`,
  `python -m nifikb diagnose --file SALES_20260926.csv --sample SALES_20260926.csv`, `provenance --file …`, `logs --file …`,
  `search "<error text>"`, `trace <processor>`, `issues --kind attribute-unset`, `learn for <file>`,
  `ticket INC0012345`, `late`, `target --file …`, `compare --env uat --key …`, `onboard proposal.toml`, `report`.
- **Colleagues without an agent:** `python -m nifikb web` (set `[web]` host / login): they paste a file name, error or
  sample and get the same ranked investigation.
- **Learning loop:** after a solved ticket the agent proposes a learning (symptom, cause, fix, how to spot it) with
  `applies_to` names. From then on, `diagnose` and `find_learnings` surface it automatically for matching files, tables,
  feeds and processors. `kb_overview` and the daily report list **recurring causes nobody has written down yet**: those
  are the learnings to add next. Review the learnings monthly: retire stale ones and promote recurring ones into `context.md`.

## 6. Configuration reference (`nifikb.toml`)

| Section | Keys |
|---|---|
| `[nifi]` | `home`, `flow_file` (optional), `extra_nar_dirs` |
| `[logs]` | `dirs` (default `<home>/logs`), `files` (patterns, default `nifi-app*.log*`, `nifi-bootstrap*.log*`), `keep_days` (14), `initial_tail_mb` (200), `enabled` |
| `[nifi_api]` | `url`, `username` + `password_env` / `password_file`, or `token_env` / `token_file`, or `client_cert` + `client_key`; `ca_cert` or `verify_ssl = false`; `timeout` |
| `[registry]` | `url` (…/nifi-registry-api), `username` + `password_env` / `password_file`, `ca_cert` |
| `[output]` | `dir` (generated KB, default `kb`) |
| `[knowledge]` | `dir` (team knowledge, default `knowledge`) |
| `[code]` | `repos` |
| top level (before any `[section]`) | `db_refresh_hours` (table schemas, default 24) |
| `[[databases]]` | `name`, `kind` (mariadb / mysql / postgres / sqlite), `host`, `port`, `database`, `user`, `password_env` / `password_file`, `include_tables`, `profile_tables`, `sample_rows`, `all_tables`, `match_jdbc` / `dbcp_services` (link to the flow's DBCP when host / db differ), `max_tables`, `schemas` |
| `[targets]` | `location_template` (`{table}`, `{table_lower}`, `{id}`), `hdfs_url` + `hdfs_user` or `kerberos = true` (+ `curl`), `hdfs_cli`, `s3_profile`, `s3_endpoint`, `s3_region`, `s3_cli`, `ca_cert`, `max_entries` (2000), `max_depth` (4), `max_download_mb` (200, hdfs CLI only), `timeout` |
| `[tickets]` | `kind` (`jira` / `servicenow`), `url`, `username` + `token_env` / `password_env` (or `*_file`; a token alone is sent as Bearer), `table` (ServiceNow, `incident`), `note_field` (`work_notes`), `ca_cert` |
| `[environments.<name>]` | `flow_file`, `db` (a `[[databases]]` name), for `compare --env <name>` |
| `[audit]` | `db`, `table`, overrides `file_column`, `status_column`, `time_column`, `error_column`, `rows_column`, `link_column` |
| `[report]` | `email_to`, `email_from`, `smtp_host`, `smtp_port`, `smtp_starttls`, `smtp_user` + `smtp_password_env` / `_file`, `webhook_url_env` / `webhook_url_file` |
| `[web]` | `host`, `port`, `user` + `password_env` / `password_file` |
| `[metadata]` | `db`, `target_db` (`"none"` when loads go to files), `tables` (patterns of config tables), `snapshot_max_rows`, `structure_max_rows`, `refresh_hours` (config rows, default 1); optional overrides `definition_table`, `definition_id`, `definition_keys`, `definition_target`, `definition_location`, `structure_table`, `structure_parent`, `structure_field`, `structure_type`, `structure_order`, `structure_length`, `structure_nullable`, `structure_path`; `[[metadata.relations]] child = "T.C" parent = "T.C"` |

## 7. Maintenance

- **Refresh:** a scheduled `ops\build.cmd` (Windows) or `ops/build.sh` (Linux cron), log in `ops/build.log`, or `build` by
  hand. The log index is also brought up to date on every `logs` / `investigate` call. `build --refresh-db` re-reads
  schemas and metadata now; `diagnose --live` reads config rows on demand.
- **Health:** `python -m nifikb doctor` (also an MCP tool).
- **Agent instructions:** edit `CLAUDE.md`, then run `ops\sync-agent-docs.cmd`. A test fails if the three copies differ.
- **Upgrading nifikb:** replace the `nifikb/` folder. Parser version changes are part of the build signature, so the
  next `build` re-parses everything by itself.
- **Tests:** `python -m unittest discover -s tests -v`. Fixtures are in `tests/fixtures_builder.py`: a nested flow;
  a company-style Java repo with a base class, constants, a DAO, a service interface, a test-only mock and poms;
  a custom NAR with generated `.class` files; SQLite metadata tables; and a lineage flow.

## 8. Known limitations and assumptions

- **Office schema not verified.** Real `OBJ_*` column names were never seen, so detection is heuristic. Check
  `kb/metadata.md` and override in `[metadata]`. Tables beyond the four named ones (the "and many more") are picked up by
  the `tables` patterns (`OBJ_%`, `%_CONFIG`, …). Add patterns if yours are named differently.
- **Java is parsed with regular expressions,** not a compiler. It handles common idioms: builders, constants across
  files, base classes, `AllowableValue`, attribute maps, `CoreAttributes`. Unusual code (properties built in loops,
  reflection, annotation processors) can be missed. The custom-code docs show exactly what was found.
- **Attributes named at runtime are not guessed.** A processor whose attribute names come from database columns is
  treated as an "unknown writer", so the lineage checks stay quiet downstream of it (no false alarms, but fewer
  findings). The same applies to scripts, InvokeHTTP, and ListenHTTP / Kafka headers.
- **Deployed-NAR strings are collected per jar.** Drift checks compare only names defined in the component's own module.
- **Spark:** `spark-submit` calls in the scripts ExecuteStreamCommand runs are detected and named (class, jar, name);
  the Spark jobs themselves are not analysed (by request, for now).
- **Provenance** is only as deep as NiFi keeps it (`nifi.provenance.repository.max.storage.time`, default 24 h) and needs
  a NiFi user with provenance policies. It was tested against a simulated API only.
- **Logs:** only WARN / ERROR / FATAL lines (and bootstrap lifecycle lines) are indexed; INFO / DEBUG is ignored by design.
  A processor that fails without logging and routes to an auto-terminated relationship is only visible via provenance.
- **Targets:** listings are capped (`max_entries`, `max_depth`); outputs named by the flow rather than after the input
  file are shown as "newest outputs". Only Parquet schemas are read (not ORC / Avro). With the `hdfs` CLI the whole file
  is copied to read its footer (WebHDFS reads only the tail).
- **Late files** need at least `--min-history` (5) successful loads of a feed in the window; irregular feeds are skipped.
  Whether the file reached the source server (SFTP / landing) is deliberately not checked.
- **Tickets:** facts are extracted with patterns (file names, known feed / table names, error lines, header lines); a
  vague ticket gives a vague investigation. Only CSV / JSON attachments up to 5 MB are used as samples.
- **Databases:** Oracle and SQL Server are not supported (drivers and dialect would need adding in `db.py`).
- **Sandbox state:** the local MariaDB is not a Windows service (start `C:\Program Files\MariaDB 13.0\bin\mariadbd.exe`
  by hand). The sample flow's Postgres (`localhost:5432/testDB`) is not installed.

## 9. Open questions for the team

1. Real `OBJ_*` / config table DDL and one example row per table: confirm the auto-detection, and list the other config tables.
2. The load-audit table (name, which status values mean success / failure): supported by `[audit]`, to be confirmed.
3. How the office reaches HDFS / S3 from the laptop or server (WebHDFS + Kerberos? an `aws` profile?), and the Jira /
   ServiceNow integration user (read + comment / work note).
4. A read-only MariaDB user for the config tables (to verify detection on the real schema), and a NiFi user with
   provenance policies for `[nifi_api]`.
5. Whether the security team approves sending the KB (configuration and masked config rows) to the AI provider.
6. Who owns `knowledge/context.md` and the monthly review of learnings.

## 10. Troubleshooting

| Symptom | Check |
|---|---|
| Agent cannot see the `nifikb` tools | `doctor` → "Claude Code MCP" / "Gemini CLI MCP"; if `python` is not on PATH use `py` in `.mcp.json` and `.gemini/settings.json`; start the agent from this folder |
| "Knowledge base not built yet" | `python -m nifikb build` |
| No tables / metadata in answers | `doctor` → databases (driver, password env var, read-only user), `[metadata] db` name |
| `diagnose --file` finds nothing | `kb/metadata.md` → lookup keys; file-name patterns in `OBJ_DEFINITION` (`*`, `%`, `YYYYMMDD`, regex are understood); try `--feed` / `--table` or `search` |
| Custom processor "source code not found" | add the repo to `[code] repos`; the class must match the flow type (`com.x.Y`) |
| Answers based on old config rows | `diagnose … --live`, or `build --refresh-db` |
| Build slow on huge schemas | lower `sample_rows` / `profile_tables`; `max_tables` |
| `provenance` says HTTP 403 | the NiFi user needs the policies "query provenance" (global) and "view provenance" (on the process groups) |
| `provenance` finds no events for a file that did arrive | provenance retention (`nifi.provenance.repository.max.storage.time`) or the `filename` attribute was renamed upstream; try `--uuid` from `logs` |
| `logs` shows nothing | `doctor` → logs (folder, file patterns); a cluster needs every node's log folder in `[logs] dirs` |
| `target` says "no location" | the definition has no location column: set `[targets] location_template` or `[metadata] definition_location` |
| `target` on HDFS: HTTP 401 / 403 | Kerberos: `kinit` first and `kerberos = true`; simple auth: `hdfs_user` must be allowed to list the path |
| `ticket` finds no file / feed | the ticket text names neither; ask the reporter, or run `investigate` with the names by hand |
| `late` says nothing although a feed is late | fewer than 5 successful loads in the window, or no `[audit] time_column`; try `late --days 60 --min-history 3` |

## 11. Extending

- **New finding:** add it in `analyze.py` (`self._finding(severity, kind, comp, message)`), add a test, and add a line
  to the glossary in `CLAUDE.md`.
- **New DB kind:** extend `db.connect`, `list_tables` and `describe_table` (dialect-specific SQL), plus `doctor._databases`.
- **New MCP tool:** add it to `TOOLS` and `Server.call` in `mcp.py`, prefer reusing a CLI command, and document it in
  `CLAUDE.md`.
- Keep outputs compact. Agents read `kb/` through tools, so cap lists and link to details instead of dumping them.
