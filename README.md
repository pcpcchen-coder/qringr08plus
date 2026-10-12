# QRing R08 Plus / AIRingAgent

**換機接手：[M6 Mac 安裝、資料搬移與開發指南](docs/M6-HANDOFF.md)**

## 貼身 AI 助理規劃

[眼鏡 × Apple Watch × 戒指 × iPhone：獨立應用藍圖](docs/wearable-ai/README.md)

包含裝置分工、九種應用構想、三個優先原型、AI 互動與工作記憶、分階段驗證及官方來源。此部分為產品規劃，尚未完成四裝置整合。

## 戒指查詢紀錄

[查詢與來源索引](docs/ring-research/README.md)彙整配戴／取下判斷、充電處理、關機與官方耗電規格，並連結既有觸控、加速度與健康能力實測。每份記錄附來源、查核日期及待驗證項目。

## QRing Hand：用戒指控制機器手掌

握拳時，接在 Raspberry Pi 上的 Amazing Hand 右手跟著握拳。它是獨立的 Mac App，程式放在手那一邊的 Repo：[this-is-yourX](https://github.com/pcpcchen-coder/this-is-yourX) 的 `right_hand/control_methods/qring_fist/`（[PR #6](https://github.com/pcpcchen-coder/this-is-yourX/pull/6)）。這裡只留[說明與這次在戒指上看到的事](docs/2026-10-11-qring-hand.md)，包含三軸更新率的觀察：等回報再送約 4 Hz，固定每 0.1 秒送一次約 10–15 Hz。

## QRing Studio 0.4.0 Mac App

可安裝的 Apple Silicon Mac App 已完成：勾選式滑鼠控制、五步方向校正、裝置電量與版本、按需心率／血氧量測、能力探索與完整本機收發紀錄。

0.3.0 加入常駐選單列圖示、游標狀態文字與下拉快捷控制；關閉主視窗後仍可在選單列操作。[選單列使用說明](mac-app/README.md#選單列狀態與快捷操作)。

[App 安裝與開發文件](mac-app/README.md) · [0.4.0 快照輪詢調校](docs/2026-10-12-snapshot-polling.md) · [0.3.0 功能進度](docs/2026-10-11-studio-0.3.0-progress.md) · [版本紀錄](CHANGELOG.md)

所有 App 持續量測預設關閉；未確認的協定功能標示為候選。戒指內建心率排程的停止尚未確認，詳見文件。健康數值與個人校正檔不提交至此公開 Repo。

Repo 已收錄 0.4.0 的完整原始碼、測試與建置腳本；二進位安裝包仍為本機產物，尚未發布 GitHub Release。詳見 [建置產物說明](releases/README.md)。

0.4.0 新增快照輪詢調校，可分別設定發送節拍、取樣等待上限與輪後休息時間；顯示實際送出、接收、數值變化及等待逾時統計。

0.3.0 已包含：姿勢穩定後以戒指單擊確認校正、重複觸控的時間與次數回饋、健康候選的本次原始讀值、可儲存的防重複間隔與四方向容許範圍。資料間隙會延續游標速度，回中立立即停止。充電自動暫停與配戴偵測仍是規劃，沒有當成已完成功能。

## 獨立 CLI 舊原型

以下是根目錄獨立 CLI／早期校正工具的使用紀錄，與 `mac-app/` 的最新 App 分開。CLI 的 0.35 秒逾時停止預設保留；最新 App 行為請看上方文件。

將 QRing R08 的加速度與觸控事件轉成 Mac 輸入。目前有傾斜滑鼠原型，使用者已確認游標能移動；原本方向不符合直覺，因此新增五姿勢校正網頁。

## 已驗證

實機：R08_E703 / RT08_V3.1 / RT08_3.10.48_260309。MacBook Air、Python 3.9.6。

- BLE 連線、GATT 版本讀取。
- 單擊、上滑、下滑、長按四種觸控事件。
- 三軸加速度，約 10Hz 快照輪詢短測；包含重複值。
- 傾斜滑鼠程式 dry-run：校正成功、87 筆三軸資料、設定還原。
- 中立死區、速度限制、資料逾時與暫停邏輯檢查。

詳細紀錄在 [docs](docs)，原始資料在 [logs](logs)。

## 校正網頁

```sh
.venv/bin/python calibration_server.py
```

在這台 Mac 的瀏覽器開啟 http://127.0.0.1:8765，按「連接戒指」，依序記錄中立、向右、向左、向上、向下姿勢。每個姿勢保持約 3 秒，再用頁面內的游標確認方向與速度，按「儲存校正」。設定保存在本機 calibration.json，後續 ring_mouse.py 自動使用；不要把個人校正檔提交到 GitHub。

完成校正後先按「中斷連線」，再啟動戒指滑鼠，避免兩個程式同時使用戒指。

網頁版本不控制系統游標，也不會自動啟用點擊。Start Calibration.command 提供本機啟動入口。

[私人線上入口](https://qring-direction-calibration.george-chen-1104.chatgpt.site)只提供介面與本機入口；實際感測與設定留在 Mac。沒有本機服務時不能進行實機校正。

## 安裝

僅針對 macOS 原型，已在 Python 3.9.6 驗證。其他系統與版本尚未測試。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

手機 QRing 先斷線。Mac 若已把戒指當作 HID 滑鼠連線，程式會先取用已連線 peripheral，再視需要掃描。

## 使用

先測試資料，不移動或點擊游標：

```sh
.venv/bin/python ring_mouse.py --dry-run --seconds 15
```

系統設定 → 隱私權與安全性 → 輔助使用，允許執行程式的 App 控制電腦。Codex 執行時先授權 Codex；Terminal 執行時授權 Terminal。權限可能依系統歸屬到 Python，應以實際啟動後的權限檢查為準。程式權限不足會退出，不會繞過限制。

僅移動游標，預設不點擊：

```sh
.venv/bin/python ring_mouse.py --seconds 60
```

1. 保持戒指戴在手上、手指靜止 3 秒，直到 calibrated / ready；若已有網頁校正檔，程式直接使用已儲存姿勢。
2. 啟動時暫停；長按約 3 秒啟用／暫停移動。
3. 向兩個方向緩慢傾斜。實際方向受配戴方向影響；如需反轉，使用 --invert-x 或 --invert-y。
4. Control-C 結束，或 60 秒自動結束，程式會嘗試還原設定。

也可雙擊 Start Ring Mouse.command；若從 GitHub 下載，需先設定可執行權限（chmod +x），macOS 可能需要確認允許開啟。

確認移動可控後，才使用 --click 啟用單擊左鍵。沒有啟用拖曳、右鍵或捲動。

## 控制與限制

- 重力方向投影到校正姿勢的兩個切平面方向，映射成游標速度，不做加速度雙重積分。
- 8 度死區、平滑、預設 220 pixels/sec 上限。
- 資料超過 0.35 秒沒更新、幅度異常或偏離中立姿勢過多，速度歸零。
- 游標限制在主螢幕；多螢幕尚未支援。
- 每次啟動需校正，不自動登入執行。
- 斷線／輪詢失敗會結束，不自動恢復控制。
- 輔助使用權限不足會退出；已觀測游標移動；點擊與長時間手感尚待驗證。
- 某些測試中停止 ACK 後仍有資料；程式結束會送停止指令並還原觸控設定，不宣稱所有韌體均立即停止串流。意外強制終止時，還原可能無法完成。

原始 BLE 記錄會保存在本機 logs。社群協定依據：[Halo-Ring](https://github.com/MRziyi/Halo-Ring/blob/main/Doc/09-r08-ble-protocol-spec.md)。
