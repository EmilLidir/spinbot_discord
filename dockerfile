# Use an official Python slim image as a parent image
FROM python:3.12-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies needed for Chrome, ChromeDriver, and basic utilities
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    # Chrome dependencies
    libglib2.0-0 \
    libnss3 \
    libgconf-2-4 \
    libfontconfig1 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-dri3-0 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxss1 \
    libxtst6 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libexpat1 \
    libgbm1 \
    libgtk-3-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    # End Chrome dependencies
    xvfb \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Install Google Chrome Stable
RUN curl -sS -o - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install ChromeDriver
# IMPORTANT: Match this with the google-chrome-stable version.
# Find versions at: https://googlechromelabs.github.io/chrome-for-testing/
ARG CHROMEDRIVER_VERSION="136.0.7103.94"
RUN wget -O /tmp/chromedriver.zip "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${CHROMEDRIVER_VERSION}/linux64/chromedriver-linux64.zip" \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && mv /usr/local/bin/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver \
    && rm -rf /tmp/chromedriver.zip /usr/local/bin/chromedriver-linux64 \
    && chmod +x /usr/local/bin/chromedriver

# Verify versions (optional, but good for debugging build)
RUN google-chrome --version
RUN chromedriver --version

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure your main script is executable if needed, though python command handles it
# RUN chmod +x ./spin_bot_with_recaptcha.py

CMD ["python", "main.py"]