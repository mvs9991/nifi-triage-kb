"""Daily health report: what went wrong or changed in the last N hours, before anyone raises a ticket.

Sections: live NiFi health, new error patterns (first seen in the window), top recurring errors, NiFi restarts / crashes,
failed loads (load-audit table), config-row changes, flow changes, metadata drift. Output as markdown / HTML; optional
delivery by e-mail (SMTP) or a Teams / Slack incoming webhook - only with an explicit --send and a [report] section.
"""
import html
import json
import os
import smtplib
import time
import urllib.request
from email.message import EmailMessage
from pathlib import Path

from . import audit as auditmod, logs as lg, nifiapi


def build_report(cfg, store, names, hours=24.0):
    lg.index(cfg, store, log=lambda m: None)
    now = time.time()
    newest_log = store.db.execute("SELECT MAX(epoch) FROM log_events").fetchone()[0] or now
    since_log = newest_log - hours * 3600  # logs copied from elsewhere may be older than "now"
    since = now - hours * 3600
    sec = []
    stats = {}

    api = nifiapi.settings(cfg)
    if api:
        try:
            h = nifiapi.health(nifiapi.Client(api), versioned=store.versioned_groups())
            stats["live problems"] = len(h["problems"])
            sec.append(("Live NiFi health", [f"**{p['severity']}** {p['kind']}: {p['message']}" + (f" ({names[p['component_id']]})"
                                             if p.get("component_id") in names else "") for p in h["problems"]]
                        or ["no problems (no back-pressure, stuck queues, invalid processors; repositories fine)"]))
        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
            sec.append(("Live NiFi health", [f"not available: {e}"]))

    new = store.db.execute(
        "SELECT template, level, component_id, component_type, COUNT(*) n, MIN(ts) first, MAX(cause) cause, MAX(message) sample "
        "FROM log_events WHERE level IN ('ERROR','FATAL') GROUP BY template, component_id HAVING MIN(epoch) >= ? ORDER BY n DESC LIMIT 15",
        (since_log,)).fetchall()
    stats["new error patterns"] = len(new)
    sec.append(("New error patterns (first seen in this window)", [
        f"x{r['n']} {names.get(r['component_id'], r['component_type'] or 'NiFi')}: {lg.compact(r['sample'])[:220]}"
        + (f" — cause: {r['cause'][:160]}" if r["cause"] else "") for r in new] or ["none"]))
    top = store.db.execute(
        "SELECT template, component_id, component_type, COUNT(*) n, MAX(cause) cause, MAX(message) sample FROM log_events "
        "WHERE level IN ('ERROR','FATAL') AND epoch >= ? GROUP BY template, component_id ORDER BY n DESC LIMIT 10", (since_log,)).fetchall()
    stats["errors logged"] = sum(r["n"] for r in top)
    sec.append(("Most frequent errors", [f"x{r['n']} {names.get(r['component_id'], r['component_type'] or 'NiFi')}: "
                                          f"{lg.compact(r['sample'])[:200]}" + (f" — cause: {r['cause'][:140]}" if r["cause"] else "")
                                          for r in top] or ["none"]))
    life = store.db.execute("SELECT ts, message FROM log_events WHERE (level = 'LIFECYCLE' OR (file LIKE '%bootstrap%' AND level IN "
                            "('WARN','ERROR','FATAL'))) AND epoch >= ? ORDER BY epoch", (since_log,)).fetchall()
    if life:
        sec.append(("NiFi lifecycle (bootstrap log: starts, stops, crashes, warnings)", [f"{r['ts'][:19]} {r['message'][:200]}" for r in life]))

    amodel = store.get_meta("audit_model")
    if amodel and amodel.get("time_column"):
        try:
            rows = failed_loads(cfg, amodel, since)
            stats["failed loads"] = len(rows)
            sec.append(("Failed loads (load audit)", [auditmod.summarize(amodel, r) for r in rows[:30]] or ["none"]))
        except Exception as e:  # DB unreachable etc.
            sec.append(("Failed loads (load audit)", [f"not available: {e}"]))

    changes = store.db.execute("SELECT ts, change FROM meta_changes WHERE ts >= ? ORDER BY ts DESC LIMIT 40", (since,)).fetchall()
    stats["config row changes"] = len(changes)
    if changes:
        sec.append(("Config-row changes", [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['ts']))} {r['change']}" for r in changes]))
    flow = store.db.execute("SELECT ts, change FROM changelog WHERE ts >= ? AND change NOT LIKE 'config %' ORDER BY ts DESC LIMIT 40",
                            (since,)).fetchall()
    if flow:
        sec.append(("Flow changes", [f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(r['ts']))} {r['change']}" for r in flow]))
    drift = store.db.execute("SELECT severity, message FROM findings WHERE kind = 'metadata-drift' ORDER BY severity").fetchall()
    stats["definitions with drift"] = len(drift)
    if drift:
        sec.append(("Metadata drift (definitions that disagree with their target)",
                    [f"**{r['severity']}** {r['message'][:220]}" for r in drift[:15]] + ([f"… {len(drift) - 15} more"] if len(drift) > 15 else [])))
    for name, fn in (("Late / missing files", late_files_section), ("Suggested learnings", learning_suggestions_section)):
        try:
            lines = fn(cfg, store)
        except Exception as e:  # optional sections must never break the report
            lines = [f"not available: {e}"]
        if lines:
            sec.append((name, lines))
    return {"title": f"NiFi daily report — last {hours:g} h — {time.strftime('%Y-%m-%d %H:%M')}", "stats": stats, "sections": sec}


def late_files_section(cfg, store):
    from . import late
    items = late.late_files(cfg, store)
    return late.format_items(items)[:40] if items else []


def learning_suggestions_section(cfg, store):
    from . import learnings as lm
    return lm.format_suggestions(lm.suggestions(cfg, store))


def failed_loads(cfg, model, since):
    from . import db as dbmod
    a = auditmod.settings(cfg)
    dcfg = next(d for d in cfg["databases"] if d["name"] == a["db"])
    conn, dialect = dbmod.connect(dcfg)
    try:
        q = '"' if dialect != "mysql" else "`"
        p = dbmod._ph(dialect)
        sql = (f"SELECT * FROM {auditmod._fq(dialect, model.get('schema'), model['table'])} WHERE {q}{model['time_column']}{q} >= {p} "
               f"ORDER BY {q}{model['time_column']}{q} DESC LIMIT 500")
        rows = dbmod._rows(conn, sql, (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(since)),))
        return [{k: dbmod.mask_value(k, v) for k, v in r.items()} for r in rows if auditmod.is_failure(model, r)]
    finally:
        conn.close()


def to_markdown(r):
    L = [f"# {r['title']}", "", " · ".join(f"{k}: **{v}**" for k, v in r["stats"].items())]
    for title, lines in r["sections"]:
        L += ["", f"## {title}"] + [f"- {x}" for x in lines]
    return "\n".join(L) + "\n"


def to_html(r):
    def inline(t):
        t = html.escape(t)
        parts = t.split("**")
        return "".join(f"<b>{p}</b>" if i % 2 else p for i, p in enumerate(parts))
    body = [f"<h1>{html.escape(r['title'])}</h1>", "<p>" + " · ".join(f"{html.escape(k)}: <b>{v}</b>" for k, v in r["stats"].items()) + "</p>"]
    for title, lines in r["sections"]:
        body.append(f"<h2>{html.escape(title)}</h2><ul>" + "".join(f"<li>{inline(x)}</li>" for x in lines) + "</ul>")
    style = ("body{font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#222;max-width:1100px;margin:20px}"
             "h1{font-size:20px}h2{font-size:16px;margin-top:22px;border-bottom:1px solid #ddd}li{margin:3px 0}")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(r['title'])}</title><style>{style}</style></head>" \
           f"<body>{''.join(body)}</body></html>"


def _secret(c, key):
    if c.get(f"{key}_env") and os.environ.get(c[f"{key}_env"]):
        return os.environ[c[f"{key}_env"]]
    if c.get(f"{key}_file"):
        return Path(c[f"{key}_file"]).read_text(encoding="utf-8").strip()
    return c.get(key)


def send(cfg, r):
    """Deliver per [report]: email (SMTP) and / or webhook (Teams / Slack incoming webhook). Returns what was done."""
    c = cfg.get("report") or {}
    done = []
    if c.get("email_to"):
        msg = EmailMessage()
        msg["Subject"] = r["title"]
        msg["From"] = c.get("email_from", "nifikb@localhost")
        msg["To"] = ", ".join(c["email_to"]) if isinstance(c["email_to"], list) else c["email_to"]
        msg.set_content(to_markdown(r))
        msg.add_alternative(to_html(r), subtype="html")
        with smtplib.SMTP(c.get("smtp_host", "localhost"), int(c.get("smtp_port", 25)), timeout=30) as s:
            if c.get("smtp_starttls"):
                s.starttls()
            if c.get("smtp_user"):
                s.login(c["smtp_user"], _secret(c, "smtp_password") or "")
            s.send_message(msg)
        done.append(f"e-mailed to {msg['To']}")
    url = _secret(c, "webhook_url")
    if url:
        text = to_markdown(r)
        payload = {"text": text[:25000]}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30):
            pass
        done.append("posted to the webhook")
    return done
