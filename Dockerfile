# Use Python Slim as base
FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive
ENV PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright

# Fix Playwright dependencies (need some system libs)
RUN sed -i 's/main/main non-free non-free-firmware/g' /etc/apt/sources.list.d/debian.sources || \
    sed -i 's/main/main non-free non-free-firmware/g' /etc/apt/sources.list
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    sqlite3 \
    unrar \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and chromium browser (needed for scraping)
RUN playwright install --with-deps chromium

# Copy app code
COPY app /app/app

# Expose port
EXPOSE 8000

# Start command with reload for development # , "--reload"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"] 
