#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
二手 iPhone 16 行情看板 — 資料抓取
輸出 data.json（給 build.py 產生網頁）

來源：
  1. 露天市集   rtapi.ruten.com.tw  搜尋 API + 商品明細 API
  2. Smart3C    SHOPLINE 商店頁（伺服器端渲染，可直接解析）
  3. 保衛站      SHOPLINE 商店頁
  4. SOGI 手機王  行情基準（門市最低 / 二手均價，依機型＋容量）

設計原則：
  - 任何單一來源失敗不影響其他來源，只記在 errors。
  - 若總筆數異常少（可能是對方改版），不覆寫舊資料，直接以非零狀態結束。
"""

import json
import re
import sys
import time
import datetime as dt
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data.json"
TPE = dt.timezone(dt.timedelta(hours=8))

# ── 想追蹤別的世代時，改這一區就好 ───────────────────────────────
GEN = "16"                       # 機型世代
GEN_LABEL = "iPhone 16"
PRICE_MIN, PRICE_MAX = 8000, 60000
RUTEN_QUERIES = [
    "二手 iPhone 16", "二手 iPhone 16 Pro", "二手 iPhone 16 Pro Max",
    "二手 iPhone 16 Plus", "二手 iPhone 16e", "中古 iPhone 16",
    "iPhone 16 二手機", "福利品 iPhone 16",
]
VARIANTS = ["iPhone 16", "iPhone 16 Plus", "iPhone 16 Pro",
            "iPhone 16 Pro Max", "iPhone 16e"]
# ──────────────────────────────────────────────────────────────

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept": "application/json, text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
})

MIN_ITEMS = 5          # 低於這個數量視為抓取異常，不覆寫

ACCESSORY = re.compile(
    r"(保護殼|保護貼|鋼化|玻璃貼|手機殼|皮套|背蓋|支架|傳輸線|充電線|充電器|快充|轉接|"
    r"鏡頭貼|掛繩|收納|模型|空盒|包裝盒|卡針|卡托|自拍|耳機|行動電源|磁吸|指環|貼紙|"
    r"按鍵|氣囊|貼膜|鏡頭蓋|手機架|繞線|數據線|SIM)", re.I)
# 零件機、鎖機、故障機 — 這些不是可正常使用的二手機
JUNK = re.compile(
    r"(零件機|ID有鎖|ID鎖|iCloud鎖|有鎖|鎖機|無法開機|不能正常使用|故障|報廢|泡水|"
    r"螢幕破|面板破|拆機|殺肉)", re.I)
NOISE = re.compile(r"(可免|高價回收|回收中古|舊機折抵|門號折抵|信用卡分期|現金分期|萊分期|以舊換新|收購)")
NOT_A_PHONE = re.compile(r"(預購|摺疊|Duo)", re.I)

MODEL_RE = re.compile(r"(?:iphone|apple|蘋果|愛鳳|\bi)\s*([0-9]{1,2})\s*(pro\s*max|promax|pm|pro|plus|air|e)?", re.I)
CAP_RE = re.compile(r"(128|256|512|1024|2048)\s*(?:GB|G)\b", re.I)
TB_RE = re.compile(r"([12])\s*TB", re.I)
BATT_RE = re.compile(r"(?:電池健康度?|健康度|電池效能|電池|電力|電)\s*[:：]?\s*(\d{2,3})\s*%")
BATT_RE2 = re.compile(r"(\d{2,3})\s*%\s*(?:電池|電力|電)")
COND_RE = re.compile(r"([0-9](?:\.[0-9])?)\s*成\s*([0-9])?\s*新")
# 「128G/256G/512G」「參考 14 15 128G 512G 1TB」這類一頁多規格的賣場，
# 抓不出單一價格對應的規格，整筆略過。
VARIANT_TOKEN = re.compile(rf"({GEN}\s*e|{GEN}\s*pro\s*max|{GEN}\s*promax|{GEN}\s*pro|{GEN}\s*plus)", re.I)


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def too_ambiguous(head: str) -> bool:
    caps = set(m.group(1) for m in CAP_RE.finditer(head)) | set(
        m.group(1) + "TB" for m in TB_RE.finditer(head))
    if len(caps) >= 3:
        return True
    toks = set(re.sub(r"\s+", "", m.group(1)).lower() for m in VARIANT_TOKEN.finditer(head))
    return len(toks) >= 3


def classify(title: str):
    """從標題判斷是不是本世代機型，回傳機型名稱或 None。"""
    head = NOISE.split(title)[0]
    if too_ambiguous(head):
        return None
    m = MODEL_RE.search(head)
    if not m or m.group(1) != GEN:
        return None
    sfx = (m.group(2) or "").lower().replace(" ", "")
    if sfx in ("promax", "pm"):
        v = f"{GEN_LABEL} Pro Max"
    elif sfx == "pro":
        v = f"{GEN_LABEL} Pro"
    elif sfx == "plus":
        v = f"{GEN_LABEL} Plus"
    elif sfx == "e":
        v = f"{GEN_LABEL}e"
    else:
        v = GEN_LABEL
    if v == GEN_LABEL:
        low = head.lower()
        if re.search(rf"pro\s*max|promax|{GEN}pm", low):
            v = f"{GEN_LABEL} Pro Max"
        elif re.search(r"\bpro\b", low):
            v = f"{GEN_LABEL} Pro"
        elif re.search(r"\bplus\b", low):
            v = f"{GEN_LABEL} Plus"
        elif f"{GEN}e" in low:
            v = f"{GEN_LABEL}e"
    return v if v in VARIANTS else None


def capacity(title: str):
    head = NOISE.split(title)[0]
    m = TB_RE.search(head)
    if m:
        return f"{m.group(1)}TB"
    m = CAP_RE.search(head)
    if not m:
        return None
    g = m.group(1)
    return {"1024": "1TB", "2048": "2TB"}.get(g, g + "GB")


def battery(text: str):
    m = BATT_RE.search(text) or BATT_RE2.search(text)
    if m and 50 <= int(m.group(1)) <= 100:
        return int(m.group(1))
    return None


def condition(text: str):
    m = COND_RE.search(text)
    if m:
        return (f"{m.group(1)}.{m.group(2)}" if m.group(2) else m.group(1)) + "成新"
    for pat, label in (
        (r"全新未拆|全新未使用", "全新未拆"),
        (r"近全新|幾乎全新|極新", "近全新"),
        (r"福利品|福利機", "福利品"),
        (r"展示機", "展示機"),
        (r"機況(?:漂亮|良好|不錯)", "機況良好"),
    ):
        if re.search(pat, text):
            return label
    return None


# --------------------------------------------------------------- 露天市集
RUTEN_USED_PHONE_CATE = "002100010047"   # 二手手機 / Apple


def ruten_search_ids(pages=2, per=100):
    ids, seen = [], set()
    for q in RUTEN_QUERIES:
        for p in range(pages):
            url = ("https://rtapi.ruten.com.tw/api/search/v3/index.php/core/prod"
                   f"?q={quote(q)}&type=direct&sort=prc%2Fac&offset={p*per+1}&limit={per}")
            r = SESSION.get(url, timeout=30)
            r.raise_for_status()
            rows = (r.json() or {}).get("Rows") or []
            for row in rows:
                i = row.get("Id")
                if i and i not in seen:
                    seen.add(i)
                    ids.append(i)
            if len(rows) < per:
                break
            time.sleep(0.3)
    return ids


def ruten_details(ids, chunk=30):
    out = []
    for i in range(0, len(ids), chunk):
        batch = ",".join(ids[i:i + chunk])
        url = f"https://rtapi.ruten.com.tw/api/prod/v2/index.php/prod?id={batch}"
        r = SESSION.get(url, timeout=30, headers={"Referer": "https://www.ruten.com.tw/"})
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            out.extend(data)
        time.sleep(0.3)
    return out


def scrape_ruten():
    raw = ruten_details(ruten_search_ids())
    items = []
    for x in raw:
        title = norm_ws(x.get("ProdName"))
        if not title or ACCESSORY.search(title) or JUNK.search(title) or NOT_A_PHONE.search(title):
            continue
        if not str(x.get("CateId") or "").startswith(RUTEN_USED_PHONE_CATE):
            continue
        if int(x.get("StockQty") or 0) <= 0:
            continue
        pr = x.get("PriceRange") or [0]
        price = int(pr[0] or 0)
        if not (PRICE_MIN <= price <= PRICE_MAX):
            continue
        v = classify(title)
        if not v:
            continue
        img = x.get("Image") or ""
        if img and not img.startswith("http"):
            img = "https://gcs.rimg.com.tw" + img
        img = re.sub(r"_m\.(jpg|png|webp)$", r"_b.\1", img, flags=re.I)
        items.append({
            "t": title[:60],
            "p": price,
            "v": v,
            "c": capacity(title),
            "b": battery(title),
            "g": condition(title),
            "i": img,
            "u": f"https://www.ruten.com.tw/item/show?{x.get('ProdId')}",
            "s": "",
            "src": "露天市集",
        })
    return items


# --------------------------------------------------------------- SHOPLINE 商店
def scrape_shopline(url, source_name, origin):
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for a in soup.select("a[ga-product]"):
        try:
            ga = json.loads(a.get("ga-product") or "{}")
        except Exception:
            ga = {}
        title = norm_ws(ga.get("title") or a.get_text(" "))
        if not title:
            continue
        if ACCESSORY.search(title) or JUNK.search(title) or NOT_A_PHONE.search(title):
            continue
        v = classify(title)
        if not v:
            continue

        card, node = None, a
        for _ in range(5):
            node = node.parent
            if node is None:
                break
            if "NT$" in node.get_text(" "):
                card = node
                break
        text = card.get_text(" ") if card else a.get_text(" ")
        prices = [int(m.replace(",", "")) for m in re.findall(r"NT\$\s?([\d,]+)", text)]
        prices = [p for p in prices if PRICE_MIN <= p <= PRICE_MAX]
        if not prices:
            continue

        img = ""
        img_tag = (card or a).find("img")
        if img_tag:
            ss = img_tag.get("data-srcset") or img_tag.get("srcset") or ""
            img = ss.split(",")[0].strip().split(" ")[0] if ss else (
                img_tag.get("data-src") or img_tag.get("src") or "")
        if img.startswith("//"):
            img = "https:" + img

        grades = []
        try:
            for var in json.loads(ga.get("variations") or "[]"):
                zh = (var.get("fields_translations") or {}).get("zh-hant") or []
                if zh:
                    grades.append(zh[0])
        except Exception:
            pass

        href = a.get("href") or ""
        if href and not href.startswith("http"):
            href = origin.rstrip("/") + "/" + href.lstrip("/")

        items.append({
            "t": title[:60],
            "p": min(prices),
            "v": v,
            "c": capacity(title),
            "b": battery(text),
            "g": (grades[0] if grades else None) or condition(title),
            "i": img,
            "u": href,
            "s": source_name,
            "src": source_name,
        })
    return items


# --------------------------------------------------------------- SOGI 行情基準
SOGI_URL = "https://www.sogi.com.tw/brands/Apple/116"
SOGI_ROW = re.compile(
    r"Apple\s+(iPhone[^$]{0,26}?)\s*門市最低\s*\$?([\d,]+|-)\s*二手價\s*\$?([\d,]+|-)")


def scrape_sogi():
    """回傳 {機型: {容量或 "*": {used, retail}}}。SOGI 對部分機型會分容量列出。"""
    r = SESSION.get(SOGI_URL, timeout=30)
    r.raise_for_status()
    text = re.sub(r"\s+", " ", BeautifulSoup(r.text, "html.parser").get_text(" "))
    out = {}
    for m in SOGI_ROW.finditer(text):
        name = norm_ws(m.group(1))
        cap = capacity(name) or "*"
        base = re.sub(r"\s*(128|256|512|1024)\s*GB\s*$", "", name, flags=re.I)
        base = re.sub(r"\s*[12]\s*TB\s*$", "", base, flags=re.I).strip()
        if base.lower() not in [v.lower() for v in VARIANTS]:
            continue
        key = next(v for v in VARIANTS if v.lower() == base.lower())
        store = None if m.group(2) == "-" else int(m.group(2).replace(",", ""))
        used = None if m.group(3) == "-" else int(m.group(3).replace(",", ""))
        out.setdefault(key, {})[cap] = {"used": used, "retail": store}
    return out


# --------------------------------------------------------------- main
def main():
    errors, items = [], []

    for name, fn in (
        ("露天市集", scrape_ruten),
        ("Smart3C", lambda: scrape_shopline(
            "https://www.smart3c.com.tw/zh-hant/categories/"
            "%E3%80%90apple--%E8%98%8B%E6%9E%9C%E3%80%91",
            "Smart3C", "https://www.smart3c.com.tw")),
        ("保衛站", lambda: scrape_shopline(
            "https://www.guardstation.com.tw/pages/used-apple",
            "保衛站", "https://www.guardstation.com.tw")),
    ):
        try:
            got = fn()
            items.extend(got)
            print(f"[ok] {name}: {len(got)} 件", flush=True)
        except Exception as e:
            errors.append(f"{name}: {e}")
            print(f"[fail] {name}: {e}", file=sys.stderr, flush=True)

    benchmarks = {}
    try:
        benchmarks = scrape_sogi()
        print(f"[ok] SOGI 行情: {len(benchmarks)} 個機型", flush=True)
    except Exception as e:
        errors.append(f"SOGI: {e}")
        print(f"[fail] SOGI: {e}", file=sys.stderr, flush=True)

    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: x["p"]):
        key = (it["v"], it["c"], it["p"], it["s"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    if len(uniq) < MIN_ITEMS:
        print(f"只抓到 {len(uniq)} 件，低於安全下限 {MIN_ITEMS}，不覆寫 data.json。", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        sys.exit(1)

    # 沿用舊的行情基準，避免 SOGI 當天失敗就整欄消失
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            merged = dict(old.get("benchmarks") or {})
            for k, v in benchmarks.items():
                merged.setdefault(k, {}).update(v)
            benchmarks = merged
        except Exception:
            pass

    payload = {
        "updated": dt.datetime.now(TPE).isoformat(timespec="seconds"),
        "benchmarks": benchmarks,
        "items": uniq,
        "errors": errors,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"寫入 {OUT.name}：{len(uniq)} 件，最低 ${uniq[0]['p']:,}", flush=True)


if __name__ == "__main__":
    main()
