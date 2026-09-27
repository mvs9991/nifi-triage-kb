"""Environment comparison ("works in UAT, fails in PROD"): two flows, and the config tables of two databases.

Flows are matched by process-group path + component name + type (ids differ between environments); parameter contexts
by name. Config rows are matched by primary key (the metadata model of the current KB), masked on both sides.
[environments.<name>] in nifikb.toml gives an environment a flow_file and a db, so `compare --env uat` compares it with the
main configuration."""
from collections import Counter
from pathlib import Path

from . import metadata as metamod
from .analyze import Analysis, type_short
from .catalog import Catalog
from .code import CodeIndex
from .flow import load_flow
from .util import REDACTED, SECRET_NAME


def _flow_view(path, cfg):
    flow = load_flow(Path(path))
    an = Analysis(flow, Catalog(), CodeIndex(), cfg).run()
    comps, seen = {}, Counter()
    for c in list(flow.components.values()) + list(flow.services.values()):
        if c["kind"] not in ("PROCESSOR", "CONTROLLER_SERVICE", "INPUT_PORT", "OUTPUT_PORT"):
            continue
        base = f"{(flow.groups.get(c['group_id']) or {}).get('path', '(controller)')} :: {c['name']} [{type_short(c['type']) or c['kind'].lower()}]"
        seen[base] += 1
        key = base if seen[base] == 1 else f"{base} #{seen[base]}"
        props = {f["display"]: ("<sensitive>" if f["source"] == "sensitive" else f["resolved"]) for f in an.props[c["id"]]}
        comps[key] = {"state": c.get("state"), "schedule": f"{c.get('scheduling_strategy')} {c.get('scheduling_period')}"
                      if c["kind"] == "PROCESSOR" else None, "props": props, "auto": sorted(c.get("auto_terminated") or [])}
    params = {}
    for name, ctx in flow.param_contexts.items():
        for k, v in ctx["params"].items():
            params[f"{name} :: {k}"] = "<sensitive>" if v.get("sensitive") else (REDACTED if SECRET_NAME.search(k) else v.get("value"))
    return comps, params


def compare_flows(cfg, left, right, left_name="left", right_name="right", limit=300):
    lc, lp = _flow_view(left, cfg)
    rc, rp = _flow_view(right, cfg)
    out = []
    for k in sorted(set(lc) - set(rc)):
        out.append(f"only in {left_name}: {k}")
    for k in sorted(set(rc) - set(lc)):
        out.append(f"only in {right_name}: {k}")
    for k in sorted(set(lc) & set(rc)):
        a, b = lc[k], rc[k]
        for field in ("state", "schedule", "auto"):
            if a[field] != b[field]:
                out.append(f"{k}: {field} {a[field]} ({left_name}) vs {b[field]} ({right_name})")
        for p in sorted(set(a["props"]) | set(b["props"])):
            va, vb = a["props"].get(p), b["props"].get(p)
            if va != vb and "<sensitive>" not in (va, vb):
                out.append(f"{k}: '{p}' = {_v(va)} ({left_name}) vs {_v(vb)} ({right_name})")
    for k in sorted(set(lp) | set(rp)):
        va, vb = lp.get(k), rp.get(k)
        if va != vb and not (va == vb == "<sensitive>"):
            if k not in lp or k not in rp:
                out.append(f"parameter {k}: only in {left_name if k in lp else right_name}")
            elif "<sensitive>" not in (va, vb):
                out.append(f"parameter {k} = {_v(va)} ({left_name}) vs {_v(vb)} ({right_name})")
    return out[:limit] + ([f"… {len(out) - limit} more differences"] if len(out) > limit else [])


def _v(v):
    s = "∅" if v is None else str(v)
    return f"`{s if len(s) <= 120 else s[:119] + '…'}`"


def compare_config(cfg, store, left_db, right_db, key=None, left_name=None, right_name=None):
    """Row differences of the metadata config tables between two [[databases]] entries (optionally one file / feed)."""
    m = metamod.settings(cfg)
    model = store.get_meta("metadata_model")
    if not m or not model:
        return ["metadata not configured ([metadata] in nifikb.toml) - nothing to compare"]
    dbs = {d["name"]: d for d in cfg["databases"]}
    for name in (left_db, right_db):
        if name not in dbs:
            return [f"unknown database '{name}' - [[databases]] names: {', '.join(dbs)}"]
    st = model.get("structure_table")
    left = metamod.fetch_live(dbs[left_db], m, model)
    right = metamod.fetch_live(dbs[right_db], m, model)
    ids = None
    if key:
        found = metamod.dossier(model, metamod.Rows(left), key)["definitions"] or metamod.dossier(model, metamod.Rows(right), key)["definitions"]
        ids = [d["id"] for d in found]
        if not ids:
            return [f"'{key}' matches no definition in either database"]
    if st:
        if ids is not None:
            left[st] = metamod.fetch_structure(dbs[left_db], model, ids)
            right[st] = metamod.fetch_structure(dbs[right_db], model, ids)
        else:
            left[st] = metamod.fetch_rows(dbs[left_db], m, {**model, "tables": {st: model["tables"][st]}}, log=lambda _m: None).get(st, [])
            right[st] = metamod.fetch_rows(dbs[right_db], m, {**model, "tables": {st: model["tables"][st]}}, log=lambda _m: None).get(st, [])
    changes = metamod.diff_rows(model, left, right)
    if ids is not None:
        wanted = {str(i) for i in ids}
        changes = [c for c in changes if c["link"] in wanted]
    ln, rn = left_name or left_db, right_name or right_db
    lines = [c["change"].replace(" added:", f" only in {rn}:").replace(" removed", f" only in {ln}") for c in changes]
    return [f"differences {ln} → {rn} (rows matched by primary key; secret columns not compared):"] + (lines or ["none"])


def environment(cfg, name):
    envs = cfg.get("environments") or {}
    if name not in envs:
        raise ValueError(f"no [environments.{name}] in nifikb.toml (known: {', '.join(envs) or 'none'})")
    return envs[name]
