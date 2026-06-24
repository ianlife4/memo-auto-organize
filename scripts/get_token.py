"""
Dropbox Refresh Token 取得工具

用法:
  1. 先在 Dropbox 開發者平台建好 App (Full Dropbox 權限)
  2. 在 App 的 Settings 頁面拿 App key 跟 App secret
  3. 雙擊 取token.bat (在父目錄)，這支 script 會跑
  4. 跟著 prompt 操作: 輸入 key/secret → 開瀏覽器授權 → 貼 code → 拿到 refresh token
  5. token 自動寫進 .secrets.json (這個檔不會 push 到 GitHub)

之後跑 GHA workflow 會把 token 從 GitHub Secrets 讀進來，不需要再跑這支。
"""
import json
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SECRETS_FILE = Path(__file__).resolve().parent.parent / ".secrets.json"


def main():
    print("=" * 60)
    print("Dropbox Refresh Token 取得工具")
    print("=" * 60)
    print()
    print("步驟 1: 開啟 https://www.dropbox.com/developers/apps")
    print("        進入你剛建的 App (memo-auto-organize)")
    print("        Settings 分頁裡會看到:")
    print("          App key:    xxxxxxxxxxxxxxx")
    print("          App secret: 點 Show 顯示")
    print()
    app_key = input("貼上 App key: ").strip()
    app_secret = input("貼上 App secret: ").strip()

    if not app_key or not app_secret:
        print("錯誤: key/secret 不能空白")
        sys.exit(1)

    # 步驟 2: 開瀏覽器授權 (PKCE flow, token_access_type=offline 拿 refresh token)
    auth_url = (
        "https://www.dropbox.com/oauth2/authorize?"
        + urllib.parse.urlencode({
            "client_id": app_key,
            "response_type": "code",
            "token_access_type": "offline",
        })
    )
    print()
    print("步驟 2: 開瀏覽器授權 (現在自動開)")
    print(f"  網址: {auth_url}")
    print()
    print("  瀏覽器會顯示授權頁面 → 按 'Allow' → 拿到一串 Access Code")
    print("  把那串 code 整個複製")
    print()
    webbrowser.open(auth_url)

    code = input("貼上 Access Code: ").strip()
    if not code:
        print("錯誤: code 不能空白")
        sys.exit(1)

    # 步驟 3: 用 code 換 refresh token
    print()
    print("步驟 3: 用 code 換 refresh token...")
    body = urllib.parse.urlencode({
        "code": code,
        "grant_type": "authorization_code",
        "client_id": app_key,
        "client_secret": app_secret,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.dropboxapi.com/oauth2/token",
        data=body,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"  失敗: HTTP {e.code}")
        print(f"  {err_body}")
        print()
        print("  常見原因:")
        print("  - Code 已過期或用過 (重跑這支 script 再來一次)")
        print("  - App key 或 secret 錯了")
        sys.exit(1)

    refresh_token = data.get("refresh_token")
    if not refresh_token:
        print(f"  錯誤: 回應沒有 refresh_token")
        print(f"  回應: {data}")
        sys.exit(1)

    # 寫進 .secrets.json
    secrets = {
        "DROPBOX_APP_KEY": app_key,
        "DROPBOX_APP_SECRET": app_secret,
        "DROPBOX_REFRESH_TOKEN": refresh_token,
    }
    SECRETS_FILE.write_text(json.dumps(secrets, indent=2), encoding="utf-8")

    print()
    print("=" * 60)
    print("成功！Refresh Token 已寫進 .secrets.json")
    print("=" * 60)
    print()
    print(f"檔案: {SECRETS_FILE}")
    print()
    print("Next steps:")
    print("  1. 等下要把這三個值貼到 GitHub repo 的 Secrets")
    print("  2. 然後雙擊 推上github.bat 把整個 auto_organize\\ push 上去")
    print()
    print("這個 .secrets.json 不會被 push (.gitignore 排除)")
    print()
    input("按 Enter 結束...")


if __name__ == "__main__":
    main()
