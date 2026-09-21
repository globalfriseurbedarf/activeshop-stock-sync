# ActiveShop -> Shopify Stock Sync (Local CSV Fallback)

Kod once ActiveShop stok feedini internetten indirmeyi dener.

Indirme Cloudflare/401/403 nedeniyle basarisiz olursa repository kokundeki `b2b-de.csv` dosyasini kullanir.

## GitHub dosya yapisi

```text
activeshop-stock-sync/
├─ .github/
│  └─ workflows/
│     └─ stock-sync.yml
├─ b2b-de.csv           <-- Opera VPN ile indirdigin guncel dosyayi BURAYA koy
├─ README.md
├─ requirements.txt
└─ stock_sync.py
```

ActiveShop feedi GitHubdan bloklu kaldigi surece stoklar `b2b-de.csv` dosyasindaki snapshot kadar guncel olur. Opera VPN ile yeni dosya indirdiginde GitHubdaki ayni `b2b-de.csv` dosyasini yenisiyle degistir.

Online feed tekrar calismaya baslarsa kod otomatik olarak online dosyayi kullanir; yerel dosyaya gecmez.
