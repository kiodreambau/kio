# Slack Bug Intake Design

**Status:** Approved  
**Parent issue:** https://github.com/kiodreambau/kio/issues/3

The canonical cross-system design is `Bug Intake and Kio Repair Pipeline.md` in
the Dreambau shared knowledge core. This repository implements the signed
ingress, private artifact boundary, GitHub issue adapter and explicit repair
trigger. It does not store Slack/GitHub credentials or private screenshots in
Git.

## Invariants

- Slack request signatures are checked against the raw body and timestamp.
- Replayed event IDs and root message timestamps are idempotent.
- Only configured channel and repository allowlists are accepted.
- Normal reports open/link an issue; only an explicit fix trigger queues code.
- Screenshots use private randomized paths, strict media/size limits and TTL.
- Kio never force-pushes, auto-merges or promotes to `dev`.
- Repair jobs use a separate bearer-authenticated API and a one-use lease; the
  server never returns private filesystem paths.
- An active worker may download only its leased screenshots. They are mode-0600
  temporary files on Kio's Mac and are removed after the Codex run.
- Kio's Mac executes repairs only in repositories explicitly mapped by its
  local TOML. Slack report content is treated as untrusted data.
