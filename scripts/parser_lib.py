"""
MEMO烏骨雞 報告庫 — 整理 + 索引產生器

雙擊「更新.bat」會跑這支：
  1. 掃根目錄散落的 PDF
  2. 從檔名推斷 類別/股號/日期/券商 → 改名 → 移到 年份\類別\
  3. 認不出來的丟 待處理\
  4. 掃完所有已分類 PDF，產生 閱讀器\assets\report-index.js
"""
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from zhconv import convert as _zh_convert
    def to_traditional(text: str) -> str:
        return _zh_convert(text, "zh-tw") if text else text
except ImportError:
    def to_traditional(text: str) -> str:
        return text  # 沒裝 zhconv 就原樣返回

# 強制 UTF-8 輸出，避免 Windows cp950 對簡體中文崩潰
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPTS_DIR = Path(__file__).resolve().parent
ROOT = Path(r"C:\Users\J.Chun\Dropbox\MEMO烏骨雞")
READER_INDEX = ROOT / "閱讀器" / "assets" / "report-index.js"
PENDING_DIR = ROOT / "待處理"
STOCK_NAMES_FILE = SCRIPTS_DIR / "stock_names.json"
CATEGORIES = ["個股", "海外個股", "產業", "總經", "策略與定期刊物", "外資報告", "Memo"]

# 國際大行 — broker 落在這裡就覆寫 category 成「外資報告」
FOREIGN_BROKERS = {"JPM", "MS", "GS", "Bernstein", "Daiwa", "UBS", "MQ",
                   "中金", "廣發", "Nomura", "Jefferies", "Citi",
                   "Barclays", "Mizuho", "SocGen", "DB", "BofA", "ML",
                   "CLSA", "HSBC", "CS"}


def is_foreign_broker(brk: str) -> bool:
    if not brk:
        return False
    return brk in FOREIGN_BROKERS


# 股號別名 (中文短名/英文名/英文簡稱) → 補 STOCK_NAMES 抓不到的情況
STOCK_ALIASES = {
    "1101": ["台泥"],
    "1216": ["統一企業", "PCSC"],
    "1303": ["南亞", "Nan Ya"],
    "1326": ["台化"],
    "1402": ["遠東新"],
    "1605": ["華新"],
    "2002": ["中鋼"],
    "2059": ["川湖"],
    "2207": ["和泰車", "Hotai"],
    "2303": ["聯電", "UMC"],
    "2317": ["鴻海", "Hon Hai", "Foxconn"],
    "2327": ["國巨", "Yageo"],
    "2330": ["台積電", "TSMC", "tsmc"],
    "2356": ["英業達", "Inventec"],
    "2357": ["華碩", "Asus", "ASUS"],
    "2382": ["廣達", "Quanta"],
    "2412": ["中華電"],
    "2449": ["京元電", "KYEC", "King Yuan"],
    "2454": ["聯發科", "MediaTek", "MTK"],
    "2474": ["可成", "Catcher"],
    "2603": ["長榮海運", "Evergreen"],
    "2609": ["陽明", "Yang Ming"],
    "2615": ["萬海", "Wan Hai"],
    "2618": ["長榮航"],
    "2880": ["華南金"],
    "2882": ["國泰金"],
    "2883": ["凱基金"],
    "2891": ["中信金"],
    "3008": ["大立光", "Largan"],
    "3017": ["奇鋐", "Auras"],
    "3034": ["聯詠", "Novatek"],
    "3037": ["欣興", "Unimicron"],
    "3105": ["穩懋"],
    "3231": ["緯創", "Wistron"],
    "3406": ["玉晶光", "GSEO"],
    "3481": ["群創", "Innolux"],
    "3661": ["世芯-KY", "Alchip"],
    "3665": ["貿聯-KY", "BizLink"],
    "4938": ["和碩", "Pegatron"],
    "4919": ["新唐", "Nuvoton"],
    "5347": ["世界先進", "世界", "Vanguard", "VIS"],
    "6146": ["DISCO"],
    "6669": ["緯穎", "Wiwynn"],
    "6770": ["力積電", "PSMC"],
    "6789": ["采鈺"],
    "6831": ["邁科", "Microloops"],
    "8046": ["南電", "NYPCB"],
    "8069": ["元太", "E Ink"],
    "8112": ["至上"],
    "8341": ["日友"],
}


def lookup_stock_in_text(text: str):
    """從文字反查股號。先試 STOCK_NAMES，再試 alias，長名優先避免短名誤配。
    英文 alias 做 case-insensitive 比對。"""
    if not text:
        return None, None
    text_lower = text.lower()
    candidates = []
    for code, name in STOCK_NAMES.items():
        if name and len(name) >= 2:
            candidates.append((len(name), code, name, name))
    for code, aliases in STOCK_ALIASES.items():
        for alias in aliases:
            if alias and len(alias) >= 2:
                candidates.append((len(alias), code, alias, STOCK_NAMES.get(code) or alias))
    candidates.sort(reverse=True)  # 長的優先
    for _, code, key, display_name in candidates:
        if key in text or key.lower() in text_lower:
            return code, display_name
    return None, None


def enrich_meta(meta: dict, filename: str) -> dict:
    """補上 parser 沒抓到的 stock_code + 統一中文轉繁體"""
    if not meta:
        return meta
    if not meta.get("stock_code") and meta.get("category") in ("個股", "外資報告", "產業"):
        code, name = lookup_stock_in_text(filename + " " + (meta.get("topic") or ""))
        if code:
            meta["stock_code"] = code
            if not meta.get("stock_name"):
                meta["stock_name"] = name
    # 統一轉繁體 (避免顯示簡體混雜)
    for k in ("topic", "stock_name", "broker"):
        if meta.get(k):
            meta[k] = to_traditional(meta[k])
    return meta


def load_stock_names() -> dict:
    if STOCK_NAMES_FILE.exists():
        try:
            return json.loads(STOCK_NAMES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_stock_names(mapping: dict) -> None:
    STOCK_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOCK_NAMES_FILE.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


STOCK_NAMES = load_stock_names()

# 券商關鍵字 (順序敏感：長的、特殊的放前面)
BROKERS = [
    # 本土券商
    ("第一金投顧", "第一金"), ("第一金", "第一金"),
    ("國泰證期", "國泰"), ("國泰海通", "國泰海通"), ("國泰", "國泰"),
    ("中金公司", "中金"), ("中金", "中金"),
    ("台新新光金控", "元富"), ("台新", "台新"),
    ("元富投顧", "元富"), ("元富", "元富"),
    ("統一投顧", "統一"), ("統一", "統一"),
    ("富邦期貨", "富邦"), ("富邦", "富邦"),
    ("兆豐", "兆豐"), ("元大", "元大"), ("永豐", "永豐"),
    ("凱基", "凱基"), ("中信", "中信"), ("宏遠", "宏遠"),
    ("玉山", "玉山"), ("華南", "華南"), ("福邦", "福邦"),
    ("群益", "群益"), ("國票", "國票"),
    ("大華", "大華"), ("日盛", "日盛"), ("台証", "台証"),
    ("復華", "復華"), ("合庫", "合庫"), ("康和", "康和"),
    ("富果", "富果"), ("美好金融", "美好金融"),
    ("開源", "開源"), ("國信", "國信"),
    # 廣發系列
    ("GFHK", "廣發"), ("廣發", "廣發"), ("GF", "廣發"),
    # 外資
    ("JPM", "JPM"), ("Daiwa", "Daiwa"), ("daiwa", "Daiwa"),
    ("Bernstein", "Bernstein"), ("BERNSTEIN", "Bernstein"),
    ("CICC", "中金"), ("UBS", "UBS"),
    ("MS", "MS"), ("ms", "MS"),
    ("GS", "GS"), ("gs", "GS"),
    ("MQ", "MQ"), ("DIGITIMES", "DIGITIMES"),
    # 中國券商
    ("东兴证券", "东兴证券"), ("中邮证券", "中邮证券"),
    ("天风证券", "天风证券"), ("国信证券", "国信证券"),
    ("国盛证券", "国盛证券"), ("招商证券", "招商证券"),
    ("方正证券", "方正证券"), ("华西证券", "华西证券"),
    ("华泰证券", "华泰证券"), ("海通证券", "海通证券"),
    ("中信建投", "中信建投"), ("招银国际", "招银国际"),
    ("锦研视角", "锦研视角"), ("慧博智能投研", "慧博"),
    ("慧博", "慧博"),
    # 研究機構
    ("集邦", "集邦"), ("TrendForce", "集邦"),
    # 外資中文翻譯名 (Pattern A 中國研報網站翻譯後的命名)
    ("摩根士丹利", "MS"), ("摩根大通", "JPM"),
    ("瑞银", "UBS"), ("瑞士信贷", "CS"),
    ("野村", "Nomura"), ("高盛", "GS"),
    ("杰富瑞", "Jefferies"), ("花旗", "Citi"),
    ("巴克莱", "Barclays"), ("瑞穗", "Mizuho"),
    ("法兴", "SocGen"), ("德意志", "DB"),
    ("美银", "BofA"), ("美林", "ML"),
    ("中信里昂", "CLSA"), ("汇丰", "HSBC"),
    # Pattern B 中國研報網站特殊券商
    ("东兴证券", "东兴证券"), ("东吴证券", "东吴证券"),
    ("交银国际证券", "交银国际"), ("交银国际", "交银国际"),
    ("华源证券", "华源证券"), ("华西证券", "华西证券"),
    # 中國銀行系投資銀行 / 國際財經媒體
    ("中国银河", "中国银河"), ("彭博", "Bloomberg"),
    ("路透", "Reuters"), ("Wind资讯", "Wind"),
]

OVERSEAS_MARKETS = ("US", "HK", "JP", "CN", "KR", "UK")
DATE_RE = re.compile(r"(20\d{6})")  # YYYYMMDD


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def detect_broker(text: str) -> str:
    for keyword, name in BROKERS:
        if keyword in text:
            return name
    return ""


def detect_date(text: str) -> str:
    """回傳 YYYY-MM-DD 或空字串"""
    # YYYYMMDD
    for m in DATE_RE.finditer(text):
        try:
            datetime.strptime(m.group(1), "%Y%m%d")
            return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"
        except ValueError:
            continue
    # MMDDYYYY (晨訊06232026)
    m = re.search(r"(\d{2})(\d{2})(20\d{2})", text)
    if m:
        try:
            raw = f"{m.group(3)}{m.group(1)}{m.group(2)}"
            datetime.strptime(raw, "%Y%m%d")
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        except ValueError:
            pass
    # YYMMDD (Nan Ya Plastics ... JPM 260621)
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
    if m:
        raw = "20" + m.group(1)
        try:
            datetime.strptime(raw, "%Y%m%d")
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        except ValueError:
            pass
    return ""


def parse_filename(filename: str):
    """解析檔名 → metadata dict 或 None"""
    raw = normalize(filename)
    raw = re.sub(r"\.(pdf|md|docx|txt|zip)$", "", raw, flags=re.IGNORECASE)
    # 移除尾部 _(1) (2) (3) 重複編號 (含連帶的尾底線/空白)
    raw = re.sub(r"[_\s]*\(\d+\)$", "", raw)
    raw = raw.rstrip("_- ")
    # 移除網站浮水印/廣告
    raw = re.sub(r"【洞[一-鿿]研报[^】]*】", "", raw)
    raw = re.sub(r"【洞[一-鿿]研報[^】]*】", "", raw)
    raw = re.sub(r"DJyanbao\.com", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"洞见研报", "", raw)
    raw = re.sub(r"洞見研報", "", raw)
    raw = raw.strip(" -_")
    # 統一分隔符: ｜ → |，| 前後空白吃掉
    name = re.sub(r"\s*\|\s*", "|", raw)
    broker = detect_broker(name)

    # ===== Memo (自製) =====
    # 聯友金屬-創(7610)-2026-06-23-memo
    m = re.match(r"^(.+?)-([創興上櫃])\((\d{4,6})\)-(\d{4}-\d{2}-\d{2})-?memo$", name, re.IGNORECASE)
    if m:
        company, board, code, date = m.groups()
        return _meta("Memo", date=date, broker="自製",
                     stock_code=code, stock_name=company.strip(),
                     topic=f"{company.strip()} ({board}板)")
    # 聯友金屬(7610)-2026-06-23-memo
    m = re.match(r"^(.+?)\((\d{4,6})\)-?(\d{4}-\d{2}-\d{2})-?memo$", name, re.IGNORECASE)
    if m:
        company, code, date = m.groups()
        return _meta("Memo", date=date, broker="自製",
                     stock_code=code, stock_name=company.strip(),
                     topic=company.strip())
    # 7610_20260623_memo (標準化後檔名，容忍尾底線)
    m = re.match(r"^(\d{4,6})_(\d{8})_memo_*$", name, re.IGNORECASE)
    if m:
        code, ymd = m.groups()
        return _meta("Memo", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker="自製", stock_code=code,
                     stock_name=STOCK_NAMES.get(code, ""))
    # 松翰(5471)_20260623_memo (新格式)
    m = re.match(r"^([一-鿿]+)\((\d{4,6})\)_(\d{8})_memo$", name, re.IGNORECASE)
    if m:
        cname, code, ymd = m.groups()
        return _meta("Memo", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker="自製", stock_code=code, stock_name=cname,
                     topic=cname)
    # 國泰證期研究部 矽格(6257 TT) Call Memo 20260623
    m = re.match(r"^(.+?)\s+([一-鿿]+)\((\d{4,6})(?:\s+TT)?\)\s+Call Memo\s+(\d{8})$", name, re.IGNORECASE)
    if m:
        brk_raw, cname, code, ymd = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        return _meta("Memo", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, stock_code=code, stock_name=cname,
                     topic=f"{cname} Call Memo")

    # ===== 個股 (券商-股號-公司-日期，新格式) =====
    # 元大-2059-川湖-20260608 / 台新-4807-日成-KY-20260612
    m = re.match(r"^([一-鿿]+)-(\d{4})-([一-鿿A-Za-z\-]+)-(\d{8})$", name)
    if m:
        brk_raw, code, cname, ymd = m.groups()
        brk = detect_broker(brk_raw) or brk_raw
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=code, stock_name=cname.strip(), broker=brk)
    # 修正規則：之前被誤分類成「YYYYMMDD_股號 公司_券商」
    m = re.match(r"^(\d{8})_(\d{4})\s+([一-鿿A-Za-z\-\s]+?)_([一-鿿A-Za-z]+)$", name)
    if m:
        ymd, code, cname, brk_raw = m.groups()
        brk = detect_broker(brk_raw) or brk_raw
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=code, stock_name=cname.strip(), broker=brk)

    # ===== 海外個股 (券商-英文公司名(TICKER.MARKET)，新格式) =====
    # 群益-DigitalOcean Holdings Inc. (DOCN.US)
    m = re.match(r"^([一-鿿]+)-(.+?)\s*\(([A-Z][A-Z0-9.]*)\.([A-Z]+)\)(.*)$", name)
    if m:
        brk_raw, cname, ticker, market, rest = m.groups()
        if market in OVERSEAS_MARKETS:
            brk = detect_broker(brk_raw) or brk_raw
            date = detect_date(rest + " " + name) or ""
            return _meta("海外個股", date=date, ticker=ticker, market=market,
                         stock_name=cname.strip(), broker=brk)
    # 修正規則：之前被誤分類成「YYYYMMDD_英文公司名 (TICKER.MARKET)_券商」
    m = re.match(r"^(\d{8})_(.+?)\s*\(([A-Z][A-Z0-9.]*)\.([A-Z]+)\)_([一-鿿A-Za-z]+)$", name)
    if m:
        ymd, cname, ticker, market, brk_raw = m.groups()
        if market in OVERSEAS_MARKETS:
            brk = detect_broker(brk_raw) or brk_raw
            return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         ticker=ticker, market=market,
                         stock_name=cname.strip(), broker=brk)

    # ===== 個股 (｜ 分隔主流，台股) =====
    # 2609 陽明|20260622|元富 / 2609 陽明|20260622|元富|主題
    m = re.match(r"^(\d{4})\s+([^\d|][^|]{0,30}?)\|(\d{8})\|([^|]+?)(?:\|.*)?$", name)
    if m:
        code, stk_name, ymd, brk_raw = m.groups()
        stk_clean = re.sub(r"\s*\([^)]*\)\s*", "", stk_name).strip()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=code, stock_name=stk_clean, broker=brk)
    # 1303 南亞 (Nan Ya Plastics)  20260621  JPM  (空白分隔變體)
    m = re.match(r"^(\d{4})\s+([^\d][^\d]{0,30}?)\s+(\d{8})\s+([一-鿿A-Za-z]+)$", name)
    if m:
        code, stk_name, ymd, brk_raw = m.groups()
        stk_clean = re.sub(r"\s*\([^)]*\)\s*", "", stk_name).strip()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=code, stock_name=stk_clean, broker=brk)

    # ===== 海外個股 =====
    # 英文公司名 (TICKER-US)|YYYYMMDD|券商  ex: Amphenol Corporation (APH-US)|20260622|群益
    m = re.match(r"^([A-Za-z][A-Za-z\s\-\.]+?)\s*\(([A-Z][A-Z0-9\.]*)[\-\s]([A-Z]+)\)\|(\d{8})\|([^|]+)$", name)
    if m:
        cname, ticker, market, ymd, brk_raw = m.groups()
        if market in OVERSEAS_MARKETS:
            return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         ticker=ticker, market=market, stock_name=cname.strip(),
                         broker=detect_broker(brk_raw) or brk_raw.strip())
    # 朋友規範化: AAPL_US_20260129_元大
    m = re.match(r"^([A-Z][A-Z0-9.]*)_(" + "|".join(OVERSEAS_MARKETS) + r")_(\d{8})_(.+)$", name)
    if m:
        ymd = m.group(3)
        return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     ticker=m.group(1), market=m.group(2),
                     broker=detect_broker(m.group(4)) or m.group(4).strip())
    # 20260623兆豐海外個股報告-TSLA(TSLA US)
    m = re.match(r"^(\d{8})([一-鿿]+)海外個股報告-([A-Z][A-Z0-9.]*)\([A-Z][A-Z0-9.]*\s*([A-Z]+)\)$", name)
    if m:
        ymd = m.group(1)
        market = m.group(4) if m.group(4) in OVERSEAS_MARKETS else "US"
        return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     ticker=m.group(3), market=market, broker=m.group(2))
    # GF-SpaceX's Move ... 20260622  (廣發海外)
    m = re.match(r"^GF-(.+?)\s*(\d{8})$", name)
    if m:
        topic = m.group(1).strip()
        ymd = m.group(2)
        if topic.isdigit() and len(topic) == 4:  # GF-3665 → 廣發台股
            return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         stock_code=topic, broker="廣發")
        return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_name=topic, broker="廣發", topic=topic)
    # 外資台股: Nan Ya Plastics(1303TW) JPM 260621
    m = re.match(r"^(.+?)\((\d{4})TW\)\s+([A-Za-z]+)\s+(\d{6})$", name)
    if m:
        date = detect_date(name)
        return _meta("個股", date=date, stock_code=m.group(2),
                     stock_name=m.group(1).strip(),
                     broker=detect_broker(m.group(3)) or m.group(3))

    # ===== 個股 (有股號) =====
    # 朋友規範化: 2609_20260623_元富
    m = re.match(r"^(\d{4})_(\d{8})_(.+)$", name)
    if m:
        ymd = m.group(2)
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=m.group(1),
                     broker=detect_broker(m.group(3)) or m.group(3).strip())
    # 2383台光電20260622-元富投顧(...) / 2609陽明20260623-...
    m = re.match(r"^(\d{4})([一-鿿]+)(\d{8})-(.+)$", name)
    if m:
        ymd = m.group(3)
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=m.group(1), stock_name=m.group(2),
                     broker=detect_broker(m.group(4)))
    # 可成(2474)-20260622-速報-元富投顧(...) / 陽明(2609)-...
    m = re.match(r"^([一-鿿]+)\((\d{4})\)-(\d{8})-(.+)$", name)
    if m:
        ymd = m.group(3)
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=m.group(2), stock_name=m.group(1),
                     broker=detect_broker(m.group(4)))
    # 20260623兆豐個股報告-日友(8341)
    m = re.match(r"^(\d{8})([一-鿿]+)個股報告-([一-鿿]+)\((\d{4})\)$", name)
    if m:
        ymd = m.group(1)
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=m.group(4), stock_name=m.group(3),
                     broker=m.group(2))

    # ===== 策略類 (券商|主題|YYYYMMDD[|細節]) =====
    # 中信|主動式ETF籌碼追蹤|20260622 / 兆豐|投資早報|20260622
    # 中信|投資早報|20260622|2883凱基金、6533晶心科
    m = re.match(r"^([一-鿿A-Za-z]+)\|([^|]+?)\|(\d{8})(?:\|(.+))?$", name)
    if m:
        brk_raw, topic, ymd, detail = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        if brk:
            full = topic + " " + (detail or "")
            cat = classify_topic_text(full)
            return _meta(cat, date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         broker=brk, topic=topic.strip())
    # MS|Power Semis|Supply Driven Upcycle|20260618 (外資英文有多段)
    m = re.match(r"^([A-Z]{2,4})\|(.+)\|(\d{8})$", name)
    if m:
        brk_raw, mid, ymd = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        if brk:
            topic = mid.replace("|", " - ").strip()
            return _meta("產業", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         broker=brk, topic=topic)
    # 群益|專題報告|7月台股投資策略|20260622|指數挑戰...
    m = re.match(r"^([一-鿿]+)\|([^|]+?)\|([^|]+?)\|(\d{8})(?:\|(.+))?$", name)
    if m:
        brk_raw, t1, t2, ymd, _det = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        if brk:
            topic = f"{t1.strip()} {t2.strip()}"
            cat = classify_topic_text(topic)
            return _meta(cat, date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         broker=brk, topic=topic)

    # ===== 外資英文 (YYMMDD_xxx_xxx_xxx) =====
    # 260618_6831_邁科_daiwa_Taiwan Microloops
    m = re.match(r"^(\d{6})_(\d{4})_([一-鿿]+)_([a-z]+)_(.+)$", name, re.IGNORECASE)
    if m:
        yymmdd, code, cname, brk_raw, topic = m.groups()
        date = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}"
        brk = detect_broker(brk_raw) or brk_raw.upper()
        return _meta("個股", date=date, stock_code=code,
                     stock_name=cname.strip(), broker=brk, topic=topic.strip())
    # 260618_功率半導體_ms_power-semis (產業)
    m = re.match(r"^(\d{6})_([一-鿿]+)_([a-z]+)_(.+)$", name, re.IGNORECASE)
    if m:
        yymmdd, topic_zh, brk_raw, topic_en = m.groups()
        date = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}"
        brk = detect_broker(brk_raw) or brk_raw.upper()
        return _meta("產業", date=date, broker=brk,
                     topic=topic_zh.strip())
    # 260622_ms_kyec / 260622_jp_innostar-OW-initiation (短格式)
    m = re.match(r"^(\d{6})_([a-z]+)_(.+)$", name, re.IGNORECASE)
    if m:
        yymmdd, brk_raw, topic = m.groups()
        try:
            datetime.strptime("20" + yymmdd, "%Y%m%d")
            date = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}"
            brk = detect_broker(brk_raw) or brk_raw.upper()
            return _meta("產業", date=date, broker=brk, topic=topic.strip())
        except ValueError:
            pass

    # ===== 中國研報 (券商_主題_YYMMDD) =====
    # 中邮证券_钼行业专题报告：...资源博弈加剧_260618
    m = re.match(r"^([一-鿿]+证券|[一-鿿]+视角|[一-鿿]+智能投研|[一-鿿]+证券[一-鿿]*)_(.+)_(\d{6})$", name)
    if m:
        brk_raw, topic, yymmdd = m.groups()
        try:
            datetime.strptime("20" + yymmdd, "%Y%m%d")
            date = f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:]}"
            brk = detect_broker(brk_raw) or brk_raw
            return _meta("產業", date=date, broker=brk, topic=topic.strip())
        except ValueError:
            pass

    # ===== 修正規則：YYYYMMDD_股號_中文_英文券商_英文主題 =====
    # 20260621_1303_南亞_JPM_Nan Ya Plastics Corp → 個股
    m = re.match(r"^(\d{8})_(\d{4})_([一-鿿]+)_([A-Za-z]+)_(.+)$", name)
    if m:
        ymd, code, cname, brk_raw, topic = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.upper()
        return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     stock_code=code, stock_name=cname, broker=brk, topic=topic.strip())
    # 20260621_JPM_Nan Ya Plastics Corp → 海外個股(無 ticker, 純英文)
    m = re.match(r"^(\d{8})_([A-Z]{2,5})_(.+)$", name)
    if m:
        ymd, brk_raw, topic = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.upper()
        return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, topic=topic.strip(), stock_name=topic.strip())
    # YYYYMMDD_NN_中文券商_YYYYMMDD_英文主題 (集邦那種雙日期)
    m = re.match(r"^\d{8}_\d{1,2}_([一-鿿A-Za-z]+)_(\d{8})_(.+)$", name)
    if m:
        brk_raw, ymd, topic = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        return _meta("產業", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, topic=topic.strip())

    # ===== 中國研報網站翻譯外資 (Pattern A) =====
    # 摩根士丹利-电池与人工智能：xxx-20260621【52页】_pS32
    # 基础化工-基础化工行业：xxx-广发证券[作者]-20260621【11页】_yC80 (中國券商在 topic 內)
    m = re.match(r"^([一-鿿]+)-(.+?)-(\d{8})【\d+[页頁]】(?:_[\w]+)?$", name)
    if m:
        head, topic_raw, ymd = m.groups()
        brk = detect_broker(head)
        if not brk:
            # head 是行業類別，broker 藏在 topic_raw 內，找 X证券
            brk_m = re.search(r"([一-鿿]{2,}证券)", topic_raw)
            if brk_m:
                brk = brk_m.group(1)
        if brk:
            topic = topic_raw.split("-", 1)[0].strip()
            cat = classify_topic_text(topic + " " + name)
            return _meta(cat, date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         broker=brk, topic=topic)

    # ===== 中國研報網站【洞见研报】(Pattern B) =====
    # 【东兴证券】电子行业2026半年度策略：xxx【洞见研报DJyanbao.com】
    m = re.match(r"^【([一-鿿A-Za-z]+)】(.+?)(?:【洞[一-鿿]+研报[^】]+】)?$", name)
    if m:
        brk_raw, topic = m.groups()
        brk = detect_broker(brk_raw) or brk_raw
        topic = topic.strip()
        cat = classify_topic_text(topic)
        # 沒明確日期 → 用 today (fallback)
        date = datetime.now().strftime("%Y-%m-%d")
        return _meta(cat, date=date, broker=brk, topic=topic)

    # ===== 產業 / 總經 / 策略 =====
    date = detect_date(name)
    # 規範化格式優先: 20260623_貨櫃產業_元富 (含 _ - 空白 等分隔符)
    m = re.match(r"^(\d{8})[_\-\s]+(.+?)[_\-\s]+([一-鿿A-Za-z]+)$", name)
    if m:
        ymd = m.group(1)
        topic_clean = m.group(2).strip(" _-—")
        brk_raw = m.group(3).strip()
        brk = detect_broker(brk_raw) or brk_raw
        cat = classify_topic_text(topic_clean + " " + name)
        return _meta(cat, date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, topic=topic_clean)
    if date and broker:
        # 產業專題--貨櫃產業 20260623_元富投顧(...)
        if "產業" in name:
            topic = re.sub(r"\d{8}.*$", "", name).strip(" _-")
            topic = re.sub(r"^產業專題-+", "", topic).strip(" _-")
            return _meta("產業", date=date, broker=broker, topic=topic or name)
        # 週報/日報/早報/晨訊/彙報/投資策略 → 策略與定期刊物
        if any(k in name for k in ["週報", "週刊", "日報", "日刊", "早報", "彙報", "晨訊", "投資策略", "投資週報", "股市彙報", "投資早報", "Morning"]):
            topic = clean_topic(name, date, broker)
            return _meta("策略與定期刊物", date=date, broker=broker, topic=topic)
        # 總經類關鍵字
        if any(k in name for k in ["總經", "總體", "FOMC", "BOE", "BOJ", "ECB", "央行", "利率評論", "通膨", "外匯週報"]):
            topic = clean_topic(name, date, broker)
            return _meta("總經", date=date, broker=broker, topic=topic)
        # 預設歸到產業 (帶日期+券商通常是產業/主題報告)
        topic = clean_topic(name, date, broker)
        return _meta("產業", date=date, broker=broker, topic=topic)

    # 沒 YYYYMMDD，只有 4 位 MMDD: 元富投顧(...)股市彙報 0622
    if not date and broker:
        m = re.match(r"^(.+?)\s+(\d{4})$", name)
        if m:
            mmdd = m.group(2)
            try:
                mm, dd = int(mmdd[:2]), int(mmdd[2:])
                year = datetime.now().year
                datetime(year, mm, dd)
                return _meta("策略與定期刊物",
                             date=f"{year:04d}-{mm:02d}-{dd:02d}",
                             broker=broker, topic=m.group(1).strip())
            except ValueError:
                pass

    return None


def _meta(category, **kwargs):
    base = {"category": category, "date": "", "broker": "",
            "stock_code": "", "stock_name": "",
            "ticker": "", "market": "", "topic": ""}
    base.update(kwargs)
    return base


def classify_topic_text(text: str) -> str:
    """根據主題字串判斷類別"""
    if any(k in text for k in ["總經", "總體", "FOMC", "央行", "利率", "通膨", "BOJ", "BOE", "ECB", "美聯儲", "聯準會"]):
        return "總經"
    if any(k in text for k in ["週報", "週刊", "日報", "日刊", "早報", "彙報", "晨訊", "晨會", "晨會分析", "晨會報告", "投資策略", "投資週報", "投資早報", "盤後", "盤前", "盤勢", "投資周報", "Morning", "ETF", "籌碼", "短沖", "週策略", "市場觀察", "盤後快訊", "投資周刊", "投資週刊", "快訊", "彙報", "新聞摘要", "早會", "每日"]):
        return "策略與定期刊物"
    return "產業"


def clean_topic(name: str, date: str, broker: str) -> str:
    topic = name
    for ymd in DATE_RE.findall(name):
        topic = topic.replace(ymd, "")
    if broker:
        topic = topic.replace(broker, "")
    topic = re.sub(r"投顧\(.+?\)", "", topic)
    topic = re.sub(r"[_\-\s]+", " ", topic).strip(" _-—")
    return topic or "report"


def sanitize_for_filename(text: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:60] or "report"


def standardized_name(meta: dict, ext: str = ".pdf") -> str:
    # 簡 → 繁 (對 topic, stock_name, broker 都套用，避免中港報告顯示簡體)
    for k in ("topic", "stock_name", "broker"):
        if meta.get(k):
            meta[k] = to_traditional(meta[k])
    ymd = meta["date"].replace("-", "")
    if meta["category"] == "外資報告":
        # 根據 metadata 形態決定命名
        if meta.get("stock_code"):
            return f"{meta['stock_code']}_{ymd}_{meta['broker']}{ext}"
        if meta.get("ticker"):
            mkt = meta.get("market") or "US"
            return f"{meta['ticker']}_{mkt}_{ymd}_{meta['broker']}{ext}"
        topic = sanitize_for_filename(meta.get("topic") or "report")
        return f"{ymd}_{topic}_{meta['broker']}{ext}"
    if meta["category"] == "個股":
        return f"{meta['stock_code']}_{ymd}_{meta['broker']}{ext}"
    if meta["category"] == "海外個股":
        ticker = meta.get("ticker") or meta.get("stock_code") or "X"
        market = meta.get("market") or "US"
        return f"{ticker}_{market}_{ymd}_{meta['broker']}{ext}"
    if meta["category"] == "Memo":
        return f"{meta['stock_code']}_{ymd}_memo{ext}"
    topic = sanitize_for_filename(meta.get("topic") or "report")
    return f"{ymd}_{topic}_{meta['broker']}{ext}"


def unique_path(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    n = 2
    while True:
        cand = target.with_name(f"{stem}_({n}){suffix}")
        if not cand.exists():
            return cand
        n += 1


RESERVED_NAMES = {"desktop.ini", "0_使用說明.txt"}


def is_reserved(path: Path) -> bool:
    name = path.name
    if name in RESERVED_NAMES:
        return True
    if name.startswith("0_") or name.startswith("_"):
        return True
    return False


def collect_files():
    """掃根目錄 + 所有 年份\類別\ 下的檔案"""
    accepted = {".pdf", ".md", ".docx", ".txt", ".zip"}
    files = []
    # 根目錄
    for f in ROOT.iterdir():
        if f.is_file() and f.suffix.lower() in accepted and not is_reserved(f):
            files.append(f)
    # 年份子目錄
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for f in cat_dir.iterdir():
                if f.is_file() and f.suffix.lower() in accepted and not is_reserved(f):
                    files.append(f)
    return files


def organize():
    moved, pending, skipped = 0, 0, 0
    PENDING_DIR.mkdir(exist_ok=True)
    learned = 0
    for pdf in sorted(collect_files()):
        # zip 一律移待處理
        if pdf.suffix.lower() == ".zip":
            target = unique_path(PENDING_DIR / pdf.name)
            if str(pdf.parent.resolve()) != str(PENDING_DIR.resolve()):
                shutil.move(str(pdf), str(target))
                print(f"  [待處理] (zip) {pdf.name}")
                pending += 1
            continue
        meta = parse_filename(pdf.name)
        meta = enrich_meta(meta, pdf.name)
        if not meta or not meta.get("date") or not meta.get("broker"):
            if str(pdf.parent.resolve()) == str(PENDING_DIR.resolve()):
                continue  # 已在待處理就不重複搬
            target = unique_path(PENDING_DIR / pdf.name)
            shutil.move(str(pdf), str(target))
            print(f"  [待處理] {pdf.name}")
            pending += 1
            continue
        if meta["category"] == "個股" and not meta.get("stock_code"):
            target = unique_path(PENDING_DIR / pdf.name)
            shutil.move(str(pdf), str(target))
            print(f"  [待處理] (個股缺股號) {pdf.name}")
            pending += 1
            continue
        if meta.get("stock_code") and meta.get("stock_name"):
            code = meta["stock_code"]
            name = meta["stock_name"].strip()
            if name and STOCK_NAMES.get(code) != name:
                STOCK_NAMES[code] = name
                learned += 1
        # 外資 broker → 一律歸到「外資報告」(Memo 不動)
        if is_foreign_broker(meta["broker"]) and meta["category"] != "Memo":
            meta["category"] = "外資報告"
        year = meta["date"][:4]
        target_dir = ROOT / year / meta["category"]
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            naive_target = target_dir / standardized_name(meta, pdf.suffix.lower())
        except Exception as e:
            print(f"  [待處理] {pdf.name} (改名失敗: {e})")
            shutil.move(str(pdf), str(unique_path(PENDING_DIR / pdf.name)))
            pending += 1
            continue
        # 已經在標準位置且標準名 → skip (避免被 unique_path 誤判為衝突再加 _(2))
        if naive_target.exists() and naive_target.resolve() == pdf.resolve():
            skipped += 1
            continue
        target = unique_path(naive_target)
        if pdf.resolve() == target.resolve():
            skipped += 1
            continue
        shutil.move(str(pdf), str(target))
        old_loc = f"{pdf.parent.name}\\" if pdf.parent != ROOT else ""
        print(f"  [整理] {old_loc}{pdf.name}  →  {year}\\{meta['category']}\\{target.name}")
        moved += 1
    if learned:
        save_stock_names(STOCK_NAMES)
        print(f"  (新增 {learned} 筆股號對照表 → _scripts\\stock_names.json)")
    return moved, pending, skipped


def build_index():
    reports = []
    for year_path in sorted(ROOT.iterdir()):
        if not year_path.is_dir() or not re.match(r"^20\d{2}$", year_path.name):
            continue
        for cat_path in sorted(year_path.iterdir()):
            if not cat_path.is_dir() or cat_path.name not in CATEGORIES:
                continue
            for pdf in sorted(cat_path.iterdir()):
                if pdf.suffix.lower() not in {".pdf", ".md", ".docx", ".txt"}:
                    continue
                reports.append(build_entry(pdf, cat_path.name, year_path.name))

    payload = {
        "schema_version": "hermes_static_report_reader.v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "title": "MEMO烏骨雞 報告庫",
        "stats": {"reports": len(reports)},
        "reports": reports,
    }
    READER_INDEX.parent.mkdir(parents=True, exist_ok=True)
    READER_INDEX.write_text(
        "window.HERMES_STATIC_REPORT_READER_INDEX = " + json.dumps(payload, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    print(f"\n  寫入 閱讀器\\assets\\report-index.js  ({len(reports)} 筆)")


def build_entry(pdf: Path, category: str, year: str) -> dict:
    meta = parse_filename(pdf.name) or {}
    meta = enrich_meta(meta, pdf.name)
    date = meta.get("date") or guess_date_from_year(year, pdf.name)
    broker = meta.get("broker", "")
    stock_code = meta.get("stock_code", "")
    stock_name = meta.get("stock_name", "") or STOCK_NAMES.get(stock_code, "")
    topic = meta.get("topic", "")
    market = meta.get("market", "")

    if category == "海外個股":
        ticker = meta.get("ticker") or stock_code
        rid = f"{ticker}_{market}_{date.replace('-', '')}_{broker}" if (ticker and date) else pdf.stem
        display_subject = f"{ticker} {stock_name}".strip() if ticker else (stock_name or pdf.stem)
    elif category == "個股":
        rid = f"{stock_code}_{date.replace('-', '')}_{broker}" if (stock_code and date) else pdf.stem
        display_subject = f"{stock_code} {stock_name}".strip() if stock_code else pdf.stem
    else:
        rid = pdf.stem
        display_subject = topic or pdf.stem

    rel_pdf = pdf.relative_to(ROOT).as_posix()
    href = "../" + "/".join(quote(part) for part in rel_pdf.split("/"))
    search_bits = [pdf.stem, date, category, stock_code, stock_name, topic, broker, pdf.name]
    search_text = " ".join(s for s in search_bits if s).lower()

    return {
        "id": rid,
        "date": date,
        "category": category,
        "report_type": category,
        "title": "報告",
        "display_name": stock_name or topic or pdf.stem,
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
        "source_file": pdf.name,
        "search_text": search_text,
        "pdf_href": href,
        "pdf_status": "relative",
    }


def guess_date_from_year(year: str, name: str) -> str:
    m = DATE_RE.search(name)
    if m:
        ymd = m.group(1)
        return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
    return f"{year}-01-01"


def dedupe_duplicates() -> int:
    """掃所有 年份/類別/ 下檔名為 stem_(N) 的重複版，與原版比 size，相同就刪。"""
    import re as _re
    removed = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not _re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for f in cat_dir.iterdir():
                if not f.is_file():
                    continue
                m = _re.match(r"^(.+)_\((\d+)\)$", f.stem)
                if not m:
                    continue
                base = m.group(1)
                original = f.with_name(f"{base}{f.suffix}")
                if original.exists():
                    s1, s2 = original.stat().st_size, f.stat().st_size
                    # size 完全相同 → 必為重複；差 ≤ 100 bytes → PDF metadata 差異也算重複
                    if abs(s1 - s2) <= 100:
                        print(f"  [刪重複] {f.relative_to(ROOT)} (= {original.name})")
                        f.unlink()
                        removed += 1
    return removed


def fix_orphan_duplicates() -> int:
    """孤立的 _(N) 版本（沒對應的 _.pdf 原版）→ 改回 _.pdf"""
    import re as _re
    fixed = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not _re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            # 按 N 由小到大處理，避免互踩
            files_with_n = []
            for f in cat_dir.iterdir():
                if not f.is_file():
                    continue
                m = _re.match(r"^(.+)_\((\d+)\)$", f.stem)
                if m:
                    files_with_n.append((int(m.group(2)), m.group(1), f))
            files_with_n.sort()
            for _, base, f in files_with_n:
                original = f.with_name(f"{base}{f.suffix}")
                if not original.exists():
                    print(f"  [改回原名] {f.relative_to(ROOT)} → {original.name}")
                    f.rename(original)
                    fixed += 1
    return fixed


def write_heartbeat():
    """寫 timestamp 給雲端 GHA 看：本機剛跑過，雲端不用再跑"""
    try:
        heartbeat_path = SCRIPTS_DIR / "last_local_run.txt"
        heartbeat_path.write_text(
            datetime.now(timezone.utc).isoformat(),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"  (heartbeat 寫入失敗: {e})")


def sync_parser_to_cloud():
    """把本機 update.py 內容同步到 auto_organize/scripts/parser_lib.py
    確保雲端跑跟本機一樣的 parser 規則。需要再手動 git push。
    """
    cloud_parser = SCRIPTS_DIR / "auto_organize" / "scripts" / "parser_lib.py"
    if not cloud_parser.parent.exists():
        return
    try:
        src = Path(__file__).read_bytes()
        if cloud_parser.exists() and cloud_parser.read_bytes() == src:
            return  # 已一致
        cloud_parser.write_bytes(src)
        print(f"  (parser_lib.py 已同步到 auto_organize\\，記得 git push 雲端才會用到)")
    except Exception as e:
        print(f"  (parser sync 失敗: {e})")


def main():
    print(f"根目錄: {ROOT}\n")
    print("[1/4] 整理檔案...")
    moved, pending, skipped = organize()
    print(f"  完成: 整理 {moved} 份、待處理 {pending} 份、原地 {skipped} 份\n")
    print("[2/4] 自動刪重複...")
    removed = dedupe_duplicates()
    print(f"  完成: 刪除 {removed} 份重複\n")
    print("[3/4] 整理孤立 _(N) → 原名...")
    fixed = fix_orphan_duplicates()
    print(f"  完成: 整理 {fixed} 份\n")
    print("[4/4] 重建索引...")
    build_index()
    write_heartbeat()
    sync_parser_to_cloud()
    print("\n全部完成。開 啟動閱讀器.bat 看結果。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n!! 錯誤: {e}", file=sys.stderr)
        raise
    finally:
        try:
            input("\n按 Enter 結束...")
        except EOFError:
            pass
