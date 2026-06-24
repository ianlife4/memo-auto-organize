@echo off
chcp 65001 >nul
title Dropbox Token 取得工具
python "%~dp0scripts\get_token.py"
pause
