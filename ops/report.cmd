@echo off
rem Daily NiFi health report: refresh the KB, then e-mail / post the report as configured in [report] of nifikb.toml.
cd /d "%~dp0.."
python -m nifikb build >> "%~dp0build.log" 2>&1
python -m nifikb report --hours 24 --html "%~dp0last-report.html" --send >> "%~dp0build.log" 2>&1
