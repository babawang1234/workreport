"""把 Web 版部署到 Ubuntu 云服务器（Nginx + systemd + 本地 venv）。

用法（PowerShell）：
    python deploy/server/deploy.py --host 1.2.3.4 --password 你的root密码
可选：--user root --port 22 --app-dir /opt/workbrief

会读取本机 .env 里的 DATABASE_URL / LLM_* / SUPPORT_* / ALIPAY_QR 写入服务器环境文件。
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[2]
UPLOAD = ["core", "webapp", "assets", "requirements-web.txt"]

SYSTEMD = """[Unit]
Description=WorkBrief web app
After=network.target

[Service]
WorkingDirectory={app_dir}
EnvironmentFile={app_dir}/.env
ExecStart={app_dir}/.venv/bin/python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8600
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

NGINX = """server {{
    listen 80 default_server;
    server_name _;
    client_max_body_size 20m;

    location /static/assets/ {{
        alias {app_dir}/assets/;
        expires 7d;
    }}

    location /static/ {{
        alias {app_dir}/webapp/static/;
        expires 7d;
        add_header Cache-Control "public";
    }}

    location / {{
        proxy_pass http://127.0.0.1:8600;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 600s;
    }}
}}
"""

ENV_KEYS = [
    "DATABASE_URL",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_MAX_TOKENS",
    "SITE_URL",
    "SUPPORT_TEXT",
    "SUPPORT_WECHAT",
    "ALIPAY_QR",
    "ADMIN_USER",
    "ADMIN_PASSWORD",
]


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def ssh(host: str, user: str, password: str, port: int) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=port, username=user, password=password, timeout=25)
    return client


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 1800) -> None:
    print(f"\n$ {cmd.splitlines()[0]}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    channel = stdout.channel
    while True:
        while channel.recv_ready():
            sys.stdout.write(channel.recv(4096).decode("utf-8", "ignore"))
            sys.stdout.flush()
        while channel.recv_stderr_ready():
            sys.stdout.write(channel.recv_stderr(4096).decode("utf-8", "ignore"))
            sys.stdout.flush()
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            break
        time.sleep(0.1)
    code = channel.recv_exit_status()
    if code:
        raise SystemExit(f"命令失败（{code}）：{cmd.splitlines()[0]}")


def ensure_dir(sftp: paramiko.SFTPClient, path: str) -> None:
    try:
        sftp.stat(path)
        return
    except IOError:
        pass
    parent = path.rsplit("/", 1)[0]
    if parent and parent != path:
        ensure_dir(sftp, parent)
    try:
        sftp.mkdir(path)
    except IOError:
        pass


def upload(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    if local.is_dir():
        ensure_dir(sftp, remote)
        for item in local.iterdir():
            if item.name in {"__pycache__", ".venv"} or item.suffix == ".pyc":
                continue
            upload(sftp, item, f"{remote}/{item.name}")
        return
    sftp.put(str(local), remote)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--password", default=os.environ.get("SERVER_PASSWORD", ""))
    parser.add_argument("--user", default="ubuntu")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--app-dir", default="/opt/workbrief")
    args = parser.parse_args()

    if not args.password:
        print("缺少 --password 或 SERVER_PASSWORD")
        return 2

    load_dotenv()
    app_dir = args.app_dir.rstrip("/")
    sudo = "" if args.user == "root" else "sudo -n "

    print(f"连接 {args.user}@{args.host}:{args.port}")
    client = ssh(args.host, args.user, args.password, args.port)

    run(
        client,
        f"{sudo}bash -c 'export DEBIAN_FRONTEND=noninteractive; "
        "apt-get update -y >/dev/null && "
        "apt-get install -y python3-venv python3-pip nginx curl >/dev/null 2>&1'; "
        "python3 --version; nginx -v",
    )
    run(client, f"{sudo}mkdir -p {app_dir} && {sudo}chown -R {args.user}:{args.user} {app_dir}")

    print("\n上传代码...")
    sftp = client.open_sftp()
    for name in UPLOAD:
        local = ROOT / name
        if local.exists():
            upload(sftp, local, f"{app_dir}/{name}")

    env_lines = ["PYTHONUNBUFFERED=1"]
    for key in ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            env_lines.append(f'{key}="{value}"')
    env_text = "\n".join(env_lines) + "\n"
    with sftp.open(f"{app_dir}/.env", "w") as handle:
        handle.write(env_text)
    sftp.chmod(f"{app_dir}/.env", stat.S_IRUSR | stat.S_IWUSR)
    sftp.close()

    run(
        client,
        f"cd {app_dir} && python3 -m venv .venv && "
        ".venv/bin/pip install -q --upgrade pip && "
        ".venv/bin/pip install -q -r requirements-web.txt && "
        ".venv/bin/python -c \"import fastapi, psycopg2, markdown; print('deps ok')\"",
    )

    for path, content, mode in [
        ("/etc/systemd/system/workbrief.service", SYSTEMD.format(app_dir=app_dir), 0o644),
        ("/etc/nginx/sites-available/workbrief", NGINX.format(app_dir=app_dir), 0o644),
    ]:
        tmp = f"/tmp/{Path(path).name}"
        with client.open_sftp().open(tmp, "w") as handle:
            handle.write(content)
        run(client, f"{sudo}mv -f {tmp} {path}")

    run(
        client,
        f"{sudo}ln -sf /etc/nginx/sites-available/workbrief /etc/nginx/sites-enabled/workbrief; "
        f"{sudo}rm -f /etc/nginx/sites-enabled/default; "
        f"{sudo}nginx -t && {sudo}systemctl restart nginx && "
        f"{sudo}systemctl daemon-reload && {sudo}systemctl enable workbrief && "
        f"{sudo}systemctl restart workbrief && "
        "sleep 3 && systemctl is-active workbrief && "
        "curl -s -o /dev/null -w 'home:%{http_code}\\n' http://127.0.0.1/ && "
        "curl -s -o /dev/null -w 'activate:%{http_code}\\n' http://127.0.0.1/activate",
    )
    client.close()

    print(f"\n部署完成：http://{args.host}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
