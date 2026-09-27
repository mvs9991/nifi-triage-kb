"""Team knowledge that the flow, code and databases cannot tell: what we learned while fixing tickets.

knowledge/
  context.md            curated team context (owners, environments, conventions, quirks) - humans maintain it
  learnings/<id>.md     one learning per file, written by people or by agents (Claude, Gemini, ...) after a ticket

A learning file is markdown with a small header:

    ---
    id: 2026-09-26-sales-feed-pipe-delimited
    title: SALES feed switches to pipe delimiter at month end
    kind: pattern            # fix | pattern | gotcha | context | faq
    date: 2026-09-26
    author: claude
    tags: [delimiter, sales]
    applies_to: [SALES_YYYYMMDD.csv, stg_sales, MetadataLookup]
    ticket: INC12345
    status: active           # active | obsolete
    ---
    ## Symptom / ## Cause / ## Fix / ## How to spot it next time

Files are plain text on purpose: reviewable in git, editable by hand, safe with several agents writing at once.
"""
import datetime as _dt
import os
import re
from pathlib import Path

from .db import BEARER_RE
from .util import REDACTED, redact_secrets, slugify

KINDS = ("fix", "pattern", "gotcha", "context", "faq")
LIST_KEYS = ("tags", "applies_to")
MAX_BODY = 20000
SECRETISH = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*(?!<redacted>|\*\*\*)\S{4,}")
CONTEXT_TEMPLATE = """# Team context

Curated by the team; agents read this at the start of every session (kb_overview). Keep it short and current.
Promote recurring learnings from `learnings/` into here.

## Environments
- (e.g. PROD NiFi cluster URL, DEV/UAT, which DB holds the metadata tables)

## Ownership / escalation
- (who owns which feeds / source systems, who can change OBJ_* rows, on-call rota)

## Conventions
- (file naming, how new feeds are onboarded, which columns in OBJ_DEFINITION mean what)

## Known quirks
- (things that look wrong but are intended, recurring vendor issues)
"""


def root(cfg):
    return Path(cfg["knowledge"]["dir"])


def ensure(cfg):
    r = root(cfg)
    (r / "learnings").mkdir(parents=True, exist_ok=True)
    if not (r / "context.md").exists():
        (r / "context.md").write_text(CONTEXT_TEMPLATE, encoding="utf-8")
    return r


def clean(text):
    """Secrets never enter the knowledge folder (it is sent to AI providers and committed to git)."""
    text = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(text or ""))
    return SECRETISH.sub(lambda m: f"{m.group(1)}={REDACTED}", text)


# ---------------------------------------------------------------------------------------------- parse / write
def parse(text, path=None):
    meta, body = {}, text
    m = re.match(r"﻿?---\s*\n(.*?)\n---\s*\n?(.*)\Z", text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), re.sub(r"\s+#.*$", "", v).strip()
            if k in LIST_KEYS:
                v = [x.strip().strip("'\"") for x in v.strip("[]").split(",") if x.strip()]
            meta[k] = v
    meta.setdefault("id", Path(path).stem if path else "")
    meta.setdefault("title", next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.strip()), meta["id"]))
    meta.setdefault("status", "active")
    meta.setdefault("kind", "fix")
    for k in LIST_KEYS:
        meta.setdefault(k, [])
    meta["body"] = body.strip()
    meta["path"] = str(path) if path else None
    return meta


def render(meta):
    head = ["---"]
    for k in ("id", "title", "kind", "date", "author", "tags", "applies_to", "ticket", "status", "replaced_by"):
        v = meta.get(k)
        if v in (None, "", []):
            continue
        head.append(f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}")
    return "\n".join(head + ["---", "", meta.get("body", "").strip(), ""])


def load_all(cfg, include_obsolete=True):
    d = root(cfg) / "learnings"
    out = []
    for p in sorted(d.glob("*.md")) if d.is_dir() else []:
        try:
            item = parse(p.read_text(encoding="utf-8"), p)
        except (OSError, UnicodeDecodeError):
            continue
        if include_obsolete or item["status"] != "obsolete":
            out.append(item)
    out.sort(key=lambda x: (x.get("date") or "", x["id"]), reverse=True)
    return out


def get(cfg, ident):
    for item in load_all(cfg):
        if item["id"] == ident:
            return item
    matches = [i for i in load_all(cfg) if i["id"].startswith(ident) or ident.lower() in i["id"]]
    return matches[0] if len(matches) == 1 else None


def add(cfg, title, body, kind="fix", tags=(), applies_to=(), ticket=None, author=None):
    """Write one learning; returns (meta, warnings). Secrets are redacted before anything touches disk."""
    title = clean(" ".join((title or "").split()))
    body = clean(body or "").strip()
    if not title:
        raise ValueError("a learning needs a title")
    if not body:
        raise ValueError("a learning needs a body (symptom, cause, fix, how to spot it)")
    if len(body) > MAX_BODY:
        raise ValueError(f"body is {len(body)} characters; keep a learning under {MAX_BODY} (link to the ticket instead)")
    kind = (kind or "fix").lower()
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    warnings = []
    existing = load_all(cfg, include_obsolete=False)
    words = set(re.findall(r"\w{4,}", title.lower()))
    for e in existing:
        other = set(re.findall(r"\w{4,}", e["title"].lower()))
        if words and len(words & other) / len(words | other) >= 0.6:
            warnings.append(f"similar learning exists: {e['id']} - {e['title']} (consider updating or retiring it)")
    date = _dt.date.today().isoformat()
    d = ensure(cfg) / "learnings"
    ident = f"{date}-{slugify(title, 50)}"
    n = 2
    while (d / f"{ident}.md").exists():
        ident = f"{date}-{slugify(title, 50)}-{n}"
        n += 1
    meta = {"id": ident, "title": title, "kind": kind, "date": date,
            "author": clean(author or os.environ.get("NIFIKB_AUTHOR") or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"),
            "tags": sorted({clean(t).strip().lower() for t in tags if t and t.strip()}),
            "applies_to": [clean(a).strip() for a in applies_to if a and a.strip()],
            "ticket": clean(ticket) if ticket else None, "status": "active", "body": body}
    path = d / f"{ident}.md"
    path.write_text(render(meta), encoding="utf-8")
    meta["path"] = str(path)
    if re.search(r"(?i)\b(password|secret|token)\b", body) and REDACTED not in body:
        warnings.append("the body mentions passwords / secrets - double-check nothing sensitive was written")
    return meta, warnings


def retire(cfg, ident, reason=None, replaced_by=None):
    item = get(cfg, ident)
    if not item:
        raise ValueError(f"no learning '{ident}'")
    item["status"] = "obsolete"
    if replaced_by:
        item["replaced_by"] = replaced_by
    if reason:
        item["body"] = item["body"] + f"\n\n> Retired {_dt.date.today().isoformat()}: {clean(reason)}"
    Path(item["path"]).write_text(render(item), encoding="utf-8")
    return item


# ---------------------------------------------------------------------------------------------- relevance
def relevant(cfg, terms, limit=5):
    """Active learnings whose applies_to / tags / title match any of the terms (file names, tables, processor names,
    ids, feed names). applies_to values may be patterns (SALES_*.csv, SALES_YYYYMMDD.csv)."""
    from .metadata import pattern_regex
    terms = [str(t) for t in terms if t and len(str(t)) >= 3]
    low = {t.lower() for t in terms}
    scored = []
    for item in load_all(cfg, include_obsolete=False):
        score = 0
        for a in item["applies_to"]:
            al = a.lower()
            if al in low:
                score += 3
                continue
            rx = pattern_regex(a)
            if rx and any(rx.match(t) for t in terms):
                score += 3
            elif any(len(t) >= 6 and (t in al or al in t) for t in low):
                score += 1
        score += sum(2 for t in item["tags"] if t.lower() in low)
        title = item["title"].lower()
        score += sum(1 for t in low if len(t) >= 5 and t in title)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda x: (x[0], x[1].get("date") or ""), reverse=True)
    return [dict(i, score=s) for s, i in scored[:limit]]


def search_docs(cfg):
    """Search-index entries for every learning and for context.md."""
    docs = []
    for item in load_all(cfg):
        rel = f"../knowledge/learnings/{Path(item['path']).name}"
        docs.append({"kind": "learning" if item["status"] != "obsolete" else "learning-obsolete", "ref": item["id"],
                     "title": item["title"], "doc": rel,
                     "body": " ".join([item["body"], " ".join(item["tags"]), " ".join(item["applies_to"]), item.get("ticket") or ""])})
    ctx = root(cfg) / "context.md"
    if ctx.exists():
        docs.append({"kind": "context", "ref": "context.md", "title": "Team context", "doc": "../knowledge/context.md",
                     "body": ctx.read_text(encoding="utf-8")})
    return docs


def context_text(cfg, max_chars=12000):
    ctx = root(cfg) / "context.md"
    if not ctx.exists():
        return ""
    text = ctx.read_text(encoding="utf-8")
    if text.strip() == CONTEXT_TEMPLATE.strip():
        return ""  # untouched template adds nothing
    return text if len(text) <= max_chars else text[:max_chars] + "\n[… context.md continues]"


def format_item(item, full=True):
    head = (f"{item['id']} [{item['kind']}{', OBSOLETE' if item['status'] == 'obsolete' else ''}] {item['title']}"
            + (f" · tags: {', '.join(item['tags'])}" if item["tags"] else "")
            + (f" · applies to: {', '.join(item['applies_to'])}" if item["applies_to"] else "")
            + (f" · ticket {item['ticket']}" if item.get("ticket") else "")
            + (f" · {item.get('date')} by {item.get('author')}" if item.get("date") else ""))
    return head + ("\n\n" + item["body"] if full else "")


# ------------------------------------------------------------------------------------------------ suggestions
def suggestions(cfg, store, days=30, min_count=3, limit=10):
    """Causes that keep coming back in investigations and that no active learning covers yet:
    [{signature, count, keys, days, example, kind}], most frequent first."""
    import re
    import time
    rows = store.investigations_since(time.time() - days * 86400)
    groups = {}
    for r in rows:
        g = groups.setdefault(r["signature"], {"signature": r["signature"], "kind": r["kind"], "count": 0, "keys": [], "days": set(),
                                               "example": r["cause"]})
        g["count"] += 1
        g["days"].add(time.strftime("%Y-%m-%d", time.localtime(r["ts"])))
        if r["key"] not in g["keys"]:
            g["keys"].append(r["key"])
    items = load_all(cfg, include_obsolete=False)
    out = []
    for g in groups.values():
        if g["count"] < min_count or (len(g["days"]) < 2 and len(g["keys"]) < 2):
            continue  # one person re-running the same check is not a recurring problem
        label = g["example"].split(":", 1)[0] if ":" in g["example"] else ""
        words = {w for w in re.findall(r"[a-z][a-z_]{4,}", g["signature"].lower()) if w not in STOP}
        terms = g["keys"] + ([label] if label else [])
        covered = False
        for item in relevant(cfg, terms, limit=10) if items else []:
            text = f"{item['title']} {item['body']}".lower()
            if item["score"] >= 3 and sum(1 for w in words if w in text) >= min(2, len(words)):
                covered = True
                break
        if not covered:
            out.append(dict(g, days=sorted(g["days"])))
    out.sort(key=lambda g: (-g["count"], -len(g["keys"])))
    return out[:limit]


STOP = {"structure", "config", "table", "column", "columns", "field", "fields", "processor", "logged", "error", "errors", "which",
        "there", "their", "since", "last", "this", "that", "with", "from", "into", "the", "and", "load", "file", "files"}


def format_suggestions(items):
    return [f"seen {g['count']}x ({', '.join(g['keys'][:3])}{' …' if len(g['keys']) > 3 else ''}; {g['days'][0]}"
            + (f" .. {g['days'][-1]}" if len(g["days"]) > 1 else "") + f") and no learning covers it: {g['example'][:220]}"
            for g in items]
