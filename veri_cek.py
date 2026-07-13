"""Resmi YKS tercih kilavuzu verisini yerel bir JSON dosyasina indirir.

Tamamen standart kutuphane ile calisir (dis bagimlilik yok). Veriyi resmi genel
tercih API'sinden, tarayicinin yaptigi istegin AYNISI ile, sirali ve araliklı
(sunucuya saygili) sekilde ceker. Bir kez calistirilir; sonrasinda tercih robotu
tamamen cevrimdisi calisir.

NOT: Asagidaki API adresi, verinin cekilebilmesi icin teknik olarak zorunludur
(kaynak resmi kamu verisidir). Indirilen 'veri.json' dosyasini paylasmayin;
her kullanici bu betikle kendi kopyasini olusturmalidir.

Kullanim:
    python veri_cek.py
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

API = "https://yokatlas.yok.gov.tr/api/tercih-kilavuz/search"
OUT = Path(__file__).parent / "veri.json"
PAGE_SIZE = 500        # tek istekte gelen kayit sayisi (buyuk olursa aktarim kopuyor)
DELAY_SECONDS = 1.0    # istekler arasi bekleme (sunucuya saygi)

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Origin": "https://yokatlas.yok.gov.tr",
    "Referer": "https://yokatlas.yok.gov.tr/tercih-sihirbazi-t4-tablo.php",
}

# API'nin bekledigi bos filtre iskeleti (hepsi bos = tum programlar)
EMPTY_FILTERS = {
    "puanTuru": None, "universiteId": [], "birimGrupId": [], "ilKodu": [],
    "birimTuruId": None, "universiteTuru": None, "bursOraniId": None,
    "ogrenimTuruId": None, "kilavuzKodu": None,
    "minBasariSirasi": None, "maxBasariSirasi": None,
}

# API'den alacagimiz ham alan -> bizim kullanacagimiz sade ad
FIELD_MAP = {
    "kilavuzKodu": "program_kodu",
    "universiteAdi": "universite",
    "universiteTuru": "universite_turu",   # DEVLET / VAKIF / KKTC
    "fymkAdi": "fakulte",
    "birimAdi": "program",
    "ilAdi": "sehir",
    "puanTuru": "puan_turu",               # SAY / EA / SOZ / DIL / TYT
    "bursOraniAdi": "burs",
    "ogrenimDiliAdi": "ogrenim_dili",
    "ogrenimTuruAdi": "ogrenim_turu",
    "ogrenimSuresi": "ogrenim_suresi",
    "kontenjan": "kontenjan",
    "minPuan": "taban_puan",
    "basariSirasi": "basari_sirasi",
    "ucret": "ucret",
}


def fetch_page(page: int, size: int) -> dict:
    body = json.dumps({
        "filters": EMPTY_FILTERS,
        "page": page, "size": size,
        "sortBy": "basariSirasi", "direction": "ASC",
    }).encode("utf-8")
    req = urllib.request.Request(API, data=body, method="POST", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()  # bazen chunked aktarim erken bitebiliyor; retry sarmalar
    return json.loads(raw.decode("utf-8"))


def slim(record: dict) -> dict:
    return {sade: record.get(ham) for ham, sade in FIELD_MAP.items()}


def main() -> None:
    print("Tercih verisi indiriliyor...")
    first = fetch_page(0, PAGE_SIZE)
    total = first.get("totalElements", 0)
    pages = first.get("totalPages", 1)
    print(f"  Toplam {total} program, {pages} sayfa (sayfa basi {PAGE_SIZE}).")

    records = [slim(r) for r in first.get("content", [])]
    print(f"  Sayfa 1/{pages} alindi ({len(records)} kayit).")

    for page in range(1, pages):
        time.sleep(DELAY_SECONDS)
        for attempt in range(4):
            try:
                data = fetch_page(page, PAGE_SIZE)
                new = [slim(r) for r in data.get("content", [])]
                records.extend(new)
                print(f"  Sayfa {page+1}/{pages} alindi ({len(new)} kayit, toplam {len(records)}).")
                break
            except Exception as e:  # HTTP hatasi veya kopan aktarim (IncompleteRead)
                print(f"    ! Sayfa {page+1} hata ({type(e).__name__}), tekrar ({attempt+1}/4)...")
                time.sleep(3)
        else:
            print(f"    ! Sayfa {page+1} alinamadi, atlaniyor.")

    OUT.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nBitti: {len(records)} program -> {OUT}")


if __name__ == "__main__":
    main()
