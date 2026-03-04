# ZUEB Agent Guide

## Goal
Port verified Android app behavior into Python services (CLI first, Bot second).
Prioritize protocol compatibility over refactoring style changes.

## Source Of Truth
- Primary reverse-engineering scope: `GradleProject/src/main/java/com/supwisdom/superapp`
- Critical obfuscated references for auth/network:
  - `GradleProject/src/main/java/supwisdom/bn1.java` (RSA encryption)
  - `GradleProject/src/main/java/supwisdom/mj1.java` (login/personal APIs)
  - `GradleProject/src/main/java/supwisdom/gn1.java` (host/base URL config)
- Existing Python behavior under `cli/` and `bot/` is the current contract; keep backward compatibility unless explicitly changed.

## Python Runtime
- Interpreter: `.venv/bin/python`
- Install core CLI deps:
  - `uv pip install click python-dotenv httpx cryptography`
- Install full project deps (CLI + Bot):
  - `uv pip install -r requirements.txt`

## Run Commands
- CLI help: `.venv/bin/python -m cli --help`
- CLI commands:
  - `.venv/bin/python -m cli login -u <username> -p <password>`
  - `.venv/bin/python -m cli status`
  - `.venv/bin/python -m cli attendance`
  - `.venv/bin/python -m cli schedule [--semester CODE | --year YYYY --term 1|2] [--week N] [--list-semesters]`
  - `.venv/bin/python -m cli logout`
- Bot: `.venv/bin/python -m bot`
- Skill helper (JSON output): `.venv/bin/python bot/agent/helper.py <command>`

## Current Python Layout
```text
cli/
  __main__.py
  main.py                    # click commands: login/status/logout/attendance/schedule
  config.py
  formatters.py
  auth/{client,crypto,login,token}.py
  schedule/{sso,client,service}.py
  attendance/{sso,sign,client,service}.py

bot/
  __main__.py
  app.py
  config.py
  handlers/
  agent/{client,helper,prompts}.py
  scheduler/nightly_attendance.py
```

## Persistence And Config
- Session files:
  - `~/.config/zueb-cli/session.json`
  - `~/.config/zueb-cli/device.json`
- Environment variables in `.env` / `.env.example`:
  - CLI: `ZUEB_USERNAME`, `ZUEB_PASSWORD`
  - Bot: `TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OWNER_ID`, `NIGHTLY_CHECK_*`, etc.

## Implementation Rules
- Do not invent endpoints, headers, params, or cryptography; map from app code or captured behavior.
- Keep login flow order: `loginConfigs -> publicKey(optional) -> mfa/detect -> passwordLogin -> me/user`.
- Keep attendance as read-only status query (no punch-in/out write operations).
- `bot/agent/helper.py` output must remain strict JSON for Claude Skills.
- Schedule Skill should preserve raw `schedule` payload and may append derived fields (for example location-based staggered class times) under additive keys.
- Never leak secrets in logs or responses (passwords, full tokens, raw auth headers).
- If behavior changes, update this file and `README.md` in the same change.
