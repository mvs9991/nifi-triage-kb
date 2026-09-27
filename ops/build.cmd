@echo off
rem Refresh the NiFi knowledge base (no-op when nothing changed). Used by the scheduled task from register-schedule.ps1.
rem Database passwords come from user environment variables, e.g.  setx NIFIKB_DB_PASSWORD "..."  (once, then log off/on).
cd /d "%~dp0.."
echo ==== %date% %time% >> "%~dp0build.log"
python -m nifikb build >> "%~dp0build.log" 2>&1
