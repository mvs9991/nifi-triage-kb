"""Index custom processor code and scripts: NiFi component metadata plus hardcoded values and SQL tables.

Parsing is regex based on purpose (no JDK / parser dependency). It targets the idioms NiFi components are
written with (PropertyDescriptor.Builder, Relationship.Builder, @CapabilityDescription, session.putAttribute).
"""
import re
from pathlib import Path

from . import sqlparse
from .util import (HOST_RE, IP_RE, JDBC_RE, SECRET_ASSIGN_RE, SECRET_NAME, UNIX_PATH_RE, URL_RE, WIN_PATH_RE, REDACTED, clip,
                   redact_secrets)

LANGS = {
    ".java": "java", ".groovy": "groovy", ".kt": "kotlin", ".scala": "scala",
    ".py": "python", ".sh": "shell", ".bash": "shell", ".ps1": "powershell", ".bat": "batch", ".cmd": "batch",
    ".sql": "sql", ".js": "javascript", ".rb": "ruby",
    ".properties": "config", ".yaml": "config", ".yml": "config", ".conf": "config", ".cfg": "config", ".ini": "config",
}
SKIP_DIRS = {".git", ".svn", ".idea", ".vscode", "target", "build", "out", "node_modules", "__pycache__", ".gradle",
             "dist", ".mvn", "venv", ".venv", ".tox"}
MAX_BYTES = 2_000_000
JVM = {"java", "groovy", "kotlin", "scala"}

PARSER_VERSION = "4"  # bump when index_file output changes, so cached per-file results are re-parsed

STR_LIT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
PKG_RE = re.compile(r"^\s*package\s+([\w.]+)", re.M)
DECL_RE = re.compile(
    r"^[ \t]*(?:@[\w.]+(?:\([^)\n]*\))?\s+)*((?:(?:public|protected|private|abstract|final|static|sealed|non-sealed|strictfp)\s+)*)"
    r"(class|interface|enum|record)\s+(\w+)(?:\s*<[^>{]*>)?(?:\s*\([^)]*\))?"
    r"(?:\s+extends\s+([\w.<>, ?]+?))?(?:\s+implements\s+([\w.<>, ?]+?))?\s*\{", re.M)
PD_RE = re.compile(r"(?:(\w+)\s*=\s*)?new\s+PropertyDescriptor\.Builder\(\)(.*?)\.build\(\)", re.S)
REL_RE = re.compile(r"(?:(\w+)\s*=\s*)?new\s+Relationship\.Builder\(\)(.*?)\.build\(\)", re.S)
ALLOWABLE_RE = re.compile(r"(\w+)\s*=\s*new\s+AllowableValue\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+|[\w.]+)")
ARG = r"((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+|[\w.]+(?:\(\))?)"
PUT_ATTR_RE = re.compile(r"putAttribute\(\s*[\w.()]+\s*,\s*" + ARG + r"\s*,")
REMOVE_ATTR_RE = re.compile(r"removeAttribute\(\s*[\w.()]+\s*,\s*" + ARG + r"\s*\)")
GET_ATTR_RE = re.compile(r"getAttribute\(\s*" + ARG + r"\s*\)")
PUT_ALL_RE = re.compile(r"putAllAttributes\(\s*[\w.()]+\s*,\s*(\w+)\s*\)")
CONST_RE = re.compile(r"(?:(?:public|protected|private|static|final)\s+)+String\s+([A-Z][A-Z0-9_]*)\s*=\s*"
                      r"((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+|[\w.]+)\s*;")
IFACE_CONST_RE = re.compile(r"^\s*String\s+([A-Z][A-Z0-9_]*)\s*=\s*((?:\"(?:[^\"\\\n]|\\.)*\"\s*\+?\s*)+)\s*;", re.M)
ENUM_CONST_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*\(\s*\"([^\"]+)\"", re.M)
ANNOT_STR_RE = r"@{}\s*\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+)\)"
TAGS_RE = re.compile(r"@Tags\s*\(\s*\{([^}]*)\}\s*\)")
WRITES_RE = re.compile(r"@WritesAttribute\s*\(\s*attribute\s*=\s*\"([^\"]+)\"(?:\s*,\s*description\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+))?")
READS_RE = re.compile(r"@ReadsAttribute\s*\(\s*attribute\s*=\s*\"([^\"]+)\"(?:\s*,\s*description\s*=\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+))?")
DYNPROP_RE = re.compile(r"@DynamicProperty\s*\((.*?)\)\s*(?=@|public|protected|private|abstract|final|class)", re.S)
INPUT_REQ_RE = re.compile(r"@InputRequirement\s*\(\s*(?:InputRequirement\.)?Requirement\.(\w+)")
FLAG_ANNOTS = ("SupportsBatching", "TriggerSerially", "TriggerWhenEmpty", "Stateful", "Restricted", "SideEffectFree",
               "PrimaryNodeOnly", "DefaultSchedule", "RequiresInstanceClassLoading", "Deprecated")
METHOD_RE = re.compile(r"^\s*(?:@\w+\s*)*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\(", re.M)
MESSAGE_RE = re.compile(r"(?:\b(?:log|logger|LOG|LOGGER)|getLogger\(\))\s*\.\s*(error|warn|info|debug)\(\s*"
                        r"((?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+)(?:\s*\+\s*(?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+))*)")
THROW_RE = re.compile(r"throw\s+new\s+(\w+(?:Exception|Error))\(\s*"
                      r"((?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+)(?:\s*\+\s*(?:\"(?:[^\"\\\n]|\\.)*\"|[\w.()\[\]]+))*)")
PY_MESSAGE_RE = re.compile(r"(?:\b(?:logging|log|logger|LOG|LOGGER)\.(error|warning|warn|info|exception|critical)\(\s*f?[\"']([^\"'\n]+)[\"']"
                           r"|\braise\s+(\w+)\(\s*f?[\"']([^\"'\n]+)[\"'])")
PY_DEF_RE = re.compile(r"^\s*def\s+(\w+)\s*\(", re.M)
PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)
NIFI_BASES = ("Processor", "ControllerService", "ReportingTask", "RecordReader", "RecordSetWriter")
CORE_ATTRIBUTE_KEYS = {"FILENAME": "filename", "PATH": "path", "ABSOLUTE_PATH": "absolute.path", "UUID": "uuid",
                       "MIME_TYPE": "mime.type", "DISCARD_REASON": "discard.reason", "ALTERNATE_IDENTIFIER": "alternate.identifier",
                       "PRIORITY": "priority"}
IO_PATTERNS = {
    "jdbc": r"DBCPService|getConnection\(|PreparedStatement|DriverManager|JdbcTemplate|ResultSet\b",
    "sftp/ssh": r"JSch|ChannelSftp|SSHClient|SFTPClient|SftpClient|com\.jcraft|SFTPTransfer|net\.schmizz",
    "http": r"HttpClient|HttpURLConnection|OkHttpClient|RestTemplate|WebClient|HttpGet\b|HttpPost\b|WebClientService",
    "s3": r"AmazonS3|S3Client|PutObjectRequest|GetObjectRequest",
    "kafka": r"KafkaProducer|KafkaConsumer",
    "file system": r"Files\.(?:write|move|copy|delete|newBufferedWriter|readAllLines|lines|walk|list)\(|new File\(|FileInputStream|FileOutputStream",
    "json": r"ObjectMapper|JsonNode|Gson\b|JSONObject|JsonPath",
    "records": r"RecordReaderFactory|RecordSetWriterFactory",
    "shell": r"ProcessBuilder|Runtime\.getRuntime\(\)\.exec",
    "email": r"javax\.mail|jakarta\.mail|Transport\.send",
    "cache": r"DistributedMapCacheClient|MapCacheClient",
    "state": r"getStateManager|StateManager\b",
    "spark": r"SparkSession|SparkLauncher|spark-submit",
}


def _concat(s):
    """Join "a" + "b" string concatenations into one literal."""
    return "".join(m.group(1) for m in STR_LIT.finditer(s)).replace('\\"', '"').replace("\\n", " ")


def _template(expr):
    """"File " + name + " not found" -> 'File {} not found' (log / exception message templates)."""
    parts = re.split(r"\s*\+\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", expr)
    out = []
    for p in parts:
        p = p.strip()
        m = STR_LIT.fullmatch(p)
        out.append(m.group(1).replace('\\"', '"').replace("\\n", " ") if m else "{}")
    return re.sub(r"(\{\}\s*)+", "{} ", "".join(out)).strip()


def _arg(expr, consts):
    """Value of a builder / call argument: a literal, a (qualified) constant, Enum.X.key() or CoreAttributes.X.key().
    Unresolved constants come back as '@ref:Name' and are resolved across files by CodeIndex."""
    if expr is None:
        return None
    expr = expr.strip()
    if expr.startswith('"'):
        return _concat(expr)
    m = re.fullmatch(r"(?:[\w.]*\.)?CoreAttributes\.(\w+)\.key\(\)", expr)
    if m:
        return CORE_ATTRIBUTE_KEYS.get(m.group(1), m.group(1).lower())
    ref = re.sub(r"\.(?:key|getKey|value|getValue|getName|name|toString)\(\)$", "", expr)
    if not re.fullmatch(r"[\w.]+", ref) or not re.search(r"[A-Z]", ref.split(".")[-1][:1]):
        return None
    return consts.get(ref) or consts.get(ref.split(".")[-1]) or f"@ref:{ref}"


def _call(builder, name, consts=None):
    m = re.search(r"\.{}\(\s*((?:\"(?:[^\"\\]|\\.)*\"\s*\+?\s*)+|[\w.]+(?:\(\))?)\s*\)".format(name), builder, re.S)
    return _arg(m.group(1), consts or {}) if m else None


def _lineno(text, pos):
    return text.count("\n", 0, pos) + 1


def iter_code_files(roots):
    for root in roots:
        root = Path(root)
        if root.is_file():
            yield root
            continue
        if not root.is_dir():
            continue
        stack = [root]
        while stack:
            d = stack.pop()
            try:
                entries = sorted(d.iterdir())
            except OSError:
                continue
            for e in entries:
                if e.is_dir():
                    if e.name not in SKIP_DIRS:
                        stack.append(e)
                elif (e.suffix.lower() in LANGS or e.name == "pom.xml" or "META-INF" in e.parts and "services" in e.parts) \
                        and e.stat().st_size <= MAX_BYTES:
                    yield e


def index_file(path):
    """Everything worth knowing about one source file, JSON-serializable."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    lang = "pom" if path.name == "pom.xml" else "services" if "META-INF" in path.parts else LANGS.get(path.suffix.lower(), "other")
    info = {"path": str(path), "lang": lang, "lines": text.count("\n") + 1, "components": [], "hardcoded": [],
            "tables": [], "functions": [], "imports": [], "is_test": bool(re.search(r"[\\/]src[\\/](?:test|it|integration-test)[\\/]", str(path))
                                                                             or re.match(r"test_\w+\.py$", path.name))}
    if lang == "pom":
        info["artifact"] = _pom_artifact(text)
        return info
    if lang == "services":
        info["service_classes"] = [ln.split("#")[0].strip() for ln in text.splitlines() if ln.split("#")[0].strip()]
        return info
    if lang in JVM:
        info["package"] = (PKG_RE.search(text) or [None, None])[1]
        info.update(_jvm_file(text, info["package"]))
        info["functions"] = sorted(set(METHOD_RE.findall(text)))[:80]
    elif lang == "python":
        info["functions"] = PY_DEF_RE.findall(text)[:80]
        info["imports"] = sorted({a or b for a, b in PY_IMPORT_RE.findall(text)})
        info["messages"] = [{"level": lvl, "text": re.sub(r"\{[^}]*\}|%[sdrf]", "{}", msg), "line": _lineno(text, m.start())}
                            for m in PY_MESSAGE_RE.finditer(text) for lvl, msg in [(m.group(1) or m.group(3) or "print", m.group(2) or m.group(4))]
                            if msg and len(msg) >= 4][:200]
    if "spark-submit" in text:
        info["spark"] = spark_submits(text)
    info["hardcoded"] = scan_hardcoded(text, lang)
    info["tables"] = sorted({t for h in info["hardcoded"] if h["kind"] == "sql" for t in h.get("tables", [])})
    return info


def spark_submits(text):
    """spark-submit calls in a shell / Python script: class, app (jar / .py), name, master, deploy mode, first arguments."""
    starts = [m.start() for m in re.finditer(r"spark-submit", text)]
    joined = re.sub(r"\\\r?\n\s*", " ", text)  # shell line continuations
    out = []
    for n, m in enumerate(re.finditer(r"spark-submit\b([^\n;&|]*)", joined)):
        toks = [t.strip("\"',[]() \t") for t in re.findall(r"\"[^\"]*\"|'[^']*'|[^\s,]+", m.group(1))]
        toks = [t for t in toks if t]
        opts, app, args, i = {}, None, [], 0
        while i < len(toks):
            t = toks[i]
            if app is None and t.startswith("--"):
                if "=" in t:
                    k, v = t[2:].split("=", 1)
                    opts.setdefault(k, v)
                    i += 1
                elif t[2:] in ("verbose", "supervise") or i + 1 >= len(toks):
                    i += 1
                else:
                    opts.setdefault(t[2:], toks[i + 1])
                    i += 2
                continue
            if app is None:
                app = t
            else:
                args.append(t)
            i += 1
        out.append({"line": _lineno(text, starts[n]) if n < len(starts) else None, "class": opts.get("class"), "name": opts.get("name"),
                    "master": opts.get("master"), "deploy_mode": opts.get("deploy-mode"), "queue": opts.get("queue"), "app": app,
                    "args": [redact_secrets(a) for a in args[:8]]})
    return out


def spark_label(s):
    what = s.get("class") or s.get("app") or "?"
    return (f"{what}" + (f" in {s['app']}" if s.get("class") and s.get("app") else "")
            + (f" ({', '.join(x for x in [s.get('master') or '', s.get('deploy_mode') or ''] if x)})" if s.get("master") or s.get("deploy_mode") else ""))


def _pom_artifact(text):
    parent = re.search(r"<parent>(.*?)</parent>", text, re.S)
    body = re.sub(r"<parent>.*?</parent>", "", text, flags=re.S)
    deps_block = " ".join(re.findall(r"<dependencies>(.*?)</dependencies>", body, re.S))
    body = re.sub(r"<(dependencies|dependencyManagement|build|profiles|reporting)>.*?</\1>", "", body, flags=re.S)

    def tag(block, name):
        m = re.search(rf"<{name}>\s*([^<]+?)\s*</{name}>", block or "")
        return m.group(1) if m else None

    return {"artifactId": tag(body, "artifactId"), "groupId": tag(body, "groupId") or tag(parent.group(1) if parent else "", "groupId"),
            "version": tag(body, "version") or tag(parent.group(1) if parent else "", "version"),
            "packaging": tag(body, "packaging") or "jar", "name": tag(body, "name"),
            "modules": re.findall(r"<module>\s*([^<]+?)\s*</module>", body),
            "dependencies": re.findall(r"<artifactId>\s*([^<]+?)\s*</artifactId>", deps_block)}


def _header(text, pos):
    """Annotations / javadoc that belong to the declaration at pos: back to the previous statement or closing-brace line
    (string literals are masked so a ';' inside @CapabilityDescription("...") does not cut the header)."""
    window = text[max(0, pos - 8000): pos]
    masked = re.sub(r'"(?:[^"\\\n]|\\.)*"', lambda m: '"' + " " * (len(m.group(0)) - 2) + '"', window)
    cut = masked.rfind(";")
    for m in re.finditer(r"\n[ \t]*\}[ \t]*(?=\n)", masked):
        cut = max(cut, m.end() - 1)
    return window[cut + 1:]


def _members(text, consts):
    """Property descriptors, relationships and attribute reads / writes found anywhere in the file."""
    allowable = {f: _arg(v, consts) for f, v in ALLOWABLE_RE.findall(text)}
    props = []
    for pm in PD_RE.finditer(text):
        b = pm.group(2)
        svc = re.search(r"\.identifiesControllerService\(\s*([\w.]+)\.class", b)
        av = re.search(r"\.allowableValues\(([^;]*?)\)\s*(?:\.|$)", b, re.S)
        values = []
        if av and ".class" not in av.group(1):
            for a in re.split(r",(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", av.group(1)):
                a = a.strip()
                if a:
                    values.append(allowable.get(a) or allowable.get(a.split(".")[-1]) or _arg(a, consts))
        default = _call(b, "defaultValue", consts)
        dm = re.search(r"\.defaultValue\(\s*([\w.]+)\.getValue\(\)\s*\)", b)
        if dm:
            default = allowable.get(dm.group(1).split(".")[-1]) or default
        props.append({
            "field": pm.group(1), "name": _call(b, "name", consts), "displayName": _call(b, "displayName", consts),
            "description": _call(b, "description", consts) or "", "default": default,
            "required": bool(re.search(r"\.required\(\s*true", b)), "sensitive": bool(re.search(r"\.sensitive\(\s*true", b)),
            "el": bool(re.search(r"\.expressionLanguageSupported\(\s*(true|ExpressionLanguageScope\.(?!NONE))", b)),
            "service": svc.group(1) if svc else None, "allowable": [v for v in values if v],
            "line": _lineno(text, pm.start()),
        })
    rels = [{"field": rm.group(1), "name": _call(rm.group(2), "name", consts), "description": _call(rm.group(2), "description", consts) or "",
             "line": _lineno(text, rm.start())} for rm in REL_RE.finditer(text)]
    writes, dynamic = {}, False
    for m in PUT_ATTR_RE.finditer(text):
        v = _arg(m.group(1), consts)
        if v:
            writes.setdefault(v, _lineno(text, m.start()))
        else:
            dynamic = True
    for var in set(PUT_ALL_RE.findall(text)):
        for m in re.finditer(rf"\b{re.escape(var)}\s*\.\s*put\(\s*" + ARG + r"\s*,", text):
            v = _arg(m.group(1), consts)
            if v:
                writes.setdefault(v, _lineno(text, m.start()))
        if re.search(rf"\b{re.escape(var)}\s*\.\s*put\(\s*(?!\"|[A-Z][\w.]*\s*,|[\w.]+\.(?:key|getKey)\(\)\s*,)", text) or \
                re.search(rf"\b{re.escape(var)}\s*\.\s*putAll\(", text):
            dynamic = True
    if "putAllAttributes" in text and not PUT_ALL_RE.search(text):
        dynamic = True
    reads = {}
    for m in GET_ATTR_RE.finditer(text):
        v = _arg(m.group(1), consts)
        if v:
            reads.setdefault(v, _lineno(text, m.start()))
    removes = sorted({v for v in (_arg(m.group(1), consts) for m in REMOVE_ATTR_RE.finditer(text)) if v})
    return {"properties": props, "relationships": rels, "writes": writes, "reads": reads, "removes": removes, "dynamic_writes": dynamic}


def _jvm_file(text, package):
    """Classes (with annotations and super types), constants, members, I/O, log / exception messages of one JVM file."""
    consts = {}
    for name, v in CONST_RE.findall(text) + IFACE_CONST_RE.findall(text):
        consts.setdefault(name, REDACTED if SECRET_NAME.search(name) and v.startswith('"')
                          else _arg(v, {}) if not v.startswith('"') else _concat(v))
    for name, v in ENUM_CONST_RE.findall(text):
        consts.setdefault(name, v)
    classes = []
    for m in DECL_RE.finditer(text):
        mods, decl, name = m.group(1) or "", m.group(2), m.group(3)
        header = _header(text, m.start()) + text[m.start():m.start(1)]  # + same-line annotations
        cap = re.search(ANNOT_STR_RE.format("CapabilityDescription"), header, re.S)
        tags = TAGS_RE.search(header)
        req = INPUT_REQ_RE.search(header)
        dyn = []
        for d in DYNPROP_RE.findall(header):
            nm = re.search(r'name\s*=\s*"([^"]+)"', d)
            ds = re.search(r'description\s*=\s*((?:"(?:[^"\\]|\\.)*"\s*\+?\s*)+)', d)
            dyn.append({"name": nm.group(1) if nm else None, "description": _concat(ds.group(1)) if ds else ""})
        classes.append({
            "class": name, "fqcn": f"{package}.{name}" if package else name, "decl": decl, "line": _lineno(text, m.start(3)),
            "top_level": not text[m.start():m.start() + 1].isspace(),
            "extends": (m.group(4) or "").strip(), "implements": (m.group(5) or "").strip(), "abstract": "abstract" in mods or decl == "interface",
            "description": _concat(cap.group(1)) if cap else "",
            "tags": [_concat(t) for t in re.findall(r'"[^"]*"', tags.group(1))] if tags else [],
            "input_requirement": req.group(1) if req else None,
            "writes_attributes_doc": [{"name": a, "description": _concat(d) if d else ""} for a, d in WRITES_RE.findall(header)],
            "reads_attributes_doc": [{"name": a, "description": _concat(d) if d else ""} for a, d in READS_RE.findall(header)],
            "dynamic_properties": [d for d in dyn if d["name"] or d["description"]],
            "flags": [f for f in FLAG_ANNOTS if re.search(rf"@{f}\b", header)],
            "annotated": "@CapabilityDescription" in header or "@Tags" in header,
        })
    members = _members(text, consts) if classes else {}
    messages = []
    for m in MESSAGE_RE.finditer(text):
        messages.append({"level": m.group(1), "text": _template(m.group(2)), "line": _lineno(text, m.start())})
    for m in THROW_RE.finditer(text):
        messages.append({"level": m.group(1), "text": _template(m.group(2)), "line": _lineno(text, m.start())})
    messages = [msg for msg in messages if len(msg["text"].replace("{}", "").strip()) >= 4][:200]
    io = sorted(k for k, rx in IO_PATTERNS.items() if re.search(rx, text))
    return {"classes": classes, "consts": consts, "members": members, "messages": messages, "io": io, "components": []}


def scan_hardcoded(text, lang):
    """Find hardcoded URLs, JDBC strings, hosts, IPs, paths, secrets and SQL, with line numbers (secrets redacted)."""
    found, seen = [], set()

    def add(kind, value, line_no, line, **extra):
        key = (kind, value, line_no)
        if key not in seen:
            seen.add(key)
            found.append({"kind": kind, "value": clip(value, 200), "line": line_no, "code": clip(redact_secrets(line.strip()), 160), **extra})

    lines = text.splitlines()
    comment = {"python": "#", "shell": "#", "config": "#", "powershell": "#", "ruby": "#", "sql": "--"}.get(lang, "//")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith(comment) or stripped.startswith(("*", "/*", "import ", "package ")):
            continue
        for m in SECRET_ASSIGN_RE.finditer(line):
            value = m.group(2)
            if not re.fullmatch(r"[\w.\-]*\$\{.*\}|#\{.*\}|%\(.*|\{\w*\}|<.*>|\*+|changeme|password|secret|null|none|true|false", value, re.I):
                add("secret", f"{m.group(1)}={REDACTED}", i, line)
        for m in JDBC_RE.finditer(line):
            add("jdbc", m.group(0), i, line)
        for m in URL_RE.finditer(line):
            if "xmlns" not in line and "apache.org/licenses" not in line and "www.w3.org" not in m.group(0):
                add("s3" if m.group(0).lower().startswith("s3") else "url", m.group(0), i, line)
        for m in re.finditer(r"(?i)bucket\w*\s*(?:=|:|,|\()\s*[\"']([a-z0-9][a-z0-9.\-]{2,62})[\"']", line):
            add("s3", m.group(1), i, line)
        for m in IP_RE.finditer(line):
            if not re.search(r"(?i)version|0\.0\.0\.0|127\.0\.0\.1", line):
                add("ip", m.group(0), i, line)
        in_strings = " ".join(m.group(1) for m in re.finditer(r"[\"']([^\"']*)[\"']", line)) if lang != "config" else line
        for m in HOST_RE.finditer(in_strings):
            if not re.search(r"(?i)\.(java|py|class|jar|xml|json|csv|txt)$", m.group(0)) and not URL_RE.search(in_strings):
                add("host", m.group(0), i, line)
        for rx in (WIN_PATH_RE, UNIX_PATH_RE):
            for m in rx.finditer(in_strings):
                add("path", m.group(0).strip(), i, line)
    for stmt, line_no in _sql_literals(text, lang):
        tables = sqlparse.tables(stmt)
        if tables:
            add("sql", stmt, line_no, lines[line_no - 1] if line_no <= len(lines) else "", tables=tables)
    return found


def _sql_literals(text, lang):
    if lang == "sql":
        for m in re.finditer(r"[^;]+", text):
            if sqlparse.looks_like_sql(m.group(0)):
                yield m.group(0).strip(), _lineno(text, m.start() + len(m.group(0)) - len(m.group(0).lstrip()))
        return
    # string literals, including Java "a" + "b" concatenations and Python triple quotes
    for m in re.finditer(r'"""(.*?)"""|\'\'\'(.*?)\'\'\'|((?:"(?:[^"\\\n]|\\.)*"\s*\+?\s*)+)|\'((?:[^\'\\\n]|\\.)*)\'', text, re.S):
        body = m.group(1) or m.group(2) or (_concat(m.group(3)) if m.group(3) else m.group(4)) or ""
        if sqlparse.looks_like_sql(body):
            yield body.strip(), _lineno(text, m.start())


SERVICE_KINDS = {"org.apache.nifi.processor.Processor": "PROCESSOR", "org.apache.nifi.controller.ControllerService": "CONTROLLER_SERVICE",
                 "org.apache.nifi.reporting.ReportingTask": "REPORTING_TASK"}


class CodeIndex:
    """All indexed files, with lookups by fully-qualified class name and by file name.

    `finalize()` (after all files are added) resolves constants across files, walks class hierarchies so properties,
    relationships and attributes declared in abstract base classes reach the concrete components, applies the
    META-INF/services registrations and maps every component to its Maven module and the NAR module that packages it."""

    def __init__(self, files=None):
        self.files = {}
        self.by_fqcn = {}
        self.by_basename = {}
        self.classes = {}      # fqcn -> (class info, path)
        self.modules = {}      # module dir -> pom info
        self.registered = {}   # fqcn -> {"kind", "path"}
        for info in files or []:
            self.add(info)
        if files:
            self.finalize()

    def add(self, info):
        path = info["path"]
        self.files[path] = info
        self.by_basename.setdefault(Path(path).name.lower(), []).append(path)
        for c in info.get("classes") or []:
            self.classes.setdefault(c["fqcn"], (c, path))
        if info.get("lang") == "pom" and info.get("artifact"):
            self.modules[str(Path(path).parent)] = info["artifact"]
        if info.get("lang") == "services":
            kind = SERVICE_KINDS.get(Path(path).name)
            for fqcn in info.get("service_classes") or []:
                self.registered[fqcn] = {"kind": kind, "path": path}

    # ------------------------------------------------------------------------------------------ resolution
    def finalize(self):
        self._consts()
        simple = {}
        for fqcn, (c, _) in self.classes.items():
            simple.setdefault(c["class"], []).append(fqcn)
        self.by_fqcn = {}
        for fqcn, (c, path) in sorted(self.classes.items()):
            if c["decl"] != "class" or (self.files.get(path) or {}).get("is_test"):
                continue
            chain = self._ancestors(fqcn, simple)
            supers = " ".join(x["extends"] + " " + x["implements"] for x, _ in [(c, path)] + chain)
            reg = self.registered.get(fqcn)
            if not (reg or c["annotated"] or any(b in supers for b in NIFI_BASES)):
                continue
            kind = (reg or {}).get("kind") or ("PROCESSOR" if "Processor" in supers else "CONTROLLER_SERVICE" if "Service" in supers
                                               else "REPORTING_TASK" if "ReportingTask" in supers else "COMPONENT")
            comp = self._component(c, path, chain, kind, reg)
            self.by_fqcn[fqcn] = [{"path": path, "line": c["line"], "component": comp}]

    def _consts(self):
        table, by_simple = {}, {}
        for path, info in self.files.items():
            top = next((c for c in info.get("classes") or [] if c["top_level"]), None)
            for name, v in (info.get("consts") or {}).items():
                if top:
                    table[f"{top['class']}.{name}"] = v
                    table[f"{top['fqcn']}.{name}"] = v
                by_simple.setdefault(name, set()).add(v)
        self._const_table, self._const_simple = table, {k: next(iter(v)) for k, v in by_simple.items() if len(v) == 1}

    def resolve(self, value):
        for _ in range(6):
            if not isinstance(value, str) or not value.startswith("@ref:"):
                return value
            ref = value[5:]
            parts = ref.split(".")
            value = (self._const_table.get(ref) or self._const_table.get(".".join(parts[-2:]))
                     or self._const_simple.get(parts[-1]))
        return None if isinstance(value, str) and value.startswith("@ref:") else value

    def _ancestors(self, fqcn, simple):
        out, seen = [], {fqcn}
        c, _ = self.classes[fqcn]
        while c and c["extends"]:
            base = re.sub(r"<.*", "", c["extends"].split(",")[0]).strip()
            cands = [base] if base in self.classes else simple.get(base.split(".")[-1], [])
            pkg = c["fqcn"].rsplit(".", 1)[0]
            nxt = next((x for x in cands if x.startswith(pkg + ".")), cands[0] if len(cands) == 1 else None)
            if not nxt or nxt in seen:
                break
            seen.add(nxt)
            c, p = self.classes[nxt]
            out.append((c, p))
        return out

    def _primary_members(self, c, path):
        """Member facts of a file belong to its first top-level class."""
        info = self.files.get(path) or {}
        top = next((x for x in info.get("classes") or [] if x["top_level"]), None)
        return (info.get("members") or {}) if top and top["fqcn"] == c["fqcn"] else {}

    def _component(self, c, path, chain, kind, reg):
        props, rels, writes, reads, removes, io = {}, {}, {}, {}, set(), set()
        wdoc, rdoc, dyn, flags, dynamic = {}, {}, [], set(), False
        for depth, (cls, p) in enumerate([(c, path)] + chain):
            m = self._primary_members(cls, p)
            origin = None if depth == 0 else cls["class"]
            for pr in m.get("properties", []):
                pr = dict(pr, name=self.resolve(pr["name"]), displayName=self.resolve(pr["displayName"]),
                          description=self.resolve(pr["description"]) or "", default=self.resolve(pr["default"]),
                          allowable=[v for v in (self.resolve(a) for a in pr.get("allowable") or []) if v],
                          path=p, **({"from": origin} if origin else {}))
                props.setdefault(pr["name"] or pr["field"], pr)
            for r in m.get("relationships", []):
                r = dict(r, name=self.resolve(r["name"]), description=self.resolve(r["description"]) or "", path=p,
                         **({"from": origin} if origin else {}))
                rels.setdefault(r["name"] or r["field"], r)
            for a, line in (m.get("writes") or {}).items():
                a = self.resolve(a)
                if a:
                    writes.setdefault(a, f"{Path(p).name}:{line}")
            for a, line in (m.get("reads") or {}).items():
                a = self.resolve(a)
                if a:
                    reads.setdefault(a, f"{Path(p).name}:{line}")
            removes |= {x for x in (self.resolve(a) for a in m.get("removes") or []) if x}
            dynamic = dynamic or bool(m.get("dynamic_writes"))
            io |= set((self.files.get(p) or {}).get("io") or [])
            for w in cls["writes_attributes_doc"]:
                wdoc.setdefault(w["name"], w["description"])
            for r in cls["reads_attributes_doc"]:
                rdoc.setdefault(r["name"], r["description"])
            dyn += cls["dynamic_properties"]
            flags |= set(cls["flags"])
        described = next((x for x, _ in [(c, path)] + chain if x["description"]), c)
        module = self.module_of(path)
        return {
            "class": c["class"], "fqcn": c["fqcn"], "kind": kind, "line": c["line"], "extends": c["extends"], "implements": c["implements"],
            "abstract": c["abstract"], "ancestors": [x["fqcn"] for x, _ in chain], "description": described["description"],
            "super_chain": [re.sub(r"<.*", "", x["extends"]).strip() for x, _ in [(c, path)] + chain if x["extends"]],
            "tags": c["tags"] or next((x["tags"] for x, _ in chain if x["tags"]), []),
            "input_requirement": c["input_requirement"] or next((x["input_requirement"] for x, _ in chain if x["input_requirement"]), None),
            "registered": bool(reg), "registered_in": (reg or {}).get("path"),
            "properties": [v for v in props.values() if v.get("name")], "relationships": [v for v in rels.values() if v.get("name")],
            "writes_attributes": sorted(set(writes) | set(wdoc)), "writes_at": writes, "writes_attributes_doc": sorted(wdoc),
            "writes_doc": wdoc, "reads_attributes": sorted(set(reads) | set(rdoc)), "reads_at": reads, "reads_attributes_doc": sorted(rdoc),
            "removes_attributes": sorted(removes), "dynamic_writes": dynamic, "dynamic_properties": dyn, "flags": sorted(flags),
            "io": sorted(io), "module": module, "nar_modules": self.nar_modules_of(module),
        }

    # -------------------------------------------------------------------------------------------- maven
    def module_of(self, path):
        p = Path(path).parent
        while True:
            info = self.modules.get(str(p))
            if info:
                return dict(info, dir=str(p))
            if p.parent == p:
                return None
            p = p.parent

    def nar_modules_of(self, module):
        if not module or not module.get("artifactId"):
            return []
        return [dict(m, dir=d) for d, m in self.modules.items() if m.get("packaging") == "nar"
                and (module["artifactId"] in (m.get("dependencies") or []) or d == module.get("dir"))]

    def implementers(self, api):
        """Concrete classes in the repos implementing a (custom) controller-service interface."""
        simple = api.rsplit(".", 1)[-1]
        return sorted(fqcn for fqcn, (c, path) in self.classes.items()
                      if c["decl"] == "class" and not c["abstract"] and not (self.files.get(path) or {}).get("is_test")
                      and simple in re.split(r"[\s,<>]+", c["implements"] + " " + c["extends"]))

    def components(self):
        return [(fqcn, entries) for fqcn, entries in sorted(self.by_fqcn.items())]

    def hardcoded(self):
        for path, info in sorted(self.files.items()):
            for h in info.get("hardcoded") or []:
                yield path, h
