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
    # 「目標價從980 元上修至1,500 元」「目標價自XX 上調至 YY 元」(國票等本土券商常用)
    r"目標?[价價][^。\n]{0,40}?(?:上修至|下修至|上調至|下調至|調整至|至)\s*(?:NT\$|US\$|HK\$|RMB|\$)?\s*([\d,]+\.?\d*)\s*元",
    # 「目標價為 2,250 元」「目標價 X 元」直接接
    r"目標?[价價](?:為)?\s*(?:NT\$|US\$|HK\$|RMB|\$)?\s*([\d,]+\.?\d*)\s*元(?:\s|$|[，。,.\(（])",
]

TARGET_PATTERNS = [
    # 「泰宗 (4169 TT, NT$217.5, 增加持股)」凱基股票標頭格式 — NT$ 後第一個數字
    r"\(\d{4}\s*(?:TT|TW|TWO)\s*,\s*(NT\$|US\$|HK\$|\$)\s*([\d,]+\.?\d*)",
    # 「Target price\n NT$80.00」「Target Price: NT$5,950」
    r"(?:Target\s*[Pp]rice|Price\s*[Tt]arget)(?:\s*\([^\)]*\))?\s*[:：]?\s*\n?\s*(NT\$|US\$|HK\$|RMB|JPY|EUR|GBP|SGD|\$)\s*([\d,]+\.?\d*)",
    # 「目標價: 80 元」「目標價(元): 80」「目標價 (NT$) 60.00」(台/中) 單值
    r"目標?[价價]\s*[（(]?\s*[元美\w$%]*\s*[)）]?\s*[:：\s]+\s*(NT\$|US\$|HK\$|RMB|\$)?\s*([\d,]+\.?\d*)",
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


# 外資 broker keywords in PDF body (LINE bot 上傳的常沒 broker name in filename)
BROKER_KEYWORDS = {
    "Nomura": ["Nomura", "nomura"],
    "JPM": ["J.P. Morgan", "JPMorgan", "JP Morgan"],
    "MS": ["Morgan Stanley"],
    "GS": ["Goldman Sachs"],
    "UBS": ["UBS Securities", "UBS Investment", "UBS AG"],
    "Citi": ["Citi Research", "Citigroup"],
    "BofA": ["BofA Securities", "Merrill Lynch", "Bank of America"],
    "Daiwa": ["Daiwa Securities"],
    "HSBC": ["HSBC Securities", "HSBC Global", "HSBC Bank"],
    "Jefferies": ["Jefferies"],
    "MQ": ["Macquarie"],
    "Bernstein": ["Bernstein Research", "Sanford C. Bernstein"],
    "CLSA": ["CLSA Asia", "CLSA Limited"],
    "DB": ["Deutsche Bank"],
    "Mizuho": ["Mizuho Securities"],
    "Nikko": ["Nikko Securities"],
    "Barclays": ["Barclays Capital"],
}


def detect_broker_in_text(text: str) -> str:
    """從 PDF 內文掃外資 broker keyword，取出現 ≥ 3 次的最頻繁者"""
    if not text:
        return ""
    counts = {}
    for short, kws in BROKER_KEYWORDS.items():
        c = 0
        for kw in kws:
            c += text.count(kw)
        if c > 0:
            counts[short] = c
    if not counts:
        return ""
    best = max(counts.items(), key=lambda x: x[1])
    return best[0] if best[1] >= 3 else ""


def extract_pdf_title(doc) -> str:
    """從 PDF metadata 抽 title，沒則用第一頁首字串"""
    md = doc.metadata or {}
    title = (md.get("title") or "").strip()
    # 排除無意義的 PDF metadata title
    bad_titles = {"untitled", "document", "report", "microsoft word", ""}
    if title and title.lower() not in bad_titles and len(title) > 3:
        # 清掉常見前綴
        title = re.sub(r"^(M\s+)?(Update|Flash|Note|Report)\s+", "", title)
        return title.strip()
    return ""


_TITLE_PATTERNS = [
    # "6894-衛司特-20260623-宏遠投顧" / "6894_衛司特_20260623"
    re.compile(r"(?<![\d])(\d{4,5})[\-_]([一-鿿][一-鿿\-]{1,6})[\-_]\d{6,8}"),
    # "6894-衛司特" (沒日期段)
    re.compile(r"(?<![\d])(\d{4,5})[\-_]([一-鿿][一-鿿\-]{1,6})(?![一-鿿\d])"),
]


def extract_pdf_stock_id(text_or_title: str) -> dict:
    """從 PDF metadata title 抽『股號-公司名』強信號 pattern。
    回傳 {stock_code, stock_name} 或 {}.
    只看 metadata title (Word 轉 PDF 的格式) 因為 PDF 內文太多年份雜訊會誤判。"""
    if not text_or_title:
        return {}
    for pat in _TITLE_PATTERNS:
        m = pat.search(text_or_title)
        if m:
            return {"stock_code": m.group(1), "stock_name": m.group(2)}
    return {}


# 「泰宗 (4169 TT)」「智易(3596)」「聚賢研發-創(7631 TT)」— 中文名(可含-/KY/創) 接 (NNNN
_BODY_NAME_PAT = re.compile(r"([一-鿿][一-鿿A-Za-z\-]{1,9})\s*[\(（]\s*(\d{4})\s*(?:TT|TW|TWO)?\s*[\)）]")
# 反向「1519.TT 華城」「2330 TT 台積電」— NNNN(.TT) 接中文名
_BODY_NAME_PAT_REV = re.compile(r"(\d{4})\s*(?:\.TT|\.TW|\s+TT|\s+TW)\s+([一-鿿][一-鿿A-Za-z\-]{1,9})")


def _body_name_pairs(text: str):
    """回傳所有 (code, name) — 正向「名(NNNN)」+ 反向「NNNN.TT 名」"""
    pairs = {}
    for name, code in _BODY_NAME_PAT.findall(text):
        if 2 <= len(name) <= 10:
            pairs.setdefault(code, name)
    for code, name in _BODY_NAME_PAT_REV.findall(text):
        if 2 <= len(name) <= 10:
            pairs.setdefault(code, name)
    return pairs


def extract_stock_name_from_body(text: str, stock_code: str) -> str:
    if not text or not stock_code:
        return ""
    return _body_name_pairs(text).get(stock_code, "")


def extract_pdf_report_date(text: str) -> str:
    """從 PDF 抽『報告日期：YYYY/MM/DD』等格式，回傳 YYYY-MM-DD 或空字串"""
    head = text[:3000]
    patterns = [
        r"報告日期[\s：:]+(\d{4})[\/\-年\.](\d{1,2})[\/\-月\.](\d{1,2})",
        r"出版日期[\s：:]+(\d{4})[\/\-年\.](\d{1,2})[\/\-月\.](\d{1,2})",
        r"發布日期[\s：:]+(\d{4})[\/\-年\.](\d{1,2})[\/\-月\.](\d{1,2})",
        r"(?:^|\n|\s)日期[\s：:]+(\d{4})[\/\-年\.](\d{1,2})[\/\-月\.](\d{1,2})",
    ]
    for p in patterns:
        m = re.search(p, head)
        if m:
            y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
            return f"{y}-{mo}-{d}"
    return ""


def extract_metadata(pdf_path, max_pages: int = 5) -> dict:
    """一次開 PDF 抽 analysts + target_price + pdf_title + body_excerpt
    + stock_id (從內文抽 stock_code/stock_name) + report_date (從內文抽報告日期)"""
    empty = {"analysts": [], "target_price": {}, "pdf_title": "", "body_excerpt": "",
             "stock_id": {}, "report_date": ""}
    if not fitz:
        return empty
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return empty
    text_pieces = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        try:
            text_pieces.append(page.get_text())
        except Exception:
            pass
    pdf_title = extract_pdf_title(doc)
    doc.close()
    text = "\n".join(text_pieces)
    # body_excerpt: 用於 user 搜尋。同時保留簡繁兩種 (搜「儲能」「储能」都能找到)
    body = re.sub(r"\s+", " ", text).strip()[:4000]
    try:
        import zhconv
        body_tw = zhconv.convert(body, "zh-hant")
        body_cn = zhconv.convert(body, "zh-hans")
        body_excerpt = (body_tw + " " + body_cn).lower()[:8000]
    except ImportError:
        body_excerpt = body.lower()
    # stock_id 從 title 抽; title 抓不到時用內文「中文名(NNNN TT)」補
    stock_id = extract_pdf_stock_id(pdf_title)
    return {
        "analysts": extract_analysts_from_text(text),
        "target_price": extract_target_price(text),
        "pdf_title": pdf_title,
        "body_excerpt": body_excerpt,
        "detected_broker": detect_broker_in_text(text),
        "stock_id": stock_id,
        "report_date": extract_pdf_report_date(text),
        # 純股名 (供 build_entry 在主檔沒這股號時補名), 正向+反向 pattern
        "body_stock_names": _body_name_pairs(text),
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
