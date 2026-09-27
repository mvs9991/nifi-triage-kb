---
description: Save a reusable lesson from this conversation (or from the text given) as a team learning shared with Gemini and people
argument-hint: [what to remember - optional; defaults to the ticket just solved]
---
Record a team learning following the "Team learnings" rules in CLAUDE.md.

What to capture: $ARGUMENTS
(If empty, use the root cause and fix established in this conversation.)

1. `find_learnings` with the file names / tables / feeds / processors involved; if an existing learning covers it, update
   by retiring it (`retire_learning` with `replaced_by`) and adding the corrected one — never create a near duplicate.
2. Only save knowledge the KB cannot derive (not what the flow / code / tables already show), verified in this
   conversation, without secrets or personal data.
3. `add_learning`: specific title, kind, applies_to (file patterns, tables, feeds, processor names / short ids, config
   rows), tags, ticket if known, author "claude", body with ## Symptom, ## Cause, ## Fix, ## How to spot it next time.
4. Show me the saved id and the text. If the lesson keeps recurring, suggest what to add to `knowledge/context.md`.
