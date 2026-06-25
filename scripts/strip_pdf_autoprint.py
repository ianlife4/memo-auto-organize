"""
PDF 預處理：移除會在開啟時自動觸發列印的 JavaScript / OpenAction。

對研報的影響:
  - 移除 /OpenAction → 不會 auto-print、不會跳到指定頁
  - 移除 /AA (additional actions) → 不會在 close/save 觸發 JS
  - 移除 /Names/JavaScript → 不會註冊全域 JS
  - 不影響: 文字、圖表、超連結、書籤、頁面結構

跑 update.py 時對新進的 PDF 自動跑一次。也可單獨跑對所有檔案批次處理。
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from pdfrw import PdfReader, PdfWriter
except ImportError:
    print("缺 pdfrw，請: pip install pdfrw --user")
    sys.exit(1)


def strip_pdf_actions(path: Path) -> bool:
    """回 True 表示有修改 + 已儲存"""
    try:
        pdf = PdfReader(str(path))
    except Exception as e:
        return False  # 損毀或加密 PDF 跳過

    if not pdf.Root:
        return False

    changed = False
    root = pdf.Root
    # 1. OpenAction (PDF 開啟時觸發的動作，包含 auto-print)
    if root.OpenAction is not None:
        root.OpenAction = None
        changed = True
    # 2. AA (Additional Actions: open/close/print/save 時觸發)
    if root.AA is not None:
        root.AA = None
        changed = True
    # 3. Names/JavaScript (註冊的 JS 函數)
    if root.Names is not None:
        if root.Names.JavaScript is not None:
            root.Names.JavaScript = None
            changed = True
        if root.Names.JS is not None:
            root.Names.JS = None
            changed = True
    # 4. AcroForm CO (calculate order，會跑 JS)
    if root.AcroForm is not None and root.AcroForm.CO is not None:
        root.AcroForm.CO = None
        changed = True

    if changed:
        try:
            PdfWriter(str(path), trailer=pdf).write()
            return True
        except Exception as e:
            print(f"  寫入失敗 {path.name}: {e}")
            return False
    return False


def process_dir(root: Path, recursive: bool = True) -> dict:
    stats = {"scanned": 0, "stripped": 0, "skipped": 0}
    pdfs = root.rglob("*.pdf") if recursive else root.glob("*.pdf")
    for p in pdfs:
        if not p.is_file():
            continue
        stats["scanned"] += 1
        if strip_pdf_actions(p):
            stats["stripped"] += 1
            print(f"  [strip] {p.relative_to(root)}")
        else:
            stats["skipped"] += 1
    return stats


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\J.Chun\Dropbox\MEMO烏骨雞"
    root = Path(target)
    if not root.exists():
        print(f"目錄不存在: {root}")
        sys.exit(1)
    print(f"掃描 {root}")
    stats = process_dir(root)
    print(f"\n掃 {stats['scanned']} 份，移除 auto-print {stats['stripped']} 份，原樣 {stats['skipped']} 份")


if __name__ == "__main__":
    main()
