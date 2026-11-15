"""OPS-02: render the real Compose configuration without a Docker engine or .env keys."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = (
    "MOCK_MODE",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "OPENAI_MODEL",
    "GEMINI_MODEL",
    "BACKEND_PORT",
    "FRONTEND_PORT",
    "VITE_API_URL",
    "CORS_ORIGINS",
)


@pytest.fixture
def render_compose(tmp_path: Path):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose CLI is unavailable; engine is not required")
    version = subprocess.run([docker, "compose", "version"], capture_output=True, timeout=10)
    if version.returncode:
        pytest.skip("Docker Compose CLI is unavailable; engine is not required")

    def render(settings=None, env_text=""):
        # Explicit env file prevents loading the real checkout's .env. Never forward real keys.
        env_file = tmp_path / "compose.env"
        env_file.write_text(env_text)
        env = {k: v for k, v in os.environ.items() if k not in SETTINGS}
        env.update(settings or {})
        result = subprocess.run(
            [
                docker,
                "compose",
                "--env-file",
                str(env_file),
                "-f",
                str(ROOT / "docker-compose.yml"),
                "--project-name",
                "firetwin-config-check",
                "config",
                "--format",
                "json",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        return json.loads(result.stdout)["services"]

    return render


def test_backend_mounts_only_runtime_data_read_only(render_compose) -> None:
    mounts = render_compose()["backend"]["volumes"]
    assert {m["target"]: m["source"] for m in mounts} == {
        "/app/data/processed": str(ROOT / "data/processed"),
        "/app/data/docs": str(ROOT / "data/docs"),
        "/app/ml/artifacts": str(ROOT / "ml/artifacts"),
    }
    assert all(m["type"] == "bind" and m["read_only"] for m in mounts)
    assert all(m["bind"].get("create_host_path", False) is False for m in mounts)


@pytest.mark.parametrize("mode", [None, "", "0", "1"])
def test_compose_preserves_automatic_and_explicit_modes(render_compose, mode) -> None:
    services = render_compose({} if mode is None else {"MOCK_MODE": mode})
    assert services["backend"]["environment"]["MOCK_MODE"] == (mode or "")


def test_shell_mode_overrides_env_file(render_compose) -> None:
    assert render_compose(env_text="MOCK_MODE=1\n")["backend"]["environment"]["MOCK_MODE"] == "1"
    services = render_compose({"MOCK_MODE": "0"}, env_text="MOCK_MODE=1\n")
    assert services["backend"]["environment"]["MOCK_MODE"] == "0"


def test_port_overrides_keep_browser_url_cors_and_keys_separate(render_compose) -> None:
    services = render_compose(
        {
            "BACKEND_PORT": "18000",
            "FRONTEND_PORT": "15173",
            "OPENAI_API_KEY": "synthetic-openai-fixture",
            "GEMINI_API_KEY": "synthetic-gemini-fixture",
        }
    )
    backend, frontend = services["backend"], services["frontend"]
    assert backend["ports"][0]["published"] == "18000"
    assert frontend["ports"][0]["published"] == "15173"
    assert backend["ports"][0]["host_ip"] == frontend["ports"][0]["host_ip"] == "127.0.0.1"
    assert frontend["environment"] == {"VITE_API_URL": "http://localhost:18000"}
    assert backend["environment"]["CORS_ORIGINS"] == (
        "http://localhost:15173,http://127.0.0.1:15173"
    )
    assert backend["environment"]["OPENAI_API_KEY"] == "synthetic-openai-fixture"
    assert backend["environment"]["GEMINI_API_KEY"] == "synthetic-gemini-fixture"
