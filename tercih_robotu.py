"""Yerel tercih robotu (resmi YKS tercih verisiyle calisir).

Tamamen cevrimdisi ve tamamen bizim kodumuz:
- Veri      : veri_cek.py ile indirilen veri.json (resmi tercih kilavuzu verisi)
- Filtreleme: saf Python (anlik, deterministik) -- dogal dil sorgusunu ayristirir
- Yorum     : ISTEGE BAGLI olarak Foundry Local (qwen3-4b) sonuclari Turkce yorumlar

Kullanim:
    python tercih_robotu.py

Ornek sorular:
    480 bin siralamayla istanbul'da hangi bilgisayar bolumlerine girerim
    ankara devlet universitesi tip
    izmir vakif hukuk burslu
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

VERI = Path(__file__).parent / "veri.json"
GOSTER = 25         # ekranda gosterilecek program sayisi
LLM_ALIAS = "qwen3-4b"  # yorum icin kullanilacak Foundry Local modeli
LLM_GIRDI = 15      # LLM'e verilecek en iyi program sayisi


# --------------------------------------------------------------------------
# Turkce metin yardimcilari
# --------------------------------------------------------------------------

def tr_lower(s: str) -> str:
    return (s or "").replace("I", "ı").replace("İ", "i").lower()


_KATLA = str.maketrans("çşğüöıÇŞĞÜÖİI", "csguoicsguoii")


def katla(s: str) -> str:
    """Diakritikleri kaldirir + kucuk harf: 'Uçak'->'ucak', 'Mühendisliği'->
    'muhendisligi', 'ELAZIĞ'->'elazig'. Kullanicilar ç/ş/ğ/ü/ö/ı'siz yazsa da
    eslesme calissin diye."""
    return (s or "").translate(_KATLA).lower()


def parse_siralama(text: str) -> int | None:
    """'480 bin', '1.5 milyon', '1,5 milyon', '480.000', '480000' -> tam sayi siralama."""
    t = tr_lower(text)
    
    # Milyon tespiti (Nokta veya virgüllü ondalıkları destekler)
    m = re.search(r"(\d[\d.,\s]*)\s*milyon", t)
    if m:
        val_str = m.group(1).replace(" ", "")
        val_str = val_str.replace(",", ".")
        try:
            return int(float(val_str) * 1_000_000)
        except ValueError:
            pass

    # Bin tespiti (Ondalık veya düz sayıları destekler, örn: "480 bin", "1.5 bin")
    m = re.search(r"(\d[\d.,\s]*)\s*bin", t)
    if m:
        val_str = m.group(1).replace(" ", "")
        val_str = val_str.replace(",", ".")
        try:
            return int(float(val_str) * 1_000)
        except ValueError:
            pass

    # duz sayi (nokta binlik ayraci olabilir): en az 3 haneli
    m = re.search(r"\b(\d{1,3}(?:\.\d{3})+|\d{3,})\b", t)
    if m:
        return int(m.group(1).replace(".", ""))

    return None


PUAN_TURLERI = {"say": "SAY", "sayısal": "SAY", "sayisal": "SAY",
                "ea": "EA", "eşit": "EA", "esit": "EA","esıt":"EA","eşıt":"EA",
                "söz": "SÖZ", "soz": "SÖZ", "sözel": "SÖZ", "sozel": "SÖZ",
                "dil": "DİL", "tyt": "TYT"}
UNI_TURLERI = {"devlet": "DEVLET", "vakıf": "VAKIF", "vakif": "VAKIF",
               "özel": "VAKIF", "ozel": "VAKIF", "kktc": "KKTC"}
# Sehir adina eklenebilen Turkce ekler (elazığ+da, izmir+de, ankara+dan...)
SEHIR_EKLERI = ("ndan", "nden", "dan", "den", "tan", "ten", "nda", "nde",
                "da", "de", "ta", "te", "ya", "ye")
# Filtre kelimesi olup program adi sanilmamasi gereken kelimeler
DURDURMA = {"siralama", "sıralama", "siralamayla", "sıralamayla", "ile", "hangi",
            "bolum", "bölüm", "bolumler", "bölümler", "bolumlere", "bölümlere",
            "bolumleri", "bölümleri", "girerim", "girebilirim", "gidebilirim",
            "universite", "üniversite", "universitesi", "üniversitesi", "de", "da",
            "ta", "te", "nerede", "nereye", "nereleri", "nereler", "icin", "için",
            "puani", "puanı", "puanim", "puanım", "burslu", "ucretsiz", "ücretsiz",
            "ucretli", "ücretli", "bin", "milyon", "ve", "bir", "var", "benim",
            "yer", "yeri", "yerler", "yerleri", "yerlere", "tercih", "tercihler",
            "edebilirim", "yapabilirim", "olan", "hangisi", "hangileri", "misin",
            "goster", "göster", "oner", "öner", "onerir", "önerir", "liste",
            "listesi", "okumak", "istiyorum", "isterim", "bana",
            "ağırlık", "agirlik",
            # siralama ifadelerindeki genel kelimeler (bolum adi degil)
            "ilk", "ust", "üst", "alt", "girmis", "girmiş", "biri", "kisi", "kişi",
            "çok", "cok", "en", "memnun", "tane", "sırala", "sirala", "adet",
            "kaliteli", "iyi", "kalınan", "kalinan", "populer", "popüler",
            # 'program' ailesi bazi bolum adlarinda gecse de genel kelimedir
            "program", "programlar", "programi", "programı", "programlari",
            "programları", "programa", "programlara", "girebileceğim",
            "girebilecegim", "gireceğim", "girecegim","burslu","burs"
            "lisans", "önlisans", "onlisans", "türkçe", "turkce", "ingilizce"}


def build_sehir_index(veriler: list[dict]) -> set[str]:
    return {katla(v["sehir"]) for v in veriler if v.get("sehir")}


def build_program_sozlugu(veriler: list[dict]) -> set[str]:
    """Tum program adlarinda gecen kelimeleri (diakritiksiz) toplar. Bir sorgu
    kelimesi ancak bu sozlukte varsa 'program adi filtresi' sayilir; boylece
    'girebileceğim', 'programlar', 'var' gibi konusma kelimeleri filtreye
    donusup sonucu sifirlamaz."""
    kelimeler: set[str] = set()
    for v in veriler:
        metin = katla(v.get("program", ""))  # sadece program adi (fakulte degil)
        for kel in re.findall(r"[a-z0-9]+", metin):
            if len(kel) >= 3:
                kelimeler.add(kel)
    return kelimeler


# Yaygin universite kisaltmalari -> universite adinda gecen ayirt edici metin
UNI_KISALTMA = {
    "itü": "istanbul teknik", "itu": "istanbul teknik",
    "odtü": "orta doğu", "odtu": "orta doğu", "metu": "orta doğu",
    "ytü": "yıldız teknik", "ytu": "yıldız teknik",
    "boun": "boğaziçi", "gtü": "gebze teknik", "gtu": "gebze teknik",
    "ktü": "karadeniz teknik", "ktu": "karadeniz teknik",
    "iyte": "izmir yüksek teknoloji", "ytü": "yıldız teknik",
    "gtü": "gebze teknik", "erü": "erciyes", "eskişehir": "eskişehir",
}
# Universite adlarinda gecse de filtre olmamasi gereken genel kelimeler
UNI_GENEL = {"üniversitesi", "üniversite", "teknik", "yüksek", "teknoloji",
             "enstitüsü", "ve", "bilim", "bilimleri", "büyük", "milli",
             "savunma", "sağlık", "güzel", "sanatlar", "ileri"}

# --- Sabitlerin diakritiksiz (katlanmis) versiyonlari: sorgu tokenlari da
#     katlanmis geldigi icin eslesme bunlar uzerinden yapilir ---
PUAN_TURLERI_K = {katla(k): v for k, v in PUAN_TURLERI.items()}
UNI_TURLERI_K = {katla(k): v for k, v in UNI_TURLERI.items()}
UNI_KISALTMA_K = {katla(k): katla(v) for k, v in UNI_KISALTMA.items()}
UNI_GENEL_K = {katla(x) for x in UNI_GENEL}
DURDURMA_K = {katla(x) for x in DURDURMA}


def build_universite_sozlugu(veriler: list[dict], sehirler: set[str],
                             program_sozlugu: set[str]) -> set[str]:
    """Universite adlarindaki ayirt edici kelimeleri (diakritiksiz) toplar
    (bogazici, hacettepe, koc...). Sehir adlarini, genel kelimeleri ve program
    kelimelerini haric tutar ki 'istanbul' sehir, 'bilgisayar' bolum olarak kalsin."""
    kelimeler: set[str] = set()
    for v in veriler:
        for kel in re.findall(r"[a-z0-9]+", katla(v.get("universite", ""))):
            if (len(kel) >= 3 and kel not in sehirler and kel not in UNI_GENEL_K
                    and kel not in program_sozlugu):
                kelimeler.add(kel)
    return kelimeler


def program_kelimesi_mi(token: str, sozluk: set[str]) -> bool:
    """Token bir program adinda geciyor mu? Turkce ekleri hosgormek icin
    ('mühendislik' ~ 'mühendisliği') onek eslesmesi de dener."""
    if token in sozluk:
        return True
    # sorgu koku, sozlukteki daha uzun bir kelimenin basiysa (muhendis -> muhendislik)
    if len(token) >= 4 and any(k.startswith(token) for k in sozluk):
        return True
    return False


def eslesen_sehir(token: str, sehirler: set[str]) -> str | None:
    """Token bir sehir mi? Once dogrudan, sonra Turkce ekleri soyarak dener
    ('elazığda' -> 'elazığ', 'izmirde' -> 'izmir')."""
    if token in sehirler:
        return token
    for ek in SEHIR_EKLERI:  # uzun ekler once denensin diye tuple sirali
        if token.endswith(ek):
            kok = token[: -len(ek)]
            if kok in sehirler:
                return kok
    return None


def eslesen_kisaltma(token: str) -> str | None:
    """Token (katlanmis) bir universite kisaltmasi mi? Ekli halleri de dener
    ('odtude' -> 'odtu', 'ituye' -> 'itu')."""
    if token in UNI_KISALTMA_K:
        return UNI_KISALTMA_K[token]
    for ek in SEHIR_EKLERI:
        if token.endswith(ek):
            kok = token[: -len(ek)]
            if kok in UNI_KISALTMA_K:
                return UNI_KISALTMA_K[kok]
    return None


def parse_query(text: str, sehirler: set[str], program_sozlugu: set[str],
                uni_sozlugu: set[str] | None = None) -> dict:
    """Dogal dil sorgusunu yapisal filtreye cevirir. Tokenlar diakritiksiz
    (katlanmis) islenir; kullanici 'ucak muhendisligi' yazsa da eslesir."""
    tokens = re.findall(r"[a-z0-9]+", katla(text))   # hepsi katlanmis

    f = {"siralama": parse_siralama(text), "puan_turu": None,
         "universite_turu": None, "sehir": None, "burs": None,
         "dil": None, "seviye": None, "universite": None, "anahtar": []}

    if "burslu" in tokens:
        f["burs"] = "burslu"
    elif "ucretsiz" in tokens:
        f["burs"] = "ucretsiz"

    for tok in tokens:
        sehir = eslesen_sehir(tok, sehirler)
        kisaltma = eslesen_kisaltma(tok)
        if tok in PUAN_TURLERI_K and not f["puan_turu"]:
            f["puan_turu"] = PUAN_TURLERI_K[tok]
        elif tok in UNI_TURLERI_K and not f["universite_turu"]:
            f["universite_turu"] = UNI_TURLERI_K[tok]
        elif tok in ("turkce",) and not f["dil"]:
            f["dil"] = "turkce"
        elif tok in ("ingilizce", "inglizce") and not f["dil"]:
            f["dil"] = "ingilizce"
        elif tok in ("onlisans",) and not f["seviye"]:
            f["seviye"] = "onlisans"
        elif tok == "lisans" and not f["seviye"]:
            f["seviye"] = "lisans"
        elif kisaltma and not f["universite"]:
            f["universite"] = kisaltma
        elif sehir and not f["sehir"]:
            f["sehir"] = sehir
        # Ayirt edici universite adi kelimesi (bogazici, hacettepe, koc...)
        elif uni_sozlugu and tok in uni_sozlugu and not f["universite"]:
            f["universite"] = tok
        # Sadece gercekten bir program adinda gecen kelimeler filtre olur
        # (genel konusma/yapisal kelimeler DURDURMA ile elenir)
        elif (tok not in DURDURMA_K
              and not tok.startswith(("siralama", "puan"))
              and program_kelimesi_mi(tok, program_sozlugu)):
            f["anahtar"].append(tok)

    return f


# --------------------------------------------------------------------------
# Filtreleme
# --------------------------------------------------------------------------

def filtre_bos(f: dict) -> bool:
    """Sorgudan hicbir kriter cikmadi mi? (anlamsiz/taninmayan sorgu)"""
    return not any([f["siralama"], f["puan_turu"], f["universite_turu"],
                    f["sehir"], f["burs"], f["dil"], f["seviye"],
                    f["universite"], f["anahtar"]])


def filtrele(veriler: list[dict], f: dict) -> list[dict]:
    sonuc = []
    for v in veriler:
        if f["puan_turu"] and v.get("puan_turu") != f["puan_turu"]:
            continue
        if f["universite_turu"] and v.get("universite_turu") != f["universite_turu"]:
            continue
        if f["sehir"] and katla(v.get("sehir", "")) != f["sehir"]:
            continue
        if f["universite"] and f["universite"] not in katla(v.get("universite", "")):
            continue
        if f["burs"]:
            burs = katla(v.get("burs", ""))
            if f["burs"] == "burslu" and "burslu" not in burs:
                continue
            if f["burs"] == "ucretsiz" and burs not in ("", "ucretsiz"):
                continue
        if f["dil"]:
            dil = katla(v.get("ogrenim_dili", ""))
            if not dil.startswith(f["dil"]):  # 'ingilizce' -> 'İngilizce' ve 'İngilizce (%30)'
                continue
        if f["seviye"]:
            sure = v.get("ogrenim_suresi") or 0
            if f["seviye"] == "onlisans" and sure != 2:
                continue
            if f["seviye"] == "lisans" and sure < 4:
                continue
        if f["anahtar"]:
            # Yalnizca PROGRAM adinda ara; fakulte adinda arama, cunku
            # 'Mimarlik ve Muhendislik Fakultesi' gibi adlar alakasiz
            # bolumleri sonuca katiyordu.
            hedef = katla(v.get("program", ""))
            # Turkce ek toleransi: 'muhendislik' -> 'muhendisligi' eslessin diye
            # uzun kelimelerde son 2 harfi (eki) dusurup kok olarak da dene.
            def _eslesir(k: str) -> bool:
                return k in hedef or (len(k) > 5 and k[:-2] in hedef)
            if not all(_eslesir(k) for k in f["anahtar"]):
                continue
        # Siralama filtresi: adayin sirasi, programin taban sirasindan kucuk/esitse girer
        if f["siralama"] is not None:
            bs = v.get("basari_sirasi")
            if not bs or bs <= 0:  # dolmayan / siralamasiz programlar
                continue
            if bs < f["siralama"]:  # programin tabani adaydan daha iyi -> giremez
                continue
        sonuc.append(v)

    # En rekabetci (dusuk basari sirasi) once; siralamasizlar sona
    sonuc.sort(key=lambda v: (v.get("basari_sirasi") or 10**9))
    return sonuc


def ozetle(f: dict) -> str:
    parts = []
    if f["siralama"] is not None:
        parts.append(f"{f['siralama']:,} sıralama".replace(",", "."))
    if f["puan_turu"]:
        parts.append(f["puan_turu"])
    if f["universite_turu"]:
        parts.append(f["universite_turu"])
    if f["sehir"]:
        parts.append(f["sehir"].capitalize())
    if f["universite"]:
        parts.append(f["universite"].title())
    if f["burs"]:
        parts.append(f["burs"])
    if f["dil"]:
        parts.append(f["dil"].capitalize())
    if f["seviye"]:
        parts.append("Önlisans" if f["seviye"] == "onlisans" else "Lisans")
    if f["anahtar"]:
        parts.append(" ".join(f["anahtar"]))
    return " | ".join(parts) if parts else "(filtre yok - tüm programlar)"


def yazdir(sonuc: list[dict], f: dict) -> None:
    print(f"\n  Filtre: {ozetle(f)}")
    print(f"  Eşleşen program sayısı: {len(sonuc)}\n")
    if not sonuc:
        print("  Bu kriterlere uyan program bulunamadı.\n")
        return
    for i, v in enumerate(sonuc[:GOSTER], 1):
        bs = v.get("basari_sirasi")
        bs_txt = f"{bs:,}".replace(",", ".") if bs and bs > 0 else "dolmadı"
        tp = v.get("taban_puan")
        tp_txt = f"{tp:.2f}" if isinstance(tp, (int, float)) and tp else "-"
        print(f"  {i:>2}. {v.get('universite','')} — {v.get('program','')}")
        print(f"      {v.get('sehir','')} | {v.get('universite_turu','')} | "
              f"{v.get('puan_turu','')} | {v.get('burs') or 'Ücretsiz'} | "
              f"Taban: {tp_txt} | Başarı sırası: {bs_txt} | Kont: {v.get('kontenjan','-')}")
    if len(sonuc) > GOSTER:
        print(f"\n  ... ve {len(sonuc) - GOSTER} program daha (ilk {GOSTER} gösterildi).")
    print()


# --------------------------------------------------------------------------
# LLM yorum katmani (Foundry Local, ISTEGE BAGLI)
#
# Filtreleme her zaman Python'da yapilir; LLM yalnizca ZATEN filtrelenmis
# gercek programlari alip yorumlar. Boylece uydurma sonuc uretemez.
# --------------------------------------------------------------------------

LLM_SISTEM = (
    "Sen bir universite tercih danismanisin ve YALNIZCA Turkce konusursun; "
    "cevabina baska dilde tek kelime karistirma. Sana bir ogrencinin sorusu ve "
    "bu soruya uyan GERCEK programlarin listesi verilecek. SADECE bu listedeki "
    "programlara dayanarak kisa bir tavsiye ver: en mantikli 3-4 tercihi sirala, "
    "her biri icin nedenini (basari sirasi guvenligi, burs/ucret, sehir) tek "
    "cumleyle acikla. Listede olmayan universite/program UYDURMA. Abartili "
    "olma, ozet ve net ol. "
    "BICIM: Duz metin yaz. Markdown KULLANMA; yildiz (*), kalin (**), tire (-) "
    "ya da madde isareti koyma. Her tercihi yeni satirda, numarayla yaz."
)


def foundry(*args: str) -> str:
    result = subprocess.run(
        ["foundry", *args], capture_output=True, text=True, encoding="utf-8"
    )
    return (result.stdout or "") + (result.stderr or "")


def get_service_endpoint() -> str:
    for attempt in range(2):
        out = foundry("service", "status")
        m = re.search(r"https?://[\w.\-]+:\d+", out)
        if m:
            return m.group(0) + "/v1"
        if attempt == 0:
            print("      Servis başlatılıyor...")
            foundry("service", "start")
    raise RuntimeError("Foundry Local servisi başlatılamadı.")


def resolve_model_id(endpoint: str, alias: str) -> str:
    req = urllib.request.Request(endpoint + "/models", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        for model in json.loads(r.read().decode("utf-8")).get("data", []):
            if model["id"].lower().startswith(alias.lower()):
                foundry("model", "load", model["id"])
                return model["id"]
    raise RuntimeError(f"Model bulunamadı: {alias}. Önce 'foundry model download {alias}'.")


def chat_stream(endpoint: str, model_id: str, messages: list[dict]):
    payload = {"model": model_id, "messages": messages, "temperature": 0.3,
               "max_tokens": 400, "stream": True}  # CPU'da uretimi sinirla
    req = urllib.request.Request(
        endpoint + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data == "[DONE]":
                break
            choices = json.loads(data).get("choices")
            if choices:
                parca = choices[0].get("delta", {}).get("content")
                if parca:
                    yield parca


def llm_baglam(sonuc: list[dict]) -> str:
    satirlar = []
    for v in sonuc[:LLM_GIRDI]:
        bs = v.get("basari_sirasi")
        bs_txt = f"{bs}" if bs and bs > 0 else "dolmadı"
        satirlar.append(
            f"- {v.get('universite','')} | {v.get('program','')} | "
            f"{v.get('sehir','')} | {v.get('universite_turu','')} | "
            f"{v.get('burs') or 'Ücretsiz'} | başarı sırası: {bs_txt}"
        )
    return "\n".join(satirlar)


def llm_yorumla(endpoint: str, model_id: str, soru: str, sonuc: list[dict]) -> None:
    icerik = (f"Öğrencinin sorusu: {soru}\n\n"
              f"Bu soruya uyan gerçek programlar:\n{llm_baglam(sonuc)}\n\n"
              f"Bu programlara göre tavsiyeni ver. /no_think")
    messages = [{"role": "system", "content": LLM_SISTEM},
                {"role": "user", "content": icerik}]
    print("\n  🤖 Yapay zeka yorumu (yavaş olabilir, lütfen bekleyin)...\n  ", end="", flush=True)
    basladi = False
    for parca in chat_stream(endpoint, model_id, messages):
        if not basladi:
            parca = parca.lstrip()
            if not parca:
                continue
            basladi = True
        print(parca.replace("\n", "\n  "), end="", flush=True)
    print("\n")


# --------------------------------------------------------------------------
# Ana dongu
# --------------------------------------------------------------------------

def main() -> None:
    if not VERI.exists():
        print(f"HATA: {VERI.name} bulunamadı. Önce 'python veri_cek.py' çalıştırın.")
        return
    veriler = json.loads(VERI.read_text(encoding="utf-8"))
    sehirler = build_sehir_index(veriler)
    program_sozlugu = build_program_sozlugu(veriler)
    uni_sozlugu = build_universite_sozlugu(veriler, sehirler, program_sozlugu)
    print(f"Tercih robotu hazır — {len(veriler):,} program yüklendi.".replace(",", "."))
    print("Doğal dilde yazın. Örnek: '480 bin sıralamayla istanbul devlet bilgisayar'")
    print("Filtreler: sıralama · şehir · puan türü (say/söz/ea/dil) · devlet/vakıf ·")
    print("           türkçe/ingilizce · lisans/önlisans · burslu/ücretsiz · bölüm adı")
    print("Komutlar: 'yorum' = yapay zeka önerisini aç/kapat  |  'çıkış' = kapat\n")

    yorum_acik = False
    llm = {"endpoint": None, "model": None}  # ilk ihtiyacta baglanilir (tembel)

    while True:
        try:
            q = input("Sorgu > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q or tr_lower(q) in ("çıkış", "cikis", "exit", "quit"):
            break
        if tr_lower(q) == "yorum":
            yorum_acik = not yorum_acik
            durum = "AÇIK (sonuçlar yapay zeka ile yorumlanacak, yavaş)" if yorum_acik else "KAPALI (sadece hızlı liste)"
            print(f"  Yapay zeka yorumu: {durum}\n")
            continue

        f = parse_query(q, sehirler, program_sozlugu, uni_sozlugu)
        if filtre_bos(f):
            print("\n  Sorgunuzda tanıdığım bir kriter bulamadım.")
            print("  Şehir, sıralama, puan türü, üniversite türü ya da bölüm adı yazın.")
            print("  Örnek: '290 bin say ankarada bilgisayar mühendisliği'\n")
            continue
        sonuc = filtrele(veriler, f)
        yazdir(sonuc, f)

        if yorum_acik and sonuc:
            if llm["model"] is None:  # ilk yorumda Foundry Local'e baglan
                try:
                    print("  Foundry Local'e bağlanılıyor...")
                    llm["endpoint"] = get_service_endpoint()
                    llm["model"] = resolve_model_id(llm["endpoint"], LLM_ALIAS)
                except Exception as e:
                    print(f"  ! Yapay zekaya bağlanılamadı: {e}\n")
                    continue
            try:
                llm_yorumla(llm["endpoint"], llm["model"], q, sonuc)
            except Exception as e:
                print(f"  ! Yorum üretilemedi: {e}\n")


if __name__ == "__main__":
    main()
