# KIO Review Template Sources

KIO keeps its review policy in the repository instead of importing an opaque third-party
agent skill. Project owners can review and change the policy together with the code that it
governs.

## Sources used

- [Google Engineering Practices: The Standard of Code Review](https://google.github.io/eng-practices/review/reviewer/standard.html)
  informs the rule that a review should improve code health without blocking on subjective
  perfection or unrelated cleanup.
- [Google Engineering Practices: What to look for](https://google.github.io/eng-practices/review/reviewer/looking-for.html)
  informs the split between behavior, test quality, documentation, and user-facing UI checks.
- [OWASP Secure Code Review Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html)
  informs the security scope used only by the explicitly local `thermonuclear` mode.

## KIO adaptation

| KIO pass | Purpose | Required output |
| --- | --- | --- |
| Basic | High-confidence defects in the changed behavior and nearby contract | File or behavior evidence, impact, and causal explanation |
| Correctness | Control flow, compatibility, changed UX, and accessibility when UI changed | A failing user or system path introduced by the diff |
| Test density | Missing regression coverage and assertions that would not catch a break | The exact behavior that needs proof and why existing tests are insufficient |
| Stability | Failure paths, retries, state, migrations, concurrency, and safe degradation | A realistic operational failure caused by the changed code |
| Performance | Repeated work, unbounded access, I/O, memory, latency, and narrow mobile responsiveness | A concrete affected path, never a speculative micro-optimization |

The Level 4 review runs correctness, test density, stability, and performance independently.
Accessibility remains within correctness because it is only meaningful when the changed diff
contains a relevant user interface path.

Every pass must separate an evidenced finding from a check that was not possible in the
available environment. KIO writes `Not verified:` with the missing evidence instead of
claiming that tests, browser flows, profiling, or production behavior were checked. This
keeps the GitHub review discussable without exposing private model reasoning.

## Deliberate constraints

- Do not expose hidden model reasoning. A finding must instead show evidence, impact, and a
  causal explanation that an author can discuss in GitHub.
- Do not auto-push, auto-fix, merge, approve, or request changes. KIO submits a `COMMENT`
  review and leaves the decision to the author and human reviewer.
- Do not trigger from comments. A PR label selects Level 1 through 4, then requesting
  `kiodreambau` as reviewer creates the run.
- Keep security breadth in the local-only `thermonuclear` mode until the project has a
  specifically reviewed security policy and a human escalation path.

## Project customization

Start with `.kio/review-policy.md` for team rules and
`.kio/config.toml` `[review_templates]` for a repository-specific pass. Keep templates
short, evidence-driven, and tied to actual project controls such as test commands, migration
rules, supported browsers, or performance budgets.
