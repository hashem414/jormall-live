# Sources and implementation assumptions

Reviewed for this build: 2026-09-20. Sources describe the upstream product; they do not certify this third-party implementation.

1. OpenAI, Skills: https://developers.openai.com/codex/skills/
   A skill consists of SKILL.md plus optional scripts/resources. The user-scope install location is ~/.agents/skills. A skill is not itself an always-on telemetry process. This project separately installs an OS task.

2. OpenAI, Codex open-source protocol: https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs
   Raw source: https://raw.githubusercontent.com/openai/codex/main/codex-rs/protocol/src/protocol.rs
   TokenUsage includes input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens. TokenUsageInfo distinguishes cumulative total_token_usage and last_token_usage. TokenCountEvent may contain rate_limits with no usage info. RateLimitSnapshot includes primary/secondary windows. This project uses cumulative deltas and a conservative schema check. The provider-only codex_rollout_budget_units field is marked skip_serializing in the inspected source; the collector does not treat any local field as a guaranteed Pro budget allocation.
   JSONL rollout storage is an implementation surface, NOT a stable per-person billing API. Runtime compatibility must be checked against the installed Codex build. Source reviewed from main, not pinned to a deployed user release.

3. OpenAI, Pricing/usage limits: https://developers.openai.com/codex/pricing/
   Quota consumption depends on model, context, task and other factors; tokens are not a direct per-person percentage of an allowance. The product usage dashboard and CLI /status are references for overall limits. This project does not scrape the dashboard, infer simultaneous users from quota deltas, use API prices as Pro billing, or issue reset/redeem calls.

4. OpenAI, App Server: https://developers.openai.com/codex/app-server/
   account/rateLimits/read exposes account-limit snapshots. These are not a breakdown of human users sharing one login. The current collector does not invoke app-server or read OpenAI credentials; it optionally forwards sanitized snapshots already in local rollout events.

5. OpenAI, advanced configuration: https://developers.openai.com/codex/config-advanced/
   OTel log events can include tool-result snippets even with prompt logging off. This is why this package does not send raw OTel logs remotely. No otel configuration is modified by installation.

6. OpenAI Account Sharing Policy: https://help.openai.com/en/articles/10471989-openai-account-sharing-policy
   Personal accounts are for the individual owner, not sharing among separate people. This package is a telemetry utility, not a workaround for account policy or access limits.

7. Node.js SQLite documentation: https://nodejs.org/api/sqlite.html
   Backend uses built-in node:sqlite DatabaseSync and prepared statements. Runtime tested: Node 22.16.0; Node emits an experimental SQLite warning on that build. Dockerfile selects Node 24; that image was not built in this environment.

8. Docker Compose variable interpolation: https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/
   compose.yaml reads local .env variables and requires ADMIN_TOKEN/PUBLIC_URL. .env is excluded from source control and Docker build context.

9. Railway public networking: https://docs.railway.com/networking/public-networking
   Optional hosting route, not performed as part of the delivered build. A live deployment requires a connected account, actual service, domain and writable persistent storage. No free-tier availability or uninterrupted uptime is promised.

No real user conversation, OpenAI password, OAuth token, API key or usage history was supplied or used to test the package.
