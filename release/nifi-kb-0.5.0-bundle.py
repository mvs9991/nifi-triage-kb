# nifi-kb 0.5.0 - paste bundle - 72 files. Save as nifi-kb-0.5.0-bundle.py, then run:  python nifi-kb-0.5.0-bundle.py
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
#@@ FILE CLAUDE.md tc 1a4243cc19269f2f
#|# NiFi flow assistant
#|
#|You are the support and knowledge assistant for our Apache NiFi platform. You explain how the ingestion flows work
#|(JSON / file / API / SFTP / database, end to end), and you triage support tickets: **why a file, feed or API load
#|failed, was not picked up, or loaded wrongly**. Most tickets are metadata problems: the config tables (OBJ_DEFINITION,
#|OBJ_STRUCTURE, SOURCE_FEED_CONFIG, NIFI_JSON_API_CONFIG, …) that the custom Java metadata processors read at runtime
#|disagree with the incoming file, with the target table, or with each other.
#|
#|(CLAUDE.md, GEMINI.md and AGENTS.md are identical copies for Claude Code, Gemini CLI and other agents — edit one, copy it
#|over the other two; a test fails when they differ.)
#|
#|## Quick start — follow this exactly
#|
#|1. Once per session: call `kb_overview`.
#|2. **Any ticket / problem report → call `investigate` first** with everything the ticket gives: `file`, `feed`, `table`,
#|   `error_text`, `headers` (in file order) or `sample_path`. It runs every check and returns **ranked likely causes**
#|   with the evidence below them. Given only a Jira / ServiceNow id (`PROJ-123`, `INC0012345`), call `ticket` instead: it
#|   reads the ticket, extracts those facts (and attached samples) and runs `investigate` for you.
#|3. Answer from that report: **Cause**, **Evidence** (ids, `TABLE:id`, `file:line`, log lines), **Fix**, **Also noticed**.
#|   Only call other tools when the report is not conclusive (the "Next checks" section says what is missing).
#|4. If the lesson is reusable, `add_learning`. Never change anything — propose changes.
#|
#|## Start of every session
#|
#|1. Call `kb_overview` (or read `kb/INDEX.md`). It returns the flows, external systems, issue counts, **when the KB was
#|   built**, the team context (`knowledge/context.md`) and the most recent team learnings. Read them before answering.
#|2. If the user says the flow, code, NARs or database changed since that build time, call `build` first.
#|3. If results look incomplete (no custom code, no tables, metadata roles missing), call `doctor` and tell the user what
#|   to configure instead of guessing.
#|
#|## Tools
#|
#|Use the `nifikb` MCP tools (Claude Code: `.mcp.json`, Gemini CLI: `.gemini/settings.json`). Without MCP, run the same
#|commands from this folder with `python -m nifikb …`.
#|
#|| MCP tool | CLI | Use for |
#||---|---|---|
#|| `kb_overview` | read `kb/INDEX.md` | start of session: flows, external systems, issue counts, build time, recent log errors, team context, recent learnings |
#|| `investigate` | `investigate --file/--feed/--table/--error … [--headers …] [--sample f] [--live]` | **first call for any ticket**: everything below in one ranked report |
#|| `diagnose` | `diagnose [headers…] --file/--table/--feed <name> [--sample f] [--live] [--json]` | **any ticket about a file, feed, API, table or "metadata issue"** |
#|| `logs` | `logs [--component C] [--file F] [--uuid U] [--grep T] [--level L] [--since H]` | warnings / errors from `nifi-app.log` (grouped, with root cause) and NiFi starts / stops / crashes from `nifi-bootstrap.log` (`LIFECYCLE`) |
#|| `provenance` | `provenance --file F \| --uuid U \| --component C` | where a FlowFile went and where / why it ended: **DROPPED at which processor** (auto-terminated relationship, expired, …), sent where, or still in flight — needs `[nifi_api]` |
#|| `bulletins` | `bulletins` | errors currently shown in the NiFi UI (last ~5 minutes) — needs `[nifi_api]` |
#|| `ticket` | `ticket <id> [--post]` | Jira / ServiceNow ticket → extracted file / feed / error / headers → `investigate` → draft reply. Agents never post; a person adds `--post` |
#|| `load_audit` | `audit --file F \| --definition ID` | the platform's own load record of a file: status, error, row count, time |
#|| `late_files` | `late [--days N]` | **"file not received"**: feeds whose next file is overdue, from their usual arrival pattern in the load audit |
#|| `check_target_output` | `target --file F \| --key K \| --location L` | **"loaded but data missing / wrong"**: files the load wrote to HDFS / S3 and the Parquet schema vs the structure rows |
#|| `health` | `health` | live flow health: back-pressure, stuck queues, invalid processors, disabled services, disk, heap — needs `[nifi_api]` |
#|| `versions` | `versions [--group G]` | NiFi Registry: deployed version per process group, local changes, who changed it when and why |
#|| `compare` | `compare --env uat [--key F]` | **"works in UAT, fails in PROD"**: processors, properties, parameters and config rows of two environments |
#|| `check_new_feed` | `onboard proposal.toml [--sample f]` | **onboarding**: validate proposed config rows for a new feed before anyone inserts them; returns problems + INSERTs to review |
#|| `daily_report` | `report [--hours 24]` | what went wrong recently: new errors, crashes, failed / late loads, config and flow changes, drift, recurring causes |
#|| `search` | `search <words>` | processors, properties, SQL, tables, code, **log / error messages**, metadata definitions, config rows, learnings |
#|| `show` | `show <name \| id-prefix \| table>` | one component with every non-default setting, a process group, a custom class, or a table |
#|| `trace` | `trace <name \| id> [--up]` | data path downstream (or upstream with `--up`), across process groups |
#|| `issues` | `issues [--kind K] [--contains T]` | static findings (see the glossary below), filtered |
#|| `read_kb_file` | read `kb/<file>.md` | flows/*.md, services.md, metadata.md, db/*.md, scripts/*.md, custom-code/*.md, CHANGELOG.md |
#|| `sql` | `sql "SELECT …" [--db name]` | read-only live query (single SELECT; sensitive columns masked) — e.g. load / audit status of one file |
#|| `find_learnings` | `learn for <terms…>` / `learn list` | team learnings from earlier tickets that match file names, tables, feeds, processors, error words |
#|| `get_learning` | `learn show <id>` | full text of one learning |
#|| `add_learning` | `learn add --title … --body …` | record a reusable lesson after solving a ticket (rules below) |
#|| `retire_learning` | `learn retire <id> --reason …` | mark a learning obsolete when it no longer holds |
#|| `build` | `build [--refresh-db]` | refresh the KB (no-op when nothing changed) |
#|| `doctor` | `doctor [--offline]` | check config, NiFi files, repos, DB access, metadata roles, KB freshness, agent setup |
#|
#|## Where the knowledge is
#|
#|`kb/` is **generated** by `nifikb build` from the flow, NARs, code repos and databases — never edit it, never read the raw
#|sources it was built from. `knowledge/` is **written by people and agents** and survives every build.
#|
#|| Need | Read |
#||---|---|
#|| Overview, list of flows, external systems | `kb/INDEX.md` |
#|| One flow (process group): data-path tree + every processor's non-default settings, attributes read / written | `kb/flows/<name>.md` |
#|| Controller services (DB pools, readers / writers, SSL, AWS creds) | `kb/services.md` |
#|| Config tables that drive the flow: roles (definition / structure), relations, which custom code reads them, drift vs target tables | `kb/metadata.md` |
#|| Everything a flow touches: tables, buckets, URLs, hosts, paths, topics | `kb/external-systems.md` |
#|| Hardcoded values in flow + code | `kb/hardcoded.md` |
#|| Findings (glossary below) | `kb/issues.md` |
#|| Custom processors / services: Java source incl. inherited properties, attributes read / written with `file:line`, log / error messages, what they talk to, Maven module → NAR → deployed version, source-vs-deployed drift | `kb/custom-code/` |
#|| Scripts the flow executes (ExecuteStreamCommand / ExecuteScript) | `kb/scripts/` |
#|| Table schemas, row counts, value profiles (one file per table for large schemas) | `kb/db/` |
#|| What changed between builds: flow components, and config-table rows (`config …` lines) | `kb/CHANGELOG.md` |
#|| Team context: environments, owners, conventions, known quirks | `knowledge/context.md` |
#|| Lessons from earlier tickets | `knowledge/learnings/*.md` (via `find_learnings`) |
#|
#|## Triage playbook (support tickets)
#|
#|1. **Extract** from the ticket: file name(s), feed / API / source name, target table, the headers or JSON keys that were
#|   sent (or a sample file path), the exact error text, and when it happened. Ask only for what you cannot find.
#|2. **Investigate**: `investigate` with all of it. It combines the checks below and ranks what it finds; read its ranked
#|   causes first, then the evidence sections.
#|3. **Go deeper only where the report is not conclusive** — the individual tools:
#|   - `diagnose` — the metadata side in detail: which definition / config rows match the name (file-name patterns,
#|     feed, table, API), the structure (sequence, type, length, mandatory) vs the headers or `sample_path` (JSON payloads:
#|     the feed's root path, e.g. `$.data`, is applied and nested fields are compared as paths), the target, related feed /
#|     API / server rows, and the definition's **recent config-row changes** (`live=true` also shows rows changed since the
#|     snapshot — "it worked yesterday" tickets are often a changed `OBJ_*` row).
#|   - `provenance` — **file missing / not loaded / silently dropped**: the FlowFile's path through the flow and the
#|     processor where it was DROPPED, with the reason (auto-terminated relationship, expired in a queue, emptied by a
#|     user) and its attributes at that moment. No events at all = the file never entered NiFi under that name (listing,
#|     path, file-name filter, permissions) or its events aged out.
#|   - `logs` — what NiFi logged: errors for the file (`file`), for a processor (`component`), a FlowFile (`uuid`) or a text
#|     (`grep`), grouped with counts and the root cause; `level=LIFECYCLE` shows NiFi restarts / crashes
#|     (`nifi-bootstrap.log`). Most processors log an ERROR just before routing to `failure`, so an auto-terminated failure
#|     still leaves a log line.
#|   - `search` a distinctive fragment of the ticket's error text: custom Java log / exception messages are indexed and
#|     point to the exact `File.java:line` and processor.
#|   - `find_learnings` for earlier tickets like this one — a strong hint, not proof.
#|   - `late_files` — **"file not received"**: is the feed overdue compared with when it usually arrives, and did the
#|     latest attempt fail? (Whether the file reached the source server is outside nifikb — ask the sender.)
#|   - `check_target_output` — **"loaded but the data is missing / wrong"**: what the load wrote to HDFS / S3, and whether
#|     the written Parquet has the structure's columns and types. (`investigate` already includes it when `[targets]` is set.)
#|   - `versions` / `compare` — **"it worked before" / "works in UAT"**: registry versions and who changed the flow, or the
#|     differences between two environments' flows and config rows.
#|   - `health` — the whole instance: back-pressure, stuck queues, invalid processors, disk, heap.
#|4. **Read the evidence**, most severe first (glossary below). Decide whose side the problem is on: the sender's file,
#|   our config rows, the target table, the flow, or the deployed code.
#|5. **Confirm in the flow** when the cause is not yet certain: `show` / `trace` the processors named, the custom-code doc
#|   for how the processor uses the config tables and which attributes it sets, `sql` for load / audit rows of that file.
#|6. **Answer** in this shape:
#|   - **Cause** — one or two sentences.
#|   - **Evidence** — components with short id (`PutDatabaseRecord 4cb1c050`), config rows as `TABLE:id`, code as
#|     `file:line`, the exact mismatching fields / values, and the learning id if one applied.
#|   - **Fix** — who changes what: the sender (file layout), us (the exact config row / column, as a proposed SQL
#|     statement for a human to review and run), the flow (processor + property), or a deployment (which NAR version).
#|   - **Also noticed** — other problems seen on the same path, briefly.
#|7. **Record the lesson** if it is reusable (next section).
#|
#|## Other questions
#|
#|- **"How does feed / flow X work?"** — `diagnose --feed X` (config rows) + `trace` from its entry processor; describe the
#|  path source → metadata lookup → transforms → target, naming the attributes that carry the metadata between them.
#|- **Impact analysis** ("what breaks if we rename column C / change OBJ_STRUCTURE for X / upgrade NAR N / move server S") —
#|  `search` the name, `trace` downstream of every processor found, check `kb/metadata.md` for definitions using it and
#|  `find_learnings` for past incidents; list what would break and what to test.
#|- **Onboarding a new feed** — take an existing, similar feed as the template (`diagnose --feed`), list the config rows it
#|  needs (definition, structure with sequence / type / length / mandatory per column, feed / API / server rows), write
#|  them as a proposal (`examples/new-feed.example.toml`) and run `check_new_feed` with `like` = the template feed and a
#|  sample: it checks column names / types / required columns of the config tables, duplicate ids and names, whether an
#|  existing definition would also match the file, the structure, the target table and the sample, and prints the
#|  INSERT statements for a human to review. Report every ERROR before anyone inserts.
#|- **"What went wrong overnight / is everything OK?"** — `daily_report` (includes late files and recurring causes that
#|  have no learning yet), then `health`.
#|- **Explaining code** — use the custom-code doc first; open the Java file only at the `file:line` it gives.
#|
#|## Team learnings — the memory shared by every agent and person
#|
#|After a ticket is solved, add a learning with `add_learning` **when the knowledge is reusable and the KB cannot derive
#|it**: a recurring root cause, a vendor / source-system quirk, a misleading symptom, a fix procedure, a convention nobody
#|wrote down, an answer to a question people keep asking.
#|
#|Do **not** add: one-off facts, anything the flow / code / tables already show (the KB regenerates those), guesses, or
#|anything sensitive — no passwords, tokens, personal data, customer records (secrets are redacted automatically, but do
#|not rely on it).
#|
#|How to write one:
#|- `title`: one specific line — "SALES feed switches to pipe delimiter at month end", not "delimiter issue".
#|- `kind`: `fix` (cause + fix of a failure), `pattern` (recurring behaviour), `gotcha` (misleading / surprising),
#|  `context` (background), `faq`.
#|- `applies_to`: the file names or patterns (`SALES_*.csv`), tables, feeds, APIs, processor names or short ids and config
#|  rows (`OBJ_DEFINITION:12`) it concerns — this is how `diagnose` and `find_learnings` surface it later.
#|- `tags`, `ticket`, `author` (`claude`, `gemini`, or the person's name).
#|- `body` in markdown:
#|
#|      ## Symptom
#|      What the user saw (error text, missing file, wrong rows).
#|      ## Cause
#|      The verified root cause, with evidence (ids, rows, file:line).
#|      ## Fix
#|      What was changed or what to change, and who owns it.
#|      ## How to spot it next time
#|      The quickest check (a diagnose call, a query, a finding kind).
#|
#|Before adding, `find_learnings` for the same thing: if an older learning is wrong or outdated, `retire_learning` it
#|(with `replaced_by`) and add the corrected one. Tell the user which learning you added. Promoting stable, important
#|learnings into `knowledge/context.md` is a human decision — suggest it when the same lesson keeps coming back.
#|
#|`kb_overview` and `daily_report` list **recurring causes with no learning yet** (the same top cause in several
#|investigations). When a ticket confirms one of them, write it down — that is the highest-value learning there is.
#|
#|## Rules
#|
#|- **Read-only.** Never run or claim to have run writes (INSERT / UPDATE / DELETE, flow or NAR changes). Propose them.
#|  The only things you write are learnings (`add_learning`, `retire_learning`) and the KB itself (`build`).
#|- **Never open `flow.json.gz` / `flow.xml.gz` or NAR files** — they are huge; the KB contains them in digested form.
#|- Open source files in the Bitbucket repos only when the KB points to them (`path:line`) and you need implementation detail.
#|- Quote component names with their short id and code as `file:line`, so answers are verifiable.
#|- If the KB says something is missing (custom code not provided, DB not configured, role not detected), say so and name
#|  the setting that would fix it instead of guessing. `kb/metadata.md` lists auto-detected metadata roles; a wrong
#|  guess is fixed in `[metadata]` of `nifikb.toml`.
#|- Masked values (`***`, `<redacted>`, `<sensitive>`) are secrets; never try to recover them.
#|- Say how fresh your evidence is (KB build time, or `live`), especially when the answer depends on config rows.
#|
#|## Findings glossary (`issues`, `diagnose`)
#|
#|| Kind | Meaning |
#||---|---|
#|| `unknown-header`, `header-name`, `missing-field`, `field-order`, `duplicate-header` | the incoming file / JSON does not match the structure rows (names, case / underscores, mandatory fields, sequence) |
#|| `column-missing`, `required-column`, `type-mismatch`, `length`, `nullability`, `duplicate-seq`, `duplicate-field`, `target-missing`, `no-structure` | the structure rows disagree with the real target table (config problem on our side); `metadata-drift` in `issues` |
#|| `json-root` | no record found under the feed's JSON root path in the sample: wrong root path in the config, or the API changed its payload shape |
#|| `attribute-unset`, `attribute-misnamed` | a processor reads `${x}` that nothing upstream sets, or sets under another name (`tableName` vs `table_name`) — empty at runtime |
#|| `field-mismatch`, `missing-table` | a PutDatabaseRecord's record fields vs its table columns; a table the flow uses does not exist |
#|| `custom-source-drift`, `bundle-version`, `custom-nar-missing`, `custom-not-registered`, `custom-code-missing` | what runs is not what is in the repo: deployed NAR older / newer, other version in the flow, NAR absent (ghost processor), class not loadable, source not provided |
#|| `dropped-errors`, `unhandled-relationship`, `no-input`, `disabled-service`, `disabled-downstream` | flow wiring: failures silently auto-terminated, processor invalid, nothing feeds it, service disabled, data queues up |
#|| `plaintext-secret`, `unknown-type`, `missing-service`, `db-unreachable` | configuration hygiene / environment problems |
#|
#|## NiFi reading guide
#|
#|- In `flows/*.md` data paths, `*rel* → X` means relationship `rel` is connected to X; `✖ auto-terminated` relationships are dropped.
#|- Property values: `raw` ⇒ `resolved` shows parameters `#{..}` and variables `${var}` substituted; remaining `${attr}` are
#|  FlowFile attributes set upstream (see "writes attributes" on earlier processors).
#|- Processor states: RUNNING, STOPPED, DISABLED. Components with `unhandled-relationship` are INVALID and do not run.
#|- "hardcoded" = a literal in the flow instead of a Parameter Context value.
#|- Loads go to HDFS / S3 (PutParquet, PutS3Object, PutHDFS): a definition's "target" is then a location, not a database
#|  table — `diagnose` shows it as "loads to …" and does not check it against a table (`[metadata] target_db = "none"`).
#|- Spark jobs are submitted by scripts that ExecuteStreamCommand runs; the script doc and the processor say which job
#|  (`spark-submit` class / jar / name). The Spark code itself is not analysed.
#|- In our metadata-driven flows the file → table mapping, column list, delimiter and connection details live in the config
#|  tables, not in processor properties: the custom metadata processor reads them and writes attributes (e.g.
#|  `table_name`), and downstream processors use them as `${table_name}`. A wrong or missing config row therefore shows up
#|  as a wrong / empty attribute several processors later — follow the attribute, not only the connections.
#@@ COPY GEMINI.md CLAUDE.md
#@@ COPY AGENTS.md CLAUDE.md
#@@ FILE README.md tc ca573e64a71a931c
#|# nifikb — NiFi knowledge base and support-triage tools for AI assistants
#|
#|Reads a NiFi install (flow + NARs), your custom processor / script / Spark repos, the (read-only) databases, and the
#|**metadata config tables that drive a metadata-driven flow** (e.g. `OBJ_DEFINITION`, `OBJ_STRUCTURE`,
#|`SOURCE_FEED_CONFIG`, `NIFI_JSON_API_CONFIG`). It writes a compact, linked markdown knowledge base plus a searchable
#|SQLite index, and exposes triage tools over the CLI and an MCP server. An AI assistant (Claude Code, Gemini CLI, …)
#|calls these tools instead of re-reading multi-MB flow files, so answers are cheap in tokens and verifiable.
#|
#|No required dependencies (Python 3.11+ standard library). Optional DB drivers:
#|`pip install pymysql` (MariaDB/MySQL), `pip install pg8000` (PostgreSQL).
#|
#|## What it does
#|
#|- **Flow**: every process group as a data-path tree (crosses groups through ports), processors with only non-default
#|  settings (defaults come from the NAR manifests), parameters / variables resolved, attributes read / written.
#|- **Custom Java NARs**: custom processors and controller services from source — class hierarchies (properties and
#|  relationships declared in your abstract base classes), constants resolved across files, `AllowableValue`s, attributes
#|  read / written with `file:line` (incl. `putAllAttributes` maps and `CoreAttributes`), what the code talks to (JDBC, SFTP,
#|  HTTP, S3, Kafka, …), log / exception messages (a ticket's error text finds the code line), `META-INF/services`
#|  registration, and Maven module → NAR module → deployed NAR → version the flow runs. The deployed NAR's compiled
#|  classes are read too (constant pool, no JDK needed): they show when the repo source differs from what actually runs,
#|  and give SQL / tables / URLs even when source is missing. NARs built without docs get their property metadata from source.
#|- **Attribute lineage**: follows FlowFile attributes through the whole graph (standard processors from their manifests,
#|  custom ones from their code, UpdateAttribute incl. Advanced rules) and flags `${x}` reads that nothing upstream sets,
#|  or sets under another name (`tableName` vs `table_name`).
#|- **Scripts and other code**: scripts the flow executes, SQL / tables / hardcoded values in Groovy, Scala, Python, shell.
#|- **Databases**: columns, keys, indexes, FKs, row estimates for the tables the flow / code use; missing tables and
#|  record-field / column mismatches. Large schemas are split into one file per table.
#|- **Metadata config tables** (`[metadata]`): auto-detects the definition table (one row per file), the structure table
#|  (one row per column: name, type, sequence, length, mandatory) and how the feed / API / server config tables relate
#|  (declared FKs + shared id columns). Takes a masked snapshot, checks every definition against its real target table
#|  (missing / NOT NULL columns, types, lengths, nullability, duplicate sequences) and links the custom processors whose
#|  code reads those tables.
#|- **Triage**: `diagnose` — give a file name (patterns like `SALES_YYYYMMDD.csv`, `*`, `%`, regex are understood), a
#|  table, feed or API name and/or the headers / a sample file, and get the expected structure, what does not match
#|  (unknown / renamed / missing headers, wrong order, structure vs table drift), the related feed / API / server config,
#|  the processors involved and their known issues.
#|- **Config-row history**: every metadata refresh (hourly by default) records which `OBJ_*` / config rows changed;
#|  shown in `CHANGELOG.md` and per definition in `diagnose` ("worked yesterday" tickets).
#|- **JSON / API payloads**: `diagnose --sample payload.json` applies the feed's configured root path (e.g. `$.data`) and
#|  compares nested fields against the structure's JSON paths.
#|- **NiFi logs**: `nifi-app*.log` / `nifi-bootstrap*.log` indexed incrementally (only warnings / errors, with the root
#|  cause from the stack trace, tied to the processor, FlowFile and file name, grouped by message shape) — `logs`.
#|- **Provenance** (optional, NiFi REST API, read-only): where a FlowFile went and where / why it was DROPPED (auto-terminated
#|  relationship, expired, …) — the answer to "file silently disappeared" — `provenance`, plus live `bulletins`.
#|- **`investigate`**: one call per ticket runs all of the above and returns ranked likely causes with evidence and
#|  proposed fix SQL for a human to review (made for smaller models such as Gemini Flash). A sample file's content is
#|  checked too: real vs configured delimiter, column count, mandatory / type / date / length per column, encoding.
#|- **Load audit** (`[audit]`): the platform's own record of each load (status, error, rows) in every investigation, and
#|  **late files**: each feed's usual arrival pattern is learned from it, overdue feeds are flagged (`late`).
#|- **Target side** (`[targets]`, read-only): what a load wrote to HDFS (WebHDFS / Kerberos / `hdfs` CLI), S3 (`aws` CLI /
#|  boto3) or a mounted folder, and the written **Parquet schema vs the structure rows** (footer decoded without pyarrow).
#|- **Ticket systems** (`[tickets]`): `ticket INC0012345` / `ticket PROJ-123` reads a ServiceNow / Jira ticket, extracts
#|  file / feed / table / error / headers and attached samples, investigates and drafts a reply (posted only with `--post`).
#|- **Onboarding** (`onboard proposal.toml`): checks proposed config rows for a new feed before anyone inserts them.
#|- **Environments** (`compare --env uat`): flow and config-row differences between UAT and PROD.
#|- **Live NiFi** (`health`, `versions`): back-pressure, stuck queues, invalid processors, disks; NiFi Registry versions.
#|- **Daily report** (`report --send`): errors, crashes, failed / late loads, config / flow changes, drift and recurring
#|  causes nobody has written down yet, by e-mail or Teams / Slack webhook; a self-service **web page** (`web`) for
#|  colleagues; an **eval** harness that replays past tickets through the tools (and the model).
#|- **HDFS / S3 loads**: definitions whose target is a location are shown as "loads to …" (`target_db = "none"` switches
#|  table checks off); **Spark**: `spark-submit` in scripts run by ExecuteStreamCommand is detected and named.
#|- **Lint**: invalid processors, silently dropped failures, disabled services in use, missing code, metadata drift.
#|- **Team learnings** (`knowledge/`): what people and agents learn while fixing tickets (symptom, cause, fix, how to spot
#|  it), one markdown file each, redacted, searchable at once and surfaced automatically by `diagnose` for matching files,
#|  tables, feeds and processors; plus `knowledge/context.md`, curated team context every agent session starts with.
#|- **Agents**: MCP server with 27 tools, one playbook for Claude Code / Gemini CLI / others (`CLAUDE.md` = `GEMINI.md` =
#|  `AGENTS.md`), `/triage` and `/learn` commands for both CLIs, and `doctor` to check an installation.
#|- **Secrets**: sensitive columns, secrets in code, JSON bodies and auth headers are masked everywhere (KB files,
#|  `kb.sqlite`, learnings, CLI and MCP output). Databases are only ever read.
#|
#|Start with [HANDOFF.md](HANDOFF.md) for the full picture (architecture, rollout, maintenance, limitations).
#|
#|## Setup
#|
#|1. `python -m nifikb init --nifi-home <path>` (or edit `nifikb.toml`):
#|   - `[nifi] home` — NiFi install dir (reads `conf/flow.json.gz` or `conf/flow.xml.gz`, `lib/*.nar`, `conf/nifi.properties`)
#|   - `[nifi] extra_nar_dirs` — folders with custom NARs that are not in `<home>/lib`
#|   - `[code] repos` — Bitbucket clones: custom processors (incl. the metadata processor), scripts, Spark jobs
#|   - `[[databases]]` — read-only connections; password from an environment variable (`password_env`)
#|   - `[logs]` — NiFi's log folder (default `<home>/logs`); `[nifi_api]` — URL + read-only user for provenance
#|   - `[metadata]` — `db = "<the [[databases]] name holding the config tables>"`, `target_db = "none"` when loads go to
#|     HDFS / S3; everything else is auto-detected
#|   - optional: `[audit]`, `[targets]`, `[tickets]`, `[environments.<name>]`, `[registry]`, `[report]`, `[web]` — the
#|     template explains each one; [HANDOFF.md](HANDOFF.md) section 6 lists every key
#|   `nifikb.toml` is the only file to edit; passwords come from `password_env` or `password_file`, never the file itself.
#|2. `python -m nifikb build`
#|3. `python -m nifikb doctor` — fix every FAIL.
#|4. Open this folder in Claude Code or Gemini CLI. Both pick up the MCP server (`.mcp.json`, `.gemini/settings.json`)
#|   and the instructions (`CLAUDE.md` / `GEMINI.md` / `AGENTS.md`, identical copies with the triage playbook); use
#|   `/triage <ticket>` and `/learn`.
#|5. Check `kb/metadata.md`: it lists which metadata roles were auto-detected. Override any wrong guess in `[metadata]`.
#|6. Fill in `knowledge/context.md` (environments, owners, conventions).
#|
#|Keep it fresh with `python -m nifikb watch` (polls every 30 s), a scheduled task, or `build` before a session —
#|unchanged inputs make it a no-op; NAR and code parsing is cached per file; database schemas and the metadata snapshot
#|are re-read every `db_refresh_hours` (or `build --refresh-db`; `diagnose --live` reads the config tables on demand).
#|
#|## Commands
#|
#|```
#|python -m nifikb build [--force] [--refresh-db]
#|python -m nifikb investigate [--file F] [--feed N] [--table T] [--error TEXT] [--headers …] [--sample S] [--live]
#|python -m nifikb diagnose [headers…] [--file|--table|--feed NAME] [--sample FILE] [--live] [--json]
#|python -m nifikb logs [--component C] [--file F] [--uuid U] [--grep T] [--level ERROR|LIFECYCLE] [--since H]
#|python -m nifikb provenance --file F | --uuid U | --component C      python -m nifikb bulletins
#|python -m nifikb search <words>          python -m nifikb show <name | id | table>
#|python -m nifikb trace <name | id> [--up]  python -m nifikb issues [--kind K] [--contains TEXT]
#|python -m nifikb sql "SELECT …"          python -m nifikb status
#|python -m nifikb ticket <id> [--post]    python -m nifikb late [--days 35]
#|python -m nifikb audit --file F          python -m nifikb target --file F | --key K | --location L
#|python -m nifikb health                  python -m nifikb versions [--group G]
#|python -m nifikb compare --env uat [--key F] [--what flow|config]
#|python -m nifikb onboard proposal.toml [--sample S] [--live]   # see examples/new-feed.example.toml
#|python -m nifikb report [--hours 24] [--html F] [--send]        python -m nifikb web
#|python -m nifikb eval [--agent "gemini -p"]                     # replay evals/cases.toml
#|python -m nifikb learn add|list|show|for|retire|context|suggest  # team learnings in knowledge/
#|python -m nifikb doctor [--offline]       # check the installation
#|python -m nifikb mcp                      # MCP server on stdio (started by the agents, not by hand)
#|```
#|
#|Example: `python -m nifikb diagnose --file /landing/pos/SALES_20260926.csv --sample SALES_20260926.csv`
#|
#|## Office rollout checklist
#|
#|- [ ] `python ops/package.py` here, copy `dist/nifi-kb-<version>.zip` to the office laptop, unzip (no downloads allowed there? `python ops/bundle.py` makes one paste-able text file instead, see HANDOFF.md section 4); `python -m unittest discover -s tests` (all green; live DB tests skipped)
#|- [ ] `python -m nifikb init --nifi-home <NiFi dir>` or edit `nifikb.toml`
#|- [ ] Custom NARs: already in `<nifi>/lib`, or list their folder in `extra_nar_dirs`
#|- [ ] Clone the Bitbucket repos (custom processors incl. the metadata processor, scripts, Spark jobs) and list them in `[code] repos`
#|- [ ] Ask the DBA for a read-only MariaDB user; add a `[[databases]]` block; `set NIFIKB_DB_PASSWORD=...`; `pip install pymysql`
#|- [ ] Add `[metadata]` with `db = "<that database's name>"` (and `target_db` if the load tables live in another database)
#|- [ ] `python -m nifikb build`, then check `kb/INDEX.md`, `kb/metadata.md` (detected roles + drift) and `kb/issues.md`
#|- [ ] Try a real past ticket: `python -m nifikb investigate --file <file name> --sample <the file>` (or `ticket <id>`)
#|- [ ] Optional: `[audit]` (load-audit table), `[targets]` (HDFS / S3 access), `[tickets]` (Jira / ServiceNow user), `[environments.uat]`
#|- [ ] Confirm with your security team that the KB (configuration, masked config rows — no secrets) may be sent to your AI provider
#|- [ ] `python -m nifikb doctor` shows no FAIL; fill in `knowledge/context.md`
#|- [ ] Schedule the refresh and the daily report: `powershell -ExecutionPolicy Bypass -File ops\register-schedule.ps1 -EveryMinutes 60 -ReportAt 08:00`
#|- [ ] Commit the folder to git (`kb/` is ignored; `knowledge/` is shared by the team)
#|
#|## Tests
#|
#|`python -m unittest discover -s tests -v` — unit tests plus end-to-end builds over a nested multi-group fixture (custom
#|NAR, Java processors, scripts, SQLite metadata DB with definition / structure / feed / API config tables), the MCP
#|server over stdio, simulated NiFi / Registry / WebHDFS / Jira / ServiceNow APIs, a fake `aws` CLI, a real Parquet file,
#|and, when present, the real local NiFi install.
#|Set `NIFIKB_TEST_MARIADB=host:port:user:password` (an admin user; the test creates and drops its own database and a
#|read-only user) to also run the live MariaDB tests.
#@@ FILE HANDOFF.md tc 6001f488dea4bf80
#|# nifikb — handoff
#|
#|For whoever runs, uses or develops this next: the team, a new maintainer, or an AI agent picking the project up.
#|Last updated 2026-09-27 (version 0.5.0). The day-to-day agent instructions are in `CLAUDE.md` (identical copies:
#|`GEMINI.md`, `AGENTS.md`); setup details are in `README.md`; this file explains the whole picture.
#|
#|## 1. What it is and why
#|
#|Our NiFi platform runs thousands of processors across many ETL flows, and ingestion is **metadata-driven**. Custom Java
#|processors (packaged as NARs in NiFi's `lib`) read config tables at runtime:
#|- `OBJ_DEFINITION`: one row per file / object, with file name, target table, delimiter and so on;
#|- `OBJ_STRUCTURE`: one row per column, with name, type, sequence, length and mandatory flag;
#|- `SOURCE_FEED_CONFIG`: SFTP / SSH servers;
#|- `NIFI_JSON_API_CONFIG`: APIs.
#|
#|The config tables live in MariaDB; loads are written to HDFS / S3 (PutParquet, PutS3Object); Spark jobs are submitted by
#|scripts run from ExecuteStreamCommand. At the office the agent will be **Gemini CLI with a Flash model**, so the tools
#|do the planning (`investigate`) and the model mainly explains the result.
#|
#|Most support tickets are metadata problems. Answering them by hand means reading the flow, the Java code and several
#|tables. That is slow, and too big for an AI to re-read on every question.
#|
#|`nifikb` digests all of it once into a compact knowledge base and gives AI agents (Opus in Claude Code, Gemini CLI, …)
#|a set of deterministic tools to answer from. The agents reason; the tools supply verified facts with ids, `TABLE:id`
#|and `file:line`. What the team learns while fixing tickets is stored as **learnings** that every agent and person
#|shares.
#|
#|## 2. Status
#|
#|| Area | State |
#||---|---|
#|| Flow digestion (JSON + XML flows, nested groups, ports, parameters, variables, controller services) | done, tested; real local NiFi 1.27 install builds cleanly |
#|| NAR catalog (manifests, defaults, relationships, attributes) | done, tested on 134 real NARs |
#|| Custom Java NARs: source parsing (base classes, constants, attribute maps, messages, I/O), Maven module → NAR → version, deployed-bytecode drift | done, tested with fixture code modelled on typical company code — **not yet run on the real Bitbucket repos** |
#|| Metadata config tables: auto-detected roles and relations, masked snapshot, definition-vs-target drift, `diagnose --file/--feed/--table` | done, tested on SQLite + live MariaDB — **real office column names never seen**; roles are auto-detected and overridable |
#|| Attribute lineage (`${x}` read but never set / misnamed upstream) | done, tested; no false positives on the real local flow |
#|| Config-row change history (per-row diff at every metadata refresh; `CHANGELOG.md`; `diagnose` shows a definition's recent changes and, live, changes since the snapshot) | done, tested; refresh interval `[metadata] refresh_hours` (default 1 h) |
#|| JSON / API payloads (`--sample` with the feed's root path, nested fields compared as paths, `structure_path` role) | done, tested on fixtures |
#|| NiFi logs (`nifi-app*.log`, `nifi-bootstrap*.log`): incremental index of warnings / errors with root cause, runtime id → flow component, file name / FlowFile uuid, grouping, rotation, retention; `logs` tool | done, tested on the real sandbox logs (4 MB, 95 events in 0.07 s) |
#|| Provenance + bulletins through the NiFi REST API (`[nifi_api]`, read-only): where a FlowFile was DROPPED and why | done, tested against a **simulated** NiFi API (no JDK on the sandbox, NiFi could not run) — first real test at the office |
#|| `investigate`: one call, ranked likely causes (provenance, file log errors, metadata, config changes, code line, learnings, findings) | done, tested |
#|| HDFS / S3 targets (`target_db = "none"`, locations recognised, `definition_location` role) | done, tested |
#|| Spark: `spark-submit` in scripts detected (class / jar / name / master) and shown on the ExecuteStreamCommand | done, tested; Spark code itself not analysed |
#|| Sample content checks (`--sample`): configured vs real delimiter, width, mandatory, type, date, length, encoding / BOM; JSON records per path | done, tested on fixtures and a real 2,823-row CSV |
#|| Proposed fix SQL (UPDATE / INSERT for the config rows, for a human to review) in `diagnose` / `investigate` | done, tested; never executed |
#|| Load audit (`[audit]`, auto-detected table / columns): last load of a file in `investigate`, `load_audit` tool | done, tested (SQLite + MariaDB) |
#|| Late / missing files: each feed's arrival pattern (intra-day / daily at HH:MM on weekdays / weekly) learned from the load audit; `late`, daily report | done, tested |
#|| Target side (`[targets]`): what a load wrote to HDFS (WebHDFS, Kerberos via curl, or the `hdfs` CLI) / S3 (boto3 or the `aws` CLI) / a mounted folder; **Parquet schema read from the file footer (stdlib)** vs the structure; part of `investigate` | done, tested with a fake WebHDFS and a fake `aws` CLI; the Parquet decoder was verified against pyarrow-written files (format 1.0 + 2.6, nested, decimal) |
#|| Live health (`health`): back-pressure, stuck queues, invalid processors, services, heap, disk, cluster, registry state | done, tested against a simulated NiFi API |
#|| NiFi Registry (`versions`, `[registry]`): deployed version per process group, live state, history (author, comment); version changes in `CHANGELOG.md` | done, tested against a simulated API |
#|| Environment comparison (`compare --env uat`): processors / properties / parameters of two flows + config rows of two databases | done, tested |
#|| New-feed validator (`onboard proposal.toml`): proposed config rows vs the config tables' schema, existing rows, file patterns, structure, target, sample, a similar feed; prints INSERTs to review | done, tested; also run against the sandbox MariaDB |
#|| Ticket systems (`ticket <id>`, `[tickets]`): Jira (Cloud / Server) and ServiceNow; facts + attached samples → `investigate` → draft reply; posts only with `--post` (never from an agent) | done, tested against fake Jira / ServiceNow APIs |
#|| Daily report (`report`, markdown / HTML, e-mail via SMTP, Teams / Slack webhook): new errors, crashes, failed / late loads, config and flow changes, drift, recurring causes | done, tested (fake SMTP + webhook) |
#|| Learning suggestions: recurring top causes across investigations that no learning covers (`learn suggest`, `kb_overview`, daily report) | done, tested |
#|| Self-service web page (`web`): investigate with upload, report, health, search, learnings; basic auth | done, tested |
#|| Evaluation harness (`eval`): replays past tickets with known causes, optionally through the model CLI (`--agent "gemini -p"`) | done, tested; fill `evals/cases.toml` with real tickets |
#|| Single config file `nifikb.toml` (sections in reading order; secrets via env var or `password_file`) | done |
#|| Databases | MariaDB / MySQL, PostgreSQL, SQLite. Oracle / SQL Server not supported |
#|| Agent layer: MCP server (27 tools), CLAUDE / GEMINI / AGENTS.md, `/triage` and `/learn` commands, Claude Code settings | done, MCP tested over stdio |
#|| Team learnings (`knowledge/`) | done, tested (CLI, MCP, redaction, relevance, search, diagnose) |
#|| Scale | office-sized synthetic flow (6,000 processors, 300 services, 127k metadata rows, 3,000 target tables): full build ≈ 10 s, no-op rebuild instant, `diagnose` < 1 s |
#|| Tests | 107 in `tests/` (4 need a live MariaDB: `NIFIKB_TEST_MARIADB=host:port:admin:password`) — all green |
#|
#|Development so far happened on a personal sandbox (`D:\Sanjay`: NiFi 1.27 with a sample sales flow, a local MariaDB
#|`testDB` seeded with demo `OBJ_*` tables). **Nothing has run against the office environment yet** — section 4 is the plan.
#|
#|## 3. How it works
#|
#|```
#| NiFi install ──┐   flow.json.gz / flow.xml.gz, lib/*.nar, nifi.properties, logs/nifi-app*.log, nifi-bootstrap*.log
#| NiFi REST API ─┤   (optional, live) provenance events, bulletins, health; NiFi Registry: versions
#| Ticket system ─┤   (optional) Jira / ServiceNow tickets in, draft replies out (posted only by a person)
#| HDFS / S3 ─────┤   (optional, read-only) listings of load targets + Parquet footers
#| Bitbucket ─────┤   Java processors / services, poms, META-INF/services, scripts, Spark code
#| Databases ─────┤   read-only: schemas of the tables the flow and code use, OBJ_* config rows (masked)
#| knowledge/ ────┘   team context + learnings (written by people and agents)
#|        │
#|        ▼  python -m nifikb build   (incremental: unchanged inputs = no-op; NAR / code parses cached per file)
#| kb/  (generated, never edit)                       kb/kb.sqlite (search index, facts, snapshots, caches)
#|   INDEX.md, flows/*.md, services.md, metadata.md,  ◄── CLI (python -m nifikb …) and MCP server (python -m nifikb mcp)
#|   custom-code/*.md, scripts/*.md, db/**, issues.md,        ▲
#|   external-systems.md, hardcoded.md, CHANGELOG.md           │ tools: investigate, ticket, kb_overview, diagnose, logs, provenance,
#|                                                             │ late_files, check_target_output, load_audit, health, versions, compare,
#|                                                             │ check_new_feed, daily_report, search, show, trace, issues, sql, learnings …
#|                                                    Claude Code (.mcp.json, CLAUDE.md) · Gemini CLI (.gemini/, GEMINI.md)
#|```
#|
#|### Modules (`nifikb/`)
#|
#|| Module | Responsibility |
#||---|---|
#|| `flow.py` | load flow.json / flow.xml into groups, components, services, connections, parameter contexts |
#|| `catalog.py` | read NARs: extension manifests, service files, **string literals of custom NARs' compiled classes** (constant pool) |
#|| `code.py` | index source files: Java classes / hierarchies / constants / properties / relationships / attributes / messages / I/O, poms, services, scripts, hardcoded values, SQL tables; `CodeIndex.finalize()` resolves across files |
#|| `analyze.py` | properties (resolved, defaults, secrets), resources, lint, custom components (drift, versions, registration), **attribute lineage** |
#|| `db.py` | read-only DB access (sessions forced read-only), introspection, guarded ad-hoc SELECT, masking |
#|| `metadata.py` | config tables: role / relation discovery, snapshot, structure checks, drift lint, file-pattern matching, dossiers |
#|| `diagnose.py` | triage engine behind `diagnose` (record-schema path and metadata path) + relevant learnings |
#|| `investigate.py` | one-call investigation: runs all checks and ranks the likely causes |
#|| `logs.py` | incremental NiFi log index: parsing, root causes, grouping, rotation, retention, queries |
#|| `nifiapi.py` | read-only NiFi REST client: login, provenance query lifecycle, FlowFile journeys, bulletins, health, registry versions |
#|| `content.py` · `fixes.py` | sample content validation (CSV / JSON) · proposed fix SQL for config rows |
#|| `audit.py` · `late.py` | load-audit table (detection, lookups) · arrival patterns and overdue feeds |
#|| `target.py` | HDFS / S3 / local listings of load targets, Parquet footer decoder, schema vs structure |
#|| `tickets.py` | Jira / ServiceNow clients, fact extraction, attachments, draft reply |
#|| `compare.py` · `onboard.py` | environment comparison · new-feed proposal validator |
#|| `report.py` · `web.py` · `evals.py` | daily report + delivery · self-service web page · ticket replay harness |
#|| `learnings.py` | `knowledge/`: parse / write / redact / relevance / search entries; recurring-cause suggestions |
#|| `render.py` | all markdown in `kb/` |
#|| `build.py` | orchestration, caching, change log, search index (`_store_facts`) |
#|| `store.py` | SQLite schema: persistent caches + derived facts + FTS5 search |
#|| `cli.py` · `mcp.py` · `doctor.py` | command line, MCP server (stdio JSON-RPC, stdlib only), installation check |
#|
#|Design choices worth keeping:
#|- **Standard library only.** The only optional dependencies are DB drivers (and boto3, if present, for S3). It must run
#|  on a locked-down office laptop. Even the Parquet schema is decoded without pyarrow.
#|- **Deterministic tools, model does the reasoning.** Matching follows NiFi's own rules (e.g. PutDatabaseRecord's
#|  field-name translation), so results can be explained and trusted.
#|- **No vector search.** The FTS5 index plus structured lookups keep token use low, and agents query rather than read.
#|- **Read-only by construction.** DB sessions are forced read-only, `sql` accepts only a single SELECT, HDFS / S3 are
#|  only listed and a Parquet footer read, and agents only write learnings. Proposed SQL (fixes, new feeds) is printed,
#|  never run. The only outward write is `ticket <id> --post`, run by a person.
#|- **Secrets never stored.** Sensitive columns, secret-named constants, passwords in text, bearer tokens and NiFi
#|  sensitive properties are masked before anything is written. `kb.sqlite` uses `secure_delete`.
#|
#|## 4. Office rollout (step by step)
#|
#|Two ways to run it: on the **office laptop** with local copies of the repos and the NiFi folder, or on a **Linux
#|server** next to NiFi (then logs and `conf/` are read in place; use `python3`, `password_file`, `ops/build.sh` + cron).
#|
#|1. On this machine run `python ops/package.py` and copy `dist/nifi-kb-<version>.zip` to the office laptop (clean: no `kb/`,
#|   no caches, a fresh `nifikb.toml` template; this sandbox's config is included as `nifikb.toml.sandbox` for reference).
#|   Unzip it. Python 3.11+ is needed: `python --version` or `py --version`.
#|   **No downloads allowed on the laptop?** Run `python ops/bundle.py` (optionally `--max-kb 200` to split it into parts)
#|   instead. It writes the same content as one plain-text Python file per part (`dist/nifi-kb-<version>-bundle*.py`).
#|   Open it anywhere you can read text on the laptop (e.g. the file view of a git repo in the browser, or an e-mail), copy
#|   all of it, paste it into a new file with the same name, save as UTF-8, and run `python <file>`. It recreates the
#|   `nifi-kb` folder next to it and checks every file's hash, so a cut-off or damaged paste is reported instead of
#|   producing broken files. Unpacking again later (an upgrade) never overwrites your `nifikb.toml` or `knowledge/`.
#|   Check with IT / security that bringing the tool in this way is allowed — it is only source code and docs.
#|2. `pip install pymysql` (MariaDB / MySQL) — `pg8000` for PostgreSQL.
#|3. `python -m unittest discover -s tests` — should end with `OK (skipped=4)`.
#|4. Edit `nifikb.toml` (or start from `python -m nifikb init --nifi-home <NiFi dir>`):
#|   - `[nifi] home` = the NiFi install folder (the flow is read from `conf/`, NARs from `lib/`). If the laptop has no NiFi
#|     install, copy `conf/flow.json.gz` and the custom NARs over, and use `flow_file` + `extra_nar_dirs`.
#|   - `[code] repos` = the Bitbucket clones: all custom NAR projects (Maven, incl. the metadata processor), scripts, Spark jobs.
#|   - `[logs] dirs` = NiFi's `logs/` folder (default `<home>/logs`). With a NiFi cluster, list each node's log folder.
#|   - `[nifi_api]` = NiFi URL + a read-only user with the policies **query provenance** and **view provenance**
#|     (for "where was my file dropped"). Optional but strongly recommended.
#|   - `[[databases]]` = the MariaDB holding the config tables, with a **read-only** user from the DBA. Password via
#|     `password_env` (`setx NIFIKB_DB_PASSWORD "…"` on Windows) or `password_file` (a file with `chmod 600` on Linux).
#|   - `[metadata] db = "<name of that block>"` and **`target_db = "none"`** — loads go to HDFS / S3, not to tables.
#|5. `python -m nifikb build`, then `python -m nifikb doctor`, and fix everything marked FAIL.
#|6. Check `kb/metadata.md`. It lists which columns were **guessed** as the definition id, lookup keys, target table and
#|   the structure's field / type / sequence / length / mandatory columns. Correct any wrong guess in `[metadata]` and rebuild.
#|7. Check `kb/custom-code/INDEX.md`. Every custom processor used in the flow should show its source, and its "Deployed NAR"
#|   section should say whether the repo matches what runs. Then run `python -m nifikb issues --kind custom-source-drift`.
#|8. Optional, each one adds a check to `investigate` (all read-only; `doctor` verifies them):
#|   - `[audit]` — the per-file load-audit table (auto-detected; check `doctor` → load audit). Also enables `late`.
#|   - `[targets]` — HDFS (`hdfs_url` for WebHDFS, `kerberos = true` with a `kinit` ticket, or the `hdfs` CLI) and S3
#|     (`aws` CLI profile or boto3). If `OBJ_DEFINITION` has no location column, set `location_template`.
#|   - `[tickets]` — Jira or ServiceNow with an integration user; try `python -m nifikb ticket <id>` (no `--post`).
#|   - `[environments.uat]` — a copy of UAT's flow file + a `[[databases]]` entry for UAT's config tables.
#|   - `[registry]`, `[report]` (SMTP / webhook), `[web]` (login) — see section 6.
#|9. Fill in `knowledge/context.md`: environments, owners, conventions, quirks.
#|10. Replay 3–5 real past tickets with `/triage` in Claude Code or Gemini CLI and compare with what actually happened.
#|    Save the lessons with `/learn`. Put them in `evals/cases.toml` (from `cases.example.toml`) and run
#|    `python -m nifikb eval --agent "gemini -p"` after every upgrade.
#|11. Schedule the refresh and the daily report: Windows
#|    `powershell -ExecutionPolicy Bypass -File ops\register-schedule.ps1 -EveryMinutes 60 -ReportAt 08:00`;
#|    Linux `crontab -e` → `*/30 * * * * sh /opt/nifi-kb/ops/build.sh` and `0 8 * * * sh /opt/nifi-kb/ops/report.sh`.
#|12. **Security review before any AI use.** The KB contains configuration (hosts, paths, table and column names) and
#|    masked config rows, and warning / error log lines (secrets, tokens and e-mail addresses masked; kept `keep_days`),
#|    but no secrets. Confirm with the security team that sending this to your AI provider is allowed.
#|13. Commit the folder to git (the `.gitignore` excludes `kb/`) so `knowledge/` is shared by the team.
#|
#|## 5. Daily use
#|
#|- **Claude Code** (Opus recommended): open the folder. `.mcp.json` starts the MCP server, `.claude/settings.json` allows
#|  the `nifikb` tools, and `CLAUDE.md` holds the playbook. Use `/triage <ticket>` and `/learn`.
#|- **Gemini CLI (Flash):** open the folder. `.gemini/settings.json` starts the same MCP server and `GEMINI.md` holds the
#|  same playbook, which starts every ticket with `investigate`. Use `/triage` and `/learn`.
#|- **No agent:** use the CLI directly, e.g.
#|  `python -m nifikb investigate --file SALES_20260926.csv --error "Structure mismatch"`,
#|  `python -m nifikb diagnose --file SALES_20260926.csv --sample SALES_20260926.csv`, `provenance --file …`, `logs --file …`,
#|  `search "<error text>"`, `trace <processor>`, `issues --kind attribute-unset`, `learn for <file>`,
#|  `ticket INC0012345`, `late`, `target --file …`, `compare --env uat --key …`, `onboard proposal.toml`, `report`.
#|- **Colleagues without an agent:** `python -m nifikb web` (set `[web]` host / login): they paste a file name, error or
#|  sample and get the same ranked investigation.
#|- **Learning loop:** after a solved ticket the agent proposes a learning (symptom, cause, fix, how to spot it) with
#|  `applies_to` names. From then on, `diagnose` and `find_learnings` surface it automatically for matching files, tables,
#|  feeds and processors. `kb_overview` and the daily report list **recurring causes nobody has written down yet**: those
#|  are the learnings to add next. Review the learnings monthly: retire stale ones and promote recurring ones into `context.md`.
#|
#|## 6. Configuration reference (`nifikb.toml`)
#|
#|| Section | Keys |
#||---|---|
#|| `[nifi]` | `home`, `flow_file` (optional), `extra_nar_dirs` |
#|| `[logs]` | `dirs` (default `<home>/logs`), `files` (patterns, default `nifi-app*.log*`, `nifi-bootstrap*.log*`), `keep_days` (14), `initial_tail_mb` (200), `enabled` |
#|| `[nifi_api]` | `url`, `username` + `password_env` / `password_file`, or `token_env` / `token_file`, or `client_cert` + `client_key`; `ca_cert` or `verify_ssl = false`; `timeout` |
#|| `[registry]` | `url` (…/nifi-registry-api), `username` + `password_env` / `password_file`, `ca_cert` |
#|| `[output]` | `dir` (generated KB, default `kb`) |
#|| `[knowledge]` | `dir` (team knowledge, default `knowledge`) |
#|| `[code]` | `repos` |
#|| top level (before any `[section]`) | `db_refresh_hours` (table schemas, default 24) |
#|| `[[databases]]` | `name`, `kind` (mariadb / mysql / postgres / sqlite), `host`, `port`, `database`, `user`, `password_env` / `password_file`, `include_tables`, `profile_tables`, `sample_rows`, `all_tables`, `match_jdbc` / `dbcp_services` (link to the flow's DBCP when host / db differ), `max_tables`, `schemas` |
#|| `[targets]` | `location_template` (`{table}`, `{table_lower}`, `{id}`), `hdfs_url` + `hdfs_user` or `kerberos = true` (+ `curl`), `hdfs_cli`, `s3_profile`, `s3_endpoint`, `s3_region`, `s3_cli`, `ca_cert`, `max_entries` (2000), `max_depth` (4), `max_download_mb` (200, hdfs CLI only), `timeout` |
#|| `[tickets]` | `kind` (`jira` / `servicenow`), `url`, `username` + `token_env` / `password_env` (or `*_file`; a token alone is sent as Bearer), `table` (ServiceNow, `incident`), `note_field` (`work_notes`), `ca_cert` |
#|| `[environments.<name>]` | `flow_file`, `db` (a `[[databases]]` name), for `compare --env <name>` |
#|| `[audit]` | `db`, `table`, overrides `file_column`, `status_column`, `time_column`, `error_column`, `rows_column`, `link_column` |
#|| `[report]` | `email_to`, `email_from`, `smtp_host`, `smtp_port`, `smtp_starttls`, `smtp_user` + `smtp_password_env` / `_file`, `webhook_url_env` / `webhook_url_file` |
#|| `[web]` | `host`, `port`, `user` + `password_env` / `password_file` |
#|| `[metadata]` | `db`, `target_db` (`"none"` when loads go to files), `tables` (patterns of config tables), `snapshot_max_rows`, `structure_max_rows`, `refresh_hours` (config rows, default 1); optional overrides `definition_table`, `definition_id`, `definition_keys`, `definition_target`, `definition_location`, `structure_table`, `structure_parent`, `structure_field`, `structure_type`, `structure_order`, `structure_length`, `structure_nullable`, `structure_path`; `[[metadata.relations]] child = "T.C" parent = "T.C"` |
#|
#|## 7. Maintenance
#|
#|- **Refresh:** a scheduled `ops\build.cmd` (Windows) or `ops/build.sh` (Linux cron), log in `ops/build.log`, or `build` by
#|  hand. The log index is also brought up to date on every `logs` / `investigate` call. `build --refresh-db` re-reads
#|  schemas and metadata now; `diagnose --live` reads config rows on demand.
#|- **Health:** `python -m nifikb doctor` (also an MCP tool).
#|- **Agent instructions:** edit `CLAUDE.md`, then run `ops\sync-agent-docs.cmd`. A test fails if the three copies differ.
#|- **Upgrading nifikb:** replace the `nifikb/` folder. Parser version changes are part of the build signature, so the
#|  next `build` re-parses everything by itself.
#|- **Tests:** `python -m unittest discover -s tests -v`. Fixtures are in `tests/fixtures_builder.py`: a nested flow;
#|  a company-style Java repo with a base class, constants, a DAO, a service interface, a test-only mock and poms;
#|  a custom NAR with generated `.class` files; SQLite metadata tables; and a lineage flow.
#|
#|## 8. Known limitations and assumptions
#|
#|- **Office schema not verified.** Real `OBJ_*` column names were never seen, so detection is heuristic. Check
#|  `kb/metadata.md` and override in `[metadata]`. Tables beyond the four named ones (the "and many more") are picked up by
#|  the `tables` patterns (`OBJ_%`, `%_CONFIG`, …). Add patterns if yours are named differently.
#|- **Java is parsed with regular expressions,** not a compiler. It handles common idioms: builders, constants across
#|  files, base classes, `AllowableValue`, attribute maps, `CoreAttributes`. Unusual code (properties built in loops,
#|  reflection, annotation processors) can be missed. The custom-code docs show exactly what was found.
#|- **Attributes named at runtime are not guessed.** A processor whose attribute names come from database columns is
#|  treated as an "unknown writer", so the lineage checks stay quiet downstream of it (no false alarms, but fewer
#|  findings). The same applies to scripts, InvokeHTTP, and ListenHTTP / Kafka headers.
#|- **Deployed-NAR strings are collected per jar.** Drift checks compare only names defined in the component's own module.
#|- **Spark:** `spark-submit` calls in the scripts ExecuteStreamCommand runs are detected and named (class, jar, name);
#|  the Spark jobs themselves are not analysed (by request, for now).
#|- **Provenance** is only as deep as NiFi keeps it (`nifi.provenance.repository.max.storage.time`, default 24 h) and needs
#|  a NiFi user with provenance policies. It was tested against a simulated API only.
#|- **Logs:** only WARN / ERROR / FATAL lines (and bootstrap lifecycle lines) are indexed; INFO / DEBUG is ignored by design.
#|  A processor that fails without logging and routes to an auto-terminated relationship is only visible via provenance.
#|- **Targets:** listings are capped (`max_entries`, `max_depth`); outputs named by the flow rather than after the input
#|  file are shown as "newest outputs". Only Parquet schemas are read (not ORC / Avro). With the `hdfs` CLI the whole file
#|  is copied to read its footer (WebHDFS reads only the tail).
#|- **Late files** need at least `--min-history` (5) successful loads of a feed in the window; irregular feeds are skipped.
#|  Whether the file reached the source server (SFTP / landing) is deliberately not checked.
#|- **Tickets:** facts are extracted with patterns (file names, known feed / table names, error lines, header lines); a
#|  vague ticket gives a vague investigation. Only CSV / JSON attachments up to 5 MB are used as samples.
#|- **Databases:** Oracle and SQL Server are not supported (drivers and dialect would need adding in `db.py`).
#|- **Sandbox state:** the local MariaDB is not a Windows service (start `C:\Program Files\MariaDB 13.0\bin\mariadbd.exe`
#|  by hand). The sample flow's Postgres (`localhost:5432/testDB`) is not installed.
#|
#|## 9. Open questions for the team
#|
#|1. Real `OBJ_*` / config table DDL and one example row per table: confirm the auto-detection, and list the other config tables.
#|2. The load-audit table (name, which status values mean success / failure): supported by `[audit]`, to be confirmed.
#|3. How the office reaches HDFS / S3 from the laptop or server (WebHDFS + Kerberos? an `aws` profile?), and the Jira /
#|   ServiceNow integration user (read + comment / work note).
#|4. A read-only MariaDB user for the config tables (to verify detection on the real schema), and a NiFi user with
#|   provenance policies for `[nifi_api]`.
#|5. Whether the security team approves sending the KB (configuration and masked config rows) to the AI provider.
#|6. Who owns `knowledge/context.md` and the monthly review of learnings.
#|
#|## 10. Troubleshooting
#|
#|| Symptom | Check |
#||---|---|
#|| Agent cannot see the `nifikb` tools | `doctor` → "Claude Code MCP" / "Gemini CLI MCP"; if `python` is not on PATH use `py` in `.mcp.json` and `.gemini/settings.json`; start the agent from this folder |
#|| "Knowledge base not built yet" | `python -m nifikb build` |
#|| No tables / metadata in answers | `doctor` → databases (driver, password env var, read-only user), `[metadata] db` name |
#|| `diagnose --file` finds nothing | `kb/metadata.md` → lookup keys; file-name patterns in `OBJ_DEFINITION` (`*`, `%`, `YYYYMMDD`, regex are understood); try `--feed` / `--table` or `search` |
#|| Custom processor "source code not found" | add the repo to `[code] repos`; the class must match the flow type (`com.x.Y`) |
#|| Answers based on old config rows | `diagnose … --live`, or `build --refresh-db` |
#|| Build slow on huge schemas | lower `sample_rows` / `profile_tables`; `max_tables` |
#|| `provenance` says HTTP 403 | the NiFi user needs the policies "query provenance" (global) and "view provenance" (on the process groups) |
#|| `provenance` finds no events for a file that did arrive | provenance retention (`nifi.provenance.repository.max.storage.time`) or the `filename` attribute was renamed upstream; try `--uuid` from `logs` |
#|| `logs` shows nothing | `doctor` → logs (folder, file patterns); a cluster needs every node's log folder in `[logs] dirs` |
#|| `target` says "no location" | the definition has no location column: set `[targets] location_template` or `[metadata] definition_location` |
#|| `target` on HDFS: HTTP 401 / 403 | Kerberos: `kinit` first and `kerberos = true`; simple auth: `hdfs_user` must be allowed to list the path |
#|| `ticket` finds no file / feed | the ticket text names neither; ask the reporter, or run `investigate` with the names by hand |
#|| `late` says nothing although a feed is late | fewer than 5 successful loads in the window, or no `[audit] time_column`; try `late --days 60 --min-history 3` |
#|
#|## 11. Extending
#|
#|- **New finding:** add it in `analyze.py` (`self._finding(severity, kind, comp, message)`), add a test, and add a line
#|  to the glossary in `CLAUDE.md`.
#|- **New DB kind:** extend `db.connect`, `list_tables` and `describe_table` (dialect-specific SQL), plus `doctor._databases`.
#|- **New MCP tool:** add it to `TOOLS` and `Server.call` in `mcp.py`, prefer reusing a CLI command, and document it in
#|  `CLAUDE.md`.
#|- Keep outputs compact. Agents read `kb/` through tools, so cap lists and link to details instead of dumping them.
#@@ FILE .mcp.json t 5c33adbdfb60eb30
#|{
#|  "mcpServers": {
#|    "nifikb": {
#|      "type": "stdio",
#|      "command": "python",
#|      "args": ["-m", "nifikb", "mcp"]
#|    }
#|  }
#|}
#@@ FILE .gitignore t 93dc33c8b3188a1a
#|__pycache__/
#|*.pyc
#|
#|# Generated on each machine by `python -m nifikb build` (contains flow configuration; rebuild instead of committing)
#|kb/
#|ops/build.log
#|
#|# Keep: knowledge/ (team context + learnings), nifikb.toml (no secrets - passwords come from environment variables)
#|dist/
#|ops/last-report.html
#@@ FILE nifikb/__init__.py t 9242d667b348dee4
#|"""NiFi knowledge base: turns a NiFi flow, custom code and DB schemas into LLM-friendly docs."""
#|__version__ = "0.5.0"
#@@ FILE nifikb/__main__.py t b7710ce17a291c3e
#|import sys
#|
#|from .cli import main
#|
#|sys.exit(main())
#@@ FILE nifikb/analyze.py t d70b490ae63e6410
#|"""Turn a parsed Flow + NAR catalog + code index into facts: resolved properties, external resources,
#|hardcoded values, lint findings, flow tags and the connection graph."""
#|import csv
#|import json
#|import re
#|from collections import defaultdict
#|from pathlib import Path
#|
#|from . import sqlparse
#|from .util import (EL_REF_RE, EL_VAR_RE, JDBC_RE, PARAM_RE, REDACTED, SECRET_NAME, UNIX_PATH_RE, URL_RE,
#|                   WIN_PATH_RE, clip, short)
#|
#|EL_FUNCS = {"now", "uuid", "UUID", "hostname", "ip", "nextInt", "random", "literal", "thread", "getStateValue", "anyAttribute",
#|            "allAttributes", "anyMatchingAttribute", "allMatchingAttributes", "anyDelineatedValue", "allDelineatedValues",
#|            "getUri", "math", "toRadians"}
#|CORE_ATTRS = {"filename", "path", "absolute.path", "uuid", "mime.type", "fileSize", "entryDate", "lineageStartDate"}
#|
#|# (resource kind, regex on "<raw name> <display name>")
#|NAME_RULES = [
#|    ("db_table", re.compile(r"(?i)table[ _-]?name|table-name|db-fetch-table|put-db-record-table|\btable\b(?!.*(?:cache|schema|columns|count))")),
#|    ("sql", re.compile(r"(?i)\bsql\b|query|statement|sql-select|sql-pre|sql-post|putsql")),
#|    ("s3_bucket", re.compile(r"(?i)\bbucket\b")),
#|    ("object_key", re.compile(r"(?i)object key|^key\b|prefix")),
#|    ("file_path", re.compile(r"(?i)director|path|file to fetch|folder|\bfile\b|filename|location")),
#|    ("host", re.compile(r"(?i)host|server|bootstrap|broker|endpoint|address")),
#|    ("port", re.compile(r"(?i)\bport\b|listening port")),
#|    ("topic", re.compile(r"(?i)topic|queue name|destination name|subject|channel")),
#|    ("command", re.compile(r"(?i)command|script file|script body|module directory|executable")),
#|    ("email", re.compile(r"(?i)^(to|from|cc|bcc)$|recipient|sender|email")),
#|]
#|SQL_NAME_EXCLUDE = re.compile(r"(?i)timeout|size|fetch|max|cache|type|columns|strategy|column|rows|batch|translate|normaliz|quote|output|format")
#|SQL_TABLE_EXCLUDE = re.compile(r"(?i)schema-cache|cache-size|column|strategy|translat|behavior|quot")
#|SCRIPT_EXT = re.compile(r"[^\s\"';|&]+\.(?:py|groovy|sh|bash|js|rb|jar|ps1|bat|cmd|sql|jython|clj|lua)\b", re.I)
#|
#|TAG_RULES = [
#|    ("api-in", re.compile(r"ListenHTTP|HandleHttpRequest|ListenTCP|ListenUDP|ListenSyslog|ListenWebSocket")),
#|    ("api-call", re.compile(r"InvokeHTTP|GetHTTP|PostHTTP|InvokeAWSGatewayApi|ConnectWebSocket")),
#|    ("s3", re.compile(r"S3")), ("azure", re.compile(r"Azure|ADLS")), ("gcs", re.compile(r"GCS|BigQuery|PubSub")),
#|    ("sftp/ftp", re.compile(r"SFTP|FTP")), ("local-file", re.compile(r"\b(GetFile|ListFile|FetchFile|PutFile|TailFile)\b")),
#|    ("hdfs", re.compile(r"HDFS")), ("kafka", re.compile(r"Kafka")), ("jms", re.compile(r"JMS|AMQP|MQTT")),
#|    ("db-write", re.compile(r"PutDatabaseRecord|PutSQL|ConvertJSONToSQL|PutMongo|PutElasticsearch|PutCassandra|PutHive")),
#|    ("db-read", re.compile(r"ExecuteSQL|QueryDatabaseTable|GenerateTableFetch|ListDatabaseTables|GetMongo|LookupRecord|DatabaseRecordLookup")),
#|    ("json", re.compile(r"(?i)json|jolt")), ("csv", re.compile(r"CSV")), ("xml", re.compile(r"XML|XPath|XQuery")),
#|    ("avro", re.compile(r"Avro")), ("parquet", re.compile(r"Parquet")),
#|    ("script", re.compile(r"ExecuteStreamCommand|ExecuteProcess|ExecuteScript|ExecuteGroovyScript|InvokeScripted|ExecutePython")),
#|    ("email", re.compile(r"PutEmail|ConsumeIMAP|ConsumePOP3")), ("archive/zip", re.compile(r"CompressContent|UnpackContent|MergeContent")),
#|    ("routing", re.compile(r"RouteOnAttribute|RouteOnContent|RouteText|QueryRecord|PartitionRecord")),
#|]
#|WRITES_ATTR_PROCS = ("UpdateAttribute", "EvaluateJsonPath", "EvaluateXPath", "EvaluateXQuery", "ExtractText", "ExtractGrok",
#|                     "GenerateFlowFile", "LookupAttribute")
#|# Properties whose literal value names an attribute the processor writes (ExecuteStreamCommand "Output Destination Attribute", ...)
#|ATTR_NAME_PROP = re.compile(r"(?i)(destination|output|result|target|response|put\s+cache\s+value\s+in).*attribute|attribute[\s._-]*name")
#|# Processors whose written attribute names cannot be known statically (scripts, HTTP / message headers)
#|UNKNOWN_WRITERS = {"ExecuteScript", "ExecuteGroovyScript", "InvokeScriptedProcessor", "ScriptedTransformRecord", "ExecuteClojure",
#|                   "InvokeHTTP", "HandleHttpRequest", "ListenHTTP", "GetHTTP", "ConsumeJMS", "ConsumeMQTT", "ConsumeAMQP", "ConsumeGCPubSub",
#|                   "ExtractEmailHeaders", "ExtractHL7Attributes", "ConsumeAzureEventHub", "GetSQS", "ConsumeKinesisStream"}
#|DYNAMIC_REL_PROCS = ("RouteOnAttribute", "RouteOnContent", "RouteText", "QueryRecord", "PartitionRecord", "RouteHL7")
#|
#|
#|def type_short(t):
#|    return (t or "").rsplit(".", 1)[-1]
#|
#|
#|class Analysis:
#|    def __init__(self, flow, catalog, code_index, config=None):
#|        self.flow, self.catalog, self.code, self.config = flow, catalog, code_index, config or {}
#|        self.props = defaultdict(list)       # component id -> [property facts]
#|        self.resources = []                  # {kind, value, component_id, source, detail}
#|        self.findings = []                   # {severity, kind, component_id, message, location}
#|        self.attrs_written = defaultdict(set)
#|        self.attrs_read = defaultdict(set)
#|        self.attr_reads = defaultdict(list)  # component id -> [(attribute, where, from a default value)]
#|        self.out_edges = defaultdict(list)   # id -> [(connection, dest_id)]
#|        self.in_edges = defaultdict(list)
#|        self.custom = {}                     # type -> {code: [...], nar: ..., used_by: [...]}
#|        self.scripts = {}                    # resolved script path -> {used_by, exists, index}
#|        self.field_checks = []               # PutDatabaseRecord record fields vs. table columns (filled by db step)
#|        self.jdbc = {}                       # service id -> parsed jdbc info
#|        self.service_users = {}              # service id -> [component ids referencing it]
#|        self.res_by_comp = defaultdict(list)  # component id -> [resources]
#|        self.children = defaultdict(list)    # group id -> child group ids
#|        self._memo = {}
#|
#|    # ---------------------------------------------------------------------------------------- driver
#|    def run(self):
#|        for gid, g in self.flow.groups.items():
#|            if g["parent_id"]:
#|                self.children[g["parent_id"]].append(gid)
#|        for c in self.flow.connections:
#|            self.out_edges[c["source_id"]].append((c, c["dest_id"]))
#|            self.in_edges[c["dest_id"]].append((c, c["source_id"]))
#|        for comp in list(self.flow.components.values()) + list(self.flow.services.values()):
#|            self._analyze_properties(comp)
#|        for comp in self.flow.components.values():
#|            if comp["kind"] == "PROCESSOR":
#|                self._lint_processor(comp)
#|        self._lint_services()
#|        self._lint_secret_config()
#|        self._custom_components()
#|        self._attribute_lineage()
#|        self._parse_jdbc()
#|        return self
#|
#|    # ------------------------------------------------------------------------------------ properties
#|    def ext(self, comp):
#|        """Extension info for a component: the NAR manifest, or - for custom NARs built without docs - what the Java
#|        source says (property display names, defaults, sensitivity, services, relationships, attributes)."""
#|        t = comp.get("type")
#|        if not t:
#|            return None
#|        e = self.catalog.get(t)
#|        if e and e.get("has_manifest"):
#|            return e
#|        code = self.code.by_fqcn.get(t)
#|        if not code:
#|            return e
#|        key = ("code_ext", t)
#|        if key not in self._memo:
#|            c = code[0]["component"]
#|            self._memo[key] = {
#|                "type": t, "kind": c["kind"], "description": c.get("description") or "", "tags": c.get("tags") or [],
#|                "properties": {p["name"]: {"displayName": p.get("displayName") or p["name"], "description": p.get("description") or "",
#|                                           "default": p.get("default"), "required": p.get("required"), "sensitive": p.get("sensitive"),
#|                                           "el_scope": "FLOWFILE_ATTRIBUTES" if p.get("el") else None, "service_api": p.get("service"),
#|                                           "allowable": {v: v for v in p.get("allowable") or []}}
#|                               for p in c.get("properties") or []},
#|                "relationships": [{"name": r["name"], "description": r.get("description") or "", "auto_terminated": False}
#|                                  for r in c.get("relationships") or []],
#|                "dynamic_relationships": False, "dynamic_properties": bool(c.get("dynamic_properties")),
#|                "reads_attributes": c.get("reads_attributes") or [], "writes_attributes": c.get("writes_attributes") or [],
#|                "input_requirement": c.get("input_requirement"), "has_manifest": False, "from_code": True,
#|                "nar": (e or {}).get("nar"), "nar_group": (e or {}).get("nar_group"),
#|            }
#|        return self._memo[key]
#|
#|    def variables(self, group_id):
#|        out = {}
#|        for gid in reversed(self.flow.group_chain(group_id)):
#|            out.update(self.flow.groups[gid].get("variables") or {})
#|        return out
#|
#|    def params(self, group_id):
#|        g = self.flow.groups.get(group_id) or {}
#|        out, seen = {}, set()
#|
#|        def walk(ctx_name):
#|            if not ctx_name or ctx_name in seen or ctx_name not in self.flow.param_contexts:
#|                return
#|            seen.add(ctx_name)
#|            ctx = self.flow.param_contexts[ctx_name]
#|            for k, v in ctx["params"].items():
#|                out.setdefault(k, v)
#|            for inherited in ctx["inherits"]:
#|                walk(inherited)
#|
#|        walk(g.get("parameter_context"))
#|        return out
#|
#|    def resolve(self, value, group_id):
#|        """Substitute #{params} and ${variables}; runtime attributes stay as ${...}."""
#|        params, variables = self.params(group_id), self.variables(group_id)
#|
#|        def p(m):
#|            name = (m.group(1) or m.group(2)).strip()
#|            if name not in params:
#|                return m.group(0)
#|            v = params[name]
#|            if v["sensitive"]:
#|                return "<sensitive>"
#|            if SECRET_NAME.search(name):
#|                return REDACTED
#|            return v["value"] if v["value"] is not None else m.group(0)
#|
#|        def var(m):
#|            if m.group(1) not in variables:
#|                return m.group(0)
#|            return REDACTED if SECRET_NAME.search(m.group(1)) else variables[m.group(1)]
#|
#|        out = PARAM_RE.sub(p, value)
#|        out = EL_VAR_RE.sub(var, out)
#|        return out
#|
#|    def _analyze_properties(self, comp):
#|        ext = self.ext(comp)
#|        descs = (ext or {}).get("properties", {})
#|        gid = comp["group_id"]
#|        variables = self.variables(gid)
#|        tshort = type_short(comp["type"])
#|        for name, value in comp["properties"].items():
#|            if value is None:
#|                continue
#|            d = descs.get(name)
#|            display = d["displayName"] if d else name
#|            dynamic = bool(ext and ext.get("has_manifest") and d is None)
#|            fact = {"name": name, "display": display, "value": value, "resolved": value, "source": "literal",
#|                    "default": False, "dynamic": dynamic, "service": None, "kinds": []}
#|            if value.startswith("enc{") or (d and d["sensitive"]):
#|                fact.update(value="<encrypted>" if value.startswith("enc{") else REDACTED, resolved=REDACTED, source="sensitive")
#|                self.props[comp["id"]].append(fact)
#|                continue
#|            service_id = self.flow.resolve_id(value)
#|            if (d and d.get("service_api")) or service_id in self.flow.services:
#|                svc = self.flow.services.get(service_id)
#|                fact.update(source="service", service=service_id, resolved=svc["name"] if svc else f"<missing service {value}>")
#|                if not svc and not PARAM_RE.search(value):
#|                    self._finding("error", "missing-service", comp, f"Property '{display}' points to controller service {value} which is not in the flow")
#|                self.props[comp["id"]].append(fact)
#|                continue
#|            if d and d.get("default") is not None and d["default"] == value:
#|                fact["default"] = True
#|            if d and d.get("allowable") and value in d["allowable"] and d["allowable"][value] not in (None, value):
#|                fact["resolved"] = f"{value} ({d['allowable'][value]})"
#|            has_param, has_el = bool(PARAM_RE.search(value)), "${" in value
#|            if has_param or has_el:
#|                fact["resolved"] = self.resolve(value, gid)
#|                fact["source"] = "parameter" if has_param and not has_el else "expression" if has_el and not has_param else "parameter+expression"
#|                refs = {m.group(1) for m in EL_REF_RE.finditer(value)}
#|                guarded = set(re.findall(r"\$\{\s*([\w.\-]+)\s*:\s*(?:isEmpty|isNull|notNull|replaceNull|replaceEmpty)\b", value))
#|                for ref in refs:
#|                    if ref not in variables and ref not in EL_FUNCS:
#|                        self.attrs_read[comp["id"]].add(ref)
#|                        self.attr_reads[comp["id"]].append((ref, display, fact["default"] or ref in guarded))
#|                if refs and all(r in variables for r in refs) and not has_param:
#|                    fact["source"] = "variable"
#|            elif SECRET_NAME.search(f"{name} {display}") and len(value) > 1 and not (d and d["allowable"]) and value.lower() not in ("true", "false", "none"):
#|                fact.update(value=REDACTED, resolved=REDACTED)
#|                self._finding("high", "plaintext-secret", comp, f"Property '{display}' holds a plain-text secret (not a sensitive property or parameter)")
#|            if dynamic and tshort in WRITES_ATTR_PROCS:
#|                self.attrs_written[comp["id"]].add(name)
#|            self._extract_resources(comp, fact)
#|            self.props[comp["id"]].append(fact)
#|        cid = comp["id"]
#|        if ext:
#|            for a in ext.get("writes_attributes") or []:
#|                self.attrs_written[cid].add(a)
#|        code = self.code.by_fqcn.get(comp.get("type") or "")
#|        if code:  # what the Java code really does, beyond the documented @WritesAttribute / @ReadsAttribute
#|            c = code[0]["component"]
#|            self.attrs_written[cid] |= set(c.get("writes_attributes") or [])
#|            for a in c.get("reads_attributes") or []:
#|                self.attrs_read[cid].add(a)
#|                self.attr_reads[cid].append((a, f"code {(c.get('reads_at') or {}).get(a, '')}".strip(), False))
#|        for f in self.props[cid]:
#|            if ATTR_NAME_PROP.search(f"{f['name']} {f['display']}") and f["source"] == "literal" and re.fullmatch(r"[\w.\-]+", f["resolved"] or ""):
#|                self.attrs_written[cid].add(f["resolved"])
#|        if tshort == "UpdateAttribute" and comp.get("annotation_data"):  # Advanced-UI rules
#|            self.attrs_written[cid] |= set(re.findall(r"<attribute>\s*([^<]+?)\s*</attribute>", comp["annotation_data"]))
#|            for m in EL_REF_RE.finditer(comp["annotation_data"]):
#|                if m.group(1) not in variables and m.group(1) not in EL_FUNCS:
#|                    self.attrs_read[cid].add(m.group(1))
#|                    self.attr_reads[cid].append((m.group(1), "advanced rules", False))
#|
#|    def _extract_resources(self, comp, fact):
#|        label = f"{fact['name']} {fact['display']}"
#|        raw, resolved = fact["value"], fact["resolved"]
#|        literal_part = PARAM_RE.sub("", EL_REF_RE.sub("", raw))
#|        is_hardcoded = fact["source"] in ("literal", "variable") or bool(
#|            re.search(r"[A-Za-z]:\\|/[\w.-]+/|://|\.(?:com|net|org|csv|json|xml|py|sql)\b", literal_part))
#|        kinds = []
#|
#|        def add(kind, value, detail=None):
#|            value = clip(value, 300)
#|            kinds.append(kind)
#|            res = {"kind": kind, "value": value, "component_id": comp["id"], "property": fact["display"],
#|                   "source": fact["source"], "hardcoded": is_hardcoded and fact["source"] != "sensitive",
#|                   "raw": clip(raw, 300), "detail": detail}
#|            self.resources.append(res)
#|            self.res_by_comp[comp["id"]].append(res)
#|
#|        for m in JDBC_RE.finditer(resolved):
#|            add("jdbc", m.group(0))
#|        for m in URL_RE.finditer(resolved):
#|            add("url", m.group(0))
#|        for kind, rx in NAME_RULES:
#|            if not rx.search(label) or fact["default"]:
#|                continue
#|            if kind == "sql":
#|                if SQL_NAME_EXCLUDE.search(label) or not sqlparse.looks_like_sql(resolved):
#|                    continue
#|                add("sql", resolved, detail=json.dumps(sqlparse.tables(resolved)))
#|                for t in sqlparse.tables(resolved):
#|                    add("db_table", t, detail="from SQL")
#|            elif kind == "db_table":
#|                if SQL_TABLE_EXCLUDE.search(label) or sqlparse.looks_like_sql(resolved) or len(resolved) > 200                         or resolved.lower() in ("true", "false") or resolved.strip().isdigit():
#|                    continue
#|                for t in re.split(r"\s*,\s*", resolved):
#|                    if t and re.fullmatch(r"[\w$#{}.\-`\"\[\]<> ]+", t):
#|                        add("db_table", t.strip("`\"[]").lower())
#|            elif kind == "file_path":
#|                if WIN_PATH_RE.search(resolved) or UNIX_PATH_RE.search(resolved) or re.search(r"[\\/]", literal_part) or re.match(r"^\.{0,2}/", resolved):
#|                    add("file_path", resolved)
#|            elif kind == "port":
#|                if resolved.strip().isdigit():
#|                    add("port", resolved.strip())
#|            elif kind == "host":
#|                if re.fullmatch(r"[\w.\-:,${}#' ]+", resolved) and not resolved.strip().isdigit() and resolved.lower() not in ("true", "false"):
#|                    add("host", resolved)
#|            elif kind == "command":
#|                add("command", resolved)
#|                for s in SCRIPT_EXT.findall(resolved):
#|                    add("script", s)
#|            elif kind == "s3_bucket" and "S3" in comp["type"] or kind in ("topic", "email") \
#|                    or kind == "object_key" and "S3" in comp["type"] and fact["source"] != "expression":
#|                add(kind, resolved)
#|        fact["kinds"] = sorted(set(kinds))
#|
#|    # ------------------------------------------------------------------------------------------ lint
#|    def _finding(self, severity, kind, comp, message, location=None):
#|        self.findings.append({"severity": severity, "kind": kind, "component_id": comp["id"] if comp else None,
#|                              "message": message, "location": location})
#|
#|    def relationships(self, comp):
#|        ext = self.ext(comp)
#|        if not ext or not ext.get("has_manifest"):
#|            return None
#|        rels = {r["name"] for r in ext["relationships"]}
#|        if ext.get("dynamic_relationships") or type_short(comp["type"]) in DYNAMIC_REL_PROCS:
#|            rels |= {f["name"] for f in self.props[comp["id"]] if f["dynamic"]}
#|        return rels
#|
#|    def _lint_processor(self, comp):
#|        rels = self.relationships(comp)
#|        connected = {r for c, _ in self.out_edges[comp["id"]] for r in c["relationships"]}
#|        if rels is not None:
#|            loose = sorted(rels - connected - set(comp["auto_terminated"]))
#|            if loose and comp["state"] != "DISABLED":
#|                self._finding("error", "unhandled-relationship", comp,
#|                              f"Relationship(s) {', '.join(loose)} neither connected nor auto-terminated -> processor is INVALID and will not run")
#|        dropped = sorted(set(comp["auto_terminated"]) & {"failure", "retry", "invalid", "not.found", "permission.denied", "comms.failure",
#|                                                         "unmatched", "no retry", "timeout", "nonzero status"})
#|        if dropped and comp["state"] != "DISABLED":
#|            self._finding("warn", "dropped-errors", comp, f"{', '.join(dropped)} auto-terminated: failed FlowFiles are silently dropped (no retry/alert)")
#|        for c, dst in self.out_edges[comp["id"]]:
#|            target = self.flow.components.get(dst)
#|            if target and target.get("state") == "DISABLED" and comp["state"] != "DISABLED":
#|                self._finding("info", "disabled-downstream", comp, f"Routes '{','.join(c['relationships'])}' to DISABLED processor '{target['name']}' ({short(dst)}); data will queue up")
#|        if comp["type"] and not self.catalog.get(comp["type"]) and self.catalog.types:
#|            if (comp["bundle"].get("group") or "").startswith("org.apache.nifi"):
#|                self._finding("warn", "unknown-type", comp, f"Type {comp['type']} not found in any NAR (missing bundle / version mismatch?)")
#|        ext = self.ext(comp)
#|        if ext and ext.get("input_requirement") == "INPUT_REQUIRED" and not self.in_edges[comp["id"]] and comp["state"] != "DISABLED":
#|            self._finding("warn", "no-input", comp, "Processor requires input but has no incoming connection")
#|
#|    def _lint_services(self):
#|        used = defaultdict(list)
#|        for cid, facts in self.props.items():
#|            for f in facts:
#|                if f["service"]:
#|                    used[f["service"]].append(cid)
#|        self.service_users = used
#|        for sid, svc in self.flow.services.items():
#|            users = [self._comp(u) for u in used.get(sid, [])]
#|            active_users = [u for u in users if u and u.get("state") in ("RUNNING", "ENABLED")]
#|            if svc.get("state") == "DISABLED" and active_users:
#|                self._finding("error", "disabled-service", svc, f"Service is DISABLED but used by running component(s): {', '.join(u['name'] for u in active_users)}")
#|
#|    def _lint_secret_config(self):
#|        for name, ctx in self.flow.param_contexts.items():
#|            for pname, p in ctx["params"].items():
#|                if SECRET_NAME.search(pname) and not p["sensitive"] and p.get("value"):
#|                    self.findings.append({"severity": "high", "kind": "plaintext-secret", "component_id": None, "location": f"parameter context {name}",
#|                                          "message": f"parameter '{pname}' in context '{name}' looks like a secret but is not marked sensitive"})
#|        for gid, g in self.flow.groups.items():
#|            for vname, v in (g.get("variables") or {}).items():
#|                if SECRET_NAME.search(vname) and v:
#|                    self.findings.append({"severity": "high", "kind": "plaintext-secret", "component_id": None, "location": f"variables of {g['path']}",
#|                                          "message": f"variable '{vname}' in '{g['path']}' holds a plain-text secret"})
#|
#|    def _comp(self, cid):
#|        return self.flow.components.get(cid) or self.flow.services.get(cid)
#|
#|    # --------------------------------------------------------------------------- custom code & scripts
#|    def is_custom(self, comp):
#|        group = (comp.get("bundle") or {}).get("group") or ""
#|        t = comp.get("type") or ""
#|        if comp["kind"] not in ("PROCESSOR", "CONTROLLER_SERVICE") or not t:
#|            return False
#|        return (group and not group.startswith("org.apache.nifi")) or (not group and not t.startswith("org.apache.nifi"))
#|
#|    def _custom_components(self):
#|        deployed = defaultdict(set)  # NAR artifact -> versions present in lib / extra dirs
#|        for n in self.catalog.nars:
#|            deployed[n.get("artifact")].add(n.get("version"))
#|        for comp in list(self.flow.components.values()) + list(self.flow.services.values()):
#|            if self.is_custom(comp) or comp["type"] in self.code.by_fqcn:
#|                cat = self.catalog.get(comp["type"])
#|                entry = self.custom.setdefault(comp["type"], {"type": comp["type"], "used_by": [], "code": self.code.by_fqcn.get(comp["type"], []),
#|                                                              "nar": (cat or {}).get("nar"), "bundle": comp["bundle"], "bundle_versions": []})
#|                entry["used_by"].append(comp["id"])
#|                bundle = comp["bundle"] or {}
#|                if bundle.get("version") not in entry["bundle_versions"]:
#|                    entry["bundle_versions"].append(bundle.get("version"))
#|                first = comp["id"] == entry["used_by"][0]
#|                if not first:
#|                    continue
#|                if not entry["code"]:
#|                    self._finding("warn", "custom-code-missing", comp,
#|                                  f"Custom type {comp['type']} ({bundle.get('artifact')}) - source code not found in configured repos"
#|                                  + ("" if entry["nar"] else "; NAR not found either"))
#|                elif not cat and self.catalog.types:
#|                    self._finding("error", "custom-nar-missing", comp,
#|                                  f"Custom type {comp['type']} has source code but no NAR in lib / extra_nar_dirs provides it "
#|                                  f"(bundle {bundle.get('artifact')} {bundle.get('version')}) -> NiFi shows it as a ghost processor")
#|                if cat and bundle.get("artifact") in deployed and bundle.get("version") not in deployed[bundle["artifact"]]:
#|                    self._finding("warn", "bundle-version", comp,
#|                                  f"Flow uses {bundle['artifact']} {bundle.get('version')} but lib has {', '.join(sorted(v or '?' for v in deployed[bundle['artifact']]))}")
#|                src = (entry["code"][0]["component"] if entry["code"] else {})
#|                if src and not src.get("registered") and any(Path(p).name.startswith("org.apache.nifi.") for p in self._service_files(src)):
#|                    self._finding("warn", "custom-not-registered", comp,
#|                                  f"{comp['type']} is not listed in its module's META-INF/services file -> NiFi will not load it from a new build")
#|                dep = (cat or {}).get("deployed")
#|                strings = self.catalog.jar_strings(dep) if dep and src else set()
#|                if strings:
#|                    mod = (src.get("module") or {}).get("dir") or str(Path(entry["code"][0]["path"]).parent)
#|                    own_file = Path(entry["code"][0]["path"]).name
#|                    missing = [f"property '{p['name']}'" for p in src.get("properties") or []
#|                               if p.get("name") and str(p.get("path", "")).startswith(mod) and p["name"] not in strings]
#|                    missing += [f"relationship '{r['name']}'" for r in src.get("relationships") or []
#|                                if r.get("name") and str(r.get("path", "")).startswith(mod) and r["name"] not in strings]
#|                    missing += [f"attribute '{a}'" for a, at in (src.get("writes_at") or {}).items()
#|                                if at.split(":")[0] == own_file and a not in strings]
#|                    entry["drift"] = missing
#|                    if missing:
#|                        self._finding("warn", "custom-source-drift", comp,
#|                                      f"repo source of {type_short(comp['type'])} has {', '.join(missing[:6])}"
#|                                      + (f" (+{len(missing) - 6} more)" if len(missing) > 6 else "")
#|                                      + f" that the deployed NAR ({Path(dep['jar']).name}) does not contain - the running build is not this source")
#|            if comp["kind"] == "PROCESSOR":
#|                self._link_scripts(comp)
#|
#|    def _service_files(self, src):
#|        """META-INF/services files in the component's Maven module."""
#|        mod = (src.get("module") or {}).get("dir")
#|        if not mod:
#|            return []
#|        return [p for p, info in self.code.files.items() if info.get("lang") == "services" and p.startswith(mod)]
#|
#|    # ------------------------------------------------------------------------------------ attribute lineage
#|    def unknown_writer(self, comp):
#|        """True when the attributes this component may add cannot be known statically."""
#|        kind, tshort = comp["kind"], type_short(comp.get("type") or "")
#|        if kind == "REMOTE_OUTPUT_PORT" or (kind == "INPUT_PORT" and comp["group_id"] == self.flow.root_id):
#|            return True
#|        if kind != "PROCESSOR":
#|            return False
#|        if tshort in UNKNOWN_WRITERS:
#|            return True
#|        if any(re.search(r"(?i)header.*attribute|attributes?.*header", f"{f['name']} {f['display']}") and f["resolved"]
#|               for f in self.props[comp["id"]]):
#|            return True
#|        if tshort == "UpdateAttribute" and not any(f["dynamic"] for f in self.props[comp["id"]]) and not comp.get("annotation_data"):
#|            return not self.catalog.get(comp["type"])  # rules not visible and no manifest to tell dynamic properties apart
#|        code = self.code.by_fqcn.get(comp.get("type") or "")
#|        if code:
#|            return bool(code[0]["component"].get("dynamic_writes"))
#|        if self.is_custom(comp):
#|            return True  # custom without source: documented attributes only
#|        return not self.catalog.get(comp["type"])
#|
#|    def _attribute_lineage(self):
#|        """Forward data-flow over the graph: which attributes can have been set before each component, and whether an
#|        unknown writer is upstream. A property reading ${x} with x never set upstream is a classic metadata bug."""
#|        nodes = [c for c in self.flow.components.values()]
#|        written = {c["id"]: set(self.attrs_written[c["id"]]) for c in nodes}
#|        unknown = {c["id"]: self.unknown_writer(c) for c in nodes}
#|        avail = {c["id"]: set() for c in nodes}
#|        unk_in = {c["id"]: False for c in nodes}
#|        work = list(avail)
#|        queued = set(work)
#|        while work:
#|            cid = work.pop()
#|            queued.discard(cid)
#|            out_set = avail[cid] | written.get(cid, set())
#|            out_unk = unk_in[cid] or unknown.get(cid, False)
#|            for _, dst in self.out_edges[cid]:
#|                if dst not in avail:
#|                    continue
#|                if not out_set <= avail[dst] or (out_unk and not unk_in[dst]):
#|                    avail[dst] |= out_set
#|                    unk_in[dst] = unk_in[dst] or out_unk
#|                    if dst not in queued:
#|                        queued.add(dst)
#|                        work.append(dst)
#|        self.attrs_available, self.unknown_upstream = avail, unk_in
#|        services_reads = self._service_reads()
#|        for c in nodes:
#|            if c["kind"] != "PROCESSOR" or c.get("state") == "DISABLED":
#|                continue
#|            reads = [(a, where) for a, where, is_default in self.attr_reads[c["id"]] if not is_default]
#|            reads += services_reads.get(c["id"], [])
#|            if not self.in_edges[c["id"]]:
#|                continue  # source processor: its ${attr} references cannot come from FlowFiles
#|            have = avail[c["id"]]
#|            missing = {}
#|            for a, where in reads:
#|                if a in CORE_ATTRS or a in have or any(a.startswith(h + ".") for h in have):
#|                    continue
#|                missing.setdefault(a, where)
#|            for a, where in sorted(missing.items()):
#|                near = self._near(a, have)
#|                if near:
#|                    self._finding("warn", "attribute-misnamed", c,
#|                                  f"reads ${{{a}}} ({where}) but upstream only sets '{near}' - likely a naming mismatch")
#|                elif not unk_in[c["id"]]:
#|                    self._finding("warn", "attribute-unset", c,
#|                                  f"reads ${{{a}}} ({where}) but no upstream processor sets it - the expression evaluates to empty")
#|
#|    def _service_reads(self):
#|        """Attributes read by controller services, charged to the processors using them (e.g. reader 'Schema Name' ${schema.name})."""
#|        out = defaultdict(list)
#|        for sid, svc in self.flow.services.items():
#|            reads = [(a, f"service {svc['name']}: {where}") for a, where, is_default in self.attr_reads[sid] if not is_default]
#|            props = {f["name"]: f["resolved"] for f in self.props[sid]}
#|            if props.get("schema-access-strategy") == "schema-name" and not any(a == "schema.name" for a, _ in reads):
#|                reads.append(("schema.name", f"service {svc['name']}: Schema Name (default)"))
#|            for user in self.service_users.get(sid, []):
#|                out[user] += reads
#|        return out
#|
#|    @staticmethod
#|    def _near(name, candidates):
#|        squash = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
#|        for c in candidates:
#|            if squash(c) == squash(name):
#|                return c
#|        import difflib
#|        close = difflib.get_close_matches(name, list(candidates), n=1, cutoff=0.85)
#|        return close[0] if close else None
#|
#|    def _link_scripts(self, comp):
#|        for r in [r for r in self.res_by_comp[comp["id"]] if r["kind"] == "script"]:
#|            path = r["value"].strip("\"'")
#|            p = Path(path)
#|            entry = self.scripts.setdefault(path, {"path": path, "used_by": [], "exists": p.is_file(), "index": None})
#|            entry["used_by"].append(comp["id"])
#|            if not entry["exists"]:
#|                matches = self.code.by_basename.get(p.name.lower(), [])
#|                if matches:
#|                    entry["repo_match"] = matches[0]
#|
#|    # ------------------------------------------------------------------------------------------ jdbc
#|    def _parse_jdbc(self):
#|        for sid, svc in self.flow.services.items():
#|            for f in self.props[sid]:
#|                m = re.match(r"jdbc:(\w+)(?::\w+)*://(?:[^@/]*@)?([^:/;?,]+)(?::(\d+))?(?:/([^;?]*))?", f["resolved"] or "", re.I)
#|                if m:
#|                    self.jdbc[sid] = {"vendor": m.group(1).lower(), "host": m.group(2).lower(), "port": m.group(3),
#|                                      "database": (m.group(4) or "").split("/")[0], "url": f["resolved"],
#|                                      "user": next((p["resolved"] for p in self.props[sid] if re.search(r"(?i)user", p["display"])), None)}
#|
#|    def db_service_of(self, comp):
#|        for f in self.props[comp["id"]]:
#|            if f["service"] and f["service"] in self.jdbc:
#|                return f["service"]
#|        return None
#|
#|    def tables_by_service(self):
#|        """{service id or None: {table: [component ids]}} for every table the flow touches."""
#|        if "tables" in self._memo:
#|            return self._memo["tables"]
#|        out = self._memo["tables"] = defaultdict(lambda: defaultdict(list))
#|        for r in self.resources:
#|            if r["kind"] == "db_table":
#|                comp = self.flow.components.get(r["component_id"])
#|                sid = self.db_service_of(comp) if comp else None
#|                out[sid][r["value"]].append(r["component_id"])
#|        return out
#|
#|    def record_fields(self, comp):
#|        """Field names a PutDatabaseRecord-style processor will send (best effort) + where they came from."""
#|        reader = next((self.flow.services.get(f["service"]) for f in self.props[comp["id"]]
#|                       if f["service"] and re.search(r"(?i)reader", f["display"] + f["name"])), None)
#|        if not reader:
#|            return None, None
#|        rp = {f["name"]: f["resolved"] for f in self.props[reader["id"]]}
#|        strategy = rp.get("schema-access-strategy", "")
#|        text = rp.get("schema-text", "")
#|        if strategy == "schema-text-property" and text and "${" not in text:
#|            try:
#|                return [f["name"] for f in json.loads(text).get("fields", [])], f"schema text of {reader['name']}"
#|            except ValueError:
#|                return None, None
#|        if strategy == "csv-header-derived":
#|            for src in self._upstream_files(comp["id"]):
#|                try:
#|                    with open(src, newline="", encoding="utf-8-sig") as fh:
#|                        header = next(csv.reader(fh, delimiter=rp.get("Value Separator", ",")[:1] or ","))
#|                    return [h.strip() for h in header], f"CSV header of {src}"
#|                except (OSError, StopIteration, UnicodeDecodeError):
#|                    continue
#|        return None, None
#|
#|    def _upstream_files(self, cid, depth=0, seen=None):
#|        seen = seen or set()
#|        if depth > 6 or cid in seen:
#|            return []
#|        seen.add(cid)
#|        out = []
#|        for _, src in self.in_edges[cid]:
#|            for r in self.res_by_comp[src]:
#|                if r["kind"] == "file_path" and Path(r["value"]).is_file():
#|                    out.append(r["value"])
#|            out.extend(self._upstream_files(src, depth + 1, seen))
#|        return out
#|
#|    # ----------------------------------------------------------------------------------------- tags
#|    def group_tags(self, group_id, recursive=True):
#|        if "own_tags" not in self._memo:
#|            own = self._memo["own_tags"] = defaultdict(set)
#|            for comp in list(self.flow.components.values()) + list(self.flow.services.values()):
#|                if comp["type"]:
#|                    for tag, rx in TAG_RULES:
#|                        if rx.search(type_short(comp["type"])):
#|                            own[comp["group_id"]].add(tag)
#|                    if self.is_custom(comp):
#|                        own[comp["group_id"]].add("custom")
#|        own = self._memo["own_tags"]
#|        gids = {group_id} | (self.descendants(group_id) if recursive else set())
#|        return sorted(set().union(*(own[g] for g in gids)))
#|
#|    def descendants(self, group_id):
#|        out, stack = set(), [group_id]
#|        while stack:
#|            for child in self.children[stack.pop()]:
#|                if child not in out:
#|                    out.add(child)
#|                    stack.append(child)
#|        return out
#|
#|    def entry_points(self, group_id=None):
#|        """Where data enters: processors without incoming connections, input ports, remote output ports.
#|        With group_id, the group's own input ports count too (they are fed from the parent group)."""
#|        out = []
#|        for comp in self.flow.components.values():
#|            if group_id and comp["group_id"] != group_id:
#|                continue
#|            if group_id and comp["kind"] == "INPUT_PORT":
#|                out.append(comp)
#|                continue
#|            incoming = [s for _, s in self.in_edges[comp["id"]] if s != comp["id"]]
#|            if not incoming and comp["kind"] in ("PROCESSOR", "INPUT_PORT", "REMOTE_OUTPUT_PORT"):
#|                out.append(comp)
#|        return sorted(out, key=lambda c: (c["kind"] != "PROCESSOR", c["name"]))
#|
#|    def key_facts(self, comp, limit=150):
#|        """One-line summary of what a component touches (tables, buckets, urls, paths, commands)."""
#|        bits = []
#|        order = ["db_table", "s3_bucket", "object_key", "url", "jdbc", "host", "port", "topic", "file_path", "script", "command", "email"]
#|        rs = self.res_by_comp[comp["id"]]
#|        for kind in order:
#|            vals = []
#|            for r in rs:
#|                if r["kind"] == kind and r["value"] not in vals and not (kind == "command" and any(x["kind"] == "script" for x in rs)):
#|                    vals.append(r["value"])
#|            if vals:
#|                bits.append(f"{kind.replace('db_', '').replace('s3_', '')}={'; '.join(vals)}")
#|        for f in self.props[comp["id"]]:
#|            if re.search(r"(?i)statement[ -]type|http method|^method$|completion strategy|conflict", f["display"] + " " + f["name"]) and not f["default"]:
#|                bits.append(f"{f['display']}={f['resolved']}")
#|            elif f["service"] and re.search(r"(?i)dbcp|connection pool|database", f["display"]) and f["resolved"]:
#|                bits.append(f"db={f['resolved']}")
#|        if comp["kind"] == "PROCESSOR" and comp["scheduling_strategy"] == "CRON_DRIVEN":
#|            bits.append(f"cron='{comp['scheduling_period']}'")
#|        elif comp["kind"] == "PROCESSOR" and not self.in_edges[comp["id"]] and comp["scheduling_period"] not in (None, "0 sec"):
#|            bits.append(f"every {comp['scheduling_period']}")
#|        return clip(", ".join(bits), limit)
#@@ FILE nifikb/audit.py t 3128c68c96f0d885
#|"""Load-audit table: the platform's own record of each file load (status, error, rows, time) - usually the fastest route
#|to "what happened to file X". Configured in [audit]; columns are auto-detected and can be overridden."""
#|import re
#|
#|from . import db as dbmod
#|
#|FILE_COL = re.compile(r"(?i)file_?(name|nm)?$|^file|src_?file|source_?file|object_?name|obj_?name")
#|STATUS_COL = re.compile(r"(?i)(^|_)(status|state|result|outcome|load_?status|job_?status)(_?(cd|code|desc))?$")
#|TIME_COL = re.compile(r"(?i)(^|_)(ts|timestamp|time|date|dt|dttm|created|updated|load_?ts|start_?ts|end_?ts|insert_?ts|run_?ts)"
#|                      r"(_?(on|at|ts|dt|time))?$")
#|ERROR_COL = re.compile(r"(?i)err|message|msg|reason|remark|comment|exception")
#|ROWS_COL = re.compile(r"(?i)(row|record|rec)_?(count|cnt|num)|(count|cnt)$|rows")
#|LINK_COL = re.compile(r"(?i)^(obj|object|def|definition|feed)_?id$")
#|TABLE_NAME = re.compile(r"(?i)audit|load_?log|file_?log|process_?log|job_?log|file_?status|ingest(ion)?_?log|load_?hist|run_?log")
#|FAIL_WORDS = re.compile(r"(?i)fail|error|reject|abort|invalid|exception|^e$|^f$|^x$")
#|IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")
#|
#|
#|def settings(cfg):
#|    a = cfg.get("audit")
#|    if not a:
#|        return None
#|    a = dict(a)
#|    dbs = cfg.get("databases", [])
#|    a.setdefault("db", (cfg.get("metadata") or {}).get("db") or (dbs[0]["name"] if dbs else None))
#|    if not any(d["name"] == a["db"] for d in dbs):
#|        raise ValueError(f"[audit] db = {a['db']!r} is not a [[databases]] name")
#|    for k in ("table", "file_column", "status_column", "time_column", "error_column", "rows_column", "link_column"):
#|        if a.get(k) and not IDENT.match(a[k]):
#|            raise ValueError(f"[audit] {k} = {a[k]!r} is not a plain table / column name")
#|    return a
#|
#|
#|def patterns(a):
#|    """Include patterns so the audit table gets documented (and its columns known) by the normal DB step."""
#|    return [a["table"].lower()] if a.get("table") else ["*audit*", "*load_log*", "*file_log*", "*process_log*", "*job_log*",
#|                                                          "*file_status*", "*ingest*log*", "*load_hist*", "*run_log*"]
#|
#|
#|def detect(a, db_result):
#|    """{table, schema, columns...} for the audit table, from the documented tables of its database."""
#|    tables = db_result.get("tables", []) if db_result else []
#|    cands = [t for t in tables if (a.get("table") and t["table"].lower() == a["table"].lower())
#|             or (not a.get("table") and TABLE_NAME.search(t["table"]))]
#|    best = None
#|    for t in cands:
#|        cols = [c["name"] for c in t["columns"]]
#|        pick = lambda rx, key: a.get(key) or next((c for c in cols if rx.search(c)), None)
#|        found = {"file_column": pick(FILE_COL, "file_column"), "status_column": pick(STATUS_COL, "status_column"),
#|                 "time_column": pick(TIME_COL, "time_column"), "error_column": pick(ERROR_COL, "error_column"),
#|                 "rows_column": pick(ROWS_COL, "rows_column"), "link_column": pick(LINK_COL, "link_column")}
#|        score = sum(1 for v in found.values() if v) + (3 if found["file_column"] else 0)
#|        if found["file_column"] and (best is None or score > best[0]):
#|            best = (score, dict(found, table=t["table"], schema=t.get("schema"),
#|                                guessed=[k for k, v in found.items() if v and not a.get(k)]))
#|    return best[1] if best else None
#|
#|
#|def _fq(dialect, schema, table):
#|    q = '"' if dialect != "mysql" else "`"
#|    return f"{q}{table}{q}" if dialect == "sqlite" or not schema else f"{q}{schema}{q}.{q}{table}{q}"
#|
#|
#|def lookup(cfg, model, file=None, link_ids=(), limit=10):
#|    """Latest audit rows for a file name (exact or contained, e.g. with a path) and / or definition ids."""
#|    a = settings(cfg)
#|    dcfg = next(d for d in cfg["databases"] if d["name"] == a["db"])
#|    conn, dialect = dbmod.connect(dcfg)
#|    try:
#|        q = '"' if dialect != "mysql" else "`"
#|        p = dbmod._ph(dialect)
#|        where, params = [], []
#|        if file:
#|            where.append(f"({q}{model['file_column']}{q} = {p} OR {q}{model['file_column']}{q} LIKE {p})")
#|            params += [file, f"%{file}"]
#|        if link_ids and model.get("link_column"):
#|            where.append(f"{q}{model['link_column']}{q} IN ({','.join([p] * len(link_ids))})")
#|            params += list(link_ids)
#|        if not where:
#|            return []
#|        order = f" ORDER BY {q}{model['time_column']}{q} DESC" if model.get("time_column") else ""
#|        sql = f"SELECT * FROM {_fq(dialect, model.get('schema'), model['table'])} WHERE {' OR '.join(where)}{order} LIMIT {int(limit)}"
#|        rows = dbmod._rows(conn, sql, tuple(params))
#|        return [{k: dbmod.mask_value(k, v) for k, v in r.items()} for r in rows]
#|    finally:
#|        conn.close()
#|
#|
#|def is_failure(model, row):
#|    v = row.get(model.get("status_column"))
#|    return bool(v is not None and FAIL_WORDS.search(str(v)))
#|
#|
#|def summarize(model, row):
#|    get = lambda k: row.get(model.get(k)) if model.get(k) else None
#|    parts = [f"{get('file_column')}", f"status {get('status_column')}" if get("status_column") is not None else "",
#|             f"at {get('time_column')}" if get("time_column") is not None else "",
#|             f"{get('rows_column')} rows" if get("rows_column") is not None else "",
#|             f"error: {str(get('error_column'))[:200]}" if get("error_column") not in (None, "") else ""]
#|    return ", ".join(x for x in parts if x)
#|
#|
#|def format_rows(model, rows):
#|    if not rows:
#|        return "no load-audit rows for this file / feed"
#|    return "\n".join(("x " if is_failure(model, r) else "  ") + summarize(model, r) for r in rows)
#@@ FILE nifikb/build.py tc 3171af11332bea14
#|"""Build / incrementally refresh the knowledge base."""
#|import hashlib
#|import json
#|import re
#|import shutil
#|import time
#|from pathlib import Path
#|
#|from . import __version__, audit as auditmod, db as dbmod, learnings as learnmod, logs as logmod, metadata as metamod
#|from .analyze import Analysis, type_short
#|from .catalog import PARSER_VERSION as NAR_PARSER_VERSION, Catalog, find_nars, read_nar
#|from .code import PARSER_VERSION as CODE_PARSER_VERSION, CodeIndex, index_file, iter_code_files
#|from .flow import load_flow
#|from .render import Renderer
#|from .store import Store
#|from .util import REDACTED, clip, file_sig, redact_secrets, sha1_file, short, slugify, write_if_changed
#|
#|GENERATED_DIRS = ("flows", "custom-code", "scripts", "db")
#|
#|
#|def _h(obj):
#|    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()
#|
#|
#|def find_flow_file(cfg):
#|    nifi = cfg["nifi"]
#|    if nifi.get("flow_file"):
#|        return Path(nifi["flow_file"])
#|    home = Path(nifi["home"])
#|    for name in ("conf/flow.json.gz", "conf/flow.xml.gz", "flow.json.gz", "flow.xml.gz"):
#|        if (home / name).is_file():
#|            return home / name
#|    raise FileNotFoundError(f"no flow.json.gz / flow.xml.gz under {home} (set [nifi] flow_file)")
#|
#|
#|def read_nifi_properties(cfg):
#|    home = cfg["nifi"].get("home")
#|    path = Path(home) / "conf" / "nifi.properties" if home else None
#|    props = {}
#|    if path and path.is_file():
#|        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
#|            if "=" in line and not line.lstrip().startswith("#"):
#|                k, v = line.split("=", 1)
#|                props[k.strip()] = REDACTED if re.search(r"(?i)pass|secret|key$", k) and v.strip() else v.strip()
#|    return props
#|
#|
#|def build(cfg, force=False, refresh_db=False, log=print):
#|    out = Path(cfg["output"]["dir"])
#|    out.mkdir(parents=True, exist_ok=True)
#|    store = Store(str(out / "kb.sqlite"))
#|    try:
#|        return _build(cfg, store, out, force, refresh_db, log)
#|    finally:
#|        store.close()
#|
#|
#|def _build(cfg, store, out, force, refresh_db, log):
#|    t0 = time.time()
#|    flow_path = find_flow_file(cfg)
#|    nar_dirs = [Path(cfg["nifi"]["home"]) / d for d in ("lib", "extensions")] if cfg["nifi"].get("home") else []
#|    nar_dirs += [Path(d) for d in cfg["nifi"].get("extra_nar_dirs", [])]
#|    nar_files = find_nars(nar_dirs)
#|    repos = [Path(r) for r in cfg["code"].get("repos", [])]
#|    code_files = list(iter_code_files(repos))
#|    referenced = [Path(p) for p in store.get_meta("referenced_scripts", []) if Path(p).is_file()]
#|    sources = {
#|        "flow": sha1_file(flow_path),
#|        "nars": _h([(str(p), file_sig(p)) for p in nar_files]),
#|        "code": _h([(str(p), file_sig(p)) for p in code_files + referenced]),
#|        "config": _h({k: v for k, v in cfg.items() if k != "_path"}),
#|        "knowledge": _h([(str(p), file_sig(p)) for p in sorted(Path(cfg["knowledge"]["dir"]).rglob("*.md"))]
#|                        if Path(cfg["knowledge"]["dir"]).is_dir() else []),
#|        # any change to nifikb itself (an upgrade, a fix) regenerates the KB, not only a version bump
#|        "version": f"{__version__}/{CODE_PARSER_VERSION}/{NAR_PARSER_VERSION}/"
#|                   + _h([(p.name, file_sig(p)) for p in sorted(Path(__file__).parent.glob("*.py"))]),
#|    }
#|    build_sig = _h(sources)
#|    db_due = refresh_db or _db_due(cfg, store)
#|    meta_due = refresh_db or _meta_due(cfg, store)
#|    if not force and build_sig == store.get_meta("build_sig") and not db_due and not meta_due and (out / "INDEX.md").exists():
#|        log(f"Knowledge base is up to date ({out}). Use --force to rebuild.")
#|        return {"status": "up-to-date", "out": str(out)}
#|
#|    log(f"Reading flow {flow_path}")
#|    flow = load_flow(flow_path)
#|
#|    catalog, nar_keep = Catalog(), []
#|    for p in nar_files:
#|        key, sig = str(p), f"{file_sig(p)}:{NAR_PARSER_VERSION}"
#|        data = store.cached("cache_nar", key, sig)
#|        if data is None:
#|            try:
#|                data = read_nar(p)
#|            except Exception as e:  # corrupt / partial NAR
#|                log(f"  skip NAR {p.name}: {e}")
#|                continue
#|            store.put_cache("cache_nar", key, sig, data)
#|        catalog.add(data)
#|        nar_keep.append(key)
#|    store.prune_cache("cache_nar", nar_keep)
#|    log(f"  {len(nar_files)} NARs, {len(catalog.types)} component types")
#|
#|    code, code_keep, parsed = CodeIndex(), [], 0
#|
#|    def index_cached(p):
#|        nonlocal parsed
#|        key, sig = str(p), f"{file_sig(p)}:{CODE_PARSER_VERSION}"
#|        data = store.cached("cache_code", key, sig)
#|        if data is None:
#|            data = index_file(p)
#|            store.put_cache("cache_code", key, sig, data)
#|            parsed += 1
#|        code_keep.append(key)
#|        return data
#|
#|    for p in code_files:
#|        try:
#|            code.add(index_cached(p))
#|        except OSError as e:
#|            log(f"  skip {p}: {e}")
#|    code.finalize()
#|    log(f"  code: {len(code_files)} files ({parsed} re-parsed), {len(code.by_fqcn)} NiFi components, {len(code.modules)} maven modules")
#|
#|    an = Analysis(flow, catalog, code, cfg).run()
#|    previews = {}
#|    for path, entry in an.scripts.items():
#|        target = Path(path) if entry["exists"] else (Path(entry["repo_match"]) if entry.get("repo_match") else None)
#|        if target and target.is_file():
#|            entry["index"] = code.files.get(str(target)) or index_cached(target)
#|            text = target.read_text(encoding="utf-8", errors="replace")
#|            if len(text) < 6000:
#|                previews[path] = "\n".join(redact_secrets(ln) for ln in text.splitlines())
#|    store.prune_cache("cache_code", code_keep)
#|    store.set_meta("referenced_scripts", [p for p, e in an.scripts.items() if e["exists"]])
#|
#|    db_results = _databases(cfg, an, code, store, db_due, log)
#|    meta = _metadata(cfg, an, store, db_results, db_due or meta_due, log, schemas_due=db_due)
#|    asettings = auditmod.settings(cfg)
#|    audit_model = auditmod.detect(asettings, next((d for d in db_results if d["name"] == asettings["db"]), None)) if asettings else None
#|    store.set_meta("audit_model", audit_model)
#|    if asettings:
#|        log(f"  audit: {'table ' + audit_model['table'] if audit_model else 'no load-audit table found - set [audit] table'}")
#|    _field_checks(an, db_results)
#|
#|    instance = read_nifi_properties(cfg)
#|    snapshot = _snapshot(an)
#|    previous = store.last_snapshot()
#|    changes = _diff(previous, snapshot) if previous else []
#|    if changes:
#|        store.add_changes(changes)
#|        log(f"  {len(changes)} flow change(s) since last build")
#|    if previous is None or changes:
#|        store.add_snapshot(sources["flow"], snapshot)
#|
#|    renderer = Renderer(an, out, code, db_results, {"code_roots": [str(r) for r in repos], "script_previews": previews,
#|                                                     "metadata": bool(meta), "learnings": len(learnmod.load_all(cfg, False)),
#|                                                     "metadata_summary": (f"{len(meta['model']['tables'])} config tables · {meta['checked']} "
#|                                                                          f"definitions checked · {len(meta['drift'])} with drift") if meta else None,
#|                                                     "knowledge_dir": cfg["knowledge"]["dir"]})
#|    files = renderer.render_all(instance, store.changes())
#|    files["README.md"] = _readme(cfg)
#|    if meta:
#|        meta["code_map"] = _config_table_code(meta, code, catalog)
#|        files["metadata.md"] = metamod.render(meta["model"], meta["rows"], meta["drift"], meta["checked"], meta["code_map"])
#|    written = sum(write_if_changed(out / rel, content) for rel, content in files.items())
#|    if not meta and (out / "metadata.md").exists():
#|        (out / "metadata.md").unlink()
#|    for d in GENERATED_DIRS:
#|        for f in (out / d).rglob("*.md") if (out / d).exists() else []:
#|            if f.relative_to(out).as_posix() not in files:
#|                f.unlink()
#|        for sub in sorted((p for p in (out / d).rglob("*") if p.is_dir()), reverse=True) if (out / d).exists() else []:
#|            if not any(sub.iterdir()):
#|                sub.rmdir()
#|    _store_facts(store, an, renderer, code, db_results, meta, cfg)
#|    try:
#|        logmod.index(cfg, store, log)
#|    except Exception as e:  # never fail a build because of a log file
#|        log(f"  ⚠ logs: {type(e).__name__}: {e}")
#|    # Scripts referenced by the flow are only known after analysis; sign them now so the next run can compare.
#|    referenced = [Path(p) for p in store.get_meta("referenced_scripts", []) if Path(p).is_file()]
#|    sources["code"] = _h([(str(p), file_sig(p)) for p in code_files + referenced])
#|    store.set_meta("build_sig", _h(sources))
#|    store.set_meta("built_at", time.time())
#|    store.set_meta("flow_file", str(flow_path))
#|    log(f"Knowledge base written to {out}: {len(files)} files ({written} changed), "
#|        f"{len(an.findings)} findings, {time.time() - t0:.1f}s")
#|    return {"status": "built", "out": str(out), "files": len(files), "changed": written, "findings": len(an.findings),
#|            "changes": changes}
#|
#|
#|# ------------------------------------------------------------------------------------------ databases
#|def _db_due(cfg, store):
#|    hours = float(cfg.get("db_refresh_hours", 24))
#|    for d in cfg.get("databases", []):
#|        row = store.db.execute("SELECT fetched FROM cache_db WHERE name=?", (d["name"],)).fetchone()
#|        if not row or time.time() - row["fetched"] > hours * 3600:
#|            return True
#|    return False
#|
#|
#|def _meta_due(cfg, store):
#|    """Config rows change more often than schemas: re-read them every [metadata] refresh_hours (default 1)."""
#|    m = cfg.get("metadata")
#|    if not m:
#|        return False
#|    row = store.db.execute("SELECT fetched FROM cache_db WHERE name='__metadata__'").fetchone()
#|    return not row or time.time() - row["fetched"] > float(m.get("refresh_hours", 1)) * 3600
#|
#|
#|def _databases(cfg, an, code, store, due, log):
#|    results = []
#|    tables_by_service = an.tables_by_service()
#|    code_tables = {t for info in code.files.values() for t in info.get("tables") or []}
#|    for s in an.scripts.values():
#|        if s.get("index"):
#|            code_tables |= set(s["index"].get("tables") or [])
#|    msettings = metamod.settings(cfg)
#|    asettings = auditmod.settings(cfg)
#|    for dcfg in cfg.get("databases", []):
#|        if msettings and dcfg["name"] == msettings["db"]:
#|            dcfg = dict(dcfg, include_tables=list(dcfg.get("include_tables") or []) + metamod.table_patterns(msettings))
#|        if asettings and dcfg["name"] == asettings["db"]:
#|            dcfg = dict(dcfg, include_tables=list(dcfg.get("include_tables") or []) + auditmod.patterns(asettings))
#|        services = [sid for sid, j in an.jdbc.items()
#|                    if dbmod.matches_jdbc(dcfg, dict(j, service_name=an.flow.services[sid]["name"]))]
#|        wanted = {t for sid in services for t in tables_by_service.get(sid, {})}
#|        sig = _h([dcfg, sorted(wanted), sorted(code_tables)])
#|        cached, fetched = store.cached_db(dcfg["name"], sig)
#|        data, error = cached, None
#|        if due or cached is None:
#|            try:
#|                data = dbmod.introspect(dcfg, wanted, code_tables, log=log)
#|                data["fetched"] = time.strftime("%Y-%m-%d %H:%M")
#|                store.put_db(dcfg["name"], sig, data)
#|            except dbmod.DbError as e:
#|                error = str(e)
#|                log(f"  ⚠ {e}" + (" - using cached schema" if cached else ""))
#|                an.findings.append({"severity": "warn", "kind": "db-unreachable", "component_id": None,
#|                                    "message": f"database '{dcfg['name']}': {error}", "location": dcfg["name"]})
#|        entry = dict(data or {"name": dcfg["name"], "tables": [], "missing": []})
#|        entry.update(name=dcfg["name"], services=services, error=error)
#|        for t in entry.get("missing", []):
#|            users = [cid for sid in services for cid in tables_by_service.get(sid, {}).get(t, [])]
#|            an.findings.append({"severity": "error", "kind": "missing-table", "component_id": users[0] if users else None,
#|                                "message": f"table '{t}' is written/read by the flow but does not exist in database '{dcfg['name']}'",
#|                                "location": dcfg["name"]})
#|        results.append(entry)
#|    return results
#|
#|
#|def _metadata(cfg, an, store, db_results, due, log, schemas_due=True):
#|    """Config tables that drive a metadata-driven flow: discover roles, snapshot rows, describe target tables, lint."""
#|    m = metamod.settings(cfg)
#|    if not m:
#|        return None
#|    meta_db = next((d for d in db_results if d["name"] == m["db"]), {})
#|    model = metamod.discover(m, meta_db)
#|    sig = _h([m, {t: i["columns"] for t, i in model["tables"].items()}])
#|    cached, _ = store.cached_db("__metadata__", sig)
#|    rows_by_table, targets = None, None
#|    if model["tables"] and (due or cached is None):
#|        try:
#|            rows_by_table = metamod.fetch_rows(metamod.db_config(cfg, m["db"]), m, model, log)
#|            old_targets = (cached or store.cached_db_any("__metadata__") or {}).get("targets")
#|            targets = (_metadata_targets(cfg, m, model, metamod.Rows(rows_by_table), db_results, log)
#|                       if schemas_due or not old_targets else old_targets)  # target schemas follow db_refresh_hours
#|            previous = store.get_meta_rows()
#|            store.put_meta_rows(rows_by_table)
#|            store.put_db("__metadata__", sig, {"targets": targets})
#|            if previous:  # first snapshot: nothing to compare
#|                changes = metamod.diff_rows(model, previous, rows_by_table)
#|                if changes:
#|                    store.add_meta_changes(changes)
#|                    store.add_changes([f"config {c['change']}" for c in changes[:500]]
#|                                      + ([f"config … {len(changes) - 500} more row changes (python -m nifikb diagnose --file <name> "
#|                                          "shows those of one definition)"] if len(changes) > 500 else []))
#|                    log(f"  metadata: {len(changes)} config row change(s) since the last snapshot")
#|        except dbmod.DbError as e:
#|            rows_by_table = None
#|            log(f"  ⚠ metadata: {e} - using the last snapshot")
#|            an.findings.append({"severity": "warn", "kind": "db-unreachable", "component_id": None, "location": m["db"],
#|                                "message": f"metadata config tables could not be read: {e} (using the last snapshot)"})
#|    if rows_by_table is None:
#|        rows_by_table = store.get_meta_rows()
#|        targets = (cached or store.cached_db_any("__metadata__") or {}).get("targets") or {"tables": [], "all_table_names": []}
#|    if not model["tables"]:
#|        log(f"  ⚠ metadata: no config tables matched {m['tables']} in database '{m['db']}'")
#|    tdb = next((d for d in db_results if d["name"] == m["target_db"]), None)
#|    if tdb is not None:
#|        have = {t["table"].lower() for t in tdb.get("tables", [])}
#|        tdb["tables"] = tdb.get("tables", []) + [t for t in targets["tables"] if t["table"].lower() not in have]
#|        if not tdb.get("all_table_names"):
#|            tdb["all_table_names"] = targets.get("all_table_names") or []
#|    rows = metamod.Rows(rows_by_table)
#|    drift, checked = metamod.lint(model, rows, db_results)
#|    an.findings.extend(drift)
#|    if checked:
#|        log(f"  metadata: {checked} definitions checked against target tables, {len(drift)} with problems")
#|    return {"model": model, "rows": rows, "drift": drift, "checked": checked, "settings": m}
#|
#|
#|def _metadata_targets(cfg, m, model, rows, db_results, log):
#|    """Describe the target tables named in the definition rows that the flow itself does not reference."""
#|    dt, col = model.get("definition_table"), model.get("definition_target")
#|    tdb = next((d for d in db_results if d["name"] == m["target_db"]), {})
#|    if not dt or not col or not m["target_db"]:
#|        return {"tables": [], "all_table_names": tdb.get("all_table_names") or []}
#|    names = sorted({str(r[col]).strip() for r in rows.table(dt) if r.get(col) and "${" not in str(r[col])
#|                    and metamod.table_target(model, r[col])})
#|    have = {t["table"].lower() for t in tdb.get("tables", [])}
#|    todo = [n for n in names if n.lower().split(".")[-1] not in have]
#|    if not todo:
#|        return {"tables": [], "all_table_names": tdb.get("all_table_names") or []}
#|    tcfg = dict(metamod.db_config(cfg, m["target_db"]), include_tables=[], all_tables=False, profile_tables=[], sample_rows=0,
#|                max_tables=len(todo) + 10)
#|    res = dbmod.introspect(tcfg, set(), todo, log=lambda msg: log(msg.replace("  db ", "  metadata target tables, db ")))
#|    return {"tables": res["tables"], "all_table_names": res["all_table_names"]}
#|
#|
#|def _normalize(name, translate):
#|    return re.sub(r"_", "", name).upper() if translate else name
#|
#|
#|def _field_checks(an, db_results):
#|    """PutDatabaseRecord: compare incoming record fields with the target table's columns."""
#|    for comp in an.flow.components.values():
#|        if type_short(comp["type"]) != "PutDatabaseRecord":
#|            continue
#|        sid = an.db_service_of(comp)
#|        db = next((d for d in db_results if sid in d.get("services", [])), None)
#|        props = {f["name"]: f["resolved"] for f in an.props[comp["id"]]}
#|        table = (props.get("put-db-record-table-name") or "").lower()
#|        if not db or not table or "${" in table:
#|            continue
#|        t = next((x for x in db.get("tables", []) if x["table"].lower() == table.split(".")[-1]), None)
#|        fields, origin = an.record_fields(comp)
#|        if not t or not fields:
#|            continue
#|        translate = props.get("put-db-record-translate-field-names", "true") != "false"
#|        cols = {_normalize(c["name"], translate): c for c in t["columns"]}
#|        norm_fields = {_normalize(f, translate): f for f in fields}
#|        extra = [f for n, f in norm_fields.items() if n not in cols]
#|        required = [c["name"] for n, c in cols.items() if n not in norm_fields and not c["nullable"]
#|                    and c.get("default") is None and "auto_increment" not in str(c.get("extra", "")).lower()
#|                    and not str(c.get("default") or "").startswith("nextval")]
#|        msg = []
#|        if extra:
#|            behavior = props.get("put-db-record-unmatched-field-behavior", "Ignore Unmatched Fields")
#|            msg.append(f"record fields with no column: {', '.join(extra)} ({behavior})")
#|        if required:
#|            msg.append(f"NOT NULL columns never supplied: {', '.join(required)}")
#|        message = "; ".join(msg) or f"all {len(fields)} fields map to columns"
#|        an.field_checks.append({"component_id": comp["id"], "db": db["name"], "table": table, "message": f"{message} (fields from {origin})",
#|                                "fields": fields, "translate": translate})
#|        if msg:
#|            sev = "error" if extra and "Fail" in props.get("put-db-record-unmatched-field-behavior", "") else "warn"
#|            an.findings.append({"severity": sev, "kind": "field-mismatch", "component_id": comp["id"],
#|                                "message": f"{table}: {message} (fields from {origin})", "location": db["name"]})
#|
#|
#|# ------------------------------------------------------------------------------------ snapshot / diff
#|def _snapshot(an):
#|    comps = {}
#|    for c in list(an.flow.components.values()) + list(an.flow.services.values()):
#|        if c.get("placeholder"):
#|            continue
#|        comps[c["id"]] = {"n": c["name"], "t": type_short(c["type"]) or c["kind"].lower(), "g": (an.flow.groups.get(c["group_id"]) or {}).get("path", ""),
#|                          "s": c.get("state"), "p": {f["display"]: clip(f["value"], 200) for f in an.props[c["id"]]},
#|                          "sch": f"{c.get('scheduling_strategy')} {c.get('scheduling_period')}" if c["kind"] == "PROCESSOR" else None,
#|                          "at": c.get("auto_terminated")}
#|    conns = sorted({f"{c['source_id']}|{','.join(c['relationships'])}|{c['dest_id']}" for c in an.flow.connections})
#|    versions = {gid: {"n": g["path"], "v": (g.get("version_control") or {}).get("version")}
#|                for gid, g in an.flow.groups.items() if g.get("version_control")}
#|    return {"c": comps, "e": conns, "g": versions}
#|
#|
#|def _diff(old, new):
#|    out = []
#|    oc, nc = old["c"], new["c"]
#|
#|    def name(cid, snap):
#|        c = snap["c"].get(cid)
#|        return f"{c['n']} [{c['t']}] `{short(cid)}` in {c['g']}" if c else f"`{short(cid)}`"
#|
#|    for cid in sorted(set(nc) - set(oc)):
#|        out.append(f"added {name(cid, new)}")
#|    for cid in sorted(set(oc) - set(nc)):
#|        out.append(f"removed {name(cid, old)}")
#|    for cid in sorted(set(nc) & set(oc)):
#|        a, b = oc[cid], nc[cid]
#|        if a["s"] != b["s"]:
#|            out.append(f"{name(cid, new)}: state {a['s']} → {b['s']}")
#|        if a["n"] != b["n"]:
#|            out.append(f"{name(cid, new)}: renamed from '{a['n']}'")
#|        if a.get("sch") != b.get("sch"):
#|            out.append(f"{name(cid, new)}: schedule {a.get('sch')} → {b.get('sch')}")
#|        if a.get("at") != b.get("at"):
#|            out.append(f"{name(cid, new)}: auto-terminated {a.get('at')} → {b.get('at')}")
#|        for k in sorted(set(a["p"]) | set(b["p"])):
#|            if a["p"].get(k) != b["p"].get(k):
#|                out.append(f"{name(cid, new)}: '{k}' `{a['p'].get(k)}` → `{b['p'].get(k)}`")
#|    snap_names = {**old["c"], **new["c"]}
#|
#|    def edge(e):
#|        s, rel, d = e.split("|")
#|        return f"{snap_names.get(s, {}).get('n', short(s))} -{rel}→ {snap_names.get(d, {}).get('n', short(d))}"
#|
#|    for gid, g in sorted((new.get("g") or {}).items()):
#|        before = (old.get("g") or {}).get(gid)
#|        if before and before.get("v") != g.get("v"):
#|            out.append(f"process group {g['n']}: registry version {before.get('v')} → {g.get('v')}")
#|        elif not before and old.get("g") is not None:
#|            out.append(f"process group {g['n']}: now version-controlled (v{g.get('v')})")
#|    for e in sorted(set(new["e"]) - set(old["e"])):
#|        out.append(f"connection added: {edge(e)}")
#|    for e in sorted(set(old["e"]) - set(new["e"])):
#|        out.append(f"connection removed: {edge(e)}")
#|    return out
#|
#|
#|# --------------------------------------------------------------------------------------- sqlite facts
#|def _config_table_code(meta, code, catalog=None, depth=2):
#|    """{custom component class: [config tables its source mentions]}. Follows the classes the component's source refers
#|    to (e.g. processor -> service -> DAO) and matches table names as words, so constants and dynamically built SQL count."""
#|    tables = sorted(meta["model"]["tables"], key=len, reverse=True)
#|    if not tables:
#|        return {}
#|    rx = re.compile(r"(?i)(?<![\w$])(" + "|".join(re.escape(t) for t in tables) + r")(?![\w$])")
#|    canon = {t.lower(): t for t in tables}
#|    by_stem = {}
#|    for path, info in code.files.items():
#|        if info.get("lang") in ("java", "groovy", "kotlin", "scala", "python"):
#|            by_stem.setdefault(Path(path).stem, []).append(path)
#|    texts = {}
#|
#|    def text(path):
#|        if path not in texts:
#|            try:
#|                texts[path] = Path(path).read_text(encoding="utf-8", errors="replace")
#|            except OSError:
#|                texts[path] = ""
#|        return texts[path]
#|
#|    out = {}
#|    for fqcn, entries in code.components():
#|        seen, frontier, found = set(), [e["path"] for e in entries], set()
#|        for _ in range(depth + 1):
#|            nxt = []
#|            for path in frontier:
#|                if path in seen:
#|                    continue
#|                seen.add(path)
#|                src = text(path)
#|                found |= {canon[m.lower()] for m in rx.findall(src)}
#|                idents = set(re.findall(r"\b[A-Z][A-Za-z0-9_]+\b", src))
#|                nxt += [p for stem in idents & by_stem.keys() for p in by_stem[stem]]
#|            frontier = nxt
#|        if found:
#|            out[fqcn] = sorted(found)
#|    for t, ext in (catalog.types.items() if catalog else []):
#|        # no source: fall back to the deployed jar's string literals (jar-wide, so less precise than source)
#|        if ext.get("deployed") and t not in code.by_fqcn:
#|            found = {canon[m.lower()] for s in catalog.jar_strings(ext["deployed"]) for m in rx.findall(s)}
#|            if found:
#|                out[t] = sorted(found)
#|    return out
#|
#|
#|def _metadata_docs(meta):
#|    """Search entries: one per definition (keys, target, field names) and one per row of the other config tables."""
#|    docs, model, rows = [], meta["model"], meta["rows"]
#|    dt, st = model.get("definition_table"), model.get("structure_table")
#|    for table in model["tables"]:
#|        if table == st:
#|            continue
#|        pk = model["tables"][table]["pk"]
#|        for r in rows.table(table):
#|            ident = ":".join(str(r.get(c)) for c in pk) if pk else ""
#|            values = " ".join(str(v) for v in r.values() if v not in (None, "***") and not isinstance(v, bool))
#|            if table == dt:
#|                fields = metamod.structure_of(model, rows, r)
#|                target = r.get(model.get("definition_target")) if model.get("definition_target") else ""
#|                docs.append({"kind": "metadata", "ref": f"{table}:{r.get(model.get('definition_id'))}",
#|                             "title": f"{metamod.definition_label(model, r)} → {target or '?'}",
#|                             "body": clip(values, 2000) + " " + " ".join(f["name"] for f in fields), "doc": "metadata.md"})
#|            else:
#|                docs.append({"kind": "config", "ref": f"{table}:{ident}", "title": f"{table} {ident}".strip(),
#|                             "body": clip(values, 2000), "doc": "metadata.md"})
#|    return docs
#|
#|
#|def _store_facts(store, an, renderer, code, db_results, meta=None, cfg=None):
#|    store.reset_derived()
#|    flow = an.flow
#|    groups, comps, props, docs = [], [], [], []
#|    for gid, g in flow.groups.items():
#|        groups.append({"id": gid, "name": g["name"], "parent_id": g["parent_id"], "path": g["path"], "doc": renderer.group_file[gid],
#|                       "tags": ",".join(an.group_tags(gid, False)), "instance_id": g.get("instance_id"),
#|                       "version": json.dumps(g.get("version_control")) if g.get("version_control") else None})
#|        labels = " ".join(lab["text"] for lab in flow.labels if lab["group_id"] == gid)
#|        docs.append({"kind": "flow", "ref": gid, "title": g["path"], "body": f"{labels} {g.get('comments', '')} {' '.join(an.group_tags(gid))}",
#|                     "doc": renderer.group_file[gid]})
#|    for c in list(flow.components.values()) + list(flow.services.values()):
#|        doc = renderer.group_file.get(c["group_id"], "INDEX.md") if c["kind"] != "CONTROLLER_SERVICE" else "services.md"
#|        facts = an.key_facts(c, 400)
#|        comps.append({"id": c["id"], "kind": c["kind"], "name": c["name"], "type": c["type"], "group_id": c["group_id"],
#|                      "group_path": (flow.groups.get(c["group_id"]) or {}).get("path", "(controller)"), "state": c.get("state"),
#|                      "custom": int(an.is_custom(c)), "facts": facts, "auto_term": json.dumps(c.get("auto_terminated") or []),
#|                      "doc": renderer.comp_docs.get(c["id"], ""), "instance_id": c.get("instance_id")})
#|        body = []
#|        for f in an.props[c["id"]]:
#|            props.append({"component_id": c["id"], "name": f["name"], "display": f["display"], "value": f["value"], "resolved": f["resolved"],
#|                          "source": f["source"], "is_default": int(f["default"]), "kinds": ",".join(f["kinds"])})
#|            if not f["default"]:
#|                body.append(f"{f['display']}={f['resolved']}")
#|        if c["kind"] in ("PROCESSOR", "CONTROLLER_SERVICE", "INPUT_PORT", "OUTPUT_PORT"):
#|            docs.append({"kind": c["kind"].lower(), "ref": c["id"], "title": f"{c['name']} [{type_short(c['type'])}]",
#|                         "body": f"{c['type']} {facts} {c.get('comments', '')} " + " ".join(body), "doc": doc})
#|    store.insert("groups", groups)
#|    store.insert("components", comps)
#|    store.insert("properties", props)
#|    store.insert("connections", [{"id": c["id"], "source_id": c["source_id"], "dest_id": c["dest_id"], "relationships": ",".join(c["relationships"]),
#|                                  "group_id": c["group_id"], "name": c["name"]} for c in flow.connections])
#|    store.insert("resources", [{"kind": r["kind"], "value": r["value"], "component_id": r["component_id"], "property": r["property"],
#|                                "source": r["source"], "hardcoded": int(r["hardcoded"]), "raw": r["raw"]} for r in an.resources])
#|    store.insert("findings", [{"severity": f["severity"], "kind": f["kind"], "component_id": f["component_id"], "message": f["message"],
#|                               "location": f.get("location")} for f in an.findings])
#|    for fqcn, entries in code.components():
#|        for e in entries:
#|            store.insert("code_components", [{"fqcn": fqcn, "path": e["path"], "line": e["line"], "data": json.dumps(e["component"])}])
#|            comp = e["component"]
#|            docs.append({"kind": "code", "ref": fqcn, "title": fqcn,
#|                         "body": f"{comp.get('description', '')} {' '.join(comp.get('tags', []))} "
#|                                 + " ".join(f"{p.get('name')} {p.get('displayName') or ''}" for p in comp.get("properties") or []),
#|                         "doc": renderer.custom_file.get(fqcn, "custom-code/INDEX.md")})
#|    fqcn_of = {e["path"]: fqcn for fqcn, entries in code.components() for e in entries}
#|    for path, info in code.files.items():
#|        doc = renderer.custom_file.get(fqcn_of.get(path), "hardcoded.md")
#|        for m in info.get("messages") or []:  # a ticket's error text finds the code line that produces it
#|            docs.append({"kind": "message", "ref": f"{Path(path).name}:{m['line']}", "title": f"{m['level']} in {Path(path).name}:{m['line']}",
#|                         "body": m["text"], "doc": doc})
#|        if info.get("hardcoded") or info.get("tables") or info.get("spark"):
#|            docs.append({"kind": "file", "ref": path, "title": Path(path).name,
#|                         "body": " ".join(h["value"] for h in info.get("hardcoded", [])) + " " + " ".join(info.get("tables", []))
#|                         + " " + " ".join(f"spark-submit {x.get('class') or ''} {(x.get('class') or '').rsplit('.', 1)[-1]} "
#|                                          f"{x.get('app') or ''} {Path(x.get('app') or 'x').name} {x.get('name') or ''}"
#|                                          for x in info.get("spark") or []),
#|                         "doc": "hardcoded.md"})
#|    for d in db_results:
#|        store.set_meta(f"db_all_tables:{d['name']}", d.get("all_table_names") or [])
#|        for t in d.get("tables", []):
#|            doc = renderer.table_file.get((d["name"], t["table"]), f"db/{slugify(d['name'])}.md")
#|            store.insert("db_tables", [{"db": d["name"], "schema_name": t["schema"], "name": t["table"], "data": json.dumps(t, default=str),
#|                                        "doc": doc}])
#|            docs.append({"kind": "table", "ref": f"{d['name']}.{t['table']}", "title": t["table"],
#|                         "body": " ".join(c["name"] for c in t.get("columns", [])) + " " + (t.get("comment") or ""), "doc": doc})
#|    if meta:
#|        docs += _metadata_docs(meta)
#|    store.set_meta("metadata_model", meta["model"] if meta else None)
#|    store.set_meta("config_table_code", meta.get("code_map", {}) if meta else {})
#|    if cfg:
#|        docs += learnmod.search_docs(cfg)
#|    store.insert("search", docs)
#|    store.insert("record_schemas", [{"component_id": c["component_id"], "db": c["db"], "table_name": c["table"],
#|                                     "fields": json.dumps(c["fields"]), "translate": int(c["translate"])} for c in an.field_checks])
#|
#|
#|def _readme(cfg):
#|    return f"""# NiFi knowledge base (generated)
#|
#|Start with [INDEX.md](INDEX.md). Generated by `nifikb` {__version__}; do not edit by hand — rebuild instead:
#|
#|    python -m nifikb build            # incremental: no-op when nothing changed
#|    python -m nifikb build --force    # full rebuild
#|    python -m nifikb watch            # rebuild automatically when the flow / code changes
#|
#|Config: `{cfg.get('_path', 'nifikb.toml')}`
#|"""
#|
#|
#|def clean(out):
#|    for d in GENERATED_DIRS:
#|        shutil.rmtree(Path(out) / d, ignore_errors=True)
#@@ FILE nifikb/catalog.py tc 9cd579d17b5774b1
#|"""Catalog of processor / controller-service types from the NAR files NiFi loads.
#|
#|Each NAR carries META-INF/docs/extension-manifest.xml with descriptions, property display names,
#|defaults, sensitivity and relationships. Older or hand-built NARs may lack it; for those we fall back to
#|the META-INF/services entries inside the bundled jars so we at least know which classes the NAR provides.
#|"""
#|import io
#|import re
#|import xml.etree.ElementTree as ET
#|import zipfile
#|from pathlib import Path
#|
#|PARSER_VERSION = "2"  # bump when read_nar output changes, so cached NAR results are re-read
#|# Bundled third-party jars never hold our components; skipping them keeps custom-NAR scanning fast.
#|THIRD_PARTY_JAR = re.compile(r"(?i)^(?:.*/)?(commons-|jackson-|slf4j|log4j|logback|guava|httpclient|httpcore|netty|aws-|jaxb|javax|jakarta|"
#|                             r"snakeyaml|gson|json-|joda|bc(prov|pkix)|avro|kotlin|scala-|spring-|hadoop-|protobuf|okhttp|okio|"
#|                             r"jsch|sshj|mysql|mariadb|postgresql|ojdbc|mssql)")
#|MAX_JAR_BYTES = 30_000_000
#|MAX_STRINGS = 20000
#|
#|SERVICE_FILES = {
#|    "META-INF/services/org.apache.nifi.processor.Processor": "PROCESSOR",
#|    "META-INF/services/org.apache.nifi.controller.ControllerService": "CONTROLLER_SERVICE",
#|    "META-INF/services/org.apache.nifi.reporting.ReportingTask": "REPORTING_TASK",
#|}
#|
#|
#|def _t(el, tag, default=None):
#|    child = el.find(tag) if el is not None else None
#|    return child.text if child is not None and child.text is not None else default
#|
#|
#|def read_nar(path):
#|    """Return {nar: {...}, extensions: [...]} for one NAR file."""
#|    with zipfile.ZipFile(path) as z:
#|        names = set(z.namelist())
#|        manifest = {}
#|        if "META-INF/MANIFEST.MF" in names:
#|            for line in z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace").splitlines():
#|                if ": " in line:
#|                    k, v = line.split(": ", 1)
#|                    manifest[k.strip()] = v.strip()
#|        nar = {
#|            "file": str(path), "group": manifest.get("Nar-Group"), "artifact": manifest.get("Nar-Id") or Path(path).stem,
#|            "version": manifest.get("Nar-Version"), "parent": manifest.get("Nar-Dependency-Id"),
#|            "build": manifest.get("Build-Timestamp"),
#|        }
#|        if "META-INF/docs/extension-manifest.xml" in names:
#|            extensions = _parse_extension_manifest(z.read("META-INF/docs/extension-manifest.xml"))
#|        else:
#|            extensions = _scan_service_files(z, names)
#|        if nar["group"] and not nar["group"].startswith("org.apache.nifi"):
#|            nar["jar_strings"] = _component_jar_strings(z, names, {e["type"] for e in extensions}, extensions)
#|    for ext in extensions:
#|        ext["nar"] = nar["artifact"]
#|        ext["nar_group"] = nar["group"]
#|        if ext.get("deployed"):
#|            ext["deployed"]["nar"] = nar["artifact"]
#|    return {"nar": nar, "extensions": extensions}
#|
#|
#|def _component_jar_strings(z, names, types, extensions):
#|    """String literals of every class in the bundled jar(s) that hold the NAR's own components. Marks each extension
#|    with the jar it lives in (ext['deployed'])."""
#|    out = {}
#|    wanted = {t.replace(".", "/") + ".class": t for t in types if t}
#|    for jar_name in sorted(n for n in names if n.endswith(".jar") and not THIRD_PARTY_JAR.search(Path(n).name)):
#|        try:
#|            if z.getinfo(jar_name).file_size > MAX_JAR_BYTES:
#|                continue
#|            with zipfile.ZipFile(io.BytesIO(z.read(jar_name))) as jar:
#|                jar_names = jar.namelist()
#|                hits = [wanted[n] for n in jar_names if n in wanted]
#|                if not hits:
#|                    continue
#|                strings = set()
#|                for n in jar_names:
#|                    if n.endswith(".class") and len(strings) < MAX_STRINGS:
#|                        strings.update(s for s in class_strings(jar.read(n)) if 0 < len(s) <= 400)
#|                out[jar_name] = sorted(strings)[:MAX_STRINGS]
#|                for ext in extensions:
#|                    if ext["type"] in hits:
#|                        ext["deployed"] = {"jar": jar_name}
#|        except (zipfile.BadZipFile, KeyError, OSError):
#|            continue
#|    return out
#|
#|
#|def class_strings(data):
#|    """String literals (CONSTANT_String entries) of one .class file, from its constant pool.
#|    Invokedynamic string-concat recipes keep their \\u0001 placeholders, shown as {}."""
#|    if data[:4] != b"\xca\xfe\xba\xbe" or len(data) < 10:
#|        return []
#|    count = int.from_bytes(data[8:10], "big")
#|    utf8, refs, i, idx = {}, [], 10, 1
#|    try:
#|        while idx < count:
#|            tag = data[i]
#|            if tag == 1:
#|                n = int.from_bytes(data[i + 1:i + 3], "big")
#|                utf8[idx] = data[i + 3:i + 3 + n]
#|                i += 3 + n
#|            elif tag in (3, 4):
#|                i += 5
#|            elif tag in (5, 6):
#|                i += 9
#|                idx += 1  # long / double take two slots
#|            elif tag == 8:
#|                refs.append(int.from_bytes(data[i + 1:i + 3], "big"))
#|                i += 3
#|            elif tag in (7, 16, 19, 20):
#|                i += 3
#|            elif tag in (9, 10, 11, 12, 17, 18):
#|                i += 5
#|            elif tag == 15:
#|                i += 4
#|            else:
#|                break
#|            idx += 1
#|    except IndexError:
#|        pass
#|    out = []
#|    for r in refs:
#|        raw = utf8.get(r)
#|        if raw is not None:
#|            out.append(raw.decode("utf-8", "replace").replace("\x01", "{}"))
#|    return out
#|
#|
#|def _parse_extension_manifest(data):
#|    root = ET.fromstring(data)
#|    out = []
#|    for ext in root.iter("extension"):
#|        props = {}
#|        for p in ext.findall("./properties/property"):
#|            csd = p.find("controllerServiceDefinition")
#|            props[_t(p, "name")] = {
#|                "displayName": _t(p, "displayName") or _t(p, "name"),
#|                "description": _t(p, "description", ""),
#|                "default": _t(p, "defaultValue"),
#|                "required": _t(p, "required") == "true",
#|                "sensitive": _t(p, "sensitive") == "true",
#|                "el_scope": _t(p, "expressionLanguageScope"),
#|                "service_api": _t(csd, "className") if csd is not None else None,
#|                "allowable": {_t(a, "value"): _t(a, "displayName") for a in p.findall("./allowableValues/allowableValue")},
#|            }
#|        out.append({
#|            "type": _t(ext, "name"),
#|            "kind": _t(ext, "type"),
#|            "description": _t(ext, "description", ""),
#|            "tags": [t.text for t in ext.findall("./tags/tag") if t.text],
#|            "properties": props,
#|            "relationships": [
#|                {"name": _t(r, "name"), "description": _t(r, "description", ""), "auto_terminated": _t(r, "autoTerminated") == "true"}
#|                for r in ext.findall("./relationships/relationship")
#|            ],
#|            "dynamic_relationships": ext.find("dynamicRelationship") is not None,
#|            "dynamic_properties": ext.find("./dynamicProperties/dynamicProperty") is not None,
#|            "reads_attributes": [_t(a, "name") for a in ext.findall("./readsAttributes/readsAttribute")],
#|            "writes_attributes": [_t(a, "name") for a in ext.findall("./writesAttributes/writesAttribute")],
#|            "input_requirement": _t(ext, "inputRequirement"),
#|            "has_manifest": True,
#|        })
#|    return out
#|
#|
#|def _scan_service_files(z, names):
#|    out = []
#|    for jar_name in (n for n in names if n.endswith(".jar")):
#|        try:
#|            with zipfile.ZipFile(io.BytesIO(z.read(jar_name))) as jar:
#|                jar_names = set(jar.namelist())
#|                for svc, kind in SERVICE_FILES.items():
#|                    if svc in jar_names:
#|                        for line in jar.read(svc).decode("utf-8", "replace").splitlines():
#|                            line = line.split("#", 1)[0].strip()
#|                            if line:
#|                                out.append({"type": line, "kind": kind, "description": "", "tags": [], "properties": {},
#|                                            "relationships": [], "dynamic_relationships": False, "dynamic_properties": False,
#|                                            "reads_attributes": [], "writes_attributes": [], "input_requirement": None,
#|                                            "has_manifest": False, "jar": jar_name})
#|        except zipfile.BadZipFile:
#|            continue
#|    return out
#|
#|
#|class Catalog:
#|    """type name -> extension info, built from all NARs (cached by file size+mtime in the store)."""
#|
#|    def __init__(self):
#|        self.types = {}
#|        self.nars = []
#|        self._jar_strings = {}   # (nar artifact, jar) -> set of string literals
#|
#|    def add(self, nar_info):
#|        nar = nar_info["nar"]
#|        self.nars.append({k: v for k, v in nar.items() if k != "jar_strings"})
#|        for jar, strings in (nar.get("jar_strings") or {}).items():
#|            self._jar_strings[(nar["artifact"], jar)] = set(strings)
#|        for ext in nar_info["extensions"]:
#|            self.types.setdefault(ext["type"], ext)
#|
#|    def get(self, type_name):
#|        return self.types.get(type_name)
#|
#|    def jar_strings(self, deployed_or_type):
#|        """String literals of the deployed classes for an extension (its ext['deployed']) or a type name."""
#|        ext = self.types.get(deployed_or_type) if isinstance(deployed_or_type, str) else None
#|        deployed = (ext or {}).get("deployed") if ext else deployed_or_type
#|        if not deployed:
#|            return set()
#|        nar = (ext or {}).get("nar") or deployed.get("nar")
#|        if nar:
#|            return self._jar_strings.get((nar, deployed["jar"]), set())
#|        return next((s for (_, j), s in self._jar_strings.items() if j == deployed["jar"]), set())
#|
#|    def custom_nars(self):
#|        return [n for n in self.nars if n.get("group") and not n["group"].startswith("org.apache.nifi")]
#|
#|
#|def find_nars(dirs):
#|    seen = []
#|    for d in dirs:
#|        d = Path(d)
#|        if d.is_dir():
#|            seen.extend(sorted(d.rglob("*.nar")))
#|    return seen
#@@ FILE nifikb/cli.py tc 31f6d82512d20770
#|"""Command line: build the knowledge base and answer cheap lookups from it.
#|
#|  python -m nifikb build [--force] [--refresh-db]
#|  python -m nifikb watch [--interval 30]
#|  python -m nifikb status
#|  python -m nifikb search <words...>
#|  python -m nifikb show <name | id prefix | class>
#|  python -m nifikb trace <name | id prefix> [--up] [--depth N]
#|  python -m nifikb sql "SELECT ..." [--db name]
#|  python -m nifikb diagnose [headers...] [--file NAME] [--sample FILE] [--live] [--json]
#|  python -m nifikb issues [--kind K] [--contains TEXT]
#|  python -m nifikb learn add|list|show|for|retire|context   (team learnings in knowledge/)
#|  python -m nifikb logs [--component C] [--file F] [--uuid U] [--grep T] [--level L] [--since H]
#|  python -m nifikb provenance --file F | --uuid U | --component C      (NiFi REST API)
#|  python -m nifikb bulletins
#|  python -m nifikb late                         (feeds whose file is overdue, from the load-audit history)
#|  python -m nifikb ticket INC0012345 [--post]    (Jira / ServiceNow: investigate a ticket, draft the reply)
#|  python -m nifikb target --file F               (HDFS / S3 output + Parquet schema vs structure)
#|  python -m nifikb onboard proposal.toml [--sample f]   (validate config rows for a new feed)
#|  python -m nifikb compare --env uat [--key F]  (flow + config rows vs another environment)
#|  python -m nifikb versions [--group G]         (registry versions: deployed, live state, history)
#|  python -m nifikb report [--hours 24] [--out f.md] [--html f.html] [--send]
#|  python -m nifikb health [--threshold 80]      (NiFi API: queues, back-pressure, invalid processors, disks)
#|  python -m nifikb investigate [--file F] [--feed N] [--table T] [--error TEXT] [--headers ...] [--sample S] [--live]
#|  python -m nifikb doctor [--offline]
#|  python -m nifikb eval [--cases evals/cases.toml] [--agent "gemini -p"] [--save results.json]
#|  python -m nifikb web [--host H] [--port P]   (self-service page for colleagues)
#|  python -m nifikb mcp                      (MCP server on stdio for AI agents)
#|  python -m nifikb init [--nifi-home PATH]
#|"""
#|import argparse
#|import json
#|import sys
#|import time
#|from pathlib import Path
#|
#|from . import __version__
#|from .build import build
#|from .config import PROJECT_DIR, load_config, write_template
#|from .render import tree_lines
#|from .store import Store
#|
#|
#|_OPEN_STORES = []  # closed by main(): the MCP server runs many commands in one long-lived process
#|
#|
#|def _store(cfg):
#|    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
#|    if not path.exists():
#|        sys.exit("Knowledge base not built yet: run `python -m nifikb build`")
#|    store = Store(str(path))
#|    _OPEN_STORES.append(store)
#|    return store
#|
#|
#|def _close_stores():
#|    while _OPEN_STORES:
#|        try:
#|            _OPEN_STORES.pop().db.close()
#|        except Exception:  # already closed
#|            pass
#|
#|
#|def resolve(store, ref):
#|    """Find components by id prefix, exact name, or name substring."""
#|    db = store.db
#|    rows = db.execute("SELECT * FROM components WHERE id LIKE ? OR lower(name)=lower(?)", (ref + "%", ref)).fetchall() if len(ref) >= 4 else []
#|    if not rows:
#|        rows = db.execute("SELECT * FROM components WHERE lower(name)=lower(?)", (ref,)).fetchall()
#|    if not rows:
#|        rows = db.execute("SELECT * FROM components WHERE lower(name) LIKE lower(?) AND kind!='FUNNEL'", (f"%{ref}%",)).fetchall()
#|    return rows
#|
#|
#|def cmd_build(cfg, args):
#|    res = build(cfg, force=args.force, refresh_db=args.refresh_db)
#|    return 0 if res["status"] in ("built", "up-to-date") else 1
#|
#|
#|def cmd_watch(cfg, args):
#|    print(f"Watching every {args.interval}s (Ctrl+C to stop)")
#|    while True:
#|        try:
#|            build(cfg, log=lambda m: print(time.strftime("%H:%M:%S"), m) if "up to date" not in m else None)
#|        except Exception as e:  # keep watching even if one build fails (e.g. flow file mid-write)
#|            print(time.strftime("%H:%M:%S"), f"build failed: {type(e).__name__}: {e}")
#|        time.sleep(args.interval)
#|
#|
#|def cmd_status(cfg, args):
#|    store = _store(cfg)
#|    built = store.get_meta("built_at")
#|    counts = {t: store.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("groups", "components", "connections", "findings", "code_components", "db_tables")}
#|    print(f"built: {time.strftime('%Y-%m-%d %H:%M', time.localtime(built)) if built else 'never'} from {store.get_meta('flow_file')}")
#|    print("  " + ", ".join(f"{k}={v}" for k, v in counts.items()))
#|    for row in store.db.execute("SELECT severity, COUNT(*) n FROM findings GROUP BY severity"):
#|        print(f"  findings {row['severity']}: {row['n']}")
#|    return 0
#|
#|
#|def cmd_search(cfg, args):
#|    store = _store(cfg)
#|    rows = store.search(" ".join(args.terms), args.limit)
#|    if not rows:
#|        print("no matches")
#|    for r in rows:
#|        ref = r["ref"][:8] if r["kind"] in ("processor", "controller_service", "flow", "input_port", "output_port") else r["ref"]
#|        print(f"[{r['kind']}] {r['title']}  ({ref}) -> {r['doc']}\n    {r['snip']}")
#|    return 0
#|
#|
#|def cmd_show(cfg, args):
#|    store = _store(cfg)
#|    rows = resolve(store, args.ref)
#|    if not rows:
#|        code = store.db.execute("SELECT * FROM code_components WHERE fqcn=? OR fqcn LIKE ?", (args.ref, f"%.{args.ref}")).fetchall()
#|        group = store.db.execute("SELECT * FROM groups WHERE lower(name)=lower(?) OR id LIKE ?", (args.ref, args.ref + "%")).fetchall()
#|        target = (code and f"custom-code/{code[0]['fqcn'].rsplit('.', 1)[-1]}.md") or (group and group[0]["doc"])
#|        if target and (Path(cfg["output"]["dir"]) / target).exists():
#|            print((Path(cfg["output"]["dir"]) / target).read_text(encoding="utf-8"))
#|            return 0
#|        tables = store.db.execute("SELECT db, schema_name, name, doc FROM db_tables WHERE lower(name)=lower(?) "
#|                                  "OR lower(schema_name || '.' || name)=lower(?)", (args.ref, args.ref)).fetchall()
#|        for t in tables:
#|            path = Path(cfg["output"]["dir"]) / (t["doc"] or "")
#|            if path.is_file():
#|                print(_table_text(path.read_text(encoding="utf-8"), t["schema_name"], t["name"]))
#|        if tables:
#|            return 0
#|        print(f"nothing named '{args.ref}'")
#|        return 1
#|    if len(rows) > 1 and not any(r["id"].startswith(args.ref) for r in rows):
#|        print(f"{len(rows)} matches, be more specific (or use the id):")
#|        for r in rows[:30]:
#|            print(f"  {r['id'][:8]}  {r['name']} [{(r['type'] or r['kind']).rsplit('.', 1)[-1]}] in {r['group_path']}")
#|        return 1
#|    r = rows[0]
#|    print(r["doc"] or f"{r['name']} [{r['kind']}] `{r['id']}` in {r['group_path']}\n{r['facts']}")
#|    ins = store.db.execute("SELECT c.relationships, s.name, s.id FROM connections c JOIN components s ON s.id=c.source_id WHERE c.dest_id=?", (r["id"],)).fetchall()
#|    outs = store.db.execute("SELECT c.relationships, d.name, d.id FROM connections c JOIN components d ON d.id=c.dest_id WHERE c.source_id=?", (r["id"],)).fetchall()
#|    if not r["doc"]:
#|        for x in ins:
#|            print(f"  from {x['name']} ({x['id'][:8]}) [{x['relationships']}]")
#|        for x in outs:
#|            print(f"  to {x['name']} ({x['id'][:8]}) [{x['relationships']}]")
#|    return 0
#|
#|
#|def _table_text(doc, schema, name):
#|    """A per-table doc as is, or just that table's section of a whole-database doc."""
#|    heads = {f"## {schema}.{name}", f"## {name}"}
#|    lines = doc.splitlines()
#|    start = next((i for i, ln in enumerate(lines) if ln.strip() in heads), None)
#|    if start is None:
#|        return doc
#|    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("## ", "Other tables in schema"))), len(lines))
#|    return "\n".join(lines[start:end]).rstrip()
#|
#|
#|def cmd_trace(cfg, args):
#|    store = _store(cfg)
#|    rows = resolve(store, args.ref)
#|    if len(rows) != 1 and not (rows and rows[0]["id"].startswith(args.ref)):
#|        print("need exactly one component; matches:" if rows else f"nothing named '{args.ref}'")
#|        for r in rows[:30]:
#|            print(f"  {r['id'][:8]}  {r['name']} in {r['group_path']}")
#|        return 1
#|    db = store.db
#|    group_names = {g["id"]: g["name"] for g in db.execute("SELECT id, name FROM groups")}
#|    comps = {c["id"]: dict(c, auto_terminated=json.loads(c["auto_term"] or "[]"), group_name=group_names.get(c["group_id"]))
#|             for c in db.execute("SELECT * FROM components")}
#|    edges = {}
#|    for c in db.execute("SELECT * FROM connections"):
#|        a, b = (c["dest_id"], c["source_id"]) if args.up else (c["source_id"], c["dest_id"])
#|        edges.setdefault(a, []).append((c["relationships"].split(",") if c["relationships"] else [], b))
#|
#|    def get(cid):
#|        c = comps.get(cid)
#|        if c and args.show_groups and c.get("group_name"):
#|            c = dict(c, facts=f"{c['facts']} · PG {c['group_name']}".strip(" ·"))
#|        return c
#|
#|    for line in tree_lines([rows[0]["id"]], get, lambda x: edges.get(x, []), max_depth=args.depth, upstream=args.up):
#|        print(line)
#|    return 0
#|
#|
#|def cmd_sql(cfg, args):
#|    from . import db as dbmod
#|    dbs = cfg.get("databases", [])
#|    if not dbs:
#|        print("no [[databases]] configured in nifikb.toml")
#|        return 1
#|    dcfg = next((d for d in dbs if d["name"] == args.db), None) if args.db else dbs[0]
#|    if not dcfg:
#|        print(f"unknown db '{args.db}'; configured: {', '.join(d['name'] for d in dbs)}")
#|        return 1
#|    try:
#|        cols, rows = dbmod.run_query(dcfg, args.query, args.max_rows)
#|    except dbmod.DbError as e:
#|        print(f"error: {e}")
#|        return 1
#|    widths = [min(40, max([len(str(c))] + [len(str(r[i])) for r in rows])) for i, c in enumerate(cols)]
#|    print(" | ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
#|    print("-+-".join("-" * w for w in widths))
#|    for r in rows:
#|        print(" | ".join(str(v)[:40].ljust(w) for v, w in zip(r, widths)))
#|    print(f"({len(rows)} rows{', truncated' if len(rows) == args.max_rows else ''})")
#|    return 0
#|
#|
#|def _csv(value):
#|    return [x.strip() for x in (value or "").split(",") if x.strip()]
#|
#|
#|def cmd_learn(cfg, args):
#|    from . import learnings as lm
#|    if args.action == "add":
#|        body = args.body
#|        if args.body_file:
#|            body = Path(args.body_file).read_text(encoding="utf-8")
#|        elif body in (None, "-") and not sys.stdin.isatty():
#|            body = sys.stdin.read()
#|        try:
#|            item, warnings = lm.add(cfg, args.title, body, kind=args.kind, tags=_csv(args.tags), applies_to=_csv(args.applies_to),
#|                                    ticket=args.ticket, author=args.author)
#|        except ValueError as e:
#|            print(f"error: {e}")
#|            return 1
#|        index_learning(cfg, item)
#|        print(f"saved {item['path']}")
#|        for w in warnings:
#|            print(f"note: {w}")
#|        return 0
#|    if args.action == "list":
#|        items = [i for i in lm.load_all(cfg, include_obsolete=args.all) if not args.tag or args.tag.lower() in i["tags"]]
#|        if args.json:
#|            print(json.dumps([{k: v for k, v in i.items() if k != "body"} for i in items], indent=2))
#|        else:
#|            for i in items:
#|                print(lm.format_item(i, full=False))
#|            if not items:
#|                print("no learnings yet - add one with: python -m nifikb learn add --title ... --body ...")
#|        return 0
#|    if args.action == "show":
#|        item = lm.get(cfg, args.id)
#|        print(lm.format_item(item) if item else f"no learning '{args.id}'")
#|        return 0 if item else 1
#|    if args.action == "for":
#|        items = lm.relevant(cfg, args.terms, limit=args.limit)
#|        for i in items:
#|            print(lm.format_item(i, full=args.full))
#|        if not items:
#|            print("no matching learnings")
#|        return 0
#|    if args.action == "retire":
#|        try:
#|            item = lm.retire(cfg, args.id, args.reason, args.replaced_by)
#|        except ValueError as e:
#|            print(f"error: {e}")
#|            return 1
#|        index_learning(cfg, item)
#|        print(f"retired {item['id']}")
#|        return 0
#|    if args.action == "suggest":
#|        items = lm.suggestions(cfg, _store(cfg), days=args.days, min_count=args.min_count)
#|        for line in lm.format_suggestions(items):
#|            print(f"- {line}")
#|        if not items:
#|            print("no recurring, unrecorded causes in the recent investigations")
#|        return 0
#|    if args.action == "context":
#|        path = lm.ensure(cfg) / "context.md"
#|        print(path.read_text(encoding="utf-8"))
#|        return 0
#|    return 1
#|
#|
#|def runtime_names(store):
#|    """Runtime (instance) id and flow id -> 'name (Type) in group' for everything in the flow."""
#|    try:
#|        rows = store.db.execute("SELECT id, instance_id, name, type, group_path FROM components").fetchall()
#|    except Exception:  # KB built by an older version: no instance ids yet
#|        rows = [dict(r, instance_id=None) for r in store.db.execute("SELECT id, name, type, group_path FROM components").fetchall()]
#|    out = {}
#|    for r in rows:
#|        label = f"{r['name']} `{r['id'][:8]}` in {r['group_path']}"
#|        out[r["id"]] = label
#|        if r["instance_id"]:
#|            out[r["instance_id"]] = label
#|    return out
#|
#|
#|def component_runtime_ids(store, ref):
#|    ids = []
#|    for r in resolve(store, ref):
#|        ids.append(r["id"])
#|        try:
#|            if r["instance_id"]:
#|                ids.append(r["instance_id"])
#|        except (IndexError, KeyError):
#|            pass
#|    return ids
#|
#|
#|def cmd_logs(cfg, args):
#|    from . import logs as lg
#|    store = _store(cfg)
#|    lg.index(cfg, store, log=lambda m: None)
#|    comp_ids = component_runtime_ids(store, args.component) if args.component else []
#|    if args.component and not comp_ids:
#|        print(f"no component '{args.component}' in the flow")
#|        return 1
#|    rows = lg.query(store, comp_ids, args.file, args.uuid, args.grep, args.level, args.since, args.limit)
#|    newest = store.db.execute("SELECT MAX(ts), COUNT(*) FROM log_events").fetchone()
#|    print(f"log index: {newest[1]} warning / error events, newest {newest[0] or '-'} (grouped by message shape, newest first)")
#|    print(lg.format_rows(rows, runtime_names(store)))
#|    return 0
#|
#|
#|def _api(cfg):
#|    from . import nifiapi
#|    a = nifiapi.settings(cfg)
#|    if not a:
#|        print("NiFi REST API not configured: add [nifi_api] url / username / password_env to nifikb.toml "
#|              "(meanwhile `python -m nifikb logs --file <name>` shows what the logs say)")
#|        return None
#|    return nifiapi.Client(a)
#|
#|
#|def cmd_provenance(cfg, args):
#|    from . import nifiapi
#|    if not (args.file or args.uuid or args.component):
#|        print("give --file <name>, --uuid <FlowFile uuid> or --component <processor>")
#|        return 1
#|    client = _api(cfg)
#|    if not client:
#|        return 1
#|    store = _store(cfg)
#|    names = runtime_names(store)
#|    comp = None
#|    if args.component:
#|        ids = component_runtime_ids(store, args.component)
#|        if not ids:
#|            print(f"no component '{args.component}' in the flow")
#|            return 1
#|        comp = ids[-1]  # the runtime (instance) id when known: that is what provenance records
#|    try:
#|        flows = nifiapi.journey(client, args.file, args.uuid, comp, max_results=args.max)
#|    except nifiapi.NiFiApiError as e:
#|        print(f"error: {e}")
#|        return 1
#|    print(nifiapi.format_journey(flows, names, args.file or args.uuid or args.component))
#|    return 0
#|
#|
#|def cmd_bulletins(cfg, args):
#|    from . import nifiapi
#|    client = _api(cfg)
#|    if not client:
#|        return 1
#|    store = _store(cfg)
#|    try:
#|        print(nifiapi.format_bulletins(client.bulletins(args.limit), runtime_names(store)))
#|    except nifiapi.NiFiApiError as e:
#|        print(f"error: {e}")
#|        return 1
#|    return 0
#|
#|
#|def cmd_investigate(cfg, args):
#|    from . import diagnose as dg, investigate as inv
#|    if not (args.file or args.feed or args.table or args.error):
#|        print("give at least one of --file, --feed, --table, --error")
#|        return 1
#|    store = _store(cfg)
#|    report = inv.investigate(cfg, store, runtime_names(store), file=args.file, feed=args.feed, table=args.table,
#|                             error_text=args.error, headers=dg.split_headers(args.headers), sample_path=args.sample,
#|                             live=args.live, since_hours=args.since)
#|    print(inv.format_report(report))
#|    return 0
#|
#|
#|def cmd_health(cfg, args):
#|    from . import nifiapi
#|    client = _api(cfg)
#|    if not client:
#|        return 1
#|    store = _store(cfg)
#|    try:
#|        h = nifiapi.health(client, bp_threshold=args.threshold, versioned=store.versioned_groups())
#|    except nifiapi.NiFiApiError as e:
#|        print(f"error: {e}")
#|        return 1
#|    print(nifiapi.format_health(h, runtime_names(store)))
#|    return 0
#|
#|
#|def cmd_audit(cfg, args):
#|    from . import audit as auditmod
#|    store = _store(cfg)
#|    model = store.get_meta("audit_model")
#|    if not model:
#|        print("no load-audit table: add [audit] (db, table) to nifikb.toml and run build")
#|        return 1
#|    try:
#|        rows = auditmod.lookup(cfg, model, file=args.file, link_ids=[args.definition] if args.definition else (), limit=args.limit)
#|    except Exception as e:
#|        print(f"error: {e}")
#|        return 1
#|    print(f"load audit table {model['table']} (file column {model['file_column']}, status {model.get('status_column')}, "
#|          f"time {model.get('time_column')}):")
#|    print(auditmod.format_rows(model, rows))
#|    return 0
#|
#|
#|def cmd_report(cfg, args):
#|    from . import report as rp
#|    store = _store(cfg)
#|    r = rp.build_report(cfg, store, runtime_names(store), hours=args.hours)
#|    md = rp.to_markdown(r)
#|    if args.out:
#|        Path(args.out).write_text(md, encoding="utf-8")
#|    if args.html:
#|        Path(args.html).write_text(rp.to_html(r), encoding="utf-8")
#|    if not args.out and not args.html:
#|        print(md)
#|    if args.send:
#|        try:
#|            done = rp.send(cfg, r)
#|        except Exception as e:  # SMTP / webhook failures must be visible
#|            print(f"error sending the report: {type(e).__name__}: {e}")
#|            return 1
#|        print("; ".join(done) if done else "nothing to send: set [report] email_to and / or webhook_url in nifikb.toml")
#|    return 0
#|
#|
#|def cmd_eval(cfg, args):
#|    from . import evals
#|    path = Path(args.cases or Path(cfg["_path"]).parent / "evals" / "cases.toml")
#|    if not path.exists():
#|        print(f"no cases file {path} - copy evals/cases.example.toml to evals/cases.toml and add past tickets")
#|        return 1
#|    store = _store(cfg)
#|    results = evals.run(cfg, store, runtime_names(store), evals.load_cases(path), top=args.top, agent=args.agent)
#|    print(evals.summary(results))
#|    if args.save:
#|        evals.save(results, args.save)
#|    return 0 if all(r["tools_ok"] and r.get("agent_ok", True) for r in results) else 2
#|
#|
#|def cmd_versions(cfg, args):
#|    import datetime as dt
#|    from . import nifiapi
#|    store = _store(cfg)
#|    rows = store.db.execute("SELECT id, instance_id, path, version FROM groups WHERE version IS NOT NULL ORDER BY path").fetchall()
#|    if args.group:
#|        rows = [r for r in rows if args.group.lower() in r["path"].lower() or r["id"].startswith(args.group)]
#|    if not rows:
#|        print("no version-controlled process groups" + (f" matching '{args.group}'" if args.group else ""))
#|        return 1
#|    api = nifiapi.Client(nifiapi.settings(cfg)) if nifiapi.settings(cfg) else None
#|    reg = nifiapi.RegistryClient(nifiapi.registry_settings(cfg)) if nifiapi.registry_settings(cfg) else None
#|    for r in rows:
#|        vc = json.loads(r["version"])
#|        print(f"{r['path']}: registry flow {vc.get('flow_name') or vc.get('flow')} (bucket {vc.get('bucket')}), deployed v{vc.get('version')}")
#|        if api:
#|            try:
#|                st = api.version_state(r["instance_id"] or r["id"])
#|                print(f"  live state: {st.get('state')}" + (f" - {st['stateExplanation']}" if st.get("stateExplanation") else ""))
#|            except nifiapi.NiFiApiError as e:
#|                print(f"  live state not available: {e}")
#|        if reg:
#|            try:
#|                for v in reg.versions(vc.get("bucket_id") or vc.get("bucket"), vc.get("flow"))[:args.limit]:
#|                    when = dt.datetime.fromtimestamp((v.get("timestamp") or 0) / 1000).strftime("%Y-%m-%d %H:%M") if v.get("timestamp") else "?"
#|                    mark = "  <- deployed" if str(v.get("version")) == str(vc.get("version")) else ""
#|                    print(f"  v{v.get('version')}  {when}  {v.get('author') or '?'}: {v.get('comments') or ''}{mark}")
#|            except nifiapi.NiFiApiError as e:
#|                print(f"  registry history not available: {e}")
#|    if not reg:
#|        print("(add [registry] url to nifikb.toml for the version history with authors and comments)")
#|    return 0
#|
#|
#|def cmd_compare(cfg, args):
#|    """Environment comparison: this configuration's flow / config tables vs another environment's."""
#|    from . import compare
#|    from .build import find_flow_file
#|    other = {}
#|    if args.env:
#|        try:
#|            other = compare.environment(cfg, args.env)
#|        except ValueError as e:
#|            print(e)
#|            return 2
#|    right_flow = args.flow or other.get("flow_file")
#|    right_db = args.db or other.get("db")
#|    left_db = args.base_db or (cfg.get("metadata") or {}).get("db")
#|    name = args.env or "other"
#|    if not right_flow and not right_db:
#|        print("nothing to compare: give --env (an [environments.<name>] section) or --flow FILE and / or --db NAME")
#|        return 2
#|    if right_flow and args.what in ("all", "flow"):
#|        print(f"## Flow: this environment vs {name} ({right_flow})")
#|        try:
#|            lines = compare.compare_flows(cfg, find_flow_file(cfg), right_flow, "here", name, limit=args.limit)
#|        except (OSError, ValueError) as e:
#|            lines = [f"cannot read {right_flow}: {e}"]
#|        print("\n".join(f"- {line}" for line in lines) if lines else "- no differences")
#|        print()
#|    if right_db and args.what in ("all", "config"):
#|        print(f"## Config tables: {left_db} vs {right_db}" + (f" (definition matching '{args.key}')" if args.key else ""))
#|        try:
#|            lines = compare.compare_config(cfg, _store(cfg), left_db, right_db, args.key, "here", name)
#|        except Exception as e:  # driver / connection errors: report, do not crash
#|            lines = [f"cannot read the config tables: {type(e).__name__}: {e}"]
#|        print("\n".join(f"- {line}" for line in lines[:args.limit]))
#|        if len(lines) > args.limit:
#|            print(f"- … {len(lines) - args.limit} more")
#|    return 0
#|
#|
#|def cmd_onboard(cfg, args):
#|    """New-feed validator: proposed config rows vs the config tables, existing rows, target table and a sample."""
#|    from . import onboard
#|    try:
#|        proposal = onboard.load_proposal(args.proposal)
#|    except (OSError, ValueError) as e:
#|        print(f"cannot read the proposal {args.proposal}: {e}")
#|        return 2
#|    if args.sample:
#|        proposal["sample"] = args.sample
#|    if args.example:
#|        proposal["example_file"] = args.example
#|    res = onboard.validate(cfg, _store(cfg), proposal, live=args.live)
#|    if args.json:
#|        print(json.dumps(res, indent=1, default=str))
#|    else:
#|        print(onboard.format_report(res))
#|    return 1 if res.get("error") or any(i[0] == "error" for i in res.get("issues", [])) else 0
#|
#|
#|def cmd_target(cfg, args):
#|    """Target side: what the load wrote to the definition's HDFS / S3 location, and its Parquet schema vs the structure."""
#|    from . import diagnose as dg, target
#|    store = _store(cfg)
#|    since = time.time() - args.hours * 3600 if args.hours else None
#|    if args.location:
#|        fields = []
#|        if args.key:
#|            diag = dg.metadata_diagnosis(cfg, store, args.key)
#|            fields = next((d["fields"] for d in diag.get("definitions") or []), [])
#|        try:
#|            print(target.format_check(target.check(cfg, args.location, fields, file=args.file, since=since), args.limit))
#|        except target.TargetError as e:
#|            print(e)
#|            return 1
#|        return 0
#|    key = args.key or args.file
#|    if not key:
#|        print("give --file / --key (a file, feed or table name) or --location")
#|        return 2
#|    diag = dg.metadata_diagnosis(cfg, store, key)
#|    if diag.get("error"):
#|        print(diag["error"])
#|        return 1
#|    model = store.get_meta("metadata_model")
#|    results = target.check_diagnosis(cfg, model, diag, file=args.file, since=since)
#|    if not results:
#|        print(f"no location for '{key}': the definition has no location column / file target"
#|              + ("" if target.settings(cfg).get("location_template") else " - set [targets] location_template, e.g. \"s3://lake/raw/{table}/\""))
#|        return 1
#|    for d, res in results:
#|        print(f"## {d['label']} ({model['definition_table']}:{d['id']})")
#|        print(target.format_check(res, args.limit))
#|    return 1 if any(i[0] == "error" for _, r in results for i in r["issues"]) else 0
#|
#|
#|def cmd_ticket(cfg, args):
#|    """Read a Jira / ServiceNow ticket, investigate what it names, draft a reply (posted only with --post)."""
#|    import shutil
#|    from . import investigate as inv, tickets
#|    try:
#|        t = tickets.settings(cfg)
#|    except tickets.TicketError as e:
#|        print(e)
#|        return 2
#|    if not t:
#|        print("ticket system not configured: add [tickets] kind / url / username / token_env to nifikb.toml")
#|        return 2
#|    store = _store(cfg)
#|    cl = tickets.client(t)
#|    try:
#|        ticket = cl.fetch(args.id)
#|    except tickets.TicketError as e:
#|        print(f"error: {e}")
#|        return 1
#|    facts = tickets.extract(ticket, store, store.get_meta("metadata_model"))
#|    tmp, samples = (None, []) if args.no_attachments else tickets.fetch_samples(cl, ticket)
#|    try:
#|        if not (facts["files"] or facts["feeds"] or facts["tables"] or facts["error"]):
#|            print(f"# {ticket['id']}: {ticket['title']}")
#|            print("no file, feed, table or error text found in the ticket - ask the reporter for the file name and the error")
#|            return 1
#|        report = inv.investigate(cfg, store, runtime_names(store), file=facts["files"][0] if facts["files"] else None,
#|                                 feed=facts["feeds"][0] if facts["feeds"] and not facts["files"] else None,
#|                                 table=facts["tables"][0] if facts["tables"] else None, error_text=facts["error"],
#|                                 headers=facts["headers"], sample_path=samples[0] if samples else None, live=args.live)
#|        print(f"# {ticket['id']}: {ticket['title']}" + (f" [{ticket['status']}]" if ticket.get("status") else ""))
#|        print("extracted: " + "; ".join(f"{k}={v}" for k, v in facts.items() if v)
#|              + (f"; sample attachment={Path(samples[0]).name}" if samples else ""))
#|        print()
#|        print(inv.format_report(report))
#|        built = store.get_meta("built_at")
#|        built = time.strftime("%Y-%m-%d %H:%M", time.localtime(built)) if built else None
#|        draft = tickets.draft_comment(ticket, facts, report, built)
#|        print()
#|        print("## Draft reply" + (" (posting)" if args.post else " (not posted - run again with --post to add it to the ticket)"))
#|        print(draft)
#|        if args.post:
#|            try:
#|                cl.post(ticket, draft)
#|                print(f"posted to {ticket['id']}")
#|            except tickets.TicketError as e:
#|                print(f"posting failed: {e}")
#|                return 1
#|        return 0
#|    finally:
#|        if tmp:
#|            shutil.rmtree(tmp, ignore_errors=True)
#|
#|
#|def cmd_late(cfg, args):
#|    """Feeds whose next file is overdue, judged from their load-audit arrival history."""
#|    from . import late
#|    store = _store(cfg)
#|    try:
#|        items = late.late_files(cfg, store, days=args.days, min_history=args.min_history)
#|    except Exception as e:  # DB down, no time column: say so
#|        print(f"late-file check not available: {e}")
#|        return 1
#|    print("\n".join(f"- {line}" for line in late.format_items(items)))
#|    return 1 if items else 0
#|
#|
#|def cmd_doctor(cfg, args):
#|    from . import doctor
#|    text, fails = doctor.report(doctor.run(cfg, offline=args.offline))
#|    print(text)
#|    return 1 if fails else 0
#|
#|
#|def index_learning(cfg, item):
#|    """Make a new learning searchable at once (the next build re-indexes everything anyway)."""
#|    from . import learnings as lm
#|    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
#|    if not path.exists():
#|        return
#|    store = Store(str(path))
#|    try:
#|        store.db.execute("DELETE FROM search WHERE ref = ?", (item["id"],))
#|        store.insert("search", [d for d in lm.search_docs(cfg) if d["ref"] == item["id"]])
#|        store.set_meta("build_sig", None)  # learnings changed: the next build re-indexes everything
#|    finally:
#|        store.close()
#|
#|
#|def cmd_issues(cfg, args):
#|    store = _store(cfg)
#|    sql, params = "SELECT severity, kind, component_id, location, message FROM findings WHERE 1=1", []
#|    for col in ("kind", "severity"):
#|        if getattr(args, col):
#|            sql += f" AND {col} = ?"
#|            params.append(getattr(args, col))
#|    if args.contains:
#|        sql += " AND message LIKE ?"
#|        params.append(f"%{args.contains}%")
#|    sql += " ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'high' THEN 1 WHEN 'warn' THEN 2 ELSE 3 END, kind LIMIT ?"
#|    params.append(args.limit)
#|    counts = store.db.execute("SELECT severity, kind, COUNT(*) n FROM findings GROUP BY severity, kind ORDER BY n DESC").fetchall()
#|    print("counts: " + (", ".join(f"{r['kind']} {r['severity']} x{r['n']}" for r in counts) or "none"))
#|    rows = store.db.execute(sql, params).fetchall()
#|    for r in rows:
#|        print(f"[{r['severity']}] {r['kind']} {(r['component_id'] or '')[:8] or r['location'] or ''}: {r['message']}")
#|    if not rows:
#|        print("no matching findings")
#|    return 0
#|
#|
#|def cmd_diagnose(cfg, args):
#|    """Support triage: headers / sample payload (+ optional file, table, feed or API name) -> what the flow and the
#|    metadata expect, and what does not match."""
#|    from . import diagnose as dg
#|    store = _store(cfg)
#|    headers = dg.split_headers(args.fields)
#|    if args.key:
#|        result = dg.metadata_diagnosis(cfg, store, args.key, headers, live=args.live, sample_path=args.sample)
#|    elif headers or args.sample:
#|        headers += dg.headers_from_sample(args.sample) if args.sample else []
#|        result = dg.record_diagnosis(store, headers, cfg)
#|    else:
#|        print("give header names, --sample <file>, and/or --file/--table/--feed <name>")
#|        return 1
#|    print(json.dumps(result, indent=2, default=str) if args.json else dg.format_text(result))
#|    if result.get("error") or (result["mode"] == "metadata" and not result.get("matches")):
#|        return 1
#|    return 0
#|
#|
#|def cmd_init(args):
#|    path = Path(args.config or PROJECT_DIR / "nifikb.toml")
#|    write_template(path, args.nifi_home)
#|    print(f"wrote {path}")
#|    return 0
#|
#|
#|def main(argv=None):
#|    try:
#|        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
#|    except (AttributeError, ValueError):
#|        pass
#|    p = argparse.ArgumentParser(prog="nifikb", description=f"NiFi knowledge base {__version__}")
#|    p.add_argument("--config", help="path to nifikb.toml (default: ./nifikb.toml, $NIFIKB_CONFIG, or next to the package)")
#|    sub = p.add_subparsers(dest="cmd", required=True)
#|    b = sub.add_parser("build", help="build / refresh the knowledge base (incremental)")
#|    b.add_argument("--force", action="store_true")
#|    b.add_argument("--refresh-db", action="store_true", help="re-read database schemas now")
#|    w = sub.add_parser("watch", help="rebuild whenever the flow, NARs, code or config change")
#|    w.add_argument("--interval", type=int, default=30)
#|    sub.add_parser("status")
#|    s = sub.add_parser("search", help="full-text search over flows, processors, properties, code, tables")
#|    s.add_argument("terms", nargs="+")
#|    s.add_argument("--limit", type=int, default=15)
#|    sh = sub.add_parser("show", help="details of one component / group / custom class")
#|    sh.add_argument("ref")
#|    t = sub.add_parser("trace", help="downstream (default) or upstream (--up) path from a component, across groups")
#|    t.add_argument("ref")
#|    t.add_argument("--up", action="store_true")
#|    t.add_argument("--depth", type=int, default=40)
#|    t.add_argument("--show-groups", action="store_true", help="append the process group of every node")
#|    q = sub.add_parser("sql", help="read-only query against a configured database")
#|    q.add_argument("query")
#|    q.add_argument("--db")
#|    q.add_argument("--max-rows", type=int, default=100)
#|    d = sub.add_parser("diagnose", help="match a set of incoming field/header names to the record-ingestion "
#|                                        "processor they belong to and report mismatches against its target table")
#|    d.add_argument("fields", nargs="*", help="incoming field/header names, space- or comma-separated")
#|    d.add_argument("--file", "--table", "--feed", "--key", dest="key",
#|                   help="file name, target table, feed or API name to look up in the metadata config tables")
#|    d.add_argument("--sample", help="sample file to take the headers from (CSV/delimited header line, JSON or JSON lines)")
#|    d.add_argument("--live", action="store_true", help="read the metadata tables now instead of the last build's snapshot")
#|    d.add_argument("--json", action="store_true", help="machine-readable output (for agents / scripts)")
#|    iss = sub.add_parser("issues", help="list static findings, filtered")
#|    iss.add_argument("--kind")
#|    iss.add_argument("--severity")
#|    iss.add_argument("--contains", help="substring of the message")
#|    iss.add_argument("--limit", type=int, default=100)
#|    from .learnings import KINDS
#|    lr = sub.add_parser("learn", help="team learnings kept in knowledge/: add, list, show, for, retire, context")
#|    lsub = lr.add_subparsers(dest="action", required=True)
#|    la = lsub.add_parser("add", help="record what was learned (symptom, cause, fix, how to spot it)")
#|    la.add_argument("--title", required=True)
#|    la.add_argument("--body", help="markdown text; '-' or omitted reads stdin")
#|    la.add_argument("--body-file")
#|    la.add_argument("--kind", default="fix", choices=KINDS)
#|    la.add_argument("--tags", help="comma separated")
#|    la.add_argument("--applies-to", help="comma separated: file names / patterns, tables, feeds, processor names or ids, config rows")
#|    la.add_argument("--ticket")
#|    la.add_argument("--author", help="default: $NIFIKB_AUTHOR or the OS user")
#|    ll = lsub.add_parser("list")
#|    ll.add_argument("--tag")
#|    ll.add_argument("--all", action="store_true", help="include retired ones")
#|    ll.add_argument("--json", action="store_true")
#|    ls = lsub.add_parser("show")
#|    ls.add_argument("id")
#|    lf = lsub.add_parser("for", help="learnings relevant to file names, tables, feeds, processors ...")
#|    lf.add_argument("terms", nargs="+")
#|    lf.add_argument("--limit", type=int, default=5)
#|    lf.add_argument("--full", action="store_true")
#|    lre = lsub.add_parser("retire", help="mark a learning obsolete (kept for history)")
#|    lre.add_argument("id")
#|    lre.add_argument("--reason")
#|    lre.add_argument("--replaced-by")
#|    lsub.add_parser("context", help="print knowledge/context.md (creates the template)")
#|    lsg = lsub.add_parser("suggest", help="causes that keep coming back in investigations and have no learning yet")
#|    lsg.add_argument("--days", type=int, default=30)
#|    lsg.add_argument("--min-count", type=int, default=3)
#|    lg = sub.add_parser("logs", help="warnings / errors from nifi-app*.log and nifi-bootstrap*.log (indexed incrementally)")
#|    lg.add_argument("--component", help="processor / service name or id")
#|    lg.add_argument("--file", help="file name (FlowFile name or anywhere in the message)")
#|    lg.add_argument("--uuid", help="FlowFile uuid")
#|    lg.add_argument("--grep", help="text in the message or cause")
#|    lg.add_argument("--level", choices=["WARN", "ERROR", "FATAL", "LIFECYCLE"])
#|    lg.add_argument("--since", type=float, help="hours before the newest indexed event")
#|    lg.add_argument("--limit", type=int, default=30)
#|    pv = sub.add_parser("provenance", help="where FlowFiles went / were dropped (NiFi REST API, [nifi_api])")
#|    pv.add_argument("--file", help="file name (filename attribute)")
#|    pv.add_argument("--uuid", help="FlowFile uuid")
#|    pv.add_argument("--component", help="processor name or id: its recent events")
#|    pv.add_argument("--max", type=int, default=500)
#|    vs = sub.add_parser("versions", help="version-controlled process groups: deployed version, live state, registry history")
#|    vs.add_argument("--group", help="process group name / path / id prefix")
#|    vs.add_argument("--limit", type=int, default=10)
#|    cp = sub.add_parser("compare", help="environment comparison: flow (processors, properties, parameters) and config rows vs UAT / PROD")
#|    cp.add_argument("--env", help="an [environments.<name>] section of nifikb.toml (flow_file, db)")
#|    cp.add_argument("--flow", help="the other environment's flow.json.gz / flow.xml.gz")
#|    cp.add_argument("--db", help="the other environment's [[databases]] name (config tables)")
#|    cp.add_argument("--base-db", help="this environment's config db (default: [metadata] db)")
#|    cp.add_argument("--key", help="only the definition matching this file / feed / table")
#|    cp.add_argument("--what", choices=["all", "flow", "config"], default="all")
#|    cp.add_argument("--limit", type=int, default=300)
#|    ob = sub.add_parser("onboard", help="check proposed config rows for a NEW feed before they are inserted (TOML / JSON proposal)")
#|    ob.add_argument("proposal", help="proposal file: [definition], [[structure]] or structure_csv, [[rows.<TABLE>]] - see README")
#|    ob.add_argument("--sample", help="sample file of the new feed")
#|    ob.add_argument("--example", help="a real file name the definition must match")
#|    ob.add_argument("--live", action="store_true", help="compare with the config rows now instead of the KB snapshot")
#|    ob.add_argument("--json", action="store_true")
#|    tg = sub.add_parser("target", help="what a load wrote to HDFS / S3: files, newest output, Parquet schema vs the structure rows")
#|    tg.add_argument("--file", help="input file name (its definition, and outputs named like it)")
#|    tg.add_argument("--key", help="feed / table / definition name")
#|    tg.add_argument("--location", help="list this location directly (s3://…, hdfs://…, /path)")
#|    tg.add_argument("--hours", type=float, help="warn when nothing was written in the last N hours")
#|    tg.add_argument("--limit", type=int, default=10)
#|    tk = sub.add_parser("ticket", help="Jira / ServiceNow ticket: extract file / feed / error, investigate, draft a reply")
#|    tk.add_argument("id", help="PROJ-123 or INC0012345")
#|    tk.add_argument("--post", action="store_true", help="add the draft to the ticket (Jira comment / ServiceNow work note)")
#|    tk.add_argument("--live", action="store_true", help="read the config rows now")
#|    tk.add_argument("--no-attachments", action="store_true", help="do not download CSV / JSON attachments as samples")
#|    lt = sub.add_parser("late", help="late / missing files: feeds whose next file is overdue (learned from the load audit)")
#|    lt.add_argument("--days", type=int, default=35, help="history window (default 35 days)")
#|    lt.add_argument("--min-history", type=int, default=5, help="arrivals needed before a feed is judged")
#|    rpt = sub.add_parser("report", help="daily health report: new errors, crashes, failed loads, config / flow changes, drift")
#|    rpt.add_argument("--hours", type=float, default=24)
#|    rpt.add_argument("--out", help="write markdown to this file")
#|    rpt.add_argument("--html", help="write HTML to this file")
#|    rpt.add_argument("--send", action="store_true", help="e-mail / post it as configured in [report]")
#|    au = sub.add_parser("audit", help="load-audit rows (status, error, rows, time) of a file or definition ([audit])")
#|    au.add_argument("--file")
#|    au.add_argument("--definition", help="definition id (e.g. OBJ_ID)")
#|    au.add_argument("--limit", type=int, default=10)
#|    he = sub.add_parser("health", help="live flow health: back-pressure, stuck queues, invalid processors, services, disks (NiFi API)")
#|    he.add_argument("--threshold", type=float, default=80.0, help="back-pressure warning level in %% (default 80)")
#|    bl = sub.add_parser("bulletins", help="current NiFi bulletins (errors shown in the UI, last 5 minutes)")
#|    bl.add_argument("--limit", type=int, default=50)
#|    iv = sub.add_parser("investigate", help="one-call ticket investigation: metadata + provenance + logs + code + learnings, ranked")
#|    iv.add_argument("--file", help="file name from the ticket")
#|    iv.add_argument("--feed", help="feed / API name")
#|    iv.add_argument("--table", help="target table")
#|    iv.add_argument("--error", help="error text from the ticket")
#|    iv.add_argument("--headers", nargs="*", help="headers / field names sent, in file order")
#|    iv.add_argument("--sample", help="sample file (CSV / JSON)")
#|    iv.add_argument("--live", action="store_true", help="read the config rows now")
#|    iv.add_argument("--since", type=float, default=72, help="hours of processor log errors to include (default 72)")
#|    dr = sub.add_parser("doctor", help="check the installation: config, NiFi files, repos, databases, metadata, agents, KB freshness")
#|    dr.add_argument("--offline", action="store_true", help="skip database connections")
#|    ev = sub.add_parser("eval", help="replay past tickets with known causes: do the tools (and the model) find them?")
#|    ev.add_argument("--cases", help="default evals/cases.toml")
#|    ev.add_argument("--top", type=int, help="the true cause must be within the top N ranked causes (default: per case, 3)")
#|    ev.add_argument("--agent", help='model CLI to answer from the report, e.g. "gemini -p" (prompt on stdin, or {prompt_file})')
#|    ev.add_argument("--save", help="write results as JSON")
#|    wb = sub.add_parser("web", help="self-service web page for colleagues: investigate, daily report, health, search, learnings")
#|    wb.add_argument("--host", help="default [web] host or 127.0.0.1")
#|    wb.add_argument("--port", type=int, help="default [web] port or 8765")
#|    sub.add_parser("mcp", help="run the MCP server on stdio (for Claude Code, Gemini CLI and other MCP clients)")
#|    i = sub.add_parser("init", help="write a starter nifikb.toml")
#|    i.add_argument("--nifi-home", default="D:/Sanjay/nifi-1.27.0")
#|    args = p.parse_args(argv)
#|    if args.cmd == "init":
#|        return cmd_init(args)
#|    if args.cmd == "web":
#|        from .web import serve as serve_web
#|        serve_web(load_config(args.config), args.host, args.port)
#|        return 0
#|    if args.cmd == "mcp":
#|        from .mcp import serve
#|        for stream in (sys.stdin, sys.stdout):
#|            try:
#|                stream.reconfigure(encoding="utf-8")
#|            except (AttributeError, ValueError):
#|                pass
#|        serve(args.config)
#|        return 0
#|    cfg = load_config(args.config)
#|    try:
#|        return {"build": cmd_build, "watch": cmd_watch, "status": cmd_status, "search": cmd_search, "show": cmd_show,
#|                "trace": cmd_trace, "sql": cmd_sql, "diagnose": cmd_diagnose, "issues": cmd_issues, "learn": cmd_learn,
#|                "doctor": cmd_doctor, "logs": cmd_logs,
#|                "provenance": cmd_provenance, "bulletins": cmd_bulletins, "investigate": cmd_investigate,
#|                "health": cmd_health, "audit": cmd_audit, "report": cmd_report, "eval": cmd_eval,
#|                "versions": cmd_versions, "compare": cmd_compare,
#|                "onboard": cmd_onboard, "target": cmd_target,
#|                "ticket": cmd_ticket, "late": cmd_late}[args.cmd](cfg, args)
#|    finally:
#|        _close_stores()
#@@ FILE nifikb/code.py tc ab64b8fc56afc67e
#|"""Index custom processor code and scripts: NiFi component metadata plus hardcoded values and SQL tables.
#|
#|Parsing is regex based on purpose (no JDK / parser dependency). It targets the idioms NiFi components are
#|written with (PropertyDescriptor.Builder, Relationship.Builder, @CapabilityDescription, session.putAttribute).
#|"""
#|import re
#|from pathlib import Path
#|
#|from . import sqlparse
#|from .util import (HOST_RE, IP_RE, JDBC_RE, SECRET_ASSIGN_RE, SECRET_NAME, UNIX_PATH_RE, URL_RE, WIN_PATH_RE, REDACTED, clip,
#|                   redact_secrets)
#|
#|LANGS = {
#|    ".java": "java", ".groovy": "groovy", ".kt": "kotlin", ".scala": "scala",
#|    ".py": "python", ".sh": "shell", ".bash": "shell", ".ps1": "powershell", ".bat": "batch", ".cmd": "batch",
#|    ".sql": "sql", ".js": "javascript", ".rb": "ruby",
#|    ".properties": "config", ".yaml": "config", ".yml": "config", ".conf": "config", ".cfg": "config", ".ini": "config",
#|}
#|SKIP_DIRS = {".git", ".svn", ".idea", ".vscode", "target", "build", "out", "node_modules", "__pycache__", ".gradle",
#|             "dist", ".mvn", "venv", ".venv", ".tox"}
#|MAX_BYTES = 2_000_000
#|JVM = {"java", "groovy", "kotlin", "scala"}
#|
#|PARSER_VERSION = "4"  # bump when index_file output changes, so cached per-file results are re-parsed
#|
#|STR_LIT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
#|PKG_RE = re.compile(r"^\s*package\s+([\w.]+)", re.M)
#|DECL_RE = re.compile(
#|    r"^[ \t]*(?:@[\w.]+(?:\([^)\n]*\))?\s+)*((?:(?:public|protected|private|abstract|final|static|sealed|non-sealed|strictfp)\s+)*)"
#|    r"(class|interface|enum|record)\s+(\w+)(?:\s*<[^>{]*>)?(?:\s*\([^)]*\))?"
#|    r"(?:\s+extends\s+([\w.<>, ?]+?))?(?:\s+implements\s+([\w.<>, ?]+?))?\s*\{", re.M)
#|PD_RE = re.compile(r"(?:(\w+)\s*=\s*)?new\s+PropertyDescriptor\.Builder\(\)(.*?)\.build\(\)", re.S)
#|REL_RE = re.compile(r"(?:(\w+)\s*=\s*)?new\s+Relationship\.Builder\(\)(.*?)\.build\(\)", re.S)
#|ALLOWABLE_RE = re.compile(r"(\w+)\s*=\s*new\s+AllowableValue\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+|[\w.]+)")
#|ARG = r"((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+|[\w.]+(?:\(\))?)"
#|PUT_ATTR_RE = re.compile(r"putAttribute\(\s*[\w.()]+\s*,\s*" + ARG + r"\s*,")
#|REMOVE_ATTR_RE = re.compile(r"removeAttribute\(\s*[\w.()]+\s*,\s*" + ARG + r"\s*\)")
#|GET_ATTR_RE = re.compile(r"getAttribute\(\s*" + ARG + r"\s*\)")
#|PUT_ALL_RE = re.compile(r"putAllAttributes\(\s*[\w.()]+\s*,\s*(\w+)\s*\)")
#|CONST_RE = re.compile(r"(?:(?:public|protected|private|static|final)\s+)+String\s+([A-Z][A-Z0-9_]*)\s*=\s*"
#|                      r"((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+|[\w.]+)\s*;")
#|IFACE_CONST_RE = re.compile(r"^\s*String\s+([A-Z][A-Z0-9_]*)\s*=\s*((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+)\s*;", re.M)
#|ENUM_CONST_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*\(\s*\"([^\"]+)\"", re.M)
#|ANNOT_STR_RE = r"@{}\s*\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)\)"
#|TAGS_RE = re.compile(r"@Tags\s*\(\s*\{([^}]*)\}\s*\)")
#|WRITES_RE = re.compile(r"@WritesAttribute\s*\(\s*attribute\s*=\s*\"([^\"]+)\"(?:\s*,\s*description\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+))?")
#|READS_RE = re.compile(r"@ReadsAttribute\s*\(\s*attribute\s*=\s*\"([^\"]+)\"(?:\s*,\s*description\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+))?")
#|DYNPROP_RE = re.compile(r"@DynamicProperty\s*\((.*?)\)\s*(?=@|public|protected|private|abstract|final|class)", re.S)
#|INPUT_REQ_RE = re.compile(r"@InputRequirement\s*\(\s*(?:InputRequirement\.)?Requirement\.(\w+)")
#|FLAG_ANNOTS = ("SupportsBatching", "TriggerSerially", "TriggerWhenEmpty", "Stateful", "Restricted", "SideEffectFree",
#|               "PrimaryNodeOnly", "DefaultSchedule", "RequiresInstanceClassLoading", "Deprecated")
#|METHOD_RE = re.compile(r"^\s*(?:@\w+\s*)*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\(", re.M)
#|MESSAGE_RE = re.compile(r"(?:\b(?:log|logger|LOG|LOGGER)|getLogger\(\))\s*\.\s*(error|warn|info|debug)\(\s*"
#|                        r"((?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+)(?:\s*\+\s*(?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+))*)")
#|THROW_RE = re.compile(r"throw\s+new\s+(\w+(?:Exception|Error))\(\s*"
#|                      r"((?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+)(?:\s*\+\s*(?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+))*)")
#|PY_MESSAGE_RE = re.compile(r"(?:\b(?:logging|log|logger|LOG|LOGGER)\.(error|warning|warn|info|exception|critical)\(\s*f?[\"']([^\"'\n]+)[\"']"
#|                           r"|\braise\s+(\w+)\(\s*f?[\"']([^\"'\n]+)[\"'])")
#|PY_DEF_RE = re.compile(r"^\s*def\s+(\w+)\s*\(", re.M)
#|PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
#|NIFI_BASES = ("Processor", "ControllerService", "ReportingTask", "RecordReader", "RecordSetWriter")
#|CORE_ATTRIBUTE_KEYS = {"FILENAME": "filename", "PATH": "path", "ABSOLUTE_PATH": "absolute.path", "UUID": "uuid",
#|                       "MIME_TYPE": "mime.type", "DISCARD_REASON": "discard.reason", "ALTERNATE_IDENTIFIER": "alternate.identifier",
#|                       "PRIORITY": "priority"}
#|IO_PATTERNS = {
#|    "jdbc": r"DBCPService|getConnection\(|PreparedStatement|DriverManager|JdbcTemplate|ResultSet\b",
#|    "sftp/ssh": r"JSch|ChannelSftp|SSHClient|SFTPClient|SftpClient|com\.jcraft|SFTPTransfer|net\.schmizz",
#|    "http": r"HttpClient|HttpURLConnection|OkHttpClient|RestTemplate|WebClient|HttpGet\b|HttpPost\b|WebClientService",
#|    "s3": r"AmazonS3|S3Client|PutObjectRequest|GetObjectRequest",
#|    "kafka": r"KafkaProducer|KafkaConsumer",
#|    "file system": r"Files\.(?:write|move|copy|delete|newBufferedWriter|readAllLines|lines|walk|list)\(|new File\(|FileInputStream|FileOutputStream",
#|    "json": r"ObjectMapper|JsonNode|Gson\b|JSONObject|JsonPath",
#|    "records": r"RecordReaderFactory|RecordSetWriterFactory",
#|    "shell": r"ProcessBuilder|Runtime\.getRuntime\(\)\.exec",
#|    "email": r"javax\.mail|jakarta\.mail|Transport\.send",
#|    "cache": r"DistributedMapCacheClient|MapCacheClient",
#|    "state": r"getStateManager|StateManager\b",
#|    "spark": r"SparkSession|SparkLauncher|spark-submit",
#|}
#|
#|
#|def _concat(s):
#|    """Join "a" + "b" string concatenations into one literal."""
#|    return "".join(m.group(1) for m in STR_LIT.finditer(s)).replace('\\"', '"').replace("\\n", " ")
#|
#|
#|def _template(expr):
#|    """"File " + name + " not found" -> 'File {} not found' (log / exception message templates)."""
#|    parts = re.split(r"\s*\+\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", expr)
#|    out = []
#|    for p in parts:
#|        p = p.strip()
#|        m = STR_LIT.fullmatch(p)
#|        out.append(m.group(1).replace('\\"', '"').replace("\\n", " ") if m else "{}")
#|    return re.sub(r"(\{\}\s*)+", "{} ", "".join(out)).strip()
#|
#|
#|def _arg(expr, consts):
#|    """Value of a builder / call argument: a literal, a (qualified) constant, Enum.X.key() or CoreAttributes.X.key().
#|    Unresolved constants come back as '@ref:Name' and are resolved across files by CodeIndex."""
#|    if expr is None:
#|        return None
#|    expr = expr.strip()
#|    if expr.startswith('"'):
#|        return _concat(expr)
#|    m = re.fullmatch(r"(?:[\w.]*\.)?CoreAttributes\.(\w+)\.key\(\)", expr)
#|    if m:
#|        return CORE_ATTRIBUTE_KEYS.get(m.group(1), m.group(1).lower())
#|    ref = re.sub(r"\.(?:key|getKey|value|getValue|getName|name|toString)\(\)$", "", expr)
#|    if not re.fullmatch(r"[\w.]+", ref) or not re.search(r"[A-Z]", ref.split(".")[-1][:1]):
#|        return None
#|    return consts.get(ref) or consts.get(ref.split(".")[-1]) or f"@ref:{ref}"
#|
#|
#|def _call(builder, name, consts=None):
#|    m = re.search(r"\.{}\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+|[\w.]+(?:\(\))?)\s*\)".format(name), builder, re.S)
#|    return _arg(m.group(1), consts or {}) if m else None
#|
#|
#|def _lineno(text, pos):
#|    return text.count("\n", 0, pos) + 1
#|
#|
#|def iter_code_files(roots):
#|    for root in roots:
#|        root = Path(root)
#|        if root.is_file():
#|            yield root
#|            continue
#|        if not root.is_dir():
#|            continue
#|        stack = [root]
#|        while stack:
#|            d = stack.pop()
#|            try:
#|                entries = sorted(d.iterdir())
#|            except OSError:
#|                continue
#|            for e in entries:
#|                if e.is_dir():
#|                    if e.name not in SKIP_DIRS:
#|                        stack.append(e)
#|                elif (e.suffix.lower() in LANGS or e.name == "pom.xml" or "META-INF" in e.parts and "services" in e.parts) \
#|                        and e.stat().st_size <= MAX_BYTES:
#|                    yield e
#|
#|
#|def index_file(path):
#|    """Everything worth knowing about one source file, JSON-serializable."""
#|    path = Path(path)
#|    text = path.read_text(encoding="utf-8", errors="replace")
#|    lang = "pom" if path.name == "pom.xml" else "services" if "META-INF" in path.parts else LANGS.get(path.suffix.lower(), "other")
#|    info = {"path": str(path), "lang": lang, "lines": text.count("\n") + 1, "components": [], "hardcoded": [],
#|            "tables": [], "functions": [], "imports": [], "is_test": bool(re.search(r"[\\/]src[\\/](?:test|it|integration-test)[\\/]", str(path))
#|                                                                             or re.match(r"test_\w+\.py$", path.name))}
#|    if lang == "pom":
#|        info["artifact"] = _pom_artifact(text)
#|        return info
#|    if lang == "services":
#|        info["service_classes"] = [ln.split("#")[0].strip() for ln in text.splitlines() if ln.split("#")[0].strip()]
#|        return info
#|    if lang in JVM:
#|        info["package"] = (PKG_RE.search(text) or [None, None])[1]
#|        info.update(_jvm_file(text, info["package"]))
#|        info["functions"] = sorted(set(METHOD_RE.findall(text)))[:80]
#|    elif lang == "python":
#|        info["functions"] = PY_DEF_RE.findall(text)[:80]
#|        info["imports"] = sorted({a or b for a, b in PY_IMPORT_RE.findall(text)})
#|        info["messages"] = [{"level": lvl, "text": re.sub(r"\{[^}]*\}|%[sdrf]", "{}", msg), "line": _lineno(text, m.start())}
#|                            for m in PY_MESSAGE_RE.finditer(text) for lvl, msg in [(m.group(1) or m.group(3) or "print", m.group(2) or m.group(4))]
#|                            if msg and len(msg) >= 4][:200]
#|    if "spark-submit" in text:
#|        info["spark"] = spark_submits(text)
#|    info["hardcoded"] = scan_hardcoded(text, lang)
#|    info["tables"] = sorted({t for h in info["hardcoded"] if h["kind"] == "sql" for t in h.get("tables", [])})
#|    return info
#|
#|
#|def spark_submits(text):
#|    """spark-submit calls in a shell / Python script: class, app (jar / .py), name, master, deploy mode, first arguments."""
#|    starts = [m.start() for m in re.finditer(r"spark-submit", text)]
#|    joined = re.sub(r"\\\r?\n\s*", " ", text)  # shell line continuations
#|    out = []
#|    for n, m in enumerate(re.finditer(r"spark-submit\b([^\n;&|]*)", joined)):
#|        toks = [t.strip("\"',[]() \t") for t in re.findall(r"\"[^\"]*\"|'[^']*'|[^\s,]+", m.group(1))]
#|        toks = [t for t in toks if t]
#|        opts, app, args, i = {}, None, [], 0
#|        while i < len(toks):
#|            t = toks[i]
#|            if app is None and t.startswith("--"):
#|                if "=" in t:
#|                    k, v = t[2:].split("=", 1)
#|                    opts.setdefault(k, v)
#|                    i += 1
#|                elif t[2:] in ("verbose", "supervise") or i + 1 >= len(toks):
#|                    i += 1
#|                else:
#|                    opts.setdefault(t[2:], toks[i + 1])
#|                    i += 2
#|                continue
#|            if app is None:
#|                app = t
#|            else:
#|                args.append(t)
#|            i += 1
#|        out.append({"line": _lineno(text, starts[n]) if n < len(starts) else None, "class": opts.get("class"), "name": opts.get("name"),
#|                    "master": opts.get("master"), "deploy_mode": opts.get("deploy-mode"), "queue": opts.get("queue"), "app": app,
#|                    "args": [redact_secrets(a) for a in args[:8]]})
#|    return out
#|
#|
#|def spark_label(s):
#|    what = s.get("class") or s.get("app") or "?"
#|    return (f"{what}" + (f" in {s['app']}" if s.get("class") and s.get("app") else "")
#|            + (f" ({', '.join(x for x in [s.get('master') or '', s.get('deploy_mode') or ''] if x)})" if s.get("master") or s.get("deploy_mode") else ""))
#|
#|
#|def _pom_artifact(text):
#|    parent = re.search(r"<parent>(.*?)</parent>", text, re.S)
#|    body = re.sub(r"<parent>.*?</parent>", "", text, flags=re.S)
#|    deps_block = " ".join(re.findall(r"<dependencies>(.*?)</dependencies>", body, re.S))
#|    body = re.sub(r"<(dependencies|dependencyManagement|build|profiles|reporting)>.*?</\1>", "", body, flags=re.S)
#|
#|    def tag(block, name):
#|        m = re.search(rf"<{name}>\s*([^<]+?)\s*</{name}>", block or "")
#|        return m.group(1) if m else None
#|
#|    return {"artifactId": tag(body, "artifactId"), "groupId": tag(body, "groupId") or tag(parent.group(1) if parent else "", "groupId"),
#|            "version": tag(body, "version") or tag(parent.group(1) if parent else "", "version"),
#|            "packaging": tag(body, "packaging") or "jar", "name": tag(body, "name"),
#|            "modules": re.findall(r"<module>\s*([^<]+?)\s*</module>", body),
#|            "dependencies": re.findall(r"<artifactId>\s*([^<]+?)\s*</artifactId>", deps_block)}
#|
#|
#|def _header(text, pos):
#|    """Annotations / javadoc that belong to the declaration at pos: back to the previous statement or closing-brace line
#|    (string literals are masked so a ';' inside @CapabilityDescription("...") does not cut the header)."""
#|    window = text[max(0, pos - 8000): pos]
#|    masked = re.sub(r'"(?:[^"\\\n]|\\.)*"', lambda m: '"' + " " * (len(m.group(0)) - 2) + '"', window)
#|    cut = masked.rfind(";")
#|    for m in re.finditer(r"\n[ \t]*\}[ \t]*(?=\n)", masked):
#|        cut = max(cut, m.end() - 1)
#|    return window[cut + 1:]
#|
#|
#|def _members(text, consts):
#|    """Property descriptors, relationships and attribute reads / writes found anywhere in the file."""
#|    allowable = {f: _arg(v, consts) for f, v in ALLOWABLE_RE.findall(text)}
#|    props = []
#|    for pm in PD_RE.finditer(text):
#|        b = pm.group(2)
#|        svc = re.search(r"\.identifiesControllerService\(\s*([\w.]+)\.class", b)
#|        av = re.search(r"\.allowableValues\(([^;]*?)\)\s*(?:\.|$)", b, re.S)
#|        values = []
#|        if av and ".class" not in av.group(1):
#|            for a in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", av.group(1)):
#|                a = a.strip()
#|                if a:
#|                    values.append(allowable.get(a) or allowable.get(a.split(".")[-1]) or _arg(a, consts))
#|        default = _call(b, "defaultValue", consts)
#|        dm = re.search(r"\.defaultValue\(\s*([\w.]+)\.getValue\(\)\s*\)", b)
#|        if dm:
#|            default = allowable.get(dm.group(1).split(".")[-1]) or default
#|        props.append({
#|            "field": pm.group(1), "name": _call(b, "name", consts), "displayName": _call(b, "displayName", consts),
#|            "description": _call(b, "description", consts) or "", "default": default,
#|            "required": bool(re.search(r"\.required\(\s*true", b)), "sensitive": bool(re.search(r"\.sensitive\(\s*true", b)),
#|            "el": bool(re.search(r"\.expressionLanguageSupported\(\s*(true|ExpressionLanguageScope\.(?!NONE))", b)),
#|            "service": svc.group(1) if svc else None, "allowable": [v for v in values if v],
#|            "line": _lineno(text, pm.start()),
#|        })
#|    rels = [{"field": rm.group(1), "name": _call(rm.group(2), "name", consts), "description": _call(rm.group(2), "description", consts) or "",
#|             "line": _lineno(text, rm.start())} for rm in REL_RE.finditer(text)]
#|    writes, dynamic = {}, False
#|    for m in PUT_ATTR_RE.finditer(text):
#|        v = _arg(m.group(1), consts)
#|        if v:
#|            writes.setdefault(v, _lineno(text, m.start()))
#|        else:
#|            dynamic = True
#|    for var in set(PUT_ALL_RE.findall(text)):
#|        for m in re.finditer(rf"\b{re.escape(var)}\s*\.\s*put\(\s*" + ARG + r"\s*,", text):
#|            v = _arg(m.group(1), consts)
#|            if v:
#|                writes.setdefault(v, _lineno(text, m.start()))
#|        if re.search(rf"\b{re.escape(var)}\s*\.\s*put\(\s*(?!\"|[A-Z][\w.]*\s*,|[\w.]+\.(?:key|getKey)\(\)\s*,)", text) or \
#|                re.search(rf"\b{re.escape(var)}\s*\.\s*putAll\(", text):
#|            dynamic = True
#|    if "putAllAttributes" in text and not PUT_ALL_RE.search(text):
#|        dynamic = True
#|    reads = {}
#|    for m in GET_ATTR_RE.finditer(text):
#|        v = _arg(m.group(1), consts)
#|        if v:
#|            reads.setdefault(v, _lineno(text, m.start()))
#|    removes = sorted({v for v in (_arg(m.group(1), consts) for m in REMOVE_ATTR_RE.finditer(text)) if v})
#|    return {"properties": props, "relationships": rels, "writes": writes, "reads": reads, "removes": removes, "dynamic_writes": dynamic}
#|
#|
#|def _jvm_file(text, package):
#|    """Classes (with annotations and super types), constants, members, I/O, log / exception messages of one JVM file."""
#|    consts = {}
#|    for name, v in CONST_RE.findall(text) + IFACE_CONST_RE.findall(text):
#|        consts.setdefault(name, REDACTED if SECRET_NAME.search(name) and v.startswith('"')
#|                          else _arg(v, {}) if not v.startswith('"') else _concat(v))
#|    for name, v in ENUM_CONST_RE.findall(text):
#|        consts.setdefault(name, v)
#|    classes = []
#|    for m in DECL_RE.finditer(text):
#|        mods, decl, name = m.group(1) or "", m.group(2), m.group(3)
#|        header = _header(text, m.start()) + text[m.start():m.start(1)]  # + same-line annotations
#|        cap = re.search(ANNOT_STR_RE.format("CapabilityDescription"), header, re.S)
#|        tags = TAGS_RE.search(header)
#|        req = INPUT_REQ_RE.search(header)
#|        dyn = []
#|        for d in DYNPROP_RE.findall(header):
#|            nm = re.search(r'name\s*=\s*"([^"]+)"', d)
#|            ds = re.search(r'description\s*=\s*((?:"(?:[^"\\]|\\.)*"\s*\+?\s*)+)', d)
#|            dyn.append({"name": nm.group(1) if nm else None, "description": _concat(ds.group(1)) if ds else ""})
#|        classes.append({
#|            "class": name, "fqcn": f"{package}.{name}" if package else name, "decl": decl, "line": _lineno(text, m.start(3)),
#|            "top_level": not text[m.start():m.start() + 1].isspace(),
#|            "extends": (m.group(4) or "").strip(), "implements": (m.group(5) or "").strip(), "abstract": "abstract" in mods or decl == "interface",
#|            "description": _concat(cap.group(1)) if cap else "",
#|            "tags": [_concat(t) for t in re.findall(r'"[^"]*"', tags.group(1))] if tags else [],
#|            "input_requirement": req.group(1) if req else None,
#|            "writes_attributes_doc": [{"name": a, "description": _concat(d) if d else ""} for a, d in WRITES_RE.findall(header)],
#|            "reads_attributes_doc": [{"name": a, "description": _concat(d) if d else ""} for a, d in READS_RE.findall(header)],
#|            "dynamic_properties": [d for d in dyn if d["name"] or d["description"]],
#|            "flags": [f for f in FLAG_ANNOTS if re.search(rf"@{f}\b", header)],
#|            "annotated": "@CapabilityDescription" in header or "@Tags" in header,
#|        })
#|    members = _members(text, consts) if classes else {}
#|    messages = []
#|    for m in MESSAGE_RE.finditer(text):
#|        messages.append({"level": m.group(1), "text": _template(m.group(2)), "line": _lineno(text, m.start())})
#|    for m in THROW_RE.finditer(text):
#|        messages.append({"level": m.group(1), "text": _template(m.group(2)), "line": _lineno(text, m.start())})
#|    messages = [msg for msg in messages if len(msg["text"].replace("{}", "").strip()) >= 4][:200]
#|    io = sorted(k for k, rx in IO_PATTERNS.items() if re.search(rx, text))
#|    return {"classes": classes, "consts": consts, "members": members, "messages": messages, "io": io, "components": []}
#|
#|
#|def scan_hardcoded(text, lang):
#|    """Find hardcoded URLs, JDBC strings, hosts, IPs, paths, secrets and SQL, with line numbers (secrets redacted)."""
#|    found, seen = [], set()
#|
#|    def add(kind, value, line_no, line, **extra):
#|        key = (kind, value, line_no)
#|        if key not in seen:
#|            seen.add(key)
#|            found.append({"kind": kind, "value": clip(value, 200), "line": line_no, "code": clip(redact_secrets(line.strip()), 160), **extra})
#|
#|    lines = text.splitlines()
#|    comment = {"python": "#", "shell": "#", "config": "#", "powershell": "#", "ruby": "#", "sql": "--"}.get(lang, "//")
#|    for i, line in enumerate(lines, 1):
#|        stripped = line.strip()
#|        if not stripped or stripped.startswith(comment) or stripped.startswith(("*", "/*", "import ", "package ")):
#|            continue
#|        for m in SECRET_ASSIGN_RE.finditer(line):
#|            value = m.group(2)
#|            if not re.fullmatch(r"[\w.\-]*\$\{.*\}|#\{.*\}|%\(.*|\{\w*\}|<.*>|\*+|changeme|password|secret|null|none|true|false", value, re.I):
#|                add("secret", f"{m.group(1)}={REDACTED}", i, line)
#|        for m in JDBC_RE.finditer(line):
#|            add("jdbc", m.group(0), i, line)
#|        for m in URL_RE.finditer(line):
#|            if "xmlns" not in line and "apache.org/licenses" not in line and "www.w3.org" not in m.group(0):
#|                add("s3" if m.group(0).lower().startswith("s3") else "url", m.group(0), i, line)
#|        for m in re.finditer(r"(?i)bucket\w*\s*(?:=|:|,|\()\s*[\"']([a-z0-9][a-z0-9.\-]{2,62})[\"']", line):
#|            add("s3", m.group(1), i, line)
#|        for m in IP_RE.finditer(line):
#|            if not re.search(r"(?i)version|0\.0\.0\.0|127\.0\.0\.1", line):
#|                add("ip", m.group(0), i, line)
#|        in_strings = " ".join(m.group(1) for m in re.finditer(r"[\"']([^\"']*)[\"']", line)) if lang != "config" else line
#|        for m in HOST_RE.finditer(in_strings):
#|            if not re.search(r"(?i)\.(java|py|class|jar|xml|json|csv|txt)$", m.group(0)) and not URL_RE.search(in_strings):
#|                add("host", m.group(0), i, line)
#|        for rx in (WIN_PATH_RE, UNIX_PATH_RE):
#|            for m in rx.finditer(in_strings):
#|                add("path", m.group(0).strip(), i, line)
#|    for stmt, line_no in _sql_literals(text, lang):
#|        tables = sqlparse.tables(stmt)
#|        if tables:
#|            add("sql", stmt, line_no, lines[line_no - 1] if line_no <= len(lines) else "", tables=tables)
#|    return found
#|
#|
#|def _sql_literals(text, lang):
#|    if lang == "sql":
#|        for m in re.finditer(r"[^;]+", text):
#|            if sqlparse.looks_like_sql(m.group(0)):
#|                yield m.group(0).strip(), _lineno(text, m.start() + len(m.group(0)) - len(m.group(0).lstrip()))
#|        return
#|    # string literals, including Java "a" + "b" concatenations and Python triple quotes
#|    for m in re.finditer(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'|((?:"(?:[^"\\\n]|\\.)*"\s*\+?\s*)+)|\'((?:[^\'\\\n]|\\.)*)\'', text, re.S):
#|        body = m.group(1) or m.group(2) or (_concat(m.group(3)) if m.group(3) else m.group(4)) or ""
#|        if sqlparse.looks_like_sql(body):
#|            yield body.strip(), _lineno(text, m.start())
#|
#|
#|SERVICE_KINDS = {"org.apache.nifi.processor.Processor": "PROCESSOR", "org.apache.nifi.controller.ControllerService": "CONTROLLER_SERVICE",
#|                 "org.apache.nifi.reporting.ReportingTask": "REPORTING_TASK"}
#|
#|
#|class CodeIndex:
#|    """All indexed files, with lookups by fully-qualified class name and by file name.
#|
#|    `finalize()` (after all files are added) resolves constants across files, walks class hierarchies so properties,
#|    relationships and attributes declared in abstract base classes reach the concrete components, applies the
#|    META-INF/services registrations and maps every component to its Maven module and the NAR module that packages it."""
#|
#|    def __init__(self, files=None):
#|        self.files = {}
#|        self.by_fqcn = {}
#|        self.by_basename = {}
#|        self.classes = {}      # fqcn -> (class info, path)
#|        self.modules = {}      # module dir -> pom info
#|        self.registered = {}   # fqcn -> {"kind", "path"}
#|        for info in files or []:
#|            self.add(info)
#|        if files:
#|            self.finalize()
#|
#|    def add(self, info):
#|        path = info["path"]
#|        self.files[path] = info
#|        self.by_basename.setdefault(Path(path).name.lower(), []).append(path)
#|        for c in info.get("classes") or []:
#|            self.classes.setdefault(c["fqcn"], (c, path))
#|        if info.get("lang") == "pom" and info.get("artifact"):
#|            self.modules[str(Path(path).parent)] = info["artifact"]
#|        if info.get("lang") == "services":
#|            kind = SERVICE_KINDS.get(Path(path).name)
#|            for fqcn in info.get("service_classes") or []:
#|                self.registered[fqcn] = {"kind": kind, "path": path}
#|
#|    # ------------------------------------------------------------------------------------------ resolution
#|    def finalize(self):
#|        self._consts()
#|        simple = {}
#|        for fqcn, (c, _) in self.classes.items():
#|            simple.setdefault(c["class"], []).append(fqcn)
#|        self.by_fqcn = {}
#|        for fqcn, (c, path) in sorted(self.classes.items()):
#|            if c["decl"] != "class" or (self.files.get(path) or {}).get("is_test"):
#|                continue
#|            chain = self._ancestors(fqcn, simple)
#|            supers = " ".join(x["extends"] + " " + x["implements"] for x, _ in [(c, path)] + chain)
#|            reg = self.registered.get(fqcn)
#|            if not (reg or c["annotated"] or any(b in supers for b in NIFI_BASES)):
#|                continue
#|            kind = (reg or {}).get("kind") or ("PROCESSOR" if "Processor" in supers else "CONTROLLER_SERVICE" if "Service" in supers
#|                                               else "REPORTING_TASK" if "ReportingTask" in supers else "COMPONENT")
#|            comp = self._component(c, path, chain, kind, reg)
#|            self.by_fqcn[fqcn] = [{"path": path, "line": c["line"], "component": comp}]
#|
#|    def _consts(self):
#|        table, by_simple = {}, {}
#|        for path, info in self.files.items():
#|            top = next((c for c in info.get("classes") or [] if c["top_level"]), None)
#|            for name, v in (info.get("consts") or {}).items():
#|                if top:
#|                    table[f"{top['class']}.{name}"] = v
#|                    table[f"{top['fqcn']}.{name}"] = v
#|                by_simple.setdefault(name, set()).add(v)
#|        self._const_table, self._const_simple = table, {k: next(iter(v)) for k, v in by_simple.items() if len(v) == 1}
#|
#|    def resolve(self, value):
#|        for _ in range(6):
#|            if not isinstance(value, str) or not value.startswith("@ref:"):
#|                return value
#|            ref = value[5:]
#|            parts = ref.split(".")
#|            value = (self._const_table.get(ref) or self._const_table.get(".".join(parts[-2:]))
#|                     or self._const_simple.get(parts[-1]))
#|        return None if isinstance(value, str) and value.startswith("@ref:") else value
#|
#|    def _ancestors(self, fqcn, simple):
#|        out, seen = [], {fqcn}
#|        c, _ = self.classes[fqcn]
#|        while c and c["extends"]:
#|            base = re.sub(r"<.*", "", c["extends"].split(",")[0]).strip()
#|            cands = [base] if base in self.classes else simple.get(base.split(".")[-1], [])
#|            pkg = c["fqcn"].rsplit(".", 1)[0]
#|            nxt = next((x for x in cands if x.startswith(pkg + ".")), cands[0] if len(cands) == 1 else None)
#|            if not nxt or nxt in seen:
#|                break
#|            seen.add(nxt)
#|            c, p = self.classes[nxt]
#|            out.append((c, p))
#|        return out
#|
#|    def _primary_members(self, c, path):
#|        """Member facts of a file belong to its first top-level class."""
#|        info = self.files.get(path) or {}
#|        top = next((x for x in info.get("classes") or [] if x["top_level"]), None)
#|        return (info.get("members") or {}) if top and top["fqcn"] == c["fqcn"] else {}
#|
#|    def _component(self, c, path, chain, kind, reg):
#|        props, rels, writes, reads, removes, io = {}, {}, {}, {}, set(), set()
#|        wdoc, rdoc, dyn, flags, dynamic = {}, {}, [], set(), False
#|        for depth, (cls, p) in enumerate([(c, path)] + chain):
#|            m = self._primary_members(cls, p)
#|            origin = None if depth == 0 else cls["class"]
#|            for pr in m.get("properties", []):
#|                pr = dict(pr, name=self.resolve(pr["name"]), displayName=self.resolve(pr["displayName"]),
#|                          description=self.resolve(pr["description"]) or "", default=self.resolve(pr["default"]),
#|                          allowable=[v for v in (self.resolve(a) for a in pr.get("allowable") or []) if v],
#|                          path=p, **({"from": origin} if origin else {}))
#|                props.setdefault(pr["name"] or pr["field"], pr)
#|            for r in m.get("relationships", []):
#|                r = dict(r, name=self.resolve(r["name"]), description=self.resolve(r["description"]) or "", path=p,
#|                         **({"from": origin} if origin else {}))
#|                rels.setdefault(r["name"] or r["field"], r)
#|            for a, line in (m.get("writes") or {}).items():
#|                a = self.resolve(a)
#|                if a:
#|                    writes.setdefault(a, f"{Path(p).name}:{line}")
#|            for a, line in (m.get("reads") or {}).items():
#|                a = self.resolve(a)
#|                if a:
#|                    reads.setdefault(a, f"{Path(p).name}:{line}")
#|            removes |= {x for x in (self.resolve(a) for a in m.get("removes") or []) if x}
#|            dynamic = dynamic or bool(m.get("dynamic_writes"))
#|            io |= set((self.files.get(p) or {}).get("io") or [])
#|            for w in cls["writes_attributes_doc"]:
#|                wdoc.setdefault(w["name"], w["description"])
#|            for r in cls["reads_attributes_doc"]:
#|                rdoc.setdefault(r["name"], r["description"])
#|            dyn += cls["dynamic_properties"]
#|            flags |= set(cls["flags"])
#|        described = next((x for x, _ in [(c, path)] + chain if x["description"]), c)
#|        module = self.module_of(path)
#|        return {
#|            "class": c["class"], "fqcn": c["fqcn"], "kind": kind, "line": c["line"], "extends": c["extends"], "implements": c["implements"],
#|            "abstract": c["abstract"], "ancestors": [x["fqcn"] for x, _ in chain], "description": described["description"],
#|            "super_chain": [re.sub(r"<.*", "", x["extends"]).strip() for x, _ in [(c, path)] + chain if x["extends"]],
#|            "tags": c["tags"] or next((x["tags"] for x, _ in chain if x["tags"]), []),
#|            "input_requirement": c["input_requirement"] or next((x["input_requirement"] for x, _ in chain if x["input_requirement"]), None),
#|            "registered": bool(reg), "registered_in": (reg or {}).get("path"),
#|            "properties": [v for v in props.values() if v.get("name")], "relationships": [v for v in rels.values() if v.get("name")],
#|            "writes_attributes": sorted(set(writes) | set(wdoc)), "writes_at": writes, "writes_attributes_doc": sorted(wdoc),
#|            "writes_doc": wdoc, "reads_attributes": sorted(set(reads) | set(rdoc)), "reads_at": reads, "reads_attributes_doc": sorted(rdoc),
#|            "removes_attributes": sorted(removes), "dynamic_writes": dynamic, "dynamic_properties": dyn, "flags": sorted(flags),
#|            "io": sorted(io), "module": module, "nar_modules": self.nar_modules_of(module),
#|        }
#|
#|    # -------------------------------------------------------------------------------------------- maven
#|    def module_of(self, path):
#|        p = Path(path).parent
#|        while True:
#|            info = self.modules.get(str(p))
#|            if info:
#|                return dict(info, dir=str(p))
#|            if p.parent == p:
#|                return None
#|            p = p.parent
#|
#|    def nar_modules_of(self, module):
#|        if not module or not module.get("artifactId"):
#|            return []
#|        return [dict(m, dir=d) for d, m in self.modules.items() if m.get("packaging") == "nar"
#|                and (module["artifactId"] in (m.get("dependencies") or []) or d == module.get("dir"))]
#|
#|    def implementers(self, api):
#|        """Concrete classes in the repos implementing a (custom) controller-service interface."""
#|        simple = api.rsplit(".", 1)[-1]
#|        return sorted(fqcn for fqcn, (c, path) in self.classes.items()
#|                      if c["decl"] == "class" and not c["abstract"] and not (self.files.get(path) or {}).get("is_test")
#|                      and simple in re.split(r"[\s,<>]+", c["implements"] + " " + c["extends"]))
#|
#|    def components(self):
#|        return [(fqcn, entries) for fqcn, entries in sorted(self.by_fqcn.items())]
#|
#|    def hardcoded(self):
#|        for path, info in sorted(self.files.items()):
#|            for h in info.get("hardcoded") or []:
#|                yield path, h
#@@ FILE nifikb/compare.py t fab72679d11a0281
#|"""Environment comparison ("works in UAT, fails in PROD"): two flows, and the config tables of two databases.
#|
#|Flows are matched by process-group path + component name + type (ids differ between environments); parameter contexts
#|by name. Config rows are matched by primary key (the metadata model of the current KB), masked on both sides.
#|[environments.<name>] in nifikb.toml gives an environment a flow_file and a db, so `compare --env uat` compares it with the
#|main configuration."""
#|from collections import Counter
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|from .analyze import Analysis, type_short
#|from .catalog import Catalog
#|from .code import CodeIndex
#|from .flow import load_flow
#|from .util import REDACTED, SECRET_NAME
#|
#|
#|def _flow_view(path, cfg):
#|    flow = load_flow(Path(path))
#|    an = Analysis(flow, Catalog(), CodeIndex(), cfg).run()
#|    comps, seen = {}, Counter()
#|    for c in list(flow.components.values()) + list(flow.services.values()):
#|        if c["kind"] not in ("PROCESSOR", "CONTROLLER_SERVICE", "INPUT_PORT", "OUTPUT_PORT"):
#|            continue
#|        base = f"{(flow.groups.get(c['group_id']) or {}).get('path', '(controller)')} :: {c['name']} [{type_short(c['type']) or c['kind'].lower()}]"
#|        seen[base] += 1
#|        key = base if seen[base] == 1 else f"{base} #{seen[base]}"
#|        props = {f["display"]: ("<sensitive>" if f["source"] == "sensitive" else f["resolved"]) for f in an.props[c["id"]]}
#|        comps[key] = {"state": c.get("state"), "schedule": f"{c.get('scheduling_strategy')} {c.get('scheduling_period')}"
#|                      if c["kind"] == "PROCESSOR" else None, "props": props, "auto": sorted(c.get("auto_terminated") or [])}
#|    params = {}
#|    for name, ctx in flow.param_contexts.items():
#|        for k, v in ctx["params"].items():
#|            params[f"{name} :: {k}"] = "<sensitive>" if v.get("sensitive") else (REDACTED if SECRET_NAME.search(k) else v.get("value"))
#|    return comps, params
#|
#|
#|def compare_flows(cfg, left, right, left_name="left", right_name="right", limit=300):
#|    lc, lp = _flow_view(left, cfg)
#|    rc, rp = _flow_view(right, cfg)
#|    out = []
#|    for k in sorted(set(lc) - set(rc)):
#|        out.append(f"only in {left_name}: {k}")
#|    for k in sorted(set(rc) - set(lc)):
#|        out.append(f"only in {right_name}: {k}")
#|    for k in sorted(set(lc) & set(rc)):
#|        a, b = lc[k], rc[k]
#|        for field in ("state", "schedule", "auto"):
#|            if a[field] != b[field]:
#|                out.append(f"{k}: {field} {a[field]} ({left_name}) vs {b[field]} ({right_name})")
#|        for p in sorted(set(a["props"]) | set(b["props"])):
#|            va, vb = a["props"].get(p), b["props"].get(p)
#|            if va != vb and "<sensitive>" not in (va, vb):
#|                out.append(f"{k}: '{p}' = {_v(va)} ({left_name}) vs {_v(vb)} ({right_name})")
#|    for k in sorted(set(lp) | set(rp)):
#|        va, vb = lp.get(k), rp.get(k)
#|        if va != vb and not (va == vb == "<sensitive>"):
#|            if k not in lp or k not in rp:
#|                out.append(f"parameter {k}: only in {left_name if k in lp else right_name}")
#|            elif "<sensitive>" not in (va, vb):
#|                out.append(f"parameter {k} = {_v(va)} ({left_name}) vs {_v(vb)} ({right_name})")
#|    return out[:limit] + ([f"… {len(out) - limit} more differences"] if len(out) > limit else [])
#|
#|
#|def _v(v):
#|    s = "∅" if v is None else str(v)
#|    return f"`{s if len(s) <= 120 else s[:119] + '…'}`"
#|
#|
#|def compare_config(cfg, store, left_db, right_db, key=None, left_name=None, right_name=None):
#|    """Row differences of the metadata config tables between two [[databases]] entries (optionally one file / feed)."""
#|    m = metamod.settings(cfg)
#|    model = store.get_meta("metadata_model")
#|    if not m or not model:
#|        return ["metadata not configured ([metadata] in nifikb.toml) - nothing to compare"]
#|    dbs = {d["name"]: d for d in cfg["databases"]}
#|    for name in (left_db, right_db):
#|        if name not in dbs:
#|            return [f"unknown database '{name}' - [[databases]] names: {', '.join(dbs)}"]
#|    st = model.get("structure_table")
#|    left = metamod.fetch_live(dbs[left_db], m, model)
#|    right = metamod.fetch_live(dbs[right_db], m, model)
#|    ids = None
#|    if key:
#|        found = metamod.dossier(model, metamod.Rows(left), key)["definitions"] or metamod.dossier(model, metamod.Rows(right), key)["definitions"]
#|        ids = [d["id"] for d in found]
#|        if not ids:
#|            return [f"'{key}' matches no definition in either database"]
#|    if st:
#|        if ids is not None:
#|            left[st] = metamod.fetch_structure(dbs[left_db], model, ids)
#|            right[st] = metamod.fetch_structure(dbs[right_db], model, ids)
#|        else:
#|            left[st] = metamod.fetch_rows(dbs[left_db], m, {**model, "tables": {st: model["tables"][st]}}, log=lambda _m: None).get(st, [])
#|            right[st] = metamod.fetch_rows(dbs[right_db], m, {**model, "tables": {st: model["tables"][st]}}, log=lambda _m: None).get(st, [])
#|    changes = metamod.diff_rows(model, left, right)
#|    if ids is not None:
#|        wanted = {str(i) for i in ids}
#|        changes = [c for c in changes if c["link"] in wanted]
#|    ln, rn = left_name or left_db, right_name or right_db
#|    lines = [c["change"].replace(" added:", f" only in {rn}:").replace(" removed", f" only in {ln}") for c in changes]
#|    return [f"differences {ln} → {rn} (rows matched by primary key; secret columns not compared):"] + (lines or ["none"])
#|
#|
#|def environment(cfg, name):
#|    envs = cfg.get("environments") or {}
#|    if name not in envs:
#|        raise ValueError(f"no [environments.{name}] in nifikb.toml (known: {', '.join(envs) or 'none'})")
#|    return envs[name]
#@@ FILE nifikb/config.py tc 061d778e5653e461
#|"""Configuration: nifikb.toml - the only file to edit (paths are relative to it; secrets come from env vars or files)."""
#|import os
#|import tomllib
#|from pathlib import Path
#|
#|PROJECT_DIR = Path(__file__).resolve().parent.parent
#|
#|TEMPLATE = """# =====================================================================================================================
#|# nifikb configuration - the ONLY file you edit.
#|#   * Paths may be absolute or relative to this file; ${{VARS}} are expanded.
#|#   * No secrets in here: passwords come from an environment variable (password_env) or a protected file
#|#     (password_file, chmod 600 on Linux).
#|#   * After editing:  python -m nifikb build   then   python -m nifikb doctor
#|# =====================================================================================================================
#|
#|db_refresh_hours = 24                    # how often table schemas are re-read (build --refresh-db forces it)
#|
#|# ---- 1. NiFi -------------------------------------------------------------------------------------------------------
#|[nifi]
#|home = "{home}"                 # NiFi install folder: conf/flow.json.gz, lib/*.nar and logs/ are read from here
#|# flow_file = "copies/flow.json.gz"      # or a copied flow file, when NiFi runs on another machine
#|extra_nar_dirs = []                      # folders with custom NARs that are not in <home>/lib
#|
#|[logs]                                   # nifi-app*.log / nifi-bootstrap*.log - read incrementally, only warnings / errors kept
#|# dirs = ["/opt/nifi/logs"]              # default: <home>/logs
#|keep_days = 14                           # keep this many days of events (counted back from the newest one)
#|# initial_tail_mb = 200                  # first run on a huge log: only read its last N MB
#|
#|# [nifi_api]                             # optional, read-only: provenance ("where was my file dropped, why") + live bulletins
#|# url = "https://nifi-host:8443/nifi-api"
#|# username = "readonly_user"             # needs the NiFi policies "query provenance" + "view provenance"
#|# password_env = "NIFIKB_NIFI_PASSWORD"  # or: password_file = "~/.nifikb/nifi.pw"
#|# ca_cert = "/etc/pki/nifi-ca.pem"       # CA of NiFi's certificate;  verify_ssl = false only for a quick test
#|# client_cert = "me.pem"                 # instead of username / password when NiFi uses client certificates
#|# client_key = "me.key"
#|# token_env = "NIFIKB_NIFI_TOKEN"        # or a pre-issued bearer token (Kerberos / OIDC setups)
#|
#|# [registry]                             # optional, read-only: NiFi Registry version history (who changed a versioned flow, when, why)
#|# url = "https://registry-host:18443/nifi-registry-api"
#|# username = "readonly_user"
#|# password_env = "NIFIKB_REGISTRY_PASSWORD"
#|# ca_cert = "/etc/pki/nifi-ca.pem"
#|
#|# ---- 2. Code -------------------------------------------------------------------------------------------------------
#|[code]
#|repos = []                               # Bitbucket clones: custom NAR projects (Maven / Java), scripts, Spark job scripts
#|
#|# ---- 3. Databases (read-only users only) ---------------------------------------------------------------------------
#|# One block per database. The flow's DBCP connection pools are matched by host + port + database of their JDBC URL.
#|# [[databases]]
#|# name = "metadata"
#|# kind = "mariadb"                       # mariadb | mysql | postgres | sqlite
#|# host = "db-host"
#|# port = 3306
#|# database = "nifi_meta"
#|# user = "readonly_user"
#|# password_env = "NIFIKB_DB_PASSWORD"    # or: password_file = "~/.nifikb/db.pw"
#|# include_tables = []                    # also document these tables (SQL LIKE / glob patterns, e.g. "file_%")
#|# profile_tables = []                    # list distinct values of low-cardinality text columns (status, source, ...)
#|# sample_rows = 0                        # >0 adds a few masked sample rows per table
#|
#|# ---- 4. Metadata config tables (OBJ_DEFINITION, OBJ_STRUCTURE, feed / API / server config, ...) --------------------
#|# Enables `diagnose` / `investigate` by file / feed / table, a masked snapshot of the config rows, their change history,
#|# and definition checks. Roles and relations are auto-detected: kb/metadata.md shows what was detected - override only
#|# what is wrong.
#|# [metadata]
#|# db = "metadata"                        # the [[databases]] name that holds the config tables
#|# target_db = "none"                     # loads go to HDFS / S3 files: no target-table checks. Or the [[databases]] name
#|#                                        #   holding the load tables, to check definitions against them.
#|# tables = ["OBJ_%", "%_CONFIG", "%_CONFIG_%", "%_DEFINITION", "%_STRUCTURE", "%_METADATA%"]   # which tables are config
#|# refresh_hours = 1                      # re-read the config rows (and record row changes) at most this often
#|# snapshot_max_rows = 20000              # rows per config table kept (masked); structure table: structure_max_rows
#|# --- overrides, only if kb/metadata.md shows a wrong guess:
#|# definition_table = "OBJ_DEFINITION"    # one row per file / object
#|# definition_id = "OBJ_ID"
#|# definition_keys = ["FILE_NAME", "TABLE_NAME"]   # what file / table names are matched against (patterns *, %, YYYYMMDD, regex)
#|# definition_target = "TABLE_NAME"       # the table a file is loaded into
#|# definition_location = "HDFS_PATH"      # the HDFS / S3 location it is written to
#|# structure_table = "OBJ_STRUCTURE"      # one row per column of a definition
#|# structure_parent = "OBJ_ID"
#|# structure_field = "COL_NAME"
#|# structure_type = "DATA_TYPE"
#|# structure_order = "COL_SEQ"
#|# structure_length = "COL_LENGTH"
#|# structure_nullable = "NULLABLE_FLAG"   # a column named like MANDATORY / REQUIRED / NOT_NULL is read as "required"
#|# structure_path = "JSON_PATH"           # JSON path per column for API / JSON feeds ($.data[*].customer.name)
#|# [[metadata.relations]]                 # joins that are not declared as foreign keys
#|# child = "SOURCE_FEED_CONFIG.OBJ_ID"
#|# parent = "OBJ_DEFINITION.OBJ_ID"
#|
#|# ---- 5. Target storage, ticket system, other environments (all optional, all read-only) ----------------------------
#|# [targets]                             # read-only look at what loads wrote (investigate / target): listings + Parquet footer
#|# location_template = "s3://datalake/raw/{{table_lower}}/"   # when OBJ_DEFINITION has no location column: where {{table}} lands
#|# hdfs_url = "https://namenode:9871/webhdfs/v1"   # WebHDFS for hdfs:// and /paths (or leave out to use the `hdfs` CLI)
#|# hdfs_user = "nifikb"                   # simple auth; or kerberos = true (uses `curl --negotiate` with the kinit ticket)
#|# s3_profile = "readonly"                # aws CLI / boto3 profile; s3_endpoint / s3_region for S3-compatible stores
#|# max_download_mb = 200                  # hdfs CLI only: largest file copied to read its Parquet schema
#|
#|# [tickets]                             # Jira / ServiceNow: `ticket <id>` reads it, investigates, drafts a reply
#|# kind = "servicenow"                    # or "jira"
#|# url = "https://acme.service-now.com"   # Jira: "https://acme.atlassian.net" or the Jira Server base URL
#|# username = "nifikb.integration"        # Jira Cloud: the account e-mail (with token_env = API token)
#|# password_env = "NIFIKB_TICKET_PASSWORD"   # or token_env (Jira Server PAT / OAuth token, sent as Bearer when no username)
#|# table = "incident"                     # ServiceNow table
#|# note_field = "work_notes"              # ServiceNow: where --post writes (work_notes = internal)
#|
#|# [environments.uat]                     # other environments for `compare --env uat` ("works in UAT, fails in PROD")
#|# flow_file = "copies/uat/flow.json.gz"  # its flow (copy it over; read-only)
#|# db = "metadata_uat"                    # the [[databases]] name holding its config tables (read-only user)
#|
#|# ---- 6. Load audit, daily report, web page -------------------------------------------------------------------------
#|# [audit]                                # the platform's per-file load log: investigate shows the last load of a file
#|# db = "metadata"                        # [[databases]] name (default: the metadata db)
#|# table = "FILE_LOAD_AUDIT"              # auto-detected (a table named like *audit* / *load_log* with a file-name column)
#|# file_column = "FILE_NAME"              # overrides, only if kb/INDEX / doctor shows a wrong guess:
#|# status_column = "LOAD_STATUS"
#|# time_column = "LOAD_TS"
#|# error_column = "ERROR_MSG"
#|# rows_column = "ROW_COUNT"
#|# link_column = "OBJ_ID"                 # the definition id, to list all loads of one definition
#|
#|# [report]                               # python -m nifikb report --send (e.g. scheduled daily)
#|# email_to = ["nifi-team@company.com"]
#|# email_from = "nifikb@company.com"
#|# smtp_host = "smtp.company.com"
#|# smtp_port = 25
#|# smtp_starttls = false
#|# smtp_user = ""                         # + smtp_password_env / smtp_password_file when the relay needs a login
#|# webhook_url_env = "NIFIKB_WEBHOOK"     # Teams / Slack incoming-webhook URL (kept out of this file)
#|
#|# [web]                                  # python -m nifikb web - self-service page for colleagues (read-only)
#|# host = "127.0.0.1"                     # "0.0.0.0" to reach it from other machines (then set a login)
#|# port = 8765
#|# user = "support"                       # HTTP basic login shared by the team
#|# password_env = "NIFIKB_WEB_PASSWORD"   # or password_file
#|
#|# ---- 7. Where things are written -----------------------------------------------------------------------------------
#|[output]
#|dir = "kb"                               # generated knowledge base (markdown + kb.sqlite) - rebuilt, never edited by hand
#|
#|[knowledge]
#|dir = "knowledge"                        # team context + learnings written by people and agents - kept, commit it to git
#|"""
#|
#|
#|def find_config(path=None):
#|    candidates = [path, os.environ.get("NIFIKB_CONFIG"), Path.cwd() / "nifikb.toml", PROJECT_DIR / "nifikb.toml"]
#|    for c in candidates:
#|        if c and Path(c).is_file():
#|            return Path(c).resolve()
#|    raise FileNotFoundError("nifikb.toml not found (run `python -m nifikb init` or pass --config)")
#|
#|
#|def load_config(path=None):
#|    path = find_config(path)
#|    with open(path, "rb") as f:
#|        cfg = tomllib.load(f)
#|    base = path.parent
#|
#|    def rel(p):
#|        p = Path(os.path.expanduser(os.path.expandvars(str(p))))
#|        return str(p if p.is_absolute() else (base / p).resolve())
#|
#|    for section in ("nifi", "output", "code", "logs", "knowledge"):
#|        cfg.setdefault(section, {})
#|    cfg.setdefault("databases", [])
#|    # an older layout put db_refresh_hours below [code], where TOML files it under code
#|    if "db_refresh_hours" not in cfg and "db_refresh_hours" in cfg["code"]:
#|        cfg["db_refresh_hours"] = cfg["code"].pop("db_refresh_hours")
#|    if cfg["nifi"].get("home"):
#|        cfg["nifi"]["home"] = rel(cfg["nifi"]["home"])
#|    if cfg["nifi"].get("flow_file"):
#|        cfg["nifi"]["flow_file"] = rel(cfg["nifi"]["flow_file"])
#|    cfg["nifi"]["extra_nar_dirs"] = [rel(p) for p in cfg["nifi"].get("extra_nar_dirs", [])]
#|    cfg["output"]["dir"] = rel(cfg["output"].get("dir", "kb"))
#|    cfg["knowledge"]["dir"] = rel(cfg["knowledge"].get("dir", "knowledge"))
#|    cfg["code"]["repos"] = [rel(p) for p in cfg["code"].get("repos", [])]
#|    if cfg["logs"].get("dirs"):
#|        cfg["logs"]["dirs"] = [rel(p) for p in cfg["logs"]["dirs"]]
#|    for d in cfg["databases"]:
#|        if d.get("kind") == "sqlite" and d.get("database"):
#|            d["database"] = rel(d["database"])
#|        if d.get("password_file"):
#|            d["password_file"] = rel(d["password_file"])
#|        d.setdefault("name", d.get("database", "db"))
#|    for key in ("nifi_api", "registry", "targets", "tickets"):
#|        api = cfg.get(key)
#|        if not api:
#|            continue
#|        for k in ("password_file", "token_file", "ca_cert", "client_cert", "client_key", "client_key_password_file"):
#|            if api.get(k):
#|                api[k] = rel(api[k])
#|    for env in (cfg.get("environments") or {}).values():
#|        if isinstance(env, dict) and env.get("flow_file"):
#|            env["flow_file"] = rel(env["flow_file"])
#|    for key in ("web", "report"):
#|        for k in ("password_file", "smtp_password_file", "webhook_url_file"):
#|            if (cfg.get(key) or {}).get(k):
#|                cfg[key][k] = rel(cfg[key][k])
#|    if not cfg["nifi"].get("home") and not cfg["nifi"].get("flow_file"):
#|        raise ValueError(f"{path}: set [nifi] home or flow_file")
#|    cfg["_path"] = str(path)
#|    return cfg
#|
#|
#|def write_template(path, nifi_home):
#|    path = Path(path)
#|    if path.exists():
#|        raise FileExistsError(f"{path} already exists")
#|    path.write_text(TEMPLATE.format(home=str(nifi_home).replace("\\", "/")), encoding="utf-8")
#|    return path
#@@ FILE nifikb/content.py tc dab3483caf40eb70
#|"""Content validation of a sample file against the structure rows: not only the header, every row.
#|
#|Most "metadata" tickets are data-vs-metadata problems: a delimiter inside a value shifting the columns, an empty
#|mandatory field, text in a numeric column, a date in another format, a value longer than the column, a file that is not
#|UTF-8. This reads a sample (CSV / delimited text or JSON) and reports each problem with counts and the first examples.
#|"""
#|import csv
#|import io
#|import re
#|from datetime import datetime
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|
#|DELIM_COL = re.compile(r"(?i)delim|separator|(^|_)sep$|field_?sep")
#|DELIM_NAMES = {"TAB": "\t", "\\T": "\t", "PIPE": "|", "COMMA": ",", "SEMICOLON": ";", "CARET": "^", "TILDE": "~", "SPACE": " "}
#|DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f", "%Y/%m/%d",
#|                "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%m/%d/%Y %H:%M", "%d.%m.%Y", "%Y%m%d", "%Y%m%d%H%M%S", "%d-%b-%Y", "%d-%b-%y",
#|                "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")
#|NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
#|INT_RE = re.compile(r"^[+-]?\d+$")
#|MAX_ROWS = 20000
#|EXAMPLES = 3
#|
#|
#|def delimiter_for(model, def_row, related_rows, sample_text):
#|    """The configured delimiter (a DELIMITER-like column on the definition or a linked row), else sniffed."""
#|    for r in [def_row] + [x for rs in (related_rows or {}).values() for x in rs]:
#|        for c, v in r.items():
#|            if DELIM_COL.search(c) and isinstance(v, str) and v:
#|                v = DELIM_NAMES.get(v.strip().upper(), v)
#|                v = {"\\t": "\t", "\\u0001": "\x01", "\\x01": "\x01"}.get(v, v)
#|                return v, f"configured in {c}"
#|    try:
#|        return csv.Sniffer().sniff(sample_text[:20000], delimiters=",|\t;~^").delimiter, "detected"
#|    except csv.Error:
#|        return ",", "default"
#|
#|
#|def read_text(path):
#|    """(text, notes): UTF-8 with a fallback, noting a BOM, non-UTF-8 bytes and mixed line endings."""
#|    raw = Path(path).read_bytes()[:50_000_000]
#|    notes = []
#|    if raw.startswith(b"\xef\xbb\xbf"):
#|        notes.append({"severity": "warn", "kind": "data-encoding",
#|                      "message": "file starts with a UTF-8 byte-order mark (BOM): the first header can become '\\ufeffNAME' and not match"})
#|    try:
#|        text = raw.decode("utf-8-sig")
#|    except UnicodeDecodeError as e:
#|        text = raw.decode("cp1252", errors="replace")
#|        notes.append({"severity": "error", "kind": "data-encoding",
#|                      "message": f"file is not valid UTF-8 (first bad byte at offset {e.start}); it looks like Windows-1252 / Latin-1 - "
#|                                 "accented characters will be garbled or rejected"})
#|    crlf, lf = raw.count(b"\r\n"), raw.count(b"\n")
#|    if crlf and lf - crlf > 1:
#|        notes.append({"severity": "warn", "kind": "data-encoding", "message": f"mixed line endings ({crlf} CRLF, {lf - crlf} LF)"})
#|    return text, notes
#|
#|
#|def _is_date(v):
#|    v = v.strip()
#|    for fmt in DATE_FORMATS:
#|        try:
#|            datetime.strptime(v, fmt)
#|            return True
#|        except ValueError:
#|            continue
#|    return False
#|
#|
#|class _Col:
#|    def __init__(self, field):
#|        self.f = field
#|        self.problems = {}  # kind -> [count, examples]
#|
#|    def hit(self, kind, row_no, value):
#|        entry = self.problems.setdefault(kind, [0, []])
#|        entry[0] += 1
#|        if len(entry[1]) < EXAMPLES:
#|            entry[1].append(f"row {row_no}: {str(value)[:40]!r}")
#|
#|    def check(self, row_no, value):
#|        f = self.f
#|        v = "" if value is None else str(value)
#|        if v.strip() == "":
#|            if f.get("nullable") is False:
#|                self.hit("data-mandatory", row_no, v)
#|            return
#|        family = metamod.type_family(f.get("type"))
#|        if family == "numeric":
#|            s = v.strip().replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", v.strip()) else v.strip()
#|            if not NUMBER_RE.match(s):
#|                self.hit("data-type", row_no, v)
#|            elif re.search(r"(?i)int|long|short|byte|serial", str(f.get("type"))) and not INT_RE.match(s):
#|                self.hit("data-type", row_no, v)
#|        elif family == "temporal" and not _is_date(v):
#|            self.hit("data-date", row_no, v)
#|        elif family == "bool" and v.strip().lower() not in ("true", "false", "0", "1", "y", "n", "yes", "no", "t", "f"):
#|            self.hit("data-type", row_no, v)
#|        if f.get("length") and len(v) > f["length"]:
#|            self.hit("data-length", row_no, v)
#|
#|    def issues(self, total):
#|        labels = {"data-mandatory": ("error", "is empty but mandatory"), "data-type": ("error", f"is not a valid {self.f.get('type')}"),
#|                  "data-date": ("error", f"is not a recognisable date / time ({self.f.get('type')})"),
#|                  "data-length": ("error", f"is longer than {self.f.get('length')} characters")}
#|        out = []
#|        for kind, (n, ex) in self.problems.items():
#|            sev, what = labels[kind]
#|            out.append({"severity": sev, "kind": kind,
#|                        "message": f"'{self.f['name']}' {what} in {n} of {total} rows (e.g. {'; '.join(ex)})"})
#|        return out
#|
#|
#|def _rows(text, delim, max_rows):
#|    out = []
#|    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim)):
#|        if i > max_rows:
#|            break
#|        if row and any(c.strip() for c in row):
#|            out.append((i + 1, row))
#|    return out
#|
#|
#|def validate_csv(fields, path, model=None, def_row=None, related=None, max_rows=MAX_ROWS):
#|    text, issues = read_text(path)
#|    delim, how = delimiter_for(model or {}, def_row or {}, related, text)
#|    rows = _rows(text, delim, max_rows)
#|    if rows and len(rows[0][1]) == 1 and len(fields) > 1:  # wrong delimiter: find the one the file really uses
#|        for cand in ",|\t;~^\x01":
#|            if cand != delim and len(rows[0][1][0].split(cand)) >= 2:
#|                issues.append({"severity": "error", "kind": "data-delimiter",
#|                               "message": f"the file is delimited by {cand!r}, but the delimiter is {delim!r} ({how}) - every row "
#|                                          "reads as a single column. Checked below with the file's own delimiter.",
#|                               "data": {"delimiter": cand, "column": how[len("configured in "):] if how.startswith("configured in ") else None}})
#|                delim, how, rows = cand, "found in the file", _rows(text, cand, max_rows)
#|                break
#|    if not rows:
#|        return issues + [{"severity": "error", "kind": "data-empty", "message": "the sample has no rows"}], {"delimiter": delim}
#|    names = {f["name"].lower(): f for f in fields}
#|    squash = {re.sub(r"[^a-z0-9]", "", k): f for k, f in names.items()}
#|    header = rows[0][1]
#|    matched = sum(1 for h in header if h.strip().lower() in names or re.sub(r"[^a-z0-9]", "", h.lower()) in squash)
#|    has_header = matched >= max(1, len(header) // 2)
#|    info = {"delimiter": delim, "delimiter_source": how, "header": has_header, "rows": len(rows) - (1 if has_header else 0),
#|            "header_row": [h.strip() for h in header] if has_header else None}
#|    if has_header:
#|        cols = [names.get(h.strip().lower()) or squash.get(re.sub(r"[^a-z0-9]", "", h.lower())) for h in header]
#|        data, width = rows[1:], len(header)
#|    else:
#|        ordered = sorted(fields, key=lambda f: (f["seq"] is None, f["seq"] or 0))
#|        cols, data, width = ordered, rows, len(ordered)
#|        if len(header) != len(ordered):
#|            issues.append({"severity": "error", "kind": "data-width",
#|                           "message": f"no header row and {len(header)} columns in row 1, but the structure has {len(ordered)} fields"})
#|    bad_width, examples = 0, []
#|    checkers = [_Col(f) if f else None for f in cols]
#|    for row_no, row in data:
#|        if len(row) != width:
#|            bad_width += 1
#|            if len(examples) < EXAMPLES:
#|                examples.append(f"row {row_no} has {len(row)}")
#|            continue
#|        for chk, value in zip(checkers, row):
#|            if chk:
#|                chk.check(row_no, value)
#|    if bad_width:
#|        issues.append({"severity": "error", "kind": "data-width",
#|                       "message": f"{bad_width} of {len(data)} rows do not have {width} columns ({'; '.join(examples)}) - a delimiter or "
#|                                  "line break inside a value, or unbalanced quotes"})
#|    for chk in checkers:
#|        if chk:
#|            issues += chk.issues(len(data))
#|    return issues, info
#|
#|
#|def validate_json(fields, records, root=None, max_rows=MAX_ROWS):
#|    """records: the list below the root path. Fields compared by (dotted) path relative to the root."""
#|    issues, total = [], 0
#|    prefix = metamod.json_path(root) + "." if root and metamod.json_path(root) else ""
#|
#|    def rel(f):
#|        p = metamod.json_path(f.get("path") or f["name"])
#|        return p[len(prefix):] if prefix and p.startswith(prefix) else p
#|
#|    checkers = {rel(f): _Col(f) for f in fields}
#|    missing = {k: 0 for k in checkers}
#|    for i, rec in enumerate(records[:max_rows], 1):
#|        if not isinstance(rec, dict):
#|            continue
#|        total += 1
#|        flat = _flatten_values(rec)
#|        for path, chk in checkers.items():
#|            key = next((k for k in flat if k.lower() == path.lower() or k.lower().endswith("." + path.lower())), None)
#|            if key is None:
#|                missing[path] += 1
#|                if chk.f.get("nullable") is False:
#|                    chk.hit("data-mandatory", i, "<missing>")
#|                continue
#|            chk.check(i, flat[key])
#|    for path, n in missing.items():
#|        if 0 < n < total and checkers[path].f.get("nullable") is not False:
#|            issues.append({"severity": "warn", "kind": "data-missing", "message": f"'{path}' is missing in {n} of {total} records"})
#|    for chk in checkers.values():
#|        issues += chk.issues(total)
#|    return issues, {"records": total}
#|
#|
#|def _flatten_values(rec, prefix=""):
#|    out = {}
#|    for k, v in rec.items():
#|        p = f"{prefix}.{k}" if prefix else str(k)
#|        if isinstance(v, dict):
#|            out.update(_flatten_values(v, p))
#|        elif isinstance(v, list) and v and isinstance(v[0], dict):
#|            out.update(_flatten_values(v[0], p))
#|        else:
#|            out[p] = v
#|    return out
#|
#|
#|def json_records(data, root):
#|    """All records below the root path (not only the first)."""
#|    node = data
#|    for part in [p for p in re.split(r"\.|/|\[[^\]]*\]", re.sub(r"^\$", "", root or "")) if p]:
#|        if isinstance(node, list):
#|            node = next((x for x in node if isinstance(x, dict)), {})
#|        node = node.get(part, {}) if isinstance(node, dict) else {}
#|    if isinstance(node, list):
#|        return [x for x in node if isinstance(x, dict)]
#|    return [node] if isinstance(node, dict) and node else []
#@@ FILE nifikb/db.py tc 90d10e93241bee86
#|"""Read-only database access: schema introspection for the tables the flow/code touch, and guarded ad-hoc SELECTs.
#|
#|Drivers are optional and imported lazily:
#|  mariadb / mysql -> pymysql   (pip install pymysql)
#|  postgres        -> psycopg2  or pg8000
#|  sqlite          -> stdlib (used by tests and for local files)
#|"""
#|import fnmatch
#|import os
#|import re
#|import sqlite3
#|
#|from .util import REDACTED, SECRET_NAME, redact_secrets
#|
#|MASK_COLUMNS = re.compile(r"(?i)pass|pwd|secret|token|ssn|aadhaar|pan_?no|card|cvv|email|phone|mobile|dob|birth|salary|account_?no|iban")
#|MASK_EXTRA = re.compile(r"(?i)authorization|auth_?(token|header|value|key)|passphrase|private|cert|keystore|truststore|credential")
#|BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}")
#|
#|
#|def sensitive_column(name):
#|    name = str(name)
#|    return bool(MASK_COLUMNS.search(name) or SECRET_NAME.search(name) or MASK_EXTRA.search(name))
#|
#|
#|def mask_value(column, value):
#|    """Masked form of one value read from a database: sensitive columns become ***, secrets inside text are redacted."""
#|    if value is None:
#|        return None
#|    if sensitive_column(column):
#|        return "***"
#|    if isinstance(value, str):
#|        return BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(value))
#|    return value
#|READ_ONLY_SQL = re.compile(r"(?is)^\s*(select|with|show|describe|desc|explain)\b")
#|WRITE_WORDS = re.compile(r"(?i)\b(insert|update|delete|merge|replace|create|alter|drop|truncate|grant|revoke|call|exec|execute|lock|load|into\s+outfile|set\s+global)\b")
#|
#|
#|class DbError(Exception):
#|    pass
#|
#|
#|def connect(cfg):
#|    kind = (cfg.get("kind") or "mariadb").lower()
#|    password = cfg.get("password")
#|    if cfg.get("password_env"):
#|        password = os.environ.get(cfg["password_env"], password)
#|    if not password and cfg.get("password_file"):
#|        try:
#|            with open(cfg["password_file"], encoding="utf-8") as f:
#|                password = f.read().strip()
#|        except OSError as e:
#|            raise DbError(f"cannot read password_file of {cfg.get('name')}: {e}") from e
#|    try:
#|        if kind in ("mariadb", "mysql"):
#|            try:
#|                import pymysql
#|            except ImportError as e:
#|                raise DbError("MariaDB/MySQL needs the 'pymysql' package: pip install pymysql") from e
#|            conn = pymysql.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)), user=cfg.get("user"),
#|                                   password=password or "", database=cfg.get("database"), connect_timeout=int(cfg.get("timeout", 10)),
#|                                   read_timeout=int(cfg.get("query_timeout", 60)), charset="utf8mb4")
#|            with conn.cursor() as cur:
#|                cur.execute("SET SESSION TRANSACTION READ ONLY")
#|            return conn, "mysql"
#|        if kind in ("postgres", "postgresql"):
#|            try:
#|                import psycopg2
#|                conn = psycopg2.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)), user=cfg.get("user"),
#|                                        password=password, dbname=cfg.get("database"), connect_timeout=int(cfg.get("timeout", 10)),
#|                                        options="-c default_transaction_read_only=on -c statement_timeout=%d" % (int(cfg.get("query_timeout", 60)) * 1000))
#|            except ImportError:
#|                try:
#|                    import pg8000.dbapi as pg8000
#|                except ImportError as e:
#|                    raise DbError("PostgreSQL needs 'psycopg2-binary' or 'pg8000': pip install pg8000") from e
#|                conn = pg8000.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)), user=cfg.get("user"),
#|                                      password=password, database=cfg.get("database"), timeout=int(cfg.get("timeout", 10)))
#|                cur = conn.cursor()
#|                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
#|            return conn, "postgres"
#|        if kind == "sqlite":
#|            return sqlite3.connect(f"file:{cfg['database']}?mode=ro", uri=True), "sqlite"
#|    except DbError:
#|        raise
#|    except Exception as e:  # driver specific connection errors
#|        raise DbError(f"cannot connect to {cfg.get('name')}: {type(e).__name__}: {e}") from e
#|    raise DbError(f"unsupported database kind '{kind}'")
#|
#|
#|def _rows(conn, sql, params=()):
#|    cur = conn.cursor()
#|    cur.execute(sql, params)
#|    cols = [d[0] for d in cur.description] if cur.description else []
#|    return [dict(zip(cols, r)) for r in cur.fetchall()]
#|
#|
#|def _ph(dialect):
#|    return "?" if dialect == "sqlite" else "%s"
#|
#|
#|def list_tables(conn, dialect, schemas):
#|    if dialect == "sqlite":
#|        return [{"schema": "main", "table": r["name"], "type": r["type"].upper(), "rows": None, "comment": ""}
#|                for r in _rows(conn, "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
#|    ph = ",".join([_ph(dialect)] * len(schemas))
#|    if dialect == "mysql":
#|        sql = (f"SELECT TABLE_SCHEMA AS s, TABLE_NAME AS t, TABLE_TYPE AS ty, TABLE_ROWS AS n, TABLE_COMMENT AS c "
#|               f"FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ({ph})")
#|    else:
#|        sql = (f"SELECT t.table_schema AS s, t.table_name AS t, t.table_type AS ty, c.reltuples::bigint AS n, "
#|               f"obj_description(c.oid) AS c FROM information_schema.tables t "
#|               f"LEFT JOIN pg_catalog.pg_namespace ns ON ns.nspname = t.table_schema "
#|               f"LEFT JOIN pg_catalog.pg_class c ON c.relname = t.table_name AND c.relnamespace = ns.oid "
#|               f"WHERE t.table_schema IN ({ph})")
#|    return [{"schema": r["s"], "table": r["t"], "type": r["ty"], "rows": r["n"], "comment": r["c"] or ""}
#|            for r in _rows(conn, sql, tuple(schemas))]
#|
#|
#|def describe_table(conn, dialect, schema, table):
#|    if dialect == "sqlite":
#|        cols = [{"name": r["name"], "type": r["type"], "nullable": not r["notnull"], "key": "PRI" if r["pk"] else "",
#|                 "default": r["dflt_value"], "extra": "", "comment": ""} for r in _rows(conn, f'PRAGMA table_info("{table}")')]
#|        fks = [{"column": r["from"], "ref": f"{r['table']}.{r['to']}"} for r in _rows(conn, f'PRAGMA foreign_key_list("{table}")')]
#|        idx = [{"name": r["name"], "unique": bool(r["unique"]),
#|                "columns": [c["name"] for c in _rows(conn, f'PRAGMA index_info("{r["name"]}")')]}
#|               for r in _rows(conn, f'PRAGMA index_list("{table}")')]
#|        idx.sort(key=lambda i: (i["name"].upper() != "PRIMARY", i["name"]))
#|        return {"columns": cols, "foreign_keys": fks, "indexes": idx}
#|    p = _ph(dialect)
#|    if dialect == "mysql":
#|        cols = _rows(conn, "SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, COLUMN_KEY AS `key`, "
#|                           "COLUMN_DEFAULT AS `default`, EXTRA AS extra, COLUMN_COMMENT AS comment FROM information_schema.COLUMNS "
#|                           f"WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} ORDER BY ORDINAL_POSITION", (schema, table))
#|        fks = _rows(conn, "SELECT COLUMN_NAME AS `column`, CONCAT(REFERENCED_TABLE_NAME,'.',REFERENCED_COLUMN_NAME) AS ref "
#|                          f"FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} AND REFERENCED_TABLE_NAME IS NOT NULL",
#|                    (schema, table))
#|        idx_rows = _rows(conn, "SELECT INDEX_NAME AS name, NON_UNIQUE AS nu, COLUMN_NAME AS col FROM information_schema.STATISTICS "
#|                               f"WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} ORDER BY INDEX_NAME, SEQ_IN_INDEX", (schema, table))
#|    else:
#|        cols = _rows(conn, "SELECT c.column_name AS name, c.data_type || COALESCE('(' || c.character_maximum_length || ')', '') AS type, "
#|                           "c.is_nullable AS nullable, CASE WHEN k.column_name IS NOT NULL THEN 'PRI' ELSE '' END AS key, "
#|                           "c.column_default AS default, '' AS extra, '' AS comment FROM information_schema.columns c "
#|                           "LEFT JOIN (SELECT ku.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage ku "
#|                           "ON tc.constraint_name = ku.constraint_name AND tc.table_schema = ku.table_schema "
#|                           f"WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema={p} AND tc.table_name={p}) k ON k.column_name = c.column_name "
#|                           f"WHERE c.table_schema={p} AND c.table_name={p} ORDER BY c.ordinal_position", (schema, table, schema, table))
#|        fks = _rows(conn, "SELECT kcu.column_name AS column, ccu.table_name || '.' || ccu.column_name AS ref "
#|                          "FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
#|                          "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
#|                          f"WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema={p} AND tc.table_name={p}", (schema, table))
#|        idx_rows = _rows(conn, "SELECT i.relname AS name, CASE WHEN ix.indisunique THEN 0 ELSE 1 END AS nu, a.attname AS col "
#|                               "FROM pg_class t JOIN pg_index ix ON t.oid = ix.indrelid JOIN pg_class i ON i.oid = ix.indexrelid "
#|                               "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey) JOIN pg_namespace n ON n.oid = t.relnamespace "
#|                               f"WHERE n.nspname={p} AND t.relname={p}", (schema, table))
#|    for c in cols:
#|        c["nullable"] = str(c["nullable"]).upper() in ("YES", "TRUE", "1")
#|    idx = {}
#|    for r in idx_rows:
#|        idx.setdefault(r["name"], {"name": r["name"], "unique": not int(r["nu"]), "columns": []})["columns"].append(r["col"])
#|    indexes = sorted(idx.values(), key=lambda i: (i["name"].upper() != "PRIMARY", i["name"]))
#|    return {"columns": cols, "foreign_keys": fks, "indexes": indexes}
#|
#|
#|def profile_table(conn, dialect, schema, table, columns, max_distinct=20):
#|    """Distinct values of low-cardinality text columns (e.g. status, source_system). Masked columns are skipped."""
#|    q = '"' if dialect != "mysql" else "`"
#|    fq = f"{q}{table}{q}" if dialect == "sqlite" else f"{q}{schema}{q}.{q}{table}{q}"
#|    out = {}
#|    for c in columns:
#|        if sensitive_column(c["name"]) or not re.search(r"(?i)char|text|enum|string", str(c["type"])):
#|            continue
#|        rows = _rows(conn, f"SELECT {q}{c['name']}{q} AS v, COUNT(*) AS n FROM {fq} GROUP BY {q}{c['name']}{q} ORDER BY n DESC LIMIT {max_distinct + 1}")
#|        if 0 < len(rows) <= max_distinct:
#|            out[c["name"]] = [(mask_value(c["name"], r["v"]), r["n"]) for r in rows]
#|    return out
#|
#|
#|def sample_rows(conn, dialect, schema, table, n):
#|    q = '"' if dialect != "mysql" else "`"
#|    fq = f"{q}{table}{q}" if dialect == "sqlite" else f"{q}{schema}{q}.{q}{table}{q}"
#|    rows = _rows(conn, f"SELECT * FROM {fq} LIMIT {int(n)}")
#|    return [{k: mask_value(k, v) for k, v in r.items()} for r in rows]
#|
#|
#|def introspect(cfg, wanted_tables, optional_tables=(), log=print):
#|    """Describe wanted tables (+ optional ones if they exist, + config include patterns) for one database.
#|    Only wanted tables that do not exist are reported as missing."""
#|    conn, dialect = connect(cfg)
#|    try:
#|        schemas = cfg.get("schemas") or ([cfg["database"]] if dialect == "mysql" else ["public"])
#|        all_tables = list_tables(conn, dialect, schemas)
#|        by_name = {}
#|        for t in all_tables:
#|            by_name.setdefault(t["table"].lower(), t)
#|            by_name.setdefault(f"{t['schema']}.{t['table']}".lower(), t)
#|        patterns = [p.lower().replace("%", "*") for p in cfg.get("include_tables") or []]
#|        chosen, missing = {}, []
#|        for name in sorted(set(wanted_tables) | set(optional_tables)):
#|            t = by_name.get(name.lower()) or by_name.get(name.lower().split(".")[-1])
#|            if t:
#|                chosen[(t["schema"], t["table"])] = t
#|            elif name in wanted_tables and "${" not in name and "#{" not in name:
#|                missing.append(name)
#|        for t in all_tables:
#|            if cfg.get("all_tables") or any(fnmatch.fnmatch(t["table"].lower(), p) for p in patterns):
#|                chosen[(t["schema"], t["table"])] = t
#|        max_tables = int(cfg.get("max_tables", 300))
#|        profile = {p.lower() for p in cfg.get("profile_tables") or []}
#|        out = []
#|        for (schema, table), t in sorted(chosen.items())[:max_tables]:
#|            info = dict(t)
#|            info.update(describe_table(conn, dialect, schema, table))
#|            if dialect == "sqlite":
#|                info["rows"] = _rows(conn, f'SELECT COUNT(*) AS n FROM "{table}"')[0]["n"]
#|            if table.lower() in profile:
#|                info["profile"] = profile_table(conn, dialect, schema, table, info["columns"])
#|            if int(cfg.get("sample_rows", 0)) > 0:
#|                info["sample"] = sample_rows(conn, dialect, schema, table, cfg["sample_rows"])
#|            out.append(info)
#|        log(f"  db {cfg['name']}: {len(all_tables)} tables in {', '.join(schemas)}, documented {len(out)}, missing {len(missing)}")
#|        return {"name": cfg["name"], "kind": cfg.get("kind"), "dialect": dialect, "schemas": schemas, "tables": out,
#|                "missing": missing, "table_count": len(all_tables), "all_table_names": sorted(t["table"] for t in all_tables)}
#|    finally:
#|        conn.close()
#|
#|
#|def run_query(cfg, sql, max_rows=200):
#|    sql = sql.strip().rstrip(";")
#|    if ";" in sql or not READ_ONLY_SQL.match(sql) or WRITE_WORDS.search(re.sub(r"'[^']*'", "''", sql)):
#|        raise DbError("only a single read-only SELECT / WITH / SHOW / DESCRIBE / EXPLAIN statement is allowed")
#|    conn, dialect = connect(cfg)
#|    try:
#|        cur = conn.cursor()
#|        cur.execute(sql)
#|        cols = [d[0] for d in cur.description] if cur.description else []
#|        rows = cur.fetchmany(max_rows)
#|        if cfg.get("mask", True):
#|            rows = [tuple(mask_value(c, v) for c, v in zip(cols, r)) for r in rows]
#|        return cols, rows
#|    finally:
#|        try:
#|            conn.rollback()
#|        except Exception:
#|            pass
#|        conn.close()
#|
#|
#|def matches_jdbc(cfg, jdbc):
#|    """Does a configured database correspond to a DBCP service's JDBC URL?"""
#|    if cfg.get("dbcp_services") and jdbc.get("service_name") in cfg["dbcp_services"]:
#|        return True
#|    if cfg.get("match_jdbc"):
#|        return cfg["match_jdbc"].lower() in (jdbc.get("url") or "").lower()
#|    local = {"localhost", "127.0.0.1", "::1"}
#|    h1, h2 = (cfg.get("host") or "").lower(), (jdbc.get("host") or "").lower()
#|    same_host = h1 == h2 or (h1 in local and h2 in local)
#|    same_db = (cfg.get("database") or "").lower() == (jdbc.get("database") or "").lower()
#|    port_ok = not jdbc.get("port") or str(jdbc["port"]) == str(cfg.get("port", jdbc["port"]))
#|    return same_host and same_db and port_ok
#@@ FILE nifikb/diagnose.py tc 5b5e654f1af476cc
#|"""Support triage: given headers / a sample payload and optionally a file / table / feed name, explain what the flow
#|and the metadata expect and what does not match. Returns plain dicts (used by the CLI, --json and the MCP server)."""
#|import csv
#|import difflib
#|import io
#|import json
#|import re
#|import time
#|from pathlib import Path
#|
#|from . import db as dbmod, metadata as metamod
#|from .build import _normalize
#|
#|SEV_RANK = {"error": 0, "high": 1, "warn": 2, "info": 3}
#|
#|
#|# ------------------------------------------------------------------------------------------------ inputs
#|def headers_from_sample(path):
#|    """Field names from a sample file: JSON (object, array of objects, or an object wrapping a record list) or
#|    delimited text (header line; delimiter sniffed)."""
#|    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
#|    stripped = text.lstrip()
#|    if stripped[:1] in "{[":
#|        try:
#|            data = json.loads(stripped)
#|        except ValueError:
#|            data = [json.loads(line) for line in stripped.splitlines() if line.strip()]  # JSON lines
#|        return _json_keys(data)
#|    first = next((ln for ln in text.splitlines() if ln.strip()), "")
#|    try:
#|        dialect = csv.Sniffer().sniff(first, delimiters=",|\t;~^")
#|        delim = dialect.delimiter
#|    except csv.Error:
#|        delim = ","
#|    return [h.strip() for h in next(csv.reader(io.StringIO(first), delimiter=delim)) if h.strip()]
#|
#|
#|def read_sample(path):
#|    """{'kind': 'json', 'data': payload} or {'kind': 'csv', 'data': [headers]} - JSON is kept whole so the metadata path
#|    can apply the feed's root path and compare nested fields."""
#|    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
#|    stripped = text.lstrip()
#|    if stripped[:1] in "{[":
#|        try:
#|            return {"kind": "json", "data": json.loads(stripped)}
#|        except ValueError:
#|            return {"kind": "json", "data": [json.loads(line) for line in stripped.splitlines() if line.strip()]}
#|    return {"kind": "csv", "data": headers_from_sample(path), "path": str(path)}
#|
#|
#|def _json_keys(data):
#|    if isinstance(data, list):
#|        rec = next((x for x in data if isinstance(x, dict)), None)
#|        return list(rec) if rec else []
#|    if isinstance(data, dict):
#|        lists = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
#|        if len(lists) == 1 and len(data) <= 5:
#|            return list(lists[0][0])
#|        return list(data)
#|    return []
#|
#|
#|def split_headers(values):
#|    return [f for part in values or [] for f in str(part).replace(",", " ").split() if f]
#|
#|
#|# ------------------------------------------------------------------------------------------------ record-schema path
#|def record_diagnosis(store, headers, cfg=None):
#|    """Match headers to the PutDatabaseRecord-style processors whose reader schema is known statically."""
#|    rows = store.db.execute("SELECT * FROM record_schemas").fetchall()
#|    result = {"mode": "record", "headers": headers, "best": None, "issues": [], "findings": [], "candidates": []}
#|    if not rows:
#|        result["error"] = ("no record-based ingestion points in the KB (no PutDatabaseRecord-style processor with a resolvable "
#|                           "reader schema + matched table)")
#|        return result
#|    scored = []
#|    for r in rows:
#|        fields, translate = json.loads(r["fields"]), bool(r["translate"])
#|        ng = {_normalize(f, translate): f for f in headers}
#|        ne = {_normalize(f, translate): f for f in fields}
#|        scored.append((len(set(ng) & set(ne)) / max(len(ne), 1), r, fields, translate, ng, ne))
#|    scored.sort(key=lambda x: -x[0])
#|    for score, r, *_ in scored[:5]:
#|        c = store.db.execute("SELECT name FROM components WHERE id=?", (r["component_id"],)).fetchone()
#|        result["candidates"].append({"score": round(score, 3), "component_id": r["component_id"], "name": c["name"] if c else "?",
#|                                     "db": r["db"], "table": r["table_name"]})
#|    score, r, fields, translate, ng, ne = scored[0]
#|    if score == 0:
#|        result["error"] = "no confident match"
#|        return result
#|    comp = component_ref(store, r["component_id"])
#|    result["best"] = dict(comp, score=round(score, 3), db=r["db"], table=r["table_name"], expected_fields=fields)
#|    issues = result["issues"]
#|    for n, h in ng.items():
#|        if n not in ne:
#|            guess = difflib.get_close_matches(h, fields, n=1)
#|            issues.append({"severity": "error", "kind": "unknown-header",
#|                           "message": f"header '{h}' is not one of the expected fields" + (f" (did you mean '{guess[0]}'?)" if guess else "")})
#|    missing = [ne[n] for n in ne if n not in ng]
#|    if missing:
#|        issues.append({"severity": "warn", "kind": "missing-field", "message": f"expected fields not present in your headers: {', '.join(missing)}"})
#|    dbtab = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=lower(?)", (r["db"], r["table_name"])).fetchone()
#|    columns = json.loads(dbtab["data"])["columns"] if dbtab else []
#|    matched = {n: f for n, f in ng.items() if n in ne}
#|    cols = {_normalize(c["name"], translate): c for c in columns}
#|    extra = [f for n, f in matched.items() if n not in cols]
#|    required = [c["name"] for n, c in cols.items() if n not in matched and not c["nullable"] and c.get("default") is None
#|                and "auto_increment" not in str(c.get("extra", "")).lower() and not str(c.get("default") or "").startswith("nextval")]
#|    if extra:
#|        issues.append({"severity": "error", "kind": "column-missing",
#|                       "message": f"these headers have no matching column in {r['table_name']}: {', '.join(extra)}"})
#|    if required:
#|        issues.append({"severity": "error", "kind": "required-column",
#|                       "message": f"NOT NULL column(s) in {r['table_name']} that nothing supplies: {', '.join(required)}"})
#|    result["findings"] = findings_for(store, [r["component_id"]])
#|    if cfg:
#|        result["learnings"] = learnings_for(cfg, [r["table_name"], comp["name"], comp["short_id"], comp["type"]])
#|    return result
#|
#|
#|# ------------------------------------------------------------------------------------------------ metadata path
#|def metadata_diagnosis(cfg, store, key, headers=(), live=False, sample_path=None):
#|    """Everything the metadata config tables say about one file / table / feed / API, plus checks and linked processors."""
#|    m = metamod.settings(cfg)
#|    model = store.get_meta("metadata_model")
#|    if not m or not model:
#|        return {"mode": "metadata", "key": key, "error": "metadata support is not configured: add a [metadata] section to nifikb.toml "
#|                                                          "and run `python -m nifikb build` (see README)"}
#|    st = model.get("structure_table")
#|    targets_live = None
#|    if live:
#|        dcfg = metamod.db_config(cfg, m["db"])
#|        rows_by_table = metamod.fetch_live(dcfg, m, model)
#|        first = metamod.dossier(model, metamod.Rows(rows_by_table), key)
#|        ids = [d["id"] for d in first["definitions"]]
#|        if st:
#|            rows_by_table[st] = metamod.fetch_structure(dcfg, model, ids)
#|        names = sorted({str(d["target"]) for d in first["definitions"] if d.get("target")})
#|        if names and m["target_db"]:
#|            tcfg = dict(metamod.db_config(cfg, m["target_db"]), include_tables=[], all_tables=False, profile_tables=[],
#|                        sample_rows=0, max_tables=len(names) + 5)
#|            res = dbmod.introspect(tcfg, set(), names, log=lambda _m: None)
#|            targets_live = [{"name": m["target_db"], "tables": res["tables"], "all_table_names": res["all_table_names"]}]
#|    else:
#|        rows_by_table = store.get_meta_rows(exclude=st)
#|        first = metamod.dossier(model, metamod.Rows(rows_by_table), key)
#|        if st:
#|            rows_by_table[st] = store.get_structure_rows(st, model["structure_parent"], [d["id"] for d in first["definitions"]])
#|    rows = metamod.Rows(rows_by_table)
#|    db_results = targets_live or _target_results(store, model, first)
#|    sample = read_sample(sample_path) if sample_path else None
#|    result = metamod.dossier(model, rows, key, headers=headers, db_results=db_results, sample=sample)
#|    result.update(mode="metadata", live=live, headers=list(headers))
#|    fetched = store.cached_db_fetched("__metadata__")
#|    result["snapshot"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(fetched)) if fetched else None
#|    ids = [d["id"] for d in result["definitions"]]
#|    result["recent_changes"] = [{"when": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"])), "change": r["change"]}
#|                                for r in store.meta_changes_for(ids, 15)]
#|    if live and ids:  # what changed in these rows after the last snapshot (often: "it broke this morning")
#|        snap = store.get_meta_rows(exclude=st)
#|        if st:
#|            snap[st] = store.get_structure_rows(st, model["structure_parent"], ids)
#|        wanted = {str(i) for i in ids}
#|        result["changed_since_snapshot"] = [c["change"] for c in metamod.diff_rows(model, snap, rows_by_table)
#|                                            if c["link"] in wanted][:30]
#|    result["processors"] = linked_processors(store, model, result)
#|    result["findings"] = findings_for(store, [p["id"] for p in result["processors"]])
#|    for d in result["definitions"]:
#|        d["issues"].sort(key=lambda i: SEV_RANK.get(i["severity"], 9))
#|    terms = [key, Path(key.replace("\\", "/")).name]
#|    terms += [x for d in result["definitions"] for x in (d.get("label"), d.get("target"), f"{model.get('definition_table')}:{d.get('id')}")]
#|    terms += [x for p in result["processors"] for x in (p["name"], p["short_id"], p["type"])]
#|    terms += [m["table"] for m in result["matches"]]
#|    result["learnings"] = learnings_for(cfg, terms)
#|    return result
#|
#|
#|def learnings_for(cfg, terms):
#|    from . import learnings as lm
#|    return [{"id": i["id"], "title": i["title"], "kind": i["kind"], "score": i["score"], "ticket": i.get("ticket"),
#|             "date": i.get("date"), "excerpt": " ".join(i["body"].split())[:400]} for i in lm.relevant(cfg, terms)]
#|
#|
#|def _target_results(store, model, pre):
#|    names = {str(d["target"]).lower().split(".")[-1] for d in pre["definitions"] if d.get("target")}
#|    tables = []
#|    for n in names:
#|        row = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=?", (model["target_db"], n)).fetchone()
#|        if row:
#|            tables.append(json.loads(row["data"]))
#|    return [{"name": model["target_db"], "tables": tables, "all_table_names": store.get_meta(f"db_all_tables:{model['target_db']}", [])}]
#|
#|
#|def linked_processors(store, model, result, cap=25):
#|    """Processors tied to this object: configured with one of its identifying values, writing its target table, or
#|    reading the config tables (the metadata lookup processors)."""
#|    found = {}
#|
#|    def add(cid, why):
#|        if cid in found:
#|            if why not in found[cid]["why"]:
#|                found[cid]["why"].append(why)
#|            return
#|        if len(found) >= cap:
#|            return
#|        ref = component_ref(store, cid)
#|        if ref:
#|            found[cid] = dict(ref, why=[why])
#|
#|    values = set()
#|    rows = [x["row"] for x in result.get("matches", [])] + [d["row"] for d in result.get("definitions", [])]
#|    rows += [r for rs in result.get("related", {}).values() for r in rs]
#|    for r in rows:
#|        for k, v in r.items():
#|            if isinstance(v, str) and 4 <= len(v) <= 200 and v != "***" and (
#|                    metamod.KEY_COL.search(k) or metamod.TARGET_COL.search(k) or re.search(r"(?i)host|url|endpoint|dir|path", k)):
#|                values.add(v)
#|    for v in sorted(values):
#|        q = ("SELECT DISTINCT component_id, display FROM properties WHERE lower(resolved)=lower(?) "
#|             "OR (length(?) >= 6 AND instr(lower(resolved), lower(?)) > 0) LIMIT 50")
#|        for p in store.db.execute(q, (v, v, v)):
#|            add(p["component_id"], f"property '{p['display']}' contains '{v}'")
#|    for d in result.get("definitions", []):
#|        if d.get("target"):
#|            t = str(d["target"]).lower().split(".")[-1]
#|            for p in store.db.execute("SELECT DISTINCT component_id FROM resources WHERE kind='db_table' AND lower(value) IN (?, ?)",
#|                                      (t, str(d["target"]).lower())):
#|                add(p["component_id"], f"writes/reads target table {d['target']}")
#|    for t in model["tables"]:
#|        for p in store.db.execute("SELECT DISTINCT component_id FROM resources WHERE kind='db_table' AND lower(value)=lower(?) LIMIT 10", (t,)):
#|            add(p["component_id"], f"reads config table {t}")
#|    for fqcn, tables in (store.get_meta("config_table_code") or {}).items():
#|        for p in store.db.execute("SELECT id FROM components WHERE type=? LIMIT 10", (fqcn,)):
#|            add(p["id"], f"custom {fqcn.rsplit('.', 1)[-1]} queries {', '.join(tables)} in its code")
#|    return list(found.values())
#|
#|
#|# ------------------------------------------------------------------------------------------------ shared
#|def component_ref(store, cid):
#|    c = store.db.execute("SELECT id, name, type, group_id, group_path, state FROM components WHERE id=?", (cid,)).fetchone()
#|    if not c:
#|        return None
#|    g = store.db.execute("SELECT doc FROM groups WHERE id=?", (c["group_id"],)).fetchone()
#|    return {"id": c["id"], "short_id": c["id"][:8], "name": c["name"], "type": (c["type"] or "").rsplit(".", 1)[-1],
#|            "group": c["group_path"], "state": c["state"], "doc": f"{g['doc']}#c-{c['id'][:8]}" if g else None}
#|
#|
#|def findings_for(store, component_ids):
#|    out = []
#|    for cid in component_ids:
#|        for f in store.db.execute("SELECT severity, kind, message FROM findings WHERE component_id=?", (cid,)):
#|            out.append({"component_id": cid, "severity": f["severity"], "kind": f["kind"], "message": f["message"]})
#|    out.sort(key=lambda f: SEV_RANK.get(f["severity"], 9))
#|    return out
#|
#|
#|def has_errors(result):
#|    issues = list(result.get("issues", [])) + [i for d in result.get("definitions", []) for i in d.get("issues", [])]
#|    return any(i["severity"] == "error" for i in issues)
#|
#|
#|# ------------------------------------------------------------------------------------------------ text output
#|def format_text(result):
#|    if result["mode"] == "record":
#|        return _format_record(result)
#|    return _format_metadata(result)
#|
#|
#|def _issue_lines(issues, indent="  "):
#|    marks = {"error": "x", "high": "x", "warn": "!", "info": "-"}
#|    return [f"{indent}{marks.get(i['severity'], '-')} [{i['severity']}] {i['message']}" for i in issues]
#|
#|
#|def _learning_lines(r):
#|    items = r.get("learnings") or []
#|    if not items:
#|        return []
#|    L = ["", "Team learnings that may apply (python -m nifikb learn show <id>):"]
#|    for i in items:
#|        L.append(f"  {i['id']} [{i['kind']}] {i['title']}" + (f" (ticket {i['ticket']})" if i.get("ticket") else ""))
#|        L.append(f"    {i['excerpt'][:300]}")
#|    return L
#|
#|
#|def _format_record(r):
#|    L = []
#|    if r.get("error"):
#|        L.append(r["error"] + (";" if r["candidates"] else ""))
#|        if r["candidates"]:
#|            L.append("closest ingestion points by name overlap:")
#|            L += [f"  {c['score']:.0%}  {c['name']} -> {c['db']}.{c['table']}" for c in r["candidates"]]
#|        return "\n".join(L)
#|    b = r["best"]
#|    L.append(f"Best match ({b['score']:.0%} of expected fields present): {b['name']} `{b['short_id']}` -> {b['db']}.{b['table']}  [{b['doc']}]")
#|    L += _issue_lines(r["issues"])
#|    if not r["issues"]:
#|        L.append("  OK all headers map cleanly to the reader schema and table columns")
#|    if r["findings"]:
#|        L.append("  known issues already flagged on this processor:")
#|        L += [f"    [{f['severity']}] {f['kind']}: {f['message']}" for f in r["findings"]]
#|    L += _learning_lines(r)
#|    return "\n".join(L)
#|
#|
#|def _short_row(row, limit=12):
#|    items = [(k, v) for k, v in row.items() if v not in (None, "")]
#|    s = ", ".join(f"{k}={v}" for k, v in items[:limit])
#|    return s + (f", … +{len(items) - limit}" if len(items) > limit else "")
#|
#|
#|def _format_metadata(r):
#|    if r.get("error"):
#|        return r["error"]
#|    L = [f"Metadata for '{r['key']}'" + (" (live: config rows read just now)" if r.get("live") else
#|                                         f" (config rows from the snapshot of {r.get('snapshot') or 'the last build'}; "
#|                                         "use live mode for rows changed since)")]
#|    if not r["matches"]:
#|        L.append("  nothing in the config tables matches this name")
#|        if r.get("suggestions"):
#|            L.append("  did you mean: " + ", ".join(r["suggestions"]))
#|        return "\n".join(L)
#|    L.append("Matched:")
#|    L += [f"  {x['table']}.{x['column']} ({x['match']}): {_short_row(x['row'])}" for x in r["matches"][:10]]
#|    for d in r["definitions"]:
#|        L += ["", f"Definition {d['id']} · {d['label']}" + (f" → target table {d['target']}" if d.get("target") else "")
#|              + (f" → loads to {d['location']}" if d.get("location") else "")]
#|        if d["fields"]:
#|            L.append(f"  structure ({len(d['fields'])} fields): " + ", ".join(
#|                (f"{f['seq']}:" if f["seq"] is not None else "") + f["name"] + (f" {f['type']}" if f.get("type") else "")
#|                + (f"({f['length']})" if f.get("length") else "") + ("?" if f.get("nullable") else "")
#|                for f in d["fields"][:80]) + (" …" if len(d["fields"]) > 80 else ""))
#|        smp = d.get("sample")
#|        if smp and smp.get("kind") == "csv" and smp.get("delimiter"):
#|            L.append(f"  sample: CSV, delimiter {smp['delimiter']!r} ({smp.get('delimiter_source')}), "
#|                     f"{'with' if smp.get('header') else 'no'} header row, {smp.get('rows', 0)} data rows checked")
#|        if smp and smp.get("kind") == "json":
#|            L.append(f"  sample: JSON, record root {smp.get('root') or '(top level)'}, {smp['fields']} "
#|                     + ("nested field paths compared" if smp.get("paths") else "top-level keys compared") + " (order not checked)")
#|        L += _issue_lines(d["issues"])
#|        if not d["issues"]:
#|            L.append("  OK structure, headers and target table agree")
#|        from .fixes import format_fixes
#|        L += format_fixes(d.get("fixes") or [])
#|    if r.get("changed_since_snapshot"):
#|        L += ["", f"Config rows changed since the snapshot of {r.get('snapshot') or 'the last build'} (live read):"]
#|        L += [f"  {c}" for c in r["changed_since_snapshot"]]
#|    if r.get("recent_changes"):
#|        L += ["", "Recent config-row changes for this definition (from earlier snapshots, newest first):"]
#|        L += [f"  {c['when']}  {c['change']}" for c in r["recent_changes"]]
#|    if r["related"]:
#|        L += ["", "Related config rows:"]
#|        for t, rows in r["related"].items():
#|            for row in rows[:5]:
#|                L.append(f"  {t}: {_short_row(row)}")
#|            if len(rows) > 5:
#|                L.append(f"  {t}: … {len(rows) - 5} more")
#|    if r.get("processors"):
#|        L += ["", "Flow processors involved:"]
#|        for p in r["processors"]:
#|            L.append(f"  {p['name']} [{p['type']}] `{p['short_id']}` {p['state'] or ''} in {p['group']} — {'; '.join(p['why'][:2])}  [{p['doc']}]")
#|    if r.get("findings"):
#|        L += ["", "Known issues on those processors:"]
#|        L += [f"  [{f['severity']}] {f['component_id'][:8]} {f['kind']}: {f['message']}" for f in r["findings"][:30]]
#|    L += _learning_lines(r)
#|    return "\n".join(L)
#@@ FILE nifikb/doctor.py tc d39a714db243d005
#|"""`nifikb doctor`: one command that checks an installation end to end (first thing to run on a new machine)."""
#|import json
#|import shutil
#|import sys
#|import time
#|from pathlib import Path
#|
#|from .config import PROJECT_DIR
#|
#|OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
#|
#|
#|def run(cfg, offline=False):
#|    checks = []
#|
#|    def add(status, label, detail=""):
#|        checks.append((status, label, detail))
#|
#|    add(OK if sys.version_info >= (3, 11) else FAIL, "python", f"{sys.version.split()[0]} ({sys.executable})"
#|        + ("" if sys.version_info >= (3, 11) else " - needs 3.11+"))
#|    add(OK, "config", cfg["_path"])
#|    _nifi(cfg, add)
#|    _code(cfg, add)
#|    _databases(cfg, add, offline)
#|    _metadata(cfg, add)
#|    _kb(cfg, add)
#|    _audit(cfg, add)
#|    _logs(cfg, add)
#|    _nifi_api(cfg, add, offline)
#|    _optional(cfg, add)
#|    _agents(cfg, add)
#|    _knowledge(cfg, add)
#|    return checks
#|
#|
#|def _nifi(cfg, add):
#|    from .build import find_flow_file
#|    from .catalog import find_nars
#|    try:
#|        flow = find_flow_file(cfg)
#|        add(OK, "flow file", f"{flow} ({flow.stat().st_size / 1e6:.1f} MB, modified {time.strftime('%Y-%m-%d %H:%M', time.localtime(flow.stat().st_mtime))})")
#|    except FileNotFoundError as e:
#|        add(FAIL, "flow file", str(e))
#|    home = cfg["nifi"].get("home")
#|    dirs = [Path(home) / d for d in ("lib", "extensions")] if home else []
#|    for d in cfg["nifi"].get("extra_nar_dirs", []):
#|        add(OK if Path(d).is_dir() else FAIL, "extra NAR dir", d)
#|        dirs.append(Path(d))
#|    nars = find_nars(dirs)
#|    add(OK if nars else WARN, "NARs", f"{len(nars)} found" + ("" if nars else " - no property defaults / docs; set [nifi] home or extra_nar_dirs"))
#|
#|
#|def _code(cfg, add):
#|    repos = cfg["code"].get("repos", [])
#|    if not repos:
#|        add(WARN, "code repos", "none configured - custom processors will only have NAR docs (set [code] repos to the Bitbucket clones)")
#|    for r in repos:
#|        p = Path(r)
#|        if not p.exists():
#|            add(FAIL, "code repo", f"{r} does not exist")
#|            continue
#|        java = sum(1 for _ in p.rglob("*.java"))
#|        poms = sum(1 for _ in p.rglob("pom.xml"))
#|        svc = sum(1 for _ in p.rglob("META-INF/services/org.apache.nifi.*"))
#|        other = sum(1 for ext in ("*.py", "*.groovy", "*.scala", "*.sh", "*.sql") for _ in p.rglob(ext))
#|        add(OK, "code repo", f"{r}: {java} Java, {poms} pom.xml, {svc} NiFi service registrations, {other} scripts/other")
#|
#|
#|def _databases(cfg, add, offline):
#|    from . import db as dbmod
#|    import os
#|    if not cfg.get("databases"):
#|        add(WARN, "databases", "none configured - no table schemas, no metadata checks (add a [[databases]] block)")
#|    for d in cfg.get("databases", []):
#|        kind = (d.get("kind") or "mariadb").lower()
#|        label = f"database {d['name']}"
#|        driver = {"mariadb": "pymysql", "mysql": "pymysql", "postgres": "pg8000", "postgresql": "pg8000"}.get(kind)
#|        if driver:
#|            try:
#|                __import__(driver)
#|            except ImportError:
#|                if kind.startswith("postgres"):
#|                    try:
#|                        __import__("psycopg2")
#|                        driver = None
#|                    except ImportError:
#|                        pass
#|                if driver:
#|                    add(FAIL, label, f"driver missing: pip install {driver}")
#|                    continue
#|        if d.get("password_env") and not os.environ.get(d["password_env"]) and not d.get("password_file"):
#|            add(WARN, label, f"environment variable {d['password_env']} is not set in this shell")
#|        if d.get("password_file"):
#|            pf = Path(d["password_file"])
#|            if not pf.is_file():
#|                add(FAIL, label, f"password_file {pf} not found")
#|                continue
#|            if os.name == "posix" and pf.stat().st_mode & 0o077:
#|                add(WARN, label, f"password_file {pf} is readable by others: chmod 600 {pf}")
#|        if offline:
#|            continue
#|        try:
#|            conn, dialect = dbmod.connect(d)
#|        except dbmod.DbError as e:
#|            add(FAIL, label, str(e))
#|            continue
#|        try:
#|            cur = conn.cursor()
#|            cur.execute("SELECT 1")
#|            cur.fetchall()
#|            detail = f"{kind} connected as {d.get('user') or '-'}"
#|            status = OK
#|            if dialect == "mysql":
#|                cur.execute("SHOW GRANTS")
#|                grants = " ".join(g for g in (str(r[0]) for r in cur.fetchall()) if _grant_covers(g, d.get("database"))).upper()
#|                if any(w in grants for w in ("ALL PRIVILEGES", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER")):
#|                    status, detail = WARN, detail + " - this user can WRITE; use a SELECT-only user (sessions are read-only anyway)"
#|                else:
#|                    detail += ", read-only grants"
#|            add(status, label, detail)
#|        except Exception as e:  # driver specific
#|            add(FAIL, label, f"{type(e).__name__}: {e}")
#|        finally:
#|            conn.close()
#|
#|
#|def _grant_covers(grant, database):
#|    """Does a MySQL/MariaDB GRANT line apply to the configured database (or to all databases)?"""
#|    import fnmatch
#|    import re
#|    m = re.search(r"\bON\s+(?:TABLE\s+)?`?([^`.\s]+|\*)`?\.", grant, re.I)
#|    if not m:
#|        return False
#|    target = m.group(1)
#|    if target == "*":
#|        return True
#|    pattern = target.replace("\\_", "\0").replace("%", "*").replace("_", "?").replace("\0", "_")
#|    return bool(database) and fnmatch.fnmatch(database.lower(), pattern.lower())
#|
#|
#|def _metadata(cfg, add):
#|    from . import metadata as metamod
#|    try:
#|        m = metamod.settings(cfg)
#|    except ValueError as e:
#|        add(FAIL, "metadata", str(e))
#|        return
#|    if not m:
#|        add(WARN, "metadata", "[metadata] not configured - no OBJ_* definition / structure checks and no `diagnose --file`")
#|        return
#|    model = _store_meta(cfg, "metadata_model")
#|    if not model:
#|        add(WARN, "metadata", f"configured (db '{m['db']}') - run build to detect the config tables")
#|        return
#|    missing = [r for r in ("definition_table", "structure_table") if not model.get(r)]
#|    detail = (f"{len(model['tables'])} config tables, definition {model.get('definition_table')}, structure {model.get('structure_table')}, "
#|              f"{len(model['relations'])} relations")
#|    if missing:
#|        add(WARN, "metadata", detail + f" - not detected: {', '.join(missing)} (set them in [metadata])")
#|    elif model.get("guessed"):
#|        add(OK, "metadata", detail + f" - auto-detected {', '.join(model['guessed'])}: confirm in kb/metadata.md")
#|    else:
#|        add(OK, "metadata", detail)
#|
#|
#|def _store_meta(cfg, key):
#|    import sqlite3
#|    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
#|    if not path.exists():
#|        return None
#|    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
#|    try:
#|        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
#|        return json.loads(row[0]) if row else None
#|    except sqlite3.Error:
#|        return None
#|    finally:
#|        db.close()
#|
#|
#|def _kb(cfg, add):
#|    from .build import find_flow_file
#|    built = _store_meta(cfg, "built_at")
#|    if not built:
#|        add(FAIL, "knowledge base", "not built yet: python -m nifikb build")
#|        return
#|    age_h = (time.time() - built) / 3600
#|    detail = f"built {time.strftime('%Y-%m-%d %H:%M', time.localtime(built))} ({age_h:.1f} h ago)"
#|    try:
#|        stale = find_flow_file(cfg).stat().st_mtime > built
#|    except FileNotFoundError:
#|        stale = False
#|    if stale:
#|        add(WARN, "knowledge base", detail + " - the flow changed since: run build (or schedule it)")
#|    else:
#|        add(OK if age_h < 48 else WARN, "knowledge base", detail + ("" if age_h < 48 else " - older than 2 days: schedule `build`"))
#|
#|
#|def _audit(cfg, add):
#|    from . import audit as auditmod
#|    try:
#|        a = auditmod.settings(cfg)
#|    except ValueError as e:
#|        add(FAIL, "load audit", str(e))
#|        return
#|    if not a:
#|        add(WARN, "load audit", "[audit] not configured - investigate cannot show the last load status of a file")
#|        return
#|    m = _store_meta(cfg, "audit_model")
#|    if not m:
#|        add(WARN, "load audit", f"no audit table found in '{a['db']}' - set [audit] table (then build)")
#|    else:
#|        add(OK, "load audit", f"{m['table']}: file {m['file_column']}, status {m.get('status_column')}, time {m.get('time_column')}, "
#|                              f"error {m.get('error_column')}" + (f" (guessed: {', '.join(m['guessed'])})" if m.get("guessed") else ""))
#|
#|
#|def _logs(cfg, add):
#|    from . import logs as lg
#|    s = lg.settings(cfg)
#|    if not s["enabled"]:
#|        add(WARN, "logs", "no log directory (set [logs] dirs, or [nifi] home) - errors from nifi-app.log are not available")
#|        return
#|    missing = [d for d in s["dirs"] if not Path(d).is_dir()]
#|    files = lg.log_files(s)
#|    if missing:
#|        add(FAIL if not files else WARN, "logs", f"directory not found: {', '.join(missing)}")
#|    if files:
#|        newest = max(files, key=lambda f: f.stat().st_mtime)
#|        events = _store_count(cfg, "SELECT COUNT(*) FROM log_events")
#|        add(OK, "logs", f"{len(files)} file(s), newest {newest.name} modified "
#|                         f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(newest.stat().st_mtime))}; {events} warning / error events indexed")
#|    elif not missing:
#|        add(WARN, "logs", f"no files matching {', '.join(s['patterns'])} in {', '.join(s['dirs'])}")
#|
#|
#|def _store_count(cfg, sql):
#|    import sqlite3
#|    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
#|    if not path.exists():
#|        return 0
#|    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
#|    try:
#|        return db.execute(sql).fetchone()[0]
#|    except sqlite3.Error:
#|        return 0
#|    finally:
#|        db.close()
#|
#|
#|def _nifi_api(cfg, add, offline):
#|    from . import nifiapi
#|    a = nifiapi.settings(cfg)
#|    if not a:
#|        add(WARN, "NiFi API", "[nifi_api] not configured - no provenance ('where was my file dropped') and no live bulletins")
#|        return
#|    if offline:
#|        add(OK, "NiFi API", f"{a['url']} (not contacted: --offline)")
#|        return
#|    try:
#|        about = nifiapi.Client(a).about()
#|        add(OK, "NiFi API", f"{a['url']} - {about.get('title', 'NiFi')} {about.get('version', '')}".strip())
#|    except (nifiapi.NiFiApiError, OSError, ValueError) as e:
#|        add(FAIL, "NiFi API", str(e))
#|
#|
#|def _optional(cfg, add):
#|    """[targets], [tickets], [environments.*], [registry]: configuration that can be checked without contacting anything."""
#|    import os
#|    if "targets" in cfg:
#|        t = cfg["targets"] or {}
#|        tools = []
#|        if t.get("hdfs_url"):
#|            tools.append(f"WebHDFS {t['hdfs_url']}" + (" (kerberos via curl)" if t.get("kerberos") else ""))
#|            if t.get("kerberos") and not shutil.which(t.get("curl", "curl")):
#|                add(FAIL, "targets", "kerberos = true needs curl on the PATH")
#|        elif shutil.which("hdfs") or t.get("hdfs_cli"):
#|            tools.append("hdfs CLI")
#|        if t.get("s3_cli"):
#|            tools.append("S3 via configured CLI")
#|        else:
#|            try:
#|                import boto3  # noqa: F401
#|                tools.append("S3 via boto3")
#|            except ImportError:
#|                tools.append("S3 via aws CLI" if shutil.which("aws") else "no S3 access (install the aws CLI or boto3)")
#|        add(OK, "targets", ", ".join(tools + ["local / mounted folders"])
#|            + (f"; location_template {t['location_template']}" if t.get("location_template") else ""))
#|    tk = cfg.get("tickets")
#|    if tk:
#|        secret = next((k for k in ("token", "password") if tk.get(f"{k}_env") and os.environ.get(tk[f"{k}_env"]) or tk.get(f"{k}_file")), None)
#|        if tk.get("kind") not in ("jira", "servicenow") or not tk.get("url"):
#|            add(FAIL, "tickets", "[tickets] needs kind = \"jira\" | \"servicenow\" and url")
#|        elif not secret:
#|            add(WARN, "tickets", f"{tk['kind']} {tk['url']}: no credential (set token_env / password_env or *_file)")
#|        else:
#|            add(OK, "tickets", f"{tk['kind']} {tk['url']} (posting only with `ticket <id> --post`)")
#|    dbs = {d["name"] for d in cfg.get("databases", [])}
#|    for name, env in (cfg.get("environments") or {}).items():
#|        problems = []
#|        if env.get("flow_file") and not Path(env["flow_file"]).exists():
#|            problems.append(f"flow_file {env['flow_file']} not found")
#|        if env.get("db") and env["db"] not in dbs:
#|            problems.append(f"db '{env['db']}' is not a [[databases]] name")
#|        add(FAIL if problems else OK, f"environment {name}", "; ".join(problems) or
#|            ", ".join(x for x in (env.get("flow_file"), env.get("db")) if x))
#|
#|
#|def _agents(cfg, add):
#|    root = Path(cfg["_path"]).parent
#|    for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
#|        if not (root / f).exists():
#|            add(WARN, "agent instructions", f"{f} missing next to nifikb.toml")
#|    texts = {f: (root / f).read_text(encoding="utf-8").replace("\r\n", "\n") for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md") if (root / f).exists()}
#|    if len(set(texts.values())) > 1:
#|        add(WARN, "agent instructions", "CLAUDE.md / GEMINI.md / AGENTS.md differ - copy the edited one over the others")
#|    elif texts:
#|        add(OK, "agent instructions", ", ".join(texts))
#|    for f, kind in ((".mcp.json", "Claude Code MCP"), (".gemini/settings.json", "Gemini CLI MCP")):
#|        p = root / f
#|        if not p.exists():
#|            add(WARN, kind, f"{f} missing")
#|            continue
#|        try:
#|            server = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["nifikb"]
#|        except (ValueError, KeyError) as e:
#|            add(FAIL, kind, f"{f}: no mcpServers.nifikb entry ({e})")
#|            continue
#|        cmd = server.get("command", "")
#|        found = shutil.which(cmd)
#|        if not found:
#|            alt = next((c for c in ("py", "python3", "python") if shutil.which(c)), None)
#|            add(FAIL, kind, f"{f}: command '{cmd}' not on PATH" + (f" - change it to '{alt}'" if alt else ""))
#|        else:
#|            add(OK, kind, f"{f} -> {cmd} {' '.join(server.get('args', []))}")
#|    if root.resolve() != PROJECT_DIR.resolve() and not (root / "nifikb").is_dir():
#|        add(WARN, "MCP working dir", f"the agents start `python -m nifikb` in {root}; the nifikb package lives in {PROJECT_DIR}")
#|
#|
#|def _knowledge(cfg, add):
#|    from . import learnings as lm
#|    r = lm.ensure(cfg)
#|    items = lm.load_all(cfg, include_obsolete=False)
#|    add(OK, "learnings", f"{len(items)} active in {r / 'learnings'}")
#|    if not lm.context_text(cfg):
#|        add(WARN, "team context", f"{r / 'context.md'} is still the template - fill in environments, owners, conventions")
#|    else:
#|        add(OK, "team context", str(r / "context.md"))
#|
#|
#|def report(checks):
#|    lines = [f"[{s}] {label}: {detail}" for s, label, detail in checks]
#|    fails = sum(1 for s, _, _ in checks if s == FAIL)
#|    warns = sum(1 for s, _, _ in checks if s == WARN)
#|    lines.append(f"\n{fails} problem(s), {warns} warning(s)")
#|    return "\n".join(lines), fails
#@@ FILE nifikb/evals.py t 184d8faaafffa027
#|"""Evaluation set of past tickets with known root causes: are the tools (and the model) getting them right?
#|
#|evals/cases.toml:
#|
#|    [[case]]
#|    id = "INC1001"
#|    ticket = "SALES file of 26 Sep did not load, customer names missing"   # what the user wrote (for the agent run)
#|    file = "SALES_20260926.csv"                   # the investigate inputs: file / feed / table / error / headers / sample
#|    headers = ["ORDER_NO", "CUSTNAME", "AMOUNT"]
#|    expect_any = ["CUSTNAME", "CUST_NAME"]        # at least one must appear in the top `top` ranked causes
#|    expect_all = []                               # every one must appear
#|    top = 3
#|    answer_expect = ["CUST_NAME"]                 # with --agent: words the model's answer must contain (default: expect_any)
#|
#|`python -m nifikb eval` checks the ranked causes; `--agent "<command>"` also sends ticket + report to a model CLI (the
#|prompt is written to its stdin, or to a file whose path replaces {prompt_file}) and checks its answer.
#|"""
#|import json
#|import shlex
#|import subprocess
#|import tempfile
#|import time
#|import tomllib
#|from pathlib import Path
#|
#|PROMPT = """You are the NiFi support assistant. A colleague reported:
#|
#|{ticket}
#|
#|The nifikb tools investigated it. Their report (ranked likely causes first, then evidence):
#|
#|{report}
#|
#|Answer in this shape: Cause (one or two sentences), Evidence (ids, rows, file:line, log lines), Fix (who changes what).
#|"""
#|
#|
#|def load_cases(path):
#|    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
#|    cases = data.get("case") or []
#|    base = Path(path).parent
#|    for c in cases:
#|        if c.get("sample"):
#|            p = Path(c["sample"])
#|            c["sample"] = str(p if p.is_absolute() else (base / p))
#|    return cases
#|
#|
#|def run(cfg, store, names, cases, top=None, agent=None, timeout=300, log=print):
#|    from . import diagnose as dg, investigate as inv
#|    results = []
#|    for c in cases:
#|        t0 = time.time()
#|        r = inv.investigate(cfg, store, names, file=c.get("file"), feed=c.get("feed"), table=c.get("table"),
#|                            error_text=c.get("error"), headers=dg.split_headers(c.get("headers") or []), sample_path=c.get("sample"),
#|                            live=bool(c.get("live")), record=False)
#|        n = int(c.get("top") or top or 3)
#|        ranked = r["causes"][:n]
#|        text = "\n".join(ranked).lower()
#|        any_ok = not c.get("expect_any") or any(w.lower() in text for w in c["expect_any"])
#|        all_ok = all(w.lower() in text for w in c.get("expect_all") or [])
#|        position = next((i + 1 for i, cause in enumerate(r["causes"])
#|                         if any(w.lower() in cause.lower() for w in (c.get("expect_any") or c.get("expect_all") or []))), None)
#|        res = {"id": c.get("id"), "tools_ok": any_ok and all_ok, "position": position, "top": n, "seconds": round(time.time() - t0, 1),
#|               "first_cause": r["causes"][0] if r["causes"] else None}
#|        if agent:
#|            answer = ask_agent(agent, PROMPT.format(ticket=c.get("ticket") or c.get("id"), report=inv.format_report(r)), timeout)
#|            words = c.get("answer_expect") or c.get("expect_any") or []
#|            res["agent_ok"] = bool(answer) and all(w.lower() in answer.lower() for w in words) if c.get("answer_expect") else \
#|                any(w.lower() in answer.lower() for w in words)
#|            res["answer"] = answer[:2000]
#|        results.append(res)
#|        log(f"{'PASS' if res['tools_ok'] and res.get('agent_ok', True) else 'FAIL'} {res['id']}: cause at rank {position or '-'}"
#|            + (f", agent {'ok' if res['agent_ok'] else 'wrong'}" if agent else ""))
#|    return results
#|
#|
#|def ask_agent(command, prompt, timeout):
#|    """Run a model CLI non-interactively: the prompt goes to stdin, or into a temp file named by {prompt_file}."""
#|    tmp = None
#|    try:
#|        if "{prompt_file}" in command:
#|            fd, tmp = tempfile.mkstemp(suffix=".txt")
#|            with open(fd, "w", encoding="utf-8") as f:
#|                f.write(prompt)
#|            argv = [a.replace("{prompt_file}", tmp) for a in shlex.split(command, posix=True)]
#|            proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
#|        else:
#|            proc = subprocess.run(shlex.split(command, posix=True), input=prompt, capture_output=True, text=True, encoding="utf-8",
#|                                  timeout=timeout)
#|        return (proc.stdout or "") + (proc.stderr if proc.returncode else "")
#|    except (OSError, subprocess.TimeoutExpired) as e:
#|        return f"<agent failed: {e}>"
#|    finally:
#|        if tmp:
#|            Path(tmp).unlink(missing_ok=True)
#|
#|
#|def summary(results):
#|    n = len(results)
#|    tools = sum(r["tools_ok"] for r in results)
#|    lines = [f"tools: {tools}/{n} cases have the true cause in their top ranks"]
#|    agents = [r for r in results if "agent_ok" in r]
#|    if agents:
#|        lines.append(f"agent: {sum(r['agent_ok'] for r in agents)}/{len(agents)} answers name the true cause")
#|    ranks = [r["position"] for r in results if r["position"]]
#|    if ranks:
#|        lines.append(f"mean rank of the true cause: {sum(ranks) / len(ranks):.1f}")
#|    return "\n".join(lines)
#|
#|
#|def save(results, path):
#|    Path(path).write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M"), "results": results}, indent=2), encoding="utf-8")
#@@ FILE nifikb/fixes.py t 4967308a081fb582
#|"""Proposed fixes for config-side problems, as SQL for a human to review and run (nifikb never runs them).
#|
#|Each proposal says who should act: often the right fix is the sender correcting the file, not us changing the metadata;
#|the SQL is then offered only as the alternative."""
#|
#|
#|def quote(v):
#|    if v is None:
#|        return "NULL"
#|    if isinstance(v, bool):
#|        return "1" if v else "0"
#|    if isinstance(v, (int, float)):
#|        return str(v)
#|    return "'" + str(v).replace("'", "''") + "'"
#|
#|
#|def _where(key):
#|    return " AND ".join(f"{c} = {quote(v)}" for c, v in key.items()) or "1 = 0"
#|
#|
#|def suggest(model, entry):
#|    st, dt = model.get("structure_table"), model.get("definition_table")
#|    col = {k: model.get(k) for k in ("structure_field", "structure_type", "structure_length", "structure_nullable", "structure_order",
#|                                     "structure_parent", "definition_id", "definition_target")}
#|    fields = {f["name"].lower(): f for f in entry.get("fields") or []}
#|    out, seen = [], set()
#|
#|    def add(why, who, sql, note=""):
#|        if sql and sql not in seen:
#|            seen.add(sql)
#|            out.append({"why": why, "who": who, "sql": sql, "note": note})
#|
#|    required_flag = "'Y'" if model.get("nullable_means_required") else "'N'"
#|    optional_flag = "'N'" if model.get("nullable_means_required") else "'Y'"
#|    for i in entry.get("issues") or []:
#|        d, kind = i.get("data") or {}, i["kind"]
#|        if kind == "header-name" and st and col["structure_field"]:
#|            f = fields.get(str(d.get("field", "")).lower())
#|            if f:
#|                add(f"header '{d['header']}' vs structure '{f['name']}'", "sender (preferred) or config",
#|                    f"UPDATE {st} SET {col['structure_field']} = {quote(d['header'])} WHERE {_where(f['key'])};",
#|                    f"prefer asking the sender to send '{f['name']}'; change the row only if '{d['header']}' is the agreed name "
#|                    f"(and if {col['structure_field']} is also the target column name, the target column must match)")
#|        elif kind == "length" and st and col["structure_length"]:
#|            for name, table_len in d.get("items") or []:
#|                f = fields.get(name.lower())
#|                if f:
#|                    add(f"'{name}' longer in the structure than in {d.get('table')}", "config (or widen the target column)",
#|                        f"UPDATE {st} SET {col['structure_length']} = {table_len} WHERE {_where(f['key'])};",
#|                        f"or widen the column instead: ALTER TABLE {d.get('table')} MODIFY {name} VARCHAR({f['length']}) - decide which "
#|                        "length is right")
#|        elif kind == "type-mismatch" and st and col["structure_type"]:
#|            for name, table_type in d.get("items") or []:
#|                f = fields.get(name.lower())
#|                if f:
#|                    add(f"'{name}' type differs from {d.get('table')}", "config",
#|                        f"UPDATE {st} SET {col['structure_type']} = {quote(str(table_type).split('(')[0].upper())} WHERE {_where(f['key'])};",
#|                        "check the type name convention used in the structure table before running")
#|        elif kind == "nullability" and st and col["structure_nullable"]:
#|            for name, _ in d.get("items") or []:
#|                f = fields.get(name.lower())
#|                if f:
#|                    add(f"'{name}' nullable in the structure but NOT NULL in {d.get('table')}", "config",
#|                        f"UPDATE {st} SET {col['structure_nullable']} = {required_flag} WHERE {_where(f['key'])};",
#|                        "use the flag values the table already uses (Y/N, 1/0, ...)")
#|        elif kind == "required-column" and st and col["structure_parent"] and col["structure_field"]:
#|            seqs = [f["seq"] for f in entry.get("fields") or [] if f.get("seq") is not None]
#|            nxt = (max(seqs) if seqs else 0) + 1
#|            for n, (name, typ) in enumerate(d.get("columns") or []):
#|                cols = [col["structure_parent"], col["structure_field"]]
#|                vals = [quote(entry.get("id")), quote(name)]
#|                for key, val in (("structure_type", quote(str(typ).split("(")[0].upper())), ("structure_order", str(nxt + n)),
#|                                 ("structure_nullable", required_flag)):
#|                    if col[key]:
#|                        cols.append(col[key])
#|                        vals.append(val)
#|                add(f"NOT NULL column '{name}' is never supplied", "config (or give the column a default)",
#|                    f"INSERT INTO {st} ({', '.join(cols)}) VALUES ({', '.join(vals)});",
#|                    "only if the file really carries this value; if NiFi / the load sets it, give the table column a DEFAULT instead")
#|        elif kind == "column-missing" and st and col["structure_field"]:
#|            for name, table_col in d.get("pairs") or []:
#|                f = fields.get(str(name).lower())
#|                if f and table_col:
#|                    add(f"structure field '{name}' has no column; the table has '{table_col}'", "config",
#|                        f"UPDATE {st} SET {col['structure_field']} = {quote(table_col)} WHERE {_where(f['key'])};",
#|                        "if the field is really the same column")
#|        elif kind == "missing-field" and i["severity"] == "error" and st and col["structure_nullable"]:
#|            f = fields.get(str(d.get("field", "")).lower())
#|            if f:
#|                add(f"mandatory field '{f['name']}' missing from the file", "sender (preferred) or config",
#|                    f"UPDATE {st} SET {col['structure_nullable']} = {optional_flag} WHERE {_where(f['key'])};",
#|                    "prefer asking the sender to include it; make it optional only if the business agrees")
#|        elif kind == "target-missing" and dt and col["definition_target"] and d.get("suggestion"):
#|            add(f"target table '{d['target']}' does not exist", "config",
#|                f"UPDATE {dt} SET {col['definition_target']} = {quote(d['suggestion'])} WHERE {col['definition_id']} = {quote(entry.get('id'))};",
#|                "or create the table if the name is right")
#|        elif kind == "data-delimiter" and dt and d.get("column") and col["definition_id"]:
#|            add(f"the file uses {d['delimiter']!r}", "sender (preferred) or config",
#|                f"UPDATE {dt} SET {d['column']} = {quote(d['delimiter'])} WHERE {col['definition_id']} = {quote(entry.get('id'))};",
#|                "only if the sender changed the format on purpose and will keep it; otherwise ask them to send the agreed delimiter")
#|    return out
#|
#|
#|def format_fixes(fixes, indent="  "):
#|    if not fixes:
#|        return []
#|    L = [f"{indent}proposed fixes (review first - nifikb never runs them):"]
#|    for f in fixes:
#|        L.append(f"{indent}  -- {f['why']} [{f['who']}]" + (f": {f['note']}" if f.get("note") else ""))
#|        L.append(f"{indent}  {f['sql']}")
#|    return L
#@@ FILE nifikb/flow.py tc 1c02906b1b263cec
#|"""Load a NiFi flow into one normalized model.
#|
#|Supported inputs:
#|  * conf/flow.json.gz            (NiFi 1.16+ / 2.x)
#|  * conf/flow.xml.gz             (NiFi 1.x, older installs only have this one)
#|  * exported flow definitions    ("Download flow definition" / NiFi Registry snapshot JSON)
#|"""
#|import gzip
#|import json
#|import xml.etree.ElementTree as ET
#|from collections import Counter
#|from pathlib import Path
#|
#|NODE_KINDS = ("PROCESSOR", "INPUT_PORT", "OUTPUT_PORT", "FUNNEL", "REMOTE_INPUT_PORT", "REMOTE_OUTPUT_PORT")
#|
#|
#|class Flow:
#|    def __init__(self, source, fmt):
#|        self.source = str(source)
#|        self.format = fmt
#|        self.root_id = None
#|        self.groups = {}          # id -> {id, name, parent_id, comments, variables, parameter_context, path}
#|        self.components = {}      # id -> processor / port / funnel / remote port
#|        self.services = {}        # id -> controller service
#|        self.connections = []     # {id, name, source_id, dest_id, relationships, group_id, ...}
#|        self.labels = []          # {group_id, text}
#|        self.param_contexts = {}  # name -> {params: {name: {value, sensitive, description}}, inherits: [names]}
#|        self.reporting_tasks = []
#|        self.aliases = {}         # instance id / versioned id -> canonical id
#|
#|    def resolve_id(self, ident):
#|        return self.aliases.get(ident, ident)
#|
#|    def alias(self, other, canonical):
#|        if other and other != canonical:
#|            self.aliases[other] = canonical
#|
#|    def group_chain(self, group_id):
#|        """Group ids from the given group up to the root."""
#|        chain = []
#|        while group_id and group_id in self.groups and group_id not in chain:
#|            chain.append(group_id)
#|            group_id = self.groups[group_id]["parent_id"]
#|        return chain
#|
#|    def nifi_version(self):
#|        versions = Counter(
#|            c["bundle"].get("version")
#|            for c in list(self.components.values()) + list(self.services.values())
#|            if c.get("bundle", {}).get("group") == "org.apache.nifi" and c["bundle"].get("version")
#|        )
#|        return versions.most_common(1)[0][0] if versions else None
#|
#|    def finish(self):
#|        for gid, g in self.groups.items():
#|            names = [self.groups[x]["name"] for x in reversed(self.group_chain(gid))]
#|            g["path"] = " / ".join(names)
#|            g["depth"] = len(names) - 1
#|        # Connections can point at components we did not see (remote ports of old exports, broken flows).
#|        for c in self.connections:
#|            for end in ("source", "dest"):
#|                cid = c[f"{end}_id"] = self.resolve_id(c[f"{end}_id"])
#|                if cid not in self.components:
#|                    self.components[cid] = _component(
#|                        cid, None, c.get(f"{end}_type") or "UNKNOWN", c.get(f"{end}_name") or "?", None, {},
#|                        c.get(f"{end}_group_id") or c["group_id"], placeholder=True)
#|        return self
#|
#|
#|def _component(cid, instance_id, kind, name, ctype, bundle, group_id, **extra):
#|    comp = {
#|        "id": cid, "instance_id": instance_id, "kind": kind, "name": name or "", "type": ctype or "",
#|        "bundle": bundle or {}, "group_id": group_id, "properties": {}, "state": None,
#|        "scheduling_strategy": None, "scheduling_period": None, "concurrent_tasks": None,
#|        "auto_terminated": [], "comments": "", "execution_node": None, "placeholder": False,
#|    }
#|    comp.update(extra)
#|    return comp
#|
#|
#|def load_flow(path):
#|    path = Path(path)
#|    data = path.read_bytes()
#|    if data[:2] == b"\x1f\x8b":
#|        data = gzip.decompress(data)
#|    text = data.decode("utf-8-sig")
#|    if text.lstrip().startswith("<"):
#|        return _load_xml(path, ET.fromstring(text)).finish()
#|    return _load_json(path, json.loads(text)).finish()
#|
#|
#|# ----------------------------------------------------------------------------------------------- JSON
#|
#|def _load_json(path, doc):
#|    if "rootGroup" in doc:
#|        flow, root, contexts = Flow(path, "flow.json"), doc["rootGroup"], doc.get("parameterContexts") or []
#|        for cs in doc.get("controllerServices") or []:
#|            _json_service(flow, cs, None)
#|        flow.reporting_tasks = [
#|            {"name": r.get("name"), "type": r.get("type"), "properties": r.get("properties") or {}}
#|            for r in doc.get("reportingTasks") or []
#|        ]
#|    elif "flowContents" in doc:
#|        flow, root, contexts = Flow(path, "flow-definition"), doc["flowContents"], doc.get("parameterContexts") or {}
#|    else:
#|        raise ValueError(f"{path}: not a NiFi flow (no rootGroup / flowContents)")
#|    if isinstance(contexts, dict):
#|        contexts = list(contexts.values())
#|    for pc in contexts:
#|        flow.param_contexts[pc["name"]] = {
#|            "params": {
#|                p["name"]: {"value": p.get("value"), "sensitive": bool(p.get("sensitive")), "description": p.get("description")}
#|                for p in pc.get("parameters") or []
#|            },
#|            "inherits": list(pc.get("inheritedParameterContexts") or []),
#|            "description": pc.get("description"),
#|        }
#|    _json_group(flow, root, None)
#|    flow.root_id = root.get("identifier")
#|    return flow
#|
#|
#|def _json_vc(c):
#|    if not c:
#|        return None
#|    return {"registry": c.get("registryUrl") or c.get("registryId") or c.get("storageLocation"), "bucket": c.get("bucketId"),
#|            "flow": c.get("flowId"), "flow_name": c.get("flowName"), "version": c.get("version"), "latest": c.get("latest")}
#|
#|
#|def _xml_vc(el):
#|    if el is None:
#|        return None
#|    return {"registry": _t(el, "registryId"), "bucket": _t(el, "bucketName") or _t(el, "bucketId"), "bucket_id": _t(el, "bucketId"),
#|            "flow": _t(el, "flowId"), "flow_name": _t(el, "flowName"), "version": _t(el, "version")}
#|
#|
#|def _json_group(flow, g, parent_id):
#|    gid = g.get("identifier")
#|    flow.alias(g.get("instanceIdentifier"), gid)
#|    flow.groups[gid] = {
#|        "id": gid, "name": g.get("name") or "NiFi Flow", "parent_id": parent_id, "comments": g.get("comments") or "",
#|        "variables": dict(g.get("variables") or {}), "parameter_context": g.get("parameterContextName"),
#|        "versioned": bool(g.get("versionedFlowCoordinates")), "instance_id": g.get("instanceIdentifier") or gid,
#|        "version_control": _json_vc(g.get("versionedFlowCoordinates")),
#|    }
#|    for p in g.get("processors") or []:
#|        _json_component(flow, p, "PROCESSOR", gid)
#|    for p in g.get("inputPorts") or []:
#|        _json_component(flow, p, "INPUT_PORT", gid)
#|    for p in g.get("outputPorts") or []:
#|        _json_component(flow, p, "OUTPUT_PORT", gid)
#|    for f in g.get("funnels") or []:
#|        _json_component(flow, f, "FUNNEL", gid)
#|    for rpg in g.get("remoteProcessGroups") or []:
#|        target = rpg.get("targetUris") or rpg.get("targetUri") or ""
#|        for kind, key in (("REMOTE_INPUT_PORT", "inputPorts"), ("REMOTE_OUTPUT_PORT", "outputPorts")):
#|            for port in rpg.get(key) or []:
#|                comp = _json_component(flow, port, kind, gid)
#|                comp["name"] = f"{rpg.get('name') or target} :: {port.get('name')}"
#|                comp["type"] = f"remote site-to-site {target}"
#|    for cs in g.get("controllerServices") or []:
#|        _json_service(flow, cs, gid)
#|    for c in g.get("connections") or []:
#|        src, dst = c.get("source") or {}, c.get("destination") or {}
#|        flow.alias(c.get("instanceIdentifier"), c.get("identifier"))
#|        flow.connections.append({
#|            "id": c.get("identifier"), "name": c.get("name") or "", "group_id": gid,
#|            "source_id": src.get("id"), "source_type": src.get("type"), "source_name": src.get("name"), "source_group_id": src.get("groupId"),
#|            "dest_id": dst.get("id"), "dest_type": dst.get("type"), "dest_name": dst.get("name"), "dest_group_id": dst.get("groupId"),
#|            "relationships": sorted(c.get("selectedRelationships") or []),
#|            "backpressure": f"{c.get('backPressureObjectThreshold')} / {c.get('backPressureDataSizeThreshold')}",
#|            "expiration": c.get("flowFileExpiration"), "prioritizers": c.get("prioritizers") or [],
#|            "load_balance": c.get("loadBalanceStrategy"),
#|        })
#|    for label in g.get("labels") or []:
#|        if (label.get("label") or "").strip():
#|            flow.labels.append({"group_id": gid, "text": label["label"].strip()})
#|    for child in g.get("processGroups") or []:
#|        _json_group(flow, child, gid)
#|
#|
#|def _json_component(flow, p, kind, gid):
#|    cid = p.get("identifier")
#|    flow.alias(p.get("instanceIdentifier"), cid)
#|    comp = _component(
#|        cid, p.get("instanceIdentifier"), kind, p.get("name") or ("funnel" if kind == "FUNNEL" else ""), p.get("type"),
#|        p.get("bundle"), gid,
#|        properties={k: v for k, v in (p.get("properties") or {}).items() if v is not None},
#|        state="STOPPED" if p.get("scheduledState") == "ENABLED" else p.get("scheduledState"), scheduling_strategy=p.get("schedulingStrategy"),
#|        scheduling_period=p.get("schedulingPeriod"), concurrent_tasks=p.get("concurrentlySchedulableTaskCount"),
#|        auto_terminated=sorted(p.get("autoTerminatedRelationships") or []), comments=p.get("comments") or "",
#|        execution_node=p.get("executionNode"), annotation_data=p.get("annotationData") or "",
#|    )
#|    flow.components[cid] = comp
#|    return comp
#|
#|
#|def _json_service(flow, cs, gid):
#|    sid = cs.get("identifier")
#|    flow.alias(cs.get("instanceIdentifier"), sid)
#|    flow.services[sid] = _component(
#|        sid, cs.get("instanceIdentifier"), "CONTROLLER_SERVICE", cs.get("name"), cs.get("type"), cs.get("bundle"), gid,
#|        properties={k: v for k, v in (cs.get("properties") or {}).items() if v is not None},
#|        state=cs.get("scheduledState"), comments=cs.get("comments") or "",
#|    )
#|
#|
#|# ------------------------------------------------------------------------------------------------ XML
#|
#|def _t(el, tag, default=None):
#|    child = el.find(tag)
#|    return child.text if child is not None and child.text is not None else default
#|
#|
#|def _props(el):
#|    return {_t(p, "name"): _t(p, "value") for p in el.findall("property") if _t(p, "value") is not None}
#|
#|
#|def _bundle(el):
#|    b = el.find("bundle")
#|    return {"group": _t(b, "group"), "artifact": _t(b, "artifact"), "version": _t(b, "version")} if b is not None else {}
#|
#|
#|def _load_xml(path, root_el):
#|    flow = Flow(path, "flow.xml")
#|    ctx_names = {}
#|    for pc in root_el.findall("./parameterContexts/parameterContext"):
#|        name = _t(pc, "name")
#|        ctx_names[_t(pc, "id")] = name
#|        flow.param_contexts[name] = {
#|            "params": {
#|                _t(p, "name"): {"value": _t(p, "value"), "sensitive": _t(p, "sensitive") == "true", "description": _t(p, "description")}
#|                for p in pc.findall("parameter")
#|            },
#|            "inherits": [x.text for x in pc.findall("inheritedParameterContextId") if x.text],
#|            "description": _t(pc, "description"),
#|        }
#|    for ctx in flow.param_contexts.values():
#|        ctx["inherits"] = [ctx_names.get(i, i) for i in ctx["inherits"]]
#|    rg = root_el.find("rootGroup")
#|    _xml_group(flow, rg, None, ctx_names)
#|    flow.root_id = _t(rg, "id")
#|    for cs in root_el.findall("./controllerServices/controllerService"):
#|        _xml_service(flow, cs, None)
#|    for rt in root_el.findall("./reportingTasks/reportingTask"):
#|        flow.reporting_tasks.append({"name": _t(rt, "name"), "type": _t(rt, "class"), "properties": _props(rt)})
#|    return flow
#|
#|
#|def _xml_group(flow, g, parent_id, ctx_names):
#|    gid = _t(g, "id")
#|    flow.alias(_t(g, "versionedComponentId"), gid)
#|    flow.groups[gid] = {
#|        "id": gid, "name": _t(g, "name") or "NiFi Flow", "parent_id": parent_id, "comments": _t(g, "comment", ""),
#|        "variables": {v.get("name"): v.get("value") for v in g.findall("variable")},
#|        "parameter_context": ctx_names.get(_t(g, "parameterContextId")), "versioned": g.find("versionControlInformation") is not None,
#|        "instance_id": gid, "version_control": _xml_vc(g.find("versionControlInformation")),
#|    }
#|    for p in g.findall("processor"):
#|        pid = _t(p, "id")
#|        flow.alias(_t(p, "versionedComponentId"), pid)
#|        flow.components[pid] = _component(
#|            pid, pid, "PROCESSOR", _t(p, "name"), _t(p, "class"), _bundle(p), gid, properties=_props(p),
#|            state=_t(p, "scheduledState"), scheduling_strategy=_t(p, "schedulingStrategy"),
#|            scheduling_period=_t(p, "schedulingPeriod"), concurrent_tasks=int(_t(p, "maxConcurrentTasks", "1")),
#|            auto_terminated=sorted(x.text for x in p.findall("autoTerminatedRelationship") if x.text),
#|            comments=_t(p, "comment", ""), execution_node=_t(p, "executionNode"), annotation_data=_t(p, "annotationData", ""),
#|        )
#|    for tag, kind in (("inputPort", "INPUT_PORT"), ("outputPort", "OUTPUT_PORT"), ("funnel", "FUNNEL")):
#|        for p in g.findall(tag):
#|            pid = _t(p, "id")
#|            flow.alias(_t(p, "versionedComponentId"), pid)
#|            flow.components[pid] = _component(pid, pid, kind, _t(p, "name", "funnel" if kind == "FUNNEL" else ""), None, {}, gid,
#|                                              state=_t(p, "scheduledState"), comments=_t(p, "comments", ""))
#|    for rpg in g.findall("remoteProcessGroup"):
#|        target = _t(rpg, "urls") or _t(rpg, "url") or ""
#|        for tag, kind in (("inputPort", "REMOTE_INPUT_PORT"), ("outputPort", "REMOTE_OUTPUT_PORT")):
#|            for port in rpg.findall(tag):
#|                pid = _t(port, "id")
#|                flow.alias(_t(port, "versionedComponentId"), pid)
#|                flow.components[pid] = _component(pid, pid, kind, f"{_t(rpg, 'name') or target} :: {_t(port, 'name')}",
#|                                                  f"remote site-to-site {target}", {}, gid)
#|    for cs in g.findall("controllerService"):
#|        _xml_service(flow, cs, gid)
#|    for c in g.findall("connection"):
#|        flow.alias(_t(c, "versionedComponentId"), _t(c, "id"))
#|        flow.connections.append({
#|            "id": _t(c, "id"), "name": _t(c, "name", ""), "group_id": gid,
#|            "source_id": _t(c, "sourceId"), "source_type": _t(c, "sourceType"), "source_name": None, "source_group_id": _t(c, "sourceGroupId"),
#|            "dest_id": _t(c, "destinationId"), "dest_type": _t(c, "destinationType"), "dest_name": None, "dest_group_id": _t(c, "destinationGroupId"),
#|            "relationships": sorted(x.text for x in c.findall("relationship") if x.text),
#|            "backpressure": f"{_t(c, 'maxWorkQueueSize')} / {_t(c, 'maxWorkQueueDataSize')}",
#|            "expiration": _t(c, "flowFileExpiration"),
#|            "prioritizers": [x.text for x in c.findall("queuePrioritizerClass") if x.text],
#|            "load_balance": _t(c, "loadBalanceStrategy"),
#|        })
#|    for label in g.findall("label"):
#|        if (_t(label, "value") or "").strip():
#|            flow.labels.append({"group_id": gid, "text": _t(label, "value").strip()})
#|    for child in g.findall("processGroup"):
#|        _xml_group(flow, child, gid, ctx_names)
#|
#|
#|def _xml_service(flow, cs, gid):
#|    sid = _t(cs, "id")
#|    flow.alias(_t(cs, "versionedComponentId"), sid)
#|    flow.services[sid] = _component(
#|        sid, sid, "CONTROLLER_SERVICE", _t(cs, "name"), _t(cs, "class"), _bundle(cs), gid, properties=_props(cs),
#|        state="ENABLED" if _t(cs, "enabled") == "true" else "DISABLED", comments=_t(cs, "comment", ""),
#|    )
#@@ FILE nifikb/investigate.py tc f6d959c3058b0a9e
#|"""One-call ticket investigation: metadata diagnosis + provenance + logs + code messages + learnings + static findings,
#|merged into a ranked list of likely causes with the evidence under it. Built for smaller models (Gemini Flash): the
#|tool does the planning, the model explains the result."""
#|import re
#|import time
#|from pathlib import Path
#|
#|from . import audit as auditmod, diagnose as dg, learnings as lm, logs as lg, metadata as metamod, nifiapi, target as tgt
#|
#|PRIORITY = {"provenance": 1, "audit": 2, "target": 2.5, "live": 3, "file-log": 4, "structure": 5, "config-change": 6, "instance": 7,
#|            "processor-log": 8, "learning": 9, "finding": 10, "warning": 11}
#|
#|
#|def _runtime_ids(store, flow_ids):
#|    ids = set(flow_ids)
#|    for fid in flow_ids:
#|        try:
#|            row = store.db.execute("SELECT instance_id FROM components WHERE id=?", (fid,)).fetchone()
#|        except Exception:
#|            row = None
#|        if row and row[0]:
#|            ids.add(row[0])
#|    return sorted(ids)
#|
#|
#|def investigate(cfg, store, names, file=None, feed=None, table=None, error_text=None, headers=(), sample_path=None,
#|                live=False, since_hours=72, record=True):
#|    key = file or feed or table
#|    causes, sections, next_checks = [], [], []
#|
#|    def cause(kind, text):
#|        causes.append((PRIORITY[kind], len(causes), text, kind))
#|
#|    # 1. metadata: definition, structure vs file, target, related config, processors, config changes
#|    diag, proc_ids = None, []
#|    if key and metamod.settings(cfg) and store.get_meta("metadata_model"):
#|        diag = dg.metadata_diagnosis(cfg, store, key, list(headers), live=live, sample_path=sample_path)
#|        sections.append(("Metadata (config tables)", dg.format_text(diag)))
#|        fixes = [f for d in diag.get("definitions") or [] for f in d.get("fixes") or []]
#|        if fixes:
#|            text = "\n".join(f"-- {f['why']} [{f['who']}]" + (f": {f['note']}" if f.get("note") else "") + "\n" + f["sql"] for f in fixes)
#|            sections.insert(0, ("Proposed fixes (for a human to review and run - never applied automatically)", text))
#|        proc_ids = [p["id"] for p in diag.get("processors") or []]
#|        for d in diag.get("definitions") or []:
#|            for i in d["issues"]:
#|                if i["severity"] == "error":
#|                    cause("structure", f"{d['label']}: {i['message']}")
#|                elif i["severity"] == "warn":
#|                    cause("warning", f"{d['label']}: {i['message']}")
#|        for c in diag.get("changed_since_snapshot") or []:
#|            cause("config-change", f"config row changed since the last snapshot: {c}")
#|        recent = [c for c in diag.get("recent_changes") or []
#|                  if time.time() - time.mktime(time.strptime(c["when"], "%Y-%m-%d %H:%M")) < 3 * 86400]
#|        for c in recent[:5]:
#|            cause("config-change", f"config row changed {c['when']}: {c['change']}")
#|        if not diag.get("matches"):
#|            next_checks.append(f"'{key}' matches no config row" + (f" - did you mean {', '.join(diag['suggestions'][:3])}?"
#|                                                                   if diag.get("suggestions") else "; try the feed / table / API name"))
#|    elif key:
#|        next_checks.append("metadata not configured ([metadata] in nifikb.toml) - no structure / config checks")
#|
#|    # 2. provenance: where did the FlowFile(s) end up
#|    api = nifiapi.settings(cfg)
#|    if file and api:
#|        try:
#|            flows = nifiapi.journey(nifiapi.Client(api), filename=Path(file.replace("\\", "/")).name)
#|            sections.append(("Provenance (what happened to the FlowFile)", nifiapi.format_journey(flows, names, file)))
#|            for f in flows:
#|                if f["verdict"].startswith(("DROPPED", "last seen")):
#|                    cause("provenance", f"FlowFile {str(f['uuid'])[:8]} {f['verdict']}"
#|                          + (f" [{', '.join(f'{k}={v}' for k, v in list(f['attributes'].items())[:4])}]" if f["attributes"] else ""))
#|            if not flows:
#|                cause("provenance", f"no provenance events for '{file}': it never entered NiFi under that name (not picked up: "
#|                                    "source path / listing / file-name filter) or its events aged out")
#|        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
#|            next_checks.append(f"provenance not available: {e}")
#|    elif file:
#|        next_checks.append("configure [nifi_api] to see where the FlowFile was dropped (provenance)")
#|
#|    # 2a. the platform's own load-audit record of this file / definition
#|    amodel = store.get_meta("audit_model")
#|    if amodel and (file or diag):
#|        try:
#|            ids = [d["id"] for d in (diag or {}).get("definitions") or []]
#|            fname_a = Path(file.replace("\\", "/")).name if file else None
#|            rows = auditmod.lookup(cfg, amodel, file=fname_a, link_ids=ids if not fname_a else ())
#|            if not rows and ids:
#|                rows = auditmod.lookup(cfg, amodel, link_ids=ids)
#|            sections.append((f"Load audit ({amodel['table']})", auditmod.format_rows(amodel, rows)))
#|            file_rows_a = [r for r in rows if fname_a and fname_a.lower() in str(r.get(amodel["file_column"]) or "").lower()]
#|            if file_rows_a:
#|                last = file_rows_a[0]
#|                if auditmod.is_failure(amodel, last):
#|                    cause("audit", f"load audit: last load FAILED - {auditmod.summarize(amodel, last)}")
#|                else:
#|                    cause("warning", f"load audit: last load recorded as {auditmod.summarize(amodel, last)}")
#|            elif fname_a:
#|                cause("warning", f"no load-audit row for {fname_a}: the load step never recorded this file")
#|        except Exception as e:  # DB down etc.: never break the investigation
#|            next_checks.append(f"load audit not available: {e}")
#|
#|    # 2a'. the target side: did the load write anything to HDFS / S3, and does the Parquet match the structure
#|    if diag and tgt.enabled(cfg):
#|        for d, res in tgt.check_diagnosis(cfg, store.get_meta("metadata_model"), diag, file=file):
#|            sections.append((f"Target output ({d['label']})", tgt.format_check(res)))
#|            for sev, kind, msg in res["issues"]:
#|                if sev == "error":
#|                    cause("target", f"{d['label']} target: {msg}")
#|                elif sev == "warn":
#|                    cause("warning", f"{d['label']} target: {msg}")
#|
#|    # 2b. live health of the processors involved (stuck queue / invalid / stopped) and of the whole instance (disk, heap)
#|    if api:
#|        try:
#|            h = nifiapi.health(nifiapi.Client(api), versioned=store.versioned_groups())
#|            involved = set(_runtime_ids(store, proc_ids))
#|            mine = [p for p in h["problems"] if p.get("component_id") in involved]
#|            instance = [p for p in h["problems"] if p["kind"] in ("disk", "heap", "cluster")]
#|            for p in mine:
#|                cause("live", f"live NiFi: {p['message']}")
#|            for p in instance:
#|                cause("instance", f"live NiFi (whole instance): {p['message']}")
#|            if mine or instance:
#|                sections.append(("Live NiFi health (problems touching this ticket)", "\n".join(
#|                    f"[{p['severity']}] {p['kind']}: {p['message']}" for p in mine + instance)))
#|        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
#|            next_checks.append(f"live health not available: {e}")
#|
#|    # 3. logs: errors about this file, and about the processors involved
#|    lg.index(cfg, store, log=lambda m: None)
#|    fname = Path(file.replace("\\", "/")).name if file else None
#|    file_rows = lg.query(store, filename=fname, limit=10) if fname else []
#|    for r in file_rows:
#|        if r["level"] in ("ERROR", "FATAL", "WARN"):
#|            who = names.get(r["component_id"], r["component_type"] or "NiFi")
#|            cause("file-log", f"{who} logged {r['level']} x{r['n']} for this file: {lg.compact(r['sample'])[:220]}"
#|                              + (f" - cause: {r['cause']}" if r["cause"] else ""))
#|    runtime = _runtime_ids(store, proc_ids)
#|    proc_rows = lg.query(store, component_ids=runtime, since_hours=since_hours, limit=10) if runtime else []
#|    listed = {(r["component_id"], r["template"]) for r in file_rows}
#|    proc_rows = [r for r in proc_rows if (r["component_id"], r["template"]) not in listed]  # already ranked as file errors
#|    for r in proc_rows[:4]:
#|        if r["level"] in ("ERROR", "FATAL"):
#|            cause("processor-log", f"{names.get(r['component_id'], r['component_type'])} logged ERROR x{r['n']} "
#|                                   f"({r['first'][:16]} .. {r['last'][:16]}): {lg.compact(r['sample'])[:180]}"
#|                                   + (f" - cause: {r['cause']}" if r["cause"] else ""))
#|    grep_rows = lg.query(store, grep=error_text, limit=10) if error_text else []
#|    for title, rows in (("Log errors for this file", file_rows), ("Log errors of the processors involved", proc_rows),
#|                        (f"Log lines containing '{error_text}'", grep_rows)):
#|        if rows:
#|            sections.append((title, lg.format_rows(rows, names)))
#|
#|    # 4. the error text in the custom code (which processor / line raises it)
#|    if error_text:
#|        words = [w for w in error_text.replace('"', " ").split() if len(w) > 2][:8]
#|        hits = [r for r in store.search(" ".join(words), 10) if r["kind"] == "message"] if words else []
#|        if hits:
#|            sections.append(("Code that produces this error text", "\n".join(f"{r['title']} -> {r['doc']}: {r['snip']}" for r in hits)))
#|            cause("processor-log", f"the error text comes from {hits[0]['title']} ({hits[0]['doc']})")
#|
#|    # 5. learnings
#|    items = (diag or {}).get("learnings") or []
#|    if not items:
#|        terms = [x for x in (key, fname, table, feed) if x] + (error_text.split()[:6] if error_text else [])
#|        items = dg.learnings_for(cfg, terms)
#|    for i in items[:3]:
#|        if i["score"] >= 3:
#|            cause("learning", f"known issue {i['id']}: {i['title']}")
#|    if items:
#|        sections.append(("Team learnings", "\n".join(f"{i['id']} [{i['kind']}] {i['title']}\n  {i['excerpt'][:300]}" for i in items)))
#|
#|    # 6. static findings on the processors involved
#|    for f in (diag or {}).get("findings") or []:
#|        if f["kind"] in ("attribute-unset", "attribute-misnamed", "custom-source-drift", "custom-nar-missing", "bundle-version",
#|                         "field-mismatch", "missing-table", "unhandled-relationship", "disabled-service"):
#|            cause("finding", f"{f['kind']} on `{f['component_id'][:8]}`: {f['message']}")
#|        elif f["kind"] == "dropped-errors":
#|            cause("warning", f"`{f['component_id'][:8]}` silently drops failures ({f['message'].split(':')[0]}) - errors there leave "
#|                             "only a log line / provenance DROP")
#|
#|    causes.sort()
#|    seen, ranked = set(), []
#|    for _, _, text, kind in causes:
#|        if text not in seen:
#|            seen.add(text)
#|            ranked.append((kind, text))
#|    if key and record:
#|        try:  # remembered for learning suggestions (recurring causes nobody has written down yet)
#|            store.add_investigation(key, [(k, signature(t), t) for k, t in ranked[:3] if k not in NOT_REMEMBERED])
#|        except Exception:
#|            pass  # a read-only / locked KB must not break the investigation
#|    return {"key": key, "causes": [t for _, t in ranked[:10]], "sections": sections, "next_checks": next_checks}
#|
#|
#|NOT_REMEMBERED = {"learning", "instance", "warning"}  # already written down / not about the ticket / too weak
#|
#|
#|def signature(text):
#|    """A cause without its variable parts (dates, counts, ids, quoted values), so repeats of one problem group together."""
#|    s = re.sub(r"'[^']*'|`[^`]*`|\"[^\"]*\"", "'…'", text)
#|    s = re.sub(r"\b[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b[0-9a-f]{8}\b", "#", s)
#|    s = re.sub(r"\d{4}-\d\d-\d\d[ T]?[\d:.,]*|\d+", "#", s)
#|    s = re.sub(r"\[[^\]]*=[^\]]*\]", "", s)  # attribute dumps
#|    return re.sub(r"\s+", " ", s).strip()[:300]
#|
#|
#|def format_report(r):
#|    L = [f"# Investigation: {r['key'] or '(no name given)'}", "", "## Most likely causes (ranked; strongest evidence first)"]
#|    L += [f"{n}. {c}" for n, c in enumerate(r["causes"], 1)] or ["(nothing conclusive found - see the evidence and next checks)"]
#|    if r["next_checks"]:
#|        L += ["", "## Next checks"] + [f"- {c}" for c in r["next_checks"]]
#|    for title, text in r["sections"]:
#|        L += ["", f"## {title}", text]
#|    return "\n".join(L)
#@@ FILE nifikb/late.py tc 19dec5c5881231d9
#|"""Late / missing files: learn each feed's arrival pattern from the load-audit history (successful loads) and flag the
#|feeds whose next file is overdue - before a user raises a ticket.
#|
#|Per definition (audit link column) or, without one, per file-name shape (SALES_20260926.csv -> sales_#.csv):
#|  intra-day feeds (median gap < 20 h)  late when nothing arrived for 3 x the usual gap (at least 1 h)
#|  daily feeds                          expected on the weekdays it usually arrives, around its usual time of day;
#|                                       late when today's file is past that time + tolerance (the spread of past arrivals, >= 1 h)
#|  weekly / monthly feeds               late when the gap since the last arrival exceeds 1.5 x the usual gap
#|Feeds with fewer than `min_history` arrivals are not judged."""
#|import datetime as dt
#|import statistics
#|from collections import defaultdict
#|from pathlib import PurePath
#|
#|from . import audit as auditmod, db as dbmod, metadata as metamod
#|
#|
#|def _when(v):
#|    if isinstance(v, dt.datetime):
#|        return v
#|    if isinstance(v, dt.date):
#|        return dt.datetime(v.year, v.month, v.day)
#|    s = str(v or "").strip().replace("T", " ")
#|    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%Y%m%d%H%M%S"):
#|        try:
#|            return dt.datetime.strptime(s[:26], fmt)
#|        except ValueError:
#|            continue
#|    return None
#|
#|
#|def history(cfg, model, days):
#|    """Audit rows of the last `days` days: [{file, when, failed, link}] (oldest first)."""
#|    if not model.get("time_column"):
#|        raise ValueError("the load-audit table has no time column ([audit] time_column)")
#|    a = auditmod.settings(cfg)
#|    dcfg = next(d for d in cfg["databases"] if d["name"] == a["db"])
#|    conn, dialect = dbmod.connect(dcfg)
#|    try:
#|        q = '"' if dialect != "mysql" else "`"
#|        cols = [c for c in (model["file_column"], model["time_column"], model.get("status_column"), model.get("link_column")) if c]
#|        since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
#|        sql = (f"SELECT {', '.join(f'{q}{c}{q}' for c in cols)} FROM {auditmod._fq(dialect, model.get('schema'), model['table'])} "
#|               f"WHERE {q}{model['time_column']}{q} >= {dbmod._ph(dialect)} ORDER BY {q}{model['time_column']}{q} LIMIT 200000")
#|        rows = dbmod._rows(conn, sql, (since,))
#|    finally:
#|        conn.close()
#|    out = []
#|    for r in rows:
#|        when = _when(r.get(model["time_column"]))
#|        if when:
#|            out.append({"file": r.get(model["file_column"]), "when": when, "failed": auditmod.is_failure(model, r),
#|                        "link": r.get(model["link_column"]) if model.get("link_column") else None})
#|    return out
#|
#|
#|def _group_key(row):
#|    if row["link"] is not None:
#|        return ("id", str(row["link"]))
#|    name = PurePath(str(row["file"] or "").replace("\\", "/")).name
#|    return ("shape", metamod._shape(name))
#|
#|
#|def _fmt_gap(seconds):
#|    if seconds < 3600:
#|        return f"{seconds / 60:.0f} min"
#|    if seconds < 2 * 86400:
#|        return f"{seconds / 3600:.1f} h"
#|    return f"{seconds / 86400:.1f} days"
#|
#|
#|def analyse(rows, now=None, min_history=5, labels=None):
#|    """[{key, label, kind, last, expected, late_by, message, last_failed}] for overdue feeds, most overdue first."""
#|    now = now or dt.datetime.now()
#|    groups = defaultdict(list)
#|    for r in rows:
#|        groups[_group_key(r)].append(r)
#|    out = []
#|    for key, rs in groups.items():
#|        rs.sort(key=lambda r: r["when"])
#|        ok = [r["when"] for r in rs if not r["failed"]]
#|        if len(ok) < min_history:
#|            continue
#|        label = (labels or {}).get(key[1]) or (PurePath(str(rs[-1]["file"] or "").replace("\\", "/")).name if key[0] == "id" else key[1])
#|        last = ok[-1]
#|        last_failed = rs[-1]["failed"] and rs[-1]["when"] > last
#|        gaps = [(b - a).total_seconds() for a, b in zip(ok, ok[1:]) if (b - a).total_seconds() > 60]
#|        if not gaps:
#|            continue
#|        gap = statistics.median(gaps)
#|        since_last = (now - last).total_seconds()
#|        item = None
#|        if gap < 20 * 3600:
#|            allowed = max(3 * gap, 3600)
#|            if since_last > allowed:
#|                item = {"kind": "intra-day", "expected": last + dt.timedelta(seconds=gap), "late_by": since_last - gap,
#|                        "message": f"no file for {_fmt_gap(since_last)} (usually every {_fmt_gap(gap)}); last {last:%Y-%m-%d %H:%M}"}
#|        elif gap < 2.5 * 86400:
#|            first_per_day = {}
#|            for w in ok:
#|                first_per_day.setdefault(w.date(), w)
#|            minutes = [w.hour * 60 + w.minute for w in first_per_day.values()]
#|            usual = statistics.median(minutes)
#|            spread = statistics.median([abs(m - usual) for m in minutes]) if len(minutes) > 2 else 0
#|            tolerance = max(60, 3 * spread)
#|            span_days = max(1, (ok[-1].date() - ok[0].date()).days + 1)
#|            weeks = max(1, span_days / 7)
#|            per_weekday = defaultdict(int)
#|            for d in first_per_day:
#|                per_weekday[d.weekday()] += 1
#|            weekdays = {wd for wd in range(7) if per_weekday[wd] / weeks >= 0.6}
#|            due = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=usual + tolerance)
#|            if now.weekday() in weekdays and now > due and last.date() < now.date():
#|                item = {"kind": "daily", "expected": due - dt.timedelta(minutes=tolerance),
#|                        "late_by": (now - due).total_seconds() + tolerance * 60,
#|                        "message": f"today's file not loaded - usually by {int(usual // 60):02d}:{int(usual % 60):02d} "
#|                                   f"(±{tolerance:.0f} min, on {_days(weekdays)}); last {last:%Y-%m-%d %H:%M}"}
#|        else:
#|            if since_last > 1.5 * gap + 3600:
#|                item = {"kind": "periodic", "expected": last + dt.timedelta(seconds=gap), "late_by": since_last - gap,
#|                        "message": f"no file for {_fmt_gap(since_last)} (usually every {_fmt_gap(gap)}); last {last:%Y-%m-%d %H:%M}"}
#|        if item:
#|            if last_failed:
#|                item["message"] += f" - the latest attempt ({rs[-1]['file']}, {rs[-1]['when']:%Y-%m-%d %H:%M}) FAILED"
#|            item.update(key=key[1], label=label, last=last, last_failed=last_failed)
#|            out.append(item)
#|    out.sort(key=lambda i: -i["late_by"])
#|    return out
#|
#|
#|def _days(weekdays):
#|    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
#|    if weekdays == set(range(7)):
#|        return "every day"
#|    if weekdays == set(range(5)):
#|        return "Mon-Fri"
#|    return ", ".join(names[d] for d in sorted(weekdays))
#|
#|
#|def labels_from_snapshot(store):
#|    """Definition id -> label (file pattern / name) from the metadata snapshot."""
#|    model = store.get_meta("metadata_model")
#|    if not model or not model.get("definition_table"):
#|        return {}
#|    rows = store.get_meta_rows(exclude=model.get("structure_table")).get(model["definition_table"], [])
#|    return {str(r.get(model["definition_id"])): metamod.definition_label(model, r) for r in rows}
#|
#|
#|def late_files(cfg, store, days=35, now=None, min_history=5):
#|    model = store.get_meta("audit_model")
#|    if not model:
#|        return None
#|    return analyse(history(cfg, model, days), now=now, min_history=min_history, labels=labels_from_snapshot(store))
#|
#|
#|def format_items(items, model=None):
#|    if items is None:
#|        return ["load audit not configured ([audit]) - no arrival history to learn from"]
#|    if not items:
#|        return ["no late or missing files (feeds with enough load history)"]
#|    return [f"**{i['label']}**: {i['message']}" for i in items]
#@@ FILE nifikb/learnings.py t 14b4312d20452b5a
#|"""Team knowledge that the flow, code and databases cannot tell: what we learned while fixing tickets.
#|
#|knowledge/
#|  context.md            curated team context (owners, environments, conventions, quirks) - humans maintain it
#|  learnings/<id>.md     one learning per file, written by people or by agents (Claude, Gemini, ...) after a ticket
#|
#|A learning file is markdown with a small header:
#|
#|    ---
#|    id: 2026-09-26-sales-feed-pipe-delimited
#|    title: SALES feed switches to pipe delimiter at month end
#|    kind: pattern            # fix | pattern | gotcha | context | faq
#|    date: 2026-09-26
#|    author: claude
#|    tags: [delimiter, sales]
#|    applies_to: [SALES_YYYYMMDD.csv, stg_sales, MetadataLookup]
#|    ticket: INC12345
#|    status: active           # active | obsolete
#|    ---
#|    ## Symptom / ## Cause / ## Fix / ## How to spot it next time
#|
#|Files are plain text on purpose: reviewable in git, editable by hand, safe with several agents writing at once.
#|"""
#|import datetime as _dt
#|import os
#|import re
#|from pathlib import Path
#|
#|from .db import BEARER_RE
#|from .util import REDACTED, redact_secrets, slugify
#|
#|KINDS = ("fix", "pattern", "gotcha", "context", "faq")
#|LIST_KEYS = ("tags", "applies_to")
#|MAX_BODY = 20000
#|SECRETISH = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*(?!<redacted>|\*\*\*)\S{4,}")
#|CONTEXT_TEMPLATE = """# Team context
#|
#|Curated by the team; agents read this at the start of every session (kb_overview). Keep it short and current.
#|Promote recurring learnings from `learnings/` into here.
#|
#|## Environments
#|- (e.g. PROD NiFi cluster URL, DEV/UAT, which DB holds the metadata tables)
#|
#|## Ownership / escalation
#|- (who owns which feeds / source systems, who can change OBJ_* rows, on-call rota)
#|
#|## Conventions
#|- (file naming, how new feeds are onboarded, which columns in OBJ_DEFINITION mean what)
#|
#|## Known quirks
#|- (things that look wrong but are intended, recurring vendor issues)
#|"""
#|
#|
#|def root(cfg):
#|    return Path(cfg["knowledge"]["dir"])
#|
#|
#|def ensure(cfg):
#|    r = root(cfg)
#|    (r / "learnings").mkdir(parents=True, exist_ok=True)
#|    if not (r / "context.md").exists():
#|        (r / "context.md").write_text(CONTEXT_TEMPLATE, encoding="utf-8")
#|    return r
#|
#|
#|def clean(text):
#|    """Secrets never enter the knowledge folder (it is sent to AI providers and committed to git)."""
#|    text = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(text or ""))
#|    return SECRETISH.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
#|
#|
#|# ---------------------------------------------------------------------------------------------- parse / write
#|def parse(text, path=None):
#|    meta, body = {}, text
#|    m = re.match(r"﻿?---\s*\n(.*?)\n---\s*\n?(.*)\Z", text, re.S)
#|    if m:
#|        body = m.group(2)
#|        for line in m.group(1).splitlines():
#|            if ":" not in line or line.lstrip().startswith("#"):
#|                continue
#|            k, v = line.split(":", 1)
#|            k, v = k.strip(), re.sub(r"\s+#.*$", "", v).strip()
#|            if k in LIST_KEYS:
#|                v = [x.strip().strip("'\"") for x in v.strip("[]").split(",") if x.strip()]
#|            meta[k] = v
#|    meta.setdefault("id", Path(path).stem if path else "")
#|    meta.setdefault("title", next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.strip()), meta["id"]))
#|    meta.setdefault("status", "active")
#|    meta.setdefault("kind", "fix")
#|    for k in LIST_KEYS:
#|        meta.setdefault(k, [])
#|    meta["body"] = body.strip()
#|    meta["path"] = str(path) if path else None
#|    return meta
#|
#|
#|def render(meta):
#|    head = ["---"]
#|    for k in ("id", "title", "kind", "date", "author", "tags", "applies_to", "ticket", "status", "replaced_by"):
#|        v = meta.get(k)
#|        if v in (None, "", []):
#|            continue
#|        head.append(f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}")
#|    return "\n".join(head + ["---", "", meta.get("body", "").strip(), ""])
#|
#|
#|def load_all(cfg, include_obsolete=True):
#|    d = root(cfg) / "learnings"
#|    out = []
#|    for p in sorted(d.glob("*.md")) if d.is_dir() else []:
#|        try:
#|            item = parse(p.read_text(encoding="utf-8"), p)
#|        except (OSError, UnicodeDecodeError):
#|            continue
#|        if include_obsolete or item["status"] != "obsolete":
#|            out.append(item)
#|    out.sort(key=lambda x: (x.get("date") or "", x["id"]), reverse=True)
#|    return out
#|
#|
#|def get(cfg, ident):
#|    for item in load_all(cfg):
#|        if item["id"] == ident:
#|            return item
#|    matches = [i for i in load_all(cfg) if i["id"].startswith(ident) or ident.lower() in i["id"]]
#|    return matches[0] if len(matches) == 1 else None
#|
#|
#|def add(cfg, title, body, kind="fix", tags=(), applies_to=(), ticket=None, author=None):
#|    """Write one learning; returns (meta, warnings). Secrets are redacted before anything touches disk."""
#|    title = clean(" ".join((title or "").split()))
#|    body = clean(body or "").strip()
#|    if not title:
#|        raise ValueError("a learning needs a title")
#|    if not body:
#|        raise ValueError("a learning needs a body (symptom, cause, fix, how to spot it)")
#|    if len(body) > MAX_BODY:
#|        raise ValueError(f"body is {len(body)} characters; keep a learning under {MAX_BODY} (link to the ticket instead)")
#|    kind = (kind or "fix").lower()
#|    if kind not in KINDS:
#|        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
#|    warnings = []
#|    existing = load_all(cfg, include_obsolete=False)
#|    words = set(re.findall(r"\w{4,}", title.lower()))
#|    for e in existing:
#|        other = set(re.findall(r"\w{4,}", e["title"].lower()))
#|        if words and len(words & other) / len(words | other) >= 0.6:
#|            warnings.append(f"similar learning exists: {e['id']} - {e['title']} (consider updating or retiring it)")
#|    date = _dt.date.today().isoformat()
#|    d = ensure(cfg) / "learnings"
#|    ident = f"{date}-{slugify(title, 50)}"
#|    n = 2
#|    while (d / f"{ident}.md").exists():
#|        ident = f"{date}-{slugify(title, 50)}-{n}"
#|        n += 1
#|    meta = {"id": ident, "title": title, "kind": kind, "date": date,
#|            "author": clean(author or os.environ.get("NIFIKB_AUTHOR") or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"),
#|            "tags": sorted({clean(t).strip().lower() for t in tags if t and t.strip()}),
#|            "applies_to": [clean(a).strip() for a in applies_to if a and a.strip()],
#|            "ticket": clean(ticket) if ticket else None, "status": "active", "body": body}
#|    path = d / f"{ident}.md"
#|    path.write_text(render(meta), encoding="utf-8")
#|    meta["path"] = str(path)
#|    if re.search(r"(?i)\b(password|secret|token)\b", body) and REDACTED not in body:
#|        warnings.append("the body mentions passwords / secrets - double-check nothing sensitive was written")
#|    return meta, warnings
#|
#|
#|def retire(cfg, ident, reason=None, replaced_by=None):
#|    item = get(cfg, ident)
#|    if not item:
#|        raise ValueError(f"no learning '{ident}'")
#|    item["status"] = "obsolete"
#|    if replaced_by:
#|        item["replaced_by"] = replaced_by
#|    if reason:
#|        item["body"] = item["body"] + f"\n\n> Retired {_dt.date.today().isoformat()}: {clean(reason)}"
#|    Path(item["path"]).write_text(render(item), encoding="utf-8")
#|    return item
#|
#|
#|# ---------------------------------------------------------------------------------------------- relevance
#|def relevant(cfg, terms, limit=5):
#|    """Active learnings whose applies_to / tags / title match any of the terms (file names, tables, processor names,
#|    ids, feed names). applies_to values may be patterns (SALES_*.csv, SALES_YYYYMMDD.csv)."""
#|    from .metadata import pattern_regex
#|    terms = [str(t) for t in terms if t and len(str(t)) >= 3]
#|    low = {t.lower() for t in terms}
#|    scored = []
#|    for item in load_all(cfg, include_obsolete=False):
#|        score = 0
#|        for a in item["applies_to"]:
#|            al = a.lower()
#|            if al in low:
#|                score += 3
#|                continue
#|            rx = pattern_regex(a)
#|            if rx and any(rx.match(t) for t in terms):
#|                score += 3
#|            elif any(len(t) >= 6 and (t in al or al in t) for t in low):
#|                score += 1
#|        score += sum(2 for t in item["tags"] if t.lower() in low)
#|        title = item["title"].lower()
#|        score += sum(1 for t in low if len(t) >= 5 and t in title)
#|        if score:
#|            scored.append((score, item))
#|    scored.sort(key=lambda x: (x[0], x[1].get("date") or ""), reverse=True)
#|    return [dict(i, score=s) for s, i in scored[:limit]]
#|
#|
#|def search_docs(cfg):
#|    """Search-index entries for every learning and for context.md."""
#|    docs = []
#|    for item in load_all(cfg):
#|        rel = f"../knowledge/learnings/{Path(item['path']).name}"
#|        docs.append({"kind": "learning" if item["status"] != "obsolete" else "learning-obsolete", "ref": item["id"],
#|                     "title": item["title"], "doc": rel,
#|                     "body": " ".join([item["body"], " ".join(item["tags"]), " ".join(item["applies_to"]), item.get("ticket") or ""])})
#|    ctx = root(cfg) / "context.md"
#|    if ctx.exists():
#|        docs.append({"kind": "context", "ref": "context.md", "title": "Team context", "doc": "../knowledge/context.md",
#|                     "body": ctx.read_text(encoding="utf-8")})
#|    return docs
#|
#|
#|def context_text(cfg, max_chars=12000):
#|    ctx = root(cfg) / "context.md"
#|    if not ctx.exists():
#|        return ""
#|    text = ctx.read_text(encoding="utf-8")
#|    if text.strip() == CONTEXT_TEMPLATE.strip():
#|        return ""  # untouched template adds nothing
#|    return text if len(text) <= max_chars else text[:max_chars] + "\n[… context.md continues]"
#|
#|
#|def format_item(item, full=True):
#|    head = (f"{item['id']} [{item['kind']}{', OBSOLETE' if item['status'] == 'obsolete' else ''}] {item['title']}"
#|            + (f" · tags: {', '.join(item['tags'])}" if item["tags"] else "")
#|            + (f" · applies to: {', '.join(item['applies_to'])}" if item["applies_to"] else "")
#|            + (f" · ticket {item['ticket']}" if item.get("ticket") else "")
#|            + (f" · {item.get('date')} by {item.get('author')}" if item.get("date") else ""))
#|    return head + ("\n\n" + item["body"] if full else "")
#|
#|
#|# ------------------------------------------------------------------------------------------------ suggestions
#|def suggestions(cfg, store, days=30, min_count=3, limit=10):
#|    """Causes that keep coming back in investigations and that no active learning covers yet:
#|    [{signature, count, keys, days, example, kind}], most frequent first."""
#|    import re
#|    import time
#|    rows = store.investigations_since(time.time() - days * 86400)
#|    groups = {}
#|    for r in rows:
#|        g = groups.setdefault(r["signature"], {"signature": r["signature"], "kind": r["kind"], "count": 0, "keys": [], "days": set(),
#|                                               "example": r["cause"]})
#|        g["count"] += 1
#|        g["days"].add(time.strftime("%Y-%m-%d", time.localtime(r["ts"])))
#|        if r["key"] not in g["keys"]:
#|            g["keys"].append(r["key"])
#|    items = load_all(cfg, include_obsolete=False)
#|    out = []
#|    for g in groups.values():
#|        if g["count"] < min_count or (len(g["days"]) < 2 and len(g["keys"]) < 2):
#|            continue  # one person re-running the same check is not a recurring problem
#|        label = g["example"].split(":", 1)[0] if ":" in g["example"] else ""
#|        words = {w for w in re.findall(r"[a-z][a-z_]{4,}", g["signature"].lower()) if w not in STOP}
#|        terms = g["keys"] + ([label] if label else [])
#|        covered = False
#|        for item in relevant(cfg, terms, limit=10) if items else []:
#|            text = f"{item['title']} {item['body']}".lower()
#|            if item["score"] >= 3 and sum(1 for w in words if w in text) >= min(2, len(words)):
#|                covered = True
#|                break
#|        if not covered:
#|            out.append(dict(g, days=sorted(g["days"])))
#|    out.sort(key=lambda g: (-g["count"], -len(g["keys"])))
#|    return out[:limit]
#|
#|
#|STOP = {"structure", "config", "table", "column", "columns", "field", "fields", "processor", "logged", "error", "errors", "which",
#|        "there", "their", "since", "last", "this", "that", "with", "from", "into", "the", "and", "load", "file", "files"}
#|
#|
#|def format_suggestions(items):
#|    return [f"seen {g['count']}x ({', '.join(g['keys'][:3])}{' …' if len(g['keys']) > 3 else ''}; {g['days'][0]}"
#|            + (f" .. {g['days'][-1]}" if len(g["days"]) > 1 else "") + f") and no learning covers it: {g['example'][:220]}"
#|            for g in items]
#@@ FILE nifikb/logs.py tc 1a2b1ff7ef795c5b
#|"""NiFi logs (nifi-app*.log, nifi-bootstrap*.log): an incremental, compact index of what went wrong.
#|
#|The logs are huge and always growing, so:
#|- files are read incrementally (byte offset per file; rotation / truncation detected by a head fingerprint);
#|  rolled files (nifi-app_2026-09-26_10.0.log, *.gz) are read once; a first run reads at most `initial_tail_mb` of each;
#|- only WARN / ERROR / FATAL lines are kept (plus lifecycle lines of the bootstrap log: starts, stops, restarts, crashes),
#|  with their exception / root cause taken from the stack trace that follows;
#|- each event is tied to the processor / service (runtime id -> flow component), the FlowFile uuid and file name, and a
#|  message template (variable parts removed) so thousands of identical errors collapse into one line with a count;
#|- events older than `keep_days` (relative to the newest one) are pruned; duplicates are ignored.
#|"""
#|import fnmatch
#|import gzip
#|import hashlib
#|import re
#|import time
#|from pathlib import Path
#|
#|from .db import BEARER_RE
#|from .util import REDACTED, redact_secrets
#|
#|UNQUOTED_SECRET_RE = re.compile(r"(?i)\b(pass(?:word|wd)?|pwd|secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*(?!<redacted>)[^\s,;&'\"]+")
#|EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
#|
#|
#|def scrub(text):
#|    """Secrets, bearer tokens and e-mail addresses out of a log message (error messages often quote data values)."""
#|    text = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(text))
#|    text = UNQUOTED_SECRET_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
#|    return EMAIL_RE.sub("<email>", text)
#|
#|LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) (TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+\[(.*?)\] (\S+) ?(.*)$")
#|COMP_RE = re.compile(r"\b([A-Z][\w$]*)\[id=([\w-]+)\]")
#|SERVICE_RE = re.compile(r"service=([A-Z][\w$]*)\[id=([\w-]+)\]")
#|FF_START = "StandardFlowFileRecord["
#|CAUSE_RE = re.compile(r"^(?:Caused by: )?((?:[a-z_$][\w$]*\.)+[A-Z][\w$]*(?:Exception|Error|Throwable|Failure)[\w$]*)(?::\s*(.*))?$")
#|LIFECYCLE_RE = re.compile(r"(?i)launched apache nifi|started apache nifi|apache nifi (?:is|has) (?:stopped|shut down|started)|"
#|                          r"nifi pid|stopping apache nifi|restart(?:ing)? apache nifi|nifi (?:has )?died|process .{0,40} died|"
#|                          r"terminated|outofmemory|hs_err|killing|not running|"
#|                          r"graceful shutdown|failed to start|shutdown hook")
#|UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
#|DEFAULT_PATTERNS = ("nifi-app*.log*", "nifi-bootstrap*.log*")
#|
#|
#|def settings(cfg):
#|    lg = dict(cfg.get("logs") or {})
#|    home = cfg["nifi"].get("home")
#|    dirs = lg.get("dirs") or ([str(Path(home) / "logs")] if home else [])
#|    return {"dirs": dirs, "patterns": lg.get("files") or list(DEFAULT_PATTERNS), "keep_days": float(lg.get("keep_days", 14)),
#|            "initial_tail_mb": float(lg.get("initial_tail_mb", 200)), "enabled": lg.get("enabled", True) and bool(dirs)}
#|
#|
#|def log_files(s):
#|    out = []
#|    for d in s["dirs"]:
#|        p = Path(d)
#|        if p.is_dir():
#|            out += [f for f in sorted(p.iterdir()) if f.is_file() and any(fnmatch.fnmatch(f.name, pat) for pat in s["patterns"])]
#|    return out
#|
#|
#|# ---------------------------------------------------------------------------------------------- parsing
#|def _flowfile(msg):
#|    """(uuid, file name, message with the FlowFile record replaced by <flowfile>) - the record nests brackets."""
#|    i = msg.find(FF_START)
#|    if i < 0:
#|        return None, None, msg
#|    depth, j = 0, i + len(FF_START) - 1
#|    while j < len(msg):
#|        if msg[j] == "[":
#|            depth += 1
#|        elif msg[j] == "]":
#|            depth -= 1
#|            if depth == 0:
#|                break
#|        j += 1
#|    rec = msg[i:j + 1]
#|    uuid = re.search(r"uuid=([0-9a-f-]{36})", rec)
#|    name = re.search(r",name=(.*?),size=", rec)
#|    fname = name.group(1) if name else None
#|    if fname and UUID_RE.fullmatch(fname):
#|        fname = None  # FlowFiles created inside NiFi are named after their uuid: not a file name
#|    return (uuid.group(1) if uuid else None, fname, msg[:i] + "<flowfile>" + msg[j + 1:])
#|
#|
#|def compact(msg):
#|    """Message with the FlowFile record shortened to FlowFile[uuid8, name]."""
#|    uuid, fname, stripped = _flowfile(msg)
#|    if not uuid:
#|        return msg
#|    return stripped.replace("<flowfile>", f"FlowFile[{uuid[:8]}" + (f", {fname}]" if fname else "]"))
#|
#|
#|def template(msg):
#|    """Stable shape of a message: ids, numbers, quoted values and paths replaced."""
#|    t = UUID_RE.sub("<id>", msg)
#|    t = re.sub(r"'[^']{0,200}'|\"[^\"]{0,200}\"", "<v>", t)
#|    t = re.sub(r"(?:[A-Za-z]:)?[\\/][^\s,;\]]+", "<path>", t)
#|    t = re.sub(r"\b\d+(?:[.,]\d+)*\b", "<n>", t)
#|    return re.sub(r"\s+", " ", t)[:300]
#|
#|
#|def parse_lines(lines, source, bootstrap=False):
#|    """Yield events from an iterable of (line_no, text)."""
#|    ev, cont = None, 0
#|    for no, line in lines:
#|        line = line.rstrip("\r\n")
#|        m = LINE_RE.match(line)
#|        if m:
#|            if ev:
#|                yield ev
#|            ev, cont = None, 0
#|            ts, ms, level, thread, logger, msg = m.groups()
#|            keep = level in ("WARN", "ERROR", "FATAL") or (bootstrap and LIFECYCLE_RE.search(msg))
#|            if not keep:
#|                continue
#|            uuid, fname, stripped = _flowfile(msg)
#|            comp = SERVICE_RE.search(msg) or COMP_RE.search(msg)
#|            ev = {"ts": f"{ts}.{ms}", "epoch": time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")) + int(ms) / 1000,
#|                  "level": level if not (bootstrap and level == "INFO") else "LIFECYCLE", "thread": thread[:80],
#|                  "logger": logger, "component_type": comp.group(1) if comp else None,
#|                  "component_id": comp.group(2) if comp else None, "flowfile_uuid": uuid, "filename": fname,
#|                  "message": scrub(msg)[:2000], "cause": None, "file": source, "line": no}
#|            ev["template"] = template(COMP_RE.sub(lambda x: x.group(1), stripped))
#|        elif ev and cont < 60:
#|            cont += 1
#|            c = CAUSE_RE.match(line.strip())
#|            if c and not line.lstrip().startswith("at "):
#|                ev["cause"] = scrub(f"{c.group(1).rsplit('.', 1)[-1]}: {c.group(2) or ''}".strip(": "))[:600]
#|    if ev:
#|        yield ev
#|
#|
#|def _head(path):
#|    opener = gzip.open if path.suffix == ".gz" else open
#|    try:
#|        with opener(path, "rb") as f:
#|            return hashlib.sha1(f.read(4096)).hexdigest()
#|    except OSError:
#|        return ""
#|
#|
#|def _read(path, start):
#|    """(line_no, text) from byte offset `start` (whole file for .gz); returns the iterator and a callable end offset."""
#|    if path.suffix == ".gz":
#|        f = gzip.open(path, "rt", encoding="utf-8", errors="replace")
#|    else:
#|        f = open(path, "rb")
#|        f.seek(start)
#|        if start:
#|            f.readline()  # we may have landed mid-line
#|    state = {"end": start}
#|
#|    def gen():
#|        with f:
#|            for i, raw in enumerate(f, 1):
#|                yield i, raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
#|            if not isinstance(f, gzip.GzipFile) and hasattr(f, "tell"):
#|                try:
#|                    state["end"] = f.tell()
#|                except (OSError, ValueError):
#|                    pass
#|    return gen(), state
#|
#|
#|# ---------------------------------------------------------------------------------------------- indexing
#|def index(cfg, store, log=print):
#|    """Bring the log index up to date. Returns (files read, events added)."""
#|    s = settings(cfg)
#|    if not s["enabled"]:
#|        return 0, 0
#|    files, added = 0, 0
#|    for path in log_files(s):
#|        st = path.stat()
#|        head = _head(path)
#|        row = store.db.execute("SELECT sig, offset, head FROM log_files WHERE path=?", (str(path),)).fetchone()
#|        rolled = path.suffix == ".gz" or re.search(r"_\d{4}-\d{2}-\d{2}", path.name)
#|        sig = f"{st.st_size}:{int(st.st_mtime)}"
#|        if row and (row["sig"] == sig or (rolled and row["head"] == head)):
#|            continue  # unchanged, or a rolled file already read
#|        if rolled and time.time() - st.st_mtime > s["keep_days"] * 86400 * 4 and not row:
#|            continue  # very old rolled file
#|        start = 0
#|        if row and not rolled and row["head"] == head and st.st_size >= row["offset"]:
#|            start = row["offset"]  # the same file grew: read only the new part
#|        elif not row and path.suffix != ".gz" and st.st_size > s["initial_tail_mb"] * 1e6:
#|            start = int(st.st_size - s["initial_tail_mb"] * 1e6)  # first run on a huge file: its tail only
#|        lines, state = _read(path, start)
#|        events = list(parse_lines(lines, path.name, bootstrap="bootstrap" in path.name))
#|        added += store.add_log_events(events)
#|        end = state["end"] if path.suffix != ".gz" else st.st_size
#|        store.db.execute("INSERT OR REPLACE INTO log_files(path, sig, offset, head) VALUES(?,?,?,?)", (str(path), sig, end or st.st_size, head))
#|        files += 1
#|    store.prune_log_events(s["keep_days"])
#|    store.db.commit()
#|    if files:
#|        log(f"  logs: {files} file(s) read, {added} new warning / error event(s)")
#|    return files, added
#|
#|
#|# ---------------------------------------------------------------------------------------------- queries
#|def query(store, component_ids=(), filename=None, uuid=None, grep=None, level=None, since_hours=None, limit=50):
#|    where, params = [], []
#|    if component_ids:
#|        where.append(f"component_id IN ({','.join('?' * len(component_ids))})")
#|        params += list(component_ids)
#|    if filename:
#|        where.append("(filename = ? OR message LIKE ?)")
#|        params += [filename, f"%{filename}%"]
#|    if uuid:
#|        where.append("flowfile_uuid = ?")
#|        params.append(uuid)
#|    if grep:
#|        where.append("(message LIKE ? OR cause LIKE ?)")
#|        params += [f"%{grep}%", f"%{grep}%"]
#|    if level:
#|        where.append("level = ?")
#|        params.append(level.upper())
#|    if since_hours:
#|        newest = store.db.execute("SELECT MAX(epoch) FROM log_events").fetchone()[0] or time.time()
#|        where.append("epoch >= ?")
#|        params.append(newest - float(since_hours) * 3600)  # relative to the newest event: works on copied / old logs too
#|    sql = ("SELECT template, level, component_type, component_id, COUNT(*) n, MIN(ts) first, MAX(ts) last, "
#|           "MAX(cause) cause, MAX(message) sample, GROUP_CONCAT(DISTINCT filename) files, MAX(flowfile_uuid) uuid "
#|           "FROM log_events" + (" WHERE " + " AND ".join(where) if where else "")
#|           + " GROUP BY template, level, component_id ORDER BY MAX(epoch) DESC LIMIT ?")
#|    return store.db.execute(sql, (*params, limit)).fetchall()
#|
#|
#|def format_rows(rows, names=None):
#|    names = names or {}
#|    if not rows:
#|        return "no matching warnings / errors in the indexed logs"
#|    L = []
#|    for r in rows:
#|        who = r["component_type"] or ""
#|        if r["component_id"]:
#|            flow = names.get(r["component_id"])
#|            who += f" `{r['component_id'][:8]}`" + (f" ({flow})" if flow else "")
#|        files = [f for f in (r["files"] or "").split(",") if f][:3]
#|        L.append(f"[{r['level']}] x{r['n']} {r['first'][:16]} .. {r['last'][:16]}  {who}".rstrip())
#|        L.append(f"    {compact(r['sample'])[:400]}")
#|        if r["cause"]:
#|            L.append(f"    cause: {r['cause']}")
#|        if files:
#|            L.append(f"    files: {', '.join(files)}")
#|    return "\n".join(L)
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
#@@ FILE nifikb/target.py t ccbca36fdb64cc20
#|"""Target-side check: did the load write anything to the definition's HDFS / S3 location, and does the Parquet it wrote
#|match the structure rows?
#|
#|Read-only everywhere: directory listings and the last bytes of one Parquet file (its footer holds the schema) - no data
#|rows are read. Backends, chosen by the location's scheme:
#|  s3://bucket/prefix        boto3 when installed, otherwise the `aws` CLI (its own credentials / profile / SSO)
#|  hdfs://…/path or /path    WebHDFS ([targets] hdfs_url; `kerberos = true` uses `curl --negotiate`) or the `hdfs` CLI
#|  a local / mounted folder  read directly
#|The Parquet schema is decoded here (Thrift compact protocol, stdlib only), so nothing needs to be installed."""
#|import datetime as dt
#|import json
#|import os
#|import re
#|import shutil
#|import ssl
#|import struct
#|import subprocess
#|import tempfile
#|import time
#|import urllib.error
#|import urllib.parse
#|import urllib.request
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|
#|PLACEHOLDER = re.compile(r"\$\{|#\{|\{[a-z_]+\}|(?<![A-Za-z])(?:YYYY|yyyy|MM|DD|dd|HH)(?![A-Za-z])")
#|FOOTER_READ = 64 * 1024
#|
#|
#|class TargetError(Exception):
#|    pass
#|
#|
#|def settings(cfg):
#|    t = dict(cfg.get("targets") or {})
#|    t.setdefault("max_entries", 2000)
#|    t.setdefault("max_depth", 4)
#|    t.setdefault("timeout", 30)
#|    t.setdefault("max_download_mb", 200)
#|    return t
#|
#|
#|# ------------------------------------------------------------------------------------------------ Parquet footer
#|class _Compact:
#|    """Minimal Thrift compact-protocol reader: structs become {field id: value}."""
#|
#|    def __init__(self, data):
#|        self.b, self.i = data, 0
#|
#|    def byte(self):
#|        v = self.b[self.i]
#|        self.i += 1
#|        return v
#|
#|    def varint(self):
#|        shift = out = 0
#|        while True:
#|            b = self.byte()
#|            out |= (b & 0x7F) << shift
#|            if not b & 0x80:
#|                return out
#|            shift += 7
#|
#|    def zigzag(self):
#|        n = self.varint()
#|        return (n >> 1) ^ -(n & 1)
#|
#|    def value(self, t):
#|        if t in (1, 2):
#|            return t == 1
#|        if t == 3:
#|            return self.byte()
#|        if t in (4, 5, 6):
#|            return self.zigzag()
#|        if t == 7:
#|            v = struct.unpack("<d", self.b[self.i:self.i + 8])[0]
#|            self.i += 8
#|            return v
#|        if t == 8:
#|            n = self.varint()
#|            v = self.b[self.i:self.i + n]
#|            self.i += n
#|            return v
#|        if t in (9, 10):
#|            h = self.byte()
#|            n, et = h >> 4, h & 0x0F
#|            if n == 15:
#|                n = self.varint()
#|            return [self.byte() == 1 if et in (1, 2) else self.value(et) for _ in range(n)]
#|        if t == 11:
#|            n = self.varint()
#|            if not n:
#|                return {}
#|            h = self.byte()
#|            return dict((self.value(h >> 4), self.value(h & 0x0F)) for _ in range(n))
#|        if t == 12:
#|            return self.struct()
#|        raise TargetError(f"unsupported Thrift type {t} in the Parquet footer")
#|
#|    def struct(self):
#|        out, last = {}, 0
#|        while True:
#|            h = self.byte()
#|            if h == 0:
#|                return out
#|            delta, t = h >> 4, h & 0x0F
#|            fid = last + delta if delta else self.zigzag()
#|            out[fid] = self.value(t)
#|            last = fid
#|
#|
#|PHYSICAL = {0: "BOOLEAN", 1: "INT", 2: "BIGINT", 3: "TIMESTAMP", 4: "FLOAT", 5: "DOUBLE", 6: "BINARY", 7: "FIXED_BINARY"}
#|CONVERTED = {0: "STRING", 4: "STRING", 6: "DATE", 7: "TIME", 8: "TIME", 9: "TIMESTAMP", 10: "TIMESTAMP", 15: "TINYINT", 16: "SMALLINT",
#|             17: "TINYINT", 18: "SMALLINT", 19: "INT", 20: "BIGINT", 21: "JSON", 22: "BINARY"}
#|LOGICAL = {1: "STRING", 4: "STRING", 6: "DATE", 7: "TIME", 8: "TIMESTAMP", 12: "JSON", 14: "UUID"}
#|
#|
#|def parquet_schema(footer_bytes):
#|    """[{name, type, nullable}] of the leaf columns (nested ones as a.b.c) + {rows, created_by}, from the file tail."""
#|    if len(footer_bytes) < 12 or footer_bytes[-4:] != b"PAR1":
#|        raise TargetError("not a Parquet file (no PAR1 magic at the end)")
#|    n = struct.unpack("<i", footer_bytes[-8:-4])[0]
#|    if n + 8 > len(footer_bytes):
#|        raise TargetError(f"footer needs {n + 8} bytes")
#|    meta = _Compact(footer_bytes[-8 - n:-8]).struct()
#|    elems = meta.get(2) or []
#|    cols, pos = [], 1
#|
#|    def walk(prefix, count):
#|        nonlocal pos
#|        for _ in range(count):
#|            e = elems[pos]
#|            pos += 1
#|            name = e.get(4, b"").decode("utf-8", "replace")
#|            full = f"{prefix}.{name}" if prefix else name
#|            if e.get(5):
#|                walk(full, e[5])
#|                continue
#|            typ = PHYSICAL.get(e.get(1), "?")
#|            logical = e.get(10) or {}
#|            if 5 in logical or e.get(6) == 5:
#|                typ = f"DECIMAL({e.get(8, '?')},{e.get(7, 0)})"
#|            elif 10 in logical:
#|                info = logical[10]
#|                bits, signed = info.get(1, 32), info.get(2, True)
#|                typ = {8: "TINYINT", 16: "SMALLINT", 32: "INT", 64: "BIGINT"}.get(bits, "INT") + ("" if signed else " UNSIGNED")
#|            elif logical:
#|                typ = next((LOGICAL[k] for k in logical if k in LOGICAL), typ)
#|            elif e.get(6) in CONVERTED:
#|                typ = CONVERTED[e[6]]
#|            cols.append({"name": full, "type": typ, "nullable": e.get(3, 1) != 0})
#|
#|    if elems:
#|        walk("", elems[0].get(5, 0))
#|    created = meta.get(6)
#|    return cols, {"rows": meta.get(3), "created_by": created.decode("utf-8", "replace") if isinstance(created, bytes) else None}
#|
#|
#|# ------------------------------------------------------------------------------------------------ backends
#|def _run(argv, timeout):
#|    try:
#|        p = subprocess.run(argv, capture_output=True, timeout=timeout)
#|    except FileNotFoundError:
#|        raise TargetError(f"'{argv[0]}' not found - install it or set its path in [targets]")
#|    except subprocess.TimeoutExpired:
#|        raise TargetError(f"{' '.join(argv[:3])} … timed out after {timeout}s")
#|    if p.returncode:
#|        raise TargetError(f"{' '.join(argv[:3])} … failed: {p.stderr.decode('utf-8', 'replace').strip()[:300]}")
#|    return p.stdout
#|
#|
#|class Local:
#|    name = "local"
#|
#|    def __init__(self, t):
#|        self.t = t
#|
#|    def list(self, path):
#|        root, out = Path(path), []
#|        if not root.exists():
#|            raise TargetError(f"{path} does not exist")
#|        base_depth = len(root.parts)
#|        for dirpath, dirs, files in os.walk(root):
#|            if len(Path(dirpath).parts) - base_depth >= self.t["max_depth"]:
#|                dirs[:] = []
#|            for f in files:
#|                p = Path(dirpath) / f
#|                st = p.stat()
#|                out.append({"path": p.as_posix(), "size": st.st_size, "mtime": st.st_mtime})
#|                if len(out) >= self.t["max_entries"]:
#|                    return out
#|        return out
#|
#|    def tail(self, path, size, n):
#|        with open(path, "rb") as f:
#|            f.seek(max(0, size - n))
#|            return f.read()
#|
#|
#|class WebHdfs:
#|    name = "webhdfs"
#|
#|    def __init__(self, t):
#|        self.t = t
#|        self.url = t["hdfs_url"].rstrip("/")
#|        self.ctx = ssl.create_default_context(cafile=t.get("ca_cert") or None) if self.url.startswith("https") else None
#|
#|    def _get(self, path, **params):
#|        if self.t.get("hdfs_user") and not self.t.get("kerberos"):
#|            params["user.name"] = self.t["hdfs_user"]
#|        url = f"{self.url}{urllib.parse.quote(path)}?{urllib.parse.urlencode(params)}"
#|        if self.t.get("kerberos"):  # SPNEGO: curl does the Kerberos handshake with the ticket from kinit
#|            return _run([self.t.get("curl", "curl"), "-sfL", "--negotiate", "-u", ":", *(["--cacert", self.t["ca_cert"]] if self.t.get("ca_cert") else []),
#|                         url], self.t["timeout"])
#|        try:
#|            with urllib.request.urlopen(url, timeout=self.t["timeout"], context=self.ctx) as r:
#|                return r.read()
#|        except urllib.error.HTTPError as e:
#|            raise TargetError(f"WebHDFS {params.get('op')} {path}: HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}")
#|        except (urllib.error.URLError, OSError) as e:
#|            raise TargetError(f"WebHDFS not reachable at {self.url}: {e}")
#|
#|    def list(self, path):
#|        out, todo = [], [(path.rstrip("/") or "/", 0)]
#|        while todo and len(out) < self.t["max_entries"]:
#|            p, depth = todo.pop(0)
#|            try:
#|                data = json.loads(self._get(p, op="LISTSTATUS"))
#|            except TargetError as e:
#|                if "404" in str(e) or "FileNotFound" in str(e):
#|                    raise TargetError(f"{p} does not exist in HDFS")
#|                raise
#|            for s in data["FileStatuses"]["FileStatus"]:
#|                full = f"{p.rstrip('/')}/{s['pathSuffix']}" if s["pathSuffix"] else p
#|                if s["type"] == "DIRECTORY":
#|                    if depth + 1 < self.t["max_depth"]:
#|                        todo.append((full, depth + 1))
#|                else:
#|                    out.append({"path": full, "size": s["length"], "mtime": s["modificationTime"] / 1000})
#|        return out[:self.t["max_entries"]]
#|
#|    def tail(self, path, size, n):
#|        off = max(0, size - n)
#|        return self._get(path, op="OPEN", offset=off, length=size - off)
#|
#|
#|class HdfsCli:
#|    name = "hdfs cli"
#|    LINE = re.compile(r"^([-d])\S*\s+\S+\s+\S+\s+\S+\s+(\d+)\s+(\d{4}-\d\d-\d\d \d\d:\d\d)\s+(.+)$")
#|
#|    def __init__(self, t):
#|        self.t = t
#|        self.cmd = t.get("hdfs_cli") if isinstance(t.get("hdfs_cli"), list) else [t.get("hdfs_cli") or "hdfs"]
#|
#|    def list(self, path):
#|        out = []
#|        text = _run([*self.cmd, "dfs", "-ls", "-R", path], self.t["timeout"] * 4).decode("utf-8", "replace")
#|        for line in text.splitlines():
#|            m = self.LINE.match(line.strip())
#|            if m and m.group(1) == "-":
#|                out.append({"path": m.group(4), "size": int(m.group(2)),
#|                            "mtime": time.mktime(time.strptime(m.group(3), "%Y-%m-%d %H:%M"))})
#|                if len(out) >= self.t["max_entries"]:
#|                    break
#|        return out
#|
#|    def tail(self, path, size, n):
#|        if size > self.t["max_download_mb"] * 1024 * 1024:
#|            raise TargetError(f"{path} is {size // 1048576} MB - the hdfs CLI cannot read only the footer; use WebHDFS "
#|                              "([targets] hdfs_url) or raise max_download_mb")
#|        with tempfile.TemporaryDirectory() as tmp:
#|            local = Path(tmp) / "f.parquet"
#|            _run([*self.cmd, "dfs", "-get", path, str(local)], self.t["timeout"] * 4)
#|            return Local(self.t).tail(local, local.stat().st_size, n)
#|
#|
#|class S3:
#|    name = "s3"
#|
#|    def __init__(self, t):
#|        self.t = t
#|        self.client = None
#|        try:
#|            if t.get("s3_cli"):
#|                raise ImportError  # an explicitly configured CLI wins over boto3
#|            import boto3  # optional
#|            session = boto3.session.Session(profile_name=t.get("s3_profile")) if t.get("s3_profile") else boto3.session.Session()
#|            self.client = session.client("s3", endpoint_url=t.get("s3_endpoint") or None, region_name=t.get("s3_region") or None)
#|        except ImportError:
#|            self.client = None
#|        self.cli = t.get("s3_cli") if isinstance(t.get("s3_cli"), list) else [t.get("s3_cli") or "aws"]
#|
#|    def _opts(self):
#|        return [*(["--profile", self.t["s3_profile"]] if self.t.get("s3_profile") else []),
#|                *(["--endpoint-url", self.t["s3_endpoint"]] if self.t.get("s3_endpoint") else []),
#|                *(["--region", self.t["s3_region"]] if self.t.get("s3_region") else [])]
#|
#|    @staticmethod
#|    def split(path):
#|        u = urllib.parse.urlparse(path)
#|        return u.netloc, u.path.lstrip("/")
#|
#|    def list(self, path):
#|        bucket, prefix = self.split(path)
#|        out = []
#|        if self.client:
#|            pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix,
#|                                                                         PaginationConfig={"MaxItems": self.t["max_entries"]})
#|            for page in pages:
#|                for o in page.get("Contents") or []:
#|                    out.append({"path": f"s3://{bucket}/{o['Key']}", "size": o["Size"], "mtime": o["LastModified"].timestamp()})
#|            return out
#|        data = _run([*self.cli, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix, "--max-items",
#|                     str(self.t["max_entries"]), "--output", "json", *self._opts()], self.t["timeout"] * 4)
#|        for o in (json.loads(data or b"{}") or {}).get("Contents") or []:
#|            when = dt.datetime.fromisoformat(str(o["LastModified"]).replace("Z", "+00:00")).timestamp()
#|            out.append({"path": f"s3://{bucket}/{o['Key']}", "size": o["Size"], "mtime": when})
#|        return out
#|
#|    def tail(self, path, size, n):
#|        bucket, key = self.split(path)
#|        rng = f"bytes={max(0, size - n)}-{size - 1}"
#|        if self.client:
#|            return self.client.get_object(Bucket=bucket, Key=key, Range=rng)["Body"].read()
#|        with tempfile.TemporaryDirectory() as tmp:
#|            local = Path(tmp) / "tail.bin"
#|            _run([*self.cli, "s3api", "get-object", "--bucket", bucket, "--key", key, "--range", rng, str(local), *self._opts()],
#|                 self.t["timeout"] * 4)
#|            return local.read_bytes()
#|
#|
#|def backend(t, location):
#|    loc = str(location)
#|    if re.match(r"(?i)s3a?://", loc):
#|        return S3(t), re.sub(r"(?i)^s3a://", "s3://", loc)
#|    if re.match(r"(?i)hdfs://", loc) or (loc.startswith("/") and (t.get("hdfs_url") or t.get("hdfs_cli")) and not Path(loc).exists()):
#|        path = urllib.parse.urlparse(loc).path if loc.lower().startswith("hdfs://") else loc
#|        if t.get("hdfs_url"):
#|            return WebHdfs(t), path
#|        if t.get("hdfs_cli") or shutil.which("hdfs"):
#|            return HdfsCli(t), path
#|        raise TargetError("HDFS location, but neither [targets] hdfs_url (WebHDFS) nor an hdfs CLI is available")
#|    if re.match(r"(?i)file://", loc):
#|        return Local(t), urllib.parse.urlparse(loc).path
#|    if re.match(r"(?i)[a-z][a-z0-9+.-]+://", loc):
#|        raise TargetError(f"unsupported location scheme in {loc}")
#|    return Local(t), loc
#|
#|
#|# ------------------------------------------------------------------------------------------------ check
#|def listable_root(location):
#|    """The fixed part of a location with placeholders (…/dt=${now()…}/ → …/): list from there."""
#|    loc = str(location).strip()
#|    m = PLACEHOLDER.search(loc)
#|    if not m:
#|        return loc, False
#|    return loc[:loc.rfind("/", 0, m.start()) + 1] or loc[:m.start()], True
#|
#|
#|def _stem(name):
#|    s = Path(str(name).replace("\\", "/")).name
#|    return re.sub(r"(\.(csv|txt|dat|json|xml|gz|zip|parquet|psv|tsv))+$", "", s, flags=re.I).lower()
#|
#|
#|def check(cfg, location, fields=(), file=None, since=None):
#|    """{location, root, backend, files (newest first), matches, schema, issues: [(severity, kind, message)]}."""
#|    t = settings(cfg)
#|    root, templated = listable_root(location)
#|    res = {"location": location, "root": root, "files": [], "matches": [], "schema": None, "issues": []}
#|    be, path = backend(t, root)
#|    res["backend"] = be.name
#|    try:
#|        files = be.list(path)
#|    except TargetError as e:
#|        res["issues"].append(("error", "target-location", f"cannot list {root}: {e}"))
#|        return res
#|    files.sort(key=lambda f: -f["mtime"])
#|    data = [f for f in files if not re.search(r"(^|/)(_SUCCESS|_committed_|_started_|\.crc$|\._)", f["path"]) and not Path(f["path"]).name.startswith(".")]
#|    res["files"] = data
#|    if not data:
#|        res["issues"].append(("error", "target-empty", f"no data files under {root}" + (" (location has placeholders; listed its fixed part)" if templated else "")))
#|        return res
#|    empty = [f for f in data[:50] if f["size"] == 0]
#|    if empty:
#|        res["issues"].append(("warn", "target-zero-byte", f"{len(empty)} zero-byte file(s) among the newest, e.g. {empty[0]['path']}"))
#|    if file:
#|        stem = _stem(file)
#|        res["matches"] = [f for f in data if stem and stem in Path(f["path"]).name.lower()] + \
#|                         [f for f in data if stem and stem in f["path"].lower() and stem not in Path(f["path"]).name.lower()]
#|        if not res["matches"]:
#|            newest = time.strftime("%Y-%m-%d %H:%M", time.localtime(data[0]["mtime"]))
#|            res["issues"].append(("warn", "target-no-file-output", f"no output named like '{stem}' under {root} (outputs are often "
#|                                                                   f"named by the flow, not the input file; newest output {newest})"))
#|    if since:
#|        recent = [f for f in data if f["mtime"] >= since]
#|        if not recent:
#|            res["issues"].append(("warn", "target-stale", f"nothing written under {root} since {time.strftime('%Y-%m-%d %H:%M', time.localtime(since))}"))
#|    pq = next((f for f in (res["matches"] or data) if f["path"].lower().endswith(".parquet") or ".parquet" in f["path"].lower()), None)
#|    if pq is None:
#|        pq = next((f for f in (res["matches"] or data) if f["size"] > 12 and not re.search(r"\.(csv|json|txt|avro|orc|gz)$", f["path"], re.I)), None)
#|    if pq and fields:
#|        try:
#|            tail = be.tail(pq["path"], pq["size"], FOOTER_READ)
#|            if len(tail) >= 8 and tail[-4:] == b"PAR1":
#|                n = struct.unpack("<i", tail[-8:-4])[0]
#|                if n + 8 > len(tail):
#|                    tail = be.tail(pq["path"], pq["size"], n + 8)
#|                cols, info = parquet_schema(tail)
#|                res["schema"] = {"file": pq["path"], "columns": cols, **info}
#|                res["issues"] += compare_schema(fields, cols, pq["path"])
#|        except (TargetError, OSError, IndexError, struct.error) as e:
#|            res["issues"].append(("info", "target-schema", f"could not read the Parquet schema of {pq['path']}: {e}"))
#|    return res
#|
#|
#|def compare_schema(fields, cols, where):
#|    """Structure rows vs the columns of a written Parquet file."""
#|    issues = []
#|    have = {c["name"].lower(): c for c in cols}
#|    leaf = {c["name"].lower().split(".")[-1]: c for c in cols}
#|    names = {f["name"].lower() for f in fields}
#|    missing = [f["name"] for f in fields if f["name"].lower() not in have and f["name"].lower().split(".")[-1] not in leaf]
#|    if missing:
#|        issues.append(("error", "parquet-missing-column", f"structure field(s) not in the written Parquet ({Path(where).name}): "
#|                                                          + ", ".join(missing[:15]) + (f", … +{len(missing) - 15}" if len(missing) > 15 else "")))
#|    extra = [c["name"] for c in cols if c["name"].lower() not in names and c["name"].lower().split(".")[-1] not in names]
#|    if extra:
#|        issues.append(("info", "parquet-extra-column", f"Parquet has column(s) not in the structure (often load metadata): {', '.join(extra[:15])}"))
#|    diffs = []
#|    for f in fields:
#|        c = have.get(f["name"].lower()) or leaf.get(f["name"].lower().split(".")[-1])
#|        if not c or not f.get("type"):
#|            continue
#|        a, b = metamod.type_family(f["type"]), metamod.type_family(c["type"])
#|        if a and b and a != b:
#|            diffs.append(f"'{f['name']}' is {f['type']} in the structure but {c['type']} in the Parquet")
#|    if diffs:
#|        issues.append(("warn", "parquet-type", "; ".join(diffs[:8]) + (f"; … +{len(diffs) - 8} more" if len(diffs) > 8 else "")))
#|    return issues
#|
#|
#|def format_check(res, limit=10):
#|    L = [f"location: {res['location']}" + (f" (listed {res['root']})" if res["root"] != res["location"] else "")
#|         + (f" via {res.get('backend')}" if res.get("backend") else "")]
#|    for sev, kind, msg in res["issues"]:
#|        L.append(f"  [{sev}] {kind}: {msg}")
#|    files = res["matches"] or res["files"]
#|    if files:
#|        L.append(f"  {'outputs for this file' if res['matches'] else 'newest outputs'} ({len(res['matches'] or res['files'])} found):")
#|        for f in files[:limit]:
#|            L.append(f"    {time.strftime('%Y-%m-%d %H:%M', time.localtime(f['mtime']))}  {f['size']:>12,}  {f['path']}")
#|    if res.get("schema"):
#|        s = res["schema"]
#|        L.append(f"  Parquet schema of {Path(s['file']).name}: {s.get('rows')} rows, "
#|                 + ", ".join(f"{c['name']} {c['type']}" for c in s["columns"][:30]) + (" …" if len(s["columns"]) > 30 else ""))
#|    return "\n".join(L)
#|
#|
#|# ------------------------------------------------------------------------------------------------ per definition
#|def enabled(cfg):
#|    return "targets" in cfg  # an empty [targets] section enables local / mounted locations
#|
#|
#|def location_of(cfg, model, entry):
#|    """Where a definition's data lands: its location column, a file-location target, or [targets] location_template."""
#|    if entry.get("location"):
#|        return str(entry["location"])
#|    tmpl = settings(cfg).get("location_template")
#|    table = entry.get("target")
#|    if tmpl and table:
#|        return tmpl.format(table=str(table), table_lower=str(table).lower(), id=entry.get("id"), label=entry.get("label"))
#|    return None
#|
#|
#|def check_diagnosis(cfg, model, diag, file=None, since=None):
#|    """[(definition entry, check result)] for the definitions of a metadata diagnosis that have a location."""
#|    out = []
#|    for d in (diag or {}).get("definitions") or []:
#|        loc = location_of(cfg, model, d)
#|        if not loc:
#|            continue
#|        try:
#|            out.append((d, check(cfg, loc, d.get("fields") or [], file=file, since=since)))
#|        except TargetError as e:
#|            out.append((d, {"location": loc, "root": loc, "files": [], "matches": [], "schema": None,
#|                            "issues": [("error", "target-location", str(e))]}))
#|    return out
#@@ FILE nifikb/tickets.py t 9805b818cbfa0a6b
#|"""Ticket systems (Jira, ServiceNow): read a ticket, pull the facts investigate needs out of it (file names, feed / table
#|names known to the config tables, error text, header lines, attached samples), run the investigation and draft a reply.
#|
#|Reading is all it does by default. A comment is posted only by a person running `ticket <id> --post` (never by an agent
#|through MCP), after secrets and e-mail addresses are scrubbed; ServiceNow gets a work note (internal), not a customer
#|comment, unless [tickets] note_field says otherwise."""
#|import base64
#|import json
#|import os
#|import re
#|import ssl
#|import tempfile
#|import urllib.error
#|import urllib.parse
#|import urllib.request
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|from .logs import scrub
#|
#|FILE_RE = re.compile(r"(?<![\w/\\.-])([\w][\w.\-]*\.(?:csv|txt|dat|json|jsonl|xml|gz|zip|parquet|psv|tsv|xlsx?|avro|orc))\b", re.I)
#|ERROR_RE = re.compile(r"(?i)\b(error|exception|failed|failure|failing|cannot|can't|unable|invalid|mismatch|not found|refused|timed? ?out|"
#|                      r"violat|duplicate|truncat|denied|rejected)\b")
#|HEADER_HINT = re.compile(r"(?i)^\s*(headers?|columns?|fields?|keys?)\s*(?:are|sent|used|:|=|-)+\s*(.+)$")
#|SAMPLE_EXT = re.compile(r"(?i)\.(csv|txt|dat|json|jsonl|psv|tsv)$")
#|MAX_ATTACHMENT = 5 * 1024 * 1024
#|
#|
#|class TicketError(Exception):
#|    pass
#|
#|
#|def settings(cfg):
#|    t = cfg.get("tickets") or {}
#|    if not t.get("url") or not t.get("kind"):
#|        return None
#|    if t["kind"] not in ("jira", "servicenow"):
#|        raise TicketError("[tickets] kind must be 'jira' or 'servicenow'")
#|    return t
#|
#|
#|def _secret(t, key):
#|    if t.get(f"{key}_env") and os.environ.get(t[f"{key}_env"]):
#|        return os.environ[t[f"{key}_env"]]
#|    if t.get(f"{key}_file"):
#|        return Path(t[f"{key}_file"]).read_text(encoding="utf-8").strip()
#|    return None
#|
#|
#|class _Http:
#|    def __init__(self, t):
#|        self.t = t
#|        self.base = t["url"].rstrip("/")
#|        self.timeout = float(t.get("timeout", 30))
#|        self.ctx = ssl.create_default_context(cafile=t.get("ca_cert") or None) if self.base.startswith("https") else None
#|        token, password = _secret(t, "token"), _secret(t, "password")
#|        if t.get("username") and (password or token):
#|            raw = f"{t['username']}:{password or token}".encode()
#|            self.auth = "Basic " + base64.b64encode(raw).decode()  # Jira Cloud (e-mail + API token), ServiceNow basic
#|        elif token:
#|            self.auth = f"Bearer {token}"  # Jira Server / DC personal access token, ServiceNow OAuth token
#|        else:
#|            self.auth = None
#|
#|    def call(self, method, path, body=None, raw=False):
#|        headers = {"Accept": "application/json"}
#|        if self.auth:
#|            headers["Authorization"] = self.auth
#|        data = None
#|        if body is not None:
#|            data = json.dumps(body).encode()
#|            headers["Content-Type"] = "application/json"
#|        url = path if path.startswith("http") else self.base + path
#|        if not url.startswith(self.base):
#|            raise TicketError(f"refusing to follow a link outside {self.base}")  # attachment URLs must stay on the ticket host
#|        req = urllib.request.Request(url, data=data, method=method, headers=headers)
#|        try:
#|            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
#|                if raw:
#|                    return r.read(MAX_ATTACHMENT + 1)
#|                text = r.read().decode("utf-8", "replace")
#|        except urllib.error.HTTPError as e:
#|            hint = {401: "authentication failed - check [tickets] username / token_env / password_env",
#|                    403: "the ticket user lacks permission", 404: "ticket not found"}.get(e.code, "")
#|            raise TicketError(f"HTTP {e.code} on {method} {path.split('?')[0]}: {hint}".strip()) from e
#|        except (urllib.error.URLError, OSError) as e:
#|            raise TicketError(f"cannot reach {self.base}: {e}") from e
#|        return json.loads(text) if text.strip() else None
#|
#|
#|def _adf_text(node):
#|    """Jira Cloud v3 'Atlassian document format' -> plain text (v2 returns plain strings already)."""
#|    if isinstance(node, str):
#|        return node
#|    if isinstance(node, dict):
#|        if node.get("type") == "text":
#|            return node.get("text", "")
#|        sep = "\n" if node.get("type") in ("paragraph", "heading", "codeBlock", "listItem", "doc") else ""
#|        return sep.join(_adf_text(c) for c in node.get("content") or [])
#|    if isinstance(node, list):
#|        return "\n".join(_adf_text(c) for c in node)
#|    return ""
#|
#|
#|class Jira:
#|    def __init__(self, t):
#|        self.http, self.t = _Http(t), t
#|
#|    def fetch(self, key):
#|        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", key):
#|            raise TicketError(f"'{key}' does not look like a Jira key (PROJ-123)")
#|        d = self.http.call("GET", f"/rest/api/2/issue/{key}?fields=summary,description,comment,created,status,attachment")
#|        f = d.get("fields") or {}
#|        comments = [_adf_text(c.get("body")) for c in ((f.get("comment") or {}).get("comments") or [])]
#|        atts = [{"name": a.get("filename"), "size": a.get("size") or 0, "url": a.get("content")} for a in f.get("attachment") or []]
#|        return {"id": d.get("key", key), "title": f.get("summary") or "", "description": _adf_text(f.get("description")) or "",
#|                "comments": comments, "created": f.get("created"), "status": ((f.get("status") or {}).get("name")),
#|                "attachments": atts, "ref": d.get("key", key)}
#|
#|    def download(self, att):
#|        return self.http.call("GET", att["url"], raw=True)
#|
#|    def post(self, ticket, text):
#|        self.http.call("POST", f"/rest/api/2/issue/{ticket['ref']}/comment", {"body": text})
#|
#|
#|class ServiceNow:
#|    def __init__(self, t):
#|        self.http, self.t = _Http(t), t
#|        self.table = t.get("table", "incident")
#|
#|    def fetch(self, number):
#|        if not re.fullmatch(r"[A-Za-z]{2,8}\d+", number):
#|            raise TicketError(f"'{number}' does not look like a ServiceNow number (INC0012345)")
#|        q = urllib.parse.urlencode({"sysparm_query": f"number={number}", "sysparm_limit": 1, "sysparm_display_value": "true",
#|                                    "sysparm_fields": "sys_id,number,short_description,description,comments,work_notes,sys_created_on,state"})
#|        rows = (self.http.call("GET", f"/api/now/table/{self.table}?{q}") or {}).get("result") or []
#|        if not rows:
#|            raise TicketError(f"{number} not found in {self.table}")
#|        r = rows[0]
#|        q = urllib.parse.urlencode({"sysparm_query": f"table_sys_id={r['sys_id']}", "sysparm_limit": 20})
#|        atts = [{"name": a.get("file_name"), "size": int(a.get("size_bytes") or 0), "url": f"/api/now/attachment/{a['sys_id']}/file"}
#|                for a in (self.http.call("GET", f"/api/now/attachment?{q}") or {}).get("result") or []]
#|        comments = [c for c in (r.get("comments"), r.get("work_notes")) if c]
#|        return {"id": r.get("number", number), "title": r.get("short_description") or "", "description": r.get("description") or "",
#|                "comments": comments, "created": r.get("sys_created_on"), "status": r.get("state"), "attachments": atts,
#|                "ref": r["sys_id"]}
#|
#|    def download(self, att):
#|        return self.http.call("GET", att["url"], raw=True)
#|
#|    def post(self, ticket, text):
#|        self.http.call("PATCH", f"/api/now/table/{self.table}/{ticket['ref']}", {self.t.get("note_field", "work_notes"): text})
#|
#|
#|def client(t):
#|    return Jira(t) if t["kind"] == "jira" else ServiceNow(t)
#|
#|
#|# ------------------------------------------------------------------------------------------------ facts
#|def _known_names(store, model):
#|    """Normalised identifying values of the config rows (file patterns, feeds, APIs, tables) -> original value."""
#|    known = {}
#|    if not model:
#|        return known
#|    rows = store.get_meta_rows(exclude=model.get("structure_table"))
#|    for table, rs in rows.items():
#|        info = model["tables"].get(table) or {}
#|        cols = [c for c in info.get("columns") or [] if metamod.KEY_COL.search(c) or metamod.TARGET_COL.search(c)
#|                or c in (model.get("definition_keys") or [])]
#|        for r in rs:
#|            for c in cols:
#|                v = r.get(c)
#|                if isinstance(v, str) and 3 <= len(v) <= 120 and v != "***" and not re.search(r"\s", v):
#|                    known.setdefault(metamod.norm(v), v)
#|    return known
#|
#|
#|def extract(ticket, store=None, model=None):
#|    """{files, feeds, tables, error, headers} from the ticket text (title, description, comments)."""
#|    text = "\n".join([ticket.get("title") or "", ticket.get("description") or ""] + list(ticket.get("comments") or []))
#|    files = []
#|    for m in FILE_RE.finditer(text):
#|        if m.group(1) not in files:
#|            files.append(m.group(1))
#|    known = _known_names(store, model) if store is not None else {}
#|    feeds, tables = [], []
#|    for tok in re.findall(r"[A-Za-z][\w.\-]{2,}", text):
#|        v = known.get(metamod.norm(tok))
#|        if v and v not in feeds and v not in tables and tok not in files:
#|            (tables if metamod.norm(v).startswith(("stg_", "tgt_", "dim_", "fact_", "raw_")) else feeds).append(v)
#|    headers, candidates = [], []
#|    title = (ticket.get("title") or "").strip()
#|    for n, line in enumerate(text.splitlines()):
#|        s = line.strip()
#|        h = HEADER_HINT.match(s)
#|        if h and not headers:
#|            parts = [p.strip().strip("'\"`") for p in re.split(r"[,|;\t]", h.group(2)) if p.strip()]
#|            if len(parts) >= 2:
#|                headers = parts
#|                continue
#|        if (ERROR_RE.search(s) or re.search(r"\w(Exception|Error)\b", s)) and 10 <= len(s) <= 500 and not h:
#|            # the most specific line wins: an exception class or "Error: ..." beats a summary like "load failed"
#|            score = 3 * bool(re.search(r"\w(Exception|Error)\b", s)) + (":" in s) - (s == title)
#|            candidates.append((-score, n, re.sub(r"(?i)^error\s*:\s*", "", s)))
#|    error = min(candidates)[2] if candidates else None
#|    if not headers:  # a pasted header line: 3+ identifier-like tokens split by one delimiter
#|        for line in text.splitlines():
#|            s = line.strip()
#|            for d in (",", "|", ";", "\t"):
#|                parts = [p.strip() for p in s.split(d)]
#|                if len(parts) >= 3 and all(re.fullmatch(r"[A-Za-z_][\w .\-]{0,60}", p) for p in parts) and s.count(" ") < len(parts) * 2:
#|                    headers = parts
#|                    break
#|            if headers:
#|                break
#|    error_words = error
#|    if error and len(error) > 200:
#|        error_words = error[:200]
#|    return {"files": files[:5], "feeds": feeds[:5], "tables": tables[:5], "error": error_words, "headers": headers}
#|
#|
#|def fetch_samples(cl, ticket, max_files=2):
#|    """Download small CSV / JSON attachments to a temp folder (the caller removes it). Returns (dir, [paths])."""
#|    wanted = [a for a in ticket.get("attachments") or [] if a.get("name") and SAMPLE_EXT.search(a["name"])
#|              and 0 < (a.get("size") or 1) <= MAX_ATTACHMENT][:max_files]
#|    if not wanted:
#|        return None, []
#|    tmp = tempfile.mkdtemp(prefix="nifikb-ticket-")
#|    paths = []
#|    for a in wanted:
#|        try:
#|            data = cl.download(a)
#|        except TicketError:
#|            continue
#|        if data is None or len(data) > MAX_ATTACHMENT:
#|            continue
#|        p = Path(tmp) / re.sub(r"[^\w.\-]", "_", a["name"])
#|        p.write_bytes(data)
#|        paths.append(str(p))
#|    return tmp, paths
#|
#|
#|def draft_comment(ticket, facts, report, kb_built=None):
#|    """A short reply for the ticket: likely causes, proposed fixes, what was checked. Scrubbed of secrets / e-mails."""
#|    L = [f"Automated first analysis (nifikb) for {ticket['id']} - please verify before acting."]
#|    looked = [f"file {', '.join(facts['files'])}" if facts["files"] else None, f"feed {', '.join(facts['feeds'])}" if facts["feeds"] else None,
#|              f"table {', '.join(facts['tables'])}" if facts["tables"] else None, "the error text" if facts["error"] else None,
#|              f"{len(facts['headers'])} headers" if facts["headers"] else None]
#|    L.append("Checked: " + ", ".join(x for x in looked if x) + (f" (knowledge base built {kb_built})" if kb_built else ""))
#|    L.append("")
#|    if report["causes"]:
#|        L.append("Most likely causes:")
#|        L += [f"{n}. {c}" for n, c in enumerate(report["causes"][:5], 1)]
#|    else:
#|        L.append("No conclusive cause found yet - the support team will look further.")
#|    fixes = next((text for title, text in report["sections"] if title.startswith("Proposed fixes")), None)
#|    if fixes:
#|        L += ["", "Proposed config fix (to be reviewed and run by the platform team):", fixes]
#|    if report.get("next_checks"):
#|        L += ["", "Still open: " + "; ".join(report["next_checks"][:3])]
#|    return scrub("\n".join(L))
#@@ FILE nifikb/util.py t 45126c6fba2974e8
#|"""Small shared helpers: ids, slugs, redaction, and the regexes used to spot hardcoded values."""
#|import hashlib
#|import os
#|import re
#|from pathlib import Path
#|
#|REDACTED = "<redacted>"
#|
#|SECRET_NAME = re.compile(r"(?i)(pass(word|wd)?|pwd|secret|api[_\- ]?key|access[_\- ]?key|private[_\- ]?key|token|credential)")
#|URL_RE = re.compile(r"\b(?:https?|ftps?|sftp|s3a?|s3n|hdfs|wss?|gs|abfss?|wasbs?)://[^\s\"'<>`)]+", re.I)
#|JDBC_RE = re.compile(r"\bjdbc:[a-z0-9]+:[^\s\"'<>`]+", re.I)
#|IP_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
#|HOST_RE = re.compile(r"(?<![\w.@/-])(?:[a-z0-9-]+\.)+(?:com|net|org|io|local|internal|corp|lan|intra|cloud|in|co|aws)(?![\w.-])", re.I)
#|WIN_PATH_RE = re.compile(r"(?:(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|\\\\[\w.-]+\\)[^\"'<>|*?\r\n]*")
#|UNIX_PATH_RE = re.compile(r"(?<![\w.:/$}])/(?:opt|data|home|tmp|var|mnt|srv|app|apps|usr|etc|nifi|shared|export|landing|archive|inbound|outbound)(?:/[\w.${}#@ -]*)*", re.I)
#|# Captures the literal assigned to something that looks like a secret: password = "x", "pwd": "x", pass: 'x'
#|SECRET_ASSIGN_RE = re.compile(
#|    r"(?i)([\w.\-]*(?:pass(?:word|wd)?|pwd|secret|api[_-]?key|access[_-]?key|token)[\w.\-]*)[\"']?\s*(?:=|:|,|\()\s*[\"']([^\"']{2,})[\"']"
#|)
#|
#|EL_VAR_RE = re.compile(r"\$\{\s*([A-Za-z_][\w.\-]*)\s*\}")
#|EL_REF_RE = re.compile(r"\$\{\s*([A-Za-z_][\w.\-]*)\s*(?=[:}])")
#|PARAM_RE = re.compile(r"#\{\s*(?:'([^']+)'|([^}]+?))\s*\}")
#|
#|
#|def short(i):
#|    return (i or "")[:8]
#|
#|
#|def slugify(text, maxlen=60):
#|    s = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
#|    return (s[:maxlen].rstrip("-")) or "unnamed"
#|
#|
#|def sha1_bytes(data):
#|    return hashlib.sha1(data).hexdigest()
#|
#|
#|def sha1_file(path):
#|    h = hashlib.sha1()
#|    with open(path, "rb") as f:
#|        for chunk in iter(lambda: f.read(1 << 20), b""):
#|            h.update(chunk)
#|    return h.hexdigest()
#|
#|
#|def file_sig(path):
#|    st = os.stat(path)
#|    return f"{st.st_size}:{int(st.st_mtime)}"
#|
#|
#|def redact_secrets(text):
#|    """Replace literal secret values (password = "x") in a line of code or config."""
#|    return SECRET_ASSIGN_RE.sub(lambda m: m.group(0).replace(m.group(2), REDACTED), text)
#|
#|
#|def clip(text, n=160):
#|    text = " ".join((text or "").split())
#|    return text if len(text) <= n else text[: n - 1] + "…"
#|
#|
#|def md_escape(text):
#|    return (text or "").replace("|", "\\|").replace("\n", " ")
#|
#|
#|def write_if_changed(path, content):
#|    path = Path(path)
#|    path.parent.mkdir(parents=True, exist_ok=True)
#|    if path.exists() and path.read_text(encoding="utf-8") == content:
#|        return False
#|    path.write_text(content, encoding="utf-8")
#|    return True
#@@ FILE nifikb/web.py tc 61fa7b086636fc87
#|"""Self-service web page for colleagues (stdlib only): investigate a file / feed / table / error, daily report, live health,
#|search, team learnings. Read-only. `python -m nifikb web` - configure host / port / login in [web] of nifikb.toml.
#|
#|Security: binds to 127.0.0.1 unless [web] host is set; optional HTTP basic login (one shared user, password from an env var
#|or file); every value is HTML-escaped; uploads are size-limited, written to a temp file and deleted after use."""
#|import base64
#|import email.parser
#|import email.policy
#|import hmac
#|import html
#|import os
#|import re
#|import tempfile
#|import threading
#|import urllib.parse
#|from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
#|from pathlib import Path
#|
#|from . import __version__
#|
#|MAX_UPLOAD = 20 * 1024 * 1024
#|STYLE = """body{font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1f2328;margin:0}
#|header{background:#1f4e79;color:#fff;padding:10px 20px}header a{color:#fff;margin-right:16px;text-decoration:none}
#|main{padding:16px 20px;max-width:1200px}label{display:block;margin-top:8px;font-weight:600}
#|input[type=text],textarea{width:100%;max-width:700px;padding:6px;font:inherit}textarea{height:60px}
#|button{margin-top:12px;padding:7px 18px;background:#1f4e79;color:#fff;border:0;border-radius:4px;cursor:pointer}
#|pre{background:#f6f8fa;padding:10px;overflow-x:auto;white-space:pre-wrap;font-size:12.5px;border:1px solid #d0d7de}
#|ol li{margin:4px 0}.hint{color:#57606a;font-size:12.5px}h2{margin-top:24px;border-bottom:1px solid #d0d7de}"""
#|
#|
#|def _page(title, body):
#|    nav = "".join(f'<a href="{u}">{t}</a>' for u, t in (("/", "Investigate"), ("/report", "Daily report"), ("/health", "Live health"),
#|                                                         ("/search", "Search"), ("/learnings", "Learnings")))
#|    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)} - nifikb</title><style>{STYLE}</style>"
#|            f"</head><body><header><b>NiFi support</b> &nbsp; {nav}</header><main>{body}</main></body></html>").encode("utf-8")
#|
#|
#|def _md_to_html(text):
#|    """Render nifikb's markdown-like reports: #/## headings, numbered causes as a list, the rest preformatted."""
#|    out, pre, ol = [], [], []
#|
#|    def flush():
#|        if ol:
#|            out.append("<ol>" + "".join(f"<li>{html.escape(x)}</li>" for x in ol) + "</ol>")
#|            ol.clear()
#|        if pre:
#|            out.append("<pre>" + html.escape("\n".join(pre)) + "</pre>")
#|            pre.clear()
#|
#|    for line in text.splitlines():
#|        if line.startswith("## ") or line.startswith("# "):
#|            flush()
#|            out.append(("<h2>" if line.startswith("## ") else "<h1>") + html.escape(line.lstrip("# ")) + ("</h2>" if line.startswith("## ") else "</h1>"))
#|        elif re.match(r"^\d+\. ", line) and not pre:
#|            ol.append(line.split(". ", 1)[1])
#|        elif line.strip() or pre:
#|            if ol:
#|                flush()
#|            pre.append(line)
#|    flush()
#|    return "".join(out)
#|
#|
#|def _form(values=None):
#|    v = {k: html.escape(values.get(k, "")) for k in ("file", "feed", "table", "error", "headers")} if values else dict.fromkeys(
#|        ("file", "feed", "table", "error", "headers"), "")
#|    return f"""<h1>Investigate a problem</h1>
#|<p class="hint">Fill in what the ticket gives - any one field is enough. The answer lists the most likely causes first, with evidence.</p>
#|<form method="post" action="/investigate" enctype="multipart/form-data">
#|<label>File name</label><input type="text" name="file" value="{v['file']}" placeholder="SALES_20260926.csv">
#|<label>Feed / API name</label><input type="text" name="feed" value="{v['feed']}">
#|<label>Target table</label><input type="text" name="table" value="{v['table']}">
#|<label>Error text</label><input type="text" name="error" value="{v['error']}" placeholder="a distinctive part of the error message">
#|<label>Headers / field names sent (in file order, comma separated)</label><textarea name="headers">{v['headers']}</textarea>
#|<label>Sample file (CSV / JSON, max 20 MB)</label><input type="file" name="sample">
#|<label><input type="checkbox" name="live" value="1"> read the config tables now (if they may have changed)</label>
#|<button type="submit">Investigate</button></form>"""
#|
#|
#|class App:
#|    def __init__(self, cfg):
#|        from .config import load_config
#|        self.cfg = cfg if isinstance(cfg, dict) else load_config(cfg)
#|        w = self.cfg.get("web") or {}
#|        self.user = w.get("user")
#|        self.password = (os.environ.get(w["password_env"]) if w.get("password_env") else None) or \
#|            (Path(w["password_file"]).read_text(encoding="utf-8").strip() if w.get("password_file") else None)
#|        self.lock = threading.Lock()
#|
#|    def store(self):
#|        from .cli import _store
#|        return _store(self.cfg)
#|
#|    def names(self, store):
#|        from .cli import runtime_names
#|        return runtime_names(store)
#|
#|    # ------------------------------------------------------------------------------------------ pages
#|    def investigate(self, fields, sample_bytes=None, sample_name=None):
#|        from . import diagnose as dg, investigate as inv
#|        tmp = None
#|        try:
#|            if sample_bytes:
#|                suffix = Path(sample_name or "sample.csv").suffix or ".csv"
#|                fd, tmp = tempfile.mkstemp(suffix=suffix)
#|                with os.fdopen(fd, "wb") as f:
#|                    f.write(sample_bytes)
#|            store = self.store()
#|            try:
#|                r = inv.investigate(self.cfg, store, self.names(store), file=fields.get("file") or None, feed=fields.get("feed") or None,
#|                                    table=fields.get("table") or None, error_text=fields.get("error") or None,
#|                                    headers=dg.split_headers([fields.get("headers", "")]), sample_path=tmp, live=bool(fields.get("live")))
#|            finally:
#|                store.db.close()
#|            return inv.format_report(r)
#|        finally:
#|            if tmp:
#|                os.unlink(tmp)
#|
#|    def report(self):
#|        from . import report as rp
#|        store = self.store()
#|        try:
#|            return rp.to_markdown(rp.build_report(self.cfg, store, self.names(store)))
#|        finally:
#|            store.db.close()
#|
#|    def health(self):
#|        from . import nifiapi
#|        if not nifiapi.settings(self.cfg):
#|            return "NiFi REST API not configured ([nifi_api] in nifikb.toml)."
#|        store = self.store()
#|        try:
#|            return nifiapi.format_health(nifiapi.health(nifiapi.Client(nifiapi.settings(self.cfg)), versioned=store.versioned_groups()),
#|                                         self.names(store))
#|        except nifiapi.NiFiApiError as e:
#|            return f"error: {e}"
#|        finally:
#|            store.db.close()
#|
#|    def search(self, q):
#|        store = self.store()
#|        try:
#|            rows = store.search(q, 30) if q else []
#|            return "\n".join(f"[{r['kind']}] {r['title']}  -> {r['doc']}\n    {r['snip']}" for r in rows) or ("no matches" if q else "")
#|        finally:
#|            store.db.close()
#|
#|    def learnings(self):
#|        from . import learnings as lm
#|        items = lm.load_all(self.cfg, include_obsolete=False)
#|        return "\n\n".join(lm.format_item(i) for i in items) or "no team learnings yet"
#|
#|
#|def make_handler(app):
#|    class Handler(BaseHTTPRequestHandler):
#|        server_version = f"nifikb/{__version__}"
#|
#|        def log_message(self, fmt, *args):
#|            pass
#|
#|        def _auth(self):
#|            if not app.user or not app.password:
#|                return True
#|            head = self.headers.get("Authorization", "")
#|            if head.startswith("Basic "):
#|                try:
#|                    user, _, pw = base64.b64decode(head[6:]).decode("utf-8").partition(":")
#|                except (ValueError, UnicodeDecodeError):
#|                    return False
#|                if hmac.compare_digest(user, app.user) and hmac.compare_digest(pw, app.password):
#|                    return True
#|            self.send_response(401)
#|            self.send_header("WWW-Authenticate", 'Basic realm="nifikb"')
#|            self.end_headers()
#|            return False
#|
#|        def _send(self, body, code=200):
#|            self.send_response(code)
#|            self.send_header("Content-Type", "text/html; charset=utf-8")
#|            self.send_header("Content-Length", str(len(body)))
#|            self.send_header("X-Content-Type-Options", "nosniff")
#|            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'")
#|            self.end_headers()
#|            self.wfile.write(body)
#|
#|        def do_GET(self):
#|            if not self._auth():
#|                return
#|            url = urllib.parse.urlparse(self.path)
#|            q = urllib.parse.parse_qs(url.query)
#|            try:
#|                if url.path == "/":
#|                    return self._send(_page("Investigate", _form()))
#|                if url.path == "/report":
#|                    return self._send(_page("Daily report", _md_to_html(app.report())))
#|                if url.path == "/health":
#|                    return self._send(_page("Live health", "<h1>Live NiFi health</h1><pre>" + html.escape(app.health()) + "</pre>"))
#|                if url.path == "/search":
#|                    term = (q.get("q") or [""])[0]
#|                    body = (f"<h1>Search</h1><form><input type='text' name='q' value='{html.escape(term, quote=True)}'>"
#|                            f"<button>Search</button></form><pre>{html.escape(app.search(term))}</pre>")
#|                    return self._send(_page("Search", body))
#|                if url.path == "/learnings":
#|                    return self._send(_page("Learnings", "<h1>Team learnings</h1><pre>" + html.escape(app.learnings()) + "</pre>"))
#|                self._send(_page("Not found", "<p>Not found</p>"), 404)
#|            except Exception as e:  # show the problem instead of a dropped connection
#|                self._send(_page("Error", f"<pre>{html.escape(type(e).__name__ + ': ' + str(e))}</pre>"), 500)
#|
#|        def do_POST(self):
#|            if not self._auth():
#|                return
#|            if urllib.parse.urlparse(self.path).path != "/investigate":
#|                return self._send(_page("Not found", "<p>Not found</p>"), 404)
#|            length = int(self.headers.get("Content-Length") or 0)
#|            if length > MAX_UPLOAD + 100_000:
#|                return self._send(_page("Too large", "<p>The upload is larger than 20 MB.</p>"), 413)
#|            body = self.rfile.read(length)
#|            fields, sample, sample_name = {}, None, None
#|            ctype = self.headers.get("Content-Type", "")
#|            if ctype.startswith("multipart/form-data"):
#|                msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
#|                    f"Content-Type: {ctype}\r\n\r\n".encode() + body)
#|                for part in msg.iter_parts():
#|                    name = part.get_param("name", header="content-disposition")
#|                    payload = part.get_payload(decode=True) or b""
#|                    if name == "sample":
#|                        if payload:
#|                            sample, sample_name = payload, part.get_filename()
#|                    elif name:
#|                        fields[name] = payload.decode("utf-8", "replace").strip()
#|            else:
#|                fields = {k: v[0].strip() for k, v in urllib.parse.parse_qs(body.decode("utf-8", "replace")).items()}
#|            if not any(fields.get(k) for k in ("file", "feed", "table", "error")):
#|                return self._send(_page("Investigate", "<p><b>Give at least a file, feed, table or error text.</b></p>" + _form(fields)))
#|            try:
#|                report = app.investigate(fields, sample, sample_name)
#|                self._send(_page("Investigation", _form(fields) + "<hr>" + _md_to_html(report)))
#|            except Exception as e:
#|                self._send(_page("Error", _form(fields) + f"<pre>{html.escape(type(e).__name__ + ': ' + str(e))}</pre>"), 500)
#|    return Handler
#|
#|
#|def serve(cfg, host=None, port=None):
#|    app = App(cfg)
#|    w = app.cfg.get("web") or {}
#|    host = host or w.get("host", "127.0.0.1")
#|    port = int(port or w.get("port", 8765))
#|    server = ThreadingHTTPServer((host, port), make_handler(app))
#|    print(f"nifikb web on http://{host}:{server.server_address[1]}/" + ("" if app.user else "  (no login configured: [web] user + password_env)"))
#|    server.serve_forever()
#@@ FILE tests/fixtures/local/flow.json.gz b 4b0b53402c2e9e72
#|H4sIAAAAAAAA/+09aXPbtrZ/haPpx8CX2Egg3xwvuZ5xbF/baWfedcaD1WZLkypJOXEz/e/3gBQl
#|epEiOWmSlyidJhaE7ewLcOCPI1eY0mbF1a+uqrOyGL38OLpRv5fV7DN5MbrJikFD/De0qA/n2Y2r
#|dqvs1hXn15VTdqecFM3oJY7br/egvXnq6xejyl1ldVNlrh69/O+7F6OxqtSNa1y1UxaN+9A8bD6p
#|ytvMwvJdu4FeVZnnrjpz1W1m+mkqNy6rBkA5V/Uf07bG3Yxz1cy6lGXzuion4wAmTFk0mc9cNXo5
#|8jqOU2JjxAVNEI29QyohGBHiEyoSLxlToxejrKgbVRh3MBwr41QkgsYoxpIgHMcxYiRhyOuEOwF/
#|YaxhbAHQQO+jbD+L9vPy/SiAcnMDE8HuRvBpXNZZM6XBB8DzFmDyrv0XMD6uSoC0bnc/A/imbNzJ
#|4y+mfcsWYw8ATV1qBOEp8owIRI1PkMKxQAb2jWGjWOLFgGLpY+v9ANCUkxgpYxNrTWo8NnNA911j
#|rvez3H0KUMxSMoU1TTpom7txmKKsrrbUWJlrt1XAJrbmgG2F7VlV2a3hMnpSWPgBpr3qqPxwBuij
#|gEe8MsCKo9CC+olQoSr4+rZn8xHeIulWPOpwP3YwLLDRx9Gb8tZFwKo+z0wTnTUV8NcV7H106lrI
#|X4wOy6sod7cuj95fuyLysLmoKJvIgwhY6Lh3enp8+rgfrHGT1WH1CLCeuWHXAGDUlFELLbT/8rFD
#|iGqu/764CCvUFxe1gn8urWrUZa2A8V2EokdtlxaELytMs2XqW5h5pwytgRxDWHYdtLmoxescA3e7
#|rjZVNm5a1voIX9TNXYvw8CMg2U5yEMATV2Vl2H0c1S5wxPyrwRLnB2/2Ti93Tw9+3TuCPu6DM5Ow
#|jaPSBtpvHx4GVgGc5rDuBIZ1ZKH9pHeZy+3gCzxt15M8wFMcBsxC+2/bp2H+alL0nd9keZ4BAHGr
#|TMykqoA387uzbpdK5y6okLnCUpOmPA/EKWDv9tTl7Sz1ddYK3MirLJ9Urt1tT8GtKQVBGspmqyP8
#|uxkinD1rYKrAM2+Pjg6OXof9uaa6G+jQ8Dl7vBpMopX5o/T+jTPXqsjqG5jmZO9o+/Dg//Yu9w+P
#|f9s/ONwbtUr4VddzRg8cRwBE3QnkuCwA7PNO0k5Oj3f2zs5aXmtl52Bt7fj3iweqhnFLLbMeEVAM
#|MMp4pJ0jiKRKmFilWnqxRKdKmVA5UDWwrEFKw7CEW2xw+gxVk+Bkqmk4JhtN889qmqUK5gi4b6NZ
#|NprlWZpFOCYtJQ6lqXOIcmaQIIohY4j1VMaJ1nixZlFeaokHmkViQ5CRhHCdJk45NdcsJ5NmFzha
#|q9qdOlNWdnUNI2KxroZ5arWvomnGkwZZjap2UaRycE/RzSRvMpDcMBv40VOIvcrrwJBNYGYUuO5G
#|IRM2g+rsL9eyQhzQcm/GPyfgqVrUDZqTcjjh/QGT4kY1gaWRKfPJTQGW41rdZmWg4D5IRQTa5G3f
#|B3Rk6FM/mgVUQlEH/x/5INIoEDWs2VSTx0tao8eo7kKKjk84ldQN+ETThCCeSmZjRiX37Ak4XXWH
#|GgiNyknTq6mysGFrIWYJAobKAvWCvQj8GcrRlHsOjs72Ts8f9dOgOGBBX1aACuj29nwfBZsKPaYD
#|X7sCZNQsosh9WjyJl45oU3lolfwSanV4Xkqs/dDl8RygVJAOXQZ89JiRZv8oO5Vm6TiLhyGJSilB
#|oDkwV5wJQoMQ2alUAX1bJYqC4g1ynDUzGmyM0arGqDUoP53RcTFJncYCwl1NEU2NQ0IxjKSS2ogk
#|5danyyJnpfQwRcAl9sgZ5rAXRvuW159rdAYRtBRsY3U2VudLWp3Lg9dHx6d7zzA+J2XdXFXu7D+H
#|G/uzsT+faX9+TqtjU429sx5JDvEOVVIigcH0GMnjNJEmscItS6IkxibDUEdRiVyiEocxT6hlc6vT
#|eoqA0JCbXimXEvcZakLXzqU8sdhXMTlA7QrGuwokcaiz2qzHWSf48StoeBVUQd8Sgsm3RQZ6Nuo3
#|PDQiwXpG+70aPHcfms8Q5o69fnRpfkqMdw/Otl8d7u3+kHJMKLPOeIpkTAyimCVIEsFQLA0zSZwa
#|LZd4jwILhc0wGUoIRSDBRnqpjPB2Lsd7LU84YBqnbnZAgkFEPu1Ail6YOVn7CGbBil9FoFV1NWnh
#|GgjJdAvRdv9ddDKVRZjyjfoQbTfAThq2HB264qoJaU7Cky5X2Y48UW3j+K65LoMs9jNFuy7PwGi3
#|ZIngi4OroqxAc5zvHhwNNMKjHTxKpHY6ob64CKd4t+7STsZ5ZsJR5db4Lrr4zLTrxWjjTnzCnSir
#|7Aq+yttEavGXq8oo+L+T+qdzMZjR2MQcPFcSS3AxHKgmzg24CdpQGVuYUC9UTSw1qdbp8EjYJxDY
#|2jR4LhyL9oznuYEtgVn7wFau7WRsAttNYPt0YPv2ZHf7/DkR7SaduglnN+nUL2F1JMh8jB1D1FuM
#|qLQwynmJiItT4DufpNQvsjrKG+84ZgM2NdSmiHtNCOEwDxvcuFr5dgCE2P09pPWd4M3tgM3tgP8/
#|twNAI/ywoTaYKsni2CBiMIzS1iOtnYNwWWrpaCJSvzhlhqUzwql7VxxBKylqrbBWGY7x81NmEGaL
#|PmfG1tYwm5zZJmf2Q+fM3gWhBAf1pKz6S+Dg999vADwWzrQAPb7cTIVSiYHwk6XWIOpEgrQF95WB
#|uxBj2IEQybJIViXJvXtBnHAkYbNxSlOlxeBeUOC1clIZ190kXz2Kbhaia1U0rRFNPz9kBzmzLtwT
#|Vr36aoF0whEJKEWp1IBgjmGD1GDkueSxB38uaU8UpkDug/u6d/gZEO5PgNj56mDJBNsBWECNFFlB
#|jKIpF4anASwQO5cfFNZ9aEXur+mPIDC1y4GznjC09cQEZTyais5JBR/A8B7r36F/qG6or8vcBqmD
#|P/f7BAIFhTjoBfrjddCWfqoV9z6Ms5lu6XXOGASuAtPx16zsQbsQ97Y/5qWyr1QeUDC8sn18eXR8
#|fnl4vL17+Wr7cPtopw1wg/oPk4NOnKU9OzQOpgleWNXFcvOZdo7fnJwCkz4h7TvHQNmd84Pjoy9o
#|txVNMBhokF5GOaJGWyQ8CCQVVsuYKMr54lt9WHqgPh9esHDADFZwmWpgC0rYMuldMT3/BaV3pTT9
#|848DFgjwiuUfXxDOxdHX82tMnifGnS2J6hbjG2H+Z4XZGwqudqJRIhOI8S1RIFBGg2VWwscx5y62
#|C3kgXP73yfDcWjAwxUQ65rTiSpGlpnjFM/MvyOSfDASefz6/QJBXLK74hoK8SgXHxh5/xyLMmYgp
#|hb6SA59RHIM9BsFFCbMqAYdPYrL4XAinWjmiB9QnIlgcYGoqE+BPnSz1pn8U9n5KdlcsX/gOQoVV
#|aiU2MvwdyzDDxqYESEaJADnShAGrxRopTwV4gkLEdtmlZec8GQaKnKTA50ozrphMnVzqU6+Yh/v2
#|ZniVnN8CUf4R44aNNH+v0pxQbxk3Brk0BpHmIIyKEjDLWKWxA3kC93hZfgQC6XtHuxwrRBPFLRc+
#|Fdwsk+YVyx++A6O1Sq3FIq/6R0viPUOW+2OljSz/o7IsaCpMogSykoB3zcAwSg1GyFEKnlWqeUoW
#|56pjjV1KhtkuZgxFEDBqB/aHMkGWyfIP54A+JcvUCYmpIMgzBaZZGo4EFQ7x1OJYYa6wHIQQXzdX
#|DcGDsunQ4wA3AqMkiROsYsVg79+/JZ6duv2M4kuoN0JSjZhOwIjGqUU6hlAVJAgMdJymqV6c3wIL
#|5UhKB+THzjPEYppQBlaWy6XB8U9hirEyUmmToDSmoKOCelNWWUQcUYljqWI+/lbiC2BZQYdHTeCL
#|UdDBlFrwshJN9UZ8v2vxZRZiu1hYCIRBcqlP4KcUWCzWUnOTJiRuveGFt8+8Bys0uMqaMCB/KmiM
#|Pdfx8vT0ijffvl1ua6XrdYtOiH803fR9C/HP7EETaq2CkBeJxKSIEpwibUGOcCytEcJYKuQy6mtt
#|h46lS0iChCGpwIxizcQyGf5hzlE3MryR4a8ow++mxHji8pYTliRWaMRVHE5tLcRrxguUcE5hSAJh
#|0WJxZqlPmByaZAjwJEoUxQk3BOLsFsMPqosIZluJZJIzsLwkxXT6cFOyRRnHBAQ8FjzBPQfBQm/H
#|VoU3RqPCvY9uVT5xdeTLKuoKKeoo81Fz7SoXqfB/EQoOB9z2PrOhrrC9Xf5idO2yq+tm9JKx9lJo
#|f8Vx5MuimVVtkPGHwMEPiXG4/Wro7n62Lk1TIbViaVCA4A9Z0GxKhiN3GGpjjgVeUp5KDbckHh5j
#|M6oNMgrDalJrQ/Fj5GMye7Okf4uvR/JpKIkMSJ4XRT6JR9IhrscjTr49HnmMibRMhetLGmxSGphY
#|AlqpBhZLjeF0yXmLihNvh0zMYwcRJsNCs1h7GPwUHnn/4liLgAEeA2O25UZ19D5rriNQMDequou6
#|GrA6uiguir0idIiupicnQUG1dQKzC8hRqGOtAoYjA8T4o/0Mu6+aqAQIoqc5PGZDyhCZfHPKaGMw
#|TolHgOFwp4xLJJzCEL8L7lPCCXdLboULk1I5zLcZRghKDLMKrCGXxj+mTDqrXUThUbgBYXZUEU1q
#|F5mqLKJg9GxkVJ5HgO3+qzyrG1dE100zHtAC1Mt7F71XRROKMKYvIUf6Lto+OWineJoa3UZmckKX
#|UEN8HWokHtwKKsHhilk4UUwd0pRoZBkoe8Nokvgld/1UjNN78RdOGENCxyKG0CSNnXxMDTZ7rqKF
#|f0CN/ftiUk6ah5LyJFa5uMfjdBlW/yEeB2vq27zFU3ehV0t/Pj8/+Zjfk764AZPp24cPAX6Ypvls
#|PloxS/T8NM5jfZvEczBl8nXAXPHe9fMvRj/2jeisGA5T8g9R892C19wfqm7GFUgb6GowoIhqiPFA
#|WXAwjB6c/9Qz6ZY897lSRes0Dtk5+/W0q4V9GH8sqNMx9e3WcNBzCnL6ImVXZSrP/mrDgr5yul65
#|SidrX6JAsCF03Zfz9sU256DOIltOgqVvK5VHs+Jk2Py8DMdM6qa8gdb/hE7RTl/4A19dBCTA5JMm
#|y+tpSfvMPZuu+LAg/NfgH0dnLrzk37Tlyy/gvy7Au9d8cRHykHu1UeMHq15A+9kf2Tj6d7tCdJgV
#|g823cE0LoGeN0yL6KUV/+dh93gqf/+5gmNY7t7iCTdTtUoHcEP+hrixxOolqg0BUzyOuOX4R/J/d
#|trV2M7wsKpWaThd+uwG0foyi6KLlqIvRS/ipYwAAtW0PG+3ajytYom9uS8Hr8MV/o/Dn47BnGXpe
#|FpMb3Q0Yzp4VzQWwy+NBf07Aj8iau8t2tLMrDwTraNylA55+OKTjsadHdXvMgYDrbrStHV1/KYjU
#|3MNR4fdOFFcLlmmf/1hnxJ9NdZmtjjfgr+Z6nQF3Tq21AGgEOzFNi+R14Lipq/E6+O3XMaVda51O
#|vwRObZtWHzi+LteDSFkbchstJvBzB5K1YANJWpfb1sNBCUPy9XEeKgKrtbYG+qvKQDOvNSgYchV4
#|T9XN2vTtB/usesZo6wAvwdVeOAhGvIv+Xlph+sgR2R5nnS+ywPTfs9dbnVXr/IB9AAWw90x3YFaf
#|O3MB1Dhb6Ab8vby6e0GN6hO5vfPT48PDvdPLs73TXw/aNOIXi/Vi8N2EilHCMQX3zYXrpypFnEup
#|tacYL8vTc6MSPbxHTlMIagQ1MYVITyeKzt237duqXM9/UzBi696wb+fBfcpxefAqULzMTXFgYK11
#|FgUAp+8KPfJDfvnYgt81/jzSMaiZ/h7EQyqcQFQXI6wwCeIhkLZKIcwdhHXOMC4WHkVLzIQSfhjb
#|pTZhSOs4gfhdqVgPLoK1gUogxJlrfqvaV+zWDXMejv520rJW4HJQmHxi3dNRxJcKU1oxilrUDN8y
#|KQby95yAZaGMZ8U1oLCZ4fOBkAO6wqNMORrgcv1Y5YGO6DH8pns74c3B0cGb7cMBhs8rlYX3F+69
#|lPjpF6G+iH6ZMeY3VzHflwF2RhinU4s4CclWzVOkKcPIYEclsViaZHGSbLV326bMu/tq52Rn9kLD
#|SVk+vlG1gJ5Wm/HWk8OfQ8IwW0++lTVKO+gmK1AG66Hw0ETYcsBMeDP0N5U1Ufilh+0pT7g71b7t
#|0b1kEnL4UfvbDqtoBzzgOjrqEBK2Ou5eQa//zLe6LqMX87UcbLF/xw/+aroF6OydjbD0eQmOf7Qz
#|fPliJGaTqA/tXlGeeTcdjvBwX/OB0dvTQ/j6dxj4cr6rl//6V14alV9Dy0vOKPlX4+pm91W/QpgU
#|ade8d26636Cwq0m7j/tLve1yKf3c/Qx16Zsl0LZzzN6Usy2OUNhSD+z9V6Z+V1V9cTHfP2JkK91i
#|W7+raoiUe1QM6DoBurwPdwteht96+TERqZYs0amwJpVScUsSzyR2Po4xpSHLTbkGAyoswZgQhqU3
#|MVOJ515R6GDAaDPhv7DjNBOEaf+NEutGGUOMZBIMYRou3GLhkKQ4haFeU5N64RRZkgT2WN87MfJG
#|c2RhTs0loTr2D6OIZ/lJg3Di+/GUzPyix/xpy6Pjo70lTksbNvRBxApJ1XVik+f5Le0vqgW9MAar
#|0K9EyTePaTY+x+wo51YBenTeMd1MYQev4OXFxZkqfld34EEHaOecap1Xk7zZX3Yvatrn1QrXsJ7o
#|uuQ21oI3rC5fnx6/PRnNb2vt9G93mcC+b49eHb892m0x3fc4njQ6vLV3UuZZ2+ns/HRv+83lb//e
#|O7rc/nX74DDQBgj3P3rHPaVxeQAA
#@@ FILE tests/fixtures/local/flow.xml.gz b e9523116cb14db59
#|H4sIAAAAAAAA/+1d60/kOLb/vtL+DxG6H9cQ24mdjGhWNNCzSHTBAj0j3dtXyE/IdFVSk6RomNH+
#|73uceqWgigqdgqFnInU3jWMfP87x75zjx/HuP+8Gfe/W5EWSpe+28La/5ZlUZTpJr99tfbr8gKIt
#|ryhFqkU/S827rTTb+ufe3/+2a/vZ14MsLfOs3zf5rAyqkQq2IKPn7Q7E3WUyMPlhntya9PImN0If
#|ZKO03MP+7s7qr9PCR5BeLilclV3xsSqbm+ukKPPEFDvjhKHIxcCUJnctN3flND3PsvLHPBsNq18h
#|IdF7sc8jFlEf+TgmCPu+jwLCAmQlC00E/2Asd3cg46RICpT3esmHxPsAQ7O7U/0++TbMiqSEUfHu
#|3m35bojvxz93phlUNhhAP2a/u9G1Sd9AO9Uoz2F07/c+9d6ffuodHh3u7iz7/KDk6aiUMBL6LOsn
#|8PXi8vxo/+PVz/866l3t/7R/fLL//uRoTuhB7gktbawY9UvXnw+Q6ehumOTC9WPP9wqjdndWZ1ik
#|8F6oL2e5KYpRbk7lL0aVjlfFTdbXe25k/Rmpp3KupnkoSnGR/GZqVL0f3y8l+jjrhGw/u3Z9uBhZ
#|m9zNGDHMMwUFs3ySMJENHFtfW1uTDR4SHwmlmdaKK4tVTTag0GRaGBDPwRB+puWx3uOGq4iEHNmA
#|RIgqy5DAfoQUUMQgXjjGYndnadEZ4UrMPphS3bjWL4jdA8HDAScT2eOsLn2Qryjv+9NZskwgXUpf
#|FMVell9vi6FQN2Y7TWyyPRufYnuMErnerrVmXGhGQ4KI9efNg5TratY9oLq7c12bjFU+kZeJFarc
#|c9/RtCqUinx3Z/atln8yaHt4m/BtfzaI86bsPGiLA5rZdCovRfGlmCDMw9T5oEF79agPqHdm8iTT
#|01nxKH3ODpOKfvJbNUUm3+ik0JJPs2L3ienrSSIeZ68n1YYXsLhM0hNza/p7P++f91w362mzrP2s
#|KC4zQG4BYGlFvwBmLaQ97KXRF6Uozd75p17vuPfjrJfT9CWjclECGJjr+73L449H51eH58c/HfXq
#|wzPLMCts7owauSHoZdrs7Z+c7O4sJs1y5qP0cDQGm55Is2IPmPwobZ7blPn9XOfUfp0PHoBEZu1H
#|o25EmhSDvbOj3v7J8f8eXX04Of35w7GDy0d56tLzfvxxyiffGyRpUUnQ4pe5NOTZ0OTlfV1ux9MZ
#|5o5XZl41kR5MaSfboj8ye//z+3gCivLmP58dhhefCwH/XmlAuKtCDIZABHmP0q406MQkVeW2Km5h
#|YlTE5tPiUaNWN9PhkZMtgJcpJ1c19tBARuONQaFFlR+zW+MdGteBis3eYZKDjsjyhzU/nypMcwvK
#|r1zbl3Pj0lt14yS79vpuQnpfb0zqOe55aVZ61ungVfUenZ+fnm+yWsg0SAoHi542aWLa1yxGZXbp
#|qAJ3jD43/YpJxU0y3IPubU+690SuJpSsSPqgyFvTmXd/e9r9tRSrTi8YBE9YCELIuvUYxtgiowKD
#|baSkdUbPWgvB+IQbiSOwLCRFlCuDIhFgFItYqojxUFveyEI4G5XO8pGiMOdGZflDXq+yFOIoeEFL
#|YUmrOouhsxg6i+G5FsNwVCItUV5NovkPoU2+CtRjPzZh4Nd9GMEpQczGOBRhEBGqW2kbaE95P3zo
#|kszqP8uK8jo3F/8+aVXLYs8LJ1kOjp6s+rh3cXR+eXX8Y+/0/KhV7RfT+rxLqM8bg5h3BjZZG3vE
#|YeKmaC2Oj1ZyiAqT3yZq5ejEvghpTE1NMCRlBIU8DrQf0Di0wQZZpqCz4HujsVG1qY46yBiIDRMF
#|TdU3y2jOxq6ytjc4OBIskfwe2SwfiHJVpdUq3QYrBYxNCzB9DLJOZ1QdLlZVXuajdrbwYt2jFDrq
#|4H5StzQ34jbJVqLYBzAGPbBaPk3LgY8B5TbJg3mTVNYfDdJvaNNBVXCjjRpqx6Av5v4hZ1oQHQ+5
#|ytJSJKlbzC1+7W+Ouuj3s69oMOqXCbiNc6heKVoTI2NjY/brKAOrHiVg7YP5l4B990pCPal4DB8N
#|qt98xw2ASJkMTDZaiSKVVZmlLaeO2w5wNg/KUjRz1F6ql+MBnUC9cs4AKpLfVlaIncu1sUEFKw1J
#|N7/X1dmuUj3xj0BrV74qcj6q87mSlZxsPLBPuLuVvbtRh9jnMVOa1ayKWNAYGSaYwThkVAcNHGLN
#|JbZGWxSHxCAq4hhFGLxiFYc+Z7FiOjKNHOIfTWqcLzHdu3jKH2b+dNOGUPKC7vDjNv21vOGxB/Qn
#|d4cPjy/c3tth5w+/9Ar6xRO47L9vhcrvHfA/WQFuRb/yAD88afVfmruyVR2f0gQMA28KNi9ojVxP
#|cA1Zi9SoKLMBKqvWf7tpCeKTA2SZHPTiCzpGA7CZli0lPCLyLD0YM1B8cz1IfauQkFzGLNRYYd5A
#|DwahBoUJepAoi4GCsuCWGIIIF5HyBdCy0ea2jhlmEwUY4pdUgN3O8Z9Y8XXrwN/5zvFrbhj3AK26
#|neJup/gvsVNsVGTEwlkyGyNBtY60FirEuIFBEOMwDnxfgUGAGaISTAMJFgGCZBkbyiJuN+8Y4yCK
#|pp5x8JJHyjrPuPOMOwuh84w7z/jP7BkLC7oK11eIsSJIxYSEkjMjjGigCCMTxJoSgzgH9UfDQKGI
#|iAApRbSlsc+kxJs/MjX3kCM/6k5MTUSh85Q7T/mN6sHv8MRUZQQn6g86LtWdk3okDt05qeVEu3NS
#|jyvvzkk1aFN3Tqo7J9Wdk9p4L7tzUn/4OamnqTRfqH7GsnKEI4FVfZ+ZEIpwyFRsY6Eiqxt404QG
#|2ihLUewThSgOGIpJFCA/VoFiPlcybnYB6ahyMQy4I0YMINtAPNq/eLi0PD10FZKXXFpe3rDOqe6c
#|6s6pfq5T/XOWf4Hh2cxe62QuLvPsZhA+vC9vsrSV4hD59agyr9bt5k7bsz8t4J1NaLbdFF8k22jb
#|vlB5MiyLz7kZZLfmSo+G/QQ8RFNsD++9rTY7/FutejPthXdo+gno3tWrKV6reo6v0yw33sXl4XHv
#|5Qyn01EJxszCMYL9sswTCQqj1TECcTcn5J2Y9Hq1iJOQbaIPHwHKqsWXBu1+cnM+/c3kmQsJVI6K
#|1oZPlifXkNzfqOUTcMWl5PUNdcssMpq70+MhjtzRuPUn7JTEyg99JIgfIyoMWD5hqJBhUtHY10T7
#|cvP7CATaPL16Hb/kUbtuI6GzeTqbp9tIeM2NhE9nh/uX3YXrx+LQbSQsJ9ptJDyuvNtIaNCmbiOh
#|20joNhI23stuI+Gvt5EgrLImxEHNOlFUcxRaSQgJhbGBXHSnq0FqdK8sDmcRSV90jb+7V/YndnIv
#|Lk/PzrpT4929su5eWfMKu3tlf557ZX0h60A6XgK3LAB1PdfZOBQxYoJiFirCRNQkPrmJNGE6kigU
#|vgu2okMUKRshFoYU6mS+COJ1S+C/Hafa3DksnPxvqSFACA62WRzEYeBzn3BMJ2fp2TYNQkwiEvpR
#|yPCChQBWoHdjkuub8t1WEFQX0b4murxZaU3U5apK8Zy0vduy4IBVRuXWHibDO1AI7mNNzh4Uny4D
#|OJfQbXem5qtXJRUwf3JvbK8WXmK98sbkxhPub/pgmxC0W41vy5hIVaiJX4+YE1CpwO7GFkZKSkWb
#|XAzkPIqlCDiwjmhEdciRiEmICCNY+yGO8PoTHM2YiMksbOzjMAF1ZmFWZxYJll6Y2DCzzt1GqWPW
#|fKv0ufzAwsdcLUwqFgQokn7kgxHMfRM34AezlCsaMxT5gQ+TihskKZFIBzCpVEAZs2vvpzTjRzAL
#|W4Qpe4IdtPo6ZUe4POLvhtnxAeZJ5U0WUG95A26yN8yTgcjvPbVs7aYBdyLFaRzW3ZSAEMRUoEWo
#|bRgr24A7UimMObHIaoIRjcIYRUZgFMgotJyEJDRrr9E24w6fbfQh/BR38AJ3+PJNwSbciZpz50Ck
#|3qgwnsqhrc4Z1p4S/b4HTJt+6idFCRr8piyH3kwjOcj7aryvYK47a1GN34fx5L23f3ZckfiGOceA
#|FfUw2r6RKAhwJANfWhXSBlwNfUxiHQhElZSIEu4UWQyQSCWoG66AysYwMJxeBBuj3Cq2kniBrf5r
#|TDq7OOkezjjv73/7+9+OUpfBm15MnD4QU+OxO6ySu054CoD0S/U7uL956YFbarwnOWxHafqIxbHV
#|EdX1g4ohpyhQlGquIiapbMBiLFQspGKI+xRsFaUoElpoRAwRzARcBNZfx+IFRjJ/erUdj3k1exNm
#|Z6EXS/vk81hoXr/TH2iDEWM+A4kWATVNjiBArhjTiCAbCIVorEBsaWRQyDX2BVh0OF4b5GcBcti8
#|Swu3FJt0KeAqZrjOJj/0OdIRUYLyMFJhk7hFJjIklpoiHoMpQ0NskKAKI8Dn0Lexj5kLA9i8S4TO
#|lpAwJU/1CcAoBUdtYcll0i/B2MKtU0B5FPvW+JxyIaMmt05pJARTzKKAa+iXiRiCXhKQYiCDfU6i
#|iDU5LVKDAGnce0xJWtZXwarZNMYfPJlbD9BoNU4V2ShX5rjpCZlZ9gcEqoeyjps+kLVY5gEpt4e7
#|d3Z+enB0ceH8u1rqLKee+9rHTcVwscwyUs/rxJKCy4hWDf/wqdc7Olkos9ihvO7UFSPlYNUtAC1z
#|Hgfizp2p/PfIjIy7Uz99LetR+tIS07euJq9hLf00K2hXvvK15Ett1U7o96IvAPlna2eHp1e908ur
#|k9P9w6v3+yf7vYMjt5T3OON8RrsFU0cYDPTZubidpbW4mZOPV+anFR2cfjw7BwlaqKSebwoIjyBg
#|JSiATpJS10HBMMKcC8UjHFAsgyb4TajWwgYGRUxxMDswB1CwMRCMtYoipWm01n9+PVBo9KbZ2wSF
#|Ro+t/JGgUOtOhwvfMS74EhvwAuuC4SxNRrU0MYloEJEmISoojxQTEdIxeJo0MAbF0ghkKJWccRly
#|8oaMhUZhOd4mLjQywztjYSOgMA1R9ddDBbdDbu3CwqBkAXiwHGQF21D6RDzeIX+Vydts8/5tTt5O
#|qXdK/VWUOriUkZYLp7FDLBBlItRhZHkUNtksY9TqIFQKGe4Tt4QFZCjRKMKC+ybi4Ac0ui/yasb+
#|+sn1NnGh0eLFd4ULs/3kDhfeEi7AHDGE0/p+H+hLFPiU0YAbGcas0SKAVVFMJQokA1DxuUbStxgp
#|ogEtfM651B0ubMZeWL+P0Bn7nbHfEhW4FIbImliQiEQga4zSmAlQTU1QIQwin1ILjn+oLaLYB0PB
#|D0PEAi1YGMOkI2/IWmj0ZsXbRIVGqxfflbXwpoHhr2wtGGNJ3SwNCXcHfGQQiiDmJm7yvlmAleYE
#|BJSSCCMqSYAi4kskLI1AiUWRrxvF23kta6FB6Pq3iQuNwiN1uNDhwga8iJjh+pZBaLBGOgpjLhnW
#|lDTBBUEZlrGxKAho6I4xgb1gmTuhpmXsE0HDsFFU61fChSaT643iQpNd0O8KF7JxAJiiCnDWocPb
#|QgdnWVtWP+MdBe5wdmwCI0UoxMOtg6VT3CpqKGMSsRhki2oiUEyURAEXEXjsYWj8N7TG0Ogl2LeJ
#|Do0coe8KHTqr4Y/GBXdEum/yi3GQkAfGQxDBDK6vaXEN8iGlzzQXQviyyXmDWGAWS+UjLDB4FtJE
#|SGohQB8bzLRRQeiuAzUIZXVw8dM4SsqFKX/Ol0R3W3JL9xlXQJdf6FXF7fayil/oJu80nonJk9n1
#|12kEl2KT13tNddJaT2IfTH+bi+TKEDjV9XuvGoa1VwXTbHJdv9W1vfqN/zbXHCd04Lu7Ut9Hk0F6
#|mZeCJpWJCt9QsWagkvQGOF4uhrPZRP25uU6Kst310NXBdbz55dtxpm33+T+baPhy5nwLJZkDILYK
#|qjQhtORtpNoAiNs82x7nbDcAoJvM8jemnkXmMhlsikxRisFwA7QAR9c8njV+harV8P3kinoXBpSq
#|KFdH7flHuwCgqeqPtPH+VUVa806SdOXUaB1c5t8unIx3MH1Ya1U97SKnHhVKDBvU8rl1tFkXPe2j
#|yL881t7PodQDHe7UD1hMraQ7TwazEFIvyr+PmV4pIh+Pe8cf909a1TKJH7dW7j+3i1c8FfzLXCT9
#|Ktjyuki77eP+gAk2KpN+gTb4uFxlDS+1fdcZxY2iJ641it2yfBgFGJxkpcAotrG7hxuiILBC+twG
#|sWn2Tlxlmy4J9/iitvC4vr+qCfw80w4GDd1UI4bgb3Jr2gXX7Oy6V7Xrfof/brmools/eFtjydz6
#|h0tz2V3aaQ5cHSdV8fQKSPy/isLvszyZy3OVjgayyjqjl6Tl1n/+8SDzryORlkl5f1WVMnptgWEO
#|E+PKwASrZ9XZCMT5ce5xWwC6TdMGVRFzmpN2gQrruYtKSS8hW8XwbpLz1zK/StaPwwBw+6ZJxnsj
#|GhEEudEjVVaD1aSdgyIfNhmnKV0FJkETumOj2EmQS2hQYHiTNWux0NotElU9xM8tQBq1HSS5qTQ0
#|61sGWfvNx84FtcobNQHsCnDBs2aZq6iZTjZEUTbmy7SQTfJnlNIG+ltdt1+SGXL+v9cOmJ2CGkeM
#|Ru6/YD8Wq605Z1VkaYHaBs3qnNy37+S+kktx8SUZvoojnVSvdqC5QfZyLkvns3/fPvtLuJyN6htH
#|TZ5FiZp6Di7Ty/W2GtGxteJVwYtb1dTCtW4SiX6ta21UpIzkGoXEhbiSIQcy4GkrbGhMNI4VWxuL
#|Zayj3h+cHcz2zM6y7FF07BfwsbVUw+1lNb+Qt+3qm3rXb8G5nj4L48377306P1klkb9A+39wNuE1
#|2KW/9n/Y2elnSvRvIOWHMKBkpwTFfvi+ra0ybtKhc99z78Bxwus94TY7JswbtT0ut5m40LqihVwv
#|q/3yRuFQfwGb7vO8QSgg23w72P5FtGsU6ANwILMCjYoKIJe9M/FtBBU4vi5uOijijdIFXzlVyVC0
#|inM/pwZy8HXJk0rfJFyfnrC6p6xrxa2z5a2dVWJS9TszOiI+V0wZTTAnMvalxKGKMOGhFSKgggIQ
#|C6sIYYHUEVWWxD7GAfzRKrYMcFqEsp1H4h4o+1kkpefs8lXNDX13C6TfT9qNiqvrMgOXsgY4KydV
#|OyUPRnuix8uZVYj+NmJTwfYgSVECqOvecFjd6JYB6auKxF2DitqNzqwiVwfqJ9aUT3Aftdudrypz
#|9JE05VdjUmQAYyrW5KPVPdxErY5pVWWT5yHgn6c6Sqdxs9vWW2S2fG7lDfr77dYewIpgsn6VifKI
#|IIAUn0ruSyaaBFdkfhTgSPiIhZi600XutoLgKAzjWEpLMW4W5Whv/zbPXm0npTosUK/xz7KXMnGd
#|X2ozxQyk0dpo5AawOybz3W2nbPCYTKMHYNbrvjYbwRbLhbgrVskQaUXgR0yo9JuE/FWQPQ5imAHc
#|XdDGkUExxRwJZiVV3EZGkGfg12sfj6wBWXdAcryc+ZwDkhWMTUGtOyTZHZLs0L8h+s/Pt695LrF3
#|2mv36OeGFM1TVYDrnbll3mEGM+6pmihpo9BuBYCmnMXxni0QbY3fj3i3dfjD5wuR/iLuP1dYOwbL
#|SUzj3Z08y8ofZ+j8WD1O7urs5maY5e5piup9qEmi20MaGNAMZ3l2m0Bnqw/j2xUHM0qQ9F+uKYX7
#|FMQAAA==
#@@ FILE tests/fixtures/repo/nifi-acme-processors/pom.xml t 71d6f74a011a4230
#|<project>
#|  <parent><groupId>com.acme</groupId><artifactId>acme-parent</artifactId><version>1.0</version></parent>
#|  <artifactId>nifi-acme-processors</artifactId>
#|  <packaging>jar</packaging>
#|  <dependencies><dependency><artifactId>nifi-api</artifactId></dependency></dependencies>
#|</project>
#@@ FILE tests/fixtures/repo/nifi-acme-processors/src/main/java/com/acme/nifi/ValidateOrderJson.java t 0d4cd2b7f3021105
#|package com.acme.nifi;
#|
#|import org.apache.nifi.annotation.behavior.InputRequirement;
#|import org.apache.nifi.annotation.behavior.WritesAttribute;
#|import org.apache.nifi.annotation.documentation.CapabilityDescription;
#|import org.apache.nifi.annotation.documentation.Tags;
#|import org.apache.nifi.components.PropertyDescriptor;
#|import org.apache.nifi.processor.AbstractProcessor;
#|import org.apache.nifi.processor.Relationship;
#|
#|@Tags({"acme", "json", "validation"})
#|@InputRequirement(InputRequirement.Requirement.INPUT_REQUIRED)
#|@CapabilityDescription("Validates vendor order JSON against the ACME validator service "
#|        + "and routes to valid or invalid.")
#|@WritesAttribute(attribute = "validation.status", description = "VALID or INVALID")
#|public class ValidateOrderJson extends AbstractProcessor {
#|
#|    static final String ORDER_ID_ATTR = "order.id";
#|    private static final String AUDIT_SQL = "INSERT INTO validation_log (order_id, status) VALUES (?, ?)";
#|    private static final String FALLBACK_URL = "https://validator-backup.acme.com/api/v1/check";
#|    private static final String DEFAULT_PASSWORD = "Sup3rS3cret!";
#|
#|    public static final PropertyDescriptor VALIDATION_URL = new PropertyDescriptor.Builder()
#|            .name("Validation URL")
#|            .description("Endpoint of the validator service")
#|            .defaultValue("https://validator.acme.com/api/v1/check")
#|            .required(true)
#|            .build();
#|
#|    public static final PropertyDescriptor API_TOKEN = new PropertyDescriptor.Builder()
#|            .name("Api Token")
#|            .displayName("API Token")
#|            .description("Token for the validator")
#|            .sensitive(true)
#|            .build();
#|
#|    public static final Relationship REL_VALID = new Relationship.Builder()
#|            .name("valid").description("Order passed validation").build();
#|    public static final Relationship REL_INVALID = new Relationship.Builder()
#|            .name("invalid").description("Order failed validation").build();
#|    public static final Relationship REL_FAILURE = new Relationship.Builder()
#|            .name("failure").description("Validator could not be reached").build();
#|
#|    @Override
#|    public void onTrigger(ProcessContext context, ProcessSession session) {
#|        FlowFile flowFile = session.get();
#|        String orderId = flowFile.getAttribute(ORDER_ID_ATTR);
#|        String vendor = flowFile.getAttribute("vendor");
#|        String bucket = "acme-orders-raw";
#|        flowFile = session.putAttribute(flowFile, "validation.status", "VALID");
#|        flowFile = session.putAttribute(flowFile, "validated.by", "acme");
#|        String archive = "/data/archive/orders";
#|        session.transfer(flowFile, REL_VALID);
#|    }
#|
#|    private void audit(Connection c) {
#|        String q = "SELECT status FROM order_status s "
#|                + "JOIN vendors v ON v.id = s.vendor_id WHERE s.order_id = ?";
#|    }
#|}
#@@ FILE tests/fixtures/repo/nifi-acme-processors/src/main/resources/META-INF/services/org.apache.nifi.processor.Processor t c170a921d2ac0a47
#|com.acme.nifi.ValidateOrderJson
#@@ FILE tests/fixtures/repo/scripts/enrich.py t db3737e67fb96bcd
#|import sys
#|import pymysql
#|
#|DB_HOST = "10.20.30.40"
#|password = "hunter2"
#|conn = pymysql.connect(host=DB_HOST, user="etl", password=password, database="meta")
#|
#|
#|def enrich(order_id):
#|    cur = conn.cursor()
#|    cur.execute("SELECT name, region FROM customers WHERE id = %s", (order_id,))
#|    return cur.fetchone()
#|
#|
#|def main():
#|    print(enrich(sys.argv[1]))
#@@ FILE tests/fixtures/repo/scripts/load_audit.groovy t d2e8136fc0abb9db
#|def sql = "UPDATE file_audit SET status = 'LOADED' WHERE file_name = ?"
#|def target = "s3://acme-orders-curated/audit/"
#@@ FILE tests/fixtures/stg_sales.parquet b 3b77654b35086125
#|UEFSMRUEFSAVJEwVBBUAEgAAEDwBAAAAAAAAAAIAAAAAAAAAFQAVEhUWLBUEFRAVBhUGHBgIAgAA
#|AAAAAAAYCAEAAAAAAAAAFgAoCAIAAAAAAAAAGAgBAAAAAAAAABERAAAACSACAAAABAEBAwIVBBUU
#|FRhMFQQVABIAAAokAQAAAGEBAAAAYhUAFRIVFiwVBBUQFQYVBhw2ACgBYhgBYRERAAAACSACAAAA
#|BAEBAwIVBBUKFQ5MFQIVABIAAAUQAAAAAJYVABUSFRYsFQQVEBUGFQYcGAUAAAAAlhgFAAAAAJYW
#|AigFAAAAAJYYBQAAAACWEREAAAAJIAIAAAADAQECABUEFRwVIEwVAhUAEgAADjQKAAAAMjAyNi0w
#|OS0yNhUAFRIVFiwVBBUQFQYVBhw2ACgKMjAyNi0wOS0yNhgKMjAyNi0wOS0yNhERAAAACSACAAAA
#|BAEBBAAVBBUUFRhMFQQVABIAAAokAQAAAHgBAAAAeRUAFRIVFiwVBBUQFQYVBhw2ACgBeRgBeBER
#|AAAACSACAAAABAEBAwIVBBlsNQAYBnNjaGVtYRUKABUEJQIYCE9SREVSX05PABUMJQIYCUNVU1Rf
#|TkFNRSUATBwAAAAVDhUKFQIYBkFNT1VOVCUKFQQVFCxcFQQVFAAAABUMJQIYCE9SREVSX0RUJQBM
#|HAAAABUMJQIYB0xPQURfVFMlAEwcAAAAFgQZHBlcJgAcFQQZNQAGEBkYCE9SREVSX05PFQIWBBbM
#|ARbUASZIJggcGAgCAAAAAAAAABgIAQAAAAAAAAAWACgIAgAAAAAAAAAYCAEAAAAAAAAAEREAGSwV
#|BBUAFQIAFQAVEBUCADwpBhkmAAQAAAAmABwVDBk1AAYQGRgJQ1VTVF9OQU1FFQIWBBZ8FoQBJpAC
#|JtwBHDYAKAFiGAFhEREAGSwVBBUAFQIAFQAVEBUCADwWBBkGGSYABAAAACYAHBUOGTUABhAZGAZB
#|TU9VTlQVAhYEFp4BFqYBJooDJuACHBgFAAAAAJYYBQAAAACWFgIoBQAAAACWGAUAAAAAlhERABks
#|FQQVABUCABUAFRAVAgA8KQYZJgICAAAAJgAcFQwZNQAGEBkYCE9SREVSX0RUFQIWBBaoARawASbC
#|BCaGBBw2ACgKMjAyNi0wOS0yNhgKMjAyNi0wOS0yNhERABksFQQVABUCABUAFRAVAgA8FigZBhkm
#|AAQAAAAmABwVDBk1AAYQGRgHTE9BRF9UUxUCFgQWfBaEASbqBSa2BRw2ACgBeRgBeBERABksFQQV
#|ABUCABUAFRAVAgA8FgQZBhkmAAQAAAAWigYWBCYIFrIGABkcGAxBUlJPVzpzY2hlbWEYzAMvLy8v
#|LzFBQkFBQVFBQUFBQUFBS0FBd0FCZ0FGQUFnQUNnQUFBQUFCQkFBTUFBQUFDQUFJQUFBQUJBQUlB
#|QUFBQkFBQUFBVUFBQURnQUFBQW5BQUFBR0FBQUFBd0FBQUFCQUFBQUVULy8vOEFBQUVGRUFBQUFC
#|Z0FBQUFFQUFBQUFBQUFBQWNBQUFCTVQwRkVYMVJUQUhELy8vOXMvLy8vQUFBQkJSQUFBQUFjQUFB
#|QUJBQUFBQUFBQUFBSUFBQUFUMUpFUlZKZlJGUUFBQUFBblAvLy81ai8vLzhBQUFFSEVBQUFBQ0FB
#|QUFBRUFBQUFBQUFBQUFZQUFBQkJUVTlWVGxRQUFBZ0FEQUFFQUFnQUNBQUFBQW9BQUFBQ0FBQUEw
#|UC8vL3dBQUFRVVFBQUFBSUFBQUFBUUFBQUFBQUFBQUNRQUFBRU5WVTFSZlRrRk5SUUFBQUFRQUJB
#|QUVBQUFBRUFBVUFBZ0FCZ0FIQUF3QUFBQVFBQkFBQUFBQUFBRUNFQUFBQUNRQUFBQUVBQUFBQUFB
#|QUFBZ0FBQUJQVWtSRlVsOU9Ud0FBQUFBSUFBd0FDQUFIQUFnQUFBQUFBQUFCUUFBQUFBQUFBQUE9
#|ABggcGFycXVldC1jcHAtYXJyb3cgdmVyc2lvbiAyNS4wLjEZXBwAABwAABwAABwAABwAAABiBAAA
#|UEFSMQ==
#@@ FILE tests/fixtures_builder.py tc bc8e25ac276960fa
#|"""Builds a realistic multi-group test environment in a temp dir: flow.json.gz, custom NAR, SQLite metadata DB, config."""
#|import gzip
#|import io
#|import json
#|import sqlite3
#|import zipfile
#|from pathlib import Path
#|
#|FIXTURES = Path(__file__).parent / "fixtures"
#|SECRET_VALUES = ["abc123secret", "hunter2", "Sup3rS3cret!", "plainpass99", "varsecret77"]
#|
#|ROOT, PG = "root-0000-0000", "pg-vendor-0000"
#|DBCP_INSTANCE = "dbcp-instance-1111"
#|
#|
#|def proc(pid, name, ptype, props=None, state="RUNNING", auto=(), bundle=None, group=ROOT, **kw):
#|    p = {"identifier": pid, "instanceIdentifier": f"inst-{pid}", "name": name, "type": ptype,
#|         "bundle": bundle or {"group": "org.apache.nifi", "artifact": "nifi-standard-nar", "version": "1.27.0"},
#|         "properties": props or {}, "scheduledState": state, "schedulingStrategy": kw.get("strategy", "TIMER_DRIVEN"),
#|         "schedulingPeriod": kw.get("period", "0 sec"), "concurrentlySchedulableTaskCount": kw.get("tasks", 1),
#|         "autoTerminatedRelationships": list(auto), "executionNode": kw.get("node", "ALL"), "comments": kw.get("comments", ""),
#|         "componentType": "PROCESSOR", "groupIdentifier": group}
#|    return p
#|
#|
#|def conn(cid, src, src_type, dst, dst_type, rels, group=ROOT, src_group=None, dst_group=None):
#|    return {"identifier": cid, "instanceIdentifier": f"inst-{cid}", "name": "",
#|            "source": {"id": src, "type": src_type, "groupId": src_group or group, "name": src},
#|            "destination": {"id": dst, "type": dst_type, "groupId": dst_group or group, "name": dst},
#|            "selectedRelationships": rels, "backPressureObjectThreshold": 10000, "backPressureDataSizeThreshold": "1 GB",
#|            "flowFileExpiration": "0 sec", "prioritizers": [], "loadBalanceStrategy": "DO_NOT_LOAD_BALANCE"}
#|
#|
#|def service(sid, name, stype, props, state="ENABLED", group=ROOT):
#|    return {"identifier": sid, "instanceIdentifier": f"instance-{sid}" if sid != "dbcp-1111" else DBCP_INSTANCE, "name": name, "type": stype,
#|            "bundle": {"group": "org.apache.nifi", "artifact": "nifi-dbcp-service-nar", "version": "1.27.0"},
#|            "properties": props, "scheduledState": state, "componentType": "CONTROLLER_SERVICE", "groupIdentifier": group}
#|
#|
#|ACME = {"group": "com.acme", "artifact": "acme-nifi-nar", "version": "1.0.0"}
#|JSON_SCHEMA = json.dumps({"type": "record", "name": "Audit", "fields": [
#|    {"name": "order_id", "type": "string"}, {"name": "vendor", "type": "string"},
#|    {"name": "status", "type": "string"}, {"name": "extra_field", "type": "string"}]})
#|
#|
#|def nested_flow(bucket="#{s3.bucket}"):
#|    vendor = {
#|        "identifier": PG, "instanceIdentifier": "inst-pg", "name": "Vendor JSON Ingestion", "comments": "Receives vendor orders as JSON",
#|        "parameterContextName": "vendor-params", "variables": {},
#|        "versionedFlowCoordinates": {"registryUrl": "http://registry:18080", "bucketId": "b1", "flowId": "f1", "version": 3},
#|        "processors": [
#|            proc("p-extract", "Extract fields", "org.apache.nifi.processors.standard.EvaluateJsonPath",
#|                 {"Destination": "flowfile-attribute", "order.id": "$.id", "vendor": "$.vendor"}, auto=["unmatched", "failure"], group=PG),
#|            proc("p-validate", "Validate order", "com.acme.nifi.ValidateOrderJson",
#|                 {"Validation URL": "https://validator.acme.com/api/v1/check", "Api Token": "abc123secret"}, bundle=ACME, group=PG),
#|            proc("p-s3", "Store raw JSON", "org.apache.nifi.processors.aws.s3.PutS3Object",
#|                 {"Bucket": bucket, "Object Key": "${vendor}/${filename}", "Region": "us-east-1", "Secret Access Key": "#{aws.secret}"},
#|                 auto=["failure"], group=PG,
#|                 bundle={"group": "org.apache.nifi", "artifact": "nifi-aws-nar", "version": "1.27.0"}),
#|            proc("p-rejects", "Write rejects", "org.apache.nifi.processors.standard.PutFile",
#|                 {"Directory": "#{reject.dir}/rejects", "Conflict Resolution Strategy": "replace"}, auto=["success", "failure"], group=PG),
#|        ],
#|        "inputPorts": [{"identifier": "in-port", "instanceIdentifier": "inst-in", "name": "orders in", "scheduledState": "RUNNING",
#|                        "componentType": "INPUT_PORT", "groupIdentifier": PG}],
#|        "outputPorts": [{"identifier": "out-port", "instanceIdentifier": "inst-out", "name": "stored", "scheduledState": "RUNNING",
#|                         "componentType": "OUTPUT_PORT", "groupIdentifier": PG}],
#|        "connections": [
#|            conn("c1", "in-port", "INPUT_PORT", "p-extract", "PROCESSOR", [], group=PG),
#|            conn("c2", "p-extract", "PROCESSOR", "p-validate", "PROCESSOR", ["matched"], group=PG),
#|            conn("c3", "p-validate", "PROCESSOR", "p-s3", "PROCESSOR", ["valid"], group=PG),
#|            conn("c4", "p-validate", "PROCESSOR", "p-rejects", "PROCESSOR", ["invalid"], group=PG),
#|            conn("c5", "p-s3", "PROCESSOR", "out-port", "OUTPUT_PORT", ["success"], group=PG),
#|        ],
#|        "controllerServices": [], "labels": [{"label": "Validation is done by the ACME custom processor", "componentType": "LABEL"}],
#|        "funnels": [], "processGroups": [], "remoteProcessGroups": [],
#|    }
#|    root = {
#|        "identifier": ROOT, "instanceIdentifier": "inst-root", "name": "NiFi Flow", "comments": "",
#|        "variables": {"base.dir": "/data/landing", "etl.password": "varsecret77"},
#|        "processors": [
#|            proc("p-listen", "Receive orders API", "org.apache.nifi.processors.standard.ListenHTTP",
#|                 {"Listening Port": "8081", "Base Path": "orders"}),
#|            proc("p-audit", "Write audit row", "org.apache.nifi.processors.standard.PutDatabaseRecord",
#|                 {"put-db-record-record-reader": "instance-reader-1", "put-db-record-dcbp-service": DBCP_INSTANCE,
#|                  "put-db-record-statement-type": "INSERT", "put-db-record-table-name": "file_audit",
#|                  "put-db-record-unmatched-field-behavior": "Fail on Unmatched Fields"}, auto=["success", "failure", "retry"]),
#|            proc("p-archive", "Archive order", "org.apache.nifi.processors.standard.PutDatabaseRecord",
#|                 {"put-db-record-record-reader": "instance-reader-1", "put-db-record-dcbp-service": DBCP_INSTANCE,
#|                  "put-db-record-statement-type": "INSERT", "put-db-record-table-name": "order_archive"}, auto=["success", "failure", "retry"]),
#|            proc("p-lookup", "Lookup customer", "org.apache.nifi.processors.standard.ExecuteSQL",
#|                 {"Database Connection Pooling Service": DBCP_INSTANCE,
#|                  "SQL select query": "SELECT c.id, c.name FROM customers c JOIN orders o ON o.cust_id = c.id WHERE o.id = '${order.id}'"},
#|                 auto=["failure"]),
#|            proc("p-enrich", "Enrich via python", "org.apache.nifi.processors.standard.ExecuteStreamCommand",
#|                 {"Command Path": "python", "Command Arguments": "${base.dir}/scripts/enrich.py ${order.id}"}, auto=["original", "nonzero status"]),
#|            proc("p-gen", "Nightly trigger", "org.apache.nifi.processors.standard.GenerateFlowFile", {}, state="DISABLED",
#|                 strategy="CRON_DRIVEN", period="0 0 2 * * ?"),
#|        ],
#|        "inputPorts": [], "outputPorts": [], "funnels": [], "remoteProcessGroups": [], "labels": [],
#|        "connections": [
#|            conn("r1", "p-listen", "PROCESSOR", "in-port", "INPUT_PORT", ["success"], dst_group=PG),
#|            conn("r2", "out-port", "OUTPUT_PORT", "p-audit", "PROCESSOR", [], src_group=PG),
#|            conn("r3", "out-port", "OUTPUT_PORT", "p-lookup", "PROCESSOR", [], src_group=PG),
#|            conn("r4", "p-lookup", "PROCESSOR", "p-enrich", "PROCESSOR", ["success"]),
#|            conn("r5", "p-enrich", "PROCESSOR", "p-archive", "PROCESSOR", ["output stream"]),
#|            conn("r6", "p-gen", "PROCESSOR", "p-lookup", "PROCESSOR", ["success"]),
#|        ],
#|        "controllerServices": [
#|            service("dbcp-1111", "MetaDB", "org.apache.nifi.dbcp.DBCPConnectionPool", {
#|                "Database Connection URL": "jdbc:mariadb://dbhost.acme.com:3306/meta", "Database Driver Class Name": "org.mariadb.jdbc.Driver",
#|                "Database User": "nifi_rw", "Password": "enc{0123456789abcdef}"}),
#|            service("reader-1", "AuditJsonReader", "org.apache.nifi.json.JsonTreeReader", {
#|                "schema-access-strategy": "schema-text-property", "schema-text": JSON_SCHEMA}),
#|            service("writer-unused", "UnusedWriter", "org.apache.nifi.json.JsonRecordSetWriter", {}, state="DISABLED"),
#|        ],
#|        "processGroups": [vendor],
#|    }
#|    return {
#|        "encodingVersion": {"majorVersion": 2, "minorVersion": 0},
#|        "parameterContexts": [{
#|            "name": "vendor-params", "inheritedParameterContexts": ["shared-params"],
#|            "parameters": [{"name": "s3.bucket", "value": "acme-orders-raw", "sensitive": False},
#|                           {"name": "aws.secret", "value": "enc{ffff}", "sensitive": True},
#|                           {"name": "db.password", "value": "plainpass99", "sensitive": False}]},
#|            {"name": "shared-params", "parameters": [{"name": "reject.dir", "value": "/data/shared", "sensitive": False}]}],
#|        "controllerServices": [], "reportingTasks": [], "rootGroup": root,
#|    }
#|
#|
#|NESTED_XML = """<?xml version="1.0" encoding="UTF-8"?>
#|<flowController encoding-version="1.4">
#|  <parameterContexts>
#|    <parameterContext><id>ctx-1</id><name>file-params</name>
#|      <parameter><name>landing</name><value>/data/in</value><sensitive>false</sensitive></parameter>
#|    </parameterContext>
#|  </parameterContexts>
#|  <rootGroup>
#|    <id>r</id><name>NiFi Flow</name>
#|    <processor><id>x-list</id><name>List landing</name><class>org.apache.nifi.processors.standard.ListFile</class>
#|      <bundle><group>org.apache.nifi</group><artifact>nifi-standard-nar</artifact><version>1.19.1</version></bundle>
#|      <maxConcurrentTasks>1</maxConcurrentTasks><schedulingPeriod>1 min</schedulingPeriod><scheduledState>RUNNING</scheduledState>
#|      <schedulingStrategy>TIMER_DRIVEN</schedulingStrategy>
#|      <property><name>Input Directory</name><value>/data/in/files</value></property>
#|      <property><name>File Filter</name></property>
#|    </processor>
#|    <processGroup><id>g1</id><name>File Ingestion</name><parameterContextId>ctx-1</parameterContextId>
#|      <inputPort><id>g1-in</id><name>files</name><scheduledState>RUNNING</scheduledState></inputPort>
#|      <processor><id>x-fetch</id><name>Fetch it</name><class>org.apache.nifi.processors.standard.FetchFile</class>
#|        <bundle><group>org.apache.nifi</group><artifact>nifi-standard-nar</artifact><version>1.19.1</version></bundle>
#|        <maxConcurrentTasks>2</maxConcurrentTasks><schedulingPeriod>0 sec</schedulingPeriod><scheduledState>STOPPED</scheduledState>
#|        <schedulingStrategy>TIMER_DRIVEN</schedulingStrategy>
#|        <property><name>File to Fetch</name><value>#{landing}/${filename}</value></property>
#|        <autoTerminatedRelationship>failure</autoTerminatedRelationship>
#|        <autoTerminatedRelationship>success</autoTerminatedRelationship>
#|      </processor>
#|      <connection><id>gc1</id><sourceId>g1-in</sourceId><sourceGroupId>g1</sourceGroupId><sourceType>INPUT_PORT</sourceType>
#|        <destinationId>x-fetch</destinationId><destinationGroupId>g1</destinationGroupId><destinationType>PROCESSOR</destinationType></connection>
#|      <variable name="region" value="eu"/>
#|    </processGroup>
#|    <connection><id>rc1</id><sourceId>x-list</sourceId><sourceGroupId>r</sourceGroupId><sourceType>PROCESSOR</sourceType>
#|      <destinationId>g1-in</destinationId><destinationGroupId>g1</destinationGroupId><destinationType>INPUT_PORT</destinationType>
#|      <relationship>success</relationship></connection>
#|  </rootGroup>
#|  <controllerServices/>
#|</flowController>
#|"""
#|
#|ACME_MANIFEST = """<extensionManifest><groupId>com.acme</groupId><artifactId>acme-nifi-nar</artifactId><version>1.0.0</version><extensions>
#|<extension><name>com.acme.nifi.ValidateOrderJson</name><type>PROCESSOR</type>
#|<description>Validates vendor order JSON (from NAR manifest).</description><tags><tag>acme</tag></tags>
#|<properties>
#| <property><name>Validation URL</name><displayName>Validation URL</displayName><description>Endpoint</description>
#|  <defaultValue>https://validator.acme.com/api/v1/check</defaultValue><required>true</required><sensitive>false</sensitive></property>
#| <property><name>Api Token</name><displayName>API Token</displayName><description>Token</description><required>false</required><sensitive>false</sensitive></property>
#|</properties>
#|<relationships><relationship><name>valid</name><description>ok</description><autoTerminated>false</autoTerminated></relationship>
#|<relationship><name>invalid</name><description>bad</description><autoTerminated>false</autoTerminated></relationship>
#|<relationship><name>failure</name><description>error</description><autoTerminated>false</autoTerminated></relationship></relationships>
#|<inputRequirement>INPUT_REQUIRED</inputRequirement>
#|</extension></extensions></extensionManifest>"""
#|
#|
#|STD_MANIFEST = """<extensionManifest><groupId>org.apache.nifi</groupId><artifactId>nifi-standard-nar</artifactId><version>1.27.0</version><extensions>
#|<extension><name>org.apache.nifi.processors.standard.GenerateFlowFile</name><type>PROCESSOR</type><description>Generates FlowFiles</description>
#| <properties><property><name>File Size</name><displayName>File Size</displayName><defaultValue>0B</defaultValue><required>true</required><sensitive>false</sensitive></property></properties>
#| <dynamicProperties><dynamicProperty><name>attribute</name><value>value</value><description>Adds an attribute</description></dynamicProperty></dynamicProperties>
#| <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship></relationships>
#| <writesAttributes><writesAttribute><name>mime.type</name></writesAttribute></writesAttributes><inputRequirement>INPUT_FORBIDDEN</inputRequirement></extension>
#|<extension><name>org.apache.nifi.processors.attributes.UpdateAttribute</name><type>PROCESSOR</type><description>Updates attributes</description>
#| <properties><property><name>Delete Attributes Expression</name><displayName>Delete Attributes Expression</displayName><required>false</required><sensitive>false</sensitive></property></properties>
#| <dynamicProperties><dynamicProperty><name>attribute</name><value>value</value><description>Sets an attribute</description></dynamicProperty></dynamicProperties>
#| <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship></relationships>
#| <inputRequirement>INPUT_REQUIRED</inputRequirement></extension>
#|<extension><name>org.apache.nifi.processors.standard.PutDatabaseRecord</name><type>PROCESSOR</type><description>Writes records</description>
#| <properties>
#|  <property><name>put-db-record-table-name</name><displayName>Table Name</displayName><required>true</required><sensitive>false</sensitive><expressionLanguageScope>FLOWFILE_ATTRIBUTES</expressionLanguageScope></property>
#|  <property><name>put-db-record-catalog-name</name><displayName>Catalog Name</displayName><required>false</required><sensitive>false</sensitive></property>
#|  <property><name>put-db-record-dcbp-service</name><displayName>Database Connection Pooling Service</displayName><required>true</required><sensitive>false</sensitive><controllerServiceDefinition><className>org.apache.nifi.dbcp.DBCPService</className></controllerServiceDefinition></property>
#|  <property><name>put-db-record-record-reader</name><displayName>Record Reader</displayName><required>true</required><sensitive>false</sensitive><controllerServiceDefinition><className>org.apache.nifi.serialization.RecordReaderFactory</className></controllerServiceDefinition></property>
#| </properties>
#| <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship>
#|  <relationship><name>failure</name><description>bad</description><autoTerminated>false</autoTerminated></relationship>
#|  <relationship><name>retry</name><description>again</description><autoTerminated>false</autoTerminated></relationship></relationships>
#| <writesAttributes><writesAttribute><name>putdatabaserecord.error</name></writesAttribute></writesAttributes><inputRequirement>INPUT_REQUIRED</inputRequirement></extension>
#|</extensions></extensionManifest>"""
#|
#|
#|def lineage_flow():
#|    """Metadata lookup -> UpdateAttribute -> PutDatabaseRecord with one misnamed and one never-set attribute."""
#|    flow = metadata_flow()
#|    std = {"group": "org.apache.nifi", "artifact": "nifi-standard-nar", "version": "1.27.0"}
#|    flow["rootGroup"]["processors"] += [
#|        proc("l-gen", "Poll landing", "org.apache.nifi.processors.standard.GenerateFlowFile", {"File Size": "0B"}, bundle=std),
#|        proc("l-meta", "Lookup file metadata", "com.acme.meta.MetadataLookup", {"Object Key": "${filename}", "metadata-db": DBCP_INSTANCE},
#|             bundle={"group": "com.acme", "artifact": "acme-meta-nar", "version": "2.0.0"}, auto=["not found", "failure"]),
#|        proc("l-ua", "Set target", "org.apache.nifi.processors.attributes.UpdateAttribute",
#|             {"target.table": "${tableName}", "load.mode": "${mode:isEmpty():ifElse('full', ${mode})}"},
#|             bundle=dict(std, artifact="nifi-update-attribute-nar")),
#|        proc("l-put", "Load table", "org.apache.nifi.processors.standard.PutDatabaseRecord",
#|             {"put-db-record-table-name": "${target.table}", "put-db-record-catalog-name": "${target_catalog}",
#|              "put-db-record-dcbp-service": DBCP_INSTANCE, "put-db-record-record-reader": "instance-reader-1"},
#|             bundle=std, auto=["success", "failure", "retry"]),
#|    ]
#|    flow["rootGroup"]["connections"] += [conn("l1", "l-gen", "PROCESSOR", "l-meta", "PROCESSOR", ["success"]),
#|                                         conn("l2", "l-meta", "PROCESSOR", "l-ua", "PROCESSOR", ["success"]),
#|                                         conn("l3", "l-ua", "PROCESSOR", "l-put", "PROCESSOR", ["success"])]
#|    return flow
#|
#|
#|class FakeNiFi:
#|    """A NiFi REST API stand-in (login, provenance query lifecycle, event details, bulletins, about) built from the
#|    documented request / response shapes. Runtime ids are the fixture's instance ids (inst-<id>)."""
#|
#|    EVENTS = [
#|        {"id": "11", "eventId": 11, "eventTime": "09/26/2026 10:15:01.100 UTC", "eventType": "RECEIVE", "flowFileUuid": "u-1",
#|         "filename": "orders_0926.json", "componentId": "inst-p-listen", "componentName": "Receive orders API",
#|         "componentType": "ListenHTTP", "transitUri": "http://0.0.0.0:8081/orders", "childUuids": [], "details": None},
#|        {"id": "12", "eventId": 12, "eventTime": "09/26/2026 10:15:01.300 UTC", "eventType": "ATTRIBUTES_MODIFIED",
#|         "flowFileUuid": "u-1", "filename": "orders_0926.json", "componentId": "inst-p-extract", "componentName": "Extract fields",
#|         "componentType": "EvaluateJsonPath", "childUuids": []},
#|        {"id": "13", "eventId": 13, "eventTime": "09/26/2026 10:15:02.000 UTC", "eventType": "ROUTE", "flowFileUuid": "u-1",
#|         "filename": "orders_0926.json", "componentId": "inst-p-validate", "componentName": "Validate order",
#|         "componentType": "ValidateOrderJson", "relationship": "invalid", "childUuids": []},
#|        {"id": "14", "eventId": 14, "eventTime": "09/26/2026 10:15:02.200 UTC", "eventType": "DROP", "flowFileUuid": "u-1",
#|         "filename": "orders_0926.json", "componentId": "inst-p-rejects", "componentName": "Write rejects",
#|         "componentType": "PutFile", "details": "Auto-Terminated by failure Relationship", "childUuids": []},
#|        {"id": "21", "eventId": 21, "eventTime": "09/26/2026 11:00:00.000 UTC", "eventType": "RECEIVE", "flowFileUuid": "u-2",
#|         "filename": "late.json", "componentId": "inst-p-listen", "componentName": "Receive orders API", "componentType": "ListenHTTP",
#|         "childUuids": []},
#|        {"id": "22", "eventId": 22, "eventTime": "09/26/2026 12:00:00.000 UTC", "eventType": "DROP", "flowFileUuid": "u-2",
#|         "filename": "late.json", "componentId": "inst-p-audit", "componentName": "Write audit row", "componentType": "PutDatabaseRecord",
#|         "details": "FlowFile Expired", "childUuids": []},
#|    ]
#|    ATTRS = {"14": [{"name": "validation.status", "value": "INVALID", "previousValue": None},
#|                    {"name": "validation.error", "value": "vendor missing", "previousValue": None},
#|                    {"name": "api.token", "value": "tok-SECRET-9", "previousValue": "tok-SECRET-9"},
#|                    {"name": "vendor", "value": "", "previousValue": ""}]}
#|
#|    def __init__(self, user="admin", password="pw123456789"):
#|        import http.server
#|        import threading
#|        import urllib.parse
#|        fake = self
#|        self.queries, self.deleted, self.calls = {}, [], []
#|
#|        class Handler(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def _send(self, code, obj=None, text=None):
#|                body = (text if text is not None else json.dumps(obj)).encode()
#|                self.send_response(code)
#|                self.send_header("Content-Type", "text/plain" if text is not None else "application/json")
#|                self.send_header("Content-Length", str(len(body)))
#|                self.end_headers()
#|                self.wfile.write(body)
#|
#|            def _authed(self):
#|                want = "Bearer reg-tok" if self.path.startswith("/nifi-registry-api/") else "Bearer tok-123"
#|                return self.headers.get("Authorization") == want
#|
#|            def do_POST(self):
#|                n = int(self.headers.get("Content-Length") or 0)
#|                raw = self.rfile.read(n).decode()
#|                fake.calls.append(("POST", self.path))
#|                if self.path == "/nifi-registry-api/access/token/login":
#|                    ok = self.headers.get("Authorization") == "Basic " + __import__("base64").b64encode(f"{user}:{password}".encode()).decode()
#|                    return self._send(201, text="reg-tok") if ok else self._send(401, text="bad")
#|                if self.path == "/nifi-api/access/token":
#|                    form = dict(urllib.parse.parse_qsl(raw))
#|                    return self._send(201, text="tok-123") if form == {"username": user, "password": password} else self._send(401, text="bad")
#|                if not self._authed():
#|                    return self._send(401, text="unauthorized")
#|                if self.path == "/nifi-api/provenance":
#|                    terms = json.loads(raw)["provenance"]["request"]["searchTerms"]
#|                    qid = f"q{len(fake.queries) + 1}"
#|                    fake.queries[qid] = {k: v["value"] for k, v in terms.items()}
#|                    return self._send(201, {"provenance": {"id": qid, "finished": False}})
#|                self._send(404, text="nope")
#|
#|            def do_GET(self):
#|                fake.calls.append(("GET", self.path))
#|                if not self._authed():
#|                    return self._send(401, text="unauthorized")
#|                if self.path.startswith("/nifi-api/provenance/"):
#|                    terms = fake.queries[self.path.rsplit("/", 1)[1]]
#|                    key = {"Filename": "filename", "FlowFileUUID": "flowFileUuid", "ProcessorID": "componentId"}
#|                    evs = [e for e in fake.EVENTS if all(e.get(key[k]) == v for k, v in terms.items())]
#|                    return self._send(200, {"provenance": {"finished": True, "results": {"provenanceEvents": evs}}})
#|                if self.path.startswith("/nifi-api/provenance-events/"):
#|                    eid = self.path.rsplit("/", 1)[1]
#|                    ev = dict(next(e for e in fake.EVENTS if e["id"] == eid), attributes=fake.ATTRS.get(eid, []))
#|                    return self._send(200, {"provenanceEvent": ev})
#|                if self.path.startswith("/nifi-api/flow/bulletin-board"):
#|                    return self._send(200, {"bulletinBoard": {"bulletins": [{"bulletin": {
#|                        "level": "ERROR", "sourceId": "inst-p-audit", "sourceName": "Write audit row", "timestamp": "10:15:02 UTC",
#|                        "message": "Failed to put Records to database: Table file_audit not found"}}]}})
#|                if self.path == "/nifi-api/versions/process-groups/inst-pg":
#|                    return self._send(200, {"versionControlInformation": {"groupId": "inst-pg", "flowName": "vendor-json", "version": 3,
#|                                                                          "state": "STALE", "stateExplanation": "A newer version (4) is available"}})
#|                if self.path == "/nifi-registry-api/buckets/b1/flows/f1/versions":
#|                    return self._send(200, [{"version": 3, "timestamp": 1789900000000, "author": "bob", "comments": "add order validation"},
#|                                            {"version": 4, "timestamp": 1790000000000, "author": "alice", "comments": "switch vendor to API v2"}])
#|                if self.path == "/nifi-api/flow/about":
#|                    return self._send(200, {"about": {"title": "NiFi", "version": "1.27.0"}})
#|                if self.path.startswith("/nifi-api/flow/process-groups/root/status"):
#|                    proc = lambda pid, name, typ, st: {"processorStatusSnapshot": {"id": pid, "name": name, "type": typ, "runStatus": st,
#|                                                                                    "flowFilesIn": 0}}
#|                    conn = lambda cid, s, sn, d, dn, n, pct: {"connectionStatusSnapshot": {
#|                        "id": cid, "sourceId": s, "sourceName": sn, "destinationId": d, "destinationName": dn,
#|                        "queuedCount": n, "queued": f"{n} (1 MB)", "percentUseCount": pct, "percentUseBytes": "1"}}
#|                    vendor = {"name": "Vendor JSON Ingestion",
#|                              "processorStatusSnapshots": [proc("inst-p-validate", "Validate order", "ValidateOrderJson", "Running"),
#|                                                           proc("inst-p-rejects", "Write rejects", "PutFile", "Stopped")],
#|                              "connectionStatusSnapshots": [conn("c2", "inst-p-extract", "Extract fields", "inst-p-validate", "Validate order",
#|                                                                 "10,000", "100"),
#|                                                            conn("c4", "inst-p-validate", "Validate order", "inst-p-rejects", "Write rejects",
#|                                                                 "5", "0")]}
#|                    root = {"name": "NiFi Flow",
#|                            "processorStatusSnapshots": [proc("inst-p-archive", "Archive order", "PutDatabaseRecord", "Invalid"),
#|                                                         proc("inst-p-audit", "Write audit row", "PutDatabaseRecord", "Running")],
#|                            "connectionStatusSnapshots": [conn("r5", "inst-p-enrich", "Enrich via python", "inst-p-archive", "Archive order",
#|                                                               "0", "0")],
#|                            "processGroupStatusSnapshots": [{"processGroupStatusSnapshot": vendor}]}
#|                    return self._send(200, {"processGroupStatus": {"aggregateSnapshot": root}})
#|                if self.path == "/nifi-api/processors/inst-p-archive":
#|                    return self._send(200, {"component": {"id": "inst-p-archive", "validationErrors": [
#|                        "'Table Name' validated against 'order_archive' is invalid because table does not exist"]}})
#|                if self.path.startswith("/nifi-api/flow/process-groups/root/controller-services"):
#|                    return self._send(200, {"controllerServices": [
#|                        {"component": {"id": "instance-reader-1", "name": "AuditJsonReader", "state": "ENABLED"}},
#|                        {"component": {"id": "instance-writer-unused", "name": "UnusedWriter", "state": "DISABLED"}}]})
#|                if self.path == "/nifi-api/system-diagnostics":
#|                    return self._send(200, {"systemDiagnostics": {"aggregateSnapshot": {
#|                        "heapUtilization": "91.0%", "contentRepositoryStorageUsage": [
#|                            {"identifier": "default", "utilization": "96.0%", "usedSpace": "96 GB", "totalSpace": "100 GB"}],
#|                        "flowFileRepositoryStorageUsage": {"utilization": "20.0%"}}}})
#|                if self.path == "/nifi-api/flow/cluster/summary":
#|                    return self._send(200, {"clusterSummary": {"clustered": True, "connectedNodeCount": 2, "totalNodeCount": 3}})
#|                self._send(404, text="nope")
#|
#|            def do_DELETE(self):
#|                fake.deleted.append(self.path)
#|                self._send(200, {})
#|
#|        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
#|        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/nifi-api"
#|        threading.Thread(target=self.server.serve_forever, daemon=True).start()
#|
#|    def stop(self):
#|        self.server.shutdown()
#|        self.server.server_close()
#|
#|
#|def make_nar(path, manifest_xml=None, group="com.acme", artifact="acme-nifi-nar", service_classes=()):
#|    with zipfile.ZipFile(path, "w") as z:
#|        z.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nNar-Group: {group}\nNar-Id: {artifact}\nNar-Version: 1.0.0\n")
#|        if manifest_xml:
#|            z.writestr("META-INF/docs/extension-manifest.xml", manifest_xml)
#|        if service_classes:
#|            jar = io.BytesIO()
#|            with zipfile.ZipFile(jar, "w") as j:
#|                j.writestr("META-INF/services/org.apache.nifi.processor.Processor", "\n".join(service_classes) + "\n")
#|            z.writestr(f"META-INF/bundled-dependencies/{artifact}-1.0.0.jar", jar.getvalue())
#|
#|
#|def make_db(path):
#|    db = sqlite3.connect(path)
#|    db.executescript("""
#|        CREATE TABLE file_audit(id INTEGER PRIMARY KEY, order_id TEXT NOT NULL, vendor TEXT, status TEXT,
#|                                received_at TEXT NOT NULL, user_email TEXT);
#|        CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, region TEXT);
#|        CREATE TABLE orders(id TEXT PRIMARY KEY, cust_id INTEGER REFERENCES customers(id), total REAL);
#|        CREATE TABLE file_calls(id INTEGER PRIMARY KEY, source_system TEXT, status TEXT, file_name TEXT);
#|        CREATE TABLE unrelated(x INTEGER);
#|        CREATE INDEX ix_audit_order ON file_audit(order_id);
#|        INSERT INTO file_calls(source_system, status, file_name) VALUES ('vendorA','LOADED','a.json'), ('vendorA','FAILED','b.json'),
#|                                                                     ('vendorB','LOADED','c.json');
#|        INSERT INTO file_audit(order_id, vendor, status, received_at, user_email) VALUES ('o1','vendorA','OK','2026-01-01','x@y.com');
#|    """)
#|    db.commit()
#|    db.close()
#|
#|
#|API_TOKEN = "abcdefghijklmnop1234"
#|METADATA_SQL = """
#|    CREATE TABLE OBJ_DEFINITION(OBJ_ID INTEGER PRIMARY KEY, FILE_NAME TEXT, TABLE_NAME TEXT, SOURCE_SYSTEM TEXT, DELIMITER TEXT, ACTIVE_FLAG TEXT);
#|    CREATE TABLE OBJ_STRUCTURE(STRUCT_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER REFERENCES OBJ_DEFINITION(OBJ_ID), COL_NAME TEXT,
#|                               DATA_TYPE TEXT, COL_SEQ INTEGER, COL_LENGTH INTEGER, MANDATORY_FLAG TEXT, JSON_PATH TEXT);
#|    CREATE TABLE SOURCE_FEED_CONFIG(FEED_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, FEED_NAME TEXT, SFTP_HOST TEXT, SFTP_USER TEXT,
#|                                    SFTP_PASSWORD TEXT, REMOTE_DIR TEXT);
#|    CREATE TABLE NIFI_JSON_API_CONFIG(API_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, API_NAME TEXT, API_URL TEXT, AUTH_HEADER TEXT,
#|                                      JSON_ROOT_PATH TEXT, REQUEST_TEMPLATE TEXT);
#|    CREATE TABLE stg_sales(order_no INTEGER NOT NULL, cust_name VARCHAR(20), amount DECIMAL(10,2), order_dt DATE, region VARCHAR(10),
#|                           load_ts TEXT NOT NULL);
#|    CREATE TABLE stg_customers(cust_id INTEGER PRIMARY KEY, name VARCHAR(100), email VARCHAR(200));
#|    CREATE TABLE stg_orders(order_id INTEGER NOT NULL, customer_name VARCHAR(100), amount DECIMAL(10,2));
#|    CREATE TABLE FILE_LOAD_AUDIT(AUDIT_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, FILE_NAME TEXT, LOAD_STATUS TEXT, LOAD_TS TEXT,
#|                                 ERROR_MSG TEXT, ROW_COUNT INTEGER);
#|    INSERT INTO FILE_LOAD_AUDIT VALUES (1, 1, '/landing/pos/SALES_20260925.csv', 'SUCCESS', '2026-09-25 02:10:00', NULL, 1200),
#|                                       (2, 1, '/landing/pos/SALES_20260926.csv', 'FAILED', '2026-09-26 02:14:00',
#|                                        'Column count mismatch at line 12: expected 5, found 6', 0);
#|    INSERT INTO OBJ_DEFINITION VALUES (1, 'SALES_YYYYMMDD.csv', 'stg_sales', 'POS', ',', 'Y'),
#|                                      (2, 'customers_*.json', 'stg_customers', 'CRM', NULL, 'Y'),
#|                                      (3, 'returns.csv', 'stg_returns', 'POS', ',', 'Y'),
#|                                      (4, 'orders_api', 'stg_orders', 'SHOP', NULL, 'Y');
#|    INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES
#|        (1, 'ORDER_NO', 'INTEGER', 1, NULL, 'Y'), (1, 'CUST_NAME', 'VARCHAR', 2, 50, 'N'), (1, 'AMOUNT', 'VARCHAR', 3, 20, 'N'),
#|        (1, 'ORDER_DT', 'DATE', 4, NULL, 'N'), (1, 'REGION', 'VARCHAR', 5, 10, 'N'),
#|        (2, 'CUST_ID', 'INT', 1, NULL, 'Y'), (2, 'NAME', 'VARCHAR', 2, 100, 'N'), (2, 'EMAIL', 'VARCHAR', 3, 200, 'N'),
#|        (3, 'RET_ID', 'INT', 1, NULL, 'Y');
#|    INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG, JSON_PATH) VALUES
#|        (4, 'ORDER_ID', 'INT', 1, NULL, 'Y', '$.orders[*].id'), (4, 'CUSTOMER_NAME', 'VARCHAR', 2, 100, 'N', '$.orders[*].customer.name'),
#|        (4, 'AMOUNT', 'DECIMAL', 3, NULL, 'N', '$.orders[*].amount');
#|    INSERT INTO SOURCE_FEED_CONFIG VALUES (10, 1, 'pos_sales_feed', 'sftp.pos.acme.com', 'nifi', 'Sup3rS3cret!', '/outbound/sales');
#|    INSERT INTO NIFI_JSON_API_CONFIG VALUES (20, 2, 'crm_customers_api', 'https://crm.acme.com/api/v2/customers',
#|                                             'Bearer abcdefghijklmnop1234', '$.data', '{"client": "nifi", "password": "hunter2"}'),
#|                                            (21, 4, 'orders_api', 'https://shop.acme.com/api/orders', 'Bearer qrstuvwxyz987654321', '$.orders', NULL);
#|"""
#|
#|
#|METADATA_BASE = """package com.acme.meta.base;
#|
#|import org.apache.nifi.components.PropertyDescriptor;
#|import org.apache.nifi.dbcp.DBCPService;
#|import org.apache.nifi.processor.AbstractProcessor;
#|import org.apache.nifi.processor.Relationship;
#|
#|/** Shared base of all ACME metadata processors. */
#|public abstract class AbstractMetadataProcessor extends AbstractProcessor {
#|
#|    public static final PropertyDescriptor METADATA_DB = new PropertyDescriptor.Builder()
#|            .name(MetaConstants.PROP_METADATA_DB)
#|            .displayName("Metadata DB")
#|            .description("Connection pool for the OBJ_* config tables")
#|            .identifiesControllerService(DBCPService.class)
#|            .required(true)
#|            .build();
#|
#|    public static final Relationship REL_FAILURE = new Relationship.Builder()
#|            .name("failure").description("Lookup failed").build();
#|}
#|"""
#|METADATA_CONSTANTS = """package com.acme.meta.base;
#|
#|public interface MetaConstants {
#|    String PROP_METADATA_DB = "metadata-db";
#|    String ATTR_TABLE = "table_name";
#|    String ATTR_STRUCTURE = "structure.json";
#|}
#|"""
#|METADATA_PROCESSOR = """package com.acme.meta;
#|
#|import com.acme.meta.base.AbstractMetadataProcessor;
#|import com.acme.meta.base.MetaConstants;
#|import org.apache.nifi.annotation.behavior.WritesAttribute;
#|import org.apache.nifi.annotation.behavior.WritesAttributes;
#|import org.apache.nifi.annotation.documentation.CapabilityDescription;
#|import org.apache.nifi.annotation.documentation.Tags;
#|import org.apache.nifi.components.AllowableValue;
#|import org.apache.nifi.components.PropertyDescriptor;
#|import org.apache.nifi.flowfile.attributes.CoreAttributes;
#|import org.apache.nifi.processor.Relationship;
#|import org.apache.nifi.processor.exception.ProcessException;
#|
#|@Tags({"acme", "metadata"})
#|@CapabilityDescription("Looks up the object definition; structure and feed config for the incoming file and writes them as attributes.")
#|@WritesAttributes({
#|        @WritesAttribute(attribute = "table_name", description = "Target table from OBJ_DEFINITION"),
#|        @WritesAttribute(attribute = "structure.json", description = "Columns from OBJ_STRUCTURE")})
#|public class MetadataLookup extends AbstractMetadataProcessor {
#|
#|    private static final String REL_NOT_FOUND_NAME = "not found";
#|    static final AllowableValue BY_FILE = new AllowableValue("by-file", "By file name", "Match FILE_NAME patterns");
#|    static final AllowableValue BY_FEED = new AllowableValue("by-feed", "By feed name", "Match SOURCE_FEED_CONFIG.FEED_NAME");
#|
#|    public static final PropertyDescriptor OBJECT_KEY = new PropertyDescriptor.Builder()
#|            .name("Object Key").description("File name or feed name to look up").required(true)
#|            .expressionLanguageSupported(ExpressionLanguageScope.FLOWFILE_ATTRIBUTES).build();
#|
#|    public static final PropertyDescriptor METADATA_SERVICE = new PropertyDescriptor.Builder()
#|            .name("metadata-service").displayName("Metadata Service").identifiesControllerService(MetadataService.class).build();
#|
#|    public static final PropertyDescriptor LOOKUP_MODE = new PropertyDescriptor.Builder()
#|            .name("lookup-mode").displayName("Lookup Mode").allowableValues(BY_FILE, BY_FEED)
#|            .defaultValue(BY_FILE.getValue()).build();
#|
#|    public static final Relationship REL_SUCCESS = new Relationship.Builder().name("success").description("found").build();
#|    public static final Relationship REL_NOT_FOUND = new Relationship.Builder().name(REL_NOT_FOUND_NAME).description("no definition").build();
#|
#|    private final MetadataDao dao = new MetadataDao();
#|
#|    @Override
#|    public void onTrigger(ProcessContext context, ProcessSession session) {
#|        FlowFile flowFile = session.get();
#|        String fileName = flowFile.getAttribute(CoreAttributes.FILENAME.key());
#|        Definition def = dao.load(fileName);
#|        if (def == null) {
#|            getLogger().error("No OBJ_DEFINITION row for file {}", new Object[]{fileName});
#|            session.transfer(flowFile, REL_NOT_FOUND);
#|            return;
#|        }
#|        if (!def.matches()) {
#|            throw new ProcessException("Structure mismatch for " + fileName + " against OBJ_STRUCTURE");
#|        }
#|        Map<String, String> attrs = new HashMap<>();
#|        attrs.put(MetaConstants.ATTR_TABLE, def.getTable());
#|        attrs.put(MetaConstants.ATTR_STRUCTURE, def.getColumnsJson());
#|        attrs.put("delimiter", def.getDelimiter());
#|        flowFile = session.putAllAttributes(flowFile, attrs);
#|        session.transfer(flowFile, REL_SUCCESS);
#|    }
#|}
#|"""
#|METADATA_SERVICE_API = """package com.acme.meta;
#|
#|import org.apache.nifi.controller.ControllerService;
#|
#|public interface MetadataService extends ControllerService {
#|    Definition find(String fileName);
#|}
#|"""
#|METADATA_SERVICE_IMPL = """package com.acme.meta;
#|
#|import org.apache.nifi.annotation.documentation.CapabilityDescription;
#|import org.apache.nifi.controller.AbstractControllerService;
#|
#|@CapabilityDescription("Caches OBJ_DEFINITION rows")
#|public class CachingMetadataService extends AbstractControllerService implements MetadataService {
#|}
#|"""
#|MOCK_TEST_PROCESSOR = """package com.acme.meta;
#|
#|import org.apache.nifi.processor.AbstractProcessor;
#|
#|public class MockUpstream extends AbstractProcessor {
#|}
#|"""
#|UNREGISTERED_PROCESSOR = """package com.acme.meta;
#|
#|import com.acme.meta.base.AbstractMetadataProcessor;
#|
#|public class LegacyMetadataLookup extends AbstractMetadataProcessor {
#|}
#|"""
#|PROCESSORS_POM = """<project><parent><groupId>com.acme</groupId><artifactId>acme-meta</artifactId><version>2.0.0</version></parent>
#|<artifactId>acme-meta-processors</artifactId><packaging>jar</packaging>
#|<dependencies><dependency><groupId>org.apache.nifi</groupId><artifactId>nifi-api</artifactId></dependency></dependencies></project>"""
#|NAR_POM = """<project><parent><groupId>com.acme</groupId><artifactId>acme-meta</artifactId><version>2.0.0</version></parent>
#|<artifactId>acme-meta-nar</artifactId><packaging>nar</packaging>
#|<dependencies><dependency><groupId>com.acme</groupId><artifactId>acme-meta-processors</artifactId><version>2.0.0</version></dependency></dependencies></project>"""
#|
#|
#|def class_file(name, strings):
#|    """A minimal valid .class file whose constant pool holds `strings` as string literals (no JDK needed)."""
#|    import struct
#|    pool, count = b"", 1
#|
#|    def utf8(s):
#|        b = s.encode("utf-8")
#|        return b"\x01" + struct.pack(">H", len(b)) + b
#|
#|    pool += utf8(name.replace(".", "/")) + b"\x07" + struct.pack(">H", 1)          # 1 utf8, 2 class
#|    pool += utf8("java/lang/Object") + b"\x07" + struct.pack(">H", 3)              # 3 utf8, 4 class
#|    count = 5
#|    for s in strings:
#|        pool += utf8(s) + b"\x08" + struct.pack(">H", count)                         # utf8, then String -> it
#|        count += 2
#|    return (b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 52, count) + pool
#|            + struct.pack(">HHHHHHH", 0x21, 2, 4, 0, 0, 0, 0))
#|
#|
#|def make_meta_nar(path, missing_attribute="delimiter"):
#|    """Deployed build of acme-meta-nar 2.0.0 - built from an older commit: no `delimiter` attribute yet."""
#|    lookup = ["Object Key", "File name or feed name to look up", "metadata-service", "Metadata Service", "lookup-mode", "Lookup Mode", "by-file", "by-feed", "success",
#|              "not found", "No OBJ_DEFINITION row for file {}", "Structure mismatch for {} against OBJ_STRUCTURE",
#|              "table_name", "structure.json", "delimiter"]
#|    lookup = [s for s in lookup if s != missing_attribute]
#|    jar = io.BytesIO()
#|    with zipfile.ZipFile(jar, "w") as j:
#|        j.writestr("META-INF/services/org.apache.nifi.processor.Processor", "com.acme.meta.MetadataLookup\n")
#|        j.writestr("com/acme/meta/MetadataLookup.class", class_file("com.acme.meta.MetadataLookup", lookup))
#|        j.writestr("com/acme/meta/MetadataDao.class", class_file("com.acme.meta.MetadataDao", [
#|            "OBJ_DEFINITION", "SOURCE_FEED_CONFIG", "SELECT * FROM {} d WHERE d.FILE_NAME = ?",
#|            "SELECT s.COL_NAME FROM OBJ_STRUCTURE s WHERE s.OBJ_ID = ?"]))
#|        j.writestr("com/acme/meta/base/AbstractMetadataProcessor.class",
#|                   class_file("com.acme.meta.base.AbstractMetadataProcessor", ["metadata-db", "Metadata DB", "failure"]))
#|    with zipfile.ZipFile(path, "w") as z:
#|        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nNar-Group: com.acme\nNar-Id: acme-meta-nar\nNar-Version: 2.0.0\n")
#|        z.writestr("META-INF/bundled-dependencies/acme-meta-processors-2.0.0.jar", jar.getvalue())
#|        z.writestr("META-INF/bundled-dependencies/commons-lang3-3.12.0.jar", b"not really a jar")
#|METADATA_DAO = """package com.acme.meta;
#|
#|class MetadataDao {
#|    private static final String DEF_TABLE = "OBJ_DEFINITION";
#|    private static final String STRUCT_TABLE = "obj_structure";
#|    private static final String FEED_TABLE = "SOURCE_FEED_CONFIG";
#|
#|    void load(String key) {
#|        String sql = "SELECT * FROM " + DEF_TABLE + " d WHERE d.FILE_NAME = ?";
#|    }
#|}
#|"""
#|
#|
#|def make_metadata_repo(root):
#|    mod = Path(root) / "nifi-meta-processors"
#|    src = mod / "src" / "main" / "java" / "com" / "acme" / "meta"
#|    (src / "base").mkdir(parents=True, exist_ok=True)
#|    (src / "MetadataLookup.java").write_text(METADATA_PROCESSOR, encoding="utf-8")
#|    (src / "LegacyMetadataLookup.java").write_text(UNREGISTERED_PROCESSOR, encoding="utf-8")
#|    (src / "MetadataDao.java").write_text(METADATA_DAO, encoding="utf-8")
#|    (src / "MetadataService.java").write_text(METADATA_SERVICE_API, encoding="utf-8")
#|    (src / "CachingMetadataService.java").write_text(METADATA_SERVICE_IMPL, encoding="utf-8")
#|    test_src = mod / "src" / "test" / "java" / "com" / "acme" / "meta"
#|    test_src.mkdir(parents=True, exist_ok=True)
#|    (test_src / "MockUpstream.java").write_text(MOCK_TEST_PROCESSOR, encoding="utf-8")
#|    (src / "base" / "AbstractMetadataProcessor.java").write_text(METADATA_BASE, encoding="utf-8")
#|    (src / "base" / "MetaConstants.java").write_text(METADATA_CONSTANTS, encoding="utf-8")
#|    svc = mod / "src" / "main" / "resources" / "META-INF" / "services"
#|    svc.mkdir(parents=True, exist_ok=True)
#|    (svc / "org.apache.nifi.processor.Processor").write_text("com.acme.meta.MetadataLookup\n", encoding="utf-8")
#|    (mod / "pom.xml").write_text(PROCESSORS_POM, encoding="utf-8")
#|    (Path(root) / "nifi-meta-nar").mkdir(parents=True, exist_ok=True)
#|    (Path(root) / "nifi-meta-nar" / "pom.xml").write_text(NAR_POM, encoding="utf-8")
#|    return Path(root)
#|
#|
#|def metadata_flow():
#|    """The nested flow plus the two processors a metadata-driven flow has: a lookup of the config tables and a
#|    processor configured with a feed name."""
#|    flow = nested_flow()
#|    flow["rootGroup"]["processors"] += [
#|        proc("p-meta", "Read object metadata", "org.apache.nifi.processors.standard.ExecuteSQL",
#|             {"Database Connection Pooling Service": DBCP_INSTANCE,
#|              "SQL select query": "SELECT s.COL_NAME, s.DATA_TYPE FROM OBJ_DEFINITION d JOIN OBJ_STRUCTURE s ON s.OBJ_ID = d.OBJ_ID "
#|                                  "WHERE d.FILE_NAME = '${filename}'"}, auto=["failure"]),
#|        proc("p-feed", "Tag POS feed", "org.apache.nifi.processors.attributes.UpdateAttribute", {"feed.name": "pos_sales_feed"},
#|             bundle={"group": "org.apache.nifi", "artifact": "nifi-update-attribute-nar", "version": "1.27.0"}),
#|        proc("p-lookup-meta", "Metadata lookup", "com.acme.meta.MetadataLookup", {"Object Key": "${filename}"},
#|             bundle={"group": "com.acme", "artifact": "acme-meta-nar", "version": "1.9.0"}),
#|    ]
#|    flow["rootGroup"]["connections"] += [conn("r7", "p-feed", "PROCESSOR", "p-meta", "PROCESSOR", ["success"]),
#|                                         conn("r8", "p-meta", "PROCESSOR", "p-lookup-meta", "PROCESSOR", ["success"])]
#|    return flow
#|
#|
#|def make_env(tmp, flow=None, with_db=True, with_metadata=False):
#|    """Create a full environment under tmp and return the config path."""
#|    tmp = Path(tmp)
#|    (tmp / "nars").mkdir(parents=True, exist_ok=True)
#|    make_nar(tmp / "nars" / "acme-nifi-nar-1.0.0.nar", ACME_MANIFEST)
#|    make_nar(tmp / "nars" / "legacy-nar.nar", None, group="com.legacy", artifact="legacy-nar", service_classes=["com.legacy.OldProcessor"])
#|    flow_path = tmp / "flow.json.gz"
#|    with gzip.open(flow_path, "wt", encoding="utf-8") as f:
#|        json.dump(flow or nested_flow(), f)
#|    dbs = ""
#|    if with_db:
#|        make_db(tmp / "meta.db")
#|        if with_metadata:
#|            db = sqlite3.connect(tmp / "meta.db")
#|            db.executescript(METADATA_SQL)
#|            db.commit()
#|            db.close()
#|        dbs = f"""
#|[[databases]]
#|name = "metadata"
#|kind = "sqlite"
#|database = "{(tmp / 'meta.db').as_posix()}"
#|match_jdbc = "dbhost.acme.com:3306/meta"
#|include_tables = ["file_%"]
#|profile_tables = ["file_calls"]
#|sample_rows = 1
#|"""
#|        if with_metadata:
#|            dbs += '\n[audit]\ndb = "metadata"\n\n[metadata]\ndb = "metadata"\n'
#|    repos = [(FIXTURES / "repo").as_posix()]
#|    if with_metadata:
#|        repos.append(make_metadata_repo(tmp / "meta-repo").as_posix())
#|        make_meta_nar(tmp / "nars" / "acme-meta-nar-2.0.0.nar")
#|    cfg = tmp / "nifikb.toml"
#|    cfg.write_text(f"""
#|[nifi]
#|flow_file = "{flow_path.as_posix()}"
#|extra_nar_dirs = ["{(tmp / 'nars').as_posix()}"]
#|
#|[output]
#|dir = "{(tmp / 'kb').as_posix()}"
#|
#|[code]
#|repos = {json.dumps(repos)}
#|{dbs}""", encoding="utf-8")
#|    return cfg
#@@ FILE tests/test_mariadb.py t 02498f6da29a6d68
#|"""Live MariaDB regression test. Skipped unless NIFIKB_TEST_MARIADB=host:port:admin_user:admin_password is set.
#|
#|Creates a scratch database + a SELECT-only user, runs a full build against it, then drops both."""
#|import os
#|import shutil
#|import sqlite3
#|import tempfile
#|import unittest
#|from pathlib import Path
#|
#|from test_nifikb import run_cli
#|from fixtures_builder import make_env, metadata_flow
#|from nifikb import db as dbmod
#|from nifikb.build import build
#|from nifikb.config import load_config
#|
#|MARIADB = os.environ.get("NIFIKB_TEST_MARIADB")
#|
#|
#|@unittest.skipUnless(MARIADB, "set NIFIKB_TEST_MARIADB=host:port:user:password to run against a live MariaDB")
#|class TestMariaDB(unittest.TestCase):
#|    @classmethod
#|    def setUpClass(cls):
#|        import pymysql
#|        host, port, user, password = MARIADB.split(":", 3)
#|        cls.admin = pymysql.connect(host=host, port=int(port), user=user, password=password, autocommit=True)
#|        with cls.admin.cursor() as cur:
#|            for stmt in [
#|                "DROP DATABASE IF EXISTS nifikb_test", "CREATE DATABASE nifikb_test", "USE nifikb_test",
#|                "CREATE TABLE file_audit(id INT AUTO_INCREMENT PRIMARY KEY, order_id VARCHAR(40) NOT NULL, vendor VARCHAR(40), "
#|                "status VARCHAR(20), received_at DATETIME NOT NULL, user_email VARCHAR(100), KEY ix_order(order_id)) COMMENT='one row per file call'",
#|                "CREATE TABLE customers(id INT PRIMARY KEY, name VARCHAR(80), region VARCHAR(10))",
#|                "CREATE TABLE orders(id VARCHAR(40) PRIMARY KEY, cust_id INT, total DECIMAL(10,2), FOREIGN KEY (cust_id) REFERENCES customers(id))",
#|                "CREATE TABLE file_calls(id INT AUTO_INCREMENT PRIMARY KEY, source_system VARCHAR(20), status ENUM('LOADED','FAILED'), file_name VARCHAR(200))",
#|                "INSERT INTO file_calls(source_system, status, file_name) VALUES ('vendorA','LOADED','a.json'),('vendorA','FAILED','b.json'),('vendorB','LOADED','c.json')",
#|                "INSERT INTO file_audit(order_id, vendor, status, received_at, user_email) VALUES ('o1','vendorA','OK',NOW(),'x@y.com')",
#|                "CREATE TABLE OBJ_DEFINITION(OBJ_ID INT PRIMARY KEY, FILE_NAME VARCHAR(200), TABLE_NAME VARCHAR(100), ACTIVE_FLAG CHAR(1))",
#|                "CREATE TABLE OBJ_STRUCTURE(STRUCT_ID INT AUTO_INCREMENT PRIMARY KEY, OBJ_ID INT NOT NULL, COL_NAME VARCHAR(100), "
#|                "DATA_TYPE VARCHAR(30), COL_SEQ INT, COL_LENGTH INT, MANDATORY_FLAG CHAR(1), FOREIGN KEY (OBJ_ID) REFERENCES OBJ_DEFINITION(OBJ_ID))",
#|                "CREATE TABLE SOURCE_FEED_CONFIG(FEED_ID INT PRIMARY KEY, OBJ_ID INT, FEED_NAME VARCHAR(50), SFTP_HOST VARCHAR(100), "
#|                "SFTP_PASSWORD VARCHAR(100), REMOTE_DIR VARCHAR(200))",
#|                "CREATE TABLE stg_sales(order_no INT NOT NULL, cust_name VARCHAR(20), amount DECIMAL(10,2), order_dt DATE, region VARCHAR(10), "
#|                "load_ts DATETIME NOT NULL)",
#|                "INSERT INTO OBJ_DEFINITION VALUES (1, 'SALES_YYYYMMDD.csv', 'stg_sales', 'Y')",
#|                "INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES "
#|                "(1,'ORDER_NO','INT',1,NULL,'Y'),(1,'CUST_NAME','VARCHAR',2,50,'N'),(1,'AMOUNT','VARCHAR',3,20,'N'),"
#|                "(1,'ORDER_DT','DATE',4,NULL,'N'),(1,'REGION','VARCHAR',5,10,'N')",
#|                "INSERT INTO SOURCE_FEED_CONFIG VALUES (10, 1, 'pos_sales_feed', 'sftp.pos.acme.com', 'Sup3rS3cret!', '/outbound/sales')",
#|                "CREATE USER IF NOT EXISTS 'nifikb_ro'@'%' IDENTIFIED BY 'ro_pass_123'",
#|                "CREATE USER IF NOT EXISTS 'nifikb_ro'@'localhost' IDENTIFIED BY 'ro_pass_123'",
#|                "GRANT SELECT ON nifikb_test.* TO 'nifikb_ro'@'%'",
#|                "GRANT SELECT ON nifikb_test.* TO 'nifikb_ro'@'localhost'",
#|            ]:
#|                cur.execute(stmt)
#|        cls.tmp = tempfile.mkdtemp()
#|        cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_db=False)
#|        with open(cfg_path, "a", encoding="utf-8") as f:
#|            f.write(f'\n[[databases]]\nname = "metadata"\nkind = "mariadb"\nhost = "{host}"\nport = {port}\ndatabase = "nifikb_test"\n'
#|                    f'user = "nifikb_ro"\npassword_env = "NIFIKB_TEST_RO_PASS"\nmatch_jdbc = "dbhost.acme.com:3306/meta"\n'
#|                    f'include_tables = ["file_%"]\nprofile_tables = ["file_calls"]\nsample_rows = 1\n'
#|                    f'\n[metadata]\ndb = "metadata"\n')
#|        os.environ["NIFIKB_TEST_RO_PASS"] = "ro_pass_123"
#|        cls.cfg_path = cfg_path
#|        cls.cfg = load_config(cfg_path)
#|        cls.logs = []
#|        cls.res = build(cls.cfg, log=cls.logs.append)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        with cls.admin.cursor() as cur:
#|            cur.execute("DROP DATABASE IF EXISTS nifikb_test")
#|            cur.execute("DROP USER IF EXISTS 'nifikb_ro'@'%'")
#|            cur.execute("DROP USER IF EXISTS 'nifikb_ro'@'localhost'")
#|        cls.admin.close()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_schema_documented(self):
#|        doc = (self.kb / "db/metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("## nifikb_test.file_audit", doc, "\n".join(self.logs))
#|        self.assertIn("one row per file call", doc)
#|        self.assertIn("| order_id | varchar(40) | N |", doc)
#|        self.assertIn("auto_increment", doc)
#|        self.assertIn("Indexes: PRIMARY(id) unique, ix_order(order_id)", doc)
#|        self.assertIn("FKs: cust_id→customers.id", doc)
#|        self.assertIn("values of `status`: LOADED×2, FAILED×1", doc)
#|        self.assertIn("## nifikb_test.customers", doc)
#|        self.assertNotIn("x@y.com", doc)
#|        self.assertIn("order_archive", doc)
#|
#|    def test_findings(self):
#|        db = sqlite3.connect(self.kb / "kb.sqlite")
#|        rows = dict(db.execute("SELECT kind, message FROM findings WHERE kind IN ('missing-table','field-mismatch','db-unreachable')").fetchall())
#|        db.close()
#|        self.assertIn("missing-table", rows)
#|        self.assertIn("received_at", rows.get("field-mismatch", ""))
#|        self.assertNotIn("db-unreachable", rows)
#|
#|    def test_metadata(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertRegex(doc, r"(?i)definition table: `obj_definition`")
#|        self.assertIn("(foreign key)", doc)
#|        self.assertIn("(shared column name)", doc)
#|        self.assertIn("NOT NULL column(s) of stg_sales not in the structure: load_ts", doc)
#|        self.assertIn("'AMOUNT' is VARCHAR in the structure but decimal(10,2)", doc)
#|        for live in ([], ["--live"]):
#|            rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "--file", "SALES_20260926.csv", *live,
#|                              "ORDER_NO", "CUST_NAME", "AMOUNT", "REGION", "ORDER_DT")
#|            self.assertEqual(rc, 0, out)
#|            self.assertIn("header order differs", out)
#|            self.assertIn("SFTP_PASSWORD=***", out)
#|            self.assertNotIn("Sup3rS3cret!", out)
#|        self.assertFalse(b"Sup3rS3cret!" in (self.kb / "kb.sqlite").read_bytes(), "secret stored in kb.sqlite")
#|
#|    def test_read_only(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT source_system, COUNT(*) n FROM file_calls GROUP BY source_system")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("vendorB", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT user_email FROM file_audit")
#|        self.assertIn("***", out)
#|        conn, _ = dbmod.connect(self.cfg["databases"][0])
#|        try:
#|            with self.assertRaises(Exception):
#|                with conn.cursor() as cur:
#|                    cur.execute("INSERT INTO file_calls(source_system) VALUES ('hack')")
#|        finally:
#|            conn.close()
#|
#|
#|if __name__ == "__main__":
#|    unittest.main()
#@@ FILE tests/test_nifikb.py tc b901703d0966d7b0
#|"""Regression suite for nifikb. Run: python -m unittest discover -s tests -v"""
#|import contextlib
#|import gzip
#|import io
#|import json
#|import os
#|import shutil
#|import sqlite3
#|import sys
#|import tempfile
#|import unittest
#|from pathlib import Path
#|
#|sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#|sys.path.insert(0, str(Path(__file__).resolve().parent))
#|
#|from fixtures_builder import FIXTURES, NESTED_XML, SECRET_VALUES, make_env, nested_flow  # noqa: E402
#|from nifikb import cli, code as codemod, db as dbmod, sqlparse  # noqa: E402
#|from nifikb.analyze import Analysis  # noqa: E402
#|from nifikb.build import build  # noqa: E402
#|from nifikb.catalog import Catalog, read_nar  # noqa: E402
#|from nifikb.code import CodeIndex  # noqa: E402
#|from nifikb.config import load_config  # noqa: E402
#|from nifikb.flow import load_flow  # noqa: E402
#|
#|REAL_NIFI = Path(os.environ.get("NIFIKB_TEST_NIFI_HOME", "D:/Sanjay/nifi-1.27.0"))
#|
#|
#|def run_cli(*argv):
#|    buf = io.StringIO()
#|    with contextlib.redirect_stdout(buf):
#|        rc = cli.main(list(argv))
#|    return rc, buf.getvalue()
#|
#|
#|def all_text(kb):
#|    out = {}
#|    for p in Path(kb).rglob("*.md"):
#|        out[str(p)] = p.read_text(encoding="utf-8")
#|    return out
#|
#|
#|class TestSql(unittest.TestCase):
#|    def test_tables(self):
#|        self.assertEqual(sqlparse.tables("SELECT a FROM x.orders o JOIN customers c ON c.id=o.c LEFT JOIN `vendors` v ON 1=1"),
#|                         ["x.orders", "customers", "vendors"])
#|        self.assertEqual(sqlparse.tables("insert into file_audit (a) values (1)"), ["file_audit"])
#|        self.assertEqual(sqlparse.tables("UPDATE t1 SET a = (SELECT max(b) FROM t2)"), ["t1", "t2"])
#|        self.assertEqual(sqlparse.tables("WITH recent AS (SELECT * FROM calls) SELECT * FROM recent"), ["calls"])
#|        self.assertEqual(sqlparse.tables("DELETE FROM stage_${table.name} WHERE 1=1"), ["stage_${table.name}"])
#|        self.assertEqual(sqlparse.tables("SELECT 'from nowhere' AS x FROM real_table"), ["real_table"])
#|
#|    def test_looks_like_sql(self):
#|        self.assertTrue(sqlparse.looks_like_sql("select id from orders"))
#|        self.assertFalse(sqlparse.looks_like_sql("Select the file to fetch"))
#|        self.assertFalse(sqlparse.looks_like_sql("update"))
#|
#|
#|class TestFlowLoading(unittest.TestCase):
#|    def test_json_xml_parity_on_real_export(self):
#|        j = load_flow(FIXTURES / "local" / "flow.json.gz")
#|        x = load_flow(FIXTURES / "local" / "flow.xml.gz")
#|        self.assertEqual((j.format, x.format), ("flow.json", "flow.xml"))
#|
#|        def sig(flow):
#|            comps = {c["id"]: c for c in flow.components.values()}
#|            nodes = sorted((c["kind"], c["name"], c["type"], json.dumps(c["properties"], sort_keys=True), tuple(c["auto_terminated"]))
#|                           for c in comps.values())
#|            edges = sorted((comps[c["source_id"]]["name"], tuple(c["relationships"]), comps[c["dest_id"]]["name"]) for c in flow.connections)
#|            svcs = sorted((s["name"], s["type"], s["state"]) for s in flow.services.values())
#|            return nodes, edges, svcs, sorted(flow.labels, key=lambda lab: lab["text"]) and len(flow.labels)
#|
#|        self.assertEqual(sig(j), sig(x))
#|        self.assertEqual(len(j.components), 12)  # 9 processors + 3 funnels
#|        self.assertEqual(j.groups[j.root_id]["variables"]["nifi.path"], r"D:\Sanjay\nifi-1.27.0")
#|
#|    def test_nested_xml(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            p = Path(tmp) / "flow.xml.gz"
#|            p.write_bytes(gzip.compress(NESTED_XML.encode()))
#|            flow = load_flow(p)
#|            self.assertEqual(flow.groups["g1"]["path"], "NiFi Flow / File Ingestion")
#|            self.assertEqual(flow.groups["g1"]["parameter_context"], "file-params")
#|            self.assertEqual(flow.groups["g1"]["variables"], {"region": "eu"})
#|            self.assertEqual(flow.components["x-fetch"]["state"], "STOPPED")
#|            self.assertEqual(flow.components["x-fetch"]["concurrent_tasks"], 2)
#|            self.assertNotIn("File Filter", flow.components["x-list"]["properties"])
#|            an = Analysis(flow, Catalog(), CodeIndex()).run()
#|            fetch_props = {f["name"]: f for f in an.props["x-fetch"]}
#|            self.assertEqual(fetch_props["File to Fetch"]["resolved"], "/data/in/${filename}")
#|            self.assertIn("filename", an.attrs_read["x-fetch"])
#|            self.assertEqual([c["id"] for c in an.entry_points("g1")], ["g1-in"])
#|            self.assertEqual([c["id"] for c in an.entry_points()], ["x-list"])
#|
#|    def test_flow_definition_export(self):
#|        doc = nested_flow()
#|        export = {"flowContents": doc["rootGroup"], "parameterContexts": {c["name"]: c for c in doc["parameterContexts"]}}
#|        with tempfile.TemporaryDirectory() as tmp:
#|            p = Path(tmp) / "export.json"
#|            p.write_text(json.dumps(export))
#|            flow = load_flow(p)
#|            self.assertEqual(flow.format, "flow-definition")
#|            self.assertIn("vendor-params", flow.param_contexts)
#|            self.assertEqual(len([c for c in flow.components.values() if c["kind"] == "PROCESSOR"]), 10)
#|
#|
#|class TestCatalogAndCode(unittest.TestCase):
#|    def test_fake_nars(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            make_env(tmp, with_db=False)
#|            acme = read_nar(Path(tmp) / "nars" / "acme-nifi-nar-1.0.0.nar")
#|            ext = acme["extensions"][0]
#|            self.assertEqual(ext["type"], "com.acme.nifi.ValidateOrderJson")
#|            self.assertEqual([r["name"] for r in ext["relationships"]], ["valid", "invalid", "failure"])
#|            self.assertEqual(ext["properties"]["Validation URL"]["default"], "https://validator.acme.com/api/v1/check")
#|            legacy = read_nar(Path(tmp) / "nars" / "legacy-nar.nar")
#|            self.assertEqual([e["type"] for e in legacy["extensions"]], ["com.legacy.OldProcessor"])
#|            self.assertFalse(legacy["extensions"][0]["has_manifest"])
#|
#|    @unittest.skipUnless((REAL_NIFI / "lib" / "nifi-standard-nar-1.27.0.nar").exists(), "real NiFi not installed")
#|    def test_real_standard_nar(self):
#|        info = read_nar(REAL_NIFI / "lib" / "nifi-standard-nar-1.27.0.nar")
#|        types = {e["type"]: e for e in info["extensions"]}
#|        pdr = types["org.apache.nifi.processors.standard.PutDatabaseRecord"]
#|        self.assertEqual(pdr["properties"]["put-db-record-table-name"]["displayName"], "Table Name")
#|        self.assertEqual({r["name"] for r in pdr["relationships"]}, {"success", "failure", "retry"})
#|        self.assertTrue(types["org.apache.nifi.processors.standard.RouteOnAttribute"]["dynamic_relationships"])
#|
#|    def test_java_processor(self):
#|        info = codemod.index_file(FIXTURES / "repo/nifi-acme-processors/src/main/java/com/acme/nifi/ValidateOrderJson.java")
#|        comp = codemod.CodeIndex([info]).by_fqcn["com.acme.nifi.ValidateOrderJson"][0]["component"]
#|        self.assertEqual(comp["fqcn"], "com.acme.nifi.ValidateOrderJson")
#|        self.assertEqual(comp["tags"], ["acme", "json", "validation"])
#|        self.assertEqual(comp["input_requirement"], "INPUT_REQUIRED")
#|        self.assertIn("ACME validator service and routes", comp["description"])
#|        props = {p["name"]: p for p in comp["properties"]}
#|        self.assertEqual(props["Validation URL"]["default"], "https://validator.acme.com/api/v1/check")
#|        self.assertTrue(props["Api Token"]["sensitive"])
#|        self.assertEqual([r["name"] for r in comp["relationships"]], ["valid", "invalid", "failure"])
#|        self.assertEqual(comp["reads_attributes"], ["order.id", "vendor"])
#|        self.assertEqual(comp["writes_attributes"], ["validated.by", "validation.status"])
#|        kinds = {(h["kind"], h["value"]) for h in info["hardcoded"]}
#|        self.assertIn(("url", "https://validator-backup.acme.com/api/v1/check"), kinds)
#|        self.assertIn(("s3", "acme-orders-raw"), kinds)
#|        self.assertIn(("path", "/data/archive/orders"), kinds)
#|        self.assertEqual(info["tables"], ["order_status", "validation_log", "vendors"])
#|        secret = [h for h in info["hardcoded"] if h["kind"] == "secret"]
#|        self.assertEqual(len(secret), 1)
#|        self.assertNotIn("Sup3rS3cret!", json.dumps(info))
#|
#|    def test_python_script(self):
#|        info = codemod.index_file(FIXTURES / "repo/scripts/enrich.py")
#|        self.assertEqual(info["functions"], ["enrich", "main"])
#|        self.assertEqual(info["imports"], ["pymysql", "sys"])
#|        self.assertEqual(info["tables"], ["customers"])
#|        self.assertIn(("ip", "10.20.30.40"), {(h["kind"], h["value"]) for h in info["hardcoded"]})
#|        self.assertNotIn("hunter2", json.dumps(info))
#|
#|
#|class TestEndToEnd(unittest.TestCase):
#|    """Full build over the nested fixture: flow + custom NAR + repo + SQLite metadata DB."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp)
#|        cls.cfg = load_config(cls.cfg_path)
#|        cls.res = build(cls.cfg, log=lambda m: None)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|        cls.text = all_text(cls.kb)
#|        cls.db = sqlite3.connect(cls.kb / "kb.sqlite")
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.db.close()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def findings(self, kind):
#|        return self.db.execute("SELECT component_id, message FROM findings WHERE kind=?", (kind,)).fetchall()
#|
#|    def test_files_generated(self):
#|        for f in ["INDEX.md", "flows/root.md", "flows/vendor-json-ingestion.md", "services.md", "external-systems.md", "hardcoded.md",
#|                  "issues.md", "custom-code/ValidateOrderJson.md", "custom-code/INDEX.md", "scripts/enrich-py.md", "db/metadata.md", "CHANGELOG.md"]:
#|            self.assertTrue((self.kb / f).exists(), f)
#|
#|    def test_no_secret_leaks(self):
#|        blob = "\n".join(self.text.values()) + (self.kb / "kb.sqlite").read_bytes().decode("latin-1")
#|        for s in SECRET_VALUES + ["enc{0123456789abcdef}", "enc{ffff}"]:
#|            self.assertNotIn(s, blob, f"secret {s!r} leaked into the knowledge base")
#|
#|    def test_cross_group_tree(self):
#|        vendor = (self.kb / "flows/vendor-json-ingestion.md").read_text(encoding="utf-8")
#|        self.assertIn("⇥ input port **orders in**", vendor)
#|        self.assertIn("*matched* → **Validate order** [ValidateOrderJson]", vendor)
#|        self.assertIn("*valid* → **Store raw JSON** [PutS3Object]", vendor)
#|        self.assertIn("bucket=acme-orders-raw", vendor)
#|        root = (self.kb / "flows/root.md").read_text(encoding="utf-8")
#|        self.assertIn("in PG **Vendor JSON Ingestion**", root)
#|        rc, out = run_cli("--config", str(self.cfg_path), "trace", "Receive orders API")
#|        self.assertEqual(rc, 0)
#|        for name in ("Extract fields", "Validate order", "Store raw JSON", "Write audit row", "Lookup customer", "Archive order"):
#|            self.assertIn(name, out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "trace", "Archive order", "--up")
#|        self.assertIn("◀ **Archive order**", out)
#|        self.assertIn("Nightly trigger", out)
#|        self.assertIn("Receive orders API", out)
#|
#|    def test_parameters_variables_resolved(self):
#|        props = dict(self.db.execute("SELECT name, resolved FROM properties WHERE component_id='p-rejects'").fetchall())
#|        self.assertEqual(props["Directory"], "/data/shared/rejects")  # inherited parameter context
#|        props = dict(self.db.execute("SELECT name, resolved FROM properties WHERE component_id='p-s3'").fetchall())
#|        self.assertEqual(props["Bucket"], "acme-orders-raw")
#|        self.assertEqual(props["Secret Access Key"], "<sensitive>")
#|        props = dict(self.db.execute("SELECT name, resolved FROM properties WHERE component_id='p-enrich'").fetchall())
#|        self.assertEqual(props["Command Arguments"], "/data/landing/scripts/enrich.py ${order.id}")
#|
#|    def test_resources_and_hardcoded(self):
#|        rows = self.db.execute("SELECT kind, value, hardcoded FROM resources").fetchall()
#|        kinds = {(k, v): h for k, v, h in rows}
#|        self.assertEqual(kinds[("url", "https://validator.acme.com/api/v1/check")], 1)
#|        self.assertEqual(kinds[("s3_bucket", "acme-orders-raw")], 0)  # parameterized: not hardcoded
#|        self.assertEqual(kinds[("db_table", "file_audit")], 1)
#|        self.assertIn(("db_table", "customers"), kinds)
#|        self.assertIn(("db_table", "orders"), kinds)
#|        self.assertIn(("port", "8081"), kinds)
#|        self.assertIn(("jdbc", "jdbc:mariadb://dbhost.acme.com:3306/meta"), kinds)
#|        hard = (self.kb / "hardcoded.md").read_text(encoding="utf-8")
#|        self.assertIn("validator-backup.acme.com", hard)   # from Java code
#|        self.assertIn("10.20.30.40", hard)                  # from python script
#|        self.assertIn("s3://acme-orders-curated/audit/", hard)  # from groovy
#|
#|    def test_lint_findings(self):
#|        unhandled = self.findings("unhandled-relationship")
#|        self.assertEqual([r[0] for r in unhandled], ["p-validate"])
#|        self.assertIn("failure", unhandled[0][1])
#|        secrets = {m for _, m in self.findings("plaintext-secret")}
#|        self.assertTrue(any("API Token" in m for m in secrets))
#|        self.assertTrue(any("db.password" in m for m in secrets))
#|        self.assertTrue(any("etl.password" in m for m in secrets))
#|        dropped = {c for c, _ in self.findings("dropped-errors")}
#|        self.assertIn("p-audit", dropped)
#|        self.assertNotIn("p-gen", dropped)
#|
#|    def test_custom_code_linked(self):
#|        doc = (self.kb / "custom-code/ValidateOrderJson.md").read_text(encoding="utf-8")
#|        self.assertIn("ValidateOrderJson.java:16", doc)
#|        self.assertIn("- writes: `validated.by` (ValidateOrderJson.java:51), `validation.status` (ValidateOrderJson.java:50)", doc)
#|        self.assertIn("- reads: `order.id` (ValidateOrderJson.java:47), `vendor` (ValidateOrderJson.java:48)", doc)
#|        self.assertIn("Vendor JSON Ingestion", doc)
#|        self.assertFalse(self.findings("custom-code-missing"))
#|        script = (self.kb / "scripts/enrich-py.md").read_text(encoding="utf-8")
#|        self.assertIn("repo match", script)
#|        self.assertIn("Functions: enrich, main", script)
#|
#|    def test_database(self):
#|        doc = (self.kb / "db/metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("## file_audit", doc)
#|        self.assertIn("## customers", doc)       # from ExecuteSQL
#|        self.assertIn("## file_calls", doc)      # include_tables pattern
#|        self.assertNotIn("## unrelated", doc)
#|        self.assertIn("values of `source_system`: vendorA×2, vendorB×1", doc)
#|        self.assertIn("user_email", doc)
#|        self.assertNotIn("x@y.com", doc)          # sample rows are masked
#|        self.assertIn("order_archive", doc)       # missing table reported
#|        missing = self.findings("missing-table")
#|        self.assertEqual([(c, "order_archive" in m) for c, m in missing], [("p-archive", True)])
#|        mismatch = self.findings("field-mismatch")
#|        self.assertEqual(len(mismatch), 1)
#|        self.assertIn("extra_field", mismatch[0][1])
#|        self.assertIn("received_at", mismatch[0][1])
#|
#|    def test_index_summary(self):
#|        idx = (self.kb / "INDEX.md").read_text(encoding="utf-8")
#|        self.assertIn("Vendor JSON Ingestion", idx)
#|        self.assertIn("json", idx)
#|        self.assertIn("MetaDB `jdbc:mariadb://dbhost.acme.com:3306/meta` → tables: customers, file_audit, order_archive, orders", idx)
#|        self.assertIn("db.password=<redacted>", idx)
#|        self.assertLess(len(idx), 6000)
#|
#|    def test_cli_search_show_sql(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "validator")
#|        self.assertIn("Validate order", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "file_audit")
#|        self.assertIn("Write audit row", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "show", "p-valid")
#|        self.assertIn("### Validate order", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "show", "ValidateOrderJson")
#|        self.assertIn("# ValidateOrderJson", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT status, COUNT(*) n FROM file_calls GROUP BY status ORDER BY status")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("FAILED", out)
#|        for bad in ("DELETE FROM file_calls", "SELECT 1; DROP TABLE file_calls", "UPDATE file_calls SET status='x'"):
#|            rc, out = run_cli("--config", str(self.cfg_path), "sql", bad)
#|            self.assertEqual(rc, 1, bad)
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT user_email FROM file_audit")
#|        self.assertIn("***", out)
#|        self.assertEqual(dbmod.run_query(self.cfg["databases"][0], "SELECT COUNT(*) FROM file_calls")[1], [(3,)])
#|
#|    def test_diagnose(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "order_id,vendor,staatus,order_source")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("Write audit row", out)
#|        self.assertIn("file_audit", out)
#|        self.assertIn("did you mean 'status'?", out)
#|        self.assertIn("expected fields not present in your headers: status, extra_field", out)
#|        self.assertIn("NOT NULL column(s) in file_audit that nothing supplies: received_at", out)
#|        self.assertIn("field-mismatch", out)  # known finding surfaced alongside the live diagnosis
#|
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "order_id", "vendor", "status", "extra_field")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("100%", out)
#|        self.assertIn("these headers have no matching column in file_audit: extra_field", out)
#|
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "totally", "unrelated", "headers")
#|        self.assertEqual(rc, 1)
#|        self.assertIn("no confident match", out)
#|
#|
#|class TestMetadata(unittest.TestCase):
#|    """Metadata-driven ingestion: OBJ_DEFINITION / OBJ_STRUCTURE / feed + API config tables, auto-detected."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        cls.cfg = load_config(cls.cfg_path)
#|        cls.logs = []
#|        build(cls.cfg, log=cls.logs.append)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def diagnose(self, *argv):
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", *argv)
#|        return rc, out
#|
#|    def test_roles_and_relations_detected(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("definition table: `OBJ_DEFINITION` · id `OBJ_ID` · lookup keys `FILE_NAME`, `TABLE_NAME` · target table column `TABLE_NAME`", doc)
#|        self.assertIn("field `COL_NAME` · type `DATA_TYPE` · order `COL_SEQ` · length `COL_LENGTH` · nullable `MANDATORY_FLAG` (flag means required)", doc)
#|        self.assertIn("`SOURCE_FEED_CONFIG.OBJ_ID` → `OBJ_DEFINITION.OBJ_ID` (shared column name)", doc)
#|        self.assertIn("`OBJ_STRUCTURE.OBJ_ID` → `OBJ_DEFINITION.OBJ_ID` (foreign key)", doc)
#|        self.assertNotIn("stg_sales |", doc.split("## Config tables")[1].split("## Relations")[0])  # target tables are not config
#|        self.assertIn("metadata.md", (self.kb / "INDEX.md").read_text(encoding="utf-8"))
#|
#|    def test_drift_findings(self):
#|        db = sqlite3.connect(self.kb / "kb.sqlite")
#|        rows = [r[0] for r in db.execute("SELECT message FROM findings WHERE kind='metadata-drift'")]
#|        db.close()
#|        self.assertEqual(len(rows), 2, rows)
#|        sales = next(r for r in rows if "stg_sales" in r)
#|        self.assertIn("NOT NULL column(s) of stg_sales not in the structure: load_ts", sales)
#|        self.assertIn("'CUST_NAME' length 50", sales)
#|        self.assertIn("'AMOUNT' is VARCHAR in the structure but DECIMAL(10,2)", sales)
#|        self.assertTrue(any("'stg_returns' does not exist" in r for r in rows))
#|        self.assertIn("metadata-drift", (self.kb / "issues.md").read_text(encoding="utf-8"))
#|
#|    def test_secrets_never_stored(self):
#|        from fixtures_builder import API_TOKEN
#|        blob = (self.kb / "kb.sqlite").read_bytes()
#|        for secret in ("Sup3rS3cret!", API_TOKEN, "hunter2"):
#|            self.assertFalse(secret.encode() in blob, f"{secret} stored in kb.sqlite")
#|            for path, text in all_text(self.kb).items():
#|                self.assertNotIn(secret, text, path)
#|        rc, out = self.diagnose("--feed", "crm_customers_api", "--json")
#|        self.assertNotIn(API_TOKEN, out)
#|        self.assertNotIn("hunter2", out)
#|
#|    def test_file_pattern_and_headers(self):
#|        rc, out = self.diagnose("--file", "/landing/pos/SALES_20260926.csv", "CUSTNAME", "AMT", "REGION", "ORDER_DT")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("pattern 'SALES_YYYYMMDD.csv'", out)
#|        self.assertIn("header 'CUSTNAME' differs from 'CUST_NAME' only by case", out)
#|        self.assertIn("header 'AMT' is not in the structure (did you mean 'AMOUNT'?)", out)
#|        self.assertIn("[error] structure field 'ORDER_NO' (seq 1) is not in the headers", out)
#|        self.assertIn("[warn] structure field 'AMOUNT' (seq 3) is not in the headers (nullable)", out)
#|        self.assertIn("header order differs from the structure sequence: headers REGION, ORDER_DT", out)
#|        self.assertIn("SFTP_PASSWORD=***", out)
#|        self.assertIn("Tag POS feed", out)           # linked through the related feed row's FEED_NAME
#|        self.assertIn("Read object metadata", out)   # reads the config tables
#|
#|    def test_feed_table_and_json(self):
#|        rc, out = self.diagnose("--feed", "pos_sales_feed", "--json")
#|        res = json.loads(out)
#|        self.assertEqual(res["definitions"][0]["target"], "stg_sales")
#|        self.assertEqual([f["name"] for f in res["definitions"][0]["fields"]], ["ORDER_NO", "CUST_NAME", "AMOUNT", "ORDER_DT", "REGION"])
#|        self.assertIn("p-feed", [p["id"] for p in res["processors"]])
#|        rc, out = self.diagnose("--table", "stg_customers", "CUST_ID", "NAME", "EMAIL")
#|        self.assertIn("OK structure, headers and target table agree", out)
#|        rc, out = self.diagnose("--feed", "crm_customers_api")
#|        self.assertIn("NIFI_JSON_API_CONFIG.API_NAME (exact)", out)
#|        self.assertIn("AUTH_HEADER=***", out)
#|
#|    def test_sample_file_headers(self):
#|        sample = Path(self.tmp) / "customers_20260926.json"
#|        sample.write_text(json.dumps({"data": [{"CUST_ID": 1, "NAME": "a", "E_MAIL": "x"}], "count": 1}), encoding="utf-8")
#|        rc, out = self.diagnose("--file", sample.name, "--sample", str(sample))
#|        self.assertIn("header 'E_MAIL' differs from 'EMAIL' only by case/underscores", out)
#|        csv_sample = Path(self.tmp) / "SALES_20260101.csv"
#|        csv_sample.write_text("ORDER_NO|CUST_NAME|AMOUNT|ORDER_DT|REGION\n1|a|2|2026-01-01|N\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", csv_sample.name, "--sample", str(csv_sample))
#|        self.assertNotIn("is not in the headers", out)
#|        self.assertNotIn("header order differs", out)
#|
#|    def test_nested_json_api_payload(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("· JSON path `JSON_PATH`", doc)
#|        self.assertNotIn("stg_orders:", doc.split("## Definitions vs. target tables")[1])  # columns match by COL_NAME
#|        payload = Path(self.tmp) / "orders_page1.json"
#|        payload.write_text(json.dumps({"page": 1, "orders": [{"id": 7, "customer": {"fullName": "A"}, "amount": 2.5}]}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(payload))
#|        self.assertIn("sample: JSON, record root $.orders, 3 nested field paths compared (order not checked)", out)
#|        self.assertIn("header 'customer.fullName' is not in the structure (did you mean 'customer.name'?)", out)
#|        self.assertIn("structure field 'customer.name' (seq 2) is not in the headers (nullable)", out)
#|        self.assertNotIn("order differs", out)
#|        self.assertNotIn("AUTH_HEADER=Bearer", out)
#|        good = Path(self.tmp) / "orders_ok.json"
#|        good.write_text(json.dumps({"orders": [{"id": 1, "customer": {"name": "B"}, "amount": 1}]}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(good))
#|        self.assertIn("OK structure, headers and target table agree", out)
#|        wrong = Path(self.tmp) / "orders_wrapped.json"
#|        wrong.write_text(json.dumps({"data": {"items": [{"id": 1}]}}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(wrong))
#|        self.assertIn("no JSON record found in the sample below root path '$.orders'", out)
#|
#|    def test_file_targets_hdfs_s3(self):
#|        from nifikb import metadata as metamod
#|        model = {"target_db": "metadata"}
#|        self.assertTrue(metamod.table_target(model, "stg_sales"))
#|        self.assertTrue(metamod.table_target(model, "dw.stg_sales"))
#|        for loc in ("s3://raw-bucket/sales/", "hdfs://nn:8020/data/raw/sales", "/data/raw/sales", "s3a://b/k"):
#|            self.assertFalse(metamod.table_target(model, loc), loc)
#|        self.assertFalse(metamod.table_target({"target_db": None}, "stg_sales"))
#|        with tempfile.TemporaryDirectory() as tmp:  # loads go to files: target checks off, no false "table missing"
#|            cfg_path = make_env(tmp, with_metadata=True)
#|            with open(cfg_path, "a", encoding="utf-8") as f:
#|                f.write('target_db = "none"\n')
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            db.execute("ALTER TABLE OBJ_DEFINITION ADD COLUMN HDFS_PATH TEXT")
#|            db.execute("UPDATE OBJ_DEFINITION SET HDFS_PATH = '/data/raw/sales' WHERE OBJ_ID = 1")
#|            db.commit()
#|            db.close()
#|            cfg = load_config(cfg_path)
#|            build(cfg, log=lambda m: None)
#|            doc = (Path(cfg["output"]["dir"]) / "metadata.md").read_text(encoding="utf-8")
#|            self.assertIn("location column `HDFS_PATH`", doc)
#|            self.assertIn("target checks off", doc)
#|            self.assertNotIn("does not exist in the target database", doc)
#|            rc, out = run_cli("--config", str(cfg_path), "diagnose", "--file", "SALES_20260926.csv", "ORDER_NO", "CUST_NAME")
#|            self.assertIn("→ loads to /data/raw/sales", out)
#|            self.assertNotIn("NOT NULL column(s) of stg_sales", out)
#|
#|    def test_content_validation_csv(self):
#|        sample = Path(self.tmp) / "SALES_20260930.csv"
#|        sample.write_text("ORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\n1,Alice,10.5,2026-09-01,EU\n,Bob,3,2026-09-02,EU\n"
#|                          "x7,Carol,4,2026-09-03,EU\n4,\"Dan, Jr\",5,31/31/2026,EU\n5,Eve,6,2026-09-05,EUROPE-WEST-1\n"
#|                          "6,Frank,7,2026-09-06,EU,extra\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", sample.name, "--sample", str(sample))
#|        self.assertIn("sample: CSV, delimiter ',' (configured in DELIMITER), with header row, 6 data rows checked", out)
#|        self.assertIn("'ORDER_NO' is empty but mandatory in 1 of 6 rows (e.g. row 3: '')", out)
#|        self.assertIn("'ORDER_NO' is not a valid INTEGER in 1 of 6 rows (e.g. row 4: 'x7')", out)
#|        self.assertIn("'ORDER_DT' is not a recognisable date / time (DATE) in 1 of 6 rows (e.g. row 5: '31/31/2026')", out)
#|        self.assertIn("'REGION' is longer than 10 characters in 1 of 6 rows", out)
#|        self.assertIn("1 of 6 rows do not have 5 columns (row 7 has 6)", out)
#|        self.assertNotIn("Dan, Jr", out.split("rows do not have")[0][-200:])  # quoted comma is fine
#|
#|    def test_content_validation_delimiter_and_encoding(self):
#|        piped = Path(self.tmp) / "SALES_20261001.csv"
#|        piped.write_text("ORDER_NO|CUST_NAME|AMOUNT|ORDER_DT|REGION\n1|A|2|2026-10-01|EU\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", piped.name, "--sample", str(piped))
#|        self.assertIn("the file is delimited by '|', but the delimiter is ','", out)
#|        self.assertIn("with header row, 1 data rows checked", out)
#|        latin = Path(self.tmp) / "SALES_20261002.csv"
#|        latin.write_bytes(b"\xef\xbb\xbfORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\n1,Ren\xe9e,2,2026-10-02,EU\n")
#|        rc, out = self.diagnose("--file", latin.name, "--sample", str(latin))
#|        self.assertIn("file is not valid UTF-8", out)
#|        latin.write_bytes(b"\xef\xbb\xbfORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\n1,Renee,2,2026-10-02,EU\n")
#|        rc, out = self.diagnose("--file", latin.name, "--sample", str(latin))
#|        self.assertIn("byte-order mark", out)
#|        self.assertNotIn("only by case/underscores", out)  # the BOM does not break the header match
#|
#|    def test_content_validation_json(self):
#|        payload = Path(self.tmp) / "orders_bad.json"
#|        payload.write_text(json.dumps({"orders": [{"id": 1, "customer": {"name": "A"}, "amount": 2.5},
#|                                                  {"customer": {"name": "B"}, "amount": "abc"}]}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(payload))
#|        self.assertIn("'ORDER_ID' is empty but mandatory in 1 of 2 rows", out)
#|        self.assertIn("'AMOUNT' is not a valid DECIMAL in 1 of 2 rows (e.g. row 2: 'abc')", out)
#|
#|    def test_proposed_fixes(self):
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv", "ORDER_NO", "CUSTNAME", "AMOUNT", "ORDER_DT", "REGION")
#|        self.assertIn("proposed fixes (review first - nifikb never runs them):", out)
#|        self.assertIn("UPDATE OBJ_STRUCTURE SET COL_NAME = 'CUSTNAME' WHERE STRUCT_ID = 2;", out)
#|        self.assertIn("[sender (preferred) or config]", out)
#|        self.assertIn("UPDATE OBJ_STRUCTURE SET COL_LENGTH = 20 WHERE STRUCT_ID = 2;", out)
#|        self.assertIn("UPDATE OBJ_STRUCTURE SET DATA_TYPE = 'DECIMAL' WHERE STRUCT_ID = 3;", out)
#|        self.assertIn("INSERT INTO OBJ_STRUCTURE (OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, MANDATORY_FLAG) VALUES (1, 'load_ts', 'TEXT', 6, 'Y');", out)
#|        rc, out = self.diagnose("--file", "returns.csv")
#|        self.assertNotIn("stg_orders", out)  # never point a definition at a merely similar-looking table
#|        from nifikb.fixes import quote
#|        self.assertEqual(quote("O'Brien"), "'O''Brien'")
#|        piped = Path(self.tmp) / "SALES_20261003.csv"
#|        piped.write_text("ORDER_NO|CUST_NAME|AMOUNT|ORDER_DT|REGION\n1|A|2|2026-10-01|EU\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", piped.name, "--sample", str(piped))
#|        self.assertIn("UPDATE OBJ_DEFINITION SET DELIMITER = '|' WHERE OBJ_ID = 1;", out)
#|
#|    def test_unknown_suggests(self):
#|        rc, out = self.diagnose("--file", "SALEZ_20260926.csv")
#|        self.assertEqual(rc, 1)
#|        self.assertIn("did you mean: SALES_YYYYMMDD.csv", out)
#|
#|    def test_live_matches_snapshot(self):
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv", "--live", "--json")
#|        live = json.loads(out)
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv", "--json")
#|        snap = json.loads(out)
#|        self.assertTrue(live["live"])
#|        self.assertEqual([f["name"] for f in live["definitions"][0]["fields"]], [f["name"] for f in snap["definitions"][0]["fields"]])
#|        self.assertEqual(sorted(i["kind"] for i in live["definitions"][0]["issues"]),
#|                         sorted(i["kind"] for i in snap["definitions"][0]["issues"]))
#|
#|    def test_custom_code_reading_config_tables(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("`com.acme.meta.MetadataLookup` ([doc](custom-code/MetadataLookup.md)): OBJ_DEFINITION, OBJ_STRUCTURE, SOURCE_FEED_CONFIG", doc)
#|        self.assertNotIn("ValidateOrderJson", doc.split("## Custom code that reads these tables")[1].split("##")[0])
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv")
#|        self.assertIn("Metadata lookup [MetadataLookup]", out)
#|        self.assertIn("custom MetadataLookup queries OBJ_DEFINITION, OBJ_STRUCTURE, SOURCE_FEED_CONFIG in its code", out)
#|
#|    def test_show_table(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "show", "stg_sales")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("| load_ts |", out)
#|        self.assertNotIn("stg_customers", out)  # only that table's section
#|
#|    def test_search_finds_config_rows(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "sftp.pos.acme.com")
#|        self.assertIn("SOURCE_FEED_CONFIG", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "CUST_NAME")
#|        self.assertIn("SALES_YYYYMMDD.csv", out)
#|
#|    def test_mcp_server(self):
#|        import subprocess
#|        msgs = [
#|            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
#|                                                                          "clientInfo": {"name": "test", "version": "0"}}},
#|            {"jsonrpc": "2.0", "method": "notifications/initialized"},
#|            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
#|            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "diagnose", "arguments": {
#|                "key": "SALES_20260926.csv", "headers": ["ORDER_NO", "CUST_NAME", "AMOUNT", "REGION", "ORDER_DT"]}}},
#|            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "issues", "arguments": {"kind": "metadata-drift"}}},
#|            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "read_kb_file", "arguments": {"path": "../nifikb.toml"}}},
#|            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "pos_sales_feed"}}},
#|            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "sql", "arguments": {"query": "DELETE FROM OBJ_DEFINITION"}}},
#|        ]
#|        proc = subprocess.run([sys.executable, "-m", "nifikb", "--config", str(self.cfg_path), "mcp"],
#|                              input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, encoding="utf-8",
#|                              cwd=str(Path(__file__).resolve().parent.parent), timeout=120)
#|        replies = {r["id"]: r for r in (json.loads(line) for line in proc.stdout.splitlines() if line.strip())}
#|        self.assertEqual(sorted(replies), [1, 2, 3, 4, 5, 6, 7], proc.stderr)
#|        self.assertEqual(replies[1]["result"]["serverInfo"]["name"], "nifikb")
#|        self.assertIn("diagnose", [t["name"] for t in replies[2]["result"]["tools"]])
#|        diag = replies[3]["result"]["content"][0]["text"]
#|        self.assertIn("header order differs from the structure sequence", diag)
#|        self.assertIn("→ target table stg_sales", diag)
#|        self.assertNotIn('"definitions"', diag)  # text only unless structured=true
#|        self.assertIn("stg_returns", replies[4]["result"]["content"][0]["text"])
#|        self.assertTrue(replies[5]["result"]["isError"])       # no reading outside kb/
#|        self.assertIn("SOURCE_FEED_CONFIG", replies[6]["result"]["content"][0]["text"])
#|        self.assertTrue(replies[7]["result"]["isError"])       # read-only
#|
#|    def test_overrides_and_validation(self):
#|        from nifikb import metadata as metamod
#|        cfg = dict(self.cfg, metadata={"db": "metadata", "structure_order": "bad name;"})
#|        with self.assertRaises(ValueError):
#|            metamod.settings(cfg)
#|        cfg = dict(self.cfg, metadata={"db": "nope"})
#|        with self.assertRaises(ValueError):
#|            metamod.settings(cfg)
#|
#|
#|LOG_SAMPLE = """2026-09-26 10:15:01,100 INFO [main] org.apache.nifi.NiFi Launching NiFi...
#|2026-09-26 10:15:02,254 ERROR [Timer-Driven Process Thread-1] o.a.n.p.standard.PutDatabaseRecord PutDatabaseRecord[id=inst-p-audit-0000-0000-000000000000] Failed to put Records to database for StandardFlowFileRecord[uuid=6b52c7d3-acef-4940-8ff7-d91b7a7abd21,claim=StandardContentClaim [resourceClaim=StandardResourceClaim[id=1-6, container=default, section=6], offset=0, length=53],offset=0,name=orders_0926.json,size=53]. Routing to failure.
#|org.apache.nifi.processors.standard.db.TableNotFoundException: Table meta.file_audit not found, ensure the Catalog, Schema, and/or Table Names match
#|\tat org.apache.nifi.processors.standard.db.TableSchema.from(TableSchema.java:117)
#|Caused by: java.sql.SQLSyntaxErrorException: Table 'meta.file_audit' doesn't exist
#|\tat org.mariadb.jdbc.X.y(X.java:1)
#|2026-09-26 10:16:02,254 ERROR [Timer-Driven Process Thread-2] o.a.n.p.standard.PutDatabaseRecord PutDatabaseRecord[id=inst-p-audit-0000-0000-000000000000] Failed to put Records to database for StandardFlowFileRecord[uuid=9b52c7d3-acef-4940-8ff7-d91b7a7abd21,claim=,offset=0,name=orders_0927.json,size=53]. Routing to failure.
#|2026-09-26 10:17:00,000 WARN [Timer-Driven Process Thread-3] o.a.n.c.repository.FileSystemRepository Unable to write flowfile content; waiting for archive cleanup. Total number of files currently archived = 12
#|2026-09-26 10:18:00,000 DEBUG [x] o.a.n.Y password=hunter2 ignored debug line
#|"""
#|BOOT_SAMPLE = """2026-09-26 09:00:00,000 INFO [main] org.apache.nifi.bootstrap.Command Launched Apache NiFi with Process ID 4242
#|2026-09-26 09:30:00,000 INFO [main] o.a.n.b.NotificationServiceManager Registered no Notification Services for Notification Type NIFI_DIED
#|2026-09-26 11:59:00,000 WARN [NiFi Bootstrap Command Listener] org.apache.nifi.bootstrap.RunNiFi Apache NiFi appears to have died. Restarting...
#|"""
#|
#|
#|class TestLogsAndProvenance(unittest.TestCase):
#|    """nifi-app / bootstrap log indexing (incremental, rotation, causes, grouping) and provenance through a fake NiFi API."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import FakeNiFi
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.logdir = Path(cls.tmp) / "logs"
#|        cls.logdir.mkdir()
#|        (cls.logdir / "nifi-app.log").write_text(LOG_SAMPLE.replace("inst-p-audit-0000-0000-000000000000", "inst-p-audit"), encoding="utf-8")
#|        (cls.logdir / "nifi-bootstrap.log").write_text(BOOT_SAMPLE, encoding="utf-8")
#|        cls.fake = FakeNiFi()
#|        os.environ["NIFIKB_TEST_NIFI_PW"] = "pw123456789"
#|        cls.cfg_path = make_env(cls.tmp)
#|        with open(cls.cfg_path, "a", encoding="utf-8") as f:
#|            f.write(f'\n[logs]\ndirs = ["{cls.logdir.as_posix()}"]\n'
#|                    f'\n[nifi_api]\nurl = "{cls.fake.url}"\nusername = "admin"\npassword_env = "NIFIKB_TEST_NIFI_PW"\n'
#|                    f'\n[registry]\nurl = "{cls.fake.url.replace("/nifi-api", "")}"\nusername = "admin"\npassword_env = "NIFIKB_TEST_NIFI_PW"\n')
#|        cls.cfg = load_config(cls.cfg_path)
#|        build(cls.cfg, log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.fake.stop()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def cli(self, *argv):
#|        return run_cli("--config", str(self.cfg_path), *argv)
#|
#|    def test_log_parser_units(self):
#|        from nifikb import logs
#|        events = list(logs.parse_lines(enumerate(LOG_SAMPLE.splitlines(), 1), "nifi-app.log"))
#|        self.assertEqual([e["level"] for e in events], ["ERROR", "ERROR", "WARN"])
#|        e = events[0]
#|        self.assertEqual((e["component_type"], e["component_id"]), ("PutDatabaseRecord", "inst-p-audit-0000-0000-000000000000"))
#|        self.assertEqual((e["flowfile_uuid"], e["filename"]), ("6b52c7d3-acef-4940-8ff7-d91b7a7abd21", "orders_0926.json"))
#|        self.assertEqual(e["cause"], "SQLSyntaxErrorException: Table 'meta.file_audit' doesn't exist")  # the root cause
#|        self.assertEqual(events[0]["template"], events[1]["template"])  # same shape -> grouped
#|        boot = list(logs.parse_lines(enumerate(BOOT_SAMPLE.splitlines(), 1), "nifi-bootstrap.log", bootstrap=True))
#|        self.assertEqual([b["level"] for b in boot], ["LIFECYCLE", "WARN"])  # NIFI_DIED setup line is not a crash
#|
#|    def test_logs_cli(self):
#|        rc, out = self.cli("logs", "--file", "orders_0926.json")
#|        self.assertIn("PutDatabaseRecord", out)
#|        self.assertIn("(Write audit row `p-audit` in NiFi Flow)", out)  # runtime id -> flow component
#|        self.assertIn("cause: SQLSyntaxErrorException", out)
#|        rc, out = self.cli("logs", "--component", "Write audit row")
#|        self.assertIn("x2", out)
#|        rc, out = self.cli("logs", "--level", "LIFECYCLE")
#|        self.assertIn("Launched Apache NiFi", out)
#|        self.assertNotIn("hunter2", out)
#|
#|    def test_incremental_and_rotation(self):
#|        from nifikb import logs
#|        from nifikb.store import Store
#|        store = Store(str(Path(self.cfg["output"]["dir"]) / "kb.sqlite"))
#|        try:
#|            self.assertEqual(logs.index(self.cfg, store, log=lambda m: None), (0, 0))  # nothing new
#|            app = self.logdir / "nifi-app.log"
#|            with open(app, "a", encoding="utf-8") as f:
#|                f.write("2026-09-26 12:00:00,000 ERROR [T] o.a.n.X FetchFile[id=inst-p-extract] Could not fetch file a.csv\n")
#|            self.assertEqual(logs.index(self.cfg, store, log=lambda m: None)[1], 1)  # only the new line
#|            (self.logdir / "nifi-app_2026-09-26_10.0.log").write_text(LOG_SAMPLE.replace("inst-p-audit-0000-0000-000000000000", "inst-p-audit"),
#|                                                                        encoding="utf-8")  # rolled copy: duplicates ignored
#|            self.assertEqual(logs.index(self.cfg, store, log=lambda m: None)[1], 0)
#|        finally:
#|            store.close()
#|
#|    def test_provenance_dropped_flowfile(self):
#|        rc, out = self.cli("provenance", "--file", "orders_0926.json")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("DROPPED at Write rejects (PutFile): Auto-Terminated by failure Relationship", out)
#|        self.assertIn("ROUTE", out)
#|        self.assertIn("-> invalid", out)
#|        self.assertIn("(Validate order `p-valida` in", out)
#|        self.assertIn("validation.error=vendor missing", out)
#|        self.assertNotIn("tok-SECRET-9", out)
#|        self.assertTrue(self.fake.deleted)  # the temporary provenance query was removed
#|        rc, out = self.cli("provenance", "--file", "late.json")
#|        self.assertIn("FlowFile Expired", out)
#|        rc, out = self.cli("provenance", "--file", "never.json")
#|        self.assertIn("no provenance events", out)
#|
#|    def test_bulletins_and_doctor(self):
#|        rc, out = self.cli("bulletins")
#|        self.assertIn("Table file_audit not found", out)
#|        self.assertIn("(Write audit row", out)
#|        rc, out = self.cli("doctor", "--offline")
#|        self.assertIn("[OK  ] NiFi API", out)
#|        self.assertIn("[OK  ] logs", out)
#|
#|    def test_health(self):
#|        rc, out = self.cli("health")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("[error] back-pressure: queue Extract fields → Validate order in NiFi Flow/Vendor JSON Ingestion is at 100%", out)
#|        self.assertIn("[error] stuck-queue: 5 FlowFile(s) waiting in Validate order → Write rejects", out)
#|        self.assertIn("the destination processor is STOPPED", out)
#|        self.assertIn("(Write rejects `p-reject` in", out)
#|        self.assertIn("invalid-processor: Archive order (PutDatabaseRecord) in NiFi Flow is INVALID: 'Table Name' validated against", out)
#|        self.assertIn("service-not-enabled: controller service UnusedWriter is DISABLED", out)
#|        self.assertIn("[error] disk: content repository default at 96%", out)
#|        self.assertIn("[warn] heap: JVM heap at 91%", out)
#|        self.assertIn("[error] cluster: only 2 of 3 cluster nodes connected", out)
#|        self.assertEqual(out.index("[error]") < out.index("[warn]"), True)  # errors first
#|
#|    def test_daily_report(self):
#|        rc, out = self.cli("report", "--hours", "100000")
#|        self.assertIn("# NiFi daily report", out)
#|        self.assertIn("## Live NiFi health", out)
#|        self.assertIn("stuck-queue", out)
#|        self.assertIn("## New error patterns (first seen in this window)", out)
#|        self.assertIn("cause: SQLSyntaxErrorException", out)
#|        self.assertIn("Launched Apache NiFi", out)
#|        html_path = Path(self.tmp) / "report.html"
#|        rc, out = self.cli("report", "--hours", "100000", "--html", str(html_path))
#|        page = html_path.read_text(encoding="utf-8")
#|        self.assertTrue(page.startswith("<!doctype html>"))
#|        self.assertIn("<h2>Most frequent errors</h2>", page)
#|        rc, out = self.cli("report", "--send")
#|        self.assertIn("nothing to send", out)
#|
#|    def test_report_delivery(self):
#|        import http.server
#|        import socketserver
#|        import threading
#|        from nifikb import report as rp
#|        posted, mails = [], []
#|
#|        class Hook(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def do_POST(self):
#|                posted.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
#|                self.send_response(200)
#|                self.end_headers()
#|
#|        class Smtp(socketserver.StreamRequestHandler):
#|            def handle(self):
#|                w = lambda s: self.wfile.write((s + "\r\n").encode())
#|                w("220 fake")
#|                data, in_data = [], False
#|                for raw in self.rfile:
#|                    line = raw.decode().rstrip("\r\n")
#|                    if in_data:
#|                        if line == ".":
#|                            in_data = False
#|                            mails.append("\n".join(data))
#|                            w("250 ok")
#|                        else:
#|                            data.append(line)
#|                        continue
#|                    cmd = line[:4].upper()
#|                    if cmd in ("EHLO", "HELO"):
#|                        w("250 fake")
#|                    elif cmd == "DATA":
#|                        in_data = True
#|                        w("354 go")
#|                    elif cmd == "QUIT":
#|                        w("221 bye")
#|                        return
#|                    else:
#|                        w("250 ok")
#|
#|        hook = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hook)
#|        smtp = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Smtp)
#|        for srv in (hook, smtp):
#|            threading.Thread(target=srv.serve_forever, daemon=True).start()
#|        try:
#|            os.environ["NIFIKB_TEST_HOOK"] = f"http://127.0.0.1:{hook.server_address[1]}/hook"
#|            cfg = dict(self.cfg, report={"email_to": ["team@acme.test"], "email_from": "kb@acme.test", "smtp_host": "127.0.0.1",
#|                                         "smtp_port": smtp.server_address[1], "webhook_url_env": "NIFIKB_TEST_HOOK"})
#|            r = {"title": "NiFi daily report — test", "stats": {"errors": 3}, "sections": [("Most frequent errors", ["x3 boom"])]}
#|            done = rp.send(cfg, r)
#|            self.assertEqual(done, ["e-mailed to team@acme.test", "posted to the webhook"])
#|            self.assertIn("x3 boom", posted[0]["text"])
#|            self.assertIn("Subject: NiFi daily report", mails[0])
#|            self.assertIn("text/html", mails[0])
#|        finally:
#|            hook.shutdown()
#|            smtp.shutdown()
#|            smtp.server_close()
#|            hook.server_close()
#|
#|    def test_versions(self):
#|        rc, out = self.cli("versions")
#|        self.assertIn("NiFi Flow / Vendor JSON Ingestion: registry flow f1 (bucket b1), deployed v3", out)
#|        self.assertIn("live state: STALE - A newer version (4) is available", out)
#|        self.assertIn("alice: switch vendor to API v2", out)
#|        self.assertIn("bob: add order validation  <- deployed", out)
#|        rc, out = self.cli("health")
#|        self.assertIn("version-state: process group NiFi Flow / Vendor JSON Ingestion (registry flow vendor-json, v3): a newer version exists", out)
#|        doc = next((Path(self.cfg["output"]["dir"]) / "flows").glob("*vendor-json*.md")).read_text(encoding="utf-8")
#|        self.assertIn("version-controlled: flow f1 v3 (bucket b1)", doc)
#|
#|    def test_bad_password(self):
#|        from nifikb import nifiapi
#|        c = nifiapi.Client({"url": self.fake.url, "username": "admin", "password": "wrong"})
#|        with self.assertRaises(nifiapi.NiFiApiError) as e:
#|            c.about()
#|        self.assertIn("authentication failed", str(e.exception))
#|
#|
#|class TestInvestigate(unittest.TestCase):
#|    """The one-call investigation: provenance drop, file log errors, structure errors, code line, drift - ranked."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import FakeNiFi, metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        logdir = Path(cls.tmp) / "logs"
#|        logdir.mkdir()
#|        (logdir / "nifi-app.log").write_text(LOG_SAMPLE.replace("inst-p-audit-0000-0000-000000000000", "inst-p-audit")
#|                                             .replace("orders_0926.json", "SALES_20260926.csv"), encoding="utf-8")
#|        cls.fake = FakeNiFi()
#|        cls.fake.EVENTS = [dict(e, filename="SALES_20260926.csv") if e["filename"] == "orders_0926.json" else e for e in FakeNiFi.EVENTS]
#|        os.environ["NIFIKB_TEST_NIFI_PW"] = "pw123456789"
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        with open(cls.cfg_path, "a", encoding="utf-8") as f:
#|            f.write(f'\n[logs]\ndirs = ["{logdir.as_posix()}"]\n[nifi_api]\nurl = "{cls.fake.url}"\nusername = "admin"\n'
#|                    f'password_env = "NIFIKB_TEST_NIFI_PW"\n')
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.fake.stop()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_ranked_report(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260926.csv", "--error", "Structure mismatch",
#|                          "--headers", "ORDER_NO", "CUSTNAME", "AMOUNT")
#|        self.assertEqual(rc, 0, out)
#|        ranked = out.split("## Most likely causes")[1].split("##")[0]
#|        lines = [ln for ln in ranked.splitlines() if ln[:2].rstrip(".").isdigit()]
#|        self.assertIn("DROPPED at Write rejects (PutFile): Auto-Terminated by failure Relationship", lines[0])
#|        self.assertIn("load audit: last load FAILED - /landing/pos/SALES_20260926.csv, status FAILED, at 2026-09-26 02:14:00, 0 rows, "
#|                      "error: Column count mismatch at line 12", lines[1])
#|        self.assertIn("logged ERROR x1 for this file", lines[2])
#|        self.assertIn("SQLSyntaxErrorException", lines[2])
#|        self.assertIn("## Load audit (FILE_LOAD_AUDIT)", out)
#|        self.assertTrue(any("header 'CUSTNAME' differs from 'CUST_NAME'" in ln for ln in lines))
#|        self.assertTrue(any("MetadataLookup.java:" in ln for ln in lines))
#|        self.assertIn("## Provenance (what happened to the FlowFile)", out)
#|        self.assertIn("## Metadata (config tables)", out)
#|        self.assertNotIn("tok-SECRET-9", out)
#|
#|    def test_audit_cli_and_doctor(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "audit", "--file", "SALES_20260925.csv")
#|        self.assertIn("load audit table FILE_LOAD_AUDIT (file column FILE_NAME, status LOAD_STATUS, time LOAD_TS)", out)
#|        self.assertIn("status SUCCESS, at 2026-09-25 02:10:00, 1200 rows", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "audit", "--definition", "1")
#|        self.assertIn("x /landing/pos/SALES_20260926.csv, status FAILED", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "doctor", "--offline")
#|        self.assertIn("[OK  ] load audit: FILE_LOAD_AUDIT: file FILE_NAME, status LOAD_STATUS, time LOAD_TS, error ERROR_MSG", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260101.csv")
#|        self.assertIn("no load-audit row for SALES_20260101.csv", out)
#|
#|    def test_not_picked_up(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260101.csv")
#|        self.assertIn("no provenance events for 'SALES_20260101.csv': it never entered NiFi under that name", out)
#|
#|    def test_web_page(self):
#|        import threading
#|        import urllib.request
#|        from http.server import ThreadingHTTPServer
#|        from nifikb.web import App, make_handler
#|        cfg = load_config(self.cfg_path)
#|        os.environ["NIFIKB_TEST_WEB_PW"] = "s3cret-web"
#|        cfg["web"] = {"user": "support", "password_env": "NIFIKB_TEST_WEB_PW"}
#|        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(cfg)))
#|        threading.Thread(target=server.serve_forever, daemon=True).start()
#|        base = f"http://127.0.0.1:{server.server_address[1]}"
#|        auth = {"Authorization": "Basic " + __import__("base64").b64encode(b"support:s3cret-web").decode()}
#|
#|        def get(path, data=None, headers=None, ctype=None):
#|            req = urllib.request.Request(base + path, data=data, headers=dict(auth if headers is None else headers))
#|            if ctype:
#|                req.add_header("Content-Type", ctype)
#|            with urllib.request.urlopen(req, timeout=60) as r:
#|                return r.read().decode("utf-8")
#|        try:
#|            with self.assertRaises(urllib.error.HTTPError) as e:
#|                get("/", headers={})
#|            self.assertEqual(e.exception.code, 401)
#|            self.assertIn("Investigate a problem", get("/"))
#|            page = get("/investigate", data=urllib.parse.urlencode({"file": "SALES_20260926.csv", "headers": "ORDER_NO,CUSTNAME"}).encode(),
#|                       ctype="application/x-www-form-urlencoded")
#|            self.assertIn("<ol><li>FlowFile u-1 DROPPED at Write rejects", page)
#|            self.assertIn("<h2>Provenance (what happened to the FlowFile)</h2>", page)
#|            boundary = "----nifikbtest"
#|            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\nSALES_20260927.csv\r\n"
#|                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"sample\"; filename=\"SALES_20260927.csv\"\r\n"
#|                    f"Content-Type: text/csv\r\n\r\nORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\r\nabc,A,1,2026-09-27,EU\r\n--{boundary}--\r\n").encode()
#|            page = get("/investigate", data=body, ctype=f"multipart/form-data; boundary={boundary}")
#|            self.assertIn("&#x27;ORDER_NO&#x27; is not a valid INTEGER", page)
#|            page = get("/search?q=" + urllib.parse.quote("<script>alert(1)</script>"))
#|            self.assertNotIn("<script>alert(1)</script>", page)
#|            self.assertIn("&lt;script&gt;", page)
#|            self.assertIn("<h1>NiFi daily report", get("/report"))
#|            self.assertIn("stuck-queue", get("/health"))
#|        finally:
#|            server.shutdown()
#|            server.server_close()
#|
#|    def test_eval_harness(self):
#|        cases = Path(self.tmp) / "cases.toml"
#|        cases.write_text('''
#|[[case]]
#|id = "hit"
#|ticket = "SALES of 26 Sep did not load"
#|file = "SALES_20260926.csv"
#|headers = ["ORDER_NO", "CUSTNAME", "AMOUNT"]
#|expect_any = ["CUSTNAME"]
#|top = 5
#|answer_expect = ["CUST_NAME"]
#|
#|[[case]]
#|id = "miss"
#|file = "SALES_20260926.csv"
#|expect_any = ["something that is not the cause"]
#|''', encoding="utf-8")
#|        agent = f'"{sys.executable}" -c "import sys; t = sys.stdin.read(); print(\'Cause: rename CUST_NAME\' if \'CUSTNAME\' in t else \'no idea\')"'
#|        rc, out = run_cli("--config", str(self.cfg_path), "eval", "--cases", str(cases), "--agent", agent,
#|                          "--save", str(Path(self.tmp) / "eval.json"))
#|        self.assertEqual(rc, 2)  # one case fails on purpose
#|        self.assertIn("PASS hit: cause at rank", out)
#|        self.assertIn("agent ok", out)
#|        self.assertIn("FAIL miss", out)
#|        self.assertIn("tools: 1/2 cases have the true cause in their top ranks", out)
#|        self.assertIn("agent: 1/2 answers name the true cause", out)
#|        saved = json.loads((Path(self.tmp) / "eval.json").read_text(encoding="utf-8"))
#|        self.assertEqual([r["id"] for r in saved["results"]], ["hit", "miss"])
#|
#|    def test_mcp_investigate(self):
#|        from nifikb.mcp import Server
#|        text, err = Server(str(self.cfg_path)).call("investigate", {"file": "SALES_20260926.csv", "headers": ["ORDER_NO", "CUSTNAME"]})
#|        self.assertFalse(err, text)
#|        self.assertIn("## Most likely causes", text)
#|
#|
#|class TestConfigChanges(unittest.TestCase):
#|    """Config-row changes between metadata snapshots: live 'changed since snapshot', change log, per-definition history."""
#|
#|    def test_changes_tracked(self):
#|        from fixtures_builder import metadata_flow
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            cfg = load_config(cfg_path)
#|            build(cfg, log=lambda m: None)
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            db.executescript("""
#|                UPDATE OBJ_STRUCTURE SET COL_LENGTH = 20 WHERE OBJ_ID = 1 AND COL_NAME = 'CUST_NAME';
#|                INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES (1, 'LOAD_TS', 'TEXT', 6, NULL, 'Y');
#|                UPDATE SOURCE_FEED_CONFIG SET REMOTE_DIR = '/outbound/sales_v2', SFTP_PASSWORD = 'N3wS3cret!' WHERE FEED_ID = 10;
#|                UPDATE OBJ_STRUCTURE SET COL_LENGTH = 99 WHERE OBJ_ID = 2 AND COL_NAME = 'NAME';
#|            """)
#|            db.commit()
#|            db.close()
#|
#|            rc, out = run_cli("--config", str(cfg_path), "diagnose", "--file", "SALES_20260926.csv", "--live")
#|            self.assertIn("Config rows changed since the snapshot of", out)
#|            self.assertIn("CUST_NAME): COL_LENGTH 50 → 20", out)
#|            self.assertIn("LOAD_TS", out)
#|            self.assertIn("REMOTE_DIR /outbound/sales → /outbound/sales_v2", out)
#|            self.assertNotIn("N3wS3cret!", out)
#|            self.assertNotIn("SFTP_PASSWORD", out.split("Config rows changed since")[1].split("\n\n")[0])
#|            self.assertNotIn("COL_LENGTH 100 → 99", out)  # other definition
#|
#|            build(cfg, refresh_db=True, log=lambda m: None)
#|            log = (Path(cfg["output"]["dir"]) / "CHANGELOG.md").read_text(encoding="utf-8")
#|            self.assertIn("config OBJ_STRUCTURE:", log)
#|            self.assertIn("COL_LENGTH 50 → 20", log)
#|            rc, out = run_cli("--config", str(cfg_path), "diagnose", "--feed", "pos_sales_feed")
#|            self.assertIn("Recent config-row changes for this definition", out)
#|            self.assertIn("REMOTE_DIR /outbound/sales → /outbound/sales_v2", out)
#|            self.assertNotIn("COL_LENGTH 100 → 99", out)
#|            self.assertFalse(b"N3wS3cret!" in (Path(cfg["output"]["dir"]) / "kb.sqlite").read_bytes())
#|
#|    def test_metadata_refresh_interval(self):
#|        from fixtures_builder import metadata_flow
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp, flow=metadata_flow(), with_metadata=True))
#|            build(cfg, log=lambda m: None)
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "up-to-date")
#|            cfg["metadata"]["refresh_hours"] = 0  # always due -> config rows re-read, flow unchanged
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "built")
#|
#|
#|class TestJavaAndLineage(unittest.TestCase):
#|    """Company-style Java custom processors (base classes, constants, attribute maps), the deployed NAR's bytecode,
#|    and attribute lineage through a metadata-driven flow."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import STD_MANIFEST, lineage_flow, make_nar
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=lineage_flow(), with_metadata=True)
#|        make_nar(Path(cls.tmp) / "nars" / "nifi-standard-nar-1.27.0.nar", STD_MANIFEST, group="org.apache.nifi", artifact="nifi-standard-nar")
#|        cls.cfg = load_config(cls.cfg_path)
#|        build(cls.cfg, log=lambda m: None)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|        db = sqlite3.connect(cls.kb / "kb.sqlite")
#|        cls.found = db.execute("SELECT kind, component_id, message FROM findings").fetchall()
#|        db.close()
#|        cls.doc = (cls.kb / "custom-code" / "MetadataLookup.md").read_text(encoding="utf-8")
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def of(self, kind):
#|        return [(c, m) for k, c, m in self.found if k == kind]
#|
#|    def test_inheritance_and_constants(self):
#|        self.assertIn("extends AbstractMetadataProcessor → AbstractProcessor", self.doc)
#|        self.assertIn("| metadata-db | Metadata DB |  | Y | service DBCPService (from AbstractMetadataProcessor)", self.doc)
#|        self.assertIn("| lookup-mode | Lookup Mode | by-file |  | one of by-file, by-feed |", self.doc)
#|        self.assertIn("- `failure`: Lookup failed (from AbstractMetadataProcessor)", self.doc)
#|        self.assertIn("- `not found`: no definition", self.doc)
#|        self.assertIn("**Does:** Looks up the object definition; structure and feed config", self.doc)  # ';' inside the annotation
#|
#|    def test_attributes_from_code(self):
#|        self.assertIn("- reads: `filename` (MetadataLookup.java:", self.doc)
#|        self.assertIn("`table_name` (MetadataLookup.java:", self.doc)
#|        self.assertIn("`delimiter` (MetadataLookup.java:", self.doc)
#|        flow = (self.kb / "flows" / "root.md").read_text(encoding="utf-8")
#|        section = flow.split('<a id="c-l-meta"></a>')[1].split("### ")[0]
#|        self.assertIn("writes attributes: delimiter, structure.json, table_name", section)
#|        self.assertIn("reads attributes: filename", section)
#|
#|    def test_maven_and_deployment(self):
#|        self.assertIn("Maven module: `com.acme:acme-meta-processors:2.0.0`", self.doc)
#|        self.assertIn("Packaged by NAR module: `acme-meta-nar:2.0.0`", self.doc)
#|        self.assertIn("deployed NAR: 2.0.0 (acme-meta-nar-2.0.0.nar)", self.doc)
#|        self.assertIn("⚠ In the repo source but **not in the deployed build**: attribute 'delimiter'", self.doc)
#|        self.assertIn("Tables in its SQL: `obj_structure`", self.doc)
#|        self.assertEqual([c for c, _ in self.of("custom-source-drift")], ["p-lookup-meta"])
#|        self.assertIn("acme-meta-nar 1.9.0 but lib has 2.0.0", self.of("bundle-version")[0][1])
#|        self.assertFalse(self.of("custom-nar-missing"))
#|
#|    def test_registration(self):
#|        from nifikb import code as codemod
#|        idx = codemod.CodeIndex([codemod.index_file(p) for p in codemod.iter_code_files([Path(self.tmp) / "meta-repo"])])
#|        self.assertTrue(idx.by_fqcn["com.acme.meta.MetadataLookup"][0]["component"]["registered"])
#|        legacy = idx.by_fqcn["com.acme.meta.LegacyMetadataLookup"][0]["component"]  # a processor only through its base class
#|        self.assertFalse(legacy["registered"])
#|        self.assertEqual(legacy["kind"], "PROCESSOR")
#|        self.assertNotIn("com.acme.meta.base.MetaConstants", idx.by_fqcn)
#|        self.assertNotIn("com.acme.meta.MockUpstream", idx.by_fqcn)             # src/test is not deployed code
#|        self.assertEqual(idx.by_fqcn["com.acme.meta.CachingMetadataService"][0]["component"]["kind"], "CONTROLLER_SERVICE")
#|        self.assertEqual(idx.implementers("MetadataService"), ["com.acme.meta.CachingMetadataService"])
#|        self.assertIn("service MetadataService (implemented by CachingMetadataService)", self.doc)
#|
#|    def test_attribute_lineage(self):
#|        misnamed = self.of("attribute-misnamed")
#|        self.assertEqual([c for c, _ in misnamed], ["l-ua"])
#|        self.assertIn("reads ${tableName}", misnamed[0][1])
#|        self.assertIn("'table_name'", misnamed[0][1])
#|        unset = self.of("attribute-unset")
#|        self.assertEqual([(c, "${target_catalog}" in m) for c, m in unset], [("l-put", True)])
#|        self.assertFalse(any("${mode}" in m for _, m in unset + misnamed))  # guarded with isEmpty()
#|        self.assertFalse(any(m.startswith("reads ${target.table}") for _, m in unset + misnamed))  # set upstream by UpdateAttribute
#|
#|    def test_error_text_search(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "Structure mismatch")
#|        self.assertIn("MetadataLookup.java:", out)
#|        self.assertIn("custom-code/MetadataLookup.md", out)
#|
#|    def test_class_strings_parser(self):
#|        from fixtures_builder import class_file
#|        from nifikb.catalog import class_strings
#|        self.assertEqual(class_strings(class_file("a.B", ["x", "SELECT 1 FROM t", "\x01 and \x01"])), ["x", "SELECT 1 FROM t", "{} and {}"])
#|        self.assertEqual(class_strings(b"not a class"), [])
#|
#|
#|class TestSparkSubmit(unittest.TestCase):
#|    def test_script_submitting_spark(self):
#|        from fixtures_builder import proc
#|        flow = nested_flow()
#|        flow["rootGroup"]["processors"].append(proc(
#|            "p-spark", "Run sales aggregation", "org.apache.nifi.processors.standard.ExecuteStreamCommand",
#|            {"Command Path": "bash", "Command Arguments": "/opt/jobs/submit_sales.sh ${filename}"}, auto=["original"]))
#|        with tempfile.TemporaryDirectory() as tmp:
#|            repo = Path(tmp) / "jobs-repo"
#|            repo.mkdir()
#|            (repo / "submit_sales.sh").write_text(
#|                "#!/bin/bash\nRUN_DATE=$1\nspark-submit --master yarn --deploy-mode cluster \\\n  --class com.acme.etl.SalesAggregate "
#|                "--name sales-agg \\\n  /opt/jobs/sales-etl.jar --date $RUN_DATE\n", encoding="utf-8")
#|            cfg_path = make_env(tmp, flow=flow, with_db=False)
#|            text = cfg_path.read_text(encoding="utf-8").replace('repos = ["', f'repos = ["{repo.as_posix()}", "')
#|            cfg_path.write_text(text, encoding="utf-8")
#|            cfg = load_config(cfg_path)
#|            build(cfg, log=lambda m: None)
#|            kb = Path(cfg["output"]["dir"])
#|            flow_doc = (kb / "flows" / "root.md").read_text(encoding="utf-8")
#|            self.assertIn("submits Spark job: com.acme.etl.SalesAggregate in /opt/jobs/sales-etl.jar (yarn, cluster)", flow_doc)
#|            script_doc = next((kb / "scripts").glob("submit-sales*.md")).read_text(encoding="utf-8")
#|            self.assertIn("## Spark jobs submitted", script_doc)
#|            self.assertIn("name `sales-agg`", script_doc)
#|            rc, out = run_cli("--config", str(cfg_path), "search", "SalesAggregate")
#|            self.assertIn("submit_sales.sh", out)
#|
#|
#|class TestVersionChange(unittest.TestCase):
#|    def test_registry_version_in_changelog(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp, with_db=False))
#|            build(cfg, log=lambda m: None)
#|            flow = nested_flow()
#|            flow["rootGroup"]["processGroups"][0]["versionedFlowCoordinates"]["version"] = 4
#|            with gzip.open(Path(tmp) / "flow.json.gz", "wt", encoding="utf-8") as f:
#|                json.dump(flow, f)
#|            build(cfg, log=lambda m: None)
#|            log = (Path(cfg["output"]["dir"]) / "CHANGELOG.md").read_text(encoding="utf-8")
#|            self.assertIn("process group NiFi Flow / Vendor JSON Ingestion: registry version 3 → 4", log)
#|
#|
#|class TestCompare(unittest.TestCase):
#|    """Environment comparison: flow (components, properties, parameters) and config rows, 'works in UAT, fails in PROD'."""
#|
#|    def test_compare_env(self):
#|        from fixtures_builder import metadata_flow, proc
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            # UAT: a copy of the config db with a changed delimiter, a changed structure row and a secret change
#|            shutil.copy(Path(tmp) / "meta.db", Path(tmp) / "uat.db")
#|            db = sqlite3.connect(Path(tmp) / "uat.db")
#|            db.executescript("UPDATE OBJ_DEFINITION SET DELIMITER = '|' WHERE OBJ_ID = 1;"
#|                             "UPDATE OBJ_STRUCTURE SET COL_LENGTH = 80 WHERE OBJ_ID = 1 AND COL_NAME = 'CUST_NAME';"
#|                             "UPDATE SOURCE_FEED_CONFIG SET SFTP_PASSWORD = 'OtherSecret1!';"
#|                             "UPDATE OBJ_DEFINITION SET ACTIVE_FLAG = 'N' WHERE OBJ_ID = 3;")
#|            db.commit()
#|            db.close()
#|            # UAT flow: another bucket parameter, a changed property, a stopped processor, one extra processor
#|            flow = metadata_flow()
#|            flow["parameterContexts"][0]["parameters"][0]["value"] = "acme-orders-uat"
#|            flow["rootGroup"]["processGroups"][0]["processors"][0]["properties"]["vendor"] = "$.vendorName"
#|            flow["rootGroup"]["processors"][-1]["scheduledState"] = "DISABLED"
#|            flow["rootGroup"]["processors"].append(proc("p-extra", "Debug log", "org.apache.nifi.processors.standard.LogAttribute", {}))
#|            with gzip.open(Path(tmp) / "uat.json.gz", "wt", encoding="utf-8") as f:
#|                json.dump(flow, f)
#|            with open(cfg_path, "a", encoding="utf-8") as f:
#|                f.write(f'\n[[databases]]\nname = "metadata_uat"\nkind = "sqlite"\ndatabase = "{(Path(tmp) / "uat.db").as_posix()}"\n'
#|                        f'\n[environments.uat]\nflow_file = "uat.json.gz"\ndb = "metadata_uat"\n')
#|            build(load_config(cfg_path), log=lambda m: None)
#|            rc, out = run_cli("--config", str(cfg_path), "compare", "--env", "uat")
#|            self.assertEqual(rc, 0, out)
#|            self.assertIn("only in uat: NiFi Flow :: Debug log [LogAttribute]", out)
#|            self.assertIn("'vendor' = `$.vendor` (here) vs `$.vendorName` (uat)", out)
#|            self.assertIn("parameter vendor-params :: s3.bucket = `acme-orders-raw` (here) vs `acme-orders-uat` (uat)", out)
#|            self.assertIn("Metadata lookup [MetadataLookup]: state RUNNING (here) vs DISABLED (uat)", out)
#|            self.assertIn("DELIMITER , → |", out)
#|            self.assertIn("COL_LENGTH 50 → 80", out)
#|            self.assertNotIn("OtherSecret1!", out)
#|            self.assertNotIn("Sup3rS3cret!", out)
#|            self.assertNotIn("SFTP_PASSWORD", out)
#|            # one definition only
#|            rc, out = run_cli("--config", str(cfg_path), "compare", "--env", "uat", "--what", "config", "--key", "SALES_20260926.csv")
#|            self.assertIn("DELIMITER , → |", out)
#|            self.assertNotIn("ACTIVE_FLAG", out)
#|            self.assertNotIn("## Flow", out)
#|            rc, out = run_cli("--config", str(cfg_path), "compare", "--env", "prod")
#|            self.assertEqual(rc, 2)
#|            self.assertIn("no [environments.prod]", out)
#|
#|
#|class TestOnboard(unittest.TestCase):
#|    """New-feed validator: proposed config rows checked before anyone inserts them."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def write(self, name, text):
#|        path = Path(self.tmp) / name
#|        path.write_text(text, encoding="utf-8")
#|        return path
#|
#|    def test_good_proposal(self):
#|        self.write("CUSTOMERS_EXTRA_20260927.csv", "CUST_ID,NAME,EMAIL\n1,Ann,ann@example.com\n")
#|        path = self.write("good.toml", """
#|example_file = "CUSTOMERS_EXTRA_20260927.csv"
#|sample = "CUSTOMERS_EXTRA_20260927.csv"
#|[definition]
#|OBJ_ID = 7
#|FILE_NAME = "CUSTOMERS_EXTRA_YYYYMMDD.csv"
#|TABLE_NAME = "stg_customers"
#|SOURCE_SYSTEM = "CRM"
#|DELIMITER = ","
#|ACTIVE_FLAG = "Y"
#|[[structure]]
#|COL_NAME = "CUST_ID"
#|DATA_TYPE = "INT"
#|COL_SEQ = 1
#|MANDATORY_FLAG = "Y"
#|[[structure]]
#|COL_NAME = "NAME"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 2
#|COL_LENGTH = 100
#|[[structure]]
#|COL_NAME = "EMAIL"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 3
#|COL_LENGTH = 200
#|""")
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path))
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("READY to insert", out)
#|        self.assertIn("INSERT INTO OBJ_DEFINITION (OBJ_ID, FILE_NAME, TABLE_NAME, SOURCE_SYSTEM, DELIMITER, ACTIVE_FLAG) "
#|                      "VALUES (7, 'CUSTOMERS_EXTRA_YYYYMMDD.csv', 'stg_customers', 'CRM', ',', 'Y');", out)
#|        self.assertIn("INSERT INTO OBJ_STRUCTURE (COL_NAME, DATA_TYPE, COL_SEQ, MANDATORY_FLAG, OBJ_ID) VALUES ('CUST_ID', 'INT', 1, 'Y', 7);", out)
#|
#|    def test_bad_proposal(self):
#|        self.write("SALES_20260927.csv", "ORDER_NO;CUST_NAME;AMOUNT\n1;Bob;3.5\n")
#|        path = self.write("bad.toml", """
#|example_file = "SALES_20260927.csv"
#|sample = "SALES_20260927.csv"
#|like = "SALES_YYYYMMDD.csv"
#|[definition]
#|OBJ_ID = 1
#|FILE_NAME = "SALES_YYYYMMDD.csv"
#|TABEL_NAME = "stg_sales"
#|[[structure]]
#|COL_NAME = "ORDER_NO"
#|DATA_TYPE = "INTEGER"
#|COL_SEQ = 1
#|[[structure]]
#|COL_NAME = "CUST_NAME"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 1
#|[[structure]]
#|COL_NAME = "AMOUNT"
#|DATA_TYPE = "MONEYZ"
#|COL_SEQ = "three"
#|[[rows.SOURCE_FEED_CONFIG]]
#|FEED_NAME = "pos_sales_feed_2"
#|SFTP_PASSWORD = "TopSecret123!"
#|""")
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path))
#|        self.assertEqual(rc, 1, out)
#|        self.assertIn("error(s) to fix first", out)
#|        self.assertIn("definition: OBJ_DEFINITION has no column 'TABEL_NAME' (did you mean 'TABLE_NAME'?)", out)
#|        self.assertIn("definition: OBJ_DEFINITION:1 already exists", out)
#|        self.assertIn("duplicate COL_SEQ value(s): [1]", out)
#|        self.assertIn("COL_SEQ = 'three' is not an integer", out)
#|        self.assertIn("'CUST_NAME' is VARCHAR without a length", out)
#|        self.assertIn("type 'MONEYZ' is not a usual type name", out)
#|        self.assertIn("SFTP_PASSWORD holds a secret", out)
#|        self.assertIn("SOURCE_SYSTEM, DELIMITER, ACTIVE_FLAG - the proposal leaves them empty", out)
#|        self.assertIn("fill COL_LENGTH, MANDATORY_FLAG - the proposal does not", out)
#|        self.assertNotIn("TopSecret123!", out)
#|        self.assertIn("/* set by DBA */ NULL", out)
#|        self.assertIn("sample:", out)
#|
#|    def test_ambiguous_and_pattern(self):
#|        path = self.write("amb.json", json.dumps({"example_file": "SALES_20260927.csv",
#|                                                  "definition": {"FILE_NAME": "SALES_*.csv", "TABLE_NAME": "stg_sales"},
#|                                                  "structure": [{"COL_NAME": "ORDER_NO", "DATA_TYPE": "INTEGER", "COL_SEQ": 1}]}))
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path))
#|        self.assertIn("already matches existing OBJ_DEFINITION row(s) OBJ_DEFINITION:1", out)
#|        self.assertIn("the definition id is not given", out)
#|        self.assertNotIn("duplicate-name", out)  # the target table may be shared
#|        self.assertIn("/* new id */ NULL", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path), "--example", "INVOICE_20260927.csv")
#|        self.assertIn("does not match the example file 'INVOICE_20260927.csv'", out)
#|
#|    def test_mcp_inline(self):
#|        from nifikb.mcp import Server
#|        text, err = Server(str(self.cfg_path)).call("check_new_feed", {"proposal": {
#|            "definition": {"OBJ_ID": 8, "FILE_NAME": "x_YYYYMMDD.csv", "TABLE_NAME": "stg_nothere"},
#|            "structure": [{"COL_NAME": "A", "DATA_TYPE": "INT", "COL_SEQ": 1}]}})
#|        self.assertIn("target stg_nothere", text)
#|
#|
#|FAKE_AWS = r'''
#|import json, os, sys, datetime
#|root = os.environ["FAKE_S3_ROOT"]
#|a = sys.argv[1:]
#|def opt(n):
#|    return a[a.index(n) + 1] if n in a else None
#|bucket = opt("--bucket")
#|if a[:2] == ["s3api", "list-objects-v2"]:
#|    out = []
#|    base = os.path.join(root, bucket)
#|    for d, _, files in os.walk(base):
#|        for f in files:
#|            p = os.path.join(d, f)
#|            key = os.path.relpath(p, base).replace(os.sep, "/")
#|            if key.startswith(opt("--prefix") or ""):
#|                out.append({"Key": key, "Size": os.path.getsize(p),
#|                            "LastModified": datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).isoformat()})
#|    print(json.dumps({"Contents": out}))
#|elif a[:2] == ["s3api", "get-object"]:
#|    lo, hi = opt("--range").split("=")[1].split("-")
#|    with open(os.path.join(root, bucket, opt("--key")), "rb") as f:
#|        f.seek(int(lo))
#|        data = f.read(int(hi) - int(lo) + 1)
#|    open(a[-1] if not a[-1].startswith("--") else a[a.index("--range") + 2], "wb").write(data)
#|    print("{}")
#|else:
#|    sys.exit(2)
#|'''
#|
#|
#|class TestTarget(unittest.TestCase):
#|    """Target side of a load: HDFS / S3 / local listings, the Parquet footer schema vs the structure rows."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        lake = Path(cls.tmp) / "lake" / "stg_sales" / "dt=2026-09-26"
#|        lake.mkdir(parents=True)
#|        shutil.copy(FIXTURES / "stg_sales.parquet", lake / "SALES_20260926.parquet")
#|        (lake / "_SUCCESS").write_bytes(b"")
#|        db = sqlite3.connect(Path(cls.tmp) / "meta.db")
#|        db.execute("ALTER TABLE OBJ_DEFINITION ADD COLUMN HDFS_PATH TEXT")
#|        db.execute("UPDATE OBJ_DEFINITION SET HDFS_PATH = ? WHERE OBJ_ID = 1",
#|                   ((Path(cls.tmp) / "lake" / "stg_sales").as_posix() + "/dt=${now():format('yyyy-MM-dd')}/",))
#|        db.commit()
#|        db.close()
#|        with open(cls.cfg_path, "a", encoding="utf-8") as f:
#|            f.write("\n[targets]\n")
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_parquet_footer(self):
#|        from nifikb.target import parquet_schema
#|        cols, info = parquet_schema((FIXTURES / "stg_sales.parquet").read_bytes())
#|        self.assertEqual([(c["name"], c["type"]) for c in cols],
#|                         [("ORDER_NO", "BIGINT"), ("CUST_NAME", "STRING"), ("AMOUNT", "DECIMAL(10,2)"), ("ORDER_DT", "STRING"), ("LOAD_TS", "STRING")])
#|        self.assertEqual(info["rows"], 2)
#|
#|    def test_local_target_and_investigate(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "target", "--file", "SALES_20260926.csv")
#|        self.assertEqual(rc, 1, out)  # REGION was not written
#|        self.assertIn("structure field(s) not in the written Parquet (SALES_20260926.parquet): REGION", out)
#|        self.assertIn("'ORDER_DT' is DATE in the structure but STRING in the Parquet", out)
#|        self.assertIn("Parquet has column(s) not in the structure (often load metadata): LOAD_TS", out)
#|        self.assertIn("outputs for this file (1 found)", out)
#|        self.assertNotIn("_SUCCESS", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260926.csv")
#|        self.assertIn("SALES_YYYYMMDD.csv target: structure field(s) not in the written Parquet", out)
#|        self.assertIn("## Target output (SALES_YYYYMMDD.csv)", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "target", "--location", str(Path(self.tmp) / "lake" / "nothing"))
#|        self.assertIn("does not exist", out)
#|
#|    def test_webhdfs(self):
#|        import http.server
#|        import threading
#|        import urllib.parse as up
#|        base = Path(self.tmp) / "lake"
#|
#|        class H(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def do_GET(self):
#|                u = up.urlparse(self.path)
#|                q = dict(up.parse_qsl(u.query))
#|                p = base / up.unquote(u.path).removeprefix("/webhdfs/v1/lake/").strip("/")
#|                if not p.exists():
#|                    self.send_response(404)
#|                    self.end_headers()
#|                    self.wfile.write(b'{"RemoteException":{"exception":"FileNotFoundException"}}')
#|                    return
#|                if q["op"] == "LISTSTATUS":
#|                    st = [{"pathSuffix": c.name, "type": "DIRECTORY" if c.is_dir() else "FILE", "length": 0 if c.is_dir() else c.stat().st_size,
#|                           "modificationTime": int(c.stat().st_mtime * 1000)} for c in p.iterdir()]
#|                    body = json.dumps({"FileStatuses": {"FileStatus": st}}).encode()
#|                else:
#|                    data = p.read_bytes()
#|                    off = int(q.get("offset", 0))
#|                    body = data[off:off + int(q.get("length", len(data)))]
#|                self.send_response(200)
#|                self.end_headers()
#|                self.wfile.write(body)
#|
#|        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
#|        threading.Thread(target=srv.serve_forever, daemon=True).start()
#|        try:
#|            cfg = self.cfg_path.read_text(encoding="utf-8").replace("\n[targets]\n", f'\n[targets]\nhdfs_url = "http://127.0.0.1:{srv.server_port}/webhdfs/v1"\nhdfs_user = "nifikb"\n')
#|            path = Path(self.tmp) / "webhdfs.toml"
#|            path.write_text(cfg, encoding="utf-8")
#|            rc, out = run_cli("--config", str(path), "target", "--location", "hdfs://nameservice1/lake/stg_sales/", "--key", "SALES_20260926.csv")
#|            self.assertIn("via webhdfs", out)
#|            self.assertIn("SALES_20260926.parquet", out)
#|            self.assertIn("not in the written Parquet (SALES_20260926.parquet): REGION", out)
#|            rc, out = run_cli("--config", str(path), "target", "--location", "hdfs:///lake/missing/")
#|            self.assertIn("does not exist in HDFS", out)
#|        finally:
#|            srv.shutdown()
#|
#|    def test_s3_cli(self):
#|        s3 = Path(self.tmp) / "s3" / "datalake" / "raw" / "stg_sales"
#|        s3.mkdir(parents=True)
#|        shutil.copy(FIXTURES / "stg_sales.parquet", s3 / "part-0000.parquet")
#|        fake = Path(self.tmp) / "fake_aws.py"
#|        fake.write_text(FAKE_AWS, encoding="utf-8")
#|        cfg = self.cfg_path.read_text(encoding="utf-8").replace(
#|            "\n[targets]\n", f'\n[targets]\ns3_cli = {json.dumps([sys.executable, str(fake)])}\nlocation_template = "s3://datalake/raw/{{table_lower}}/"\n')
#|        path = Path(self.tmp) / "s3.toml"
#|        path.write_text(cfg, encoding="utf-8")
#|        os.environ["FAKE_S3_ROOT"] = str(Path(self.tmp) / "s3")
#|        try:
#|            # OBJ_DEFINITION 3 (returns.csv) has no location column value: the template gives s3://datalake/raw/stg_returns/
#|            rc, out = run_cli("--config", str(path), "target", "--key", "returns.csv")
#|            self.assertIn("s3://datalake/raw/stg_returns/", out)
#|            self.assertIn("no data files under", out)
#|            rc, out = run_cli("--config", str(path), "target", "--location", "s3://datalake/raw/stg_sales/", "--key", "SALES_20260926.csv")
#|            self.assertIn("via s3", out)
#|            self.assertIn("s3://datalake/raw/stg_sales/part-0000.parquet", out)
#|            self.assertIn("REGION", out)
#|        finally:
#|            os.environ.pop("FAKE_S3_ROOT", None)
#|
#|
#|class TestTickets(unittest.TestCase):
#|    """Jira / ServiceNow: extract facts, investigate, draft a reply; post only with --post."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        import http.server
#|        import threading
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|        cls.posted, cls.auth = [], []
#|        test = cls
#|
#|        class H(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def reply(self, obj, raw=None):
#|                body = raw if raw is not None else json.dumps(obj).encode()
#|                self.send_response(200)
#|                self.send_header("Content-Type", "application/json")
#|                self.end_headers()
#|                self.wfile.write(body)
#|
#|            def do_GET(self):
#|                test.auth.append(self.headers.get("Authorization"))
#|                port = self.server.server_port
#|                if self.path.startswith("/rest/api/2/issue/NIFI-7"):
#|                    return self.reply({"key": "NIFI-7", "fields": {
#|                        "summary": "SALES_20260926.csv not loaded", "status": {"name": "Open"},
#|                        "description": "The POS file SALES_20260926.csv failed last night.\nError: Column count mismatch at line 12: "
#|                                       "expected 5, found 6\nHeaders sent: ORDER_NO, CUST_NAME, AMOUNT, ORDER_DT, REGION, EXTRA_COL\n"
#|                                       "Reach me at bob@acme.com",
#|                        "comment": {"comments": [{"body": "still failing today"}]},
#|                        "attachment": [{"filename": "SALES_20260926.csv", "size": 60,
#|                                        "content": f"http://127.0.0.1:{port}/secure/attachment/1/SALES_20260926.csv"},
#|                                       {"filename": "screenshot.png", "size": 10, "content": f"http://127.0.0.1:{port}/x.png"}]}})
#|                if self.path.startswith("/secure/attachment/1/"):
#|                    return self.reply(None, raw=b"ORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION,EXTRA_COL\n1,a,2.5,2026-09-26,EU,x\n")
#|                if self.path.startswith("/api/now/table/incident?"):
#|                    return self.reply({"result": [{"sys_id": "abc123", "number": "INC0010001", "short_description": "POS feed stuck",
#|                                                   "description": "Nothing arrived from pos_sales_feed since Monday", "state": "New"}]})
#|                if self.path.startswith("/api/now/attachment?"):
#|                    return self.reply({"result": []})
#|                self.send_response(404)
#|                self.end_headers()
#|
#|            def do_POST(self):
#|                test.posted.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
#|                self.reply({"id": "1"})
#|
#|            do_PATCH = do_POST
#|
#|        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
#|        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
#|        base = cls.cfg_path.read_text(encoding="utf-8")
#|        cls.jira = Path(cls.tmp) / "jira.toml"
#|        cls.jira.write_text(base + f'\n[tickets]\nkind = "jira"\nurl = "http://127.0.0.1:{cls.srv.server_port}"\n'
#|                                   'username = "bot@acme.com"\ntoken_env = "NIFIKB_TEST_TICKET_TOKEN"\n', encoding="utf-8")
#|        cls.snow = Path(cls.tmp) / "snow.toml"
#|        cls.snow.write_text(base + f'\n[tickets]\nkind = "servicenow"\nurl = "http://127.0.0.1:{cls.srv.server_port}"\n'
#|                                   'username = "nifikb"\npassword_env = "NIFIKB_TEST_TICKET_TOKEN"\n', encoding="utf-8")
#|        os.environ["NIFIKB_TEST_TICKET_TOKEN"] = "tok-123"
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.srv.shutdown()
#|        cls.srv.server_close()
#|        os.environ.pop("NIFIKB_TEST_TICKET_TOKEN", None)
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_extract(self):
#|        from nifikb import tickets
#|        facts = tickets.extract({"title": "load failed", "description": "file ORDERS_1.json and orders.csv\nfields: a | b | c\n"
#|                                 "java.sql.SQLException: Data too long for column 'x'"})
#|        self.assertEqual(facts["files"], ["ORDERS_1.json", "orders.csv"])
#|        self.assertEqual(facts["headers"], ["a", "b", "c"])
#|        self.assertIn("Data too long", facts["error"])
#|
#|    def test_jira_investigate_and_draft(self):
#|        self.posted.clear()
#|        rc, out = run_cli("--config", str(self.jira), "ticket", "NIFI-7")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("files=['SALES_20260926.csv']", out)
#|        self.assertIn("sample attachment=SALES_20260926.csv", out)
#|        self.assertIn("load audit: last load FAILED", out)
#|        self.assertIn("EXTRA_COL", out)
#|        self.assertIn("## Draft reply (not posted", out)
#|        self.assertNotIn("bob@acme.com", out.split("## Draft reply")[1])
#|        self.assertEqual(self.posted, [])
#|        self.assertTrue(any(a and a.startswith("Basic ") for a in self.auth))
#|        rc, out = run_cli("--config", str(self.jira), "ticket", "NIFI-7", "--post", "--no-attachments")
#|        self.assertIn("posted to NIFI-7", out)
#|        self.assertEqual(self.posted[0][0], "/rest/api/2/issue/NIFI-7/comment")
#|        self.assertIn("Automated first analysis (nifikb) for NIFI-7", self.posted[0][1]["body"])
#|
#|    def test_servicenow_feed(self):
#|        self.posted.clear()
#|        rc, out = run_cli("--config", str(self.snow), "ticket", "INC0010001")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("feeds=['pos_sales_feed']", out)
#|        self.assertIn("# Investigation: pos_sales_feed", out)
#|        rc, out = run_cli("--config", str(self.snow), "ticket", "INC0010001", "--post")
#|        self.assertEqual(self.posted[0][0], "/api/now/table/incident/abc123")
#|        self.assertIn("work_notes", self.posted[0][1])
#|        rc, out = run_cli("--config", str(self.snow), "ticket", "not a number")
#|        self.assertIn("does not look like a ServiceNow number", out)
#|
#|    def test_mcp_never_posts(self):
#|        from nifikb.mcp import TOOLS
#|        schema = next(t for t in TOOLS if t["name"] == "ticket")["inputSchema"]["properties"]
#|        self.assertNotIn("post", schema)
#|        rc, out = run_cli("--config", str(self.jira), "doctor", "--offline")
#|        self.assertIn("(posting only with `ticket <id> --post`)", out)
#|
#|
#|class TestLateFiles(unittest.TestCase):
#|    """Arrival patterns learned from the load audit: intra-day, daily (weekdays + time of day), weekly."""
#|
#|    def rows(self, times, link=None, name="F_{:%Y%m%d%H%M}.csv", failed=()):
#|        return [{"file": name.format(t), "when": t, "failed": t in failed, "link": link} for t in times]
#|
#|    def test_patterns(self):
#|        import datetime as dt
#|        from nifikb import late
#|        now = dt.datetime(2026, 9, 28, 9, 30)  # a Monday
#|        start = now - dt.timedelta(days=30)
#|        daily = [dt.datetime.combine((start + dt.timedelta(days=i)).date(), dt.time(2, 10 + i % 7)) for i in range(30)]
#|        daily = [d for d in daily if d.weekday() < 5 and d.date() < now.date()]
#|        hourly = [now - dt.timedelta(hours=6 + i) for i in range(48)][::-1]
#|        weekly = [now - dt.timedelta(days=12 + 7 * i) for i in range(5)][::-1]
#|        fine = [now - dt.timedelta(minutes=15 * i) for i in range(1, 60)][::-1]
#|        fail = [dt.datetime.combine(now.date(), dt.time(2, 15))]
#|        rows = (self.rows(daily, link=1) + self.rows(fail, link=1, failed=fail) + self.rows(hourly, link=2)
#|                + self.rows(weekly, link=3) + self.rows(fine, link=4))
#|        items = late.analyse(rows, now=now, labels={"1": "SALES_YYYYMMDD.csv", "2": "orders_api", "3": "returns.csv"})
#|        by = {i["label"]: i for i in items}
#|        self.assertEqual(set(by), {"SALES_YYYYMMDD.csv", "orders_api", "returns.csv"})
#|        self.assertIn("today's file not loaded - usually by 02:1", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("on Mon-Fri", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("the latest attempt", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("FAILED", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("usually every 1.0 h", by["orders_api"]["message"])
#|        self.assertIn("usually every 7.0 days", by["returns.csv"]["message"])
#|        # a Saturday: the Mon-Fri feed is not expected
#|        sat = dt.datetime(2026, 9, 26, 9, 30)
#|        rows_sat = self.rows([d for d in daily if d < sat], link=1)
#|        self.assertEqual(late.analyse(rows_sat, now=sat), [])
#|        # before the usual time + tolerance: not late yet
#|        early = dt.datetime(2026, 9, 28, 2, 30)
#|        self.assertEqual(late.analyse(self.rows(daily, link=1), now=early), [])
#|
#|    def test_cli_and_report(self):
#|        import datetime as dt
#|        from fixtures_builder import metadata_flow
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            now = dt.datetime.now()
#|            for i in range(60):
#|                t = now - dt.timedelta(hours=5, minutes=30 * i)
#|                db.execute("INSERT INTO FILE_LOAD_AUDIT(OBJ_ID, FILE_NAME, LOAD_STATUS, LOAD_TS, ROW_COUNT) VALUES (3, ?, 'SUCCESS', ?, 10)",
#|                           (f"returns_{t:%H%M}.csv", t.strftime("%Y-%m-%d %H:%M:%S")))
#|            db.commit()
#|            db.close()
#|            build(load_config(cfg_path), log=lambda m: None)
#|            rc, out = run_cli("--config", str(cfg_path), "late")
#|            self.assertEqual(rc, 1, out)
#|            self.assertIn("**returns.csv**: no file for 5.", out)
#|            self.assertIn("usually every 30 min", out)
#|            rc, md = run_cli("--config", str(cfg_path), "report")
#|            self.assertIn("## Late / missing files", md)
#|            self.assertIn("**returns.csv**", md)
#|
#|
#|class TestLearningSuggestions(unittest.TestCase):
#|    """Recurring causes across investigations that no learning covers yet."""
#|
#|    def test_suggest_until_written_down(self):
#|        from fixtures_builder import metadata_flow
#|        from nifikb.investigate import signature
#|        self.assertEqual(signature("FlowFile 1a2b3c4d DROPPED at 'Put' on 2026-09-26 02:14:00 after 3 retries"),
#|                         "FlowFile # DROPPED at '…' on # after # retries")
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            build(load_config(cfg_path), log=lambda m: None)
#|            cli_ = lambda *a: run_cli("--config", str(cfg_path), *a)
#|            rc, out = cli_("learn", "suggest")
#|            self.assertIn("no recurring", out)
#|            for day in ("20260926", "20260927", "20260928"):
#|                cli_("investigate", "--file", f"SALES_{day}.csv")
#|            rc, out = cli_("learn", "suggest")
#|            self.assertIn("seen 3x (SALES_20260926.csv, SALES_20260927.csv, SALES_20260928.csv", out)
#|            self.assertIn("NOT NULL column(s) of stg_sales not in the structure: load_ts", out)
#|            rc, md = cli_("report")
#|            self.assertIn("## Suggested learnings", md)
#|            from nifikb.mcp import Server
#|            text, _ = Server(str(cfg_path)).call("kb_overview", {})
#|            self.assertIn("# Recurring causes with no learning yet", text)
#|            # once it is written down, it is no longer suggested
#|            cli_("learn", "add", "--title", "stg_sales needs load_ts from the flow", "--kind", "gotcha", "--applies-to", "SALES_*.csv,stg_sales",
#|                 "--body", "## Cause\nload_ts is NOT NULL in stg_sales and set by the flow, not the file.\n## Fix\nnone needed")
#|            rc, out = cli_("learn", "suggest")
#|            self.assertNotIn("load_ts", out)
#|
#|
#|class TestLearnings(unittest.TestCase):
#|    """Team learnings written by people / agents: redaction, relevance, search, diagnose, MCP, doctor."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        cls.cfg = load_config(cls.cfg_path)
#|        build(cls.cfg, log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def cli(self, *argv):
#|        return run_cli("--config", str(self.cfg_path), *argv)
#|
#|    def test_add_redact_find_retire(self):
#|        rc, out = self.cli("learn", "add", "--title", "SALES feed switches to pipe delimiter at month end", "--kind", "pattern",
#|                           "--tags", "delimiter,Sales", "--applies-to", "SALES_*.csv,stg_sales", "--ticket", "INC1001",
#|                           "--body", "## Cause\nVendor exports with | on month end. SFTP password=Hunter2Secret! and Bearer abcdefghijklmnopqrstu\n"
#|                                     "## Fix\nAsk vendor; or set OBJ_DEFINITION.DELIMITER per run.")
#|        self.assertEqual(rc, 0, out)
#|        path = Path(out.split("saved ", 1)[1].splitlines()[0].strip())
#|        text = path.read_text(encoding="utf-8")
#|        self.assertNotIn("Hunter2Secret!", text)
#|        self.assertNotIn("abcdefghijklmnopqrstu", text)
#|        self.assertIn("applies_to: [SALES_*.csv, stg_sales]", text)
#|        self.assertIn("tags: [delimiter, sales]", text)
#|        # immediately searchable, without a rebuild
#|        rc, out = self.cli("search", "pipe", "delimiter")
#|        self.assertIn("[learning]", out)
#|        # relevant by file-name pattern
#|        rc, out = self.cli("learn", "for", "SALES_20260926.csv")
#|        self.assertIn("pipe delimiter", out)
#|        # diagnose shows it
#|        rc, out = self.cli("diagnose", "--file", "SALES_20260926.csv")
#|        self.assertIn("Team learnings that may apply", out)
#|        self.assertIn("SALES feed switches to pipe delimiter", out)
#|        # near-duplicate warning
#|        rc, out = self.cli("learn", "add", "--title", "Sales feed switches to pipe delimiter at month end again", "--body", "same")
#|        self.assertIn("similar learning exists", out)
#|        # retire hides it from relevance but keeps the file
#|        ident = path.stem
#|        rc, out = self.cli("learn", "retire", ident, "--reason", "vendor fixed their export")
#|        self.assertEqual(rc, 0, out)
#|        rc, out = self.cli("learn", "for", "stg_sales")
#|        self.assertNotIn(ident, out)
#|        rc, out = self.cli("learn", "list", "--all")
#|        self.assertIn("OBSOLETE", out)
#|        self.assertIn("vendor fixed their export", path.read_text(encoding="utf-8"))
#|
#|    def test_rejects_bad_input(self):
#|        rc, out = self.cli("learn", "add", "--title", "no body", "--body", "  ")
#|        self.assertEqual(rc, 1)
#|        rc, out = self.cli("learn", "add", "--title", "x", "--body", "y" * 30000)
#|        self.assertIn("keep a learning under", out)
#|
#|    def test_hand_written_file_is_indexed_on_build(self):
#|        d = Path(self.cfg["knowledge"]["dir"]) / "learnings"
#|        d.mkdir(parents=True, exist_ok=True)
#|        (d / "manual-note.md").write_text("---\ntitle: Customers API returns 206 during vendor maintenance\nkind: gotcha\n"
#|                                          "applies_to: [crm_customers_api]\n---\nRetry after 02:00.\n", encoding="utf-8")
#|        build(self.cfg, log=lambda m: None)
#|        rc, out = self.cli("search", "vendor", "maintenance")
#|        self.assertIn("Customers API returns 206", out)
#|        rc, out = self.cli("diagnose", "--feed", "crm_customers_api")
#|        self.assertIn("manual-note", out)
#|        self.assertIn("active learning(s)", (Path(self.cfg["output"]["dir"]) / "INDEX.md").read_text(encoding="utf-8"))
#|
#|    def test_mcp_learning_tools(self):
#|        from nifikb.mcp import Server
#|        s = Server(str(self.cfg_path))
#|        text, err = s.call("add_learning", {"title": "Returns file lands in wrong folder after DST change",
#|                                            "body": "## Symptom\nnothing picked up\n## Fix\nuse UTC in the ListSFTP filter",
#|                                            "kind": "gotcha", "applies_to": ["returns.csv"], "author": "gemini"})
#|        self.assertFalse(err, text)
#|        ident = text.split()[1]
#|        text, err = s.call("find_learnings", {"terms": ["returns.csv"]})
#|        self.assertIn(ident, text)
#|        text, err = s.call("get_learning", {"id": ident})
#|        self.assertIn("use UTC", text)
#|        self.assertIn("by gemini", text)
#|        text, err = s.call("kb_overview", {})
#|        self.assertIn("Recent team learnings", text)
#|        self.assertIn(ident, text)
#|        text, err = s.call("add_learning", {"title": "", "body": "x"})
#|        self.assertTrue(err)
#|
#|    def test_doctor(self):
#|        rc, out = self.cli("doctor")
#|        self.assertIn("[OK  ] database metadata: sqlite connected", out)
#|        self.assertIn("[OK  ] metadata:", out)
#|        self.assertIn("[OK  ] knowledge base: built", out)
#|        self.assertIn("team context", out)
#|        self.assertIn("problem(s)", out)
#|
#|
#|class TestAgentFiles(unittest.TestCase):
#|    """The agent instruction copies must not drift apart; the agent wiring must point at this package."""
#|
#|    def test_instruction_files_identical(self):
#|        root = Path(__file__).resolve().parent.parent
#|        texts = {f: (root / f).read_text(encoding="utf-8").replace("\r\n", "\n") for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")}
#|        self.assertEqual(len(set(texts.values())), 1, "CLAUDE.md, GEMINI.md and AGENTS.md differ - copy the edited one over the others")
#|        text = texts["CLAUDE.md"]
#|        from nifikb.mcp import TOOLS
#|        for tool in [t["name"] for t in TOOLS]:  # every MCP tool is documented for the agents
#|            self.assertIn(f"`{tool}`", text)
#|
#|    def test_package_is_clean(self):
#|        import importlib.util
#|        root = Path(__file__).resolve().parent.parent
#|        spec = importlib.util.spec_from_file_location("package", root / "ops" / "package.py")
#|        mod = importlib.util.module_from_spec(spec)
#|        spec.loader.exec_module(mod)
#|        with tempfile.TemporaryDirectory() as tmp:
#|            target, _ = mod.package(tmp)
#|            import zipfile
#|            with zipfile.ZipFile(target) as z:
#|                names = z.namelist()
#|                config = z.read("nifi-kb/nifikb.toml").decode("utf-8")
#|        self.assertFalse([n for n in names if "/kb/" in n or "__pycache__" in n or n.endswith((".log", ".sqlite"))])
#|        for must in ("nifi-kb/nifikb/cli.py", "nifi-kb/CLAUDE.md", "nifi-kb/GEMINI.md", "nifi-kb/.mcp.json", "nifi-kb/HANDOFF.md",
#|                     "nifi-kb/.claude/commands/triage.md", "nifi-kb/.gemini/commands/triage.toml", "nifi-kb/knowledge/README.md"):
#|            self.assertIn(must, names)
#|        self.assertIn('home = "C:/path/to/nifi"', config)  # fresh template, not this machine's config
#|        self.assertNotIn("testdb", config)
#|
#|    def test_paste_bundle(self):
#|        """ops/bundle.py: one text file per part, survives CRLF / trimmed blanks / BOM, detects cut-off and damaged pastes."""
#|        import importlib.util
#|        import subprocess
#|        root = Path(__file__).resolve().parent.parent
#|        sys.path.insert(0, str(root / "ops"))
#|        spec = importlib.util.spec_from_file_location("bundle", root / "ops" / "bundle.py")
#|        mod = importlib.util.module_from_spec(spec)
#|        spec.loader.exec_module(mod)
#|        from package import collect
#|        with tempfile.TemporaryDirectory() as tmp:
#|            parts = mod.bundle(Path(tmp) / "b", max_kb=300)
#|            self.assertGreater(len(parts), 1)
#|            out = Path(tmp) / "out"
#|            for path, _ in parts:  # a messy paste: Windows line endings, trailing blanks trimmed, a BOM
#|                text = path.read_text(encoding="utf-8")
#|                messy = "﻿" + "\r\n".join(line.rstrip() for line in text.split("\n"))
#|                path.write_text(messy, encoding="utf-8", newline="")
#|                r = subprocess.run([sys.executable, str(path), str(out)], capture_output=True, text=True)
#|                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
#|            expected = dict(collect(sandbox_config=False))
#|            self.assertNotIn("nifikb.toml.sandbox", expected)
#|            for rel, data in expected.items():
#|                got = (out / rel).read_bytes()
#|                if rel.endswith((".gz", ".parquet")):
#|                    self.assertEqual(got, data, rel)  # binary: exact
#|                else:  # text: equal up to trailing blanks, which the messy paste removed
#|                    self.assertEqual([x.rstrip() for x in got.decode().splitlines()], [x.rstrip() for x in data.decode().splitlines()], rel)
#|            self.assertEqual((out / "GEMINI.md").read_bytes(), (out / "CLAUDE.md").read_bytes())
#|            # your own config survives a re-unpack (upgrade)
#|            (out / "nifikb.toml").write_text("# mine", encoding="utf-8")
#|            for path, _ in parts:
#|                subprocess.run([sys.executable, str(path), str(out)], capture_output=True, text=True)
#|            self.assertEqual((out / "nifikb.toml").read_text(encoding="utf-8"), "# mine")
#|            # cut off / damaged
#|            text = parts[0][0].read_text(encoding="utf-8")
#|            cut = Path(tmp) / "cut.py"
#|            cut.write_text(text[: len(text) // 2].rsplit("\n", 1)[0] + "\n", encoding="utf-8")
#|            r = subprocess.run([sys.executable, str(cut), str(Path(tmp) / "o2")], capture_output=True, text=True)
#|            self.assertEqual(r.returncode, 2)
#|            self.assertIn("paste was cut off", r.stdout)
#|            lines = text.split("\n")
#|            i = next(n for n, line in enumerate(lines) if line.startswith("#|def "))
#|            lines[i] = lines[i].replace("def ", "dfe ", 1)
#|            bad = Path(tmp) / "bad.py"
#|            bad.write_text("\n".join(lines), encoding="utf-8")
#|            r = subprocess.run([sys.executable, str(bad), str(Path(tmp) / "o3")], capture_output=True, text=True)
#|            self.assertEqual(r.returncode, 1)
#|            self.assertIn("damaged in the paste and NOT written", r.stdout)
#|        sys.path.remove(str(root / "ops"))
#|
#|    def test_mcp_configs(self):
#|        root = Path(__file__).resolve().parent.parent
#|        for f in (".mcp.json", ".gemini/settings.json"):
#|            server = json.loads((root / f).read_text(encoding="utf-8"))["mcpServers"]["nifikb"]
#|            self.assertEqual(server["args"], ["-m", "nifikb", "mcp"])
#|        from nifikb.mcp import TOOLS
#|        self.assertEqual(len({t["name"] for t in TOOLS}), len(TOOLS))
#|
#|
#|class TestDoctorUnits(unittest.TestCase):
#|    def test_grant_scope(self):
#|        from nifikb.doctor import _grant_covers
#|        self.assertTrue(_grant_covers("GRANT SELECT ON `testdb`.* TO `u`@`h`", "testDB"))
#|        self.assertTrue(_grant_covers("GRANT ALL PRIVILEGES ON *.* TO `root`@`h`", "meta"))
#|        self.assertTrue(_grant_covers("GRANT INSERT ON `meta`.`t` TO `u`@`h`", "meta"))
#|        self.assertFalse(_grant_covers(r"GRANT SELECT, INSERT ON `test\_%`.* TO PUBLIC", "testDB"))  # MariaDB default
#|        self.assertFalse(_grant_covers("GRANT SELECT, INSERT ON `other`.* TO `u`@`h`", "meta"))
#|
#|
#|class TestMetadataUnits(unittest.TestCase):
#|    def test_pattern_regex(self):
#|        from nifikb.metadata import pattern_regex
#|        cases = [("SALES_YYYYMMDD.csv", "SALES_20260926.csv", True), ("SALES_YYYYMMDD.csv", "SALES_2026092.csv", False),
#|                 ("SUMMARY_*.txt", "SUMMARY_x.txt", True), ("cust_%.json", "cust_abc.json", True),
#|                 ("inv_\\d{6}\\.dat", "inv_123456.dat", True), ("${prefix}_orders.csv", "eu_orders.csv", True),
#|                 ("DDMMYYYY_feed.csv", "26092026_feed.csv", True)]
#|        for pat, name, ok in cases:
#|            self.assertEqual(bool(pattern_regex(pat).match(name)), ok, (pat, name))
#|        self.assertIsNone(pattern_regex("plain.csv"))
#|
#|    def test_type_family(self):
#|        from nifikb.metadata import type_family
#|        self.assertEqual(type_family("NUMBER(10)"), "numeric")
#|        self.assertEqual(type_family("varchar2(20)"), "string")
#|        self.assertEqual(type_family("datetime"), "temporal")
#|        self.assertEqual(type_family("TIMESTAMP(6)"), "temporal")
#|        self.assertIsNone(type_family(""))
#|
#|    def test_mask_row(self):
#|        from nifikb.metadata import mask_row
#|        r = mask_row({"API_KEY": "k", "HEADERS": "Authorization: Bearer abcdefghijklmnop", "BODY": '{"password": "p4ss"}', "N": 3})
#|        self.assertEqual(r["API_KEY"], "***")
#|        self.assertNotIn("abcdefghijklmnop", r["HEADERS"])
#|        self.assertNotIn("p4ss", r["BODY"])
#|        self.assertEqual(r["N"], 3)
#|
#|
#|class TestIncremental(unittest.TestCase):
#|    def test_rebuild_and_changelog(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp)
#|            cfg = load_config(cfg_path)
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "built")
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "up-to-date")
#|            flow = nested_flow(bucket="acme-orders-v2")
#|            flow["rootGroup"]["processors"] = [p for p in flow["rootGroup"]["processors"] if p["identifier"] != "p-gen"]
#|            flow["rootGroup"]["connections"] = [c for c in flow["rootGroup"]["connections"] if c["identifier"] != "r6"]
#|            with gzip.open(Path(tmp) / "flow.json.gz", "wt", encoding="utf-8") as f:
#|                json.dump(flow, f)
#|            res = build(cfg, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            changes = "\n".join(res["changes"])
#|            self.assertIn("'Bucket' `#{s3.bucket}` → `acme-orders-v2`", changes)
#|            self.assertIn("removed Nightly trigger", changes)
#|            self.assertIn("connection removed: Nightly trigger -success→ Lookup customer", changes)
#|            log = (Path(cfg["output"]["dir"]) / "CHANGELOG.md").read_text(encoding="utf-8")
#|            self.assertIn("acme-orders-v2", log)
#|            hard = (Path(cfg["output"]["dir"]) / "hardcoded.md").read_text(encoding="utf-8")
#|            self.assertIn("acme-orders-v2", hard)  # bucket is now a literal
#|
#|    def test_db_unreachable_uses_cache(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp))
#|            build(cfg, log=lambda m: None)
#|            os.remove(Path(tmp) / "meta.db")
#|            res = build(cfg, force=True, refresh_db=True, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            doc = (Path(cfg["output"]["dir"]) / "db/metadata.md").read_text(encoding="utf-8")
#|            self.assertIn("## file_audit", doc)
#|            idx = (Path(cfg["output"]["dir"]) / "db/INDEX.md").read_text(encoding="utf-8")
#|            self.assertIn("cached schema", idx)
#|
#|
#|@unittest.skipUnless((REAL_NIFI / "conf" / "flow.json.gz").exists(), "real NiFi not installed")
#|class TestRealNifi(unittest.TestCase):
#|    """End-to-end over the actual local NiFi install (conf + lib NARs + scripts)."""
#|
#|    def test_build(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = Path(tmp) / "nifikb.toml"
#|            cfg_path.write_text(f'[nifi]\nhome = "{REAL_NIFI.as_posix()}"\n[output]\ndir = "{Path(tmp, "kb").as_posix()}"\n'
#|                                f'[code]\nrepos = ["{(REAL_NIFI / "scripts").as_posix()}"]\n', encoding="utf-8")
#|            cfg = load_config(cfg_path)
#|            res = build(cfg, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            kb = Path(cfg["output"]["dir"])
#|            root = (kb / "flows/root.md").read_text(encoding="utf-8")
#|            self.assertEqual(root.count("table=sales"), 3)
#|            self.assertIn("Statement Type=INSERT_IGNORE", root)
#|            self.assertIn("*failure* → **PutDatabaseRecord** [PutDatabaseRecord] `4cb1c050`", root)
#|            self.assertIn("default hidden", root)  # NAR manifests were used
#|            script = (kb / "scripts/remove-duplicates-py.md").read_text(encoding="utf-8")
#|            self.assertIn("drop_duplicates(subset='ORDERNUMBER'", script)
#|            blob = "\n".join(all_text(kb).values())
#|            self.assertNotIn('"1234"', blob)  # stats.py password redacted
#|            self.assertIn("`sales` — `stats.py`", (kb / "external-systems.md").read_text(encoding="utf-8"))
#|            idx = (kb / "db/INDEX.md").read_text(encoding="utf-8")
#|            self.assertIn("jdbc:postgresql://localhost:5432/testDB", idx)
#|
#|
#|if __name__ == "__main__":
#|    unittest.main()
#|
#|
#|class TestManyTables(unittest.TestCase):
#|    def test_database_doc_splits_per_table(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp)
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            for i in range(70):
#|                db.execute(f"CREATE TABLE wide_{i}(id INTEGER PRIMARY KEY, v{i} TEXT)")
#|            db.commit()
#|            db.close()
#|            cfg = load_config(cfg_path)
#|            cfg["databases"][0]["include_tables"].append("wide_%")
#|            build(cfg, log=lambda m: None)
#|            kb = Path(cfg["output"]["dir"])
#|            index = (kb / "db" / "metadata.md").read_text(encoding="utf-8")
#|            self.assertIn("one file per table under `db/metadata/`", index)
#|            self.assertIn("[wide-7.md](metadata/wide-7.md)", index)
#|            self.assertIn("| v7 | TEXT |", (kb / "db" / "metadata" / "wide-7.md").read_text(encoding="utf-8"))
#|            rc, out = run_cli("--config", str(cfg_path), "show", "wide_7")
#|            self.assertIn("| v7 | TEXT |", out)
#|            # dropping the tables removes their files on the next build
#|            cfg["databases"][0]["include_tables"].remove("wide_%")
#|            build(cfg, refresh_db=True, log=lambda m: None)
#|            self.assertFalse((kb / "db" / "metadata").exists())
#|
#|
#|class TestScale(unittest.TestCase):
#|    def test_large_flow_is_fast(self):
#|        import time
#|        from fixtures_builder import conn as mk_conn, proc as mk_proc
#|        flow = nested_flow()
#|        for g in range(150):
#|            gid = f"g{g}"
#|            procs = [mk_proc(f"{gid}-p{i}", f"Step {i}", "org.apache.nifi.processors.standard.InvokeHTTP",
#|                             {"Remote URL": f"https://api{g}.acme.com/v1/{i}", "put-db-record-table-name": f"t_{g}_{i}"}, group=gid)
#|                     for i in range(20)]
#|            conns = [mk_conn(f"{gid}-c{i}", f"{gid}-p{i - 1}", "PROCESSOR", f"{gid}-p{i}", "PROCESSOR", ["Response"], group=gid)
#|                     for i in range(1, 20)]
#|            flow["rootGroup"]["processGroups"].append({
#|                "identifier": gid, "name": f"Flow {g}", "processors": procs, "connections": conns, "inputPorts": [], "outputPorts": [],
#|                "funnels": [], "labels": [], "controllerServices": [], "processGroups": [], "remoteProcessGroups": [], "variables": {}})
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp, flow=flow, with_db=False))
#|            t = time.time()
#|            res = build(cfg, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            self.assertLess(time.time() - t, 30)
#|            self.assertTrue((Path(cfg["output"]["dir"]) / "flows" / "flow-149.md").exists())
#@@ FILE ops/build.cmd t 52b9392d46df1b51
#|@echo off
#|rem Refresh the NiFi knowledge base (no-op when nothing changed). Used by the scheduled task from register-schedule.ps1.
#|rem Database passwords come from user environment variables, e.g.  setx NIFIKB_DB_PASSWORD "..."  (once, then log off/on).
#|cd /d "%~dp0.."
#|echo ==== %date% %time% >> "%~dp0build.log"
#|python -m nifikb build >> "%~dp0build.log" 2>&1
#@@ FILE ops/build.sh t 3b9e9d48d937a624
#|#!/usr/bin/env sh
#|# Refresh the NiFi knowledge base (no-op when nothing changed). Linux counterpart of build.cmd.
#|# Cron (every 30 min):  */30 * * * * sh /opt/nifi-kb/ops/build.sh
#|# Use password_file (chmod 600) in nifikb.toml so cron needs no environment variables.
#|cd "$(dirname "$0")/.." || exit 1
#|PY="${PYTHON:-python3}"
#|echo "==== $(date '+%Y-%m-%d %H:%M:%S')" >> ops/build.log
#|"$PY" -m nifikb build >> ops/build.log 2>&1
#@@ FILE ops/bundle.py t 541c7e964658d4d0
#|"""Pack nifi-kb into ONE plain-text Python file (or a few) for machines where nothing can be downloaded but text can be
#|pasted - e.g. open it in a browser / Bitbucket / e-mail on the office laptop, copy all, paste into a new file, run it.
#|
#|    python ops/bundle.py [--out dist] [--max-kb 0] [--no-tests] [--with-learnings]
#|
#|--max-kb splits the bundle into parts of about that size (clipboard / editor limits); each part is self-contained and
#|unpacked the same way into the same folder. The unpacker (ops/bundle_unpack.py) checks every file's hash, so a paste
#|that was cut off or damaged is reported instead of producing broken files. Same content as ops/package.py (minus the
#|sandbox config).
#|"""
#|import argparse
#|import base64
#|import hashlib
#|import sys
#|from pathlib import Path
#|
#|ROOT = Path(__file__).resolve().parent.parent
#|sys.path.insert(0, str(ROOT))
#|sys.path.insert(0, str(ROOT / "ops"))
#|
#|from bundle_unpack import DATA_LINE, text_hash  # noqa: E402
#|from nifikb import __version__  # noqa: E402
#|from package import collect  # noqa: E402
#|
#|
#|def encode(rel, data):
#|    """Header + '#|' lines for one file."""
#|    if " " in rel:
#|        raise ValueError(f"file names with blanks are not supported in a bundle: {rel}")
#|    try:
#|        text = data.decode("utf-8")
#|        if "\x00" in text or "\r" in text.replace("\r\n", ""):
#|            raise UnicodeDecodeError("utf-8", data, 0, 1, "binary-looking")
#|    except UnicodeDecodeError:
#|        b64 = base64.b64encode(data).decode("ascii")
#|        lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
#|        return [f"#@@ FILE {rel} b {hashlib.sha256(data).hexdigest()[:16]}"] + [f"#|{x}" for x in lines]
#|    crlf = "\r\n" in text
#|    text = text.replace("\r\n", "\n")
#|    newline = text.endswith("\n")
#|    mode = ("tc" if crlf else "t") if newline else ("tcn" if crlf else "tn")
#|    body = text[:-1] if newline else text
#|    lines = body.split("\n") if body else []
#|    return [f"#@@ FILE {rel} {mode} {text_hash(text)}"] + [f"#|{x}" for x in lines]
#|
#|
#|def bundle(out_dir, max_kb=0, tests=True, with_learnings=False):
#|    files = [(rel, data) for rel, data in collect(with_learnings, sandbox_config=False)
#|             if tests or not rel.startswith("tests/")]
#|    first_of = {}
#|    items = []  # (rel, lines, source rel for copies)
#|    for rel, data in files:
#|        digest = hashlib.sha256(data).hexdigest()
#|        if digest in first_of and data:
#|            items.append((rel, [f"#@@ COPY {rel} {first_of[digest]}"], first_of[digest]))  # CLAUDE.md = GEMINI.md = AGENTS.md
#|        else:
#|            first_of[digest] = rel
#|            items.append((rel, encode(rel, data), None))
#|    parts, current, size = [], [], 0
#|    part_of = {}
#|    for rel, lines, source in items:
#|        n = sum(len(x) + 1 for x in lines)
#|        if source is None and max_kb and current and size + n > max_kb * 1024:
#|            parts.append(current)
#|            current, size = [], 0
#|        if source is not None:  # a copy goes with its source
#|            parts_list = parts + [current]
#|            parts_list[part_of[source]].append((rel, lines))
#|            part_of[rel] = part_of[source]
#|            continue
#|        current.append((rel, lines))
#|        part_of[rel] = len(parts)
#|        size += n
#|    parts.append(current)
#|    stub = (ROOT / "ops" / "bundle_unpack.py").read_text(encoding="utf-8")
#|    out_dir = Path(out_dir)
#|    out_dir.mkdir(parents=True, exist_ok=True)
#|    for old in out_dir.glob(f"nifi-kb-{__version__}-bundle*.py"):
#|        old.unlink()
#|    written = []
#|    for i, part in enumerate(parts, 1):
#|        name = f"nifi-kb-{__version__}-bundle.py" if len(parts) == 1 else f"nifi-kb-{__version__}-bundle-part{i}of{len(parts)}.py"
#|        head = (f"# nifi-kb {__version__} - paste bundle" + (f", part {i} of {len(parts)}" if len(parts) > 1 else "")
#|                + f" - {len(part)} files. Save as {name}, then run:  python {name}\n")
#|        body = [line for _, lines in part for line in lines]
#|        text = (head + stub.rstrip("\n") + "\n\n" + DATA_LINE + "\n" + "\n".join(body) + "\n"
#|                + f"#@@ END part {i} of {len(parts)} files {len(part)}\n")
#|        path = out_dir / name
#|        path.write_text(text, encoding="utf-8", newline="\n")
#|        written.append((path, len(part)))
#|    return written
#|
#|
#|def main():
#|    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
#|    ap.add_argument("--out", default=str(ROOT / "dist"))
#|    ap.add_argument("--max-kb", type=int, default=0, help="split into parts of about this many KB (0 = one file)")
#|    ap.add_argument("--no-tests", action="store_true", help="leave tests/ out (smaller; you cannot run the test suite there)")
#|    ap.add_argument("--with-learnings", action="store_true", help="also copy knowledge/learnings/*.md")
#|    args = ap.parse_args()
#|    for path, n in bundle(args.out, args.max_kb, not args.no_tests, args.with_learnings):
#|        print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB, {n} files)")
#|    print("On the office laptop: create an empty file with the same name, paste the whole content, save as UTF-8, "
#|          "run  python <file>  - it recreates the nifi-kb folder next to it.")
#|
#|
#|if __name__ == "__main__":
#|    main()
#@@ FILE ops/bundle_unpack.py t c56748f989ce7c37
#|"""nifi-kb paste bundle: recreates the nifi-kb folder from this single file (for machines where files cannot be
#|downloaded, only text pasted).
#|
#|    python <this file> [target folder]        default target: a folder "nifi-kb" next to this file
#|
#|Everything below the DATA line is the content of the files, stored as comment lines ("#|" + the line) so the whole file
#|stays plain, readable text and valid Python. Each file's hash is checked; a file whose paste was damaged is NOT written
#|and is listed, so only that part needs pasting again. Your own nifikb.toml and knowledge/ files are never overwritten.
#|Standard library only; Python 3.8+ can unpack, nifi-kb itself needs 3.11+.
#|"""
#|import base64
#|import hashlib
#|import sys
#|from pathlib import Path, PurePosixPath
#|
#|KEEP = ("nifikb.toml", "knowledge/")  # yours after the first unpack: never overwritten
#|DATA_LINE = "# ==== DATA ===="
#|
#|
#|def text_hash(text):
#|    """Hash that survives a copy / paste: line endings and trailing blanks do not count."""
#|    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
#|    while lines and not lines[-1]:
#|        lines.pop()
#|    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
#|
#|
#|def safe_path(rel):
#|    p = PurePosixPath(rel)
#|    if p.is_absolute() or ".." in p.parts or ":" in rel or not rel:
#|        raise ValueError(f"unsafe path in bundle: {rel!r}")
#|    return p
#|
#|
#|def parse(lines):
#|    """[(kind, path, mode, hash, content lines or source path)], (part, parts, count) from the END line or None."""
#|    entries, current, end, seen_data = [], None, None, False
#|    for n, raw in enumerate(lines, 1):
#|        line = raw.rstrip("\r\n")
#|        if not seen_data:
#|            seen_data = line.strip() == DATA_LINE
#|            continue
#|        if line.startswith("#|"):
#|            if current is None:
#|                raise ValueError(f"line {n}: content before any file header")
#|            current[4].append(line[2:])
#|        elif line.startswith("#@@ FILE "):
#|            _, _, path, mode, digest = line.split(" ")[:5]
#|            current = ["file", path, mode, digest, []]
#|            entries.append(current)
#|        elif line.startswith("#@@ COPY "):
#|            _, _, path, source = line.split(" ")[:4]
#|            entries.append(["copy", path, None, None, source])
#|            current = None
#|        elif line.startswith("#@@ END "):
#|            bits = line.split()
#|            end = (int(bits[3]), int(bits[5]), int(bits[7]))  # "#@@ END part 1 of 3 files 42"
#|            current = None
#|        elif line.strip() in ("", "#"):
#|            continue  # an editor added or trimmed an empty line
#|        else:
#|            raise ValueError(f"line {n} is not part of the bundle (damaged paste?): {line[:60]!r}")
#|    if not seen_data:
#|        raise ValueError(f"no '{DATA_LINE}' line - this is not a complete nifi-kb bundle")
#|    return entries, end
#|
#|
#|def main(argv=None):
#|    argv = sys.argv[1:] if argv is None else argv
#|    me = Path(__file__).resolve()
#|    target = Path(argv[0]).resolve() if argv else me.parent / "nifi-kb"
#|    with open(me, encoding="utf-8-sig") as f:
#|        entries, end = parse(f.readlines())
#|    files = [e for e in entries if e[0] == "file"]
#|    if end is None:
#|        print("ERROR: the bundle is incomplete (its last line '#@@ END ...' is missing) - the paste was cut off. "
#|              "Copy the whole file again (Ctrl+A in the source view).")
#|        return 2
#|    part, parts, count = end
#|    if count != len(files) + sum(1 for e in entries if e[0] == "copy"):
#|        print(f"ERROR: expected {count} files in this part, found {len(entries)} - the paste lost lines; copy it again.")
#|        return 2
#|    written, kept, bad = [], [], []
#|    contents = {}
#|    for kind, rel, mode, digest, body in entries:
#|        path = safe_path(rel)
#|        if kind == "copy":
#|            if body not in contents:
#|                bad.append(f"{rel} (copy of {body}, which is not in this part or was damaged)")
#|                continue
#|            data = contents[body]
#|        elif mode == "b":
#|            data = base64.b64decode("".join(body))
#|            if hashlib.sha256(data).hexdigest()[:16] != digest:
#|                bad.append(rel)
#|                continue
#|        else:
#|            text = "\n".join(body) + ("\n" if mode in ("t", "tc") else "")
#|            if text_hash(text) != digest:
#|                bad.append(rel)
#|                continue
#|            data = (text.replace("\n", "\r\n") if mode in ("tc", "tcn") else text).encode("utf-8")
#|        contents[rel] = data
#|        dest = target / Path(*path.parts)
#|        if dest.exists() and (rel == KEEP[0] or rel.startswith(KEEP[1])) and rel != "knowledge/README.md":
#|            kept.append(rel)
#|            continue
#|        dest.parent.mkdir(parents=True, exist_ok=True)
#|        dest.write_bytes(data)
#|        written.append(rel)
#|    print(f"part {part} of {parts}: {len(written)} files written to {target}" + (f", {len(kept)} of yours kept ({', '.join(kept)})" if kept else ""))
#|    if bad:
#|        print(f"ERROR: {len(bad)} file(s) damaged in the paste and NOT written - copy this part again:")
#|        for b in bad:
#|            print(f"  {b}")
#|        return 1
#|    if part == parts:
#|        print("Next: cd into the folder, then  python -m unittest discover -s tests  (expect OK),  edit nifikb.toml,  "
#|              "python -m nifikb build,  python -m nifikb doctor  - see HANDOFF.md section 4.")
#|    else:
#|        print(f"Now unpack part {part + 1} of {parts} the same way (into the same folder).")
#|    return 0
#|
#|
#|if __name__ == "__main__":
#|    sys.exit(main())
#@@ FILE ops/package.py tc bf7717252b18bd30
#|"""Build a clean zip to move nifikb to another machine (e.g. the office laptop).
#|
#|    python ops/package.py [--out dist] [--with-learnings]
#|
#|Included: the nifikb package, tests, ops scripts, examples/, evals/cases.example.toml, agent setup (CLAUDE/GEMINI/AGENTS.md, .mcp.json, .gemini/, .claude/),
#|docs, knowledge/README.md + context.md, and a fresh nifikb.toml template (this machine's config holds local paths and
#|sandbox databases, so it is saved as nifikb.toml.sandbox for reference only).
#|Never included: kb/ (rebuild there), caches, logs, secrets.
#|"""
#|import argparse
#|import sys
#|import zipfile
#|from pathlib import Path
#|
#|ROOT = Path(__file__).resolve().parent.parent
#|sys.path.insert(0, str(ROOT))
#|
#|from nifikb import __version__  # noqa: E402
#|from nifikb.config import TEMPLATE  # noqa: E402
#|
#|FILES = ["CLAUDE.md", "GEMINI.md", "AGENTS.md", "README.md", "HANDOFF.md", ".mcp.json", ".gitignore"]
#|DIRS = ["nifikb", "tests", "ops", ".gemini", ".claude", "examples"]
#|SKIP_PARTS = {"__pycache__", ".pytest_cache", "dist"}
#|SKIP_NAMES = {"build.log", "settings.local.json", "last-report.html", "cases.toml"}
#|
#|
#|def collect(with_learnings=False, sandbox_config=True):
#|    """[(relative path, bytes)] of everything that is shipped - shared by the zip and the paste bundle (ops/bundle.py)."""
#|    out = []
#|
#|    def add(path):
#|        rel = path.relative_to(ROOT)
#|        if SKIP_PARTS & set(rel.parts) or path.name in SKIP_NAMES or path.suffix == ".pyc":
#|            return
#|        out.append((rel.as_posix(), path.read_bytes()))
#|
#|    for f in FILES:
#|        if (ROOT / f).is_file():
#|            add(ROOT / f)
#|    for d in DIRS:
#|        for p in sorted((ROOT / d).rglob("*")) if (ROOT / d).is_dir() else []:
#|            if p.is_file():
#|                add(p)
#|    if (ROOT / "evals" / "cases.example.toml").is_file():  # the team's own evals/cases.toml holds real tickets: not shipped
#|        add(ROOT / "evals" / "cases.example.toml")
#|    knowledge = ROOT / "knowledge"
#|    for f in ("README.md", "context.md"):
#|        if (knowledge / f).is_file():
#|            add(knowledge / f)
#|    if with_learnings:
#|        for p in sorted((knowledge / "learnings").glob("*.md")):
#|            add(p)
#|    out.append(("knowledge/learnings/.keep", b""))
#|    out.append(("nifikb.toml", TEMPLATE.format(home="C:/path/to/nifi").encode("utf-8")))  # fresh template
#|    if sandbox_config and (ROOT / "nifikb.toml").is_file():
#|        out.append(("nifikb.toml.sandbox", (ROOT / "nifikb.toml").read_bytes()))  # reference only
#|    return out
#|
#|
#|def package(out_dir, with_learnings=False):
#|    out_dir = Path(out_dir)
#|    out_dir.mkdir(parents=True, exist_ok=True)
#|    target = out_dir / f"nifi-kb-{__version__}.zip"
#|    names = []
#|    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
#|        for rel, data in collect(with_learnings):
#|            z.writestr(f"nifi-kb/{rel}", data)
#|            names.append(rel)
#|    return target, names
#|
#|
#|def main():
#|    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
#|    ap.add_argument("--out", default=str(ROOT / "dist"))
#|    ap.add_argument("--with-learnings", action="store_true", help="also copy knowledge/learnings/*.md")
#|    args = ap.parse_args()
#|    target, names = package(args.out, args.with_learnings)
#|    print(f"wrote {target} ({target.stat().st_size / 1024:.0f} KB, {len(names)} entries)")
#|    print("On the new machine: unzip, then follow HANDOFF.md section 4 (edit nifikb.toml, build, doctor).")
#|
#|
#|if __name__ == "__main__":
#|    main()
#@@ FILE ops/register-schedule.ps1 t 6b93315f1a18bbb9
#|# Registers Windows scheduled tasks (current user, no admin needed):
#|#   nifikb-build   refreshes the knowledge base every N minutes
#|#   nifikb-report  (optional) builds and sends the daily health report at a fixed time ([report] in nifikb.toml)
#|#
#|#   powershell -ExecutionPolicy Bypass -File ops\register-schedule.ps1 [-EveryMinutes 60] [-ReportAt 08:00]
#|# Remove with:  Unregister-ScheduledTask -TaskName nifikb-build -Confirm:$false  (same for nifikb-report)
#|param([int]$EveryMinutes = 60, [string]$ReportAt = "")
#|
#|$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
#|
#|$build = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot "build.cmd")
#|$every = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
#|Register-ScheduledTask -TaskName "nifikb-build" -Action $build -Trigger $every -Settings $settings `
#|    -Description "Refresh the NiFi knowledge base (python -m nifikb build)" -Force | Out-Null
#|Write-Host "Scheduled nifikb-build every $EveryMinutes minutes."
#|
#|if ($ReportAt) {
#|    $report = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot "report.cmd")
#|    $daily = New-ScheduledTaskTrigger -Daily -At $ReportAt
#|    Register-ScheduledTask -TaskName "nifikb-report" -Action $report -Trigger $daily -Settings $settings `
#|        -Description "Daily NiFi health report (python -m nifikb report --send)" -Force | Out-Null
#|    Write-Host "Scheduled nifikb-report daily at $ReportAt."
#|}
#|Write-Host "Log: $(Join-Path $PSScriptRoot 'build.log')"
#@@ FILE ops/report.cmd t 39b7c825fba5dea2
#|@echo off
#|rem Daily NiFi health report: refresh the KB, then e-mail / post the report as configured in [report] of nifikb.toml.
#|cd /d "%~dp0.."
#|python -m nifikb build >> "%~dp0build.log" 2>&1
#|python -m nifikb report --hours 24 --html "%~dp0last-report.html" --send >> "%~dp0build.log" 2>&1
#@@ FILE ops/report.sh t 8590c70b5b5a0b14
#|#!/usr/bin/env sh
#|# Daily NiFi health report: refresh the KB, then e-mail / post it as configured in [report] of nifikb.toml.
#|# Cron (08:00 every day):  0 8 * * * sh /opt/nifi-kb/ops/report.sh
#|cd "$(dirname "$0")/.." || exit 1
#|PY="${PYTHON:-python3}"
#|"$PY" -m nifikb build >> ops/build.log 2>&1
#|"$PY" -m nifikb report --hours 24 --html ops/last-report.html --send >> ops/build.log 2>&1
#@@ FILE ops/sync-agent-docs.cmd t a008859ee9ae6ea0
#|@echo off
#|rem CLAUDE.md is the master copy of the agent instructions; Gemini CLI reads GEMINI.md, other agents AGENTS.md.
#|cd /d "%~dp0.."
#|copy /y CLAUDE.md GEMINI.md >nul
#|copy /y CLAUDE.md AGENTS.md >nul
#|echo GEMINI.md and AGENTS.md updated from CLAUDE.md
#@@ FILE .gemini/commands/learn.toml t da3b77dbf0ce8cdc
#|description = "Save a reusable lesson from this conversation as a team learning shared with Claude and people"
#|prompt = """
#|Record a team learning following the "Team learnings" rules in GEMINI.md.
#|
#|What to capture: {{args}}
#|(If empty, use the root cause and fix established in this conversation.)
#|
#|1. find_learnings with the file names / tables / feeds / processors involved; if an existing learning covers it, retire it
#|   (retire_learning with replaced_by) and add the corrected one - never create a near duplicate.
#|2. Only save knowledge the KB cannot derive (not what the flow / code / tables already show), verified in this
#|   conversation, without secrets or personal data.
#|3. add_learning: specific title, kind, applies_to (file patterns, tables, feeds, processor names / short ids, config
#|   rows), tags, ticket if known, author "gemini", body with ## Symptom, ## Cause, ## Fix, ## How to spot it next time.
#|4. Show the saved id and the text. If the lesson keeps recurring, suggest what to add to knowledge/context.md.
#|"""
#@@ FILE .gemini/commands/triage.toml tc 29d6495e134235e5
#|description = "Triage a NiFi support ticket end to end (metadata, flow, custom code) and record what was learned"
#|prompt = """
#|Triage this NiFi support ticket by following the "Triage playbook" in GEMINI.md exactly:
#|
#|{{args}}
#|
#|Steps: kb_overview if you have not yet this session -> only a Jira / ServiceNow id given: ticket with it (reads the ticket and runs investigate); otherwise investigate with everything the ticket gives (file, feed, table, error_text, headers in file order or sample_path; live=true if config rows may have changed) -> read the ranked causes and evidence -> only if not conclusive: diagnose / provenance / logs / late_files (file not received) / check_target_output (loaded but data wrong) / search / show / trace / sql -> answer as Cause / Evidence / Fix / Also noticed, with short ids, TABLE:id, file:line and log lines.
#|Propose fixes (SQL for config rows, property changes) for a human to apply; never apply them.
#|
#|Finally, if the cause or fix is reusable and not derivable from the KB, call add_learning (kind, applies_to, tags,
#|ticket, author "gemini", body with Symptom / Cause / Fix / How to spot it next time) - retire an outdated learning instead
#|of duplicating it - and tell me the learning id. If nothing reusable was learned, say so and do not add one.
#|"""
#@@ FILE .gemini/settings.json t 63e96f305c59b3e2
#|{
#|  "mcpServers": {
#|    "nifikb": {
#|      "command": "python",
#|      "args": ["-m", "nifikb", "mcp"],
#|      "cwd": ".",
#|      "timeout": 600000
#|    }
#|  }
#|}
#@@ FILE .claude/commands/learn.md t b22b0c47e9a01925
#|---
#|description: Save a reusable lesson from this conversation (or from the text given) as a team learning shared with Gemini and people
#|argument-hint: [what to remember - optional; defaults to the ticket just solved]
#|---
#|Record a team learning following the "Team learnings" rules in CLAUDE.md.
#|
#|What to capture: $ARGUMENTS
#|(If empty, use the root cause and fix established in this conversation.)
#|
#|1. `find_learnings` with the file names / tables / feeds / processors involved; if an existing learning covers it, update
#|   by retiring it (`retire_learning` with `replaced_by`) and adding the corrected one — never create a near duplicate.
#|2. Only save knowledge the KB cannot derive (not what the flow / code / tables already show), verified in this
#|   conversation, without secrets or personal data.
#|3. `add_learning`: specific title, kind, applies_to (file patterns, tables, feeds, processor names / short ids, config
#|   rows), tags, ticket if known, author "claude", body with ## Symptom, ## Cause, ## Fix, ## How to spot it next time.
#|4. Show me the saved id and the text. If the lesson keeps recurring, suggest what to add to `knowledge/context.md`.
#@@ FILE .claude/commands/triage.md tc 835a148b50cc1f3f
#|---
#|description: Triage a NiFi support ticket end to end (metadata, flow, custom code) and record what was learned
#|argument-hint: <ticket text, ticket id + details, or a file name>
#|---
#|Triage this NiFi support ticket by following the "Triage playbook" in CLAUDE.md exactly:
#|
#|$ARGUMENTS
#|
#|Steps: `kb_overview` if you have not yet this session → only a Jira / ServiceNow id given: `ticket` with it (reads the
#|ticket and runs investigate); otherwise `investigate` with everything the ticket gives (file, feed,
#|table, error_text, headers in file order or sample_path; `live=true` if config rows may have changed) → read the ranked
#|causes and evidence → only if not conclusive: `diagnose` / `provenance` / `logs` / `late_files` (file not received) /
#|`check_target_output` (loaded but data wrong) / `search` / `show` / `trace` / `sql` →
#|answer as **Cause / Evidence / Fix / Also noticed**, with short ids, `TABLE:id`, `file:line` and log lines.
#|Propose fixes (SQL for config rows, property changes) for a human to apply; never apply them.
#|
#|Finally, if the cause or fix is reusable and not derivable from the KB, call `add_learning` (kind, applies_to, tags,
#|ticket, author "claude", body with Symptom / Cause / Fix / How to spot it next time) — retire an outdated learning instead
#|of duplicating it — and tell me the learning id. If nothing reusable was learned, say so and do not add one.
#@@ FILE .claude/settings.json t 64a048b09bef2abb
#|{
#|  "enableAllProjectMcpServers": true,
#|  "permissions": {
#|    "allow": [
#|      "mcp__nifikb",
#|      "Bash(python -m nifikb:*)",
#|      "Bash(py -m nifikb:*)",
#|      "Read(kb/**)",
#|      "Read(knowledge/**)"
#|    ],
#|    "deny": [
#|      "Read(**/flow.json.gz)",
#|      "Read(**/flow.xml.gz)",
#|      "Read(**/*.nar)",
#|      "Read(kb/kb.sqlite)"
#|    ]
#|  }
#|}
#@@ FILE examples/new-feed.example.toml t 2783f2eb9c44c1ab
#|# Proposal for a NEW feed - check it before anyone inserts the rows:
#|#   python -m nifikb onboard examples/new-feed.example.toml [--live]
#|# Column names are the config tables' own (kb/metadata.md lists them). Nothing is written anywhere: the check lists problems
#|# and prints INSERT statements for a human to review and run. Leave secrets (passwords, tokens) out - the DBA sets them.
#|
#|example_file = "INVOICE_20260927.csv"     # a real file name the definition must match (checked against every definition)
#|# sample = "INVOICE_20260927.csv"         # optional: a sample file (relative to this file) - header and content are checked
#|like = "SALES_YYYYMMDD.csv"               # optional: an existing, similar feed - columns / rows it has and this one lacks
#|# structure_csv = "invoice_columns.csv"   # optional: the structure rows as CSV (header = column names), instead of [[structure]]
#|
#|[definition]                              # one OBJ_DEFINITION row
#|# OBJ_ID = 123                            # leave out when the database generates it
#|FILE_NAME = "INVOICE_YYYYMMDD.csv"
#|TABLE_NAME = "stg_invoice"
#|SOURCE_SYSTEM = "ERP"
#|DELIMITER = ","
#|ACTIVE_FLAG = "Y"
#|
#|[[structure]]                             # one OBJ_STRUCTURE row per column, in file order (the parent id is filled in)
#|COL_NAME = "INVOICE_NO"
#|DATA_TYPE = "INTEGER"
#|COL_SEQ = 1
#|MANDATORY_FLAG = "Y"
#|
#|[[structure]]
#|COL_NAME = "CUSTOMER_NAME"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 2
#|COL_LENGTH = 100
#|
#|[[structure]]
#|COL_NAME = "AMOUNT"
#|DATA_TYPE = "DECIMAL"
#|COL_SEQ = 3
#|
#|[[rows.SOURCE_FEED_CONFIG]]               # rows of other config tables that belong to the feed (the link column is filled in)
#|FEED_NAME = "erp_invoice_feed"
#|SFTP_HOST = "sftp.erp.example.com"
#|REMOTE_DIR = "/outbound/invoice"
#@@ FILE evals/cases.example.toml t 6127cbefffc19fae
#|# Evaluation set: real past tickets with their known root cause (anonymise as needed).
#|# Copy to evals/cases.toml and add 15-30 tickets covering your common problem types.
#|#   python -m nifikb eval                         -> do the tools rank the true cause in the top 3?
#|#   python -m nifikb eval --agent "gemini -p"     -> does the model's answer name it? (prompt goes to stdin)
#|#   python -m nifikb eval --save evals/last.json  -> keep results to compare after changes
#|# Sample files can live in evals/samples/ (paths are relative to this file).
#|
#|[[case]]
#|id = "INC-0001-example"
#|ticket = "SALES file of 26 Sep did not load, customer names are missing in the report"
#|file = "SALES_20260926.csv"
#|headers = ["ORDER_NO", "CUSTNAME", "AMOUNT", "ORDER_DT", "REGION"]
#|expect_any = ["CUSTNAME"]            # the true cause: the header CUSTNAME does not match structure field CUST_NAME
#|top = 3
#|answer_expect = ["CUST_NAME"]        # the model's answer must mention the structure field
#|
#|# [[case]]
#|# id = "INC-0002"
#|# ticket = "orders API load failed at 02:14 with 'Column count mismatch'"
#|# file = "orders_20260926.json"
#|# error = "Column count mismatch"
#|# sample = "samples/orders_20260926.json"
#|# expect_any = ["delimited by", "column count"]
#@@ FILE knowledge/README.md t b96f72b044673f83
#|# Team knowledge
#|
#|Everything here is written by people and by the AI agents (Claude Code, Gemini CLI, …) and is **kept across builds**,
#|unlike `kb/`, which `nifikb build` regenerates. Commit this folder to git so the whole team (and every agent session)
#|shares it.
#|
#|| File | Who writes it | What goes in |
#||---|---|---|
#|| `context.md` | people (agents may suggest edits) | short, curated background: environments, owners / escalation, conventions, known quirks. Every agent session reads it first. |
#|| `learnings/<id>.md` | agents after solving a ticket, or people | one reusable lesson per file: symptom, cause, fix, how to spot it next time |
#|
#|## Adding a learning
#|
#|From an agent: the `add_learning` tool, or the `/learn` command in Claude Code and Gemini CLI.
#|From a terminal:
#|
#|```
#|python -m nifikb learn add --title "SALES feed switches to pipe delimiter at month end" --kind pattern ^
#|    --applies-to "SALES_*.csv,stg_sales" --tags "delimiter,vendor" --ticket INC12345 --body-file note.md
#|python -m nifikb learn list            # newest first;  --all includes retired ones
#|python -m nifikb learn for SALES_20260926.csv stg_sales
#|python -m nifikb learn retire <id> --reason "vendor fixed the export" [--replaced-by <id>]
#|```
#|
#|Or write the file by hand (it is picked up on the next `build`; `learn add` makes it searchable immediately):
#|
#|```markdown
#|---
#|id: 2026-09-26-sales-feed-pipe-delimiter
#|title: SALES feed switches to pipe delimiter at month end
#|kind: pattern            # fix | pattern | gotcha | context | faq
#|date: 2026-09-26
#|author: sanjay
#|tags: [delimiter, vendor]
#|applies_to: [SALES_*.csv, stg_sales, MetadataLookup, OBJ_DEFINITION:12]
#|ticket: INC12345
#|status: active           # active | obsolete
#|---
#|## Symptom
#|Month-end SALES files fail with "Structure mismatch", all other days load.
#|## Cause
#|The vendor's month-end export uses `|`; OBJ_DEFINITION:12 has DELIMITER `,`.
#|## Fix
#|Vendor agreed to always send `,` (INC12345). Until then re-drop the file after converting.
#|## How to spot it next time
#|`diagnose --file <name> --sample <file>` shows one header containing `|`.
#|```
#|
#|`applies_to` is what makes a learning show up automatically in `diagnose` and `find_learnings`: use file names or
#|patterns (`SALES_*.csv`, `SALES_YYYYMMDD.csv`), table names, feed / API names, processor names or short ids, and config
#|rows as `TABLE:id`.
#|
#|## Keeping it healthy
#|
#|- One lesson per file; specific titles. Update by retiring the old learning and adding a new one (history is kept).
#|- Only what the KB cannot derive: causes, quirks, procedures, conventions — not copies of flow / table facts.
#|- **Never** secrets, tokens, customer data. Passwords and bearer tokens are redacted automatically, but review anyway.
#|- Review monthly: retire what no longer holds; move lessons that keep recurring into `context.md`.
#@@ FILE knowledge/context.md tc c271d68c80171159
#|# Team context
#|
#|Curated by the team; agents read this at the start of every session (kb_overview). Keep it short and current.
#|Promote recurring learnings from `learnings/` into here.
#|
#|## Environments
#|- (e.g. PROD NiFi cluster URL, DEV/UAT, which DB holds the metadata tables)
#|
#|## Ownership / escalation
#|- (who owns which feeds / source systems, who can change OBJ_* rows, on-call rota)
#|
#|## Conventions
#|- (file naming, how new feeds are onboarded, which columns in OBJ_DEFINITION mean what)
#|
#|## Known quirks
#|- (things that look wrong but are intended, recurring vendor issues)
#@@ FILE knowledge/learnings/.keep tn e3b0c44298fc1c14
#@@ FILE nifikb.toml t 595032d5c8ab336e
#|# =====================================================================================================================
#|# nifikb configuration - the ONLY file you edit.
#|#   * Paths may be absolute or relative to this file; ${VARS} are expanded.
#|#   * No secrets in here: passwords come from an environment variable (password_env) or a protected file
#|#     (password_file, chmod 600 on Linux).
#|#   * After editing:  python -m nifikb build   then   python -m nifikb doctor
#|# =====================================================================================================================
#|
#|db_refresh_hours = 24                    # how often table schemas are re-read (build --refresh-db forces it)
#|
#|# ---- 1. NiFi -------------------------------------------------------------------------------------------------------
#|[nifi]
#|home = "C:/path/to/nifi"                 # NiFi install folder: conf/flow.json.gz, lib/*.nar and logs/ are read from here
#|# flow_file = "copies/flow.json.gz"      # or a copied flow file, when NiFi runs on another machine
#|extra_nar_dirs = []                      # folders with custom NARs that are not in <home>/lib
#|
#|[logs]                                   # nifi-app*.log / nifi-bootstrap*.log - read incrementally, only warnings / errors kept
#|# dirs = ["/opt/nifi/logs"]              # default: <home>/logs
#|keep_days = 14                           # keep this many days of events (counted back from the newest one)
#|# initial_tail_mb = 200                  # first run on a huge log: only read its last N MB
#|
#|# [nifi_api]                             # optional, read-only: provenance ("where was my file dropped, why") + live bulletins
#|# url = "https://nifi-host:8443/nifi-api"
#|# username = "readonly_user"             # needs the NiFi policies "query provenance" + "view provenance"
#|# password_env = "NIFIKB_NIFI_PASSWORD"  # or: password_file = "~/.nifikb/nifi.pw"
#|# ca_cert = "/etc/pki/nifi-ca.pem"       # CA of NiFi's certificate;  verify_ssl = false only for a quick test
#|# client_cert = "me.pem"                 # instead of username / password when NiFi uses client certificates
#|# client_key = "me.key"
#|# token_env = "NIFIKB_NIFI_TOKEN"        # or a pre-issued bearer token (Kerberos / OIDC setups)
#|
#|# [registry]                             # optional, read-only: NiFi Registry version history (who changed a versioned flow, when, why)
#|# url = "https://registry-host:18443/nifi-registry-api"
#|# username = "readonly_user"
#|# password_env = "NIFIKB_REGISTRY_PASSWORD"
#|# ca_cert = "/etc/pki/nifi-ca.pem"
#|
#|# ---- 2. Code -------------------------------------------------------------------------------------------------------
#|[code]
#|repos = []                               # Bitbucket clones: custom NAR projects (Maven / Java), scripts, Spark job scripts
#|
#|# ---- 3. Databases (read-only users only) ---------------------------------------------------------------------------
#|# One block per database. The flow's DBCP connection pools are matched by host + port + database of their JDBC URL.
#|# [[databases]]
#|# name = "metadata"
#|# kind = "mariadb"                       # mariadb | mysql | postgres | sqlite
#|# host = "db-host"
#|# port = 3306
#|# database = "nifi_meta"
#|# user = "readonly_user"
#|# password_env = "NIFIKB_DB_PASSWORD"    # or: password_file = "~/.nifikb/db.pw"
#|# include_tables = []                    # also document these tables (SQL LIKE / glob patterns, e.g. "file_%")
#|# profile_tables = []                    # list distinct values of low-cardinality text columns (status, source, ...)
#|# sample_rows = 0                        # >0 adds a few masked sample rows per table
#|
#|# ---- 4. Metadata config tables (OBJ_DEFINITION, OBJ_STRUCTURE, feed / API / server config, ...) --------------------
#|# Enables `diagnose` / `investigate` by file / feed / table, a masked snapshot of the config rows, their change history,
#|# and definition checks. Roles and relations are auto-detected: kb/metadata.md shows what was detected - override only
#|# what is wrong.
#|# [metadata]
#|# db = "metadata"                        # the [[databases]] name that holds the config tables
#|# target_db = "none"                     # loads go to HDFS / S3 files: no target-table checks. Or the [[databases]] name
#|#                                        #   holding the load tables, to check definitions against them.
#|# tables = ["OBJ_%", "%_CONFIG", "%_CONFIG_%", "%_DEFINITION", "%_STRUCTURE", "%_METADATA%"]   # which tables are config
#|# refresh_hours = 1                      # re-read the config rows (and record row changes) at most this often
#|# snapshot_max_rows = 20000              # rows per config table kept (masked); structure table: structure_max_rows
#|# --- overrides, only if kb/metadata.md shows a wrong guess:
#|# definition_table = "OBJ_DEFINITION"    # one row per file / object
#|# definition_id = "OBJ_ID"
#|# definition_keys = ["FILE_NAME", "TABLE_NAME"]   # what file / table names are matched against (patterns *, %, YYYYMMDD, regex)
#|# definition_target = "TABLE_NAME"       # the table a file is loaded into
#|# definition_location = "HDFS_PATH"      # the HDFS / S3 location it is written to
#|# structure_table = "OBJ_STRUCTURE"      # one row per column of a definition
#|# structure_parent = "OBJ_ID"
#|# structure_field = "COL_NAME"
#|# structure_type = "DATA_TYPE"
#|# structure_order = "COL_SEQ"
#|# structure_length = "COL_LENGTH"
#|# structure_nullable = "NULLABLE_FLAG"   # a column named like MANDATORY / REQUIRED / NOT_NULL is read as "required"
#|# structure_path = "JSON_PATH"           # JSON path per column for API / JSON feeds ($.data[*].customer.name)
#|# [[metadata.relations]]                 # joins that are not declared as foreign keys
#|# child = "SOURCE_FEED_CONFIG.OBJ_ID"
#|# parent = "OBJ_DEFINITION.OBJ_ID"
#|
#|# ---- 5. Target storage, ticket system, other environments (all optional, all read-only) ----------------------------
#|# [targets]                             # read-only look at what loads wrote (investigate / target): listings + Parquet footer
#|# location_template = "s3://datalake/raw/{table_lower}/"   # when OBJ_DEFINITION has no location column: where {table} lands
#|# hdfs_url = "https://namenode:9871/webhdfs/v1"   # WebHDFS for hdfs:// and /paths (or leave out to use the `hdfs` CLI)
#|# hdfs_user = "nifikb"                   # simple auth; or kerberos = true (uses `curl --negotiate` with the kinit ticket)
#|# s3_profile = "readonly"                # aws CLI / boto3 profile; s3_endpoint / s3_region for S3-compatible stores
#|# max_download_mb = 200                  # hdfs CLI only: largest file copied to read its Parquet schema
#|
#|# [tickets]                             # Jira / ServiceNow: `ticket <id>` reads it, investigates, drafts a reply
#|# kind = "servicenow"                    # or "jira"
#|# url = "https://acme.service-now.com"   # Jira: "https://acme.atlassian.net" or the Jira Server base URL
#|# username = "nifikb.integration"        # Jira Cloud: the account e-mail (with token_env = API token)
#|# password_env = "NIFIKB_TICKET_PASSWORD"   # or token_env (Jira Server PAT / OAuth token, sent as Bearer when no username)
#|# table = "incident"                     # ServiceNow table
#|# note_field = "work_notes"              # ServiceNow: where --post writes (work_notes = internal)
#|
#|# [environments.uat]                     # other environments for `compare --env uat` ("works in UAT, fails in PROD")
#|# flow_file = "copies/uat/flow.json.gz"  # its flow (copy it over; read-only)
#|# db = "metadata_uat"                    # the [[databases]] name holding its config tables (read-only user)
#|
#|# ---- 6. Load audit, daily report, web page -------------------------------------------------------------------------
#|# [audit]                                # the platform's per-file load log: investigate shows the last load of a file
#|# db = "metadata"                        # [[databases]] name (default: the metadata db)
#|# table = "FILE_LOAD_AUDIT"              # auto-detected (a table named like *audit* / *load_log* with a file-name column)
#|# file_column = "FILE_NAME"              # overrides, only if kb/INDEX / doctor shows a wrong guess:
#|# status_column = "LOAD_STATUS"
#|# time_column = "LOAD_TS"
#|# error_column = "ERROR_MSG"
#|# rows_column = "ROW_COUNT"
#|# link_column = "OBJ_ID"                 # the definition id, to list all loads of one definition
#|
#|# [report]                               # python -m nifikb report --send (e.g. scheduled daily)
#|# email_to = ["nifi-team@company.com"]
#|# email_from = "nifikb@company.com"
#|# smtp_host = "smtp.company.com"
#|# smtp_port = 25
#|# smtp_starttls = false
#|# smtp_user = ""                         # + smtp_password_env / smtp_password_file when the relay needs a login
#|# webhook_url_env = "NIFIKB_WEBHOOK"     # Teams / Slack incoming-webhook URL (kept out of this file)
#|
#|# [web]                                  # python -m nifikb web - self-service page for colleagues (read-only)
#|# host = "127.0.0.1"                     # "0.0.0.0" to reach it from other machines (then set a login)
#|# port = 8765
#|# user = "support"                       # HTTP basic login shared by the team
#|# password_env = "NIFIKB_WEB_PASSWORD"   # or password_file
#|
#|# ---- 7. Where things are written -----------------------------------------------------------------------------------
#|[output]
#|dir = "kb"                               # generated knowledge base (markdown + kb.sqlite) - rebuilt, never edited by hand
#|
#|[knowledge]
#|dir = "knowledge"                        # team context + learnings written by people and agents - kept, commit it to git
#@@ END part 1 of 1 files 72
