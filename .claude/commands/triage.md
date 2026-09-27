---
description: Triage a NiFi support ticket end to end (metadata, flow, custom code) and record what was learned
argument-hint: <ticket text, ticket id + details, or a file name>
---
Triage this NiFi support ticket by following the "Triage playbook" in CLAUDE.md exactly:

$ARGUMENTS

Steps: `kb_overview` if you have not yet this session → only a Jira / ServiceNow id given: `ticket` with it (reads the
ticket and runs investigate); otherwise `investigate` with everything the ticket gives (file, feed,
table, error_text, headers in file order or sample_path; `live=true` if config rows may have changed) → read the ranked
causes and evidence → only if not conclusive: `diagnose` / `provenance` / `logs` / `late_files` (file not received) /
`check_target_output` (loaded but data wrong) / `search` / `show` / `trace` / `sql` →
answer as **Cause / Evidence / Fix / Also noticed**, with short ids, `TABLE:id`, `file:line` and log lines.
Propose fixes (SQL for config rows, property changes) for a human to apply; never apply them.

Finally, if the cause or fix is reusable and not derivable from the KB, call `add_learning` (kind, applies_to, tags,
ticket, author "claude", body with Symptom / Cause / Fix / How to spot it next time) — retire an outdated learning instead
of duplicating it — and tell me the learning id. If nothing reusable was learned, say so and do not add one.
