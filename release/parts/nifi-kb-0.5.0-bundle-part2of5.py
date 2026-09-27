# nifi-kb 0.5.0 - paste bundle, part 2 of 5 - 14 files. Save as nifi-kb-0.5.0-bundle-part2of5.py, then run:  python nifi-kb-0.5.0-bundle-part2of5.py
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
#@@ FILE nifikb/code.py tc ab64b8fc56afc67e
#|"""Index custom processor code and scripts: NiFi component metadata plus hardcoded values and SQL tables.
#|
#|Parsing is regex based on purpose (no JDK / parser dependency). It targets the idioms NiFi components are
#|written with (PropertyDescriptor.Builder, Relationship.Builder, @CapabilityDescription, session.putAttribute).
#|"""
#|import re
#|from pathlib import Path
#|
#|from . import sqlparse
#|from .util import (HOST_RE, IP_RE, JDBC_RE, SECRET_ASSIGN_RE, SECRET_NAME, UNIX_PATH_RE, URL_RE, WIN_PATH_RE, REDACTED, clip,
#|                   redact_secrets)
#|
#|LANGS = {
#|    ".java": "java", ".groovy": "groovy", ".kt": "kotlin", ".scala": "scala",
#|    ".py": "python", ".sh": "shell", ".bash": "shell", ".ps1": "powershell", ".bat": "batch", ".cmd": "batch",
#|    ".sql": "sql", ".js": "javascript", ".rb": "ruby",
#|    ".properties": "config", ".yaml": "config", ".yml": "config", ".conf": "config", ".cfg": "config", ".ini": "config",
#|}
#|SKIP_DIRS = {".git", ".svn", ".idea", ".vscode", "target", "build", "out", "node_modules", "__pycache__", ".gradle",
#|             "dist", ".mvn", "venv", ".venv", ".tox"}
#|MAX_BYTES = 2_000_000
#|JVM = {"java", "groovy", "kotlin", "scala"}
#|
#|PARSER_VERSION = "4"  # bump when index_file output changes, so cached per-file results are re-parsed
#|
#|STR_LIT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
#|PKG_RE = re.compile(r"^\s*package\s+([\w.]+)", re.M)
#|DECL_RE = re.compile(
#|    r"^[ \t]*(?:@[\w.]+(?:\([^)\n]*\))?\s+)*((?:(?:public|protected|private|abstract|final|static|sealed|non-sealed|strictfp)\s+)*)"
#|    r"(class|interface|enum|record)\s+(\w+)(?:\s*<[^>{]*>)?(?:\s*\([^)]*\))?"
#|    r"(?:\s+extends\s+([\w.<>, ?]+?))?(?:\s+implements\s+([\w.<>, ?]+?))?\s*\{", re.M)
#|PD_RE = re.compile(r"(?:(\w+)\s*=\s*)?new\s+PropertyDescriptor\.Builder\(\)(.*?)\.build\(\)", re.S)
#|REL_RE = re.compile(r"(?:(\w+)\s*=\s*)?new\s+Relationship\.Builder\(\)(.*?)\.build\(\)", re.S)
#|ALLOWABLE_RE = re.compile(r"(\w+)\s*=\s*new\s+AllowableValue\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+|[\w.]+)")
#|ARG = r"((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+|[\w.]+(?:\(\))?)"
#|PUT_ATTR_RE = re.compile(r"putAttribute\(\s*[\w.()]+\s*,\s*" + ARG + r"\s*,")
#|REMOVE_ATTR_RE = re.compile(r"removeAttribute\(\s*[\w.()]+\s*,\s*" + ARG + r"\s*\)")
#|GET_ATTR_RE = re.compile(r"getAttribute\(\s*" + ARG + r"\s*\)")
#|PUT_ALL_RE = re.compile(r"putAllAttributes\(\s*[\w.()]+\s*,\s*(\w+)\s*\)")
#|CONST_RE = re.compile(r"(?:(?:public|protected|private|static|final)\s+)+String\s+([A-Z][A-Z0-9_]*)\s*=\s*"
#|                      r"((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+|[\w.]+)\s*;")
#|IFACE_CONST_RE = re.compile(r"^\s*String\s+([A-Z][A-Z0-9_]*)\s*=\s*((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+)\s*;", re.M)
#|ENUM_CONST_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*\(\s*\"([^\"]+)\"", re.M)
#|ANNOT_STR_RE = r"@{}\s*\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)\)"
#|TAGS_RE = re.compile(r"@Tags\s*\(\s*\{([^}]*)\}\s*\)")
#|WRITES_RE = re.compile(r"@WritesAttribute\s*\(\s*attribute\s*=\s*\"([^\"]+)\"(?:\s*,\s*description\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+))?")
#|READS_RE = re.compile(r"@ReadsAttribute\s*\(\s*attribute\s*=\s*\"([^\"]+)\"(?:\s*,\s*description\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+))?")
#|DYNPROP_RE = re.compile(r"@DynamicProperty\s*\((.*?)\)\s*(?=@|public|protected|private|abstract|final|class)", re.S)
#|INPUT_REQ_RE = re.compile(r"@InputRequirement\s*\(\s*(?:InputRequirement\.)?Requirement\.(\w+)")
#|FLAG_ANNOTS = ("SupportsBatching", "TriggerSerially", "TriggerWhenEmpty", "Stateful", "Restricted", "SideEffectFree",
#|               "PrimaryNodeOnly", "DefaultSchedule", "RequiresInstanceClassLoading", "Deprecated")
#|METHOD_RE = re.compile(r"^\s*(?:@\w+\s*)*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\(", re.M)
#|MESSAGE_RE = re.compile(r"(?:\b(?:log|logger|LOG|LOGGER)|getLogger\(\))\s*\.\s*(error|warn|info|debug)\(\s*"
#|                        r"((?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+)(?:\s*\+\s*(?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+))*)")
#|THROW_RE = re.compile(r"throw\s+new\s+(\w+(?:Exception|Error))\(\s*"
#|                      r"((?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+)(?:\s*\+\s*(?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+))*)")
#|PY_MESSAGE_RE = re.compile(r"(?:\b(?:logging|log|logger|LOG|LOGGER)\.(error|warning|warn|info|exception|critical)\(\s*f?[\"']([^\"'\n]+)[\"']"
#|                           r"|\braise\s+(\w+)\(\s*f?[\"']([^\"'\n]+)[\"'])")
#|PY_DEF_RE = re.compile(r"^\s*def\s+(\w+)\s*\(", re.M)
#|PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
#|NIFI_BASES = ("Processor", "ControllerService", "ReportingTask", "RecordReader", "RecordSetWriter")
#|CORE_ATTRIBUTE_KEYS = {"FILENAME": "filename", "PATH": "path", "ABSOLUTE_PATH": "absolute.path", "UUID": "uuid",
#|                       "MIME_TYPE": "mime.type", "DISCARD_REASON": "discard.reason", "ALTERNATE_IDENTIFIER": "alternate.identifier",
#|                       "PRIORITY": "priority"}
#|IO_PATTERNS = {
#|    "jdbc": r"DBCPService|getConnection\(|PreparedStatement|DriverManager|JdbcTemplate|ResultSet\b",
#|    "sftp/ssh": r"JSch|ChannelSftp|SSHClient|SFTPClient|SftpClient|com\.jcraft|SFTPTransfer|net\.schmizz",
#|    "http": r"HttpClient|HttpURLConnection|OkHttpClient|RestTemplate|WebClient|HttpGet\b|HttpPost\b|WebClientService",
#|    "s3": r"AmazonS3|S3Client|PutObjectRequest|GetObjectRequest",
#|    "kafka": r"KafkaProducer|KafkaConsumer",
#|    "file system": r"Files\.(?:write|move|copy|delete|newBufferedWriter|readAllLines|lines|walk|list)\(|new File\(|FileInputStream|FileOutputStream",
#|    "json": r"ObjectMapper|JsonNode|Gson\b|JSONObject|JsonPath",
#|    "records": r"RecordReaderFactory|RecordSetWriterFactory",
#|    "shell": r"ProcessBuilder|Runtime\.getRuntime\(\)\.exec",
#|    "email": r"javax\.mail|jakarta\.mail|Transport\.send",
#|    "cache": r"DistributedMapCacheClient|MapCacheClient",
#|    "state": r"getStateManager|StateManager\b",
#|    "spark": r"SparkSession|SparkLauncher|spark-submit",
#|}
#|
#|
#|def _concat(s):
#|    """Join "a" + "b" string concatenations into one literal."""
#|    return "".join(m.group(1) for m in STR_LIT.finditer(s)).replace('\\"', '"').replace("\\n", " ")
#|
#|
#|def _template(expr):
#|    """"File " + name + " not found" -> 'File {} not found' (log / exception message templates)."""
#|    parts = re.split(r"\s*\+\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", expr)
#|    out = []
#|    for p in parts:
#|        p = p.strip()
#|        m = STR_LIT.fullmatch(p)
#|        out.append(m.group(1).replace('\\"', '"').replace("\\n", " ") if m else "{}")
#|    return re.sub(r"(\{\}\s*)+", "{} ", "".join(out)).strip()
#|
#|
#|def _arg(expr, consts):
#|    """Value of a builder / call argument: a literal, a (qualified) constant, Enum.X.key() or CoreAttributes.X.key().
#|    Unresolved constants come back as '@ref:Name' and are resolved across files by CodeIndex."""
#|    if expr is None:
#|        return None
#|    expr = expr.strip()
#|    if expr.startswith('"'):
#|        return _concat(expr)
#|    m = re.fullmatch(r"(?:[\w.]*\.)?CoreAttributes\.(\w+)\.key\(\)", expr)
#|    if m:
#|        return CORE_ATTRIBUTE_KEYS.get(m.group(1), m.group(1).lower())
#|    ref = re.sub(r"\.(?:key|getKey|value|getValue|getName|name|toString)\(\)$", "", expr)
#|    if not re.fullmatch(r"[\w.]+", ref) or not re.search(r"[A-Z]", ref.split(".")[-1][:1]):
#|        return None
#|    return consts.get(ref) or consts.get(ref.split(".")[-1]) or f"@ref:{ref}"
#|
#|
#|def _call(builder, name, consts=None):
#|    m = re.search(r"\.{}\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+|[\w.]+(?:\(\))?)\s*\)".format(name), builder, re.S)
#|    return _arg(m.group(1), consts or {}) if m else None
#|
#|
#|def _lineno(text, pos):
#|    return text.count("\n", 0, pos) + 1
#|
#|
#|def iter_code_files(roots):
#|    for root in roots:
#|        root = Path(root)
#|        if root.is_file():
#|            yield root
#|            continue
#|        if not root.is_dir():
#|            continue
#|        stack = [root]
#|        while stack:
#|            d = stack.pop()
#|            try:
#|                entries = sorted(d.iterdir())
#|            except OSError:
#|                continue
#|            for e in entries:
#|                if e.is_dir():
#|                    if e.name not in SKIP_DIRS:
#|                        stack.append(e)
#|                elif (e.suffix.lower() in LANGS or e.name == "pom.xml" or "META-INF" in e.parts and "services" in e.parts) \
#|                        and e.stat().st_size <= MAX_BYTES:
#|                    yield e
#|
#|
#|def index_file(path):
#|    """Everything worth knowing about one source file, JSON-serializable."""
#|    path = Path(path)
#|    text = path.read_text(encoding="utf-8", errors="replace")
#|    lang = "pom" if path.name == "pom.xml" else "services" if "META-INF" in path.parts else LANGS.get(path.suffix.lower(), "other")
#|    info = {"path": str(path), "lang": lang, "lines": text.count("\n") + 1, "components": [], "hardcoded": [],
#|            "tables": [], "functions": [], "imports": [], "is_test": bool(re.search(r"[\\/]src[\\/](?:test|it|integration-test)[\\/]", str(path))
#|                                                                             or re.match(r"test_\w+\.py$", path.name))}
#|    if lang == "pom":
#|        info["artifact"] = _pom_artifact(text)
#|        return info
#|    if lang == "services":
#|        info["service_classes"] = [ln.split("#")[0].strip() for ln in text.splitlines() if ln.split("#")[0].strip()]
#|        return info
#|    if lang in JVM:
#|        info["package"] = (PKG_RE.search(text) or [None, None])[1]
#|        info.update(_jvm_file(text, info["package"]))
#|        info["functions"] = sorted(set(METHOD_RE.findall(text)))[:80]
#|    elif lang == "python":
#|        info["functions"] = PY_DEF_RE.findall(text)[:80]
#|        info["imports"] = sorted({a or b for a, b in PY_IMPORT_RE.findall(text)})
#|        info["messages"] = [{"level": lvl, "text": re.sub(r"\{[^}]*\}|%[sdrf]", "{}", msg), "line": _lineno(text, m.start())}
#|                            for m in PY_MESSAGE_RE.finditer(text) for lvl, msg in [(m.group(1) or m.group(3) or "print", m.group(2) or m.group(4))]
#|                            if msg and len(msg) >= 4][:200]
#|    if "spark-submit" in text:
#|        info["spark"] = spark_submits(text)
#|    info["hardcoded"] = scan_hardcoded(text, lang)
#|    info["tables"] = sorted({t for h in info["hardcoded"] if h["kind"] == "sql" for t in h.get("tables", [])})
#|    return info
#|
#|
#|def spark_submits(text):
#|    """spark-submit calls in a shell / Python script: class, app (jar / .py), name, master, deploy mode, first arguments."""
#|    starts = [m.start() for m in re.finditer(r"spark-submit", text)]
#|    joined = re.sub(r"\\\r?\n\s*", " ", text)  # shell line continuations
#|    out = []
#|    for n, m in enumerate(re.finditer(r"spark-submit\b([^\n;&|]*)", joined)):
#|        toks = [t.strip("\"',[]() \t") for t in re.findall(r"\"[^\"]*\"|'[^']*'|[^\s,]+", m.group(1))]
#|        toks = [t for t in toks if t]
#|        opts, app, args, i = {}, None, [], 0
#|        while i < len(toks):
#|            t = toks[i]
#|            if app is None and t.startswith("--"):
#|                if "=" in t:
#|                    k, v = t[2:].split("=", 1)
#|                    opts.setdefault(k, v)
#|                    i += 1
#|                elif t[2:] in ("verbose", "supervise") or i + 1 >= len(toks):
#|                    i += 1
#|                else:
#|                    opts.setdefault(t[2:], toks[i + 1])
#|                    i += 2
#|                continue
#|            if app is None:
#|                app = t
#|            else:
#|                args.append(t)
#|            i += 1
#|        out.append({"line": _lineno(text, starts[n]) if n < len(starts) else None, "class": opts.get("class"), "name": opts.get("name"),
#|                    "master": opts.get("master"), "deploy_mode": opts.get("deploy-mode"), "queue": opts.get("queue"), "app": app,
#|                    "args": [redact_secrets(a) for a in args[:8]]})
#|    return out
#|
#|
#|def spark_label(s):
#|    what = s.get("class") or s.get("app") or "?"
#|    return (f"{what}" + (f" in {s['app']}" if s.get("class") and s.get("app") else "")
#|            + (f" ({', '.join(x for x in [s.get('master') or '', s.get('deploy_mode') or ''] if x)})" if s.get("master") or s.get("deploy_mode") else ""))
#|
#|
#|def _pom_artifact(text):
#|    parent = re.search(r"<parent>(.*?)</parent>", text, re.S)
#|    body = re.sub(r"<parent>.*?</parent>", "", text, flags=re.S)
#|    deps_block = " ".join(re.findall(r"<dependencies>(.*?)</dependencies>", body, re.S))
#|    body = re.sub(r"<(dependencies|dependencyManagement|build|profiles|reporting)>.*?</\1>", "", body, flags=re.S)
#|
#|    def tag(block, name):
#|        m = re.search(rf"<{name}>\s*([^<]+?)\s*</{name}>", block or "")
#|        return m.group(1) if m else None
#|
#|    return {"artifactId": tag(body, "artifactId"), "groupId": tag(body, "groupId") or tag(parent.group(1) if parent else "", "groupId"),
#|            "version": tag(body, "version") or tag(parent.group(1) if parent else "", "version"),
#|            "packaging": tag(body, "packaging") or "jar", "name": tag(body, "name"),
#|            "modules": re.findall(r"<module>\s*([^<]+?)\s*</module>", body),
#|            "dependencies": re.findall(r"<artifactId>\s*([^<]+?)\s*</artifactId>", deps_block)}
#|
#|
#|def _header(text, pos):
#|    """Annotations / javadoc that belong to the declaration at pos: back to the previous statement or closing-brace line
#|    (string literals are masked so a ';' inside @CapabilityDescription("...") does not cut the header)."""
#|    window = text[max(0, pos - 8000): pos]
#|    masked = re.sub(r'"(?:[^"\\\n]|\\.)*"', lambda m: '"' + " " * (len(m.group(0)) - 2) + '"', window)
#|    cut = masked.rfind(";")
#|    for m in re.finditer(r"\n[ \t]*\}[ \t]*(?=\n)", masked):
#|        cut = max(cut, m.end() - 1)
#|    return window[cut + 1:]
#|
#|
#|def _members(text, consts):
#|    """Property descriptors, relationships and attribute reads / writes found anywhere in the file."""
#|    allowable = {f: _arg(v, consts) for f, v in ALLOWABLE_RE.findall(text)}
#|    props = []
#|    for pm in PD_RE.finditer(text):
#|        b = pm.group(2)
#|        svc = re.search(r"\.identifiesControllerService\(\s*([\w.]+)\.class", b)
#|        av = re.search(r"\.allowableValues\(([^;]*?)\)\s*(?:\.|$)", b, re.S)
#|        values = []
#|        if av and ".class" not in av.group(1):
#|            for a in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", av.group(1)):
#|                a = a.strip()
#|                if a:
#|                    values.append(allowable.get(a) or allowable.get(a.split(".")[-1]) or _arg(a, consts))
#|        default = _call(b, "defaultValue", consts)
#|        dm = re.search(r"\.defaultValue\(\s*([\w.]+)\.getValue\(\)\s*\)", b)
#|        if dm:
#|            default = allowable.get(dm.group(1).split(".")[-1]) or default
#|        props.append({
#|            "field": pm.group(1), "name": _call(b, "name", consts), "displayName": _call(b, "displayName", consts),
#|            "description": _call(b, "description", consts) or "", "default": default,
#|            "required": bool(re.search(r"\.required\(\s*true", b)), "sensitive": bool(re.search(r"\.sensitive\(\s*true", b)),
#|            "el": bool(re.search(r"\.expressionLanguageSupported\(\s*(true|ExpressionLanguageScope\.(?!NONE))", b)),
#|            "service": svc.group(1) if svc else None, "allowable": [v for v in values if v],
#|            "line": _lineno(text, pm.start()),
#|        })
#|    rels = [{"field": rm.group(1), "name": _call(rm.group(2), "name", consts), "description": _call(rm.group(2), "description", consts) or "",
#|             "line": _lineno(text, rm.start())} for rm in REL_RE.finditer(text)]
#|    writes, dynamic = {}, False
#|    for m in PUT_ATTR_RE.finditer(text):
#|        v = _arg(m.group(1), consts)
#|        if v:
#|            writes.setdefault(v, _lineno(text, m.start()))
#|        else:
#|            dynamic = True
#|    for var in set(PUT_ALL_RE.findall(text)):
#|        for m in re.finditer(rf"\b{re.escape(var)}\s*\.\s*put\(\s*" + ARG + r"\s*,", text):
#|            v = _arg(m.group(1), consts)
#|            if v:
#|                writes.setdefault(v, _lineno(text, m.start()))
#|        if re.search(rf"\b{re.escape(var)}\s*\.\s*put\(\s*(?!\"|[A-Z][\w.]*\s*,|[\w.]+\.(?:key|getKey)\(\)\s*,)", text) or \
#|                re.search(rf"\b{re.escape(var)}\s*\.\s*putAll\(", text):
#|            dynamic = True
#|    if "putAllAttributes" in text and not PUT_ALL_RE.search(text):
#|        dynamic = True
#|    reads = {}
#|    for m in GET_ATTR_RE.finditer(text):
#|        v = _arg(m.group(1), consts)
#|        if v:
#|            reads.setdefault(v, _lineno(text, m.start()))
#|    removes = sorted({v for v in (_arg(m.group(1), consts) for m in REMOVE_ATTR_RE.finditer(text)) if v})
#|    return {"properties": props, "relationships": rels, "writes": writes, "reads": reads, "removes": removes, "dynamic_writes": dynamic}
#|
#|
#|def _jvm_file(text, package):
#|    """Classes (with annotations and super types), constants, members, I/O, log / exception messages of one JVM file."""
#|    consts = {}
#|    for name, v in CONST_RE.findall(text) + IFACE_CONST_RE.findall(text):
#|        consts.setdefault(name, REDACTED if SECRET_NAME.search(name) and v.startswith('"')
#|                          else _arg(v, {}) if not v.startswith('"') else _concat(v))
#|    for name, v in ENUM_CONST_RE.findall(text):
#|        consts.setdefault(name, v)
#|    classes = []
#|    for m in DECL_RE.finditer(text):
#|        mods, decl, name = m.group(1) or "", m.group(2), m.group(3)
#|        header = _header(text, m.start()) + text[m.start():m.start(1)]  # + same-line annotations
#|        cap = re.search(ANNOT_STR_RE.format("CapabilityDescription"), header, re.S)
#|        tags = TAGS_RE.search(header)
#|        req = INPUT_REQ_RE.search(header)
#|        dyn = []
#|        for d in DYNPROP_RE.findall(header):
#|            nm = re.search(r'name\s*=\s*"([^"]+)"', d)
#|            ds = re.search(r'description\s*=\s*((?:"(?:[^"\\]|\\.)*"\s*\+?\s*)+)', d)
#|            dyn.append({"name": nm.group(1) if nm else None, "description": _concat(ds.group(1)) if ds else ""})
#|        classes.append({
#|            "class": name, "fqcn": f"{package}.{name}" if package else name, "decl": decl, "line": _lineno(text, m.start(3)),
#|            "top_level": not text[m.start():m.start() + 1].isspace(),
#|            "extends": (m.group(4) or "").strip(), "implements": (m.group(5) or "").strip(), "abstract": "abstract" in mods or decl == "interface",
#|            "description": _concat(cap.group(1)) if cap else "",
#|            "tags": [_concat(t) for t in re.findall(r'"[^"]*"', tags.group(1))] if tags else [],
#|            "input_requirement": req.group(1) if req else None,
#|            "writes_attributes_doc": [{"name": a, "description": _concat(d) if d else ""} for a, d in WRITES_RE.findall(header)],
#|            "reads_attributes_doc": [{"name": a, "description": _concat(d) if d else ""} for a, d in READS_RE.findall(header)],
#|            "dynamic_properties": [d for d in dyn if d["name"] or d["description"]],
#|            "flags": [f for f in FLAG_ANNOTS if re.search(rf"@{f}\b", header)],
#|            "annotated": "@CapabilityDescription" in header or "@Tags" in header,
#|        })
#|    members = _members(text, consts) if classes else {}
#|    messages = []
#|    for m in MESSAGE_RE.finditer(text):
#|        messages.append({"level": m.group(1), "text": _template(m.group(2)), "line": _lineno(text, m.start())})
#|    for m in THROW_RE.finditer(text):
#|        messages.append({"level": m.group(1), "text": _template(m.group(2)), "line": _lineno(text, m.start())})
#|    messages = [msg for msg in messages if len(msg["text"].replace("{}", "").strip()) >= 4][:200]
#|    io = sorted(k for k, rx in IO_PATTERNS.items() if re.search(rx, text))
#|    return {"classes": classes, "consts": consts, "members": members, "messages": messages, "io": io, "components": []}
#|
#|
#|def scan_hardcoded(text, lang):
#|    """Find hardcoded URLs, JDBC strings, hosts, IPs, paths, secrets and SQL, with line numbers (secrets redacted)."""
#|    found, seen = [], set()
#|
#|    def add(kind, value, line_no, line, **extra):
#|        key = (kind, value, line_no)
#|        if key not in seen:
#|            seen.add(key)
#|            found.append({"kind": kind, "value": clip(value, 200), "line": line_no, "code": clip(redact_secrets(line.strip()), 160), **extra})
#|
#|    lines = text.splitlines()
#|    comment = {"python": "#", "shell": "#", "config": "#", "powershell": "#", "ruby": "#", "sql": "--"}.get(lang, "//")
#|    for i, line in enumerate(lines, 1):
#|        stripped = line.strip()
#|        if not stripped or stripped.startswith(comment) or stripped.startswith(("*", "/*", "import ", "package ")):
#|            continue
#|        for m in SECRET_ASSIGN_RE.finditer(line):
#|            value = m.group(2)
#|            if not re.fullmatch(r"[\w.\-]*\$\{.*\}|#\{.*\}|%\(.*|\{\w*\}|<.*>|\*+|changeme|password|secret|null|none|true|false", value, re.I):
#|                add("secret", f"{m.group(1)}={REDACTED}", i, line)
#|        for m in JDBC_RE.finditer(line):
#|            add("jdbc", m.group(0), i, line)
#|        for m in URL_RE.finditer(line):
#|            if "xmlns" not in line and "apache.org/licenses" not in line and "www.w3.org" not in m.group(0):
#|                add("s3" if m.group(0).lower().startswith("s3") else "url", m.group(0), i, line)
#|        for m in re.finditer(r"(?i)bucket\w*\s*(?:=|:|,|\()\s*[\"']([a-z0-9][a-z0-9.\-]{2,62})[\"']", line):
#|            add("s3", m.group(1), i, line)
#|        for m in IP_RE.finditer(line):
#|            if not re.search(r"(?i)version|0\.0\.0\.0|127\.0\.0\.1", line):
#|                add("ip", m.group(0), i, line)
#|        in_strings = " ".join(m.group(1) for m in re.finditer(r"[\"']([^\"']*)[\"']", line)) if lang != "config" else line
#|        for m in HOST_RE.finditer(in_strings):
#|            if not re.search(r"(?i)\.(java|py|class|jar|xml|json|csv|txt)$", m.group(0)) and not URL_RE.search(in_strings):
#|                add("host", m.group(0), i, line)
#|        for rx in (WIN_PATH_RE, UNIX_PATH_RE):
#|            for m in rx.finditer(in_strings):
#|                add("path", m.group(0).strip(), i, line)
#|    for stmt, line_no in _sql_literals(text, lang):
#|        tables = sqlparse.tables(stmt)
#|        if tables:
#|            add("sql", stmt, line_no, lines[line_no - 1] if line_no <= len(lines) else "", tables=tables)
#|    return found
#|
#|
#|def _sql_literals(text, lang):
#|    if lang == "sql":
#|        for m in re.finditer(r"[^;]+", text):
#|            if sqlparse.looks_like_sql(m.group(0)):
#|                yield m.group(0).strip(), _lineno(text, m.start() + len(m.group(0)) - len(m.group(0).lstrip()))
#|        return
#|    # string literals, including Java "a" + "b" concatenations and Python triple quotes
#|    for m in re.finditer(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'|((?:"(?:[^"\\\n]|\\.)*"\s*\+?\s*)+)|\'((?:[^\'\\\n]|\\.)*)\'', text, re.S):
#|        body = m.group(1) or m.group(2) or (_concat(m.group(3)) if m.group(3) else m.group(4)) or ""
#|        if sqlparse.looks_like_sql(body):
#|            yield body.strip(), _lineno(text, m.start())
#|
#|
#|SERVICE_KINDS = {"org.apache.nifi.processor.Processor": "PROCESSOR", "org.apache.nifi.controller.ControllerService": "CONTROLLER_SERVICE",
#|                 "org.apache.nifi.reporting.ReportingTask": "REPORTING_TASK"}
#|
#|
#|class CodeIndex:
#|    """All indexed files, with lookups by fully-qualified class name and by file name.
#|
#|    `finalize()` (after all files are added) resolves constants across files, walks class hierarchies so properties,
#|    relationships and attributes declared in abstract base classes reach the concrete components, applies the
#|    META-INF/services registrations and maps every component to its Maven module and the NAR module that packages it."""
#|
#|    def __init__(self, files=None):
#|        self.files = {}
#|        self.by_fqcn = {}
#|        self.by_basename = {}
#|        self.classes = {}      # fqcn -> (class info, path)
#|        self.modules = {}      # module dir -> pom info
#|        self.registered = {}   # fqcn -> {"kind", "path"}
#|        for info in files or []:
#|            self.add(info)
#|        if files:
#|            self.finalize()
#|
#|    def add(self, info):
#|        path = info["path"]
#|        self.files[path] = info
#|        self.by_basename.setdefault(Path(path).name.lower(), []).append(path)
#|        for c in info.get("classes") or []:
#|            self.classes.setdefault(c["fqcn"], (c, path))
#|        if info.get("lang") == "pom" and info.get("artifact"):
#|            self.modules[str(Path(path).parent)] = info["artifact"]
#|        if info.get("lang") == "services":
#|            kind = SERVICE_KINDS.get(Path(path).name)
#|            for fqcn in info.get("service_classes") or []:
#|                self.registered[fqcn] = {"kind": kind, "path": path}
#|
#|    # ------------------------------------------------------------------------------------------ resolution
#|    def finalize(self):
#|        self._consts()
#|        simple = {}
#|        for fqcn, (c, _) in self.classes.items():
#|            simple.setdefault(c["class"], []).append(fqcn)
#|        self.by_fqcn = {}
#|        for fqcn, (c, path) in sorted(self.classes.items()):
#|            if c["decl"] != "class" or (self.files.get(path) or {}).get("is_test"):
#|                continue
#|            chain = self._ancestors(fqcn, simple)
#|            supers = " ".join(x["extends"] + " " + x["implements"] for x, _ in [(c, path)] + chain)
#|            reg = self.registered.get(fqcn)
#|            if not (reg or c["annotated"] or any(b in supers for b in NIFI_BASES)):
#|                continue
#|            kind = (reg or {}).get("kind") or ("PROCESSOR" if "Processor" in supers else "CONTROLLER_SERVICE" if "Service" in supers
#|                                               else "REPORTING_TASK" if "ReportingTask" in supers else "COMPONENT")
#|            comp = self._component(c, path, chain, kind, reg)
#|            self.by_fqcn[fqcn] = [{"path": path, "line": c["line"], "component": comp}]
#|
#|    def _consts(self):
#|        table, by_simple = {}, {}
#|        for path, info in self.files.items():
#|            top = next((c for c in info.get("classes") or [] if c["top_level"]), None)
#|            for name, v in (info.get("consts") or {}).items():
#|                if top:
#|                    table[f"{top['class']}.{name}"] = v
#|                    table[f"{top['fqcn']}.{name}"] = v
#|                by_simple.setdefault(name, set()).add(v)
#|        self._const_table, self._const_simple = table, {k: next(iter(v)) for k, v in by_simple.items() if len(v) == 1}
#|
#|    def resolve(self, value):
#|        for _ in range(6):
#|            if not isinstance(value, str) or not value.startswith("@ref:"):
#|                return value
#|            ref = value[5:]
#|            parts = ref.split(".")
#|            value = (self._const_table.get(ref) or self._const_table.get(".".join(parts[-2:]))
#|                     or self._const_simple.get(parts[-1]))
#|        return None if isinstance(value, str) and value.startswith("@ref:") else value
#|
#|    def _ancestors(self, fqcn, simple):
#|        out, seen = [], {fqcn}
#|        c, _ = self.classes[fqcn]
#|        while c and c["extends"]:
#|            base = re.sub(r"<.*", "", c["extends"].split(",")[0]).strip()
#|            cands = [base] if base in self.classes else simple.get(base.split(".")[-1], [])
#|            pkg = c["fqcn"].rsplit(".", 1)[0]
#|            nxt = next((x for x in cands if x.startswith(pkg + ".")), cands[0] if len(cands) == 1 else None)
#|            if not nxt or nxt in seen:
#|                break
#|            seen.add(nxt)
#|            c, p = self.classes[nxt]
#|            out.append((c, p))
#|        return out
#|
#|    def _primary_members(self, c, path):
#|        """Member facts of a file belong to its first top-level class."""
#|        info = self.files.get(path) or {}
#|        top = next((x for x in info.get("classes") or [] if x["top_level"]), None)
#|        return (info.get("members") or {}) if top and top["fqcn"] == c["fqcn"] else {}
#|
#|    def _component(self, c, path, chain, kind, reg):
#|        props, rels, writes, reads, removes, io = {}, {}, {}, {}, set(), set()
#|        wdoc, rdoc, dyn, flags, dynamic = {}, {}, [], set(), False
#|        for depth, (cls, p) in enumerate([(c, path)] + chain):
#|            m = self._primary_members(cls, p)
#|            origin = None if depth == 0 else cls["class"]
#|            for pr in m.get("properties", []):
#|                pr = dict(pr, name=self.resolve(pr["name"]), displayName=self.resolve(pr["displayName"]),
#|                          description=self.resolve(pr["description"]) or "", default=self.resolve(pr["default"]),
#|                          allowable=[v for v in (self.resolve(a) for a in pr.get("allowable") or []) if v],
#|                          path=p, **({"from": origin} if origin else {}))
#|                props.setdefault(pr["name"] or pr["field"], pr)
#|            for r in m.get("relationships", []):
#|                r = dict(r, name=self.resolve(r["name"]), description=self.resolve(r["description"]) or "", path=p,
#|                         **({"from": origin} if origin else {}))
#|                rels.setdefault(r["name"] or r["field"], r)
#|            for a, line in (m.get("writes") or {}).items():
#|                a = self.resolve(a)
#|                if a:
#|                    writes.setdefault(a, f"{Path(p).name}:{line}")
#|            for a, line in (m.get("reads") or {}).items():
#|                a = self.resolve(a)
#|                if a:
#|                    reads.setdefault(a, f"{Path(p).name}:{line}")
#|            removes |= {x for x in (self.resolve(a) for a in m.get("removes") or []) if x}
#|            dynamic = dynamic or bool(m.get("dynamic_writes"))
#|            io |= set((self.files.get(p) or {}).get("io") or [])
#|            for w in cls["writes_attributes_doc"]:
#|                wdoc.setdefault(w["name"], w["description"])
#|            for r in cls["reads_attributes_doc"]:
#|                rdoc.setdefault(r["name"], r["description"])
#|            dyn += cls["dynamic_properties"]
#|            flags |= set(cls["flags"])
#|        described = next((x for x, _ in [(c, path)] + chain if x["description"]), c)
#|        module = self.module_of(path)
#|        return {
#|            "class": c["class"], "fqcn": c["fqcn"], "kind": kind, "line": c["line"], "extends": c["extends"], "implements": c["implements"],
#|            "abstract": c["abstract"], "ancestors": [x["fqcn"] for x, _ in chain], "description": described["description"],
#|            "super_chain": [re.sub(r"<.*", "", x["extends"]).strip() for x, _ in [(c, path)] + chain if x["extends"]],
#|            "tags": c["tags"] or next((x["tags"] for x, _ in chain if x["tags"]), []),
#|            "input_requirement": c["input_requirement"] or next((x["input_requirement"] for x, _ in chain if x["input_requirement"]), None),
#|            "registered": bool(reg), "registered_in": (reg or {}).get("path"),
#|            "properties": [v for v in props.values() if v.get("name")], "relationships": [v for v in rels.values() if v.get("name")],
#|            "writes_attributes": sorted(set(writes) | set(wdoc)), "writes_at": writes, "writes_attributes_doc": sorted(wdoc),
#|            "writes_doc": wdoc, "reads_attributes": sorted(set(reads) | set(rdoc)), "reads_at": reads, "reads_attributes_doc": sorted(rdoc),
#|            "removes_attributes": sorted(removes), "dynamic_writes": dynamic, "dynamic_properties": dyn, "flags": sorted(flags),
#|            "io": sorted(io), "module": module, "nar_modules": self.nar_modules_of(module),
#|        }
#|
#|    # -------------------------------------------------------------------------------------------- maven
#|    def module_of(self, path):
#|        p = Path(path).parent
#|        while True:
#|            info = self.modules.get(str(p))
#|            if info:
#|                return dict(info, dir=str(p))
#|            if p.parent == p:
#|                return None
#|            p = p.parent
#|
#|    def nar_modules_of(self, module):
#|        if not module or not module.get("artifactId"):
#|            return []
#|        return [dict(m, dir=d) for d, m in self.modules.items() if m.get("packaging") == "nar"
#|                and (module["artifactId"] in (m.get("dependencies") or []) or d == module.get("dir"))]
#|
#|    def implementers(self, api):
#|        """Concrete classes in the repos implementing a (custom) controller-service interface."""
#|        simple = api.rsplit(".", 1)[-1]
#|        return sorted(fqcn for fqcn, (c, path) in self.classes.items()
#|                      if c["decl"] == "class" and not c["abstract"] and not (self.files.get(path) or {}).get("is_test")
#|                      and simple in re.split(r"[\s,<>]+", c["implements"] + " " + c["extends"]))
#|
#|    def components(self):
#|        return [(fqcn, entries) for fqcn, entries in sorted(self.by_fqcn.items())]
#|
#|    def hardcoded(self):
#|        for path, info in sorted(self.files.items()):
#|            for h in info.get("hardcoded") or []:
#|                yield path, h
#@@ FILE nifikb/compare.py t fab72679d11a0281
#|"""Environment comparison ("works in UAT, fails in PROD"): two flows, and the config tables of two databases.
#|
#|Flows are matched by process-group path + component name + type (ids differ between environments); parameter contexts
#|by name. Config rows are matched by primary key (the metadata model of the current KB), masked on both sides.
#|[environments.<name>] in nifikb.toml gives an environment a flow_file and a db, so `compare --env uat` compares it with the
#|main configuration."""
#|from collections import Counter
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|from .analyze import Analysis, type_short
#|from .catalog import Catalog
#|from .code import CodeIndex
#|from .flow import load_flow
#|from .util import REDACTED, SECRET_NAME
#|
#|
#|def _flow_view(path, cfg):
#|    flow = load_flow(Path(path))
#|    an = Analysis(flow, Catalog(), CodeIndex(), cfg).run()
#|    comps, seen = {}, Counter()
#|    for c in list(flow.components.values()) + list(flow.services.values()):
#|        if c["kind"] not in ("PROCESSOR", "CONTROLLER_SERVICE", "INPUT_PORT", "OUTPUT_PORT"):
#|            continue
#|        base = f"{(flow.groups.get(c['group_id']) or {}).get('path', '(controller)')} :: {c['name']} [{type_short(c['type']) or c['kind'].lower()}]"
#|        seen[base] += 1
#|        key = base if seen[base] == 1 else f"{base} #{seen[base]}"
#|        props = {f["display"]: ("<sensitive>" if f["source"] == "sensitive" else f["resolved"]) for f in an.props[c["id"]]}
#|        comps[key] = {"state": c.get("state"), "schedule": f"{c.get('scheduling_strategy')} {c.get('scheduling_period')}"
#|                      if c["kind"] == "PROCESSOR" else None, "props": props, "auto": sorted(c.get("auto_terminated") or [])}
#|    params = {}
#|    for name, ctx in flow.param_contexts.items():
#|        for k, v in ctx["params"].items():
#|            params[f"{name} :: {k}"] = "<sensitive>" if v.get("sensitive") else (REDACTED if SECRET_NAME.search(k) else v.get("value"))
#|    return comps, params
#|
#|
#|def compare_flows(cfg, left, right, left_name="left", right_name="right", limit=300):
#|    lc, lp = _flow_view(left, cfg)
#|    rc, rp = _flow_view(right, cfg)
#|    out = []
#|    for k in sorted(set(lc) - set(rc)):
#|        out.append(f"only in {left_name}: {k}")
#|    for k in sorted(set(rc) - set(lc)):
#|        out.append(f"only in {right_name}: {k}")
#|    for k in sorted(set(lc) & set(rc)):
#|        a, b = lc[k], rc[k]
#|        for field in ("state", "schedule", "auto"):
#|            if a[field] != b[field]:
#|                out.append(f"{k}: {field} {a[field]} ({left_name}) vs {b[field]} ({right_name})")
#|        for p in sorted(set(a["props"]) | set(b["props"])):
#|            va, vb = a["props"].get(p), b["props"].get(p)
#|            if va != vb and "<sensitive>" not in (va, vb):
#|                out.append(f"{k}: '{p}' = {_v(va)} ({left_name}) vs {_v(vb)} ({right_name})")
#|    for k in sorted(set(lp) | set(rp)):
#|        va, vb = lp.get(k), rp.get(k)
#|        if va != vb and not (va == vb == "<sensitive>"):
#|            if k not in lp or k not in rp:
#|                out.append(f"parameter {k}: only in {left_name if k in lp else right_name}")
#|            elif "<sensitive>" not in (va, vb):
#|                out.append(f"parameter {k} = {_v(va)} ({left_name}) vs {_v(vb)} ({right_name})")
#|    return out[:limit] + ([f"… {len(out) - limit} more differences"] if len(out) > limit else [])
#|
#|
#|def _v(v):
#|    s = "∅" if v is None else str(v)
#|    return f"`{s if len(s) <= 120 else s[:119] + '…'}`"
#|
#|
#|def compare_config(cfg, store, left_db, right_db, key=None, left_name=None, right_name=None):
#|    """Row differences of the metadata config tables between two [[databases]] entries (optionally one file / feed)."""
#|    m = metamod.settings(cfg)
#|    model = store.get_meta("metadata_model")
#|    if not m or not model:
#|        return ["metadata not configured ([metadata] in nifikb.toml) - nothing to compare"]
#|    dbs = {d["name"]: d for d in cfg["databases"]}
#|    for name in (left_db, right_db):
#|        if name not in dbs:
#|            return [f"unknown database '{name}' - [[databases]] names: {', '.join(dbs)}"]
#|    st = model.get("structure_table")
#|    left = metamod.fetch_live(dbs[left_db], m, model)
#|    right = metamod.fetch_live(dbs[right_db], m, model)
#|    ids = None
#|    if key:
#|        found = metamod.dossier(model, metamod.Rows(left), key)["definitions"] or metamod.dossier(model, metamod.Rows(right), key)["definitions"]
#|        ids = [d["id"] for d in found]
#|        if not ids:
#|            return [f"'{key}' matches no definition in either database"]
#|    if st:
#|        if ids is not None:
#|            left[st] = metamod.fetch_structure(dbs[left_db], model, ids)
#|            right[st] = metamod.fetch_structure(dbs[right_db], model, ids)
#|        else:
#|            left[st] = metamod.fetch_rows(dbs[left_db], m, {**model, "tables": {st: model["tables"][st]}}, log=lambda _m: None).get(st, [])
#|            right[st] = metamod.fetch_rows(dbs[right_db], m, {**model, "tables": {st: model["tables"][st]}}, log=lambda _m: None).get(st, [])
#|    changes = metamod.diff_rows(model, left, right)
#|    if ids is not None:
#|        wanted = {str(i) for i in ids}
#|        changes = [c for c in changes if c["link"] in wanted]
#|    ln, rn = left_name or left_db, right_name or right_db
#|    lines = [c["change"].replace(" added:", f" only in {rn}:").replace(" removed", f" only in {ln}") for c in changes]
#|    return [f"differences {ln} → {rn} (rows matched by primary key; secret columns not compared):"] + (lines or ["none"])
#|
#|
#|def environment(cfg, name):
#|    envs = cfg.get("environments") or {}
#|    if name not in envs:
#|        raise ValueError(f"no [environments.{name}] in nifikb.toml (known: {', '.join(envs) or 'none'})")
#|    return envs[name]
#@@ FILE nifikb/config.py tc 061d778e5653e461
#|"""Configuration: nifikb.toml - the only file to edit (paths are relative to it; secrets come from env vars or files)."""
#|import os
#|import tomllib
#|from pathlib import Path
#|
#|PROJECT_DIR = Path(__file__).resolve().parent.parent
#|
#|TEMPLATE = """# =====================================================================================================================
#|# nifikb configuration - the ONLY file you edit.
#|#   * Paths may be absolute or relative to this file; ${{VARS}} are expanded.
#|#   * No secrets in here: passwords come from an environment variable (password_env) or a protected file
#|#     (password_file, chmod 600 on Linux).
#|#   * After editing:  python -m nifikb build   then   python -m nifikb doctor
#|# =====================================================================================================================
#|
#|db_refresh_hours = 24                    # how often table schemas are re-read (build --refresh-db forces it)
#|
#|# ---- 1. NiFi -------------------------------------------------------------------------------------------------------
#|[nifi]
#|home = "{home}"                 # NiFi install folder: conf/flow.json.gz, lib/*.nar and logs/ are read from here
#|# flow_file = "copies/flow.json.gz"      # or a copied flow file, when NiFi runs on another machine
#|extra_nar_dirs = []                      # folders with custom NARs that are not in <home>/lib
#|
#|[logs]                                   # nifi-app*.log / nifi-bootstrap*.log - read incrementally, only warnings / errors kept
#|# dirs = ["/opt/nifi/logs"]              # default: <home>/logs
#|keep_days = 14                           # keep this many days of events (counted back from the newest one)
#|# initial_tail_mb = 200                  # first run on a huge log: only read its last N MB
#|
#|# [nifi_api]                             # optional, read-only: provenance ("where was my file dropped, why") + live bulletins
#|# url = "https://nifi-host:8443/nifi-api"
#|# username = "readonly_user"             # needs the NiFi policies "query provenance" + "view provenance"
#|# password_env = "NIFIKB_NIFI_PASSWORD"  # or: password_file = "~/.nifikb/nifi.pw"
#|# ca_cert = "/etc/pki/nifi-ca.pem"       # CA of NiFi's certificate;  verify_ssl = false only for a quick test
#|# client_cert = "me.pem"                 # instead of username / password when NiFi uses client certificates
#|# client_key = "me.key"
#|# token_env = "NIFIKB_NIFI_TOKEN"        # or a pre-issued bearer token (Kerberos / OIDC setups)
#|
#|# [registry]                             # optional, read-only: NiFi Registry version history (who changed a versioned flow, when, why)
#|# url = "https://registry-host:18443/nifi-registry-api"
#|# username = "readonly_user"
#|# password_env = "NIFIKB_REGISTRY_PASSWORD"
#|# ca_cert = "/etc/pki/nifi-ca.pem"
#|
#|# ---- 2. Code -------------------------------------------------------------------------------------------------------
#|[code]
#|repos = []                               # Bitbucket clones: custom NAR projects (Maven / Java), scripts, Spark job scripts
#|
#|# ---- 3. Databases (read-only users only) ---------------------------------------------------------------------------
#|# One block per database. The flow's DBCP connection pools are matched by host + port + database of their JDBC URL.
#|# [[databases]]
#|# name = "metadata"
#|# kind = "mariadb"                       # mariadb | mysql | postgres | sqlite
#|# host = "db-host"
#|# port = 3306
#|# database = "nifi_meta"
#|# user = "readonly_user"
#|# password_env = "NIFIKB_DB_PASSWORD"    # or: password_file = "~/.nifikb/db.pw"
#|# include_tables = []                    # also document these tables (SQL LIKE / glob patterns, e.g. "file_%")
#|# profile_tables = []                    # list distinct values of low-cardinality text columns (status, source, ...)
#|# sample_rows = 0                        # >0 adds a few masked sample rows per table
#|
#|# ---- 4. Metadata config tables (OBJ_DEFINITION, OBJ_STRUCTURE, feed / API / server config, ...) --------------------
#|# Enables `diagnose` / `investigate` by file / feed / table, a masked snapshot of the config rows, their change history,
#|# and definition checks. Roles and relations are auto-detected: kb/metadata.md shows what was detected - override only
#|# what is wrong.
#|# [metadata]
#|# db = "metadata"                        # the [[databases]] name that holds the config tables
#|# target_db = "none"                     # loads go to HDFS / S3 files: no target-table checks. Or the [[databases]] name
#|#                                        #   holding the load tables, to check definitions against them.
#|# tables = ["OBJ_%", "%_CONFIG", "%_CONFIG_%", "%_DEFINITION", "%_STRUCTURE", "%_METADATA%"]   # which tables are config
#|# refresh_hours = 1                      # re-read the config rows (and record row changes) at most this often
#|# snapshot_max_rows = 20000              # rows per config table kept (masked); structure table: structure_max_rows
#|# --- overrides, only if kb/metadata.md shows a wrong guess:
#|# definition_table = "OBJ_DEFINITION"    # one row per file / object
#|# definition_id = "OBJ_ID"
#|# definition_keys = ["FILE_NAME", "TABLE_NAME"]   # what file / table names are matched against (patterns *, %, YYYYMMDD, regex)
#|# definition_target = "TABLE_NAME"       # the table a file is loaded into
#|# definition_location = "HDFS_PATH"      # the HDFS / S3 location it is written to
#|# structure_table = "OBJ_STRUCTURE"      # one row per column of a definition
#|# structure_parent = "OBJ_ID"
#|# structure_field = "COL_NAME"
#|# structure_type = "DATA_TYPE"
#|# structure_order = "COL_SEQ"
#|# structure_length = "COL_LENGTH"
#|# structure_nullable = "NULLABLE_FLAG"   # a column named like MANDATORY / REQUIRED / NOT_NULL is read as "required"
#|# structure_path = "JSON_PATH"           # JSON path per column for API / JSON feeds ($.data[*].customer.name)
#|# [[metadata.relations]]                 # joins that are not declared as foreign keys
#|# child = "SOURCE_FEED_CONFIG.OBJ_ID"
#|# parent = "OBJ_DEFINITION.OBJ_ID"
#|
#|# ---- 5. Target storage, ticket system, other environments (all optional, all read-only) ----------------------------
#|# [targets]                             # read-only look at what loads wrote (investigate / target): listings + Parquet footer
#|# location_template = "s3://datalake/raw/{{table_lower}}/"   # when OBJ_DEFINITION has no location column: where {{table}} lands
#|# hdfs_url = "https://namenode:9871/webhdfs/v1"   # WebHDFS for hdfs:// and /paths (or leave out to use the `hdfs` CLI)
#|# hdfs_user = "nifikb"                   # simple auth; or kerberos = true (uses `curl --negotiate` with the kinit ticket)
#|# s3_profile = "readonly"                # aws CLI / boto3 profile; s3_endpoint / s3_region for S3-compatible stores
#|# max_download_mb = 200                  # hdfs CLI only: largest file copied to read its Parquet schema
#|
#|# [tickets]                             # Jira / ServiceNow: `ticket <id>` reads it, investigates, drafts a reply
#|# kind = "servicenow"                    # or "jira"
#|# url = "https://acme.service-now.com"   # Jira: "https://acme.atlassian.net" or the Jira Server base URL
#|# username = "nifikb.integration"        # Jira Cloud: the account e-mail (with token_env = API token)
#|# password_env = "NIFIKB_TICKET_PASSWORD"   # or token_env (Jira Server PAT / OAuth token, sent as Bearer when no username)
#|# table = "incident"                     # ServiceNow table
#|# note_field = "work_notes"              # ServiceNow: where --post writes (work_notes = internal)
#|
#|# [environments.uat]                     # other environments for `compare --env uat` ("works in UAT, fails in PROD")
#|# flow_file = "copies/uat/flow.json.gz"  # its flow (copy it over; read-only)
#|# db = "metadata_uat"                    # the [[databases]] name holding its config tables (read-only user)
#|
#|# ---- 6. Load audit, daily report, web page -------------------------------------------------------------------------
#|# [audit]                                # the platform's per-file load log: investigate shows the last load of a file
#|# db = "metadata"                        # [[databases]] name (default: the metadata db)
#|# table = "FILE_LOAD_AUDIT"              # auto-detected (a table named like *audit* / *load_log* with a file-name column)
#|# file_column = "FILE_NAME"              # overrides, only if kb/INDEX / doctor shows a wrong guess:
#|# status_column = "LOAD_STATUS"
#|# time_column = "LOAD_TS"
#|# error_column = "ERROR_MSG"
#|# rows_column = "ROW_COUNT"
#|# link_column = "OBJ_ID"                 # the definition id, to list all loads of one definition
#|
#|# [report]                               # python -m nifikb report --send (e.g. scheduled daily)
#|# email_to = ["nifi-team@company.com"]
#|# email_from = "nifikb@company.com"
#|# smtp_host = "smtp.company.com"
#|# smtp_port = 25
#|# smtp_starttls = false
#|# smtp_user = ""                         # + smtp_password_env / smtp_password_file when the relay needs a login
#|# webhook_url_env = "NIFIKB_WEBHOOK"     # Teams / Slack incoming-webhook URL (kept out of this file)
#|
#|# [web]                                  # python -m nifikb web - self-service page for colleagues (read-only)
#|# host = "127.0.0.1"                     # "0.0.0.0" to reach it from other machines (then set a login)
#|# port = 8765
#|# user = "support"                       # HTTP basic login shared by the team
#|# password_env = "NIFIKB_WEB_PASSWORD"   # or password_file
#|
#|# ---- 7. Where things are written -----------------------------------------------------------------------------------
#|[output]
#|dir = "kb"                               # generated knowledge base (markdown + kb.sqlite) - rebuilt, never edited by hand
#|
#|[knowledge]
#|dir = "knowledge"                        # team context + learnings written by people and agents - kept, commit it to git
#|"""
#|
#|
#|def find_config(path=None):
#|    candidates = [path, os.environ.get("NIFIKB_CONFIG"), Path.cwd() / "nifikb.toml", PROJECT_DIR / "nifikb.toml"]
#|    for c in candidates:
#|        if c and Path(c).is_file():
#|            return Path(c).resolve()
#|    raise FileNotFoundError("nifikb.toml not found (run `python -m nifikb init` or pass --config)")
#|
#|
#|def load_config(path=None):
#|    path = find_config(path)
#|    with open(path, "rb") as f:
#|        cfg = tomllib.load(f)
#|    base = path.parent
#|
#|    def rel(p):
#|        p = Path(os.path.expanduser(os.path.expandvars(str(p))))
#|        return str(p if p.is_absolute() else (base / p).resolve())
#|
#|    for section in ("nifi", "output", "code", "logs", "knowledge"):
#|        cfg.setdefault(section, {})
#|    cfg.setdefault("databases", [])
#|    # an older layout put db_refresh_hours below [code], where TOML files it under code
#|    if "db_refresh_hours" not in cfg and "db_refresh_hours" in cfg["code"]:
#|        cfg["db_refresh_hours"] = cfg["code"].pop("db_refresh_hours")
#|    if cfg["nifi"].get("home"):
#|        cfg["nifi"]["home"] = rel(cfg["nifi"]["home"])
#|    if cfg["nifi"].get("flow_file"):
#|        cfg["nifi"]["flow_file"] = rel(cfg["nifi"]["flow_file"])
#|    cfg["nifi"]["extra_nar_dirs"] = [rel(p) for p in cfg["nifi"].get("extra_nar_dirs", [])]
#|    cfg["output"]["dir"] = rel(cfg["output"].get("dir", "kb"))
#|    cfg["knowledge"]["dir"] = rel(cfg["knowledge"].get("dir", "knowledge"))
#|    cfg["code"]["repos"] = [rel(p) for p in cfg["code"].get("repos", [])]
#|    if cfg["logs"].get("dirs"):
#|        cfg["logs"]["dirs"] = [rel(p) for p in cfg["logs"]["dirs"]]
#|    for d in cfg["databases"]:
#|        if d.get("kind") == "sqlite" and d.get("database"):
#|            d["database"] = rel(d["database"])
#|        if d.get("password_file"):
#|            d["password_file"] = rel(d["password_file"])
#|        d.setdefault("name", d.get("database", "db"))
#|    for key in ("nifi_api", "registry", "targets", "tickets"):
#|        api = cfg.get(key)
#|        if not api:
#|            continue
#|        for k in ("password_file", "token_file", "ca_cert", "client_cert", "client_key", "client_key_password_file"):
#|            if api.get(k):
#|                api[k] = rel(api[k])
#|    for env in (cfg.get("environments") or {}).values():
#|        if isinstance(env, dict) and env.get("flow_file"):
#|            env["flow_file"] = rel(env["flow_file"])
#|    for key in ("web", "report"):
#|        for k in ("password_file", "smtp_password_file", "webhook_url_file"):
#|            if (cfg.get(key) or {}).get(k):
#|                cfg[key][k] = rel(cfg[key][k])
#|    if not cfg["nifi"].get("home") and not cfg["nifi"].get("flow_file"):
#|        raise ValueError(f"{path}: set [nifi] home or flow_file")
#|    cfg["_path"] = str(path)
#|    return cfg
#|
#|
#|def write_template(path, nifi_home):
#|    path = Path(path)
#|    if path.exists():
#|        raise FileExistsError(f"{path} already exists")
#|    path.write_text(TEMPLATE.format(home=str(nifi_home).replace("\\", "/")), encoding="utf-8")
#|    return path
#@@ FILE nifikb/content.py tc dab3483caf40eb70
#|"""Content validation of a sample file against the structure rows: not only the header, every row.
#|
#|Most "metadata" tickets are data-vs-metadata problems: a delimiter inside a value shifting the columns, an empty
#|mandatory field, text in a numeric column, a date in another format, a value longer than the column, a file that is not
#|UTF-8. This reads a sample (CSV / delimited text or JSON) and reports each problem with counts and the first examples.
#|"""
#|import csv
#|import io
#|import re
#|from datetime import datetime
#|from pathlib import Path
#|
#|from . import metadata as metamod
#|
#|DELIM_COL = re.compile(r"(?i)delim|separator|(^|_)sep$|field_?sep")
#|DELIM_NAMES = {"TAB": "\t", "\\T": "\t", "PIPE": "|", "COMMA": ",", "SEMICOLON": ";", "CARET": "^", "TILDE": "~", "SPACE": " "}
#|DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f", "%Y/%m/%d",
#|                "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%m/%d/%Y %H:%M", "%d.%m.%Y", "%Y%m%d", "%Y%m%d%H%M%S", "%d-%b-%Y", "%d-%b-%y",
#|                "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")
#|NUMBER_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")
#|INT_RE = re.compile(r"^[+-]?\d+$")
#|MAX_ROWS = 20000
#|EXAMPLES = 3
#|
#|
#|def delimiter_for(model, def_row, related_rows, sample_text):
#|    """The configured delimiter (a DELIMITER-like column on the definition or a linked row), else sniffed."""
#|    for r in [def_row] + [x for rs in (related_rows or {}).values() for x in rs]:
#|        for c, v in r.items():
#|            if DELIM_COL.search(c) and isinstance(v, str) and v:
#|                v = DELIM_NAMES.get(v.strip().upper(), v)
#|                v = {"\\t": "\t", "\\u0001": "\x01", "\\x01": "\x01"}.get(v, v)
#|                return v, f"configured in {c}"
#|    try:
#|        return csv.Sniffer().sniff(sample_text[:20000], delimiters=",|\t;~^").delimiter, "detected"
#|    except csv.Error:
#|        return ",", "default"
#|
#|
#|def read_text(path):
#|    """(text, notes): UTF-8 with a fallback, noting a BOM, non-UTF-8 bytes and mixed line endings."""
#|    raw = Path(path).read_bytes()[:50_000_000]
#|    notes = []
#|    if raw.startswith(b"\xef\xbb\xbf"):
#|        notes.append({"severity": "warn", "kind": "data-encoding",
#|                      "message": "file starts with a UTF-8 byte-order mark (BOM): the first header can become '\\ufeffNAME' and not match"})
#|    try:
#|        text = raw.decode("utf-8-sig")
#|    except UnicodeDecodeError as e:
#|        text = raw.decode("cp1252", errors="replace")
#|        notes.append({"severity": "error", "kind": "data-encoding",
#|                      "message": f"file is not valid UTF-8 (first bad byte at offset {e.start}); it looks like Windows-1252 / Latin-1 - "
#|                                 "accented characters will be garbled or rejected"})
#|    crlf, lf = raw.count(b"\r\n"), raw.count(b"\n")
#|    if crlf and lf - crlf > 1:
#|        notes.append({"severity": "warn", "kind": "data-encoding", "message": f"mixed line endings ({crlf} CRLF, {lf - crlf} LF)"})
#|    return text, notes
#|
#|
#|def _is_date(v):
#|    v = v.strip()
#|    for fmt in DATE_FORMATS:
#|        try:
#|            datetime.strptime(v, fmt)
#|            return True
#|        except ValueError:
#|            continue
#|    return False
#|
#|
#|class _Col:
#|    def __init__(self, field):
#|        self.f = field
#|        self.problems = {}  # kind -> [count, examples]
#|
#|    def hit(self, kind, row_no, value):
#|        entry = self.problems.setdefault(kind, [0, []])
#|        entry[0] += 1
#|        if len(entry[1]) < EXAMPLES:
#|            entry[1].append(f"row {row_no}: {str(value)[:40]!r}")
#|
#|    def check(self, row_no, value):
#|        f = self.f
#|        v = "" if value is None else str(value)
#|        if v.strip() == "":
#|            if f.get("nullable") is False:
#|                self.hit("data-mandatory", row_no, v)
#|            return
#|        family = metamod.type_family(f.get("type"))
#|        if family == "numeric":
#|            s = v.strip().replace(",", "") if re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", v.strip()) else v.strip()
#|            if not NUMBER_RE.match(s):
#|                self.hit("data-type", row_no, v)
#|            elif re.search(r"(?i)int|long|short|byte|serial", str(f.get("type"))) and not INT_RE.match(s):
#|                self.hit("data-type", row_no, v)
#|        elif family == "temporal" and not _is_date(v):
#|            self.hit("data-date", row_no, v)
#|        elif family == "bool" and v.strip().lower() not in ("true", "false", "0", "1", "y", "n", "yes", "no", "t", "f"):
#|            self.hit("data-type", row_no, v)
#|        if f.get("length") and len(v) > f["length"]:
#|            self.hit("data-length", row_no, v)
#|
#|    def issues(self, total):
#|        labels = {"data-mandatory": ("error", "is empty but mandatory"), "data-type": ("error", f"is not a valid {self.f.get('type')}"),
#|                  "data-date": ("error", f"is not a recognisable date / time ({self.f.get('type')})"),
#|                  "data-length": ("error", f"is longer than {self.f.get('length')} characters")}
#|        out = []
#|        for kind, (n, ex) in self.problems.items():
#|            sev, what = labels[kind]
#|            out.append({"severity": sev, "kind": kind,
#|                        "message": f"'{self.f['name']}' {what} in {n} of {total} rows (e.g. {'; '.join(ex)})"})
#|        return out
#|
#|
#|def _rows(text, delim, max_rows):
#|    out = []
#|    for i, row in enumerate(csv.reader(io.StringIO(text), delimiter=delim)):
#|        if i > max_rows:
#|            break
#|        if row and any(c.strip() for c in row):
#|            out.append((i + 1, row))
#|    return out
#|
#|
#|def validate_csv(fields, path, model=None, def_row=None, related=None, max_rows=MAX_ROWS):
#|    text, issues = read_text(path)
#|    delim, how = delimiter_for(model or {}, def_row or {}, related, text)
#|    rows = _rows(text, delim, max_rows)
#|    if rows and len(rows[0][1]) == 1 and len(fields) > 1:  # wrong delimiter: find the one the file really uses
#|        for cand in ",|\t;~^\x01":
#|            if cand != delim and len(rows[0][1][0].split(cand)) >= 2:
#|                issues.append({"severity": "error", "kind": "data-delimiter",
#|                               "message": f"the file is delimited by {cand!r}, but the delimiter is {delim!r} ({how}) - every row "
#|                                          "reads as a single column. Checked below with the file's own delimiter.",
#|                               "data": {"delimiter": cand, "column": how[len("configured in "):] if how.startswith("configured in ") else None}})
#|                delim, how, rows = cand, "found in the file", _rows(text, cand, max_rows)
#|                break
#|    if not rows:
#|        return issues + [{"severity": "error", "kind": "data-empty", "message": "the sample has no rows"}], {"delimiter": delim}
#|    names = {f["name"].lower(): f for f in fields}
#|    squash = {re.sub(r"[^a-z0-9]", "", k): f for k, f in names.items()}
#|    header = rows[0][1]
#|    matched = sum(1 for h in header if h.strip().lower() in names or re.sub(r"[^a-z0-9]", "", h.lower()) in squash)
#|    has_header = matched >= max(1, len(header) // 2)
#|    info = {"delimiter": delim, "delimiter_source": how, "header": has_header, "rows": len(rows) - (1 if has_header else 0),
#|            "header_row": [h.strip() for h in header] if has_header else None}
#|    if has_header:
#|        cols = [names.get(h.strip().lower()) or squash.get(re.sub(r"[^a-z0-9]", "", h.lower())) for h in header]
#|        data, width = rows[1:], len(header)
#|    else:
#|        ordered = sorted(fields, key=lambda f: (f["seq"] is None, f["seq"] or 0))
#|        cols, data, width = ordered, rows, len(ordered)
#|        if len(header) != len(ordered):
#|            issues.append({"severity": "error", "kind": "data-width",
#|                           "message": f"no header row and {len(header)} columns in row 1, but the structure has {len(ordered)} fields"})
#|    bad_width, examples = 0, []
#|    checkers = [_Col(f) if f else None for f in cols]
#|    for row_no, row in data:
#|        if len(row) != width:
#|            bad_width += 1
#|            if len(examples) < EXAMPLES:
#|                examples.append(f"row {row_no} has {len(row)}")
#|            continue
#|        for chk, value in zip(checkers, row):
#|            if chk:
#|                chk.check(row_no, value)
#|    if bad_width:
#|        issues.append({"severity": "error", "kind": "data-width",
#|                       "message": f"{bad_width} of {len(data)} rows do not have {width} columns ({'; '.join(examples)}) - a delimiter or "
#|                                  "line break inside a value, or unbalanced quotes"})
#|    for chk in checkers:
#|        if chk:
#|            issues += chk.issues(len(data))
#|    return issues, info
#|
#|
#|def validate_json(fields, records, root=None, max_rows=MAX_ROWS):
#|    """records: the list below the root path. Fields compared by (dotted) path relative to the root."""
#|    issues, total = [], 0
#|    prefix = metamod.json_path(root) + "." if root and metamod.json_path(root) else ""
#|
#|    def rel(f):
#|        p = metamod.json_path(f.get("path") or f["name"])
#|        return p[len(prefix):] if prefix and p.startswith(prefix) else p
#|
#|    checkers = {rel(f): _Col(f) for f in fields}
#|    missing = {k: 0 for k in checkers}
#|    for i, rec in enumerate(records[:max_rows], 1):
#|        if not isinstance(rec, dict):
#|            continue
#|        total += 1
#|        flat = _flatten_values(rec)
#|        for path, chk in checkers.items():
#|            key = next((k for k in flat if k.lower() == path.lower() or k.lower().endswith("." + path.lower())), None)
#|            if key is None:
#|                missing[path] += 1
#|                if chk.f.get("nullable") is False:
#|                    chk.hit("data-mandatory", i, "<missing>")
#|                continue
#|            chk.check(i, flat[key])
#|    for path, n in missing.items():
#|        if 0 < n < total and checkers[path].f.get("nullable") is not False:
#|            issues.append({"severity": "warn", "kind": "data-missing", "message": f"'{path}' is missing in {n} of {total} records"})
#|    for chk in checkers.values():
#|        issues += chk.issues(total)
#|    return issues, {"records": total}
#|
#|
#|def _flatten_values(rec, prefix=""):
#|    out = {}
#|    for k, v in rec.items():
#|        p = f"{prefix}.{k}" if prefix else str(k)
#|        if isinstance(v, dict):
#|            out.update(_flatten_values(v, p))
#|        elif isinstance(v, list) and v and isinstance(v[0], dict):
#|            out.update(_flatten_values(v[0], p))
#|        else:
#|            out[p] = v
#|    return out
#|
#|
#|def json_records(data, root):
#|    """All records below the root path (not only the first)."""
#|    node = data
#|    for part in [p for p in re.split(r"\.|/|\[[^\]]*\]", re.sub(r"^\$", "", root or "")) if p]:
#|        if isinstance(node, list):
#|            node = next((x for x in node if isinstance(x, dict)), {})
#|        node = node.get(part, {}) if isinstance(node, dict) else {}
#|    if isinstance(node, list):
#|        return [x for x in node if isinstance(x, dict)]
#|    return [node] if isinstance(node, dict) and node else []
#@@ FILE nifikb/db.py tc 90d10e93241bee86
#|"""Read-only database access: schema introspection for the tables the flow/code touch, and guarded ad-hoc SELECTs.
#|
#|Drivers are optional and imported lazily:
#|  mariadb / mysql -> pymysql   (pip install pymysql)
#|  postgres        -> psycopg2  or pg8000
#|  sqlite          -> stdlib (used by tests and for local files)
#|"""
#|import fnmatch
#|import os
#|import re
#|import sqlite3
#|
#|from .util import REDACTED, SECRET_NAME, redact_secrets
#|
#|MASK_COLUMNS = re.compile(r"(?i)pass|pwd|secret|token|ssn|aadhaar|pan_?no|card|cvv|email|phone|mobile|dob|birth|salary|account_?no|iban")
#|MASK_EXTRA = re.compile(r"(?i)authorization|auth_?(token|header|value|key)|passphrase|private|cert|keystore|truststore|credential")
#|BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{8,}")
#|
#|
#|def sensitive_column(name):
#|    name = str(name)
#|    return bool(MASK_COLUMNS.search(name) or SECRET_NAME.search(name) or MASK_EXTRA.search(name))
#|
#|
#|def mask_value(column, value):
#|    """Masked form of one value read from a database: sensitive columns become ***, secrets inside text are redacted."""
#|    if value is None:
#|        return None
#|    if sensitive_column(column):
#|        return "***"
#|    if isinstance(value, str):
#|        return BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(value))
#|    return value
#|READ_ONLY_SQL = re.compile(r"(?is)^\s*(select|with|show|describe|desc|explain)\b")
#|WRITE_WORDS = re.compile(r"(?i)\b(insert|update|delete|merge|replace|create|alter|drop|truncate|grant|revoke|call|exec|execute|lock|load|into\s+outfile|set\s+global)\b")
#|
#|
#|class DbError(Exception):
#|    pass
#|
#|
#|def connect(cfg):
#|    kind = (cfg.get("kind") or "mariadb").lower()
#|    password = cfg.get("password")
#|    if cfg.get("password_env"):
#|        password = os.environ.get(cfg["password_env"], password)
#|    if not password and cfg.get("password_file"):
#|        try:
#|            with open(cfg["password_file"], encoding="utf-8") as f:
#|                password = f.read().strip()
#|        except OSError as e:
#|            raise DbError(f"cannot read password_file of {cfg.get('name')}: {e}") from e
#|    try:
#|        if kind in ("mariadb", "mysql"):
#|            try:
#|                import pymysql
#|            except ImportError as e:
#|                raise DbError("MariaDB/MySQL needs the 'pymysql' package: pip install pymysql") from e
#|            conn = pymysql.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 3306)), user=cfg.get("user"),
#|                                   password=password or "", database=cfg.get("database"), connect_timeout=int(cfg.get("timeout", 10)),
#|                                   read_timeout=int(cfg.get("query_timeout", 60)), charset="utf8mb4")
#|            with conn.cursor() as cur:
#|                cur.execute("SET SESSION TRANSACTION READ ONLY")
#|            return conn, "mysql"
#|        if kind in ("postgres", "postgresql"):
#|            try:
#|                import psycopg2
#|                conn = psycopg2.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)), user=cfg.get("user"),
#|                                        password=password, dbname=cfg.get("database"), connect_timeout=int(cfg.get("timeout", 10)),
#|                                        options="-c default_transaction_read_only=on -c statement_timeout=%d" % (int(cfg.get("query_timeout", 60)) * 1000))
#|            except ImportError:
#|                try:
#|                    import pg8000.dbapi as pg8000
#|                except ImportError as e:
#|                    raise DbError("PostgreSQL needs 'psycopg2-binary' or 'pg8000': pip install pg8000") from e
#|                conn = pg8000.connect(host=cfg.get("host", "localhost"), port=int(cfg.get("port", 5432)), user=cfg.get("user"),
#|                                      password=password, database=cfg.get("database"), timeout=int(cfg.get("timeout", 10)))
#|                cur = conn.cursor()
#|                cur.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
#|            return conn, "postgres"
#|        if kind == "sqlite":
#|            return sqlite3.connect(f"file:{cfg['database']}?mode=ro", uri=True), "sqlite"
#|    except DbError:
#|        raise
#|    except Exception as e:  # driver specific connection errors
#|        raise DbError(f"cannot connect to {cfg.get('name')}: {type(e).__name__}: {e}") from e
#|    raise DbError(f"unsupported database kind '{kind}'")
#|
#|
#|def _rows(conn, sql, params=()):
#|    cur = conn.cursor()
#|    cur.execute(sql, params)
#|    cols = [d[0] for d in cur.description] if cur.description else []
#|    return [dict(zip(cols, r)) for r in cur.fetchall()]
#|
#|
#|def _ph(dialect):
#|    return "?" if dialect == "sqlite" else "%s"
#|
#|
#|def list_tables(conn, dialect, schemas):
#|    if dialect == "sqlite":
#|        return [{"schema": "main", "table": r["name"], "type": r["type"].upper(), "rows": None, "comment": ""}
#|                for r in _rows(conn, "SELECT name, type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
#|    ph = ",".join([_ph(dialect)] * len(schemas))
#|    if dialect == "mysql":
#|        sql = (f"SELECT TABLE_SCHEMA AS s, TABLE_NAME AS t, TABLE_TYPE AS ty, TABLE_ROWS AS n, TABLE_COMMENT AS c "
#|               f"FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ({ph})")
#|    else:
#|        sql = (f"SELECT t.table_schema AS s, t.table_name AS t, t.table_type AS ty, c.reltuples::bigint AS n, "
#|               f"obj_description(c.oid) AS c FROM information_schema.tables t "
#|               f"LEFT JOIN pg_catalog.pg_namespace ns ON ns.nspname = t.table_schema "
#|               f"LEFT JOIN pg_catalog.pg_class c ON c.relname = t.table_name AND c.relnamespace = ns.oid "
#|               f"WHERE t.table_schema IN ({ph})")
#|    return [{"schema": r["s"], "table": r["t"], "type": r["ty"], "rows": r["n"], "comment": r["c"] or ""}
#|            for r in _rows(conn, sql, tuple(schemas))]
#|
#|
#|def describe_table(conn, dialect, schema, table):
#|    if dialect == "sqlite":
#|        cols = [{"name": r["name"], "type": r["type"], "nullable": not r["notnull"], "key": "PRI" if r["pk"] else "",
#|                 "default": r["dflt_value"], "extra": "", "comment": ""} for r in _rows(conn, f'PRAGMA table_info("{table}")')]
#|        fks = [{"column": r["from"], "ref": f"{r['table']}.{r['to']}"} for r in _rows(conn, f'PRAGMA foreign_key_list("{table}")')]
#|        idx = [{"name": r["name"], "unique": bool(r["unique"]),
#|                "columns": [c["name"] for c in _rows(conn, f'PRAGMA index_info("{r["name"]}")')]}
#|               for r in _rows(conn, f'PRAGMA index_list("{table}")')]
#|        idx.sort(key=lambda i: (i["name"].upper() != "PRIMARY", i["name"]))
#|        return {"columns": cols, "foreign_keys": fks, "indexes": idx}
#|    p = _ph(dialect)
#|    if dialect == "mysql":
#|        cols = _rows(conn, "SELECT COLUMN_NAME AS name, COLUMN_TYPE AS type, IS_NULLABLE AS nullable, COLUMN_KEY AS `key`, "
#|                           "COLUMN_DEFAULT AS `default`, EXTRA AS extra, COLUMN_COMMENT AS comment FROM information_schema.COLUMNS "
#|                           f"WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} ORDER BY ORDINAL_POSITION", (schema, table))
#|        fks = _rows(conn, "SELECT COLUMN_NAME AS `column`, CONCAT(REFERENCED_TABLE_NAME,'.',REFERENCED_COLUMN_NAME) AS ref "
#|                          f"FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} AND REFERENCED_TABLE_NAME IS NOT NULL",
#|                    (schema, table))
#|        idx_rows = _rows(conn, "SELECT INDEX_NAME AS name, NON_UNIQUE AS nu, COLUMN_NAME AS col FROM information_schema.STATISTICS "
#|                               f"WHERE TABLE_SCHEMA={p} AND TABLE_NAME={p} ORDER BY INDEX_NAME, SEQ_IN_INDEX", (schema, table))
#|    else:
#|        cols = _rows(conn, "SELECT c.column_name AS name, c.data_type || COALESCE('(' || c.character_maximum_length || ')', '') AS type, "
#|                           "c.is_nullable AS nullable, CASE WHEN k.column_name IS NOT NULL THEN 'PRI' ELSE '' END AS key, "
#|                           "c.column_default AS default, '' AS extra, '' AS comment FROM information_schema.columns c "
#|                           "LEFT JOIN (SELECT ku.column_name FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage ku "
#|                           "ON tc.constraint_name = ku.constraint_name AND tc.table_schema = ku.table_schema "
#|                           f"WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema={p} AND tc.table_name={p}) k ON k.column_name = c.column_name "
#|                           f"WHERE c.table_schema={p} AND c.table_name={p} ORDER BY c.ordinal_position", (schema, table, schema, table))
#|        fks = _rows(conn, "SELECT kcu.column_name AS column, ccu.table_name || '.' || ccu.column_name AS ref "
#|                          "FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
#|                          "JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name "
#|                          f"WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema={p} AND tc.table_name={p}", (schema, table))
#|        idx_rows = _rows(conn, "SELECT i.relname AS name, CASE WHEN ix.indisunique THEN 0 ELSE 1 END AS nu, a.attname AS col "
#|                               "FROM pg_class t JOIN pg_index ix ON t.oid = ix.indrelid JOIN pg_class i ON i.oid = ix.indexrelid "
#|                               "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey) JOIN pg_namespace n ON n.oid = t.relnamespace "
#|                               f"WHERE n.nspname={p} AND t.relname={p}", (schema, table))
#|    for c in cols:
#|        c["nullable"] = str(c["nullable"]).upper() in ("YES", "TRUE", "1")
#|    idx = {}
#|    for r in idx_rows:
#|        idx.setdefault(r["name"], {"name": r["name"], "unique": not int(r["nu"]), "columns": []})["columns"].append(r["col"])
#|    indexes = sorted(idx.values(), key=lambda i: (i["name"].upper() != "PRIMARY", i["name"]))
#|    return {"columns": cols, "foreign_keys": fks, "indexes": indexes}
#|
#|
#|def profile_table(conn, dialect, schema, table, columns, max_distinct=20):
#|    """Distinct values of low-cardinality text columns (e.g. status, source_system). Masked columns are skipped."""
#|    q = '"' if dialect != "mysql" else "`"
#|    fq = f"{q}{table}{q}" if dialect == "sqlite" else f"{q}{schema}{q}.{q}{table}{q}"
#|    out = {}
#|    for c in columns:
#|        if sensitive_column(c["name"]) or not re.search(r"(?i)char|text|enum|string", str(c["type"])):
#|            continue
#|        rows = _rows(conn, f"SELECT {q}{c['name']}{q} AS v, COUNT(*) AS n FROM {fq} GROUP BY {q}{c['name']}{q} ORDER BY n DESC LIMIT {max_distinct + 1}")
#|        if 0 < len(rows) <= max_distinct:
#|            out[c["name"]] = [(mask_value(c["name"], r["v"]), r["n"]) for r in rows]
#|    return out
#|
#|
#|def sample_rows(conn, dialect, schema, table, n):
#|    q = '"' if dialect != "mysql" else "`"
#|    fq = f"{q}{table}{q}" if dialect == "sqlite" else f"{q}{schema}{q}.{q}{table}{q}"
#|    rows = _rows(conn, f"SELECT * FROM {fq} LIMIT {int(n)}")
#|    return [{k: mask_value(k, v) for k, v in r.items()} for r in rows]
#|
#|
#|def introspect(cfg, wanted_tables, optional_tables=(), log=print):
#|    """Describe wanted tables (+ optional ones if they exist, + config include patterns) for one database.
#|    Only wanted tables that do not exist are reported as missing."""
#|    conn, dialect = connect(cfg)
#|    try:
#|        schemas = cfg.get("schemas") or ([cfg["database"]] if dialect == "mysql" else ["public"])
#|        all_tables = list_tables(conn, dialect, schemas)
#|        by_name = {}
#|        for t in all_tables:
#|            by_name.setdefault(t["table"].lower(), t)
#|            by_name.setdefault(f"{t['schema']}.{t['table']}".lower(), t)
#|        patterns = [p.lower().replace("%", "*") for p in cfg.get("include_tables") or []]
#|        chosen, missing = {}, []
#|        for name in sorted(set(wanted_tables) | set(optional_tables)):
#|            t = by_name.get(name.lower()) or by_name.get(name.lower().split(".")[-1])
#|            if t:
#|                chosen[(t["schema"], t["table"])] = t
#|            elif name in wanted_tables and "${" not in name and "#{" not in name:
#|                missing.append(name)
#|        for t in all_tables:
#|            if cfg.get("all_tables") or any(fnmatch.fnmatch(t["table"].lower(), p) for p in patterns):
#|                chosen[(t["schema"], t["table"])] = t
#|        max_tables = int(cfg.get("max_tables", 300))
#|        profile = {p.lower() for p in cfg.get("profile_tables") or []}
#|        out = []
#|        for (schema, table), t in sorted(chosen.items())[:max_tables]:
#|            info = dict(t)
#|            info.update(describe_table(conn, dialect, schema, table))
#|            if dialect == "sqlite":
#|                info["rows"] = _rows(conn, f'SELECT COUNT(*) AS n FROM "{table}"')[0]["n"]
#|            if table.lower() in profile:
#|                info["profile"] = profile_table(conn, dialect, schema, table, info["columns"])
#|            if int(cfg.get("sample_rows", 0)) > 0:
#|                info["sample"] = sample_rows(conn, dialect, schema, table, cfg["sample_rows"])
#|            out.append(info)
#|        log(f"  db {cfg['name']}: {len(all_tables)} tables in {', '.join(schemas)}, documented {len(out)}, missing {len(missing)}")
#|        return {"name": cfg["name"], "kind": cfg.get("kind"), "dialect": dialect, "schemas": schemas, "tables": out,
#|                "missing": missing, "table_count": len(all_tables), "all_table_names": sorted(t["table"] for t in all_tables)}
#|    finally:
#|        conn.close()
#|
#|
#|def run_query(cfg, sql, max_rows=200):
#|    sql = sql.strip().rstrip(";")
#|    if ";" in sql or not READ_ONLY_SQL.match(sql) or WRITE_WORDS.search(re.sub(r"'[^']*'", "''", sql)):
#|        raise DbError("only a single read-only SELECT / WITH / SHOW / DESCRIBE / EXPLAIN statement is allowed")
#|    conn, dialect = connect(cfg)
#|    try:
#|        cur = conn.cursor()
#|        cur.execute(sql)
#|        cols = [d[0] for d in cur.description] if cur.description else []
#|        rows = cur.fetchmany(max_rows)
#|        if cfg.get("mask", True):
#|            rows = [tuple(mask_value(c, v) for c, v in zip(cols, r)) for r in rows]
#|        return cols, rows
#|    finally:
#|        try:
#|            conn.rollback()
#|        except Exception:
#|            pass
#|        conn.close()
#|
#|
#|def matches_jdbc(cfg, jdbc):
#|    """Does a configured database correspond to a DBCP service's JDBC URL?"""
#|    if cfg.get("dbcp_services") and jdbc.get("service_name") in cfg["dbcp_services"]:
#|        return True
#|    if cfg.get("match_jdbc"):
#|        return cfg["match_jdbc"].lower() in (jdbc.get("url") or "").lower()
#|    local = {"localhost", "127.0.0.1", "::1"}
#|    h1, h2 = (cfg.get("host") or "").lower(), (jdbc.get("host") or "").lower()
#|    same_host = h1 == h2 or (h1 in local and h2 in local)
#|    same_db = (cfg.get("database") or "").lower() == (jdbc.get("database") or "").lower()
#|    port_ok = not jdbc.get("port") or str(jdbc["port"]) == str(cfg.get("port", jdbc["port"]))
#|    return same_host and same_db and port_ok
#@@ FILE nifikb/diagnose.py tc 5b5e654f1af476cc
#|"""Support triage: given headers / a sample payload and optionally a file / table / feed name, explain what the flow
#|and the metadata expect and what does not match. Returns plain dicts (used by the CLI, --json and the MCP server)."""
#|import csv
#|import difflib
#|import io
#|import json
#|import re
#|import time
#|from pathlib import Path
#|
#|from . import db as dbmod, metadata as metamod
#|from .build import _normalize
#|
#|SEV_RANK = {"error": 0, "high": 1, "warn": 2, "info": 3}
#|
#|
#|# ------------------------------------------------------------------------------------------------ inputs
#|def headers_from_sample(path):
#|    """Field names from a sample file: JSON (object, array of objects, or an object wrapping a record list) or
#|    delimited text (header line; delimiter sniffed)."""
#|    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
#|    stripped = text.lstrip()
#|    if stripped[:1] in "{[":
#|        try:
#|            data = json.loads(stripped)
#|        except ValueError:
#|            data = [json.loads(line) for line in stripped.splitlines() if line.strip()]  # JSON lines
#|        return _json_keys(data)
#|    first = next((ln for ln in text.splitlines() if ln.strip()), "")
#|    try:
#|        dialect = csv.Sniffer().sniff(first, delimiters=",|\t;~^")
#|        delim = dialect.delimiter
#|    except csv.Error:
#|        delim = ","
#|    return [h.strip() for h in next(csv.reader(io.StringIO(first), delimiter=delim)) if h.strip()]
#|
#|
#|def read_sample(path):
#|    """{'kind': 'json', 'data': payload} or {'kind': 'csv', 'data': [headers]} - JSON is kept whole so the metadata path
#|    can apply the feed's root path and compare nested fields."""
#|    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
#|    stripped = text.lstrip()
#|    if stripped[:1] in "{[":
#|        try:
#|            return {"kind": "json", "data": json.loads(stripped)}
#|        except ValueError:
#|            return {"kind": "json", "data": [json.loads(line) for line in stripped.splitlines() if line.strip()]}
#|    return {"kind": "csv", "data": headers_from_sample(path), "path": str(path)}
#|
#|
#|def _json_keys(data):
#|    if isinstance(data, list):
#|        rec = next((x for x in data if isinstance(x, dict)), None)
#|        return list(rec) if rec else []
#|    if isinstance(data, dict):
#|        lists = [v for v in data.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
#|        if len(lists) == 1 and len(data) <= 5:
#|            return list(lists[0][0])
#|        return list(data)
#|    return []
#|
#|
#|def split_headers(values):
#|    return [f for part in values or [] for f in str(part).replace(",", " ").split() if f]
#|
#|
#|# ------------------------------------------------------------------------------------------------ record-schema path
#|def record_diagnosis(store, headers, cfg=None):
#|    """Match headers to the PutDatabaseRecord-style processors whose reader schema is known statically."""
#|    rows = store.db.execute("SELECT * FROM record_schemas").fetchall()
#|    result = {"mode": "record", "headers": headers, "best": None, "issues": [], "findings": [], "candidates": []}
#|    if not rows:
#|        result["error"] = ("no record-based ingestion points in the KB (no PutDatabaseRecord-style processor with a resolvable "
#|                           "reader schema + matched table)")
#|        return result
#|    scored = []
#|    for r in rows:
#|        fields, translate = json.loads(r["fields"]), bool(r["translate"])
#|        ng = {_normalize(f, translate): f for f in headers}
#|        ne = {_normalize(f, translate): f for f in fields}
#|        scored.append((len(set(ng) & set(ne)) / max(len(ne), 1), r, fields, translate, ng, ne))
#|    scored.sort(key=lambda x: -x[0])
#|    for score, r, *_ in scored[:5]:
#|        c = store.db.execute("SELECT name FROM components WHERE id=?", (r["component_id"],)).fetchone()
#|        result["candidates"].append({"score": round(score, 3), "component_id": r["component_id"], "name": c["name"] if c else "?",
#|                                     "db": r["db"], "table": r["table_name"]})
#|    score, r, fields, translate, ng, ne = scored[0]
#|    if score == 0:
#|        result["error"] = "no confident match"
#|        return result
#|    comp = component_ref(store, r["component_id"])
#|    result["best"] = dict(comp, score=round(score, 3), db=r["db"], table=r["table_name"], expected_fields=fields)
#|    issues = result["issues"]
#|    for n, h in ng.items():
#|        if n not in ne:
#|            guess = difflib.get_close_matches(h, fields, n=1)
#|            issues.append({"severity": "error", "kind": "unknown-header",
#|                           "message": f"header '{h}' is not one of the expected fields" + (f" (did you mean '{guess[0]}'?)" if guess else "")})
#|    missing = [ne[n] for n in ne if n not in ng]
#|    if missing:
#|        issues.append({"severity": "warn", "kind": "missing-field", "message": f"expected fields not present in your headers: {', '.join(missing)}"})
#|    dbtab = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=lower(?)", (r["db"], r["table_name"])).fetchone()
#|    columns = json.loads(dbtab["data"])["columns"] if dbtab else []
#|    matched = {n: f for n, f in ng.items() if n in ne}
#|    cols = {_normalize(c["name"], translate): c for c in columns}
#|    extra = [f for n, f in matched.items() if n not in cols]
#|    required = [c["name"] for n, c in cols.items() if n not in matched and not c["nullable"] and c.get("default") is None
#|                and "auto_increment" not in str(c.get("extra", "")).lower() and not str(c.get("default") or "").startswith("nextval")]
#|    if extra:
#|        issues.append({"severity": "error", "kind": "column-missing",
#|                       "message": f"these headers have no matching column in {r['table_name']}: {', '.join(extra)}"})
#|    if required:
#|        issues.append({"severity": "error", "kind": "required-column",
#|                       "message": f"NOT NULL column(s) in {r['table_name']} that nothing supplies: {', '.join(required)}"})
#|    result["findings"] = findings_for(store, [r["component_id"]])
#|    if cfg:
#|        result["learnings"] = learnings_for(cfg, [r["table_name"], comp["name"], comp["short_id"], comp["type"]])
#|    return result
#|
#|
#|# ------------------------------------------------------------------------------------------------ metadata path
#|def metadata_diagnosis(cfg, store, key, headers=(), live=False, sample_path=None):
#|    """Everything the metadata config tables say about one file / table / feed / API, plus checks and linked processors."""
#|    m = metamod.settings(cfg)
#|    model = store.get_meta("metadata_model")
#|    if not m or not model:
#|        return {"mode": "metadata", "key": key, "error": "metadata support is not configured: add a [metadata] section to nifikb.toml "
#|                                                          "and run `python -m nifikb build` (see README)"}
#|    st = model.get("structure_table")
#|    targets_live = None
#|    if live:
#|        dcfg = metamod.db_config(cfg, m["db"])
#|        rows_by_table = metamod.fetch_live(dcfg, m, model)
#|        first = metamod.dossier(model, metamod.Rows(rows_by_table), key)
#|        ids = [d["id"] for d in first["definitions"]]
#|        if st:
#|            rows_by_table[st] = metamod.fetch_structure(dcfg, model, ids)
#|        names = sorted({str(d["target"]) for d in first["definitions"] if d.get("target")})
#|        if names and m["target_db"]:
#|            tcfg = dict(metamod.db_config(cfg, m["target_db"]), include_tables=[], all_tables=False, profile_tables=[],
#|                        sample_rows=0, max_tables=len(names) + 5)
#|            res = dbmod.introspect(tcfg, set(), names, log=lambda _m: None)
#|            targets_live = [{"name": m["target_db"], "tables": res["tables"], "all_table_names": res["all_table_names"]}]
#|    else:
#|        rows_by_table = store.get_meta_rows(exclude=st)
#|        first = metamod.dossier(model, metamod.Rows(rows_by_table), key)
#|        if st:
#|            rows_by_table[st] = store.get_structure_rows(st, model["structure_parent"], [d["id"] for d in first["definitions"]])
#|    rows = metamod.Rows(rows_by_table)
#|    db_results = targets_live or _target_results(store, model, first)
#|    sample = read_sample(sample_path) if sample_path else None
#|    result = metamod.dossier(model, rows, key, headers=headers, db_results=db_results, sample=sample)
#|    result.update(mode="metadata", live=live, headers=list(headers))
#|    fetched = store.cached_db_fetched("__metadata__")
#|    result["snapshot"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(fetched)) if fetched else None
#|    ids = [d["id"] for d in result["definitions"]]
#|    result["recent_changes"] = [{"when": time.strftime("%Y-%m-%d %H:%M", time.localtime(r["ts"])), "change": r["change"]}
#|                                for r in store.meta_changes_for(ids, 15)]
#|    if live and ids:  # what changed in these rows after the last snapshot (often: "it broke this morning")
#|        snap = store.get_meta_rows(exclude=st)
#|        if st:
#|            snap[st] = store.get_structure_rows(st, model["structure_parent"], ids)
#|        wanted = {str(i) for i in ids}
#|        result["changed_since_snapshot"] = [c["change"] for c in metamod.diff_rows(model, snap, rows_by_table)
#|                                            if c["link"] in wanted][:30]
#|    result["processors"] = linked_processors(store, model, result)
#|    result["findings"] = findings_for(store, [p["id"] for p in result["processors"]])
#|    for d in result["definitions"]:
#|        d["issues"].sort(key=lambda i: SEV_RANK.get(i["severity"], 9))
#|    terms = [key, Path(key.replace("\\", "/")).name]
#|    terms += [x for d in result["definitions"] for x in (d.get("label"), d.get("target"), f"{model.get('definition_table')}:{d.get('id')}")]
#|    terms += [x for p in result["processors"] for x in (p["name"], p["short_id"], p["type"])]
#|    terms += [m["table"] for m in result["matches"]]
#|    result["learnings"] = learnings_for(cfg, terms)
#|    return result
#|
#|
#|def learnings_for(cfg, terms):
#|    from . import learnings as lm
#|    return [{"id": i["id"], "title": i["title"], "kind": i["kind"], "score": i["score"], "ticket": i.get("ticket"),
#|             "date": i.get("date"), "excerpt": " ".join(i["body"].split())[:400]} for i in lm.relevant(cfg, terms)]
#|
#|
#|def _target_results(store, model, pre):
#|    names = {str(d["target"]).lower().split(".")[-1] for d in pre["definitions"] if d.get("target")}
#|    tables = []
#|    for n in names:
#|        row = store.db.execute("SELECT data FROM db_tables WHERE db=? AND lower(name)=?", (model["target_db"], n)).fetchone()
#|        if row:
#|            tables.append(json.loads(row["data"]))
#|    return [{"name": model["target_db"], "tables": tables, "all_table_names": store.get_meta(f"db_all_tables:{model['target_db']}", [])}]
#|
#|
#|def linked_processors(store, model, result, cap=25):
#|    """Processors tied to this object: configured with one of its identifying values, writing its target table, or
#|    reading the config tables (the metadata lookup processors)."""
#|    found = {}
#|
#|    def add(cid, why):
#|        if cid in found:
#|            if why not in found[cid]["why"]:
#|                found[cid]["why"].append(why)
#|            return
#|        if len(found) >= cap:
#|            return
#|        ref = component_ref(store, cid)
#|        if ref:
#|            found[cid] = dict(ref, why=[why])
#|
#|    values = set()
#|    rows = [x["row"] for x in result.get("matches", [])] + [d["row"] for d in result.get("definitions", [])]
#|    rows += [r for rs in result.get("related", {}).values() for r in rs]
#|    for r in rows:
#|        for k, v in r.items():
#|            if isinstance(v, str) and 4 <= len(v) <= 200 and v != "***" and (
#|                    metamod.KEY_COL.search(k) or metamod.TARGET_COL.search(k) or re.search(r"(?i)host|url|endpoint|dir|path", k)):
#|                values.add(v)
#|    for v in sorted(values):
#|        q = ("SELECT DISTINCT component_id, display FROM properties WHERE lower(resolved)=lower(?) "
#|             "OR (length(?) >= 6 AND instr(lower(resolved), lower(?)) > 0) LIMIT 50")
#|        for p in store.db.execute(q, (v, v, v)):
#|            add(p["component_id"], f"property '{p['display']}' contains '{v}'")
#|    for d in result.get("definitions", []):
#|        if d.get("target"):
#|            t = str(d["target"]).lower().split(".")[-1]
#|            for p in store.db.execute("SELECT DISTINCT component_id FROM resources WHERE kind='db_table' AND lower(value) IN (?, ?)",
#|                                      (t, str(d["target"]).lower())):
#|                add(p["component_id"], f"writes/reads target table {d['target']}")
#|    for t in model["tables"]:
#|        for p in store.db.execute("SELECT DISTINCT component_id FROM resources WHERE kind='db_table' AND lower(value)=lower(?) LIMIT 10", (t,)):
#|            add(p["component_id"], f"reads config table {t}")
#|    for fqcn, tables in (store.get_meta("config_table_code") or {}).items():
#|        for p in store.db.execute("SELECT id FROM components WHERE type=? LIMIT 10", (fqcn,)):
#|            add(p["id"], f"custom {fqcn.rsplit('.', 1)[-1]} queries {', '.join(tables)} in its code")
#|    return list(found.values())
#|
#|
#|# ------------------------------------------------------------------------------------------------ shared
#|def component_ref(store, cid):
#|    c = store.db.execute("SELECT id, name, type, group_id, group_path, state FROM components WHERE id=?", (cid,)).fetchone()
#|    if not c:
#|        return None
#|    g = store.db.execute("SELECT doc FROM groups WHERE id=?", (c["group_id"],)).fetchone()
#|    return {"id": c["id"], "short_id": c["id"][:8], "name": c["name"], "type": (c["type"] or "").rsplit(".", 1)[-1],
#|            "group": c["group_path"], "state": c["state"], "doc": f"{g['doc']}#c-{c['id'][:8]}" if g else None}
#|
#|
#|def findings_for(store, component_ids):
#|    out = []
#|    for cid in component_ids:
#|        for f in store.db.execute("SELECT severity, kind, message FROM findings WHERE component_id=?", (cid,)):
#|            out.append({"component_id": cid, "severity": f["severity"], "kind": f["kind"], "message": f["message"]})
#|    out.sort(key=lambda f: SEV_RANK.get(f["severity"], 9))
#|    return out
#|
#|
#|def has_errors(result):
#|    issues = list(result.get("issues", [])) + [i for d in result.get("definitions", []) for i in d.get("issues", [])]
#|    return any(i["severity"] == "error" for i in issues)
#|
#|
#|# ------------------------------------------------------------------------------------------------ text output
#|def format_text(result):
#|    if result["mode"] == "record":
#|        return _format_record(result)
#|    return _format_metadata(result)
#|
#|
#|def _issue_lines(issues, indent="  "):
#|    marks = {"error": "x", "high": "x", "warn": "!", "info": "-"}
#|    return [f"{indent}{marks.get(i['severity'], '-')} [{i['severity']}] {i['message']}" for i in issues]
#|
#|
#|def _learning_lines(r):
#|    items = r.get("learnings") or []
#|    if not items:
#|        return []
#|    L = ["", "Team learnings that may apply (python -m nifikb learn show <id>):"]
#|    for i in items:
#|        L.append(f"  {i['id']} [{i['kind']}] {i['title']}" + (f" (ticket {i['ticket']})" if i.get("ticket") else ""))
#|        L.append(f"    {i['excerpt'][:300]}")
#|    return L
#|
#|
#|def _format_record(r):
#|    L = []
#|    if r.get("error"):
#|        L.append(r["error"] + (";" if r["candidates"] else ""))
#|        if r["candidates"]:
#|            L.append("closest ingestion points by name overlap:")
#|            L += [f"  {c['score']:.0%}  {c['name']} -> {c['db']}.{c['table']}" for c in r["candidates"]]
#|        return "\n".join(L)
#|    b = r["best"]
#|    L.append(f"Best match ({b['score']:.0%} of expected fields present): {b['name']} `{b['short_id']}` -> {b['db']}.{b['table']}  [{b['doc']}]")
#|    L += _issue_lines(r["issues"])
#|    if not r["issues"]:
#|        L.append("  OK all headers map cleanly to the reader schema and table columns")
#|    if r["findings"]:
#|        L.append("  known issues already flagged on this processor:")
#|        L += [f"    [{f['severity']}] {f['kind']}: {f['message']}" for f in r["findings"]]
#|    L += _learning_lines(r)
#|    return "\n".join(L)
#|
#|
#|def _short_row(row, limit=12):
#|    items = [(k, v) for k, v in row.items() if v not in (None, "")]
#|    s = ", ".join(f"{k}={v}" for k, v in items[:limit])
#|    return s + (f", … +{len(items) - limit}" if len(items) > limit else "")
#|
#|
#|def _format_metadata(r):
#|    if r.get("error"):
#|        return r["error"]
#|    L = [f"Metadata for '{r['key']}'" + (" (live: config rows read just now)" if r.get("live") else
#|                                         f" (config rows from the snapshot of {r.get('snapshot') or 'the last build'}; "
#|                                         "use live mode for rows changed since)")]
#|    if not r["matches"]:
#|        L.append("  nothing in the config tables matches this name")
#|        if r.get("suggestions"):
#|            L.append("  did you mean: " + ", ".join(r["suggestions"]))
#|        return "\n".join(L)
#|    L.append("Matched:")
#|    L += [f"  {x['table']}.{x['column']} ({x['match']}): {_short_row(x['row'])}" for x in r["matches"][:10]]
#|    for d in r["definitions"]:
#|        L += ["", f"Definition {d['id']} · {d['label']}" + (f" → target table {d['target']}" if d.get("target") else "")
#|              + (f" → loads to {d['location']}" if d.get("location") else "")]
#|        if d["fields"]:
#|            L.append(f"  structure ({len(d['fields'])} fields): " + ", ".join(
#|                (f"{f['seq']}:" if f["seq"] is not None else "") + f["name"] + (f" {f['type']}" if f.get("type") else "")
#|                + (f"({f['length']})" if f.get("length") else "") + ("?" if f.get("nullable") else "")
#|                for f in d["fields"][:80]) + (" …" if len(d["fields"]) > 80 else ""))
#|        smp = d.get("sample")
#|        if smp and smp.get("kind") == "csv" and smp.get("delimiter"):
#|            L.append(f"  sample: CSV, delimiter {smp['delimiter']!r} ({smp.get('delimiter_source')}), "
#|                     f"{'with' if smp.get('header') else 'no'} header row, {smp.get('rows', 0)} data rows checked")
#|        if smp and smp.get("kind") == "json":
#|            L.append(f"  sample: JSON, record root {smp.get('root') or '(top level)'}, {smp['fields']} "
#|                     + ("nested field paths compared" if smp.get("paths") else "top-level keys compared") + " (order not checked)")
#|        L += _issue_lines(d["issues"])
#|        if not d["issues"]:
#|            L.append("  OK structure, headers and target table agree")
#|        from .fixes import format_fixes
#|        L += format_fixes(d.get("fixes") or [])
#|    if r.get("changed_since_snapshot"):
#|        L += ["", f"Config rows changed since the snapshot of {r.get('snapshot') or 'the last build'} (live read):"]
#|        L += [f"  {c}" for c in r["changed_since_snapshot"]]
#|    if r.get("recent_changes"):
#|        L += ["", "Recent config-row changes for this definition (from earlier snapshots, newest first):"]
#|        L += [f"  {c['when']}  {c['change']}" for c in r["recent_changes"]]
#|    if r["related"]:
#|        L += ["", "Related config rows:"]
#|        for t, rows in r["related"].items():
#|            for row in rows[:5]:
#|                L.append(f"  {t}: {_short_row(row)}")
#|            if len(rows) > 5:
#|                L.append(f"  {t}: … {len(rows) - 5} more")
#|    if r.get("processors"):
#|        L += ["", "Flow processors involved:"]
#|        for p in r["processors"]:
#|            L.append(f"  {p['name']} [{p['type']}] `{p['short_id']}` {p['state'] or ''} in {p['group']} — {'; '.join(p['why'][:2])}  [{p['doc']}]")
#|    if r.get("findings"):
#|        L += ["", "Known issues on those processors:"]
#|        L += [f"  [{f['severity']}] {f['component_id'][:8]} {f['kind']}: {f['message']}" for f in r["findings"][:30]]
#|    L += _learning_lines(r)
#|    return "\n".join(L)
#@@ FILE nifikb/doctor.py tc d39a714db243d005
#|"""`nifikb doctor`: one command that checks an installation end to end (first thing to run on a new machine)."""
#|import json
#|import shutil
#|import sys
#|import time
#|from pathlib import Path
#|
#|from .config import PROJECT_DIR
#|
#|OK, WARN, FAIL = "OK  ", "WARN", "FAIL"
#|
#|
#|def run(cfg, offline=False):
#|    checks = []
#|
#|    def add(status, label, detail=""):
#|        checks.append((status, label, detail))
#|
#|    add(OK if sys.version_info >= (3, 11) else FAIL, "python", f"{sys.version.split()[0]} ({sys.executable})"
#|        + ("" if sys.version_info >= (3, 11) else " - needs 3.11+"))
#|    add(OK, "config", cfg["_path"])
#|    _nifi(cfg, add)
#|    _code(cfg, add)
#|    _databases(cfg, add, offline)
#|    _metadata(cfg, add)
#|    _kb(cfg, add)
#|    _audit(cfg, add)
#|    _logs(cfg, add)
#|    _nifi_api(cfg, add, offline)
#|    _optional(cfg, add)
#|    _agents(cfg, add)
#|    _knowledge(cfg, add)
#|    return checks
#|
#|
#|def _nifi(cfg, add):
#|    from .build import find_flow_file
#|    from .catalog import find_nars
#|    try:
#|        flow = find_flow_file(cfg)
#|        add(OK, "flow file", f"{flow} ({flow.stat().st_size / 1e6:.1f} MB, modified {time.strftime('%Y-%m-%d %H:%M', time.localtime(flow.stat().st_mtime))})")
#|    except FileNotFoundError as e:
#|        add(FAIL, "flow file", str(e))
#|    home = cfg["nifi"].get("home")
#|    dirs = [Path(home) / d for d in ("lib", "extensions")] if home else []
#|    for d in cfg["nifi"].get("extra_nar_dirs", []):
#|        add(OK if Path(d).is_dir() else FAIL, "extra NAR dir", d)
#|        dirs.append(Path(d))
#|    nars = find_nars(dirs)
#|    add(OK if nars else WARN, "NARs", f"{len(nars)} found" + ("" if nars else " - no property defaults / docs; set [nifi] home or extra_nar_dirs"))
#|
#|
#|def _code(cfg, add):
#|    repos = cfg["code"].get("repos", [])
#|    if not repos:
#|        add(WARN, "code repos", "none configured - custom processors will only have NAR docs (set [code] repos to the Bitbucket clones)")
#|    for r in repos:
#|        p = Path(r)
#|        if not p.exists():
#|            add(FAIL, "code repo", f"{r} does not exist")
#|            continue
#|        java = sum(1 for _ in p.rglob("*.java"))
#|        poms = sum(1 for _ in p.rglob("pom.xml"))
#|        svc = sum(1 for _ in p.rglob("META-INF/services/org.apache.nifi.*"))
#|        other = sum(1 for ext in ("*.py", "*.groovy", "*.scala", "*.sh", "*.sql") for _ in p.rglob(ext))
#|        add(OK, "code repo", f"{r}: {java} Java, {poms} pom.xml, {svc} NiFi service registrations, {other} scripts/other")
#|
#|
#|def _databases(cfg, add, offline):
#|    from . import db as dbmod
#|    import os
#|    if not cfg.get("databases"):
#|        add(WARN, "databases", "none configured - no table schemas, no metadata checks (add a [[databases]] block)")
#|    for d in cfg.get("databases", []):
#|        kind = (d.get("kind") or "mariadb").lower()
#|        label = f"database {d['name']}"
#|        driver = {"mariadb": "pymysql", "mysql": "pymysql", "postgres": "pg8000", "postgresql": "pg8000"}.get(kind)
#|        if driver:
#|            try:
#|                __import__(driver)
#|            except ImportError:
#|                if kind.startswith("postgres"):
#|                    try:
#|                        __import__("psycopg2")
#|                        driver = None
#|                    except ImportError:
#|                        pass
#|                if driver:
#|                    add(FAIL, label, f"driver missing: pip install {driver}")
#|                    continue
#|        if d.get("password_env") and not os.environ.get(d["password_env"]) and not d.get("password_file"):
#|            add(WARN, label, f"environment variable {d['password_env']} is not set in this shell")
#|        if d.get("password_file"):
#|            pf = Path(d["password_file"])
#|            if not pf.is_file():
#|                add(FAIL, label, f"password_file {pf} not found")
#|                continue
#|            if os.name == "posix" and pf.stat().st_mode & 0o077:
#|                add(WARN, label, f"password_file {pf} is readable by others: chmod 600 {pf}")
#|        if offline:
#|            continue
#|        try:
#|            conn, dialect = dbmod.connect(d)
#|        except dbmod.DbError as e:
#|            add(FAIL, label, str(e))
#|            continue
#|        try:
#|            cur = conn.cursor()
#|            cur.execute("SELECT 1")
#|            cur.fetchall()
#|            detail = f"{kind} connected as {d.get('user') or '-'}"
#|            status = OK
#|            if dialect == "mysql":
#|                cur.execute("SHOW GRANTS")
#|                grants = " ".join(g for g in (str(r[0]) for r in cur.fetchall()) if _grant_covers(g, d.get("database"))).upper()
#|                if any(w in grants for w in ("ALL PRIVILEGES", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER")):
#|                    status, detail = WARN, detail + " - this user can WRITE; use a SELECT-only user (sessions are read-only anyway)"
#|                else:
#|                    detail += ", read-only grants"
#|            add(status, label, detail)
#|        except Exception as e:  # driver specific
#|            add(FAIL, label, f"{type(e).__name__}: {e}")
#|        finally:
#|            conn.close()
#|
#|
#|def _grant_covers(grant, database):
#|    """Does a MySQL/MariaDB GRANT line apply to the configured database (or to all databases)?"""
#|    import fnmatch
#|    import re
#|    m = re.search(r"\bON\s+(?:TABLE\s+)?`?([^`.\s]+|\*)`?\.", grant, re.I)
#|    if not m:
#|        return False
#|    target = m.group(1)
#|    if target == "*":
#|        return True
#|    pattern = target.replace("\\_", "\0").replace("%", "*").replace("_", "?").replace("\0", "_")
#|    return bool(database) and fnmatch.fnmatch(database.lower(), pattern.lower())
#|
#|
#|def _metadata(cfg, add):
#|    from . import metadata as metamod
#|    try:
#|        m = metamod.settings(cfg)
#|    except ValueError as e:
#|        add(FAIL, "metadata", str(e))
#|        return
#|    if not m:
#|        add(WARN, "metadata", "[metadata] not configured - no OBJ_* definition / structure checks and no `diagnose --file`")
#|        return
#|    model = _store_meta(cfg, "metadata_model")
#|    if not model:
#|        add(WARN, "metadata", f"configured (db '{m['db']}') - run build to detect the config tables")
#|        return
#|    missing = [r for r in ("definition_table", "structure_table") if not model.get(r)]
#|    detail = (f"{len(model['tables'])} config tables, definition {model.get('definition_table')}, structure {model.get('structure_table')}, "
#|              f"{len(model['relations'])} relations")
#|    if missing:
#|        add(WARN, "metadata", detail + f" - not detected: {', '.join(missing)} (set them in [metadata])")
#|    elif model.get("guessed"):
#|        add(OK, "metadata", detail + f" - auto-detected {', '.join(model['guessed'])}: confirm in kb/metadata.md")
#|    else:
#|        add(OK, "metadata", detail)
#|
#|
#|def _store_meta(cfg, key):
#|    import sqlite3
#|    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
#|    if not path.exists():
#|        return None
#|    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
#|    try:
#|        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
#|        return json.loads(row[0]) if row else None
#|    except sqlite3.Error:
#|        return None
#|    finally:
#|        db.close()
#|
#|
#|def _kb(cfg, add):
#|    from .build import find_flow_file
#|    built = _store_meta(cfg, "built_at")
#|    if not built:
#|        add(FAIL, "knowledge base", "not built yet: python -m nifikb build")
#|        return
#|    age_h = (time.time() - built) / 3600
#|    detail = f"built {time.strftime('%Y-%m-%d %H:%M', time.localtime(built))} ({age_h:.1f} h ago)"
#|    try:
#|        stale = find_flow_file(cfg).stat().st_mtime > built
#|    except FileNotFoundError:
#|        stale = False
#|    if stale:
#|        add(WARN, "knowledge base", detail + " - the flow changed since: run build (or schedule it)")
#|    else:
#|        add(OK if age_h < 48 else WARN, "knowledge base", detail + ("" if age_h < 48 else " - older than 2 days: schedule `build`"))
#|
#|
#|def _audit(cfg, add):
#|    from . import audit as auditmod
#|    try:
#|        a = auditmod.settings(cfg)
#|    except ValueError as e:
#|        add(FAIL, "load audit", str(e))
#|        return
#|    if not a:
#|        add(WARN, "load audit", "[audit] not configured - investigate cannot show the last load status of a file")
#|        return
#|    m = _store_meta(cfg, "audit_model")
#|    if not m:
#|        add(WARN, "load audit", f"no audit table found in '{a['db']}' - set [audit] table (then build)")
#|    else:
#|        add(OK, "load audit", f"{m['table']}: file {m['file_column']}, status {m.get('status_column')}, time {m.get('time_column')}, "
#|                              f"error {m.get('error_column')}" + (f" (guessed: {', '.join(m['guessed'])})" if m.get("guessed") else ""))
#|
#|
#|def _logs(cfg, add):
#|    from . import logs as lg
#|    s = lg.settings(cfg)
#|    if not s["enabled"]:
#|        add(WARN, "logs", "no log directory (set [logs] dirs, or [nifi] home) - errors from nifi-app.log are not available")
#|        return
#|    missing = [d for d in s["dirs"] if not Path(d).is_dir()]
#|    files = lg.log_files(s)
#|    if missing:
#|        add(FAIL if not files else WARN, "logs", f"directory not found: {', '.join(missing)}")
#|    if files:
#|        newest = max(files, key=lambda f: f.stat().st_mtime)
#|        events = _store_count(cfg, "SELECT COUNT(*) FROM log_events")
#|        add(OK, "logs", f"{len(files)} file(s), newest {newest.name} modified "
#|                         f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(newest.stat().st_mtime))}; {events} warning / error events indexed")
#|    elif not missing:
#|        add(WARN, "logs", f"no files matching {', '.join(s['patterns'])} in {', '.join(s['dirs'])}")
#|
#|
#|def _store_count(cfg, sql):
#|    import sqlite3
#|    path = Path(cfg["output"]["dir"]) / "kb.sqlite"
#|    if not path.exists():
#|        return 0
#|    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
#|    try:
#|        return db.execute(sql).fetchone()[0]
#|    except sqlite3.Error:
#|        return 0
#|    finally:
#|        db.close()
#|
#|
#|def _nifi_api(cfg, add, offline):
#|    from . import nifiapi
#|    a = nifiapi.settings(cfg)
#|    if not a:
#|        add(WARN, "NiFi API", "[nifi_api] not configured - no provenance ('where was my file dropped') and no live bulletins")
#|        return
#|    if offline:
#|        add(OK, "NiFi API", f"{a['url']} (not contacted: --offline)")
#|        return
#|    try:
#|        about = nifiapi.Client(a).about()
#|        add(OK, "NiFi API", f"{a['url']} - {about.get('title', 'NiFi')} {about.get('version', '')}".strip())
#|    except (nifiapi.NiFiApiError, OSError, ValueError) as e:
#|        add(FAIL, "NiFi API", str(e))
#|
#|
#|def _optional(cfg, add):
#|    """[targets], [tickets], [environments.*], [registry]: configuration that can be checked without contacting anything."""
#|    import os
#|    if "targets" in cfg:
#|        t = cfg["targets"] or {}
#|        tools = []
#|        if t.get("hdfs_url"):
#|            tools.append(f"WebHDFS {t['hdfs_url']}" + (" (kerberos via curl)" if t.get("kerberos") else ""))
#|            if t.get("kerberos") and not shutil.which(t.get("curl", "curl")):
#|                add(FAIL, "targets", "kerberos = true needs curl on the PATH")
#|        elif shutil.which("hdfs") or t.get("hdfs_cli"):
#|            tools.append("hdfs CLI")
#|        if t.get("s3_cli"):
#|            tools.append("S3 via configured CLI")
#|        else:
#|            try:
#|                import boto3  # noqa: F401
#|                tools.append("S3 via boto3")
#|            except ImportError:
#|                tools.append("S3 via aws CLI" if shutil.which("aws") else "no S3 access (install the aws CLI or boto3)")
#|        add(OK, "targets", ", ".join(tools + ["local / mounted folders"])
#|            + (f"; location_template {t['location_template']}" if t.get("location_template") else ""))
#|    tk = cfg.get("tickets")
#|    if tk:
#|        secret = next((k for k in ("token", "password") if tk.get(f"{k}_env") and os.environ.get(tk[f"{k}_env"]) or tk.get(f"{k}_file")), None)
#|        if tk.get("kind") not in ("jira", "servicenow") or not tk.get("url"):
#|            add(FAIL, "tickets", "[tickets] needs kind = \"jira\" | \"servicenow\" and url")
#|        elif not secret:
#|            add(WARN, "tickets", f"{tk['kind']} {tk['url']}: no credential (set token_env / password_env or *_file)")
#|        else:
#|            add(OK, "tickets", f"{tk['kind']} {tk['url']} (posting only with `ticket <id> --post`)")
#|    dbs = {d["name"] for d in cfg.get("databases", [])}
#|    for name, env in (cfg.get("environments") or {}).items():
#|        problems = []
#|        if env.get("flow_file") and not Path(env["flow_file"]).exists():
#|            problems.append(f"flow_file {env['flow_file']} not found")
#|        if env.get("db") and env["db"] not in dbs:
#|            problems.append(f"db '{env['db']}' is not a [[databases]] name")
#|        add(FAIL if problems else OK, f"environment {name}", "; ".join(problems) or
#|            ", ".join(x for x in (env.get("flow_file"), env.get("db")) if x))
#|
#|
#|def _agents(cfg, add):
#|    root = Path(cfg["_path"]).parent
#|    for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md"):
#|        if not (root / f).exists():
#|            add(WARN, "agent instructions", f"{f} missing next to nifikb.toml")
#|    texts = {f: (root / f).read_text(encoding="utf-8").replace("\r\n", "\n") for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md") if (root / f).exists()}
#|    if len(set(texts.values())) > 1:
#|        add(WARN, "agent instructions", "CLAUDE.md / GEMINI.md / AGENTS.md differ - copy the edited one over the others")
#|    elif texts:
#|        add(OK, "agent instructions", ", ".join(texts))
#|    for f, kind in ((".mcp.json", "Claude Code MCP"), (".gemini/settings.json", "Gemini CLI MCP")):
#|        p = root / f
#|        if not p.exists():
#|            add(WARN, kind, f"{f} missing")
#|            continue
#|        try:
#|            server = json.loads(p.read_text(encoding="utf-8"))["mcpServers"]["nifikb"]
#|        except (ValueError, KeyError) as e:
#|            add(FAIL, kind, f"{f}: no mcpServers.nifikb entry ({e})")
#|            continue
#|        cmd = server.get("command", "")
#|        found = shutil.which(cmd)
#|        if not found:
#|            alt = next((c for c in ("py", "python3", "python") if shutil.which(c)), None)
#|            add(FAIL, kind, f"{f}: command '{cmd}' not on PATH" + (f" - change it to '{alt}'" if alt else ""))
#|        else:
#|            add(OK, kind, f"{f} -> {cmd} {' '.join(server.get('args', []))}")
#|    if root.resolve() != PROJECT_DIR.resolve() and not (root / "nifikb").is_dir():
#|        add(WARN, "MCP working dir", f"the agents start `python -m nifikb` in {root}; the nifikb package lives in {PROJECT_DIR}")
#|
#|
#|def _knowledge(cfg, add):
#|    from . import learnings as lm
#|    r = lm.ensure(cfg)
#|    items = lm.load_all(cfg, include_obsolete=False)
#|    add(OK, "learnings", f"{len(items)} active in {r / 'learnings'}")
#|    if not lm.context_text(cfg):
#|        add(WARN, "team context", f"{r / 'context.md'} is still the template - fill in environments, owners, conventions")
#|    else:
#|        add(OK, "team context", str(r / "context.md"))
#|
#|
#|def report(checks):
#|    lines = [f"[{s}] {label}: {detail}" for s, label, detail in checks]
#|    fails = sum(1 for s, _, _ in checks if s == FAIL)
#|    warns = sum(1 for s, _, _ in checks if s == WARN)
#|    lines.append(f"\n{fails} problem(s), {warns} warning(s)")
#|    return "\n".join(lines), fails
#@@ FILE nifikb/evals.py t 184d8faaafffa027
#|"""Evaluation set of past tickets with known root causes: are the tools (and the model) getting them right?
#|
#|evals/cases.toml:
#|
#|    [[case]]
#|    id = "INC1001"
#|    ticket = "SALES file of 26 Sep did not load, customer names missing"   # what the user wrote (for the agent run)
#|    file = "SALES_20260926.csv"                   # the investigate inputs: file / feed / table / error / headers / sample
#|    headers = ["ORDER_NO", "CUSTNAME", "AMOUNT"]
#|    expect_any = ["CUSTNAME", "CUST_NAME"]        # at least one must appear in the top `top` ranked causes
#|    expect_all = []                               # every one must appear
#|    top = 3
#|    answer_expect = ["CUST_NAME"]                 # with --agent: words the model's answer must contain (default: expect_any)
#|
#|`python -m nifikb eval` checks the ranked causes; `--agent "<command>"` also sends ticket + report to a model CLI (the
#|prompt is written to its stdin, or to a file whose path replaces {prompt_file}) and checks its answer.
#|"""
#|import json
#|import shlex
#|import subprocess
#|import tempfile
#|import time
#|import tomllib
#|from pathlib import Path
#|
#|PROMPT = """You are the NiFi support assistant. A colleague reported:
#|
#|{ticket}
#|
#|The nifikb tools investigated it. Their report (ranked likely causes first, then evidence):
#|
#|{report}
#|
#|Answer in this shape: Cause (one or two sentences), Evidence (ids, rows, file:line, log lines), Fix (who changes what).
#|"""
#|
#|
#|def load_cases(path):
#|    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
#|    cases = data.get("case") or []
#|    base = Path(path).parent
#|    for c in cases:
#|        if c.get("sample"):
#|            p = Path(c["sample"])
#|            c["sample"] = str(p if p.is_absolute() else (base / p))
#|    return cases
#|
#|
#|def run(cfg, store, names, cases, top=None, agent=None, timeout=300, log=print):
#|    from . import diagnose as dg, investigate as inv
#|    results = []
#|    for c in cases:
#|        t0 = time.time()
#|        r = inv.investigate(cfg, store, names, file=c.get("file"), feed=c.get("feed"), table=c.get("table"),
#|                            error_text=c.get("error"), headers=dg.split_headers(c.get("headers") or []), sample_path=c.get("sample"),
#|                            live=bool(c.get("live")), record=False)
#|        n = int(c.get("top") or top or 3)
#|        ranked = r["causes"][:n]
#|        text = "\n".join(ranked).lower()
#|        any_ok = not c.get("expect_any") or any(w.lower() in text for w in c["expect_any"])
#|        all_ok = all(w.lower() in text for w in c.get("expect_all") or [])
#|        position = next((i + 1 for i, cause in enumerate(r["causes"])
#|                         if any(w.lower() in cause.lower() for w in (c.get("expect_any") or c.get("expect_all") or []))), None)
#|        res = {"id": c.get("id"), "tools_ok": any_ok and all_ok, "position": position, "top": n, "seconds": round(time.time() - t0, 1),
#|               "first_cause": r["causes"][0] if r["causes"] else None}
#|        if agent:
#|            answer = ask_agent(agent, PROMPT.format(ticket=c.get("ticket") or c.get("id"), report=inv.format_report(r)), timeout)
#|            words = c.get("answer_expect") or c.get("expect_any") or []
#|            res["agent_ok"] = bool(answer) and all(w.lower() in answer.lower() for w in words) if c.get("answer_expect") else \
#|                any(w.lower() in answer.lower() for w in words)
#|            res["answer"] = answer[:2000]
#|        results.append(res)
#|        log(f"{'PASS' if res['tools_ok'] and res.get('agent_ok', True) else 'FAIL'} {res['id']}: cause at rank {position or '-'}"
#|            + (f", agent {'ok' if res['agent_ok'] else 'wrong'}" if agent else ""))
#|    return results
#|
#|
#|def ask_agent(command, prompt, timeout):
#|    """Run a model CLI non-interactively: the prompt goes to stdin, or into a temp file named by {prompt_file}."""
#|    tmp = None
#|    try:
#|        if "{prompt_file}" in command:
#|            fd, tmp = tempfile.mkstemp(suffix=".txt")
#|            with open(fd, "w", encoding="utf-8") as f:
#|                f.write(prompt)
#|            argv = [a.replace("{prompt_file}", tmp) for a in shlex.split(command, posix=True)]
#|            proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
#|        else:
#|            proc = subprocess.run(shlex.split(command, posix=True), input=prompt, capture_output=True, text=True, encoding="utf-8",
#|                                  timeout=timeout)
#|        return (proc.stdout or "") + (proc.stderr if proc.returncode else "")
#|    except (OSError, subprocess.TimeoutExpired) as e:
#|        return f"<agent failed: {e}>"
#|    finally:
#|        if tmp:
#|            Path(tmp).unlink(missing_ok=True)
#|
#|
#|def summary(results):
#|    n = len(results)
#|    tools = sum(r["tools_ok"] for r in results)
#|    lines = [f"tools: {tools}/{n} cases have the true cause in their top ranks"]
#|    agents = [r for r in results if "agent_ok" in r]
#|    if agents:
#|        lines.append(f"agent: {sum(r['agent_ok'] for r in agents)}/{len(agents)} answers name the true cause")
#|    ranks = [r["position"] for r in results if r["position"]]
#|    if ranks:
#|        lines.append(f"mean rank of the true cause: {sum(ranks) / len(ranks):.1f}")
#|    return "\n".join(lines)
#|
#|
#|def save(results, path):
#|    Path(path).write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M"), "results": results}, indent=2), encoding="utf-8")
#@@ FILE nifikb/fixes.py t 4967308a081fb582
#|"""Proposed fixes for config-side problems, as SQL for a human to review and run (nifikb never runs them).
#|
#|Each proposal says who should act: often the right fix is the sender correcting the file, not us changing the metadata;
#|the SQL is then offered only as the alternative."""
#|
#|
#|def quote(v):
#|    if v is None:
#|        return "NULL"
#|    if isinstance(v, bool):
#|        return "1" if v else "0"
#|    if isinstance(v, (int, float)):
#|        return str(v)
#|    return "'" + str(v).replace("'", "''") + "'"
#|
#|
#|def _where(key):
#|    return " AND ".join(f"{c} = {quote(v)}" for c, v in key.items()) or "1 = 0"
#|
#|
#|def suggest(model, entry):
#|    st, dt = model.get("structure_table"), model.get("definition_table")
#|    col = {k: model.get(k) for k in ("structure_field", "structure_type", "structure_length", "structure_nullable", "structure_order",
#|                                     "structure_parent", "definition_id", "definition_target")}
#|    fields = {f["name"].lower(): f for f in entry.get("fields") or []}
#|    out, seen = [], set()
#|
#|    def add(why, who, sql, note=""):
#|        if sql and sql not in seen:
#|            seen.add(sql)
#|            out.append({"why": why, "who": who, "sql": sql, "note": note})
#|
#|    required_flag = "'Y'" if model.get("nullable_means_required") else "'N'"
#|    optional_flag = "'N'" if model.get("nullable_means_required") else "'Y'"
#|    for i in entry.get("issues") or []:
#|        d, kind = i.get("data") or {}, i["kind"]
#|        if kind == "header-name" and st and col["structure_field"]:
#|            f = fields.get(str(d.get("field", "")).lower())
#|            if f:
#|                add(f"header '{d['header']}' vs structure '{f['name']}'", "sender (preferred) or config",
#|                    f"UPDATE {st} SET {col['structure_field']} = {quote(d['header'])} WHERE {_where(f['key'])};",
#|                    f"prefer asking the sender to send '{f['name']}'; change the row only if '{d['header']}' is the agreed name "
#|                    f"(and if {col['structure_field']} is also the target column name, the target column must match)")
#|        elif kind == "length" and st and col["structure_length"]:
#|            for name, table_len in d.get("items") or []:
#|                f = fields.get(name.lower())
#|                if f:
#|                    add(f"'{name}' longer in the structure than in {d.get('table')}", "config (or widen the target column)",
#|                        f"UPDATE {st} SET {col['structure_length']} = {table_len} WHERE {_where(f['key'])};",
#|                        f"or widen the column instead: ALTER TABLE {d.get('table')} MODIFY {name} VARCHAR({f['length']}) - decide which "
#|                        "length is right")
#|        elif kind == "type-mismatch" and st and col["structure_type"]:
#|            for name, table_type in d.get("items") or []:
#|                f = fields.get(name.lower())
#|                if f:
#|                    add(f"'{name}' type differs from {d.get('table')}", "config",
#|                        f"UPDATE {st} SET {col['structure_type']} = {quote(str(table_type).split('(')[0].upper())} WHERE {_where(f['key'])};",
#|                        "check the type name convention used in the structure table before running")
#|        elif kind == "nullability" and st and col["structure_nullable"]:
#|            for name, _ in d.get("items") or []:
#|                f = fields.get(name.lower())
#|                if f:
#|                    add(f"'{name}' nullable in the structure but NOT NULL in {d.get('table')}", "config",
#|                        f"UPDATE {st} SET {col['structure_nullable']} = {required_flag} WHERE {_where(f['key'])};",
#|                        "use the flag values the table already uses (Y/N, 1/0, ...)")
#|        elif kind == "required-column" and st and col["structure_parent"] and col["structure_field"]:
#|            seqs = [f["seq"] for f in entry.get("fields") or [] if f.get("seq") is not None]
#|            nxt = (max(seqs) if seqs else 0) + 1
#|            for n, (name, typ) in enumerate(d.get("columns") or []):
#|                cols = [col["structure_parent"], col["structure_field"]]
#|                vals = [quote(entry.get("id")), quote(name)]
#|                for key, val in (("structure_type", quote(str(typ).split("(")[0].upper())), ("structure_order", str(nxt + n)),
#|                                 ("structure_nullable", required_flag)):
#|                    if col[key]:
#|                        cols.append(col[key])
#|                        vals.append(val)
#|                add(f"NOT NULL column '{name}' is never supplied", "config (or give the column a default)",
#|                    f"INSERT INTO {st} ({', '.join(cols)}) VALUES ({', '.join(vals)});",
#|                    "only if the file really carries this value; if NiFi / the load sets it, give the table column a DEFAULT instead")
#|        elif kind == "column-missing" and st and col["structure_field"]:
#|            for name, table_col in d.get("pairs") or []:
#|                f = fields.get(str(name).lower())
#|                if f and table_col:
#|                    add(f"structure field '{name}' has no column; the table has '{table_col}'", "config",
#|                        f"UPDATE {st} SET {col['structure_field']} = {quote(table_col)} WHERE {_where(f['key'])};",
#|                        "if the field is really the same column")
#|        elif kind == "missing-field" and i["severity"] == "error" and st and col["structure_nullable"]:
#|            f = fields.get(str(d.get("field", "")).lower())
#|            if f:
#|                add(f"mandatory field '{f['name']}' missing from the file", "sender (preferred) or config",
#|                    f"UPDATE {st} SET {col['structure_nullable']} = {optional_flag} WHERE {_where(f['key'])};",
#|                    "prefer asking the sender to include it; make it optional only if the business agrees")
#|        elif kind == "target-missing" and dt and col["definition_target"] and d.get("suggestion"):
#|            add(f"target table '{d['target']}' does not exist", "config",
#|                f"UPDATE {dt} SET {col['definition_target']} = {quote(d['suggestion'])} WHERE {col['definition_id']} = {quote(entry.get('id'))};",
#|                "or create the table if the name is right")
#|        elif kind == "data-delimiter" and dt and d.get("column") and col["definition_id"]:
#|            add(f"the file uses {d['delimiter']!r}", "sender (preferred) or config",
#|                f"UPDATE {dt} SET {d['column']} = {quote(d['delimiter'])} WHERE {col['definition_id']} = {quote(entry.get('id'))};",
#|                "only if the sender changed the format on purpose and will keep it; otherwise ask them to send the agreed delimiter")
#|    return out
#|
#|
#|def format_fixes(fixes, indent="  "):
#|    if not fixes:
#|        return []
#|    L = [f"{indent}proposed fixes (review first - nifikb never runs them):"]
#|    for f in fixes:
#|        L.append(f"{indent}  -- {f['why']} [{f['who']}]" + (f": {f['note']}" if f.get("note") else ""))
#|        L.append(f"{indent}  {f['sql']}")
#|    return L
#@@ FILE nifikb/flow.py tc 1c02906b1b263cec
#|"""Load a NiFi flow into one normalized model.
#|
#|Supported inputs:
#|  * conf/flow.json.gz            (NiFi 1.16+ / 2.x)
#|  * conf/flow.xml.gz             (NiFi 1.x, older installs only have this one)
#|  * exported flow definitions    ("Download flow definition" / NiFi Registry snapshot JSON)
#|"""
#|import gzip
#|import json
#|import xml.etree.ElementTree as ET
#|from collections import Counter
#|from pathlib import Path
#|
#|NODE_KINDS = ("PROCESSOR", "INPUT_PORT", "OUTPUT_PORT", "FUNNEL", "REMOTE_INPUT_PORT", "REMOTE_OUTPUT_PORT")
#|
#|
#|class Flow:
#|    def __init__(self, source, fmt):
#|        self.source = str(source)
#|        self.format = fmt
#|        self.root_id = None
#|        self.groups = {}          # id -> {id, name, parent_id, comments, variables, parameter_context, path}
#|        self.components = {}      # id -> processor / port / funnel / remote port
#|        self.services = {}        # id -> controller service
#|        self.connections = []     # {id, name, source_id, dest_id, relationships, group_id, ...}
#|        self.labels = []          # {group_id, text}
#|        self.param_contexts = {}  # name -> {params: {name: {value, sensitive, description}}, inherits: [names]}
#|        self.reporting_tasks = []
#|        self.aliases = {}         # instance id / versioned id -> canonical id
#|
#|    def resolve_id(self, ident):
#|        return self.aliases.get(ident, ident)
#|
#|    def alias(self, other, canonical):
#|        if other and other != canonical:
#|            self.aliases[other] = canonical
#|
#|    def group_chain(self, group_id):
#|        """Group ids from the given group up to the root."""
#|        chain = []
#|        while group_id and group_id in self.groups and group_id not in chain:
#|            chain.append(group_id)
#|            group_id = self.groups[group_id]["parent_id"]
#|        return chain
#|
#|    def nifi_version(self):
#|        versions = Counter(
#|            c["bundle"].get("version")
#|            for c in list(self.components.values()) + list(self.services.values())
#|            if c.get("bundle", {}).get("group") == "org.apache.nifi" and c["bundle"].get("version")
#|        )
#|        return versions.most_common(1)[0][0] if versions else None
#|
#|    def finish(self):
#|        for gid, g in self.groups.items():
#|            names = [self.groups[x]["name"] for x in reversed(self.group_chain(gid))]
#|            g["path"] = " / ".join(names)
#|            g["depth"] = len(names) - 1
#|        # Connections can point at components we did not see (remote ports of old exports, broken flows).
#|        for c in self.connections:
#|            for end in ("source", "dest"):
#|                cid = c[f"{end}_id"] = self.resolve_id(c[f"{end}_id"])
#|                if cid not in self.components:
#|                    self.components[cid] = _component(
#|                        cid, None, c.get(f"{end}_type") or "UNKNOWN", c.get(f"{end}_name") or "?", None, {},
#|                        c.get(f"{end}_group_id") or c["group_id"], placeholder=True)
#|        return self
#|
#|
#|def _component(cid, instance_id, kind, name, ctype, bundle, group_id, **extra):
#|    comp = {
#|        "id": cid, "instance_id": instance_id, "kind": kind, "name": name or "", "type": ctype or "",
#|        "bundle": bundle or {}, "group_id": group_id, "properties": {}, "state": None,
#|        "scheduling_strategy": None, "scheduling_period": None, "concurrent_tasks": None,
#|        "auto_terminated": [], "comments": "", "execution_node": None, "placeholder": False,
#|    }
#|    comp.update(extra)
#|    return comp
#|
#|
#|def load_flow(path):
#|    path = Path(path)
#|    data = path.read_bytes()
#|    if data[:2] == b"\x1f\x8b":
#|        data = gzip.decompress(data)
#|    text = data.decode("utf-8-sig")
#|    if text.lstrip().startswith("<"):
#|        return _load_xml(path, ET.fromstring(text)).finish()
#|    return _load_json(path, json.loads(text)).finish()
#|
#|
#|# ----------------------------------------------------------------------------------------------- JSON
#|
#|def _load_json(path, doc):
#|    if "rootGroup" in doc:
#|        flow, root, contexts = Flow(path, "flow.json"), doc["rootGroup"], doc.get("parameterContexts") or []
#|        for cs in doc.get("controllerServices") or []:
#|            _json_service(flow, cs, None)
#|        flow.reporting_tasks = [
#|            {"name": r.get("name"), "type": r.get("type"), "properties": r.get("properties") or {}}
#|            for r in doc.get("reportingTasks") or []
#|        ]
#|    elif "flowContents" in doc:
#|        flow, root, contexts = Flow(path, "flow-definition"), doc["flowContents"], doc.get("parameterContexts") or {}
#|    else:
#|        raise ValueError(f"{path}: not a NiFi flow (no rootGroup / flowContents)")
#|    if isinstance(contexts, dict):
#|        contexts = list(contexts.values())
#|    for pc in contexts:
#|        flow.param_contexts[pc["name"]] = {
#|            "params": {
#|                p["name"]: {"value": p.get("value"), "sensitive": bool(p.get("sensitive")), "description": p.get("description")}
#|                for p in pc.get("parameters") or []
#|            },
#|            "inherits": list(pc.get("inheritedParameterContexts") or []),
#|            "description": pc.get("description"),
#|        }
#|    _json_group(flow, root, None)
#|    flow.root_id = root.get("identifier")
#|    return flow
#|
#|
#|def _json_vc(c):
#|    if not c:
#|        return None
#|    return {"registry": c.get("registryUrl") or c.get("registryId") or c.get("storageLocation"), "bucket": c.get("bucketId"),
#|            "flow": c.get("flowId"), "flow_name": c.get("flowName"), "version": c.get("version"), "latest": c.get("latest")}
#|
#|
#|def _xml_vc(el):
#|    if el is None:
#|        return None
#|    return {"registry": _t(el, "registryId"), "bucket": _t(el, "bucketName") or _t(el, "bucketId"), "bucket_id": _t(el, "bucketId"),
#|            "flow": _t(el, "flowId"), "flow_name": _t(el, "flowName"), "version": _t(el, "version")}
#|
#|
#|def _json_group(flow, g, parent_id):
#|    gid = g.get("identifier")
#|    flow.alias(g.get("instanceIdentifier"), gid)
#|    flow.groups[gid] = {
#|        "id": gid, "name": g.get("name") or "NiFi Flow", "parent_id": parent_id, "comments": g.get("comments") or "",
#|        "variables": dict(g.get("variables") or {}), "parameter_context": g.get("parameterContextName"),
#|        "versioned": bool(g.get("versionedFlowCoordinates")), "instance_id": g.get("instanceIdentifier") or gid,
#|        "version_control": _json_vc(g.get("versionedFlowCoordinates")),
#|    }
#|    for p in g.get("processors") or []:
#|        _json_component(flow, p, "PROCESSOR", gid)
#|    for p in g.get("inputPorts") or []:
#|        _json_component(flow, p, "INPUT_PORT", gid)
#|    for p in g.get("outputPorts") or []:
#|        _json_component(flow, p, "OUTPUT_PORT", gid)
#|    for f in g.get("funnels") or []:
#|        _json_component(flow, f, "FUNNEL", gid)
#|    for rpg in g.get("remoteProcessGroups") or []:
#|        target = rpg.get("targetUris") or rpg.get("targetUri") or ""
#|        for kind, key in (("REMOTE_INPUT_PORT", "inputPorts"), ("REMOTE_OUTPUT_PORT", "outputPorts")):
#|            for port in rpg.get(key) or []:
#|                comp = _json_component(flow, port, kind, gid)
#|                comp["name"] = f"{rpg.get('name') or target} :: {port.get('name')}"
#|                comp["type"] = f"remote site-to-site {target}"
#|    for cs in g.get("controllerServices") or []:
#|        _json_service(flow, cs, gid)
#|    for c in g.get("connections") or []:
#|        src, dst = c.get("source") or {}, c.get("destination") or {}
#|        flow.alias(c.get("instanceIdentifier"), c.get("identifier"))
#|        flow.connections.append({
#|            "id": c.get("identifier"), "name": c.get("name") or "", "group_id": gid,
#|            "source_id": src.get("id"), "source_type": src.get("type"), "source_name": src.get("name"), "source_group_id": src.get("groupId"),
#|            "dest_id": dst.get("id"), "dest_type": dst.get("type"), "dest_name": dst.get("name"), "dest_group_id": dst.get("groupId"),
#|            "relationships": sorted(c.get("selectedRelationships") or []),
#|            "backpressure": f"{c.get('backPressureObjectThreshold')} / {c.get('backPressureDataSizeThreshold')}",
#|            "expiration": c.get("flowFileExpiration"), "prioritizers": c.get("prioritizers") or [],
#|            "load_balance": c.get("loadBalanceStrategy"),
#|        })
#|    for label in g.get("labels") or []:
#|        if (label.get("label") or "").strip():
#|            flow.labels.append({"group_id": gid, "text": label["label"].strip()})
#|    for child in g.get("processGroups") or []:
#|        _json_group(flow, child, gid)
#|
#|
#|def _json_component(flow, p, kind, gid):
#|    cid = p.get("identifier")
#|    flow.alias(p.get("instanceIdentifier"), cid)
#|    comp = _component(
#|        cid, p.get("instanceIdentifier"), kind, p.get("name") or ("funnel" if kind == "FUNNEL" else ""), p.get("type"),
#|        p.get("bundle"), gid,
#|        properties={k: v for k, v in (p.get("properties") or {}).items() if v is not None},
#|        state="STOPPED" if p.get("scheduledState") == "ENABLED" else p.get("scheduledState"), scheduling_strategy=p.get("schedulingStrategy"),
#|        scheduling_period=p.get("schedulingPeriod"), concurrent_tasks=p.get("concurrentlySchedulableTaskCount"),
#|        auto_terminated=sorted(p.get("autoTerminatedRelationships") or []), comments=p.get("comments") or "",
#|        execution_node=p.get("executionNode"), annotation_data=p.get("annotationData") or "",
#|    )
#|    flow.components[cid] = comp
#|    return comp
#|
#|
#|def _json_service(flow, cs, gid):
#|    sid = cs.get("identifier")
#|    flow.alias(cs.get("instanceIdentifier"), sid)
#|    flow.services[sid] = _component(
#|        sid, cs.get("instanceIdentifier"), "CONTROLLER_SERVICE", cs.get("name"), cs.get("type"), cs.get("bundle"), gid,
#|        properties={k: v for k, v in (cs.get("properties") or {}).items() if v is not None},
#|        state=cs.get("scheduledState"), comments=cs.get("comments") or "",
#|    )
#|
#|
#|# ------------------------------------------------------------------------------------------------ XML
#|
#|def _t(el, tag, default=None):
#|    child = el.find(tag)
#|    return child.text if child is not None and child.text is not None else default
#|
#|
#|def _props(el):
#|    return {_t(p, "name"): _t(p, "value") for p in el.findall("property") if _t(p, "value") is not None}
#|
#|
#|def _bundle(el):
#|    b = el.find("bundle")
#|    return {"group": _t(b, "group"), "artifact": _t(b, "artifact"), "version": _t(b, "version")} if b is not None else {}
#|
#|
#|def _load_xml(path, root_el):
#|    flow = Flow(path, "flow.xml")
#|    ctx_names = {}
#|    for pc in root_el.findall("./parameterContexts/parameterContext"):
#|        name = _t(pc, "name")
#|        ctx_names[_t(pc, "id")] = name
#|        flow.param_contexts[name] = {
#|            "params": {
#|                _t(p, "name"): {"value": _t(p, "value"), "sensitive": _t(p, "sensitive") == "true", "description": _t(p, "description")}
#|                for p in pc.findall("parameter")
#|            },
#|            "inherits": [x.text for x in pc.findall("inheritedParameterContextId") if x.text],
#|            "description": _t(pc, "description"),
#|        }
#|    for ctx in flow.param_contexts.values():
#|        ctx["inherits"] = [ctx_names.get(i, i) for i in ctx["inherits"]]
#|    rg = root_el.find("rootGroup")
#|    _xml_group(flow, rg, None, ctx_names)
#|    flow.root_id = _t(rg, "id")
#|    for cs in root_el.findall("./controllerServices/controllerService"):
#|        _xml_service(flow, cs, None)
#|    for rt in root_el.findall("./reportingTasks/reportingTask"):
#|        flow.reporting_tasks.append({"name": _t(rt, "name"), "type": _t(rt, "class"), "properties": _props(rt)})
#|    return flow
#|
#|
#|def _xml_group(flow, g, parent_id, ctx_names):
#|    gid = _t(g, "id")
#|    flow.alias(_t(g, "versionedComponentId"), gid)
#|    flow.groups[gid] = {
#|        "id": gid, "name": _t(g, "name") or "NiFi Flow", "parent_id": parent_id, "comments": _t(g, "comment", ""),
#|        "variables": {v.get("name"): v.get("value") for v in g.findall("variable")},
#|        "parameter_context": ctx_names.get(_t(g, "parameterContextId")), "versioned": g.find("versionControlInformation") is not None,
#|        "instance_id": gid, "version_control": _xml_vc(g.find("versionControlInformation")),
#|    }
#|    for p in g.findall("processor"):
#|        pid = _t(p, "id")
#|        flow.alias(_t(p, "versionedComponentId"), pid)
#|        flow.components[pid] = _component(
#|            pid, pid, "PROCESSOR", _t(p, "name"), _t(p, "class"), _bundle(p), gid, properties=_props(p),
#|            state=_t(p, "scheduledState"), scheduling_strategy=_t(p, "schedulingStrategy"),
#|            scheduling_period=_t(p, "schedulingPeriod"), concurrent_tasks=int(_t(p, "maxConcurrentTasks", "1")),
#|            auto_terminated=sorted(x.text for x in p.findall("autoTerminatedRelationship") if x.text),
#|            comments=_t(p, "comment", ""), execution_node=_t(p, "executionNode"), annotation_data=_t(p, "annotationData", ""),
#|        )
#|    for tag, kind in (("inputPort", "INPUT_PORT"), ("outputPort", "OUTPUT_PORT"), ("funnel", "FUNNEL")):
#|        for p in g.findall(tag):
#|            pid = _t(p, "id")
#|            flow.alias(_t(p, "versionedComponentId"), pid)
#|            flow.components[pid] = _component(pid, pid, kind, _t(p, "name", "funnel" if kind == "FUNNEL" else ""), None, {}, gid,
#|                                              state=_t(p, "scheduledState"), comments=_t(p, "comments", ""))
#|    for rpg in g.findall("remoteProcessGroup"):
#|        target = _t(rpg, "urls") or _t(rpg, "url") or ""
#|        for tag, kind in (("inputPort", "REMOTE_INPUT_PORT"), ("outputPort", "REMOTE_OUTPUT_PORT")):
#|            for port in rpg.findall(tag):
#|                pid = _t(port, "id")
#|                flow.alias(_t(port, "versionedComponentId"), pid)
#|                flow.components[pid] = _component(pid, pid, kind, f"{_t(rpg, 'name') or target} :: {_t(port, 'name')}",
#|                                                  f"remote site-to-site {target}", {}, gid)
#|    for cs in g.findall("controllerService"):
#|        _xml_service(flow, cs, gid)
#|    for c in g.findall("connection"):
#|        flow.alias(_t(c, "versionedComponentId"), _t(c, "id"))
#|        flow.connections.append({
#|            "id": _t(c, "id"), "name": _t(c, "name", ""), "group_id": gid,
#|            "source_id": _t(c, "sourceId"), "source_type": _t(c, "sourceType"), "source_name": None, "source_group_id": _t(c, "sourceGroupId"),
#|            "dest_id": _t(c, "destinationId"), "dest_type": _t(c, "destinationType"), "dest_name": None, "dest_group_id": _t(c, "destinationGroupId"),
#|            "relationships": sorted(x.text for x in c.findall("relationship") if x.text),
#|            "backpressure": f"{_t(c, 'maxWorkQueueSize')} / {_t(c, 'maxWorkQueueDataSize')}",
#|            "expiration": _t(c, "flowFileExpiration"),
#|            "prioritizers": [x.text for x in c.findall("queuePrioritizerClass") if x.text],
#|            "load_balance": _t(c, "loadBalanceStrategy"),
#|        })
#|    for label in g.findall("label"):
#|        if (_t(label, "value") or "").strip():
#|            flow.labels.append({"group_id": gid, "text": _t(label, "value").strip()})
#|    for child in g.findall("processGroup"):
#|        _xml_group(flow, child, gid, ctx_names)
#|
#|
#|def _xml_service(flow, cs, gid):
#|    sid = _t(cs, "id")
#|    flow.alias(_t(cs, "versionedComponentId"), sid)
#|    flow.services[sid] = _component(
#|        sid, sid, "CONTROLLER_SERVICE", _t(cs, "name"), _t(cs, "class"), _bundle(cs), gid, properties=_props(cs),
#|        state="ENABLED" if _t(cs, "enabled") == "true" else "DISABLED", comments=_t(cs, "comment", ""),
#|    )
#@@ FILE nifikb/investigate.py tc f6d959c3058b0a9e
#|"""One-call ticket investigation: metadata diagnosis + provenance + logs + code messages + learnings + static findings,
#|merged into a ranked list of likely causes with the evidence under it. Built for smaller models (Gemini Flash): the
#|tool does the planning, the model explains the result."""
#|import re
#|import time
#|from pathlib import Path
#|
#|from . import audit as auditmod, diagnose as dg, learnings as lm, logs as lg, metadata as metamod, nifiapi, target as tgt
#|
#|PRIORITY = {"provenance": 1, "audit": 2, "target": 2.5, "live": 3, "file-log": 4, "structure": 5, "config-change": 6, "instance": 7,
#|            "processor-log": 8, "learning": 9, "finding": 10, "warning": 11}
#|
#|
#|def _runtime_ids(store, flow_ids):
#|    ids = set(flow_ids)
#|    for fid in flow_ids:
#|        try:
#|            row = store.db.execute("SELECT instance_id FROM components WHERE id=?", (fid,)).fetchone()
#|        except Exception:
#|            row = None
#|        if row and row[0]:
#|            ids.add(row[0])
#|    return sorted(ids)
#|
#|
#|def investigate(cfg, store, names, file=None, feed=None, table=None, error_text=None, headers=(), sample_path=None,
#|                live=False, since_hours=72, record=True):
#|    key = file or feed or table
#|    causes, sections, next_checks = [], [], []
#|
#|    def cause(kind, text):
#|        causes.append((PRIORITY[kind], len(causes), text, kind))
#|
#|    # 1. metadata: definition, structure vs file, target, related config, processors, config changes
#|    diag, proc_ids = None, []
#|    if key and metamod.settings(cfg) and store.get_meta("metadata_model"):
#|        diag = dg.metadata_diagnosis(cfg, store, key, list(headers), live=live, sample_path=sample_path)
#|        sections.append(("Metadata (config tables)", dg.format_text(diag)))
#|        fixes = [f for d in diag.get("definitions") or [] for f in d.get("fixes") or []]
#|        if fixes:
#|            text = "\n".join(f"-- {f['why']} [{f['who']}]" + (f": {f['note']}" if f.get("note") else "") + "\n" + f["sql"] for f in fixes)
#|            sections.insert(0, ("Proposed fixes (for a human to review and run - never applied automatically)", text))
#|        proc_ids = [p["id"] for p in diag.get("processors") or []]
#|        for d in diag.get("definitions") or []:
#|            for i in d["issues"]:
#|                if i["severity"] == "error":
#|                    cause("structure", f"{d['label']}: {i['message']}")
#|                elif i["severity"] == "warn":
#|                    cause("warning", f"{d['label']}: {i['message']}")
#|        for c in diag.get("changed_since_snapshot") or []:
#|            cause("config-change", f"config row changed since the last snapshot: {c}")
#|        recent = [c for c in diag.get("recent_changes") or []
#|                  if time.time() - time.mktime(time.strptime(c["when"], "%Y-%m-%d %H:%M")) < 3 * 86400]
#|        for c in recent[:5]:
#|            cause("config-change", f"config row changed {c['when']}: {c['change']}")
#|        if not diag.get("matches"):
#|            next_checks.append(f"'{key}' matches no config row" + (f" - did you mean {', '.join(diag['suggestions'][:3])}?"
#|                                                                   if diag.get("suggestions") else "; try the feed / table / API name"))
#|    elif key:
#|        next_checks.append("metadata not configured ([metadata] in nifikb.toml) - no structure / config checks")
#|
#|    # 2. provenance: where did the FlowFile(s) end up
#|    api = nifiapi.settings(cfg)
#|    if file and api:
#|        try:
#|            flows = nifiapi.journey(nifiapi.Client(api), filename=Path(file.replace("\\", "/")).name)
#|            sections.append(("Provenance (what happened to the FlowFile)", nifiapi.format_journey(flows, names, file)))
#|            for f in flows:
#|                if f["verdict"].startswith(("DROPPED", "last seen")):
#|                    cause("provenance", f"FlowFile {str(f['uuid'])[:8]} {f['verdict']}"
#|                          + (f" [{', '.join(f'{k}={v}' for k, v in list(f['attributes'].items())[:4])}]" if f["attributes"] else ""))
#|            if not flows:
#|                cause("provenance", f"no provenance events for '{file}': it never entered NiFi under that name (not picked up: "
#|                                    "source path / listing / file-name filter) or its events aged out")
#|        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
#|            next_checks.append(f"provenance not available: {e}")
#|    elif file:
#|        next_checks.append("configure [nifi_api] to see where the FlowFile was dropped (provenance)")
#|
#|    # 2a. the platform's own load-audit record of this file / definition
#|    amodel = store.get_meta("audit_model")
#|    if amodel and (file or diag):
#|        try:
#|            ids = [d["id"] for d in (diag or {}).get("definitions") or []]
#|            fname_a = Path(file.replace("\\", "/")).name if file else None
#|            rows = auditmod.lookup(cfg, amodel, file=fname_a, link_ids=ids if not fname_a else ())
#|            if not rows and ids:
#|                rows = auditmod.lookup(cfg, amodel, link_ids=ids)
#|            sections.append((f"Load audit ({amodel['table']})", auditmod.format_rows(amodel, rows)))
#|            file_rows_a = [r for r in rows if fname_a and fname_a.lower() in str(r.get(amodel["file_column"]) or "").lower()]
#|            if file_rows_a:
#|                last = file_rows_a[0]
#|                if auditmod.is_failure(amodel, last):
#|                    cause("audit", f"load audit: last load FAILED - {auditmod.summarize(amodel, last)}")
#|                else:
#|                    cause("warning", f"load audit: last load recorded as {auditmod.summarize(amodel, last)}")
#|            elif fname_a:
#|                cause("warning", f"no load-audit row for {fname_a}: the load step never recorded this file")
#|        except Exception as e:  # DB down etc.: never break the investigation
#|            next_checks.append(f"load audit not available: {e}")
#|
#|    # 2a'. the target side: did the load write anything to HDFS / S3, and does the Parquet match the structure
#|    if diag and tgt.enabled(cfg):
#|        for d, res in tgt.check_diagnosis(cfg, store.get_meta("metadata_model"), diag, file=file):
#|            sections.append((f"Target output ({d['label']})", tgt.format_check(res)))
#|            for sev, kind, msg in res["issues"]:
#|                if sev == "error":
#|                    cause("target", f"{d['label']} target: {msg}")
#|                elif sev == "warn":
#|                    cause("warning", f"{d['label']} target: {msg}")
#|
#|    # 2b. live health of the processors involved (stuck queue / invalid / stopped) and of the whole instance (disk, heap)
#|    if api:
#|        try:
#|            h = nifiapi.health(nifiapi.Client(api), versioned=store.versioned_groups())
#|            involved = set(_runtime_ids(store, proc_ids))
#|            mine = [p for p in h["problems"] if p.get("component_id") in involved]
#|            instance = [p for p in h["problems"] if p["kind"] in ("disk", "heap", "cluster")]
#|            for p in mine:
#|                cause("live", f"live NiFi: {p['message']}")
#|            for p in instance:
#|                cause("instance", f"live NiFi (whole instance): {p['message']}")
#|            if mine or instance:
#|                sections.append(("Live NiFi health (problems touching this ticket)", "\n".join(
#|                    f"[{p['severity']}] {p['kind']}: {p['message']}" for p in mine + instance)))
#|        except (nifiapi.NiFiApiError, OSError, ValueError) as e:
#|            next_checks.append(f"live health not available: {e}")
#|
#|    # 3. logs: errors about this file, and about the processors involved
#|    lg.index(cfg, store, log=lambda m: None)
#|    fname = Path(file.replace("\\", "/")).name if file else None
#|    file_rows = lg.query(store, filename=fname, limit=10) if fname else []
#|    for r in file_rows:
#|        if r["level"] in ("ERROR", "FATAL", "WARN"):
#|            who = names.get(r["component_id"], r["component_type"] or "NiFi")
#|            cause("file-log", f"{who} logged {r['level']} x{r['n']} for this file: {lg.compact(r['sample'])[:220]}"
#|                              + (f" - cause: {r['cause']}" if r["cause"] else ""))
#|    runtime = _runtime_ids(store, proc_ids)
#|    proc_rows = lg.query(store, component_ids=runtime, since_hours=since_hours, limit=10) if runtime else []
#|    listed = {(r["component_id"], r["template"]) for r in file_rows}
#|    proc_rows = [r for r in proc_rows if (r["component_id"], r["template"]) not in listed]  # already ranked as file errors
#|    for r in proc_rows[:4]:
#|        if r["level"] in ("ERROR", "FATAL"):
#|            cause("processor-log", f"{names.get(r['component_id'], r['component_type'])} logged ERROR x{r['n']} "
#|                                   f"({r['first'][:16]} .. {r['last'][:16]}): {lg.compact(r['sample'])[:180]}"
#|                                   + (f" - cause: {r['cause']}" if r["cause"] else ""))
#|    grep_rows = lg.query(store, grep=error_text, limit=10) if error_text else []
#|    for title, rows in (("Log errors for this file", file_rows), ("Log errors of the processors involved", proc_rows),
#|                        (f"Log lines containing '{error_text}'", grep_rows)):
#|        if rows:
#|            sections.append((title, lg.format_rows(rows, names)))
#|
#|    # 4. the error text in the custom code (which processor / line raises it)
#|    if error_text:
#|        words = [w for w in error_text.replace('"', " ").split() if len(w) > 2][:8]
#|        hits = [r for r in store.search(" ".join(words), 10) if r["kind"] == "message"] if words else []
#|        if hits:
#|            sections.append(("Code that produces this error text", "\n".join(f"{r['title']} -> {r['doc']}: {r['snip']}" for r in hits)))
#|            cause("processor-log", f"the error text comes from {hits[0]['title']} ({hits[0]['doc']})")
#|
#|    # 5. learnings
#|    items = (diag or {}).get("learnings") or []
#|    if not items:
#|        terms = [x for x in (key, fname, table, feed) if x] + (error_text.split()[:6] if error_text else [])
#|        items = dg.learnings_for(cfg, terms)
#|    for i in items[:3]:
#|        if i["score"] >= 3:
#|            cause("learning", f"known issue {i['id']}: {i['title']}")
#|    if items:
#|        sections.append(("Team learnings", "\n".join(f"{i['id']} [{i['kind']}] {i['title']}\n  {i['excerpt'][:300]}" for i in items)))
#|
#|    # 6. static findings on the processors involved
#|    for f in (diag or {}).get("findings") or []:
#|        if f["kind"] in ("attribute-unset", "attribute-misnamed", "custom-source-drift", "custom-nar-missing", "bundle-version",
#|                         "field-mismatch", "missing-table", "unhandled-relationship", "disabled-service"):
#|            cause("finding", f"{f['kind']} on `{f['component_id'][:8]}`: {f['message']}")
#|        elif f["kind"] == "dropped-errors":
#|            cause("warning", f"`{f['component_id'][:8]}` silently drops failures ({f['message'].split(':')[0]}) - errors there leave "
#|                             "only a log line / provenance DROP")
#|
#|    causes.sort()
#|    seen, ranked = set(), []
#|    for _, _, text, kind in causes:
#|        if text not in seen:
#|            seen.add(text)
#|            ranked.append((kind, text))
#|    if key and record:
#|        try:  # remembered for learning suggestions (recurring causes nobody has written down yet)
#|            store.add_investigation(key, [(k, signature(t), t) for k, t in ranked[:3] if k not in NOT_REMEMBERED])
#|        except Exception:
#|            pass  # a read-only / locked KB must not break the investigation
#|    return {"key": key, "causes": [t for _, t in ranked[:10]], "sections": sections, "next_checks": next_checks}
#|
#|
#|NOT_REMEMBERED = {"learning", "instance", "warning"}  # already written down / not about the ticket / too weak
#|
#|
#|def signature(text):
#|    """A cause without its variable parts (dates, counts, ids, quoted values), so repeats of one problem group together."""
#|    s = re.sub(r"'[^']*'|`[^`]*`|\"[^\"]*\"", "'…'", text)
#|    s = re.sub(r"\b[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}\b|\b[0-9a-f]{8}\b", "#", s)
#|    s = re.sub(r"\d{4}-\d\d-\d\d[ T]?[\d:.,]*|\d+", "#", s)
#|    s = re.sub(r"\[[^\]]*=[^\]]*\]", "", s)  # attribute dumps
#|    return re.sub(r"\s+", " ", s).strip()[:300]
#|
#|
#|def format_report(r):
#|    L = [f"# Investigation: {r['key'] or '(no name given)'}", "", "## Most likely causes (ranked; strongest evidence first)"]
#|    L += [f"{n}. {c}" for n, c in enumerate(r["causes"], 1)] or ["(nothing conclusive found - see the evidence and next checks)"]
#|    if r["next_checks"]:
#|        L += ["", "## Next checks"] + [f"- {c}" for c in r["next_checks"]]
#|    for title, text in r["sections"]:
#|        L += ["", f"## {title}", text]
#|    return "\n".join(L)
#@@ FILE nifikb/late.py tc 19dec5c5881231d9
#|"""Late / missing files: learn each feed's arrival pattern from the load-audit history (successful loads) and flag the
#|feeds whose next file is overdue - before a user raises a ticket.
#|
#|Per definition (audit link column) or, without one, per file-name shape (SALES_20260926.csv -> sales_#.csv):
#|  intra-day feeds (median gap < 20 h)  late when nothing arrived for 3 x the usual gap (at least 1 h)
#|  daily feeds                          expected on the weekdays it usually arrives, around its usual time of day;
#|                                       late when today's file is past that time + tolerance (the spread of past arrivals, >= 1 h)
#|  weekly / monthly feeds               late when the gap since the last arrival exceeds 1.5 x the usual gap
#|Feeds with fewer than `min_history` arrivals are not judged."""
#|import datetime as dt
#|import statistics
#|from collections import defaultdict
#|from pathlib import PurePath
#|
#|from . import audit as auditmod, db as dbmod, metadata as metamod
#|
#|
#|def _when(v):
#|    if isinstance(v, dt.datetime):
#|        return v
#|    if isinstance(v, dt.date):
#|        return dt.datetime(v.year, v.month, v.day)
#|    s = str(v or "").strip().replace("T", " ")
#|    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d-%m-%Y %H:%M:%S", "%Y%m%d%H%M%S"):
#|        try:
#|            return dt.datetime.strptime(s[:26], fmt)
#|        except ValueError:
#|            continue
#|    return None
#|
#|
#|def history(cfg, model, days):
#|    """Audit rows of the last `days` days: [{file, when, failed, link}] (oldest first)."""
#|    if not model.get("time_column"):
#|        raise ValueError("the load-audit table has no time column ([audit] time_column)")
#|    a = auditmod.settings(cfg)
#|    dcfg = next(d for d in cfg["databases"] if d["name"] == a["db"])
#|    conn, dialect = dbmod.connect(dcfg)
#|    try:
#|        q = '"' if dialect != "mysql" else "`"
#|        cols = [c for c in (model["file_column"], model["time_column"], model.get("status_column"), model.get("link_column")) if c]
#|        since = (dt.datetime.now() - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
#|        sql = (f"SELECT {', '.join(f'{q}{c}{q}' for c in cols)} FROM {auditmod._fq(dialect, model.get('schema'), model['table'])} "
#|               f"WHERE {q}{model['time_column']}{q} >= {dbmod._ph(dialect)} ORDER BY {q}{model['time_column']}{q} LIMIT 200000")
#|        rows = dbmod._rows(conn, sql, (since,))
#|    finally:
#|        conn.close()
#|    out = []
#|    for r in rows:
#|        when = _when(r.get(model["time_column"]))
#|        if when:
#|            out.append({"file": r.get(model["file_column"]), "when": when, "failed": auditmod.is_failure(model, r),
#|                        "link": r.get(model["link_column"]) if model.get("link_column") else None})
#|    return out
#|
#|
#|def _group_key(row):
#|    if row["link"] is not None:
#|        return ("id", str(row["link"]))
#|    name = PurePath(str(row["file"] or "").replace("\\", "/")).name
#|    return ("shape", metamod._shape(name))
#|
#|
#|def _fmt_gap(seconds):
#|    if seconds < 3600:
#|        return f"{seconds / 60:.0f} min"
#|    if seconds < 2 * 86400:
#|        return f"{seconds / 3600:.1f} h"
#|    return f"{seconds / 86400:.1f} days"
#|
#|
#|def analyse(rows, now=None, min_history=5, labels=None):
#|    """[{key, label, kind, last, expected, late_by, message, last_failed}] for overdue feeds, most overdue first."""
#|    now = now or dt.datetime.now()
#|    groups = defaultdict(list)
#|    for r in rows:
#|        groups[_group_key(r)].append(r)
#|    out = []
#|    for key, rs in groups.items():
#|        rs.sort(key=lambda r: r["when"])
#|        ok = [r["when"] for r in rs if not r["failed"]]
#|        if len(ok) < min_history:
#|            continue
#|        label = (labels or {}).get(key[1]) or (PurePath(str(rs[-1]["file"] or "").replace("\\", "/")).name if key[0] == "id" else key[1])
#|        last = ok[-1]
#|        last_failed = rs[-1]["failed"] and rs[-1]["when"] > last
#|        gaps = [(b - a).total_seconds() for a, b in zip(ok, ok[1:]) if (b - a).total_seconds() > 60]
#|        if not gaps:
#|            continue
#|        gap = statistics.median(gaps)
#|        since_last = (now - last).total_seconds()
#|        item = None
#|        if gap < 20 * 3600:
#|            allowed = max(3 * gap, 3600)
#|            if since_last > allowed:
#|                item = {"kind": "intra-day", "expected": last + dt.timedelta(seconds=gap), "late_by": since_last - gap,
#|                        "message": f"no file for {_fmt_gap(since_last)} (usually every {_fmt_gap(gap)}); last {last:%Y-%m-%d %H:%M}"}
#|        elif gap < 2.5 * 86400:
#|            first_per_day = {}
#|            for w in ok:
#|                first_per_day.setdefault(w.date(), w)
#|            minutes = [w.hour * 60 + w.minute for w in first_per_day.values()]
#|            usual = statistics.median(minutes)
#|            spread = statistics.median([abs(m - usual) for m in minutes]) if len(minutes) > 2 else 0
#|            tolerance = max(60, 3 * spread)
#|            span_days = max(1, (ok[-1].date() - ok[0].date()).days + 1)
#|            weeks = max(1, span_days / 7)
#|            per_weekday = defaultdict(int)
#|            for d in first_per_day:
#|                per_weekday[d.weekday()] += 1
#|            weekdays = {wd for wd in range(7) if per_weekday[wd] / weeks >= 0.6}
#|            due = dt.datetime.combine(now.date(), dt.time()) + dt.timedelta(minutes=usual + tolerance)
#|            if now.weekday() in weekdays and now > due and last.date() < now.date():
#|                item = {"kind": "daily", "expected": due - dt.timedelta(minutes=tolerance),
#|                        "late_by": (now - due).total_seconds() + tolerance * 60,
#|                        "message": f"today's file not loaded - usually by {int(usual // 60):02d}:{int(usual % 60):02d} "
#|                                   f"(±{tolerance:.0f} min, on {_days(weekdays)}); last {last:%Y-%m-%d %H:%M}"}
#|        else:
#|            if since_last > 1.5 * gap + 3600:
#|                item = {"kind": "periodic", "expected": last + dt.timedelta(seconds=gap), "late_by": since_last - gap,
#|                        "message": f"no file for {_fmt_gap(since_last)} (usually every {_fmt_gap(gap)}); last {last:%Y-%m-%d %H:%M}"}
#|        if item:
#|            if last_failed:
#|                item["message"] += f" - the latest attempt ({rs[-1]['file']}, {rs[-1]['when']:%Y-%m-%d %H:%M}) FAILED"
#|            item.update(key=key[1], label=label, last=last, last_failed=last_failed)
#|            out.append(item)
#|    out.sort(key=lambda i: -i["late_by"])
#|    return out
#|
#|
#|def _days(weekdays):
#|    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
#|    if weekdays == set(range(7)):
#|        return "every day"
#|    if weekdays == set(range(5)):
#|        return "Mon-Fri"
#|    return ", ".join(names[d] for d in sorted(weekdays))
#|
#|
#|def labels_from_snapshot(store):
#|    """Definition id -> label (file pattern / name) from the metadata snapshot."""
#|    model = store.get_meta("metadata_model")
#|    if not model or not model.get("definition_table"):
#|        return {}
#|    rows = store.get_meta_rows(exclude=model.get("structure_table")).get(model["definition_table"], [])
#|    return {str(r.get(model["definition_id"])): metamod.definition_label(model, r) for r in rows}
#|
#|
#|def late_files(cfg, store, days=35, now=None, min_history=5):
#|    model = store.get_meta("audit_model")
#|    if not model:
#|        return None
#|    return analyse(history(cfg, model, days), now=now, min_history=min_history, labels=labels_from_snapshot(store))
#|
#|
#|def format_items(items, model=None):
#|    if items is None:
#|        return ["load audit not configured ([audit]) - no arrival history to learn from"]
#|    if not items:
#|        return ["no late or missing files (feeds with enough load history)"]
#|    return [f"**{i['label']}**: {i['message']}" for i in items]
#@@ FILE nifikb/learnings.py t 14b4312d20452b5a
#|"""Team knowledge that the flow, code and databases cannot tell: what we learned while fixing tickets.
#|
#|knowledge/
#|  context.md            curated team context (owners, environments, conventions, quirks) - humans maintain it
#|  learnings/<id>.md     one learning per file, written by people or by agents (Claude, Gemini, ...) after a ticket
#|
#|A learning file is markdown with a small header:
#|
#|    ---
#|    id: 2026-09-26-sales-feed-pipe-delimited
#|    title: SALES feed switches to pipe delimiter at month end
#|    kind: pattern            # fix | pattern | gotcha | context | faq
#|    date: 2026-09-26
#|    author: claude
#|    tags: [delimiter, sales]
#|    applies_to: [SALES_YYYYMMDD.csv, stg_sales, MetadataLookup]
#|    ticket: INC12345
#|    status: active           # active | obsolete
#|    ---
#|    ## Symptom / ## Cause / ## Fix / ## How to spot it next time
#|
#|Files are plain text on purpose: reviewable in git, editable by hand, safe with several agents writing at once.
#|"""
#|import datetime as _dt
#|import os
#|import re
#|from pathlib import Path
#|
#|from .db import BEARER_RE
#|from .util import REDACTED, redact_secrets, slugify
#|
#|KINDS = ("fix", "pattern", "gotcha", "context", "faq")
#|LIST_KEYS = ("tags", "applies_to")
#|MAX_BODY = 20000
#|SECRETISH = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*(?!<redacted>|\*\*\*)\S{4,}")
#|CONTEXT_TEMPLATE = """# Team context
#|
#|Curated by the team; agents read this at the start of every session (kb_overview). Keep it short and current.
#|Promote recurring learnings from `learnings/` into here.
#|
#|## Environments
#|- (e.g. PROD NiFi cluster URL, DEV/UAT, which DB holds the metadata tables)
#|
#|## Ownership / escalation
#|- (who owns which feeds / source systems, who can change OBJ_* rows, on-call rota)
#|
#|## Conventions
#|- (file naming, how new feeds are onboarded, which columns in OBJ_DEFINITION mean what)
#|
#|## Known quirks
#|- (things that look wrong but are intended, recurring vendor issues)
#|"""
#|
#|
#|def root(cfg):
#|    return Path(cfg["knowledge"]["dir"])
#|
#|
#|def ensure(cfg):
#|    r = root(cfg)
#|    (r / "learnings").mkdir(parents=True, exist_ok=True)
#|    if not (r / "context.md").exists():
#|        (r / "context.md").write_text(CONTEXT_TEMPLATE, encoding="utf-8")
#|    return r
#|
#|
#|def clean(text):
#|    """Secrets never enter the knowledge folder (it is sent to AI providers and committed to git)."""
#|    text = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(text or ""))
#|    return SECRETISH.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
#|
#|
#|# ---------------------------------------------------------------------------------------------- parse / write
#|def parse(text, path=None):
#|    meta, body = {}, text
#|    m = re.match(r"﻿?---\s*\n(.*?)\n---\s*\n?(.*)\Z", text, re.S)
#|    if m:
#|        body = m.group(2)
#|        for line in m.group(1).splitlines():
#|            if ":" not in line or line.lstrip().startswith("#"):
#|                continue
#|            k, v = line.split(":", 1)
#|            k, v = k.strip(), re.sub(r"\s+#.*$", "", v).strip()
#|            if k in LIST_KEYS:
#|                v = [x.strip().strip("'\"") for x in v.strip("[]").split(",") if x.strip()]
#|            meta[k] = v
#|    meta.setdefault("id", Path(path).stem if path else "")
#|    meta.setdefault("title", next((ln.lstrip("# ").strip() for ln in body.splitlines() if ln.strip()), meta["id"]))
#|    meta.setdefault("status", "active")
#|    meta.setdefault("kind", "fix")
#|    for k in LIST_KEYS:
#|        meta.setdefault(k, [])
#|    meta["body"] = body.strip()
#|    meta["path"] = str(path) if path else None
#|    return meta
#|
#|
#|def render(meta):
#|    head = ["---"]
#|    for k in ("id", "title", "kind", "date", "author", "tags", "applies_to", "ticket", "status", "replaced_by"):
#|        v = meta.get(k)
#|        if v in (None, "", []):
#|            continue
#|        head.append(f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}")
#|    return "\n".join(head + ["---", "", meta.get("body", "").strip(), ""])
#|
#|
#|def load_all(cfg, include_obsolete=True):
#|    d = root(cfg) / "learnings"
#|    out = []
#|    for p in sorted(d.glob("*.md")) if d.is_dir() else []:
#|        try:
#|            item = parse(p.read_text(encoding="utf-8"), p)
#|        except (OSError, UnicodeDecodeError):
#|            continue
#|        if include_obsolete or item["status"] != "obsolete":
#|            out.append(item)
#|    out.sort(key=lambda x: (x.get("date") or "", x["id"]), reverse=True)
#|    return out
#|
#|
#|def get(cfg, ident):
#|    for item in load_all(cfg):
#|        if item["id"] == ident:
#|            return item
#|    matches = [i for i in load_all(cfg) if i["id"].startswith(ident) or ident.lower() in i["id"]]
#|    return matches[0] if len(matches) == 1 else None
#|
#|
#|def add(cfg, title, body, kind="fix", tags=(), applies_to=(), ticket=None, author=None):
#|    """Write one learning; returns (meta, warnings). Secrets are redacted before anything touches disk."""
#|    title = clean(" ".join((title or "").split()))
#|    body = clean(body or "").strip()
#|    if not title:
#|        raise ValueError("a learning needs a title")
#|    if not body:
#|        raise ValueError("a learning needs a body (symptom, cause, fix, how to spot it)")
#|    if len(body) > MAX_BODY:
#|        raise ValueError(f"body is {len(body)} characters; keep a learning under {MAX_BODY} (link to the ticket instead)")
#|    kind = (kind or "fix").lower()
#|    if kind not in KINDS:
#|        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
#|    warnings = []
#|    existing = load_all(cfg, include_obsolete=False)
#|    words = set(re.findall(r"\w{4,}", title.lower()))
#|    for e in existing:
#|        other = set(re.findall(r"\w{4,}", e["title"].lower()))
#|        if words and len(words & other) / len(words | other) >= 0.6:
#|            warnings.append(f"similar learning exists: {e['id']} - {e['title']} (consider updating or retiring it)")
#|    date = _dt.date.today().isoformat()
#|    d = ensure(cfg) / "learnings"
#|    ident = f"{date}-{slugify(title, 50)}"
#|    n = 2
#|    while (d / f"{ident}.md").exists():
#|        ident = f"{date}-{slugify(title, 50)}-{n}"
#|        n += 1
#|    meta = {"id": ident, "title": title, "kind": kind, "date": date,
#|            "author": clean(author or os.environ.get("NIFIKB_AUTHOR") or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"),
#|            "tags": sorted({clean(t).strip().lower() for t in tags if t and t.strip()}),
#|            "applies_to": [clean(a).strip() for a in applies_to if a and a.strip()],
#|            "ticket": clean(ticket) if ticket else None, "status": "active", "body": body}
#|    path = d / f"{ident}.md"
#|    path.write_text(render(meta), encoding="utf-8")
#|    meta["path"] = str(path)
#|    if re.search(r"(?i)\b(password|secret|token)\b", body) and REDACTED not in body:
#|        warnings.append("the body mentions passwords / secrets - double-check nothing sensitive was written")
#|    return meta, warnings
#|
#|
#|def retire(cfg, ident, reason=None, replaced_by=None):
#|    item = get(cfg, ident)
#|    if not item:
#|        raise ValueError(f"no learning '{ident}'")
#|    item["status"] = "obsolete"
#|    if replaced_by:
#|        item["replaced_by"] = replaced_by
#|    if reason:
#|        item["body"] = item["body"] + f"\n\n> Retired {_dt.date.today().isoformat()}: {clean(reason)}"
#|    Path(item["path"]).write_text(render(item), encoding="utf-8")
#|    return item
#|
#|
#|# ---------------------------------------------------------------------------------------------- relevance
#|def relevant(cfg, terms, limit=5):
#|    """Active learnings whose applies_to / tags / title match any of the terms (file names, tables, processor names,
#|    ids, feed names). applies_to values may be patterns (SALES_*.csv, SALES_YYYYMMDD.csv)."""
#|    from .metadata import pattern_regex
#|    terms = [str(t) for t in terms if t and len(str(t)) >= 3]
#|    low = {t.lower() for t in terms}
#|    scored = []
#|    for item in load_all(cfg, include_obsolete=False):
#|        score = 0
#|        for a in item["applies_to"]:
#|            al = a.lower()
#|            if al in low:
#|                score += 3
#|                continue
#|            rx = pattern_regex(a)
#|            if rx and any(rx.match(t) for t in terms):
#|                score += 3
#|            elif any(len(t) >= 6 and (t in al or al in t) for t in low):
#|                score += 1
#|        score += sum(2 for t in item["tags"] if t.lower() in low)
#|        title = item["title"].lower()
#|        score += sum(1 for t in low if len(t) >= 5 and t in title)
#|        if score:
#|            scored.append((score, item))
#|    scored.sort(key=lambda x: (x[0], x[1].get("date") or ""), reverse=True)
#|    return [dict(i, score=s) for s, i in scored[:limit]]
#|
#|
#|def search_docs(cfg):
#|    """Search-index entries for every learning and for context.md."""
#|    docs = []
#|    for item in load_all(cfg):
#|        rel = f"../knowledge/learnings/{Path(item['path']).name}"
#|        docs.append({"kind": "learning" if item["status"] != "obsolete" else "learning-obsolete", "ref": item["id"],
#|                     "title": item["title"], "doc": rel,
#|                     "body": " ".join([item["body"], " ".join(item["tags"]), " ".join(item["applies_to"]), item.get("ticket") or ""])})
#|    ctx = root(cfg) / "context.md"
#|    if ctx.exists():
#|        docs.append({"kind": "context", "ref": "context.md", "title": "Team context", "doc": "../knowledge/context.md",
#|                     "body": ctx.read_text(encoding="utf-8")})
#|    return docs
#|
#|
#|def context_text(cfg, max_chars=12000):
#|    ctx = root(cfg) / "context.md"
#|    if not ctx.exists():
#|        return ""
#|    text = ctx.read_text(encoding="utf-8")
#|    if text.strip() == CONTEXT_TEMPLATE.strip():
#|        return ""  # untouched template adds nothing
#|    return text if len(text) <= max_chars else text[:max_chars] + "\n[… context.md continues]"
#|
#|
#|def format_item(item, full=True):
#|    head = (f"{item['id']} [{item['kind']}{', OBSOLETE' if item['status'] == 'obsolete' else ''}] {item['title']}"
#|            + (f" · tags: {', '.join(item['tags'])}" if item["tags"] else "")
#|            + (f" · applies to: {', '.join(item['applies_to'])}" if item["applies_to"] else "")
#|            + (f" · ticket {item['ticket']}" if item.get("ticket") else "")
#|            + (f" · {item.get('date')} by {item.get('author')}" if item.get("date") else ""))
#|    return head + ("\n\n" + item["body"] if full else "")
#|
#|
#|# ------------------------------------------------------------------------------------------------ suggestions
#|def suggestions(cfg, store, days=30, min_count=3, limit=10):
#|    """Causes that keep coming back in investigations and that no active learning covers yet:
#|    [{signature, count, keys, days, example, kind}], most frequent first."""
#|    import re
#|    import time
#|    rows = store.investigations_since(time.time() - days * 86400)
#|    groups = {}
#|    for r in rows:
#|        g = groups.setdefault(r["signature"], {"signature": r["signature"], "kind": r["kind"], "count": 0, "keys": [], "days": set(),
#|                                               "example": r["cause"]})
#|        g["count"] += 1
#|        g["days"].add(time.strftime("%Y-%m-%d", time.localtime(r["ts"])))
#|        if r["key"] not in g["keys"]:
#|            g["keys"].append(r["key"])
#|    items = load_all(cfg, include_obsolete=False)
#|    out = []
#|    for g in groups.values():
#|        if g["count"] < min_count or (len(g["days"]) < 2 and len(g["keys"]) < 2):
#|            continue  # one person re-running the same check is not a recurring problem
#|        label = g["example"].split(":", 1)[0] if ":" in g["example"] else ""
#|        words = {w for w in re.findall(r"[a-z][a-z_]{4,}", g["signature"].lower()) if w not in STOP}
#|        terms = g["keys"] + ([label] if label else [])
#|        covered = False
#|        for item in relevant(cfg, terms, limit=10) if items else []:
#|            text = f"{item['title']} {item['body']}".lower()
#|            if item["score"] >= 3 and sum(1 for w in words if w in text) >= min(2, len(words)):
#|                covered = True
#|                break
#|        if not covered:
#|            out.append(dict(g, days=sorted(g["days"])))
#|    out.sort(key=lambda g: (-g["count"], -len(g["keys"])))
#|    return out[:limit]
#|
#|
#|STOP = {"structure", "config", "table", "column", "columns", "field", "fields", "processor", "logged", "error", "errors", "which",
#|        "there", "their", "since", "last", "this", "that", "with", "from", "into", "the", "and", "load", "file", "files"}
#|
#|
#|def format_suggestions(items):
#|    return [f"seen {g['count']}x ({', '.join(g['keys'][:3])}{' …' if len(g['keys']) > 3 else ''}; {g['days'][0]}"
#|            + (f" .. {g['days'][-1]}" if len(g["days"]) > 1 else "") + f") and no learning covers it: {g['example'][:220]}"
#|            for g in items]
#@@ FILE nifikb/logs.py tc 1a2b1ff7ef795c5b
#|"""NiFi logs (nifi-app*.log, nifi-bootstrap*.log): an incremental, compact index of what went wrong.
#|
#|The logs are huge and always growing, so:
#|- files are read incrementally (byte offset per file; rotation / truncation detected by a head fingerprint);
#|  rolled files (nifi-app_2026-09-26_10.0.log, *.gz) are read once; a first run reads at most `initial_tail_mb` of each;
#|- only WARN / ERROR / FATAL lines are kept (plus lifecycle lines of the bootstrap log: starts, stops, restarts, crashes),
#|  with their exception / root cause taken from the stack trace that follows;
#|- each event is tied to the processor / service (runtime id -> flow component), the FlowFile uuid and file name, and a
#|  message template (variable parts removed) so thousands of identical errors collapse into one line with a count;
#|- events older than `keep_days` (relative to the newest one) are pruned; duplicates are ignored.
#|"""
#|import fnmatch
#|import gzip
#|import hashlib
#|import re
#|import time
#|from pathlib import Path
#|
#|from .db import BEARER_RE
#|from .util import REDACTED, redact_secrets
#|
#|UNQUOTED_SECRET_RE = re.compile(r"(?i)\b(pass(?:word|wd)?|pwd|secret|token|api[_-]?key|access[_-]?key)\s*[=:]\s*(?!<redacted>)[^\s,;&'\"]+")
#|EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
#|
#|
#|def scrub(text):
#|    """Secrets, bearer tokens and e-mail addresses out of a log message (error messages often quote data values)."""
#|    text = BEARER_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", redact_secrets(text))
#|    text = UNQUOTED_SECRET_RE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
#|    return EMAIL_RE.sub("<email>", text)
#|
#|LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) (TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\s+\[(.*?)\] (\S+) ?(.*)$")
#|COMP_RE = re.compile(r"\b([A-Z][\w$]*)\[id=([\w-]+)\]")
#|SERVICE_RE = re.compile(r"service=([A-Z][\w$]*)\[id=([\w-]+)\]")
#|FF_START = "StandardFlowFileRecord["
#|CAUSE_RE = re.compile(r"^(?:Caused by: )?((?:[a-z_$][\w$]*\.)+[A-Z][\w$]*(?:Exception|Error|Throwable|Failure)[\w$]*)(?::\s*(.*))?$")
#|LIFECYCLE_RE = re.compile(r"(?i)launched apache nifi|started apache nifi|apache nifi (?:is|has) (?:stopped|shut down|started)|"
#|                          r"nifi pid|stopping apache nifi|restart(?:ing)? apache nifi|nifi (?:has )?died|process .{0,40} died|"
#|                          r"terminated|outofmemory|hs_err|killing|not running|"
#|                          r"graceful shutdown|failed to start|shutdown hook")
#|UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
#|DEFAULT_PATTERNS = ("nifi-app*.log*", "nifi-bootstrap*.log*")
#|
#|
#|def settings(cfg):
#|    lg = dict(cfg.get("logs") or {})
#|    home = cfg["nifi"].get("home")
#|    dirs = lg.get("dirs") or ([str(Path(home) / "logs")] if home else [])
#|    return {"dirs": dirs, "patterns": lg.get("files") or list(DEFAULT_PATTERNS), "keep_days": float(lg.get("keep_days", 14)),
#|            "initial_tail_mb": float(lg.get("initial_tail_mb", 200)), "enabled": lg.get("enabled", True) and bool(dirs)}
#|
#|
#|def log_files(s):
#|    out = []
#|    for d in s["dirs"]:
#|        p = Path(d)
#|        if p.is_dir():
#|            out += [f for f in sorted(p.iterdir()) if f.is_file() and any(fnmatch.fnmatch(f.name, pat) for pat in s["patterns"])]
#|    return out
#|
#|
#|# ---------------------------------------------------------------------------------------------- parsing
#|def _flowfile(msg):
#|    """(uuid, file name, message with the FlowFile record replaced by <flowfile>) - the record nests brackets."""
#|    i = msg.find(FF_START)
#|    if i < 0:
#|        return None, None, msg
#|    depth, j = 0, i + len(FF_START) - 1
#|    while j < len(msg):
#|        if msg[j] == "[":
#|            depth += 1
#|        elif msg[j] == "]":
#|            depth -= 1
#|            if depth == 0:
#|                break
#|        j += 1
#|    rec = msg[i:j + 1]
#|    uuid = re.search(r"uuid=([0-9a-f-]{36})", rec)
#|    name = re.search(r",name=(.*?),size=", rec)
#|    fname = name.group(1) if name else None
#|    if fname and UUID_RE.fullmatch(fname):
#|        fname = None  # FlowFiles created inside NiFi are named after their uuid: not a file name
#|    return (uuid.group(1) if uuid else None, fname, msg[:i] + "<flowfile>" + msg[j + 1:])
#|
#|
#|def compact(msg):
#|    """Message with the FlowFile record shortened to FlowFile[uuid8, name]."""
#|    uuid, fname, stripped = _flowfile(msg)
#|    if not uuid:
#|        return msg
#|    return stripped.replace("<flowfile>", f"FlowFile[{uuid[:8]}" + (f", {fname}]" if fname else "]"))
#|
#|
#|def template(msg):
#|    """Stable shape of a message: ids, numbers, quoted values and paths replaced."""
#|    t = UUID_RE.sub("<id>", msg)
#|    t = re.sub(r"'[^']{0,200}'|\"[^\"]{0,200}\"", "<v>", t)
#|    t = re.sub(r"(?:[A-Za-z]:)?[\\/][^\s,;\]]+", "<path>", t)
#|    t = re.sub(r"\b\d+(?:[.,]\d+)*\b", "<n>", t)
#|    return re.sub(r"\s+", " ", t)[:300]
#|
#|
#|def parse_lines(lines, source, bootstrap=False):
#|    """Yield events from an iterable of (line_no, text)."""
#|    ev, cont = None, 0
#|    for no, line in lines:
#|        line = line.rstrip("\r\n")
#|        m = LINE_RE.match(line)
#|        if m:
#|            if ev:
#|                yield ev
#|            ev, cont = None, 0
#|            ts, ms, level, thread, logger, msg = m.groups()
#|            keep = level in ("WARN", "ERROR", "FATAL") or (bootstrap and LIFECYCLE_RE.search(msg))
#|            if not keep:
#|                continue
#|            uuid, fname, stripped = _flowfile(msg)
#|            comp = SERVICE_RE.search(msg) or COMP_RE.search(msg)
#|            ev = {"ts": f"{ts}.{ms}", "epoch": time.mktime(time.strptime(ts, "%Y-%m-%d %H:%M:%S")) + int(ms) / 1000,
#|                  "level": level if not (bootstrap and level == "INFO") else "LIFECYCLE", "thread": thread[:80],
#|                  "logger": logger, "component_type": comp.group(1) if comp else None,
#|                  "component_id": comp.group(2) if comp else None, "flowfile_uuid": uuid, "filename": fname,
#|                  "message": scrub(msg)[:2000], "cause": None, "file": source, "line": no}
#|            ev["template"] = template(COMP_RE.sub(lambda x: x.group(1), stripped))
#|        elif ev and cont < 60:
#|            cont += 1
#|            c = CAUSE_RE.match(line.strip())
#|            if c and not line.lstrip().startswith("at "):
#|                ev["cause"] = scrub(f"{c.group(1).rsplit('.', 1)[-1]}: {c.group(2) or ''}".strip(": "))[:600]
#|    if ev:
#|        yield ev
#|
#|
#|def _head(path):
#|    opener = gzip.open if path.suffix == ".gz" else open
#|    try:
#|        with opener(path, "rb") as f:
#|            return hashlib.sha1(f.read(4096)).hexdigest()
#|    except OSError:
#|        return ""
#|
#|
#|def _read(path, start):
#|    """(line_no, text) from byte offset `start` (whole file for .gz); returns the iterator and a callable end offset."""
#|    if path.suffix == ".gz":
#|        f = gzip.open(path, "rt", encoding="utf-8", errors="replace")
#|    else:
#|        f = open(path, "rb")
#|        f.seek(start)
#|        if start:
#|            f.readline()  # we may have landed mid-line
#|    state = {"end": start}
#|
#|    def gen():
#|        with f:
#|            for i, raw in enumerate(f, 1):
#|                yield i, raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
#|            if not isinstance(f, gzip.GzipFile) and hasattr(f, "tell"):
#|                try:
#|                    state["end"] = f.tell()
#|                except (OSError, ValueError):
#|                    pass
#|    return gen(), state
#|
#|
#|# ---------------------------------------------------------------------------------------------- indexing
#|def index(cfg, store, log=print):
#|    """Bring the log index up to date. Returns (files read, events added)."""
#|    s = settings(cfg)
#|    if not s["enabled"]:
#|        return 0, 0
#|    files, added = 0, 0
#|    for path in log_files(s):
#|        st = path.stat()
#|        head = _head(path)
#|        row = store.db.execute("SELECT sig, offset, head FROM log_files WHERE path=?", (str(path),)).fetchone()
#|        rolled = path.suffix == ".gz" or re.search(r"_\d{4}-\d{2}-\d{2}", path.name)
#|        sig = f"{st.st_size}:{int(st.st_mtime)}"
#|        if row and (row["sig"] == sig or (rolled and row["head"] == head)):
#|            continue  # unchanged, or a rolled file already read
#|        if rolled and time.time() - st.st_mtime > s["keep_days"] * 86400 * 4 and not row:
#|            continue  # very old rolled file
#|        start = 0
#|        if row and not rolled and row["head"] == head and st.st_size >= row["offset"]:
#|            start = row["offset"]  # the same file grew: read only the new part
#|        elif not row and path.suffix != ".gz" and st.st_size > s["initial_tail_mb"] * 1e6:
#|            start = int(st.st_size - s["initial_tail_mb"] * 1e6)  # first run on a huge file: its tail only
#|        lines, state = _read(path, start)
#|        events = list(parse_lines(lines, path.name, bootstrap="bootstrap" in path.name))
#|        added += store.add_log_events(events)
#|        end = state["end"] if path.suffix != ".gz" else st.st_size
#|        store.db.execute("INSERT OR REPLACE INTO log_files(path, sig, offset, head) VALUES(?,?,?,?)", (str(path), sig, end or st.st_size, head))
#|        files += 1
#|    store.prune_log_events(s["keep_days"])
#|    store.db.commit()
#|    if files:
#|        log(f"  logs: {files} file(s) read, {added} new warning / error event(s)")
#|    return files, added
#|
#|
#|# ---------------------------------------------------------------------------------------------- queries
#|def query(store, component_ids=(), filename=None, uuid=None, grep=None, level=None, since_hours=None, limit=50):
#|    where, params = [], []
#|    if component_ids:
#|        where.append(f"component_id IN ({','.join('?' * len(component_ids))})")
#|        params += list(component_ids)
#|    if filename:
#|        where.append("(filename = ? OR message LIKE ?)")
#|        params += [filename, f"%{filename}%"]
#|    if uuid:
#|        where.append("flowfile_uuid = ?")
#|        params.append(uuid)
#|    if grep:
#|        where.append("(message LIKE ? OR cause LIKE ?)")
#|        params += [f"%{grep}%", f"%{grep}%"]
#|    if level:
#|        where.append("level = ?")
#|        params.append(level.upper())
#|    if since_hours:
#|        newest = store.db.execute("SELECT MAX(epoch) FROM log_events").fetchone()[0] or time.time()
#|        where.append("epoch >= ?")
#|        params.append(newest - float(since_hours) * 3600)  # relative to the newest event: works on copied / old logs too
#|    sql = ("SELECT template, level, component_type, component_id, COUNT(*) n, MIN(ts) first, MAX(ts) last, "
#|           "MAX(cause) cause, MAX(message) sample, GROUP_CONCAT(DISTINCT filename) files, MAX(flowfile_uuid) uuid "
#|           "FROM log_events" + (" WHERE " + " AND ".join(where) if where else "")
#|           + " GROUP BY template, level, component_id ORDER BY MAX(epoch) DESC LIMIT ?")
#|    return store.db.execute(sql, (*params, limit)).fetchall()
#|
#|
#|def format_rows(rows, names=None):
#|    names = names or {}
#|    if not rows:
#|        return "no matching warnings / errors in the indexed logs"
#|    L = []
#|    for r in rows:
#|        who = r["component_type"] or ""
#|        if r["component_id"]:
#|            flow = names.get(r["component_id"])
#|            who += f" `{r['component_id'][:8]}`" + (f" ({flow})" if flow else "")
#|        files = [f for f in (r["files"] or "").split(",") if f][:3]
#|        L.append(f"[{r['level']}] x{r['n']} {r['first'][:16]} .. {r['last'][:16]}  {who}".rstrip())
#|        L.append(f"    {compact(r['sample'])[:400]}")
#|        if r["cause"]:
#|            L.append(f"    cause: {r['cause']}")
#|        if files:
#|            L.append(f"    files: {', '.join(files)}")
#|    return "\n".join(L)
#@@ END part 2 of 5 files 14
