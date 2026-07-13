"""Groq istemcisi (OpenAI uyumlu; yalnizca stdlib urllib — pip paketi gerekmez).

Cok cömert ücretsiz katman + cok hizli. Anahtar iki yoldan okunur:
  1) GROQ_API_KEY ortam degiskeni, ya da
  2) proje klasorundeki anahtar.txt ('gsk_' ile basliyorsa Groq sayilir).
Anahtar: https://console.groq.com  (ucretsiz)

Model degistirmek icin GROQ_MODEL ortam degiskeni veya VARSAYILAN_MODEL.
"""

import json
import os
import urllib.request
from pathlib import Path

VARSAYILAN_MODEL = "llama-3.3-70b-versatile"
ANAHTAR_DOSYASI = Path(__file__).parent / "anahtar.txt"
API = "https://api.groq.com/openai/v1/chat/completions"


def anahtar() -> str:
    k = os.environ.get("GROQ_API_KEY", "").strip()
    if k:
        return k
    if ANAHTAR_DOSYASI.exists():
        dosya = ANAHTAR_DOSYASI.read_text(encoding="utf-8").strip()
        if dosya.startswith("gsk_"):   # yalnizca Groq anahtari ise
            return dosya
    return ""


def aktif() -> bool:
    return bool(anahtar())


def model() -> str:
    return os.environ.get("GROQ_MODEL", VARSAYILAN_MODEL).strip() or VARSAYILAN_MODEL


def uret(messages: list[dict], temperature: float = 0.1,
         max_tokens: int = 1024) -> str:
    """OpenAI tarzi messages ([{role, content}]) — Groq bunu dogrudan kabul eder."""
    body = {
        "model": model(),
        "messages": [{"role": m.get("role", "user"),
                      "content": str(m.get("content", ""))} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        API, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + anahtar(),
                 # Cloudflare varsayilan Python-urllib UA'sini engelliyor (err 1010)
                 "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/131.0.0.0 Safari/537.36")})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d["choices"][0]["message"]["content"]
