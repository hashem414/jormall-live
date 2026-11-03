---
name: team-usage-meter
description: Check, explain, or install the team's consent-based numeric Codex usage meter. Use for usage statistics, tracker health, installation, or privacy questions. Never inspect or transmit conversation contents or OpenAI credentials. Tracking is performed by a separately installed local process, not by the language model.
---

# Team Usage Meter

## Mandatory boundaries
- This is a usage telemetry helper, NOT an OpenAI account-sharing mechanism, quota bypass, hard limit, or official per-person billing meter.
- Never read, print, copy, or upload `~/.codex/auth.json`, ChatGPT cookies, OAuth tokens, prompts, responses, tool outputs, reasoning text, source code, chat titles, or rollout files into model context.
- Never cat the meter's `config.json` or a member profile: they contain the meter token. The installer reads them locally without exposing them to the model.
- Never send OpenTelemetry logs directly to the dashboard: logs may contain tool-output snippets. This implementation uses a local numeric allowlist instead.
- Never edit the counters or assign invented points/tokens. Unknown is unknown, not zero.
- Team share is observed input-plus-output tokens divided by all observed team tokens in the selected period. Cached tokens are part of input; reasoning tokens are part of output. These are not percentages of Pro allowance or OpenAI credit charges.
- The account-limit snapshots, when available, are account-wide observations. Do not attribute them to the reporting person, average them across people, infer usage from their differences, or multiply them by token shares.
- Local JSONL rollout format can change; this is a best-effort adapter, not a stable public billing API. Cloud-only jobs, other devices, disabled logging, and copied/forked histories can reduce coverage.
- Shared personal OpenAI accounts are not permitted by OpenAI's account-sharing policy. The tool does not change that policy or isolate conversations already visible within a shared account.

## Installed usage
First locate this skill directory without listing conversation files. To show local numeric tracker health, run:

```text
node <skill-directory>/scripts/agent.mjs status
```

To send pending numeric events immediately, only after the member has installed/consented:

```text
node <skill-directory>/scripts/agent.mjs once
```

This reads local rollout files internally, but returns only sanitized tracker status. Never inspect the raw files yourself.
Explain `last_success`, `pending`, `files_found`, `issues`, `conflicts` and `expired`. A recent sync means the collector is connected, not proof the person is actively coding. `files_found=0` means the relevant Codex home may be wrong, no local session was created, or the installed Codex build uses a different storage format.
Direct the user to their dashboard to see team totals. Do not read credential files to log into it.

## First installation
Explain exactly what is sent and obtain the member's consent before installing, enabling scheduled tasks, or sending telemetry. The recipient must have their own dashboard member profile file and Node.js 20+.

```text
node <skill-directory>/install.mjs --profile <private-member-profile-path> --accept --autostart
```

Run the above only after explicit consent to both collection and automatic startup. Never put the actual token into a command line, chat, repository, URL, or AGENTS.md. Read `README_AR.md` for platform details. Do not claim deployment, operating-system startup, or a live Codex test succeeded without checking the output.

## Ongoing behavior
Do not invoke the model per usage sample. Once installed, the OS task syncs about once per minute without using the model. On user request you may run `status` or `once`; do not start extra watchers if the scheduled task is working. Restart Codex after skill installation if it is not discovered.
