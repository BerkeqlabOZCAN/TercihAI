"""kilavuzlar/ klasorundeki PDF kilavuzlari metne cevirip parcalara boler ve
kilavuz.json'a yazar. Bir kez calistirilir; sonra chatbot bu dosyadan kilavuz
sorularini cevaplar.

Tek dis bagimlilik: pypdf (yalnizca bu hazirlik adiminda; calisma aninda gerekmez).
    pip install pypdf
    python kilavuz_hazirla.py
"""

import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

sys.stdout.reconfigure(encoding="utf-8")

KOK = Path(__file__).parent
PDF_DIR = KOK / "kilavuzlar"
OUT = KOK / "kilavuz.json"
CHUNK_KELIME = 140   # parca basina hedef kelime
ORTUSME = 25         # ardisik parcalar arasi ortusme


def temizle(metin: str) -> str:
    metin = metin.replace("­", "")            # yumusak tire
    metin = re.sub(r"[ \t]+", " ", metin)
    metin = re.sub(r"\n{2,}", "\n", metin)
    return metin.strip()


def parcala(metin: str, kaynak: str, sayfa: int) -> list[dict]:
    kelimeler = metin.split()
    adim = CHUNK_KELIME - ORTUSME
    parcalar = []
    for bas in range(0, max(len(kelimeler), 1), adim):
        dilim = kelimeler[bas: bas + CHUNK_KELIME]
        if len(dilim) < 8:   # cok kisa artik parcalari atla
            break
        parcalar.append({"kaynak": kaynak, "sayfa": sayfa, "metin": " ".join(dilim)})
        if bas + CHUNK_KELIME >= len(kelimeler):
            break
    return parcalar


def main() -> None:
    pdfler = sorted(PDF_DIR.glob("*.pdf"))
    if not pdfler:
        print(f"HATA: {PDF_DIR} icinde PDF yok. Kilavuz PDF'lerini oraya koyun.")
        return

    tum = []
    for pdf in pdfler:
        print(f"Okunuyor: {pdf.name} ...")
        reader = PdfReader(str(pdf))
        for i, page in enumerate(reader.pages, 1):
            try:
                metin = temizle(page.extract_text() or "")
            except Exception:
                metin = ""
            if len(metin.split()) >= 8:
                tum.extend(parcala(metin, pdf.name, i))
        print(f"  {len(reader.pages)} sayfa islendi.")

    OUT.write_text(json.dumps(tum, ensure_ascii=False), encoding="utf-8")
    print(f"\nBitti: {len(tum)} parca -> {OUT.name} "
          f"({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
