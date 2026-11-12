#!/bin/bash
# 推送到 GitHub：走 ssh.github.com:443，规避国内网络对 SSH 22 端口的阻断。
# 用法：./push.sh   （在本机终端里运行，需要能读取 ~/.ssh/id_ed25519_github）
set -euo pipefail
cd "$(dirname "$0")"

KEY="$HOME/.ssh/id_ed25519_github"
if [ ! -f "$KEY" ]; then
    echo "找不到 SSH 私钥：$KEY" >&2
    exit 1
fi

KH="$(mktemp -t scrcpy-gh-hosts)"
trap 'rm -f "$KH"' EXIT

echo "→ 获取 GitHub 官方主机密钥"
curl -fsS --max-time 20 https://api.github.com/meta | python3 -c '
import json, sys
for k in json.load(sys.stdin)["ssh_keys"]:
    for host in ("github.com", "ssh.github.com", "[ssh.github.com]:443"):
        print(host, k.strip())
' > "$KH"
chmod 600 "$KH"

SSH_OPTS="-o HostName=ssh.github.com -o Port=443 -o User=git -o IdentityFile=$KEY -o IdentitiesOnly=yes -o UserKnownHostsFile=$KH -o GlobalKnownHostsFile=/dev/null -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=20 -o ServerAliveInterval=15"
export GIT_SSH_COMMAND="ssh $SSH_OPTS"

echo "→ 验证 SSH 认证"
ssh $SSH_OPTS -T git@github.com 2>&1 | head -3 || true

echo "→ 推送 main 分支"
git push --progress -u origin main
