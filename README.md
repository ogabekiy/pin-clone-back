# Pinterest Clone — Backend Services

Ushbu qism Pinterest klonining backend infratuzilmasi bo'lib, **FastAPI**, **PostgreSQL + pgvector** va **OpenAI CLIP AI Embedder** mikroxizmatlaridan iborat.

---

## 🏗️ Arxitektura

Backend 2 ta asosiy xizmatdan tashkil topgan:

1. **`api/` (Port 8000)**:
   * **FastAPI** — Asinxron REST API.
   * **PostgreSQL + pgvector (512 o'lchamli)** — Foydalanuvchilar, pinlar, boardlar, xabarlar va vektor indekslarini saqlash.
   * **SQLAlchemy 2.0 (Async) + Alembic** — ORM va migratsiyalar.
   * **Cloudflare R2** — Rasmlarni to'g'ridan-to'g'ri frontenddan presigned URL orqali xavfsiz yuklash.
   * **Google OAuth** — JWT tokenlar `httpOnly` kukilarda saqlanadi.
   * **Gibrid Qidiruv (Hybrid Search)** — CLIP vektor semantikasi va matn sarlavhasi/tavsifi bo'yicha birlashtirilgan reyting.
   * **Tavsiyalar Tizimi** — Foydalanuvchining ko'rishlari (1.0x), yoqtirishlari (1.5x) va saqlashlari (2.0x) bo'yicha shaxsiy feed yaratuvchi algoritm.
   * **1-on-1 Chat API** — Foydalanuvchilar o'rtasida real-vaqt xabarlar va o'qilmagan xabarlar hisoblagichi.

2. **`embedder/` (Port 8001)**:
   * **PyTorch + Hugging Face Transformers** (`openai/clip-vit-base-patch32`).
   * Matn va rasmlarni normalizatsiya qilingan 512 o'lchamli vektorlarga aylantirib beruvchi lokal neyron tarmoq xizmati.

---

## 🐳 AWS Serverga Docker orqali Deploy Qilish (Tavsiya etiladi)

Serverda (AWS EC2 / Ubuntu) loyihani **1 ta buyruq** bilan ishga tushirish uchun Docker tayyorlandi.

### 1. Serverda Git Clone / Pull
```bash
git clone <sizning-repo-linki>
cd pinterest-clone
```

### 2. `.env` faylini to'ldirish
```bash
cp .env.example .env
nano .env  # R2 kalitlari va Google OAuth ma'lumotlarini kiriting
```

### 3. Hammasini 1 ta buyruqda ishga tushirish:
```bash
docker compose up -d --build
```

**Bu buyruq orqali avtomatik tarzda:**
1. ✅ **`postgres`**: `pgvector` moduli bilan ishga tushadi va salomatlik holati (healthcheck) tekshiriladi.
2. ✅ **`embedder`**: OpenAI CLIP neyron tarmoq modelini yuklab, xotirada tayyorlab qo'yadi.
3. ✅ **`api`**: Postgres to'liq tayyor bo'lishini kutadi, **Alembic migratsiyalarini avtomatik yurgizadi** va FastAPI serverini 8000-portda ishga tushiradi.

### 4. Holat va Loglarni tekshirish:
```bash
docker compose ps
docker compose logs -f api
```

### 5. Yangilanishlarni olish (Kelgusida):
```bash
git pull
docker compose up -d --build
```

---

## 🛠️ Lokal Muhitda Qo'lda Ishga Tushirish (Docker'siz)
* Python 3.11+
* PostgreSQL 15+ (`pgvector` kengaytmasi bilan)
* Cloudflare R2 hisobi (yoki S3 mos ob'ekt saqlash xizmati)

### 2. Virtual Muhitni Tayyorlash
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Bog'liqliklarni O'rnatish
```bash
# API bog'liqliklari
pip install -r api/pyproject.toml (yoki pip install fastapi uvicorn sqlalchemy asyncpg alembic boto3 python-jose google-auth requests httpx)

# Embedder bog'liqliklari
pip install torch torchvision transformers pillow httpx
```

### 4. Konfiguratsiya (`backend/.env`)
`backend/.env.example` faylidan nusxa oling va qiymatlarni to'ldiring:
```bash
cp .env.example .env
```

`.env` tarkibi:
```env
DEBUG=True
SECRET_KEY=your_jwt_secret_key_here
COOKIE_NAME=pin_access_token
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# Ma'lumotlar bazasi
DATABASE_URL=postgresql+asyncpg://ogabek@localhost:5432/pinterest_db

# Cloudflare R2
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=pin-images
R2_PUBLIC_URL=https://pub-your_public_id.r2.dev

# Google OAuth
GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com

# Embedder Service
EMBEDDER_URL=http://127.0.0.1:8001
```

### 5. Ma'lumotlar Bazasi Migratsiyasi
```bash
cd api
alembic upgrade head
```

### 6. Xizmatlarni Ishga Tushirish

**1-terminal: CLIP Embedder Xizmati**
```bash
cd backend/embedder
../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

**2-terminal: Asosiy API Xizmati**
```bash
cd backend/api
../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 📡 Asosiy API Endpointlar

* **Hujjatlar (Swagger UI)**: `http://127.0.0.1:8000/docs`
* **Auth**:
  * `POST /auth/google` — Google orqali kirish (JWT cookie)
  * `POST /auth/logout` — Chiqish
  * `GET /auth/me` — Joriy foydalanuvchi
* **Pinlar**:
  * `GET /pins` — Bosh sahifa feedi (kursorli paginatsiya)
  * `POST /pins/upload-url` — R2 presigned URL olish
  * `POST /pins` — Yangi pin yaratish (fonda avtomatik CLIP embedding)
  * `GET /pins/{id}` — Pin ma'lumotlari va ko'rishlar soni
  * `POST /pins/{id}/view` — Ko'rishlar hisoblagichi (+1 deduplicated)
  * `GET /pins/{id}/similar` — Kosinus o'xshashlik bo'yicha eng yaqin pinlar
  * `POST /pins/{id}/like` — Layk bosish / bekor qilish
  * `POST /pins/{id}/comments` — Izoh qoldirish
* **Qidiruv & Tavsiyalar**:
  * `GET /search?q=...` — Gibrid qidiruv (CLIP semantikasi + sarlavha/tavsif mosligi)
  * `POST /search/image` — Vizual qidiruv (yuklangan rasm orqali qidirish)
  * `GET /feed/personal` — Shaxsiy tavsiya feedi
* **Foydalanuvchilar**:
  * `GET /users/{identifier}` — Profil statistikasi (`id` yoki `username` orqali)
  * `GET /users/{identifier}/pins` — Yaratilgan pinlar
  * `GET /users/{identifier}/likes` — Yoqqan pinlar
  * `PATCH /users/me` — Profilni tahrirlash (ism, avatar, `@username`)
  * `POST /users/{identifier}/follow` — Obuna bo'lish
* **Chat**:
  * `GET /chat/conversations` — Suhbatlar ro'yxati
  * `GET /chat/messages/{partner_id}` — Suhbat xabarlari
  * `POST /chat/messages` — Yangi xabar yuborish
  * `GET /chat/unread-count` — O'qilmagan xabarlar soni

