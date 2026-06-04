# Google Search Console'ga Savdogar'ni Qo'shish — To'liq Qo'llanma 🚀

## 📋 Qadam 1: Google Search Console'ga Kirish

**URL:** https://search.google.com/search-console/about

```
1. Google akkauntingiz bilan kiring (Gmail)
2. "Start now" yoki "O'zini boshlash" tugmasini bosing
3. "URL prefix" tanlang (masalan: https://savdogar.vercel.app)
```

---

## 🔗 Qadam 2: Sayt Qo'shish

**Sahifa:** Search Console → "Add property"

```
┌─────────────────────────────────────────────┐
│  URL prefix / Domain                        │
├─────────────────────────────────────────────┤
│  Qaysi birini tanlash?                      │
│                                             │
│  🔹 URL prefix                              │
│     ✓ Ushbu turi Vercel uchun to'g'ri       │
│     Masalan: https://savdogar.vercel.app   │
│                                             │
│  🔹 Domain                                  │
│     Keyingi: savdogar.uz almashtirilsa      │
│                                             │
│  ➡️ SHUNI TANLANG: URL prefix               │
└─────────────────────────────────────────────┘
```

---

## ✅ Qadam 3: Sayt Tekshirish (Verification)

**Google Search Console size 2 ta usul taklif qiladi:**

### A️⃣ HTML Faylini Yuklash (ENG OSON!)

```
1. "HTML file" tab'ini bosing
2. verification.html faylini yuklab oling
3. Savdogar saytining /public folder'ga yuklang:
   📁 frontend/public/google[hash].html
4. "Verify" tugmasini bosing
5. Google'ga aytiladi: "Ha, shu saytning egasiman!"
```

**OR**

### B️⃣ Meta Tag'ni Qo'shish

```
1. "Meta tag" tab'ini bosing
2. Kodni ko'payting:
   <meta name="google-site-verification" content="..." />
3. frontend/app/layout.tsx'ga qo'shing
4. Deploy qiling
5. "Verify" bosing
```

---

## 🗺️ Qadam 4: Sitemap Submit Qilish

**Sahifa:** Search Console → Left menu → "Sitemaps"

```
1. Sitemap URL'ini kiriting:
   https://savdogar.vercel.app/sitemap.xml
   
2. "Submit" tugmasini bosing

3. Status: "Success" ko'rinishi kerak ✅
```

---

## 🔍 Qadam 5: Pages Indexing Tekshirish

**Sahifa:** Search Console → "Pages" tab

```
Agar ko'rsa:
┌──────────────────────────┐
│ ✅ 6 pages indexed       │
│ ⏳ 2 pages pending       │
│ ⚠️ 1 pages errors        │
└──────────────────────────┘

Bu yaxshi! Google'ga 3-7 kun vaqt ber, 
barcha sahifalar indeks qilinadi.
```

---

## 📊 Qadam 6: Search Performance Ko'rish

**Sahifa:** Search Console → "Performance"

```
1-2 hafta'dan so'ng ko'rishga bo'ladi:
- Qancha marta "Savdogar" qidirildi
- Qancha marta saytga bosildi
- O'rtacha pozitsiya (ranking)
- Qaysi so'zlar uchun chiqadi
```

Masalan:
```
📈 Performance
├─ Total Clicks: 5
├─ Total Impressions: 45
├─ Avg. CTR: 11%
└─ Avg. Position: 2.3
```

---

## 🎯 Qadam 7: Errors Tekshirish

**Sahifa:** Search Console → "Coverage"

Agar qizil icon ko'rsa:
```
❌ Error: "robots.txt is blocking this page"
   → Shuning uchun robots.txt'da Disallow qilgan bo'lsangiz, 
     Remove qiling

❌ Soft 404 errors
   → 404 sahifalar to'g'ri 404 status kodi bersa, xalol

✅ Valid: Barcha sahifalar indeks qilingan
```

---

## 🚀 Qadam 8: Mobile Friendliness Tekshirish

**Sahifa:** Search Console → "Mobile usability"

```
✅ No issues — Google mobilda to'g'ri ko'radi
⚠️ Agar xato bo'lsa → 
   - Font kichik
   - Tugmalar yaqin
   - Responsive design yo'q
```

---

## 📱 URL INSPECTION TOOL — Bitta URL Test Qilish

**Sahifa:** Search Console → Top "URL Inspection"

```
1. Sahifa URL'ini kiritib Enter bosing:
   https://savdogar.vercel.app

2. **Google'da indexlanganmi?**
   ✅ "URL is on Google" = Indexed
   ⏳ "URL not on Google" = Wait 7-10 days
   
3. **Mobile OK?**
   ✅ "No mobile usability issues"

4. **Screenshot ko'rish:**
   "Screenshots" tab'i — Google'ga nima ko'rinib turigani
```

---

## ⚡ Tezlatish Tips

Sayt tezroq indeks qilish uchun:

```
1. ✅ robots.txt yaratildi
2. ✅ sitemap.xml yaratildi
3. ✅ Meta tags optimizatsiya qilindi
4. ✅ Mobile responsive ✓
5. Qo'shimchalar (optional):
   - Meta tags: Open Graph ✓ (qiqdik)
   - Performance: Lighthouse 90+ (Vercel auto qiladi)
   - Backlinks: Boshqa saytlardan link (keyincha)
```

---

## 📝 CHECKLIST — Sening uchun Amal Qo'shni

- [ ] Google Search Console'ga kir
- [ ] "URL prefix" sifatida qo'sh: `https://savdogar.vercel.app`
- [ ] HTML file yoki Meta tag orqali verify qil
- [ ] `/sitemap.xml` submit qil
- [ ] 7-10 kun kut, keyin "Performance" ko'r
- [ ] Errors bo'lsa, fix qil

---

## 🎉 Yakuniy Natiija (1-2 hafta'dan so'ng)

```
Google Search Console:
├─ Pages indexed: ✅
├─ Sitemaps: ✅ Submitted
├─ Mobile usability: ✅ No issues
└─ Performance: 📊 Clicks va impressions ko'runa boshlaydi

Google Search'da:
"Savdogar CRM" qidirganda → 📍 Top 10 da chiqish mumkin
```

---

## ❓ FAQ

**Q: Nima vaqt kerak sayt Google'da chiqish uchun?**
> **A:** Birinchi indeks — 3-7 kun. Ranking'i o'zgarib turadigan bo'ladi iloji borida. 1-2 hafta'dan so'ng stable ko'rsa bo'ladi.

**Q: Agar "URL not on Google" chiqsa?**
> **A:** Normal! 7-10 kun kut. Yoki "Request indexing" tugmasini bosib yubor:
> ```
> Search Console → URL Inspection → "Request indexing"
> ```

**Q: robots.txt va sitemap.xml'da nima farq?**
> ```
> robots.txt   = "Google, shunga ya'ni bu joylarni indeks qilma!"
> sitemap.xml  = "Google, shunga ya'ni bu joylar mavjud, shunga borr!"
> ```

**Q: SEO uchun yana nima qilish kerak?**
> 1. **Internal Links** — Sahifalar o'rtasida bog'lanish
> 2. **Backlinks** — Boshqa saytlardan link (keyincha)
> 3. **Page Speed** — Vercel fast! ✓
> 4. **Content** — Keyword'lar tabiiy ravishda yozilgan ✓

---

**Savollar bo'lsa, yubor! 🚀**

Meni SEO status'ni qat'niy ko'rish uchun URL yuboring: 
`https://savdogar.vercel.app`
