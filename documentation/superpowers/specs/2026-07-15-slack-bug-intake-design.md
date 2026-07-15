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

