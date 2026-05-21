# Savdogar — CRM/POS + SAYR integratsiya

**Savdogar** — tur agentligi uchun ichki CRM/POS tizimi.  
**SAYR** — tashqi tur paketlar aggregator platformasi (alohida servis). Ikkalasi API orqali ulanadi.

## Arxitektura

```
┌─────────────────┐     webhook / API      ┌──────────────────┐
│  SAYR platform  │ ◄────────────────────► │    Savdogar      │
│  (tur katalog)  │                        │  CRM / POS / API │
└─────────────────┘                        └──────────────────┘
         │                                           │
    Tur paketlar                              Sotuv xabarlari
    birlashgan                                Admin panel
```

### Integratsiya oqimi

1. Savdogar admin **SAYR ga ulanish** so‘rovini yuboradi (`POST /api/integrations/sayr/connect`)
2. SAYR **superadmin** tasdiqlaydi → webhook `integration.approved`
3. SAYR da user yaratilsa → webhook `user.provisioned` → Savdogarda avtomatik user
4. SAYR da bron/sotuv → webhook `booking.created` / `booking.confirmed` → **CRM/POS** ga xabar
5. Turlar sinxronlash → webhook `tour.sync`

### SAYR webhook (Savdogar qabul qiladi)

`POST http://localhost:8000/api/integrations/sayr/webhook`

```json
{
  "event": "booking.confirmed",
  "data": {
    "savdogar_company_id": 1,
    "booking_id": "sayr-12345",
    "user_name": "Ali Valiyev",
    "user_email": "ali@mail.uz",
    "tour_title": "Samarqand 3 kun",
    "total_price": 2500000,
    "guests_count": 2
  }
}
```

Header: `X-Sayr-Signature: sha256=<hmac>`

## Ishga tushirish

### Backend (`Savdogar-api`) — port 8000

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Superadmin:** `admin@savdogar.uz` / `SavdogarAdmin123!`

### Frontend (`Savdogar_agentligi`) — port 3000

```powershell
cd frontend
npm install
copy .env.local.example .env.local
npm run dev:clean
```

`.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SOCKET_URL=http://localhost:8000
```

## Repolar

| Qism | GitHub |
|------|--------|
| Backend | `i81609260-art/Savdogar-api` |
| Frontend | `IsaFrDev/Savdogar_agentligi` |

## Admin panel

- `/admin/integrations` — SAYR ulanish va POS sotuvlari
- Bronlar, CRM, hisobotlar — ichki Savdogar funksiyalari
