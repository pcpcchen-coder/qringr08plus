# M6 Mac 接手指南：QRing Studio 0.4.0

更新日期：2026-10-12（Asia/Taipei）。已完成 M6 原始碼接手、開發環境、原生介面、戒指連線、加速度取樣與既有權限排查。歷程見 [M6 本機紀錄](2026-10-09-m6-setup.md)，最新功能與驗證見 [0.3.0 進度](2026-10-11-studio-0.3.0-progress.md)。

新增快照輪詢節拍與等待設定，見 [0.4.0 輪詢調校](2026-10-12-snapshot-polling.md)。

## 接手狀態

- 最新 App 原始碼、UI、BLE 引擎、校正流程、建置腳本與測試完整收錄在 `mac-app/`。
- 已整合選單列、戒指單擊校正、觸控／健康候選回饋、可儲存的防重複與方向範圍、資料間隙續移。
- 合計 50 項合成測試，封裝啟動及簽章檢查；實際驗證日期與範圍見進度文件。
- M6 實機曾驗證連線、加速度、原生設定介面與權限恢復；完整方向手感、誤觸率、長期穩定性與耗電尚待測試。
- 健康有效回報與醫療準確度分開；未知候選只顯示原始讀值。充電自動暫停與配戴偵測尚未實作。
- 內建心率排程的關閉 ACK 後讀回未改變，只能保證 App 不主動啟動未勾選項目。

## 先帶走哪些東西

1. **安裝包**：0.4.0 請從最新原始碼建置，見 [建置產物說明](../releases/README.md)。尚無 GitHub Release 二進位下載。以下 QRing-Studio-0.2.0-arm64.dmg 為早期交付的歷史包，不能當作新版。
   原機位置：~/Projects/AIRingAgent/releases/。
   安裝包沒有上傳 GitHub Release，單純 clone Repo 不會取得二進位 App。
   SHA-256：
   ```text
   ce04ceb2c391c7f09c034529c4fa78798b98f667d9c466b6a5bce83e47b8ab71
   ```
2. **原始碼**：clone 此 Repo，見下方。
3. **校正（選用）**：原機 ~/Library/Application Support/QRing Studio/calibration.json。
   帶至新機同一路徑，且在 App 關閉時放入；不要覆蓋新機已完成的校正。也可以在新機重新做中立、右、左、上、下五步校正。
4. **私人紀錄（選用）**：同資料夾的 session-*.jsonl，可能包含健康資訊。只以私人方式搬移，不提交公開 Repo。
5. 不搬移 .venv、不沿用原機的 BLE UUID、不搬移或修改 macOS 權限資料庫。

安裝包不應包含個人校正與健康紀錄。原機 ~/Applications/QRing Studio.app 是已安裝 App，必要時亦可私人複製，但優先使用 DMG。

## 在目標 Mac 安裝與驗收

1. 確認為 Apple Silicon。若是 Intel，這個安裝包不可使用。
2. 將最新建置的 QRing Studio.app 複製到 Applications；若使用早期 DMG，要先確認其版本。
3. 本版為 ad-hoc 簽章、未經 Apple 公證。若系統拒絕開啟，保留完整提示交給接手 Agent 判讀；不要透過關閉系統防護或刪除權限資料庫處理。
4. 關閉原 Mac 的戒指 App／舊腳本，讓手機 QRing 斷線。避免兩台 Mac 同時連線。
5. 在新機開啟 App，允許藍牙；按「連接戒指」，核對名稱、硬體、韌體、電量。
6. 完成／驗證五步校正。
7. 按「授權滑鼠控制」，依新機設定名稱授權 QRing Studio：「裝置控制和資料取用」或舊版的「輔助使用」。原機授權不會隨 App 搬移。
8. 先只勾選游標移動，不開點擊。長按開始，逐一驗證四方向、中立停止、長按暫停、取消勾選停止。
9. 分別單次測試心率與血氧；未勾選項目不得持續排程。
10. 確認收發紀錄可檢索與匯出，關閉 App 能停止服務與嘗試還原設定。

如果新機找不到戒指，不直接套用早期文件的原機 UUID。目前 App 會按 R08_E703 名稱搜尋，或取得已連線的 HID peripheral。

## 在目標 Mac 繼續開發

```sh
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/pcpcchen-coder/qringr08plus.git
cd qringr08plus
uname -m
sw_vers
xcode-select -p
/usr/bin/python3 --version
```

以上只讀取環境。若已有 checkout，更新該 checkout，勿重複 clone 或覆蓋未提交工作。

### 打包前必須核對

目前 mac-app/build_app.py 使用：

- 執行中 Python 的 Apple Python3.framework（支援 Xcode 或 Command Line Tools 位置）。
- 其中 Versions/3.9/bin/python3.9。
- 執行中 venv 的 site-packages；請使用 Repo 根目錄的 .venv。
- swiftc、codesign。
- arm64-apple-macosx13.0 編譯目標。

不要假設新機的 /usr/bin/python3 仍是 3.9。先檢查：

```sh
/usr/bin/python3 -c 'import sys; print(sys.version); print(sys.base_prefix)'
command -v swiftc
command -v codesign
```

若 3.9 framework 不存在，**先適配打包腳本與原生容器的 runtime 路徑**，不要用新版本建立 venv 然後強行套入舊版的 3.9 路徑。這是接手時最重要的建置限制。安裝已封裝 DMG 則不需要新機另外安裝 Python。

若指定的 framework 存在，從 Repo 根目錄：

```sh
/usr/bin/python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cd mac-app
../.venv/bin/python -m unittest -v test_studio.py
node --test test_calibration.cjs
../.venv/bin/python build_app.py
../releases/.build.noindex/'QRing Studio.app'/Contents/MacOS/QRingStudio --self-test
```

build_app.py 會重建 Repo 的 releases/.build.noindex/QRing Studio.app；不要在這個生成物內手改檔案。實際修改 mac-app/ 原始碼再重新打包。個人資料保存在 Application Support，與生成物分開。建置產物不放在一般可索引資料夾，舊版另以 ZIP 備份，以免啟動區出現多個同名項目。

## 程式與資源位置

| 位置 | 責任 |
| --- | --- |
| mac-app/native/Studio.swift | AppKit / WKWebView 容器、內建服務啟動、原生匯出、結束時清理 |
| mac-app/server.py | 本機 API、校正儲存、來源檢查與匯出 |
| mac-app/device.py | 唯一 BLE 連線、按需排程、停止／還原、封包解析、游標輸出 |
| mac-app/ring_mouse.py | 四方向映射、可調範圍、中立停止區、平滑、資料間隙續移 |
| mac-app/web/ | App 主介面與五步校正 |
| mac-app/catalog.json | 社群協定入口，不能當作實機支援清單 |
| mac-app/verified-device.json | 綁定本戒指與韌體的既有實測，不含個人健康數值 |
| mac-app/test_studio.py | 38 項合成 unit/API 測試 |
| mac-app/test_calibration.cjs | 12 項 JavaScript 校正與移動規則測試 |
| mac-app/build_app.py | 內建 runtime 打包與 ad-hoc 簽章 |
| requirements.txt | 版本固定的相依套件 |

App 服務：127.0.0.1:18765；self-test：18767。早期網頁校正服務：8765。繼續開發 App 時勿把舊版網頁服務當作 App 後端，也勿讓舊版 ring_mouse.py 與新 App 同時控制同一顆戒指。

## 接手 Agent 的工作順序

1. 讀本指南、[App README](../mac-app/README.md)與實機驗證紀錄。
2. 查新機環境與目前 Repo 版本，保留使用者未提交的工作。
3. 先執行測試與封裝啟動檢查；實機操作另核對授權、連線、四方向、中立停止及長按暫停。
4. 若要重建，先解決 Python runtime 的可移植性。
5. 維持所有持續量測與滑鼠預設關閉；斷線不得自動重啟游標控制。
6. 保留「實機回報／有效值／準確度」的區分，不把候選功能宣稱為可靠健康量測。
7. 不刷韌體、不恢復原廠、不送出未知破壞性寫入。
8. 私人校正與健康紀錄不得提交公開 Repo；文件可記錄不含個人數值的功能結論。
