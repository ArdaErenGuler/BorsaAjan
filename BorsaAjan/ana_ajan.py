import json
import os
import time
import random
import requests
import pandas as pd
import yfinance as yf
import feedparser
from google import genai
from datetime import datetime

print("\n🦅 BorsaAjanı Başlatılıyor...")

# ==========================================
# 1. AYARLARI YÜKLE
# ==========================================
try:
    with open("ayarlar.json", "r", encoding="utf-8") as f:
        AYARLAR = json.load(f)
except FileNotFoundError:
    print("❌ HATA: ayarlar.json dosyası bulunamadı!")
    exit()

API_KEY = AYARLAR["GOOGLE_API_KEY"]
TG_TOKEN = AYARLAR["TG_TOKEN"]
TG_CHAT_ID = AYARLAR["TG_CHAT_ID"]
STRATEJI = AYARLAR["STRATEJI"]

try:
    client = genai.Client(api_key=API_KEY)
except Exception as e:
    print(f"❌ Gemini AI Bağlantı Hatası: {e}")
    exit()

HISSELER = [
    "AEFES.IS", "AGHOL.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKFGY.IS", "AKFYE.IS", "AKSA.IS", "AKSEN.IS", "ALARK.IS",
    "ALBRK.IS", "ALFAS.IS", "ARCLK.IS", "ASELS.IS", "ASTOR.IS", "ASUZU.IS", "BERA.IS", "BIENY.IS", "BIMAS.IS", "BIOEN.IS",
    "BOBET.IS", "BRSAN.IS", "BRYAT.IS", "BUCIM.IS", "CANTE.IS", "CCOLA.IS", "CIMSA.IS", "CWENE.IS", "DOAS.IS", "DOHOL.IS",
    "ECILC.IS", "ECZYT.IS", "EGEEN.IS", "EKGYO.IS", "ENJSA.IS", "ENKAI.IS", "EREGL.IS", "EUPWR.IS", "EUREN.IS", "FROTO.IS",
    "GARAN.IS", "GENIL.IS", "GESAN.IS", "GLYHO.IS", "GUBRF.IS", "GWIND.IS", "HALKB.IS", "HEKTS.IS", "IMASM.IS", "INVEO.IS",
    "ISCTR.IS", "ISDMR.IS", "ISGYO.IS", "ISMEN.IS", "IZENR.IS", "KALES.IS", "KCHOL.IS", "KMPUR.IS", "KONTR.IS", "KONYA.IS",
     "KRDMD.IS", "KZBGY.IS", "MAVI.IS", "MGROS.IS", "MIATK.IS", "ODAS.IS", "OTKAR.IS", "OYAKC.IS",
    "PENTA.IS", "PETKM.IS", "PGSUS.IS", "PNLSN.IS", "QUAGR.IS", "SAHOL.IS", "SASA.IS", "SDTTR.IS", "SISE.IS", "SKBNK.IS",
    "SMRTG.IS", "SOKM.IS", "TABGD.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TOASO.IS", "TSKB.IS", "TTKOM.IS",
    "TTRAK.IS", "TUKAS.IS", "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS", "YKBNK.IS", "YYLGD.IS",
    "ZOREN.IS"
]

SINYAL_GECMISI = []

# ==========================================
# 2. FONKSİYONLAR
# ==========================================

def portfoy_yukle():
    if os.path.exists("portfoy.json"):
        with open("portfoy.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def portfoy_kaydet(portfoy):
    with open("portfoy.json", "w", encoding="utf-8") as f:
        json.dump(portfoy, f, indent=4, ensure_ascii=False)
        
def telegram_sinyal_gonder(veri, ai_yorumu, haberler):
    mesaj = f"""🚀 *YENİ FIRSAT SİNYALİ* 🚀
-----------------------------------
🏢 *Hisse:* #{veri['sembol'].replace('.IS', '')}
💰 *Anlık Fiyat:* {veri['fiyat']:.2f} TL
📊 *Teknik:* RSI: {veri['rsi']:.1f} | F/K: {veri['fk']:.1f} | ROE: %{veri['roe']*100:.1f}
-----------------------------------
🤖 *GEMINI AI KARARI:*
{ai_yorumu}

📰 *SON HABERLER:*
{haberler}
-----------------------------------
📱 _Midas'ı kontrol etmeyi unutma!_"""

    try:
        yanit = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                              json={"chat_id": TG_CHAT_ID, "text": mesaj})
        
        if yanit.status_code != 200:
            print(f"⚠️ Telegram API Hatası: {yanit.text}")
        else:
            print("📲 Telegram alım mesajı başarıyla uçuruldu!")

    except Exception as e:
        print(f"Telegram Bağlantı Hatası: {e}")

# --- YENİ EKLENEN: SATIŞ MESAJI FONKSİYONU ---
def telegram_satis_gonder(veri, alis_fiyati, ai_yorumu):
    kar_zarar_yuzdesi = ((veri['fiyat'] - alis_fiyati) / alis_fiyati) * 100
    isaret = "🟢 KÂR" if kar_zarar_yuzdesi > 0 else "🔴 ZARAR KES"
    
    mesaj = f"""🚨 *SATIŞ SİNYALİ* 🚨
-----------------------------------
🏢 *Hisse:* #{veri['sembol'].replace('.IS', '')}
📉 *Alış Fiyatı:* {alis_fiyati:.2f} TL
📈 *Güncel Fiyat:* {veri['fiyat']:.2f} TL
📊 *Durum:* {isaret} (%{kar_zarar_yuzdesi:.2f})
-----------------------------------
🤖 *GEMINI AI KARARI:*
{ai_yorumu}
-----------------------------------
📱 _Pozisyonu kapatmayı değerlendir!_"""

    try:
        yanit = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                              json={"chat_id": TG_CHAT_ID, "text": mesaj})
        if yanit.status_code != 200:
            print(f"⚠️ Telegram API Hatası: {yanit.text}")
        else:
            print("📲 Telegram satış mesajı başarıyla uçuruldu!")
    except Exception as e:
        print(f"Telegram Satış Mesajı Hatası: {e}")
# ---------------------------------------------

def teknik_veri_cek(sembol):
    try:
        hisse = yf.Ticker(sembol)
        df = hisse.history(period="1mo", interval="1d")
        if df.empty: return None

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).ewm(com=13, min_periods=14).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(com=13, min_periods=14).mean()
        rsi = 100 - (100 / (1 + (gain / loss)))

        info = hisse.info
        fk = info.get('trailingPE', 999.0)
        pddd = info.get('priceToBook', 999.0)
        roe = info.get('returnOnEquity', 0.0)

        return {
            "sembol": sembol,
            "fiyat": df['Close'].iloc[-1],
            "rsi": rsi.iloc[-1],
            "fk": fk,
            "pddd": pddd,
            "roe": roe
        }
    except Exception as e:
        print(f"Veri Çekme Hatası ({sembol}): {e}")
        return None

def haberleri_bul(sembol):
    try:
        saf_isim = sembol.split('.')[0]
        url = f"https://news.google.com/rss/search?q={saf_isim}+hisse+kap&hl=tr-TR&gl=TR&ceid=TR:tr"
        feed = feedparser.parse(url)
        if not feed.entries: return "Önemli bir haber bulunamadı."
        return "\n".join([f"- {h.title}" for h in feed.entries[:2]])
    except:
        return "Haber servisi okunamadı."

def ai_onayi_al(veri, haberler):
    prompt = f"""Sen usta, net ve kısa konuşan bir Borsa İstanbul analistisin. 
    Hisse: {veri['sembol']}
    Veriler: Fiyat {veri['fiyat']} TL | F/K: {veri['fk']:.2f} | RSI: {veri['rsi']:.1f} | ROE: %{veri['roe']*100:.1f}
    Son Haberler: {haberler}
    
    Görev: Bu verileri analiz et. Almak mantıklıysa ve risk yoksa 'KARAR: ONAY' yaz.
    ONAY verirsen, NEDEN almamız gerektiğini 3 kısa maddeyle (Teknik, Temel, Haber) çok net açıkla.
    Eğer riskliyse 'KARAR: RET' yaz ve tek cümleyle neden reddettiğini söyle."""
    
    deneme = 0
    while deneme < 3:
        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            cevap = response.text.strip()
            if "ONAY" in cevap.upper():
                return True, cevap
            return False, cevap
        except Exception as e:
            hata_mesaji = str(e)
            if "429" in hata_mesaji or "RESOURCE_EXHAUSTED" in hata_mesaji:
                deneme += 1
                print(f"⏳ Google API Limiti! {veri['sembol']} için 60sn bekleniyor... (Deneme: {deneme}/3)")
                time.sleep(60)
            else:
                return False, f"AI bağlantı hatası: {e}"
                
    return False, "❌ Google API limiti aşılamadı (3 kez denendi). Bu tur pas geçiliyor."

# --- YENİ EKLENEN: AI SATIŞ ONAYI FONKSİYONU ---
def ai_satis_onayi_al(veri, alis_fiyati):
    kar_zarar = ((veri['fiyat'] - alis_fiyati) / alis_fiyati) * 100
    prompt = f"""Sen usta bir borsa analistisin. 
    Hisse: {veri['sembol']}
    Alış Fiyatımız: {alis_fiyati} TL | Güncel Fiyat: {veri['fiyat']} TL | Kâr/Zarar: %{kar_zarar:.2f}
    Güncel RSI: {veri['rsi']:.1f}
    
    Görev: Bu hisseyi elimizde tutuyoruz. Sence artık satmalı mıyız?
    Eğer satmak (kâr almak veya zararı kesmek) mantıklıysa 'KARAR: SAT' yaz ve nedenini 2 kısa maddeyle açıkla.
    Eğer tutmaya devam etmeliysek 'KARAR: TUT' yaz."""
    
    deneme = 0
    while deneme < 3:
        try:
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            cevap = response.text.strip()
            if "SAT" in cevap.upper():
                return True, cevap
            return False, cevap
        except Exception as e:
            hata_mesaji = str(e)
            if "429" in hata_mesaji or "RESOURCE_EXHAUSTED" in hata_mesaji:
                deneme += 1
                print(f"⏳ Google API Limiti! {veri['sembol']} satış onayı için 60sn bekleniyor... (Deneme: {deneme}/3)")
                time.sleep(60)
            else:
                return False, f"AI bağlantı hatası: {e}"
                
    return False, "❌ Google API limiti aşılamadı (3 kez denendi). Pas geçiliyor."
# -----------------------------------------------

# ==========================================
# 3. ANA MOTOR DÖNGÜSÜ
# ==========================================
print("✅ Sistem Hazır! Piyasayı dinlemeye başlıyorum...\n")

while True:
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Yeni Tarama Döngüsü Başladı...")
    
    # --- YENİ EKLENEN KISIM: SATIŞ KONTROLÜ ---
    portfoy = portfoy_yukle()
    if portfoy:
        print("💼 Önce elde tutulan hisseler kontrol ediliyor...")
        satilacaklar = []
        
        for p_sembol, p_detay in portfoy.items():
            guncel_veri = teknik_veri_cek(p_sembol)
            if guncel_veri:
                print(f"🔍 Portföydeki {p_sembol} analiz ediliyor...")
                satis_onayi, satis_yorumu = ai_satis_onayi_al(guncel_veri, p_detay["alis_fiyati"])
                if satis_onayi:
                    print(f"🚨 AI SATIŞ ONAYI VERDİ! Telegram'a gönderiliyor: {p_sembol}")
                    telegram_satis_gonder(guncel_veri, p_detay["alis_fiyati"], satis_yorumu)
                    satilacaklar.append(p_sembol)
                else:
                    print(f"🛡️ AI Tut Dedi ({p_sembol})")
            time.sleep(2) # AI'yi yormamak için kısa bir mola
            
        # Satılanları portföyden sil ve kaydet
        for satilan in satilacaklar:
            del portfoy[satilan]
        if satilacaklar:
            portfoy_kaydet(portfoy)
    # -------------------------------------------

    print("\n🔍 Yeni fırsatlar için tarama başlıyor...")
    tur_firsat_sayisi = 0
    
    for sembol in HISSELER:
        if datetime.now().hour == 0 and len(SINYAL_GECMISI) > 0:
            SINYAL_GECMISI.clear()

        veri = teknik_veri_cek(sembol)
        
        if veri:
            if veri['rsi'] >= STRATEJI['RSI_AL_LIMIT'] or veri['fk'] >= STRATEJI['MAX_FK'] or veri['roe'] <= STRATEJI['MIN_ROE']:
                print(f"📉 Elendi: {sembol} (RSI: {veri['rsi']:.1f}, F/K: {veri['fk']:.1f}, ROE: %{veri['roe']*100:.1f})")
                time.sleep(1)
                continue

            print(f"⚡ Fırsat Adayı: {sembol} (RSI: {veri['rsi']:.1f}) -> AI inceliyor...")
            
            if sembol in SINYAL_GECMISI:
                print(f"⏭️ {sembol} bugün zaten gönderildi, atlanıyor.")
                continue

            haberler = haberleri_bul(sembol)
            onay, yorum = ai_onayi_al(veri, haberler)
            
            if onay:
                print(f"✅ AI ONAYLADI! Telegram'a gönderiliyor: {sembol}")
                print(f"🧠 AI'ın Sebebi:\n{yorum}\n")
                telegram_sinyal_gonder(veri, yorum, haberler)
                SINYAL_GECMISI.append(sembol)
                tur_firsat_sayisi += 1
                
                # Portföye ekle
                portfoy = portfoy_yukle()
                if sembol not in portfoy:
                    portfoy[sembol] = {
                        "alis_fiyati": float(veri['fiyat']),
                        "tarih": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    portfoy_kaydet(portfoy)
                    print(f"💼 {sembol} portföye kaydedildi.")
                
            else:
                print(f"❌ AI Reddetti ({sembol}): {yorum[:60]}...")

        time.sleep(5) 

    if tur_firsat_sayisi == 0:
        print(f"\n📉 Tarama Bitti: Yeni fırsat bulunamadı.")
    else:
        print(f"\n🎯 Tarama Bitti: {tur_firsat_sayisi} adet sinyal gönderildi!")
        
    print(f"💤 5 dakika bekleniyor...\n")
    time.sleep(300)