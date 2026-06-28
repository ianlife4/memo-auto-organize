"""
從 PDF 內文抽研究員 + 目標價 (一次開檔抽兩個欄位)。
取代 extract_analysts.py 的 entry point - extract_from_pdf 改成 extract_metadata。
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# 從 extract_analysts.py 抓 analyst 邏輯
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_analysts import extract_from_text as extract_analysts_from_text


# Currency code → 統一表記
CURRENCY_MAP = {
    "NT$": "NTD", "NTD": "NTD",
    "US$": "USD", "USD": "USD", "$": "USD",
    "HK$": "HKD", "HKD": "HKD",
    "RMB": "CNY", "CNY": "CNY", "￥": "CNY",
    "JPY": "JPY", "¥": "JPY",
    "EUR": "EUR", "€": "EUR",
    "GBP": "GBP", "£": "GBP",
    "SGD": "SGD",
}

TARGET_PATTERNS_2COL = [
    # 統一/凱基等本土券商表格: 「目標價\n上次值\n本次值」→ 取本次
    # 用 "本次" header 提示
    (
        r"上次[\s\S]{0,30}本次[\s\S]{0,200}?目標[价價]\s*[\n\r\s]+([\d,]+\.?\d*)\s*[\n\r\s]+([\d,]+\.?\d*)",
        2,  # 取 group 2 (本次)
    ),
]

TARGET_PATTERNS_TIMEFRAME = [
    # 群益等: 「目標價\n3 個月\n2,250.00\n12 個月\n2,250.00」→ 取數字
    r"目標?[价價]\s*[\n\r\s]+\d+\s*(?:個月|月|年)\s*[\n\r\s]+([\d,]+\.?\d*)",
    # 內文描述句 (有「元」結尾為信號): 「目標價70 元」「目標價為2,250 元」「目標價至NT$80元」
    r"目標?[价價](?:為|至|調整[至為])?\s*(?:NT\$|US\$|HK\$|RMB|\$)?\s*([\d,]+\.?\d*)\s*元(?:\s|$|[，。,.\(（])",
]

TARGET_PATTERNS = [
    # 「Target price\n NT$80.00」「Target Price: NT$5,950」
    r"(?:Target\s*[Pp]rice|Price\s*[Tt]arget)(?:\s*\([^\)]*\))?\s*[:：]?\s*\n?\s*(NT\$|US\$|HK\$|RMB|JPY|EUR|GBP|SGD|\$)\s*([\d,]+\.?\d*)",
    # 「目標價: 80 元」「目標價(元): 80」 (台/中) 單值
    r"目標?[价價]\s*[（(]?\s*[元美\w]*\s*[)）]?\s*[:：\s]+\s*(NT\$|US\$|HK\$|RMB|\$)?\s*([\d,]+\.?\d*)",
    # 「PT NT$140」「PT: $XXX」 (外資簡寫)
    r"\bPT\s*[:：]?\s*(NT\$|US\$|HK\$|RMB|\$)\s*([\d,]+\.?\d*)",
]


def extract_target_price(text: str) -> dict:
    """從 text 抽出目標價。優先處理「上次/本次」雙欄取本次"""
    # 1. 先試雙欄格式 (上次/本次)
    for pat, group_idx in TARGET_PATTERNS_2COL:
        m = re.search(pat, text)
        if not m:
            continue
        value_str = m.group(group_idx).replace(",", "")
        try:
            value = float(value_str)
        except ValueError:
            continue
        if value <= 0 or value > 1e8:
            continue
        return {"raw": value_str, "currency": "NTD", "value": value}
    # 2. 時程/描述句格式
    for pat in TARGET_PATTERNS_TIMEFRAME:
        m = re.search(pat, text)
        if not m:
            continue
        value_str = m.group(1).replace(",", "")
        try:
            value = float(value_str)
        except ValueError:
            continue
        if value <= 0 or value > 1e8:
            continue
        return {"raw": value_str, "currency": "NTD", "value": value}
    # 3. 單值 patterns
    for pat in TARGET_PATTERNS:
        m = re.search(pat, text)
        if not m:
            continue
        currency_raw = (m.group(1) or "NTD").strip()
        value_str = m.group(2).replace(",", "")
        try:
            value = float(value_str)
        except ValueError:
            continue
        if value <= 0 or value > 1e8:
            continue
        currency = CURRENCY_MAP.get(currency_raw, currency_raw)
        return {
            "raw": f"{currency_raw}{value_str}",
            "currency": currency,
            "value": value,
        }
    return {}


def extract_metadata(pdf_path, max_pages: int = 3) -> dict:
    """一次開 PDF 抽 analysts + target_price"""
    if not fitz:
        return {"analysts": [], "target_price": {}}
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return {"analysts": [], "target_price": {}}
    text_pieces = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        try:
            text_pieces.append(page.get_text())
        except Exception:
            pass
    doc.close()
    text = "\n".join(text_pieces)
    return {
        "analysts": extract_analysts_from_text(text),
        "target_price": extract_target_price(text),
    }


if __name__ == "__main__":
    if not fitz:
        print("缺 PyMuPDF: pip install pymupdf --user")
        sys.exit(1)
    if len(sys.argv) < 2:
        # 預設測試
        for s in [
            r"C:\Users\J.Chun\Dropbox\MEMO烏骨雞\2026\外資報告\1216_20260625_Citi.pdf",
            r"C:\Users\J.Chun\Dropbox\MEMO烏骨雞\2026\外資報告\1303_20260621_JPM_long.pdf",
            r"C:\Users\J.Chun\Dropbox\MEMO烏骨雞\2026\個股\2474_20260624_合庫.pdf",
        ]:
            p = Path(s)
            if p.exists():
                print(f"\n{p.name}:")
                print(f"  {extract_metadata(p)}")
    else:
        print(extract_metadata(Path(sys.argv[1])))
