# nifi-kb 0.5.0 - paste bundle, part 1 of 5 - 14 files. Save as nifi-kb-0.5.0-bundle-part1of5.py, then run:  python nifi-kb-0.5.0-bundle-part1of5.py
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
#@@ END part 1 of 5 files 14
