FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Operator kabinetlariga kirish uchun brauzer (`browser_runner`).
# FAQAT chromium — uchala brauzer obrazni behuda kattalashtiradi.
# `--with-deps` kerakli tizim kutubxonalarini ham o'rnatadi; ularsiz
# Chromium slim obrazda umuman ishga tushmaydi.
RUN python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Copy source code
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

EXPOSE 8000

# Start command
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
