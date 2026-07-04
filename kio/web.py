"""Self-hosted local kio web app."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

from .config import KioConfig, load_config
from .run_store import RunSummary, list_runs, state_snapshot
from .webhooks import SignatureError, webhook_work_item, verify_signature


def create_app(config: KioConfig | None = None):
    cfg = config or load_config()
    app = FastAPI(title="kio", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        return render_dashboard(cfg, list_runs(cfg))

    @app.get("/api/runs")
    def api_runs(limit: int = 100):
        return {"runs": [run.to_json() for run in list_runs(cfg, limit=limit)]}

    @app.get("/api/config")
    def api_config():
        return {"config": public_config(cfg)}

    @app.get("/api/state")
    def api_state():
        return {"state": state_snapshot(cfg)}

    @app.post("/webhooks/github")
    async def github_webhook(
        request: Request,
        background_tasks: BackgroundTasks,
        x_github_event: str = Header(default=""),
        x_hub_signature_256: str = Header(default=""),
    ):
        body = await request.body()
        try:
            verify_signature(
                body,
                signature=x_hub_signature_256,
                secret=cfg.webhook_secret,
            )
        except SignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        payload = await request.json()
        try:
            item = webhook_work_item(
                payload,
                event=x_github_event,
                config=cfg,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not item:
            return {"accepted": False, "reason": "no kio trigger"}
        background_tasks.add_task(_process_webhook_item, cfg, item, cfg.webhook_dry_run)
        return {"accepted": True, "dedupe_key": item.dedupe_key, "mode": item.mode}

    return app


def public_config(config: KioConfig) -> dict[str, Any]:
    return {
        "bot_login": config.bot_login,
        "backend": config.backend,
        "workspace": str(config.workspace.expanduser()),
        "runs_dir": str(config.runs_dir),
        "poll_interval_seconds": config.poll_interval_seconds,
        "default_agents": config.default_agents,
        "max_agents": config.max_agents,
        "allow_thermonuclear": config.allow_thermonuclear,
        "repos": list(config.repos),
        "dashboard_host": config.dashboard_host,
        "dashboard_port": config.dashboard_port,
        "webhook_configured": bool(config.webhook_secret),
        "webhook_dry_run": config.webhook_dry_run,
        "rules_files": list(config.rules_files),
        "token_budget": config.token_budget,
        "cost_budget_usd": config.cost_budget_usd,
        "github_token_configured": bool(config.github_token),
    }


def render_dashboard(config: KioConfig, runs: list[RunSummary]) -> str:
    rows = "\n".join(_render_run_row(run) for run in runs) or _empty_row()
    cfg = public_config(config)
    repo_text = ", ".join(cfg["repos"]) if cfg["repos"] else "No repos configured"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>kio</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="shell">
    <aside class="rail" aria-label="kio navigation">
      <div class="mark">kio</div>
      <nav class="rail-actions">
        <a class="icon-button is-active" href="/" title="Runs" aria-label="Runs">◆</a>
        <a class="icon-button" href="/api/runs" title="Runs API" aria-label="Runs API">⌁</a>
        <a class="icon-button" href="/api/config" title="Config API" aria-label="Config API">⌘</a>
      </nav>
    </aside>
    <main class="workspace">
      <header class="topbar">
        <div>
          <h1>kio</h1>
          <p>{escape(repo_text)}</p>
        </div>
        <div class="toolbar" role="toolbar" aria-label="Dashboard actions">
          <button class="tool-button" title="Refresh" onclick="location.reload()" aria-label="Refresh">↻</button>
          <a class="tool-button" title="Open runs JSON" aria-label="Open runs JSON" href="/api/runs">[]</a>
          <a class="tool-button" title="Open config JSON" aria-label="Open config JSON" href="/api/config">⚙</a>
        </div>
      </header>
      <section class="status-band" aria-label="Worker status">
        <div class="metric">
          <span class="metric-label">Backend</span>
          <strong>{escape(str(cfg["backend"]))}</strong>
        </div>
        <div class="metric">
          <span class="metric-label">Token</span>
          <strong>{"set" if cfg["github_token_configured"] else "missing"}</strong>
        </div>
        <div class="metric">
          <span class="metric-label">Webhook</span>
          <strong>{"signed" if cfg["webhook_configured"] else "open"}</strong>
        </div>
        <div class="metric">
          <span class="metric-label">Agents</span>
          <strong>{cfg["default_agents"]}/{cfg["max_agents"]}</strong>
        </div>
        <div class="metric">
          <span class="metric-label">Budget</span>
          <strong>{escape(_budget_label(cfg))}</strong>
        </div>
      </section>
      <section class="run-surface" aria-label="Review runs">
        <div class="section-head">
          <h2>Runs</h2>
          <div class="segmented" aria-label="Run filters">
            <button class="segment is-selected" type="button" data-filter="all">All</button>
            <button class="segment" type="button" data-filter="prepared">Open</button>
            <button class="segment" type="button" data-filter="completed">Done</button>
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Repository</th>
                <th>PR</th>
                <th>Mode</th>
                <th>Backend</th>
                <th>SHA</th>
                <th>Source</th>
                <th>Run</th>
              </tr>
            </thead>
            <tbody>
              {rows}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  </div>
  <script>
    for (const button of document.querySelectorAll("[data-filter]")) {{
      button.addEventListener("click", () => {{
        const filter = button.dataset.filter;
        document.querySelectorAll("[data-filter]").forEach((item) =>
          item.classList.toggle("is-selected", item === button)
        );
        document.querySelectorAll("tr[data-status]").forEach((row) => {{
          row.hidden = filter !== "all" && row.dataset.status !== filter;
        }});
      }});
    }}
  </script>
</body>
</html>"""


def _render_run_row(run: RunSummary) -> str:
    status_class = "done" if run.status == "completed" else "pending"
    pr_label = f"#{run.pr}" if run.pr else "-"
    pr_cell = (
        f'<a href="{escape(run.html_url)}">{escape(pr_label)}</a>'
        if run.html_url
        else escape(pr_label)
    )
    return f"""<tr data-status="{escape(run.status)}">
  <td><span class="status {status_class}"></span>{escape(run.status)}</td>
  <td>{escape(run.repo)}</td>
  <td>{pr_cell}</td>
  <td><span class="pill">{escape(run.mode)}</span></td>
  <td>{escape(run.backend or "-")}</td>
  <td><code>{escape(_short_sha(run.head_sha))}</code></td>
  <td>{escape(run.source)}</td>
  <td><code>{escape(_compact_path(run.run_dir))}</code></td>
</tr>"""


def _empty_row() -> str:
    return """<tr>
  <td colspan="8" class="empty">No local runs yet</td>
</tr>"""


def _short_sha(value: str) -> str:
    return value[:8] if value else "-"


def _compact_path(value: str) -> str:
    try:
        path = Path(value).expanduser()
        home = Path.home()
        return "~/" + str(path.relative_to(home)) if path.is_relative_to(home) else str(path)
    except ValueError:
        return value


def _budget_label(cfg: dict[str, Any]) -> str:
    if cfg["token_budget"]:
        return f'{cfg["token_budget"]} tok'
    if cfg["cost_budget_usd"]:
        return f'${cfg["cost_budget_usd"]}'
    return "open"


def _process_webhook_item(config: KioConfig, item, dry_run: bool) -> None:
    from .worker import KioWorker

    KioWorker(config).process_item(item, dry_run=dry_run)


def _css() -> str:
    return """
:root {
  color-scheme: light dark;
  --bg: #f7f7f4;
  --surface: #ffffff;
  --surface-2: #eeeeea;
  --text: #191917;
  --muted: #696965;
  --line: #dadad3;
  --accent: #0f766e;
  --accent-2: #2563eb;
  --warn: #b45309;
  --ok: #15803d;
  --shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #11110f;
    --surface: #1a1a17;
    --surface-2: #24241f;
    --text: #f4f4ee;
    --muted: #aaa99e;
    --line: #34342e;
    --accent: #2dd4bf;
    --accent-2: #60a5fa;
    --warn: #f59e0b;
    --ok: #22c55e;
    --shadow: none;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.4 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
a { color: inherit; }
.shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
}
.rail {
  border-right: 1px solid var(--line);
  background: var(--surface);
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 24px;
  padding: 14px 10px;
}
.mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-weight: 700;
  letter-spacing: 0;
}
.rail-actions {
  display: grid;
  gap: 8px;
}
.icon-button,
.tool-button {
  width: 36px;
  height: 36px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  text-decoration: none;
  box-shadow: var(--shadow);
  cursor: pointer;
}
.icon-button:hover,
.tool-button:hover,
.icon-button.is-active {
  border-color: var(--accent);
  color: var(--accent);
}
.workspace {
  min-width: 0;
  padding: 18px 22px 28px;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}
h1,
h2,
p {
  margin: 0;
  letter-spacing: 0;
}
h1 { font-size: 24px; line-height: 1.1; }
h2 { font-size: 16px; }
.topbar p {
  color: var(--muted);
  margin-top: 4px;
  max-width: min(72ch, 70vw);
  overflow-wrap: anywhere;
}
.toolbar {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}
.status-band {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 1px;
  border: 1px solid var(--line);
  background: var(--line);
  border-radius: 8px;
  overflow: hidden;
  margin-bottom: 18px;
}
.metric {
  background: var(--surface);
  padding: 12px 14px;
  min-height: 70px;
}
.metric-label {
  display: block;
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 6px;
}
.metric strong {
  font-size: 17px;
  overflow-wrap: anywhere;
}
.run-surface {
  min-width: 0;
}
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.segmented {
  display: inline-flex;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: var(--surface);
}
.segment {
  min-width: 64px;
  height: 32px;
  border: 0;
  border-right: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.segment:last-child { border-right: 0; }
.segment.is-selected {
  color: var(--text);
  background: var(--surface-2);
}
.table-wrap {
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: auto;
  background: var(--surface);
}
table {
  width: 100%;
  border-collapse: collapse;
  min-width: 840px;
}
th,
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
th {
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
  background: var(--surface-2);
}
tr:last-child td { border-bottom: 0; }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  color: var(--muted);
}
.status {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  margin-right: 8px;
  background: var(--warn);
}
.status.done { background: var(--ok); }
.pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-2);
}
.empty {
  color: var(--muted);
  text-align: center;
  height: 84px;
}
@media (max-width: 760px) {
  .shell { grid-template-columns: 52px minmax(0, 1fr); }
  .workspace { padding: 14px; }
  .topbar { align-items: flex-start; }
  .status-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .toolbar { flex-wrap: wrap; justify-content: flex-end; }
}
"""
