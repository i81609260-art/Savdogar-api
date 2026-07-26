# Meta App Review — Turify (Instagram API with Instagram login)

Bu fayl Meta App Review topshirigʻiga koʻchiriladigan tayyor matnlarni saqlaydi.
Manba: https://developers.facebook.com/documentation/instagram-platform/app-review

---

## 0. Nega bizga review kerak

Hujjatga koʻra review **Tech Provider**lar uchun majburiy — yaʼni bir nechta
biznesga xizmat koʻrsatuvchi ilovalar uchun. Turify koʻplab tur firmalariga
xizmat qiladi, demak **Advanced Access** talab qilinadi.

---

## 1. Soʻralayotgan ruxsatlar va ular qayerda ishlatiladi

| Ruxsat | Nima uchun | Kodda qayerda | API chaqiruvi bormi |
|---|---|---|---|
| `instagram_business_basic` | Ulangan akkauntni aniqlash (ID, username) | `GET /me?fields=user_id,username` | ✅ ha |
| `instagram_business_manage_messages` | Mijoz DM yozganda javob berish va lead yigʻish | `POST /{ig-user-id}/messages` | ✅ ha |
| `instagram_business_manage_comments` | Post izohiga ochiq javob qaytarish | `POST /{comment-id}/replies` | ✅ ha |

**Ortiqcha ruxsat soʻramaymiz.** Meta konsoli taklif qilgan
`instagram_business_content_publish` va `instagram_business_manage_insights`
bizga kerak emas va soʻralmaydi — hujjatda aynan shu rad etish sababi
koʻrsatilgan: *"If you request permissions that your app does not use ...
your submission will not be approved."*

---

## 2. Ilova nima qiladi (Use case description)

> Turify is a CRM for tour agencies. A tour agency connects its own Instagram
> Business account. When a customer sends a direct message or comments on the
> agency's post, Turify automatically creates a lead in the agency's CRM
> pipeline and notifies the agency staff.
>
> Our assistant replies in the DM to collect the customer's name, phone number
> and destination of interest, then hands the conversation over to a human
> operator. For comments, we post a public reply inviting the customer to
> continue in DM.
>
> Each agency connects only its own account and sees only its own leads.

---

## 3. Ruxsat boʻyicha tavsif (har biri uchun alohida maydon)

**instagram_business_basic**
> We call `GET /me?fields=user_id,username` once, right after the agency
> authorises our app, to identify which Instagram Business account was
> connected and to display its username in the agency's dashboard. Without it
> we cannot route incoming messages to the correct agency.

**instagram_business_manage_messages**
> We receive `messages` webhooks for the connected account. When a customer
> writes to the agency, we create a lead and reply via
> `POST /{ig-user-id}/messages` to ask for the customer's name, phone number
> and preferred destination. The collected data is written into the agency's
> CRM so an operator can follow up.

**instagram_business_manage_comments**
> We receive `comments` webhooks for the connected account. When a customer
> comments on the agency's post, we create a lead and post a public reply via
> `POST /{comment-id}/replies` inviting them to continue in direct messages.

---

## 4. Tekshiruvchi uchun qadamlar (Verification details)

> **Test account**
> Email: `<TEST_EMAIL>`
> Password: `<TEST_PASSWORD>`
>
> **Steps**
> 1. Open https://turify.xyz/login and sign in with the credentials above.
>    The interface language is English by default; you can switch languages
>    from the selector in the top bar.
> 2. In the left sidebar click **Integrations**.
> 3. Click the **Instagram** card, then the **Sign in with Instagram** button.
> 4. Authorise the Instagram Business account you added as an Instagram
>    Tester. You will be redirected back to Turify and the card will show the
>    connected username and a green "Connected" badge.
> 5. From a different Instagram account, send a direct message to the
>    connected business account, for example: "Hello, how much is the Dubai
>    tour?".
> 6. Our assistant replies asking for a name, then a phone number, then a
>    destination. Answer each question.
> 7. Back in Turify, open **Pipeline** in the sidebar. The new lead appears
>    with source "instagram", containing the name, phone number and
>    destination collected in step 6.
> 8. To test comments: leave a comment on any post of the connected account.
>    A public reply is posted automatically and a lead appears in **Pipeline**.
> 9. To disconnect, return to **Integrations → Instagram → Disconnect**.

---

## 5. Ilova sozlamalari (Settings → Basic)

| Maydon | Qiymat |
|---|---|
| App Icon | 1024×1024 PNG — `frontend/public/logo.png` (tekshirildi: 1024×1024) |
| Privacy Policy URL | `https://turify.xyz/privacy` |
| Terms of Service URL | `https://turify.xyz/terms` |
| User Data Deletion | `https://turify.xyz/data-deletion` |
| App Category | Business and Pages |
| Business Email | `info@turify.xyz` |

⚠️ Terms of Service maydonida hozir `https://www.facebook.com/` turgan boʻlishi
mumkin — almashtirilmasa review rad etiladi.

---

## 6. Instagram API → 4-qadam (Business login sozlamalari)

| Maydon | Qiymat |
|---|---|
| Valid OAuth Redirect URIs | `https://savdogar-api-production.up.railway.app/api/instagram/oauth/callback` |
| Deauthorize callback URL | `https://savdogar-api-production.up.railway.app/api/instagram/deauthorize` |
| Data deletion request URL | `https://savdogar-api-production.up.railway.app/api/instagram/data-deletion` |

## 7. Webhooks (3-qadam)

| Maydon | Qiymat |
|---|---|
| Callback URL | `https://savdogar-api-production.up.railway.app/api/instagram/webhook` |
| Verify token | `.env` dagi `INSTAGRAM_VERIFY_TOKEN` qiymati |
| Subscribed fields | `messages`, `comments` |

---

## 8. Screencast talablari

Hujjat aniq talab qiladi:
- **Interfeys ingliz tilida boʻlishi shart** (shuning uchun default til `en`)
- Har bir ruxsat uchun toʻliq foydalanuvchi yoʻli koʻrsatilishi kerak
- Tushunarsiz tugmalar izohlanishi kerak (caption yoki tooltip)

Bitta yozuvda 4-boʻlimdagi 1–9 qadamlarni ketma-ket koʻrsatish yetarli:
ulash → DM → lead → izoh → javob → uzish.

---

## 9. Topshirishdan oldingi tekshiruv roʻyxati

- [ ] Ilova **Live** (Опубликовано) holatida — Development'da webhook kelmaydi
- [ ] Instagram akkaunt **Roles → Instagram Testers** ga qoʻshilgan va taklif qabul qilingan
- [ ] Har uch ruxsat boʻyicha kamida bitta muvaffaqiyatli API chaqiruvi bajarilgan
      (ulash = basic, DM javobi = messages, izoh javobi = comments)
- [ ] Privacy / Terms / Data deletion URL'lari ochiladi va 3 tilda ishlaydi
- [ ] 1024×1024 ikonka yuklangan
- [ ] Test hisobi ishlaydi va tekshiruvchiga berilgan
- [ ] Screencast ingliz tilida yozilgan
