"""Live MariaDB regression test. Skipped unless NIFIKB_TEST_MARIADB=host:port:admin_user:admin_password is set.

Creates a scratch database + a SELECT-only user, runs a full build against it, then drops both."""
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from test_nifikb import run_cli
from fixtures_builder import make_env, metadata_flow
from nifikb import db as dbmod
from nifikb.build import build
from nifikb.config import load_config

MARIADB = os.environ.get("NIFIKB_TEST_MARIADB")


@unittest.skipUnless(MARIADB, "set NIFIKB_TEST_MARIADB=host:port:user:password to run against a live MariaDB")
class TestMariaDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pymysql
        host, port, user, password = MARIADB.split(":", 3)
        cls.admin = pymysql.connect(host=host, port=int(port), user=user, password=password, autocommit=True)
        with cls.admin.cursor() as cur:
            for stmt in [
                "DROP DATABASE IF EXISTS nifikb_test", "CREATE DATABASE nifikb_test", "USE nifikb_test",
                "CREATE TABLE file_audit(id INT AUTO_INCREMENT PRIMARY KEY, order_id VARCHAR(40) NOT NULL, vendor VARCHAR(40), "
                "status VARCHAR(20), received_at DATETIME NOT NULL, user_email VARCHAR(100), KEY ix_order(order_id)) COMMENT='one row per file call'",
                "CREATE TABLE customers(id INT PRIMARY KEY, name VARCHAR(80), region VARCHAR(10))",
                "CREATE TABLE orders(id VARCHAR(40) PRIMARY KEY, cust_id INT, total DECIMAL(10,2), FOREIGN KEY (cust_id) REFERENCES customers(id))",
                "CREATE TABLE file_calls(id INT AUTO_INCREMENT PRIMARY KEY, source_system VARCHAR(20), status ENUM('LOADED','FAILED'), file_name VARCHAR(200))",
                "INSERT INTO file_calls(source_system, status, file_name) VALUES ('vendorA','LOADED','a.json'),('vendorA','FAILED','b.json'),('vendorB','LOADED','c.json')",
                "INSERT INTO file_audit(order_id, vendor, status, received_at, user_email) VALUES ('o1','vendorA','OK',NOW(),'x@y.com')",
                "CREATE TABLE OBJ_DEFINITION(OBJ_ID INT PRIMARY KEY, FILE_NAME VARCHAR(200), TABLE_NAME VARCHAR(100), ACTIVE_FLAG CHAR(1))",
                "CREATE TABLE OBJ_STRUCTURE(STRUCT_ID INT AUTO_INCREMENT PRIMARY KEY, OBJ_ID INT NOT NULL, COL_NAME VARCHAR(100), "
                "DATA_TYPE VARCHAR(30), COL_SEQ INT, COL_LENGTH INT, MANDATORY_FLAG CHAR(1), FOREIGN KEY (OBJ_ID) REFERENCES OBJ_DEFINITION(OBJ_ID))",
                "CREATE TABLE SOURCE_FEED_CONFIG(FEED_ID INT PRIMARY KEY, OBJ_ID INT, FEED_NAME VARCHAR(50), SFTP_HOST VARCHAR(100), "
                "SFTP_PASSWORD VARCHAR(100), REMOTE_DIR VARCHAR(200))",
                "CREATE TABLE stg_sales(order_no INT NOT NULL, cust_name VARCHAR(20), amount DECIMAL(10,2), order_dt DATE, region VARCHAR(10), "
                "load_ts DATETIME NOT NULL)",
                "INSERT INTO OBJ_DEFINITION VALUES (1, 'SALES_YYYYMMDD.csv', 'stg_sales', 'Y')",
                "INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES "
                "(1,'ORDER_NO','INT',1,NULL,'Y'),(1,'CUST_NAME','VARCHAR',2,50,'N'),(1,'AMOUNT','VARCHAR',3,20,'N'),"
                "(1,'ORDER_DT','DATE',4,NULL,'N'),(1,'REGION','VARCHAR',5,10,'N')",
                "INSERT INTO SOURCE_FEED_CONFIG VALUES (10, 1, 'pos_sales_feed', 'sftp.pos.acme.com', 'Sup3rS3cret!', '/outbound/sales')",
                "CREATE USER IF NOT EXISTS 'nifikb_ro'@'%' IDENTIFIED BY 'ro_pass_123'",
                "CREATE USER IF NOT EXISTS 'nifikb_ro'@'localhost' IDENTIFIED BY 'ro_pass_123'",
                "GRANT SELECT ON nifikb_test.* TO 'nifikb_ro'@'%'",
                "GRANT SELECT ON nifikb_test.* TO 'nifikb_ro'@'localhost'",
            ]:
                cur.execute(stmt)
        cls.tmp = tempfile.mkdtemp()
        cfg_path = make_env(cls.tmp, flow=metadata_flow(), with_db=False)
        with open(cfg_path, "a", encoding="utf-8") as f:
            f.write(f'\n[[databases]]\nname = "metadata"\nkind = "mariadb"\nhost = "{host}"\nport = {port}\ndatabase = "nifikb_test"\n'
                    f'user = "nifikb_ro"\npassword_env = "NIFIKB_TEST_RO_PASS"\nmatch_jdbc = "dbhost.acme.com:3306/meta"\n'
                    f'include_tables = ["file_%"]\nprofile_tables = ["file_calls"]\nsample_rows = 1\n'
                    f'\n[metadata]\ndb = "metadata"\n')
        os.environ["NIFIKB_TEST_RO_PASS"] = "ro_pass_123"
        cls.cfg_path = cfg_path
        cls.cfg = load_config(cfg_path)
        cls.logs = []
        cls.res = build(cls.cfg, log=cls.logs.append)
        cls.kb = Path(cls.cfg["output"]["dir"])

    @classmethod
    def tearDownClass(cls):
        with cls.admin.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS nifikb_test")
            cur.execute("DROP USER IF EXISTS 'nifikb_ro'@'%'")
            cur.execute("DROP USER IF EXISTS 'nifikb_ro'@'localhost'")
        cls.admin.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_schema_documented(self):
        doc = (self.kb / "db/metadata.md").read_text(encoding="utf-8")
        self.assertIn("## nifikb_test.file_audit", doc, "\n".join(self.logs))
        self.assertIn("one row per file call", doc)
        self.assertIn("| order_id | varchar(40) | N |", doc)
        self.assertIn("auto_increment", doc)
        self.assertIn("Indexes: PRIMARY(id) unique, ix_order(order_id)", doc)
        self.assertIn("FKs: cust_id→customers.id", doc)
        self.assertIn("values of `status`: LOADED×2, FAILED×1", doc)
        self.assertIn("## nifikb_test.customers", doc)
        self.assertNotIn("x@y.com", doc)
        self.assertIn("order_archive", doc)

    def test_findings(self):
        db = sqlite3.connect(self.kb / "kb.sqlite")
        rows = dict(db.execute("SELECT kind, message FROM findings WHERE kind IN ('missing-table','field-mismatch','db-unreachable')").fetchall())
        db.close()
        self.assertIn("missing-table", rows)
        self.assertIn("received_at", rows.get("field-mismatch", ""))
        self.assertNotIn("db-unreachable", rows)

    def test_metadata(self):
        doc = (self.kb / "metadata.md").read_text(encoding="utf-8")
        self.assertRegex(doc, r"(?i)definition table: `obj_definition`")
        self.assertIn("(foreign key)", doc)
        self.assertIn("(shared column name)", doc)
        self.assertIn("NOT NULL column(s) of stg_sales not in the structure: load_ts", doc)
        self.assertIn("'AMOUNT' is VARCHAR in the structure but decimal(10,2)", doc)
        for live in ([], ["--live"]):
            rc, out = run_cli("--config", str(self.cfg_path), "diagnose", "--file", "SALES_20260926.csv", *live,
                              "ORDER_NO", "CUST_NAME", "AMOUNT", "REGION", "ORDER_DT")
            self.assertEqual(rc, 0, out)
            self.assertIn("header order differs", out)
            self.assertIn("SFTP_PASSWORD=***", out)
            self.assertNotIn("Sup3rS3cret!", out)
        self.assertFalse(b"Sup3rS3cret!" in (self.kb / "kb.sqlite").read_bytes(), "secret stored in kb.sqlite")

    def test_read_only(self):
        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT source_system, COUNT(*) n FROM file_calls GROUP BY source_system")
        self.assertEqual(rc, 0)
        self.assertIn("vendorB", out)
        rc, out = run_cli("--config", str(self.cfg_path), "sql", "SELECT user_email FROM file_audit")
        self.assertIn("***", out)
        conn, _ = dbmod.connect(self.cfg["databases"][0])
        try:
            with self.assertRaises(Exception):
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO file_calls(source_system) VALUES ('hack')")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
