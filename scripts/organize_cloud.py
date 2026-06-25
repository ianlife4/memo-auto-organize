"""
雲端自動整理 - GitHub Actions 每 5 分鐘跑一次

流程:
  1. 連 Dropbox API (用 GHA Secrets 內的 token)
  2. 下載 stock_names.json (Dropbox 雲端的 master 版)
  3. 列 /MEMO烏骨雞/ 根目錄散落 PDF
  4. 對每個 PDF: parse_filename → 計算 target → dbx.files_move_v2 + rename
  5. 列 /MEMO烏骨雞/2025/ 跟 /2026/ 下的所有檔案
  6. 對每個檔案 build_entry → 組出 report-index.js
  7. 上傳 report-index.js + 更新後的 stock_names.json
"""
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import dropbox
from dropbox.exceptions import ApiError
from dropbox.files import FileMetadata, FolderMetadata, RelocationPath, WriteMode

# 把 scripts 目錄加進 path，import parser_lib
sys.path.insert(0, str(Path(__file__).resolve().parent))
import parser_lib  # 共用 parse_filename / enrich_meta / standardized_name

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# === Dropbox 路徑 ===
ROOT_PREFIX = "/MEMO烏骨雞"
STATE_DIR = "/閱讀器資料"
PENDING_DIR = f"{ROOT_PREFIX}/待處理"
INDEX_OUTPUT = f"{ROOT_PREFIX}/閱讀器/assets/report-index.js"
STOCK_NAMES_PATH = f"{STATE_DIR}/stock_names.json"

ACCEPTED_EXTS = {".pdf", ".md", ".docx", ".txt", ".zip"}
RESERVED_NAMES = {"desktop.ini", "0_使用說明.txt"}
CATEGORIES = ["個股", "海外個股", "產業", "總經", "策略與定期刊物", "外資報告", "Memo"]


def get_client() -> dropbox.Dropbox:
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    app_key = os.environ.get("DROPBOX_APP_KEY")
    app_secret = os.environ.get("DROPBOX_APP_SECRET")
    if not all([refresh_token, app_key, app_secret]):
        secrets_file = Path(__file__).resolve().parent.parent / ".secrets.json"
        if secrets_file.exists():
            s = json.loads(secrets_file.read_text(encoding="utf-8"))
            refresh_token = refresh_token or s.get("DROPBOX_REFRESH_TOKEN")
            app_key = app_key or s.get("DROPBOX_APP_KEY")
            app_secret = app_secret or s.get("DROPBOX_APP_SECRET")
    if not all([refresh_token, app_key, app_secret]):
        raise SystemExit("缺少 Dropbox 認證 (環境變數或 .secrets.json)")
    return dropbox.Dropbox(
        oauth2_refresh_token=refresh_token,
        app_key=app_key,
        app_secret=app_secret,
    )


def download_json(dbx, path: str) -> dict:
    try:
        _, resp = dbx.files_download(path)
        return json.loads(resp.content.decode("utf-8"))
    except ApiError as e:
        if "not_found" in str(e):
            return {}
        raise


def upload_text(dbx, path: str, content: str):
    dbx.files_upload(
        content.encode("utf-8"),
        path,
        mode=WriteMode.overwrite,
    )


def list_folder(dbx, path: str, recursive: bool = False) -> list:
    """列資料夾內容 (處理 paging)"""
    entries = []
    try:
        res = dbx.files_list_folder(path, recursive=recursive)
    except ApiError as e:
        if "not_found" in str(e):
            return []
        raise
    while True:
        entries.extend(res.entries)
        if not res.has_more:
            break
        res = dbx.files_list_folder_continue(res.cursor)
    return entries


def get_root_pdfs(dbx) -> list:
    """列 /MEMO烏骨雞/ 根目錄的散落檔案 (不含子目錄)"""
    files = []
    for entry in list_folder(dbx, ROOT_PREFIX, recursive=False):
        if not isinstance(entry, FileMetadata):
            continue
        name = entry.name
        if name in RESERVED_NAMES or name.startswith(("0_", "_")):
            continue
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ACCEPTED_EXTS:
            continue
        files.append(entry)
    return files


def get_all_managed_files(dbx) -> list:
    """列 /MEMO烏骨雞/{year}/{cat}/ 下所有檔案 (給 build_index 用)"""
    out = []
    for entry in list_folder(dbx, ROOT_PREFIX, recursive=True):
        if not isinstance(entry, FileMetadata):
            continue
        path = entry.path_display
        parts = path.split("/")
        # /MEMO烏骨雞/2026/個股/xxx.pdf → [MEMO烏骨雞, 2026, 個股, xxx.pdf]
        if len(parts) < 5:
            continue
        year, cat = parts[2], parts[3]
        if not re.match(r"^20\d{2}$", year):
            continue
        if cat not in CATEGORIES:
            continue
        ext = "." + entry.name.rsplit(".", 1)[-1].lower() if "." in entry.name else ""
        if ext not in ACCEPTED_EXTS:
            continue
        out.append((entry, year, cat))
    return out


def file_exists(dbx, path: str) -> bool:
    try:
        dbx.files_get_metadata(path)
        return True
    except ApiError:
        return False


def unique_dropbox_path(dbx, target_path: str) -> str:
    """target 已存在就加 _(2) _(3) ..."""
    if not file_exists(dbx, target_path):
        return target_path
    parent, _, name = target_path.rpartition("/")
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        ext = "." + ext
    else:
        stem, ext = name, ""
    n = 2
    while True:
        candidate = f"{parent}/{stem}_({n}){ext}"
        if not file_exists(dbx, candidate):
            return candidate
        n += 1


def organize(dbx) -> dict:
    """整理根目錄 PDF。回傳統計"""
    stats = {"moved": 0, "pending": 0, "learned": 0}
    pdfs = get_root_pdfs(dbx)
    print(f"  根目錄散落: {len(pdfs)} 個檔案")
    for entry in pdfs:
        name = entry.name
        src_path = entry.path_display

        # ZIP 一律進待處理
        if name.lower().endswith(".zip"):
            dst = unique_dropbox_path(dbx, f"{PENDING_DIR}/{name}")
            dbx.files_move_v2(src_path, dst)
            print(f"  [待處理 zip] {name}")
            stats["pending"] += 1
            continue

        meta = parser_lib.parse_filename(name)
        meta = parser_lib.enrich_meta(meta, name)
        if not meta or not meta.get("date") or not meta.get("broker"):
            dst = unique_dropbox_path(dbx, f"{PENDING_DIR}/{name}")
            dbx.files_move_v2(src_path, dst)
            print(f"  [待處理] {name}")
            stats["pending"] += 1
            continue
        if meta["category"] == "個股" and not meta.get("stock_code"):
            dst = unique_dropbox_path(dbx, f"{PENDING_DIR}/{name}")
            dbx.files_move_v2(src_path, dst)
            print(f"  [待處理 缺股號] {name}")
            stats["pending"] += 1
            continue

        # 學股號名稱
        if meta.get("stock_code") and meta.get("stock_name"):
            code = meta["stock_code"]
            sname = meta["stock_name"].strip()
            if sname and parser_lib.STOCK_NAMES.get(code) != sname:
                parser_lib.STOCK_NAMES[code] = sname
                stats["learned"] += 1

        # 外資 broker 覆寫 category
        if parser_lib.is_foreign_broker(meta["broker"]) and meta["category"] != "Memo":
            meta["category"] = "外資報告"

        year = meta["date"][:4]
        ext = "." + name.rsplit(".", 1)[-1].lower()
        new_name = parser_lib.standardized_name(meta, ext)
        dst = unique_dropbox_path(dbx, f"{ROOT_PREFIX}/{year}/{meta['category']}/{new_name}")
        try:
            dbx.files_move_v2(src_path, dst, autorename=False)
            print(f"  [整理] {name} -> {year}/{meta['category']}/{Path(dst).name}")
            stats["moved"] += 1
        except ApiError as e:
            print(f"  [失敗] {name}: {e}")
    return stats


def build_entry(entry: FileMetadata, category: str, year: str) -> dict:
    """跟本機 update.py build_entry 100% 一致格式"""
    from urllib.parse import quote
    name = entry.name
    stem = name.rsplit(".", 1)[0] if "." in name else name
    meta = parser_lib.parse_filename(name) or {}
    meta = parser_lib.enrich_meta(meta, name)
    date = meta.get("date") or f"{year}-01-01"
    broker = meta.get("broker", "")
    stock_code = meta.get("stock_code", "")
    stock_name = meta.get("stock_name", "") or parser_lib.STOCK_NAMES.get(stock_code, "")
    topic = meta.get("topic", "")
    market = meta.get("market", "")

    if category == "海外個股":
        ticker = meta.get("ticker") or stock_code
        rid = f"{ticker}_{market}_{date.replace('-', '')}_{broker}" if (ticker and date) else stem
        display_subject = f"{ticker} {stock_name}".strip() if ticker else (stock_name or stem)
    elif category == "個股":
        rid = f"{stock_code}_{date.replace('-', '')}_{broker}" if (stock_code and date) else stem
        display_subject = f"{stock_code} {stock_name}".strip() if stock_code else stem
    else:
        rid = stem
        display_subject = topic or stem

    rel_pdf = f"{year}/{category}/{name}"
    href = "../" + "/".join(quote(part) for part in rel_pdf.split("/"))
    search_bits = [stem, date, category, stock_code, stock_name, topic, broker, name]
    search_text = " ".join(s for s in search_bits if s).lower()

    return {
        "id": rid,
        "date": date,
        "category": category,
        "report_type": category,
        "title": "報告",
        "display_name": stock_name or topic or stem,
        "display_subject": display_subject,
        "stock_code": stock_code,
        "stock_name": stock_name,
        "industry": "",
        "topic": topic,
        "broker": broker,
        "rating": "",
        "target_price_raw": "",
        "target_price_currency": "",
        "target_price_sort_value": 0,
        "target_price_status": "",
        "has_target_price": False,
        "source_file": name,
        "search_text": search_text,
        "pdf_href": href,
        "pdf_status": "relative",
    }


def build_index(dbx) -> int:
    """掃所有歸位檔案 → 寫 report-index.js (跟本機格式 100% 一致)"""
    reports = []
    for entry, year, cat in get_all_managed_files(dbx):
        reports.append(build_entry(entry, cat, year))
    reports.sort(key=lambda r: (r["date"], r["id"]), reverse=True)

    now_iso = datetime.now().astimezone().isoformat()
    payload = {
        "schema_version": "hermes_static_report_reader.v1",
        "generated_at_utc": now_iso,
        "title": "MEMO烏骨雞 報告庫",
        "stats": {"reports": len(reports)},
        "reports": reports,
    }
    js = "window.HERMES_STATIC_REPORT_READER_INDEX = " + json.dumps(
        payload, ensure_ascii=False,
    ) + ";\n"
    upload_text(dbx, INDEX_OUTPUT, js)
    return len(reports)


HEARTBEAT_PATH = f"{STATE_DIR}/last_local_run.txt"
HEARTBEAT_THRESHOLD_MIN = 10  # 本機若 10 分鐘內跑過，雲端跳過


def check_heartbeat(dbx) -> bool:
    """看本機是否剛跑過。回 True 表示應該跳過"""
    try:
        _, resp = dbx.files_download(HEARTBEAT_PATH)
        ts_str = resp.content.decode("utf-8").strip()
        ts = datetime.fromisoformat(ts_str)
        # 對齊 timezone
        now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.utcnow()
        delta_min = (now - ts).total_seconds() / 60
        print(f"  本機上次跑: {ts_str} ({delta_min:.1f} 分鐘前)")
        return delta_min < HEARTBEAT_THRESHOLD_MIN
    except ApiError as e:
        if "not_found" in str(e):
            print("  本機沒有 heartbeat (從沒跑過)，照常跑")
            return False
        raise


def main():
    print("=" * 50)
    print(f"雲端自動整理 - {datetime.utcnow().isoformat()}Z")
    print("=" * 50)

    dbx = get_client()
    try:
        account = dbx.users_get_current_account()
        print(f"已連線: {account.name.display_name}")
    except Exception as e:
        print(f"認證失敗: {e}")
        raise SystemExit(1)

    # Heartbeat check: 本機剛跑過就跳過 (節省 GHA 用量)
    if os.environ.get("FORCE_RUN", "").lower() == "true":
        print("\n[0/3] FORCE_RUN=true，跳過 heartbeat 檢查")
    else:
        print("\n[0/3] 檢查本機 heartbeat...")
        if check_heartbeat(dbx):
            print(f"  本機 {HEARTBEAT_THRESHOLD_MIN} 分鐘內跑過，雲端跳過")
            return

    # 載 stock_names
    print("\n[1/3] 載入 stock_names...")
    stock_names = download_json(dbx, STOCK_NAMES_PATH)
    parser_lib.STOCK_NAMES = stock_names  # inject
    print(f"  {len(stock_names)} 個股號")

    # 整理
    print("\n[1/3] 整理散落 PDF...")
    stats = organize(dbx)
    print(f"  moved={stats['moved']}, pending={stats['pending']}, learned={stats['learned']}")

    if stats["learned"] > 0:
        print("  上傳更新後的 stock_names.json...")
        upload_text(dbx, STOCK_NAMES_PATH,
                    json.dumps(parser_lib.STOCK_NAMES, ensure_ascii=False, indent=2))

    # 刪重複 _(N) (跟本機 update.py 的 dedupe_duplicates 等效)
    print("\n[2/3] 刪重複 _(N)...")
    removed = dedupe_cloud(dbx)
    print(f"  刪 {removed} 份重複")

    # 重建 index
    print("\n[3/3] 重建索引...")
    n = build_index(dbx)
    print(f"  寫入 {INDEX_OUTPUT} ({n} 筆)")

    print("\n完成")


def dedupe_cloud(dbx) -> int:
    """掃所有歸位檔，找 _(N) 重複版，size 差 <= 100 bytes 就刪"""
    removed = 0
    by_dir = {}
    for entry, year, cat in get_all_managed_files(dbx):
        by_dir.setdefault((year, cat), []).append(entry)
    for (year, cat), entries in by_dir.items():
        # 建 basename → entry mapping
        by_basename = {}
        for e in entries:
            stem = e.name.rsplit(".", 1)[0] if "." in e.name else e.name
            ext = "." + e.name.rsplit(".", 1)[1] if "." in e.name else ""
            m = re.match(r"^(.+)_\((\d+)\)$", stem)
            if m:
                base = m.group(1) + ext
                original = f"{ROOT_PREFIX}/{year}/{cat}/{base}"
                # 看原版有沒有
                try:
                    orig_meta = dbx.files_get_metadata(original)
                    if hasattr(orig_meta, "size") and abs(orig_meta.size - e.size) <= 100:
                        dbx.files_delete_v2(e.path_display)
                        print(f"    [刪] {e.path_display} (= {original})")
                        removed += 1
                except ApiError:
                    pass
    return removed


if __name__ == "__main__":
    main()
