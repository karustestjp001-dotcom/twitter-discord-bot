# 專案工作偏好

## Bilibili Discord 連結

- 當使用者要求將 Bilibili 網址改成 Discord 可直接播放的連結時，直接轉換成 BiliFix 格式，不需要再次確認。
- Bilibili 長網址改用 `vxbilibili.com` 網域；`b23.tv` 短網址改用 `vxb23.tv` 網域。
- 保留影片 BV 編號、分 P 與有效時間參數，移除 `spm_id_from`、`vd_source` 等分享追蹤參數。
- 不主動展開或查詢影片內容，除非使用者另外要求。
- 機器人發送到 Discord 的 Bilibili 影片連結必須使用 BiliFix 網址，並保持可點擊。
- 第一個影片連結可正常展開預覽；同則訊息後續連結使用尖括號包住，避免產生多個預覽。
