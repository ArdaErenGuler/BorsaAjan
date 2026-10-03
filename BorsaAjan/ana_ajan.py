"""BorsaAjan - Yari otonom BIST analiz ve sinyal botu.

Hisseleri teknik/temel verilere gore on filtreden gecirir, kalanlari Gemini'ye
sorar ve kararlari Telegram'a bildirir. Sanal portfoy tutar.

ONEMLI: Bu bot yatirim tavsiyesi vermez. Egitim ve arastirma amaclidir.

Kullanim:
    py ana_ajan.py                 # normal calisma
    py ana_ajan.py --tek-tur       # tek tur calis ve cik
    py ana_ajan.py --kuru          # Telegram'a mesaj GONDERME (deneme)
    py ana_ajan.py --ai-yok        # Gemini'ye hic sorma (kota harcamaz)
    py ana_ajan.py --hisse 10      # listenin sadece ilk 10 hissesini tara
    py ana_ajan.py --saat-yok      # piyasa saati kontrolunu atla
"""

import argparse
import html
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import feedparser
import requests
import yfinance as yf

try:  # Python 3.9+
    from zoneinfo import ZoneInfo

    BORSA_TZ = ZoneInfo("Europe/Istanbul")
except Exception:  # pragma: no cover - cok eski Python
    BORSA_TZ = None

# ==========================================================================
# SABITLER VE YOLLAR
# ==========================================================================

# Yollar betigin kendi klasorune gore cozulur. Boylece bot hangi dizinden
# baslatilirsa baslatilsin ayni ayar/portfoy dosyalarini kullanir.
KOK = Path(__file__).resolve().parent
AYAR_YOLU = KOK / "ayarlar.json"
PORTFOY_YOLU = KOK / "portfoy.json"
DURUM_YOLU = KOK / "durum.json"
ONBELLEK_YOLU = KOK / "temel_onbellek.json"

TELEGRAM_SINIR = 4096  # Bot API tek mesaj karakter siniri
AG_ZAMAN_ASIMI = 15  # saniye; her HTTP cagrisi icin

# Gemini cevabindan karari okumak icin. Alt dizi aramasi ("ONAY" in cevap)
# "onaylamiyorum" gibi kelimelerde yanlis pozitif verdigi icin kullanilmaz.
KARAR_DESENI = re.compile(
    r"KARAR\s*[:\-=]?\s*\**\s*(ONAY|RET|SAT|TUT)\b",
    re.IGNORECASE,
)

HISSELER = [
    "AEFES.IS", "AGHOL.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKFGY.IS", "AKFYE.IS",
    "AKSA.IS", "AKSEN.IS", "ALARK.IS", "ALBRK.IS", "ALFAS.IS", "ARCLK.IS", "ASELS.IS",
    "ASTOR.IS", "ASUZU.IS", "BERA.IS", "BIENY.IS", "BIMAS.IS", "BIOEN.IS", "BOBET.IS",
    "BRSAN.IS", "BRYAT.IS", "BUCIM.IS", "CANTE.IS", "CCOLA.IS", "CIMSA.IS", "CWENE.IS",
    "DOAS.IS", "DOHOL.IS", "ECILC.IS", "ECZYT.IS", "EGEEN.IS", "EKGYO.IS", "ENJSA.IS",
    "ENKAI.IS", "EREGL.IS", "EUPWR.IS", "EUREN.IS", "FROTO.IS", "GARAN.IS", "GENIL.IS",
    "GESAN.IS", "GLYHO.IS", "GUBRF.IS", "GWIND.IS", "HALKB.IS", "HEKTS.IS", "IMASM.IS",
    "INVEO.IS", "ISCTR.IS", "ISDMR.IS", "ISGYO.IS", "ISMEN.IS", "IZENR.IS", "KCHOL.IS",
    "KMPUR.IS", "KONTR.IS", "KONYA.IS", "KRDMD.IS", "KZBGY.IS", "MAVI.IS", "MGROS.IS",
    "MIATK.IS", "ODAS.IS", "OTKAR.IS", "OYAKC.IS", "PENTA.IS", "PETKM.IS", "PGSUS.IS",
    "PNLSN.IS", "QUAGR.IS", "SAHOL.IS", "SASA.IS", "SDTTR.IS", "SISE.IS", "SKBNK.IS",
    "SMRTG.IS", "SOKM.IS", "TABGD.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS", "TKFEN.IS",
    "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TTRAK.IS", "TUKAS.IS", "TUPRS.IS", "ULKER.IS",
    "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS", "YKBNK.IS", "YYLGD.IS", "ZOREN.IS",
    # KALES.IS listeden cikarildi: Yahoo Finance "Quote not found for symbol"
    # (HTTP 404) donduruyor, her turda bos istek harcaniyordu.
]

# ayarlar.json'da bulunmasi ZORUNLU anahtarlar
ZORUNLU_AYARLAR = ("GOOGLE_API_KEY", "TG_TOKEN", "TG_CHAT_ID", "STRATEJI")
ZORUNLU_STRATEJI = ("RSI_AL_LIMIT", "MAX_FK", "MAX_PDDD", "MIN_ROE")

# Opsiyonel ayarlar ve varsayilanlari
VARSAYILAN_AYARLAR = {
    "GECMIS_PERIYODU": "6mo",           # RSI isinmasi icin 1mo yetersiz
    "RSI_PERIYODU": 14,
    "MIN_FK": 0.0,                      # F/K bu degerin altindaysa elenir (zarar)
    "EKSIK_TEMEL_VERI_ELENSIN": False,  # temel veri yoksa hisse elenmesin
    "DONGU_BEKLEME_SN": 300,
    "HISSE_ARASI_BEKLEME_SN": 1.0,
    "PIYASA_SAATI_ZORUNLU": True,
    "PIYASA_ACILIS": "10:00",
    "PIYASA_KAPANIS": "18:10",
    "AI_MAX_ISTEK_TUR": 15,             # tur basina en fazla kac Gemini istegi
    "AI_MAX_ISTEK_GUN": 200,            # gunluk ust sinir (ucretsiz kota korumasi)
    "AI_DAKIKADA_ISTEK": 8,             # dakikada en fazla kac istek
    "TEMEL_ONBELLEK_SAAT": 12,          # temel veri kac saat onbellekte tutulsun
    "AI_MODEL": "gemini-2.5-flash",
    "PORTFOY_MAX_HISSE": 10,
    "ZARAR_KES_YUZDE": -8.0,            # bu seviyede AI'a sormadan satis sinyali
    "KAR_AL_YUZDE": 20.0,               # bu seviyede AI'a sormadan satis sinyali
}

UYARI_METNI = "Yatirim tavsiyesi degildir. Otomatik uretilmis analizdir."


# ==========================================================================
# KUCUK YARDIMCILAR
# ==========================================================================

def ciktiyi_utf8_yap():
    """Konsol ciktisini UTF-8'e cevirir.

    Windows'ta cikti bir dosyaya veya pipe'a yonlendirildiginde Python yerel
    kod sayfasini (Turkce kurulumda cp1254) kullanir ve mesajlardaki emoji
    UnicodeEncodeError ile botu ILK SATIRDA oldurur. Gorev Zamanlayici ya da
    "py ana_ajan.py > log.txt" ile calistirmak tam olarak bu durumdur.
    """
    for akis in (sys.stdout, sys.stderr):
        try:
            akis.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass  # cok eski Python veya yeniden yapilandirilamayan akis


def gunluk(mesaj):
    """Zaman damgali ekran cikti."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {mesaj}", flush=True)


def sayi(deger):
    """Gelen degeri float'a cevirir; cevrilemiyorsa None doner.

    yfinance info sozlugu bir alani hic gondermeyebilir, None gonderebilir ya da
    metin gonderebilir. dict.get(anahtar, varsayilan) yalnizca anahtar YOKSA
    varsayilani dondurur; anahtar varip degeri None ise None doner. Bu yuzden
    varsayilana guvenmek yerine her deger buradan gecirilir.
    """
    if deger is None:
        return None
    try:
        d = float(deger)
    except (TypeError, ValueError):
        return None
    if d != d or d in (float("inf"), float("-inf")):  # NaN / sonsuz
        return None
    return d


def json_oku(yol, varsayilan):
    """JSON dosyasini guvenli okur. Bozuksa yedekler ve varsayilani doner."""
    if not yol.exists():
        return varsayilan
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        bozuk = yol.with_suffix(yol.suffix + ".bozuk")
        try:
            os.replace(yol, bozuk)
            gunluk(f"⚠️ {yol.name} okunamadi ({e.__class__.__name__}). "
                   f"{bozuk.name} olarak kenara alindi, sifirdan baslaniyor.")
        except OSError:
            gunluk(f"⚠️ {yol.name} okunamadi ve tasinamadi: {e}")
        return varsayilan


def json_yaz(yol, veri):
    """Atomik JSON yazma: once gecici dosyaya yazar, sonra yerine koyar.

    Yazma sirasinda surec olurse dosya yarim kalmaz; eski dosya bozulmaz.
    """
    gecici = yol.with_suffix(yol.suffix + ".tmp")
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(veri, f, indent=4, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(gecici, yol)
    except OSError as e:
        gunluk(f"⚠️ {yol.name} yazilamadi: {e}")
        try:
            gecici.unlink(missing_ok=True)
        except OSError:
            pass


def kirp(metin, sinir):
    """Metni sinira kadar kisaltir, kesildiyse sonuna isaret koyar."""
    metin = metin or ""
    if len(metin) <= sinir:
        return metin
    return metin[: max(0, sinir - 3)] + "..."


def bicim(deger, kalip="{:.2f}", yoksa="bilinmiyor"):
    """None gelen degerleri bicimlendirmeye sokmadan yazar."""
    d = sayi(deger)
    return kalip.format(d) if d is not None else yoksa


def yuzde_bicim(oran):
    """0.28 -> "%28.1" ; None -> "bilinmiyor"."""
    d = sayi(oran)
    return f"%{d * 100:.1f}" if d is not None else "bilinmiyor"


def simdi():
    """Borsa saat diliminde su anki zaman."""
    return datetime.now(BORSA_TZ) if BORSA_TZ else datetime.now()


# ==========================================================================
# AYARLAR
# ==========================================================================

def ayarlari_yukle():
    """ayarlar.json'u okur ve dogrular. Hata varsa anlasilir mesajla cikar."""
    if not AYAR_YOLU.exists():
        print(f"❌ {AYAR_YOLU.name} bulunamadi.")
        print(f"   Beklenen yer: {AYAR_YOLU}")
        print("   ayarlar.example.json dosyasini kopyalayip adini ayarlar.json yapin.")
        sys.exit(1)

    try:
        with open(AYAR_YOLU, "r", encoding="utf-8") as f:
            ayarlar = json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ {AYAR_YOLU.name} gecerli bir JSON degil.")
        print(f"   Satir {e.lineno}, sutun {e.colno}: {e.msg}")
        print("   Ipucu: son ogeden sonra fazladan virgul olmamali.")
        sys.exit(1)
    except OSError as e:
        print(f"❌ {AYAR_YOLU.name} okunamadi: {e}")
        sys.exit(1)

    if not isinstance(ayarlar, dict):
        print(f"❌ {AYAR_YOLU.name} icerigi bir JSON nesnesi olmali.")
        sys.exit(1)

    eksik = [a for a in ZORUNLU_AYARLAR if a not in ayarlar]
    if eksik:
        print(f"❌ {AYAR_YOLU.name} icinde eksik anahtar: {', '.join(eksik)}")
        print("   ayarlar.example.json dosyasindaki butun alanlari kopyalayin.")
        sys.exit(1)

    strateji = ayarlar.get("STRATEJI")
    if not isinstance(strateji, dict):
        print("❌ STRATEJI bir JSON nesnesi olmali.")
        sys.exit(1)

    eksik_s = [a for a in ZORUNLU_STRATEJI if a not in strateji]
    if eksik_s:
        print(f"❌ STRATEJI icinde eksik anahtar: {', '.join(eksik_s)}")
        print("   Gerekli alanlar: " + ", ".join(ZORUNLU_STRATEJI))
        sys.exit(1)

    hatali = []
    for a in ZORUNLU_STRATEJI:
        if sayi(strateji[a]) is None:
            hatali.append(f"STRATEJI.{a} sayi olmali (gelen: {strateji[a]!r})")
    for a in ("GOOGLE_API_KEY", "TG_TOKEN"):
        d = ayarlar.get(a)
        if not isinstance(d, str) or not d.strip() or d.strip().startswith("BURAYA"):
            hatali.append(f"{a} doldurulmamis")
    chat = str(ayarlar.get("TG_CHAT_ID", "")).strip()
    if not chat or chat.startswith("BURAYA"):
        hatali.append("TG_CHAT_ID doldurulmamis")
    if hatali:
        print(f"❌ {AYAR_YOLU.name} dogrulanamadi:")
        for h in hatali:
            print(f"   - {h}")
        sys.exit(1)

    for a in ZORUNLU_STRATEJI:
        strateji[a] = sayi(strateji[a])

    # Opsiyonel alanlari varsayilanlarla tamamla
    for a, v in VARSAYILAN_AYARLAR.items():
        ayarlar.setdefault(a, v)

    return ayarlar


# ==========================================================================
# DURUM (gunluk sinyal gecmisi ve AI istek sayaci)
# ==========================================================================

def durum_yukle():
    """Gunluk durumu okur. Gun degistiyse sifirlar.

    Eski kod saat == 0 kontrolu yapiyordu: bot gece calismiyorsa liste hic
    temizlenmiyor, gece calisiyorsa tarama ortasinda her hisse adiminda
    temizlenip ayni hisseye tekrar tekrar sinyal gidiyordu.
    """
    ham = json_oku(DURUM_YOLU, {})
    if not isinstance(ham, dict):
        ham = {}
    bugun = date.today().isoformat()
    if ham.get("tarih") != bugun:
        return {"tarih": bugun, "sinyal_gecmisi": [], "ai_istek": 0}
    gecmis = ham.get("sinyal_gecmisi")
    return {
        "tarih": bugun,
        "sinyal_gecmisi": [s for s in gecmis if isinstance(s, str)] if isinstance(gecmis, list) else [],
        "ai_istek": int(sayi(ham.get("ai_istek")) or 0),
    }


def durum_kaydet(durum):
    json_yaz(DURUM_YOLU, durum)


# ==========================================================================
# PORTFOY
# ==========================================================================

def portfoy_yukle():
    """Portfoyu okur ve her kaydi dogrular. Bozuk kayitlari atar.

    Eski kod json.load sonucunu dogrudan kullaniyordu: dosya [] ise
    .items() AttributeError, kayitta alis_fiyati yoksa KeyError, 0 ise
    kar/zarar hesabinda ZeroDivisionError veriyordu.
    """
    ham = json_oku(PORTFOY_YOLU, {})
    if not isinstance(ham, dict):
        gunluk("⚠️ portfoy.json bir nesne degil, bos portfoyle devam ediliyor.")
        return {}

    temiz = {}
    for sembol, detay in ham.items():
        if not isinstance(sembol, str) or not isinstance(detay, dict):
            gunluk(f"⚠️ Portfoyde gecersiz kayit atlandi: {sembol!r}")
            continue
        fiyat = sayi(detay.get("alis_fiyati"))
        if fiyat is None or fiyat <= 0:
            gunluk(f"⚠️ {sembol}: alis_fiyati gecersiz "
                   f"({detay.get('alis_fiyati')!r}), kayit atlandi.")
            continue
        temiz[sembol] = {"alis_fiyati": fiyat, "tarih": str(detay.get("tarih", ""))}
    return temiz


def portfoy_kaydet(portfoy):
    json_yaz(PORTFOY_YOLU, portfoy)


# ==========================================================================
# TEMEL VERI ONBELLEGI
# ==========================================================================

def onbellek_yukle():
    ham = json_oku(ONBELLEK_YOLU, {})
    return ham if isinstance(ham, dict) else {}


def onbellekten_al(onbellek, sembol, ttl_saat):
    kayit = onbellek.get(sembol)
    if not isinstance(kayit, dict):
        return None
    try:
        yazilma = datetime.fromisoformat(kayit["zaman"])
    except (KeyError, ValueError, TypeError):
        return None
    ttl = sayi(ttl_saat) or 12
    if datetime.now() - yazilma > timedelta(hours=ttl):
        return None
    veri = kayit.get("veri")
    return veri if isinstance(veri, dict) else None


def onbellege_yaz(onbellek, sembol, veri):
    onbellek[sembol] = {
        "zaman": datetime.now().isoformat(timespec="seconds"),
        "veri": veri,
    }


# ==========================================================================
# PIYASA SAATI
# ==========================================================================

def piyasa_acik(ayarlar):
    """BIST islem saatleri icinde miyiz? Hafta sonu kapali.

    Eski kod 7/24 tarama yapiyordu: gece 03:00'te bir onceki kapanis fiyatiyla
    "anlik fiyat" diye sinyal uretebiliyordu.
    """
    an = simdi()
    if an.weekday() >= 5:
        return False, "hafta sonu"
    try:
        a_s, a_d = (int(x) for x in str(ayarlar["PIYASA_ACILIS"]).split(":"))
        k_s, k_d = (int(x) for x in str(ayarlar["PIYASA_KAPANIS"]).split(":"))
    except (ValueError, KeyError):
        return True, "saat ayari okunamadi, acik varsayildi"
    simdiki = an.hour * 60 + an.minute
    if simdiki < a_s * 60 + a_d:
        return False, "piyasa henuz acilmadi"
    if simdiki >= k_s * 60 + k_d:
        return False, "piyasa kapandi"
    return True, "acik"


# ==========================================================================
# TEKNIK VE TEMEL VERI
# ==========================================================================

def rsi_hesapla(kapanis, periyot):
    """Wilder RSI. Veri yetersizse veya tanimsizsa None doner.

    Eski kod ewm(com=13, min_periods=14) ile 1 aylik (~22 bar) veri kullaniyordu;
    isinma tamamlanmadigi icin RSI referans degerden ~3 puan sapiyordu. Ayrica
    dusus hic yoksa (kayip=0) sonuc inf bolmesinden geliyordu, fiyat hic
    degismezse NaN cikiyordu ve NaN >= limit karsilastirmasi sessizce False
    donup hisseyi filtreden geciriyordu.
    """
    if kapanis is None or len(kapanis) < periyot + 1:
        return None

    delta = kapanis.diff()
    kazanc = delta.clip(lower=0)
    kayip = -delta.clip(upper=0)

    ort_kazanc = kazanc.ewm(alpha=1.0 / periyot, min_periods=periyot, adjust=False).mean()
    ort_kayip = kayip.ewm(alpha=1.0 / periyot, min_periods=periyot, adjust=False).mean()

    k = sayi(ort_kazanc.iloc[-1])
    z = sayi(ort_kayip.iloc[-1])
    if k is None or z is None:
        return None
    if z == 0:
        return 100.0 if k > 0 else None  # ikisi de sifirsa RSI tanimsiz
    return 100.0 - (100.0 / (1.0 + k / z))


def teknik_veri_cek(sembol, ayarlar, onbellek):
    """Fiyat, RSI ve temel verileri toplar. Basarisizsa None doner.

    Temel veriler (info) yavas ve Yahoo tarafinda siki limitli oldugu icin
    onbellekten okunur; gecmis fiyat her turda tazedir.
    """
    try:
        hisse = yf.Ticker(sembol)
        # auto_adjust bilerek varsayilanda (True) birakildi: temettu/bedelsiz
        # sonrasi GECMIS barlar duzeltilir, en son bar duzeltilmez. Alis fiyati
        # kaydedildigi gunun en son bariyla, guncel fiyat da en son barla
        # alindigi icin kar/zarar ayni temelde kalir. auto_adjust=False yapmak
        # RSI'a temettu gununde yapay bir bosluk sokar.
        df = hisse.history(period=str(ayarlar["GECMIS_PERIYODU"]), interval="1d")
    except Exception as e:
        gunluk(f"⚠️ {sembol}: fiyat gecmisi alinamadi ({e.__class__.__name__})")
        return None

    if df is None or df.empty or "Close" not in df:
        gunluk(f"⚠️ {sembol}: fiyat gecmisi bos, atlaniyor")
        return None

    kapanis = df["Close"].dropna()
    if kapanis.empty:
        gunluk(f"⚠️ {sembol}: kapanis verisi yok, atlaniyor")
        return None

    fiyat = sayi(kapanis.iloc[-1])
    if fiyat is None or fiyat <= 0:
        gunluk(f"⚠️ {sembol}: gecersiz fiyat, atlaniyor")
        return None

    periyot = int(sayi(ayarlar["RSI_PERIYODU"]) or 14)
    rsi = rsi_hesapla(kapanis, periyot)
    if rsi is None:
        gunluk(f"⚠️ {sembol}: RSI hesaplanamadi (veri yetersiz), atlaniyor")
        return None

    temel = onbellekten_al(onbellek, sembol, ayarlar["TEMEL_ONBELLEK_SAAT"])
    if temel is None:
        try:
            info = hisse.info or {}
        except Exception as e:
            gunluk(f"⚠️ {sembol}: temel veri alinamadi ({e.__class__.__name__})")
            info = {}
        temel = {
            "fk": sayi(info.get("trailingPE")),
            "pddd": sayi(info.get("priceToBook")),
            "roe": sayi(info.get("returnOnEquity")),
        }
        onbellege_yaz(onbellek, sembol, temel)

    return {
        "sembol": sembol,
        "fiyat": fiyat,
        "rsi": rsi,
        "fk": temel.get("fk"),
        "pddd": temel.get("pddd"),
        "roe": temel.get("roe"),
    }


def eleme_nedenleri(veri, ayarlar):
    """Hisse neden elenir? Bos liste donerse hisse filtreden gecer.

    Temel veri eksikse (yfinance anahtari hic gondermiyor) eski kod 999.0
    varsayilanini kullaniyordu; bu, 99 hissenin 30'unun her turda sessizce
    elenmesine yol aciyordu. Artik eksik veri ayri bir durum olarak ele alinir
    ve EKSIK_TEMEL_VERI_ELENSIN ayariyla yonetilir.
    """
    strateji = ayarlar["STRATEJI"]
    nedenler = []

    if veri["rsi"] >= strateji["RSI_AL_LIMIT"]:
        nedenler.append(f"RSI {veri['rsi']:.1f} >= {strateji['RSI_AL_LIMIT']:.0f}")

    eksik_elenir = bool(ayarlar["EKSIK_TEMEL_VERI_ELENSIN"])
    min_fk = sayi(ayarlar["MIN_FK"])

    fk = veri["fk"]
    if fk is None:
        if eksik_elenir:
            nedenler.append("F/K bilinmiyor")
    elif fk >= strateji["MAX_FK"]:
        nedenler.append(f"F/K {fk:.1f} >= {strateji['MAX_FK']:.0f}")
    elif min_fk is not None and fk <= min_fk:
        # Negatif F/K "cok ucuz" degil, sirketin zarar ettigi anlamina gelir.
        nedenler.append(f"F/K {fk:.1f} <= {min_fk:.0f} (zarar)")

    pddd = veri["pddd"]
    if pddd is None:
        if eksik_elenir:
            nedenler.append("P/D-D/D bilinmiyor")
    elif pddd >= strateji["MAX_PDDD"]:
        # Eski kodda MAX_PDDD okunuyordu ama filtrede hic kullanilmiyordu.
        nedenler.append(f"P/D-D/D {pddd:.2f} >= {strateji['MAX_PDDD']:.2f}")

    roe = veri["roe"]
    if roe is None:
        if eksik_elenir:
            nedenler.append("ROE bilinmiyor")
    elif roe <= strateji["MIN_ROE"]:
        nedenler.append(f"ROE {yuzde_bicim(roe)} <= {yuzde_bicim(strateji['MIN_ROE'])}")

    return nedenler


# ==========================================================================
# HABERLER
# ==========================================================================

def haberleri_bul(sembol):
    """Google News RSS'ten son iki basligi ceker. Hata durumunda not doner."""
    saf = sembol.split(".")[0]
    url = (
        "https://news.google.com/rss/search"
        f"?q={requests.utils.quote(saf + ' hisse kap')}&hl=tr-TR&gl=TR&ceid=TR:tr"
    )
    try:
        # feedparser.parse(url) kendi istegini zaman asimi OLMADAN atar; sunucu
        # yanit vermezse bot suresiz asili kalirdi. Istegi requests ile atip
        # icerigi feedparser'a veriyoruz.
        yanit = requests.get(url, timeout=AG_ZAMAN_ASIMI)
        yanit.raise_for_status()
        feed = feedparser.parse(yanit.content)
    except requests.RequestException as e:
        return f"Haber servisi okunamadi ({e.__class__.__name__})."
    except Exception as e:
        return f"Haber ayristirilamadi ({e.__class__.__name__})."

    girdiler = getattr(feed, "entries", None) or []
    basliklar = []
    for h in girdiler[:2]:
        baslik = (getattr(h, "title", "") or "").strip()
        if baslik:
            basliklar.append(f"- {kirp(baslik, 160)}")
    return "\n".join(basliklar) if basliklar else "Onemli bir haber bulunamadi."


# ==========================================================================
# TELEGRAM
# ==========================================================================

def telegram_gonder(ayarlar, metin, kuru=False):
    """Telegram'a HTML bicimli mesaj gonderir.

    Eski kod Markdown yildizlari yaziyor ama parse_mode gondermiyordu; mesaj
    ham yildizlarla gorunuyordu. parse_mode="Markdown" eklemek tek basina
    yetmez: Gemini metnindeki dengesiz * veya _ karakteri 400 hatasi verir.
    Cozum HTML kullanmak ve degisken metinleri html.escape ile kacirmak.
    """
    if kuru:
        print("--- [KURU KIP] Telegram'a gonderilmedi ---")
        print(re.sub(r"<[^>]+>", "", metin))
        print("--- son ---")
        return True

    metin = kirp(metin, TELEGRAM_SINIR)
    url = f"https://api.telegram.org/bot{ayarlar['TG_TOKEN']}/sendMessage"
    govde = {
        "chat_id": ayarlar["TG_CHAT_ID"],
        "text": metin,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for deneme in range(1, 4):
        try:
            yanit = requests.post(url, json=govde, timeout=AG_ZAMAN_ASIMI)
        except requests.RequestException as e:
            gunluk(f"⚠️ Telegram baglanti hatasi ({deneme}/3): {e.__class__.__name__}")
            time.sleep(2 * deneme)
            continue

        if yanit.status_code == 200:
            return True

        if yanit.status_code == 429:
            bekle = 5
            try:
                bekle = int(yanit.json().get("parameters", {}).get("retry_after", 5))
            except (ValueError, AttributeError, TypeError):
                pass
            gunluk(f"⏳ Telegram limiti, {bekle} sn bekleniyor...")
            time.sleep(bekle)
            continue

        gunluk(f"⚠️ Telegram API hatasi {yanit.status_code}: {kirp(yanit.text, 200)}")
        if 400 <= yanit.status_code < 500:
            return False  # istemci hatasi, tekrar denemek faydasiz
        time.sleep(2 * deneme)

    return False


def alis_mesaji(veri, ai_yorumu, haberler):
    e = html.escape
    return (
        "🚀 <b>YENI FIRSAT SINYALI</b> 🚀\n"
        "-----------------------------------\n"
        f"🏢 <b>Hisse:</b> #{e(veri['sembol'].replace('.IS', ''))}\n"
        f"💰 <b>Anlik Fiyat:</b> {bicim(veri['fiyat'])} TL\n"
        f"📊 <b>RSI:</b> {bicim(veri['rsi'], '{:.1f}')}"
        f" | <b>F/K:</b> {bicim(veri['fk'], '{:.1f}')}"
        f" | <b>P/D-D/D:</b> {bicim(veri['pddd'])}"
        f" | <b>ROE:</b> {yuzde_bicim(veri['roe'])}\n"
        "-----------------------------------\n"
        "🤖 <b>GEMINI AI KARARI:</b>\n"
        f"{e(kirp(ai_yorumu, 1800))}\n\n"
        "📰 <b>SON HABERLER:</b>\n"
        f"{e(kirp(haberler, 600))}\n"
        "-----------------------------------\n"
        f"<i>{e(UYARI_METNI)}</i>"
    )


def satis_mesaji(veri, alis_fiyati, gerekce, ai_yorumu):
    e = html.escape
    yuzde = ((veri["fiyat"] - alis_fiyati) / alis_fiyati) * 100
    isaret = "🟢 KAR" if yuzde > 0 else "🔴 ZARAR"
    return (
        "🚨 <b>SATIS SINYALI</b> 🚨\n"
        "-----------------------------------\n"
        f"🏢 <b>Hisse:</b> #{e(veri['sembol'].replace('.IS', ''))}\n"
        f"📉 <b>Alis Fiyati:</b> {bicim(alis_fiyati)} TL\n"
        f"📈 <b>Guncel Fiyat:</b> {bicim(veri['fiyat'])} TL\n"
        f"📊 <b>Durum:</b> {isaret} (%{yuzde:.2f})\n"
        f"🔔 <b>Tetik:</b> {e(gerekce)}\n"
        "-----------------------------------\n"
        "🤖 <b>GEREKCE:</b>\n"
        f"{e(kirp(ai_yorumu, 1800))}\n"
        "-----------------------------------\n"
        f"<i>{e(UYARI_METNI)}</i>"
    )


# ==========================================================================
# GEMINI
# ==========================================================================

class AiKapisi:
    """Gemini cagrilarini saran, kota ve hiz sinirini gozeten katman.

    Eski kodda sinir yoktu: ornek ayarlarla 98 hissenin 68'i filtreyi gecip
    her turda ~68 istek atiyordu. Ucretsiz kota (gunde ~250) 3 turda tukeniyordu.
    """

    def __init__(self, ayarlar, durum, kapali=False):
        self.ayarlar = ayarlar
        self.durum = durum
        self.kapali = kapali
        self.model = str(ayarlar["AI_MODEL"])
        self.tur_istek = 0
        self.son_cagrilar = []
        self.client = None

        if kapali:
            return
        try:
            from google import genai

            self.client = genai.Client(api_key=ayarlar["GOOGLE_API_KEY"])
        except Exception as e:
            print(f"❌ Gemini baglantisi kurulamadi: {e}")
            sys.exit(1)

    def turu_sifirla(self):
        self.tur_istek = 0

    def kota_var_mi(self):
        if self.kapali:
            return False
        if self.tur_istek >= int(sayi(self.ayarlar["AI_MAX_ISTEK_TUR"]) or 15):
            return False
        if self.durum["ai_istek"] >= int(sayi(self.ayarlar["AI_MAX_ISTEK_GUN"]) or 200):
            return False
        return True

    def _hiz_bekle(self):
        """Dakikada izin verilen istek sayisini asmamak icin bekler."""
        sinir = int(sayi(self.ayarlar["AI_DAKIKADA_ISTEK"]) or 8)
        an = time.monotonic()
        self.son_cagrilar = [t for t in self.son_cagrilar if an - t < 60]
        if len(self.son_cagrilar) >= sinir:
            bekle = 60 - (an - self.son_cagrilar[0]) + 0.5
            if bekle > 0:
                gunluk(f"⏳ Dakikalik AI limiti, {bekle:.0f} sn bekleniyor...")
                time.sleep(bekle)
            an = time.monotonic()
            self.son_cagrilar = [t for t in self.son_cagrilar if an - t < 60]
        self.son_cagrilar.append(an)

    def sor(self, prompt):
        """Modele sorar. (metin, hata) doner; metin None ise cevap alinamadi."""
        if self.kapali:
            return None, "AI kapali (--ai-yok)"
        if not self.kota_var_mi():
            return None, "AI kota siniri doldu"

        for deneme in range(1, 4):
            self._hiz_bekle()
            try:
                yanit = self.client.models.generate_content(
                    model=self.model, contents=prompt
                )
            except Exception as e:
                mesaj = str(e)
                kod = getattr(e, "code", None) or getattr(e, "status_code", None)
                limit = kod == 429 or "429" in mesaj or "RESOURCE_EXHAUSTED" in mesaj
                if limit and deneme < 3:
                    bekle = 20 * deneme
                    gunluk(f"⏳ Gemini limiti, {bekle} sn bekleniyor ({deneme}/3)")
                    time.sleep(bekle)
                    continue
                return None, f"AI hatasi: {kirp(mesaj, 160)}"

            self.tur_istek += 1
            self.durum["ai_istek"] += 1

            # response.text guvenlik filtresi veya bos yanitta None olabilir;
            # eski kod dogrudan .strip() cagirdigi icin burada patlardi.
            metin = getattr(yanit, "text", None)
            if not metin or not metin.strip():
                return None, "AI bos yanit dondurdu"
            return metin.strip(), None

        return None, "AI limiti asilamadi (3 deneme)"


def karar_oku(cevap, gecerli):
    """Cevaptan "KARAR: X" ifadesini kati bicimde okur.

    Eski kod `"ONAY" in cevap.upper()` kullaniyordu. "onaylamiyorum",
    "onay vermiyorum" gibi cumleler ONAY sayiliyor; "satmamaliyiz",
    "satis icin erken" gibi cumleler SAT sayiliyordu. Yani reddedilen hisseye
    alis, tutulmasi gereken pozisyona satis sinyali gidebiliyordu.
    Karar okunamazsa None doner ve cagiran taraf hicbir islem yapmaz.
    """
    if not cevap:
        return None
    eslesme = KARAR_DESENI.search(cevap)
    if not eslesme:
        return None
    karar = eslesme.group(1).upper()
    return karar if karar in gecerli else None


def alis_prompt(veri, haberler):
    return f"""Sen usta, net ve kisa konusan bir Borsa Istanbul analistisin.

Hisse: {veri['sembol']}
Fiyat: {bicim(veri['fiyat'])} TL
RSI: {bicim(veri['rsi'], '{:.1f}')}
F/K: {bicim(veri['fk'])}
P/D-D/D: {bicim(veri['pddd'])}
ROE: {yuzde_bicim(veri['roe'])}
Son haberler:
{haberler}

Not: "bilinmiyor" yazan veriler kaynaktan gelmedi. Yok saymadan, belirsizlik
olarak degerlendir.

Gorev: Bu verileri analiz et.
- Ilk satira MUTLAKA tam olarak "KARAR: ONAY" veya "KARAR: RET" yaz.
- ONAY verirsen alinmasi gereken 3 kisa madde yaz (Teknik, Temel, Haber).
- RET verirsen tek cumleyle nedenini yaz.
Metnin baska hicbir yerinde "KARAR:" ifadesini kullanma."""


def satis_prompt(veri, alis_fiyati):
    yuzde = ((veri["fiyat"] - alis_fiyati) / alis_fiyati) * 100
    return f"""Sen usta bir Borsa Istanbul analistisin.

Hisse: {veri['sembol']}
Alis fiyatimiz: {bicim(alis_fiyati)} TL
Guncel fiyat: {bicim(veri['fiyat'])} TL
Kar/Zarar: %{yuzde:.2f}
Guncel RSI: {bicim(veri['rsi'], '{:.1f}')}

Gorev: Bu hisseyi elimizde tutuyoruz. Satmali miyiz?
- Ilk satira MUTLAKA tam olarak "KARAR: SAT" veya "KARAR: TUT" yaz.
- SAT dersen nedenini 2 kisa maddeyle yaz.
- TUT dersen tek cumleyle nedenini yaz.
Metnin baska hicbir yerinde "KARAR:" ifadesini kullanma."""


# ==========================================================================
# TUR ADIMLARI
# ==========================================================================

def portfoyu_gozden_gecir(portfoy, ayarlar, ai, onbellek, kuru):
    """Elde tutulan hisseleri kontrol eder, satilacaklarin listesini dondurur."""
    if not portfoy:
        return []

    gunluk(f"💼 Portfoydeki {len(portfoy)} hisse kontrol ediliyor...")
    satilacaklar = []
    zarar_kes = sayi(ayarlar["ZARAR_KES_YUZDE"])
    kar_al = sayi(ayarlar["KAR_AL_YUZDE"])
    bekleme = sayi(ayarlar["HISSE_ARASI_BEKLEME_SN"]) or 0.0

    for sembol, detay in list(portfoy.items()):
        veri = teknik_veri_cek(sembol, ayarlar, onbellek)
        if not veri:
            # Veri alinamayan hissede de bekle: Yahoo hata vermeye basladiginda
            # beklemesiz dongu saniyeler icinde onlarca istek atar ve IP
            # sinirlamasina girmemize yol acar.
            time.sleep(bekleme)
            continue

        alis = detay["alis_fiyati"]  # portfoy_yukle gecerliligini garanti etti
        yuzde = ((veri["fiyat"] - alis) / alis) * 100

        # Mekanik kurallar AI'dan once: kota bitse de zarar kesme calisir.
        gerekce = None
        if zarar_kes is not None and yuzde <= zarar_kes:
            gerekce = f"Zarar kes esigi (%{zarar_kes:.1f})"
        elif kar_al is not None and yuzde >= kar_al:
            gerekce = f"Kar al esigi (%{kar_al:.1f})"

        if gerekce:
            gunluk(f"🚨 {sembol}: {gerekce} -> satis sinyali (%{yuzde:.2f})")
            mesaj = satis_mesaji(veri, alis, gerekce, "Mekanik kural tetiklendi.")
            if telegram_gonder(ayarlar, mesaj, kuru):
                satilacaklar.append(sembol)
            continue

        metin, hata = ai.sor(satis_prompt(veri, alis))
        karar = karar_oku(metin, {"SAT", "TUT"})

        if karar is None:
            gunluk(f"🤔 {sembol}: satis karari okunamadi "
                   f"({hata or 'bicim hatali'}), pozisyon korunuyor (%{yuzde:.2f})")
            continue

        if karar == "SAT":
            gunluk(f"🚨 {sembol}: AI SAT dedi (%{yuzde:.2f})")
            mesaj = satis_mesaji(veri, alis, "AI karari", metin)
            if telegram_gonder(ayarlar, mesaj, kuru):
                satilacaklar.append(sembol)
        else:
            gunluk(f"🛡️ {sembol}: AI TUT dedi (%{yuzde:.2f})")

    return satilacaklar


def firsat_tara(portfoy, ayarlar, durum, ai, onbellek, kuru, hisse_siniri, bu_tur_satilan):
    """Yeni alim firsatlarini tarar. Gonderilen sinyal sayisini dondurur."""
    gunluk("🔍 Yeni firsatlar taraniyor...")
    liste = HISSELER[:hisse_siniri] if hisse_siniri else HISSELER
    gecmis = set(durum["sinyal_gecmisi"])
    max_hisse = int(sayi(ayarlar["PORTFOY_MAX_HISSE"]) or 10)
    bekleme = sayi(ayarlar["HISSE_ARASI_BEKLEME_SN"]) or 0.0

    sinyal = 0
    elendi = 0
    atlandi = 0
    aday = 0
    ardisik_hata = 0

    for sembol in liste:
        # Zaten elimizdeki hisseye tekrar alis sinyali gonderilmez; ayni turda
        # sattigimizi hemen geri almayiz; bugun sinyal verileni tekrarlamayiz.
        if sembol in portfoy or sembol in bu_tur_satilan or sembol in gecmis:
            atlandi += 1
            continue
        if len(portfoy) >= max_hisse:
            gunluk(f"🧺 Portfoy dolu ({max_hisse} hisse), tarama durduruldu.")
            break

        veri = teknik_veri_cek(sembol, ayarlar, onbellek)
        if not veri:
            # Beklemesiz continue, Yahoo tarafinda sorun cikinca 98 hisseye
            # saniyeler icinde istek atmamiza yol aciyordu.
            ardisik_hata += 1
            time.sleep(bekleme)
            if ardisik_hata >= 10:
                gunluk("🛑 Ust uste 10 hissede veri alinamadi "
                       "(Yahoo sinirlamasi olabilir), tarama durduruldu.")
                break
            continue
        ardisik_hata = 0

        nedenler = eleme_nedenleri(veri, ayarlar)
        if nedenler:
            elendi += 1
            print(f"  📉 Elendi: {sembol} ({'; '.join(nedenler)})")
            time.sleep(bekleme)
            continue

        if ai.kapali:
            # --ai-yok kipi: filtreyi tum liste uzerinde denemek icin tarama
            # devam eder, sadece AI'a sorulmaz ve sinyal uretilmez.
            aday += 1
            gunluk(f"⚡ Firsat adayi: {sembol} (RSI {veri['rsi']:.1f}, "
                   f"F/K {bicim(veri['fk'], '{:.1f}')}, ROE {yuzde_bicim(veri['roe'])})"
                   f" — AI kapali, sinyal uretilmedi")
            time.sleep(bekleme)
            continue

        if not ai.kota_var_mi():
            gunluk("⏸️ AI kota siniri doldu, tarama bu turda durduruldu.")
            break

        aday += 1
        gunluk(f"⚡ Firsat adayi: {sembol} (RSI {veri['rsi']:.1f}) -> AI inceliyor")
        haberler = haberleri_bul(sembol)
        metin, hata = ai.sor(alis_prompt(veri, haberler))
        karar = karar_oku(metin, {"ONAY", "RET"})

        if karar is None:
            gunluk(f"🤔 {sembol}: karar okunamadi ({hata or 'bicim hatali'}), "
                   f"alim yapilmadi")
            time.sleep(bekleme)
            continue

        if karar == "RET":
            print(f"  ❌ AI reddetti ({sembol}): {kirp(metin, 90)}")
            time.sleep(bekleme)
            continue

        gunluk(f"✅ {sembol}: AI ONAY verdi, sinyal gonderiliyor")
        if telegram_gonder(ayarlar, alis_mesaji(veri, metin, haberler), kuru):
            portfoy[sembol] = {
                "alis_fiyati": veri["fiyat"],
                "tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            durum["sinyal_gecmisi"].append(sembol)
            gecmis.add(sembol)
            sinyal += 1
            portfoy_kaydet(portfoy)
            durum_kaydet(durum)
            gunluk(f"💼 {sembol} portfoye eklendi ({bicim(veri['fiyat'])} TL)")
        else:
            gunluk(f"⚠️ {sembol}: Telegram gonderilemedi, portfoye eklenmedi")

        time.sleep(bekleme)

    gunluk(f"📊 Tur ozeti: {aday} aday | {sinyal} sinyal | {elendi} elendi"
           f" | {atlandi} atlandi | AI istek: tur {ai.tur_istek},"
           f" gun {durum['ai_istek']}")
    return sinyal


# ==========================================================================
# ANA AKIS
# ==========================================================================

def tur_calistir(ayarlar, ai, kuru, hisse_siniri):
    durum = durum_yukle()
    ai.durum = durum
    ai.turu_sifirla()
    onbellek = onbellek_yukle()
    portfoy = portfoy_yukle()

    satilacaklar = portfoyu_gozden_gecir(portfoy, ayarlar, ai, onbellek, kuru)
    for s in satilacaklar:
        portfoy.pop(s, None)
    if satilacaklar:
        portfoy_kaydet(portfoy)

    firsat_tara(portfoy, ayarlar, durum, ai, onbellek, kuru,
                hisse_siniri, set(satilacaklar))

    durum_kaydet(durum)
    json_yaz(ONBELLEK_YOLU, onbellek)


def main():
    cozumleyici = argparse.ArgumentParser(description="BorsaAjan - BIST analiz botu")
    cozumleyici.add_argument("--tek-tur", action="store_true",
                             help="tek tur calis ve cik")
    cozumleyici.add_argument("--kuru", action="store_true",
                             help="Telegram'a mesaj gondermeden calis")
    cozumleyici.add_argument("--ai-yok", action="store_true",
                             help="Gemini'ye hic sorma (kota harcamaz)")
    cozumleyici.add_argument("--hisse", type=int, metavar="N",
                             help="listenin sadece ilk N hissesini tara")
    cozumleyici.add_argument("--saat-yok", action="store_true",
                             help="piyasa saati kontrolunu atla")
    arg = cozumleyici.parse_args()

    ciktiyi_utf8_yap()

    print("\n🦅 BorsaAjan baslatiliyor...")
    print(f"   Calisma klasoru: {KOK}")
    ayarlar = ayarlari_yukle()
    if arg.saat_yok:
        ayarlar["PIYASA_SAATI_ZORUNLU"] = False

    ai = AiKapisi(ayarlar, durum_yukle(), kapali=arg.ai_yok)

    kipler = []
    if arg.kuru:
        kipler.append("KURU (Telegram kapali)")
    if arg.ai_yok:
        kipler.append("AI YOK")
    if arg.hisse:
        kipler.append(f"ilk {arg.hisse} hisse")
    if arg.saat_yok:
        kipler.append("saat kontrolu kapali")
    print(f"   Kip: {', '.join(kipler) if kipler else 'normal'}")
    print(f"   Hisse sayisi: {len(HISSELER)}")
    print(f"   {UYARI_METNI}\n")

    bekleme = int(sayi(ayarlar["DONGU_BEKLEME_SN"]) or 300)
    hata_sayaci = 0

    while True:
        try:
            if ayarlar["PIYASA_SAATI_ZORUNLU"]:
                acik, neden = piyasa_acik(ayarlar)
                if not acik:
                    gunluk(f"😴 Piyasa kapali ({neden}).")
                    if arg.tek_tur:
                        return
                    time.sleep(bekleme)
                    continue

            gunluk("=" * 46)
            gunluk("Yeni tarama turu basliyor")
            tur_calistir(ayarlar, ai, arg.kuru, arg.hisse)
            hata_sayaci = 0

        except KeyboardInterrupt:
            print("\n👋 Kullanici durdurdu, cikiliyor.")
            return
        except Exception as e:
            # Ana dongu govdesi korumali: tek bir beklenmeyen istisna botu
            # kalici olarak oldurmesin. Ust uste hata gelirse bekleme artar.
            hata_sayaci += 1
            gunluk(f"💥 Turda beklenmeyen hata ({hata_sayaci}/5): "
                   f"{e.__class__.__name__}: {kirp(str(e), 200)}")
            if hata_sayaci >= 5:
                gunluk("🛑 Ust uste 5 hata, bot durduruluyor. Loglari kontrol edin.")
                return
            time.sleep(min(60 * hata_sayaci, 300))
            continue

        if arg.tek_tur:
            gunluk("Tek tur tamamlandi, cikiliyor.")
            return

        gunluk(f"💤 {bekleme} sn bekleniyor...\n")
        time.sleep(bekleme)


if __name__ == "__main__":
    main()
