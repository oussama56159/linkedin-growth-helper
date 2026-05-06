FROM python:3.11-slim

# Install system dependencies for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    libxshmfence1 \
    libxfixes3 \
    libxrandr2 \
    libxcomposite1 \
    libxdamage1 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

RUN mkdir -p storage/logs

# Create cron job for daily health check
RUN echo "0 9 * * * cd /app && /usr/local/bin/python health_check.py >> /app/storage/logs/health_check.log 2>&1" > /etc/cron.d/health-check
RUN chmod 0644 /etc/cron.d/health-check
RUN crontab /etc/cron.d/health-check

# Create startup script
RUN echo '#!/bin/bash\n\
cron\n\
python run_with_restart.py\n\
' > /app/start.sh && chmod +x /app/start.sh

CMD ["/app/start.sh"]
