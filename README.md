# Tercih Robotu — Üniversite Tercih Asistanı

~21.600 lisans/önlisans programını doğal dilde sorgulayıp sıralama, şehir, puan
türü, üniversite ve bölüme göre "nereye girerim" sorusunu yanıtlayan, tamamen
yerel çalışan bir tercih asistanı. Ayrıca yerel bir yapay zeka sohbet asistanı içerir.

Kodun tamamı bu proje için sıfırdan yazılmıştır. Program verisi, resmi ve herkese
açık YKS tercih kılavuzu API'sinden **kullanıcının kendi makinesinde** çekilir;
çekim dışında hiçbir dış servise bağlanılmaz.



## Kurulum

```powershell
python veri_cek.py    # ilk sefer: tercih verisini indirir (veri.json ~10 MB)
```

Filtreleme/arama, yapay zeka olmadan da çalışır ve **hiçbir dış paket gerektirmez**
(saf Python standart kütüphanesi). Yapay zeka sohbeti için bir anahtar koymanız
yeterli: proje klasöründe **`anahtar.txt`** oluşturup içine anahtarı yapıştırın.
Sistem anahtarın türünü kendisi anlar (`anahtar.txt` `.gitignore`'da, paylaşılmaz).

**Seçenek A — Groq (çok hızlı, cömert ücretsiz kota, önerilen).**
[console.groq.com](https://console.groq.com) → ücretsiz anahtar (`gsk_...`).
Cevaplar ~1 saniyede gelir, günde binlerce istek hakkı.

**Seçenek B — Google Gemini (kaliteli).**
[aistudio.google.com/apikey](https://aistudio.google.com/apikey) → anahtar
(`AIza...`). Ücretsiz katman modele göre 20–200 istek/gün.

**Seçenek C — Tamamen yerel (Foundry Local).** `anahtar.txt` yoksa otomatik devreye
girer. Çevrimdışı ve gizli ama CPU'da yavaş:

```powershell
winget install Microsoft.FoundryLocal
foundry model download qwen3-4b
```

Öncelik: Groq → Gemini → yerel. Anahtar türü `anahtar.txt`'deki önekten anlaşılır
(`gsk_` = Groq, `AIza`/`AQ.` = Gemini). Groq/Gemini kullanınca sohbet mesajları
ilgili servise gider; arama ve veriler her zaman yereldir.

## Kullanım

**`Tercih Robotu.bat` dosyasına çift tıklayın.** Tarayıcıda modern arayüz açılır.
Üç sekme vardır:

- **Arama** — doğal dilde yazdıkça sonuçlar anında kart kart gelir; başarı sırası
  ve taban puana göre sıralanabilir.
- **Yapay Zeka** — çok turlu sohbet; tercih önerisi, genel/sayısal sorular ve
  (isteğe bağlı) resmi başvuru/tercih **kılavuzu** hakkında sorular.
- **Tercih Listem** — beğendiğiniz programları biriktirip dışa aktarma.

### Kılavuz sorularını yanıtlama (isteğe bağlı)

Yapay zekanın başvuru/tercih süreci sorularını (ücret, tarih, şart, ek yerleştirme...)
yanıtlaması için resmi kılavuz PDF'lerini indeksleyebilirsiniz:

```powershell
pip install pypdf
# Resmi kılavuz PDF'lerini kilavuzlar/ klasörüne koyun, sonra:
python kilavuz_hazirla.py    # kilavuz.json üretir (bir kez)
```

Chatbot, kılavuzla ilgili bir soru geldiğinde cevabını **yalnızca** bu PDF'lerin
içeriğine dayandırır. PDF'ler ve çıkarılan metin depoya dahil **edilmez**
(telif; herkes kendi resmi kopyasını indirir).

Terminalden de kullanılabilir:

```powershell
python tercih_robotu.py   # metin tabanlı sürüm
python app.py             # web arayüzü (tarayıcıyı otomatik açar)
```

### Örnek sorgular

```
480 bin sıralamayla istanbul devlet bilgisayar
İTÜ mühendislik
ankara vakıf hukuk burslu
izmirde ingilizce lisans tıp
```

Robot; sıralama, şehir, üniversite adı/kısaltması (İTÜ, ODTÜ, Boğaziçi...),
üniversite türü (devlet/vakıf), puan türü (SAY/EA/SÖZ/DİL), öğrenim dili
(türkçe/ingilizce), seviye (lisans/önlisans), burs durumu ve bölüm adını sorgudan
otomatik yakalar. Sıralama verdiğinizde, **taban başarı sıranız o programın kesme
sırasına eşit veya daha iyiyse** program listelenir.

## Veri nasıl çekiliyor?

[veri_cek.py](veri_cek.py) resmi ve herkese açık tercih kılavuzu API'sine,
tarayıcının yaptığı isteğin aynısını göndererek bağlanır. İstekler **sıralı ve
aralıklı** atılır (sunucuya saygı). Sonuç yerel `veri.json` dosyasına yazılır;
sonrasında robot tamamen çevrimdışı çalışır. Bu dosya depoya dahil **edilmez**
(bkz. `.gitignore`); herkes kendi kopyasını üretir.

## Dosyalar

| Dosya | Görev |
|---|---|
| `Tercih Robotu.bat` | **Çift tıkla:** web arayüzünü açar |
| `app.py` | Web sunucusu (stdlib HTTP + JSON API) |
| `arayuz.html` | Modern/animasyonlu tek sayfa arayüz |
| `tercih_robotu.py` | Doğal dil sorgu + filtreleme motoru |
| `veri_cek.py` | Tercih verisini `veri.json`'a indirir |
| `veri.json` | İndirilen program verisi (çekim sonrası oluşur; depoya dahil değil) |
| `kilavuz_hazirla.py` | Kılavuz PDF'lerini `kilavuz.json`'a indeksler (isteğe bağlı) |
| `kilavuz.py` | Kılavuz içinde arama (saf Python TF-IDF) |
| `groq.py` / `gemini.py` | İsteğe bağlı yapay zeka istemcileri (stdlib; `anahtar.txt`) |
| `API.md` | Arayüzün kullandığı yerel API sözleşmesi |
| `calistir.bat` | Terminal başlatıcı |

## Yerellik

| Bileşen | Dış bağlantı |
|---|---|
| Veri çekme (`veri_cek.py`) | Bir kez internet |
| Arama / filtreleme / sıralama | **Sıfır** — her zaman yerel |
| Yapay zeka — Foundry Local seçeneği | **Sıfır** — çevrimdışı |
| Yapay zeka — Gemini seçeneği | Her sohbet mesajı Google'a gider |

Yani Gemini kullanmazsanız her şey %100 yerel; kullanırsanız yalnızca yapay zeka
sohbeti çevrimiçi olur (arama ve veriler yerel kalır).
