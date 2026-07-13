# Repository Instructions

This repository is a kio fork of `Nayjest/Gito`.

- Keep upstream Gito behavior in `gito/` intact unless the task explicitly needs
  an engine change.
- Put kio-local orchestration code in `kio/`.
- Keep `gito` CLI compatibility while the fork is still young; prefer adding
  `kio` commands over renaming existing Gito commands.
- The MVP must not auto-push, auto-fix, or create fix PRs.
- Treat `thermonuclear` as an explicitly gated local mode only.
- Prefer small tests around trigger parsing, mode gates, dedupe state, and run
  folder layout before touching live GitHub behavior.
