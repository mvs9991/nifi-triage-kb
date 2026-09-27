"""Catalog of processor / controller-service types from the NAR files NiFi loads.

Each NAR carries META-INF/docs/extension-manifest.xml with descriptions, property display names,
defaults, sensitivity and relationships. Older or hand-built NARs may lack it; for those we fall back to
the META-INF/services entries inside the bundled jars so we at least know which classes the NAR provides.
"""
import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PARSER_VERSION = "2"  # bump when read_nar output changes, so cached NAR results are re-read
# Bundled third-party jars never hold our components; skipping them keeps custom-NAR scanning fast.
THIRD_PARTY_JAR = re.compile(r"(?i)^(?:.*/)?(commons-|jackson-|slf4j|log4j|logback|guava|httpclient|httpcore|netty|aws-|jaxb|javax|jakarta|"
                             r"snakeyaml|gson|json-|joda|bc(prov|pkix)|avro|kotlin|scala-|spring-|hadoop-|protobuf|okhttp|okio|"
                             r"jsch|sshj|mysql|mariadb|postgresql|ojdbc|mssql)")
MAX_JAR_BYTES = 30_000_000
MAX_STRINGS = 20000

SERVICE_FILES = {
    "META-INF/services/org.apache.nifi.processor.Processor": "PROCESSOR",
    "META-INF/services/org.apache.nifi.controller.ControllerService": "CONTROLLER_SERVICE",
    "META-INF/services/org.apache.nifi.reporting.ReportingTask": "REPORTING_TASK",
}


def _t(el, tag, default=None):
    child = el.find(tag) if el is not None else None
    return child.text if child is not None and child.text is not None else default


def read_nar(path):
    """Return {nar: {...}, extensions: [...]} for one NAR file."""
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        manifest = {}
        if "META-INF/MANIFEST.MF" in names:
            for line in z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace").splitlines():
                if ": " in line:
                    k, v = line.split(": ", 1)
                    manifest[k.strip()] = v.strip()
        nar = {
            "file": str(path), "group": manifest.get("Nar-Group"), "artifact": manifest.get("Nar-Id") or Path(path).stem,
            "version": manifest.get("Nar-Version"), "parent": manifest.get("Nar-Dependency-Id"),
            "build": manifest.get("Build-Timestamp"),
        }
        if "META-INF/docs/extension-manifest.xml" in names:
            extensions = _parse_extension_manifest(z.read("META-INF/docs/extension-manifest.xml"))
        else:
            extensions = _scan_service_files(z, names)
        if nar["group"] and not nar["group"].startswith("org.apache.nifi"):
            nar["jar_strings"] = _component_jar_strings(z, names, {e["type"] for e in extensions}, extensions)
    for ext in extensions:
        ext["nar"] = nar["artifact"]
        ext["nar_group"] = nar["group"]
        if ext.get("deployed"):
            ext["deployed"]["nar"] = nar["artifact"]
    return {"nar": nar, "extensions": extensions}


def _component_jar_strings(z, names, types, extensions):
    """String literals of every class in the bundled jar(s) that hold the NAR's own components. Marks each extension
    with the jar it lives in (ext['deployed'])."""
    out = {}
    wanted = {t.replace(".", "/") + ".class": t for t in types if t}
    for jar_name in sorted(n for n in names if n.endswith(".jar") and not THIRD_PARTY_JAR.search(Path(n).name)):
        try:
            if z.getinfo(jar_name).file_size > MAX_JAR_BYTES:
                continue
            with zipfile.ZipFile(io.BytesIO(z.read(jar_name))) as jar:
                jar_names = jar.namelist()
                hits = [wanted[n] for n in jar_names if n in wanted]
                if not hits:
                    continue
                strings = set()
                for n in jar_names:
                    if n.endswith(".class") and len(strings) < MAX_STRINGS:
                        strings.update(s for s in class_strings(jar.read(n)) if 0 < len(s) <= 400)
                out[jar_name] = sorted(strings)[:MAX_STRINGS]
                for ext in extensions:
                    if ext["type"] in hits:
                        ext["deployed"] = {"jar": jar_name}
        except (zipfile.BadZipFile, KeyError, OSError):
            continue
    return out


def class_strings(data):
    """String literals (CONSTANT_String entries) of one .class file, from its constant pool.
    Invokedynamic string-concat recipes keep their \\u0001 placeholders, shown as {}."""
    if data[:4] != b"\xca\xfe\xba\xbe" or len(data) < 10:
        return []
    count = int.from_bytes(data[8:10], "big")
    utf8, refs, i, idx = {}, [], 10, 1
    try:
        while idx < count:
            tag = data[i]
            if tag == 1:
                n = int.from_bytes(data[i + 1:i + 3], "big")
                utf8[idx] = data[i + 3:i + 3 + n]
                i += 3 + n
            elif tag in (3, 4):
                i += 5
            elif tag in (5, 6):
                i += 9
                idx += 1  # long / double take two slots
            elif tag == 8:
                refs.append(int.from_bytes(data[i + 1:i + 3], "big"))
                i += 3
            elif tag in (7, 16, 19, 20):
                i += 3
            elif tag in (9, 10, 11, 12, 17, 18):
                i += 5
            elif tag == 15:
                i += 4
            else:
                break
            idx += 1
    except IndexError:
        pass
    out = []
    for r in refs:
        raw = utf8.get(r)
        if raw is not None:
            out.append(raw.decode("utf-8", "replace").replace("\x01", "{}"))
    return out


def _parse_extension_manifest(data):
    root = ET.fromstring(data)
    out = []
    for ext in root.iter("extension"):
        props = {}
        for p in ext.findall("./properties/property"):
            csd = p.find("controllerServiceDefinition")
            props[_t(p, "name")] = {
                "displayName": _t(p, "displayName") or _t(p, "name"),
                "description": _t(p, "description", ""),
                "default": _t(p, "defaultValue"),
                "required": _t(p, "required") == "true",
                "sensitive": _t(p, "sensitive") == "true",
                "el_scope": _t(p, "expressionLanguageScope"),
                "service_api": _t(csd, "className") if csd is not None else None,
                "allowable": {_t(a, "value"): _t(a, "displayName") for a in p.findall("./allowableValues/allowableValue")},
            }
        out.append({
            "type": _t(ext, "name"),
            "kind": _t(ext, "type"),
            "description": _t(ext, "description", ""),
            "tags": [t.text for t in ext.findall("./tags/tag") if t.text],
            "properties": props,
            "relationships": [
                {"name": _t(r, "name"), "description": _t(r, "description", ""), "auto_terminated": _t(r, "autoTerminated") == "true"}
                for r in ext.findall("./relationships/relationship")
            ],
            "dynamic_relationships": ext.find("dynamicRelationship") is not None,
            "dynamic_properties": ext.find("./dynamicProperties/dynamicProperty") is not None,
            "reads_attributes": [_t(a, "name") for a in ext.findall("./readsAttributes/readsAttribute")],
            "writes_attributes": [_t(a, "name") for a in ext.findall("./writesAttributes/writesAttribute")],
            "input_requirement": _t(ext, "inputRequirement"),
            "has_manifest": True,
        })
    return out


def _scan_service_files(z, names):
    out = []
    for jar_name in (n for n in names if n.endswith(".jar")):
        try:
            with zipfile.ZipFile(io.BytesIO(z.read(jar_name))) as jar:
                jar_names = set(jar.namelist())
                for svc, kind in SERVICE_FILES.items():
                    if svc in jar_names:
                        for line in jar.read(svc).decode("utf-8", "replace").splitlines():
                            line = line.split("#", 1)[0].strip()
                            if line:
                                out.append({"type": line, "kind": kind, "description": "", "tags": [], "properties": {},
                                            "relationships": [], "dynamic_relationships": False, "dynamic_properties": False,
                                            "reads_attributes": [], "writes_attributes": [], "input_requirement": None,
                                            "has_manifest": False, "jar": jar_name})
        except zipfile.BadZipFile:
            continue
    return out


class Catalog:
    """type name -> extension info, built from all NARs (cached by file size+mtime in the store)."""

    def __init__(self):
        self.types = {}
        self.nars = []
        self._jar_strings = {}   # (nar artifact, jar) -> set of string literals

    def add(self, nar_info):
        nar = nar_info["nar"]
        self.nars.append({k: v for k, v in nar.items() if k != "jar_strings"})
        for jar, strings in (nar.get("jar_strings") or {}).items():
            self._jar_strings[(nar["artifact"], jar)] = set(strings)
        for ext in nar_info["extensions"]:
            self.types.setdefault(ext["type"], ext)

    def get(self, type_name):
        return self.types.get(type_name)

    def jar_strings(self, deployed_or_type):
        """String literals of the deployed classes for an extension (its ext['deployed']) or a type name."""
        ext = self.types.get(deployed_or_type) if isinstance(deployed_or_type, str) else None
        deployed = (ext or {}).get("deployed") if ext else deployed_or_type
        if not deployed:
            return set()
        nar = (ext or {}).get("nar") or deployed.get("nar")
        if nar:
            return self._jar_strings.get((nar, deployed["jar"]), set())
        return next((s for (_, j), s in self._jar_strings.items() if j == deployed["jar"]), set())

    def custom_nars(self):
        return [n for n in self.nars if n.get("group") and not n["group"].startswith("org.apache.nifi")]


def find_nars(dirs):
    seen = []
    for d in dirs:
        d = Path(d)
        if d.is_dir():
            seen.extend(sorted(d.rglob("*.nar")))
    return seen
