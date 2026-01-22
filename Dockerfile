FROM python:3.11-slim

WORKDIR /app

# Dependencies installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bot-Code kopieren
COPY ict_alert_bot.py .

# Bot starten
CMD ["python", "ict_alert_bot.py"]
