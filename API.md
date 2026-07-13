# Backend API (frontend için)

Sunucu `python app.py` ile `http://127.0.0.1:8765` üzerinde çalışır. Tüm uç
noktalar **yereldir** (dış bağlantı yok). Frontend bu adrese `fetch` atar.

---

## 1) Arama — `GET /api/ara?q=<sorgu>`

Doğal dil sorgusunu filtreler. Anında yanıt (yapay zeka kullanmaz, hızlı).

**Yanıt:**
```json
{
  "filtre": "290.000 sıralama | SAY | Elazığ",
  "toplam": 12,
  "sonuclar": [
    {
      "universite": "FIRAT ÜNİVERSİTESİ (ELAZIĞ)",
      "program": "Kimya Mühendisliği",
      "sehir": "ELAZIĞ",
      "universite_turu": "DEVLET",
      "puan_turu": "SAY",
      "ogrenim_dili": "Türkçe",
      "ogrenim_suresi": 4,
      "burs": null,
      "taban_puan": 290.02,
      "basari_sirasi": 290020,
      "kontenjan": 60
    }
  ]
}
```
Kriter tanınmazsa: `{"filtre":"", "toplam":0, "sonuclar":[], "uyari":"..."}`
(en fazla 100 sonuç döner)

---

## 2) Sohbet (chatbot) — `POST /api/sohbet`

Çok turlu sohbet. Hem günlük/genel soruları yanıtlar, hem üniversite
sorularında gerçek veriye dayanır. **Yavaştır** (yerel model, CPU'da dakikalar).

**İstek gövdesi (JSON):**
```json
{
  "mesajlar": [
    { "rol": "user",    "icerik": "merhaba" },
    { "rol": "asistan", "icerik": "Merhaba! Nasıl yardımcı olabilirim?" },
    { "rol": "user",    "icerik": "289 bin sayısal, elazığ, mühendislik" }
  ]
}
```
- `rol`: `"user"` (kullanıcı) veya `"asistan"` (bot).
- Tüm konuşma geçmişini gönderin; hafıza böyle çalışır (backend durum tutmaz).
- Backend son 12 turu dikkate alır.

**Yanıt:**
```json
{ "cevap": "Elazığ'da 289 bin sıralamayla şu bölümlere girebilirsin: ..." }
```

**Örnek `fetch`:**
```js
const r = await fetch("/api/sohbet", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ mesajlar })   // {rol, icerik} dizisi
});
const { cevap } = await r.json();
```

---

## 3) Tek seferlik yorum — `GET /api/yorum?q=<sorgu>`

(Eski uç nokta.) Bir sorgunun filtre sonuçlarını yapay zekayla yorumlar.
Sohbet için `/api/sohbet` tercih edin. Yanıt: `{"yorum":"..."}`

---

### Notlar
- Yapay zeka cevapları **düz metindir** (markdown temizlenir; frontend `**`/`-` beklemesin).
- Model ilk çağrıda belleğe yüklenir; ilk cevap ekstra gecikebilir.
- Yükleniyor animasyonu göstermeyi unutmayın — cevaplar dakikalar sürebilir.
