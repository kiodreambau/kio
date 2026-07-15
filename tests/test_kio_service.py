import plistlib

from kio.config import KioConfig
from kio.service import (
    default_launch_agent_path,
    render_launch_agent,
    render_repair_launch_agent,
    write_launch_agent,
)


def test_render_launch_agent_contains_self_host_command(tmp_path, monkeypatch):
    monkeypatch.setattr("kio.service.shutil.which", lambda name: "/Users/kio/.local/bin/uv")
    cfg = KioConfig(workspace=tmp_path, dashboard_port=9999, webhook_secret="secret")

    plist = plistlib.loads(render_launch_agent(cfg).encode("utf-8"))

    assert plist["Label"] == "io.kio.worker"
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["ProgramArguments"][:4] == [
        "/Users/kio/.local/bin/uv",
        "run",
        "--no-project",
        "--with-editable",
    ]
    assert plist["ProgramArguments"][-5:] == ["serve", "--host", "127.0.0.1", "--port", "9999"]
    assert "--port" in plist["ProgramArguments"]
    assert plist["EnvironmentVariables"]["KIO_WORKSPACE"] == str(tmp_path)
    assert "KIO_WEBHOOK_SECRET" not in plist["EnvironmentVariables"]
    assert "GITHUB_TOKEN" not in plist["EnvironmentVariables"]


def test_render_launch_agent_can_use_python_runner(tmp_path):
    cfg = KioConfig(workspace=tmp_path, launch_agent_runner="python")

    plist = plistlib.loads(render_launch_agent(cfg).encode("utf-8"))

    assert plist["ProgramArguments"][1:4] == ["-m", "kio", "serve"]


def test_write_launch_agent_to_custom_path(tmp_path):
    cfg = KioConfig(workspace=tmp_path)
    target = tmp_path / "agent.plist"

    path = write_launch_agent(cfg, output=target)

    assert path == target
    assert target.exists()
    assert (tmp_path / "logs").exists()


def test_default_launch_agent_path_uses_label():
    cfg = KioConfig(launch_agent_label="io.kio.test")

    assert default_launch_agent_path(cfg).name == "io.kio.test.plist"


def test_render_repair_launch_agent_polls_without_embedding_machine_token(tmp_path, monkeypatch):
    monkeypatch.setattr("kio.service.shutil.which", lambda name: "/Users/kio/.local/bin/uv")
    cfg = KioConfig(
        workspace=tmp_path,
        launch_agent_label="io.kio.worker",
        repair_api_url="https://kio.dreambau.com",
        repair_worker_token="must-not-be-in-plist",
    )

    plist = plistlib.loads(render_repair_launch_agent(cfg).encode("utf-8"))

    assert plist["Label"] == "io.kio.worker.repair"
    assert plist["ProgramArguments"][-1] == "repair-poll"
    assert plist["KeepAlive"] is True
    assert "KIO_REPAIR_WORKER_TOKEN" not in plist["EnvironmentVariables"]
    assert "must-not-be-in-plist" not in str(plist)
