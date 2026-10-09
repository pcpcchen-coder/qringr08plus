#!/bin/zsh
cd "$(dirname "$0")" || exit 1
echo "請戴好戒指並保持手指靜止 3 秒。"
echo "校正成功後，長按約 3 秒開始／暫停游標移動。"
echo "此版本不啟用點擊；按 Control-C 停止，或 60 秒自動結束。"
./.venv/bin/python -u ring_mouse.py --seconds 60
echo "測試結束。按 Enter 關閉。"
read
