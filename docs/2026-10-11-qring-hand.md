# QRing Hand：用戒指控制機器手掌

日期：2026-10-11（Asia/Taipei）。這顆戒指（R08_E703 / RT08_V3.1 / RT08_3.10.48_260309）多了一種用途：握拳時，接在 Raspberry Pi 上的 Amazing Hand 右手跟著握拳。

## 程式在哪裡

程式不放在這個 Repo。它是「控制那隻手的方法之一」，和手放在一起：

- Repo：[pcpcchen-coder/this-is-yourX](https://github.com/pcpcchen-coder/this-is-yourX)
- 資料夾：`right_hand/control_methods/qring_fist/`（macOS App「QRing Hand」）
- 決策與現況：該 Repo 的 ADR-0008 與 [PR #6](https://github.com/pcpcchen-coder/this-is-yourX/pull/6)；合併前，程式在分支 `claude/adr-0008-qring-fist-control`。

這個 Repo 仍然是戒指本身的資料：協定實測、QRing Studio、查詢紀錄。

## 從這個 Repo 沿用的部分

QRing Hand 的戒指連線（`ring.py`）是照 `mac-app/` 已在這顆戒指上驗證過的做法寫的，兩邊各自維護：

- 通道與封包：寫入 6e400002、通知 6e400003；16 bytes，最後一個 byte 是前 15 個的加總 mod 256。
- 三軸：送 `A1 03` 要求一筆快照，回報的 bytes 2..7 是三個 big-endian signed int16；結束時送 `A1 00`。見[加速度實測](2026-10-09-accelerometer-verified.md)。
- 觸控：先讀回 `3B` 的原設定，啟用回報，結束時還原並讀回比對；事件是 `73 2D`（3 單擊、4 長按）。見[觸控實測](2026-10-09-touch-events-verified.md)。
- 電量：`03`。
- 找戒指：先取已連線的 peripheral，找不到再依名稱掃描。

QRing Hand 不啟動任何光學量測，也不改戒指的內建排程。它只用到重力方向：校正記下「張開」「握拳」兩個讀值，中間換算成握拳程度。

## 和 QRing Studio 的關係

- 兩個 App 不要同時連同一顆戒指。QRing Hand 連線前會問本機的 QRing Studio（127.0.0.1:18765 的 `api/control-status`）是否連著戒指，是的話拒絕連線。QRing Studio 這一側沒有改，不會反過來檢查。
- QRing Hand 是另一個 App（bundle id `com.pcpcchen.qringhand`，本機服務 127.0.0.1:18775，資料在 `~/Library/Application Support/QRing Hand/`），不需要「裝置控制和資料取用」權限，需要藍牙與區域網路權限。

## 這次在戒指上看到的事

2026-10-11 在 M6 上用這顆戒指實際操作。屬於使用時的觀察（QRing Hand 畫面上的數字），不是正式量測：

- **等回報再送，約 4 Hz**（QRing Hand 0.1.0，上午與下午各一段，各約一分鐘）。輪詢是「送一次 `A1 03`、等到回報再送下一次，再停 0.06 秒」。
- **固定節拍，約 10–15 Hz**（QRing Hand 0.1.1，14:52 連上後）。輪詢改成固定每 0.1 秒送一次 `A1 03`、不等回報，也就是[加速度實測](2026-10-09-accelerometer-verified.md)當時的送法；畫面上看到 9.8 Hz，稍後 14.7 Hz。比送出要求的 10 Hz 高的那一部分是什麼沒有查（那份實測提過快照輪詢會夾帶背景資料與重複值）。固定節拍長時間使用的穩定性與耗電還沒看過。
- `mac-app/device.py` 的輪詢也是等回報再送（之後再停 0.15 秒）。它在實機上的更新率沒有另外記錄；如果 QRing Studio 的游標也覺得不夠跟手，這是可以試的方向。這次沒有改 `mac-app/`。
- 連線、硬體與韌體版本讀取、電量、觸控回報的啟用都正常；兩次連線時畫面上的電量都是 100%。
- 觸控設定的還原：QRing Hand 0.1.1 中斷連線時紀錄了「觸控設定已還原」（還原後讀回的內容與原本相同）。0.1.0 在結束時若剛好有取樣進來，收尾會卡住而跳過還原；M6 上已換成修掉這個問題的 0.1.1。0.1.0 用過的那兩段結束時有沒有還原，沒有紀錄。

個人校正與健康數值沒有放進任何一個 Repo。

## 2026-10-12：QRing Studio 0.4.0 補充

Studio 已新增可調發送節拍、取樣等待上限與輪後休息，並呈現實際送出、接收與數值變化統計。上段為 2026-10-11 的歷史觀察；新介面與原預設的實機到達率見 [快照輪詢調校](2026-10-12-snapshot-polling.md)。要採完全不等回報的固定 10 Hz 目標，可設節拍 0.1 秒、取樣等待 0、休息 0；實際回報仍須由各自介面的統計確認。兩個 App 仍不要同時連同一顆戒指。
