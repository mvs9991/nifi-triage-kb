@echo off
rem CLAUDE.md is the master copy of the agent instructions; Gemini CLI reads GEMINI.md, other agents AGENTS.md.
cd /d "%~dp0.."
copy /y CLAUDE.md GEMINI.md >nul
copy /y CLAUDE.md AGENTS.md >nul
echo GEMINI.md and AGENTS.md updated from CLAUDE.md
