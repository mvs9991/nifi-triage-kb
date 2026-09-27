"""Target-side check: did the load write anything to the definition's HDFS / S3 location, and does the Parquet it wrote
match the structure rows?

Read-only everywhere: directory listings and the last bytes of one Parquet file (its footer holds the schema) - no data
rows are read. Backends, chosen by the location's scheme:
  s3://bucket/prefix        boto3 when installed, otherwise the `aws` CLI (its own credentials / profile / SSO)
  hdfs://…/path or /path    WebHDFS ([targets] hdfs_url; `kerberos = true` uses `curl --negotiate`) or the `hdfs` CLI
  a local / mounted folder  read directly
The Parquet schema is decoded here (Thrift compact protocol, stdlib only), so nothing needs to be installed."""
import datetime as dt
import json
import os
import re
import shutil
import ssl
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import metadata as metamod

PLACEHOLDER = re.compile(r"\$\{|#\{|\{[a-z_]+\}|(?<![A-Za-z])(?:YYYY|yyyy|MM|DD|dd|HH)(?![A-Za-z])")
FOOTER_READ = 64 * 1024


class TargetError(Exception):
    pass


def settings(cfg):
    t = dict(cfg.get("targets") or {})
    t.setdefault("max_entries", 2000)
    t.setdefault("max_depth", 4)
    t.setdefault("timeout", 30)
    t.setdefault("max_download_mb", 200)
    return t


# ------------------------------------------------------------------------------------------------ Parquet footer
class _Compact:
    """Minimal Thrift compact-protocol reader: structs become {field id: value}."""

    def __init__(self, data):
        self.b, self.i = data, 0

    def byte(self):
        v = self.b[self.i]
        self.i += 1
        return v

    def varint(self):
        shift = out = 0
        while True:
            b = self.byte()
            out |= (b & 0x7F) << shift
            if not b & 0x80:
                return out
            shift += 7

    def zigzag(self):
        n = self.varint()
        return (n >> 1) ^ -(n & 1)

    def value(self, t):
        if t in (1, 2):
            return t == 1
        if t == 3:
            return self.byte()
        if t in (4, 5, 6):
            return self.zigzag()
        if t == 7:
            v = struct.unpack("<d", self.b[self.i:self.i + 8])[0]
            self.i += 8
            return v
        if t == 8:
            n = self.varint()
            v = self.b[self.i:self.i + n]
            self.i += n
            return v
        if t in (9, 10):
            h = self.byte()
            n, et = h >> 4, h & 0x0F
            if n == 15:
                n = self.varint()
            return [self.byte() == 1 if et in (1, 2) else self.value(et) for _ in range(n)]
        if t == 11:
            n = self.varint()
            if not n:
                return {}
            h = self.byte()
            return dict((self.value(h >> 4), self.value(h & 0x0F)) for _ in range(n))
        if t == 12:
            return self.struct()
        raise TargetError(f"unsupported Thrift type {t} in the Parquet footer")

    def struct(self):
        out, last = {}, 0
        while True:
            h = self.byte()
            if h == 0:
                return out
            delta, t = h >> 4, h & 0x0F
            fid = last + delta if delta else self.zigzag()
            out[fid] = self.value(t)
            last = fid


PHYSICAL = {0: "BOOLEAN", 1: "INT", 2: "BIGINT", 3: "TIMESTAMP", 4: "FLOAT", 5: "DOUBLE", 6: "BINARY", 7: "FIXED_BINARY"}
CONVERTED = {0: "STRING", 4: "STRING", 6: "DATE", 7: "TIME", 8: "TIME", 9: "TIMESTAMP", 10: "TIMESTAMP", 15: "TINYINT", 16: "SMALLINT",
             17: "TINYINT", 18: "SMALLINT", 19: "INT", 20: "BIGINT", 21: "JSON", 22: "BINARY"}
LOGICAL = {1: "STRING", 4: "STRING", 6: "DATE", 7: "TIME", 8: "TIMESTAMP", 12: "JSON", 14: "UUID"}


def parquet_schema(footer_bytes):
    """[{name, type, nullable}] of the leaf columns (nested ones as a.b.c) + {rows, created_by}, from the file tail."""
    if len(footer_bytes) < 12 or footer_bytes[-4:] != b"PAR1":
        raise TargetError("not a Parquet file (no PAR1 magic at the end)")
    n = struct.unpack("<i", footer_bytes[-8:-4])[0]
    if n + 8 > len(footer_bytes):
        raise TargetError(f"footer needs {n + 8} bytes")
    meta = _Compact(footer_bytes[-8 - n:-8]).struct()
    elems = meta.get(2) or []
    cols, pos = [], 1

    def walk(prefix, count):
        nonlocal pos
        for _ in range(count):
            e = elems[pos]
            pos += 1
            name = e.get(4, b"").decode("utf-8", "replace")
            full = f"{prefix}.{name}" if prefix else name
            if e.get(5):
                walk(full, e[5])
                continue
            typ = PHYSICAL.get(e.get(1), "?")
            logical = e.get(10) or {}
            if 5 in logical or e.get(6) == 5:
                typ = f"DECIMAL({e.get(8, '?')},{e.get(7, 0)})"
            elif 10 in logical:
                info = logical[10]
                bits, signed = info.get(1, 32), info.get(2, True)
                typ = {8: "TINYINT", 16: "SMALLINT", 32: "INT", 64: "BIGINT"}.get(bits, "INT") + ("" if signed else " UNSIGNED")
            elif logical:
                typ = next((LOGICAL[k] for k in logical if k in LOGICAL), typ)
            elif e.get(6) in CONVERTED:
                typ = CONVERTED[e[6]]
            cols.append({"name": full, "type": typ, "nullable": e.get(3, 1) != 0})

    if elems:
        walk("", elems[0].get(5, 0))
    created = meta.get(6)
    return cols, {"rows": meta.get(3), "created_by": created.decode("utf-8", "replace") if isinstance(created, bytes) else None}


# ------------------------------------------------------------------------------------------------ backends
def _run(argv, timeout):
    try:
        p = subprocess.run(argv, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise TargetError(f"'{argv[0]}' not found - install it or set its path in [targets]")
    except subprocess.TimeoutExpired:
        raise TargetError(f"{' '.join(argv[:3])} … timed out after {timeout}s")
    if p.returncode:
        raise TargetError(f"{' '.join(argv[:3])} … failed: {p.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return p.stdout


class Local:
    name = "local"

    def __init__(self, t):
        self.t = t

    def list(self, path):
        root, out = Path(path), []
        if not root.exists():
            raise TargetError(f"{path} does not exist")
        base_depth = len(root.parts)
        for dirpath, dirs, files in os.walk(root):
            if len(Path(dirpath).parts) - base_depth >= self.t["max_depth"]:
                dirs[:] = []
            for f in files:
                p = Path(dirpath) / f
                st = p.stat()
                out.append({"path": p.as_posix(), "size": st.st_size, "mtime": st.st_mtime})
                if len(out) >= self.t["max_entries"]:
                    return out
        return out

    def tail(self, path, size, n):
        with open(path, "rb") as f:
            f.seek(max(0, size - n))
            return f.read()


class WebHdfs:
    name = "webhdfs"

    def __init__(self, t):
        self.t = t
        self.url = t["hdfs_url"].rstrip("/")
        self.ctx = ssl.create_default_context(cafile=t.get("ca_cert") or None) if self.url.startswith("https") else None

    def _get(self, path, **params):
        if self.t.get("hdfs_user") and not self.t.get("kerberos"):
            params["user.name"] = self.t["hdfs_user"]
        url = f"{self.url}{urllib.parse.quote(path)}?{urllib.parse.urlencode(params)}"
        if self.t.get("kerberos"):  # SPNEGO: curl does the Kerberos handshake with the ticket from kinit
            return _run([self.t.get("curl", "curl"), "-sfL", "--negotiate", "-u", ":", *(["--cacert", self.t["ca_cert"]] if self.t.get("ca_cert") else []),
                         url], self.t["timeout"])
        try:
            with urllib.request.urlopen(url, timeout=self.t["timeout"], context=self.ctx) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise TargetError(f"WebHDFS {params.get('op')} {path}: HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}")
        except (urllib.error.URLError, OSError) as e:
            raise TargetError(f"WebHDFS not reachable at {self.url}: {e}")

    def list(self, path):
        out, todo = [], [(path.rstrip("/") or "/", 0)]
        while todo and len(out) < self.t["max_entries"]:
            p, depth = todo.pop(0)
            try:
                data = json.loads(self._get(p, op="LISTSTATUS"))
            except TargetError as e:
                if "404" in str(e) or "FileNotFound" in str(e):
                    raise TargetError(f"{p} does not exist in HDFS")
                raise
            for s in data["FileStatuses"]["FileStatus"]:
                full = f"{p.rstrip('/')}/{s['pathSuffix']}" if s["pathSuffix"] else p
                if s["type"] == "DIRECTORY":
                    if depth + 1 < self.t["max_depth"]:
                        todo.append((full, depth + 1))
                else:
                    out.append({"path": full, "size": s["length"], "mtime": s["modificationTime"] / 1000})
        return out[:self.t["max_entries"]]

    def tail(self, path, size, n):
        off = max(0, size - n)
        return self._get(path, op="OPEN", offset=off, length=size - off)


class HdfsCli:
    name = "hdfs cli"
    LINE = re.compile(r"^([-d])\S*\s+\S+\s+\S+\s+\S+\s+(\d+)\s+(\d{4}-\d\d-\d\d \d\d:\d\d)\s+(.+)$")

    def __init__(self, t):
        self.t = t
        self.cmd = t.get("hdfs_cli") if isinstance(t.get("hdfs_cli"), list) else [t.get("hdfs_cli") or "hdfs"]

    def list(self, path):
        out = []
        text = _run([*self.cmd, "dfs", "-ls", "-R", path], self.t["timeout"] * 4).decode("utf-8", "replace")
        for line in text.splitlines():
            m = self.LINE.match(line.strip())
            if m and m.group(1) == "-":
                out.append({"path": m.group(4), "size": int(m.group(2)),
                            "mtime": time.mktime(time.strptime(m.group(3), "%Y-%m-%d %H:%M"))})
                if len(out) >= self.t["max_entries"]:
                    break
        return out

    def tail(self, path, size, n):
        if size > self.t["max_download_mb"] * 1024 * 1024:
            raise TargetError(f"{path} is {size // 1048576} MB - the hdfs CLI cannot read only the footer; use WebHDFS "
                              "([targets] hdfs_url) or raise max_download_mb")
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "f.parquet"
            _run([*self.cmd, "dfs", "-get", path, str(local)], self.t["timeout"] * 4)
            return Local(self.t).tail(local, local.stat().st_size, n)


class S3:
    name = "s3"

    def __init__(self, t):
        self.t = t
        self.client = None
        try:
            if t.get("s3_cli"):
                raise ImportError  # an explicitly configured CLI wins over boto3
            import boto3  # optional
            session = boto3.session.Session(profile_name=t.get("s3_profile")) if t.get("s3_profile") else boto3.session.Session()
            self.client = session.client("s3", endpoint_url=t.get("s3_endpoint") or None, region_name=t.get("s3_region") or None)
        except ImportError:
            self.client = None
        self.cli = t.get("s3_cli") if isinstance(t.get("s3_cli"), list) else [t.get("s3_cli") or "aws"]

    def _opts(self):
        return [*(["--profile", self.t["s3_profile"]] if self.t.get("s3_profile") else []),
                *(["--endpoint-url", self.t["s3_endpoint"]] if self.t.get("s3_endpoint") else []),
                *(["--region", self.t["s3_region"]] if self.t.get("s3_region") else [])]

    @staticmethod
    def split(path):
        u = urllib.parse.urlparse(path)
        return u.netloc, u.path.lstrip("/")

    def list(self, path):
        bucket, prefix = self.split(path)
        out = []
        if self.client:
            pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix,
                                                                         PaginationConfig={"MaxItems": self.t["max_entries"]})
            for page in pages:
                for o in page.get("Contents") or []:
                    out.append({"path": f"s3://{bucket}/{o['Key']}", "size": o["Size"], "mtime": o["LastModified"].timestamp()})
            return out
        data = _run([*self.cli, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix, "--max-items",
                     str(self.t["max_entries"]), "--output", "json", *self._opts()], self.t["timeout"] * 4)
        for o in (json.loads(data or b"{}") or {}).get("Contents") or []:
            when = dt.datetime.fromisoformat(str(o["LastModified"]).replace("Z", "+00:00")).timestamp()
            out.append({"path": f"s3://{bucket}/{o['Key']}", "size": o["Size"], "mtime": when})
        return out

    def tail(self, path, size, n):
        bucket, key = self.split(path)
        rng = f"bytes={max(0, size - n)}-{size - 1}"
        if self.client:
            return self.client.get_object(Bucket=bucket, Key=key, Range=rng)["Body"].read()
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "tail.bin"
            _run([*self.cli, "s3api", "get-object", "--bucket", bucket, "--key", key, "--range", rng, str(local), *self._opts()],
                 self.t["timeout"] * 4)
            return local.read_bytes()


def backend(t, location):
    loc = str(location)
    if re.match(r"(?i)s3a?://", loc):
        return S3(t), re.sub(r"(?i)^s3a://", "s3://", loc)
    if re.match(r"(?i)hdfs://", loc) or (loc.startswith("/") and (t.get("hdfs_url") or t.get("hdfs_cli")) and not Path(loc).exists()):
        path = urllib.parse.urlparse(loc).path if loc.lower().startswith("hdfs://") else loc
        if t.get("hdfs_url"):
            return WebHdfs(t), path
        if t.get("hdfs_cli") or shutil.which("hdfs"):
            return HdfsCli(t), path
        raise TargetError("HDFS location, but neither [targets] hdfs_url (WebHDFS) nor an hdfs CLI is available")
    if re.match(r"(?i)file://", loc):
        return Local(t), urllib.parse.urlparse(loc).path
    if re.match(r"(?i)[a-z][a-z0-9+.-]+://", loc):
        raise TargetError(f"unsupported location scheme in {loc}")
    return Local(t), loc


# ------------------------------------------------------------------------------------------------ check
def listable_root(location):
    """The fixed part of a location with placeholders (…/dt=${now()…}/ → …/): list from there."""
    loc = str(location).strip()
    m = PLACEHOLDER.search(loc)
    if not m:
        return loc, False
    return loc[:loc.rfind("/", 0, m.start()) + 1] or loc[:m.start()], True


def _stem(name):
    s = Path(str(name).replace("\\", "/")).name
    return re.sub(r"(\.(csv|txt|dat|json|xml|gz|zip|parquet|psv|tsv))+$", "", s, flags=re.I).lower()


def check(cfg, location, fields=(), file=None, since=None):
    """{location, root, backend, files (newest first), matches, schema, issues: [(severity, kind, message)]}."""
    t = settings(cfg)
    root, templated = listable_root(location)
    res = {"location": location, "root": root, "files": [], "matches": [], "schema": None, "issues": []}
    be, path = backend(t, root)
    res["backend"] = be.name
    try:
        files = be.list(path)
    except TargetError as e:
        res["issues"].append(("error", "target-location", f"cannot list {root}: {e}"))
        return res
    files.sort(key=lambda f: -f["mtime"])
    data = [f for f in files if not re.search(r"(^|/)(_SUCCESS|_committed_|_started_|\.crc$|\._)", f["path"]) and not Path(f["path"]).name.startswith(".")]
    res["files"] = data
    if not data:
        res["issues"].append(("error", "target-empty", f"no data files under {root}" + (" (location has placeholders; listed its fixed part)" if templated else "")))
        return res
    empty = [f for f in data[:50] if f["size"] == 0]
    if empty:
        res["issues"].append(("warn", "target-zero-byte", f"{len(empty)} zero-byte file(s) among the newest, e.g. {empty[0]['path']}"))
    if file:
        stem = _stem(file)
        res["matches"] = [f for f in data if stem and stem in Path(f["path"]).name.lower()] + \
                         [f for f in data if stem and stem in f["path"].lower() and stem not in Path(f["path"]).name.lower()]
        if not res["matches"]:
            newest = time.strftime("%Y-%m-%d %H:%M", time.localtime(data[0]["mtime"]))
            res["issues"].append(("warn", "target-no-file-output", f"no output named like '{stem}' under {root} (outputs are often "
                                                                   f"named by the flow, not the input file; newest output {newest})"))
    if since:
        recent = [f for f in data if f["mtime"] >= since]
        if not recent:
            res["issues"].append(("warn", "target-stale", f"nothing written under {root} since {time.strftime('%Y-%m-%d %H:%M', time.localtime(since))}"))
    pq = next((f for f in (res["matches"] or data) if f["path"].lower().endswith(".parquet") or ".parquet" in f["path"].lower()), None)
    if pq is None:
        pq = next((f for f in (res["matches"] or data) if f["size"] > 12 and not re.search(r"\.(csv|json|txt|avro|orc|gz)$", f["path"], re.I)), None)
    if pq and fields:
        try:
            tail = be.tail(pq["path"], pq["size"], FOOTER_READ)
            if len(tail) >= 8 and tail[-4:] == b"PAR1":
                n = struct.unpack("<i", tail[-8:-4])[0]
                if n + 8 > len(tail):
                    tail = be.tail(pq["path"], pq["size"], n + 8)
                cols, info = parquet_schema(tail)
                res["schema"] = {"file": pq["path"], "columns": cols, **info}
                res["issues"] += compare_schema(fields, cols, pq["path"])
        except (TargetError, OSError, IndexError, struct.error) as e:
            res["issues"].append(("info", "target-schema", f"could not read the Parquet schema of {pq['path']}: {e}"))
    return res


def compare_schema(fields, cols, where):
    """Structure rows vs the columns of a written Parquet file."""
    issues = []
    have = {c["name"].lower(): c for c in cols}
    leaf = {c["name"].lower().split(".")[-1]: c for c in cols}
    names = {f["name"].lower() for f in fields}
    missing = [f["name"] for f in fields if f["name"].lower() not in have and f["name"].lower().split(".")[-1] not in leaf]
    if missing:
        issues.append(("error", "parquet-missing-column", f"structure field(s) not in the written Parquet ({Path(where).name}): "
                                                          + ", ".join(missing[:15]) + (f", … +{len(missing) - 15}" if len(missing) > 15 else "")))
    extra = [c["name"] for c in cols if c["name"].lower() not in names and c["name"].lower().split(".")[-1] not in names]
    if extra:
        issues.append(("info", "parquet-extra-column", f"Parquet has column(s) not in the structure (often load metadata): {', '.join(extra[:15])}"))
    diffs = []
    for f in fields:
        c = have.get(f["name"].lower()) or leaf.get(f["name"].lower().split(".")[-1])
        if not c or not f.get("type"):
            continue
        a, b = metamod.type_family(f["type"]), metamod.type_family(c["type"])
        if a and b and a != b:
            diffs.append(f"'{f['name']}' is {f['type']} in the structure but {c['type']} in the Parquet")
    if diffs:
        issues.append(("warn", "parquet-type", "; ".join(diffs[:8]) + (f"; … +{len(diffs) - 8} more" if len(diffs) > 8 else "")))
    return issues


def format_check(res, limit=10):
    L = [f"location: {res['location']}" + (f" (listed {res['root']})" if res["root"] != res["location"] else "")
         + (f" via {res.get('backend')}" if res.get("backend") else "")]
    for sev, kind, msg in res["issues"]:
        L.append(f"  [{sev}] {kind}: {msg}")
    files = res["matches"] or res["files"]
    if files:
        L.append(f"  {'outputs for this file' if res['matches'] else 'newest outputs'} ({len(res['matches'] or res['files'])} found):")
        for f in files[:limit]:
            L.append(f"    {time.strftime('%Y-%m-%d %H:%M', time.localtime(f['mtime']))}  {f['size']:>12,}  {f['path']}")
    if res.get("schema"):
        s = res["schema"]
        L.append(f"  Parquet schema of {Path(s['file']).name}: {s.get('rows')} rows, "
                 + ", ".join(f"{c['name']} {c['type']}" for c in s["columns"][:30]) + (" …" if len(s["columns"]) > 30 else ""))
    return "\n".join(L)


# ------------------------------------------------------------------------------------------------ per definition
def enabled(cfg):
    return "targets" in cfg  # an empty [targets] section enables local / mounted locations


def location_of(cfg, model, entry):
    """Where a definition's data lands: its location column, a file-location target, or [targets] location_template."""
    if entry.get("location"):
        return str(entry["location"])
    tmpl = settings(cfg).get("location_template")
    table = entry.get("target")
    if tmpl and table:
        return tmpl.format(table=str(table), table_lower=str(table).lower(), id=entry.get("id"), label=entry.get("label"))
    return None


def check_diagnosis(cfg, model, diag, file=None, since=None):
    """[(definition entry, check result)] for the definitions of a metadata diagnosis that have a location."""
    out = []
    for d in (diag or {}).get("definitions") or []:
        loc = location_of(cfg, model, d)
        if not loc:
            continue
        try:
            out.append((d, check(cfg, loc, d.get("fields") or [], file=file, since=since)))
        except TargetError as e:
            out.append((d, {"location": loc, "root": loc, "files": [], "matches": [], "schema": None,
                            "issues": [("error", "target-location", str(e))]}))
    return out
