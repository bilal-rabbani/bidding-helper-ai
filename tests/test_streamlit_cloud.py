"""The app is ready for Streamlit Community Cloud."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_app_file_and_requirements():
    assert (ROOT / "app.py").exists()
    requirements = (ROOT / "requirements.txt").read_text()
    assert re.search(r"(?m)^streamlit==\d", requirements), "pin the Streamlit version"
    for lib in ("pdfplumber", "openpyxl", "pandas", "pyyaml", "requests"):
        assert lib in requirements


def test_streamlit_settings_keep_protection_on():
    config = (ROOT / ".streamlit" / "config.toml").read_text()
    assert "enableXsrfProtection = false" not in config and "enableCORS = false" not in config


def test_no_leftover_hugging_face_files():
    assert not (ROOT / "Dockerfile").exists() and not (ROOT / "scripts" / "deploy_hf.py").exists()


def test_page_config_is_set_once():
    assert (ROOT / "app.py").read_text().count("st.set_page_config(") == 1
