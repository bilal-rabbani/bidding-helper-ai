"""Deployment tests: the right files are published, and nothing private."""
from pathlib import Path

from scripts.check_no_secrets import scan_project
from scripts.deploy_hf import stage

ROOT = Path(__file__).resolve().parent.parent


def test_the_published_files(tmp_path):
    files = stage(tmp_path)
    for needed in ("app.py", "Dockerfile", "README.md", "requirements.txt", ".streamlit/config.toml",
                   "config/settings.yaml", "core/boq_parser.py", "core/chat.py", "core/urdu.py"):
        assert needed in files, needed
    for private in ("tests", "evaluation", "private_tenders", ".git", ".github", "deploy", "docs"):
        assert not any(f == private or f.startswith(private + "/") for f in files), private
    assert not any(f.endswith((".pdf", ".xlsx", ".log", ".env", ".zip")) for f in files)
    assert "cloudflared" not in files


def test_space_front_page_and_no_secrets(tmp_path):
    stage(tmp_path)
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "sdk: docker" in readme and "app_port: 7860" in readme and "title: Bidding Helper AI" in readme
    assert scan_project(tmp_path) == []


def test_docker_recipe_and_streamlit_settings():
    docker = (ROOT / "Dockerfile").read_text()
    assert "7860" in docker and "streamlit" in docker and "requirements.txt" in docker
    assert "streamlit" in (ROOT / "requirements.txt").read_text()
    assert "headless = true" in (ROOT / ".streamlit" / "config.toml").read_text()
