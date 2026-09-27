"""Configuration: nifikb.toml - the only file to edit (paths are relative to it; secrets come from env vars or files)."""
import os
import tomllib
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent

TEMPLATE = """# =====================================================================================================================
# nifikb configuration - the ONLY file you edit.
#   * Paths may be absolute or relative to this file; ${{VARS}} are expanded.
#   * No secrets in here: passwords come from an environment variable (password_env) or a protected file
#     (password_file, chmod 600 on Linux).
#   * After editing:  python -m nifikb build   then   python -m nifikb doctor
# =====================================================================================================================

db_refresh_hours = 24                    # how often table schemas are re-read (build --refresh-db forces it)

# ---- 1. NiFi -------------------------------------------------------------------------------------------------------
[nifi]
home = "{home}"                 # NiFi install folder: conf/flow.json.gz, lib/*.nar and logs/ are read from here
# flow_file = "copies/flow.json.gz"      # or a copied flow file, when NiFi runs on another machine
extra_nar_dirs = []                      # folders with custom NARs that are not in <home>/lib

[logs]                                   # nifi-app*.log / nifi-bootstrap*.log - read incrementally, only warnings / errors kept
# dirs = ["/opt/nifi/logs"]              # default: <home>/logs
keep_days = 14                           # keep this many days of events (counted back from the newest one)
# initial_tail_mb = 200                  # first run on a huge log: only read its last N MB

# [nifi_api]                             # optional, read-only: provenance ("where was my file dropped, why") + live bulletins
# url = "https://nifi-host:8443/nifi-api"
# username = "readonly_user"             # needs the NiFi policies "query provenance" + "view provenance"
# password_env = "NIFIKB_NIFI_PASSWORD"  # or: password_file = "~/.nifikb/nifi.pw"
# ca_cert = "/etc/pki/nifi-ca.pem"       # CA of NiFi's certificate;  verify_ssl = false only for a quick test
# client_cert = "me.pem"                 # instead of username / password when NiFi uses client certificates
# client_key = "me.key"
# token_env = "NIFIKB_NIFI_TOKEN"        # or a pre-issued bearer token (Kerberos / OIDC setups)

# [registry]                             # optional, read-only: NiFi Registry version history (who changed a versioned flow, when, why)
# url = "https://registry-host:18443/nifi-registry-api"
# username = "readonly_user"
# password_env = "NIFIKB_REGISTRY_PASSWORD"
# ca_cert = "/etc/pki/nifi-ca.pem"

# ---- 2. Code -------------------------------------------------------------------------------------------------------
[code]
repos = []                               # Bitbucket clones: custom NAR projects (Maven / Java), scripts, Spark job scripts

# ---- 3. Databases (read-only users only) ---------------------------------------------------------------------------
# One block per database. The flow's DBCP connection pools are matched by host + port + database of their JDBC URL.
# [[databases]]
# name = "metadata"
# kind = "mariadb"                       # mariadb | mysql | postgres | sqlite
# host = "db-host"
# port = 3306
# database = "nifi_meta"
# user = "readonly_user"
# password_env = "NIFIKB_DB_PASSWORD"    # or: password_file = "~/.nifikb/db.pw"
# include_tables = []                    # also document these tables (SQL LIKE / glob patterns, e.g. "file_%")
# profile_tables = []                    # list distinct values of low-cardinality text columns (status, source, ...)
# sample_rows = 0                        # >0 adds a few masked sample rows per table

# ---- 4. Metadata config tables (OBJ_DEFINITION, OBJ_STRUCTURE, feed / API / server config, ...) --------------------
# Enables `diagnose` / `investigate` by file / feed / table, a masked snapshot of the config rows, their change history,
# and definition checks. Roles and relations are auto-detected: kb/metadata.md shows what was detected - override only
# what is wrong.
# [metadata]
# db = "metadata"                        # the [[databases]] name that holds the config tables
# target_db = "none"                     # loads go to HDFS / S3 files: no target-table checks. Or the [[databases]] name
#                                        #   holding the load tables, to check definitions against them.
# tables = ["OBJ_%", "%_CONFIG", "%_CONFIG_%", "%_DEFINITION", "%_STRUCTURE", "%_METADATA%"]   # which tables are config
# refresh_hours = 1                      # re-read the config rows (and record row changes) at most this often
# snapshot_max_rows = 20000              # rows per config table kept (masked); structure table: structure_max_rows
# --- overrides, only if kb/metadata.md shows a wrong guess:
# definition_table = "OBJ_DEFINITION"    # one row per file / object
# definition_id = "OBJ_ID"
# definition_keys = ["FILE_NAME", "TABLE_NAME"]   # what file / table names are matched against (patterns *, %, YYYYMMDD, regex)
# definition_target = "TABLE_NAME"       # the table a file is loaded into
# definition_location = "HDFS_PATH"      # the HDFS / S3 location it is written to
# structure_table = "OBJ_STRUCTURE"      # one row per column of a definition
# structure_parent = "OBJ_ID"
# structure_field = "COL_NAME"
# structure_type = "DATA_TYPE"
# structure_order = "COL_SEQ"
# structure_length = "COL_LENGTH"
# structure_nullable = "NULLABLE_FLAG"   # a column named like MANDATORY / REQUIRED / NOT_NULL is read as "required"
# structure_path = "JSON_PATH"           # JSON path per column for API / JSON feeds ($.data[*].customer.name)
# [[metadata.relations]]                 # joins that are not declared as foreign keys
# child = "SOURCE_FEED_CONFIG.OBJ_ID"
# parent = "OBJ_DEFINITION.OBJ_ID"

# ---- 5. Target storage, ticket system, other environments (all optional, all read-only) ----------------------------
# [targets]                             # read-only look at what loads wrote (investigate / target): listings + Parquet footer
# location_template = "s3://datalake/raw/{{table_lower}}/"   # when OBJ_DEFINITION has no location column: where {{table}} lands
# hdfs_url = "https://namenode:9871/webhdfs/v1"   # WebHDFS for hdfs:// and /paths (or leave out to use the `hdfs` CLI)
# hdfs_user = "nifikb"                   # simple auth; or kerberos = true (uses `curl --negotiate` with the kinit ticket)
# s3_profile = "readonly"                # aws CLI / boto3 profile; s3_endpoint / s3_region for S3-compatible stores
# max_download_mb = 200                  # hdfs CLI only: largest file copied to read its Parquet schema

# [tickets]                             # Jira / ServiceNow: `ticket <id>` reads it, investigates, drafts a reply
# kind = "servicenow"                    # or "jira"
# url = "https://acme.service-now.com"   # Jira: "https://acme.atlassian.net" or the Jira Server base URL
# username = "nifikb.integration"        # Jira Cloud: the account e-mail (with token_env = API token)
# password_env = "NIFIKB_TICKET_PASSWORD"   # or token_env (Jira Server PAT / OAuth token, sent as Bearer when no username)
# table = "incident"                     # ServiceNow table
# note_field = "work_notes"              # ServiceNow: where --post writes (work_notes = internal)

# [environments.uat]                     # other environments for `compare --env uat` ("works in UAT, fails in PROD")
# flow_file = "copies/uat/flow.json.gz"  # its flow (copy it over; read-only)
# db = "metadata_uat"                    # the [[databases]] name holding its config tables (read-only user)

# ---- 6. Load audit, daily report, web page -------------------------------------------------------------------------
# [audit]                                # the platform's per-file load log: investigate shows the last load of a file
# db = "metadata"                        # [[databases]] name (default: the metadata db)
# table = "FILE_LOAD_AUDIT"              # auto-detected (a table named like *audit* / *load_log* with a file-name column)
# file_column = "FILE_NAME"              # overrides, only if kb/INDEX / doctor shows a wrong guess:
# status_column = "LOAD_STATUS"
# time_column = "LOAD_TS"
# error_column = "ERROR_MSG"
# rows_column = "ROW_COUNT"
# link_column = "OBJ_ID"                 # the definition id, to list all loads of one definition

# [report]                               # python -m nifikb report --send (e.g. scheduled daily)
# email_to = ["nifi-team@company.com"]
# email_from = "nifikb@company.com"
# smtp_host = "smtp.company.com"
# smtp_port = 25
# smtp_starttls = false
# smtp_user = ""                         # + smtp_password_env / smtp_password_file when the relay needs a login
# webhook_url_env = "NIFIKB_WEBHOOK"     # Teams / Slack incoming-webhook URL (kept out of this file)

# [web]                                  # python -m nifikb web - self-service page for colleagues (read-only)
# host = "127.0.0.1"                     # "0.0.0.0" to reach it from other machines (then set a login)
# port = 8765
# user = "support"                       # HTTP basic login shared by the team
# password_env = "NIFIKB_WEB_PASSWORD"   # or password_file

# ---- 7. Where things are written -----------------------------------------------------------------------------------
[output]
dir = "kb"                               # generated knowledge base (markdown + kb.sqlite) - rebuilt, never edited by hand

[knowledge]
dir = "knowledge"                        # team context + learnings written by people and agents - kept, commit it to git
"""


def find_config(path=None):
    candidates = [path, os.environ.get("NIFIKB_CONFIG"), Path.cwd() / "nifikb.toml", PROJECT_DIR / "nifikb.toml"]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c).resolve()
    raise FileNotFoundError("nifikb.toml not found (run `python -m nifikb init` or pass --config)")


def load_config(path=None):
    path = find_config(path)
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    base = path.parent

    def rel(p):
        p = Path(os.path.expanduser(os.path.expandvars(str(p))))
        return str(p if p.is_absolute() else (base / p).resolve())

    for section in ("nifi", "output", "code", "logs", "knowledge"):
        cfg.setdefault(section, {})
    cfg.setdefault("databases", [])
    # an older layout put db_refresh_hours below [code], where TOML files it under code
    if "db_refresh_hours" not in cfg and "db_refresh_hours" in cfg["code"]:
        cfg["db_refresh_hours"] = cfg["code"].pop("db_refresh_hours")
    if cfg["nifi"].get("home"):
        cfg["nifi"]["home"] = rel(cfg["nifi"]["home"])
    if cfg["nifi"].get("flow_file"):
        cfg["nifi"]["flow_file"] = rel(cfg["nifi"]["flow_file"])
    cfg["nifi"]["extra_nar_dirs"] = [rel(p) for p in cfg["nifi"].get("extra_nar_dirs", [])]
    cfg["output"]["dir"] = rel(cfg["output"].get("dir", "kb"))
    cfg["knowledge"]["dir"] = rel(cfg["knowledge"].get("dir", "knowledge"))
    cfg["code"]["repos"] = [rel(p) for p in cfg["code"].get("repos", [])]
    if cfg["logs"].get("dirs"):
        cfg["logs"]["dirs"] = [rel(p) for p in cfg["logs"]["dirs"]]
    for d in cfg["databases"]:
        if d.get("kind") == "sqlite" and d.get("database"):
            d["database"] = rel(d["database"])
        if d.get("password_file"):
            d["password_file"] = rel(d["password_file"])
        d.setdefault("name", d.get("database", "db"))
    for key in ("nifi_api", "registry", "targets", "tickets"):
        api = cfg.get(key)
        if not api:
            continue
        for k in ("password_file", "token_file", "ca_cert", "client_cert", "client_key", "client_key_password_file"):
            if api.get(k):
                api[k] = rel(api[k])
    for env in (cfg.get("environments") or {}).values():
        if isinstance(env, dict) and env.get("flow_file"):
            env["flow_file"] = rel(env["flow_file"])
    for key in ("web", "report"):
        for k in ("password_file", "smtp_password_file", "webhook_url_file"):
            if (cfg.get(key) or {}).get(k):
                cfg[key][k] = rel(cfg[key][k])
    if not cfg["nifi"].get("home") and not cfg["nifi"].get("flow_file"):
        raise ValueError(f"{path}: set [nifi] home or flow_file")
    cfg["_path"] = str(path)
    return cfg


def write_template(path, nifi_home):
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} already exists")
    path.write_text(TEMPLATE.format(home=str(nifi_home).replace("\\", "/")), encoding="utf-8")
    return path
