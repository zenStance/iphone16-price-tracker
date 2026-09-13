# 二手 iPhone 16 行情看板

每天自動抓取臺灣二手平台的 iPhone 16 系列售價，產生一頁卡片式看板，依價格由低到高排序。
整套跑在 GitHub 的伺服器上 — **不需要開電腦，也不需要任何付費服務**。

網站網址（設定完成後）：`https://<你的帳號>.github.io/<repo 名稱>/`

## 資料來源

| 來源 | 取得方式 | 提供欄位 |
|---|---|---|
| 露天市集 | 官方搜尋 / 商品 API | 照片、容量、價格、賣場連結；電池與成色視賣家標示 |
| Smart3C | 商店分類頁 | 照片、容量、價格、福利品等級 |
| 保衛站 Guard Station | 二手 Apple 頁 | 照片、容量、價格、外觀評等 |
| SOGI 手機王 | 品牌總覽頁 | 各機型／各容量的「門市最低」與「二手均價」，用來算「低於行情 %」 |

蝦皮購物沒有納入：其搜尋 API 需登入且有反爬蟲偵測，不做繞過。

## 一次性設定（約 10 分鐘）

1. 在 GitHub 建立一個新的 repository（Public 即可；Private 也能用 Pages，但需要付費方案）。
2. 把這個資料夾裡的所有檔案上傳到 repo 根目錄（可用網頁版的 **Add file → Upload files**，把 `.github`、`docs` 兩個資料夾一起拖進去）。
3. 進入 repo 的 **Settings → Pages**，「Source」選 **GitHub Actions**。
4. 進入 **Settings → Actions → General**，最下面的「Workflow permissions」選 **Read and write permissions**，存檔。
5. 進入 **Actions** 分頁，點左邊「每日更新二手 iPhone 16 行情」，右上角按 **Run workflow** 手動跑第一次。
6. 跑完後開 `https://<你的帳號>.github.io/<repo 名稱>/` 就看得到網站了。

之後每天台北時間凌晨 3 點會自動執行一次。
（GitHub 的排程在尖峰時段可能延遲幾分鐘到十幾分鐘，屬正常現象。）

## 每天實際發生的事

1. `scrape.py` 重新抓四個來源 → 覆寫 `data.json`
2. `build.py` 把 `data.json` 塞回 `template.html` → 產生 `docs/index.html`
3. Actions 自動 commit 並部署到 GitHub Pages

**已下架 / 售出的商品會自動消失**：`items` 每天整份重建，只放這次抓得到、而且庫存仍大於 0 的賣場。

## 安全機制

- 任何單一來源掛掉，其他來源照常更新，錯誤訊息會記在 Actions 的 log 裡。
- 如果總筆數少於 5 件（通常代表對方網站改版、解析失效），腳本會直接失敗並**保留舊資料**，不會把看板洗成空白。
- SOGI 行情基準當天抓不到時，沿用前一天的數值。

## 想調整的地方

| 想改什麼 | 改哪裡 |
|---|---|
| 執行時間 | `.github/workflows/daily.yml` 的 `cron`（UTC 時間，台北時間減 8 小時） |
| 追蹤別的機型 | `scrape.py` 最上方的「想追蹤別的世代時，改這一區就好」：`GEN`、`GEN_LABEL`、`VARIANTS`、`RUTEN_QUERIES`、價格範圍 |
| 價格篩選範圍 | 同上區塊的 `PRICE_MIN` / `PRICE_MAX` |
| 版面、顏色、欄位 | `template.html`（只有 `const DATA = {...};` 那段會被每日覆寫，其餘不會被動到） |
| 新增來源 | `scrape.py` 照 `scrape_shopline()` 的樣子再寫一個函式，加進 `main()` 的來源清單 |

## 本機測試

```bash
pip install requests beautifulsoup4
python scrape.py     # 產生 data.json
python build.py      # 產生 docs/index.html
open docs/index.html
```
