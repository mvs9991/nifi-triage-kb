"""SQLite store: caches (NAR + code parse results), searchable facts, flow snapshots and the change log."""
import json
import sqlite3
import time

PERSISTENT = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS cache_nar(path TEXT PRIMARY KEY, sig TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS cache_code(path TEXT PRIMARY KEY, sig TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS cache_db(name TEXT PRIMARY KEY, sig TEXT, fetched REAL, data TEXT);
CREATE TABLE IF NOT EXISTS snapshot(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, flow_sig TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS changelog(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, change TEXT);
CREATE TABLE IF NOT EXISTS meta_rows(tbl TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS ix_meta_rows ON meta_rows(tbl);
CREATE TABLE IF NOT EXISTS meta_changes(ts REAL, tbl TEXT, pk TEXT, link TEXT, change TEXT);
CREATE INDEX IF NOT EXISTS ix_meta_changes ON meta_changes(link);
CREATE TABLE IF NOT EXISTS log_files(path TEXT PRIMARY KEY, sig TEXT, offset INTEGER, head TEXT);
CREATE TABLE IF NOT EXISTS log_events(hash TEXT PRIMARY KEY, ts TEXT, epoch REAL, level TEXT, thread TEXT, logger TEXT,
    component_type TEXT, component_id TEXT, flowfile_uuid TEXT, filename TEXT, message TEXT, cause TEXT, template TEXT, file TEXT, line INTEGER);
CREATE INDEX IF NOT EXISTS ix_log_comp ON log_events(component_id);
CREATE INDEX IF NOT EXISTS ix_log_file ON log_events(filename);
CREATE INDEX IF NOT EXISTS ix_log_uuid ON log_events(flowfile_uuid);
CREATE INDEX IF NOT EXISTS ix_log_epoch ON log_events(epoch);
CREATE TABLE IF NOT EXISTS investigations(ts REAL, key TEXT, rank INTEGER, kind TEXT, signature TEXT, cause TEXT);
CREATE INDEX IF NOT EXISTS ix_inv_ts ON investigations(ts);
"""
DERIVED = """
DROP TABLE IF EXISTS components; DROP TABLE IF EXISTS properties; DROP TABLE IF EXISTS connections;
DROP TABLE IF EXISTS resources; DROP TABLE IF EXISTS findings; DROP TABLE IF EXISTS code_components;
DROP TABLE IF EXISTS db_tables; DROP TABLE IF EXISTS search; DROP TABLE IF EXISTS groups;
DROP TABLE IF EXISTS record_schemas;
CREATE TABLE groups(id TEXT PRIMARY KEY, name TEXT, parent_id TEXT, path TEXT, doc TEXT, tags TEXT, instance_id TEXT, version TEXT);
CREATE TABLE components(id TEXT PRIMARY KEY, kind TEXT, name TEXT, type TEXT, group_id TEXT, group_path TEXT, state TEXT,
                        custom INTEGER, facts TEXT, auto_term TEXT, doc TEXT, instance_id TEXT);
CREATE TABLE properties(component_id TEXT, name TEXT, display TEXT, value TEXT, resolved TEXT, source TEXT, is_default INTEGER, kinds TEXT);
CREATE TABLE connections(id TEXT, source_id TEXT, dest_id TEXT, relationships TEXT, group_id TEXT, name TEXT);
CREATE TABLE resources(kind TEXT, value TEXT, component_id TEXT, property TEXT, source TEXT, hardcoded INTEGER, raw TEXT);
CREATE TABLE findings(severity TEXT, kind TEXT, component_id TEXT, message TEXT, location TEXT);
CREATE TABLE code_components(fqcn TEXT, path TEXT, line INTEGER, data TEXT);
CREATE TABLE db_tables(db TEXT, schema_name TEXT, name TEXT, data TEXT, doc TEXT);
CREATE TABLE record_schemas(component_id TEXT, db TEXT, table_name TEXT, fields TEXT, translate INTEGER);
CREATE VIRTUAL TABLE search USING fts5(kind, ref, title, body, doc UNINDEXED, tokenize='unicode61 remove_diacritics 2 tokenchars ''._-''');
"""


class Store:
    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA secure_delete=ON")  # replaced snapshots must not linger in free pages
        self.db.executescript(PERSISTENT)

    def close(self):
        self.db.commit()
        self.db.close()

    # meta
    def get_meta(self, key, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, json.dumps(value)))

    # caches
    def cached(self, table, key, sig):
        row = self.db.execute(f"SELECT sig, data FROM {table} WHERE path=?", (key,)).fetchone()
        return json.loads(row["data"]) if row and row["sig"] == sig else None

    def put_cache(self, table, key, sig, data):
        self.db.execute(f"INSERT OR REPLACE INTO {table}(path, sig, data) VALUES(?,?,?)", (key, sig, json.dumps(data)))

    def prune_cache(self, table, keep):
        keep = set(keep)
        for row in self.db.execute(f"SELECT path FROM {table}").fetchall():
            if row["path"] not in keep:
                self.db.execute(f"DELETE FROM {table} WHERE path=?", (row["path"],))

    def cached_db(self, name, sig):
        row = self.db.execute("SELECT sig, fetched, data FROM cache_db WHERE name=?", (name,)).fetchone()
        return (json.loads(row["data"]), row["fetched"]) if row and row["sig"] == sig else (None, None)

    def cached_db_fetched(self, name):
        row = self.db.execute("SELECT fetched FROM cache_db WHERE name=?", (name,)).fetchone()
        return row["fetched"] if row else None

    def cached_db_any(self, name):
        row = self.db.execute("SELECT data FROM cache_db WHERE name=?", (name,)).fetchone()
        return json.loads(row["data"]) if row else None

    def put_db(self, name, sig, data):
        self.db.execute("INSERT OR REPLACE INTO cache_db VALUES(?,?,?,?)", (name, sig, time.time(), json.dumps(data, default=str)))

    # metadata config-table rows (masked), replaced as a whole on every metadata refresh
    def put_meta_rows(self, rows_by_table):
        self.db.execute("DELETE FROM meta_rows")
        for table, rows in rows_by_table.items():
            self.db.executemany("INSERT INTO meta_rows(tbl, data) VALUES(?,?)", [(table, json.dumps(r, default=str)) for r in rows])

    def get_meta_rows(self, exclude=None):
        out = {}
        for row in self.db.execute("SELECT tbl, data FROM meta_rows WHERE tbl IS NOT ? ORDER BY rowid", (exclude,)):
            out.setdefault(row["tbl"], []).append(json.loads(row["data"]))
        return out

    def get_structure_rows(self, table, parent_column, ids):
        """Snapshot rows of the structure table whose parent column is one of ids (compared as text)."""
        ids = [str(i) for i in ids if i is not None]
        if not ids:
            return []
        path = '$."' + parent_column.replace('"', '\\"') + '"'
        sql = (f"SELECT data FROM meta_rows WHERE tbl=? AND CAST(json_extract(data, ?) AS TEXT) IN ({','.join('?' * len(ids))}) "
               "ORDER BY rowid")
        return [json.loads(r["data"]) for r in self.db.execute(sql, (table, path, *ids))]

    def add_meta_changes(self, changes, ts=None, keep=50000):
        ts = ts or time.time()
        self.db.executemany("INSERT INTO meta_changes(ts, tbl, pk, link, change) VALUES(?,?,?,?,?)",
                            [(ts, c["tbl"], c["pk"], c["link"], c["change"]) for c in changes])
        self.db.execute("DELETE FROM meta_changes WHERE rowid NOT IN (SELECT rowid FROM meta_changes ORDER BY ts DESC LIMIT ?)", (keep,))

    def meta_changes_for(self, links, limit=20):
        links = [str(x) for x in links if x is not None]
        if not links:
            return []
        return self.db.execute(f"SELECT ts, tbl, pk, change FROM meta_changes WHERE link IN ({','.join('?' * len(links))}) "
                               "ORDER BY ts DESC, rowid DESC LIMIT ?", (*links, limit)).fetchall()

    def add_investigation(self, key, entries, ts=None, keep=20000):
        """The ranked causes of one investigation [(kind, signature, text)] - the memory behind learning suggestions."""
        ts = ts or time.time()
        self.db.executemany("INSERT INTO investigations(ts, key, rank, kind, signature, cause) VALUES(?,?,?,?,?,?)",
                            [(ts, key, n, kind, sig, text) for n, (kind, sig, text) in enumerate(entries, 1)])
        self.db.execute("DELETE FROM investigations WHERE rowid NOT IN (SELECT rowid FROM investigations ORDER BY ts DESC LIMIT ?)", (keep,))
        self.db.commit()

    def investigations_since(self, ts):
        return self.db.execute("SELECT ts, key, rank, kind, signature, cause FROM investigations WHERE ts >= ? ORDER BY ts", (ts,)).fetchall()

    def versioned_groups(self):
        """[(runtime instance id, path)] of version-controlled process groups (empty for KBs built by older versions)."""
        try:
            return [(r["instance_id"] or r["id"], r["path"]) for r in
                    self.db.execute("SELECT id, instance_id, path FROM groups WHERE version IS NOT NULL")]
        except sqlite3.Error:
            return []

    # NiFi log events (see logs.py)
    def add_log_events(self, events):
        import hashlib
        rows = []
        for e in events:
            h = hashlib.sha1(f"{e['ts']}|{e['thread']}|{e['message'][:300]}".encode("utf-8", "replace")).hexdigest()
            rows.append((h, e["ts"], e["epoch"], e["level"], e["thread"], e["logger"], e["component_type"], e["component_id"],
                         e["flowfile_uuid"], e["filename"], e["message"], e["cause"], e["template"], e["file"], e["line"]))
        before = self.db.total_changes
        self.db.executemany("INSERT OR IGNORE INTO log_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        return self.db.total_changes - before

    def prune_log_events(self, keep_days):
        newest = self.db.execute("SELECT MAX(epoch) FROM log_events").fetchone()[0]
        if newest:
            self.db.execute("DELETE FROM log_events WHERE epoch < ?", (newest - keep_days * 86400,))

    # snapshots + change log
    def last_snapshot(self):
        row = self.db.execute("SELECT data FROM snapshot ORDER BY id DESC LIMIT 1").fetchone()
        return json.loads(row["data"]) if row else None

    def add_snapshot(self, flow_sig, data, keep=20):
        self.db.execute("INSERT INTO snapshot(ts, flow_sig, data) VALUES(?,?,?)", (time.time(), flow_sig, json.dumps(data)))
        self.db.execute("DELETE FROM snapshot WHERE id NOT IN (SELECT id FROM snapshot ORDER BY id DESC LIMIT ?)", (keep,))

    def add_changes(self, changes, ts=None):
        ts = ts or time.time()
        self.db.executemany("INSERT INTO changelog(ts, change) VALUES(?,?)", [(ts, c) for c in changes])

    def changes(self, limit=300):
        return self.db.execute("SELECT ts, change FROM changelog ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    # derived facts
    def reset_derived(self):
        self.db.executescript(DERIVED)

    def insert(self, table, rows):
        rows = list(rows)
        if rows:
            cols = list(rows[0].keys())
            self.db.executemany(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                                [tuple(r[c] for c in cols) for r in rows])

    def search(self, query, limit=20):
        terms = [t for t in query.replace('"', " ").split() if t]
        if not terms:
            return []
        fts = " ".join(f'"{t}"*' for t in terms)
        try:
            return self.db.execute(
                "SELECT kind, ref, title, snippet(search, 3, '[', ']', '…', 12) AS snip, doc, bm25(search, 2.0, 5.0, 10.0, 1.0) AS score "
                "FROM search WHERE search MATCH ? ORDER BY score LIMIT ?", (fts, limit)).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query}%"
            return self.db.execute("SELECT kind, ref, title, substr(body,1,160) AS snip, doc, 0 AS score FROM search "
                                   "WHERE title LIKE ? OR body LIKE ? LIMIT ?", (like, like, limit)).fetchall()
