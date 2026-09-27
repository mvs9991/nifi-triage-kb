#!/usr/bin/env sh
# Refresh the NiFi knowledge base (no-op when nothing changed). Linux counterpart of build.cmd.
# Cron (every 30 min):  */30 * * * * sh /opt/nifi-kb/ops/build.sh
# Use password_file (chmod 600) in nifikb.toml so cron needs no environment variables.
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-python3}"
echo "==== $(date '+%Y-%m-%d %H:%M:%S')" >> ops/build.log
"$PY" -m nifikb build >> ops/build.log 2>&1
