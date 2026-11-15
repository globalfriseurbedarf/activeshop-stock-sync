# ActiveShop CSV -> Shopify Stok Sync | Tum SKU (Limitsiz)

**Stok kaynagi**: repo kokundeki **`b2b-de.csv`**; `qty` / G sutunu. Tum CSV SKU'lari kontrol edilir; kodda **300 urun siniri yoktur**. Shopify sayfalari `limit=250` istegi ile **tum sayfalar** gezilerek indirilir; bu 250, toplam SKU siniri degildir.

### Kurulum / guncelleme

1. ZIP'i **acip** dosyalari Shopify stok reposuna, ayni klasor yapisiyla yukleyin (`.github/workflows/stock-sync.yml`, `stock_sync.py`, `b2b-de.csv`, `tests/`).
2. Yeni ActiveShop feedi indirdiginizde **`b2b-de.csv`** adiyla repo kokundeki dosyayi degistirin. Dosyanin diger alanlari degismeden kalir; kod sadece `sku` ve `qty` okur.
3. Github `Actions > ActiveShop CSV + Shopify Stock Sync > Run workflow` ile tek bir tam stok senkronu calistirin; mevcut otomatik calisma **15 dakikada bir** devam eder.
4. GitHub secret **`SHOPIFY_ACCESS_TOKEN`** korunur. Magaza `bzjwyw-jv.myshopify.com`, Shopify API `2026-04`, lokasyon `119279812950` eskisi gibidir.

### Neler degismedi?

- `ZERO_OTHER_LOCATIONS=true`: diger lokasyonlardaki stoklari mevcut davranis gibi 0'a ceker.
- `SET_MISSING_SKU_TO_ZERO=false`: CSV'de olmayan Shopify SKU'larinin stoklarini **0 yapmaz**.
- Shopify'da SKU olmayan urunler atlanir. Ayni stokta gereksiz guncelleme yapilmaz. `DRY_RUN`, rate-limit bekleme ve `stock_sync_report.csv` raporu korunur.
- Online feed erisim sorunu varsa stok programi CSV dosyasiyla calisir.

### CSV onceligi ve istege bagli otomatik indirme

- **Varsayilan** `FEED_SOURCE_MODE=local_first`: GitHub'a manuel yuklediginiz guncel CSV **her zaman onceliklidir**. Dosya mevcutsa internetten yanlis/eski feed ile degistirilmez. Yerel CSV eksikse online feed denenir. Bozuk yerel CSV sessizce atlanmaz, yazma baslamadan hata verir.
- Eski online-oncelikli davranisi isterseniz kodun veya ortamin `FEED_SOURCE_MODE` degerini `online_first` yapabilirsiniz.
- Otomatik feed indirip GitHub'a commit etme adimi silinmedi, fakat manuel dosyayi ezmemek icin **varsayilan kapali**. GitHub Actions variable `AUTO_REFRESH_CSV=true` ile eskisi gibi gunde 2 defa (ve manuel calistirmada) yeniden acilir.

**Guvenlik:** Satir sayisi yeni dosyada daha az olabilir; mevcut `SET_MISSING_SKU_TO_ZERO=false` davranisi bunu korur. Eski dosyalarin yerini duzgun sekilde degistirdiginizi kontrol edin. Shopify'a gercek stok yazimi sadece GitHub Action calistiginda olur.

### Offline test

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
```
