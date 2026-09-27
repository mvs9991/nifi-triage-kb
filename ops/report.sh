#!/usr/bin/env sh
# Daily NiFi health report: refresh the KB, then e-mail / post it as configured in [report] of nifikb.toml.
# Cron (08:00 every day):  0 8 * * * sh /opt/nifi-kb/ops/report.sh
cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-python3}"
"$PY" -m nifikb build >> ops/build.log 2>&1
"$PY" -m nifikb report --hours 24 --html ops/last-report.html --send >> ops/build.log 2>&1
