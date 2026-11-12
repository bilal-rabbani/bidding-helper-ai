"""Publishes the app to a Hugging Face Space (Docker, free CPU).

Run:  python scripts/deploy_hf.py [space-name]      (needs the HF_TOKEN environment variable)
Only the files the app needs are uploaded: no tests, evaluation files, PDFs or private folders.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INCLUDE = ["app.py", "core", "config", "requirements.txt", "Dockerfile", ".streamlit"]


def stage(dest: Path) -> list:
    """Copy the files to publish into dest. Returns their names."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in INCLUDE:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(src, dest / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
        elif src.exists():
            shutil.copy2(src, dest / name)
    shutil.copy2(ROOT / "deploy" / "space_readme.md", dest / "README.md")
    return sorted(str(p.relative_to(dest)).replace(os.sep, "/") for p in dest.rglob("*") if p.is_file())


def main():
    from huggingface_hub import HfApi

    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("HF_TOKEN is not set.")
    name = sys.argv[1] if len(sys.argv) > 1 else "bidding-helper-ai"
    api = HfApi(token=token)
    user = api.whoami()["name"]
    repo_id = f"{user}/{name}"
    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        files = stage(Path(tmp))
        print(f"Uploading {len(files)} files:", ", ".join(files[:12]), "..." if len(files) > 12 else "")
        api.upload_folder(folder_path=tmp, repo_id=repo_id, repo_type="space",
                          commit_message="Deploy Bidding Helper AI")
    print("\nSpace page :", f"https://huggingface.co/spaces/{repo_id}")
    print("App link   :", f"https://{user.lower()}-{name.lower().replace('_', '-')}.hf.space")
    print("The first build takes a few minutes. Watch it in the Space's 'Logs' tab.")


if __name__ == "__main__":
    main()
