# KIO Review Policy

KIO reviews only the diff and the necessary surrounding context. A finding must name the affected file or behavior, the observable evidence, the practical impact, and why this change causes it.

Do not block a pull request for personal style preferences, unrelated cleanup, speculative risk, or a pre-existing issue. Mark optional learning feedback as `Nit:` and keep it separate from actionable defects.

For UI changes, verify the actual user flow when the configured backend can do so: desktop and narrow mobile layout, keyboard operation, visible focus, semantic labels, and error states. For risky changes, prefer a focused regression test that would fail if the behavior returned.

The author and human reviewer decide whether to change code. KIO never pushes, merges, approves, requests changes automatically, or creates a fix pull request.
