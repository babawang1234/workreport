"""把 Web 版发布到 Hugging Face Spaces（Docker）。

用法（PowerShell）：
    $env:HF_TOKEN="hf_xxx"            # 必须有 write 权限
    $env:HF_USERNAME="your-name"
    python deploy/hf/deploy.py        # 可选 --repo workbrief --skip-secrets

若本机 .env 或环境变量里有 DATABASE_URL / LLM_API_KEY 等，会自动写入 Space Secrets。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_DIR = Path(__file__).resolve().parent

SECRET_KEYS = [
    "DATABASE_URL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_MAX_TOKENS",
    "SITE_URL",
    "SUPPORT_TEXT",
    "SUPPORT_WECHAT",
    "ALIPAY_QR",
]


def load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_dir() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="hf_space_"))
    for name in ("core", "webapp", "assets"):
        src = ROOT / name
        if src.exists():
            shutil.copytree(src, tmp / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(DEPLOY_DIR / "Dockerfile", tmp / "Dockerfile")
    shutil.copy2(DEPLOY_DIR / "README.md", tmp / "README.md")
    shutil.copy2(ROOT / "requirements-web.txt", tmp / "requirements-web.txt")
    return tmp


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="workbrief")
    parser.add_argument("--skip-secrets", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    token = os.environ.get("HF_TOKEN", "").strip()
    username = os.environ.get("HF_USERNAME", "").strip()
    if not token or not username:
        print("缺少 HF_TOKEN 或 HF_USERNAME")
        return 2

    repo_id = f"{username}/{args.repo}"
    api = HfApi(token=token)
    print(f"创建/复用 Space: {repo_id}")
    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", exist_ok=True)

    folder = build_dir()
    try:
        print("上传文件...")
        api.upload_folder(folder_path=str(folder), repo_id=repo_id, repo_type="space")
    finally:
        shutil.rmtree(folder, ignore_errors=True)

    if not args.skip_secrets:
        for key in SECRET_KEYS:
            value = os.environ.get(key, "").strip()
            if value:
                api.add_space_secret(repo_id=repo_id, key=key, value=value)
                print(f"写入 Secret: {key}")

    url = f"https://{username}-{args.repo.replace('_', '-')}.hf.space"
    print(f"已推送，构建中。访问地址（构建完成后）：{url}")
    print("构建日志：https://huggingface.co/spaces/" + repo_id)

    for _ in range(40):
        time.sleep(15)
        info = api.space_info(repo_id)
        stage = getattr(info, "runtime", None)
        stage = getattr(stage, "stage", "") if stage else ""
        print(f"  状态: {stage or 'unknown'}")
        if stage in {"RUNNING", "RUNNING_BUILDING"}:
            print("已启动：", url)
            return 0
        if stage in {"BUILD_ERROR", "RUNTIME_ERROR", "CONFIG_ERROR"}:
            print("构建失败，请打开日志查看：https://huggingface.co/spaces/" + repo_id)
            return 1
    print("仍在构建，稍后刷新页面查看。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
