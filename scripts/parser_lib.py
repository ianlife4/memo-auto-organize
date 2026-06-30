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

_TW_PREFER = [  # 台灣慣用 (post-process zhconv 結果)
    # 「臺」字反正規化回「台」(台灣官方寫法)
    ("臺新", "台新"), ("臺積電", "台積電"), ("臺塑", "台塑"),
    ("臺化", "台化"), ("臺泥", "台泥"), ("臺灣", "台灣"),
    ("臺中", "台中"), ("臺北", "台北"), ("臺股", "台股"),
    ("臺幣", "台幣"), ("臺電", "台電"), ("臺光電", "台光電"),
    ("臺達電", "台達電"), ("臺虹", "台虹"), ("臺勝科", "台勝科"),
    # zhconv 過度轉換「游→遊」
    ("上遊", "上游"), ("下遊", "下游"), ("中遊", "中游"),
    # zhconv 過度轉換「群→羣」(本字但台灣慣用「群」)
    ("羣益", "群益"), ("羣創", "群創"), ("羣科", "群科"),
    ("人羣", "人群"), ("族羣", "族群"),
    # 大陸用詞 → 台灣慣用
    ("光模塊", "光模組"), ("模塊化", "模組化"),
    ("信息技術", "資訊科技"), ("信息系統", "資訊系統"),
    ("軟件", "軟體"), ("硬件", "硬體"),
    ("網絡", "網路"),
    ("奔馳", "賓士"), ("寶馬", "BMW"),
    # 簡轉繁殘留
    ("机器人", "機器人"),
]

try:
    from zhconv import convert as _zh_convert
    def to_traditional(text: str) -> str:
        if not text:
            return text
        text = _zh_convert(text, "zh-hant")
        for old, new in _TW_PREFER:
            text = text.replace(old, new)
        return text
except ImportError:
    def to_traditional(text: str) -> str:
        if not text:
            return text
        for old, new in _TW_PREFER:
            text = text.replace(old, new)
        return text

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
ANALYSTS_CACHE_FILE = SCRIPTS_DIR / "analysts_cache.json"
CATEGORIES = ["個股", "海外個股", "大陸個股", "產業", "大陸產業", "總經", "策略與定期刊物", "外資報告", "Memo"]

# 中國大陸券商 (broker 落在這 → category 改成「大陸報告」)
CHINA_BROKERS = {
    "東方財富證券", "东方财富证券",
    "長江證券", "长江证券",
    "太平洋證券", "太平洋证券",
    "興業證券", "兴业证券",
    "光大證券", "光大证券",
    "中泰證券", "中泰证券",
    "東吳證券", "东吴证券",
    "東興證券", "东兴证券",
    "招商證券", "招商证券",
    "國信證券", "国信证券",
    "國盛證券", "国盛证券",
    "方正證券", "方正证券",
    "華西證券", "华西证券",
    "華泰證券", "华泰证券",
    "海通證券", "海通证券",
    "廣發證券", "广发证券",
    "申萬宏源", "申万宏源",
    "中信建投", "中信证券",
    "中金公司",
    "銀河證券", "银河证券",
    "國金證券", "国金证券",
    "國海證券", "国海证券",
    "華創證券", "华创证券",
    "財通證券", "财通证券",
    "中郵證券", "中邮证券",
    "天風證券", "天风证券",
    "平安證券", "平安证券",
    "安信證券", "安信证券",
    "中銀證券", "中银证券",
    "華源證券", "华源证券",
    "東北證券", "东北证券",
    "國聯證券", "国联证券",
    "交銀國際", "交银国际", "交銀國際證券",
    "渤海證券", "渤海证券",
    "華福證券", "华福证券",
    "山西證券", "山西证券",
    "信達證券", "信达证券",
    "西部證券", "西部证券",
    "民生證券", "民生证券",
    "開源證券", "开源证券",
    "浙商證券", "浙商证券",
    "上海證券", "上海证券",
    "國元證券", "国元证券",
    "長城證券", "长城证券",
    "紅塔證券", "红塔证券",
    "萬聯證券", "万联证券",
    "湘財證券", "湘财证券",
    "東亞前海", "东亚前海",
    "第一創業", "第一创业",
    "中山證券", "中山证券",
    "新時代證券", "新时代证券",
    "中航證券", "中航证券",
    "華鑫證券", "华鑫证券",
    "粵開證券", "粤开证券",
    "南京證券", "南京证券",
    "東莞證券", "东莞证券",
    "華龍證券", "华龙证券",
    "甬興證券", "甬兴证券",
    "中國銀河", "中国银河", "中國銀河證券", "中国银河证券",
    "華興證券", "华兴证券",
    "西南證券", "西南证券",
    "財信證券", "财信证券",
    "財達證券", "财达证券",
    "中泰國際", "中泰国际",
    "海通國際", "海通国际",
    "瑞銀證券", "瑞银证券",
    "中銀國際", "中银国际",
    "申港證券", "申港证券",
    "華金證券", "华金证券",
    "華安證券", "华安证券",
    "華英證券", "华英证券",
    "國融證券", "国融证券",
    "國盛宏觀", "国盛宏观",
    "東方證券", "东方证券",
    "東吳國際", "东吴国际",
    "南華期貨", "南华期货",
    "中信里昂",
    # 中國研究平台 (不是券商但屬大陸出版)
    "慧博",
    "頭豹研究院", "头豹研究院", "頭豹",
    "前瞻研究院", "前瞻产业研究院", "前瞻產業研究院",
    "艾瑞諮詢", "艾瑞咨询",
    "易觀", "易观",
    "億歐", "亿欧",
    "智慧芽", "智慧牙",
    "弗若斯特沙利文", "Frost & Sullivan",
}

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
    """補上 parser 沒抓到的 stock_code + 統一中文轉繁體 + 個股辨識 + broker 補抓"""
    if not meta:
        return meta
    # 對 broker=未知 或 broker 不在 CHINA_BROKERS 但檔名/topic 內含大陸券商 → 補抓
    if meta.get("broker") in ("", "未知", None) or meta.get("broker") not in CHINA_BROKERS:
        haystack = filename + " " + (meta.get("topic") or "")
        for bk in sorted(CHINA_BROKERS, key=lambda s: -len(s)):
            # 確保是 broker 不是隨意字 — keyword 必須在前後有邊界字
            if bk in haystack:
                meta["broker"] = bk
                break
    # 從檔名 (NNNN TT) / (NNNN) / Call Memo NNNN / NNNN_公司名 / NNNN公司名 抽 stock_code
    if not meta.get("stock_code"):
        m = (re.search(r"\((\d{4})\s*[T台]", filename)         # (3030 TT) (1303 台)
             or re.search(r"\((\d{4})\)", filename)            # (1303)
             or re.search(r"Call\s*Memo\s+(\d{4})", filename, re.IGNORECASE)  # Call Memo 1301
             or re.search(r"(?:^|[\s_])(\d{4})(?=[\s_一-鿿])", filename))  # 1760 寶齡 / 7740_熙特爾 / 2383台光電 (NNNN緊貼中文)
        if m:
            code = m.group(1)
            # 過濾年份等非股號 (1900-2050)
            if not (1900 <= int(code) <= 2050) or int(code) > 2999:
                meta["stock_code"] = code
                if meta.get("category") == "產業":
                    meta["category"] = "個股"
    if not meta.get("stock_code") and meta.get("category") in ("個股", "外資報告", "產業"):
        code, name = lookup_stock_in_text(filename + " " + (meta.get("topic") or ""))
        if code:
            meta["stock_code"] = code
            if not meta.get("stock_name"):
                meta["stock_name"] = name
            # 若 broker 是個股相關 (e.g. 「研究部 XXX (NNNN TT)」)，從產業改個股
            if meta.get("category") == "產業":
                meta["category"] = "個股"
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


def load_analysts_cache() -> dict:
    if ANALYSTS_CACHE_FILE.exists():
        try:
            return json.loads(ANALYSTS_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_analysts_cache(cache: dict) -> None:
    ANALYSTS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ANALYSTS_CACHE_FILE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


ANALYSTS_CACHE = load_analysts_cache()


def get_pdf_metadata(pdf_path) -> dict:
    """從 cache 拿，沒有就開 PDF 抽 analysts + target_price + pdf_title + body_excerpt"""
    key = pdf_path.name
    try:
        mtime = pdf_path.stat().st_mtime
    except Exception:
        mtime = 0
    cached = ANALYSTS_CACHE.get(key)
    # 含 detected_broker 欄位才是 v3 cache (加 PDF 內文 broker 偵測)
    if (isinstance(cached, dict) and cached.get("mtime") == mtime
            and "detected_broker" in cached):
        return {
            "analysts": cached.get("analysts", []),
            "target_price": cached.get("target_price", {}),
            "pdf_title": cached.get("pdf_title", ""),
            "body_excerpt": cached.get("body_excerpt", ""),
            "stock_id": cached.get("stock_id", {}),
            "report_date": cached.get("report_date", ""),
            "detected_broker": cached.get("detected_broker", ""),
        }
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from extract_metadata import extract_metadata
        meta = extract_metadata(pdf_path)
    except Exception:
        meta = {"analysts": [], "target_price": {}, "pdf_title": "", "body_excerpt": "",
                "stock_id": {}, "report_date": "", "detected_broker": ""}
    ANALYSTS_CACHE[key] = {
        "mtime": mtime,
        "analysts": meta["analysts"],
        "target_price": meta["target_price"],
        "pdf_title": meta.get("pdf_title", ""),
        "body_excerpt": meta.get("body_excerpt", ""),
        "stock_id": meta.get("stock_id", {}),
        "report_date": meta.get("report_date", ""),
        "detected_broker": meta.get("detected_broker", ""),
    }
    return meta


def get_pdf_analysts(pdf_path) -> list:
    """Legacy wrapper. Use get_pdf_metadata for new code."""
    return get_pdf_metadata(pdf_path)["analysts"]


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
    # 亞洲獨立研究機構
    ("Aletheia", "Aletheia"), ("aletheia", "Aletheia"),
    ("CGS", "CGS"), ("Maybank", "Maybank"),
    # 純大寫 broker 變體 (case-sensitive substring match)
    ("CITI", "Citi"), ("HSBC", "HSBC"),
    # 報紙 / 新聞媒體
    ("工商時報", "工商時報"), ("經濟日報", "經濟日報"),
    ("鉅亨網", "鉅亨網"), ("自由時報", "自由時報"),
    ("聯合報", "聯合報"), ("中國時報", "中國時報"),
    ("哈燒新聞", "哈燒新聞"), ("MoneyDJ", "MoneyDJ"),
    ("DIGITIMES", "DIGITIMES"),
]

OVERSEAS_MARKETS = ("US", "HK", "JP", "CN", "KR", "UK")
DATE_RE = re.compile(r"(20\d{6})")  # YYYYMMDD


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    # 移除開頭過長 hash 前綴 (Google Drive ID / SHA hash 等，後面接有效 metadata)
    text = re.sub(r"^[A-F0-9]{20,}[_\s]+", "", text, flags=re.IGNORECASE)
    return text


def detect_broker(text: str) -> str:
    for keyword, name in BROKERS:
        if keyword in text:
            return name
    return ""


def detect_date(text: str) -> str:
    """回傳 YYYY-MM-DD 或空字串"""
    # YYYYMMDD (年份必須 2000-2050，否則視為 typo 略過)
    for m in DATE_RE.finditer(text):
        try:
            dt = datetime.strptime(m.group(1), "%Y%m%d")
            if 2000 <= dt.year <= 2050:
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
    raw = re.sub(r"\.(pdf|md|docx|doc|pptx|ppt|xlsx|xls|txt|zip)$", "", raw, flags=re.IGNORECASE)
    # 移除尾部 _(1) (2) (3) 重複編號 (含連帶的尾底線/空白)
    raw = re.sub(r"[_\s]*\(\d+\)$", "", raw)
    # 移除尾部 _[作者A,作者B] (避免 standardized 後再被 parse 時雙重附加)
    raw = re.sub(r"_\[[^\[\]]+\]\s*$", "", raw)
    raw = raw.rstrip("_- ")
    # 移除網站浮水印/廣告
    raw = re.sub(r"【洞[一-鿿]研报[^】]*】", "", raw)
    raw = re.sub(r"【洞[一-鿿]研報[^】]*】", "", raw)
    raw = re.sub(r"DJyanbao\.com", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"洞见研报", "", raw)
    raw = re.sub(r"洞見研報", "", raw)
    # 移除頁數標記跟 _隨機碼 (中國研報網站尾巴常見)
    raw = re.sub(r"【\d+\s*[页頁]】", "", raw)
    # 隨機碼必須「字母+數字混合」(避免誤刪 _Citi _Daiwa _memo 等純字母 broker)
    raw = re.sub(r"_(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{4,8}$", "", raw)
    # 移除多餘空白跟空 [] []
    raw = re.sub(r"\[\s*\]", "", raw)
    raw = re.sub(r"\s+", " ", raw)
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
    # 國票|台股投資週報|2606222 (7 位數誤輸入: 前 6 位視為 YYMMDD)
    m = re.match(r"^([一-鿿A-Za-z]+)\|([^|]+?)\|(\d{6,8})\d?(?:\|(.+))?$", name)
    if m:
        brk_raw, topic, ds, detail = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        if brk:
            if len(ds) == 8:
                date = f"{ds[:4]}-{ds[4:6]}-{ds[6:]}"
            else:
                date = f"20{ds[:2]}-{ds[2:4]}-{ds[4:6]}"
            full = topic + " " + (detail or "")
            cat = classify_topic_text(full)
            return _meta(cat, date=date, broker=brk, topic=topic.strip())
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
    # 20260624_MTK_CITI / 20260621_JPM_Nan Ya Plastics Corp
    # 順序可能是「YYYYMMDD_券商_主題」或「YYYYMMDD_ticker_券商」，
    # 用 detect_broker 判斷哪個 token 是已知 broker
    m = re.match(r"^(\d{8})_([A-Z]{2,5})_(.+)$", name)
    if m:
        ymd, a, b = m.groups()
        brk_a = detect_broker(a)
        brk_b_short = detect_broker(b) if len(b) <= 8 and b.isalpha() else ""
        if brk_b_short and not brk_a:
            # b 是 broker、a 是 ticker (例: 20260624_MTK_CITI)
            # a 若是台股 alias → 升級「個股」
            for tw_code, aliases in STOCK_ALIASES.items():
                if any(a == ali or a.upper() == ali.upper() for ali in aliases):
                    return _meta("個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                                 stock_code=tw_code,
                                 stock_name=STOCK_NAMES.get(tw_code, a),
                                 broker=brk_b_short)
            return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         ticker=a, market="US", stock_name=a,
                         broker=brk_b_short)
        # 預設: a 是 broker (例: 20260621_JPM_Nan Ya Plastics Corp)
        brk = brk_a or a.upper()
        return _meta("海外個股", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, topic=b.strip(), stock_name=b.strip())
    # YYYYMMDD_NN_中文券商_YYYYMMDD_英文主題 (集邦那種雙日期)
    m = re.match(r"^\d{8}_\d{1,2}_([一-鿿A-Za-z]+)_(\d{8})_(.+)$", name)
    if m:
        brk_raw, ymd, topic = m.groups()
        brk = detect_broker(brk_raw) or brk_raw.strip()
        return _meta("產業", date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, topic=topic.strip())

    # ===== 中國研報網站翻譯外資 (Pattern A) =====
    # 摩根士丹利-电池与人工智能：xxx-20260621【52页】_pS32
    # ===== 中國研報新格式: 行業-副標題：主標題-券商[作者1,作者2]-yyyymmdd =====
    # (【N頁】_xxxX 已被前面 normalize 移掉)
    # 例: 电气设备-电力设备行业专题研究：数据中心供电架构升级，SST趋势明确-东方财富证券[]-20260624
    # 例: 电气设备-新能源+商业航天系列研究：太空能源步入多路线、大市场新阶段-太平洋[刘强,钟欣材]-20260624
    m = re.match(
        r"^([一-鿿A-Za-z0-9]+)-(.+?)[：:](.+?)-([一-鿿A-Za-z]{2,15})(?:\[([^\]]*)\])?-(\d{8})\s*$",
        name,
    )
    if m:
        industry, subtitle, title, brk, authors_str, ymd = m.groups()
        # 加「证券」後綴若沒 (太平洋 → 太平洋证券，中信建投 → 中信建投证券)
        if not brk.endswith(("证券", "证劵", "證券")):
            brk = brk + "证券"
        cat = classify_topic_text(title + " " + name)
        return _meta(cat, date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, topic=title.strip())

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

    # ===== 中國研報 (Pattern D: YYYYMMDD-中國券商-主題.pdf) =====
    # 20240910-国联证券-小金属行业深度研究：xxx.pdf
    m = re.match(r"^(\d{8})-([一-鿿]+证券)-(.+)$", name)
    if m:
        ymd, brk, topic = m.groups()
        cat = classify_topic_text(topic + " " + name)
        return _meta(cat, date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk, topic=topic.strip())

    # ===== 報紙: 6.22 工商時報 / 6.23 經濟日報 =====
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\s+(.+)$", name)
    if m:
        mm, dd, paper = m.groups()
        brk = detect_broker(paper)
        if brk:
            year = datetime.now().year
            try:
                date = f"{year:04d}-{int(mm):02d}-{int(dd):02d}"
                return _meta("策略與定期刊物", date=date, broker=brk, topic=paper.strip())
            except ValueError:
                pass

    # ===== 新聞摘要 / 哈燒新聞 開頭 + YYYYMMDD =====
    m = re.match(r"^(新聞摘要|哈燒新聞)\s*[\.\s]?(\d{4}\.?\d{2}\.?\d{2}|\d{8}).*$", name)
    if m:
        brk_raw, ymd = m.groups()
        ymd = ymd.replace(".", "")
        return _meta("策略與定期刊物",
                     date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                     broker=brk_raw, topic=brk_raw)

    # ===== 個股長格式: 2303_聯電_2026-05-21_廣發_Jeff-Pu_Buy_135 =====
    m = re.match(r"^(\d{4})_([一-鿿]+)_(\d{4}-\d{2}-\d{2})_(.+)$", name)
    if m:
        code, cname, date, rest = m.groups()
        brk = detect_broker(rest) or rest.split("_", 1)[0]
        return _meta("個股", date=date, stock_code=code,
                     stock_name=cname, broker=brk)

    # ===== 用戶新格式: 主題_YYYYMMDD_券商 (主題在前) =====
    m = re.match(r"^(.+?)_(\d{8})_([一-鿿A-Za-z]+)$", name)
    if m:
        topic, ymd, brk_raw = m.groups()
        # 排除「YYYYMMDD_xxx_xxx」誤匹配 (topic 是 8 位數)
        # 年份防呆: 不合理 (非 2000-2030) → 視為 typo, 拒絕 (檔案進待處理)
        yr = int(ymd[:4])
        if not re.match(r"^\d{8}$", topic) and 2000 <= yr <= 2030:
            brk = detect_broker(brk_raw) or brk_raw
            cat = classify_topic_text(topic + " " + name)
            return _meta(cat, date=f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                         broker=brk, topic=topic.strip())

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

    # 沒 date 但有 broker → 用今天 fallback
    if not date and broker:
        date = datetime.now().strftime("%Y-%m-%d")
        topic = clean_topic(name, date, broker)
        cat = classify_topic_text(topic + " " + name)
        return _meta(cat, date=date, broker=broker, topic=topic)

    # 最終 fallback: 有意義主題但完全沒券商沒日期 → 「未知」+ today
    # 排除純亂碼 (純 hash / GUID / 純數字)
    is_garbage = (
        bool(re.match(r"^[A-F0-9\-{}]{16,}$", name, re.IGNORECASE))  # GUID / hex hash
        or bool(re.match(r"^[A-Za-z0-9]{30,}$", name))  # Google Drive ID 等長串
        or bool(re.match(r"^\d{10,}", name))  # 開頭 10+ 位純數字
    )
    if not is_garbage and len(name) >= 5:
        date = date or datetime.now().strftime("%Y-%m-%d")
        topic = clean_topic(name, date, "")
        cat = classify_topic_text(topic + " " + name)
        return _meta(cat, date=date, broker="未知", topic=topic)

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
    # strip [作者A,作者B] (analysts 已被 extract_analysts 取走，topic 不留)
    topic = re.sub(r"\[[^\[\]]+\]", "", topic)
    # strip 中國研報頁數標記跟尾巴隨機碼殘留
    topic = re.sub(r"【\d+\s*[页頁]】", "", topic)
    topic = re.sub(r"\s+[A-Za-z]{2}\d{2}\s*$", "", topic)  # 尾巴 _fA35 殘留
    topic = re.sub(r"[_\-\s]+", " ", topic).strip(" _-—")
    return topic or "report"


def sanitize_for_filename(text: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:60] or "report"


def extract_analysts(original_name: str) -> list:
    """從原始檔名抽出 [作者A,作者B] 名字 (中國研報常見)"""
    if not original_name:
        return []
    m = re.search(r"\[([^\[\]]{2,40})\]", original_name)
    if not m:
        return []
    raw = m.group(1)
    parts = [n.strip() for n in re.split(r"[,，、;；/]", raw) if n.strip()]
    # 過濾掉非人名 (例: 數字、空字串、頁碼)
    return [n for n in parts if not n.isdigit() and len(n) >= 2 and len(n) <= 8]


def _append_analysts(base_name: str, ext: str, analysts: list) -> str:
    """把 _[作者] 附加到檔名 ext 之前。一個檔名最多放 3 個作者避免太長"""
    if not analysts:
        return base_name
    sel = analysts[:3]
    return base_name.replace(ext, f"_[{','.join(sel)}]{ext}", 1)


def standardized_name(meta: dict, ext: str = ".pdf", original_name: str = "") -> str:
    # 簡 → 繁
    for k in ("topic", "stock_name", "broker"):
        if meta.get(k):
            meta[k] = to_traditional(meta[k])
    ymd = meta["date"].replace("-", "")
    analysts = meta.get("analysts") or extract_analysts(original_name)

    def _build():
        # 統一規則:
        #   有股號  : {股號}_{日期}_{券商}
        #   有 ticker: {ticker}_{市場}_{日期}_{券商}
        #   無代號  : {主題}_{日期}_{券商}    ← 主題在前
        if meta["category"] == "外資報告":
            if meta.get("stock_code"):
                return f"{meta['stock_code']}_{ymd}_{meta['broker']}{ext}"
            if meta.get("ticker"):
                mkt = meta.get("market") or "US"
                return f"{meta['ticker']}_{mkt}_{ymd}_{meta['broker']}{ext}"
            topic = sanitize_for_filename(meta.get("topic") or "report")
            return f"{topic}_{ymd}_{meta['broker']}{ext}"
        if meta["category"] == "個股":
            return f"{meta['stock_code']}_{ymd}_{meta['broker']}{ext}"
        if meta["category"] == "海外個股":
            ticker = meta.get("ticker") or meta.get("stock_code")
            if not ticker or ticker == "X":
                topic = sanitize_for_filename(meta.get("topic") or meta.get("stock_name") or "report")
                return f"{topic}_{ymd}_{meta['broker']}{ext}"
            market = meta.get("market") or "US"
            return f"{ticker}_{market}_{ymd}_{meta['broker']}{ext}"
        if meta["category"] == "Memo":
            return f"{meta['stock_code']}_{ymd}_memo{ext}"
        # 其他類別（產業/總經/策略/Fallback）
        topic = sanitize_for_filename(meta.get("topic") or "report")
        return f"{topic}_{ymd}_{meta['broker']}{ext}"

    base = _append_analysts(_build(), ext, analysts)
    # 保留原檔名「_long / _short / _full / _summary / _v\d+」版本標記
    if original_name:
        vm = re.search(r"_(long|short|full|summary|brief|flash|update|v\d+)(?:\.[a-z]+)?$",
                       original_name, re.IGNORECASE)
        if vm and vm.group(1).lower() not in base.lower():
            base = base.replace(ext, f"_{vm.group(1).lower()}{ext}")
    return base


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
    """掃根目錄 + 待處理目錄 + 所有 年份\類別\ 下的檔案"""
    accepted = {".pdf", ".md", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".txt", ".zip"}
    files = []
    # 根目錄
    for f in ROOT.iterdir():
        if f.is_file() and f.suffix.lower() in accepted and not is_reserved(f):
            files.append(f)
    # 待處理 (user 可能直接上傳到這)
    if PENDING_DIR.exists():
        for f in PENDING_DIR.iterdir():
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


def convert_office_files_in_root():
    """根目錄掃到 .pptx/.docx/.xlsx → 轉 PDF (原檔保留)"""
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        import convert_office
    except ImportError:
        return 0
    if not convert_office.is_available():
        return 0
    converted = 0
    for f in ROOT.iterdir():
        if not f.is_file() or f.suffix.lower() not in convert_office.OFFICE_EXTS:
            continue
        # 若同名 .pdf 已存在就 skip
        pdf_existing = f.with_suffix(".pdf")
        if pdf_existing.exists():
            continue
        result = convert_office.convert_to_pdf(f)
        if result:
            print(f"  [轉 PDF] {f.name} → {result.name}")
            converted += 1
    return converted


def organize():
    moved, pending, skipped = 0, 0, 0
    PENDING_DIR.mkdir(exist_ok=True)
    learned = 0
    # 整理前先把 Office 檔案轉成 PDF (原檔留著)
    converted = convert_office_files_in_root()
    if converted:
        print(f"  ({converted} 份 Office 檔已轉 PDF)")
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
        # 中國大陸 broker → 個股 → 大陸個股 / 產業 → 大陸產業 (Memo 不動)
        if meta["broker"] in CHINA_BROKERS and meta["category"] != "Memo":
            if meta["category"] == "個股":
                meta["category"] = "大陸個股"
            else:
                meta["category"] = "大陸產業"
        year = meta["date"][:4]
        target_dir = ROOT / year / meta["category"]
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            naive_target = target_dir / standardized_name(meta, pdf.suffix.lower(), pdf.name)
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
    save_analysts_cache(ANALYSTS_CACHE)


def _report_date_ok(cand: str, uploaded_at: str, category: str) -> bool:
    """報告日期 sanity guard:
    - 不晚於歸檔日+7 (擋內文除權息/財測未來日期)
    - 個股不早於 2021 (擋公司沿革歷史年份; 大陸/外資深度報告允許真舊)"""
    try:
        y, m, d = map(int, uploaded_at.split("-"))
        limit = (datetime(y, m, d) + timedelta(days=7)).strftime("%Y-%m-%d")
        if cand > limit:
            return False
    except Exception:
        pass
    if cand < "2021-01-01" and "大陸" not in category and "外資" not in category:
        return False
    return True


def build_entry(pdf: Path, category: str, year: str) -> dict:
    meta = parse_filename(pdf.name) or {}
    meta = enrich_meta(meta, pdf.name)
    date = meta.get("date") or guess_date_from_year(year, pdf.name)
    broker = meta.get("broker", "")
    stock_code = meta.get("stock_code", "")
    stock_name = meta.get("stock_name", "") or STOCK_NAMES.get(stock_code, "")
    topic = meta.get("topic", "")
    market = meta.get("market", "")
    # 中國大陸券商 → 個股 → 大陸個股 / 產業 → 大陸產業
    if broker in CHINA_BROKERS:
        if category == "個股":
            category = "大陸個股"
        elif category in ("產業", "大陸報告"):
            category = "大陸產業"

    if category == "海外個股":
        ticker = meta.get("ticker") or stock_code
        # X 是 placeholder 不該顯示
        if ticker == "X":
            ticker = ""
        rid = f"{ticker}_{market}_{date.replace('-', '')}_{broker}" if (ticker and date) else pdf.stem
        display_subject = f"{ticker} {stock_name}".strip() if ticker else (stock_name or topic or pdf.stem)
    elif category == "個股":
        rid = f"{stock_code}_{date.replace('-', '')}_{broker}" if (stock_code and date) else pdf.stem
        display_subject = f"{stock_code} {stock_name}".strip() if stock_code else pdf.stem
    else:
        rid = pdf.stem
        # 對「無股號」類別 (產業、外資報告 無 stock_code 等)，
        # 若 topic 太短 (< 6 字) → 後面會用 PDF metadata title 補
        display_subject = topic or pdf.stem

    rel_pdf = pdf.relative_to(ROOT).as_posix()
    href = "../" + "/".join(quote(part) for part in rel_pdf.split("/"))
    # 抽研究員 + 目標價 + PDF metadata title + 內文股號/報告日期
    fname_analysts = extract_analysts(pdf.name)
    pdf_meta = get_pdf_metadata(pdf)
    pdf_analysts = pdf_meta["analysts"]
    pdf_title = pdf_meta.get("pdf_title", "")
    # broker 是「未知」就用 PDF 內文偵測的外資 broker 補位
    detected_broker = pdf_meta.get("detected_broker", "")
    if detected_broker and broker in ("", "未知"):
        broker = detected_broker
        if category in ("個股", "產業"):
            category = "外資報告"
    # 內文抽出的股號/股名 — 若跟檔名不一致以內文為準
    # (僅限本土個股；外資/大陸個股檔名格式特殊，避免誤判)
    pdf_stock_id = pdf_meta.get("stock_id") or {}
    if pdf_stock_id and category == "個股":
        pdf_code = pdf_stock_id.get("stock_code", "")
        pdf_name = pdf_stock_id.get("stock_name", "")
        # 內文股號跟檔名不同 → 信任 PDF (檔名常打錯)
        if pdf_code and pdf_code != stock_code:
            stock_code = pdf_code
            stock_name = pdf_name or STOCK_NAMES.get(pdf_code, "") or stock_name
            # rid / display_subject 也要重算 (檔名歸檔仍 keep, rid 用內文值)
            rid = f"{stock_code}_{date.replace('-', '')}_{broker}" if (stock_code and date) else pdf.stem
            display_subject = f"{stock_code} {stock_name}".strip()
    # 內文抽出的報告日期 — 若有則以內文為準 (檔名日期通常是歸檔日)
    pdf_date = pdf_meta.get("report_date", "")
    if pdf_date:
        date = pdf_date
    # 對無股號類別用 PDF metadata title 取代醜 display_subject
    # 但 if 檔名 topic 已夠豐富 (中文 ≥ 3 字 或英文長度 ≥ 12)，**保留檔名**
    # 避免「2026年下半年投資展望會-傳統產業」變「PowerPoint 簡報」這種雜訊覆蓋
    cn_count = len([c for c in (display_subject or "") if "一" <= c <= "鿿"])
    topic_has_content = cn_count >= 3 or len(display_subject or "") >= 12
    # PDF metadata 雜訊 title (Office 轉 PDF 預設值)
    junk_titles = {"powerpoint 簡報", "viewpoint", "japan stock market",
                   "presentation", "microsoft word", "幻燈片", "投影片"}
    if (pdf_title
        and not stock_code
        and category in ("產業", "外資報告", "海外個股")
        and not topic_has_content
        and pdf_title.lower() not in junk_titles):
        display_subject = pdf_title[:100]
    # 策略類/總經類通常是多股週報，抽到的 target 多為雜訊不對應 row 主題 → skip
    skip_target_cats = {"策略與定期刊物", "總經"}
    target = {} if category in skip_target_cats else pdf_meta["target_price"]
    # 本土券商只顯示中文研究員 (避免 email 推回的「Iris Wang」跟「王美珍」並列重複)
    if not is_foreign_broker(broker):
        zh_pdf = [a for a in pdf_analysts if re.search(r"[一-鿿]", a)]
        # 若有中文名就只用中文；沒中文 (全英文 broker) 才保留英文
        if zh_pdf:
            pdf_analysts = zh_pdf
    # 合併去重 (保留順序: 檔名來源優先)
    analysts = list(dict.fromkeys(fname_analysts + pdf_analysts))
    body_excerpt = pdf_meta.get("body_excerpt", "")
    search_bits = [pdf.stem, date, category, stock_code, stock_name, topic, broker, pdf.name] + analysts
    # search_text 拼欄位 + PDF 內文摘錄；內文截到 800 字避免 report-index.js 爆肥
    # （內文佔整體大小 ~95%，截了仍保留前文重要關鍵字可搜尋）
    body_for_search = body_excerpt[:800] if body_excerpt else ""
    search_text = (" ".join(s for s in search_bits if s) + " " + body_for_search).lower()
    # 上傳/同步日期 (本機 mtime)
    try:
        uploaded_at = datetime.fromtimestamp(pdf.stat().st_mtime).strftime("%Y-%m-%d")
    except Exception:
        uploaded_at = date

    return {
        "id": rid,
        "date": date,
        "uploaded_at": uploaded_at,
        "analysts": analysts,
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
        "target_price_raw": target.get("raw", ""),
        "target_price_currency": target.get("currency", ""),
        "target_price_sort_value": target.get("value", 0),
        "target_price_status": "",
        "has_target_price": bool(target.get("value", 0)),
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
    """掃所有 年份/類別/ 下 stem_(N) 重複版。
    策略 (強制 dedupe)：
      - 同 base 的所有版本 (原版 + _(N))，留 size 最大那份 (內容最完整)
      - 其他全刪 (即使 size 差很多)
      - 若留下的是 _(N)，rename 回原名
    """
    import re as _re
    removed = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not _re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            # 收集 same-base 群組
            groups = {}  # base_full_name → [(n, file)]
            for f in cat_dir.iterdir():
                if not f.is_file():
                    continue
                m = _re.match(r"^(.+)_\((\d+)\)$", f.stem)
                if m:
                    base = f"{m.group(1)}{f.suffix}"
                    n = int(m.group(2))
                else:
                    base = f.name
                    n = 0
                groups.setdefault(base, []).append((n, f))
            for base, members in groups.items():
                if len(members) <= 1:
                    continue
                # 留 size 最大那個 (內容最完整)
                members_sized = [(n, f, f.stat().st_size) for n, f in members]
                members_sized.sort(key=lambda t: -t[2])
                keeper_n, keeper, keeper_size = members_sized[0]
                for n, f, sz in members_sized[1:]:
                    if not f.exists():
                        continue
                    print(f"  [強制刪重複] {f.relative_to(ROOT)} ({sz}B, 留較大 {keeper.name} {keeper_size}B)")
                    f.unlink()
                    removed += 1
                # 若 keeper 是 _(N) 後綴，rename 回 base 名
                if keeper_n > 0:
                    new_path = keeper.parent / base
                    if not new_path.exists():
                        print(f"  [還原檔名] {keeper.name} → {new_path.name}")
                        keeper.rename(new_path)
    return removed


def dedupe_size_close() -> int:
    """同類別內 size 差 ≤ 5 bytes 的兩份視為同檔 (PDF 元資料時間戳差異)，刪較舊那個"""
    import re as _re
    removed = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not _re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            files = [f for f in cat_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"]
            files.sort(key=lambda f: f.stat().st_size)
            for i in range(len(files) - 1):
                if not files[i].exists():
                    continue
                a, b = files[i], files[i + 1]
                if not b.exists():
                    continue
                if abs(a.stat().st_size - b.stat().st_size) <= 5:
                    # 刪檔名較長那個 (通常是補述版本)
                    victim = a if len(a.name) > len(b.name) else b
                    keeper = b if victim is a else a
                    print(f"  [刪近似] {victim.relative_to(ROOT)} (size 差 ≤5B, 留 {keeper.name})")
                    victim.unlink()
                    removed += 1
    return removed


def dedupe_office_residue() -> int:
    """PPT/Word 轉 PDF 後若原 docx/pptx/xlsx 還在 → 刪原檔"""
    import re as _re
    removed = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not _re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            stems = {f.stem: f for f in cat_dir.iterdir() if f.is_file() and f.suffix.lower() == ".pdf"}
            for f in list(cat_dir.iterdir()):
                if not f.is_file():
                    continue
                if f.suffix.lower() in (".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"):
                    if f.stem in stems:
                        print(f"  [刪 Office 殘留] {f.relative_to(ROOT)} (已轉 PDF)")
                        f.unlink()
                        removed += 1
    return removed


def dedupe_by_md5() -> int:
    """同類別內 size 完全相同 → 比 MD5 → 同 hash 刪一份 (保留檔名較短較整齊那份)"""
    import hashlib
    import re as _re
    removed = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not _re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            by_size = {}
            for f in cat_dir.iterdir():
                if not f.is_file():
                    continue
                by_size.setdefault(f.stat().st_size, []).append(f)
            for size, files in by_size.items():
                if len(files) <= 1:
                    continue
                by_md5 = {}
                for f in files:
                    try:
                        h = hashlib.md5(f.read_bytes()).hexdigest()
                    except Exception:
                        continue
                    by_md5.setdefault(h, []).append(f)
                for h, dups in by_md5.items():
                    if len(dups) <= 1:
                        continue
                    # 保留檔名「較乾淨」那份: 非數字開頭優先、有意義詞優先、長度其次
                    def cleanness(f):
                        s = f.stem
                        starts_digit = bool(_re.match(r"^\d", s))
                        has_topic = bool(_re.search(r"[A-Za-z]{4,}|[一-鿿]{2,}", s))
                        return (starts_digit, not has_topic, -len(s))
                    dups.sort(key=cleanness)
                    keeper = dups[0]
                    for f in dups[1:]:
                        print(f"  [刪 MD5 重複] {f.relative_to(ROOT)} (= {keeper.name})")
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


def decrypt_pdfs_in_managed_dirs():
    """對加密 PDF 解密 + 損壞 PDF 修復 (玉山 RC4 加密 / LINE bot 截斷 → PDF.js 顯示 0 頁)"""
    try:
        import pikepdf
        import fitz
    except ImportError:
        return
    decrypted = 0
    repaired = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for pdf in cat_dir.iterdir():
                if pdf.suffix.lower() != ".pdf":
                    continue
                # 判斷狀態: 加密 / 損壞 / 正常
                enc = None
                broken = False
                try:
                    doc = fitz.open(str(pdf))
                    enc = doc.metadata.get("encryption") if doc.metadata else None
                    # 0 頁或開檔有結構錯誤 = 損壞
                    if len(doc) == 0:
                        broken = True
                    doc.close()
                except Exception:
                    broken = True
                # 截斷檢查: 尾部沒 %%EOF
                if not enc and not broken:
                    try:
                        with open(pdf, "rb") as f:
                            f.seek(-1024, 2)
                            if b"%%EOF" not in f.read():
                                broken = True
                    except Exception:
                        pass
                if not enc and not broken:
                    continue
                tmp = pdf.with_suffix(".pdf.dec.tmp")
                try:
                    with pikepdf.open(str(pdf)) as p:
                        p.save(str(tmp))
                    doc2 = fitz.open(str(tmp))
                    pages = len(doc2)
                    doc2.close()
                    if pages > 0:
                        tmp.replace(pdf)
                        if enc:
                            decrypted += 1
                        else:
                            repaired += 1
                    else:
                        tmp.unlink()
                except Exception:
                    if tmp.exists():
                        try: tmp.unlink()
                        except: pass
    if decrypted:
        print(f"  PDF: 解密 {decrypted} 份 (RC4/AES)")
    if repaired:
        print(f"  PDF: 修復 {repaired} 份 (損壞/截斷)")


def strip_pdf_actions_in_managed_dirs():
    """對 2025/26/類別/ 下的 PDF 移除 auto-print + JS (擋 Citi 等廠商強制列印)"""
    try:
        sys.path.insert(0, str(SCRIPTS_DIR))
        from strip_pdf_autoprint import strip_pdf_actions
    except ImportError:
        return
    stripped = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for pdf in cat_dir.iterdir():
                if pdf.is_file() and pdf.suffix.lower() == ".pdf":
                    if strip_pdf_actions(pdf):
                        stripped += 1
    if stripped:
        print(f"  PDF: 移除 auto-print {stripped} 份")


# 中國 PDF 網站浮水印 (檔名 + PDF 內視覺都要砍)
WATERMARK_STRINGS = [
    "【价值目录】", "【價值目錄】", "价值目录", "價值目錄",
    "valuelist.cn", "VALUELIST.CN", "www.valuelist.cn",
    "【洞见研报】", "【洞見研報】", "洞见研报", "洞見研報",
    "DJyanbao.com", "djyanbao.com", "DJYANBAO",
    "网整理", "網整理",
]
WATERMARK_CACHE_FILE = SCRIPTS_DIR / "watermark_stripped.json"


def strip_visual_watermarks():
    """從 PDF 內畫面移除已知浮水印 (用 PyMuPDF redaction 蓋白)"""
    try:
        import fitz
    except ImportError:
        return
    import json as _json
    # 記錄已處理過的 PDF (避免每次都重跑掃描)
    try:
        cache = _json.loads(WATERMARK_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    stripped = 0
    for year_dir in ROOT.iterdir():
        if not year_dir.is_dir() or not re.match(r"^20\d{2}$", year_dir.name):
            continue
        for cat_dir in year_dir.iterdir():
            if not cat_dir.is_dir():
                continue
            for pdf in cat_dir.iterdir():
                if not (pdf.is_file() and pdf.suffix.lower() == ".pdf"):
                    continue
                mtime = pdf.stat().st_mtime
                key = pdf.name
                if cache.get(key) == mtime:
                    continue
                try:
                    doc = fitz.open(str(pdf))
                except Exception:
                    continue
                modified = False
                for page in doc:
                    for pat in WATERMARK_STRINGS:
                        for r in page.search_for(pat):
                            r.x0 -= 3; r.y0 -= 3
                            r.x1 += 3; r.y1 += 3
                            page.add_redact_annot(r, fill=(1, 1, 1))
                            modified = True
                    if modified:
                        try:
                            page.apply_redactions()
                        except Exception:
                            pass
                if modified:
                    try:
                        tmp = pdf.with_suffix(".pdf.tmp")
                        doc.save(str(tmp), garbage=4, deflate=True)
                        doc.close()
                        tmp.replace(pdf)
                        stripped += 1
                        cache[key] = pdf.stat().st_mtime
                    except Exception:
                        doc.close()
                else:
                    doc.close()
                    cache[key] = mtime
    try:
        WATERMARK_CACHE_FILE.write_text(_json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    if stripped:
        print(f"  PDF: 移除浮水印 {stripped} 份")


def ensure_pdfjs_patched():
    """保證 PDF.js viewer 的 enableScripting 是 false (擋 PDF auto-print)"""
    try:
        patch_module = SCRIPTS_DIR / "patch_pdfjs.py"
        if patch_module.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("patch_pdfjs", patch_module)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            ok, msg = mod.patch()
            print(f"  PDF.js: {msg}")
    except Exception as e:
        print(f"  (PDF.js patch 跳過: {e})")


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
    removed += dedupe_by_md5()
    removed += dedupe_size_close()
    removed += dedupe_office_residue()
    print(f"  完成: 刪除 {removed} 份重複\n")
    print("[3/4] 整理孤立 _(N) → 原名...")
    fixed = fix_orphan_duplicates()
    print(f"  完成: 整理 {fixed} 份\n")
    print("[4/4] 重建索引...")
    build_index()
    decrypt_pdfs_in_managed_dirs()
    strip_pdf_actions_in_managed_dirs()
    strip_visual_watermarks()
    ensure_pdfjs_patched()
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
