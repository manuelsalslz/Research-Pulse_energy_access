@echo off
REM ResearchPulse — run from project folder without installing
cd /d "%~dp0"
python -m research_agent %*
