"""BorsaAjan icin regresyon testleri.

Ag erisimi ve API anahtari GEREKTIRMEZ. Calistirma:

    py test_ana_ajan.py

Her test, duzeltilen somut bir hatayi koruma altina alir: test kirmizi olursa
o hata geri gelmis demektir.
"""

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ana_ajan as aa  # noqa: E402

GECTI = []
KALDI = []


def kontrol(ad, kosul, ayrinti=""):
    if kosul:
        GECTI.append(ad)
        print(f"  [GECTI] {ad}")
    else:
        KALDI.append((ad, ayrinti))
        print(f"  [KALDI] {ad}  {ayrinti}")


# ==========================================================================
def test_karar_oku():
    """Eski kod 'ONAY' in cevap ile calisiyordu; RET cevaplari ONAY sayiliyordu."""
    print("\n[1] karar_oku — AI kararinin dogru okunmasi")

    ret_cevaplari = [
        "KARAR: RET. Bu hisseyi onaylamiyorum, bilanco zayif.",
        "KARAR: RET - Riskli gorundugu icin onay vermiyorum.",
        "KARAR: RET\nTeknik gorunum onaylanabilir degil.",
        "KARAR: RET. Onay icin temel veriler yetersiz.",
    ]
    for c in ret_cevaplari:
        k = aa.karar_oku(c, {"ONAY", "RET"})
        kontrol(f"RET okunuyor: {c[:38]!r}", k == "RET", f"-> {k}")

    onay_cevaplari = [
        "KARAR: ONAY\n- Teknik: RSI dusuk\n- Temel: F/K makul\n- Haber: notr",
        "karar: onay\nUygun gorunuyor.",
        "**KARAR: ONAY**\nAlinabilir.",
        "KARAR ONAY\nUygun.",
    ]
    for c in onay_cevaplari:
        k = aa.karar_oku(c, {"ONAY", "RET"})
        kontrol(f"ONAY okunuyor: {c[:32]!r}", k == "ONAY", f"-> {k}")

    tut_cevaplari = [
        "KARAR: TUT. Henuz satmamaliyiz, trend yukari.",
        "KARAR: TUT - Satis icin erken, hedef fiyat uzak.",
        "KARAR: TUT\nBu seviyede satmak mantiksiz olur.",
        "KARAR: TUT. Satisi dusunmek icin neden yok.",
    ]
    for c in tut_cevaplari:
        k = aa.karar_oku(c, {"SAT", "TUT"})
        kontrol(f"TUT okunuyor: {c[:38]!r}", k == "TUT", f"-> {k}")

    k = aa.karar_oku("KARAR: SAT\nZarari kesmek gerekiyor.", {"SAT", "TUT"})
    kontrol("SAT okunuyor", k == "SAT", f"-> {k}")

    # Karar yoksa veya bicim bozuksa islem YAPILMAMALI (None donmeli)
    for bozuk in ["", None, "Bence alinabilir ama emin degilim.", "ONAY", "satilabilir"]:
        k = aa.karar_oku(bozuk, {"ONAY", "RET"})
        kontrol(f"Bicimsiz cevap None donuyor: {str(bozuk)[:28]!r}", k is None, f"-> {k}")

    # Yanlis kumeden karar sizmamali
    k = aa.karar_oku("KARAR: SAT", {"ONAY", "RET"})
    kontrol("SAT, alis kararina sizmiyor", k is None, f"-> {k}")


# ==========================================================================
def test_sayi():
    """None/metin/NaN/sonsuz degerler bicimlendirmeye sokulmadan yakalanmali."""
    print("\n[2] sayi — guvenli sayi cevrimi")
    kontrol("None -> None", aa.sayi(None) is None)
    kontrol("metin -> None", aa.sayi("abc") is None)
    kontrol("bos metin -> None", aa.sayi("") is None)
    kontrol("NaN -> None", aa.sayi(float("nan")) is None)
    kontrol("inf -> None", aa.sayi(float("inf")) is None)
    kontrol("-inf -> None", aa.sayi(float("-inf")) is None)
    kontrol("12.5 -> 12.5", aa.sayi(12.5) == 12.5)
    kontrol('"12.5" -> 12.5', aa.sayi("12.5") == 12.5)
    kontrol("0 -> 0.0", aa.sayi(0) == 0.0)
    kontrol("bicim None -> bilinmiyor", aa.bicim(None) == "bilinmiyor")
    kontrol("yuzde_bicim None -> bilinmiyor", aa.yuzde_bicim(None) == "bilinmiyor")
    kontrol("yuzde_bicim 0.281 -> %28.1", aa.yuzde_bicim(0.281) == "%28.1",
            f"-> {aa.yuzde_bicim(0.281)}")


# ==========================================================================
def test_rsi():
    """1 aylik veri isinmayi tamamlamiyordu; NaN RSI filtreden geciyordu."""
    print("\n[3] rsi_hesapla — Wilder RSI ve sinir durumlari")

    kontrol("Veri yetersiz (10 bar, periyot 14) -> None",
            aa.rsi_hesapla(pd.Series([float(100 + i) for i in range(10)]), 14) is None)

    kontrol("Bos seri -> None", aa.rsi_hesapla(pd.Series([], dtype=float), 14) is None)
    kontrol("None -> None", aa.rsi_hesapla(None, 14) is None)

    sabit = pd.Series([100.0] * 40)
    kontrol("Fiyat hic degismiyor -> None (eskiden NaN donup filtreden geciyordu)",
            aa.rsi_hesapla(sabit, 14) is None,
            f"-> {aa.rsi_hesapla(sabit, 14)}")

    artan = pd.Series([float(100 + i) for i in range(40)])
    r = aa.rsi_hesapla(artan, 14)
    kontrol("Surekli artan -> 100", r == 100.0, f"-> {r}")

    azalan = pd.Series([float(200 - i) for i in range(40)])
    r = aa.rsi_hesapla(azalan, 14)
    kontrol("Surekli azalan -> 0 civari", r is not None and r < 1.0, f"-> {r}")

    # Bilinen referans: Wilder RSI sinirlar icinde kalmali
    kapanis = pd.Series(
        [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
         45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
         46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18, 44.22, 44.57]
    )
    r = aa.rsi_hesapla(kapanis, 14)
    kontrol("Gercekci seri 0-100 arasinda", r is not None and 0 <= r <= 100, f"-> {r}")


# ==========================================================================
def test_portfoy_dogrulama():
    """Bozuk portfoy.json ve gecersiz kayitlar botu oldurmemeli."""
    print("\n[4] portfoy_yukle — bozuk dosya ve gecersiz kayit dayanikliligi")

    with tempfile.TemporaryDirectory() as gecici:
        kok = Path(gecici)
        eski = aa.PORTFOY_YOLU
        try:
            # (a) Dosya yok
            aa.PORTFOY_YOLU = kok / "yok.json"
            kontrol("Dosya yok -> bos sozluk", aa.portfoy_yukle() == {})

            # (b) Yarim yazilmis JSON (eskiden JSONDecodeError ile botu olduruyordu)
            yol = kok / "yarim.json"
            yol.write_text('{"ASELS.IS": {"alis_fiyati": 12', encoding="utf-8")
            aa.PORTFOY_YOLU = yol
            kontrol("Bozuk JSON -> bos sozluk, cokme yok", aa.portfoy_yukle() == {})
            kontrol("Bozuk dosya kenara alindi",
                    (kok / "yarim.json.bozuk").exists())

            # (c) Liste olarak kaydedilmis (eskiden AttributeError)
            yol = kok / "liste.json"
            yol.write_text("[]", encoding="utf-8")
            aa.PORTFOY_YOLU = yol
            kontrol("JSON listesi -> bos sozluk, cokme yok", aa.portfoy_yukle() == {})

            # (d) alis_fiyati eksik / sifir / metin (eskiden KeyError ve ZeroDivisionError)
            yol = kok / "gecersiz.json"
            yol.write_text(json.dumps({
                "A.IS": {"tarih": "2026-01-01"},              # alis_fiyati yok
                "B.IS": {"alis_fiyati": 0},                   # sifir -> bolme hatasi
                "C.IS": {"alis_fiyati": -5},                  # negatif
                "D.IS": {"alis_fiyati": "abc"},               # metin
                "E.IS": {"alis_fiyati": 12.5, "tarih": "x"},  # gecerli
                "F.IS": "duz metin",                          # sozluk degil
            }), encoding="utf-8")
            aa.PORTFOY_YOLU = yol
            p = aa.portfoy_yukle()
            kontrol("Sadece gecerli kayit kaliyor", list(p.keys()) == ["E.IS"], f"-> {list(p)}")
            kontrol("Gecerli kaydin fiyati float", p["E.IS"]["alis_fiyati"] == 12.5)
        finally:
            aa.PORTFOY_YOLU = eski


# ==========================================================================
def test_atomik_yazma():
    print("\n[5] json_yaz — atomik yazma ve geri okuma")
    with tempfile.TemporaryDirectory() as gecici:
        yol = Path(gecici) / "veri.json"
        aa.json_yaz(yol, {"a": 1, "turkce": "ÇĞİÖŞÜ"})
        kontrol("Dosya olustu", yol.exists())
        geri = json.loads(yol.read_text(encoding="utf-8"))
        kontrol("Icerik korunuyor", geri == {"a": 1, "turkce": "ÇĞİÖŞÜ"}, f"-> {geri}")
        kontrol("Gecici dosya temizlendi",
                not (Path(gecici) / "veri.json.tmp").exists())


# ==========================================================================
def test_eleme():
    """Eksik temel veri 999.0 sayilip hisseyi sessizce elemiyor; negatif F/K eleniyor."""
    print("\n[6] eleme_nedenleri — filtre mantigi")

    ayarlar = {
        "STRATEJI": {"RSI_AL_LIMIT": 45.0, "MAX_FK": 15.0, "MAX_PDDD": 3.0, "MIN_ROE": 0.15},
        "MIN_FK": 0.0,
        "EKSIK_TEMEL_VERI_ELENSIN": False,
    }

    uygun = {"sembol": "X.IS", "fiyat": 10.0, "rsi": 40.0, "fk": 5.0, "pddd": 1.2, "roe": 0.25}
    kontrol("Tum kosullar uygun -> elenmiyor", aa.eleme_nedenleri(uygun, ayarlar) == [],
            f"-> {aa.eleme_nedenleri(uygun, ayarlar)}")

    eksik = dict(uygun, fk=None, pddd=None, roe=None)
    kontrol("Temel veri eksik + bayrak False -> elenmiyor",
            aa.eleme_nedenleri(eksik, ayarlar) == [],
            f"-> {aa.eleme_nedenleri(eksik, ayarlar)}")

    ayarlar_siki = dict(ayarlar, EKSIK_TEMEL_VERI_ELENSIN=True)
    n = aa.eleme_nedenleri(eksik, ayarlar_siki)
    kontrol("Temel veri eksik + bayrak True -> eleniyor", len(n) == 3, f"-> {n}")

    negatif = dict(uygun, fk=-3.4)
    n = aa.eleme_nedenleri(negatif, ayarlar)
    kontrol("Negatif F/K eleniyor (zarar eden sirket)",
            any("zarar" in x for x in n), f"-> {n}")

    pahali_defter = dict(uygun, pddd=8.0)
    n = aa.eleme_nedenleri(pahali_defter, ayarlar)
    kontrol("MAX_PDDD artik uygulaniyor (eskiden hic kullanilmiyordu)",
            any("P/D-D/D" in x for x in n), f"-> {n}")

    yuksek_rsi = dict(uygun, rsi=70.0)
    kontrol("Yuksek RSI eleniyor", aa.eleme_nedenleri(yuksek_rsi, ayarlar) != [])

    dusuk_roe = dict(uygun, roe=0.02)
    n = aa.eleme_nedenleri(dusuk_roe, ayarlar)
    kontrol("Dusuk ROE eleniyor", any("ROE" in x for x in n), f"-> {n}")


# ==========================================================================
def test_piyasa_saati():
    print("\n[7] piyasa_acik — islem saatleri")
    ayarlar = {"PIYASA_ACILIS": "10:00", "PIYASA_KAPANIS": "18:10"}
    eski = aa.simdi
    try:
        for an, beklenen, ad in [
            (datetime(2026, 10, 3, 14, 0), True, "Cumartesi 14:00 -> kapali"),
            (datetime(2026, 10, 5, 9, 30), False, "Pazartesi 09:30 -> henuz acilmadi"),
            (datetime(2026, 10, 5, 11, 0), True, "Pazartesi 11:00 -> acik"),
            (datetime(2026, 10, 5, 18, 30), False, "Pazartesi 18:30 -> kapandi"),
            (datetime(2026, 10, 5, 3, 0), False, "Pazartesi 03:00 -> kapali"),
        ]:
            aa.simdi = lambda a=an: a
            acik, neden = aa.piyasa_acik(ayarlar)
            # Cumartesi testinde beklenen False; etiketi duzeltelim
            hedef = beklenen if an.weekday() < 5 else False
            kontrol(ad, acik == hedef, f"-> acik={acik} ({neden})")
    finally:
        aa.simdi = eski


# ==========================================================================
def test_telegram_mesaji():
    """AI metnindeki < > & ve * karakterleri HTML'i bozmamali."""
    print("\n[8] alis_mesaji — HTML kacirma ve uzunluk siniri")

    veri = {"sembol": "ASELS.IS", "fiyat": 12.3456, "rsi": 41.2,
            "fk": None, "pddd": 2.1, "roe": 0.22}
    kotu_metin = "KARAR: ONAY\n- F/K < 10 & cok iyi\n- *yildizli* <b>etiket</b>"
    mesaj = aa.alis_mesaji(veri, kotu_metin, "- haber <script>")

    kontrol("AI metnindeki < kacirildi", "&lt;" in mesaj)
    kontrol("AI metnindeki & kacirildi", "&amp;" in mesaj)
    kontrol("Ham <script> yok", "<script>" not in mesaj)
    kontrol("Kendi <b> etiketlerimiz duruyor", "<b>Hisse:</b>" in mesaj)
    kontrol("Eksik F/K bilinmiyor yaziyor", "bilinmiyor" in mesaj)
    kontrol("Uyari metni var", aa.UYARI_METNI in mesaj)

    uzun = aa.alis_mesaji(veri, "A" * 9000, "B" * 9000)
    kontrol("Telegram sinirina kirpiliyor", len(aa.kirp(uzun, aa.TELEGRAM_SINIR)) <= 4096,
            f"-> {len(aa.kirp(uzun, aa.TELEGRAM_SINIR))}")


# ==========================================================================
def test_durum_gun_degisimi():
    """Gunluk sinyal gecmisi saat 00 yerine TARIH degisimiyle sifirlanmali."""
    print("\n[9] durum_yukle — gun degisiminde sifirlama")
    with tempfile.TemporaryDirectory() as gecici:
        yol = Path(gecici) / "durum.json"
        eski = aa.DURUM_YOLU
        try:
            aa.DURUM_YOLU = yol

            # Dunun durumu -> sifirlanmali
            yol.write_text(json.dumps({
                "tarih": "2020-01-01",
                "sinyal_gecmisi": ["ASELS.IS", "GARAN.IS"],
                "ai_istek": 180,
            }), encoding="utf-8")
            d = aa.durum_yukle()
            kontrol("Eski tarih -> gecmis sifirlandi", d["sinyal_gecmisi"] == [])
            kontrol("Eski tarih -> AI sayaci sifirlandi", d["ai_istek"] == 0)

            # Bugunun durumu -> korunmali
            from datetime import date
            yol.write_text(json.dumps({
                "tarih": date.today().isoformat(),
                "sinyal_gecmisi": ["ASELS.IS"],
                "ai_istek": 5,
            }), encoding="utf-8")
            d = aa.durum_yukle()
            kontrol("Bugunun tarihi -> gecmis korunuyor", d["sinyal_gecmisi"] == ["ASELS.IS"])
            kontrol("Bugunun tarihi -> sayac korunuyor", d["ai_istek"] == 5)

            # Bozuk icerik -> cokmemeli
            yol.write_text("{bozuk", encoding="utf-8")
            d = aa.durum_yukle()
            kontrol("Bozuk durum dosyasi -> cokme yok", d["sinyal_gecmisi"] == [])
        finally:
            aa.DURUM_YOLU = eski


# ==========================================================================
def test_kota_kapisi():
    print("\n[10] AiKapisi — kota sinirlari")
    ayarlar = {
        "AI_MODEL": "test", "GOOGLE_API_KEY": "x",
        "AI_MAX_ISTEK_TUR": 3, "AI_MAX_ISTEK_GUN": 10, "AI_DAKIKADA_ISTEK": 8,
    }
    durum = {"tarih": "x", "sinyal_gecmisi": [], "ai_istek": 0}
    ai = aa.AiKapisi(ayarlar, durum, kapali=True)

    kontrol("Kapali kapi kota vermiyor", ai.kota_var_mi() is False)
    metin, hata = ai.sor("merhaba")
    kontrol("Kapali kapi cevap vermiyor", metin is None and "kapali" in hata, f"-> {hata}")

    ai.kapali = False
    kontrol("Acik kapi kota veriyor", ai.kota_var_mi() is True)
    ai.tur_istek = 3
    kontrol("Tur siniri dolunca kota yok", ai.kota_var_mi() is False)
    ai.tur_istek = 0
    durum["ai_istek"] = 10
    kontrol("Gunluk sinir dolunca kota yok", ai.kota_var_mi() is False)


# ==========================================================================
def test_hisse_listesi():
    print("\n[11] HISSELER — liste sagligi")
    kontrol("Tekrarlayan hisse yok", len(aa.HISSELER) == len(set(aa.HISSELER)),
            f"-> {len(aa.HISSELER)} / {len(set(aa.HISSELER))}")
    kontrol("Bosluk iceren sembol yok",
            all(s == s.strip() for s in aa.HISSELER))
    kontrol("Hepsi .IS ile bitiyor", all(s.endswith(".IS") for s in aa.HISSELER))
    kontrol("Olu KALES.IS listede degil", "KALES.IS" not in aa.HISSELER)
    kontrol("Liste bos degil", len(aa.HISSELER) > 50, f"-> {len(aa.HISSELER)}")


# ==========================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("BorsaAjan regresyon testleri (ag erisimi gerekmez)")
    print("=" * 70)

    aa.ciktiyi_utf8_yap()

    for t in (
        test_karar_oku,
        test_sayi,
        test_rsi,
        test_portfoy_dogrulama,
        test_atomik_yazma,
        test_eleme,
        test_piyasa_saati,
        test_telegram_mesaji,
        test_durum_gun_degisimi,
        test_kota_kapisi,
        test_hisse_listesi,
    ):
        t()

    print("\n" + "=" * 70)
    print(f"SONUC: {len(GECTI)} gecti, {len(KALDI)} kaldi")
    if KALDI:
        print("\nKalan testler:")
        for ad, ayrinti in KALDI:
            print(f"  - {ad}  {ayrinti}")
        sys.exit(1)
    print("Tum testler gecti.")
