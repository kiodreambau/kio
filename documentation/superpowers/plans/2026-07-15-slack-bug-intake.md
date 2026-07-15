# Slack Bug Intake Implementation Plan

> **For agentic workers:** Implement one vertical TDD slice at a time. Run the
> focused failing test before implementation and the full Kio suite before PR.

**Goal:** Turn a simple Slack message with pasted screenshots into an auditable
GitHub issue and an explicitly triggered Kio repair run.

**Architecture:** Add a small Slack Events adapter to the existing FastAPI app.
The adapter verifies and normalizes events, persists intake state and private
artifacts below configured server roots, then calls narrow GitHub/Slack ports.
Kio's existing worker remains the only repair execution boundary.

**Tech Stack:** Python 3.11+, FastAPI, standard-library HMAC/JSON/filesystem,
pytest, existing Kio GitHub and worker adapters.

---

### Task 1: Signed, idempotent event intake (Issue #4)

**Files:** Create `kio/slack_intake.py`, modify `kio/web.py`,
`kio/config.py`, `.kio/config.example.toml`, create
`tests/test_kio_slack_intake.py`, modify `tests/test_kio_web.py`.

1. Add a failing test for valid signed URL verification and a top-level report.
2. Add failing tests for invalid signature, stale timestamp and duplicate event.
3. Implement only signature validation, normalization and idempotent persistence.
4. Run focused tests, then relevant config/web tests.

### Task 2: Private screenshot artifacts (Issue #5)

**Files:** Create `kio/bug_artifacts.py`, create
`tests/test_kio_bug_artifacts.py`, modify `kio/slack_intake.py`.

1. Add one failing test for storing an allowed PNG at mode `0600` with a random
   filename and retention metadata.
2. Implement the minimal private storage boundary.
3. Add failing tests for invalid type, per-file limit and traversal attempts.
4. Implement validation and run focused tests.

### Task 3: GitHub issue and explicit repair trigger (Issue #6)

**Files:** Create `kio/bug_delivery.py`, create
`tests/test_kio_bug_delivery.py`, modify `kio/slack_intake.py` and `kio/web.py`.

1. Add a failing test that a normal report opens one deduplicated issue without
   starting a repair.
2. Implement the GitHub issue port and persisted linkage.
3. Add a failing test that `@Kio fix` queues exactly one repair run.
4. Implement the explicit worker boundary and Slack thread status callbacks.
5. Verify repository allowlist and no-auto-merge behavior.

### Task 4: Deploy and prove the live path

**Files:** Modify deployment config outside Git only for secret values; document
non-secret settings in `.kio/config.example.toml` and `documentation/kio_mvp.md`.

1. Create `#oriso-bugfix` and configure Slack event/reaction subscriptions.
2. Store the signing/bot credentials in the server secret environment.
3. Deploy the feature branch in dry-run mode and verify health.
4. Submit a synthetic message with one screenshot and verify acknowledgement,
   private artifact, one issue and one dry-run repair.
5. Enable live repair only after all evidence is green.

