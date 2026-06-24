# MEMO 烏骨雞 自動整理

GitHub Actions 每 5 分鐘自動跑一次：透過 Dropbox API 整理 `MEMO烏骨雞/` 根目錄散落的 PDF，重建閱讀器索引。

## Setup（一次性）

### 1. Dropbox App
1. https://www.dropbox.com/developers/apps → Create app
2. Scoped access / Full Dropbox / 名稱隨意
3. Permissions 分頁勾：`files.metadata.read`、`files.metadata.write`、`files.content.read`、`files.content.write` → Submit
4. Settings 分頁有 App key / App secret，下一步要用

### 2. 取 Refresh Token
- 本機雙擊 `取token.bat`，照 prompt 操作 → 拿到 token 寫進 `.secrets.json`

### 3. GitHub Repo
1. 建一個 private repo `memo-auto-organize`
2. Settings → Secrets and variables → Actions → New repository secret，加 3 個：
   - `DROPBOX_APP_KEY`
   - `DROPBOX_APP_SECRET`
   - `DROPBOX_REFRESH_TOKEN`
3. 雙擊本機 `推上github.bat` 把 code push 上去
4. 進 Actions 分頁手動跑一次 `自動整理 MEMO烏骨雞` 確認 ✓

## 跑起來會發生什麼

每 5 分鐘 GHA runner 會：
1. 用 Dropbox API 連你的 Dropbox
2. 列 `/MEMO烏骨雞/` 根目錄散落 PDF
3. 跑跟本機 update.py 一樣的 parser 規則
4. 把檔案 move 到 `2026/個股/`、`2026/外資報告/` 等對應目錄並改名
5. 重建 `/MEMO烏骨雞/閱讀器/assets/report-index.js`

朋友從別台機器把 PDF 丟進 `/MEMO烏骨雞/`（共享資料夾），5 分鐘內會自動整理好。你電腦不用開。
