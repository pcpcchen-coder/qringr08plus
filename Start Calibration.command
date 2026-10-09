#!/bin/zsh
cd "$(dirname "$0")" || exit 1
echo "校正網頁：http://127.0.0.1:8765"
echo "請在瀏覽器開啟這個網址。按 Control-C 結束服務。"
./.venv/bin/python -u calibration_server.py
read
