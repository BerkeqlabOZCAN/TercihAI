"""Kilavuz (basvuru/tercih PDF'leri) icinde arama.

kilavuz.json'daki parcalari saf Python TF-IDF ile indeksler ve bir soruya en
yakin parcalari dondurur. Dis bagimlilik YOK (numpy dahil degil) — kucuk olcekte
sozluk tabanli seyrek vektor + kosinus benzerligi yeterince hizli.

Turkce icin karakter n-gram: 'basvuru' ~ 'basvurusu' ortak parcalar uzerinden eslesir.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path

KILAVUZ = Path(__file__).parent / "kilavuz.json"


def tr_lower(s: str) -> str:
    return (s or "").replace("I", "ı").replace("İ", "i").lower()


def _tokenize(metin: str, nmin: int = 3, nmax: int = 5) -> list[str]:
    tokens: list[str] = []
    for kel in re.findall(r"[a-zçğıöşü0-9]+", tr_lower(metin)):
        tokens.append(kel)
        isaretli = f"<{kel}>"
        for n in range(nmin, nmax + 1):
            tokens.extend(isaretli[i:i + n] for i in range(len(isaretli) - n + 1))
    return tokens


class KilavuzArama:
    """Bellek ici TF-IDF; parcalari indeksler, soruya en yakinlari dondurur."""

    def __init__(self, parcalar: list[dict]):
        self.parcalar = parcalar
        self.idf: dict[str, float] = {}
        self.vektorler: list[dict[str, float]] = []
        self.normlar: list[float] = []
        self._fit()

    def _fit(self) -> None:
        n = len(self.parcalar)
        df: Counter = Counter()
        tokenler = []
        for p in self.parcalar:
            toks = _tokenize(p["metin"])
            tokenler.append(toks)
            df.update(set(toks))
        self.idf = {t: math.log((1 + n) / (1 + df_t)) + 1 for t, df_t in df.items()}
        for toks in tokenler:
            vek = {}
            for tok, sayi in Counter(toks).items():
                vek[tok] = sayi * self.idf.get(tok, 0.0)
            self.vektorler.append(vek)
            self.normlar.append(math.sqrt(sum(v * v for v in vek.values())) or 1.0)

    def ara(self, soru: str, k: int = 4) -> list[tuple[float, dict]]:
        q = {}
        for tok, sayi in Counter(_tokenize(soru)).items():
            if tok in self.idf:
                q[tok] = sayi * self.idf[tok]
        qnorm = math.sqrt(sum(v * v for v in q.values())) or 1.0
        skorlar = []
        for i, vek in enumerate(self.vektorler):
            # seyrek ic carpim: sorgunun (daha kisa) tokenleri uzerinden don
            ic = sum(qv * vek.get(tok, 0.0) for tok, qv in q.items())
            skorlar.append((ic / (qnorm * self.normlar[i]), self.parcalar[i]))
        skorlar.sort(key=lambda x: x[0], reverse=True)
        return skorlar[:k]


def yukle() -> KilavuzArama | None:
    """kilavuz.json varsa yukleyip indeksler; yoksa None."""
    if not KILAVUZ.exists():
        return None
    parcalar = json.loads(KILAVUZ.read_text(encoding="utf-8"))
    return KilavuzArama(parcalar) if parcalar else None
