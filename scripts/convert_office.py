"""
PPT / Word / Excel → PDF 自動轉檔。

優先嘗試 LibreOffice (`soffice` CLI)。沒裝就 skip，不影響其他流程。

本機 (Windows):  下載 https://www.libreoffice.org/download/download/ 裝完即可
雲端 (GHA Ubuntu): 預裝，直接 work
"""
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OFFICE_EXTS = {".pptx", ".ppt", ".docx", ".doc", ".xlsx", ".xls"}


def find_soffice() -> str:
    """找 LibreOffice CLI 路徑"""
    for candidate in ["soffice", "libreoffice"]:
        if shutil.which(candidate):
            return candidate
    # Windows 常見安裝位置
    for path in [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]:
        if Path(path).exists():
            return path
    return ""


def convert_to_pdf(src: Path) -> Path:
    """轉 src 成 PDF。回傳產生的 PDF 路徑 (或 None 失敗)"""
    if src.suffix.lower() not in OFFICE_EXTS:
        return None
    soffice = find_soffice()
    if not soffice:
        return None
    out_dir = src.parent
    try:
        proc = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf",
             "--outdir", str(out_dir), str(src)],
            capture_output=True, timeout=120,
        )
        if proc.returncode != 0:
            return None
        pdf = src.with_suffix(".pdf")
        if pdf.exists():
            return pdf
    except Exception:
        pass
    return None


def is_available() -> bool:
    return bool(find_soffice())


if __name__ == "__main__":
    if not is_available():
        print("LibreOffice 沒裝。下載: https://www.libreoffice.org/download/download/")
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python convert_office.py <file.pptx>")
        sys.exit(1)
    src = Path(sys.argv[1])
    pdf = convert_to_pdf(src)
    if pdf:
        print(f"OK: {src.name} → {pdf.name}")
    else:
        print(f"轉檔失敗: {src.name}")
        sys.exit(1)
