# ActiveShop -> Plenty Fiyat Senkronu V11

Bu repository ActiveShop B2B fiyatlarini PlentyONE ile otomatik senkronize eder.

## Ne yapar?

- ActiveShop net B2B fiyatini okur.
- Plenty `purchasePrice` alanini ActiveShop net fiyatina esitler.
- Plenty satis fiyatini su formulle hesaplar:

  `ActiveShop net fiyat x 1.25 x 1.19`

  Yani varsayilan olarak **%25 kar + %19 KDV**.
- Plenty satis fiyati icin varsayilan ID: **8**.
- Mevcut satis fiyati hedef fiyatla ayniysa tekrar yazmaz (`sales=NO_CHANGE`).
- Stok guncellemez (`UPDATE_STOCK=false`).
- ActiveShop rate limit olursa bekler ve ayni SKU'yu tekrar dener.
- ActiveShop token girisinde Cloudflare `HTTP 403 / Just a moment` gelirse 20/40/80/120 saniyelik artan bekleme ile toplam 5 deneme yapar.
- Cloudflare 403 kaliciysa uzun HTML yerine kisa ve anlasilir hata mesaji verir.
- Normal calismada en fazla 300 urun isler ve progress dosyasi sayesinde kaldigi yerden devam eder.
- Tum urunler bittiginde sonraki otomatik calisma yeni tura baslar.
- GitHub Actions otomatik olarak gunde 6 kez calisir.
- `Run workflow` ekraninda SKU girilirse **yalnizca o tek SKU** islenir ve normal progress ilerlemez.
- SKU alani bos birakilirsa normal 300 urunluk senkron calisir.

## Ornek fiyatlar

- ActiveShop net `15.32 EUR` -> Plenty satis `22.79 EUR`
- ActiveShop net `266.97 EUR` -> Plenty satis `397.12 EUR`

## GitHub'a yukleme

ZIP'i acin ve klasorun **icindeki tum dosyalari repository kokune** yukleyin. `.github` klasorunun da yuklendiginden emin olun.

Repository yapisi:

```text
.github/workflows/price-sync.yml
input/Global Fiyat Guncelleme.csv
output/.gitkeep
state/.gitkeep
tests/test_price_logic.py
.gitignore
README.md
requirements.txt
run_sync.py
sync_activeshop_to_plenty.py
```

Bu paketteki `input/Global Fiyat Guncelleme.csv`, bu sohbette yuklenen son fiyat senkron artifact'indan yeniden olusturuldu ve **3517 SKU** icerir.

## GitHub Secrets

GitHub repository icinde:

`Settings -> Secrets and variables -> Actions -> Secrets`

su secret'lari ekleyin:

| Secret | Aciklama |
|---|---|
| `ACTIVESHOP_USERNAME` | ActiveShop API/B2B kullanici adi |
| `ACTIVESHOP_PASSWORD` | ActiveShop sifresi |
| `PLENTY_BASE_URL` | Plenty sistem URL'si |
| `PLENTY_USERNAME` | Plenty API kullanicisi |
| `PLENTY_PASSWORD` | Plenty API sifresi |
| `ACTIVESHOP_PROXY_URL` | Opsiyonel; proxy yoksa eklemeyin |

Sifreleri veya tokenlari kod dosyalarina yazmayin.

## GitHub Repository Variables

`Settings -> Secrets and variables -> Actions -> Variables`

su degerleri ekleyin:

| Variable | Deger |
|---|---:|
| `PLENTY_ENABLE_WRITE` | `true` |
| `UPDATE_PURCHASE_PRICE` | `true` |
| `UPDATE_SALES_PRICE` | `true` |
| `PLENTY_SALES_PRICE_ID` | `8` |

Opsiyonel ayarlar:

| Variable | Varsayilan |
|---|---:|
| `SALES_PRICE_PROFIT_RATE` | `0.25` |
| `SALES_PRICE_VAT_RATE` | `0.19` |
| `SALES_PRICE_ADD` | `0.0` |
| `PURCHASE_PRICE_MULTIPLIER` | `1.0` |
| `PURCHASE_PRICE_ADD` | `0.0` |

## Once tek urun test edin

GitHub'da:

`Actions -> ActiveShop to Plenty PRICE Sync V11 -> Run workflow`

`Test SKU` alanina ornegin `122764` yazin.

Bu durumda:

- sadece bu SKU islenir;
- `PLENTY_ENABLE_WRITE=true` ise gercek fiyat guncellemesi yapilir;
- normal `state/price_sync_progress.json` ilerlemez;
- sonuc `output/test_sku_result.json` artifact'ina yazilir;
- logda eski ve hedef alis/satis fiyatlari gorunur.

`Test SKU` alanini bos birakirsaniz normal senkron calisir.

## Otomatik calisma

Workflow cron:

```text
41 1,5,9,13,17,21 * * *
```

GitHub cron UTC kullanir. Turkiye saatiyle yaklasik **04:41, 08:41, 12:41, 16:41, 20:41 ve 00:41** calisir.

Her normal calismada en fazla 300 SKU islenir.

## Log anlami

Ornek:

```text
ActiveShop=15.32 EUR |
Plenty EK eski=15.32 EUR |
Plenty EK hedef=15.32 EUR |
Plenty VK eski=22.79 EUR |
Plenty VK hedef=22.79 EUR |
purchase=NO_CHANGE |
sales=NO_CHANGE |
stock=DISABLED
```

- `purchase=UPDATED`: Plenty alis fiyati degisti.
- `purchase=NO_CHANGE`: alis fiyati zaten dogru.
- `sales=UPDATED`: Plenty satis fiyati guncellendi.
- `sales=NO_CHANGE`: satis fiyati zaten dogru; gereksiz API yazmasi yapilmadi.
- `stock=DISABLED`: bu workflow stok guncellemez.

## Guvenli ilk kurulum

Canli yazma acilmadan once isterseniz:

`PLENTY_ENABLE_WRITE=false`

ile DRY RUN yapabilirsiniz. Kontrol tamamlaninca tekrar `true` yapin.

## V11 Cloudflare korumasi

GitHub-hosted runner IP'leri bazen ActiveShop onundeki Cloudflare tarafindan gecici olarak challenge'a alinabilir. V11 token girisinde bunu algilar ve ayni workflow icinde otomatik tekrar dener. Varsayilanlar:

```text
ACTIVESHOP_LOGIN_RETRIES=4
ACTIVESHOP_LOGIN_BASE_WAIT=20
ACTIVESHOP_LOGIN_MAX_WAIT=120
```

Bu ayarlar toplam 5 token denemesi yapar. Cloudflare 403 tum denemelerde devam ederse workflow hata verir; bir sonraki zamanlanmis workflow GitHub tarafindan farkli bir runner/IP ile calisabilir.
