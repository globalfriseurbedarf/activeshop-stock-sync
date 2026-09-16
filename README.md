# ActiveShop -> Shopify Stok Senkronizasyonu

Bu proje ActiveShop CSV feed dosyasini indirir ve Shopify stoklarini SKU eslesmesine gore gunceller.

## Dogru depo

Stoklar su Shopify lokasyonuna yazilir:

```txt
Lager in Wroclaw
Location ID: 119279812950
```

Workflow icinde su ayar vardir:

```yaml
SHOPIFY_LOCATION_ID: "119279812950"
ZERO_OTHER_LOCATIONS: "true"
```

Bu ayar sayesinde stoklar sadece Lager in Wroclaw deposunda tutulur. Diger lokasyonlarda kalan stoklar 0 yapilir.

## GitHub Secret

Repository icinde su alana gir:

```txt
Settings > Secrets and variables > Actions > New repository secret
```

Eklemen gereken secret:

```txt
Name: SHOPIFY_ACCESS_TOKEN
Value: shpat_xxxxxxxxxxxxxxxxx
```

## Otomatik calisma

Workflow 15 dakikada bir calisir:

```yaml
cron: "*/15 * * * *"
```

Manuel calistirmak icin:

```txt
Actions > ActiveShop Shopify Stock Sync > Run workflow
```

## Test modu

Gercek guncelleme acik:

```yaml
DRY_RUN: "false"
```

Sadece test yapmak icin:

```yaml
DRY_RUN: "true"
```
