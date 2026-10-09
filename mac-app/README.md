# QRing Studio 0.2.0

macOS 戒指開發 App，整合 QRing R08 五步校正、按需感測、游標控制與原始訊息記錄。只在 R08_E703 / RT08_V3.1 / RT08_3.10.48_260309 與 Apple Silicon MacBook Air、macOS 27.0.1 實機驗證。

## 安裝與使用

本次交付包含 QRing-Studio-0.2.0-arm64.dmg。打開後把 QRing Studio 拖曳到 Applications。App 已包含 Python 與相依套件，不需要先安裝 Python、Homebrew 或另外執行終端機命令。本次也已安裝到使用者的 ~/Applications/QRing Studio.app。

這是本機 ad-hoc 簽章開發版，未經 Apple 公證；跨電腦安裝與較舊 macOS 尚未測試。宣告最低版本為 macOS 13，CPU 為 arm64，不支援 Intel Mac。

1. 戴好戒指，讓手機 QRing 斷線，開啟 App 並按「連接戒指」。首次依 macOS 提示允許藍牙。
2. 「裝置與量測」顯示電量、充電狀態、硬體、韌體與序號；序號可能為空。
3. 「五步校正」依序記錄中立、右、左、上、下，各保持約 3 秒。用頁面內游標確認並儲存。
4. 返回「裝置與量測」，勾選「啟用 Mac 游標控制」。首次按「授權滑鼠控制」，在本機系統設定的「裝置控制和資料取用」允許 QRing Studio；舊系統可能稱「輔助使用」。
5. 滑鼠勾選後仍先暫停，長按切換移動／暫停；「立即暫停」可直接停住。取消勾選立即停止 App 的游標事件。
6. 確認移動可控後，可獨立勾選單擊左鍵。未實作拖曳、右鍵或捲動。
7. 需要量測的項目才勾選，也可按「量測一次」。關閉視窗或 ⌘Q 會停止 App 任務、嘗試還原戒指設定並關閉服務。

勿同時執行舊版 ring_mouse.py、calibration_server.py 或其他戒指客戶端。本版 App 使用單一 BLE 連線，服務監聽 127.0.0.1:18765。

## 持續量測與省電

所有 App 持續量測與滑鼠功能預設關閉，每次重新開啟都不自動恢復滑鼠。勾選加速度才輪詢 A1 快照；滑鼠或校正啟用時，因功能需要也會暫時讀取加速度與觸控，介面已說明這項依賴。

- 電量：連線時單次讀取；勾選後每 60 秒更新。
- 心率／血氧：只對勾選項目排隊量測，間隔可選 1、2、5、10 分鐘；每次最長 40 秒，收到有效非零值或配戴失敗即停止。光學量測不重疊；量測中暂停游標事件。
- 取消心率／血氧勾選：當次量測送 6A 停止指令，不排下一輪。
- 觸控：勾選、滑鼠或校正需要時才啟用回報；結束後還原原設定。
- 其他 BLE 通知：進階選項，只在勾選時訂閱其他 notify/indicate characteristic；不主動送出未知應用層指令。
- 未知資料即使由戒指自發送出，也會留下 RX 記錄；收到資料不表示 App 有啟動相應感測。

App 可以在連線時備份、暫停心率、血氧、壓力、HRV 的內建自動排程，並讀回驗證，離線時還原。**本韌體關閉內建心率排程後仍讀回原設定；因此只能保證 App 不主動啟動未勾選項目，不能保證戒指所有內部感測都停止。** 血壓、體溫與未知排程尚未接管，介面明確標示。

## 能力與訊息分類

App 內建 107 筆協定入口，區分 command / SPP 與量測候選；原廠／社群協定名稱不等於這顆戒指具有相應可用能力。

「能力探索」顯示本戒指既有實測與本次回應；唯讀查詢不會自動反覆執行。心率與血氧已取得非零回報，但沒有用參考醫療儀器驗證準確度。血壓、疲勞、綜合檢查、即時心率、壓力、血糖、HRV、體溫的 12 秒探測僅得到進度／未解碼值；不能據此宣稱功能不存在或有效量測完成。ECG 設定查詢被拒絕，尚未窮盡整個 ECG 家族。

未提供韌體更新、恢復原廠、關機或任意原始寫入。破壞性入口只列在探索清單，不提供執行。

「收發訊息」記錄 TX、RX（UUID、hex、校驗）、GATT、量測、解析、排程、設定還原與系統游標／點擊輸出。未知封包保留原文。加速度快照會附帶未解碼的其他通道，不為它們杜撰生理意義。

## 資料保存

使用者資料：~/Library/Application Support/QRing Studio/

- calibration.json：校正與速度；不包含在 App 安裝包。
- session-*.jsonl：每次執行的完整本機紀錄，可能包含健康資料。
- 畫面保留最近 1,000 筆，完整本次紀錄可透過原生存檔視窗匯出。
- 不自動上傳健康資料，不向公開 Repo 提交個人校正或原始健康紀錄。

持續高頻記錄會占用磁碟，目前不自動刪除舊紀錄；使用者可自行保留或移除自己的紀錄。

## 開發與打包

原始碼在此 mac-app/；native/Studio.swift 是 AppKit + WKWebView 容器，server.py 提供 loopback API，device.py 管理 BLE 與按需排程，ring_mouse.py 提供校正與游標映射。

已驗證開發環境需要 Apple Command Line Tools 的 Python3.framework（3.9）、Swift、codesign，以及專案 .venv 的 requirements.txt 相依套件。本版打包腳本目前固定這個已驗證環境，其他 Python framework 位置與版本尚未適配。

```sh
../.venv/bin/python -m unittest -v test_studio.py
../.venv/bin/python build_app.py
../releases/'QRing Studio.app'/Contents/MacOS/QRingStudio --self-test
```

build_app.py 包含 Python framework、site-packages、AppKit 執行檔及 UI。應用程式使用 Bundle 相對路徑、使用者 Application Support，不依賴開發者工作資料夾。內建 Python 停用 bytecode 寫入，避免修改已簽章的 bundle。

10 項 unit/API 測試涵蓋未勾選不輪詢、指定量測排程、取消量測、游標關閉、無效封包／其他通道隔離、四方向與逾時停住、原子存檔、跨來源拒絕、破壞性查詢拒絕、缺少校正不得啟用滑鼠。封裝後 native self-test 啟動內建 Python 與 API，正常關閉。

自動操作新 App 未獲工具授權，完整原生畫面点選與新 App 輔助使用授權流程仍需使用者首次操作驗證；沒有把未執行的 GUI 測試列為通過。

協定來源：[Halo-Ring 社群逆向文件](https://github.com/MRziyi/Halo-Ring/blob/main/Doc/09-r08-ble-protocol-spec.md)。社群實測使用不同韌體；本版的 verified-device.json 明確綁定本次實機版本且不含個人健康數值。
