# 🦅 BorsaAjan - Yarı Otonom Borsa Analiz ve Trade Botu

BorsaAjan, BİST 100 hisselerini belirlediğiniz stratejilere göre tarayan, teknik/temel analizlerini yapan ve **Google Gemini AI** kullanarak alım-satım kararları veren otonom bir Python botudur. Kararlarını Telegram üzerinden anlık olarak bildirir ve kendi sanal portföyünü yönetir.

## 🌟 Özellikler
* **Algoritmik Tarama:** `yfinance` üzerinden hisselerin RSI, F/K, P/D D/D ve ROE verilerini çekerek ön filtreleme yapar.
* **Yapay Zeka Karar Mekanizması:** Filtreden geçen hisseler ve güncel KAP/Haber verileri **Gemini 2.5 Flash** modeline sunulur. AI, riskleri analiz ederek nihai "AL" veya "RED" kararını verir.
* **Otonom Portföy Yönetimi:** Alınan hisseler sisteme kaydedilir. Sonraki döngülerde kâr/zarar durumu hesaplanarak AI'a "SAT" veya "TUT" onayı sorulur.
* **Telegram Entegrasyonu:** Alış ve Satış sinyalleri, AI'ın detaylı gerekçeleriyle birlikte anlık olarak Telegram'a gönderilir.

## 🛠️ Kullanılan Teknolojiler
* **Dil:** Python
* **Kütüphaneler:** `yfinance`, `pandas`, `requests`, `feedparser`
* **Yapay Zeka:** Google GenAI API (Gemini 2.5 Flash)
* **Bildirim:** Telegram Bot API

## 🚀 Kurulum
1. Gerekli kütüphaneleri yükleyin.
2. `ayarlar.json` dosyanızı oluşturup API anahtarlarınızı girin.
3. `python ana_ajan.py` komutuyla botu başlatın.

---
*Not: Bu proje eğitim ve araştırma amaçlıdır. Kesinlikle yatırım tavsiyesi içermez.*
