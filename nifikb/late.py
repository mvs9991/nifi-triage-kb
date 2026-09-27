"""Late / missing files: learn each feed's arrival pattern from the load-audit history (successful loads) and flag the
feeds whose next file is overdue - before a user raises a ticket.

Per definition (audit link column) or, without one, per file-name shape (SALES_20260926.csv -> sales_#.csv):
  intra-day feeds (median gap < 20 h)  late when nothing arrived for 3 x the usual gap (at least 1 h)
  daily feeds                          expected on the weekdays it usually arrives, around its usual time of day;
                                       late when today's file is past that time + tolerance (the spread of past arrivals, >= 1 h)
  weekly / monthly feeds               late when the gap since the last arrival exceeds 1.5 x the usual gap
Feeds with fewer than `min_history` arrivals are not judged."""
import datetime as dt
import statistics
from collections import defaultdict
from pathlib import PurePath

from . import audit as auditmod, db as dbmod, metadata as metamod


def _when(v):
    if isinstance(v, dt.datetime):
        return v
    if isinstance(v, dt.date):
        return dt.datetime(v.year, v.month, v.day)
    s = str(v or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return dt.datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return None


def history(cfg, model, days):
    """Audit rows of the last `days` days: [{file, when, failed, link}] (oldest first)."""
    if not model.get("time_column"):
        raise ValueError("the load-audit table has no time column ([audit] time_column)")
    a = auditmod.settings(cfg)
    dcfg = next(d for d in cfg["databases"] if d["name"] == a["db"])
    conn, dialect = dbmod.connect(dcfg)
    try:
        q = '"' if dialect != "mysql" else "`"
        cols = [c for c in (model["file_column"], model["time_column"], model.get("status_column"), model.get("link_column")) if c]
        since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        sql = (f"SELECT {', '.join(f'{q}{c}{q}' for c in cols)} FROM {auditmod._fq(dialect, model.get('schema'), model['table'])} "
               f"WHERE {q}{model['time_column']}{q} >= {dbmod._ph(dialect)} ORDER BY {q}{model['time_column']}{q} LIMIT 200000")
        rows = dbmod._rows(conn, sql, (since,))
    finally:
        conn.close()
    out = []
    for r in rows:
        when = _when(r.get(model["time_column"]))
        if when:
            out.append({"file": r.get(model["file_column"]), "when": when, "failed": auditmod.is_failure(model, r),
                        "link": r.get(model["link_column"]) if model.get("link_column") else None})
    return out


def _group_key(row):
    if row["link"] is not None:
        return ("id", str(row["link"]))
    name = PurePath(str(row["file"] or "").replace("\\", "/")).name
    return ("shape", metamod._shape(name))


def _fmt_gap(seconds):
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    if seconds < 2 * 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} days"


def analyse(rows, now=None, min_history=5, labels=None):
    """[{key, label, kind, last, expected, late_by, message, last_failed}] for overdue feeds, most overdue first."""
    now = now or dt.datetime.now()
    groups = defaultdict(list)
    for r in rows:
        groups[_group_key(r)].append(r)
    out = []
    for key, rs in groups.items():
        rs.sort(key=lambda r: r["when"])
        ok = [r["when"] for r in rs if not r["failed"]]
        if len(ok) < min_history:
            continue
        label = (labels or {}).get(key[1]) or (PurePath(str(rs[-1]["file"] or "").replace("\\", "/")).name if key[0] == "id" else key[1])
        last = ok[-1]
        last_failed = rs[-1]["failed"] and rs[-1]["when"] > last
        gaps = [(b - a).total_seconds() for a, b in zip(ok, ok[1:]) if (b - a).total_seconds() > 60]
        if not gaps:
            continue
        gap = statistics.median(gaps)
        since_last = (now - last).total_seconds()
        item = None
        if gap < 20 * 3600:
            allowed = max(3 * gap, 3600)
            if since_last > allowed:
                item = {"kind": "intra-day", "expected": last + dt.timedelta(seconds=gap), "late_by": since_last - gap,
                        "message": f"no file for {_fmt_gap(since_last)} (usually every {_fmt_gap(gap)}); last {last:%Y-%m-%d %H:%M}"}
        elif gap < 2.5 * 86400:
            first_per_day = {}
            for w in ok:
                first_per_day.setdefault(w.date(), w)
            minutes = [w.hour * 60 + w.minute for w in first_per_day.values()]
            usual = statistics.median(minutes)
            spread = statistics.median([abs(m - usual) for m in minutes]) if len(minutes) > 2 else 0
            tolerance = max(60, 3 * spread)
            span_days = max(1, (ok[-1].date() - ok[0].date()).days + 1)
            weeks = max(1, span_days / 7)
            per_weekday = defaultdict(int)
            for d in first_per_day:
                per_weekday[d.weekday()] += 1
            weekdays = {wd for wd in range(7) if per_weekday[wd] / weeks >= 0.6}
            due = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=usual + tolerance)
            if now.weekday() in weekdays and now > due and last.date() < now.date():
                item = {"kind": "daily", "expected": due - dt.timedelta(minutes=tolerance),
                        "late_by": (now - due).total_seconds() + tolerance * 60,
                        "message": f"today's file not loaded - usually by {int(usual // 60):02d}:{int(usual % 60):02d} "
                                   f"(±{tolerance:.0f} min, on {_days(weekdays)}); last {last:%Y-%m-%d %H:%M}"}
        else:
            if since_last > 1.5 * gap + 3600:
                item = {"kind": "periodic", "expected": last + dt.timedelta(seconds=gap), "late_by": since_last - gap,
                        "message": f"no file for {_fmt_gap(since_last)} (usually every {_fmt_gap(gap)}); last {last:%Y-%m-%d %H:%M}"}
        if item:
            if last_failed:
                item["message"] += f" - the latest attempt ({rs[-1]['file']}, {rs[-1]['when']:%Y-%m-%d %H:%M}) FAILED"
            item.update(key=key[1], label=label, last=last, last_failed=last_failed)
            out.append(item)
    out.sort(key=lambda i: -i["late_by"])
    return out


def _days(weekdays):
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    if weekdays == set(range(7)):
        return "every day"
    if weekdays == set(range(5)):
        return "Mon-Fri"
    return ", ".join(names[d] for d in sorted(weekdays))


def labels_from_snapshot(store):
    """Definition id -> label (file pattern / name) from the metadata snapshot."""
    model = store.get_meta("metadata_model")
    if not model or not model.get("definition_table"):
        return {}
    rows = store.get_meta_rows(exclude=model.get("structure_table")).get(model["definition_table"], [])
    return {str(r.get(model["definition_id"])): metamod.definition_label(model, r) for r in rows}


def late_files(cfg, store, days=35, now=None, min_history=5):
    model = store.get_meta("audit_model")
    if not model:
        return None
    return analyse(history(cfg, model, days), now=now, min_history=min_history, labels=labels_from_snapshot(store))


def format_items(items, model=None):
    if items is None:
        return ["load audit not configured ([audit]) - no arrival history to learn from"]
    if not items:
        return ["no late or missing files (feeds with enough load history)"]
    return [f"**{i['label']}**: {i['message']}" for i in items]
