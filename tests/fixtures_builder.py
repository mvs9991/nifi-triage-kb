"""Builds a realistic multi-group test environment in a temp dir: flow.json.gz, custom NAR, SQLite metadata DB, config."""
import gzip
import io
import json
import sqlite3
import zipfile
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
SECRET_VALUES = ["abc123secret", "hunter2", "Sup3rS3cret!", "plainpass99", "varsecret77"]

ROOT, PG = "root-0000-0000", "pg-vendor-0000"
DBCP_INSTANCE = "dbcp-instance-1111"


def proc(pid, name, ptype, props=None, state="RUNNING", auto=(), bundle=None, group=ROOT, **kw):
    p = {"identifier": pid, "instanceIdentifier": f"inst-{pid}", "name": name, "type": ptype,
         "bundle": bundle or {"group": "org.apache.nifi", "artifact": "nifi-standard-nar", "version": "1.27.0"},
         "properties": props or {}, "scheduledState": state, "schedulingStrategy": kw.get("strategy", "TIMER_DRIVEN"),
         "schedulingPeriod": kw.get("period", "0 sec"), "concurrentlySchedulableTaskCount": kw.get("tasks", 1),
         "autoTerminatedRelationships": list(auto), "executionNode": kw.get("node", "ALL"), "comments": kw.get("comments", ""),
         "componentType": "PROCESSOR", "groupIdentifier": group}
    return p


def conn(cid, src, src_type, dst, dst_type, rels, group=ROOT, src_group=None, dst_group=None):
    return {"identifier": cid, "instanceIdentifier": f"inst-{cid}", "name": "",
            "source": {"id": src, "type": src_type, "groupId": src_group or group, "name": src},
            "destination": {"id": dst, "type": dst_type, "groupId": dst_group or group, "name": dst},
            "selectedRelationships": rels, "backPressureObjectThreshold": 10000, "backPressureDataSizeThreshold": "1 GB",
            "flowFileExpiration": "0 sec", "prioritizers": [], "loadBalanceStrategy": "DO_NOT_LOAD_BALANCE"}


def service(sid, name, stype, props, state="ENABLED", group=ROOT):
    return {"identifier": sid, "instanceIdentifier": f"instance-{sid}" if sid != "dbcp-1111" else DBCP_INSTANCE, "name": name, "type": stype,
            "bundle": {"group": "org.apache.nifi", "artifact": "nifi-dbcp-service-nar", "version": "1.27.0"},
            "properties": props, "scheduledState": state, "componentType": "CONTROLLER_SERVICE", "groupIdentifier": group}


ACME = {"group": "com.acme", "artifact": "acme-nifi-nar", "version": "1.0.0"}
JSON_SCHEMA = json.dumps({"type": "record", "name": "Audit", "fields": [
    {"name": "order_id", "type": "string"}, {"name": "vendor", "type": "string"},
    {"name": "status", "type": "string"}, {"name": "extra_field", "type": "string"}]})


def nested_flow(bucket="#{s3.bucket}"):
    vendor = {
        "identifier": PG, "instanceIdentifier": "inst-pg", "name": "Vendor JSON Ingestion", "comments": "Receives vendor orders as JSON",
        "parameterContextName": "vendor-params", "variables": {},
        "versionedFlowCoordinates": {"registryUrl": "http://registry:18080", "bucketId": "b1", "flowId": "f1", "version": 3},
        "processors": [
            proc("p-extract", "Extract fields", "org.apache.nifi.processors.standard.EvaluateJsonPath",
                 {"Destination": "flowfile-attribute", "order.id": "$.id", "vendor": "$.vendor"}, auto=["unmatched", "failure"], group=PG),
            proc("p-validate", "Validate order", "com.acme.nifi.ValidateOrderJson",
                 {"Validation URL": "https://validator.acme.com/api/v1/check", "Api Token": "abc123secret"}, bundle=ACME, group=PG),
            proc("p-s3", "Store raw JSON", "org.apache.nifi.processors.aws.s3.PutS3Object",
                 {"Bucket": bucket, "Object Key": "${vendor}/${filename}", "Region": "us-east-1", "Secret Access Key": "#{aws.secret}"},
                 auto=["failure"], group=PG,
                 bundle={"group": "org.apache.nifi", "artifact": "nifi-aws-nar", "version": "1.27.0"}),
            proc("p-rejects", "Write rejects", "org.apache.nifi.processors.standard.PutFile",
                 {"Directory": "#{reject.dir}/rejects", "Conflict Resolution Strategy": "replace"}, auto=["success", "failure"], group=PG),
        ],
        "inputPorts": [{"identifier": "in-port", "instanceIdentifier": "inst-in", "name": "orders in", "scheduledState": "RUNNING",
                        "componentType": "INPUT_PORT", "groupIdentifier": PG}],
        "outputPorts": [{"identifier": "out-port", "instanceIdentifier": "inst-out", "name": "stored", "scheduledState": "RUNNING",
                         "componentType": "OUTPUT_PORT", "groupIdentifier": PG}],
        "connections": [
            conn("c1", "in-port", "INPUT_PORT", "p-extract", "PROCESSOR", [], group=PG),
            conn("c2", "p-extract", "PROCESSOR", "p-validate", "PROCESSOR", ["matched"], group=PG),
            conn("c3", "p-validate", "PROCESSOR", "p-s3", "PROCESSOR", ["valid"], group=PG),
            conn("c4", "p-validate", "PROCESSOR", "p-rejects", "PROCESSOR", ["invalid"], group=PG),
            conn("c5", "p-s3", "PROCESSOR", "out-port", "OUTPUT_PORT", ["success"], group=PG),
        ],
        "controllerServices": [], "labels": [{"label": "Validation is done by the ACME custom processor", "componentType": "LABEL"}],
        "funnels": [], "processGroups": [], "remoteProcessGroups": [],
    }
    root = {
        "identifier": ROOT, "instanceIdentifier": "inst-root", "name": "NiFi Flow", "comments": "",
        "variables": {"base.dir": "/data/landing", "etl.password": "varsecret77"},
        "processors": [
            proc("p-listen", "Receive orders API", "org.apache.nifi.processors.standard.ListenHTTP",
                 {"Listening Port": "8081", "Base Path": "orders"}),
            proc("p-audit", "Write audit row", "org.apache.nifi.processors.standard.PutDatabaseRecord",
                 {"put-db-record-record-reader": "instance-reader-1", "put-db-record-dcbp-service": DBCP_INSTANCE,
                  "put-db-record-statement-type": "INSERT", "put-db-record-table-name": "file_audit",
                  "put-db-record-unmatched-field-behavior": "Fail on Unmatched Fields"}, auto=["success", "failure", "retry"]),
            proc("p-archive", "Archive order", "org.apache.nifi.processors.standard.PutDatabaseRecord",
                 {"put-db-record-record-reader": "instance-reader-1", "put-db-record-dcbp-service": DBCP_INSTANCE,
                  "put-db-record-statement-type": "INSERT", "put-db-record-table-name": "order_archive"}, auto=["success", "failure", "retry"]),
            proc("p-lookup", "Lookup customer", "org.apache.nifi.processors.standard.ExecuteSQL",
                 {"Database Connection Pooling Service": DBCP_INSTANCE,
                  "SQL select query": "SELECT c.id, c.name FROM customers c JOIN orders o ON o.cust_id = c.id WHERE o.id = '${order.id}'"},
                 auto=["failure"]),
            proc("p-enrich", "Enrich via python", "org.apache.nifi.processors.standard.ExecuteStreamCommand",
                 {"Command Path": "python", "Command Arguments": "${base.dir}/scripts/enrich.py ${order.id}"}, auto=["original", "nonzero status"]),
            proc("p-gen", "Nightly trigger", "org.apache.nifi.processors.standard.GenerateFlowFile", {}, state="DISABLED",
                 strategy="CRON_DRIVEN", period="0 0 2 * * ?"),
        ],
        "inputPorts": [], "outputPorts": [], "funnels": [], "remoteProcessGroups": [], "labels": [],
        "connections": [
            conn("r1", "p-listen", "PROCESSOR", "in-port", "INPUT_PORT", ["success"], dst_group=PG),
            conn("r2", "out-port", "OUTPUT_PORT", "p-audit", "PROCESSOR", [], src_group=PG),
            conn("r3", "out-port", "OUTPUT_PORT", "p-lookup", "PROCESSOR", [], src_group=PG),
            conn("r4", "p-lookup", "PROCESSOR", "p-enrich", "PROCESSOR", ["success"]),
            conn("r5", "p-enrich", "PROCESSOR", "p-archive", "PROCESSOR", ["output stream"]),
            conn("r6", "p-gen", "PROCESSOR", "p-lookup", "PROCESSOR", ["success"]),
        ],
        "controllerServices": [
            service("dbcp-1111", "MetaDB", "org.apache.nifi.dbcp.DBCPConnectionPool", {
                "Database Connection URL": "jdbc:mariadb://dbhost.acme.com:3306/meta", "Database Driver Class Name": "org.mariadb.jdbc.Driver",
                "Database User": "nifi_rw", "Password": "enc{0123456789abcdef}"}),
            service("reader-1", "AuditJsonReader", "org.apache.nifi.json.JsonTreeReader", {
                "schema-access-strategy": "schema-text-property", "schema-text": JSON_SCHEMA}),
            service("writer-unused", "UnusedWriter", "org.apache.nifi.json.JsonRecordSetWriter", {}, state="DISABLED"),
        ],
        "processGroups": [vendor],
    }
    return {
        "encodingVersion": {"majorVersion": 2, "minorVersion": 0},
        "parameterContexts": [{
            "name": "vendor-params", "inheritedParameterContexts": ["shared-params"],
            "parameters": [{"name": "s3.bucket", "value": "acme-orders-raw", "sensitive": False},
                           {"name": "aws.secret", "value": "enc{ffff}", "sensitive": True},
                           {"name": "db.password", "value": "plainpass99", "sensitive": False}]},
            {"name": "shared-params", "parameters": [{"name": "reject.dir", "value": "/data/shared", "sensitive": False}]}],
        "controllerServices": [], "reportingTasks": [], "rootGroup": root,
    }


NESTED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<flowController encoding-version="1.4">
  <parameterContexts>
    <parameterContext><id>ctx-1</id><name>file-params</name>
      <parameter><name>landing</name><value>/data/in</value><sensitive>false</sensitive></parameter>
    </parameterContext>
  </parameterContexts>
  <rootGroup>
    <id>r</id><name>NiFi Flow</name>
    <processor><id>x-list</id><name>List landing</name><class>org.apache.nifi.processors.standard.ListFile</class>
      <bundle><group>org.apache.nifi</group><artifact>nifi-standard-nar</artifact><version>1.19.1</version></bundle>
      <maxConcurrentTasks>1</maxConcurrentTasks><schedulingPeriod>1 min</schedulingPeriod><scheduledState>RUNNING</scheduledState>
      <schedulingStrategy>TIMER_DRIVEN</schedulingStrategy>
      <property><name>Input Directory</name><value>/data/in/files</value></property>
      <property><name>File Filter</name></property>
    </processor>
    <processGroup><id>g1</id><name>File Ingestion</name><parameterContextId>ctx-1</parameterContextId>
      <inputPort><id>g1-in</id><name>files</name><scheduledState>RUNNING</scheduledState></inputPort>
      <processor><id>x-fetch</id><name>Fetch it</name><class>org.apache.nifi.processors.standard.FetchFile</class>
        <bundle><group>org.apache.nifi</group><artifact>nifi-standard-nar</artifact><version>1.19.1</version></bundle>
        <maxConcurrentTasks>2</maxConcurrentTasks><schedulingPeriod>0 sec</schedulingPeriod><scheduledState>STOPPED</scheduledState>
        <schedulingStrategy>TIMER_DRIVEN</schedulingStrategy>
        <property><name>File to Fetch</name><value>#{landing}/${filename}</value></property>
        <autoTerminatedRelationship>failure</autoTerminatedRelationship>
        <autoTerminatedRelationship>success</autoTerminatedRelationship>
      </processor>
      <connection><id>gc1</id><sourceId>g1-in</sourceId><sourceGroupId>g1</sourceGroupId><sourceType>INPUT_PORT</sourceType>
        <destinationId>x-fetch</destinationId><destinationGroupId>g1</destinationGroupId><destinationType>PROCESSOR</destinationType></connection>
      <variable name="region" value="eu"/>
    </processGroup>
    <connection><id>rc1</id><sourceId>x-list</sourceId><sourceGroupId>r</sourceGroupId><sourceType>PROCESSOR</sourceType>
      <destinationId>g1-in</destinationId><destinationGroupId>g1</destinationGroupId><destinationType>INPUT_PORT</destinationType>
      <relationship>success</relationship></connection>
  </rootGroup>
  <controllerServices/>
</flowController>
"""

ACME_MANIFEST = """<extensionManifest><groupId>com.acme</groupId><artifactId>acme-nifi-nar</artifactId><version>1.0.0</version><extensions>
<extension><name>com.acme.nifi.ValidateOrderJson</name><type>PROCESSOR</type>
<description>Validates vendor order JSON (from NAR manifest).</description><tags><tag>acme</tag></tags>
<properties>
 <property><name>Validation URL</name><displayName>Validation URL</displayName><description>Endpoint</description>
  <defaultValue>https://validator.acme.com/api/v1/check</defaultValue><required>true</required><sensitive>false</sensitive></property>
 <property><name>Api Token</name><displayName>API Token</displayName><description>Token</description><required>false</required><sensitive>false</sensitive></property>
</properties>
<relationships><relationship><name>valid</name><description>ok</description><autoTerminated>false</autoTerminated></relationship>
<relationship><name>invalid</name><description>bad</description><autoTerminated>false</autoTerminated></relationship>
<relationship><name>failure</name><description>error</description><autoTerminated>false</autoTerminated></relationship></relationships>
<inputRequirement>INPUT_REQUIRED</inputRequirement>
</extension></extensions></extensionManifest>"""


STD_MANIFEST = """<extensionManifest><groupId>org.apache.nifi</groupId><artifactId>nifi-standard-nar</artifactId><version>1.27.0</version><extensions>
<extension><name>org.apache.nifi.processors.standard.GenerateFlowFile</name><type>PROCESSOR</type><description>Generates FlowFiles</description>
 <properties><property><name>File Size</name><displayName>File Size</displayName><defaultValue>0B</defaultValue><required>true</required><sensitive>false</sensitive></property></properties>
 <dynamicProperties><dynamicProperty><name>attribute</name><value>value</value><description>Adds an attribute</description></dynamicProperty></dynamicProperties>
 <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship></relationships>
 <writesAttributes><writesAttribute><name>mime.type</name></writesAttribute></writesAttributes><inputRequirement>INPUT_FORBIDDEN</inputRequirement></extension>
<extension><name>org.apache.nifi.processors.attributes.UpdateAttribute</name><type>PROCESSOR</type><description>Updates attributes</description>
 <properties><property><name>Delete Attributes Expression</name><displayName>Delete Attributes Expression</displayName><required>false</required><sensitive>false</sensitive></property></properties>
 <dynamicProperties><dynamicProperty><name>attribute</name><value>value</value><description>Sets an attribute</description></dynamicProperty></dynamicProperties>
 <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship></relationships>
 <inputRequirement>INPUT_REQUIRED</inputRequirement></extension>
<extension><name>org.apache.nifi.processors.standard.PutDatabaseRecord</name><type>PROCESSOR</type><description>Writes records</description>
 <properties>
  <property><name>put-db-record-table-name</name><displayName>Table Name</displayName><required>true</required><sensitive>false</sensitive><expressionLanguageScope>FLOWFILE_ATTRIBUTES</expressionLanguageScope></property>
  <property><name>put-db-record-catalog-name</name><displayName>Catalog Name</displayName><required>false</required><sensitive>false</sensitive></property>
  <property><name>put-db-record-dcbp-service</name><displayName>Database Connection Pooling Service</displayName><required>true</required><sensitive>false</sensitive><controllerServiceDefinition><className>org.apache.nifi.dbcp.DBCPService</className></controllerServiceDefinition></property>
  <property><name>put-db-record-record-reader</name><displayName>Record Reader</displayName><required>true</required><sensitive>false</sensitive><controllerServiceDefinition><className>org.apache.nifi.serialization.RecordReaderFactory</className></controllerServiceDefinition></property>
 </properties>
 <relationships><relationship><name>success</name><description>ok</description><autoTerminated>false</autoTerminated></relationship>
  <relationship><name>failure</name><description>bad</description><autoTerminated>false</autoTerminated></relationship>
  <relationship><name>retry</name><description>again</description><autoTerminated>false</autoTerminated></relationship></relationships>
 <writesAttributes><writesAttribute><name>putdatabaserecord.error</name></writesAttribute></writesAttributes><inputRequirement>INPUT_REQUIRED</inputRequirement></extension>
</extensions></extensionManifest>"""


def lineage_flow():
    """Metadata lookup -> UpdateAttribute -> PutDatabaseRecord with one misnamed and one never-set attribute."""
    flow = metadata_flow()
    std = {"group": "org.apache.nifi", "artifact": "nifi-standard-nar", "version": "1.27.0"}
    flow["rootGroup"]["processors"] += [
        proc("l-gen", "Poll landing", "org.apache.nifi.processors.standard.GenerateFlowFile", {"File Size": "0B"}, bundle=std),
        proc("l-meta", "Lookup file metadata", "com.acme.meta.MetadataLookup", {"Object Key": "${filename}", "metadata-db": DBCP_INSTANCE},
             bundle={"group": "com.acme", "artifact": "acme-meta-nar", "version": "2.0.0"}, auto=["not found", "failure"]),
        proc("l-ua", "Set target", "org.apache.nifi.processors.attributes.UpdateAttribute",
             {"target.table": "${tableName}", "load.mode": "${mode:isEmpty():ifElse('full', ${mode})}"},
             bundle=dict(std, artifact="nifi-update-attribute-nar")),
        proc("l-put", "Load table", "org.apache.nifi.processors.standard.PutDatabaseRecord",
             {"put-db-record-table-name": "${target.table}", "put-db-record-catalog-name": "${target_catalog}",
              "put-db-record-dcbp-service": DBCP_INSTANCE, "put-db-record-record-reader": "instance-reader-1"},
             bundle=std, auto=["success", "failure", "retry"]),
    ]
    flow["rootGroup"]["connections"] += [conn("l1", "l-gen", "PROCESSOR", "l-meta", "PROCESSOR", ["success"]),
                                         conn("l2", "l-meta", "PROCESSOR", "l-ua", "PROCESSOR", ["success"]),
                                         conn("l3", "l-ua", "PROCESSOR", "l-put", "PROCESSOR", ["success"])]
    return flow


class FakeNiFi:
    """A NiFi REST API stand-in (login, provenance query lifecycle, event details, bulletins, about) built from the
    documented request / response shapes. Runtime ids are the fixture's instance ids (inst-<id>)."""

    EVENTS = [
        {"id": "11", "eventId": 11, "eventTime": "09/26/2026 10:15:01.100 UTC", "eventType": "RECEIVE", "flowFileUuid": "u-1",
         "filename": "orders_0926.json", "componentId": "inst-p-listen", "componentName": "Receive orders API",
         "componentType": "ListenHTTP", "transitUri": "http://0.0.0.0:8081/orders", "childUuids": [], "details": None},
        {"id": "12", "eventId": 12, "eventTime": "09/26/2026 10:15:01.300 UTC", "eventType": "ATTRIBUTES_MODIFIED",
         "flowFileUuid": "u-1", "filename": "orders_0926.json", "componentId": "inst-p-extract", "componentName": "Extract fields",
         "componentType": "EvaluateJsonPath", "childUuids": []},
        {"id": "13", "eventId": 13, "eventTime": "09/26/2026 10:15:02.000 UTC", "eventType": "ROUTE", "flowFileUuid": "u-1",
         "filename": "orders_0926.json", "componentId": "inst-p-validate", "componentName": "Validate order",
         "componentType": "ValidateOrderJson", "relationship": "invalid", "childUuids": []},
        {"id": "14", "eventId": 14, "eventTime": "09/26/2026 10:15:02.200 UTC", "eventType": "DROP", "flowFileUuid": "u-1",
         "filename": "orders_0926.json", "componentId": "inst-p-rejects", "componentName": "Write rejects",
         "componentType": "PutFile", "details": "Auto-Terminated by failure Relationship", "childUuids": []},
        {"id": "21", "eventId": 21, "eventTime": "09/26/2026 11:00:00.000 UTC", "eventType": "RECEIVE", "flowFileUuid": "u-2",
         "filename": "late.json", "componentId": "inst-p-listen", "componentName": "Receive orders API", "componentType": "ListenHTTP",
         "childUuids": []},
        {"id": "22", "eventId": 22, "eventTime": "09/26/2026 12:00:00.000 UTC", "eventType": "DROP", "flowFileUuid": "u-2",
         "filename": "late.json", "componentId": "inst-p-audit", "componentName": "Write audit row", "componentType": "PutDatabaseRecord",
         "details": "FlowFile Expired", "childUuids": []},
    ]
    ATTRS = {"14": [{"name": "validation.status", "value": "INVALID", "previousValue": None},
                    {"name": "validation.error", "value": "vendor missing", "previousValue": None},
                    {"name": "api.token", "value": "tok-SECRET-9", "previousValue": "tok-SECRET-9"},
                    {"name": "vendor", "value": "", "previousValue": ""}]}

    def __init__(self, user="admin", password="pw123456789"):
        import http.server
        import threading
        import urllib.parse
        fake = self
        self.queries, self.deleted, self.calls = {}, [], []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, obj=None, text=None):
                body = (text if text is not None else json.dumps(obj)).encode()
                self.send_response(code)
                self.send_header("Content-Type", "text/plain" if text is not None else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _authed(self):
                want = "Bearer reg-tok" if self.path.startswith("/nifi-registry-api/") else "Bearer tok-123"
                return self.headers.get("Authorization") == want

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n).decode()
                fake.calls.append(("POST", self.path))
                if self.path == "/nifi-registry-api/access/token/login":
                    ok = self.headers.get("Authorization") == "Basic " + __import__("base64").b64encode(f"{user}:{password}".encode()).decode()
                    return self._send(201, text="reg-tok") if ok else self._send(401, text="bad")
                if self.path == "/nifi-api/access/token":
                    form = dict(urllib.parse.parse_qsl(raw))
                    return self._send(201, text="tok-123") if form == {"username": user, "password": password} else self._send(401, text="bad")
                if not self._authed():
                    return self._send(401, text="unauthorized")
                if self.path == "/nifi-api/provenance":
                    terms = json.loads(raw)["provenance"]["request"]["searchTerms"]
                    qid = f"q{len(fake.queries) + 1}"
                    fake.queries[qid] = {k: v["value"] for k, v in terms.items()}
                    return self._send(201, {"provenance": {"id": qid, "finished": False}})
                self._send(404, text="nope")

            def do_GET(self):
                fake.calls.append(("GET", self.path))
                if not self._authed():
                    return self._send(401, text="unauthorized")
                if self.path.startswith("/nifi-api/provenance/"):
                    terms = fake.queries[self.path.rsplit("/", 1)[1]]
                    key = {"Filename": "filename", "FlowFileUUID": "flowFileUuid", "ProcessorID": "componentId"}
                    evs = [e for e in fake.EVENTS if all(e.get(key[k]) == v for k, v in terms.items())]
                    return self._send(200, {"provenance": {"finished": True, "results": {"provenanceEvents": evs}}})
                if self.path.startswith("/nifi-api/provenance-events/"):
                    eid = self.path.rsplit("/", 1)[1]
                    ev = dict(next(e for e in fake.EVENTS if e["id"] == eid), attributes=fake.ATTRS.get(eid, []))
                    return self._send(200, {"provenanceEvent": ev})
                if self.path.startswith("/nifi-api/flow/bulletin-board"):
                    return self._send(200, {"bulletinBoard": {"bulletins": [{"bulletin": {
                        "level": "ERROR", "sourceId": "inst-p-audit", "sourceName": "Write audit row", "timestamp": "10:15:02 UTC",
                        "message": "Failed to put Records to database: Table file_audit not found"}}]}})
                if self.path == "/nifi-api/versions/process-groups/inst-pg":
                    return self._send(200, {"versionControlInformation": {"groupId": "inst-pg", "flowName": "vendor-json", "version": 3,
                                                                          "state": "STALE", "stateExplanation": "A newer version (4) is available"}})
                if self.path == "/nifi-registry-api/buckets/b1/flows/f1/versions":
                    return self._send(200, [{"version": 3, "timestamp": 1789900000000, "author": "bob", "comments": "add order validation"},
                                            {"version": 4, "timestamp": 1790000000000, "author": "alice", "comments": "switch vendor to API v2"}])
                if self.path == "/nifi-api/flow/about":
                    return self._send(200, {"about": {"title": "NiFi", "version": "1.27.0"}})
                if self.path.startswith("/nifi-api/flow/process-groups/root/status"):
                    proc = lambda pid, name, typ, st: {"processorStatusSnapshot": {"id": pid, "name": name, "type": typ, "runStatus": st,
                                                                                    "flowFilesIn": 0}}
                    conn = lambda cid, s, sn, d, dn, n, pct: {"connectionStatusSnapshot": {
                        "id": cid, "sourceId": s, "sourceName": sn, "destinationId": d, "destinationName": dn,
                        "queuedCount": n, "queued": f"{n} (1 MB)", "percentUseCount": pct, "percentUseBytes": "1"}}
                    vendor = {"name": "Vendor JSON Ingestion",
                              "processorStatusSnapshots": [proc("inst-p-validate", "Validate order", "ValidateOrderJson", "Running"),
                                                           proc("inst-p-rejects", "Write rejects", "PutFile", "Stopped")],
                              "connectionStatusSnapshots": [conn("c2", "inst-p-extract", "Extract fields", "inst-p-validate", "Validate order",
                                                                 "10,000", "100"),
                                                            conn("c4", "inst-p-validate", "Validate order", "inst-p-rejects", "Write rejects",
                                                                 "5", "0")]}
                    root = {"name": "NiFi Flow",
                            "processorStatusSnapshots": [proc("inst-p-archive", "Archive order", "PutDatabaseRecord", "Invalid"),
                                                         proc("inst-p-audit", "Write audit row", "PutDatabaseRecord", "Running")],
                            "connectionStatusSnapshots": [conn("r5", "inst-p-enrich", "Enrich via python", "inst-p-archive", "Archive order",
                                                               "0", "0")],
                            "processGroupStatusSnapshots": [{"processGroupStatusSnapshot": vendor}]}
                    return self._send(200, {"processGroupStatus": {"aggregateSnapshot": root}})
                if self.path == "/nifi-api/processors/inst-p-archive":
                    return self._send(200, {"component": {"id": "inst-p-archive", "validationErrors": [
                        "'Table Name' validated against 'order_archive' is invalid because table does not exist"]}})
                if self.path.startswith("/nifi-api/flow/process-groups/root/controller-services"):
                    return self._send(200, {"controllerServices": [
                        {"component": {"id": "instance-reader-1", "name": "AuditJsonReader", "state": "ENABLED"}},
                        {"component": {"id": "instance-writer-unused", "name": "UnusedWriter", "state": "DISABLED"}}]})
                if self.path == "/nifi-api/system-diagnostics":
                    return self._send(200, {"systemDiagnostics": {"aggregateSnapshot": {
                        "heapUtilization": "91.0%", "contentRepositoryStorageUsage": [
                            {"identifier": "default", "utilization": "96.0%", "usedSpace": "96 GB", "totalSpace": "100 GB"}],
                        "flowFileRepositoryStorageUsage": {"utilization": "20.0%"}}}})
                if self.path == "/nifi-api/flow/cluster/summary":
                    return self._send(200, {"clusterSummary": {"clustered": True, "connectedNodeCount": 2, "totalNodeCount": 3}})
                self._send(404, text="nope")

            def do_DELETE(self):
                fake.deleted.append(self.path)
                self._send(200, {})

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/nifi-api"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def make_nar(path, manifest_xml=None, group="com.acme", artifact="acme-nifi-nar", service_classes=()):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nNar-Group: {group}\nNar-Id: {artifact}\nNar-Version: 1.0.0\n")
        if manifest_xml:
            z.writestr("META-INF/docs/extension-manifest.xml", manifest_xml)
        if service_classes:
            jar = io.BytesIO()
            with zipfile.ZipFile(jar, "w") as j:
                j.writestr("META-INF/services/org.apache.nifi.processor.Processor", "\n".join(service_classes) + "\n")
            z.writestr(f"META-INF/bundled-dependencies/{artifact}-1.0.0.jar", jar.getvalue())


def make_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE file_audit(id INTEGER PRIMARY KEY, order_id TEXT NOT NULL, vendor TEXT, status TEXT,
                                received_at TEXT NOT NULL, user_email TEXT);
        CREATE TABLE customers(id INTEGER PRIMARY KEY, name TEXT, region TEXT);
        CREATE TABLE orders(id TEXT PRIMARY KEY, cust_id INTEGER REFERENCES customers(id), total REAL);
        CREATE TABLE file_calls(id INTEGER PRIMARY KEY, source_system TEXT, status TEXT, file_name TEXT);
        CREATE TABLE unrelated(x INTEGER);
        CREATE INDEX ix_audit_order ON file_audit(order_id);
        INSERT INTO file_calls(source_system, status, file_name) VALUES ('vendorA','LOADED','a.json'), ('vendorA','FAILED','b.json'),
                                                                     ('vendorB','LOADED','c.json');
        INSERT INTO file_audit(order_id, vendor, status, received_at, user_email) VALUES ('o1','vendorA','OK','2026-01-01','x@y.com');
    """)
    db.commit()
    db.close()


API_TOKEN = "abcdefghijklmnop1234"
METADATA_SQL = """
    CREATE TABLE OBJ_DEFINITION(OBJ_ID INTEGER PRIMARY KEY, FILE_NAME TEXT, TABLE_NAME TEXT, SOURCE_SYSTEM TEXT, DELIMITER TEXT, ACTIVE_FLAG TEXT);
    CREATE TABLE OBJ_STRUCTURE(STRUCT_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER REFERENCES OBJ_DEFINITION(OBJ_ID), COL_NAME TEXT,
                               DATA_TYPE TEXT, COL_SEQ INTEGER, COL_LENGTH INTEGER, MANDATORY_FLAG TEXT, JSON_PATH TEXT);
    CREATE TABLE SOURCE_FEED_CONFIG(FEED_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, FEED_NAME TEXT, SFTP_HOST TEXT, SFTP_USER TEXT,
                                    SFTP_PASSWORD TEXT, REMOTE_DIR TEXT);
    CREATE TABLE NIFI_JSON_API_CONFIG(API_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, API_NAME TEXT, API_URL TEXT, AUTH_HEADER TEXT,
                                      JSON_ROOT_PATH TEXT, REQUEST_TEMPLATE TEXT);
    CREATE TABLE stg_sales(order_no INTEGER NOT NULL, cust_name VARCHAR(20), amount DECIMAL(10,2), order_dt DATE, region VARCHAR(10),
                           load_ts TEXT NOT NULL);
    CREATE TABLE stg_customers(cust_id INTEGER PRIMARY KEY, name VARCHAR(100), email VARCHAR(200));
    CREATE TABLE stg_orders(order_id INTEGER NOT NULL, customer_name VARCHAR(100), amount DECIMAL(10,2));
    CREATE TABLE FILE_LOAD_AUDIT(AUDIT_ID INTEGER PRIMARY KEY, OBJ_ID INTEGER, FILE_NAME TEXT, LOAD_STATUS TEXT, LOAD_TS TEXT,
                                 ERROR_MSG TEXT, ROW_COUNT INTEGER);
    INSERT INTO FILE_LOAD_AUDIT VALUES (1, 1, '/landing/pos/SALES_20260925.csv', 'SUCCESS', '2026-09-25 02:10:00', NULL, 1200),
                                       (2, 1, '/landing/pos/SALES_20260926.csv', 'FAILED', '2026-09-26 02:14:00',
                                        'Column count mismatch at line 12: expected 5, found 6', 0);
    INSERT INTO OBJ_DEFINITION VALUES (1, 'SALES_YYYYMMDD.csv', 'stg_sales', 'POS', ',', 'Y'),
                                      (2, 'customers_*.json', 'stg_customers', 'CRM', NULL, 'Y'),
                                      (3, 'returns.csv', 'stg_returns', 'POS', ',', 'Y'),
                                      (4, 'orders_api', 'stg_orders', 'SHOP', NULL, 'Y');
    INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG) VALUES
        (1, 'ORDER_NO', 'INTEGER', 1, NULL, 'Y'), (1, 'CUST_NAME', 'VARCHAR', 2, 50, 'N'), (1, 'AMOUNT', 'VARCHAR', 3, 20, 'N'),
        (1, 'ORDER_DT', 'DATE', 4, NULL, 'N'), (1, 'REGION', 'VARCHAR', 5, 10, 'N'),
        (2, 'CUST_ID', 'INT', 1, NULL, 'Y'), (2, 'NAME', 'VARCHAR', 2, 100, 'N'), (2, 'EMAIL', 'VARCHAR', 3, 200, 'N'),
        (3, 'RET_ID', 'INT', 1, NULL, 'Y');
    INSERT INTO OBJ_STRUCTURE(OBJ_ID, COL_NAME, DATA_TYPE, COL_SEQ, COL_LENGTH, MANDATORY_FLAG, JSON_PATH) VALUES
        (4, 'ORDER_ID', 'INT', 1, NULL, 'Y', '$.orders[*].id'), (4, 'CUSTOMER_NAME', 'VARCHAR', 2, 100, 'N', '$.orders[*].customer.name'),
        (4, 'AMOUNT', 'DECIMAL', 3, NULL, 'N', '$.orders[*].amount');
    INSERT INTO SOURCE_FEED_CONFIG VALUES (10, 1, 'pos_sales_feed', 'sftp.pos.acme.com', 'nifi', 'Sup3rS3cret!', '/outbound/sales');
    INSERT INTO NIFI_JSON_API_CONFIG VALUES (20, 2, 'crm_customers_api', 'https://crm.acme.com/api/v2/customers',
                                             'Bearer abcdefghijklmnop1234', '$.data', '{"client": "nifi", "password": "hunter2"}'),
                                            (21, 4, 'orders_api', 'https://shop.acme.com/api/orders', 'Bearer qrstuvwxyz987654321', '$.orders', NULL);
"""


METADATA_BASE = """package com.acme.meta.base;

import org.apache.nifi.components.PropertyDescriptor;
import org.apache.nifi.dbcp.DBCPService;
import org.apache.nifi.processor.AbstractProcessor;
import org.apache.nifi.processor.Relationship;

/** Shared base of all ACME metadata processors. */
public abstract class AbstractMetadataProcessor extends AbstractProcessor {

    public static final PropertyDescriptor METADATA_DB = new PropertyDescriptor.Builder()
            .name(MetaConstants.PROP_METADATA_DB)
            .displayName("Metadata DB")
            .description("Connection pool for the OBJ_* config tables")
            .identifiesControllerService(DBCPService.class)
            .required(true)
            .build();

    public static final Relationship REL_FAILURE = new Relationship.Builder()
            .name("failure").description("Lookup failed").build();
}
"""
METADATA_CONSTANTS = """package com.acme.meta.base;

public interface MetaConstants {
    String PROP_METADATA_DB = "metadata-db";
    String ATTR_TABLE = "table_name";
    String ATTR_STRUCTURE = "structure.json";
}
"""
METADATA_PROCESSOR = """package com.acme.meta;

import com.acme.meta.base.AbstractMetadataProcessor;
import com.acme.meta.base.MetaConstants;
import org.apache.nifi.annotation.behavior.WritesAttribute;
import org.apache.nifi.annotation.behavior.WritesAttributes;
import org.apache.nifi.annotation.documentation.CapabilityDescription;
import org.apache.nifi.annotation.documentation.Tags;
import org.apache.nifi.components.AllowableValue;
import org.apache.nifi.components.PropertyDescriptor;
import org.apache.nifi.flowfile.attributes.CoreAttributes;
import org.apache.nifi.processor.Relationship;
import org.apache.nifi.processor.exception.ProcessException;

@Tags({"acme", "metadata"})
@CapabilityDescription("Looks up the object definition; structure and feed config for the incoming file and writes them as attributes.")
@WritesAttributes({
        @WritesAttribute(attribute = "table_name", description = "Target table from OBJ_DEFINITION"),
        @WritesAttribute(attribute = "structure.json", description = "Columns from OBJ_STRUCTURE")})
public class MetadataLookup extends AbstractMetadataProcessor {

    private static final String REL_NOT_FOUND_NAME = "not found";
    static final AllowableValue BY_FILE = new AllowableValue("by-file", "By file name", "Match FILE_NAME patterns");
    static final AllowableValue BY_FEED = new AllowableValue("by-feed", "By feed name", "Match SOURCE_FEED_CONFIG.FEED_NAME");

    public static final PropertyDescriptor OBJECT_KEY = new PropertyDescriptor.Builder()
            .name("Object Key").description("File name or feed name to look up").required(true)
            .expressionLanguageSupported(ExpressionLanguageScope.FLOWFILE_ATTRIBUTES).build();

    public static final PropertyDescriptor METADATA_SERVICE = new PropertyDescriptor.Builder()
            .name("metadata-service").displayName("Metadata Service").identifiesControllerService(MetadataService.class).build();

    public static final PropertyDescriptor LOOKUP_MODE = new PropertyDescriptor.Builder()
            .name("lookup-mode").displayName("Lookup Mode").allowableValues(BY_FILE, BY_FEED)
            .defaultValue(BY_FILE.getValue()).build();

    public static final Relationship REL_SUCCESS = new Relationship.Builder().name("success").description("found").build();
    public static final Relationship REL_NOT_FOUND = new Relationship.Builder().name(REL_NOT_FOUND_NAME).description("no definition").build();

    private final MetadataDao dao = new MetadataDao();

    @Override
    public void onTrigger(ProcessContext context, ProcessSession session) {
        FlowFile flowFile = session.get();
        String fileName = flowFile.getAttribute(CoreAttributes.FILENAME.key());
        Definition def = dao.load(fileName);
        if (def == null) {
            getLogger().error("No OBJ_DEFINITION row for file {}", new Object[]{fileName});
            session.transfer(flowFile, REL_NOT_FOUND);
            return;
        }
        if (!def.matches()) {
            throw new ProcessException("Structure mismatch for " + fileName + " against OBJ_STRUCTURE");
        }
        Map<String, String> attrs = new HashMap<>();
        attrs.put(MetaConstants.ATTR_TABLE, def.getTable());
        attrs.put(MetaConstants.ATTR_STRUCTURE, def.getColumnsJson());
        attrs.put("delimiter", def.getDelimiter());
        flowFile = session.putAllAttributes(flowFile, attrs);
        session.transfer(flowFile, REL_SUCCESS);
    }
}
"""
METADATA_SERVICE_API = """package com.acme.meta;

import org.apache.nifi.controller.ControllerService;

public interface MetadataService extends ControllerService {
    Definition find(String fileName);
}
"""
METADATA_SERVICE_IMPL = """package com.acme.meta;

import org.apache.nifi.annotation.documentation.CapabilityDescription;
import org.apache.nifi.controller.AbstractControllerService;

@CapabilityDescription("Caches OBJ_DEFINITION rows")
public class CachingMetadataService extends AbstractControllerService implements MetadataService {
}
"""
MOCK_TEST_PROCESSOR = """package com.acme.meta;

import org.apache.nifi.processor.AbstractProcessor;

public class MockUpstream extends AbstractProcessor {
}
"""
UNREGISTERED_PROCESSOR = """package com.acme.meta;

import com.acme.meta.base.AbstractMetadataProcessor;

public class LegacyMetadataLookup extends AbstractMetadataProcessor {
}
"""
PROCESSORS_POM = """<project><parent><groupId>com.acme</groupId><artifactId>acme-meta</artifactId><version>2.0.0</version></parent>
<artifactId>acme-meta-processors</artifactId><packaging>jar</packaging>
<dependencies><dependency><groupId>org.apache.nifi</groupId><artifactId>nifi-api</artifactId></dependency></dependencies></project>"""
NAR_POM = """<project><parent><groupId>com.acme</groupId><artifactId>acme-meta</artifactId><version>2.0.0</version></parent>
<artifactId>acme-meta-nar</artifactId><packaging>nar</packaging>
<dependencies><dependency><groupId>com.acme</groupId><artifactId>acme-meta-processors</artifactId><version>2.0.0</version></dependency></dependencies></project>"""


def class_file(name, strings):
    """A minimal valid .class file whose constant pool holds `strings` as string literals (no JDK needed)."""
    import struct
    pool, count = b"", 1

    def utf8(s):
        b = s.encode("utf-8")
        return b"\x01" + struct.pack(">H", len(b)) + b

    pool += utf8(name.replace(".", "/")) + b"\x07" + struct.pack(">H", 1)          # 1 utf8, 2 class
    pool += utf8("java/lang/Object") + b"\x07" + struct.pack(">H", 3)              # 3 utf8, 4 class
    count = 5
    for s in strings:
        pool += utf8(s) + b"\x08" + struct.pack(">H", count)                         # utf8, then String -> it
        count += 2
    return (b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 52, count) + pool
            + struct.pack(">HHHHHHH", 0x21, 2, 4, 0, 0, 0, 0))


def make_meta_nar(path, missing_attribute="delimiter"):
    """Deployed build of acme-meta-nar 2.0.0 - built from an older commit: no `delimiter` attribute yet."""
    lookup = ["Object Key", "File name or feed name to look up", "metadata-service", "Metadata Service", "lookup-mode", "Lookup Mode", "by-file", "by-feed", "success",
              "not found", "No OBJ_DEFINITION row for file {}", "Structure mismatch for {} against OBJ_STRUCTURE",
              "table_name", "structure.json", "delimiter"]
    lookup = [s for s in lookup if s != missing_attribute]
    jar = io.BytesIO()
    with zipfile.ZipFile(jar, "w") as j:
        j.writestr("META-INF/services/org.apache.nifi.processor.Processor", "com.acme.meta.MetadataLookup\n")
        j.writestr("com/acme/meta/MetadataLookup.class", class_file("com.acme.meta.MetadataLookup", lookup))
        j.writestr("com/acme/meta/MetadataDao.class", class_file("com.acme.meta.MetadataDao", [
            "OBJ_DEFINITION", "SOURCE_FEED_CONFIG", "SELECT * FROM {} d WHERE d.FILE_NAME = ?",
            "SELECT s.COL_NAME FROM OBJ_STRUCTURE s WHERE s.OBJ_ID = ?"]))
        j.writestr("com/acme/meta/base/AbstractMetadataProcessor.class",
                   class_file("com.acme.meta.base.AbstractMetadataProcessor", ["metadata-db", "Metadata DB", "failure"]))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\nNar-Group: com.acme\nNar-Id: acme-meta-nar\nNar-Version: 2.0.0\n")
        z.writestr("META-INF/bundled-dependencies/acme-meta-processors-2.0.0.jar", jar.getvalue())
        z.writestr("META-INF/bundled-dependencies/commons-lang3-3.12.0.jar", b"not really a jar")
METADATA_DAO = """package com.acme.meta;

class MetadataDao {
    private static final String DEF_TABLE = "OBJ_DEFINITION";
    private static final String STRUCT_TABLE = "obj_structure";
    private static final String FEED_TABLE = "SOURCE_FEED_CONFIG";

    void load(String key) {
        String sql = "SELECT * FROM " + DEF_TABLE + " d WHERE d.FILE_NAME = ?";
    }
}
"""


def make_metadata_repo(root):
    mod = Path(root) / "nifi-meta-processors"
    src = mod / "src" / "main" / "java" / "com" / "acme" / "meta"
    (src / "base").mkdir(parents=True, exist_ok=True)
    (src / "MetadataLookup.java").write_text(METADATA_PROCESSOR, encoding="utf-8")
    (src / "LegacyMetadataLookup.java").write_text(UNREGISTERED_PROCESSOR, encoding="utf-8")
    (src / "MetadataDao.java").write_text(METADATA_DAO, encoding="utf-8")
    (src / "MetadataService.java").write_text(METADATA_SERVICE_API, encoding="utf-8")
    (src / "CachingMetadataService.java").write_text(METADATA_SERVICE_IMPL, encoding="utf-8")
    test_src = mod / "src" / "test" / "java" / "com" / "acme" / "meta"
    test_src.mkdir(parents=True, exist_ok=True)
    (test_src / "MockUpstream.java").write_text(MOCK_TEST_PROCESSOR, encoding="utf-8")
    (src / "base" / "AbstractMetadataProcessor.java").write_text(METADATA_BASE, encoding="utf-8")
    (src / "base" / "MetaConstants.java").write_text(METADATA_CONSTANTS, encoding="utf-8")
    svc = mod / "src" / "main" / "resources" / "META-INF" / "services"
    svc.mkdir(parents=True, exist_ok=True)
    (svc / "org.apache.nifi.processor.Processor").write_text("com.acme.meta.MetadataLookup\n", encoding="utf-8")
    (mod / "pom.xml").write_text(PROCESSORS_POM, encoding="utf-8")
    (Path(root) / "nifi-meta-nar").mkdir(parents=True, exist_ok=True)
    (Path(root) / "nifi-meta-nar" / "pom.xml").write_text(NAR_POM, encoding="utf-8")
    return Path(root)


def metadata_flow():
    """The nested flow plus the two processors a metadata-driven flow has: a lookup of the config tables and a
    processor configured with a feed name."""
    flow = nested_flow()
    flow["rootGroup"]["processors"] += [
        proc("p-meta", "Read object metadata", "org.apache.nifi.processors.standard.ExecuteSQL",
             {"Database Connection Pooling Service": DBCP_INSTANCE,
              "SQL select query": "SELECT s.COL_NAME, s.DATA_TYPE FROM OBJ_DEFINITION d JOIN OBJ_STRUCTURE s ON s.OBJ_ID = d.OBJ_ID "
                                  "WHERE d.FILE_NAME = '${filename}'"}, auto=["failure"]),
        proc("p-feed", "Tag POS feed", "org.apache.nifi.processors.attributes.UpdateAttribute", {"feed.name": "pos_sales_feed"},
             bundle={"group": "org.apache.nifi", "artifact": "nifi-update-attribute-nar", "version": "1.27.0"}),
        proc("p-lookup-meta", "Metadata lookup", "com.acme.meta.MetadataLookup", {"Object Key": "${filename}"},
             bundle={"group": "com.acme", "artifact": "acme-meta-nar", "version": "1.9.0"}),
    ]
    flow["rootGroup"]["connections"] += [conn("r7", "p-feed", "PROCESSOR", "p-meta", "PROCESSOR", ["success"]),
                                         conn("r8", "p-meta", "PROCESSOR", "p-lookup-meta", "PROCESSOR", ["success"])]
    return flow


def make_env(tmp, flow=None, with_db=True, with_metadata=False):
    """Create a full environment under tmp and return the config path."""
    tmp = Path(tmp)
    (tmp / "nars").mkdir(parents=True, exist_ok=True)
    make_nar(tmp / "nars" / "acme-nifi-nar-1.0.0.nar", ACME_MANIFEST)
    make_nar(tmp / "nars" / "legacy-nar.nar", None, group="com.legacy", artifact="legacy-nar", service_classes=["com.legacy.OldProcessor"])
    flow_path = tmp / "flow.json.gz"
    with gzip.open(flow_path, "wt", encoding="utf-8") as f:
        json.dump(flow or nested_flow(), f)
    dbs = ""
    if with_db:
        make_db(tmp / "meta.db")
        if with_metadata:
            db = sqlite3.connect(tmp / "meta.db")
            db.executescript(METADATA_SQL)
            db.commit()
            db.close()
        dbs = f"""
[[databases]]
name = "metadata"
kind = "sqlite"
database = "{(tmp / 'meta.db').as_posix()}"
match_jdbc = "dbhost.acme.com:3306/meta"
include_tables = ["file_%"]
profile_tables = ["file_calls"]
sample_rows = 1
"""
        if with_metadata:
            dbs += '\n[audit]\ndb = "metadata"\n\n[metadata]\ndb = "metadata"\n'
    repos = [(FIXTURES / "repo").as_posix()]
    if with_metadata:
        repos.append(make_metadata_repo(tmp / "meta-repo").as_posix())
        make_meta_nar(tmp / "nars" / "acme-meta-nar-2.0.0.nar")
    cfg = tmp / "nifikb.toml"
    cfg.write_text(f"""
[nifi]
flow_file = "{flow_path.as_posix()}"
extra_nar_dirs = ["{(tmp / 'nars').as_posix()}"]

[output]
dir = "{(tmp / 'kb').as_posix()}"

[code]
repos = {json.dumps(repos)}
{dbs}""", encoding="utf-8")
    return cfg
