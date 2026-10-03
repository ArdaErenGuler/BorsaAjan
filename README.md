# 🦅 BorsaAjan — Yarı Otonom Borsa Analiz ve Sinyal Botu

BorsaAjan, BİST hisselerini belirlediğiniz stratejiye göre tarayan, teknik ve temel
analizlerini yapan, kalan adayları **Google Gemini** ile değerlendiren bir Python
botudur. Kararlarını Telegram üzerinden bildirir ve sanal bir portföy tutar.

> **Bu bot yatırım tavsiyesi vermez.** Eğitim ve araştırma amaçlıdır. Ürettiği
> sinyaller otomatik analiz çıktısıdır; emir iletmez, para hareketi yapmaz.

## Nasıl çalışır

1. **Ön filtre** — Her hisse için 6 aylık günlük kapanıştan Wilder RSI hesaplanır;
   F/K, P/D-D/D ve ROE verileri `yfinance`'ten alınır. Eşikleri ihlal eden hisse
   elenir ve AI'a hiç sorulmaz. Eleme nedeni ekrana yazılır.
2. **AI değerlendirmesi** — Filtreden geçen hisse, son haber başlıklarıyla birlikte
   Gemini'ye sunulur. Model ilk satıra `KARAR: ONAY` veya `KARAR: RET` yazar.
3. **Sinyal** — ONAY alan hisse için Telegram'a mesaj gider ve hisse sanal portföye
   eklenir.
4. **Pozisyon takibi** — Sonraki turlarda eldeki hisseler kontrol edilir. Zarar kes
   ve kâr al eşikleri **AI'a sorulmadan** çalışır; aradaki durumlarda modele
   `KARAR: SAT` / `KARAR: TUT` sorulur.

## Kurulum

```bash
py -m pip install -r requirements.txt
```

Ardından ayar dosyasını oluşturun:

```bash
cp BorsaAjan/ayarlar.example.json BorsaAjan/ayarlar.json
```

`ayarlar.json` içine Gemini API anahtarınızı, Telegram bot token'ınızı ve chat
ID'nizi yazın. Bu dosya `.gitignore`'da — **asla commit edilmez.**

## Çalıştırma

```bash
py BorsaAjan/ana_ajan.py
```

Deneme ve geliştirme için bayraklar:

| Bayrak | Ne yapar |
| --- | --- |
| `--tek-tur` | Tek tarama turu çalışır ve çıkar |
| `--kuru` | Telegram'a mesaj **göndermez**, ekrana yazar |
| `--ai-yok` | Gemini'ye hiç sormaz — API kotası harcamaz, sadece filtreyi test eder |
| `--hisse N` | Listenin yalnızca ilk N hissesini tarar |
| `--saat-yok` | Piyasa saati kontrolünü atlar |

Filtreyi kota harcamadan denemek için:

```bash
py BorsaAjan/ana_ajan.py --tek-tur --kuru --ai-yok --saat-yok
```

## Testler

Ağ erişimi ve API anahtarı gerektirmez:

```bash
py BorsaAjan/test_ana_ajan.py
```

81 kontrol çalışır. Her test düzeltilmiş somut bir hatayı koruma altına alır —
biri kırmızı olursa o hata geri gelmiş demektir.

## Ayarlar

`ayarlar.example.json` içindeki `_not_*` alanları her bölümü açıklar. Öne çıkanlar:

| Ayar | Varsayılan | Neden önemli |
| --- | --- | --- |
| `STRATEJI.RSI_AL_LIMIT` | `45` | RSI bu değerin üstündeyse hisse elenir |
| `STRATEJI.MAX_FK` | `15.0` | F/K üst sınırı |
| `STRATEJI.MAX_PDDD` | `3.0` | P/D-D/D üst sınırı |
| `STRATEJI.MIN_ROE` | `0.15` | ROE alt sınırı (%15) |
| `MIN_FK` | `0.0` | Negatif F/K "ucuz" değildir, zarar demektir — eler |
| `EKSIK_TEMEL_VERI_ELENSIN` | `false` | Kaynaktan gelmeyen veri hisseyi elemesin |
| `GECMIS_PERIYODU` | `"6mo"` | RSI ısınması için `1mo` yetersizdir |
| `AI_MAX_ISTEK_TUR` | `15` | Tur başına Gemini isteği üst sınırı |
| `AI_MAX_ISTEK_GUN` | `200` | Günlük kota koruması |
| `PIYASA_SAATI_ZORUNLU` | `true` | Piyasa kapalıyken tarama yapılmaz |
| `ZARAR_KES_YUZDE` | `-8.0` | Mekanik zarar kes, AI'a sorulmaz |
| `KAR_AL_YUZDE` | `20.0` | Mekanik kâr al, AI'a sorulmaz |

## Üretilen dosyalar

Hepsi betiğin kendi klasöründe oluşur ve `.gitignore`'dadır:

| Dosya | İçerik |
| --- | --- |
| `portfoy.json` | Sanal portföy (hisse, alış fiyatı, tarih) |
| `durum.json` | Günlük sinyal geçmişi ve AI istek sayacı |
| `temel_onbellek.json` | F/K, P/D-D/D, ROE önbelleği (12 saat) |

## Kullanılan teknolojiler

* **Dil:** Python 3.9+
* **Kütüphaneler:** `yfinance`, `pandas`, `requests`, `feedparser`
* **Yapay zekâ:** Google GenAI (`google-genai`), Gemini 2.5 Flash
* **Bildirim:** Telegram Bot API

## Bilinen sınırlar

* Sanal portföy tutar; **gerçek emir iletmez.** Alım-satımı kendiniz yaparsınız.
* `yfinance` verisi gecikmeli olabilir ve bazı hisseler için temel veri hiç gelmez.
  Gelmeyen veri "bilinmiyor" olarak AI'a bildirilir, sessizce 0 sayılmaz.
* Gemini ücretsiz katmanı dakikada ve günde sınırlıdır. Bot sınırı kendi takip
  eder; dolduğunda tarama o tur için durur, süreç ölmez.
* **Temettü günü:** Hisse temettü dağıttığında fiyat temettü kadar düşer. Bot
  yalnızca fiyat değişimine baktığı için bu düşüş zarar gibi görünür ve
  `ZARAR_KES_YUZDE` eşiğini tetikleyebilir. Toplam getiri (fiyat + temettü)
  hesaplanmıyor; yüksek verimli hisselerde eşiği buna göre ayarlayın.
