# kio MVP plan

kio is a local PR review orchestrator around the Gito review engine.
GitHub is the developer interface. The actual review runs on the owner's Mac.

## MVP boundary

- Trigger reviews when `@kiodreambau review` appears in a PR comment.
- Trigger standard reviews when `kiodreambau` is requested as reviewer.
- Support explicit review modes: `standard`, `stability`, `tests`, `frontend`,
  `security`, and `thermonuclear`.
- Keep `thermonuclear` disabled unless local config explicitly enables it.
- Dedupe by `repo + PR + head_sha + mode`.
- Store every run under `~/kio/runs/<repo>/pr-<number>/<head-sha>/<mode>/`.
- Use Gito as the default backend.
- Allow `codex`, `claude-code`, `opencode`, and `local` as command-template
  backends controlled only by local config.
- Bundle owner/project review rules from `AGENTS.md` and configured rule files
  into each local run.
- Pass agent limits and token/cost budgets to backend processes.
- Post results back to GitHub as comments.

## First sandbox loop

1. Fork or mirror `Nayjest/Gito` into `kiodreambau/kio`.
2. Create a sandbox repository under `kiodreambau`.
3. Create a GitHub token with only the permissions needed to read PRs and write
   issue comments in that sandbox.
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

9. Configure GitHub webhooks to POST to `/webhooks/github` when a tunnel or
   local network route is available. Set `webhook_secret` or
   `KIO_WEBHOOK_SECRET` to verify `X-Hub-Signature-256`.

10. Remove `--dry-run` after the trigger and run folder look correct.

No auto-pushes and no auto-fixes are in scope for the MVP.
