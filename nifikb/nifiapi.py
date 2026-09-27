"""Read-only NiFi REST API client: provenance (where did a FlowFile go / get dropped), bulletins, about.

Provenance answers the question the logs often cannot: a FlowFile routed to an auto-terminated relationship, expired in a
queue, or emptied by a user leaves no log line, but it does leave a DROP event naming the processor and the reason
("Auto-Terminated by failure Relationship", "FlowFile Expired", ...). The API is the only practical way to query it
(the provenance repository files are a Lucene index that must not be read while NiFi runs).

Calls made: POST /access/token (login), POST + GET + DELETE /provenance (a temporary query, deleted after reading),
GET /provenance-events/{id}, GET /flow/bulletin-board, GET /flow/about. Nothing in the flow is changed.
The NiFi user needs the "query provenance" and "view provenance" policies (read-only otherwise).
"""
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .db import mask_value

INTERESTING_ATTR = ("error", "reason", "fail", "exception", "status", "code", "message", "retry", "table", "schema", "path",
                    "filename", "directory", "bucket", "key", "fragment")


class NiFiApiError(Exception):
    pass


def settings(cfg):
    a = cfg.get("nifi_api") or {}
    if not a.get("url"):
        return None
    return a


def _secret(a, key):
    if a.get(f"{key}_env") and os.environ.get(a[f"{key}_env"]):
        return os.environ[a[f"{key}_env"]]
    if a.get(f"{key}_file"):
        return Path(a[f"{key}_file"]).read_text(encoding="utf-8").strip()
    return a.get(key)


class Client:
    def __init__(self, a):
        self.base = a["url"].rstrip("/")
        if not self.base.endswith("/nifi-api"):
            self.base += "/nifi-api"
        self.a = a
        self.timeout = float(a.get("timeout", 30))
        self.token = _secret(a, "token")
        self.ctx = None
        if self.base.startswith("https"):
            if a.get("verify_ssl", True) is False:
                self.ctx = ssl._create_unverified_context()  # explicit opt-in in nifikb.toml
            else:
                self.ctx = ssl.create_default_context(cafile=a.get("ca_cert") or None)
            if a.get("client_cert"):
                self.ctx.load_cert_chain(a["client_cert"], a.get("client_key"), _secret(a, "client_key_password"))

    # ------------------------------------------------------------------------------------------- http
    def _call(self, method, path, body=None, form=None, auth=True):
        headers = {"Accept": "application/json"}
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.token and self.a.get("username"):
                self.login()
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                raw = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            hint = {401: "authentication failed - check [nifi_api] username / password / token",
                    403: "the NiFi user lacks a policy: needs 'query provenance' (global) and 'view provenance' on the process groups",
                    404: "not found - check [nifi_api] url (it should end with /nifi-api)"}.get(e.code, "")
            raise NiFiApiError(f"HTTP {e.code} on {method} {path}: {detail} {hint}".strip()) from e
        except (urllib.error.URLError, OSError) as e:
            raise NiFiApiError(f"cannot reach {self.base}: {e}") from e
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return raw

    def login(self):
        password = _secret(self.a, "password")
        if not password:
            raise NiFiApiError("[nifi_api] username is set but no password (password_env / password_file)")
        tok = self._call("POST", "/access/token", form={"username": self.a["username"], "password": password}, auth=False)
        self.token = tok if isinstance(tok, str) else None
        if not self.token:
            raise NiFiApiError("login returned no token")

    # ------------------------------------------------------------------------------------------- API
    def about(self):
        return (self._call("GET", "/flow/about") or {}).get("about", {})

    def bulletins(self, limit=100, source_id=None):
        q = f"?limit={int(limit)}" + (f"&sourceId={urllib.parse.quote(source_id)}" if source_id else "")
        board = (self._call("GET", "/flow/bulletin-board" + q) or {}).get("bulletinBoard", {})
        return [b.get("bulletin") or {} for b in board.get("bulletins", []) if b.get("bulletin")]

    def search(self, terms, max_results=500, wait=60):
        """Run a provenance query ({'Filename': x} / {'FlowFileUUID': u} / {'ProcessorID': id}) and return its events."""
        body = {"provenance": {"request": {"maxResults": int(max_results), "summarize": True, "incrementalResults": False,
                                           "searchTerms": {k: {"value": v, "inverse": False} for k, v in terms.items()}}}}
        try:
            res = self._call("POST", "/provenance", body=body)
        except NiFiApiError as e:
            if "HTTP 400" not in str(e):
                raise
            body["provenance"]["request"]["searchTerms"] = dict(terms)  # NiFi < 1.13 takes plain strings
            res = self._call("POST", "/provenance", body=body)
        prov = (res or {}).get("provenance", {})
        qid = prov.get("id")
        deadline = time.time() + wait
        try:
            while not prov.get("finished") and time.time() < deadline:
                time.sleep(0.5)
                prov = (self._call("GET", f"/provenance/{qid}") or {}).get("provenance", {})
        finally:
            if qid:
                try:
                    self._call("DELETE", f"/provenance/{qid}")
                except NiFiApiError:
                    pass
        return (prov.get("results") or {}).get("provenanceEvents") or []

    def event(self, event_id):
        return (self._call("GET", f"/provenance-events/{event_id}") or {}).get("provenanceEvent", {})

    def pg_status(self, group="root"):
        return (self._call("GET", f"/flow/process-groups/{group}/status?recursive=true") or {}).get("processGroupStatus", {})

    def controller_status(self):
        return (self._call("GET", "/flow/status") or {}).get("controllerStatus", {})

    def system_diagnostics(self):
        return (self._call("GET", "/system-diagnostics") or {}).get("systemDiagnostics", {}).get("aggregateSnapshot", {})

    def services(self, group="root"):
        res = self._call("GET", f"/flow/process-groups/{group}/controller-services?includeAncestorGroups=false&includeDescendantGroups=true")
        return [s.get("component") or {} for s in (res or {}).get("controllerServices", [])]

    def processor(self, pid):
        return ((self._call("GET", f"/processors/{pid}") or {}).get("component") or {})

    def version_state(self, group_instance_id):
        """VersionControlInformation of one process group: state UP_TO_DATE / LOCALLY_MODIFIED / STALE / ... + version."""
        return (self._call("GET", f"/versions/process-groups/{group_instance_id}") or {}).get("versionControlInformation") or {}

    def cluster(self):
        try:
            return (self._call("GET", "/flow/cluster/summary") or {}).get("clusterSummary", {})
        except NiFiApiError:
            return {}


# ------------------------------------------------------------------------------------------- health
def _num(v):
    try:
        return int(str(v).split()[0].replace(",", "")) if v not in (None, "") else 0
    except ValueError:
        return 0


def _pct(v):
    try:
        return float(str(v).rstrip("%")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _walk(snapshot, path=""):
    """Yield (group path, snapshot) for a recursive process-group status snapshot."""
    name = snapshot.get("name") or "root"
    here = f"{path}/{name}" if path else name
    yield here, snapshot
    for child in snapshot.get("processGroupStatusSnapshots") or []:
        yield from _walk(child.get("processGroupStatusSnapshot") or {}, here)


VERSION_PROBLEMS = {"LOCALLY_MODIFIED": ("warn", "changed in NiFi but not committed to the registry"),
                    "STALE": ("warn", "a newer version exists in the registry but is not deployed"),
                    "LOCALLY_MODIFIED_AND_STALE": ("warn", "changed in NiFi AND a newer registry version is not deployed"),
                    "SYNC_FAILURE": ("error", "cannot sync with the registry")}


def version_problems(client, groups):
    """groups: [(instance id, path)] of version-controlled process groups -> problems for the ones not UP_TO_DATE."""
    out = []
    for gid, path in groups:
        try:
            vci = client.version_state(gid)
        except NiFiApiError:
            continue
        state = vci.get("state")
        if state in VERSION_PROBLEMS:
            sev, what = VERSION_PROBLEMS[state]
            out.append({"severity": sev, "kind": "version-state", "component_id": gid,
                        "message": f"process group {path} (registry flow {vci.get('flowName') or vci.get('flowId')}, v{vci.get('version')}): "
                                   f"{what}" + (f" - {vci['stateExplanation']}" if vci.get("stateExplanation") else "")})
    return out


def health(client, bp_threshold=80.0, disk_threshold=85.0, versioned=()):
    """Live problems: back-pressure, queues stuck in front of stopped / invalid / disabled processors, invalid processors
    (with NiFi's validation errors), services not enabled, full repositories, high heap, disconnected nodes."""
    problems, stats = [], {}

    def add(sev, kind, msg, cid=None):
        problems.append({"severity": sev, "kind": kind, "message": msg, "component_id": cid})

    root = (client.pg_status() or {}).get("aggregateSnapshot") or {}
    procs, conns = {}, []
    for gpath, snap in _walk(root):
        for p in snap.get("processorStatusSnapshots") or []:
            ps = p.get("processorStatusSnapshot") or {}
            procs[ps.get("id")] = dict(ps, group=gpath)
        for c in snap.get("connectionStatusSnapshots") or []:
            conns.append(dict(c.get("connectionStatusSnapshot") or {}, group=gpath))
    stats.update(processors=len(procs), connections=len(conns),
                 queued=sum(_num(c.get("queuedCount")) for c in conns))
    for c in conns:
        count, pct_n, pct_b = _num(c.get("queuedCount")), _pct(c.get("percentUseCount")), _pct(c.get("percentUseBytes"))
        where = f"{c.get('sourceName')} → {c.get('destinationName')} in {c.get('group')}"
        dest = procs.get(c.get("destinationId")) or {}
        if max(pct_n, pct_b) >= bp_threshold:
            add("error" if max(pct_n, pct_b) >= 100 else "warn", "back-pressure",
                f"queue {where} is at {max(pct_n, pct_b):.0f}% of its back-pressure threshold ({c.get('queued') or count}) - "
                "upstream processors slow down / stop", c.get("destinationId"))
        if count and dest.get("runStatus") in ("Stopped", "Invalid", "Disabled"):
            add("error", "stuck-queue", f"{count} FlowFile(s) waiting in {where}: the destination processor is {dest['runStatus'].upper()}",
                c.get("destinationId"))
    for pid, p in procs.items():
        if p.get("runStatus") == "Invalid":
            errors = []
            try:
                errors = client.processor(pid).get("validationErrors") or []
            except NiFiApiError:
                pass
            add("error", "invalid-processor", f"{p.get('name')} ({p.get('type')}) in {p.get('group')} is INVALID"
                + (f": {'; '.join(errors)[:400]}" if errors else ""), pid)
    try:
        for s in client.services():
            if s.get("state") not in ("ENABLED", None):
                add("warn" if s.get("state") == "DISABLED" else "error", "service-not-enabled",
                    f"controller service {s.get('name')} is {s.get('state')}"
                    + (f": {'; '.join(s.get('validationErrors') or [])[:300]}" if s.get("validationErrors") else ""), s.get("id"))
    except NiFiApiError:
        pass
    diag = client.system_diagnostics() or {}
    heap = _pct(diag.get("heapUtilization"))
    if heap >= disk_threshold:
        add("warn", "heap", f"JVM heap at {heap:.0f}% - NiFi may pause / slow down (OutOfMemory risk)")
    for label, key in (("content repository", "contentRepositoryStorageUsage"), ("provenance repository", "provenanceRepositoryStorageUsage"),
                       ("FlowFile repository", "flowFileRepositoryStorageUsage")):
        usage = diag.get(key)
        for u in (usage if isinstance(usage, list) else [usage] if usage else []):
            pct = _pct(u.get("utilization"))
            if pct >= disk_threshold:
                add("error" if pct >= 95 else "warn", "disk", f"{label} {u.get('identifier') or ''} at {pct:.0f}% "
                    f"({u.get('usedSpace', '?')} of {u.get('totalSpace', '?')}) - NiFi stops accepting data when full".replace("  ", " "))
    stats.update(heap=diag.get("heapUtilization"))
    problems += version_problems(client, versioned)
    cluster = client.cluster()
    if cluster.get("clustered") and cluster.get("connectedNodeCount", 0) < cluster.get("totalNodeCount", 0):
        add("error", "cluster", f"only {cluster['connectedNodeCount']} of {cluster['totalNodeCount']} cluster nodes connected")
    sev_rank = {"error": 0, "warn": 1}
    problems.sort(key=lambda p: sev_rank.get(p["severity"], 2))
    return {"problems": problems, "stats": stats}


def format_health(h, names=None):
    names = names or {}
    s = h["stats"]
    L = [f"Live NiFi health: {s.get('processors', 0)} processors, {s.get('connections', 0)} connections, "
         f"{s.get('queued', 0)} FlowFiles queued, heap {s.get('heap') or '?'}"]
    if not h["problems"]:
        L.append("no problems: no back-pressure, no stuck queues, no invalid processors, services enabled, repositories below threshold")
    for p in h["problems"]:
        cid = p.get("component_id") or ""
        L.append(f"[{p['severity']}] {p['kind']}: {p['message']}" + (f"  ({names[cid]})" if cid in names else ""))
    return "\n".join(L)


class RegistryClient(Client):
    """Read-only NiFi Registry client: version history (who changed a versioned flow when, with the commit comment)."""

    def __init__(self, r):
        r = dict(r)
        url = r["url"].rstrip("/")
        r["url"] = url if url.endswith("/nifi-registry-api") else url + "/nifi-registry-api"
        super().__init__(r)
        self.base = r["url"]

    def login(self):
        password = _secret(self.a, "password")
        if not password:
            raise NiFiApiError("[registry] username is set but no password (password_env / password_file)")
        basic = __import__("base64").b64encode(f"{self.a['username']}:{password}".encode()).decode()
        req = urllib.request.Request(self.base + "/access/token/login", data=b"", method="POST", headers={"Authorization": f"Basic {basic}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                self.token = r.read().decode().strip()
        except urllib.error.HTTPError as e:
            raise NiFiApiError(f"registry login failed: HTTP {e.code}") from e
        except (urllib.error.URLError, OSError) as e:
            raise NiFiApiError(f"cannot reach {self.base}: {e}") from e

    def versions(self, bucket, flow):
        res = self._call("GET", f"/buckets/{bucket}/flows/{flow}/versions") or []
        return sorted(res, key=lambda v: v.get("version") or 0, reverse=True)


def registry_settings(cfg):
    r = cfg.get("registry") or {}
    return r if r.get("url") else None


# ------------------------------------------------------------------------------------------- journey
def journey(client, filename=None, uuid=None, component_id=None, max_results=500, follow=20):
    """Every provenance event of the FlowFiles with this file name / uuid (and their children), grouped per FlowFile,
    with a verdict: where each one ended (dropped where and why, sent where, or still in flight)."""
    if filename:
        terms = {"Filename": filename}
    elif uuid:
        terms = {"FlowFileUUID": uuid}
    elif component_id:
        terms = {"ProcessorID": component_id}
    else:
        raise ValueError("give a file name, FlowFile uuid or processor id")
    events = client.search(terms, max_results)
    seen = {e.get("eventId") for e in events}
    uuids = {e.get("flowFileUuid") for e in events}
    for _ in range(2):  # follow FORK / CLONE / split children a little way
        children = [c for e in events for c in (e.get("childUuids") or []) if c not in uuids][:follow]
        for c in children:
            uuids.add(c)
            for e in client.search({"FlowFileUUID": c}, max_results):
                if e.get("eventId") not in seen:
                    seen.add(e.get("eventId"))
                    events.append(e)
    events.sort(key=lambda e: (int(e.get("eventId") or 0)))
    flows = {}
    for e in events:
        flows.setdefault(e.get("flowFileUuid"), []).append(e)
    out = []
    for ff, evs in flows.items():
        last = evs[-1]
        kind = last.get("eventType")
        if kind == "DROP":
            verdict = f"DROPPED at {last.get('componentName')} ({last.get('componentType')}): {last.get('details') or 'no reason given'}"
        elif kind in ("SEND", "REMOTE_INVOCATION", "UPLOAD"):
            verdict = f"sent by {last.get('componentName')} to {last.get('transitUri') or '?'}"
        elif any(c for c in (last.get("childUuids") or [])) and kind in ("FORK", "CLONE", "JOIN"):
            verdict = f"split / cloned by {last.get('componentName')} into {len(last['childUuids'])} FlowFile(s)"
        else:
            verdict = (f"last seen at {last.get('componentName')} ({kind}) - still queued / in flight, or older events were "
                       "aged out of provenance")
        attrs = {}
        if kind == "DROP" and last.get("id"):
            try:
                detail = client.event(last["id"])
                for a in detail.get("attributes") or []:
                    name = a.get("name", "")
                    if any(w in name.lower() for w in INTERESTING_ATTR) or a.get("value") != a.get("previousValue"):
                        attrs[name] = mask_value(name, a.get("value"))
            except NiFiApiError:
                pass
        out.append({"uuid": ff, "events": evs, "verdict": verdict, "attributes": dict(list(attrs.items())[:25])})
    return out


def format_journey(flows, names=None, key=""):
    names = names or {}
    if not flows:
        return (f"no provenance events for {key} - the file never entered NiFi under this name, or its events were aged out of "
                "provenance (check nifi.provenance.repository.max.storage.time)")
    L = []
    for f in flows:
        L.append(f"FlowFile {str(f['uuid'])[:8]}: {f['verdict']}")
        for e in f["events"][-40:]:
            cid = e.get("componentId") or ""
            flow = names.get(cid)
            extra = " ".join(x for x in [f"-> {e['relationship']}" if e.get("relationship") else "",
                                         e.get("details") or "", e.get("transitUri") or ""] if x)
            L.append(f"  {e.get('eventTime', '')[:23]}  {e.get('eventType', ''):<18} {e.get('componentName', '')} `{cid[:8]}`"
                     + (f" ({flow})" if flow else "") + (f"  {extra}" if extra else ""))
        if f["attributes"]:
            L.append("  attributes at the drop: " + ", ".join(f"{k}={str(v)[:80]}" for k, v in f["attributes"].items()))
    return "\n".join(L)


def format_bulletins(bulletins, names=None):
    names = names or {}
    if not bulletins:
        return "no bulletins (NiFi keeps them for 5 minutes)"
    L = []
    for b in bulletins:
        sid = b.get("sourceId") or ""
        L.append(f"[{b.get('level')}] {b.get('timestamp', '')} {b.get('sourceName', '')} `{sid[:8]}`"
                 + (f" ({names[sid]})" if sid in names else "") + f": {str(b.get('message', ''))[:400]}")
    return "\n".join(L)
