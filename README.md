# QRing R08 Plus / AIRingAgent

將 QRing R08 的加速度與觸控事件轉成 Mac 輸入。目前有可執行的傾斜滑鼠原型；真實系統游標移動仍待取得輔助使用權限後實測。

## 已驗證

實機：R08_E703 / RT08_V3.1 / RT08_3.10.48_260309。MacBook Air、Python 3.9.6。

- BLE 連線、GATT 版本讀取。
- 單擊、上滑、下滑、長按四種觸控事件。
- 三軸加速度，約 10Hz 快照輪詢短測；包含重複值。
- 傾斜滑鼠程式 dry-run：校正成功、87 筆三軸資料、設定還原。
- 中立死區、速度限制、資料逾時與暫停邏輯檢查。

詳細紀錄在 [docs](docs)，原始資料在 [logs](logs)。

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

1. 保持戒指戴在手上、手指靜止 3 秒，直到 calibrated / ready。
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
- 輔助使用權限不足會退出；實際游標、點擊與長時間手感尚待驗證。
- 某些測試中停止 ACK 後仍有資料；程式結束會送停止指令並還原觸控設定，不宣稱所有韌體均立即停止串流。意外強制終止時，還原可能無法完成。

原始 BLE 記錄會保存在本機 logs。社群協定依據：[Halo-Ring](https://github.com/MRziyi/Halo-Ring/blob/main/Doc/09-r08-ble-protocol-spec.md)。
