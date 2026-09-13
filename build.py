#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 data.json 塞進 template.html，輸出 docs/index.html（GitHub Pages 的網站根目錄）。"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data.json"
TPL = ROOT / "template.html"
OUT = ROOT / "docs" / "index.html"

data = json.loads(DATA.read_text(encoding="utf-8"))
data.pop("errors", None)          # 抓取錯誤只留在 log，不進網頁
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

html = TPL.read_text(encoding="utf-8")
new, n = re.subn(r"const DATA = \{[\s\S]*?\n\};", "const DATA = " + payload + ";", html, count=1)
if n != 1:
    raise SystemExit("在 template.html 找不到 `const DATA = {...};` 區塊，請確認樣板沒有被改壞。")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(new, encoding="utf-8")
print(f"已產生 {OUT.relative_to(ROOT)}：{len(data['items'])} 件商品")
