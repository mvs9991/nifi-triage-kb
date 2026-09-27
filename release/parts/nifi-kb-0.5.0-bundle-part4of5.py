# nifi-kb 0.5.0 - paste bundle, part 4 of 5 - 14 files. Save as nifi-kb-0.5.0-bundle-part4of5.py, then run:  python nifi-kb-0.5.0-bundle-part4of5.py
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
#@@ FILE nifikb/target.py t ccbca36fdb64cc20
#|"""Target-side check: did the load write anything to the definition's HDFS / S3 location, and does the Parquet it wrote
#|match the structure rows?
#|
#|Read-only everywhere: directory listings and the last bytes of one Parquet file (its footer holds the schema) - no data
#|rows are read. Backends, chosen by the location's scheme:
#|  s3://bucket/prefix        boto3 when installed, otherwise the `aws` CLI (its own credentials / profile / SSO)
#|  hdfs://…/path or /path    WebHDFS ([targets] hdfs_url; `kerberos = true` uses `curl --negotiate`) or the `hdfs` CLI
#|  a local / mounted folder  read directly
#|The Parquet schema is decoded here (Thrift compact protocol, stdlib only), so nothing needs to be installed."""
#|import datetime as dt
#|import json
#|import os
#|import re
#|import shutil
#|import ssl
#|import struct
#|import subprocess
#|import tempfile
#|import time
#|import urllib.error
#|import urllib.parse
#|import urllib.request
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|
#|PLACEHOLDER = re.compile(r"\$\{|#\{|\{[a-z_]+\}|(?<![A-Za-z])(?:YYYY|yyyy|MM|DD|dd|HH)(?![A-Za-z])")
#|FOOTER_READ = 64 * 1024
#|
#|
#|class TargetError(Exception):
#|    pass
#|
#|
#|def settings(cfg):
#|    t = dict(cfg.get("targets") or {})
#|    t.setdefault("max_entries", 2000)
#|    t.setdefault("max_depth", 4)
#|    t.setdefault("timeout", 30)
#|    t.setdefault("max_download_mb", 200)
#|    return t
#|
#|
#|# ------------------------------------------------------------------------------------------------ Parquet footer
#|class _Compact:
#|    """Minimal Thrift compact-protocol reader: structs become {field id: value}."""
#|
#|    def __init__(self, data):
#|        self.b, self.i = data, 0
#|
#|    def byte(self):
#|        v = self.b[self.i]
#|        self.i += 1
#|        return v
#|
#|    def varint(self):
#|        shift = out = 0
#|        while True:
#|            b = self.byte()
#|            out |= (b & 0x7F) << shift
#|            if not b & 0x80:
#|                return out
#|            shift += 7
#|
#|    def zigzag(self):
#|        n = self.varint()
#|        return (n >> 1) ^ -(n & 1)
#|
#|    def value(self, t):
#|        if t in (1, 2):
#|            return t == 1
#|        if t == 3:
#|            return self.byte()
#|        if t in (4, 5, 6):
#|            return self.zigzag()
#|        if t == 7:
#|            v = struct.unpack("<d", self.b[self.i:self.i + 8])[0]
#|            self.i += 8
#|            return v
#|        if t == 8:
#|            n = self.varint()
#|            v = self.b[self.i:self.i + n]
#|            self.i += n
#|            return v
#|        if t in (9, 10):
#|            h = self.byte()
#|            n, et = h >> 4, h & 0x0F
#|            if n == 15:
#|                n = self.varint()
#|            return [self.byte() == 1 if et in (1, 2) else self.value(et) for _ in range(n)]
#|        if t == 11:
#|            n = self.varint()
#|            if not n:
#|                return {}
#|            h = self.byte()
#|            return dict((self.value(h >> 4), self.value(h & 0x0F)) for _ in range(n))
#|        if t == 12:
#|            return self.struct()
#|        raise TargetError(f"unsupported Thrift type {t} in the Parquet footer")
#|
#|    def struct(self):
#|        out, last = {}, 0
#|        while True:
#|            h = self.byte()
#|            if h == 0:
#|                return out
#|            delta, t = h >> 4, h & 0x0F
#|            fid = last + delta if delta else self.zigzag()
#|            out[fid] = self.value(t)
#|            last = fid
#|
#|
#|PHYSICAL = {0: "BOOLEAN", 1: "INT", 2: "BIGINT", 3: "TIMESTAMP", 4: "FLOAT", 5: "DOUBLE", 6: "BINARY", 7: "FIXED_BINARY"}
#|CONVERTED = {0: "STRING", 4: "STRING", 6: "DATE", 7: "TIME", 8: "TIME", 9: "TIMESTAMP", 10: "TIMESTAMP", 15: "TINYINT", 16: "SMALLINT",
#|             17: "TINYINT", 18: "SMALLINT", 19: "INT", 20: "BIGINT", 21: "JSON", 22: "BINARY"}
#|LOGICAL = {1: "STRING", 4: "STRING", 6: "DATE", 7: "TIME", 8: "TIMESTAMP", 12: "JSON", 14: "UUID"}
#|
#|
#|def parquet_schema(footer_bytes):
#|    """[{name, type, nullable}] of the leaf columns (nested ones as a.b.c) + {rows, created_by}, from the file tail."""
#|    if len(footer_bytes) < 12 or footer_bytes[-4:] != b"PAR1":
#|        raise TargetError("not a Parquet file (no PAR1 magic at the end)")
#|    n = struct.unpack("<i", footer_bytes[-8:-4])[0]
#|    if n + 8 > len(footer_bytes):
#|        raise TargetError(f"footer needs {n + 8} bytes")
#|    meta = _Compact(footer_bytes[-8 - n:-8]).struct()
#|    elems = meta.get(2) or []
#|    cols, pos = [], 1
#|
#|    def walk(prefix, count):
#|        nonlocal pos
#|        for _ in range(count):
#|            e = elems[pos]
#|            pos += 1
#|            name = e.get(4, b"").decode("utf-8", "replace")
#|            full = f"{prefix}.{name}" if prefix else name
#|            if e.get(5):
#|                walk(full, e[5])
#|                continue
#|            typ = PHYSICAL.get(e.get(1), "?")
#|            logical = e.get(10) or {}
#|            if 5 in logical or e.get(6) == 5:
#|                typ = f"DECIMAL({e.get(8, '?')},{e.get(7, 0)})"
#|            elif 10 in logical:
#|                info = logical[10]
#|                bits, signed = info.get(1, 32), info.get(2, True)
#|                typ = {8: "TINYINT", 16: "SMALLINT", 32: "INT", 64: "BIGINT"}.get(bits, "INT") + ("" if signed else " UNSIGNED")
#|            elif logical:
#|                typ = next((LOGICAL[k] for k in logical if k in LOGICAL), typ)
#|            elif e.get(6) in CONVERTED:
#|                typ = CONVERTED[e[6]]
#|            cols.append({"name": full, "type": typ, "nullable": e.get(3, 1) != 0})
#|
#|    if elems:
#|        walk("", elems[0].get(5, 0))
#|    created = meta.get(6)
#|    return cols, {"rows": meta.get(3), "created_by": created.decode("utf-8", "replace") if isinstance(created, bytes) else None}
#|
#|
#|# ------------------------------------------------------------------------------------------------ backends
#|def _run(argv, timeout):
#|    try:
#|        p = subprocess.run(argv, capture_output=True, timeout=timeout)
#|    except FileNotFoundError:
#|        raise TargetError(f"'{argv[0]}' not found - install it or set its path in [targets]")
#|    except subprocess.TimeoutExpired:
#|        raise TargetError(f"{' '.join(argv[:3])} … timed out after {timeout}s")
#|    if p.returncode:
#|        raise TargetError(f"{' '.join(argv[:3])} … failed: {p.stderr.decode('utf-8', 'replace').strip()[:300]}")
#|    return p.stdout
#|
#|
#|class Local:
#|    name = "local"
#|
#|    def __init__(self, t):
#|        self.t = t
#|
#|    def list(self, path):
#|        root, out = Path(path), []
#|        if not root.exists():
#|            raise TargetError(f"{path} does not exist")
#|        base_depth = len(root.parts)
#|        for dirpath, dirs, files in os.walk(root):
#|            if len(Path(dirpath).parts) - base_depth >= self.t["max_depth"]:
#|                dirs[:] = []
#|            for f in files:
#|                p = Path(dirpath) / f
#|                st = p.stat()
#|                out.append({"path": p.as_posix(), "size": st.st_size, "mtime": st.st_mtime})
#|                if len(out) >= self.t["max_entries"]:
#|                    return out
#|        return out
#|
#|    def tail(self, path, size, n):
#|        with open(path, "rb") as f:
#|            f.seek(max(0, size - n))
#|            return f.read()
#|
#|
#|class WebHdfs:
#|    name = "webhdfs"
#|
#|    def __init__(self, t):
#|        self.t = t
#|        self.url = t["hdfs_url"].rstrip("/")
#|        self.ctx = ssl.create_default_context(cafile=t.get("ca_cert") or None) if self.url.startswith("https") else None
#|
#|    def _get(self, path, **params):
#|        if self.t.get("hdfs_user") and not self.t.get("kerberos"):
#|            params["user.name"] = self.t["hdfs_user"]
#|        url = f"{self.url}{urllib.parse.quote(path)}?{urllib.parse.urlencode(params)}"
#|        if self.t.get("kerberos"):  # SPNEGO: curl does the Kerberos handshake with the ticket from kinit
#|            return _run([self.t.get("curl", "curl"), "-sfL", "--negotiate", "-u", ":", *(["--cacert", self.t["ca_cert"]] if self.t.get("ca_cert") else []),
#|                         url], self.t["timeout"])
#|        try:
#|            with urllib.request.urlopen(url, timeout=self.t["timeout"], context=self.ctx) as r:
#|                return r.read()
#|        except urllib.error.HTTPError as e:
#|            raise TargetError(f"WebHDFS {params.get('op')} {path}: HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}")
#|        except (urllib.error.URLError, OSError) as e:
#|            raise TargetError(f"WebHDFS not reachable at {self.url}: {e}")
#|
#|    def list(self, path):
#|        out, todo = [], [(path.rstrip("/") or "/", 0)]
#|        while todo and len(out) < self.t["max_entries"]:
#|            p, depth = todo.pop(0)
#|            try:
#|                data = json.loads(self._get(p, op="LISTSTATUS"))
#|            except TargetError as e:
#|                if "404" in str(e) or "FileNotFound" in str(e):
#|                    raise TargetError(f"{p} does not exist in HDFS")
#|                raise
#|            for s in data["FileStatuses"]["FileStatus"]:
#|                full = f"{p.rstrip('/')}/{s['pathSuffix']}" if s["pathSuffix"] else p
#|                if s["type"] == "DIRECTORY":
#|                    if depth + 1 < self.t["max_depth"]:
#|                        todo.append((full, depth + 1))
#|                else:
#|                    out.append({"path": full, "size": s["length"], "mtime": s["modificationTime"] / 1000})
#|        return out[:self.t["max_entries"]]
#|
#|    def tail(self, path, size, n):
#|        off = max(0, size - n)
#|        return self._get(path, op="OPEN", offset=off, length=size - off)
#|
#|
#|class HdfsCli:
#|    name = "hdfs cli"
#|    LINE = re.compile(r"^([-d])\S*\s+\S+\s+\S+\s+\S+\s+(\d+)\s+(\d{4}-\d\d-\d\d \d\d:\d\d)\s+(.+)$")
#|
#|    def __init__(self, t):
#|        self.t = t
#|        self.cmd = t.get("hdfs_cli") if isinstance(t.get("hdfs_cli"), list) else [t.get("hdfs_cli") or "hdfs"]
#|
#|    def list(self, path):
#|        out = []
#|        text = _run([*self.cmd, "dfs", "-ls", "-R", path], self.t["timeout"] * 4).decode("utf-8", "replace")
#|        for line in text.splitlines():
#|            m = self.LINE.match(line.strip())
#|            if m and m.group(1) == "-":
#|                out.append({"path": m.group(4), "size": int(m.group(2)),
#|                            "mtime": time.mktime(time.strptime(m.group(3), "%Y-%m-%d %H:%M"))})
#|                if len(out) >= self.t["max_entries"]:
#|                    break
#|        return out
#|
#|    def tail(self, path, size, n):
#|        if size > self.t["max_download_mb"] * 1024 * 1024:
#|            raise TargetError(f"{path} is {size // 1048576} MB - the hdfs CLI cannot read only the footer; use WebHDFS "
#|                              "([targets] hdfs_url) or raise max_download_mb")
#|        with tempfile.TemporaryDirectory() as tmp:
#|            local = Path(tmp) / "f.parquet"
#|            _run([*self.cmd, "dfs", "-get", path, str(local)], self.t["timeout"] * 4)
#|            return Local(self.t).tail(local, local.stat().st_size, n)
#|
#|
#|class S3:
#|    name = "s3"
#|
#|    def __init__(self, t):
#|        self.t = t
#|        self.client = None
#|        try:
#|            if t.get("s3_cli"):
#|                raise ImportError  # an explicitly configured CLI wins over boto3
#|            import boto3  # optional
#|            session = boto3.session.Session(profile_name=t.get("s3_profile")) if t.get("s3_profile") else boto3.session.Session()
#|            self.client = session.client("s3", endpoint_url=t.get("s3_endpoint") or None, region_name=t.get("s3_region") or None)
#|        except ImportError:
#|            self.client = None
#|        self.cli = t.get("s3_cli") if isinstance(t.get("s3_cli"), list) else [t.get("s3_cli") or "aws"]
#|
#|    def _opts(self):
#|        return [*(["--profile", self.t["s3_profile"]] if self.t.get("s3_profile") else []),
#|                *(["--endpoint-url", self.t["s3_endpoint"]] if self.t.get("s3_endpoint") else []),
#|                *(["--region", self.t["s3_region"]] if self.t.get("s3_region") else [])]
#|
#|    @staticmethod
#|    def split(path):
#|        u = urllib.parse.urlparse(path)
#|        return u.netloc, u.path.lstrip("/")
#|
#|    def list(self, path):
#|        bucket, prefix = self.split(path)
#|        out = []
#|        if self.client:
#|            pages = self.client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix,
#|                                                                         PaginationConfig={"MaxItems": self.t["max_entries"]})
#|            for page in pages:
#|                for o in page.get("Contents") or []:
#|                    out.append({"path": f"s3://{bucket}/{o['Key']}", "size": o["Size"], "mtime": o["LastModified"].timestamp()})
#|            return out
#|        data = _run([*self.cli, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix, "--max-items",
#|                     str(self.t["max_entries"]), "--output", "json", *self._opts()], self.t["timeout"] * 4)
#|        for o in (json.loads(data or b"{}") or {}).get("Contents") or []:
#|            when = dt.datetime.fromisoformat(str(o["LastModified"]).replace("Z", "+00:00")).timestamp()
#|            out.append({"path": f"s3://{bucket}/{o['Key']}", "size": o["Size"], "mtime": when})
#|        return out
#|
#|    def tail(self, path, size, n):
#|        bucket, key = self.split(path)
#|        rng = f"bytes={max(0, size - n)}-{size - 1}"
#|        if self.client:
#|            return self.client.get_object(Bucket=bucket, Key=key, Range=rng)["Body"].read()
#|        with tempfile.TemporaryDirectory() as tmp:
#|            local = Path(tmp) / "tail.bin"
#|            _run([*self.cli, "s3api", "get-object", "--bucket", bucket, "--key", key, "--range", rng, str(local), *self._opts()],
#|                 self.t["timeout"] * 4)
#|            return local.read_bytes()
#|
#|
#|def backend(t, location):
#|    loc = str(location)
#|    if re.match(r"(?i)s3a?://", loc):
#|        return S3(t), re.sub(r"(?i)^s3a://", "s3://", loc)
#|    if re.match(r"(?i)hdfs://", loc) or (loc.startswith("/") and (t.get("hdfs_url") or t.get("hdfs_cli")) and not Path(loc).exists()):
#|        path = urllib.parse.urlparse(loc).path if loc.lower().startswith("hdfs://") else loc
#|        if t.get("hdfs_url"):
#|            return WebHdfs(t), path
#|        if t.get("hdfs_cli") or shutil.which("hdfs"):
#|            return HdfsCli(t), path
#|        raise TargetError("HDFS location, but neither [targets] hdfs_url (WebHDFS) nor an hdfs CLI is available")
#|    if re.match(r"(?i)file://", loc):
#|        return Local(t), urllib.parse.urlparse(loc).path
#|    if re.match(r"(?i)[a-z][a-z0-9+.-]+://", loc):
#|        raise TargetError(f"unsupported location scheme in {loc}")
#|    return Local(t), loc
#|
#|
#|# ------------------------------------------------------------------------------------------------ check
#|def listable_root(location):
#|    """The fixed part of a location with placeholders (…/dt=${now()…}/ → …/): list from there."""
#|    loc = str(location).strip()
#|    m = PLACEHOLDER.search(loc)
#|    if not m:
#|        return loc, False
#|    return loc[:loc.rfind("/", 0, m.start()) + 1] or loc[:m.start()], True
#|
#|
#|def _stem(name):
#|    s = Path(str(name).replace("\\", "/")).name
#|    return re.sub(r"(\.(csv|txt|dat|json|xml|gz|zip|parquet|psv|tsv))+$", "", s, flags=re.I).lower()
#|
#|
#|def check(cfg, location, fields=(), file=None, since=None):
#|    """{location, root, backend, files (newest first), matches, schema, issues: [(severity, kind, message)]}."""
#|    t = settings(cfg)
#|    root, templated = listable_root(location)
#|    res = {"location": location, "root": root, "files": [], "matches": [], "schema": None, "issues": []}
#|    be, path = backend(t, root)
#|    res["backend"] = be.name
#|    try:
#|        files = be.list(path)
#|    except TargetError as e:
#|        res["issues"].append(("error", "target-location", f"cannot list {root}: {e}"))
#|        return res
#|    files.sort(key=lambda f: -f["mtime"])
#|    data = [f for f in files if not re.search(r"(^|/)(_SUCCESS|_committed_|_started_|\.crc$|\._)", f["path"]) and not Path(f["path"]).name.startswith(".")]
#|    res["files"] = data
#|    if not data:
#|        res["issues"].append(("error", "target-empty", f"no data files under {root}" + (" (location has placeholders; listed its fixed part)" if templated else "")))
#|        return res
#|    empty = [f for f in data[:50] if f["size"] == 0]
#|    if empty:
#|        res["issues"].append(("warn", "target-zero-byte", f"{len(empty)} zero-byte file(s) among the newest, e.g. {empty[0]['path']}"))
#|    if file:
#|        stem = _stem(file)
#|        res["matches"] = [f for f in data if stem and stem in Path(f["path"]).name.lower()] + \
#|                         [f for f in data if stem and stem in f["path"].lower() and stem not in Path(f["path"]).name.lower()]
#|        if not res["matches"]:
#|            newest = time.strftime("%Y-%m-%d %H:%M", time.localtime(data[0]["mtime"]))
#|            res["issues"].append(("warn", "target-no-file-output", f"no output named like '{stem}' under {root} (outputs are often "
#|                                                                   f"named by the flow, not the input file; newest output {newest})"))
#|    if since:
#|        recent = [f for f in data if f["mtime"] >= since]
#|        if not recent:
#|            res["issues"].append(("warn", "target-stale", f"nothing written under {root} since {time.strftime('%Y-%m-%d %H:%M', time.localtime(since))}"))
#|    pq = next((f for f in (res["matches"] or data) if f["path"].lower().endswith(".parquet") or ".parquet" in f["path"].lower()), None)
#|    if pq is None:
#|        pq = next((f for f in (res["matches"] or data) if f["size"] > 12 and not re.search(r"\.(csv|json|txt|avro|orc|gz)$", f["path"], re.I)), None)
#|    if pq and fields:
#|        try:
#|            tail = be.tail(pq["path"], pq["size"], FOOTER_READ)
#|            if len(tail) >= 8 and tail[-4:] == b"PAR1":
#|                n = struct.unpack("<i", tail[-8:-4])[0]
#|                if n + 8 > len(tail):
#|                    tail = be.tail(pq["path"], pq["size"], n + 8)
#|                cols, info = parquet_schema(tail)
#|                res["schema"] = {"file": pq["path"], "columns": cols, **info}
#|                res["issues"] += compare_schema(fields, cols, pq["path"])
#|        except (TargetError, OSError, IndexError, struct.error) as e:
#|            res["issues"].append(("info", "target-schema", f"could not read the Parquet schema of {pq['path']}: {e}"))
#|    return res
#|
#|
#|def compare_schema(fields, cols, where):
#|    """Structure rows vs the columns of a written Parquet file."""
#|    issues = []
#|    have = {c["name"].lower(): c for c in cols}
#|    leaf = {c["name"].lower().split(".")[-1]: c for c in cols}
#|    names = {f["name"].lower() for f in fields}
#|    missing = [f["name"] for f in fields if f["name"].lower() not in have and f["name"].lower().split(".")[-1] not in leaf]
#|    if missing:
#|        issues.append(("error", "parquet-missing-column", f"structure field(s) not in the written Parquet ({Path(where).name}): "
#|                                                          + ", ".join(missing[:15]) + (f", … +{len(missing) - 15}" if len(missing) > 15 else "")))
#|    extra = [c["name"] for c in cols if c["name"].lower() not in names and c["name"].lower().split(".")[-1] not in names]
#|    if extra:
#|        issues.append(("info", "parquet-extra-column", f"Parquet has column(s) not in the structure (often load metadata): {', '.join(extra[:15])}"))
#|    diffs = []
#|    for f in fields:
#|        c = have.get(f["name"].lower()) or leaf.get(f["name"].lower().split(".")[-1])
#|        if not c or not f.get("type"):
#|            continue
#|        a, b = metamod.type_family(f["type"]), metamod.type_family(c["type"])
#|        if a and b and a != b:
#|            diffs.append(f"'{f['name']}' is {f['type']} in the structure but {c['type']} in the Parquet")
#|    if diffs:
#|        issues.append(("warn", "parquet-type", "; ".join(diffs[:8]) + (f"; … +{len(diffs) - 8} more" if len(diffs) > 8 else "")))
#|    return issues
#|
#|
#|def format_check(res, limit=10):
#|    L = [f"location: {res['location']}" + (f" (listed {res['root']})" if res["root"] != res["location"] else "")
#|         + (f" via {res.get('backend')}" if res.get("backend") else "")]
#|    for sev, kind, msg in res["issues"]:
#|        L.append(f"  [{sev}] {kind}: {msg}")
#|    files = res["matches"] or res["files"]
#|    if files:
#|        L.append(f"  {'outputs for this file' if res['matches'] else 'newest outputs'} ({len(res['matches'] or res['files'])} found):")
#|        for f in files[:limit]:
#|            L.append(f"    {time.strftime('%Y-%m-%d %H:%M', time.localtime(f['mtime']))}  {f['size']:>12,}  {f['path']}")
#|    if res.get("schema"):
#|        s = res["schema"]
#|        L.append(f"  Parquet schema of {Path(s['file']).name}: {s.get('rows')} rows, "
#|                 + ", ".join(f"{c['name']} {c['type']}" for c in s["columns"][:30]) + (" …" if len(s["columns"]) > 30 else ""))
#|    return "\n".join(L)
#|
#|
#|# ------------------------------------------------------------------------------------------------ per definition
#|def enabled(cfg):
#|    return "targets" in cfg  # an empty [targets] section enables local / mounted locations
#|
#|
#|def location_of(cfg, model, entry):
#|    """Where a definition's data lands: its location column, a file-location target, or [targets] location_template."""
#|    if entry.get("location"):
#|        return str(entry["location"])
#|    tmpl = settings(cfg).get("location_template")
#|    table = entry.get("target")
#|    if tmpl and table:
#|        return tmpl.format(table=str(table), table_lower=str(table).lower(), id=entry.get("id"), label=entry.get("label"))
#|    return None
#|
#|
#|def check_diagnosis(cfg, model, diag, file=None, since=None):
#|    """[(definition entry, check result)] for the definitions of a metadata diagnosis that have a location."""
#|    out = []
#|    for d in (diag or {}).get("definitions") or []:
#|        loc = location_of(cfg, model, d)
#|        if not loc:
#|            continue
#|        try:
#|            out.append((d, check(cfg, loc, d.get("fields") or [], file=file, since=since)))
#|        except TargetError as e:
#|            out.append((d, {"location": loc, "root": loc, "files": [], "matches": [], "schema": None,
#|                            "issues": [("error", "target-location", str(e))]}))
#|    return out
#@@ FILE nifikb/tickets.py t 9805b818cbfa0a6b
#|"""Ticket systems (Jira, ServiceNow): read a ticket, pull the facts investigate needs out of it (file names, feed / table
#|names known to the config tables, error text, header lines, attached samples), run the investigation and draft a reply.
#|
#|Reading is all it does by default. A comment is posted only by a person running `ticket <id> --post` (never by an agent
#|through MCP), after secrets and e-mail addresses are scrubbed; ServiceNow gets a work note (internal), not a customer
#|comment, unless [tickets] note_field says otherwise."""
#|import base64
#|import json
#|import os
#|import re
#|import ssl
#|import tempfile
#|import urllib.error
#|import urllib.parse
#|import urllib.request
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|from .logs import scrub
#|
#|FILE_RE = re.compile(r"(?<![\w/\\.-])([\w][\w.\-]*\.(?:csv|txt|dat|json|jsonl|xml|gz|zip|parquet|psv|tsv|xlsx?|avro|orc))\b", re.I)
#|ERROR_RE = re.compile(r"(?i)\b(error|exception|failed|failure|failing|cannot|can't|unable|invalid|mismatch|not found|refused|timed? ?out|"
#|                      r"violat|duplicate|truncat|denied|rejected)\b")
#|HEADER_HINT = re.compile(r"(?i)^\s*(headers?|columns?|fields?|keys?)\s*(?:are|sent|used|:|=|-)+\s*(.+)$")
#|SAMPLE_EXT = re.compile(r"(?i)\.(csv|txt|dat|json|jsonl|psv|tsv)$")
#|MAX_ATTACHMENT = 5 * 1024 * 1024
#|
#|
#|class TicketError(Exception):
#|    pass
#|
#|
#|def settings(cfg):
#|    t = cfg.get("tickets") or {}
#|    if not t.get("url") or not t.get("kind"):
#|        return None
#|    if t["kind"] not in ("jira", "servicenow"):
#|        raise TicketError("[tickets] kind must be 'jira' or 'servicenow'")
#|    return t
#|
#|
#|def _secret(t, key):
#|    if t.get(f"{key}_env") and os.environ.get(t[f"{key}_env"]):
#|        return os.environ[t[f"{key}_env"]]
#|    if t.get(f"{key}_file"):
#|        return Path(t[f"{key}_file"]).read_text(encoding="utf-8").strip()
#|    return None
#|
#|
#|class _Http:
#|    def __init__(self, t):
#|        self.t = t
#|        self.base = t["url"].rstrip("/")
#|        self.timeout = float(t.get("timeout", 30))
#|        self.ctx = ssl.create_default_context(cafile=t.get("ca_cert") or None) if self.base.startswith("https") else None
#|        token, password = _secret(t, "token"), _secret(t, "password")
#|        if t.get("username") and (password or token):
#|            raw = f"{t['username']}:{password or token}".encode()
#|            self.auth = "Basic " + base64.b64encode(raw).decode()  # Jira Cloud (e-mail + API token), ServiceNow basic
#|        elif token:
#|            self.auth = f"Bearer {token}"  # Jira Server / DC personal access token, ServiceNow OAuth token
#|        else:
#|            self.auth = None
#|
#|    def call(self, method, path, body=None, raw=False):
#|        headers = {"Accept": "application/json"}
#|        if self.auth:
#|            headers["Authorization"] = self.auth
#|        data = None
#|        if body is not None:
#|            data = json.dumps(body).encode()
#|            headers["Content-Type"] = "application/json"
#|        url = path if path.startswith("http") else self.base + path
#|        if not url.startswith(self.base):
#|            raise TicketError(f"refusing to follow a link outside {self.base}")  # attachment URLs must stay on the ticket host
#|        req = urllib.request.Request(url, data=data, method=method, headers=headers)
#|        try:
#|            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
#|                if raw:
#|                    return r.read(MAX_ATTACHMENT + 1)
#|                text = r.read().decode("utf-8", "replace")
#|        except urllib.error.HTTPError as e:
#|            hint = {401: "authentication failed - check [tickets] username / token_env / password_env",
#|                    403: "the ticket user lacks permission", 404: "ticket not found"}.get(e.code, "")
#|            raise TicketError(f"HTTP {e.code} on {method} {path.split('?')[0]}: {hint}".strip()) from e
#|        except (urllib.error.URLError, OSError) as e:
#|            raise TicketError(f"cannot reach {self.base}: {e}") from e
#|        return json.loads(text) if text.strip() else None
#|
#|
#|def _adf_text(node):
#|    """Jira Cloud v3 'Atlassian document format' -> plain text (v2 returns plain strings already)."""
#|    if isinstance(node, str):
#|        return node
#|    if isinstance(node, dict):
#|        if node.get("type") == "text":
#|            return node.get("text", "")
#|        sep = "\n" if node.get("type") in ("paragraph", "heading", "codeBlock", "listItem", "doc") else ""
#|        return sep.join(_adf_text(c) for c in node.get("content") or [])
#|    if isinstance(node, list):
#|        return "\n".join(_adf_text(c) for c in node)
#|    return ""
#|
#|
#|class Jira:
#|    def __init__(self, t):
#|        self.http, self.t = _Http(t), t
#|
#|    def fetch(self, key):
#|        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*-\d+", key):
#|            raise TicketError(f"'{key}' does not look like a Jira key (PROJ-123)")
#|        d = self.http.call("GET", f"/rest/api/2/issue/{key}?fields=summary,description,comment,created,status,attachment")
#|        f = d.get("fields") or {}
#|        comments = [_adf_text(c.get("body")) for c in ((f.get("comment") or {}).get("comments") or [])]
#|        atts = [{"name": a.get("filename"), "size": a.get("size") or 0, "url": a.get("content")} for a in f.get("attachment") or []]
#|        return {"id": d.get("key", key), "title": f.get("summary") or "", "description": _adf_text(f.get("description")) or "",
#|                "comments": comments, "created": f.get("created"), "status": ((f.get("status") or {}).get("name")),
#|                "attachments": atts, "ref": d.get("key", key)}
#|
#|    def download(self, att):
#|        return self.http.call("GET", att["url"], raw=True)
#|
#|    def post(self, ticket, text):
#|        self.http.call("POST", f"/rest/api/2/issue/{ticket['ref']}/comment", {"body": text})
#|
#|
#|class ServiceNow:
#|    def __init__(self, t):
#|        self.http, self.t = _Http(t), t
#|        self.table = t.get("table", "incident")
#|
#|    def fetch(self, number):
#|        if not re.fullmatch(r"[A-Za-z]{2,8}\d+", number):
#|            raise TicketError(f"'{number}' does not look like a ServiceNow number (INC0012345)")
#|        q = urllib.parse.urlencode({"sysparm_query": f"number={number}", "sysparm_limit": 1, "sysparm_display_value": "true",
#|                                    "sysparm_fields": "sys_id,number,short_description,description,comments,work_notes,sys_created_on,state"})
#|        rows = (self.http.call("GET", f"/api/now/table/{self.table}?{q}") or {}).get("result") or []
#|        if not rows:
#|            raise TicketError(f"{number} not found in {self.table}")
#|        r = rows[0]
#|        q = urllib.parse.urlencode({"sysparm_query": f"table_sys_id={r['sys_id']}", "sysparm_limit": 20})
#|        atts = [{"name": a.get("file_name"), "size": int(a.get("size_bytes") or 0), "url": f"/api/now/attachment/{a['sys_id']}/file"}
#|                for a in (self.http.call("GET", f"/api/now/attachment?{q}") or {}).get("result") or []]
#|        comments = [c for c in (r.get("comments"), r.get("work_notes")) if c]
#|        return {"id": r.get("number", number), "title": r.get("short_description") or "", "description": r.get("description") or "",
#|                "comments": comments, "created": r.get("sys_created_on"), "status": r.get("state"), "attachments": atts,
#|                "ref": r["sys_id"]}
#|
#|    def download(self, att):
#|        return self.http.call("GET", att["url"], raw=True)
#|
#|    def post(self, ticket, text):
#|        self.http.call("PATCH", f"/api/now/table/{self.table}/{ticket['ref']}", {self.t.get("note_field", "work_notes"): text})
#|
#|
#|def client(t):
#|    return Jira(t) if t["kind"] == "jira" else ServiceNow(t)
#|
#|
#|# ------------------------------------------------------------------------------------------------ facts
#|def _known_names(store, model):
#|    """Normalised identifying values of the config rows (file patterns, feeds, APIs, tables) -> original value."""
#|    known = {}
#|    if not model:
#|        return known
#|    rows = store.get_meta_rows(exclude=model.get("structure_table"))
#|    for table, rs in rows.items():
#|        info = model["tables"].get(table) or {}
#|        cols = [c for c in info.get("columns") or [] if metamod.KEY_COL.search(c) or metamod.TARGET_COL.search(c)
#|                or c in (model.get("definition_keys") or [])]
#|        for r in rs:
#|            for c in cols:
#|                v = r.get(c)
#|                if isinstance(v, str) and 3 <= len(v) <= 120 and v != "***" and not re.search(r"\s", v):
#|                    known.setdefault(metamod.norm(v), v)
#|    return known
#|
#|
#|def extract(ticket, store=None, model=None):
#|    """{files, feeds, tables, error, headers} from the ticket text (title, description, comments)."""
#|    text = "\n".join([ticket.get("title") or "", ticket.get("description") or ""] + list(ticket.get("comments") or []))
#|    files = []
#|    for m in FILE_RE.finditer(text):
#|        if m.group(1) not in files:
#|            files.append(m.group(1))
#|    known = _known_names(store, model) if store is not None else {}
#|    feeds, tables = [], []
#|    for tok in re.findall(r"[A-Za-z][\w.\-]{2,}", text):
#|        v = known.get(metamod.norm(tok))
#|        if v and v not in feeds and v not in tables and tok not in files:
#|            (tables if metamod.norm(v).startswith(("stg_", "tgt_", "dim_", "fact_", "raw_")) else feeds).append(v)
#|    headers, candidates = [], []
#|    title = (ticket.get("title") or "").strip()
#|    for n, line in enumerate(text.splitlines()):
#|        s = line.strip()
#|        h = HEADER_HINT.match(s)
#|        if h and not headers:
#|            parts = [p.strip().strip("'\"`") for p in re.split(r"[,|;\t]", h.group(2)) if p.strip()]
#|            if len(parts) >= 2:
#|                headers = parts
#|                continue
#|        if (ERROR_RE.search(s) or re.search(r"\w(Exception|Error)\b", s)) and 10 <= len(s) <= 500 and not h:
#|            # the most specific line wins: an exception class or "Error: ..." beats a summary like "load failed"
#|            score = 3 * bool(re.search(r"\w(Exception|Error)\b", s)) + (":" in s) - (s == title)
#|            candidates.append((-score, n, re.sub(r"(?i)^error\s*:\s*", "", s)))
#|    error = min(candidates)[2] if candidates else None
#|    if not headers:  # a pasted header line: 3+ identifier-like tokens split by one delimiter
#|        for line in text.splitlines():
#|            s = line.strip()
#|            for d in (",", "|", ";", "\t"):
#|                parts = [p.strip() for p in s.split(d)]
#|                if len(parts) >= 3 and all(re.fullmatch(r"[A-Za-z_][\w .\-]{0,60}", p) for p in parts) and s.count(" ") < len(parts) * 2:
#|                    headers = parts
#|                    break
#|            if headers:
#|                break
#|    error_words = error
#|    if error and len(error) > 200:
#|        error_words = error[:200]
#|    return {"files": files[:5], "feeds": feeds[:5], "tables": tables[:5], "error": error_words, "headers": headers}
#|
#|
#|def fetch_samples(cl, ticket, max_files=2):
#|    """Download small CSV / JSON attachments to a temp folder (the caller removes it). Returns (dir, [paths])."""
#|    wanted = [a for a in ticket.get("attachments") or [] if a.get("name") and SAMPLE_EXT.search(a["name"])
#|              and 0 < (a.get("size") or 1) <= MAX_ATTACHMENT][:max_files]
#|    if not wanted:
#|        return None, []
#|    tmp = tempfile.mkdtemp(prefix="nifikb-ticket-")
#|    paths = []
#|    for a in wanted:
#|        try:
#|            data = cl.download(a)
#|        except TicketError:
#|            continue
#|        if data is None or len(data) > MAX_ATTACHMENT:
#|            continue
#|        p = Path(tmp) / re.sub(r"[^\w.\-]", "_", a["name"])
#|        p.write_bytes(data)
#|        paths.append(str(p))
#|    return tmp, paths
#|
#|
#|def draft_comment(ticket, facts, report, kb_built=None):
#|    """A short reply for the ticket: likely causes, proposed fixes, what was checked. Scrubbed of secrets / e-mails."""
#|    L = [f"Automated first analysis (nifikb) for {ticket['id']} - please verify before acting."]
#|    looked = [f"file {', '.join(facts['files'])}" if facts["files"] else None, f"feed {', '.join(facts['feeds'])}" if facts["feeds"] else None,
#|              f"table {', '.join(facts['tables'])}" if facts["tables"] else None, "the error text" if facts["error"] else None,
#|              f"{len(facts['headers'])} headers" if facts["headers"] else None]
#|    L.append("Checked: " + ", ".join(x for x in looked if x) + (f" (knowledge base built {kb_built})" if kb_built else ""))
#|    L.append("")
#|    if report["causes"]:
#|        L.append("Most likely causes:")
#|        L += [f"{n}. {c}" for n, c in enumerate(report["causes"][:5], 1)]
#|    else:
#|        L.append("No conclusive cause found yet - the support team will look further.")
#|    fixes = next((text for title, text in report["sections"] if title.startswith("Proposed fixes")), None)
#|    if fixes:
#|        L += ["", "Proposed config fix (to be reviewed and run by the platform team):", fixes]
#|    if report.get("next_checks"):
#|        L += ["", "Still open: " + "; ".join(report["next_checks"][:3])]
#|    return scrub("\n".join(L))
#@@ FILE nifikb/util.py t 45126c6fba2974e8
#|"""Small shared helpers: ids, slugs, redaction, and the regexes used to spot hardcoded values."""
#|import hashlib
#|import os
#|import re
#|from pathlib import Path
#|
#|REDACTED = "<redacted>"
#|
#|SECRET_NAME = re.compile(r"(?i)(pass(word|wd)?|pwd|secret|api[_\- ]?key|access[_\- ]?key|private[_\- ]?key|token|credential)")
#|URL_RE = re.compile(r"\b(?:https?|ftps?|sftp|s3a?|s3n|hdfs|wss?|gs|abfss?|wasbs?)://[^\s\"'<>`)]+", re.I)
#|JDBC_RE = re.compile(r"\bjdbc:[a-z0-9]+:[^\s\"'<>`]+", re.I)
#|IP_RE = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
#|HOST_RE = re.compile(r"(?<![\w.@/-])(?:[a-z0-9-]+\.)+(?:com|net|org|io|local|internal|corp|lan|intra|cloud|in|co|aws)(?![\w.-])", re.I)
#|WIN_PATH_RE = re.compile(r"(?:(?<![A-Za-z])[A-Za-z]:[\\/](?!/)|\\\\[\w.-]+\\)[^\"'<>|*?\r\n]*")
#|UNIX_PATH_RE = re.compile(r"(?<![\w.:/$}])/(?:opt|data|home|tmp|var|mnt|srv|app|apps|usr|etc|nifi|shared|export|landing|archive|inbound|outbound)(?:/[\w.${}#@ -]*)*", re.I)
#|# Captures the literal assigned to something that looks like a secret: password = "x", "pwd": "x", pass: 'x'
#|SECRET_ASSIGN_RE = re.compile(
#|    r"(?i)([\w.\-]*(?:pass(?:word|wd)?|pwd|secret|api[_-]?key|access[_-]?key|token)[\w.\-]*)[\"']?\s*(?:=|:|,|\()\s*[\"']([^\"']{2,})[\"']"
#|)
#|
#|EL_VAR_RE = re.compile(r"\$\{\s*([A-Za-z_][\w.\-]*)\s*\}")
#|EL_REF_RE = re.compile(r"\$\{\s*([A-Za-z_][\w.\-]*)\s*(?=[:}])")
#|PARAM_RE = re.compile(r"#\{\s*(?:'([^']+)'|([^}]+?))\s*\}")
#|
#|
#|def short(i):
#|    return (i or "")[:8]
#|
#|
#|def slugify(text, maxlen=60):
#|    s = re.sub(r"[^A-Za-z0-9]+", "-", text or "").strip("-").lower()
#|    return (s[:maxlen].rstrip("-")) or "unnamed"
#|
#|
#|def sha1_bytes(data):
#|    return hashlib.sha1(data).hexdigest()
#|
#|
#|def sha1_file(path):
#|    h = hashlib.sha1()
#|    with open(path, "rb") as f:
#|        for chunk in iter(lambda: f.read(1 << 20), b""):
#|            h.update(chunk)
#|    return h.hexdigest()
#|
#|
#|def file_sig(path):
#|    st = os.stat(path)
#|    return f"{st.st_size}:{int(st.st_mtime)}"
#|
#|
#|def redact_secrets(text):
#|    """Replace literal secret values (password = "x") in a line of code or config."""
#|    return SECRET_ASSIGN_RE.sub(lambda m: m.group(0).replace(m.group(2), REDACTED), text)
#|
#|
#|def clip(text, n=160):
#|    text = " ".join((text or "").split())
#|    return text if len(text) <= n else text[: n - 1] + "…"
#|
#|
#|def md_escape(text):
#|    return (text or "").replace("|", "\\|").replace("\n", " ")
#|
#|
#|def write_if_changed(path, content):
#|    path = Path(path)
#|    path.parent.mkdir(parents=True, exist_ok=True)
#|    if path.exists() and path.read_text(encoding="utf-8") == content:
#|        return False
#|    path.write_text(content, encoding="utf-8")
#|    return True
#@@ FILE nifikb/web.py tc 61fa7b086636fc87
#|"""Self-service web page for colleagues (stdlib only): investigate a file / feed / table / error, daily report, live health,
#|search, team learnings. Read-only. `python -m nifikb web` - configure host / port / login in [web] of nifikb.toml.
#|
#|Security: binds to 127.0.0.1 unless [web] host is set; optional HTTP basic login (one shared user, password from an env var
#|or file); every value is HTML-escaped; uploads are size-limited, written to a temp file and deleted after use."""
#|import base64
#|import email.parser
#|import email.policy
#|import hmac
#|import html
#|import os
#|import re
#|import tempfile
#|import threading
#|import urllib.parse
#|from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
#|from pathlib import Path
#|
#|from . import __version__
#|
#|MAX_UPLOAD = 20 * 1024 * 1024
#|STYLE = """body{font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1f2328;margin:0}
#|header{background:#1f4e79;color:#fff;padding:10px 20px}header a{color:#fff;margin-right:16px;text-decoration:none}
#|main{padding:16px 20px;max-width:1200px}label{display:block;margin-top:8px;font-weight:600}
#|input[type=text],textarea{width:100%;max-width:700px;padding:6px;font:inherit}textarea{height:60px}
#|button{margin-top:12px;padding:7px 18px;background:#1f4e79;color:#fff;border:0;border-radius:4px;cursor:pointer}
#|pre{background:#f6f8fa;padding:10px;overflow-x:auto;white-space:pre-wrap;font-size:12.5px;border:1px solid #d0d7de}
#|ol li{margin:4px 0}.hint{color:#57606a;font-size:12.5px}h2{margin-top:24px;border-bottom:1px solid #d0d7de}"""
#|
#|
#|def _page(title, body):
#|    nav = "".join(f'<a href="{u}">{t}</a>' for u, t in (("/", "Investigate"), ("/report", "Daily report"), ("/health", "Live health"),
#|                                                         ("/search", "Search"), ("/learnings", "Learnings")))
#|    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)} - nifikb</title><style>{STYLE}</style>"
#|            f"</head><body><header><b>NiFi support</b> &nbsp; {nav}</header><main>{body}</main></body></html>").encode("utf-8")
#|
#|
#|def _md_to_html(text):
#|    """Render nifikb's markdown-like reports: #/## headings, numbered causes as a list, the rest preformatted."""
#|    out, pre, ol = [], [], []
#|
#|    def flush():
#|        if ol:
#|            out.append("<ol>" + "".join(f"<li>{html.escape(x)}</li>" for x in ol) + "</ol>")
#|            ol.clear()
#|        if pre:
#|            out.append("<pre>" + html.escape("\n".join(pre)) + "</pre>")
#|            pre.clear()
#|
#|    for line in text.splitlines():
#|        if line.startswith("## ") or line.startswith("# "):
#|            flush()
#|            out.append(("<h2>" if line.startswith("## ") else "<h1>") + html.escape(line.lstrip("# ")) + ("</h2>" if line.startswith("## ") else "</h1>"))
#|        elif re.match(r"^\d+\. ", line) and not pre:
#|            ol.append(line.split(". ", 1)[1])
#|        elif line.strip() or pre:
#|            if ol:
#|                flush()
#|            pre.append(line)
#|    flush()
#|    return "".join(out)
#|
#|
#|def _form(values=None):
#|    v = {k: html.escape(values.get(k, "")) for k in ("file", "feed", "table", "error", "headers")} if values else dict.fromkeys(
#|        ("file", "feed", "table", "error", "headers"), "")
#|    return f"""<h1>Investigate a problem</h1>
#|<p class="hint">Fill in what the ticket gives - any one field is enough. The answer lists the most likely causes first, with evidence.</p>
#|<form method="post" action="/investigate" enctype="multipart/form-data">
#|<label>File name</label><input type="text" name="file" value="{v['file']}" placeholder="SALES_20260926.csv">
#|<label>Feed / API name</label><input type="text" name="feed" value="{v['feed']}">
#|<label>Target table</label><input type="text" name="table" value="{v['table']}">
#|<label>Error text</label><input type="text" name="error" value="{v['error']}" placeholder="a distinctive part of the error message">
#|<label>Headers / field names sent (in file order, comma separated)</label><textarea name="headers">{v['headers']}</textarea>
#|<label>Sample file (CSV / JSON, max 20 MB)</label><input type="file" name="sample">
#|<label><input type="checkbox" name="live" value="1"> read the config tables now (if they may have changed)</label>
#|<button type="submit">Investigate</button></form>"""
#|
#|
#|class App:
#|    def __init__(self, cfg):
#|        from .config import load_config
#|        self.cfg = cfg if isinstance(cfg, dict) else load_config(cfg)
#|        w = self.cfg.get("web") or {}
#|        self.user = w.get("user")
#|        self.password = (os.environ.get(w["password_env"]) if w.get("password_env") else None) or \
#|            (Path(w["password_file"]).read_text(encoding="utf-8").strip() if w.get("password_file") else None)
#|        self.lock = threading.Lock()
#|
#|    def store(self):
#|        from .cli import _store
#|        return _store(self.cfg)
#|
#|    def names(self, store):
#|        from .cli import runtime_names
#|        return runtime_names(store)
#|
#|    # ------------------------------------------------------------------------------------------ pages
#|    def investigate(self, fields, sample_bytes=None, sample_name=None):
#|        from . import diagnose as dg, investigate as inv
#|        tmp = None
#|        try:
#|            if sample_bytes:
#|                suffix = Path(sample_name or "sample.csv").suffix or ".csv"
#|                fd, tmp = tempfile.mkstemp(suffix=suffix)
#|                with os.fdopen(fd, "wb") as f:
#|                    f.write(sample_bytes)
#|            store = self.store()
#|            try:
#|                r = inv.investigate(self.cfg, store, self.names(store), file=fields.get("file") or None, feed=fields.get("feed") or None,
#|                                    table=fields.get("table") or None, error_text=fields.get("error") or None,
#|                                    headers=dg.split_headers([fields.get("headers", "")]), sample_path=tmp, live=bool(fields.get("live")))
#|            finally:
#|                store.db.close()
#|            return inv.format_report(r)
#|        finally:
#|            if tmp:
#|                os.unlink(tmp)
#|
#|    def report(self):
#|        from . import report as rp
#|        store = self.store()
#|        try:
#|            return rp.to_markdown(rp.build_report(self.cfg, store, self.names(store)))
#|        finally:
#|            store.db.close()
#|
#|    def health(self):
#|        from . import nifiapi
#|        if not nifiapi.settings(self.cfg):
#|            return "NiFi REST API not configured ([nifi_api] in nifikb.toml)."
#|        store = self.store()
#|        try:
#|            return nifiapi.format_health(nifiapi.health(nifiapi.Client(nifiapi.settings(self.cfg)), versioned=store.versioned_groups()),
#|                                         self.names(store))
#|        except nifiapi.NiFiApiError as e:
#|            return f"error: {e}"
#|        finally:
#|            store.db.close()
#|
#|    def search(self, q):
#|        store = self.store()
#|        try:
#|            rows = store.search(q, 30) if q else []
#|            return "\n".join(f"[{r['kind']}] {r['title']}  -> {r['doc']}\n    {r['snip']}" for r in rows) or ("no matches" if q else "")
#|        finally:
#|            store.db.close()
#|
#|    def learnings(self):
#|        from . import learnings as lm
#|        items = lm.load_all(self.cfg, include_obsolete=False)
#|        return "\n\n".join(lm.format_item(i) for i in items) or "no team learnings yet"
#|
#|
#|def make_handler(app):
#|    class Handler(BaseHTTPRequestHandler):
#|        server_version = f"nifikb/{__version__}"
#|
#|        def log_message(self, fmt, *args):
#|            pass
#|
#|        def _auth(self):
#|            if not app.user or not app.password:
#|                return True
#|            head = self.headers.get("Authorization", "")
#|            if head.startswith("Basic "):
#|                try:
#|                    user, _, pw = base64.b64decode(head[6:]).decode("utf-8").partition(":")
#|                except (ValueError, UnicodeDecodeError):
#|                    return False
#|                if hmac.compare_digest(user, app.user) and hmac.compare_digest(pw, app.password):
#|                    return True
#|            self.send_response(401)
#|            self.send_header("WWW-Authenticate", 'Basic realm="nifikb"')
#|            self.end_headers()
#|            return False
#|
#|        def _send(self, body, code=200):
#|            self.send_response(code)
#|            self.send_header("Content-Type", "text/html; charset=utf-8")
#|            self.send_header("Content-Length", str(len(body)))
#|            self.send_header("X-Content-Type-Options", "nosniff")
#|            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'unsafe-inline'")
#|            self.end_headers()
#|            self.wfile.write(body)
#|
#|        def do_GET(self):
#|            if not self._auth():
#|                return
#|            url = urllib.parse.urlparse(self.path)
#|            q = urllib.parse.parse_qs(url.query)
#|            try:
#|                if url.path == "/":
#|                    return self._send(_page("Investigate", _form()))
#|                if url.path == "/report":
#|                    return self._send(_page("Daily report", _md_to_html(app.report())))
#|                if url.path == "/health":
#|                    return self._send(_page("Live health", "<h1>Live NiFi health</h1><pre>" + html.escape(app.health()) + "</pre>"))
#|                if url.path == "/search":
#|                    term = (q.get("q") or [""])[0]
#|                    body = (f"<h1>Search</h1><form><input type='text' name='q' value='{html.escape(term, quote=True)}'>"
#|                            f"<button>Search</button></form><pre>{html.escape(app.search(term))}</pre>")
#|                    return self._send(_page("Search", body))
#|                if url.path == "/learnings":
#|                    return self._send(_page("Learnings", "<h1>Team learnings</h1><pre>" + html.escape(app.learnings()) + "</pre>"))
#|                self._send(_page("Not found", "<p>Not found</p>"), 404)
#|            except Exception as e:  # show the problem instead of a dropped connection
#|                self._send(_page("Error", f"<pre>{html.escape(type(e).__name__ + ': ' + str(e))}</pre>"), 500)
#|
#|        def do_POST(self):
#|            if not self._auth():
#|                return
#|            if urllib.parse.urlparse(self.path).path != "/investigate":
#|                return self._send(_page("Not found", "<p>Not found</p>"), 404)
#|            length = int(self.headers.get("Content-Length") or 0)
#|            if length > MAX_UPLOAD + 100_000:
#|                return self._send(_page("Too large", "<p>The upload is larger than 20 MB.</p>"), 413)
#|            body = self.rfile.read(length)
#|            fields, sample, sample_name = {}, None, None
#|            ctype = self.headers.get("Content-Type", "")
#|            if ctype.startswith("multipart/form-data"):
#|                msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
#|                    f"Content-Type: {ctype}\r\n\r\n".encode() + body)
#|                for part in msg.iter_parts():
#|                    name = part.get_param("name", header="content-disposition")
#|                    payload = part.get_payload(decode=True) or b""
#|                    if name == "sample":
#|                        if payload:
#|                            sample, sample_name = payload, part.get_filename()
#|                    elif name:
#|                        fields[name] = payload.decode("utf-8", "replace").strip()
#|            else:
#|                fields = {k: v[0].strip() for k, v in urllib.parse.parse_qs(body.decode("utf-8", "replace")).items()}
#|            if not any(fields.get(k) for k in ("file", "feed", "table", "error")):
#|                return self._send(_page("Investigate", "<p><b>Give at least a file, feed, table or error text.</b></p>" + _form(fields)))
#|            try:
#|                report = app.investigate(fields, sample, sample_name)
#|                self._send(_page("Investigation", _form(fields) + "<hr>" + _md_to_html(report)))
#|            except Exception as e:
#|                self._send(_page("Error", _form(fields) + f"<pre>{html.escape(type(e).__name__ + ': ' + str(e))}</pre>"), 500)
#|    return Handler
#|
#|
#|def serve(cfg, host=None, port=None):
#|    app = App(cfg)
#|    w = app.cfg.get("web") or {}
#|    host = host or w.get("host", "127.0.0.1")
#|    port = int(port or w.get("port", 8765))
#|    server = ThreadingHTTPServer((host, port), make_handler(app))
#|    print(f"nifikb web on http://{host}:{server.server_address[1]}/" + ("" if app.user else "  (no login configured: [web] user + password_env)"))
#|    server.serve_forever()
#@@ FILE tests/fixtures/local/flow.json.gz b 4b0b53402c2e9e72
#|H4sIAAAAAAAA/+09aXPbtrZ/haPpx8CX2Egg3xwvuZ5xbF/baWfedcaD1WZLkypJOXEz/e/3gBQl
#|epEiOWmSlyidJhaE7ewLcOCPI1eY0mbF1a+uqrOyGL38OLpRv5fV7DN5MbrJikFD/De0qA/n2Y2r
#|dqvs1hXn15VTdqecFM3oJY7br/egvXnq6xejyl1ldVNlrh69/O+7F6OxqtSNa1y1UxaN+9A8bD6p
#|ytvMwvJdu4FeVZnnrjpz1W1m+mkqNy6rBkA5V/Uf07bG3Yxz1cy6lGXzuion4wAmTFk0mc9cNXo5
#|8jqOU2JjxAVNEI29QyohGBHiEyoSLxlToxejrKgbVRh3MBwr41QkgsYoxpIgHMcxYiRhyOuEOwF/
#|YaxhbAHQQO+jbD+L9vPy/SiAcnMDE8HuRvBpXNZZM6XBB8DzFmDyrv0XMD6uSoC0bnc/A/imbNzJ
#|4y+mfcsWYw8ATV1qBOEp8owIRI1PkMKxQAb2jWGjWOLFgGLpY+v9ANCUkxgpYxNrTWo8NnNA911j
#|rvez3H0KUMxSMoU1TTpom7txmKKsrrbUWJlrt1XAJrbmgG2F7VlV2a3hMnpSWPgBpr3qqPxwBuij
#|gEe8MsCKo9CC+olQoSr4+rZn8xHeIulWPOpwP3YwLLDRx9Gb8tZFwKo+z0wTnTUV8NcV7H106lrI
#|X4wOy6sod7cuj95fuyLysLmoKJvIgwhY6Lh3enp8+rgfrHGT1WH1CLCeuWHXAGDUlFELLbT/8rFD
#|iGqu/764CCvUFxe1gn8urWrUZa2A8V2EokdtlxaELytMs2XqW5h5pwytgRxDWHYdtLmoxescA3e7
#|rjZVNm5a1voIX9TNXYvw8CMg2U5yEMATV2Vl2H0c1S5wxPyrwRLnB2/2Ti93Tw9+3TuCPu6DM5Ow
#|jaPSBtpvHx4GVgGc5rDuBIZ1ZKH9pHeZy+3gCzxt15M8wFMcBsxC+2/bp2H+alL0nd9keZ4BAHGr
#|TMykqoA387uzbpdK5y6okLnCUpOmPA/EKWDv9tTl7Sz1ddYK3MirLJ9Urt1tT8GtKQVBGspmqyP8
#|uxkinD1rYKrAM2+Pjg6OXof9uaa6G+jQ8Dl7vBpMopX5o/T+jTPXqsjqG5jmZO9o+/Dg//Yu9w+P
#|f9s/ONwbtUr4VddzRg8cRwBE3QnkuCwA7PNO0k5Oj3f2zs5aXmtl52Bt7fj3iweqhnFLLbMeEVAM
#|MMp4pJ0jiKRKmFilWnqxRKdKmVA5UDWwrEFKw7CEW2xw+gxVk+Bkqmk4JhtN889qmqUK5gi4b6NZ
#|NprlWZpFOCYtJQ6lqXOIcmaQIIohY4j1VMaJ1nixZlFeaokHmkViQ5CRhHCdJk45NdcsJ5NmFzha
#|q9qdOlNWdnUNI2KxroZ5arWvomnGkwZZjap2UaRycE/RzSRvMpDcMBv40VOIvcrrwJBNYGYUuO5G
#|IRM2g+rsL9eyQhzQcm/GPyfgqVrUDZqTcjjh/QGT4kY1gaWRKfPJTQGW41rdZmWg4D5IRQTa5G3f
#|B3Rk6FM/mgVUQlEH/x/5INIoEDWs2VSTx0tao8eo7kKKjk84ldQN+ETThCCeSmZjRiX37Ak4XXWH
#|GgiNyknTq6mysGFrIWYJAobKAvWCvQj8GcrRlHsOjs72Ts8f9dOgOGBBX1aACuj29nwfBZsKPaYD
#|X7sCZNQsosh9WjyJl45oU3lolfwSanV4Xkqs/dDl8RygVJAOXQZ89JiRZv8oO5Vm6TiLhyGJSilB
#|oDkwV5wJQoMQ2alUAX1bJYqC4g1ynDUzGmyM0arGqDUoP53RcTFJncYCwl1NEU2NQ0IxjKSS2ogk
#|5danyyJnpfQwRcAl9sgZ5rAXRvuW159rdAYRtBRsY3U2VudLWp3Lg9dHx6d7zzA+J2XdXFXu7D+H
#|G/uzsT+faX9+TqtjU429sx5JDvEOVVIigcH0GMnjNJEmscItS6IkxibDUEdRiVyiEocxT6hlc6vT
#|eoqA0JCbXimXEvcZakLXzqU8sdhXMTlA7QrGuwokcaiz2qzHWSf48StoeBVUQd8Sgsm3RQZ6Nuo3
#|PDQiwXpG+70aPHcfms8Q5o69fnRpfkqMdw/Otl8d7u3+kHJMKLPOeIpkTAyimCVIEsFQLA0zSZwa
#|LZd4jwILhc0wGUoIRSDBRnqpjPB2Lsd7LU84YBqnbnZAgkFEPu1Ail6YOVn7CGbBil9FoFV1NWnh
#|GgjJdAvRdv9ddDKVRZjyjfoQbTfAThq2HB264qoJaU7Cky5X2Y48UW3j+K65LoMs9jNFuy7PwGi3
#|ZIngi4OroqxAc5zvHhwNNMKjHTxKpHY6ob64CKd4t+7STsZ5ZsJR5db4Lrr4zLTrxWjjTnzCnSir
#|7Aq+yttEavGXq8oo+L+T+qdzMZjR2MQcPFcSS3AxHKgmzg24CdpQGVuYUC9UTSw1qdbp8EjYJxDY
#|2jR4LhyL9oznuYEtgVn7wFau7WRsAttNYPt0YPv2ZHf7/DkR7SaduglnN+nUL2F1JMh8jB1D1FuM
#|qLQwynmJiItT4DufpNQvsjrKG+84ZgM2NdSmiHtNCOEwDxvcuFr5dgCE2P09pPWd4M3tgM3tgP8/
#|twNAI/ywoTaYKsni2CBiMIzS1iOtnYNwWWrpaCJSvzhlhqUzwql7VxxBKylqrbBWGY7x81NmEGaL
#|PmfG1tYwm5zZJmf2Q+fM3gWhBAf1pKz6S+Dg999vADwWzrQAPb7cTIVSiYHwk6XWIOpEgrQF95WB
#|uxBj2IEQybJIViXJvXtBnHAkYbNxSlOlxeBeUOC1clIZ190kXz2Kbhaia1U0rRFNPz9kBzmzLtwT
#|Vr36aoF0whEJKEWp1IBgjmGD1GDkueSxB38uaU8UpkDug/u6d/gZEO5PgNj56mDJBNsBWECNFFlB
#|jKIpF4anASwQO5cfFNZ9aEXur+mPIDC1y4GznjC09cQEZTyais5JBR/A8B7r36F/qG6or8vcBqmD
#|P/f7BAIFhTjoBfrjddCWfqoV9z6Ms5lu6XXOGASuAtPx16zsQbsQ97Y/5qWyr1QeUDC8sn18eXR8
#|fnl4vL17+Wr7cPtopw1wg/oPk4NOnKU9OzQOpgleWNXFcvOZdo7fnJwCkz4h7TvHQNmd84Pjoy9o
#|txVNMBhokF5GOaJGWyQ8CCQVVsuYKMr54lt9WHqgPh9esHDADFZwmWpgC0rYMuldMT3/BaV3pTT9
#|848DFgjwiuUfXxDOxdHX82tMnifGnS2J6hbjG2H+Z4XZGwqudqJRIhOI8S1RIFBGg2VWwscx5y62
#|C3kgXP73yfDcWjAwxUQ65rTiSpGlpnjFM/MvyOSfDASefz6/QJBXLK74hoK8SgXHxh5/xyLMmYgp
#|hb6SA59RHIM9BsFFCbMqAYdPYrL4XAinWjmiB9QnIlgcYGoqE+BPnSz1pn8U9n5KdlcsX/gOQoVV
#|aiU2MvwdyzDDxqYESEaJADnShAGrxRopTwV4gkLEdtmlZec8GQaKnKTA50ozrphMnVzqU6+Yh/v2
#|ZniVnN8CUf4R44aNNH+v0pxQbxk3Brk0BpHmIIyKEjDLWKWxA3kC93hZfgQC6XtHuxwrRBPFLRc+
#|Fdwsk+YVyx++A6O1Sq3FIq/6R0viPUOW+2OljSz/o7IsaCpMogSykoB3zcAwSg1GyFEKnlWqeUoW
#|56pjjV1KhtkuZgxFEDBqB/aHMkGWyfIP54A+JcvUCYmpIMgzBaZZGo4EFQ7x1OJYYa6wHIQQXzdX
#|DcGDsunQ4wA3AqMkiROsYsVg79+/JZ6duv2M4kuoN0JSjZhOwIjGqUU6hlAVJAgMdJymqV6c3wIL
#|5UhKB+THzjPEYppQBlaWy6XB8U9hirEyUmmToDSmoKOCelNWWUQcUYljqWI+/lbiC2BZQYdHTeCL
#|UdDBlFrwshJN9UZ8v2vxZRZiu1hYCIRBcqlP4KcUWCzWUnOTJiRuveGFt8+8Bys0uMqaMCB/KmiM
#|Pdfx8vT0ijffvl1ua6XrdYtOiH803fR9C/HP7EETaq2CkBeJxKSIEpwibUGOcCytEcJYKuQy6mtt
#|h46lS0iChCGpwIxizcQyGf5hzlE3MryR4a8ow++mxHji8pYTliRWaMRVHE5tLcRrxguUcE5hSAJh
#|0WJxZqlPmByaZAjwJEoUxQk3BOLsFsMPqosIZluJZJIzsLwkxXT6cFOyRRnHBAQ8FjzBPQfBQm/H
#|VoU3RqPCvY9uVT5xdeTLKuoKKeoo81Fz7SoXqfB/EQoOB9z2PrOhrrC9Xf5idO2yq+tm9JKx9lJo
#|f8Vx5MuimVVtkPGHwMEPiXG4/Wro7n62Lk1TIbViaVCA4A9Z0GxKhiN3GGpjjgVeUp5KDbckHh5j
#|M6oNMgrDalJrQ/Fj5GMye7Okf4uvR/JpKIkMSJ4XRT6JR9IhrscjTr49HnmMibRMhetLGmxSGphY
#|AlqpBhZLjeF0yXmLihNvh0zMYwcRJsNCs1h7GPwUHnn/4liLgAEeA2O25UZ19D5rriNQMDequou6
#|GrA6uiguir0idIiupicnQUG1dQKzC8hRqGOtAoYjA8T4o/0Mu6+aqAQIoqc5PGZDyhCZfHPKaGMw
#|TolHgOFwp4xLJJzCEL8L7lPCCXdLboULk1I5zLcZRghKDLMKrCGXxj+mTDqrXUThUbgBYXZUEU1q
#|F5mqLKJg9GxkVJ5HgO3+qzyrG1dE100zHtAC1Mt7F71XRROKMKYvIUf6Lto+OWineJoa3UZmckKX
#|UEN8HWokHtwKKsHhilk4UUwd0pRoZBkoe8Nokvgld/1UjNN78RdOGENCxyKG0CSNnXxMDTZ7rqKF
#|f0CN/ftiUk6ah5LyJFa5uMfjdBlW/yEeB2vq27zFU3ehV0t/Pj8/+Zjfk764AZPp24cPAX6Ypvls
#|PloxS/T8NM5jfZvEczBl8nXAXPHe9fMvRj/2jeisGA5T8g9R892C19wfqm7GFUgb6GowoIhqiPFA
#|WXAwjB6c/9Qz6ZY897lSRes0Dtk5+/W0q4V9GH8sqNMx9e3WcNBzCnL6ImVXZSrP/mrDgr5yul65
#|SidrX6JAsCF03Zfz9sU256DOIltOgqVvK5VHs+Jk2Py8DMdM6qa8gdb/hE7RTl/4A19dBCTA5JMm
#|y+tpSfvMPZuu+LAg/NfgH0dnLrzk37Tlyy/gvy7Au9d8cRHykHu1UeMHq15A+9kf2Tj6d7tCdJgV
#|g823cE0LoGeN0yL6KUV/+dh93gqf/+5gmNY7t7iCTdTtUoHcEP+hrixxOolqg0BUzyOuOX4R/J/d
#|trV2M7wsKpWaThd+uwG0foyi6KLlqIvRS/ipYwAAtW0PG+3ajytYom9uS8Hr8MV/o/Dn47BnGXpe
#|FpMb3Q0Yzp4VzQWwy+NBf07Aj8iau8t2tLMrDwTraNylA55+OKTjsadHdXvMgYDrbrStHV1/KYjU
#|3MNR4fdOFFcLlmmf/1hnxJ9NdZmtjjfgr+Z6nQF3Tq21AGgEOzFNi+R14Lipq/E6+O3XMaVda51O
#|vwRObZtWHzi+LteDSFkbchstJvBzB5K1YANJWpfb1sNBCUPy9XEeKgKrtbYG+qvKQDOvNSgYchV4
#|T9XN2vTtB/usesZo6wAvwdVeOAhGvIv+Xlph+sgR2R5nnS+ywPTfs9dbnVXr/IB9AAWw90x3YFaf
#|O3MB1Dhb6Ab8vby6e0GN6hO5vfPT48PDvdPLs73TXw/aNOIXi/Vi8N2EilHCMQX3zYXrpypFnEup
#|tacYL8vTc6MSPbxHTlMIagQ1MYVITyeKzt237duqXM9/UzBi696wb+fBfcpxefAqULzMTXFgYK11
#|FgUAp+8KPfJDfvnYgt81/jzSMaiZ/h7EQyqcQFQXI6wwCeIhkLZKIcwdhHXOMC4WHkVLzIQSfhjb
#|pTZhSOs4gfhdqVgPLoK1gUogxJlrfqvaV+zWDXMejv520rJW4HJQmHxi3dNRxJcKU1oxilrUDN8y
#|KQby95yAZaGMZ8U1oLCZ4fOBkAO6wqNMORrgcv1Y5YGO6DH8pns74c3B0cGb7cMBhs8rlYX3F+69
#|lPjpF6G+iH6ZMeY3VzHflwF2RhinU4s4CclWzVOkKcPIYEclsViaZHGSbLV326bMu/tq52Rn9kLD
#|SVk+vlG1gJ5Wm/HWk8OfQ8IwW0++lTVKO+gmK1AG66Hw0ETYcsBMeDP0N5U1Ufilh+0pT7g71b7t
#|0b1kEnL4UfvbDqtoBzzgOjrqEBK2Ou5eQa//zLe6LqMX87UcbLF/xw/+aroF6OydjbD0eQmOf7Qz
#|fPliJGaTqA/tXlGeeTcdjvBwX/OB0dvTQ/j6dxj4cr6rl//6V14alV9Dy0vOKPlX4+pm91W/QpgU
#|ade8d26636Cwq0m7j/tLve1yKf3c/Qx16Zsl0LZzzN6Usy2OUNhSD+z9V6Z+V1V9cTHfP2JkK91i
#|W7+raoiUe1QM6DoBurwPdwteht96+TERqZYs0amwJpVScUsSzyR2Po4xpSHLTbkGAyoswZgQhqU3
#|MVOJ515R6GDAaDPhv7DjNBOEaf+NEutGGUOMZBIMYRou3GLhkKQ4haFeU5N64RRZkgT2WN87MfJG
#|c2RhTs0loTr2D6OIZ/lJg3Di+/GUzPyix/xpy6Pjo70lTksbNvRBxApJ1XVik+f5Le0vqgW9MAar
#|0K9EyTePaTY+x+wo51YBenTeMd1MYQev4OXFxZkqfld34EEHaOecap1Xk7zZX3Yvatrn1QrXsJ7o
#|uuQ21oI3rC5fnx6/PRnNb2vt9G93mcC+b49eHb892m0x3fc4njQ6vLV3UuZZ2+ns/HRv+83lb//e
#|O7rc/nX74DDQBgj3P3rHPaVxeQAA
#@@ FILE tests/fixtures/local/flow.xml.gz b e9523116cb14db59
#|H4sIAAAAAAAA/+1d60/kOLb/vtL+DxG6H9cQ24mdjGhWNNCzSHTBAj0j3dtXyE/IdFVSk6RomNH+
#|73uceqWgigqdgqFnInU3jWMfP87x75zjx/HuP+8Gfe/W5EWSpe+28La/5ZlUZTpJr99tfbr8gKIt
#|ryhFqkU/S827rTTb+ufe3/+2a/vZ14MsLfOs3zf5rAyqkQq2IKPn7Q7E3WUyMPlhntya9PImN0If
#|ZKO03MP+7s7qr9PCR5BeLilclV3xsSqbm+ukKPPEFDvjhKHIxcCUJnctN3flND3PsvLHPBsNq18h
#|IdF7sc8jFlEf+TgmCPu+jwLCAmQlC00E/2Asd3cg46RICpT3esmHxPsAQ7O7U/0++TbMiqSEUfHu
#|3m35bojvxz93phlUNhhAP2a/u9G1Sd9AO9Uoz2F07/c+9d6ffuodHh3u7iz7/KDk6aiUMBL6LOsn
#|8PXi8vxo/+PVz/866l3t/7R/fLL//uRoTuhB7gktbawY9UvXnw+Q6ehumOTC9WPP9wqjdndWZ1ik
#|8F6oL2e5KYpRbk7lL0aVjlfFTdbXe25k/Rmpp3KupnkoSnGR/GZqVL0f3y8l+jjrhGw/u3Z9uBhZ
#|m9zNGDHMMwUFs3ySMJENHFtfW1uTDR4SHwmlmdaKK4tVTTag0GRaGBDPwRB+puWx3uOGq4iEHNmA
#|RIgqy5DAfoQUUMQgXjjGYndnadEZ4UrMPphS3bjWL4jdA8HDAScT2eOsLn2Qryjv+9NZskwgXUpf
#|FMVell9vi6FQN2Y7TWyyPRufYnuMErnerrVmXGhGQ4KI9efNg5TratY9oLq7c12bjFU+kZeJFarc
#|c9/RtCqUinx3Z/atln8yaHt4m/BtfzaI86bsPGiLA5rZdCovRfGlmCDMw9T5oEF79agPqHdm8iTT
#|01nxKH3ODpOKfvJbNUUm3+ik0JJPs2L3ienrSSIeZ68n1YYXsLhM0hNza/p7P++f91w362mzrP2s
#|KC4zQG4BYGlFvwBmLaQ97KXRF6Uozd75p17vuPfjrJfT9CWjclECGJjr+73L449H51eH58c/HfXq
#|wzPLMCts7owauSHoZdrs7Z+c7O4sJs1y5qP0cDQGm55Is2IPmPwobZ7blPn9XOfUfp0PHoBEZu1H
#|o25EmhSDvbOj3v7J8f8eXX04Of35w7GDy0d56tLzfvxxyiffGyRpUUnQ4pe5NOTZ0OTlfV1ux9MZ
#|5o5XZl41kR5MaSfboj8ye//z+3gCivLmP58dhhefCwH/XmlAuKtCDIZABHmP0q406MQkVeW2Km5h
#|YlTE5tPiUaNWN9PhkZMtgJcpJ1c19tBARuONQaFFlR+zW+MdGteBis3eYZKDjsjyhzU/nypMcwvK
#|r1zbl3Pj0lt14yS79vpuQnpfb0zqOe55aVZ61ungVfUenZ+fnm+yWsg0SAoHi542aWLa1yxGZXbp
#|qAJ3jD43/YpJxU0y3IPubU+690SuJpSsSPqgyFvTmXd/e9r9tRSrTi8YBE9YCELIuvUYxtgiowKD
#|baSkdUbPWgvB+IQbiSOwLCRFlCuDIhFgFItYqojxUFveyEI4G5XO8pGiMOdGZflDXq+yFOIoeEFL
#|YUmrOouhsxg6i+G5FsNwVCItUV5NovkPoU2+CtRjPzZh4Nd9GMEpQczGOBRhEBGqW2kbaE95P3zo
#|kszqP8uK8jo3F/8+aVXLYs8LJ1kOjp6s+rh3cXR+eXX8Y+/0/KhV7RfT+rxLqM8bg5h3BjZZG3vE
#|YeKmaC2Oj1ZyiAqT3yZq5ejEvghpTE1NMCRlBIU8DrQf0Di0wQZZpqCz4HujsVG1qY46yBiIDRMF
#|TdU3y2jOxq6ytjc4OBIskfwe2SwfiHJVpdUq3QYrBYxNCzB9DLJOZ1QdLlZVXuajdrbwYt2jFDrq
#|4H5StzQ34jbJVqLYBzAGPbBaPk3LgY8B5TbJg3mTVNYfDdJvaNNBVXCjjRpqx6Av5v4hZ1oQHQ+5
#|ytJSJKlbzC1+7W+Ouuj3s69oMOqXCbiNc6heKVoTI2NjY/brKAOrHiVg7YP5l4B990pCPal4DB8N
#|qt98xw2ASJkMTDZaiSKVVZmlLaeO2w5wNg/KUjRz1F6ql+MBnUC9cs4AKpLfVlaIncu1sUEFKw1J
#|N7/X1dmuUj3xj0BrV74qcj6q87mSlZxsPLBPuLuVvbtRh9jnMVOa1ayKWNAYGSaYwThkVAcNHGLN
#|JbZGWxSHxCAq4hhFGLxiFYc+Z7FiOjKNHOIfTWqcLzHdu3jKH2b+dNOGUPKC7vDjNv21vOGxB/Qn
#|d4cPjy/c3tth5w+/9Ar6xRO47L9vhcrvHfA/WQFuRb/yAD88afVfmruyVR2f0gQMA28KNi9ojVxP
#|cA1Zi9SoKLMBKqvWf7tpCeKTA2SZHPTiCzpGA7CZli0lPCLyLD0YM1B8cz1IfauQkFzGLNRYYd5A
#|DwahBoUJepAoi4GCsuCWGIIIF5HyBdCy0ea2jhlmEwUY4pdUgN3O8Z9Y8XXrwN/5zvFrbhj3AK26
#|neJup/gvsVNsVGTEwlkyGyNBtY60FirEuIFBEOMwDnxfgUGAGaISTAMJFgGCZBkbyiJuN+8Y4yCK
#|pp5x8JJHyjrPuPOMOwuh84w7z/jP7BkLC7oK11eIsSJIxYSEkjMjjGigCCMTxJoSgzgH9UfDQKGI
#|iAApRbSlsc+kxJs/MjX3kCM/6k5MTUSh85Q7T/mN6sHv8MRUZQQn6g86LtWdk3okDt05qeVEu3NS
#|jyvvzkk1aFN3Tqo7J9Wdk9p4L7tzUn/4OamnqTRfqH7GsnKEI4FVfZ+ZEIpwyFRsY6Eiqxt404QG
#|2ihLUewThSgOGIpJFCA/VoFiPlcybnYB6ahyMQy4I0YMINtAPNq/eLi0PD10FZKXXFpe3rDOqe6c
#|6s6pfq5T/XOWf4Hh2cxe62QuLvPsZhA+vC9vsrSV4hD59agyr9bt5k7bsz8t4J1NaLbdFF8k22jb
#|vlB5MiyLz7kZZLfmSo+G/QQ8RFNsD++9rTY7/FutejPthXdo+gno3tWrKV6reo6v0yw33sXl4XHv
#|5Qyn01EJxszCMYL9sswTCQqj1TECcTcn5J2Y9Hq1iJOQbaIPHwHKqsWXBu1+cnM+/c3kmQsJVI6K
#|1oZPlifXkNzfqOUTcMWl5PUNdcssMpq70+MhjtzRuPUn7JTEyg99JIgfIyoMWD5hqJBhUtHY10T7
#|cvP7CATaPL16Hb/kUbtuI6GzeTqbp9tIeM2NhE9nh/uX3YXrx+LQbSQsJ9ptJDyuvNtIaNCmbiOh
#|20joNhI23stuI+Gvt5EgrLImxEHNOlFUcxRaSQgJhbGBXHSnq0FqdK8sDmcRSV90jb+7V/YndnIv
#|Lk/PzrpT4929su5eWfMKu3tlf557ZX0h60A6XgK3LAB1PdfZOBQxYoJiFirCRNQkPrmJNGE6kigU
#|vgu2okMUKRshFoYU6mS+COJ1S+C/Hafa3DksnPxvqSFACA62WRzEYeBzn3BMJ2fp2TYNQkwiEvpR
#|yPCChQBWoHdjkuub8t1WEFQX0b4murxZaU3U5apK8Zy0vduy4IBVRuXWHibDO1AI7mNNzh4Uny4D
#|OJfQbXem5qtXJRUwf3JvbK8WXmK98sbkxhPub/pgmxC0W41vy5hIVaiJX4+YE1CpwO7GFkZKSkWb
#|XAzkPIqlCDiwjmhEdciRiEmICCNY+yGO8PoTHM2YiMksbOzjMAF1ZmFWZxYJll6Y2DCzzt1GqWPW
#|fKv0ufzAwsdcLUwqFgQokn7kgxHMfRM34AezlCsaMxT5gQ+TihskKZFIBzCpVEAZs2vvpzTjRzAL
#|W4Qpe4IdtPo6ZUe4POLvhtnxAeZJ5U0WUG95A26yN8yTgcjvPbVs7aYBdyLFaRzW3ZSAEMRUoEWo
#|bRgr24A7UimMObHIaoIRjcIYRUZgFMgotJyEJDRrr9E24w6fbfQh/BR38AJ3+PJNwSbciZpz50Ck
#|3qgwnsqhrc4Z1p4S/b4HTJt+6idFCRr8piyH3kwjOcj7aryvYK47a1GN34fx5L23f3ZckfiGOceA
#|FfUw2r6RKAhwJANfWhXSBlwNfUxiHQhElZSIEu4UWQyQSCWoG66AysYwMJxeBBuj3Cq2kniBrf5r
#|TDq7OOkezjjv73/7+9+OUpfBm15MnD4QU+OxO6ySu054CoD0S/U7uL956YFbarwnOWxHafqIxbHV
#|EdX1g4ohpyhQlGquIiapbMBiLFQspGKI+xRsFaUoElpoRAwRzARcBNZfx+IFRjJ/erUdj3k1exNm
#|Z6EXS/vk81hoXr/TH2iDEWM+A4kWATVNjiBArhjTiCAbCIVorEBsaWRQyDX2BVh0OF4b5GcBcti8
#|Swu3FJt0KeAqZrjOJj/0OdIRUYLyMFJhk7hFJjIklpoiHoMpQ0NskKAKI8Dn0Lexj5kLA9i8S4TO
#|lpAwJU/1CcAoBUdtYcll0i/B2MKtU0B5FPvW+JxyIaMmt05pJARTzKKAa+iXiRiCXhKQYiCDfU6i
#|iDU5LVKDAGnce0xJWtZXwarZNMYfPJlbD9BoNU4V2ShX5rjpCZlZ9gcEqoeyjps+kLVY5gEpt4e7
#|d3Z+enB0ceH8u1rqLKee+9rHTcVwscwyUs/rxJKCy4hWDf/wqdc7Olkos9ihvO7UFSPlYNUtAC1z
#|Hgfizp2p/PfIjIy7Uz99LetR+tIS07euJq9hLf00K2hXvvK15Ett1U7o96IvAPlna2eHp1e908ur
#|k9P9w6v3+yf7vYMjt5T3OON8RrsFU0cYDPTZubidpbW4mZOPV+anFR2cfjw7BwlaqKSebwoIjyBg
#|JSiATpJS10HBMMKcC8UjHFAsgyb4TajWwgYGRUxxMDswB1CwMRCMtYoipWm01n9+PVBo9KbZ2wSF
#|Ro+t/JGgUOtOhwvfMS74EhvwAuuC4SxNRrU0MYloEJEmISoojxQTEdIxeJo0MAbF0ghkKJWccRly
#|8oaMhUZhOd4mLjQywztjYSOgMA1R9ddDBbdDbu3CwqBkAXiwHGQF21D6RDzeIX+Vydts8/5tTt5O
#|qXdK/VWUOriUkZYLp7FDLBBlItRhZHkUNtksY9TqIFQKGe4Tt4QFZCjRKMKC+ybi4Ac0ui/yasb+
#|+sn1NnGh0eLFd4ULs/3kDhfeEi7AHDGE0/p+H+hLFPiU0YAbGcas0SKAVVFMJQokA1DxuUbStxgp
#|ogEtfM651B0ubMZeWL+P0Bn7nbHfEhW4FIbImliQiEQga4zSmAlQTU1QIQwin1ILjn+oLaLYB0PB
#|D0PEAi1YGMOkI2/IWmj0ZsXbRIVGqxfflbXwpoHhr2wtGGNJ3SwNCXcHfGQQiiDmJm7yvlmAleYE
#|BJSSCCMqSYAi4kskLI1AiUWRrxvF23kta6FB6Pq3iQuNwiN1uNDhwga8iJjh+pZBaLBGOgpjLhnW
#|lDTBBUEZlrGxKAho6I4xgb1gmTuhpmXsE0HDsFFU61fChSaT643iQpNd0O8KF7JxAJiiCnDWocPb
#|QgdnWVtWP+MdBe5wdmwCI0UoxMOtg6VT3CpqKGMSsRhki2oiUEyURAEXEXjsYWj8N7TG0Ogl2LeJ
#|Do0coe8KHTqr4Y/GBXdEum/yi3GQkAfGQxDBDK6vaXEN8iGlzzQXQviyyXmDWGAWS+UjLDB4FtJE
#|SGohQB8bzLRRQeiuAzUIZXVw8dM4SsqFKX/Ol0R3W3JL9xlXQJdf6FXF7fayil/oJu80nonJk9n1
#|12kEl2KT13tNddJaT2IfTH+bi+TKEDjV9XuvGoa1VwXTbHJdv9W1vfqN/zbXHCd04Lu7Ut9Hk0F6
#|mZeCJpWJCt9QsWagkvQGOF4uhrPZRP25uU6Kst310NXBdbz55dtxpm33+T+baPhy5nwLJZkDILYK
#|qjQhtORtpNoAiNs82x7nbDcAoJvM8jemnkXmMhlsikxRisFwA7QAR9c8njV+harV8P3kinoXBpSq
#|KFdH7flHuwCgqeqPtPH+VUVa806SdOXUaB1c5t8unIx3MH1Ya1U97SKnHhVKDBvU8rl1tFkXPe2j
#|yL881t7PodQDHe7UD1hMraQ7TwazEFIvyr+PmV4pIh+Pe8cf909a1TKJH7dW7j+3i1c8FfzLXCT9
#|Ktjyuki77eP+gAk2KpN+gTb4uFxlDS+1fdcZxY2iJ641it2yfBgFGJxkpcAotrG7hxuiILBC+twG
#|sWn2Tlxlmy4J9/iitvC4vr+qCfw80w4GDd1UI4bgb3Jr2gXX7Oy6V7Xrfof/brmools/eFtjydz6
#|h0tz2V3aaQ5cHSdV8fQKSPy/isLvszyZy3OVjgayyjqjl6Tl1n/+8SDzryORlkl5f1WVMnptgWEO
#|E+PKwASrZ9XZCMT5ce5xWwC6TdMGVRFzmpN2gQrruYtKSS8hW8XwbpLz1zK/StaPwwBw+6ZJxnsj
#|GhEEudEjVVaD1aSdgyIfNhmnKV0FJkETumOj2EmQS2hQYHiTNWux0NotElU9xM8tQBq1HSS5qTQ0
#|61sGWfvNx84FtcobNQHsCnDBs2aZq6iZTjZEUTbmy7SQTfJnlNIG+ltdt1+SGXL+v9cOmJ2CGkeM
#|Ru6/YD8Wq605Z1VkaYHaBs3qnNy37+S+kktx8SUZvoojnVSvdqC5QfZyLkvns3/fPvtLuJyN6htH
#|TZ5FiZp6Di7Ty/W2GtGxteJVwYtb1dTCtW4SiX6ta21UpIzkGoXEhbiSIQcy4GkrbGhMNI4VWxuL
#|Zayj3h+cHcz2zM6y7FF07BfwsbVUw+1lNb+Qt+3qm3rXb8G5nj4L48377306P1klkb9A+39wNuE1
#|2KW/9n/Y2elnSvRvIOWHMKBkpwTFfvi+ra0ybtKhc99z78Bxwus94TY7JswbtT0ut5m40LqihVwv
#|q/3yRuFQfwGb7vO8QSgg23w72P5FtGsU6ANwILMCjYoKIJe9M/FtBBU4vi5uOijijdIFXzlVyVC0
#|inM/pwZy8HXJk0rfJFyfnrC6p6xrxa2z5a2dVWJS9TszOiI+V0wZTTAnMvalxKGKMOGhFSKgggIQ
#|C6sIYYHUEVWWxD7GAfzRKrYMcFqEsp1H4h4o+1kkpefs8lXNDX13C6TfT9qNiqvrMgOXsgY4KydV
#|OyUPRnuix8uZVYj+NmJTwfYgSVECqOvecFjd6JYB6auKxF2DitqNzqwiVwfqJ9aUT3Aftdudrypz
#|9JE05VdjUmQAYyrW5KPVPdxErY5pVWWT5yHgn6c6Sqdxs9vWW2S2fG7lDfr77dYewIpgsn6VifKI
#|IIAUn0ruSyaaBFdkfhTgSPiIhZi600XutoLgKAzjWEpLMW4W5Whv/zbPXm0npTosUK/xz7KXMnGd
#|X2ozxQyk0dpo5AawOybz3W2nbPCYTKMHYNbrvjYbwRbLhbgrVskQaUXgR0yo9JuE/FWQPQ5imAHc
#|XdDGkUExxRwJZiVV3EZGkGfg12sfj6wBWXdAcryc+ZwDkhWMTUGtOyTZHZLs0L8h+s/Pt695LrF3
#|2mv36OeGFM1TVYDrnbll3mEGM+6pmihpo9BuBYCmnMXxni0QbY3fj3i3dfjD5wuR/iLuP1dYOwbL
#|SUzj3Z08y8ofZ+j8WD1O7urs5maY5e5piup9qEmi20MaGNAMZ3l2m0Bnqw/j2xUHM0qQ9F+uKYX7
#|FMQAAA==
#@@ FILE tests/fixtures/repo/nifi-acme-processors/pom.xml t 71d6f74a011a4230
#|<project>
#|  <parent><groupId>com.acme</groupId><artifactId>acme-parent</artifactId><version>1.0</version></parent>
#|  <artifactId>nifi-acme-processors</artifactId>
#|  <packaging>jar</packaging>
#|  <dependencies><dependency><artifactId>nifi-api</artifactId></dependency></dependencies>
#|</project>
#@@ FILE tests/fixtures/repo/nifi-acme-processors/src/main/java/com/acme/nifi/ValidateOrderJson.java t 0d4cd2b7f3021105
#|package com.acme.nifi;
#|
#|import org.apache.nifi.annotation.behavior.InputRequirement;
#|import org.apache.nifi.annotation.behavior.WritesAttribute;
#|import org.apache.nifi.annotation.documentation.CapabilityDescription;
#|import org.apache.nifi.annotation.documentation.Tags;
#|import org.apache.nifi.components.PropertyDescriptor;
#|import org.apache.nifi.processor.AbstractProcessor;
#|import org.apache.nifi.processor.Relationship;
#|
#|@Tags({"acme", "json", "validation"})
#|@InputRequirement(InputRequirement.Requirement.INPUT_REQUIRED)
#|@CapabilityDescription("Validates vendor order JSON against the ACME validator service "
#|        + "and routes to valid or invalid.")
#|@WritesAttribute(attribute = "validation.status", description = "VALID or INVALID")
#|public class ValidateOrderJson extends AbstractProcessor {
#|
#|    static final String ORDER_ID_ATTR = "order.id";
#|    private static final String AUDIT_SQL = "INSERT INTO validation_log (order_id, status) VALUES (?, ?)";
#|    private static final String FALLBACK_URL = "https://validator-backup.acme.com/api/v1/check";
#|    private static final String DEFAULT_PASSWORD = "Sup3rS3cret!";
#|
#|    public static final PropertyDescriptor VALIDATION_URL = new PropertyDescriptor.Builder()
#|            .name("Validation URL")
#|            .description("Endpoint of the validator service")
#|            .defaultValue("https://validator.acme.com/api/v1/check")
#|            .required(true)
#|            .build();
#|
#|    public static final PropertyDescriptor API_TOKEN = new PropertyDescriptor.Builder()
#|            .name("Api Token")
#|            .displayName("API Token")
#|            .description("Token for the validator")
#|            .sensitive(true)
#|            .build();
#|
#|    public static final Relationship REL_VALID = new Relationship.Builder()
#|            .name("valid").description("Order passed validation").build();
#|    public static final Relationship REL_INVALID = new Relationship.Builder()
#|            .name("invalid").description("Order failed validation").build();
#|    public static final Relationship REL_FAILURE = new Relationship.Builder()
#|            .name("failure").description("Validator could not be reached").build();
#|
#|    @Override
#|    public void onTrigger(ProcessContext context, ProcessSession session) {
#|        FlowFile flowFile = session.get();
#|        String orderId = flowFile.getAttribute(ORDER_ID_ATTR);
#|        String vendor = flowFile.getAttribute("vendor");
#|        String bucket = "acme-orders-raw";
#|        flowFile = session.putAttribute(flowFile, "validation.status", "VALID");
#|        flowFile = session.putAttribute(flowFile, "validated.by", "acme");
#|        String archive = "/data/archive/orders";
#|        session.transfer(flowFile, REL_VALID);
#|    }
#|
#|    private void audit(Connection c) {
#|        String q = "SELECT status FROM order_status s "
#|                + "JOIN vendors v ON v.id = s.vendor_id WHERE s.order_id = ?";
#|    }
#|}
#@@ FILE tests/fixtures/repo/nifi-acme-processors/src/main/resources/META-INF/services/org.apache.nifi.processor.Processor t c170a921d2ac0a47
#|com.acme.nifi.ValidateOrderJson
#@@ FILE tests/fixtures/repo/scripts/enrich.py t db3737e67fb96bcd
#|import sys
#|import pymysql
#|
#|DB_HOST = "10.20.30.40"
#|password = "hunter2"
#|conn = pymysql.connect(host=DB_HOST, user="etl", password=password, database="meta")
#|
#|
#|def enrich(order_id):
#|    cur = conn.cursor()
#|    cur.execute("SELECT name, region FROM customers WHERE id = %s", (order_id,))
#|    return cur.fetchone()
#|
#|
#|def main():
#|    print(enrich(sys.argv[1]))
#@@ FILE tests/fixtures/repo/scripts/load_audit.groovy t d2e8136fc0abb9db
#|def sql = "UPDATE file_audit SET status = 'LOADED' WHERE file_name = ?"
#|def target = "s3://acme-orders-curated/audit/"
#@@ FILE tests/fixtures/stg_sales.parquet b 3b77654b35086125
#|UEFSMRUEFSAVJEwVBBUAEgAAEDwBAAAAAAAAAAIAAAAAAAAAFQAVEhUWLBUEFRAVBhUGHBgIAgAA
#|AAAAAAAYCAEAAAAAAAAAFgAoCAIAAAAAAAAAGAgBAAAAAAAAABERAAAACSACAAAABAEBAwIVBBUU
#|FRhMFQQVABIAAAokAQAAAGEBAAAAYhUAFRIVFiwVBBUQFQYVBhw2ACgBYhgBYRERAAAACSACAAAA
#|BAEBAwIVBBUKFQ5MFQIVABIAAAUQAAAAAJYVABUSFRYsFQQVEBUGFQYcGAUAAAAAlhgFAAAAAJYW
#|AigFAAAAAJYYBQAAAACWEREAAAAJIAIAAAADAQECABUEFRwVIEwVAhUAEgAADjQKAAAAMjAyNi0w
#|OS0yNhUAFRIVFiwVBBUQFQYVBhw2ACgKMjAyNi0wOS0yNhgKMjAyNi0wOS0yNhERAAAACSACAAAA
#|BAEBBAAVBBUUFRhMFQQVABIAAAokAQAAAHgBAAAAeRUAFRIVFiwVBBUQFQYVBhw2ACgBeRgBeBER
#|AAAACSACAAAABAEBAwIVBBlsNQAYBnNjaGVtYRUKABUEJQIYCE9SREVSX05PABUMJQIYCUNVU1Rf
#|TkFNRSUATBwAAAAVDhUKFQIYBkFNT1VOVCUKFQQVFCxcFQQVFAAAABUMJQIYCE9SREVSX0RUJQBM
#|HAAAABUMJQIYB0xPQURfVFMlAEwcAAAAFgQZHBlcJgAcFQQZNQAGEBkYCE9SREVSX05PFQIWBBbM
#|ARbUASZIJggcGAgCAAAAAAAAABgIAQAAAAAAAAAWACgIAgAAAAAAAAAYCAEAAAAAAAAAEREAGSwV
#|BBUAFQIAFQAVEBUCADwpBhkmAAQAAAAmABwVDBk1AAYQGRgJQ1VTVF9OQU1FFQIWBBZ8FoQBJpAC
#|JtwBHDYAKAFiGAFhEREAGSwVBBUAFQIAFQAVEBUCADwWBBkGGSYABAAAACYAHBUOGTUABhAZGAZB
#|TU9VTlQVAhYEFp4BFqYBJooDJuACHBgFAAAAAJYYBQAAAACWFgIoBQAAAACWGAUAAAAAlhERABks
#|FQQVABUCABUAFRAVAgA8KQYZJgICAAAAJgAcFQwZNQAGEBkYCE9SREVSX0RUFQIWBBaoARawASbC
#|BCaGBBw2ACgKMjAyNi0wOS0yNhgKMjAyNi0wOS0yNhERABksFQQVABUCABUAFRAVAgA8FigZBhkm
#|AAQAAAAmABwVDBk1AAYQGRgHTE9BRF9UUxUCFgQWfBaEASbqBSa2BRw2ACgBeRgBeBERABksFQQV
#|ABUCABUAFRAVAgA8FgQZBhkmAAQAAAAWigYWBCYIFrIGABkcGAxBUlJPVzpzY2hlbWEYzAMvLy8v
#|LzFBQkFBQVFBQUFBQUFBS0FBd0FCZ0FGQUFnQUNnQUFBQUFCQkFBTUFBQUFDQUFJQUFBQUJBQUlB
#|QUFBQkFBQUFBVUFBQURnQUFBQW5BQUFBR0FBQUFBd0FBQUFCQUFBQUVULy8vOEFBQUVGRUFBQUFC
#|Z0FBQUFFQUFBQUFBQUFBQWNBQUFCTVQwRkVYMVJUQUhELy8vOXMvLy8vQUFBQkJSQUFBQUFjQUFB
#|QUJBQUFBQUFBQUFBSUFBQUFUMUpFUlZKZlJGUUFBQUFBblAvLy81ai8vLzhBQUFFSEVBQUFBQ0FB
#|QUFBRUFBQUFBQUFBQUFZQUFBQkJUVTlWVGxRQUFBZ0FEQUFFQUFnQUNBQUFBQW9BQUFBQ0FBQUEw
#|UC8vL3dBQUFRVVFBQUFBSUFBQUFBUUFBQUFBQUFBQUNRQUFBRU5WVTFSZlRrRk5SUUFBQUFRQUJB
#|QUVBQUFBRUFBVUFBZ0FCZ0FIQUF3QUFBQVFBQkFBQUFBQUFBRUNFQUFBQUNRQUFBQUVBQUFBQUFB
#|QUFBZ0FBQUJQVWtSRlVsOU9Ud0FBQUFBSUFBd0FDQUFIQUFnQUFBQUFBQUFCUUFBQUFBQUFBQUE9
#|ABggcGFycXVldC1jcHAtYXJyb3cgdmVyc2lvbiAyNS4wLjEZXBwAABwAABwAABwAABwAAABiBAAA
#|UEFSMQ==
#@@ FILE tests/fixtures_builder.py tc bc8e25ac276960fa
#|"""Builds a realistic multi-group test environment in a temp dir: flow.json.gz, custom NAR, SQLite metadata DB, config."""
#|import gzip
#|import io
#|import json
#|import sqlite3
#|import zipfile
#|from pathlib import Path
#|
#|FIXTURES = Path(__file__).parent / "fixtures"
#|SECRET_VALUES = ["abc123secret", "hunter2", "Sup3rS3cret!", "plainpass99", "varsecret77"]
#|
#|ROOT, PG = "root-0000-0000", "pg-vendor-0000"
#|DBCP_INSTANCE = "dbcp-instance-1111"
#|
#|
#|def proc(pid, name, ptype, props=None, state="RUNNING", auto=(), bundle=None, group=ROOT, **kw):
#|    p = {"identifier": pid, "instanceIdentifier": f"inst-{pid}", "name": name, "type": ptype,
#|         "bundle": bundle or {"group": "org.apache.nifi", "artifact": "nifi-standard-nar", "version": "1.27.0"},
#|         "properties": props or {}, "scheduledState": state, "schedulingStrategy": kw.get("strategy", "TIMER_DRIVEN"),
#|         "schedulingPeriod": kw.get("period", "0 sec"), "concurrentlySchedulableTaskCount": kw.get("tasks", 1),
#|         "autoTerminatedRelationships": list(auto), "executionNode": kw.get("node", "ALL"), "comments": kw.get("comments", ""),
#|         "componentType": "PROCESSOR", "groupIdentifier": group}
#|    return p
#|
#|
#|def conn(cid, src, src_type, dst, dst_type, rels, group=ROOT, src_group=None, dst_group=None):
#|    return {"identifier": cid, "instanceIdentifier": f"inst-{cid}", "name": "",
#|            "source": {"id": src, "type": src_type, "groupId": src_group or group, "name": src},
#|            "destination": {"id": dst, "type": dst_type, "groupId": dst_group or group, "name": dst},
#|            "selectedRelationships": rels, "backPressureObjectThreshold": 10000, "backPressureDataSizeThreshold": "1 GB",
#|            "flowFileExpiration": "0 sec", "prioritizers": [], "loadBalanceStrategy": "DO_NOT_LOAD_BALANCE"}
#|
#|
#|def service(sid, name, stype, props, state="ENABLED", group=ROOT):
#|    return {"identifier": sid, "instanceIdentifier": f"instance-{sid}" if sid != "dbcp-1111" else DBCP_INSTANCE, "name": name, "type": stype,
#|            "bundle": {"group": "org.apache.nifi", "artifact": "nifi-dbcp-service-nar", "version": "1.27.0"},
#|            "properties": props, "scheduledState": state, "componentType": "CONTROLLER_SERVICE", "groupIdentifier": group}
#|
#|
#|ACME = {"group": "com.acme", "artifact": "acme-nifi-nar", "version": "1.0.0"}
#|JSON_SCHEMA = json.dumps({"type": "record", "name": "Audit", "fields": [
#|    {"name": "order_id", "type": "string"}, {"name": "vendor", "type": "string"},
#|    {"name": "status", "type": "string"}, {"name": "extra_field", "type": "string"}]})
#|
#|
#|def nested_flow(bucket="#{s3.bucket}"):
#|    vendor = {
#|        "identifier": PG, "instanceIdentifier": "inst-pg", "name": "Vendor JSON Ingestion", "comments": "Receives vendor orders as JSON",
#|        "parameterContextName": "vendor-params", "variables": {},
#|        "versionedFlowCoordinates": {"registryUrl": "http://registry:18080", "bucketId": "b1", "flowId": "f1", "version": 3},
#|        "processors": [
#|            proc("p-extract", "Extract fields", "org.apache.nifi.processors.standard.EvaluateJsonPath",
#|                 {"Destination": "flowfile-attribute", "order.id": "$.id", "vendor": "$.vendor"}, auto=["unmatched", "failure"], group=PG),
#|            proc("p-validate", "Validate order", "com.acme.nifi.ValidateOrderJson",
#|                 {"Validation URL": "https://validator.acme.com/api/v1/check", "Api Token": "abc123secret"}, bundle=ACME, group=PG),
#|            proc("p-s3", "Store raw JSON", "org.apache.nifi.processors.aws.s3.PutS3Object",
#|                 {"Bucket": bucket, "Object Key": "${vendor}/${filename}", "Region": "us-east-1", "Secret Access Key": "#{aws.secret}"},
#|                 auto=["failure"], group=PG,
#|                 bundle={"group": "org.apache.nifi", "artifact": "nifi-aws-nar", "version": "1.27.0"}),
#|            proc("p-rejects", "Write rejects", "org.apache.nifi.processors.standard.PutFile",
#|                 {"Directory": "#{reject.dir}/rejects", "Conflict Resolution Strategy": "replace"}, auto=["success", "failure"], group=PG),
#|        ],
#|        "inputPorts": [{"identifier": "in-port", "instanceIdentifier": "inst-in", "name": "orders in", "scheduledState": "RUNNING",
#|                        "componentType": "INPUT_PORT", "groupIdentifier": PG}],
#|        "outputPorts": [{"identifier": "out-port", "instanceIdentifier": "inst-out", "name": "stored", "scheduledState": "RUNNING",
#|                         "componentType": "OUTPUT_PORT", "groupIdentifier": PG}],
#|        "connections": [
#|            conn("c1", "in-port", "INPUT_PORT", "p-extract", "PROCESSOR", [], group=PG),
#|            conn("c2", "p-extract", "PROCESSOR", "p-validate", "PROCESSOR", ["matched"], group=PG),
#|            conn("c3", "p-validate", "PROCESSOR", "p-s3", "PROCESSOR", ["valid"], group=PG),
#|            conn("c4", "p-validate", "PROCESSOR", "p-rejects", "PROCESSOR", ["invalid"], group=PG),
#|            conn("c5", "p-s3", "PROCESSOR", "out-port", "OUTPUT_PORT", ["success"], group=PG),
#|        ],
#|        "controllerServices": [], "labels": [{"label": "Validation is done by the ACME custom processor", "componentType": "LABEL"}],
#|        "funnels": [], "processGroups": [], "remoteProcessGroups": [],
#|    }
#|    root = {
#|        "identifier": ROOT, "instanceIdentifier": "inst-root", "name": "NiFi Flow", "comments": "",
#|        "variables": {"base.dir": "/data/landing", "etl.password": "varsecret77"},
#|        "processors": [
#|            proc("p-listen", "Receive orders API", "org.apache.nifi.processors.standard.ListenHTTP",
#|                 {"Listening Port": "8081", "Base Path": "orders"}),
#|            proc("p-audit", "Write audit row", "org.apache.nifi.processors.standard.PutDatabaseRecord",
#|                 {"put-db-record-record-reader": "instance-reader-1", "put-db-record-dcbp-service": DBCP_INSTANCE,
#|                  "put-db-record-statement-type": "INSERT", "put-db-record-table-name": "file_audit",
#|                  "put-db-record-unmatched-field-behavior": "Fail on Unmatched Fields"}, auto=["success", "failure", "retry"]),
#|            proc("p-archive", "Archive order", "org.apache.nifi.processors.standard.PutDatabaseRecord",
#|                 {"put-db-record-record-reader": "instance-reader-1", "put-db-record-dcbp-service": DBCP_INSTANCE,
#|                  "put-db-record-statement-type": "INSERT", "put-db-record-table-name": "order_archive"}, auto=["success", "failure", "retry"]),
#|            proc("p-lookup", "Lookup customer", "org.apache.nifi.processors.standard.ExecuteSQL",
#|                 {"Database Connection Pooling Service": DBCP_INSTANCE,
#|                  "SQL select query": "SELECT c.id, c.name FROM customers c JOIN orders o ON o.cust_id = c.id WHERE o.id = '${order.id}'"},
#|                 auto=["failure"]),
#|            proc("p-enrich", "Enrich via python", "org.apache.nifi.processors.standard.ExecuteStreamCommand",
#|                 {"Command Path": "python", "Command Arguments": "${base.dir}/scripts/enrich.py ${order.id}"}, auto=["original", "nonzero status"]),
#|            proc("p-gen", "Nightly trigger", "org.apache.nifi.processors.standard.GenerateFlowFile", {}, state="DISABLED",
#|                 strategy="CRON_DRIVEN", period="0 0 2 * * ?"),
#|        ],
#|        "inputPorts": [], "outputPorts": [], "funnels": [], "remoteProcessGroups": [], "labels": [],
#|        "connections": [
#|            conn("r1", "p-listen", "PROCESSOR", "in-port", "INPUT_PORT", ["success"], dst_group=PG),
#|            conn("r2", "out-port", "OUTPUT_PORT", "p-audit", "PROCESSOR", [], src_group=PG),
#|            conn("r3", "out-port", "OUTPUT_PORT", "p-lookup", "PROCESSOR", [], src_group=PG),
#|            conn("r4", "p-lookup", "PROCESSOR", "p-enrich", "PROCESSOR", ["success"]),
#|            conn("r5", "p-enrich", "PROCESSOR", "p-archive", "PROCESSOR", ["output stream"]),
#|            conn("r6", "p-gen", "PROCESSOR", "p-lookup", "PROCESSOR", ["success"]),
#|        ],
#|        "controllerServices": [
#|            service("dbcp-1111", "MetaDB", "org.apache.nifi.dbcp.DBCPConnectionPool", {
#|                "Database Connection URL": "jdbc:mariadb://dbhost.acme.com:3306/meta", "Database Driver Class Name": "org.mariadb.jdbc.Driver",
#|                "Database User": "nifi_rw", "Password": "enc{0123456789abcdef}"}),
#|            service("reader-1", "AuditJsonReader", "org.apache.nifi.json.JsonTreeReader", {
#|                "schema-access-strategy": "schema-text-property", "schema-text": JSON_SCHEMA}),
#|            service("writer-unused", "UnusedWriter", "org.apache.nifi.json.JsonRecordSetWriter", {}, state="DISABLED"),
#|        ],
#|        "processGroups": [vendor],
#|    }
#|    return {
#|        "encodingVersion": {"majorVersion": 2, "minorVersion": 0},
#|        "parameterContexts": [{
#|            "name": "vendor-params", "inheritedParameterContexts": ["shared-params"],
#|            "parameters": [{"name": "s3.bucket", "value": "acme-orders-raw", "sensitive": False},
#|                           {"name": "aws.secret", "value": "enc{ffff}", "sensitive": True},
#|                           {"name": "db.password", "value": "plainpass99", "sensitive": False}]},
#|            {"name": "shared-params", "parameters": [{"name": "reject.dir", "value": "/data/shared", "sensitive": False}]}],
#|        "controllerServices": [], "reportingTasks": [], "rootGroup": root,
#|    }
#|
#|
#|NESTED_XML = """<?xml version="1.0" encoding="UTF-8"?>
#|<flowController encoding-version="1.4">
#|  <parameterContexts>
#|    <parameterContext><id>ctx-1</id><name>file-params</name>
#|      <parameter><name>landing</name><value>/data/in</value><sensitive>false</sensitive></parameter>
#|    </parameterContext>
#|  </parameterContexts>
#|  <rootGroup>
#|    <id>r</id><name>NiFi Flow</name>
#|    <processor><id>x-list</id><name>List landing</name><class>org.apache.nifi.processors.standard.ListFile</class>
#|      <bundle><group>org.apache.nifi</group><artifact>nifi-standard-nar</artifact><version>1.19.1</version></bundle>
#|      <maxConcurrentTasks>1</maxConcurrentTasks><schedulingPeriod>1 min</schedulingPeriod><scheduledState>RUNNING</scheduledState>
#|      <schedulingStrategy>TIMER_DRIVEN</schedulingStrategy>
#|      <property><name>Input Directory</name><value>/data/in/files</value></property>
#|      <property><name>File Filter</name></property>
#|    </processor>
#|    <processGroup><id>g1</id><name>File Ingestion</name><parameterContextId>ctx-1</parameterContextId>
#|      <inputPort><id>g1-in</id><name>files</name><scheduledState>RUNNING</scheduledState></inputPort>
#|      <processor><id>x-fetch</id><name>Fetch it</name><class>org.apache.nifi.processors.standard.FetchFile</class>
#|        <bundle><group>org.apache.nifi</group><artifact>nifi-standard-nar</artifact><version>1.19.1</version></bundle>
#|        <maxConcurrentTasks>2</maxConcurrentTasks><schedulingPeriod>0 sec</schedulingPeriod><scheduledState>STOPPED</scheduledState>
#|        <schedulingStrategy>TIMER_DRIVEN</schedulingStrategy>
#|        <property><name>File to Fetch</name><value>#{landing}/${filename}</value></property>
#|        <autoTerminatedRelationship>failure</autoTerminatedRelationship>
#|        <autoTerminatedRelationship>success</autoTerminatedRelationship>
#|      </processor>
#|      <connection><id>gc1</id><sourceId>g1-in</sourceId><sourceGroupId>g1</sourceGroupId><sourceType>INPUT_PORT</sourceType>
#|        <destinationId>x-fetch</destinationId><destinationGroupId>g1</destinationGroupId><destinationType>PROCESSOR</destinationType></connection>
#|      <variable name="region" value="eu"/>
#|    </processGroup>
#|    <connection><id>rc1</id><sourceId>x-list</sourceId><sourceGroupId>r</sourceGroupId><sourceType>PROCESSOR</sourceType>
#|      <destinationId>g1-in</destinationId><destinationGroupId>g1</destinationGroupId><destinationType>INPUT_PORT</destinationType>
#|      <relationship>success</relationship></connection>
#|  </rootGroup>
#|  <controllerServices/>
#|</flowController>
#|"""
#|
#|ACME_MANIFEST = """<extensionManifest><groupId>com.acme</groupId><artifactId>acme-nifi-nar</artifactId><version>1.0.0</version><extensions>
#|<extension><name>com.acme.nifi.ValidateOrderJson</name><type>PROCESSOR</type>
#|<description>Validates vendor order JSON (from NAR manifest).</description><tags><tag>acme</tag></tags>
#|<properties>
#| <property><name>Validation URL</name><displayName>Validation URL</displayName><description>Endpoint</description>
#|  <defaultValue>https://validator.acme.com/api/v1/check</defaultValue><required>true</required><sensitive>false</sensitive></property>
#| <property><name>Api Token</name><displayName>API Token</displayName><description>Token</description><required>false</required><sensitive>false</sensitive></property>
#|</properties>
#|<relationships><relationship><name>valid</name><description>ok</description><autoTerminated>false</autoTerminated></relationship>
#|<relationship><name>invalid</name><description>bad</description><autoTerminated>false</autoTerminated></relationship>
#|<relationship><name>failure</name><description>error</description><autoTerminated>false</autoTerminated></relationship></relationships>
#|<inputRequirement>INPUT_REQUIRED</inputRequirement>
#|</extension></extensions></extensionManifest>"""
#|
#|
#|STD_MANIFEST = """<extensionManifest><groupId>org.apache.nifi</groupId><artifactId>nifi-standard-nar</artifactId><version>1.27.0</version><extensions>
#|<extension><name>org.apache.nifi.processors.standard.GenerateFlowFile</name><type>PROCESSOR</type><description>Generates FlowFiles</description>
#| <properties><property><name>File Size</name><displayName>File Size</displayName><defaultValue>0B</defaultValue><required>true</required><sensitive>false</sensitive></property></properties>
#| <dynamicProperties><dynamicProperty><name>attribute</name><value>value</value><description>Adds an attribute</description></dynamicProperty></dynamicProperties>
#| <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship></relationships>
#| <writesAttributes><writesAttribute><name>mime.type</name></writesAttribute></writesAttributes><inputRequirement>INPUT_FORBIDDEN</inputRequirement></extension>
#|<extension><name>org.apache.nifi.processors.attributes.UpdateAttribute</name><type>PROCESSOR</type><description>Updates attributes</description>
#| <properties><property><name>Delete Attributes Expression</name><displayName>Delete Attributes Expression</displayName><required>false</required><sensitive>false</sensitive></property></properties>
#| <dynamicProperties><dynamicProperty><name>attribute</name><value>value</value><description>Sets an attribute</description></dynamicProperty></dynamicProperties>
#| <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship></relationships>
#| <inputRequirement>INPUT_REQUIRED</inputRequirement></extension>
#|<extension><name>org.apache.nifi.processors.standard.PutDatabaseRecord</name><type>PROCESSOR</type><description>Writes records</description>
#| <properties>
#|  <property><name>put-db-record-table-name</name><displayName>Table Name</displayName><required>true</required><sensitive>false</sensitive><expressionLanguageScope>FLOWFILE_ATTRIBUTES</expressionLanguageScope></property>
#|  <property><name>put-db-record-catalog-name</name><displayName>Catalog Name</displayName><required>false</required><sensitive>false</sensitive></property>
#|  <property><name>put-db-record-dcbp-service</name><displayName>Database Connection Pooling Service</displayName><required>true</required><sensitive>false</sensitive><controllerServiceDefinition><className>org.apache.nifi.dbcp.DBCPService</className></controllerServiceDefinition></property>
#|  <property><name>put-db-record-record-reader</name><displayName>Record Reader</displayName><required>true</required><sensitive>false</sensitive><controllerServiceDefinition><className>org.apache.nifi.serialization.RecordReaderFactory</className></controllerServiceDefinition></property>
#| </properties>
#| <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship>
#|  <relationship><name>failure</name><description>bad</description><autoTerminated>false</autoTerminated></relationship>
#|  <relationship><name>retry</name><description>again</description><autoTerminated>false</autoTerminated></relationship></relationships>
#| <writesAttributes><writesAttribute><name>putdatabaserecord.error</name></writesAttribute></writesAttributes><inputRequirement>INPUT_REQUIRED</inputRequirement></extension>
#|</extensions></extensionManifest>"""
#|
#|
#|def lineage_flow():
#|    """Metadata lookup -> UpdateAttribute -> PutDatabaseRecord with one misnamed and one never-set attribute."""
#|    flow = metadata_flow()
#|    std = {"group": "org.apache.nifi", "artifact": "nifi-standard-nar", "version": "1.27.0"}
#|    flow["rootGroup"]["processors"] += [
#|        proc("l-gen", "Poll landing", "org.apache.nifi.processors.standard.GenerateFlowFile", {"File Size": "0B"}, bundle=std),
#|        proc("l-meta", "Lookup file metadata", "com.acme.meta.MetadataLookup", {"Object Key": "${filename}", "metadata-db": DBCP_INSTANCE},
#|             bundle={"group": "com.acme", "artifact": "acme-meta-nar", "version": "2.0.0"}, auto=["not found", "failure"]),
#|        proc("l-ua", "Set target", "org.apache.nifi.processors.attributes.UpdateAttribute",
#|             {"target.table": "${tableName}", "load.mode": "${mode:isEmpty():ifElse('full', ${mode})}"},
#|             bundle=dict(std, artifact="nifi-update-attribute-nar")),
#|        proc("l-put", "Load table", "org.apache.nifi.processors.standard.PutDatabaseRecord",
#|             {"put-db-record-table-name": "${target.table}", "put-db-record-catalog-name": "${target_catalog}",
#|              "put-db-record-dcbp-service": DBCP_INSTANCE, "put-db-record-record-reader": "instance-reader-1"},
#|             bundle=std, auto=["success", "failure", "retry"]),
#|    ]
#|    flow["rootGroup"]["connections"] += [conn("l1", "l-gen", "PROCESSOR", "l-meta", "PROCESSOR", ["success"]),
#|                                         conn("l2", "l-meta", "PROCESSOR", "l-ua", "PROCESSOR", ["success"]),
#|                                         conn("l3", "l-ua", "PROCESSOR", "l-put", "PROCESSOR", ["success"])]
#|    return flow
#|
#|
#|class FakeNiFi:
#|    """A NiFi REST API stand-in (login, provenance query lifecycle, event details, bulletins, about) built from the
#|    documented request / response shapes. Runtime ids are the fixture's instance ids (inst-<id>)."""
#|
#|    EVENTS = [
#|        {"id": "11", "eventId": 11, "eventTime": "09/26/2026 10:15:01.100 UTC", "eventType": "RECEIVE", "flowFileUuid": "u-1",
#|         "filename": "orders_0926.json", "componentId": "inst-p-listen", "componentName": "Receive orders API",
#|         "componentType": "ListenHTTP", "transitUri": "http://0.0.0.0:8081/orders", "childUuids": [], "details": None},
#|        {"id": "12", "eventId": 12, "eventTime": "09/26/2026 10:15:01.300 UTC", "eventType": "ATTRIBUTES_MODIFIED",
#|         "flowFileUuid": "u-1", "filename": "orders_0926.json", "componentId": "inst-p-extract", "componentName": "Extract fields",
#|         "componentType": "EvaluateJsonPath", "childUuids": []},
#|        {"id": "13", "eventId": 13, "eventTime": "09/26/2026 10:15:02.000 UTC", "eventType": "ROUTE", "flowFileUuid": "u-1",
#|         "filename": "orders_0926.json", "componentId": "inst-p-validate", "componentName": "Validate order",
#|         "componentType": "ValidateOrderJson", "relationship": "invalid", "childUuids": []},
#|        {"id": "14", "eventId": 14, "eventTime": "09/26/2026 10:15:02.200 UTC", "eventType": "DROP", "flowFileUuid": "u-1",
#|         "filename": "orders_0926.json", "componentId": "inst-p-rejects", "componentName": "Write rejects",
#|         "componentType": "PutFile", "details": "Auto-Terminated by failure Relationship", "childUuids": []},
#|        {"id": "21", "eventId": 21, "eventTime": "09/26/2026 11:00:00.000 UTC", "eventType": "RECEIVE", "flowFileUuid": "u-2",
#|         "filename": "late.json", "componentId": "inst-p-listen", "componentName": "Receive orders API", "componentType": "ListenHTTP",
#|         "childUuids": []},
#|        {"id": "22", "eventId": 22, "eventTime": "09/26/2026 12:00:00.000 UTC", "eventType": "DROP", "flowFileUuid": "u-2",
#|         "filename": "late.json", "componentId": "inst-p-audit", "componentName": "Write audit row", "componentType": "PutDatabaseRecord",
#|         "details": "FlowFile Expired", "childUuids": []},
#|    ]
#|    ATTRS = {"14": [{"name": "validation.status", "value": "INVALID", "previousValue": None},
#|                    {"name": "validation.error", "value": "vendor missing", "previousValue": None},
#|                    {"name": "api.token", "value": "tok-SECRET-9", "previousValue": "tok-SECRET-9"},
#|                    {"name": "vendor", "value": "", "previousValue": ""}]}
#|
#|    def __init__(self, user="admin", password="pw123456789"):
#|        import http.server
#|        import threading
#|        import urllib.parse
#|        fake = self
#|        self.queries, self.deleted, self.calls = {}, [], []
#|
#|        class Handler(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def _send(self, code, obj=None, text=None):
#|                body = (text if text is not None else json.dumps(obj)).encode()
#|                self.send_response(code)
#|                self.send_header("Content-Type", "text/plain" if text is not None else "application/json")
#|                self.send_header("Content-Length", str(len(body)))
#|                self.end_headers()
#|                self.wfile.write(body)
#|
#|            def _authed(self):
#|                want = "Bearer reg-tok" if self.path.startswith("/nifi-registry-api/") else "Bearer tok-123"
#|                return self.headers.get("Authorization") == want
#|
#|            def do_POST(self):
#|                n = int(self.headers.get("Content-Length") or 0)
#|                raw = self.rfile.read(n).decode()
#|                fake.calls.append(("POST", self.path))
#|                if self.path == "/nifi-registry-api/access/token/login":
#|                    ok = self.headers.get("Authorization") == "Basic " + __import__("base64").b64encode(f"{user}:{password}".encode()).decode()
#|                    return self._send(201, text="reg-tok") if ok else self._send(401, text="bad")
#|                if self.path == "/nifi-api/access/token":
#|                    form = dict(urllib.parse.parse_qsl(raw))
#|                    return self._send(201, text="tok-123") if form == {"username": user, "password": password} else self._send(401, text="bad")
#|                if not self._authed():
#|                    return self._send(401, text="unauthorized")
#|                if self.path == "/nifi-api/provenance":
#|                    terms = json.loads(raw)["provenance"]["request"]["searchTerms"]
#|                    qid = f"q{len(fake.queries) + 1}"
#|                    fake.queries[qid] = {k: v["value"] for k, v in terms.items()}
#|                    return self._send(201, {"provenance": {"id": qid, "finished": False}})
#|                self._send(404, text="nope")
#|
#|            def do_GET(self):
#|                fake.calls.append(("GET", self.path))
#|                if not self._authed():
#|                    return self._send(401, text="unauthorized")
#|                if self.path.startswith("/nifi-api/provenance/"):
#|                    terms = fake.queries[self.path.rsplit("/", 1)[1]]
#|                    key = {"Filename": "filename", "FlowFileUUID": "flowFileUuid", "ProcessorID": "componentId"}
#|                    evs = [e for e in fake.EVENTS if all(e.get(key[k]) == v for k, v in terms.items())]
#|                    return self._send(200, {"provenance": {"finished": True, "results": {"provenanceEvents": evs}}})
#|                if self.path.startswith("/nifi-api/provenance-events/"):
#|                    eid = self.path.rsplit("/", 1)[1]
#|                    ev = dict(next(e for e in fake.EVENTS if e["id"] == eid), attributes=fake.ATTRS.get(eid, []))
#|                    return self._send(200, {"provenanceEvent": ev})
#|                if self.path.startswith("/nifi-api/flow/bulletin-board"):
#|                    return self._send(200, {"bulletinBoard": {"bulletins": [{"bulletin": {
#|                        "level": "ERROR", "sourceId": "inst-p-audit", "sourceName": "Write audit row", "timestamp": "10:15:02 UTC",
#|                        "message": "Failed to put Records to database: Table file_audit not found"}}]}})
#|                if self.path == "/nifi-api/versions/process-groups/inst-pg":
#|                    return self._send(200, {"versionControlInformation": {"groupId": "inst-pg", "flowName": "vendor-json", "version": 3,
#|                                                                          "state": "STALE", "stateExplanation": "A newer version (4) is available"}})
#|                if self.path == "/nifi-registry-api/buckets/b1/flows/f1/versions":
#|                    return self._send(200, [{"version": 3, "timestamp": 1789900000000, "author": "bob", "comments": "add order validation"},
#|                                            {"version": 4, "timestamp": 1790000000000, "author": "alice", "comments": "switch vendor to API v2"}])
#|                if self.path == "/nifi-api/flow/about":
#|                    return self._send(200, {"about": {"title": "NiFi", "version": "1.27.0"}})
#|                if self.path.startswith("/nifi-api/flow/process-groups/root/status"):
#|                    proc = lambda pid, name, typ, st: {"processorStatusSnapshot": {"id": pid, "name": name, "type": typ, "runStatus": st,
#|                                                                                    "flowFilesIn": 0}}
#|                    conn = lambda cid, s, sn, d, dn, n, pct: {"connectionStatusSnapshot": {
#|                        "id": cid, "sourceId": s, "sourceName": sn, "destinationId": d, "destinationName": dn,
#|                        "queuedCount": n, "queued": f"{n} (1 MB)", "percentUseCount": pct, "percentUseBytes": "1"}}
#|                    vendor = {"name": "Vendor JSON Ingestion",
#|                              "processorStatusSnapshots": [proc("inst-p-validate", "Validate order", "ValidateOrderJson", "Running"),
#|                                                           proc("inst-p-rejects", "Write rejects", "PutFile", "Stopped")],
#|                              "connectionStatusSnapshots": [conn("c2", "inst-p-extract", "Extract fields", "inst-p-validate", "Validate order",
#|                                                                 "10,000", "100"),
#|                                                            conn("c4", "inst-p-validate", "Validate order", "inst-p-rejects", "Write rejects",
#|                                                                 "5", "0")]}
#|                    root = {"name": "NiFi Flow",
#|                            "processorStatusSnapshots": [proc("inst-p-archive", "Archive order", "PutDatabaseRecord", "Invalid"),
#|                                                         proc("inst-p-audit", "Write audit row", "PutDatabaseRecord", "Running")],
#|                            "connectionStatusSnapshots": [conn("r5", "inst-p-enrich", "Enrich via python", "inst-p-archive", "Archive order",
#|                                                               "0", "0")],
#|                            "processGroupStatusSnapshots": [{"processGroupStatusSnapshot": vendor}]}
#|                    return self._send(200, {"processGroupStatus": {"aggregateSnapshot": root}})
#|                if self.path == "/nifi-api/processors/inst-p-archive":
#|                    return self._send(200, {"component": {"id": "inst-p-archive", "validationErrors": [
#|                        "'Table Name' validated against 'order_archive' is invalid because table does not exist"]}})
#|                if self.path.startswith("/nifi-api/flow/process-groups/root/controller-services"):
#|                    return self._send(200, {"controllerServices": [
#|                        {"component": {"id": "instance-reader-1", "name": "AuditJsonReader", "state": "ENABLED"}},
#|                        {"component": {"id": "instance-writer-unused", "name": "UnusedWriter", "state": "DISABLED"}}]})
#|                if self.path == "/nifi-api/system-diagnostics":
#|                    return self._send(200, {"systemDiagnostics": {"aggregateSnapshot": {
#|                        "heapUtilization": "91.0%", "contentRepositoryStorageUsage": [
#|                            {"identifier": "default", "utilization": "96.0%", "usedSpace": "96 GB", "totalSpace": "100 GB"}],
#|                        "flowFileRepositoryStorageUsage": {"utilization": "20.0%"}}}})
#|                if self.path == "/nifi-api/flow/cluster/summary":
#|                    return self._send(200, {"clusterSummary": {"clustered": True, "connectedNodeCount": 2, "totalNodeCount": 3}})
#|                self._send(404, text="nope")
#|
#|            def do_DELETE(self):
#|                fake.deleted.append(self.path)
#|                self._send(200, {})
#|
#|        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
#|        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/nifi-api"
#|        threading.Thread(target=self.server.serve_forever, daemon=True).start()
#|
#|    def stop(self):
#|        self.server.shutdown()
#|        self.server.server_close()
#|
#|
#|def make_nar(path, manifest_xml=None, group="com.acme", artifact="acme-nifi-nar", service_classes=()):
#|    with zipfile.ZipFile(path, "w") as z:
#|        z.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nNar-Group: {group}\nNar-Id: {artifact}\nNar-Version: 1.0.0\n")
#|        if manifest_xml:
#|            z.writestr("META-INF/docs/extension-manifest.xml", manifest_xml)
#|        if service_classes:
#|            jar = io.BytesIO()
#|            with zipfile.ZipFile(jar, "w") as j:
#|                j.writestr("META-INF/services/org.apache.nifi.processor.Processor", "\n".join(service_classes) + "\n")
#|            z.writestr(f"META-INF/bundled-dependencies/{artifact}-1.0.0.jar", jar.getvalue())
#|
#|
#|def make_db(path):
#|    db = sqlite3.connect(path)
#|    db.executescript("""
#|        CREATE TABLE file_audit(id INTEGER PRIMARY KEY, order_id TEXT NOT NULL, vendor TEXT, status TEXT,
#|                                received_at TEXT NOT NULL, user_email TEXT);
#|        CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, region TEXT);
#|        CREATE TABLE orders(id TEXT PRIMARY KEY, cust_id INTEGER REFERENCES customers(id), total REAL);
#|        CREATE TABLE file_calls(id INTEGER PRIMARY KEY, source_system TEXT, status TEXT, file_name TEXT);
#|        CREATE TABLE unrelated(x INTEGER);
#|        CREATE INDEX ix_audit_order ON file_audit(order_id);
#|        INSERT INTO file_calls(source_system, status, file_name) VALUES ('vendorA','LOADED','a.json'), ('vendorA','FAILED','b.json'),
#|                                                                     ('vendorB','LOADED','c.json');
#|        INSERT INTO file_audit(order_id, vendor, status, received_at, user_email) VALUES ('o1','vendorA','OK','2026-01-01','x@y.com');
#|    """)
#|    db.commit()
#|    db.close()
#|
#|
#|API_TOKEN = "abcdefghijklmnop1234"
#|METADATA_SQL = """
#|    CREATE TABLE OBJ_DEFINITION(OBJ_ID INTEGER PRIMARY KEY, FILE_NAME TEXT, TABLE_NAME TEXT, SOURCE_SYSTEM TEXT, DELIMITER TEXT, ACTIVE_FLAG TEXT);
#|    CREATE TABLE OBJ_STRUCTURE(STRUCT_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER REFERENCES OBJ_DEFINITION(OBJ_ID), COL_NAME TEXT,
#|                               DATA_TYPE TEXT, COL_SEQ INTEGER, COL_LENGTH INTEGER, MANDATORY_FLAG TEXT, JSON_PATH TEXT);
#|    CREATE TABLE SOURCE_FEED_CONFIG(FEED_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, FEED_NAME TEXT, SFTP_HOST TEXT, SFTP_USER TEXT,
#|                                    SFTP_PASSWORD TEXT, REMOTE_DIR TEXT);
#|    CREATE TABLE NIFI_JSON_API_CONFIG(API_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, API_NAME TEXT, API_URL TEXT, AUTH_HEADER TEXT,
#|                                      JSON_ROOT_PATH TEXT, REQUEST_TEMPLATE TEXT);
#|    CREATE TABLE stg_sales(order_no INTEGER NOT NULL, cust_name VARCHAR(20), amount DECIMAL(10,2), order_dt DATE, region VARCHAR(10),
#|                           load_ts TEXT NOT NULL);
#|    CREATE TABLE stg_customers(cust_id INTEGER PRIMARY KEY, name VARCHAR(100), email VARCHAR(200));
#|    CREATE TABLE stg_orders(order_id INTEGER NOT NULL, customer_name VARCHAR(100), amount DECIMAL(10,2));
#|    CREATE TABLE FILE_LOAD_AUDIT(AUDIT_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, FILE_NAME TEXT, LOAD_STATUS TEXT, LOAD_TS TEXT,
#|                                 ERROR_MSG TEXT, ROW_COUNT INTEGER);
#|    INSERT INTO FILE_LOAD_AUDIT VALUES (1, 1, '/landing/pos/SALES_20260925.csv', 'SUCCESS', '2026-09-25 02:10:00', NULL, 1200),
#|                                       (2, 1, '/landing/pos/SALES_20260926.csv', 'FAILED', '2026-09-26 02:14:00',
#|                                        'Column count mismatch at line 12: expected 5, found 6', 0);
#|    INSERT INTO OBJ_DEFINITION VALUES (1, 'SALES_YYYYMMDD.csv', 'stg_sales', 'POS', ',', 'Y'),
#|                                      (2, 'customers_*.json', 'stg_customers', 'CRM', NULL, 'Y'),
#|                                      (3, 'returns.csv', 'stg_returns', 'POS', ',', 'Y'),
#|                                      (4, 'orders_api', 'stg_orders', 'SHOP', NULL, 'Y');
#|    INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES
#|        (1, 'ORDER_NO', 'INTEGER', 1, NULL, 'Y'), (1, 'CUST_NAME', 'VARCHAR', 2, 50, 'N'), (1, 'AMOUNT', 'VARCHAR', 3, 20, 'N'),
#|        (1, 'ORDER_DT', 'DATE', 4, NULL, 'N'), (1, 'REGION', 'VARCHAR', 5, 10, 'N'),
#|        (2, 'CUST_ID', 'INT', 1, NULL, 'Y'), (2, 'NAME', 'VARCHAR', 2, 100, 'N'), (2, 'EMAIL', 'VARCHAR', 3, 200, 'N'),
#|        (3, 'RET_ID', 'INT', 1, NULL, 'Y');
#|    INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG, JSON_PATH) VALUES
#|        (4, 'ORDER_ID', 'INT', 1, NULL, 'Y', '$.orders[*].id'), (4, 'CUSTOMER_NAME', 'VARCHAR', 2, 100, 'N', '$.orders[*].customer.name'),
#|        (4, 'AMOUNT', 'DECIMAL', 3, NULL, 'N', '$.orders[*].amount');
#|    INSERT INTO SOURCE_FEED_CONFIG VALUES (10, 1, 'pos_sales_feed', 'sftp.pos.acme.com', 'nifi', 'Sup3rS3cret!', '/outbound/sales');
#|    INSERT INTO NIFI_JSON_API_CONFIG VALUES (20, 2, 'crm_customers_api', 'https://crm.acme.com/api/v2/customers',
#|                                             'Bearer abcdefghijklmnop1234', '$.data', '{"client": "nifi", "password": "hunter2"}'),
#|                                            (21, 4, 'orders_api', 'https://shop.acme.com/api/orders', 'Bearer qrstuvwxyz987654321', '$.orders', NULL);
#|"""
#|
#|
#|METADATA_BASE = """package com.acme.meta.base;
#|
#|import org.apache.nifi.components.PropertyDescriptor;
#|import org.apache.nifi.dbcp.DBCPService;
#|import org.apache.nifi.processor.AbstractProcessor;
#|import org.apache.nifi.processor.Relationship;
#|
#|/** Shared base of all ACME metadata processors. */
#|public abstract class AbstractMetadataProcessor extends AbstractProcessor {
#|
#|    public static final PropertyDescriptor METADATA_DB = new PropertyDescriptor.Builder()
#|            .name(MetaConstants.PROP_METADATA_DB)
#|            .displayName("Metadata DB")
#|            .description("Connection pool for the OBJ_* config tables")
#|            .identifiesControllerService(DBCPService.class)
#|            .required(true)
#|            .build();
#|
#|    public static final Relationship REL_FAILURE = new Relationship.Builder()
#|            .name("failure").description("Lookup failed").build();
#|}
#|"""
#|METADATA_CONSTANTS = """package com.acme.meta.base;
#|
#|public interface MetaConstants {
#|    String PROP_METADATA_DB = "metadata-db";
#|    String ATTR_TABLE = "table_name";
#|    String ATTR_STRUCTURE = "structure.json";
#|}
#|"""
#|METADATA_PROCESSOR = """package com.acme.meta;
#|
#|import com.acme.meta.base.AbstractMetadataProcessor;
#|import com.acme.meta.base.MetaConstants;
#|import org.apache.nifi.annotation.behavior.WritesAttribute;
#|import org.apache.nifi.annotation.behavior.WritesAttributes;
#|import org.apache.nifi.annotation.documentation.CapabilityDescription;
#|import org.apache.nifi.annotation.documentation.Tags;
#|import org.apache.nifi.components.AllowableValue;
#|import org.apache.nifi.components.PropertyDescriptor;
#|import org.apache.nifi.flowfile.attributes.CoreAttributes;
#|import org.apache.nifi.processor.Relationship;
#|import org.apache.nifi.processor.exception.ProcessException;
#|
#|@Tags({"acme", "metadata"})
#|@CapabilityDescription("Looks up the object definition; structure and feed config for the incoming file and writes them as attributes.")
#|@WritesAttributes({
#|        @WritesAttribute(attribute = "table_name", description = "Target table from OBJ_DEFINITION"),
#|        @WritesAttribute(attribute = "structure.json", description = "Columns from OBJ_STRUCTURE")})
#|public class MetadataLookup extends AbstractMetadataProcessor {
#|
#|    private static final String REL_NOT_FOUND_NAME = "not found";
#|    static final AllowableValue BY_FILE = new AllowableValue("by-file", "By file name", "Match FILE_NAME patterns");
#|    static final AllowableValue BY_FEED = new AllowableValue("by-feed", "By feed name", "Match SOURCE_FEED_CONFIG.FEED_NAME");
#|
#|    public static final PropertyDescriptor OBJECT_KEY = new PropertyDescriptor.Builder()
#|            .name("Object Key").description("File name or feed name to look up").required(true)
#|            .expressionLanguageSupported(ExpressionLanguageScope.FLOWFILE_ATTRIBUTES).build();
#|
#|    public static final PropertyDescriptor METADATA_SERVICE = new PropertyDescriptor.Builder()
#|            .name("metadata-service").displayName("Metadata Service").identifiesControllerService(MetadataService.class).build();
#|
#|    public static final PropertyDescriptor LOOKUP_MODE = new PropertyDescriptor.Builder()
#|            .name("lookup-mode").displayName("Lookup Mode").allowableValues(BY_FILE, BY_FEED)
#|            .defaultValue(BY_FILE.getValue()).build();
#|
#|    public static final Relationship REL_SUCCESS = new Relationship.Builder().name("success").description("found").build();
#|    public static final Relationship REL_NOT_FOUND = new Relationship.Builder().name(REL_NOT_FOUND_NAME).description("no definition").build();
#|
#|    private final MetadataDao dao = new MetadataDao();
#|
#|    @Override
#|    public void onTrigger(ProcessContext context, ProcessSession session) {
#|        FlowFile flowFile = session.get();
#|        String fileName = flowFile.getAttribute(CoreAttributes.FILENAME.key());
#|        Definition def = dao.load(fileName);
#|        if (def == null) {
#|            getLogger().error("No OBJ_DEFINITION row for file {}", new Object[]{fileName});
#|            session.transfer(flowFile, REL_NOT_FOUND);
#|            return;
#|        }
#|        if (!def.matches()) {
#|            throw new ProcessException("Structure mismatch for " + fileName + " against OBJ_STRUCTURE");
#|        }
#|        Map<String, String> attrs = new HashMap<>();
#|        attrs.put(MetaConstants.ATTR_TABLE, def.getTable());
#|        attrs.put(MetaConstants.ATTR_STRUCTURE, def.getColumnsJson());
#|        attrs.put("delimiter", def.getDelimiter());
#|        flowFile = session.putAllAttributes(flowFile, attrs);
#|        session.transfer(flowFile, REL_SUCCESS);
#|    }
#|}
#|"""
#|METADATA_SERVICE_API = """package com.acme.meta;
#|
#|import org.apache.nifi.controller.ControllerService;
#|
#|public interface MetadataService extends ControllerService {
#|    Definition find(String fileName);
#|}
#|"""
#|METADATA_SERVICE_IMPL = """package com.acme.meta;
#|
#|import org.apache.nifi.annotation.documentation.CapabilityDescription;
#|import org.apache.nifi.controller.AbstractControllerService;
#|
#|@CapabilityDescription("Caches OBJ_DEFINITION rows")
#|public class CachingMetadataService extends AbstractControllerService implements MetadataService {
#|}
#|"""
#|MOCK_TEST_PROCESSOR = """package com.acme.meta;
#|
#|import org.apache.nifi.processor.AbstractProcessor;
#|
#|public class MockUpstream extends AbstractProcessor {
#|}
#|"""
#|UNREGISTERED_PROCESSOR = """package com.acme.meta;
#|
#|import com.acme.meta.base.AbstractMetadataProcessor;
#|
#|public class LegacyMetadataLookup extends AbstractMetadataProcessor {
#|}
#|"""
#|PROCESSORS_POM = """<project><parent><groupId>com.acme</groupId><artifactId>acme-meta</artifactId><version>2.0.0</version></parent>
#|<artifactId>acme-meta-processors</artifactId><packaging>jar</packaging>
#|<dependencies><dependency><groupId>org.apache.nifi</groupId><artifactId>nifi-api</artifactId></dependency></dependencies></project>"""
#|NAR_POM = """<project><parent><groupId>com.acme</groupId><artifactId>acme-meta</artifactId><version>2.0.0</version></parent>
#|<artifactId>acme-meta-nar</artifactId><packaging>nar</packaging>
#|<dependencies><dependency><groupId>com.acme</groupId><artifactId>acme-meta-processors</artifactId><version>2.0.0</version></dependency></dependencies></project>"""
#|
#|
#|def class_file(name, strings):
#|    """A minimal valid .class file whose constant pool holds `strings` as string literals (no JDK needed)."""
#|    import struct
#|    pool, count = b"", 1
#|
#|    def utf8(s):
#|        b = s.encode("utf-8")
#|        return b"\x01" + struct.pack(">H", len(b)) + b
#|
#|    pool += utf8(name.replace(".", "/")) + b"\x07" + struct.pack(">H", 1)          # 1 utf8, 2 class
#|    pool += utf8("java/lang/Object") + b"\x07" + struct.pack(">H", 3)              # 3 utf8, 4 class
#|    count = 5
#|    for s in strings:
#|        pool += utf8(s) + b"\x08" + struct.pack(">H", count)                         # utf8, then String -> it
#|        count += 2
#|    return (b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 52, count) + pool
#|            + struct.pack(">HHHHHHH", 0x21, 2, 4, 0, 0, 0, 0))
#|
#|
#|def make_meta_nar(path, missing_attribute="delimiter"):
#|    """Deployed build of acme-meta-nar 2.0.0 - built from an older commit: no `delimiter` attribute yet."""
#|    lookup = ["Object Key", "File name or feed name to look up", "metadata-service", "Metadata Service", "lookup-mode", "Lookup Mode", "by-file", "by-feed", "success",
#|              "not found", "No OBJ_DEFINITION row for file {}", "Structure mismatch for {} against OBJ_STRUCTURE",
#|              "table_name", "structure.json", "delimiter"]
#|    lookup = [s for s in lookup if s != missing_attribute]
#|    jar = io.BytesIO()
#|    with zipfile.ZipFile(jar, "w") as j:
#|        j.writestr("META-INF/services/org.apache.nifi.processor.Processor", "com.acme.meta.MetadataLookup\n")
#|        j.writestr("com/acme/meta/MetadataLookup.class", class_file("com.acme.meta.MetadataLookup", lookup))
#|        j.writestr("com/acme/meta/MetadataDao.class", class_file("com.acme.meta.MetadataDao", [
#|            "OBJ_DEFINITION", "SOURCE_FEED_CONFIG", "SELECT * FROM {} d WHERE d.FILE_NAME = ?",
#|            "SELECT s.COL_NAME FROM OBJ_STRUCTURE s WHERE s.OBJ_ID = ?"]))
#|        j.writestr("com/acme/meta/base/AbstractMetadataProcessor.class",
#|                   class_file("com.acme.meta.base.AbstractMetadataProcessor", ["metadata-db", "Metadata DB", "failure"]))
#|    with zipfile.ZipFile(path, "w") as z:
#|        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nNar-Group: com.acme\nNar-Id: acme-meta-nar\nNar-Version: 2.0.0\n")
#|        z.writestr("META-INF/bundled-dependencies/acme-meta-processors-2.0.0.jar", jar.getvalue())
#|        z.writestr("META-INF/bundled-dependencies/commons-lang3-3.12.0.jar", b"not really a jar")
#|METADATA_DAO = """package com.acme.meta;
#|
#|class MetadataDao {
#|    private static final String DEF_TABLE = "OBJ_DEFINITION";
#|    private static final String STRUCT_TABLE = "obj_structure";
#|    private static final String FEED_TABLE = "SOURCE_FEED_CONFIG";
#|
#|    void load(String key) {
#|        String sql = "SELECT * FROM " + DEF_TABLE + " d WHERE d.FILE_NAME = ?";
#|    }
#|}
#|"""
#|
#|
#|def make_metadata_repo(root):
#|    mod = Path(root) / "nifi-meta-processors"
#|    src = mod / "src" / "main" / "java" / "com" / "acme" / "meta"
#|    (src / "base").mkdir(parents=True, exist_ok=True)
#|    (src / "MetadataLookup.java").write_text(METADATA_PROCESSOR, encoding="utf-8")
#|    (src / "LegacyMetadataLookup.java").write_text(UNREGISTERED_PROCESSOR, encoding="utf-8")
#|    (src / "MetadataDao.java").write_text(METADATA_DAO, encoding="utf-8")
#|    (src / "MetadataService.java").write_text(METADATA_SERVICE_API, encoding="utf-8")
#|    (src / "CachingMetadataService.java").write_text(METADATA_SERVICE_IMPL, encoding="utf-8")
#|    test_src = mod / "src" / "test" / "java" / "com" / "acme" / "meta"
#|    test_src.mkdir(parents=True, exist_ok=True)
#|    (test_src / "MockUpstream.java").write_text(MOCK_TEST_PROCESSOR, encoding="utf-8")
#|    (src / "base" / "AbstractMetadataProcessor.java").write_text(METADATA_BASE, encoding="utf-8")
#|    (src / "base" / "MetaConstants.java").write_text(METADATA_CONSTANTS, encoding="utf-8")
#|    svc = mod / "src" / "main" / "resources" / "META-INF" / "services"
#|    svc.mkdir(parents=True, exist_ok=True)
#|    (svc / "org.apache.nifi.processor.Processor").write_text("com.acme.meta.MetadataLookup\n", encoding="utf-8")
#|    (mod / "pom.xml").write_text(PROCESSORS_POM, encoding="utf-8")
#|    (Path(root) / "nifi-meta-nar").mkdir(parents=True, exist_ok=True)
#|    (Path(root) / "nifi-meta-nar" / "pom.xml").write_text(NAR_POM, encoding="utf-8")
#|    return Path(root)
#|
#|
#|def metadata_flow():
#|    """The nested flow plus the two processors a metadata-driven flow has: a lookup of the config tables and a
#|    processor configured with a feed name."""
#|    flow = nested_flow()
#|    flow["rootGroup"]["processors"] += [
#|        proc("p-meta", "Read object metadata", "org.apache.nifi.processors.standard.ExecuteSQL",
#|             {"Database Connection Pooling Service": DBCP_INSTANCE,
#|              "SQL select query": "SELECT s.COL_NAME, s.DATA_TYPE FROM OBJ_DEFINITION d JOIN OBJ_STRUCTURE s ON s.OBJ_ID = d.OBJ_ID "
#|                                  "WHERE d.FILE_NAME = '${filename}'"}, auto=["failure"]),
#|        proc("p-feed", "Tag POS feed", "org.apache.nifi.processors.attributes.UpdateAttribute", {"feed.name": "pos_sales_feed"},
#|             bundle={"group": "org.apache.nifi", "artifact": "nifi-update-attribute-nar", "version": "1.27.0"}),
#|        proc("p-lookup-meta", "Metadata lookup", "com.acme.meta.MetadataLookup", {"Object Key": "${filename}"},
#|             bundle={"group": "com.acme", "artifact": "acme-meta-nar", "version": "1.9.0"}),
#|    ]
#|    flow["rootGroup"]["connections"] += [conn("r7", "p-feed", "PROCESSOR", "p-meta", "PROCESSOR", ["success"]),
#|                                         conn("r8", "p-meta", "PROCESSOR", "p-lookup-meta", "PROCESSOR", ["success"])]
#|    return flow
#|
#|
#|def make_env(tmp, flow=None, with_db=True, with_metadata=False):
#|    """Create a full environment under tmp and return the config path."""
#|    tmp = Path(tmp)
#|    (tmp / "nars").mkdir(parents=True, exist_ok=True)
#|    make_nar(tmp / "nars" / "acme-nifi-nar-1.0.0.nar", ACME_MANIFEST)
#|    make_nar(tmp / "nars" / "legacy-nar.nar", None, group="com.legacy", artifact="legacy-nar", service_classes=["com.legacy.OldProcessor"])
#|    flow_path = tmp / "flow.json.gz"
#|    with gzip.open(flow_path, "wt", encoding="utf-8") as f:
#|        json.dump(flow or nested_flow(), f)
#|    dbs = ""
#|    if with_db:
#|        make_db(tmp / "meta.db")
#|        if with_metadata:
#|            db = sqlite3.connect(tmp / "meta.db")
#|            db.executescript(METADATA_SQL)
#|            db.commit()
#|            db.close()
#|        dbs = f"""
#|[[databases]]
#|name = "metadata"
#|kind = "sqlite"
#|database = "{(tmp / 'meta.db').as_posix()}"
#|match_jdbc = "dbhost.acme.com:3306/meta"
#|include_tables = ["file_%"]
#|profile_tables = ["file_calls"]
#|sample_rows = 1
#|"""
#|        if with_metadata:
#|            dbs += '\n[audit]\ndb = "metadata"\n\n[metadata]\ndb = "metadata"\n'
#|    repos = [(FIXTURES / "repo").as_posix()]
#|    if with_metadata:
#|        repos.append(make_metadata_repo(tmp / "meta-repo").as_posix())
#|        make_meta_nar(tmp / "nars" / "acme-meta-nar-2.0.0.nar")
#|    cfg = tmp / "nifikb.toml"
#|    cfg.write_text(f"""
#|[nifi]
#|flow_file = "{flow_path.as_posix()}"
#|extra_nar_dirs = ["{(tmp / 'nars').as_posix()}"]
#|
#|[output]
#|dir = "{(tmp / 'kb').as_posix()}"
#|
#|[code]
#|repos = {json.dumps(repos)}
#|{dbs}""", encoding="utf-8")
#|    return cfg
#@@ FILE tests/test_mariadb.py t 02498f6da29a6d68
#|"""Live MariaDB regression test. Skipped unless NIFIKB_TEST_MARIADB=host:port:admin_user:admin_password is set.
#|
#|Creates a scratch database + a SELECT-only user, runs a full build against it, then drops both."""
#|import os
#|import shutil
#|import sqlite3
#|import tempfile
#|import unittest
#|from pathlib import Path
#|
#|from test_nifikb import run_cli
#|from fixtures_builder import make_env, metadata_flow
#|from nifikb import db as dbmod
#|from nifikb.build import build
#|from nifikb.config import load_config
#|
#|MARIADB = os.environ.get("NIFIKB_TEST_MARIADB")
#|
#|
#|@unittest.skipUnless(MARIADB, "set NIFIKB_TEST_MARIADB=host:port:user:password to run against a live MariaDB")
#|class TestMariaDB(unittest.TestCase):
#|    @classmethod
#|    def setUpClass(cls):
#|        import pymysql
#|        host, port, user, password = MARIADB.split(":", 3)
#|        cls.admin = pymysql.connect(host=host, port=int(port), user=user, password=password, autocommit=True)
#|        with cls.admin.cursor() as cur:
#|            for stmt in [
#|                "DROP DATABASE IF EXISTS nifikb_test", "CREATE DATABASE nifikb_test", "USE nifikb_test",
#|                "CREATE TABLE file_audit(id INT AUTO_INCREMENT PRIMARY KEY, order_id VARCHAR(40) NOT NULL, vendor VARCHAR(40), "
#|                "status VARCHAR(20), received_at DATETIME NOT NULL, user_email VARCHAR(100), KEY ix_order(order_id)) COMMENT='one row per file call'",
#|                "CREATE TABLE customers(id INT PRIMARY KEY, name VARCHAR(80), region VARCHAR(10))",
#|                "CREATE TABLE orders(id VARCHAR(40) PRIMARY KEY, cust_id INT, total DECIMAL(10,2), FOREIGN KEY (cust_id) REFERENCES customers(id))",
#|                "CREATE TABLE file_calls(id INT AUTO_INCREMENT PRIMARY KEY, source_system VARCHAR(20), status ENUM('LOADED','FAILED'), file_name VARCHAR(200))",
#|                "INSERT INTO file_calls(source_system, status, file_name) VALUES ('vendorA','LOADED','a.json'),('vendorA','FAILED','b.json'),('vendorB','LOADED','c.json')",
#|                "INSERT INTO file_audit(order_id, vendor, status, received_at, user_email) VALUES ('o1','vendorA','OK',NOW(),'x@y.com')",
#|                "CREATE TABLE OBJ_DEFINITION(OBJ_ID INT PRIMARY KEY, FILE_NAME VARCHAR(200), TABLE_NAME VARCHAR(100), ACTIVE_FLAG CHAR(1))",
#|                "CREATE TABLE OBJ_STRUCTURE(STRUCT_ID INT AUTO_INCREMENT PRIMARY KEY, OBJ_ID INT NOT NULL, COL_NAME VARCHAR(100), "
#|                "DATA_TYPE VARCHAR(30), COL_SEQ INT, COL_LENGTH INT, MANDATORY_FLAG CHAR(1), FOREIGN KEY (OBJ_ID) REFERENCES OBJ_DEFINITION(OBJ_ID))",
#|                "CREATE TABLE SOURCE_FEED_CONFIG(FEED_ID INT PRIMARY KEY, OBJ_ID INT, FEED_NAME VARCHAR(50), SFTP_HOST VARCHAR(100), "
#|                "SFTP_PASSWORD VARCHAR(100), REMOTE_DIR VARCHAR(200))",
#|                "CREATE TABLE stg_sales(order_no INT NOT NULL, cust_name VARCHAR(20), amount DECIMAL(10,2), order_dt DATE, region VARCHAR(10), "
#|                "load_ts DATETIME NOT NULL)",
#|                "INSERT INTO OBJ_DEFINITION VALUES (1, 'SALES_YYYYMMDD.csv', 'stg_sales', 'Y')",
#|                "INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES "
#|                "(1,'ORDER_NO','INT',1,NULL,'Y'),(1,'CUST_NAME','VARCHAR',2,50,'N'),(1,'AMOUNT','VARCHAR',3,20,'N'),"
#|                "(1,'ORDER_DT','DATE',4,NULL,'N'),(1,'REGION','VARCHAR',5,10,'N')",
#|                "INSERT INTO SOURCE_FEED_CONFIG VALUES (10, 1, 'pos_sales_feed', 'sftp.pos.acme.com', 'Sup3rS3cret!', '/outbound/sales')",
#|                "CREATE USER IF NOT EXISTS 'nifikb_ro'@'%' IDENTIFIED BY 'ro_pass_123'",
#|                "CREATE USER IF NOT EXISTS 'nifikb_ro'@'localhost' IDENTIFIED BY 'ro_pass_123'",
#|                "GRANT SELECT ON nifikb_test.* TO 'nifikb_ro'@'%'",
#|                "GRANT SELECT ON nifikb_test.* TO 'nifikb_ro'@'localhost'",
#|            ]:
#|                cur.execute(stmt)
#|        cls.tmp = tempfile.mkdtemp()
#|        cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_db=False)
#|        with open(cfg_path, "a", encoding="utf-8") as f:
#|            f.write(f'\n[[databases]]\nname = "metadata"\nkind = "mariadb"\nhost = "{host}"\nport = {port}\ndatabase = "nifikb_test"\n'
#|                    f'user = "nifikb_ro"\npassword_env = "NIFIKB_TEST_RO_PASS"\nmatch_jdbc = "dbhost.acme.com:3306/meta"\n'
#|                    f'include_tables = ["file_%"]\nprofile_tables = ["file_calls"]\nsample_rows = 1\n'
#|                    f'\n[metadata]\ndb = "metadata"\n')
#|        os.environ["NIFIKB_TEST_RO_PASS"] = "ro_pass_123"
#|        cls.cfg_path = cfg_path
#|        cls.cfg = load_config(cfg_path)
#|        cls.logs = []
#|        cls.res = build(cls.cfg, log=cls.logs.append)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        with cls.admin.cursor() as cur:
#|            cur.execute("DROP DATABASE IF EXISTS nifikb_test")
#|            cur.execute("DROP USER IF EXISTS 'nifikb_ro'@'%'")
#|            cur.execute("DROP USER IF EXISTS 'nifikb_ro'@'localhost'")
#|        cls.admin.close()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_schema_documented(self):
#|        doc = (self.kb / "db/metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("## nifikb_test.file_audit", doc, "\n".join(self.logs))
#|        self.assertIn("one row per file call", doc)
#|        self.assertIn("| order_id | varchar(40) | N |", doc)
#|        self.assertIn("auto_increment", doc)
#|        self.assertIn("Indexes: PRIMARY(id) unique, ix_order(order_id)", doc)
#|        self.assertIn("FKs: cust_id→customers.id", doc)
#|        self.assertIn("values of `status`: LOADED×2, FAILED×1", doc)
#|        self.assertIn("## nifikb_test.customers", doc)
#|        self.assertNotIn("x@y.com", doc)
#|        self.assertIn("order_archive", doc)
#|
#|    def test_findings(self):
#|        db = sqlite3.connect(self.kb / "kb.sqlite")
#|        rows = dict(db.execute("SELECT kind, message FROM findings WHERE kind IN ('missing-table','field-mismatch','db-unreachable')").fetchall())
#|        db.close()
#|        self.assertIn("missing-table", rows)
#|        self.assertIn("received_at", rows.get("field-mismatch", ""))
#|        self.assertNotIn("db-unreachable", rows)
#|
#|    def test_metadata(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertRegex(doc, r"(?i)definition table: `obj_definition`")
#|        self.assertIn("(foreign key)", doc)
#|        self.assertIn("(shared column name)", doc)
#|        self.assertIn("NOT NULL column(s) of stg_sales not in the structure: load_ts", doc)
#|        self.assertIn("'AMOUNT' is VARCHAR in the structure but decimal(10,2)", doc)
#|        for live in ([], ["--live"]):
#|            rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "--file", "SALES_20260926.csv", *live,
#|                              "ORDER_NO", "CUST_NAME", "AMOUNT", "REGION", "ORDER_DT")
#|            self.assertEqual(rc, 0, out)
#|            self.assertIn("header order differs", out)
#|            self.assertIn("SFTP_PASSWORD=***", out)
#|            self.assertNotIn("Sup3rS3cret!", out)
#|        self.assertFalse(b"Sup3rS3cret!" in (self.kb / "kb.sqlite").read_bytes(), "secret stored in kb.sqlite")
#|
#|    def test_read_only(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT source_system, COUNT(*) n FROM file_calls GROUP BY source_system")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("vendorB", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT user_email FROM file_audit")
#|        self.assertIn("***", out)
#|        conn, _ = dbmod.connect(self.cfg["databases"][0])
#|        try:
#|            with self.assertRaises(Exception):
#|                with conn.cursor() as cur:
#|                    cur.execute("INSERT INTO file_calls(source_system) VALUES ('hack')")
#|        finally:
#|            conn.close()
#|
#|
#|if __name__ == "__main__":
#|    unittest.main()
#@@ END part 4 of 5 files 14
