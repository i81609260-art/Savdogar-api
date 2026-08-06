# SQLite → Postgres ko'chirish (Railway)

> **Kafolat:** ko'chirish skripti hech qachon ma'lumot o'chirmaydi. Faqat
> `CREATE`, `INSERT ... ON CONFLICT DO NOTHING` va `setval` bajaradi.
> `DROP` / `TRUNCATE` / `DELETE` / `UPDATE` umuman yozilmagan.
> Manba SQLite fayli **faqat o'qish** rejimida ochiladi — ko'chirishdan keyin
> ham butun holicha qoladi va zaxira nusxa bo'lib xizmat qiladi.

---

## Nima uchun kerak

SQLite bitta yozuvchiga mo'ljallangan. Tur operator qidiruvi ishga tushganda
bir nechta worker bir vaqtda yozadi va `database is locked` xatolari boshlanadi.
Postgres bunga mo'ljallangan.

**Qo'shimcha nima kerak?** Deyarli hech nima:

| Narsa | Holat |
|---|---|
| `asyncpg` drayveri | ✅ `requirements.txt` da allaqachon bor |
| `postgres://` → `postgresql+asyncpg://` konvertatsiya | ✅ `app/config.py` da allaqachon bor |
| Sxema yaratish | ✅ `app/db_schema.py` — ilova va skript bir xil koddan foydalanadi |
| Kod o'zgarishi | ❌ **Kerak emas** — faqat `DATABASE_URL` almashadi |

---

---

## Supabase ishlatsangiz

Supabase — oddiy PostgreSQL. **Hech qanday Supabase kutubxonasi kerak emas.**

| Supabase hujjati taklif qiladi | Bu loyihada |
|---|---|
| `@supabase/supabase-js`, `@supabase/ssr` | ❌ Kerak emas — auth JWT bilan ishlaydi |
| `@supabase/server` | ❌ Node paketi, backend Python |
| Prisma | ❌ SQLAlchemy ishlatiladi |
| **Ulanish satri** | ✅ **Faqat shu** |

Supabase auth'ini qo'shish **zararli**: ikkita auth tizimi paydo bo'ladi
(Supabase sessiyasi + loyihaning JWT'si) va qaysi biri haqiqiy ekani
noaniq bo'lib qoladi. Storage va Realtime ham shunday — `/uploads` va
Socket.IO allaqachon bor.

### Qaysi portni tanlash

Supabase uch xil ulanish beradi:

| Variant | Port | Holat |
|---|---|---|
| Direct — `db.<ref>.supabase.co` | 5432 | ⚠️ Faqat IPv6, Railway'da ishlamaydi |
| Session pooler — `pooler.supabase.com` | 5432 | Migratsiya skripti uchun |
| **Transaction pooler** | **6543** | ✅ **Ilova uchun** |

```
DATABASE_URL=postgresql://postgres.PROJECT_REF:PAROL@aws-0-REGION.pooler.supabase.com:6543/postgres
```

### Nima uchun 6543 alohida ishlov talab qiladi

Transaction pooler (pgbouncer) ulanishni har so'rovdan keyin boshqa
mijozga berishi mumkin. asyncpg esa *prepared statement* larni ulanishga
bog'lab keshlaydi — keyingi so'rovda ular topilmaydi:

```
asyncpg.exceptions.DuplicatePreparedStatementError
asyncpg.exceptions.InvalidSQLStatementNameError
```

Bu xato **tasodifiy ko'rinadi va faqat yuk oshganda boshlanadi**.
`app/database.py` URL'da `:6543` yoki `pgbouncer=true` ni ko'rsa keshni
o'zi o'chiradi — qo'lda hech narsa qilish shart emas.

### Region

Supabase loyihasini **foydalanuvchilaringizga va serveringizga yaqin**
regionda oching. Har SQL so'rovi tarmoq bo'ylab boradi: Sidney'dagi baza
bilan bitta sahifa 10-20 ta so'rov qilsa, sekundlar yo'qoladi.
O'zbekiston uchun eng yaqini — Frankfurt (`eu-central-1`).

Region keyinchalik o'zgartirilmaydi — yangi loyiha ochib, ma'lumotni
qayta ko'chirish kerak bo'ladi.

---

## Qadamlar

### 1. Railway'da Postgres qo'shish

Railway loyihangizda: **+ New → Database → Add PostgreSQL**

Railway avtomatik `DATABASE_URL` o'zgaruvchisini yaratadi.

### 2. Backend servisiga ulash

Backend servis → **Variables** → **New Variable** → **Add Reference** →
Postgres servisidagi `DATABASE_URL` ni tanlang.

> ⚠️ **Hali deploy qilmang.** Avval ma'lumotni ko'chiring — aks holda ilova
> bo'sh Postgres'da ishga tushib, standart parolli **yangi** superadmin
> yaratadi va sizning haqiqiy superadmin hisobingiz ustidan tushib qoladi.

### 3. Zaxira nusxa olish (majburiy)

Railway volume'idagi SQLite faylini yuklab oling:

```bash
railway ssh
cat /data/savdogar.db > /tmp/backup.db
# yoki lokalga:
railway run -- python -c "import shutil; shutil.copy('/data/savdogar.db','/data/savdogar.backup.db')"
```

Skript faylni o'zgartirmaydi, lekin zaxira baribir olinsin.

### 4. Avval quruq yurgizish (hech nima yozmaydi)

```bash
railway run -- python migrate_to_postgres.py --dry-run
```

Chiqishda har jadval bo'yicha nechta qator ko'chishini ko'rasiz. Raqamlar
kutganingizdek bo'lsa — davom eting.

### 5. Haqiqiy ko'chirish

```bash
railway run -- python migrate_to_postgres.py
```

Oxirida jadval-jadval solishtiruv jadvali chiqadi:

```
  JADVAL                          SQLITE    POSTGRES   HOLAT
  companies                            2           2   OK
  users                                3           3   OK
  tours                               20          20   OK
  bookings                            50          50   OK
```

**Hammasi `OK` bo'lishi shart.** Bittasi ham `KAM!` bo'lsa skript nol bo'lmagan
kod bilan chiqadi — deploy qilmang, avval sababini aniqlang.

### 6. Deploy

Endi backend'ni qayta deploy qiling. Ilova Postgres'da mavjud superadminni
topadi va yangisini yaratmaydi.

### 7. Tekshirish

- Superadmin bilan kiring — **eski parolingiz** ishlashi kerak
- OpenTour firmasi va uning turlari joyida
- Bir nechta bron ochib ko'ring

---

## Agar biror narsa noto'g'ri ketsa

`DATABASE_URL` ni SQLite'ga qaytaring va qayta deploy qiling:

```
DATABASE_URL=sqlite+aiosqlite:///./savdogar.db
```

SQLite fayli o'zgarmagan, hamma narsa avvalgidek ishlaydi. Postgres'ni
tuzatib, qaytadan urinasiz — skript idempotent, ikkinchi marta ishga
tushirish xavfsiz.

---

## Tez-tez uchraydigan savollar

**Skriptni ikki marta ishga tushirsam nima bo'ladi?**
Hech nima. `ON CONFLICT DO NOTHING` — mavjud qatorlar tegilmaydi, yangilari
qo'shiladi. Uzilib qolgan ko'chirishni davom ettirish uchun ham shunday.

**`Postgres'da yo'q jadvallar` deb ogohlantirsa?**
Bu jadval SQLite'da bor, lekin modelda ham, `SCHEMA_PATCHES` da ham yo'q
degani. Odatda eski, ishlatilmaydigan jadval. Kerak bo'lsa modelga qo'shing
va skriptni qayta yurgizing.

**`FK yetishmadi` deb qolsa?**
SQLite'da FK tekshiruvi odatda o'chiq bo'ladi, shuning uchun u yerda
"yetim" qatorlar bo'lishi mumkin (masalan o'chirilgan firmaga ishora
qiluvchi bron). Postgres bunga yo'l qo'ymaydi. Skript qaysi jadval ekanini
aytadi — o'sha qatorlarni SQLite'da tekshiring.

**Nega `id` ketma-ketliklari tiklanadi?**
Busiz Postgres keyingi `INSERT` da `id=1` dan boshlab urinardi va ko'chirilgan
yozuvlar bilan to'qnashardi. Skript buni avtomatik hal qiladi.

---

## Ko'chirish nima qiladi (texnik)

1. **Sxema** — `app/db_schema.py:ensure_schema()`. Ilova ishga tushganda
   bajaradigan AYNAN o'sha kod, shuning uchun sxema kafolatlangan holda mos.
2. **Solishtirish** — SQLite va Postgres'dagi umumiy jadval/ustunlarni topadi.
   Faqat ikkalasida ham bor ustunlar ko'chadi.
3. **Tur moslash** — SQLite hamma narsani int/matn qilib saqlaydi, asyncpg esa
   turlarni qat'iy tekshiradi. `0/1 → boolean`, `'2026-08-04 19:15' → timestamp`
   va h.k. (`tests/test_migrate_to_postgres.py` da 39 ta test).
4. **FK sikli** — `companies.owner_id → users → companies` halqasi bor
   (`branches` ham unda). Skript avval FK tekshiruvini o'chirib ko'radi; ruxsat
   bo'lmasa muvaffaqiyatsiz qatorlarni kechiktirib, bir necha marta qayta uradi.
5. **Ketma-ketliklar** — `setval` bilan `MAX(id)` ga qo'yiladi.
6. **Tekshiruv** — qatorlar solishtiriladi, kamlik bo'lsa xato kodi.
