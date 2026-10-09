# AIRingAgent v0.1：MacBook Air 環境與 R08 連線紀錄

日期：2026-10-09（Asia/Taipei）

## 目前結果

- 使用者已確認戒指搭配手機 QRing App 正常工作。
- 本次實際操作平台為 MacBook Air。
- Python 虛擬環境與 BLE 套件安裝完成，套件載入與相依檢查通過。
- Mac 成功掃描到 R08_E703，並成功連線、列出 GATT services 與 characteristics。
- 測試結束後正常斷線。
- 尚未驗證觸控事件、加速度資料、更新率或控制 Mac 的功能。

## 環境

專案位於 ~/Projects/AIRingAgent，虛擬環境為 .venv。

| 項目 | 已驗證版本 |
| --- | --- |
| Python | 3.9.6（Apple Command Line Tools） |
| pip | 26.0.1 |
| bleak | 1.1.1 |
| pyobjc-core | 11.1 |
| pyobjc-framework-Cocoa | 11.1 |
| pyobjc-framework-CoreBluetooth | 11.1 |
| pyobjc-framework-libdispatch | 11.1 |
| async-timeout | 5.0.1 |
| typing-extensions | 4.16.0 |

## 問題與處理

### 1. 初次 macOS 設定失敗的原始錯誤未取得

接手時資料夾及 .venv 已存在，但 bleak 尚未安裝。無法據此判定使用者原先終端機出錯的原因。

### 2. 安裝時選到不支援 Python 3.9 的相依版本

初次安裝使用 pip 21.2.4。解析過程選到 pyobjc-core 12.0，輸出指出該版本已撤回，理由是 python_requires 錯誤宣稱支援 Python 3.9。

停止該次安裝，更新 pip，並明確指定 PyObjC 11.1 系列，重新安裝成功。

```sh
cd ~/Projects/AIRingAgent
.venv/bin/python -m pip install --no-cache-dir --upgrade pip
.venv/bin/python -m pip install --no-cache-dir bleak \
  'pyobjc-core==11.1' \
  'pyobjc-framework-Cocoa==11.1' \
  'pyobjc-framework-CoreBluetooth==11.1' \
  'pyobjc-framework-libdispatch==11.1'
```

驗證：

```sh
.venv/bin/python -m pip check
.venv/bin/python -c 'from bleak import BleakScanner; import CoreBluetooth; print("BLE_IMPORT_OK")'
```

結果為 No broken requirements found 與 BLE_IMPORT_OK。pip 曾顯示快取資料夾不可寫的警告；安裝以 --no-cache-dir 完成。

### 3. 掃描時 Mac 藍牙關閉

第一次掃描失敗：

```text
bleak.exc.BleakError: Bluetooth device is turned off
```

使用者在 Mac 控制中心開啟藍牙後，第二次掃描成功。掃描前使用者依指示準備戒指與暫停手機藍牙連線。

## 掃描結果

- 裝置名稱：R08_E703
- 本次觀測 RSSI：-50 dBm
- 廣播 service UUID：0000fee7-0000-1000-8000-00805f9b34fb

RSSI 僅為當次觀測值。macOS 提供的裝置識別碼為本機 UUID，不應當作戒指的硬體 MAC 位址；此公開紀錄省略本機 UUID 與其他附近裝置資訊。

## 實機 GATT 列舉結果

連線輸出為 CONNECTED True，列舉完成輸出 GATT_READ_OK。

| Service UUID | Characteristic UUID | Properties |
| --- | --- | --- |
| 6e40fff0-b5a3-f393-e0a9-e50e24dcca9e | 6e400002-b5a3-f393-e0a9-e50e24dcca9e | write-without-response, write |
| 6e40fff0-b5a3-f393-e0a9-e50e24dcca9e | 6e400003-b5a3-f393-e0a9-e50e24dcca9e | notify |
| de5bf728-d711-4e47-af26-65e3012a5dc7 | de5bf72a-d711-4e47-af26-65e3012a5dc7 | write-without-response, write |
| de5bf728-d711-4e47-af26-65e3012a5dc7 | de5bf729-d711-4e47-af26-65e3012a5dc7 | notify |
| 0000180a-0000-1000-8000-00805f9b34fb | 00002a25-0000-1000-8000-00805f9b34fb | read |
| 0000180a-0000-1000-8000-00805f9b34fb | 00002a27-0000-1000-8000-00805f9b34fb | read |
| 0000180a-0000-1000-8000-00805f9b34fb | 00002a26-0000-1000-8000-00805f9b34fb | read |
| 0000180a-0000-1000-8000-00805f9b34fb | 00002a23-0000-1000-8000-00805f9b34fb | read |
| 0000fee7-0000-1000-8000-00805f9b34fb | 0000fea1-0000-1000-8000-00805f9b34fb | notify, read |
| 0000fee7-0000-1000-8000-00805f9b34fb | 0000fec9-0000-1000-8000-00805f9b34fb | read |
| 0000fee7-0000-1000-8000-00805f9b34fb | 0000fea2-0000-1000-8000-00805f9b34fb | write, indicate, read |

本次只連線與列舉服務，未讀取上述 characteristic 的內容，未訂閱通知，未寫入協定指令，未更新韌體。存在 notify 通道不代表觸控資料已驗證。

## 下一步

1. 讀取硬體與韌體版本，核對實機協定。
2. 先嘗試訂閱適合的通知通道，記錄原始封包。
3. 配合使用者單擊、長按及上下滑動，確認事件與操作的對應。
4. 若需初始化或啟用指令，先核對來源與實機版本。
5. 觸控事件驗證後，再建立 Mac 控制映射；加速度資料另行驗證。

每一步以實機結果確認後再繼續。
