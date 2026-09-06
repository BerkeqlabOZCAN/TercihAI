"""Tercih Robotu - yerel web arayuzu.

Standart kutuphane ile calisan kucuk bir HTTP sunucusu. Modern/animasyonlu
arayuzu (arayuz.html) sunar ve arama isteklerini mevcut tercih_robotu.py
filtreleme motoruyla yanitlar. Dis bagimlilik yoktur.

Calistirinca tarayicida otomatik acilir:
    python app.py
"""

import json
import re
import sys
import threading
import urllib.error
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import tercih_robotu as TR
import gemini
import groq

sys.stdout.reconfigure(encoding="utf-8")

HOST, PORT = "127.0.0.1", 8765
KOK = Path(__file__).parent
ARAYUZ = KOK / "arayuz.html"

# --- Veriyi bir kez yukle -------------------------------------------------
if not TR.VERI.exists():
    print("HATA: veri.json bulunamadı. Önce 'python veri_cek.py' çalıştırın.")
    sys.exit(1)

print("Veri yükleniyor...")
VERILER = json.loads(TR.VERI.read_text(encoding="utf-8"))
SEHIRLER = TR.build_sehir_index(VERILER)
SOZLUK = TR.build_program_sozlugu(VERILER)
UNI_SOZLUK = TR.build_universite_sozlugu(VERILER, SEHIRLER, SOZLUK)
print(f"{len(VERILER):,} program hazır.".replace(",", "."))
if groq.aktif():
    print(f"Yapay zeka: Groq ({groq.model()}) — çok hızlı, cömert ücretsiz kota.")
elif gemini.aktif():
    print(f"Yapay zeka: Gemini ({gemini.model()}) — hızlı, çevrimiçi.")
else:
    print("Yapay zeka: yerel Foundry Local (anahtar.txt yok, offline/yavaş).")

# LLM baglantisi tembel kurulur (ilk yorum isteginde)
LLM = {"endpoint": None, "model": None}   # metin modeli (yorum/sohbet)

# Kilavuz (basvuru/tercih PDF) indeksi tembel kurulur (ilk kilavuz sorusunda,
# ~5 sn). kilavuz.json yoksa None kalir ve bu ozellik pasif olur.
KILAVUZ = {"idx": None, "denendi": False}

KILAVUZ_SISTEM = (
    "Sen resmi YKS başvuru/tercih kılavuzunu bilen bir asistansın. Sana sorunun "
    "yanında kılavuzdan ilgili bölümler verilecek. Cevabını YALNIZCA bu bölümlere "
    "dayandır; bölümlerde yoksa 'Bu bilgi kılavuzda bulunamadı.' de, UYDURMA. "
    "Türkçe, kısa ve net yaz. Markdown/yıldız kullanma."
)


def _kilavuz_idx():
    if not KILAVUZ["denendi"]:
        KILAVUZ["denendi"] = True
        try:
            import kilavuz
            KILAVUZ["idx"] = kilavuz.yukle()
        except Exception:
            KILAVUZ["idx"] = None
    return KILAVUZ["idx"]


def _kilavuz_oai(soru: str):
    """Soru kilavuzla ilgiliyse grounded prompt dondurur; degilse None."""
    idx = _kilavuz_idx()
    if idx is None:
        return None
    hits = idx.ara(soru, k=6)
    if not hits or hits[0][0] < 0.15:   # alakasiz -> genel sohbete birak
        return None
    baglam = "\n\n".join(
        f"[{p['kaynak']} s.{p['sayfa']}]\n{p['metin']}" for _, p in hits)
    icerik = (f"Soru: {soru}\n\nKılavuzdan ilgili bölümler:\n{baglam}\n\n"
              f"Bu bölümlere dayanarak cevap ver. /no_think")
    return [{"role": "system", "content": KILAVUZ_SISTEM},
            {"role": "user", "content": icerik}]

SOHBET_SISTEM = (
    "Sen Türkçe konuşan, samimi ve yardımsever bir asistansın. İki işi de "
    "yaparsın: (1) günlük hayat ve genel bilgi sorularına normal, kısa ve net "
    "cevap verirsin; (2) üniversite/bölüm/tercih konusunda bir danışmansın. "
    "Kullanıcının son mesajına uygun GERÇEK programlar sana ayrıca verilirse, "
    "üniversite tavsiyeni SADECE o listeye dayandır; listede olmayan üniversite "
    "veya program UYDURMA. Genel sohbet sorularında bu listeyi görmezden gel. "
    "ÇOK ÖNEMLİ: Sana veri verilmediyse, ASLA kendi kafandan üniversite/bölüm "
    "listesi ya da puan/sıralama sayısı yazma (uydurma olur). Böyle bir liste "
    "istenirse 'Bunun için Arama sekmesini kullan ya da kriter belirt' de. "
    "Her zaman Türkçe yaz. Markdown kullanma; yıldız (*), kalın (**) ya da "
    "başlık (#) koyma."
)


def _llm_baglan():
    if LLM["model"] is None:
        LLM["endpoint"] = TR.get_service_endpoint()
        LLM["model"] = TR.resolve_model_id(LLM["endpoint"], TR.LLM_ALIAS)


def _llm_uret(messages: list[dict]) -> str:
    """Tek giris noktasi. anahtar.txt/ortam degiskenine gore saglayici secilir:
    Groq (gsk_...) -> Gemini (AIza.../AQ...) -> yerel Foundry Local. Cikti
    markdown'dan temizlenir."""
    for saglayici in (groq, gemini):        # ilk aktif olan kullanilir
        if saglayici.aktif():
            try:
                return markdown_temizle(saglayici.uret(messages))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    return ("Yapay zeka şu anki ücretsiz kullanım sınırına ulaştı. "
                            "Biraz sonra tekrar dener misin? (Arama sekmesi çalışıyor.)")
                return f"Yapay zekaya bağlanılamadı (HTTP {e.code})."
            except Exception as e:
                return f"Yapay zekaya bağlanılamadı: {e}"
    # anahtar yoksa yerel model
    _llm_baglan()
    parcalar = list(TR.chat_stream(LLM["endpoint"], LLM["model"], messages))
    return markdown_temizle("".join(parcalar))


def deterministik_oneri(soru: str, sonuc: list[dict]) -> str:
    """Program onerisini DOGRUDAN veriden olusturur (LLM sayi uretmez -> uydurma
    riski sifir). Sonuclar zaten basari sirasina gore sirali gelir."""
    # Istenen adet: "5 tane", "3 universite" ... yoksa 8
    m = re.search(r"\b(\d{1,2})\s*(tane|adet|üniversite|universite|program|bölüm|bolum|okul)",
                  TR.tr_lower(soru))
    n = max(1, min(int(m.group(1)), 25)) if m else 8

    satirlar = ["İşte kriterlerine uyan programlar (giriş başarı sırasına göre, "
                "en rekabetçiden):\n"]
    for i, v in enumerate(sonuc[:n], 1):
        bs = v.get("basari_sirasi")
        bs_txt = f"{bs:,}".replace(",", ".") if bs and bs > 0 else "dolmadı"
        tp = v.get("taban_puan")
        tp_txt = f"{tp:.2f}" if isinstance(tp, (int, float)) and tp else "-"
        rozet = " · ".join(x for x in [
            v.get("sehir"), v.get("universite_turu"),
            v.get("burs") or "Ücretsiz", v.get("ogrenim_dili"),
            f"{v.get('ogrenim_suresi')} yıl" if v.get("ogrenim_suresi") else None,
        ] if x)
        satirlar.append(
            f"{i}. {v.get('universite','')} — {v.get('program','')}\n"
            f"   Başarı sırası: {bs_txt} · Taban puan: {tp_txt} · {rozet} · "
            f"Kontenjan: {v.get('kontenjan','-')}")
    toplam = len(sonuc)
    if toplam > n:
        satirlar.append(f"\n(Kriterlere uyan toplam {toplam} program var; ilk {n} "
                        f"gösterildi. Daha fazlası için Arama sekmesini kullanabilirsin.)")
    return "\n".join(satirlar)


def _birlesik_filtre(f_now: dict, dilim: list[dict], son_user: int) -> dict:
    """Cok turlu baglam: son mesaj bir 'daralt(ma)' ise (kendi bolum adi/uni yok,
    sadece siralama/sehir/tur ekliyor) onceki kullanici turundaki bolum baglamini
    devralir. 'yapay zeka programlari' -> '120 binden sonraki' -> yapay zeka +
    siralama olarak birlesir."""
    if f_now["anahtar"] or f_now["universite"]:
        return f_now   # kendi bolum/universite baglami var -> yeni sorgu
    onceki = None
    for i in range(son_user - 1, -1, -1):     # en yakin onceki kullanici turu
        m = dilim[i]
        if m.get("rol") in ("asistan", "assistant"):
            continue
        pf = TR.parse_query(str(m.get("icerik", "")), SEHIRLER, SOZLUK, UNI_SOZLUK)
        if pf["anahtar"] or pf["universite"] or pf["sehir"] or pf["siralama"]:
            onceki = pf
            break
    if not onceki:
        return f_now
    for alan in ("puan_turu", "universite_turu", "sehir", "dil", "seviye",
                 "universite", "burs", "anahtar"):
        if not f_now[alan]:
            f_now[alan] = onceki[alan]
    if f_now["siralama"] is None:
        f_now["siralama"] = onceki["siralama"]
    return f_now


def _grounded_oneri(soru: str, sonuc: list[dict]) -> list[dict]:
    """Universite sorusu icin KANITLANMIS tek-turlu oneri promptu (gercek veriye
    sadik). Sohbet formati kucuk modelde grounding'i bozdugu icin bu yol kullanilir."""
    icerik = (
        f"Öğrencinin sorusu: {soru}\n\n"
        f"Aşağıda bu soruya uyan GERÇEK programlar var. Her program için elimizdeki "
        f"veri: üniversite, bölüm, şehir, tür (devlet/vakıf), burs ve başarı sırası.\n"
        f"{TR.llm_baglam(sonuc)}\n\n"
        f"Görev: Yukarıdaki listeden en uygun programları öner.\n"
        f"ÇOK ÖNEMLİ KURALLAR:\n"
        f"- Başarı sırası sayılarını yukarıdaki listeden HARFİYEN kopyala. "
        f"ASLA kendin sayı uydurma, tahmin etme veya değiştirme.\n"
        f"- Listede OLMAYAN üniversite/program EKLEME.\n"
        f"- Öğrenci ELİMİZDE OLMAYAN bir şey sorduysa (memnuniyet, iş bulma oranı, "
        f"kampüs, öğretim kalitesi, akademik kadro vb.) bunu DÜRÜSTÇE söyle: "
        f"'Elimde ... verisi yok' de ve elindeki veriyle (başarı sırasına göre) "
        f"en iyi seçenekleri sun. O veriyi varmış gibi UYDURMA.\n"
        f"- Öğrenci bir sayı belirttiyse (örn. '5 tane') o kadar öner.\n"
        f"- Kendini tekrar etme. /no_think")
    return [{"role": "system", "content": TR.LLM_SISTEM},
            {"role": "user", "content": icerik}]


SAYI_SORUSU = ("kaç", "sayısı", "kaç tane", "kaçtır", "ne kadar", "toplam")
ONERI_ISTEGI = ("gir", "öner", "oner", "tavsiye", "yerleş", "nereye", "hangi bölüm",
                "hangi program")
# Elimizdeki veride OLMAYAN kriterler. Soru bunlardan birini iceriyorsa, cevabin
# basina "bu veri yok, siralama basari sirasina gore" uyarisi eklenir (LLM bunu
# her zaman kendi soylemedigi icin garanti altina aliriz).
EKSIK_VERI = {
    "memnun": "öğrenci memnuniyeti", "memnuniyet": "öğrenci memnuniyeti",
    "iş bulma": "iş bulma / istihdam", "istihdam": "istihdam",
    "iş imkan": "iş imkânı", "kampüs": "kampüs", "kampus": "kampüs",
    "yurt imkan": "yurt", "eğitim kalite": "eğitim kalitesi",
    "kaliteli": "eğitim kalitesi", "akademik kadro": "akademik kadro",
    "hoca": "akademik kadro", "mezun": "mezun/istihdam",
}
# Kilavuz yoluna ancak bunlardan biri gecerse gidilir (selamlama vb. yanlis
# eslesmesin diye). Karakter n-gram TF-IDF yaygin kelimelerle yanilabiliyor.
KILAVUZ_ANAHTAR = ("başvuru", "kılavuz", "ücret", "ösym", "osym", "sınav", "yerleştir",
                   "kayıt", "belge", "şart", "koşul", "engelli", "rapor", "itiraz",
                   "sonuç açıkla", "başvuru tarih", "yatay geçiş", "ek yerleştir",
                   "diploma", "obp", "kesin kayıt", "e-devlet", "e-okul", "aöf",
                   "burs koşul", "sınava gir", "geç kayıt", "nasıl başvur")


def _veri_ozeti(f: dict) -> str:
    """Sayi sorusu icin: filtreye uyan program ve farkli universite sayilari."""
    alt = dict(f)
    alt["siralama"] = None  # sayimda siralama sinirini uygulama
    sonuc = TR.filtrele(VERILER, alt)
    uniler = {v.get("universite", "") for v in sonuc}
    return (f"Elimizdeki 2025 tercih verisine göre bu kritere uyan "
            f"{len(uniler)} farklı üniversite ve {len(sonuc)} program var.")


def sohbet(mesajlar: list[dict]) -> str:
    """Cok turlu sohbet. mesajlar = [{"rol":"user"/"asistan","icerik":"..."}].
    Niyet yonlendirmesi:
    - Oneri istegi/terse kriter -> gercek veriye sadik tek-turlu oneri.
    - Sayi/olgu sorusu -> veriden hesaplanan ozetle genel sohbet.
    - Digerleri -> genel sohbet asistani."""
    if not mesajlar:
        return "Merhaba! Sana nasıl yardımcı olabilirim?"

    dilim = mesajlar[-12:]  # son 12 tur (baglami makul tut)
    son_user = max((i for i, m in enumerate(dilim)
                    if m.get("rol") not in ("asistan", "assistant")), default=-1)
    son_soru = str(dilim[son_user].get("icerik", "")) if son_user >= 0 else ""
    son_l = TR.katla(son_soru)   # diakritiksiz: 'ucret'~'ücret', 'kac'~'kaç'
    sayi_sorusu = any(TR.katla(k) in son_l for k in SAYI_SORUSU)
    oneri_ister = any(TR.katla(k) in son_l for k in ONERI_ISTEGI)

    f = TR.parse_query(son_soru, SEHIRLER, SOZLUK, UNI_SOZLUK)
    kilavuz_ister = any(TR.katla(k) in son_l for k in KILAVUZ_ANAHTAR)
    # Program onerisi niyeti: sadece universite/sehir adi yetmez; siralama,
    # bolum adi ya da acik oneri istegi olmali (yoksa 'firat erasmus' gibi bilgi
    # sorulari yanlislikla program onerisine kacar).
    program_niyeti = bool(f["siralama"] or f["anahtar"] or oneri_ister)

    # 1) KILAVUZ onceligi: basvuru/sinav/ucret gibi kelimeler varsa once kilavuza
    #    bak (sayi/siralama parse'i yanlislikla program aramasina kacirmasin).
    oai = _kilavuz_oai(son_soru) if (son_soru and kilavuz_ister) else None

    onek = ""  # cevabin basina eklenecek uyari (elimizde olmayan veri sorulunca)

    # 2) ONERI: acik program niyeti var, sayi sorusu degil
    if oai is not None:
        pass
    elif son_soru and program_niyeti and not TR.filtre_bos(f) and (oneri_ister or not sayi_sorusu):
        f = _birlesik_filtre(f, dilim, son_user)   # onceki turun bolum baglami
        sonuc = TR.filtrele(VERILER, f)
        if not sonuc:
            return ("Bu kriterlere uyan program bulamadım. Sıralamanı ya da "
                    "şehri değiştirip tekrar sorar mısın?")
        # Sayilar/programlar DOGRUDAN veriden -> LLM'e uydurma sansi verilmez.
        eksik = next((etiket for k, etiket in EKSIK_VERI.items()
                      if TR.katla(k) in son_l), None)
        if eksik:
            onek = (f"Not: Elimde {eksik} verisi yok; aşağıdaki sıralama "
                    f"programların giriş başarı sırasına (rekabet düzeyine) göredir.\n\n")
        return onek + deterministik_oneri(son_soru, sonuc)
    elif sayi_sorusu and not TR.filtre_bos(f):   # 3) VERİDEN SAYIM
        oai = [{"role": "system", "content": SOHBET_SISTEM}]
        for i, m in enumerate(dilim):
            rol = "assistant" if m.get("rol") in ("asistan", "assistant") else "user"
            icerik = str(m.get("icerik", ""))
            if i == son_user:
                icerik += f"\n\n[Kesin veri: {_veri_ozeti(f)} Bu sayıyı kullan.]"
                icerik += " /no_think"
            oai.append({"role": rol, "content": icerik})
    else:                                        # 4) GENEL SOHBET
        oai = [{"role": "system", "content": SOHBET_SISTEM}]
        for i, m in enumerate(dilim):
            rol = "assistant" if m.get("rol") in ("asistan", "assistant") else "user"
            icerik = str(m.get("icerik", ""))
            if i == son_user:
                icerik += " /no_think"
            oai.append({"role": rol, "content": icerik})

    return onek + _llm_uret(oai)


def ara(q: str) -> dict:
    f = TR.parse_query(q, SEHIRLER, SOZLUK, UNI_SOZLUK)
    if TR.filtre_bos(f):
        return {"filtre": "", "toplam": 0, "sonuclar": [],
                "uyari": "Sorguda tanıdığım bir kriter yok. Şehir, sıralama, "
                         "puan türü ya da bölüm adı yazın."}
    sonuc = TR.filtrele(VERILER, f)
    return {
        "filtre": TR.ozetle(f),
        "toplam": len(sonuc),
        "sonuclar": sonuc[:100],  # arayuze en fazla 100 kayit
    }


def markdown_temizle(t: str) -> str:
    """Model yer yer markdown uretiyor (**, -, #); arayuz duz metin gosterdigi
    icin bu isaretleri temizler."""
    t = t.replace("**", "").replace("__", "").replace("`", "")
    # Llama bazen Cince/Japonca/Korece token sizdiriyor -> at (Turkce'de gecmez)
    t = re.sub(r"[぀-ヿ㐀-鿿가-힯]+", "", t)
    t = re.sub(r"(?m)^\s*#+\s*", "", t)            # basliklar (#)
    t = re.sub(r"(?m)^\s*[-*•·]\s+", "• ", t)      # madde isaretleri -> tek tip
    t = re.sub(r"\*(.+?)\*", r"\1", t)             # *italik* -> italik
    t = t.replace("*", "")                          # kalan tekil yildizlar
    t = re.sub(r"[ \t]+\n", "\n", t)               # satir sonu bosluklar
    t = re.sub(r"[ \t]{2,}", " ", t)               # ic ice bosluklar
    t = re.sub(r"\n{3,}", "\n\n", t)               # fazla bos satir
    return t.strip()


def yorum(q: str) -> str:
    """Filtre sonuclarini LLM ile yorumlar (yavas)."""
    f = TR.parse_query(q, SEHIRLER, SOZLUK, UNI_SOZLUK)
    if TR.filtre_bos(f):
        return ("Merhaba! Sana tercih önerisi yapabilmem için ne aradığını "
                "söylemen yeterli: sıralaman, şehir, puan türü ya da bölüm adı. "
                "Örnek: \"290 bin sayısal, İstanbul, bilgisayar mühendisliği\".")
    sonuc = TR.filtrele(VERILER, f)
    if not sonuc:
        return ("Bu kriterlere uyan program bulamadım. Sıralamanı ya da şehri "
                "değiştirip tekrar dener misin?")
    icerik = (f"Öğrencinin sorusu: {q}\n\n"
              f"Bu soruya uyan gerçek programlar:\n{TR.llm_baglam(sonuc)}\n\n"
              f"Bu programlara göre tavsiyeni ver. /no_think")
    messages = [{"role": "system", "content": TR.LLM_SISTEM},
                {"role": "user", "content": icerik}]
    return _llm_uret(messages)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # sessiz

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            html = ARAYUZ.read_text(encoding="utf-8").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if path == "/api/ara":
            q = parse_qs(parsed.query).get("q", [""])[0]
            self._json(ara(q))
            return

        if path == "/api/yorum":
            q = parse_qs(parsed.query).get("q", [""])[0]
            try:
                self._json({"yorum": yorum(q)})
            except Exception as e:
                self._json({"yorum": f"Yapay zekaya bağlanılamadı: {e}"}, code=200)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/sohbet":
            self.send_response(404)
            self.end_headers()
            return
        try:
            uzunluk = int(self.headers.get("Content-Length", 0))
            veri = json.loads(self.rfile.read(uzunluk).decode("utf-8")) if uzunluk else {}
            mesajlar = veri.get("mesajlar", [])
            self._json({"cevap": sohbet(mesajlar)})
        except Exception as e:
            self._json({"cevap": f"Yapay zekaya bağlanılamadı: {e}"}, code=200)


def main():
    # Port doluysa (eski bir surum acik kalmissa) sonrakini dene
    server = None
    port = PORT
    for aday in range(PORT, PORT + 12):
        try:
            server = ThreadingHTTPServer((HOST, aday), Handler)
            port = aday
            break
        except OSError:
            continue
    if server is None:
        print("Uygun port bulunamadı. Açık kalan bir pencere olabilir.")
        return
    url = f"http://{HOST}:{port}/"
    print(f"\nTercih Robotu arayüzü çalışıyor: {url}")
    print("Kapatmak için bu pencereyi kapatın veya Ctrl+C.\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nKapatılıyor...")
        server.shutdown()


if __name__ == "__main__":
    main()
