# ActiveShop -> Shopify Stok Senkronizasyonu

Bu proje ActiveShop CSV feed dosyasini indirir ve Shopify'daki varyant stoklarini SKU eslesmesine gore gunceller.

## Dosyalar

- `stock_sync.py`: Ana Python kodu
- `requirements.txt`: Python paketleri
- `.github/workflows/stock-sync.yml`: GitHub Actions otomatik calisma dosyasi

## GitHub Secrets

Repository icinde su alana gir:

`Settings > Secrets and variables > Actions > New repository secret`

Eklemen gereken zorunlu secret:

```text
SHOPIFY_ACCESS_TOKEN
```

Opsiyonel secret:

```text
SHOPIFY_LOCATION_ID
```

Birden fazla Shopify lokasyonun varsa `SHOPIFY_LOCATION_ID` eklemen daha dogru olur.

## Ilk Test

Workflow dosyasinda ilk test icin bu sekilde birak:

```yaml
DRY_RUN: "true"
```

GitHub'da:

`Actions > ActiveShop Shopify Stock Sync > Run workflow`

Calistir.

Loglarda su alanlari kontrol et:

```text
Kullanilan ActiveShop SKU kolonu: sku
Kullanilan ActiveShop stok kolonu: qty
DRY_RUN_GUNCELLENECEK
```

## Gercek Guncelleme

Test basariliysa `.github/workflows/stock-sync.yml` icinde sunu:

```yaml
DRY_RUN: "true"
```

buna cevir:

```yaml
DRY_RUN: "false"
```

Sonra commit yap. Sistem 15 dakikada bir otomatik calisir.
