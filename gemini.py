"""Google Gemini istemcisi (yalnizca stdlib urllib — pip paketi gerekmez).

Anahtar iki yoldan okunur:
  1) GEMINI_API_KEY ortam degiskeni, ya da
  2) proje klasorundeki anahtar.txt dosyasi (paylasilmaz; .gitignore'da).
Anahtar: https://aistudio.google.com/apikey  (ucretsiz)

Varsayilan model 'gemini-flash-latest' (her zaman guncel Flash). Degistirmek icin
GEMINI_MODEL ortam degiskeni veya asagidaki VARSAYILAN_MODEL.
"""

import json
import os
import urllib.request
from pathlib import Path

VARSAYILAN_MODEL = "gemini-2.0-flash"  # ucretsiz katman ~200 istek/gun (newest'ler 20/gun)
ANAHTAR_DOSYASI = Path(__file__).parent / "anahtar.txt"


def anahtar() -> str:
    """Once ortam degiskeni, yoksa yerel anahtar.txt dosyasi (paylasilmaz).
    'gsk_' ile baslayan (Groq) anahtarlari yok sayar."""
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    if k:
        return k
    if ANAHTAR_DOSYASI.exists():
        dosya = ANAHTAR_DOSYASI.read_text(encoding="utf-8").strip()
        if not dosya.startswith("gsk_"):   # Groq anahtari degilse Gemini say
            return dosya
    return ""


def aktif() -> bool:
    return bool(anahtar())


def model() -> str:
    return os.environ.get("GEMINI_MODEL", VARSAYILAN_MODEL).strip() or VARSAYILAN_MODEL


def uret(messages: list[dict], temperature: float = 0.1,
         max_tokens: int = 1024) -> str:
    """OpenAI tarzi messages ([{role, content}]) alir, Gemini'ye cevirir,
    metin cevabi dondurur. role: system/user/assistant."""
    sistem = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    contents = []
    for m in messages:
        if m.get("role") == "system":
            continue
        rol = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": rol, "parts": [{"text": str(m.get("content", ""))}]})

    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            # Yeni Flash modelleri "dusunme" tokeni harcayip cevabi kesebiliyor;
            # kapatinca hem hizli hem cevap butcesi tam kullanilir.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if sistem:
        body["systemInstruction"] = {"parts": [{"text": sistem}]}

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model()}:generateContent?key={anahtar()}")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))

    try:
        return d["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        # Guvenlik filtresi vb. -> bos/blok
        return "Yanıt alınamadı (Gemini içerik döndürmedi)."
