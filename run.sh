#!/bin/sh
# Scrcpy Studio 启动脚本
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python app.py "$@"
