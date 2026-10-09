# 已連線戒指與被動通知測試

日期：2026-10-09（Asia/Taipei）

## 發現

充電後再次掃描 R08_E703 20 秒，仍未找到廣播。但 macOS system_profiler 顯示 R08_E703 位於 Connected 清單，Minor Type 為 Mouse，Services 為 HID BLE。這表示未掃描到廣播不等於戒指不可用；先前一直以廣播搜尋裝置的方法不足以涵蓋此狀態。

改用 CoreBluetooth retrieveConnectedPeripheralsWithServices_，查詢 HID service 1812 與戒指 primary service，再以名稱精確匹配 R08_E703，取得 peripheral 和 Bleak central manager delegate，成功建立 BleakClient。

此方式使用 Bleak 1.1.1 的內部 CoreBluetooth backend，未來升級時需重新驗證。

## 實機讀取版本

- Hardware Revision（0x2A27）：RT08_V3.1
- Firmware Revision（0x2A26）：RT08_3.10.48_260309

上述兩個值已透過 GATT 實際讀取；韌體值也與 macOS 顯示相符。

## 被動通知測試

成功訂閱 6e400003-b5a3-f393-e0a9-e50e24dcca9e，監聽 45 秒。期間已提示使用者進行單擊、上下滑動與長按，但未收到使用者確認實際完成各操作。

結果：NOTIFY_COUNT 0。

未送出應用層初始化或觸控設定指令。訂閱通知本身涉及標準 BLE 通知啟用。測試結束正常退出 BleakClient。

此結果僅證明該監聽時段沒有收到該通道通知，不能判定戒指觸控故障或不支援手勢。

## 後續

[Halo-Ring 社群協定](https://github.com/MRziyi/Halo-Ring/blob/main/Doc/09-r08-ble-protocol-spec.md)描述觸控通知的初始化流程，但其實機測試韌體為 RT08_3.10.46_250621，與本戒指不同。需核對設定與回應，再進行受控手勢測試，逐項記錄原始封包。

後续連線應先查詢已連線 peripheral，再在必要時掃描。尚未啟用或验证原始觸控事件，亦未建立 Mac 控制映射。
