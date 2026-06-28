"""
從 PDF 內文抽取研究員名字。

策略 (按準確度排序):
  1. email 對應人名: angela.hc.hsu@citi.com → "Angela Hc Hsu"
  2. "XXX, CFA" / "XXX AC": 首席分析師標記
  3. 「分析師」「Analyst」「Research Associate」標籤後的人名

只掃 PDF 前 3 頁 (分析師通常在第 1 頁或封面)。
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


# 黑名單: 不是 analyst 名字
BLACKLIST = {
    "Investment Bank", "Research", "Equity", "Asia Pacific", "Customer Service",
    "Citi Research", "Morgan Stanley", "Goldman Sachs", "JP Morgan",
    "Investment Banking", "Compliance Office", "Compliance",
    "Important Disclosures", "Disclaimer",
}


def extract_from_text(text: str) -> list:
    """從 PDF 文字內容抽 analysts 名字"""
    found = []
    seen = set()

    def add(name: str):
        n = name.strip()
        # 過濾換行/tab/特殊字元
        if "\n" in n or "\t" in n:
            # 換行往往是 PDF 抽文字殘留，取 \n 後段
            n = n.split("\n")[-1].strip()
        if not n or n in seen or len(n) < 2 or len(n) > 40:
            return
        if n in BLACKLIST or any(b in n for b in BLACKLIST):
            return
        is_cjk = bool(re.search(r"[一-鿿]", n))
        if is_cjk:
            if len(n) > 4 or re.search(r"[A-Za-z0-9]", n):
                return
        else:
            # 英文姓名規則
            if n.isupper():
                return
            tokens = n.split()
            if len(tokens) < 2:
                return
            # 拒絕「縮寫太多」的：每個 token 都 < 3 字 (例: "Minhp Yjs")
            if all(len(t) <= 3 for t in tokens):
                return
            # 第一個 token 至少 3 字 (避免 "Hc Hsu" 開頭縮寫)
            if len(tokens[0]) < 3:
                return
            # 全部 token 都要含小寫
            if not all(re.search(r"[a-z]", t) for t in tokens):
                return
        seen.add(n)
        found.append(n)

    # 1. email 對應人名
    for email in re.findall(r"\b([a-z]+(?:[.\-_][a-z]+){1,4})@[\w.\-]+", text, re.IGNORECASE):
        parts = re.split(r"[.\-_]", email)
        if 2 <= len(parts) <= 4 and all(len(p) >= 2 for p in parts):
            name = " ".join(p.title() for p in parts)
            add(name)

    # 2. XXX, CFA / XXX, FRM / XXX, CPA
    for m in re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}),\s*(?:CFA|FRM|CPA)", text):
        add(m)

    # 3. AC (首席) 或 AC 上標
    for m in re.findall(r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*(?:AC|\^AC)", text):
        add(m)

    # 4. 「Analyst」「Research Associate」「分析師」標籤旁的人名
    label_re = r"(?:Equity\s+Analyst|Research\s+Analyst|Research\s+Associate|分析師|Analyst)"
    for m in re.findall(
        rf"\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})\s*\n[^\n]*\n?{label_re}",
        text,
    ):
        add(m)
    for m in re.findall(
        rf"{label_re}\s*\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})",
        text,
    ):
        add(m)

    # 5. 中文姓名: 「研究員：王小明 / 分析師：xxx」(合庫、富邦、元富、群益、統一等本土券商)
    for m in re.findall(
        r"(?:研究員|分析師|撰寫人|報告人|證券分析師|產業分析師|策略分析師)[：:\s]+([一-鿿]{2,4})",
        text,
    ):
        add(m)

    # 6. 中文姓名直接接 email (中信等)
    # 例: 「李曉昀\nSusan.lee@ctbcsis.com」
    for m in re.findall(
        r"([一-鿿]{2,4})\s*[\n\r]+\s*[A-Za-z][\w.\-]*@[\w.\-]+",
        text,
    ):
        add(m)

    # 7. 中文姓名後跟電話/職稱再接 email (富邦等)
    # 例: 「楊惟婷\n886-2-27815995#37015\nweiting.yang@fubon.com」
    for m in re.findall(
        r"(?:\n|^)([一-鿿]{2,4})\s*\n(?:[^\n]{0,80}\n){1,3}\s*[\w.\-]+@[\w.\-]+",
        text,
    ):
        add(m)

    # Dedupe: 「Angela Hsu」是「Angela Hc Hsu」的 token subset → 保留長的
    final = []
    for n in sorted(found, key=lambda x: -len(x)):  # 長的優先
        tokens = set(n.lower().split())
        if any(tokens.issubset(set(m.lower().split())) and n != m for m in final):
            continue
        final.append(n)
    return final[:6]


def extract_from_pdf(pdf_path: Path, max_pages: int = 3) -> list:
    if not fitz:
        return []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return []
    text_pieces = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        try:
            text_pieces.append(page.get_text())
        except Exception:
            pass
    doc.close()
    return extract_from_text("\n".join(text_pieces))


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        analysts = extract_from_pdf(Path(target))
        print(f"{Path(target).name}: {analysts}")
    else:
        # 預設測 Citi 一份
        sample = Path(r"C:\Users\J.Chun\Dropbox\MEMO烏骨雞\2026\外資報告\1216_20260625_Citi.pdf")
        if sample.exists():
            print(f"{sample.name}: {extract_from_pdf(sample)}")
