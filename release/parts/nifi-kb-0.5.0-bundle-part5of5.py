# nifi-kb 0.5.0 - paste bundle, part 5 of 5 - 22 files. Save as nifi-kb-0.5.0-bundle-part5of5.py, then run:  python nifi-kb-0.5.0-bundle-part5of5.py
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
#@@ FILE tests/test_nifikb.py tc b901703d0966d7b0
#|"""Regression suite for nifikb. Run: python -m unittest discover -s tests -v"""
#|import contextlib
#|import gzip
#|import io
#|import json
#|import os
#|import shutil
#|import sqlite3
#|import sys
#|import tempfile
#|import unittest
#|from pathlib import Path
#|
#|sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
#|sys.path.insert(0, str(Path(__file__).resolve().parent))
#|
#|from fixtures_builder import FIXTURES, NESTED_XML, SECRET_VALUES, make_env, nested_flow  # noqa: E402
#|from nifikb import cli, code as codemod, db as dbmod, sqlparse  # noqa: E402
#|from nifikb.analyze import Analysis  # noqa: E402
#|from nifikb.build import build  # noqa: E402
#|from nifikb.catalog import Catalog, read_nar  # noqa: E402
#|from nifikb.code import CodeIndex  # noqa: E402
#|from nifikb.config import load_config  # noqa: E402
#|from nifikb.flow import load_flow  # noqa: E402
#|
#|REAL_NIFI = Path(os.environ.get("NIFIKB_TEST_NIFI_HOME", "D:/Sanjay/nifi-1.27.0"))
#|
#|
#|def run_cli(*argv):
#|    buf = io.StringIO()
#|    with contextlib.redirect_stdout(buf):
#|        rc = cli.main(list(argv))
#|    return rc, buf.getvalue()
#|
#|
#|def all_text(kb):
#|    out = {}
#|    for p in Path(kb).rglob("*.md"):
#|        out[str(p)] = p.read_text(encoding="utf-8")
#|    return out
#|
#|
#|class TestSql(unittest.TestCase):
#|    def test_tables(self):
#|        self.assertEqual(sqlparse.tables("SELECT a FROM x.orders o JOIN customers c ON c.id=o.c LEFT JOIN `vendors` v ON 1=1"),
#|                         ["x.orders", "customers", "vendors"])
#|        self.assertEqual(sqlparse.tables("insert into file_audit (a) values (1)"), ["file_audit"])
#|        self.assertEqual(sqlparse.tables("UPDATE t1 SET a = (SELECT max(b) FROM t2)"), ["t1", "t2"])
#|        self.assertEqual(sqlparse.tables("WITH recent AS (SELECT * FROM calls) SELECT * FROM recent"), ["calls"])
#|        self.assertEqual(sqlparse.tables("DELETE FROM stage_${table.name} WHERE 1=1"), ["stage_${table.name}"])
#|        self.assertEqual(sqlparse.tables("SELECT 'from nowhere' AS x FROM real_table"), ["real_table"])
#|
#|    def test_looks_like_sql(self):
#|        self.assertTrue(sqlparse.looks_like_sql("select id from orders"))
#|        self.assertFalse(sqlparse.looks_like_sql("Select the file to fetch"))
#|        self.assertFalse(sqlparse.looks_like_sql("update"))
#|
#|
#|class TestFlowLoading(unittest.TestCase):
#|    def test_json_xml_parity_on_real_export(self):
#|        j = load_flow(FIXTURES / "local" / "flow.json.gz")
#|        x = load_flow(FIXTURES / "local" / "flow.xml.gz")
#|        self.assertEqual((j.format, x.format), ("flow.json", "flow.xml"))
#|
#|        def sig(flow):
#|            comps = {c["id"]: c for c in flow.components.values()}
#|            nodes = sorted((c["kind"], c["name"], c["type"], json.dumps(c["properties"], sort_keys=True), tuple(c["auto_terminated"]))
#|                           for c in comps.values())
#|            edges = sorted((comps[c["source_id"]]["name"], tuple(c["relationships"]), comps[c["dest_id"]]["name"]) for c in flow.connections)
#|            svcs = sorted((s["name"], s["type"], s["state"]) for s in flow.services.values())
#|            return nodes, edges, svcs, sorted(flow.labels, key=lambda lab: lab["text"]) and len(flow.labels)
#|
#|        self.assertEqual(sig(j), sig(x))
#|        self.assertEqual(len(j.components), 12)  # 9 processors + 3 funnels
#|        self.assertEqual(j.groups[j.root_id]["variables"]["nifi.path"], r"D:\Sanjay\nifi-1.27.0")
#|
#|    def test_nested_xml(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            p = Path(tmp) / "flow.xml.gz"
#|            p.write_bytes(gzip.compress(NESTED_XML.encode()))
#|            flow = load_flow(p)
#|            self.assertEqual(flow.groups["g1"]["path"], "NiFi Flow / File Ingestion")
#|            self.assertEqual(flow.groups["g1"]["parameter_context"], "file-params")
#|            self.assertEqual(flow.groups["g1"]["variables"], {"region": "eu"})
#|            self.assertEqual(flow.components["x-fetch"]["state"], "STOPPED")
#|            self.assertEqual(flow.components["x-fetch"]["concurrent_tasks"], 2)
#|            self.assertNotIn("File Filter", flow.components["x-list"]["properties"])
#|            an = Analysis(flow, Catalog(), CodeIndex()).run()
#|            fetch_props = {f["name"]: f for f in an.props["x-fetch"]}
#|            self.assertEqual(fetch_props["File to Fetch"]["resolved"], "/data/in/${filename}")
#|            self.assertIn("filename", an.attrs_read["x-fetch"])
#|            self.assertEqual([c["id"] for c in an.entry_points("g1")], ["g1-in"])
#|            self.assertEqual([c["id"] for c in an.entry_points()], ["x-list"])
#|
#|    def test_flow_definition_export(self):
#|        doc = nested_flow()
#|        export = {"flowContents": doc["rootGroup"], "parameterContexts": {c["name"]: c for c in doc["parameterContexts"]}}
#|        with tempfile.TemporaryDirectory() as tmp:
#|            p = Path(tmp) / "export.json"
#|            p.write_text(json.dumps(export))
#|            flow = load_flow(p)
#|            self.assertEqual(flow.format, "flow-definition")
#|            self.assertIn("vendor-params", flow.param_contexts)
#|            self.assertEqual(len([c for c in flow.components.values() if c["kind"] == "PROCESSOR"]), 10)
#|
#|
#|class TestCatalogAndCode(unittest.TestCase):
#|    def test_fake_nars(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            make_env(tmp, with_db=False)
#|            acme = read_nar(Path(tmp) / "nars" / "acme-nifi-nar-1.0.0.nar")
#|            ext = acme["extensions"][0]
#|            self.assertEqual(ext["type"], "com.acme.nifi.ValidateOrderJson")
#|            self.assertEqual([r["name"] for r in ext["relationships"]], ["valid", "invalid", "failure"])
#|            self.assertEqual(ext["properties"]["Validation URL"]["default"], "https://validator.acme.com/api/v1/check")
#|            legacy = read_nar(Path(tmp) / "nars" / "legacy-nar.nar")
#|            self.assertEqual([e["type"] for e in legacy["extensions"]], ["com.legacy.OldProcessor"])
#|            self.assertFalse(legacy["extensions"][0]["has_manifest"])
#|
#|    @unittest.skipUnless((REAL_NIFI / "lib" / "nifi-standard-nar-1.27.0.nar").exists(), "real NiFi not installed")
#|    def test_real_standard_nar(self):
#|        info = read_nar(REAL_NIFI / "lib" / "nifi-standard-nar-1.27.0.nar")
#|        types = {e["type"]: e for e in info["extensions"]}
#|        pdr = types["org.apache.nifi.processors.standard.PutDatabaseRecord"]
#|        self.assertEqual(pdr["properties"]["put-db-record-table-name"]["displayName"], "Table Name")
#|        self.assertEqual({r["name"] for r in pdr["relationships"]}, {"success", "failure", "retry"})
#|        self.assertTrue(types["org.apache.nifi.processors.standard.RouteOnAttribute"]["dynamic_relationships"])
#|
#|    def test_java_processor(self):
#|        info = codemod.index_file(FIXTURES / "repo/nifi-acme-processors/src/main/java/com/acme/nifi/ValidateOrderJson.java")
#|        comp = codemod.CodeIndex([info]).by_fqcn["com.acme.nifi.ValidateOrderJson"][0]["component"]
#|        self.assertEqual(comp["fqcn"], "com.acme.nifi.ValidateOrderJson")
#|        self.assertEqual(comp["tags"], ["acme", "json", "validation"])
#|        self.assertEqual(comp["input_requirement"], "INPUT_REQUIRED")
#|        self.assertIn("ACME validator service and routes", comp["description"])
#|        props = {p["name"]: p for p in comp["properties"]}
#|        self.assertEqual(props["Validation URL"]["default"], "https://validator.acme.com/api/v1/check")
#|        self.assertTrue(props["Api Token"]["sensitive"])
#|        self.assertEqual([r["name"] for r in comp["relationships"]], ["valid", "invalid", "failure"])
#|        self.assertEqual(comp["reads_attributes"], ["order.id", "vendor"])
#|        self.assertEqual(comp["writes_attributes"], ["validated.by", "validation.status"])
#|        kinds = {(h["kind"], h["value"]) for h in info["hardcoded"]}
#|        self.assertIn(("url", "https://validator-backup.acme.com/api/v1/check"), kinds)
#|        self.assertIn(("s3", "acme-orders-raw"), kinds)
#|        self.assertIn(("path", "/data/archive/orders"), kinds)
#|        self.assertEqual(info["tables"], ["order_status", "validation_log", "vendors"])
#|        secret = [h for h in info["hardcoded"] if h["kind"] == "secret"]
#|        self.assertEqual(len(secret), 1)
#|        self.assertNotIn("Sup3rS3cret!", json.dumps(info))
#|
#|    def test_python_script(self):
#|        info = codemod.index_file(FIXTURES / "repo/scripts/enrich.py")
#|        self.assertEqual(info["functions"], ["enrich", "main"])
#|        self.assertEqual(info["imports"], ["pymysql", "sys"])
#|        self.assertEqual(info["tables"], ["customers"])
#|        self.assertIn(("ip", "10.20.30.40"), {(h["kind"], h["value"]) for h in info["hardcoded"]})
#|        self.assertNotIn("hunter2", json.dumps(info))
#|
#|
#|class TestEndToEnd(unittest.TestCase):
#|    """Full build over the nested fixture: flow + custom NAR + repo + SQLite metadata DB."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp)
#|        cls.cfg = load_config(cls.cfg_path)
#|        cls.res = build(cls.cfg, log=lambda m: None)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|        cls.text = all_text(cls.kb)
#|        cls.db = sqlite3.connect(cls.kb / "kb.sqlite")
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.db.close()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def findings(self, kind):
#|        return self.db.execute("SELECT component_id, message FROM findings WHERE kind=?", (kind,)).fetchall()
#|
#|    def test_files_generated(self):
#|        for f in ["INDEX.md", "flows/root.md", "flows/vendor-json-ingestion.md", "services.md", "external-systems.md", "hardcoded.md",
#|                  "issues.md", "custom-code/ValidateOrderJson.md", "custom-code/INDEX.md", "scripts/enrich-py.md", "db/metadata.md", "CHANGELOG.md"]:
#|            self.assertTrue((self.kb / f).exists(), f)
#|
#|    def test_no_secret_leaks(self):
#|        blob = "\n".join(self.text.values()) + (self.kb / "kb.sqlite").read_bytes().decode("latin-1")
#|        for s in SECRET_VALUES + ["enc{0123456789abcdef}", "enc{ffff}"]:
#|            self.assertNotIn(s, blob, f"secret {s!r} leaked into the knowledge base")
#|
#|    def test_cross_group_tree(self):
#|        vendor = (self.kb / "flows/vendor-json-ingestion.md").read_text(encoding="utf-8")
#|        self.assertIn("⇥ input port **orders in**", vendor)
#|        self.assertIn("*matched* → **Validate order** [ValidateOrderJson]", vendor)
#|        self.assertIn("*valid* → **Store raw JSON** [PutS3Object]", vendor)
#|        self.assertIn("bucket=acme-orders-raw", vendor)
#|        root = (self.kb / "flows/root.md").read_text(encoding="utf-8")
#|        self.assertIn("in PG **Vendor JSON Ingestion**", root)
#|        rc, out = run_cli("--config", str(self.cfg_path), "trace", "Receive orders API")
#|        self.assertEqual(rc, 0)
#|        for name in ("Extract fields", "Validate order", "Store raw JSON", "Write audit row", "Lookup customer", "Archive order"):
#|            self.assertIn(name, out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "trace", "Archive order", "--up")
#|        self.assertIn("◀ **Archive order**", out)
#|        self.assertIn("Nightly trigger", out)
#|        self.assertIn("Receive orders API", out)
#|
#|    def test_parameters_variables_resolved(self):
#|        props = dict(self.db.execute("SELECT name, resolved FROM properties WHERE component_id='p-rejects'").fetchall())
#|        self.assertEqual(props["Directory"], "/data/shared/rejects")  # inherited parameter context
#|        props = dict(self.db.execute("SELECT name, resolved FROM properties WHERE component_id='p-s3'").fetchall())
#|        self.assertEqual(props["Bucket"], "acme-orders-raw")
#|        self.assertEqual(props["Secret Access Key"], "<sensitive>")
#|        props = dict(self.db.execute("SELECT name, resolved FROM properties WHERE component_id='p-enrich'").fetchall())
#|        self.assertEqual(props["Command Arguments"], "/data/landing/scripts/enrich.py ${order.id}")
#|
#|    def test_resources_and_hardcoded(self):
#|        rows = self.db.execute("SELECT kind, value, hardcoded FROM resources").fetchall()
#|        kinds = {(k, v): h for k, v, h in rows}
#|        self.assertEqual(kinds[("url", "https://validator.acme.com/api/v1/check")], 1)
#|        self.assertEqual(kinds[("s3_bucket", "acme-orders-raw")], 0)  # parameterized: not hardcoded
#|        self.assertEqual(kinds[("db_table", "file_audit")], 1)
#|        self.assertIn(("db_table", "customers"), kinds)
#|        self.assertIn(("db_table", "orders"), kinds)
#|        self.assertIn(("port", "8081"), kinds)
#|        self.assertIn(("jdbc", "jdbc:mariadb://dbhost.acme.com:3306/meta"), kinds)
#|        hard = (self.kb / "hardcoded.md").read_text(encoding="utf-8")
#|        self.assertIn("validator-backup.acme.com", hard)   # from Java code
#|        self.assertIn("10.20.30.40", hard)                  # from python script
#|        self.assertIn("s3://acme-orders-curated/audit/", hard)  # from groovy
#|
#|    def test_lint_findings(self):
#|        unhandled = self.findings("unhandled-relationship")
#|        self.assertEqual([r[0] for r in unhandled], ["p-validate"])
#|        self.assertIn("failure", unhandled[0][1])
#|        secrets = {m for _, m in self.findings("plaintext-secret")}
#|        self.assertTrue(any("API Token" in m for m in secrets))
#|        self.assertTrue(any("db.password" in m for m in secrets))
#|        self.assertTrue(any("etl.password" in m for m in secrets))
#|        dropped = {c for c, _ in self.findings("dropped-errors")}
#|        self.assertIn("p-audit", dropped)
#|        self.assertNotIn("p-gen", dropped)
#|
#|    def test_custom_code_linked(self):
#|        doc = (self.kb / "custom-code/ValidateOrderJson.md").read_text(encoding="utf-8")
#|        self.assertIn("ValidateOrderJson.java:16", doc)
#|        self.assertIn("- writes: `validated.by` (ValidateOrderJson.java:51), `validation.status` (ValidateOrderJson.java:50)", doc)
#|        self.assertIn("- reads: `order.id` (ValidateOrderJson.java:47), `vendor` (ValidateOrderJson.java:48)", doc)
#|        self.assertIn("Vendor JSON Ingestion", doc)
#|        self.assertFalse(self.findings("custom-code-missing"))
#|        script = (self.kb / "scripts/enrich-py.md").read_text(encoding="utf-8")
#|        self.assertIn("repo match", script)
#|        self.assertIn("Functions: enrich, main", script)
#|
#|    def test_database(self):
#|        doc = (self.kb / "db/metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("## file_audit", doc)
#|        self.assertIn("## customers", doc)       # from ExecuteSQL
#|        self.assertIn("## file_calls", doc)      # include_tables pattern
#|        self.assertNotIn("## unrelated", doc)
#|        self.assertIn("values of `source_system`: vendorA×2, vendorB×1", doc)
#|        self.assertIn("user_email", doc)
#|        self.assertNotIn("x@y.com", doc)          # sample rows are masked
#|        self.assertIn("order_archive", doc)       # missing table reported
#|        missing = self.findings("missing-table")
#|        self.assertEqual([(c, "order_archive" in m) for c, m in missing], [("p-archive", True)])
#|        mismatch = self.findings("field-mismatch")
#|        self.assertEqual(len(mismatch), 1)
#|        self.assertIn("extra_field", mismatch[0][1])
#|        self.assertIn("received_at", mismatch[0][1])
#|
#|    def test_index_summary(self):
#|        idx = (self.kb / "INDEX.md").read_text(encoding="utf-8")
#|        self.assertIn("Vendor JSON Ingestion", idx)
#|        self.assertIn("json", idx)
#|        self.assertIn("MetaDB `jdbc:mariadb://dbhost.acme.com:3306/meta` → tables: customers, file_audit, order_archive, orders", idx)
#|        self.assertIn("db.password=<redacted>", idx)
#|        self.assertLess(len(idx), 6000)
#|
#|    def test_cli_search_show_sql(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "validator")
#|        self.assertIn("Validate order", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "file_audit")
#|        self.assertIn("Write audit row", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "show", "p-valid")
#|        self.assertIn("### Validate order", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "show", "ValidateOrderJson")
#|        self.assertIn("# ValidateOrderJson", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT status, COUNT(*) n FROM file_calls GROUP BY status ORDER BY status")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("FAILED", out)
#|        for bad in ("DELETE FROM file_calls", "SELECT 1; DROP TABLE file_calls", "UPDATE file_calls SET status='x'"):
#|            rc, out = run_cli("--config", str(self.cfg_path), "sql", bad)
#|            self.assertEqual(rc, 1, bad)
#|        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT user_email FROM file_audit")
#|        self.assertIn("***", out)
#|        self.assertEqual(dbmod.run_query(self.cfg["databases"][0], "SELECT COUNT(*) FROM file_calls")[1], [(3,)])
#|
#|    def test_diagnose(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "order_id,vendor,staatus,order_source")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("Write audit row", out)
#|        self.assertIn("file_audit", out)
#|        self.assertIn("did you mean 'status'?", out)
#|        self.assertIn("expected fields not present in your headers: status, extra_field", out)
#|        self.assertIn("NOT NULL column(s) in file_audit that nothing supplies: received_at", out)
#|        self.assertIn("field-mismatch", out)  # known finding surfaced alongside the live diagnosis
#|
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "order_id", "vendor", "status", "extra_field")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("100%", out)
#|        self.assertIn("these headers have no matching column in file_audit: extra_field", out)
#|
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "totally", "unrelated", "headers")
#|        self.assertEqual(rc, 1)
#|        self.assertIn("no confident match", out)
#|
#|
#|class TestMetadata(unittest.TestCase):
#|    """Metadata-driven ingestion: OBJ_DEFINITION / OBJ_STRUCTURE / feed + API config tables, auto-detected."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        cls.cfg = load_config(cls.cfg_path)
#|        cls.logs = []
#|        build(cls.cfg, log=cls.logs.append)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def diagnose(self, *argv):
#|        rc, out = run_cli("--config", str(self.cfg_path), "diagnose", *argv)
#|        return rc, out
#|
#|    def test_roles_and_relations_detected(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("definition table: `OBJ_DEFINITION` · id `OBJ_ID` · lookup keys `FILE_NAME`, `TABLE_NAME` · target table column `TABLE_NAME`", doc)
#|        self.assertIn("field `COL_NAME` · type `DATA_TYPE` · order `COL_SEQ` · length `COL_LENGTH` · nullable `MANDATORY_FLAG` (flag means required)", doc)
#|        self.assertIn("`SOURCE_FEED_CONFIG.OBJ_ID` → `OBJ_DEFINITION.OBJ_ID` (shared column name)", doc)
#|        self.assertIn("`OBJ_STRUCTURE.OBJ_ID` → `OBJ_DEFINITION.OBJ_ID` (foreign key)", doc)
#|        self.assertNotIn("stg_sales |", doc.split("## Config tables")[1].split("## Relations")[0])  # target tables are not config
#|        self.assertIn("metadata.md", (self.kb / "INDEX.md").read_text(encoding="utf-8"))
#|
#|    def test_drift_findings(self):
#|        db = sqlite3.connect(self.kb / "kb.sqlite")
#|        rows = [r[0] for r in db.execute("SELECT message FROM findings WHERE kind='metadata-drift'")]
#|        db.close()
#|        self.assertEqual(len(rows), 2, rows)
#|        sales = next(r for r in rows if "stg_sales" in r)
#|        self.assertIn("NOT NULL column(s) of stg_sales not in the structure: load_ts", sales)
#|        self.assertIn("'CUST_NAME' length 50", sales)
#|        self.assertIn("'AMOUNT' is VARCHAR in the structure but DECIMAL(10,2)", sales)
#|        self.assertTrue(any("'stg_returns' does not exist" in r for r in rows))
#|        self.assertIn("metadata-drift", (self.kb / "issues.md").read_text(encoding="utf-8"))
#|
#|    def test_secrets_never_stored(self):
#|        from fixtures_builder import API_TOKEN
#|        blob = (self.kb / "kb.sqlite").read_bytes()
#|        for secret in ("Sup3rS3cret!", API_TOKEN, "hunter2"):
#|            self.assertFalse(secret.encode() in blob, f"{secret} stored in kb.sqlite")
#|            for path, text in all_text(self.kb).items():
#|                self.assertNotIn(secret, text, path)
#|        rc, out = self.diagnose("--feed", "crm_customers_api", "--json")
#|        self.assertNotIn(API_TOKEN, out)
#|        self.assertNotIn("hunter2", out)
#|
#|    def test_file_pattern_and_headers(self):
#|        rc, out = self.diagnose("--file", "/landing/pos/SALES_20260926.csv", "CUSTNAME", "AMT", "REGION", "ORDER_DT")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("pattern 'SALES_YYYYMMDD.csv'", out)
#|        self.assertIn("header 'CUSTNAME' differs from 'CUST_NAME' only by case", out)
#|        self.assertIn("header 'AMT' is not in the structure (did you mean 'AMOUNT'?)", out)
#|        self.assertIn("[error] structure field 'ORDER_NO' (seq 1) is not in the headers", out)
#|        self.assertIn("[warn] structure field 'AMOUNT' (seq 3) is not in the headers (nullable)", out)
#|        self.assertIn("header order differs from the structure sequence: headers REGION, ORDER_DT", out)
#|        self.assertIn("SFTP_PASSWORD=***", out)
#|        self.assertIn("Tag POS feed", out)           # linked through the related feed row's FEED_NAME
#|        self.assertIn("Read object metadata", out)   # reads the config tables
#|
#|    def test_feed_table_and_json(self):
#|        rc, out = self.diagnose("--feed", "pos_sales_feed", "--json")
#|        res = json.loads(out)
#|        self.assertEqual(res["definitions"][0]["target"], "stg_sales")
#|        self.assertEqual([f["name"] for f in res["definitions"][0]["fields"]], ["ORDER_NO", "CUST_NAME", "AMOUNT", "ORDER_DT", "REGION"])
#|        self.assertIn("p-feed", [p["id"] for p in res["processors"]])
#|        rc, out = self.diagnose("--table", "stg_customers", "CUST_ID", "NAME", "EMAIL")
#|        self.assertIn("OK structure, headers and target table agree", out)
#|        rc, out = self.diagnose("--feed", "crm_customers_api")
#|        self.assertIn("NIFI_JSON_API_CONFIG.API_NAME (exact)", out)
#|        self.assertIn("AUTH_HEADER=***", out)
#|
#|    def test_sample_file_headers(self):
#|        sample = Path(self.tmp) / "customers_20260926.json"
#|        sample.write_text(json.dumps({"data": [{"CUST_ID": 1, "NAME": "a", "E_MAIL": "x"}], "count": 1}), encoding="utf-8")
#|        rc, out = self.diagnose("--file", sample.name, "--sample", str(sample))
#|        self.assertIn("header 'E_MAIL' differs from 'EMAIL' only by case/underscores", out)
#|        csv_sample = Path(self.tmp) / "SALES_20260101.csv"
#|        csv_sample.write_text("ORDER_NO|CUST_NAME|AMOUNT|ORDER_DT|REGION\n1|a|2|2026-01-01|N\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", csv_sample.name, "--sample", str(csv_sample))
#|        self.assertNotIn("is not in the headers", out)
#|        self.assertNotIn("header order differs", out)
#|
#|    def test_nested_json_api_payload(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("· JSON path `JSON_PATH`", doc)
#|        self.assertNotIn("stg_orders:", doc.split("## Definitions vs. target tables")[1])  # columns match by COL_NAME
#|        payload = Path(self.tmp) / "orders_page1.json"
#|        payload.write_text(json.dumps({"page": 1, "orders": [{"id": 7, "customer": {"fullName": "A"}, "amount": 2.5}]}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(payload))
#|        self.assertIn("sample: JSON, record root $.orders, 3 nested field paths compared (order not checked)", out)
#|        self.assertIn("header 'customer.fullName' is not in the structure (did you mean 'customer.name'?)", out)
#|        self.assertIn("structure field 'customer.name' (seq 2) is not in the headers (nullable)", out)
#|        self.assertNotIn("order differs", out)
#|        self.assertNotIn("AUTH_HEADER=Bearer", out)
#|        good = Path(self.tmp) / "orders_ok.json"
#|        good.write_text(json.dumps({"orders": [{"id": 1, "customer": {"name": "B"}, "amount": 1}]}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(good))
#|        self.assertIn("OK structure, headers and target table agree", out)
#|        wrong = Path(self.tmp) / "orders_wrapped.json"
#|        wrong.write_text(json.dumps({"data": {"items": [{"id": 1}]}}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(wrong))
#|        self.assertIn("no JSON record found in the sample below root path '$.orders'", out)
#|
#|    def test_file_targets_hdfs_s3(self):
#|        from nifikb import metadata as metamod
#|        model = {"target_db": "metadata"}
#|        self.assertTrue(metamod.table_target(model, "stg_sales"))
#|        self.assertTrue(metamod.table_target(model, "dw.stg_sales"))
#|        for loc in ("s3://raw-bucket/sales/", "hdfs://nn:8020/data/raw/sales", "/data/raw/sales", "s3a://b/k"):
#|            self.assertFalse(metamod.table_target(model, loc), loc)
#|        self.assertFalse(metamod.table_target({"target_db": None}, "stg_sales"))
#|        with tempfile.TemporaryDirectory() as tmp:  # loads go to files: target checks off, no false "table missing"
#|            cfg_path = make_env(tmp, with_metadata=True)
#|            with open(cfg_path, "a", encoding="utf-8") as f:
#|                f.write('target_db = "none"\n')
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            db.execute("ALTER TABLE OBJ_DEFINITION ADD COLUMN HDFS_PATH TEXT")
#|            db.execute("UPDATE OBJ_DEFINITION SET HDFS_PATH = '/data/raw/sales' WHERE OBJ_ID = 1")
#|            db.commit()
#|            db.close()
#|            cfg = load_config(cfg_path)
#|            build(cfg, log=lambda m: None)
#|            doc = (Path(cfg["output"]["dir"]) / "metadata.md").read_text(encoding="utf-8")
#|            self.assertIn("location column `HDFS_PATH`", doc)
#|            self.assertIn("target checks off", doc)
#|            self.assertNotIn("does not exist in the target database", doc)
#|            rc, out = run_cli("--config", str(cfg_path), "diagnose", "--file", "SALES_20260926.csv", "ORDER_NO", "CUST_NAME")
#|            self.assertIn("→ loads to /data/raw/sales", out)
#|            self.assertNotIn("NOT NULL column(s) of stg_sales", out)
#|
#|    def test_content_validation_csv(self):
#|        sample = Path(self.tmp) / "SALES_20260930.csv"
#|        sample.write_text("ORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\n1,Alice,10.5,2026-09-01,EU\n,Bob,3,2026-09-02,EU\n"
#|                          "x7,Carol,4,2026-09-03,EU\n4,\"Dan, Jr\",5,31/31/2026,EU\n5,Eve,6,2026-09-05,EUROPE-WEST-1\n"
#|                          "6,Frank,7,2026-09-06,EU,extra\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", sample.name, "--sample", str(sample))
#|        self.assertIn("sample: CSV, delimiter ',' (configured in DELIMITER), with header row, 6 data rows checked", out)
#|        self.assertIn("'ORDER_NO' is empty but mandatory in 1 of 6 rows (e.g. row 3: '')", out)
#|        self.assertIn("'ORDER_NO' is not a valid INTEGER in 1 of 6 rows (e.g. row 4: 'x7')", out)
#|        self.assertIn("'ORDER_DT' is not a recognisable date / time (DATE) in 1 of 6 rows (e.g. row 5: '31/31/2026')", out)
#|        self.assertIn("'REGION' is longer than 10 characters in 1 of 6 rows", out)
#|        self.assertIn("1 of 6 rows do not have 5 columns (row 7 has 6)", out)
#|        self.assertNotIn("Dan, Jr", out.split("rows do not have")[0][-200:])  # quoted comma is fine
#|
#|    def test_content_validation_delimiter_and_encoding(self):
#|        piped = Path(self.tmp) / "SALES_20261001.csv"
#|        piped.write_text("ORDER_NO|CUST_NAME|AMOUNT|ORDER_DT|REGION\n1|A|2|2026-10-01|EU\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", piped.name, "--sample", str(piped))
#|        self.assertIn("the file is delimited by '|', but the delimiter is ','", out)
#|        self.assertIn("with header row, 1 data rows checked", out)
#|        latin = Path(self.tmp) / "SALES_20261002.csv"
#|        latin.write_bytes(b"\xef\xbb\xbfORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\n1,Ren\xe9e,2,2026-10-02,EU\n")
#|        rc, out = self.diagnose("--file", latin.name, "--sample", str(latin))
#|        self.assertIn("file is not valid UTF-8", out)
#|        latin.write_bytes(b"\xef\xbb\xbfORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\n1,Renee,2,2026-10-02,EU\n")
#|        rc, out = self.diagnose("--file", latin.name, "--sample", str(latin))
#|        self.assertIn("byte-order mark", out)
#|        self.assertNotIn("only by case/underscores", out)  # the BOM does not break the header match
#|
#|    def test_content_validation_json(self):
#|        payload = Path(self.tmp) / "orders_bad.json"
#|        payload.write_text(json.dumps({"orders": [{"id": 1, "customer": {"name": "A"}, "amount": 2.5},
#|                                                  {"customer": {"name": "B"}, "amount": "abc"}]}), encoding="utf-8")
#|        rc, out = self.diagnose("--feed", "orders_api", "--sample", str(payload))
#|        self.assertIn("'ORDER_ID' is empty but mandatory in 1 of 2 rows", out)
#|        self.assertIn("'AMOUNT' is not a valid DECIMAL in 1 of 2 rows (e.g. row 2: 'abc')", out)
#|
#|    def test_proposed_fixes(self):
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv", "ORDER_NO", "CUSTNAME", "AMOUNT", "ORDER_DT", "REGION")
#|        self.assertIn("proposed fixes (review first - nifikb never runs them):", out)
#|        self.assertIn("UPDATE OBJ_STRUCTURE SET COL_NAME = 'CUSTNAME' WHERE STRUCT_ID = 2;", out)
#|        self.assertIn("[sender (preferred) or config]", out)
#|        self.assertIn("UPDATE OBJ_STRUCTURE SET COL_LENGTH = 20 WHERE STRUCT_ID = 2;", out)
#|        self.assertIn("UPDATE OBJ_STRUCTURE SET DATA_TYPE = 'DECIMAL' WHERE STRUCT_ID = 3;", out)
#|        self.assertIn("INSERT INTO OBJ_STRUCTURE (OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, MANDATORY_FLAG) VALUES (1, 'load_ts', 'TEXT', 6, 'Y');", out)
#|        rc, out = self.diagnose("--file", "returns.csv")
#|        self.assertNotIn("stg_orders", out)  # never point a definition at a merely similar-looking table
#|        from nifikb.fixes import quote
#|        self.assertEqual(quote("O'Brien"), "'O''Brien'")
#|        piped = Path(self.tmp) / "SALES_20261003.csv"
#|        piped.write_text("ORDER_NO|CUST_NAME|AMOUNT|ORDER_DT|REGION\n1|A|2|2026-10-01|EU\n", encoding="utf-8")
#|        rc, out = self.diagnose("--file", piped.name, "--sample", str(piped))
#|        self.assertIn("UPDATE OBJ_DEFINITION SET DELIMITER = '|' WHERE OBJ_ID = 1;", out)
#|
#|    def test_unknown_suggests(self):
#|        rc, out = self.diagnose("--file", "SALEZ_20260926.csv")
#|        self.assertEqual(rc, 1)
#|        self.assertIn("did you mean: SALES_YYYYMMDD.csv", out)
#|
#|    def test_live_matches_snapshot(self):
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv", "--live", "--json")
#|        live = json.loads(out)
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv", "--json")
#|        snap = json.loads(out)
#|        self.assertTrue(live["live"])
#|        self.assertEqual([f["name"] for f in live["definitions"][0]["fields"]], [f["name"] for f in snap["definitions"][0]["fields"]])
#|        self.assertEqual(sorted(i["kind"] for i in live["definitions"][0]["issues"]),
#|                         sorted(i["kind"] for i in snap["definitions"][0]["issues"]))
#|
#|    def test_custom_code_reading_config_tables(self):
#|        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
#|        self.assertIn("`com.acme.meta.MetadataLookup` ([doc](custom-code/MetadataLookup.md)): OBJ_DEFINITION, OBJ_STRUCTURE, SOURCE_FEED_CONFIG", doc)
#|        self.assertNotIn("ValidateOrderJson", doc.split("## Custom code that reads these tables")[1].split("##")[0])
#|        rc, out = self.diagnose("--file", "SALES_20260926.csv")
#|        self.assertIn("Metadata lookup [MetadataLookup]", out)
#|        self.assertIn("custom MetadataLookup queries OBJ_DEFINITION, OBJ_STRUCTURE, SOURCE_FEED_CONFIG in its code", out)
#|
#|    def test_show_table(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "show", "stg_sales")
#|        self.assertEqual(rc, 0)
#|        self.assertIn("| load_ts |", out)
#|        self.assertNotIn("stg_customers", out)  # only that table's section
#|
#|    def test_search_finds_config_rows(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "sftp.pos.acme.com")
#|        self.assertIn("SOURCE_FEED_CONFIG", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "CUST_NAME")
#|        self.assertIn("SALES_YYYYMMDD.csv", out)
#|
#|    def test_mcp_server(self):
#|        import subprocess
#|        msgs = [
#|            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
#|                                                                          "clientInfo": {"name": "test", "version": "0"}}},
#|            {"jsonrpc": "2.0", "method": "notifications/initialized"},
#|            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
#|            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "diagnose", "arguments": {
#|                "key": "SALES_20260926.csv", "headers": ["ORDER_NO", "CUST_NAME", "AMOUNT", "REGION", "ORDER_DT"]}}},
#|            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "issues", "arguments": {"kind": "metadata-drift"}}},
#|            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "read_kb_file", "arguments": {"path": "../nifikb.toml"}}},
#|            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "search", "arguments": {"query": "pos_sales_feed"}}},
#|            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "sql", "arguments": {"query": "DELETE FROM OBJ_DEFINITION"}}},
#|        ]
#|        proc = subprocess.run([sys.executable, "-m", "nifikb", "--config", str(self.cfg_path), "mcp"],
#|                              input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True, encoding="utf-8",
#|                              cwd=str(Path(__file__).resolve().parent.parent), timeout=120)
#|        replies = {r["id"]: r for r in (json.loads(line) for line in proc.stdout.splitlines() if line.strip())}
#|        self.assertEqual(sorted(replies), [1, 2, 3, 4, 5, 6, 7], proc.stderr)
#|        self.assertEqual(replies[1]["result"]["serverInfo"]["name"], "nifikb")
#|        self.assertIn("diagnose", [t["name"] for t in replies[2]["result"]["tools"]])
#|        diag = replies[3]["result"]["content"][0]["text"]
#|        self.assertIn("header order differs from the structure sequence", diag)
#|        self.assertIn("→ target table stg_sales", diag)
#|        self.assertNotIn('"definitions"', diag)  # text only unless structured=true
#|        self.assertIn("stg_returns", replies[4]["result"]["content"][0]["text"])
#|        self.assertTrue(replies[5]["result"]["isError"])       # no reading outside kb/
#|        self.assertIn("SOURCE_FEED_CONFIG", replies[6]["result"]["content"][0]["text"])
#|        self.assertTrue(replies[7]["result"]["isError"])       # read-only
#|
#|    def test_overrides_and_validation(self):
#|        from nifikb import metadata as metamod
#|        cfg = dict(self.cfg, metadata={"db": "metadata", "structure_order": "bad name;"})
#|        with self.assertRaises(ValueError):
#|            metamod.settings(cfg)
#|        cfg = dict(self.cfg, metadata={"db": "nope"})
#|        with self.assertRaises(ValueError):
#|            metamod.settings(cfg)
#|
#|
#|LOG_SAMPLE = """2026-09-26 10:15:01,100 INFO [main] org.apache.nifi.NiFi Launching NiFi...
#|2026-09-26 10:15:02,254 ERROR [Timer-Driven Process Thread-1] o.a.n.p.standard.PutDatabaseRecord PutDatabaseRecord[id=inst-p-audit-0000-0000-000000000000] Failed to put Records to database for StandardFlowFileRecord[uuid=6b52c7d3-acef-4940-8ff7-d91b7a7abd21,claim=StandardContentClaim [resourceClaim=StandardResourceClaim[id=1-6, container=default, section=6], offset=0, length=53],offset=0,name=orders_0926.json,size=53]. Routing to failure.
#|org.apache.nifi.processors.standard.db.TableNotFoundException: Table meta.file_audit not found, ensure the Catalog, Schema, and/or Table Names match
#|\tat org.apache.nifi.processors.standard.db.TableSchema.from(TableSchema.java:117)
#|Caused by: java.sql.SQLSyntaxErrorException: Table 'meta.file_audit' doesn't exist
#|\tat org.mariadb.jdbc.X.y(X.java:1)
#|2026-09-26 10:16:02,254 ERROR [Timer-Driven Process Thread-2] o.a.n.p.standard.PutDatabaseRecord PutDatabaseRecord[id=inst-p-audit-0000-0000-000000000000] Failed to put Records to database for StandardFlowFileRecord[uuid=9b52c7d3-acef-4940-8ff7-d91b7a7abd21,claim=,offset=0,name=orders_0927.json,size=53]. Routing to failure.
#|2026-09-26 10:17:00,000 WARN [Timer-Driven Process Thread-3] o.a.n.c.repository.FileSystemRepository Unable to write flowfile content; waiting for archive cleanup. Total number of files currently archived = 12
#|2026-09-26 10:18:00,000 DEBUG [x] o.a.n.Y password=hunter2 ignored debug line
#|"""
#|BOOT_SAMPLE = """2026-09-26 09:00:00,000 INFO [main] org.apache.nifi.bootstrap.Command Launched Apache NiFi with Process ID 4242
#|2026-09-26 09:30:00,000 INFO [main] o.a.n.b.NotificationServiceManager Registered no Notification Services for Notification Type NIFI_DIED
#|2026-09-26 11:59:00,000 WARN [NiFi Bootstrap Command Listener] org.apache.nifi.bootstrap.RunNiFi Apache NiFi appears to have died. Restarting...
#|"""
#|
#|
#|class TestLogsAndProvenance(unittest.TestCase):
#|    """nifi-app / bootstrap log indexing (incremental, rotation, causes, grouping) and provenance through a fake NiFi API."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import FakeNiFi
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.logdir = Path(cls.tmp) / "logs"
#|        cls.logdir.mkdir()
#|        (cls.logdir / "nifi-app.log").write_text(LOG_SAMPLE.replace("inst-p-audit-0000-0000-000000000000", "inst-p-audit"), encoding="utf-8")
#|        (cls.logdir / "nifi-bootstrap.log").write_text(BOOT_SAMPLE, encoding="utf-8")
#|        cls.fake = FakeNiFi()
#|        os.environ["NIFIKB_TEST_NIFI_PW"] = "pw123456789"
#|        cls.cfg_path = make_env(cls.tmp)
#|        with open(cls.cfg_path, "a", encoding="utf-8") as f:
#|            f.write(f'\n[logs]\ndirs = ["{cls.logdir.as_posix()}"]\n'
#|                    f'\n[nifi_api]\nurl = "{cls.fake.url}"\nusername = "admin"\npassword_env = "NIFIKB_TEST_NIFI_PW"\n'
#|                    f'\n[registry]\nurl = "{cls.fake.url.replace("/nifi-api", "")}"\nusername = "admin"\npassword_env = "NIFIKB_TEST_NIFI_PW"\n')
#|        cls.cfg = load_config(cls.cfg_path)
#|        build(cls.cfg, log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.fake.stop()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def cli(self, *argv):
#|        return run_cli("--config", str(self.cfg_path), *argv)
#|
#|    def test_log_parser_units(self):
#|        from nifikb import logs
#|        events = list(logs.parse_lines(enumerate(LOG_SAMPLE.splitlines(), 1), "nifi-app.log"))
#|        self.assertEqual([e["level"] for e in events], ["ERROR", "ERROR", "WARN"])
#|        e = events[0]
#|        self.assertEqual((e["component_type"], e["component_id"]), ("PutDatabaseRecord", "inst-p-audit-0000-0000-000000000000"))
#|        self.assertEqual((e["flowfile_uuid"], e["filename"]), ("6b52c7d3-acef-4940-8ff7-d91b7a7abd21", "orders_0926.json"))
#|        self.assertEqual(e["cause"], "SQLSyntaxErrorException: Table 'meta.file_audit' doesn't exist")  # the root cause
#|        self.assertEqual(events[0]["template"], events[1]["template"])  # same shape -> grouped
#|        boot = list(logs.parse_lines(enumerate(BOOT_SAMPLE.splitlines(), 1), "nifi-bootstrap.log", bootstrap=True))
#|        self.assertEqual([b["level"] for b in boot], ["LIFECYCLE", "WARN"])  # NIFI_DIED setup line is not a crash
#|
#|    def test_logs_cli(self):
#|        rc, out = self.cli("logs", "--file", "orders_0926.json")
#|        self.assertIn("PutDatabaseRecord", out)
#|        self.assertIn("(Write audit row `p-audit` in NiFi Flow)", out)  # runtime id -> flow component
#|        self.assertIn("cause: SQLSyntaxErrorException", out)
#|        rc, out = self.cli("logs", "--component", "Write audit row")
#|        self.assertIn("x2", out)
#|        rc, out = self.cli("logs", "--level", "LIFECYCLE")
#|        self.assertIn("Launched Apache NiFi", out)
#|        self.assertNotIn("hunter2", out)
#|
#|    def test_incremental_and_rotation(self):
#|        from nifikb import logs
#|        from nifikb.store import Store
#|        store = Store(str(Path(self.cfg["output"]["dir"]) / "kb.sqlite"))
#|        try:
#|            self.assertEqual(logs.index(self.cfg, store, log=lambda m: None), (0, 0))  # nothing new
#|            app = self.logdir / "nifi-app.log"
#|            with open(app, "a", encoding="utf-8") as f:
#|                f.write("2026-09-26 12:00:00,000 ERROR [T] o.a.n.X FetchFile[id=inst-p-extract] Could not fetch file a.csv\n")
#|            self.assertEqual(logs.index(self.cfg, store, log=lambda m: None)[1], 1)  # only the new line
#|            (self.logdir / "nifi-app_2026-09-26_10.0.log").write_text(LOG_SAMPLE.replace("inst-p-audit-0000-0000-000000000000", "inst-p-audit"),
#|                                                                        encoding="utf-8")  # rolled copy: duplicates ignored
#|            self.assertEqual(logs.index(self.cfg, store, log=lambda m: None)[1], 0)
#|        finally:
#|            store.close()
#|
#|    def test_provenance_dropped_flowfile(self):
#|        rc, out = self.cli("provenance", "--file", "orders_0926.json")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("DROPPED at Write rejects (PutFile): Auto-Terminated by failure Relationship", out)
#|        self.assertIn("ROUTE", out)
#|        self.assertIn("-> invalid", out)
#|        self.assertIn("(Validate order `p-valida` in", out)
#|        self.assertIn("validation.error=vendor missing", out)
#|        self.assertNotIn("tok-SECRET-9", out)
#|        self.assertTrue(self.fake.deleted)  # the temporary provenance query was removed
#|        rc, out = self.cli("provenance", "--file", "late.json")
#|        self.assertIn("FlowFile Expired", out)
#|        rc, out = self.cli("provenance", "--file", "never.json")
#|        self.assertIn("no provenance events", out)
#|
#|    def test_bulletins_and_doctor(self):
#|        rc, out = self.cli("bulletins")
#|        self.assertIn("Table file_audit not found", out)
#|        self.assertIn("(Write audit row", out)
#|        rc, out = self.cli("doctor", "--offline")
#|        self.assertIn("[OK  ] NiFi API", out)
#|        self.assertIn("[OK  ] logs", out)
#|
#|    def test_health(self):
#|        rc, out = self.cli("health")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("[error] back-pressure: queue Extract fields → Validate order in NiFi Flow/Vendor JSON Ingestion is at 100%", out)
#|        self.assertIn("[error] stuck-queue: 5 FlowFile(s) waiting in Validate order → Write rejects", out)
#|        self.assertIn("the destination processor is STOPPED", out)
#|        self.assertIn("(Write rejects `p-reject` in", out)
#|        self.assertIn("invalid-processor: Archive order (PutDatabaseRecord) in NiFi Flow is INVALID: 'Table Name' validated against", out)
#|        self.assertIn("service-not-enabled: controller service UnusedWriter is DISABLED", out)
#|        self.assertIn("[error] disk: content repository default at 96%", out)
#|        self.assertIn("[warn] heap: JVM heap at 91%", out)
#|        self.assertIn("[error] cluster: only 2 of 3 cluster nodes connected", out)
#|        self.assertEqual(out.index("[error]") < out.index("[warn]"), True)  # errors first
#|
#|    def test_daily_report(self):
#|        rc, out = self.cli("report", "--hours", "100000")
#|        self.assertIn("# NiFi daily report", out)
#|        self.assertIn("## Live NiFi health", out)
#|        self.assertIn("stuck-queue", out)
#|        self.assertIn("## New error patterns (first seen in this window)", out)
#|        self.assertIn("cause: SQLSyntaxErrorException", out)
#|        self.assertIn("Launched Apache NiFi", out)
#|        html_path = Path(self.tmp) / "report.html"
#|        rc, out = self.cli("report", "--hours", "100000", "--html", str(html_path))
#|        page = html_path.read_text(encoding="utf-8")
#|        self.assertTrue(page.startswith("<!doctype html>"))
#|        self.assertIn("<h2>Most frequent errors</h2>", page)
#|        rc, out = self.cli("report", "--send")
#|        self.assertIn("nothing to send", out)
#|
#|    def test_report_delivery(self):
#|        import http.server
#|        import socketserver
#|        import threading
#|        from nifikb import report as rp
#|        posted, mails = [], []
#|
#|        class Hook(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def do_POST(self):
#|                posted.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
#|                self.send_response(200)
#|                self.end_headers()
#|
#|        class Smtp(socketserver.StreamRequestHandler):
#|            def handle(self):
#|                w = lambda s: self.wfile.write((s + "\r\n").encode())
#|                w("220 fake")
#|                data, in_data = [], False
#|                for raw in self.rfile:
#|                    line = raw.decode().rstrip("\r\n")
#|                    if in_data:
#|                        if line == ".":
#|                            in_data = False
#|                            mails.append("\n".join(data))
#|                            w("250 ok")
#|                        else:
#|                            data.append(line)
#|                        continue
#|                    cmd = line[:4].upper()
#|                    if cmd in ("EHLO", "HELO"):
#|                        w("250 fake")
#|                    elif cmd == "DATA":
#|                        in_data = True
#|                        w("354 go")
#|                    elif cmd == "QUIT":
#|                        w("221 bye")
#|                        return
#|                    else:
#|                        w("250 ok")
#|
#|        hook = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hook)
#|        smtp = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Smtp)
#|        for srv in (hook, smtp):
#|            threading.Thread(target=srv.serve_forever, daemon=True).start()
#|        try:
#|            os.environ["NIFIKB_TEST_HOOK"] = f"http://127.0.0.1:{hook.server_address[1]}/hook"
#|            cfg = dict(self.cfg, report={"email_to": ["team@acme.test"], "email_from": "kb@acme.test", "smtp_host": "127.0.0.1",
#|                                         "smtp_port": smtp.server_address[1], "webhook_url_env": "NIFIKB_TEST_HOOK"})
#|            r = {"title": "NiFi daily report — test", "stats": {"errors": 3}, "sections": [("Most frequent errors", ["x3 boom"])]}
#|            done = rp.send(cfg, r)
#|            self.assertEqual(done, ["e-mailed to team@acme.test", "posted to the webhook"])
#|            self.assertIn("x3 boom", posted[0]["text"])
#|            self.assertIn("Subject: NiFi daily report", mails[0])
#|            self.assertIn("text/html", mails[0])
#|        finally:
#|            hook.shutdown()
#|            smtp.shutdown()
#|            smtp.server_close()
#|            hook.server_close()
#|
#|    def test_versions(self):
#|        rc, out = self.cli("versions")
#|        self.assertIn("NiFi Flow / Vendor JSON Ingestion: registry flow f1 (bucket b1), deployed v3", out)
#|        self.assertIn("live state: STALE - A newer version (4) is available", out)
#|        self.assertIn("alice: switch vendor to API v2", out)
#|        self.assertIn("bob: add order validation  <- deployed", out)
#|        rc, out = self.cli("health")
#|        self.assertIn("version-state: process group NiFi Flow / Vendor JSON Ingestion (registry flow vendor-json, v3): a newer version exists", out)
#|        doc = next((Path(self.cfg["output"]["dir"]) / "flows").glob("*vendor-json*.md")).read_text(encoding="utf-8")
#|        self.assertIn("version-controlled: flow f1 v3 (bucket b1)", doc)
#|
#|    def test_bad_password(self):
#|        from nifikb import nifiapi
#|        c = nifiapi.Client({"url": self.fake.url, "username": "admin", "password": "wrong"})
#|        with self.assertRaises(nifiapi.NiFiApiError) as e:
#|            c.about()
#|        self.assertIn("authentication failed", str(e.exception))
#|
#|
#|class TestInvestigate(unittest.TestCase):
#|    """The one-call investigation: provenance drop, file log errors, structure errors, code line, drift - ranked."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import FakeNiFi, metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        logdir = Path(cls.tmp) / "logs"
#|        logdir.mkdir()
#|        (logdir / "nifi-app.log").write_text(LOG_SAMPLE.replace("inst-p-audit-0000-0000-000000000000", "inst-p-audit")
#|                                             .replace("orders_0926.json", "SALES_20260926.csv"), encoding="utf-8")
#|        cls.fake = FakeNiFi()
#|        cls.fake.EVENTS = [dict(e, filename="SALES_20260926.csv") if e["filename"] == "orders_0926.json" else e for e in FakeNiFi.EVENTS]
#|        os.environ["NIFIKB_TEST_NIFI_PW"] = "pw123456789"
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        with open(cls.cfg_path, "a", encoding="utf-8") as f:
#|            f.write(f'\n[logs]\ndirs = ["{logdir.as_posix()}"]\n[nifi_api]\nurl = "{cls.fake.url}"\nusername = "admin"\n'
#|                    f'password_env = "NIFIKB_TEST_NIFI_PW"\n')
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.fake.stop()
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_ranked_report(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260926.csv", "--error", "Structure mismatch",
#|                          "--headers", "ORDER_NO", "CUSTNAME", "AMOUNT")
#|        self.assertEqual(rc, 0, out)
#|        ranked = out.split("## Most likely causes")[1].split("##")[0]
#|        lines = [ln for ln in ranked.splitlines() if ln[:2].rstrip(".").isdigit()]
#|        self.assertIn("DROPPED at Write rejects (PutFile): Auto-Terminated by failure Relationship", lines[0])
#|        self.assertIn("load audit: last load FAILED - /landing/pos/SALES_20260926.csv, status FAILED, at 2026-09-26 02:14:00, 0 rows, "
#|                      "error: Column count mismatch at line 12", lines[1])
#|        self.assertIn("logged ERROR x1 for this file", lines[2])
#|        self.assertIn("SQLSyntaxErrorException", lines[2])
#|        self.assertIn("## Load audit (FILE_LOAD_AUDIT)", out)
#|        self.assertTrue(any("header 'CUSTNAME' differs from 'CUST_NAME'" in ln for ln in lines))
#|        self.assertTrue(any("MetadataLookup.java:" in ln for ln in lines))
#|        self.assertIn("## Provenance (what happened to the FlowFile)", out)
#|        self.assertIn("## Metadata (config tables)", out)
#|        self.assertNotIn("tok-SECRET-9", out)
#|
#|    def test_audit_cli_and_doctor(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "audit", "--file", "SALES_20260925.csv")
#|        self.assertIn("load audit table FILE_LOAD_AUDIT (file column FILE_NAME, status LOAD_STATUS, time LOAD_TS)", out)
#|        self.assertIn("status SUCCESS, at 2026-09-25 02:10:00, 1200 rows", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "audit", "--definition", "1")
#|        self.assertIn("x /landing/pos/SALES_20260926.csv, status FAILED", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "doctor", "--offline")
#|        self.assertIn("[OK  ] load audit: FILE_LOAD_AUDIT: file FILE_NAME, status LOAD_STATUS, time LOAD_TS, error ERROR_MSG", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260101.csv")
#|        self.assertIn("no load-audit row for SALES_20260101.csv", out)
#|
#|    def test_not_picked_up(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260101.csv")
#|        self.assertIn("no provenance events for 'SALES_20260101.csv': it never entered NiFi under that name", out)
#|
#|    def test_web_page(self):
#|        import threading
#|        import urllib.request
#|        from http.server import ThreadingHTTPServer
#|        from nifikb.web import App, make_handler
#|        cfg = load_config(self.cfg_path)
#|        os.environ["NIFIKB_TEST_WEB_PW"] = "s3cret-web"
#|        cfg["web"] = {"user": "support", "password_env": "NIFIKB_TEST_WEB_PW"}
#|        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(App(cfg)))
#|        threading.Thread(target=server.serve_forever, daemon=True).start()
#|        base = f"http://127.0.0.1:{server.server_address[1]}"
#|        auth = {"Authorization": "Basic " + __import__("base64").b64encode(b"support:s3cret-web").decode()}
#|
#|        def get(path, data=None, headers=None, ctype=None):
#|            req = urllib.request.Request(base + path, data=data, headers=dict(auth if headers is None else headers))
#|            if ctype:
#|                req.add_header("Content-Type", ctype)
#|            with urllib.request.urlopen(req, timeout=60) as r:
#|                return r.read().decode("utf-8")
#|        try:
#|            with self.assertRaises(urllib.error.HTTPError) as e:
#|                get("/", headers={})
#|            self.assertEqual(e.exception.code, 401)
#|            self.assertIn("Investigate a problem", get("/"))
#|            page = get("/investigate", data=urllib.parse.urlencode({"file": "SALES_20260926.csv", "headers": "ORDER_NO,CUSTNAME"}).encode(),
#|                       ctype="application/x-www-form-urlencoded")
#|            self.assertIn("<ol><li>FlowFile u-1 DROPPED at Write rejects", page)
#|            self.assertIn("<h2>Provenance (what happened to the FlowFile)</h2>", page)
#|            boundary = "----nifikbtest"
#|            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\nSALES_20260927.csv\r\n"
#|                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"sample\"; filename=\"SALES_20260927.csv\"\r\n"
#|                    f"Content-Type: text/csv\r\n\r\nORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION\r\nabc,A,1,2026-09-27,EU\r\n--{boundary}--\r\n").encode()
#|            page = get("/investigate", data=body, ctype=f"multipart/form-data; boundary={boundary}")
#|            self.assertIn("&#x27;ORDER_NO&#x27; is not a valid INTEGER", page)
#|            page = get("/search?q=" + urllib.parse.quote("<script>alert(1)</script>"))
#|            self.assertNotIn("<script>alert(1)</script>", page)
#|            self.assertIn("&lt;script&gt;", page)
#|            self.assertIn("<h1>NiFi daily report", get("/report"))
#|            self.assertIn("stuck-queue", get("/health"))
#|        finally:
#|            server.shutdown()
#|            server.server_close()
#|
#|    def test_eval_harness(self):
#|        cases = Path(self.tmp) / "cases.toml"
#|        cases.write_text('''
#|[[case]]
#|id = "hit"
#|ticket = "SALES of 26 Sep did not load"
#|file = "SALES_20260926.csv"
#|headers = ["ORDER_NO", "CUSTNAME", "AMOUNT"]
#|expect_any = ["CUSTNAME"]
#|top = 5
#|answer_expect = ["CUST_NAME"]
#|
#|[[case]]
#|id = "miss"
#|file = "SALES_20260926.csv"
#|expect_any = ["something that is not the cause"]
#|''', encoding="utf-8")
#|        agent = f'"{sys.executable}" -c "import sys; t = sys.stdin.read(); print(\'Cause: rename CUST_NAME\' if \'CUSTNAME\' in t else \'no idea\')"'
#|        rc, out = run_cli("--config", str(self.cfg_path), "eval", "--cases", str(cases), "--agent", agent,
#|                          "--save", str(Path(self.tmp) / "eval.json"))
#|        self.assertEqual(rc, 2)  # one case fails on purpose
#|        self.assertIn("PASS hit: cause at rank", out)
#|        self.assertIn("agent ok", out)
#|        self.assertIn("FAIL miss", out)
#|        self.assertIn("tools: 1/2 cases have the true cause in their top ranks", out)
#|        self.assertIn("agent: 1/2 answers name the true cause", out)
#|        saved = json.loads((Path(self.tmp) / "eval.json").read_text(encoding="utf-8"))
#|        self.assertEqual([r["id"] for r in saved["results"]], ["hit", "miss"])
#|
#|    def test_mcp_investigate(self):
#|        from nifikb.mcp import Server
#|        text, err = Server(str(self.cfg_path)).call("investigate", {"file": "SALES_20260926.csv", "headers": ["ORDER_NO", "CUSTNAME"]})
#|        self.assertFalse(err, text)
#|        self.assertIn("## Most likely causes", text)
#|
#|
#|class TestConfigChanges(unittest.TestCase):
#|    """Config-row changes between metadata snapshots: live 'changed since snapshot', change log, per-definition history."""
#|
#|    def test_changes_tracked(self):
#|        from fixtures_builder import metadata_flow
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            cfg = load_config(cfg_path)
#|            build(cfg, log=lambda m: None)
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            db.executescript("""
#|                UPDATE OBJ_STRUCTURE SET COL_LENGTH = 20 WHERE OBJ_ID = 1 AND COL_NAME = 'CUST_NAME';
#|                INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES (1, 'LOAD_TS', 'TEXT', 6, NULL, 'Y');
#|                UPDATE SOURCE_FEED_CONFIG SET REMOTE_DIR = '/outbound/sales_v2', SFTP_PASSWORD = 'N3wS3cret!' WHERE FEED_ID = 10;
#|                UPDATE OBJ_STRUCTURE SET COL_LENGTH = 99 WHERE OBJ_ID = 2 AND COL_NAME = 'NAME';
#|            """)
#|            db.commit()
#|            db.close()
#|
#|            rc, out = run_cli("--config", str(cfg_path), "diagnose", "--file", "SALES_20260926.csv", "--live")
#|            self.assertIn("Config rows changed since the snapshot of", out)
#|            self.assertIn("CUST_NAME): COL_LENGTH 50 → 20", out)
#|            self.assertIn("LOAD_TS", out)
#|            self.assertIn("REMOTE_DIR /outbound/sales → /outbound/sales_v2", out)
#|            self.assertNotIn("N3wS3cret!", out)
#|            self.assertNotIn("SFTP_PASSWORD", out.split("Config rows changed since")[1].split("\n\n")[0])
#|            self.assertNotIn("COL_LENGTH 100 → 99", out)  # other definition
#|
#|            build(cfg, refresh_db=True, log=lambda m: None)
#|            log = (Path(cfg["output"]["dir"]) / "CHANGELOG.md").read_text(encoding="utf-8")
#|            self.assertIn("config OBJ_STRUCTURE:", log)
#|            self.assertIn("COL_LENGTH 50 → 20", log)
#|            rc, out = run_cli("--config", str(cfg_path), "diagnose", "--feed", "pos_sales_feed")
#|            self.assertIn("Recent config-row changes for this definition", out)
#|            self.assertIn("REMOTE_DIR /outbound/sales → /outbound/sales_v2", out)
#|            self.assertNotIn("COL_LENGTH 100 → 99", out)
#|            self.assertFalse(b"N3wS3cret!" in (Path(cfg["output"]["dir"]) / "kb.sqlite").read_bytes())
#|
#|    def test_metadata_refresh_interval(self):
#|        from fixtures_builder import metadata_flow
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp, flow=metadata_flow(), with_metadata=True))
#|            build(cfg, log=lambda m: None)
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "up-to-date")
#|            cfg["metadata"]["refresh_hours"] = 0  # always due -> config rows re-read, flow unchanged
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "built")
#|
#|
#|class TestJavaAndLineage(unittest.TestCase):
#|    """Company-style Java custom processors (base classes, constants, attribute maps), the deployed NAR's bytecode,
#|    and attribute lineage through a metadata-driven flow."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import STD_MANIFEST, lineage_flow, make_nar
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=lineage_flow(), with_metadata=True)
#|        make_nar(Path(cls.tmp) / "nars" / "nifi-standard-nar-1.27.0.nar", STD_MANIFEST, group="org.apache.nifi", artifact="nifi-standard-nar")
#|        cls.cfg = load_config(cls.cfg_path)
#|        build(cls.cfg, log=lambda m: None)
#|        cls.kb = Path(cls.cfg["output"]["dir"])
#|        db = sqlite3.connect(cls.kb / "kb.sqlite")
#|        cls.found = db.execute("SELECT kind, component_id, message FROM findings").fetchall()
#|        db.close()
#|        cls.doc = (cls.kb / "custom-code" / "MetadataLookup.md").read_text(encoding="utf-8")
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def of(self, kind):
#|        return [(c, m) for k, c, m in self.found if k == kind]
#|
#|    def test_inheritance_and_constants(self):
#|        self.assertIn("extends AbstractMetadataProcessor → AbstractProcessor", self.doc)
#|        self.assertIn("| metadata-db | Metadata DB |  | Y | service DBCPService (from AbstractMetadataProcessor)", self.doc)
#|        self.assertIn("| lookup-mode | Lookup Mode | by-file |  | one of by-file, by-feed |", self.doc)
#|        self.assertIn("- `failure`: Lookup failed (from AbstractMetadataProcessor)", self.doc)
#|        self.assertIn("- `not found`: no definition", self.doc)
#|        self.assertIn("**Does:** Looks up the object definition; structure and feed config", self.doc)  # ';' inside the annotation
#|
#|    def test_attributes_from_code(self):
#|        self.assertIn("- reads: `filename` (MetadataLookup.java:", self.doc)
#|        self.assertIn("`table_name` (MetadataLookup.java:", self.doc)
#|        self.assertIn("`delimiter` (MetadataLookup.java:", self.doc)
#|        flow = (self.kb / "flows" / "root.md").read_text(encoding="utf-8")
#|        section = flow.split('<a id="c-l-meta"></a>')[1].split("### ")[0]
#|        self.assertIn("writes attributes: delimiter, structure.json, table_name", section)
#|        self.assertIn("reads attributes: filename", section)
#|
#|    def test_maven_and_deployment(self):
#|        self.assertIn("Maven module: `com.acme:acme-meta-processors:2.0.0`", self.doc)
#|        self.assertIn("Packaged by NAR module: `acme-meta-nar:2.0.0`", self.doc)
#|        self.assertIn("deployed NAR: 2.0.0 (acme-meta-nar-2.0.0.nar)", self.doc)
#|        self.assertIn("⚠ In the repo source but **not in the deployed build**: attribute 'delimiter'", self.doc)
#|        self.assertIn("Tables in its SQL: `obj_structure`", self.doc)
#|        self.assertEqual([c for c, _ in self.of("custom-source-drift")], ["p-lookup-meta"])
#|        self.assertIn("acme-meta-nar 1.9.0 but lib has 2.0.0", self.of("bundle-version")[0][1])
#|        self.assertFalse(self.of("custom-nar-missing"))
#|
#|    def test_registration(self):
#|        from nifikb import code as codemod
#|        idx = codemod.CodeIndex([codemod.index_file(p) for p in codemod.iter_code_files([Path(self.tmp) / "meta-repo"])])
#|        self.assertTrue(idx.by_fqcn["com.acme.meta.MetadataLookup"][0]["component"]["registered"])
#|        legacy = idx.by_fqcn["com.acme.meta.LegacyMetadataLookup"][0]["component"]  # a processor only through its base class
#|        self.assertFalse(legacy["registered"])
#|        self.assertEqual(legacy["kind"], "PROCESSOR")
#|        self.assertNotIn("com.acme.meta.base.MetaConstants", idx.by_fqcn)
#|        self.assertNotIn("com.acme.meta.MockUpstream", idx.by_fqcn)             # src/test is not deployed code
#|        self.assertEqual(idx.by_fqcn["com.acme.meta.CachingMetadataService"][0]["component"]["kind"], "CONTROLLER_SERVICE")
#|        self.assertEqual(idx.implementers("MetadataService"), ["com.acme.meta.CachingMetadataService"])
#|        self.assertIn("service MetadataService (implemented by CachingMetadataService)", self.doc)
#|
#|    def test_attribute_lineage(self):
#|        misnamed = self.of("attribute-misnamed")
#|        self.assertEqual([c for c, _ in misnamed], ["l-ua"])
#|        self.assertIn("reads ${tableName}", misnamed[0][1])
#|        self.assertIn("'table_name'", misnamed[0][1])
#|        unset = self.of("attribute-unset")
#|        self.assertEqual([(c, "${target_catalog}" in m) for c, m in unset], [("l-put", True)])
#|        self.assertFalse(any("${mode}" in m for _, m in unset + misnamed))  # guarded with isEmpty()
#|        self.assertFalse(any(m.startswith("reads ${target.table}") for _, m in unset + misnamed))  # set upstream by UpdateAttribute
#|
#|    def test_error_text_search(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "search", "Structure mismatch")
#|        self.assertIn("MetadataLookup.java:", out)
#|        self.assertIn("custom-code/MetadataLookup.md", out)
#|
#|    def test_class_strings_parser(self):
#|        from fixtures_builder import class_file
#|        from nifikb.catalog import class_strings
#|        self.assertEqual(class_strings(class_file("a.B", ["x", "SELECT 1 FROM t", "\x01 and \x01"])), ["x", "SELECT 1 FROM t", "{} and {}"])
#|        self.assertEqual(class_strings(b"not a class"), [])
#|
#|
#|class TestSparkSubmit(unittest.TestCase):
#|    def test_script_submitting_spark(self):
#|        from fixtures_builder import proc
#|        flow = nested_flow()
#|        flow["rootGroup"]["processors"].append(proc(
#|            "p-spark", "Run sales aggregation", "org.apache.nifi.processors.standard.ExecuteStreamCommand",
#|            {"Command Path": "bash", "Command Arguments": "/opt/jobs/submit_sales.sh ${filename}"}, auto=["original"]))
#|        with tempfile.TemporaryDirectory() as tmp:
#|            repo = Path(tmp) / "jobs-repo"
#|            repo.mkdir()
#|            (repo / "submit_sales.sh").write_text(
#|                "#!/bin/bash\nRUN_DATE=$1\nspark-submit --master yarn --deploy-mode cluster \\\n  --class com.acme.etl.SalesAggregate "
#|                "--name sales-agg \\\n  /opt/jobs/sales-etl.jar --date $RUN_DATE\n", encoding="utf-8")
#|            cfg_path = make_env(tmp, flow=flow, with_db=False)
#|            text = cfg_path.read_text(encoding="utf-8").replace('repos = ["', f'repos = ["{repo.as_posix()}", "')
#|            cfg_path.write_text(text, encoding="utf-8")
#|            cfg = load_config(cfg_path)
#|            build(cfg, log=lambda m: None)
#|            kb = Path(cfg["output"]["dir"])
#|            flow_doc = (kb / "flows" / "root.md").read_text(encoding="utf-8")
#|            self.assertIn("submits Spark job: com.acme.etl.SalesAggregate in /opt/jobs/sales-etl.jar (yarn, cluster)", flow_doc)
#|            script_doc = next((kb / "scripts").glob("submit-sales*.md")).read_text(encoding="utf-8")
#|            self.assertIn("## Spark jobs submitted", script_doc)
#|            self.assertIn("name `sales-agg`", script_doc)
#|            rc, out = run_cli("--config", str(cfg_path), "search", "SalesAggregate")
#|            self.assertIn("submit_sales.sh", out)
#|
#|
#|class TestVersionChange(unittest.TestCase):
#|    def test_registry_version_in_changelog(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp, with_db=False))
#|            build(cfg, log=lambda m: None)
#|            flow = nested_flow()
#|            flow["rootGroup"]["processGroups"][0]["versionedFlowCoordinates"]["version"] = 4
#|            with gzip.open(Path(tmp) / "flow.json.gz", "wt", encoding="utf-8") as f:
#|                json.dump(flow, f)
#|            build(cfg, log=lambda m: None)
#|            log = (Path(cfg["output"]["dir"]) / "CHANGELOG.md").read_text(encoding="utf-8")
#|            self.assertIn("process group NiFi Flow / Vendor JSON Ingestion: registry version 3 → 4", log)
#|
#|
#|class TestCompare(unittest.TestCase):
#|    """Environment comparison: flow (components, properties, parameters) and config rows, 'works in UAT, fails in PROD'."""
#|
#|    def test_compare_env(self):
#|        from fixtures_builder import metadata_flow, proc
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            # UAT: a copy of the config db with a changed delimiter, a changed structure row and a secret change
#|            shutil.copy(Path(tmp) / "meta.db", Path(tmp) / "uat.db")
#|            db = sqlite3.connect(Path(tmp) / "uat.db")
#|            db.executescript("UPDATE OBJ_DEFINITION SET DELIMITER = '|' WHERE OBJ_ID = 1;"
#|                             "UPDATE OBJ_STRUCTURE SET COL_LENGTH = 80 WHERE OBJ_ID = 1 AND COL_NAME = 'CUST_NAME';"
#|                             "UPDATE SOURCE_FEED_CONFIG SET SFTP_PASSWORD = 'OtherSecret1!';"
#|                             "UPDATE OBJ_DEFINITION SET ACTIVE_FLAG = 'N' WHERE OBJ_ID = 3;")
#|            db.commit()
#|            db.close()
#|            # UAT flow: another bucket parameter, a changed property, a stopped processor, one extra processor
#|            flow = metadata_flow()
#|            flow["parameterContexts"][0]["parameters"][0]["value"] = "acme-orders-uat"
#|            flow["rootGroup"]["processGroups"][0]["processors"][0]["properties"]["vendor"] = "$.vendorName"
#|            flow["rootGroup"]["processors"][-1]["scheduledState"] = "DISABLED"
#|            flow["rootGroup"]["processors"].append(proc("p-extra", "Debug log", "org.apache.nifi.processors.standard.LogAttribute", {}))
#|            with gzip.open(Path(tmp) / "uat.json.gz", "wt", encoding="utf-8") as f:
#|                json.dump(flow, f)
#|            with open(cfg_path, "a", encoding="utf-8") as f:
#|                f.write(f'\n[[databases]]\nname = "metadata_uat"\nkind = "sqlite"\ndatabase = "{(Path(tmp) / "uat.db").as_posix()}"\n'
#|                        f'\n[environments.uat]\nflow_file = "uat.json.gz"\ndb = "metadata_uat"\n')
#|            build(load_config(cfg_path), log=lambda m: None)
#|            rc, out = run_cli("--config", str(cfg_path), "compare", "--env", "uat")
#|            self.assertEqual(rc, 0, out)
#|            self.assertIn("only in uat: NiFi Flow :: Debug log [LogAttribute]", out)
#|            self.assertIn("'vendor' = `$.vendor` (here) vs `$.vendorName` (uat)", out)
#|            self.assertIn("parameter vendor-params :: s3.bucket = `acme-orders-raw` (here) vs `acme-orders-uat` (uat)", out)
#|            self.assertIn("Metadata lookup [MetadataLookup]: state RUNNING (here) vs DISABLED (uat)", out)
#|            self.assertIn("DELIMITER , → |", out)
#|            self.assertIn("COL_LENGTH 50 → 80", out)
#|            self.assertNotIn("OtherSecret1!", out)
#|            self.assertNotIn("Sup3rS3cret!", out)
#|            self.assertNotIn("SFTP_PASSWORD", out)
#|            # one definition only
#|            rc, out = run_cli("--config", str(cfg_path), "compare", "--env", "uat", "--what", "config", "--key", "SALES_20260926.csv")
#|            self.assertIn("DELIMITER , → |", out)
#|            self.assertNotIn("ACTIVE_FLAG", out)
#|            self.assertNotIn("## Flow", out)
#|            rc, out = run_cli("--config", str(cfg_path), "compare", "--env", "prod")
#|            self.assertEqual(rc, 2)
#|            self.assertIn("no [environments.prod]", out)
#|
#|
#|class TestOnboard(unittest.TestCase):
#|    """New-feed validator: proposed config rows checked before anyone inserts them."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def write(self, name, text):
#|        path = Path(self.tmp) / name
#|        path.write_text(text, encoding="utf-8")
#|        return path
#|
#|    def test_good_proposal(self):
#|        self.write("CUSTOMERS_EXTRA_20260927.csv", "CUST_ID,NAME,EMAIL\n1,Ann,ann@example.com\n")
#|        path = self.write("good.toml", """
#|example_file = "CUSTOMERS_EXTRA_20260927.csv"
#|sample = "CUSTOMERS_EXTRA_20260927.csv"
#|[definition]
#|OBJ_ID = 7
#|FILE_NAME = "CUSTOMERS_EXTRA_YYYYMMDD.csv"
#|TABLE_NAME = "stg_customers"
#|SOURCE_SYSTEM = "CRM"
#|DELIMITER = ","
#|ACTIVE_FLAG = "Y"
#|[[structure]]
#|COL_NAME = "CUST_ID"
#|DATA_TYPE = "INT"
#|COL_SEQ = 1
#|MANDATORY_FLAG = "Y"
#|[[structure]]
#|COL_NAME = "NAME"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 2
#|COL_LENGTH = 100
#|[[structure]]
#|COL_NAME = "EMAIL"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 3
#|COL_LENGTH = 200
#|""")
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path))
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("READY to insert", out)
#|        self.assertIn("INSERT INTO OBJ_DEFINITION (OBJ_ID, FILE_NAME, TABLE_NAME, SOURCE_SYSTEM, DELIMITER, ACTIVE_FLAG) "
#|                      "VALUES (7, 'CUSTOMERS_EXTRA_YYYYMMDD.csv', 'stg_customers', 'CRM', ',', 'Y');", out)
#|        self.assertIn("INSERT INTO OBJ_STRUCTURE (COL_NAME, DATA_TYPE, COL_SEQ, MANDATORY_FLAG, OBJ_ID) VALUES ('CUST_ID', 'INT', 1, 'Y', 7);", out)
#|
#|    def test_bad_proposal(self):
#|        self.write("SALES_20260927.csv", "ORDER_NO;CUST_NAME;AMOUNT\n1;Bob;3.5\n")
#|        path = self.write("bad.toml", """
#|example_file = "SALES_20260927.csv"
#|sample = "SALES_20260927.csv"
#|like = "SALES_YYYYMMDD.csv"
#|[definition]
#|OBJ_ID = 1
#|FILE_NAME = "SALES_YYYYMMDD.csv"
#|TABEL_NAME = "stg_sales"
#|[[structure]]
#|COL_NAME = "ORDER_NO"
#|DATA_TYPE = "INTEGER"
#|COL_SEQ = 1
#|[[structure]]
#|COL_NAME = "CUST_NAME"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 1
#|[[structure]]
#|COL_NAME = "AMOUNT"
#|DATA_TYPE = "MONEYZ"
#|COL_SEQ = "three"
#|[[rows.SOURCE_FEED_CONFIG]]
#|FEED_NAME = "pos_sales_feed_2"
#|SFTP_PASSWORD = "TopSecret123!"
#|""")
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path))
#|        self.assertEqual(rc, 1, out)
#|        self.assertIn("error(s) to fix first", out)
#|        self.assertIn("definition: OBJ_DEFINITION has no column 'TABEL_NAME' (did you mean 'TABLE_NAME'?)", out)
#|        self.assertIn("definition: OBJ_DEFINITION:1 already exists", out)
#|        self.assertIn("duplicate COL_SEQ value(s): [1]", out)
#|        self.assertIn("COL_SEQ = 'three' is not an integer", out)
#|        self.assertIn("'CUST_NAME' is VARCHAR without a length", out)
#|        self.assertIn("type 'MONEYZ' is not a usual type name", out)
#|        self.assertIn("SFTP_PASSWORD holds a secret", out)
#|        self.assertIn("SOURCE_SYSTEM, DELIMITER, ACTIVE_FLAG - the proposal leaves them empty", out)
#|        self.assertIn("fill COL_LENGTH, MANDATORY_FLAG - the proposal does not", out)
#|        self.assertNotIn("TopSecret123!", out)
#|        self.assertIn("/* set by DBA */ NULL", out)
#|        self.assertIn("sample:", out)
#|
#|    def test_ambiguous_and_pattern(self):
#|        path = self.write("amb.json", json.dumps({"example_file": "SALES_20260927.csv",
#|                                                  "definition": {"FILE_NAME": "SALES_*.csv", "TABLE_NAME": "stg_sales"},
#|                                                  "structure": [{"COL_NAME": "ORDER_NO", "DATA_TYPE": "INTEGER", "COL_SEQ": 1}]}))
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path))
#|        self.assertIn("already matches existing OBJ_DEFINITION row(s) OBJ_DEFINITION:1", out)
#|        self.assertIn("the definition id is not given", out)
#|        self.assertNotIn("duplicate-name", out)  # the target table may be shared
#|        self.assertIn("/* new id */ NULL", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "onboard", str(path), "--example", "INVOICE_20260927.csv")
#|        self.assertIn("does not match the example file 'INVOICE_20260927.csv'", out)
#|
#|    def test_mcp_inline(self):
#|        from nifikb.mcp import Server
#|        text, err = Server(str(self.cfg_path)).call("check_new_feed", {"proposal": {
#|            "definition": {"OBJ_ID": 8, "FILE_NAME": "x_YYYYMMDD.csv", "TABLE_NAME": "stg_nothere"},
#|            "structure": [{"COL_NAME": "A", "DATA_TYPE": "INT", "COL_SEQ": 1}]}})
#|        self.assertIn("target stg_nothere", text)
#|
#|
#|FAKE_AWS = r'''
#|import json, os, sys, datetime
#|root = os.environ["FAKE_S3_ROOT"]
#|a = sys.argv[1:]
#|def opt(n):
#|    return a[a.index(n) + 1] if n in a else None
#|bucket = opt("--bucket")
#|if a[:2] == ["s3api", "list-objects-v2"]:
#|    out = []
#|    base = os.path.join(root, bucket)
#|    for d, _, files in os.walk(base):
#|        for f in files:
#|            p = os.path.join(d, f)
#|            key = os.path.relpath(p, base).replace(os.sep, "/")
#|            if key.startswith(opt("--prefix") or ""):
#|                out.append({"Key": key, "Size": os.path.getsize(p),
#|                            "LastModified": datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).isoformat()})
#|    print(json.dumps({"Contents": out}))
#|elif a[:2] == ["s3api", "get-object"]:
#|    lo, hi = opt("--range").split("=")[1].split("-")
#|    with open(os.path.join(root, bucket, opt("--key")), "rb") as f:
#|        f.seek(int(lo))
#|        data = f.read(int(hi) - int(lo) + 1)
#|    open(a[-1] if not a[-1].startswith("--") else a[a.index("--range") + 2], "wb").write(data)
#|    print("{}")
#|else:
#|    sys.exit(2)
#|'''
#|
#|
#|class TestTarget(unittest.TestCase):
#|    """Target side of a load: HDFS / S3 / local listings, the Parquet footer schema vs the structure rows."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        lake = Path(cls.tmp) / "lake" / "stg_sales" / "dt=2026-09-26"
#|        lake.mkdir(parents=True)
#|        shutil.copy(FIXTURES / "stg_sales.parquet", lake / "SALES_20260926.parquet")
#|        (lake / "_SUCCESS").write_bytes(b"")
#|        db = sqlite3.connect(Path(cls.tmp) / "meta.db")
#|        db.execute("ALTER TABLE OBJ_DEFINITION ADD COLUMN HDFS_PATH TEXT")
#|        db.execute("UPDATE OBJ_DEFINITION SET HDFS_PATH = ? WHERE OBJ_ID = 1",
#|                   ((Path(cls.tmp) / "lake" / "stg_sales").as_posix() + "/dt=${now():format('yyyy-MM-dd')}/",))
#|        db.commit()
#|        db.close()
#|        with open(cls.cfg_path, "a", encoding="utf-8") as f:
#|            f.write("\n[targets]\n")
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_parquet_footer(self):
#|        from nifikb.target import parquet_schema
#|        cols, info = parquet_schema((FIXTURES / "stg_sales.parquet").read_bytes())
#|        self.assertEqual([(c["name"], c["type"]) for c in cols],
#|                         [("ORDER_NO", "BIGINT"), ("CUST_NAME", "STRING"), ("AMOUNT", "DECIMAL(10,2)"), ("ORDER_DT", "STRING"), ("LOAD_TS", "STRING")])
#|        self.assertEqual(info["rows"], 2)
#|
#|    def test_local_target_and_investigate(self):
#|        rc, out = run_cli("--config", str(self.cfg_path), "target", "--file", "SALES_20260926.csv")
#|        self.assertEqual(rc, 1, out)  # REGION was not written
#|        self.assertIn("structure field(s) not in the written Parquet (SALES_20260926.parquet): REGION", out)
#|        self.assertIn("'ORDER_DT' is DATE in the structure but STRING in the Parquet", out)
#|        self.assertIn("Parquet has column(s) not in the structure (often load metadata): LOAD_TS", out)
#|        self.assertIn("outputs for this file (1 found)", out)
#|        self.assertNotIn("_SUCCESS", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "investigate", "--file", "SALES_20260926.csv")
#|        self.assertIn("SALES_YYYYMMDD.csv target: structure field(s) not in the written Parquet", out)
#|        self.assertIn("## Target output (SALES_YYYYMMDD.csv)", out)
#|        rc, out = run_cli("--config", str(self.cfg_path), "target", "--location", str(Path(self.tmp) / "lake" / "nothing"))
#|        self.assertIn("does not exist", out)
#|
#|    def test_webhdfs(self):
#|        import http.server
#|        import threading
#|        import urllib.parse as up
#|        base = Path(self.tmp) / "lake"
#|
#|        class H(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def do_GET(self):
#|                u = up.urlparse(self.path)
#|                q = dict(up.parse_qsl(u.query))
#|                p = base / up.unquote(u.path).removeprefix("/webhdfs/v1/lake/").strip("/")
#|                if not p.exists():
#|                    self.send_response(404)
#|                    self.end_headers()
#|                    self.wfile.write(b'{"RemoteException":{"exception":"FileNotFoundException"}}')
#|                    return
#|                if q["op"] == "LISTSTATUS":
#|                    st = [{"pathSuffix": c.name, "type": "DIRECTORY" if c.is_dir() else "FILE", "length": 0 if c.is_dir() else c.stat().st_size,
#|                           "modificationTime": int(c.stat().st_mtime * 1000)} for c in p.iterdir()]
#|                    body = json.dumps({"FileStatuses": {"FileStatus": st}}).encode()
#|                else:
#|                    data = p.read_bytes()
#|                    off = int(q.get("offset", 0))
#|                    body = data[off:off + int(q.get("length", len(data)))]
#|                self.send_response(200)
#|                self.end_headers()
#|                self.wfile.write(body)
#|
#|        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
#|        threading.Thread(target=srv.serve_forever, daemon=True).start()
#|        try:
#|            cfg = self.cfg_path.read_text(encoding="utf-8").replace("\n[targets]\n", f'\n[targets]\nhdfs_url = "http://127.0.0.1:{srv.server_port}/webhdfs/v1"\nhdfs_user = "nifikb"\n')
#|            path = Path(self.tmp) / "webhdfs.toml"
#|            path.write_text(cfg, encoding="utf-8")
#|            rc, out = run_cli("--config", str(path), "target", "--location", "hdfs://nameservice1/lake/stg_sales/", "--key", "SALES_20260926.csv")
#|            self.assertIn("via webhdfs", out)
#|            self.assertIn("SALES_20260926.parquet", out)
#|            self.assertIn("not in the written Parquet (SALES_20260926.parquet): REGION", out)
#|            rc, out = run_cli("--config", str(path), "target", "--location", "hdfs:///lake/missing/")
#|            self.assertIn("does not exist in HDFS", out)
#|        finally:
#|            srv.shutdown()
#|
#|    def test_s3_cli(self):
#|        s3 = Path(self.tmp) / "s3" / "datalake" / "raw" / "stg_sales"
#|        s3.mkdir(parents=True)
#|        shutil.copy(FIXTURES / "stg_sales.parquet", s3 / "part-0000.parquet")
#|        fake = Path(self.tmp) / "fake_aws.py"
#|        fake.write_text(FAKE_AWS, encoding="utf-8")
#|        cfg = self.cfg_path.read_text(encoding="utf-8").replace(
#|            "\n[targets]\n", f'\n[targets]\ns3_cli = {json.dumps([sys.executable, str(fake)])}\nlocation_template = "s3://datalake/raw/{{table_lower}}/"\n')
#|        path = Path(self.tmp) / "s3.toml"
#|        path.write_text(cfg, encoding="utf-8")
#|        os.environ["FAKE_S3_ROOT"] = str(Path(self.tmp) / "s3")
#|        try:
#|            # OBJ_DEFINITION 3 (returns.csv) has no location column value: the template gives s3://datalake/raw/stg_returns/
#|            rc, out = run_cli("--config", str(path), "target", "--key", "returns.csv")
#|            self.assertIn("s3://datalake/raw/stg_returns/", out)
#|            self.assertIn("no data files under", out)
#|            rc, out = run_cli("--config", str(path), "target", "--location", "s3://datalake/raw/stg_sales/", "--key", "SALES_20260926.csv")
#|            self.assertIn("via s3", out)
#|            self.assertIn("s3://datalake/raw/stg_sales/part-0000.parquet", out)
#|            self.assertIn("REGION", out)
#|        finally:
#|            os.environ.pop("FAKE_S3_ROOT", None)
#|
#|
#|class TestTickets(unittest.TestCase):
#|    """Jira / ServiceNow: extract facts, investigate, draft a reply; post only with --post."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        import http.server
#|        import threading
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        build(load_config(cls.cfg_path), log=lambda m: None)
#|        cls.posted, cls.auth = [], []
#|        test = cls
#|
#|        class H(http.server.BaseHTTPRequestHandler):
#|            def log_message(self, *a):
#|                pass
#|
#|            def reply(self, obj, raw=None):
#|                body = raw if raw is not None else json.dumps(obj).encode()
#|                self.send_response(200)
#|                self.send_header("Content-Type", "application/json")
#|                self.end_headers()
#|                self.wfile.write(body)
#|
#|            def do_GET(self):
#|                test.auth.append(self.headers.get("Authorization"))
#|                port = self.server.server_port
#|                if self.path.startswith("/rest/api/2/issue/NIFI-7"):
#|                    return self.reply({"key": "NIFI-7", "fields": {
#|                        "summary": "SALES_20260926.csv not loaded", "status": {"name": "Open"},
#|                        "description": "The POS file SALES_20260926.csv failed last night.\nError: Column count mismatch at line 12: "
#|                                       "expected 5, found 6\nHeaders sent: ORDER_NO, CUST_NAME, AMOUNT, ORDER_DT, REGION, EXTRA_COL\n"
#|                                       "Reach me at bob@acme.com",
#|                        "comment": {"comments": [{"body": "still failing today"}]},
#|                        "attachment": [{"filename": "SALES_20260926.csv", "size": 60,
#|                                        "content": f"http://127.0.0.1:{port}/secure/attachment/1/SALES_20260926.csv"},
#|                                       {"filename": "screenshot.png", "size": 10, "content": f"http://127.0.0.1:{port}/x.png"}]}})
#|                if self.path.startswith("/secure/attachment/1/"):
#|                    return self.reply(None, raw=b"ORDER_NO,CUST_NAME,AMOUNT,ORDER_DT,REGION,EXTRA_COL\n1,a,2.5,2026-09-26,EU,x\n")
#|                if self.path.startswith("/api/now/table/incident?"):
#|                    return self.reply({"result": [{"sys_id": "abc123", "number": "INC0010001", "short_description": "POS feed stuck",
#|                                                   "description": "Nothing arrived from pos_sales_feed since Monday", "state": "New"}]})
#|                if self.path.startswith("/api/now/attachment?"):
#|                    return self.reply({"result": []})
#|                self.send_response(404)
#|                self.end_headers()
#|
#|            def do_POST(self):
#|                test.posted.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
#|                self.reply({"id": "1"})
#|
#|            do_PATCH = do_POST
#|
#|        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
#|        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
#|        base = cls.cfg_path.read_text(encoding="utf-8")
#|        cls.jira = Path(cls.tmp) / "jira.toml"
#|        cls.jira.write_text(base + f'\n[tickets]\nkind = "jira"\nurl = "http://127.0.0.1:{cls.srv.server_port}"\n'
#|                                   'username = "bot@acme.com"\ntoken_env = "NIFIKB_TEST_TICKET_TOKEN"\n', encoding="utf-8")
#|        cls.snow = Path(cls.tmp) / "snow.toml"
#|        cls.snow.write_text(base + f'\n[tickets]\nkind = "servicenow"\nurl = "http://127.0.0.1:{cls.srv.server_port}"\n'
#|                                   'username = "nifikb"\npassword_env = "NIFIKB_TEST_TICKET_TOKEN"\n', encoding="utf-8")
#|        os.environ["NIFIKB_TEST_TICKET_TOKEN"] = "tok-123"
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        cls.srv.shutdown()
#|        cls.srv.server_close()
#|        os.environ.pop("NIFIKB_TEST_TICKET_TOKEN", None)
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def test_extract(self):
#|        from nifikb import tickets
#|        facts = tickets.extract({"title": "load failed", "description": "file ORDERS_1.json and orders.csv\nfields: a | b | c\n"
#|                                 "java.sql.SQLException: Data too long for column 'x'"})
#|        self.assertEqual(facts["files"], ["ORDERS_1.json", "orders.csv"])
#|        self.assertEqual(facts["headers"], ["a", "b", "c"])
#|        self.assertIn("Data too long", facts["error"])
#|
#|    def test_jira_investigate_and_draft(self):
#|        self.posted.clear()
#|        rc, out = run_cli("--config", str(self.jira), "ticket", "NIFI-7")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("files=['SALES_20260926.csv']", out)
#|        self.assertIn("sample attachment=SALES_20260926.csv", out)
#|        self.assertIn("load audit: last load FAILED", out)
#|        self.assertIn("EXTRA_COL", out)
#|        self.assertIn("## Draft reply (not posted", out)
#|        self.assertNotIn("bob@acme.com", out.split("## Draft reply")[1])
#|        self.assertEqual(self.posted, [])
#|        self.assertTrue(any(a and a.startswith("Basic ") for a in self.auth))
#|        rc, out = run_cli("--config", str(self.jira), "ticket", "NIFI-7", "--post", "--no-attachments")
#|        self.assertIn("posted to NIFI-7", out)
#|        self.assertEqual(self.posted[0][0], "/rest/api/2/issue/NIFI-7/comment")
#|        self.assertIn("Automated first analysis (nifikb) for NIFI-7", self.posted[0][1]["body"])
#|
#|    def test_servicenow_feed(self):
#|        self.posted.clear()
#|        rc, out = run_cli("--config", str(self.snow), "ticket", "INC0010001")
#|        self.assertEqual(rc, 0, out)
#|        self.assertIn("feeds=['pos_sales_feed']", out)
#|        self.assertIn("# Investigation: pos_sales_feed", out)
#|        rc, out = run_cli("--config", str(self.snow), "ticket", "INC0010001", "--post")
#|        self.assertEqual(self.posted[0][0], "/api/now/table/incident/abc123")
#|        self.assertIn("work_notes", self.posted[0][1])
#|        rc, out = run_cli("--config", str(self.snow), "ticket", "not a number")
#|        self.assertIn("does not look like a ServiceNow number", out)
#|
#|    def test_mcp_never_posts(self):
#|        from nifikb.mcp import TOOLS
#|        schema = next(t for t in TOOLS if t["name"] == "ticket")["inputSchema"]["properties"]
#|        self.assertNotIn("post", schema)
#|        rc, out = run_cli("--config", str(self.jira), "doctor", "--offline")
#|        self.assertIn("(posting only with `ticket <id> --post`)", out)
#|
#|
#|class TestLateFiles(unittest.TestCase):
#|    """Arrival patterns learned from the load audit: intra-day, daily (weekdays + time of day), weekly."""
#|
#|    def rows(self, times, link=None, name="F_{:%Y%m%d%H%M}.csv", failed=()):
#|        return [{"file": name.format(t), "when": t, "failed": t in failed, "link": link} for t in times]
#|
#|    def test_patterns(self):
#|        import datetime as dt
#|        from nifikb import late
#|        now = dt.datetime(2026, 9, 28, 9, 30)  # a Monday
#|        start = now - dt.timedelta(days=30)
#|        daily = [dt.datetime.combine((start + dt.timedelta(days=i)).date(), dt.time(2, 10 + i % 7)) for i in range(30)]
#|        daily = [d for d in daily if d.weekday() < 5 and d.date() < now.date()]
#|        hourly = [now - dt.timedelta(hours=6 + i) for i in range(48)][::-1]
#|        weekly = [now - dt.timedelta(days=12 + 7 * i) for i in range(5)][::-1]
#|        fine = [now - dt.timedelta(minutes=15 * i) for i in range(1, 60)][::-1]
#|        fail = [dt.datetime.combine(now.date(), dt.time(2, 15))]
#|        rows = (self.rows(daily, link=1) + self.rows(fail, link=1, failed=fail) + self.rows(hourly, link=2)
#|                + self.rows(weekly, link=3) + self.rows(fine, link=4))
#|        items = late.analyse(rows, now=now, labels={"1": "SALES_YYYYMMDD.csv", "2": "orders_api", "3": "returns.csv"})
#|        by = {i["label"]: i for i in items}
#|        self.assertEqual(set(by), {"SALES_YYYYMMDD.csv", "orders_api", "returns.csv"})
#|        self.assertIn("today's file not loaded - usually by 02:1", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("on Mon-Fri", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("the latest attempt", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("FAILED", by["SALES_YYYYMMDD.csv"]["message"])
#|        self.assertIn("usually every 1.0 h", by["orders_api"]["message"])
#|        self.assertIn("usually every 7.0 days", by["returns.csv"]["message"])
#|        # a Saturday: the Mon-Fri feed is not expected
#|        sat = dt.datetime(2026, 9, 26, 9, 30)
#|        rows_sat = self.rows([d for d in daily if d < sat], link=1)
#|        self.assertEqual(late.analyse(rows_sat, now=sat), [])
#|        # before the usual time + tolerance: not late yet
#|        early = dt.datetime(2026, 9, 28, 2, 30)
#|        self.assertEqual(late.analyse(self.rows(daily, link=1), now=early), [])
#|
#|    def test_cli_and_report(self):
#|        import datetime as dt
#|        from fixtures_builder import metadata_flow
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            now = dt.datetime.now()
#|            for i in range(60):
#|                t = now - dt.timedelta(hours=5, minutes=30 * i)
#|                db.execute("INSERT INTO FILE_LOAD_AUDIT(OBJ_ID, FILE_NAME, LOAD_STATUS, LOAD_TS, ROW_COUNT) VALUES (3, ?, 'SUCCESS', ?, 10)",
#|                           (f"returns_{t:%H%M}.csv", t.strftime("%Y-%m-%d %H:%M:%S")))
#|            db.commit()
#|            db.close()
#|            build(load_config(cfg_path), log=lambda m: None)
#|            rc, out = run_cli("--config", str(cfg_path), "late")
#|            self.assertEqual(rc, 1, out)
#|            self.assertIn("**returns.csv**: no file for 5.", out)
#|            self.assertIn("usually every 30 min", out)
#|            rc, md = run_cli("--config", str(cfg_path), "report")
#|            self.assertIn("## Late / missing files", md)
#|            self.assertIn("**returns.csv**", md)
#|
#|
#|class TestLearningSuggestions(unittest.TestCase):
#|    """Recurring causes across investigations that no learning covers yet."""
#|
#|    def test_suggest_until_written_down(self):
#|        from fixtures_builder import metadata_flow
#|        from nifikb.investigate import signature
#|        self.assertEqual(signature("FlowFile 1a2b3c4d DROPPED at 'Put' on 2026-09-26 02:14:00 after 3 retries"),
#|                         "FlowFile # DROPPED at '…' on # after # retries")
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp, flow=metadata_flow(), with_metadata=True)
#|            build(load_config(cfg_path), log=lambda m: None)
#|            cli_ = lambda *a: run_cli("--config", str(cfg_path), *a)
#|            rc, out = cli_("learn", "suggest")
#|            self.assertIn("no recurring", out)
#|            for day in ("20260926", "20260927", "20260928"):
#|                cli_("investigate", "--file", f"SALES_{day}.csv")
#|            rc, out = cli_("learn", "suggest")
#|            self.assertIn("seen 3x (SALES_20260926.csv, SALES_20260927.csv, SALES_20260928.csv", out)
#|            self.assertIn("NOT NULL column(s) of stg_sales not in the structure: load_ts", out)
#|            rc, md = cli_("report")
#|            self.assertIn("## Suggested learnings", md)
#|            from nifikb.mcp import Server
#|            text, _ = Server(str(cfg_path)).call("kb_overview", {})
#|            self.assertIn("# Recurring causes with no learning yet", text)
#|            # once it is written down, it is no longer suggested
#|            cli_("learn", "add", "--title", "stg_sales needs load_ts from the flow", "--kind", "gotcha", "--applies-to", "SALES_*.csv,stg_sales",
#|                 "--body", "## Cause\nload_ts is NOT NULL in stg_sales and set by the flow, not the file.\n## Fix\nnone needed")
#|            rc, out = cli_("learn", "suggest")
#|            self.assertNotIn("load_ts", out)
#|
#|
#|class TestLearnings(unittest.TestCase):
#|    """Team learnings written by people / agents: redaction, relevance, search, diagnose, MCP, doctor."""
#|
#|    @classmethod
#|    def setUpClass(cls):
#|        from fixtures_builder import metadata_flow
#|        cls.tmp = tempfile.mkdtemp()
#|        cls.cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_metadata=True)
#|        cls.cfg = load_config(cls.cfg_path)
#|        build(cls.cfg, log=lambda m: None)
#|
#|    @classmethod
#|    def tearDownClass(cls):
#|        shutil.rmtree(cls.tmp, ignore_errors=True)
#|
#|    def cli(self, *argv):
#|        return run_cli("--config", str(self.cfg_path), *argv)
#|
#|    def test_add_redact_find_retire(self):
#|        rc, out = self.cli("learn", "add", "--title", "SALES feed switches to pipe delimiter at month end", "--kind", "pattern",
#|                           "--tags", "delimiter,Sales", "--applies-to", "SALES_*.csv,stg_sales", "--ticket", "INC1001",
#|                           "--body", "## Cause\nVendor exports with | on month end. SFTP password=Hunter2Secret! and Bearer abcdefghijklmnopqrstu\n"
#|                                     "## Fix\nAsk vendor; or set OBJ_DEFINITION.DELIMITER per run.")
#|        self.assertEqual(rc, 0, out)
#|        path = Path(out.split("saved ", 1)[1].splitlines()[0].strip())
#|        text = path.read_text(encoding="utf-8")
#|        self.assertNotIn("Hunter2Secret!", text)
#|        self.assertNotIn("abcdefghijklmnopqrstu", text)
#|        self.assertIn("applies_to: [SALES_*.csv, stg_sales]", text)
#|        self.assertIn("tags: [delimiter, sales]", text)
#|        # immediately searchable, without a rebuild
#|        rc, out = self.cli("search", "pipe", "delimiter")
#|        self.assertIn("[learning]", out)
#|        # relevant by file-name pattern
#|        rc, out = self.cli("learn", "for", "SALES_20260926.csv")
#|        self.assertIn("pipe delimiter", out)
#|        # diagnose shows it
#|        rc, out = self.cli("diagnose", "--file", "SALES_20260926.csv")
#|        self.assertIn("Team learnings that may apply", out)
#|        self.assertIn("SALES feed switches to pipe delimiter", out)
#|        # near-duplicate warning
#|        rc, out = self.cli("learn", "add", "--title", "Sales feed switches to pipe delimiter at month end again", "--body", "same")
#|        self.assertIn("similar learning exists", out)
#|        # retire hides it from relevance but keeps the file
#|        ident = path.stem
#|        rc, out = self.cli("learn", "retire", ident, "--reason", "vendor fixed their export")
#|        self.assertEqual(rc, 0, out)
#|        rc, out = self.cli("learn", "for", "stg_sales")
#|        self.assertNotIn(ident, out)
#|        rc, out = self.cli("learn", "list", "--all")
#|        self.assertIn("OBSOLETE", out)
#|        self.assertIn("vendor fixed their export", path.read_text(encoding="utf-8"))
#|
#|    def test_rejects_bad_input(self):
#|        rc, out = self.cli("learn", "add", "--title", "no body", "--body", "  ")
#|        self.assertEqual(rc, 1)
#|        rc, out = self.cli("learn", "add", "--title", "x", "--body", "y" * 30000)
#|        self.assertIn("keep a learning under", out)
#|
#|    def test_hand_written_file_is_indexed_on_build(self):
#|        d = Path(self.cfg["knowledge"]["dir"]) / "learnings"
#|        d.mkdir(parents=True, exist_ok=True)
#|        (d / "manual-note.md").write_text("---\ntitle: Customers API returns 206 during vendor maintenance\nkind: gotcha\n"
#|                                          "applies_to: [crm_customers_api]\n---\nRetry after 02:00.\n", encoding="utf-8")
#|        build(self.cfg, log=lambda m: None)
#|        rc, out = self.cli("search", "vendor", "maintenance")
#|        self.assertIn("Customers API returns 206", out)
#|        rc, out = self.cli("diagnose", "--feed", "crm_customers_api")
#|        self.assertIn("manual-note", out)
#|        self.assertIn("active learning(s)", (Path(self.cfg["output"]["dir"]) / "INDEX.md").read_text(encoding="utf-8"))
#|
#|    def test_mcp_learning_tools(self):
#|        from nifikb.mcp import Server
#|        s = Server(str(self.cfg_path))
#|        text, err = s.call("add_learning", {"title": "Returns file lands in wrong folder after DST change",
#|                                            "body": "## Symptom\nnothing picked up\n## Fix\nuse UTC in the ListSFTP filter",
#|                                            "kind": "gotcha", "applies_to": ["returns.csv"], "author": "gemini"})
#|        self.assertFalse(err, text)
#|        ident = text.split()[1]
#|        text, err = s.call("find_learnings", {"terms": ["returns.csv"]})
#|        self.assertIn(ident, text)
#|        text, err = s.call("get_learning", {"id": ident})
#|        self.assertIn("use UTC", text)
#|        self.assertIn("by gemini", text)
#|        text, err = s.call("kb_overview", {})
#|        self.assertIn("Recent team learnings", text)
#|        self.assertIn(ident, text)
#|        text, err = s.call("add_learning", {"title": "", "body": "x"})
#|        self.assertTrue(err)
#|
#|    def test_doctor(self):
#|        rc, out = self.cli("doctor")
#|        self.assertIn("[OK  ] database metadata: sqlite connected", out)
#|        self.assertIn("[OK  ] metadata:", out)
#|        self.assertIn("[OK  ] knowledge base: built", out)
#|        self.assertIn("team context", out)
#|        self.assertIn("problem(s)", out)
#|
#|
#|class TestAgentFiles(unittest.TestCase):
#|    """The agent instruction copies must not drift apart; the agent wiring must point at this package."""
#|
#|    def test_instruction_files_identical(self):
#|        root = Path(__file__).resolve().parent.parent
#|        texts = {f: (root / f).read_text(encoding="utf-8").replace("\r\n", "\n") for f in ("CLAUDE.md", "GEMINI.md", "AGENTS.md")}
#|        self.assertEqual(len(set(texts.values())), 1, "CLAUDE.md, GEMINI.md and AGENTS.md differ - copy the edited one over the others")
#|        text = texts["CLAUDE.md"]
#|        from nifikb.mcp import TOOLS
#|        for tool in [t["name"] for t in TOOLS]:  # every MCP tool is documented for the agents
#|            self.assertIn(f"`{tool}`", text)
#|
#|    def test_package_is_clean(self):
#|        import importlib.util
#|        root = Path(__file__).resolve().parent.parent
#|        spec = importlib.util.spec_from_file_location("package", root / "ops" / "package.py")
#|        mod = importlib.util.module_from_spec(spec)
#|        spec.loader.exec_module(mod)
#|        with tempfile.TemporaryDirectory() as tmp:
#|            target, _ = mod.package(tmp)
#|            import zipfile
#|            with zipfile.ZipFile(target) as z:
#|                names = z.namelist()
#|                config = z.read("nifi-kb/nifikb.toml").decode("utf-8")
#|        self.assertFalse([n for n in names if "/kb/" in n or "__pycache__" in n or n.endswith((".log", ".sqlite"))])
#|        for must in ("nifi-kb/nifikb/cli.py", "nifi-kb/CLAUDE.md", "nifi-kb/GEMINI.md", "nifi-kb/.mcp.json", "nifi-kb/HANDOFF.md",
#|                     "nifi-kb/.claude/commands/triage.md", "nifi-kb/.gemini/commands/triage.toml", "nifi-kb/knowledge/README.md"):
#|            self.assertIn(must, names)
#|        self.assertIn('home = "C:/path/to/nifi"', config)  # fresh template, not this machine's config
#|        self.assertNotIn("testdb", config)
#|
#|    def test_paste_bundle(self):
#|        """ops/bundle.py: one text file per part, survives CRLF / trimmed blanks / BOM, detects cut-off and damaged pastes."""
#|        import importlib.util
#|        import subprocess
#|        root = Path(__file__).resolve().parent.parent
#|        sys.path.insert(0, str(root / "ops"))
#|        spec = importlib.util.spec_from_file_location("bundle", root / "ops" / "bundle.py")
#|        mod = importlib.util.module_from_spec(spec)
#|        spec.loader.exec_module(mod)
#|        from package import collect
#|        with tempfile.TemporaryDirectory() as tmp:
#|            parts = mod.bundle(Path(tmp) / "b", max_kb=300)
#|            self.assertGreater(len(parts), 1)
#|            out = Path(tmp) / "out"
#|            for path, _ in parts:  # a messy paste: Windows line endings, trailing blanks trimmed, a BOM
#|                text = path.read_text(encoding="utf-8")
#|                messy = "﻿" + "\r\n".join(line.rstrip() for line in text.split("\n"))
#|                path.write_text(messy, encoding="utf-8", newline="")
#|                r = subprocess.run([sys.executable, str(path), str(out)], capture_output=True, text=True)
#|                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
#|            expected = dict(collect(sandbox_config=False))
#|            self.assertNotIn("nifikb.toml.sandbox", expected)
#|            for rel, data in expected.items():
#|                got = (out / rel).read_bytes()
#|                if rel.endswith((".gz", ".parquet")):
#|                    self.assertEqual(got, data, rel)  # binary: exact
#|                else:  # text: equal up to trailing blanks, which the messy paste removed
#|                    self.assertEqual([x.rstrip() for x in got.decode().splitlines()], [x.rstrip() for x in data.decode().splitlines()], rel)
#|            self.assertEqual((out / "GEMINI.md").read_bytes(), (out / "CLAUDE.md").read_bytes())
#|            # your own config survives a re-unpack (upgrade)
#|            (out / "nifikb.toml").write_text("# mine", encoding="utf-8")
#|            for path, _ in parts:
#|                subprocess.run([sys.executable, str(path), str(out)], capture_output=True, text=True)
#|            self.assertEqual((out / "nifikb.toml").read_text(encoding="utf-8"), "# mine")
#|            # cut off / damaged
#|            text = parts[0][0].read_text(encoding="utf-8")
#|            cut = Path(tmp) / "cut.py"
#|            cut.write_text(text[: len(text) // 2].rsplit("\n", 1)[0] + "\n", encoding="utf-8")
#|            r = subprocess.run([sys.executable, str(cut), str(Path(tmp) / "o2")], capture_output=True, text=True)
#|            self.assertEqual(r.returncode, 2)
#|            self.assertIn("paste was cut off", r.stdout)
#|            lines = text.split("\n")
#|            i = next(n for n, line in enumerate(lines) if line.startswith("#|def "))
#|            lines[i] = lines[i].replace("def ", "dfe ", 1)
#|            bad = Path(tmp) / "bad.py"
#|            bad.write_text("\n".join(lines), encoding="utf-8")
#|            r = subprocess.run([sys.executable, str(bad), str(Path(tmp) / "o3")], capture_output=True, text=True)
#|            self.assertEqual(r.returncode, 1)
#|            self.assertIn("damaged in the paste and NOT written", r.stdout)
#|        sys.path.remove(str(root / "ops"))
#|
#|    def test_mcp_configs(self):
#|        root = Path(__file__).resolve().parent.parent
#|        for f in (".mcp.json", ".gemini/settings.json"):
#|            server = json.loads((root / f).read_text(encoding="utf-8"))["mcpServers"]["nifikb"]
#|            self.assertEqual(server["args"], ["-m", "nifikb", "mcp"])
#|        from nifikb.mcp import TOOLS
#|        self.assertEqual(len({t["name"] for t in TOOLS}), len(TOOLS))
#|
#|
#|class TestDoctorUnits(unittest.TestCase):
#|    def test_grant_scope(self):
#|        from nifikb.doctor import _grant_covers
#|        self.assertTrue(_grant_covers("GRANT SELECT ON `testdb`.* TO `u`@`h`", "testDB"))
#|        self.assertTrue(_grant_covers("GRANT ALL PRIVILEGES ON *.* TO `root`@`h`", "meta"))
#|        self.assertTrue(_grant_covers("GRANT INSERT ON `meta`.`t` TO `u`@`h`", "meta"))
#|        self.assertFalse(_grant_covers(r"GRANT SELECT, INSERT ON `test\_%`.* TO PUBLIC", "testDB"))  # MariaDB default
#|        self.assertFalse(_grant_covers("GRANT SELECT, INSERT ON `other`.* TO `u`@`h`", "meta"))
#|
#|
#|class TestMetadataUnits(unittest.TestCase):
#|    def test_pattern_regex(self):
#|        from nifikb.metadata import pattern_regex
#|        cases = [("SALES_YYYYMMDD.csv", "SALES_20260926.csv", True), ("SALES_YYYYMMDD.csv", "SALES_2026092.csv", False),
#|                 ("SUMMARY_*.txt", "SUMMARY_x.txt", True), ("cust_%.json", "cust_abc.json", True),
#|                 ("inv_\\d{6}\\.dat", "inv_123456.dat", True), ("${prefix}_orders.csv", "eu_orders.csv", True),
#|                 ("DDMMYYYY_feed.csv", "26092026_feed.csv", True)]
#|        for pat, name, ok in cases:
#|            self.assertEqual(bool(pattern_regex(pat).match(name)), ok, (pat, name))
#|        self.assertIsNone(pattern_regex("plain.csv"))
#|
#|    def test_type_family(self):
#|        from nifikb.metadata import type_family
#|        self.assertEqual(type_family("NUMBER(10)"), "numeric")
#|        self.assertEqual(type_family("varchar2(20)"), "string")
#|        self.assertEqual(type_family("datetime"), "temporal")
#|        self.assertEqual(type_family("TIMESTAMP(6)"), "temporal")
#|        self.assertIsNone(type_family(""))
#|
#|    def test_mask_row(self):
#|        from nifikb.metadata import mask_row
#|        r = mask_row({"API_KEY": "k", "HEADERS": "Authorization: Bearer abcdefghijklmnop", "BODY": '{"password": "p4ss"}', "N": 3})
#|        self.assertEqual(r["API_KEY"], "***")
#|        self.assertNotIn("abcdefghijklmnop", r["HEADERS"])
#|        self.assertNotIn("p4ss", r["BODY"])
#|        self.assertEqual(r["N"], 3)
#|
#|
#|class TestIncremental(unittest.TestCase):
#|    def test_rebuild_and_changelog(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp)
#|            cfg = load_config(cfg_path)
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "built")
#|            self.assertEqual(build(cfg, log=lambda m: None)["status"], "up-to-date")
#|            flow = nested_flow(bucket="acme-orders-v2")
#|            flow["rootGroup"]["processors"] = [p for p in flow["rootGroup"]["processors"] if p["identifier"] != "p-gen"]
#|            flow["rootGroup"]["connections"] = [c for c in flow["rootGroup"]["connections"] if c["identifier"] != "r6"]
#|            with gzip.open(Path(tmp) / "flow.json.gz", "wt", encoding="utf-8") as f:
#|                json.dump(flow, f)
#|            res = build(cfg, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            changes = "\n".join(res["changes"])
#|            self.assertIn("'Bucket' `#{s3.bucket}` → `acme-orders-v2`", changes)
#|            self.assertIn("removed Nightly trigger", changes)
#|            self.assertIn("connection removed: Nightly trigger -success→ Lookup customer", changes)
#|            log = (Path(cfg["output"]["dir"]) / "CHANGELOG.md").read_text(encoding="utf-8")
#|            self.assertIn("acme-orders-v2", log)
#|            hard = (Path(cfg["output"]["dir"]) / "hardcoded.md").read_text(encoding="utf-8")
#|            self.assertIn("acme-orders-v2", hard)  # bucket is now a literal
#|
#|    def test_db_unreachable_uses_cache(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp))
#|            build(cfg, log=lambda m: None)
#|            os.remove(Path(tmp) / "meta.db")
#|            res = build(cfg, force=True, refresh_db=True, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            doc = (Path(cfg["output"]["dir"]) / "db/metadata.md").read_text(encoding="utf-8")
#|            self.assertIn("## file_audit", doc)
#|            idx = (Path(cfg["output"]["dir"]) / "db/INDEX.md").read_text(encoding="utf-8")
#|            self.assertIn("cached schema", idx)
#|
#|
#|@unittest.skipUnless((REAL_NIFI / "conf" / "flow.json.gz").exists(), "real NiFi not installed")
#|class TestRealNifi(unittest.TestCase):
#|    """End-to-end over the actual local NiFi install (conf + lib NARs + scripts)."""
#|
#|    def test_build(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = Path(tmp) / "nifikb.toml"
#|            cfg_path.write_text(f'[nifi]\nhome = "{REAL_NIFI.as_posix()}"\n[output]\ndir = "{Path(tmp, "kb").as_posix()}"\n'
#|                                f'[code]\nrepos = ["{(REAL_NIFI / "scripts").as_posix()}"]\n', encoding="utf-8")
#|            cfg = load_config(cfg_path)
#|            res = build(cfg, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            kb = Path(cfg["output"]["dir"])
#|            root = (kb / "flows/root.md").read_text(encoding="utf-8")
#|            self.assertEqual(root.count("table=sales"), 3)
#|            self.assertIn("Statement Type=INSERT_IGNORE", root)
#|            self.assertIn("*failure* → **PutDatabaseRecord** [PutDatabaseRecord] `4cb1c050`", root)
#|            self.assertIn("default hidden", root)  # NAR manifests were used
#|            script = (kb / "scripts/remove-duplicates-py.md").read_text(encoding="utf-8")
#|            self.assertIn("drop_duplicates(subset='ORDERNUMBER'", script)
#|            blob = "\n".join(all_text(kb).values())
#|            self.assertNotIn('"1234"', blob)  # stats.py password redacted
#|            self.assertIn("`sales` — `stats.py`", (kb / "external-systems.md").read_text(encoding="utf-8"))
#|            idx = (kb / "db/INDEX.md").read_text(encoding="utf-8")
#|            self.assertIn("jdbc:postgresql://localhost:5432/testDB", idx)
#|
#|
#|if __name__ == "__main__":
#|    unittest.main()
#|
#|
#|class TestManyTables(unittest.TestCase):
#|    def test_database_doc_splits_per_table(self):
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg_path = make_env(tmp)
#|            db = sqlite3.connect(Path(tmp) / "meta.db")
#|            for i in range(70):
#|                db.execute(f"CREATE TABLE wide_{i}(id INTEGER PRIMARY KEY, v{i} TEXT)")
#|            db.commit()
#|            db.close()
#|            cfg = load_config(cfg_path)
#|            cfg["databases"][0]["include_tables"].append("wide_%")
#|            build(cfg, log=lambda m: None)
#|            kb = Path(cfg["output"]["dir"])
#|            index = (kb / "db" / "metadata.md").read_text(encoding="utf-8")
#|            self.assertIn("one file per table under `db/metadata/`", index)
#|            self.assertIn("[wide-7.md](metadata/wide-7.md)", index)
#|            self.assertIn("| v7 | TEXT |", (kb / "db" / "metadata" / "wide-7.md").read_text(encoding="utf-8"))
#|            rc, out = run_cli("--config", str(cfg_path), "show", "wide_7")
#|            self.assertIn("| v7 | TEXT |", out)
#|            # dropping the tables removes their files on the next build
#|            cfg["databases"][0]["include_tables"].remove("wide_%")
#|            build(cfg, refresh_db=True, log=lambda m: None)
#|            self.assertFalse((kb / "db" / "metadata").exists())
#|
#|
#|class TestScale(unittest.TestCase):
#|    def test_large_flow_is_fast(self):
#|        import time
#|        from fixtures_builder import conn as mk_conn, proc as mk_proc
#|        flow = nested_flow()
#|        for g in range(150):
#|            gid = f"g{g}"
#|            procs = [mk_proc(f"{gid}-p{i}", f"Step {i}", "org.apache.nifi.processors.standard.InvokeHTTP",
#|                             {"Remote URL": f"https://api{g}.acme.com/v1/{i}", "put-db-record-table-name": f"t_{g}_{i}"}, group=gid)
#|                     for i in range(20)]
#|            conns = [mk_conn(f"{gid}-c{i}", f"{gid}-p{i - 1}", "PROCESSOR", f"{gid}-p{i}", "PROCESSOR", ["Response"], group=gid)
#|                     for i in range(1, 20)]
#|            flow["rootGroup"]["processGroups"].append({
#|                "identifier": gid, "name": f"Flow {g}", "processors": procs, "connections": conns, "inputPorts": [], "outputPorts": [],
#|                "funnels": [], "labels": [], "controllerServices": [], "processGroups": [], "remoteProcessGroups": [], "variables": {}})
#|        with tempfile.TemporaryDirectory() as tmp:
#|            cfg = load_config(make_env(tmp, flow=flow, with_db=False))
#|            t = time.time()
#|            res = build(cfg, log=lambda m: None)
#|            self.assertEqual(res["status"], "built")
#|            self.assertLess(time.time() - t, 30)
#|            self.assertTrue((Path(cfg["output"]["dir"]) / "flows" / "flow-149.md").exists())
#@@ FILE ops/build.cmd t 52b9392d46df1b51
#|@echo off
#|rem Refresh the NiFi knowledge base (no-op when nothing changed). Used by the scheduled task from register-schedule.ps1.
#|rem Database passwords come from user environment variables, e.g.  setx NIFIKB_DB_PASSWORD "..."  (once, then log off/on).
#|cd /d "%~dp0.."
#|echo ==== %date% %time% >> "%~dp0build.log"
#|python -m nifikb build >> "%~dp0build.log" 2>&1
#@@ FILE ops/build.sh t 3b9e9d48d937a624
#|#!/usr/bin/env sh
#|# Refresh the NiFi knowledge base (no-op when nothing changed). Linux counterpart of build.cmd.
#|# Cron (every 30 min):  */30 * * * * sh /opt/nifi-kb/ops/build.sh
#|# Use password_file (chmod 600) in nifikb.toml so cron needs no environment variables.
#|cd "$(dirname "$0")/.." || exit 1
#|PY="${PYTHON:-python3}"
#|echo "==== $(date '+%Y-%m-%d %H:%M:%S')" >> ops/build.log
#|"$PY" -m nifikb build >> ops/build.log 2>&1
#@@ FILE ops/bundle.py t 541c7e964658d4d0
#|"""Pack nifi-kb into ONE plain-text Python file (or a few) for machines where nothing can be downloaded but text can be
#|pasted - e.g. open it in a browser / Bitbucket / e-mail on the office laptop, copy all, paste into a new file, run it.
#|
#|    python ops/bundle.py [--out dist] [--max-kb 0] [--no-tests] [--with-learnings]
#|
#|--max-kb splits the bundle into parts of about that size (clipboard / editor limits); each part is self-contained and
#|unpacked the same way into the same folder. The unpacker (ops/bundle_unpack.py) checks every file's hash, so a paste
#|that was cut off or damaged is reported instead of producing broken files. Same content as ops/package.py (minus the
#|sandbox config).
#|"""
#|import argparse
#|import base64
#|import hashlib
#|import sys
#|from pathlib import Path
#|
#|ROOT = Path(__file__).resolve().parent.parent
#|sys.path.insert(0, str(ROOT))
#|sys.path.insert(0, str(ROOT / "ops"))
#|
#|from bundle_unpack import DATA_LINE, text_hash  # noqa: E402
#|from nifikb import __version__  # noqa: E402
#|from package import collect  # noqa: E402
#|
#|
#|def encode(rel, data):
#|    """Header + '#|' lines for one file."""
#|    if " " in rel:
#|        raise ValueError(f"file names with blanks are not supported in a bundle: {rel}")
#|    try:
#|        text = data.decode("utf-8")
#|        if "\x00" in text or "\r" in text.replace("\r\n", ""):
#|            raise UnicodeDecodeError("utf-8", data, 0, 1, "binary-looking")
#|    except UnicodeDecodeError:
#|        b64 = base64.b64encode(data).decode("ascii")
#|        lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
#|        return [f"#@@ FILE {rel} b {hashlib.sha256(data).hexdigest()[:16]}"] + [f"#|{x}" for x in lines]
#|    crlf = "\r\n" in text
#|    text = text.replace("\r\n", "\n")
#|    newline = text.endswith("\n")
#|    mode = ("tc" if crlf else "t") if newline else ("tcn" if crlf else "tn")
#|    body = text[:-1] if newline else text
#|    lines = body.split("\n") if body else []
#|    return [f"#@@ FILE {rel} {mode} {text_hash(text)}"] + [f"#|{x}" for x in lines]
#|
#|
#|def bundle(out_dir, max_kb=0, tests=True, with_learnings=False):
#|    files = [(rel, data) for rel, data in collect(with_learnings, sandbox_config=False)
#|             if tests or not rel.startswith("tests/")]
#|    first_of = {}
#|    items = []  # (rel, lines, source rel for copies)
#|    for rel, data in files:
#|        digest = hashlib.sha256(data).hexdigest()
#|        if digest in first_of and data:
#|            items.append((rel, [f"#@@ COPY {rel} {first_of[digest]}"], first_of[digest]))  # CLAUDE.md = GEMINI.md = AGENTS.md
#|        else:
#|            first_of[digest] = rel
#|            items.append((rel, encode(rel, data), None))
#|    parts, current, size = [], [], 0
#|    part_of = {}
#|    for rel, lines, source in items:
#|        n = sum(len(x) + 1 for x in lines)
#|        if source is None and max_kb and current and size + n > max_kb * 1024:
#|            parts.append(current)
#|            current, size = [], 0
#|        if source is not None:  # a copy goes with its source
#|            parts_list = parts + [current]
#|            parts_list[part_of[source]].append((rel, lines))
#|            part_of[rel] = part_of[source]
#|            continue
#|        current.append((rel, lines))
#|        part_of[rel] = len(parts)
#|        size += n
#|    parts.append(current)
#|    stub = (ROOT / "ops" / "bundle_unpack.py").read_text(encoding="utf-8")
#|    out_dir = Path(out_dir)
#|    out_dir.mkdir(parents=True, exist_ok=True)
#|    for old in out_dir.glob(f"nifi-kb-{__version__}-bundle*.py"):
#|        old.unlink()
#|    written = []
#|    for i, part in enumerate(parts, 1):
#|        name = f"nifi-kb-{__version__}-bundle.py" if len(parts) == 1 else f"nifi-kb-{__version__}-bundle-part{i}of{len(parts)}.py"
#|        head = (f"# nifi-kb {__version__} - paste bundle" + (f", part {i} of {len(parts)}" if len(parts) > 1 else "")
#|                + f" - {len(part)} files. Save as {name}, then run:  python {name}\n")
#|        body = [line for _, lines in part for line in lines]
#|        text = (head + stub.rstrip("\n") + "\n\n" + DATA_LINE + "\n" + "\n".join(body) + "\n"
#|                + f"#@@ END part {i} of {len(parts)} files {len(part)}\n")
#|        path = out_dir / name
#|        path.write_text(text, encoding="utf-8", newline="\n")
#|        written.append((path, len(part)))
#|    return written
#|
#|
#|def main():
#|    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
#|    ap.add_argument("--out", default=str(ROOT / "dist"))
#|    ap.add_argument("--max-kb", type=int, default=0, help="split into parts of about this many KB (0 = one file)")
#|    ap.add_argument("--no-tests", action="store_true", help="leave tests/ out (smaller; you cannot run the test suite there)")
#|    ap.add_argument("--with-learnings", action="store_true", help="also copy knowledge/learnings/*.md")
#|    args = ap.parse_args()
#|    for path, n in bundle(args.out, args.max_kb, not args.no_tests, args.with_learnings):
#|        print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB, {n} files)")
#|    print("On the office laptop: create an empty file with the same name, paste the whole content, save as UTF-8, "
#|          "run  python <file>  - it recreates the nifi-kb folder next to it.")
#|
#|
#|if __name__ == "__main__":
#|    main()
#@@ FILE ops/bundle_unpack.py t c56748f989ce7c37
#|"""nifi-kb paste bundle: recreates the nifi-kb folder from this single file (for machines where files cannot be
#|downloaded, only text pasted).
#|
#|    python <this file> [target folder]        default target: a folder "nifi-kb" next to this file
#|
#|Everything below the DATA line is the content of the files, stored as comment lines ("#|" + the line) so the whole file
#|stays plain, readable text and valid Python. Each file's hash is checked; a file whose paste was damaged is NOT written
#|and is listed, so only that part needs pasting again. Your own nifikb.toml and knowledge/ files are never overwritten.
#|Standard library only; Python 3.8+ can unpack, nifi-kb itself needs 3.11+.
#|"""
#|import base64
#|import hashlib
#|import sys
#|from pathlib import Path, PurePosixPath
#|
#|KEEP = ("nifikb.toml", "knowledge/")  # yours after the first unpack: never overwritten
#|DATA_LINE = "# ==== DATA ===="
#|
#|
#|def text_hash(text):
#|    """Hash that survives a copy / paste: line endings and trailing blanks do not count."""
#|    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
#|    while lines and not lines[-1]:
#|        lines.pop()
#|    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]
#|
#|
#|def safe_path(rel):
#|    p = PurePosixPath(rel)
#|    if p.is_absolute() or ".." in p.parts or ":" in rel or not rel:
#|        raise ValueError(f"unsafe path in bundle: {rel!r}")
#|    return p
#|
#|
#|def parse(lines):
#|    """[(kind, path, mode, hash, content lines or source path)], (part, parts, count) from the END line or None."""
#|    entries, current, end, seen_data = [], None, None, False
#|    for n, raw in enumerate(lines, 1):
#|        line = raw.rstrip("\r\n")
#|        if not seen_data:
#|            seen_data = line.strip() == DATA_LINE
#|            continue
#|        if line.startswith("#|"):
#|            if current is None:
#|                raise ValueError(f"line {n}: content before any file header")
#|            current[4].append(line[2:])
#|        elif line.startswith("#@@ FILE "):
#|            _, _, path, mode, digest = line.split(" ")[:5]
#|            current = ["file", path, mode, digest, []]
#|            entries.append(current)
#|        elif line.startswith("#@@ COPY "):
#|            _, _, path, source = line.split(" ")[:4]
#|            entries.append(["copy", path, None, None, source])
#|            current = None
#|        elif line.startswith("#@@ END "):
#|            bits = line.split()
#|            end = (int(bits[3]), int(bits[5]), int(bits[7]))  # "#@@ END part 1 of 3 files 42"
#|            current = None
#|        elif line.strip() in ("", "#"):
#|            continue  # an editor added or trimmed an empty line
#|        else:
#|            raise ValueError(f"line {n} is not part of the bundle (damaged paste?): {line[:60]!r}")
#|    if not seen_data:
#|        raise ValueError(f"no '{DATA_LINE}' line - this is not a complete nifi-kb bundle")
#|    return entries, end
#|
#|
#|def main(argv=None):
#|    argv = sys.argv[1:] if argv is None else argv
#|    me = Path(__file__).resolve()
#|    target = Path(argv[0]).resolve() if argv else me.parent / "nifi-kb"
#|    with open(me, encoding="utf-8-sig") as f:
#|        entries, end = parse(f.readlines())
#|    files = [e for e in entries if e[0] == "file"]
#|    if end is None:
#|        print("ERROR: the bundle is incomplete (its last line '#@@ END ...' is missing) - the paste was cut off. "
#|              "Copy the whole file again (Ctrl+A in the source view).")
#|        return 2
#|    part, parts, count = end
#|    if count != len(files) + sum(1 for e in entries if e[0] == "copy"):
#|        print(f"ERROR: expected {count} files in this part, found {len(entries)} - the paste lost lines; copy it again.")
#|        return 2
#|    written, kept, bad = [], [], []
#|    contents = {}
#|    for kind, rel, mode, digest, body in entries:
#|        path = safe_path(rel)
#|        if kind == "copy":
#|            if body not in contents:
#|                bad.append(f"{rel} (copy of {body}, which is not in this part or was damaged)")
#|                continue
#|            data = contents[body]
#|        elif mode == "b":
#|            data = base64.b64decode("".join(body))
#|            if hashlib.sha256(data).hexdigest()[:16] != digest:
#|                bad.append(rel)
#|                continue
#|        else:
#|            text = "\n".join(body) + ("\n" if mode in ("t", "tc") else "")
#|            if text_hash(text) != digest:
#|                bad.append(rel)
#|                continue
#|            data = (text.replace("\n", "\r\n") if mode in ("tc", "tcn") else text).encode("utf-8")
#|        contents[rel] = data
#|        dest = target / Path(*path.parts)
#|        if dest.exists() and (rel == KEEP[0] or rel.startswith(KEEP[1])) and rel != "knowledge/README.md":
#|            kept.append(rel)
#|            continue
#|        dest.parent.mkdir(parents=True, exist_ok=True)
#|        dest.write_bytes(data)
#|        written.append(rel)
#|    print(f"part {part} of {parts}: {len(written)} files written to {target}" + (f", {len(kept)} of yours kept ({', '.join(kept)})" if kept else ""))
#|    if bad:
#|        print(f"ERROR: {len(bad)} file(s) damaged in the paste and NOT written - copy this part again:")
#|        for b in bad:
#|            print(f"  {b}")
#|        return 1
#|    if part == parts:
#|        print("Next: cd into the folder, then  python -m unittest discover -s tests  (expect OK),  edit nifikb.toml,  "
#|              "python -m nifikb build,  python -m nifikb doctor  - see HANDOFF.md section 4.")
#|    else:
#|        print(f"Now unpack part {part + 1} of {parts} the same way (into the same folder).")
#|    return 0
#|
#|
#|if __name__ == "__main__":
#|    sys.exit(main())
#@@ FILE ops/package.py tc bf7717252b18bd30
#|"""Build a clean zip to move nifikb to another machine (e.g. the office laptop).
#|
#|    python ops/package.py [--out dist] [--with-learnings]
#|
#|Included: the nifikb package, tests, ops scripts, examples/, evals/cases.example.toml, agent setup (CLAUDE/GEMINI/AGENTS.md, .mcp.json, .gemini/, .claude/),
#|docs, knowledge/README.md + context.md, and a fresh nifikb.toml template (this machine's config holds local paths and
#|sandbox databases, so it is saved as nifikb.toml.sandbox for reference only).
#|Never included: kb/ (rebuild there), caches, logs, secrets.
#|"""
#|import argparse
#|import sys
#|import zipfile
#|from pathlib import Path
#|
#|ROOT = Path(__file__).resolve().parent.parent
#|sys.path.insert(0, str(ROOT))
#|
#|from nifikb import __version__  # noqa: E402
#|from nifikb.config import TEMPLATE  # noqa: E402
#|
#|FILES = ["CLAUDE.md", "GEMINI.md", "AGENTS.md", "README.md", "HANDOFF.md", ".mcp.json", ".gitignore"]
#|DIRS = ["nifikb", "tests", "ops", ".gemini", ".claude", "examples"]
#|SKIP_PARTS = {"__pycache__", ".pytest_cache", "dist"}
#|SKIP_NAMES = {"build.log", "settings.local.json", "last-report.html", "cases.toml"}
#|
#|
#|def collect(with_learnings=False, sandbox_config=True):
#|    """[(relative path, bytes)] of everything that is shipped - shared by the zip and the paste bundle (ops/bundle.py)."""
#|    out = []
#|
#|    def add(path):
#|        rel = path.relative_to(ROOT)
#|        if SKIP_PARTS & set(rel.parts) or path.name in SKIP_NAMES or path.suffix == ".pyc":
#|            return
#|        out.append((rel.as_posix(), path.read_bytes()))
#|
#|    for f in FILES:
#|        if (ROOT / f).is_file():
#|            add(ROOT / f)
#|    for d in DIRS:
#|        for p in sorted((ROOT / d).rglob("*")) if (ROOT / d).is_dir() else []:
#|            if p.is_file():
#|                add(p)
#|    if (ROOT / "evals" / "cases.example.toml").is_file():  # the team's own evals/cases.toml holds real tickets: not shipped
#|        add(ROOT / "evals" / "cases.example.toml")
#|    knowledge = ROOT / "knowledge"
#|    for f in ("README.md", "context.md"):
#|        if (knowledge / f).is_file():
#|            add(knowledge / f)
#|    if with_learnings:
#|        for p in sorted((knowledge / "learnings").glob("*.md")):
#|            add(p)
#|    out.append(("knowledge/learnings/.keep", b""))
#|    out.append(("nifikb.toml", TEMPLATE.format(home="C:/path/to/nifi").encode("utf-8")))  # fresh template
#|    if sandbox_config and (ROOT / "nifikb.toml").is_file():
#|        out.append(("nifikb.toml.sandbox", (ROOT / "nifikb.toml").read_bytes()))  # reference only
#|    return out
#|
#|
#|def package(out_dir, with_learnings=False):
#|    out_dir = Path(out_dir)
#|    out_dir.mkdir(parents=True, exist_ok=True)
#|    target = out_dir / f"nifi-kb-{__version__}.zip"
#|    names = []
#|    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
#|        for rel, data in collect(with_learnings):
#|            z.writestr(f"nifi-kb/{rel}", data)
#|            names.append(rel)
#|    return target, names
#|
#|
#|def main():
#|    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
#|    ap.add_argument("--out", default=str(ROOT / "dist"))
#|    ap.add_argument("--with-learnings", action="store_true", help="also copy knowledge/learnings/*.md")
#|    args = ap.parse_args()
#|    target, names = package(args.out, args.with_learnings)
#|    print(f"wrote {target} ({target.stat().st_size / 1024:.0f} KB, {len(names)} entries)")
#|    print("On the new machine: unzip, then follow HANDOFF.md section 4 (edit nifikb.toml, build, doctor).")
#|
#|
#|if __name__ == "__main__":
#|    main()
#@@ FILE ops/register-schedule.ps1 t 6b93315f1a18bbb9
#|# Registers Windows scheduled tasks (current user, no admin needed):
#|#   nifikb-build   refreshes the knowledge base every N minutes
#|#   nifikb-report  (optional) builds and sends the daily health report at a fixed time ([report] in nifikb.toml)
#|#
#|#   powershell -ExecutionPolicy Bypass -File ops\register-schedule.ps1 [-EveryMinutes 60] [-ReportAt 08:00]
#|# Remove with:  Unregister-ScheduledTask -TaskName nifikb-build -Confirm:$false  (same for nifikb-report)
#|param([int]$EveryMinutes = 60, [string]$ReportAt = "")
#|
#|$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
#|
#|$build = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot "build.cmd")
#|$every = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
#|Register-ScheduledTask -TaskName "nifikb-build" -Action $build -Trigger $every -Settings $settings `
#|    -Description "Refresh the NiFi knowledge base (python -m nifikb build)" -Force | Out-Null
#|Write-Host "Scheduled nifikb-build every $EveryMinutes minutes."
#|
#|if ($ReportAt) {
#|    $report = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot "report.cmd")
#|    $daily = New-ScheduledTaskTrigger -Daily -At $ReportAt
#|    Register-ScheduledTask -TaskName "nifikb-report" -Action $report -Trigger $daily -Settings $settings `
#|        -Description "Daily NiFi health report (python -m nifikb report --send)" -Force | Out-Null
#|    Write-Host "Scheduled nifikb-report daily at $ReportAt."
#|}
#|Write-Host "Log: $(Join-Path $PSScriptRoot 'build.log')"
#@@ FILE ops/report.cmd t 39b7c825fba5dea2
#|@echo off
#|rem Daily NiFi health report: refresh the KB, then e-mail / post the report as configured in [report] of nifikb.toml.
#|cd /d "%~dp0.."
#|python -m nifikb build >> "%~dp0build.log" 2>&1
#|python -m nifikb report --hours 24 --html "%~dp0last-report.html" --send >> "%~dp0build.log" 2>&1
#@@ FILE ops/report.sh t 8590c70b5b5a0b14
#|#!/usr/bin/env sh
#|# Daily NiFi health report: refresh the KB, then e-mail / post it as configured in [report] of nifikb.toml.
#|# Cron (08:00 every day):  0 8 * * * sh /opt/nifi-kb/ops/report.sh
#|cd "$(dirname "$0")/.." || exit 1
#|PY="${PYTHON:-python3}"
#|"$PY" -m nifikb build >> ops/build.log 2>&1
#|"$PY" -m nifikb report --hours 24 --html ops/last-report.html --send >> ops/build.log 2>&1
#@@ FILE ops/sync-agent-docs.cmd t a008859ee9ae6ea0
#|@echo off
#|rem CLAUDE.md is the master copy of the agent instructions; Gemini CLI reads GEMINI.md, other agents AGENTS.md.
#|cd /d "%~dp0.."
#|copy /y CLAUDE.md GEMINI.md >nul
#|copy /y CLAUDE.md AGENTS.md >nul
#|echo GEMINI.md and AGENTS.md updated from CLAUDE.md
#@@ FILE .gemini/commands/learn.toml t da3b77dbf0ce8cdc
#|description = "Save a reusable lesson from this conversation as a team learning shared with Claude and people"
#|prompt = """
#|Record a team learning following the "Team learnings" rules in GEMINI.md.
#|
#|What to capture: {{args}}
#|(If empty, use the root cause and fix established in this conversation.)
#|
#|1. find_learnings with the file names / tables / feeds / processors involved; if an existing learning covers it, retire it
#|   (retire_learning with replaced_by) and add the corrected one - never create a near duplicate.
#|2. Only save knowledge the KB cannot derive (not what the flow / code / tables already show), verified in this
#|   conversation, without secrets or personal data.
#|3. add_learning: specific title, kind, applies_to (file patterns, tables, feeds, processor names / short ids, config
#|   rows), tags, ticket if known, author "gemini", body with ## Symptom, ## Cause, ## Fix, ## How to spot it next time.
#|4. Show the saved id and the text. If the lesson keeps recurring, suggest what to add to knowledge/context.md.
#|"""
#@@ FILE .gemini/commands/triage.toml tc 29d6495e134235e5
#|description = "Triage a NiFi support ticket end to end (metadata, flow, custom code) and record what was learned"
#|prompt = """
#|Triage this NiFi support ticket by following the "Triage playbook" in GEMINI.md exactly:
#|
#|{{args}}
#|
#|Steps: kb_overview if you have not yet this session -> only a Jira / ServiceNow id given: ticket with it (reads the ticket and runs investigate); otherwise investigate with everything the ticket gives (file, feed, table, error_text, headers in file order or sample_path; live=true if config rows may have changed) -> read the ranked causes and evidence -> only if not conclusive: diagnose / provenance / logs / late_files (file not received) / check_target_output (loaded but data wrong) / search / show / trace / sql -> answer as Cause / Evidence / Fix / Also noticed, with short ids, TABLE:id, file:line and log lines.
#|Propose fixes (SQL for config rows, property changes) for a human to apply; never apply them.
#|
#|Finally, if the cause or fix is reusable and not derivable from the KB, call add_learning (kind, applies_to, tags,
#|ticket, author "gemini", body with Symptom / Cause / Fix / How to spot it next time) - retire an outdated learning instead
#|of duplicating it - and tell me the learning id. If nothing reusable was learned, say so and do not add one.
#|"""
#@@ FILE .gemini/settings.json t 63e96f305c59b3e2
#|{
#|  "mcpServers": {
#|    "nifikb": {
#|      "command": "python",
#|      "args": ["-m", "nifikb", "mcp"],
#|      "cwd": ".",
#|      "timeout": 600000
#|    }
#|  }
#|}
#@@ FILE .claude/commands/learn.md t b22b0c47e9a01925
#|---
#|description: Save a reusable lesson from this conversation (or from the text given) as a team learning shared with Gemini and people
#|argument-hint: [what to remember - optional; defaults to the ticket just solved]
#|---
#|Record a team learning following the "Team learnings" rules in CLAUDE.md.
#|
#|What to capture: $ARGUMENTS
#|(If empty, use the root cause and fix established in this conversation.)
#|
#|1. `find_learnings` with the file names / tables / feeds / processors involved; if an existing learning covers it, update
#|   by retiring it (`retire_learning` with `replaced_by`) and adding the corrected one — never create a near duplicate.
#|2. Only save knowledge the KB cannot derive (not what the flow / code / tables already show), verified in this
#|   conversation, without secrets or personal data.
#|3. `add_learning`: specific title, kind, applies_to (file patterns, tables, feeds, processor names / short ids, config
#|   rows), tags, ticket if known, author "claude", body with ## Symptom, ## Cause, ## Fix, ## How to spot it next time.
#|4. Show me the saved id and the text. If the lesson keeps recurring, suggest what to add to `knowledge/context.md`.
#@@ FILE .claude/commands/triage.md tc 835a148b50cc1f3f
#|---
#|description: Triage a NiFi support ticket end to end (metadata, flow, custom code) and record what was learned
#|argument-hint: <ticket text, ticket id + details, or a file name>
#|---
#|Triage this NiFi support ticket by following the "Triage playbook" in CLAUDE.md exactly:
#|
#|$ARGUMENTS
#|
#|Steps: `kb_overview` if you have not yet this session → only a Jira / ServiceNow id given: `ticket` with it (reads the
#|ticket and runs investigate); otherwise `investigate` with everything the ticket gives (file, feed,
#|table, error_text, headers in file order or sample_path; `live=true` if config rows may have changed) → read the ranked
#|causes and evidence → only if not conclusive: `diagnose` / `provenance` / `logs` / `late_files` (file not received) /
#|`check_target_output` (loaded but data wrong) / `search` / `show` / `trace` / `sql` →
#|answer as **Cause / Evidence / Fix / Also noticed**, with short ids, `TABLE:id`, `file:line` and log lines.
#|Propose fixes (SQL for config rows, property changes) for a human to apply; never apply them.
#|
#|Finally, if the cause or fix is reusable and not derivable from the KB, call `add_learning` (kind, applies_to, tags,
#|ticket, author "claude", body with Symptom / Cause / Fix / How to spot it next time) — retire an outdated learning instead
#|of duplicating it — and tell me the learning id. If nothing reusable was learned, say so and do not add one.
#@@ FILE .claude/settings.json t 64a048b09bef2abb
#|{
#|  "enableAllProjectMcpServers": true,
#|  "permissions": {
#|    "allow": [
#|      "mcp__nifikb",
#|      "Bash(python -m nifikb:*)",
#|      "Bash(py -m nifikb:*)",
#|      "Read(kb/**)",
#|      "Read(knowledge/**)"
#|    ],
#|    "deny": [
#|      "Read(**/flow.json.gz)",
#|      "Read(**/flow.xml.gz)",
#|      "Read(**/*.nar)",
#|      "Read(kb/kb.sqlite)"
#|    ]
#|  }
#|}
#@@ FILE examples/new-feed.example.toml t 2783f2eb9c44c1ab
#|# Proposal for a NEW feed - check it before anyone inserts the rows:
#|#   python -m nifikb onboard examples/new-feed.example.toml [--live]
#|# Column names are the config tables' own (kb/metadata.md lists them). Nothing is written anywhere: the check lists problems
#|# and prints INSERT statements for a human to review and run. Leave secrets (passwords, tokens) out - the DBA sets them.
#|
#|example_file = "INVOICE_20260927.csv"     # a real file name the definition must match (checked against every definition)
#|# sample = "INVOICE_20260927.csv"         # optional: a sample file (relative to this file) - header and content are checked
#|like = "SALES_YYYYMMDD.csv"               # optional: an existing, similar feed - columns / rows it has and this one lacks
#|# structure_csv = "invoice_columns.csv"   # optional: the structure rows as CSV (header = column names), instead of [[structure]]
#|
#|[definition]                              # one OBJ_DEFINITION row
#|# OBJ_ID = 123                            # leave out when the database generates it
#|FILE_NAME = "INVOICE_YYYYMMDD.csv"
#|TABLE_NAME = "stg_invoice"
#|SOURCE_SYSTEM = "ERP"
#|DELIMITER = ","
#|ACTIVE_FLAG = "Y"
#|
#|[[structure]]                             # one OBJ_STRUCTURE row per column, in file order (the parent id is filled in)
#|COL_NAME = "INVOICE_NO"
#|DATA_TYPE = "INTEGER"
#|COL_SEQ = 1
#|MANDATORY_FLAG = "Y"
#|
#|[[structure]]
#|COL_NAME = "CUSTOMER_NAME"
#|DATA_TYPE = "VARCHAR"
#|COL_SEQ = 2
#|COL_LENGTH = 100
#|
#|[[structure]]
#|COL_NAME = "AMOUNT"
#|DATA_TYPE = "DECIMAL"
#|COL_SEQ = 3
#|
#|[[rows.SOURCE_FEED_CONFIG]]               # rows of other config tables that belong to the feed (the link column is filled in)
#|FEED_NAME = "erp_invoice_feed"
#|SFTP_HOST = "sftp.erp.example.com"
#|REMOTE_DIR = "/outbound/invoice"
#@@ FILE evals/cases.example.toml t 6127cbefffc19fae
#|# Evaluation set: real past tickets with their known root cause (anonymise as needed).
#|# Copy to evals/cases.toml and add 15-30 tickets covering your common problem types.
#|#   python -m nifikb eval                         -> do the tools rank the true cause in the top 3?
#|#   python -m nifikb eval --agent "gemini -p"     -> does the model's answer name it? (prompt goes to stdin)
#|#   python -m nifikb eval --save evals/last.json  -> keep results to compare after changes
#|# Sample files can live in evals/samples/ (paths are relative to this file).
#|
#|[[case]]
#|id = "INC-0001-example"
#|ticket = "SALES file of 26 Sep did not load, customer names are missing in the report"
#|file = "SALES_20260926.csv"
#|headers = ["ORDER_NO", "CUSTNAME", "AMOUNT", "ORDER_DT", "REGION"]
#|expect_any = ["CUSTNAME"]            # the true cause: the header CUSTNAME does not match structure field CUST_NAME
#|top = 3
#|answer_expect = ["CUST_NAME"]        # the model's answer must mention the structure field
#|
#|# [[case]]
#|# id = "INC-0002"
#|# ticket = "orders API load failed at 02:14 with 'Column count mismatch'"
#|# file = "orders_20260926.json"
#|# error = "Column count mismatch"
#|# sample = "samples/orders_20260926.json"
#|# expect_any = ["delimited by", "column count"]
#@@ FILE knowledge/README.md t b96f72b044673f83
#|# Team knowledge
#|
#|Everything here is written by people and by the AI agents (Claude Code, Gemini CLI, …) and is **kept across builds**,
#|unlike `kb/`, which `nifikb build` regenerates. Commit this folder to git so the whole team (and every agent session)
#|shares it.
#|
#|| File | Who writes it | What goes in |
#||---|---|---|
#|| `context.md` | people (agents may suggest edits) | short, curated background: environments, owners / escalation, conventions, known quirks. Every agent session reads it first. |
#|| `learnings/<id>.md` | agents after solving a ticket, or people | one reusable lesson per file: symptom, cause, fix, how to spot it next time |
#|
#|## Adding a learning
#|
#|From an agent: the `add_learning` tool, or the `/learn` command in Claude Code and Gemini CLI.
#|From a terminal:
#|
#|```
#|python -m nifikb learn add --title "SALES feed switches to pipe delimiter at month end" --kind pattern ^
#|    --applies-to "SALES_*.csv,stg_sales" --tags "delimiter,vendor" --ticket INC12345 --body-file note.md
#|python -m nifikb learn list            # newest first;  --all includes retired ones
#|python -m nifikb learn for SALES_20260926.csv stg_sales
#|python -m nifikb learn retire <id> --reason "vendor fixed the export" [--replaced-by <id>]
#|```
#|
#|Or write the file by hand (it is picked up on the next `build`; `learn add` makes it searchable immediately):
#|
#|```markdown
#|---
#|id: 2026-09-26-sales-feed-pipe-delimiter
#|title: SALES feed switches to pipe delimiter at month end
#|kind: pattern            # fix | pattern | gotcha | context | faq
#|date: 2026-09-26
#|author: sanjay
#|tags: [delimiter, vendor]
#|applies_to: [SALES_*.csv, stg_sales, MetadataLookup, OBJ_DEFINITION:12]
#|ticket: INC12345
#|status: active           # active | obsolete
#|---
#|## Symptom
#|Month-end SALES files fail with "Structure mismatch", all other days load.
#|## Cause
#|The vendor's month-end export uses `|`; OBJ_DEFINITION:12 has DELIMITER `,`.
#|## Fix
#|Vendor agreed to always send `,` (INC12345). Until then re-drop the file after converting.
#|## How to spot it next time
#|`diagnose --file <name> --sample <file>` shows one header containing `|`.
#|```
#|
#|`applies_to` is what makes a learning show up automatically in `diagnose` and `find_learnings`: use file names or
#|patterns (`SALES_*.csv`, `SALES_YYYYMMDD.csv`), table names, feed / API names, processor names or short ids, and config
#|rows as `TABLE:id`.
#|
#|## Keeping it healthy
#|
#|- One lesson per file; specific titles. Update by retiring the old learning and adding a new one (history is kept).
#|- Only what the KB cannot derive: causes, quirks, procedures, conventions — not copies of flow / table facts.
#|- **Never** secrets, tokens, customer data. Passwords and bearer tokens are redacted automatically, but review anyway.
#|- Review monthly: retire what no longer holds; move lessons that keep recurring into `context.md`.
#@@ FILE knowledge/context.md tc c271d68c80171159
#|# Team context
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
#@@ FILE knowledge/learnings/.keep tn e3b0c44298fc1c14
#@@ FILE nifikb.toml t 595032d5c8ab336e
#|# =====================================================================================================================
#|# nifikb configuration - the ONLY file you edit.
#|#   * Paths may be absolute or relative to this file; ${VARS} are expanded.
#|#   * No secrets in here: passwords come from an environment variable (password_env) or a protected file
#|#     (password_file, chmod 600 on Linux).
#|#   * After editing:  python -m nifikb build   then   python -m nifikb doctor
#|# =====================================================================================================================
#|
#|db_refresh_hours = 24                    # how often table schemas are re-read (build --refresh-db forces it)
#|
#|# ---- 1. NiFi -------------------------------------------------------------------------------------------------------
#|[nifi]
#|home = "C:/path/to/nifi"                 # NiFi install folder: conf/flow.json.gz, lib/*.nar and logs/ are read from here
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
#|# location_template = "s3://datalake/raw/{table_lower}/"   # when OBJ_DEFINITION has no location column: where {table} lands
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
#@@ END part 5 of 5 files 22
