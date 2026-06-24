@echo off
chcp 65001 >nul
title 推上 GitHub

cd /d "%~dp0"

REM 檢查 git 是否安裝
where git >nul 2>&1
if errorlevel 1 (
    echo 錯誤: 沒裝 git
    echo 下載: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM 第一次跑時詢問 GitHub repo URL
if not exist ".git" (
    echo.
    echo === 第一次設定 ===
    echo 先去 https://github.com/new 建一個 private repo "memo-auto-organize"
    echo 建好後，把它的 URL 貼這 (例如 https://github.com/你的帳號/memo-auto-organize.git):
    set /p REPO_URL=Repo URL:
    git init -b main
    git remote add origin %REPO_URL%
)

echo.
echo === 推 code ===
git add -A
git commit -m "auto: %date% %time%" 2>nul
git push -u origin main

if errorlevel 1 (
    echo.
    echo 推失敗。可能原因:
    echo  - 還沒 login GitHub: 跑 `gh auth login` 或 `git credential` 處理
    echo  - Branch 名稱不是 main: git push -u origin master
    pause
    exit /b 1
)

echo.
echo === 成功 ===
echo 進 GitHub repo 的 Actions 分頁，手動跑一次 "自動整理 MEMO烏骨雞" 確認跑得通
echo.
pause
