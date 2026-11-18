#!/bin/bash
# LaunchAgent 守护：检测到 USB Android 设备上线时拉起 Scrcpy Studio。
# 参数：$1 = adb 绝对路径，$2 = ScrcpyStudio.app 路径
ADB_BIN="${1:-adb}"
APP_PATH="${2:-}"

if [ -z "$APP_PATH" ]; then
    echo "缺少 App 路径" >&2
    exit 1
fi

prev=""
while true; do
    now=$("$ADB_BIN" devices 2>/dev/null \
          | /usr/bin/awk '$2 == "device" && $1 !~ /:/ { print $1 }' \
          | /usr/bin/sort | /usr/bin/tr '\n' ',')
    if [ -n "$now" ] && [ "$now" != "$prev" ]; then
        /usr/bin/open "$APP_PATH" >/dev/null 2>&1 || true
    fi
    prev="$now"
    /bin/sleep 3
done
