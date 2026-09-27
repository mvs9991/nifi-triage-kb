# Team knowledge

Everything here is written by people and by the AI agents (Claude Code, Gemini CLI, …) and is **kept across builds**,
unlike `kb/`, which `nifikb build` regenerates. Commit this folder to git so the whole team (and every agent session)
shares it.

| File | Who writes it | What goes in |
|---|---|---|
| `context.md` | people (agents may suggest edits) | short, curated background: environments, owners / escalation, conventions, known quirks. Every agent session reads it first. |
| `learnings/<id>.md` | agents after solving a ticket, or people | one reusable lesson per file: symptom, cause, fix, how to spot it next time |

## Adding a learning

From an agent: the `add_learning` tool, or the `/learn` command in Claude Code and Gemini CLI.
From a terminal:

```
python -m nifikb learn add --title "SALES feed switches to pipe delimiter at month end" --kind pattern ^
    --applies-to "SALES_*.csv,stg_sales" --tags "delimiter,vendor" --ticket INC12345 --body-file note.md
python -m nifikb learn list            # newest first;  --all includes retired ones
python -m nifikb learn for SALES_20260926.csv stg_sales
python -m nifikb learn retire <id> --reason "vendor fixed the export" [--replaced-by <id>]
```

Or write the file by hand (it is picked up on the next `build`; `learn add` makes it searchable immediately):

```markdown
---
id: 2026-09-26-sales-feed-pipe-delimiter
title: SALES feed switches to pipe delimiter at month end
kind: pattern            # fix | pattern | gotcha | context | faq
date: 2026-09-26
author: sanjay
tags: [delimiter, vendor]
applies_to: [SALES_*.csv, stg_sales, MetadataLookup, OBJ_DEFINITION:12]
ticket: INC12345
status: active           # active | obsolete
---
## Symptom
Month-end SALES files fail with "Structure mismatch", all other days load.
## Cause
The vendor's month-end export uses `|`; OBJ_DEFINITION:12 has DELIMITER `,`.
## Fix
Vendor agreed to always send `,` (INC12345). Until then re-drop the file after converting.
## How to spot it next time
`diagnose --file <name> --sample <file>` shows one header containing `|`.
```

`applies_to` is what makes a learning show up automatically in `diagnose` and `find_learnings`: use file names or
patterns (`SALES_*.csv`, `SALES_YYYYMMDD.csv`), table names, feed / API names, processor names or short ids, and config
rows as `TABLE:id`.

## Keeping it healthy

- One lesson per file; specific titles. Update by retiring the old learning and adding a new one (history is kept).
- Only what the KB cannot derive: causes, quirks, procedures, conventions — not copies of flow / table facts.
- **Never** secrets, tokens, customer data. Passwords and bearer tokens are redacted automatically, but review anyway.
- Review monthly: retire what no longer holds; move lessons that keep recurring into `context.md`.
