# Debian 12 (bookworm) ATAYLAB qadab qo'yilgan. Teglanmagan `slim` yangi
# Debian'ga siljib ketadi va u yerda paket nomlari o'zgaradi
# (masalan libasound2 -> libasound2t64), natijada Chromium bog'liqliklari
# tusatdan topilmay qoladi.
FROM python:3.12-slim-bookworm

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Operator kabinetlariga kirish uchun brauzer (`browser_runner`).
#
# `playwright install --with-deps` ISHLATILMAYDI: u UBUNTU paket nomlarini
# so'raydi (`ttf-unifont`, `ttf-ubuntu-font-family`), Debian'da esa ular yo'q
# va qurilish "has no installation candidate" xatosi bilan yiqiladi.
# Shuning uchun kutubxonalar qo'lda, Debian nomlari bilan o'rnatiladi.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# FAQAT chromium — uchala brauzer obrazni behuda kattalashtiradi.
RUN python -m playwright install chromium

# Copy source code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

# Start command
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
