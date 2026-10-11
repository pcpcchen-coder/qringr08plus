# QRing Studio 建置產物

目前原始碼版本：0.3.0（bundle build 3）。完整功能與驗證見 [進度文件](../docs/2026-10-11-studio-0.3.0-progress.md)。

此目錄的 App、DMG、ZIP、備份、研究圖片及 UI 驗證產物皆留在本機；Git 只追蹤本說明。0.3.0 尚未提供 GitHub Release 二進位下載，clone Repo 取得的是原始碼。

從 Repo 根目錄，在具有 Apple Python 3.9.framework 的專案 venv 執行：

```sh
.venv/bin/python mac-app/build_app.py
'releases/.build.noindex/QRing Studio.app/Contents/MacOS/QRingStudio' --self-test
```

輸出：`releases/.build.noindex/QRing Studio.app`。建置腳本會簽署並驗證 bundle；請勿直接修改生成的 App。要更新已安裝 App，先正常結束 App，保留個人資料，使用新建置版本替換同一路徑，並重新確認既有藍牙與控制權限。

本機 ad-hoc 簽章未經 Apple 公證；僅供 arm64 Apple Silicon。使用與開發需求見 [App README](../mac-app/README.md)。個人 `calibration.json`、`preferences.json` 及工作階段紀錄不應包含在可分享的安裝包。

先前 `QRing-Studio-0.2.0-arm64.dmg` 是歷史私人交付，不代表 0.3.0。後續若發布可下載安裝包，須在此補上實際 Release 網址、版本、SHA-256 與驗證日期。
