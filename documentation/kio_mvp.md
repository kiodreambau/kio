# kio MVP plan

kio is a local PR review orchestrator around the Gito review engine.
GitHub is the developer interface. The actual review runs on the owner's Mac.

## MVP boundary

- Trigger reviews only when `kiodreambau` is requested as a GitHub reviewer.
- Select the review depth with exactly one PR label before the request:
  `kio:1`, `kio:2`, `kio:3`, or `kio:4`. No label means Level 1.
- Ignore `issue_comment`, review-thread, and every other GitHub event. Human
  discussion in a review thread never starts another KIO run; re-request the
  reviewer to run again.
- Review Levels: Level 1 runs a basic high-confidence review; Levels 2 and 3 add
  test density and stability; Level 4 runs four independent passes for
  correctness/accessibility, test density/tooling, stability, and performance.
- Keep legacy focused modes (`tests`, `stability`, `frontend`, `security`) for
  manual CLI use. `thermonuclear` is explicitly local-gated.
- Keep `thermonuclear` disabled unless local config explicitly enables it.
- Dedupe by `repo + PR + head_sha + mode`.
- Store every run under `~/kio/runs/<repo>/pr-<number>/<head-sha>/<mode>/`.
- Use Gito as the default backend. Each selected pass gets the checked-out diff,
  project `.gito/config.toml`, bundled rule files, and its own review template.
- Allow `codex`, `claude-code`, `opencode`, and `local` as command-template
  backends controlled only by local config.
- Bundle owner/project review rules from `AGENTS.md` and configured rule files
  into each local run.
- Pass agent limits and token/cost budgets to backend processes.
- Submit one transparent, combined native GitHub PR review containing scope, reviewed commit,
  selected passes, project-rule status, findings, evidence, impact, and causal
  explanation. This deliberately does not expose hidden model reasoning.

## First sandbox loop

1. Fork or mirror `Nayjest/Gito` into `kiodreambau/kio`.
2. Create a sandbox repository under `kiodreambau`.
3. Create a GitHub token with only the permissions needed to read PRs and write
   pull-request reviews in that sandbox.
4. Copy `.kio/config.example.toml` to `~/.kio/config.toml`.
5. Set `GITHUB_TOKEN` or `GH_TOKEN`.
6. Run:

```bash
poetry install
poetry run kio once --repo kiodreambau/sandbox --dry-run
```

7. Start the local dashboard:

```bash
poetry run kio serve --host 127.0.0.1 --port 8765
```

8. Generate a macOS LaunchAgent plist for self-hosted startup:

```bash
poetry run kio launch-agent --print
poetry run kio launch-agent --output ~/Library/LaunchAgents/io.kio.worker.plist
```

Load it after reviewing the generated plist:

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/io.kio.worker.plist
launchctl enable gui/$(id -u)/io.kio.worker
```

9. Configure the GitHub webhook to POST `Pull requests` events to
   `/webhooks/github`; KIO accepts only the `review_requested` action. Do not
   subscribe to `Issue comments`. Set `webhook_secret` or `KIO_WEBHOOK_SECRET`
   to verify `X-Hub-Signature-256`.

10. Remove `--dry-run` after the trigger and run folder look correct.

No auto-pushes and no auto-fixes are in scope for the MVP.

## Team workflow

1. The author selects one `kio:N` label on the PR.
2. The author requests `kiodreambau` as reviewer in GitHub.
3. KIO writes the run artifacts, submits a native `COMMENT` review, and never
   approves or requests changes on its own.
4. Developers discuss findings in normal GitHub review threads. A new KIO pass
   requires removing and re-requesting the reviewer after new commits.
5. KIO can send a compact completion message by SMTP and optionally to Slack.
   Roundcube and Apple Mail are mail clients; no Roundcube API is needed.
6. Every run contains `codex-handoff.md`, which can be given to local Codex for
   browser, mobile, functional, and patch review. The current Codex chat does
   not expose an inbound webhook endpoint.

## Notification setup

Set non-secret routing values in KIO config and service-only values in the
environment:

```toml
notification_email_to = ["review@dreambau.com"]
notification_email_from = "kiocheck@dreambau.com"
smtp_host = "mail.dreambau.com"
smtp_port = 587
smtp_security = "starttls"
```

```sh
KIO_SMTP_USERNAME=kiocheck@dreambau.com
KIO_SMTP_PASSWORD=...                 # never commit this
KIO_SLACK_WEBHOOK_URL=https://hooks.slack.com/...  # optional, never commit this
```

Templates are versioned in `.kio/review-policy.md`, `.kio/notification-email.md`,
and `.kio/codex-handoff.md`. Review profiles remain configurable in
`[review_templates]`.
