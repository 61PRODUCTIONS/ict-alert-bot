# Dein kostenloser ICT Alert Bot: Deployment-Anleitung

**Ziel:** Deinen persönlichen ICT Trading Alert Bot 24/7 kostenlos in der Cloud laufen lassen.

**Was du brauchst:**
- ✅ Ein GitHub-Konto (kostenlos)
- ✅ Ein Railway-Konto (kostenlos)
- ✅ Deinen Telegram Bot Token & Chat ID

---

## Teil 1: Vorbereitung (ca. 5 Minuten)

### Schritt 1: Telegram Bot Token & Chat ID

Falls du es noch nicht getan hast:

1.  **Bot Token:** Schreibe "@BotFather" in Telegram, erstelle einen neuen Bot mit `/newbot` und **kopiere den HTTP API Token**.
2.  **Chat ID:** Schreibe "@userinfobot" in Telegram, starte den Chat und **kopiere deine Chat-ID**.

### Schritt 2: (Optional) Twelve Data API Key

Der Bot kann eine Demo-Datenquelle nutzen, aber für zuverlässigere Daten empfehle ich einen kostenlosen API-Schlüssel von [Twelve Data](https://twelvedata.com/pricing).

1.  Registriere dich für den **Free Plan**.
2.  Gehe zu deinem Dashboard und **kopiere den API Key**.

---

## Teil 2: Code auf GitHub hochladen (ca. 5 Minuten)

Damit der Cloud-Server auf deinen Code zugreifen kann, laden wir ihn auf GitHub hoch.

1.  **Neues Repository erstellen:**
    *   Gehe zu [GitHub](https://github.com) und logge dich ein.
    *   Klicke oben rechts auf das "+" und wähle "**New repository**".
    *   Gib einen Namen ein (z.B. `ict-alert-bot`).
    *   Wähle "**Public**".
    *   Klicke auf "**Create repository**".

2.  **Dateien hochladen:**
    *   Entpacke die `ict_alert_bot.zip` Datei, die ich dir schicke.
    *   In deinem neuen GitHub Repository, klicke auf "**Add file**" -> "**Upload files**".
    *   Ziehe **alle 5 Dateien** (`ict_alert_bot.py`, `requirements.txt`, `Dockerfile`, `railway.json`, `render.yaml`) in das Upload-Feld.
    *   Klicke auf "**Commit changes**".

---

## Teil 3: Auf Railway deployen (ca. 10 Minuten)

Railway ist ein Cloud-Anbieter, der perfekt für solche Projekte ist und einen großzügigen kostenlosen Plan hat.

1.  **Railway Account erstellen:**
    *   Gehe zu [railway.app](https://railway.app).
    *   Klicke auf "**Login**" und melde dich mit deinem **GitHub-Konto** an.

2.  **Neues Projekt erstellen:**
    *   Klicke im Railway Dashboard auf "**New Project**".
    *   Wähle "**Deploy from GitHub repo**".
    *   Wähle dein `ict-alert-bot` Repository aus.

3.  **Deployment abwarten:**
    *   Railway erkennt automatisch die `Dockerfile` und `railway.json` und beginnt mit dem Deployment. Das dauert ein paar Minuten.
    *   Es wird wahrscheinlich zuerst fehlschlagen, weil die Secrets fehlen. Das ist normal.

4.  **Secrets (Environment Variables) hinzufügen:**
    *   Klicke in deinem Railway-Projekt auf den Service (er heißt wahrscheinlich `ict-alert-bot`).
    *   Gehe zum Tab "**Variables**".
    *   Klicke auf "**New Variable**" und füge folgende Secrets hinzu:
        *   `TELEGRAM_BOT_TOKEN` = Dein Bot Token
        *   `TELEGRAM_CHAT_ID` = Deine Chat ID
        *   `TWELVE_DATA_API_KEY` = Dein (optionaler) Twelve Data API Key

5.  **Neu deployen:**
    *   Nachdem du die Variablen hinzugefügt hast, wird Railway automatisch eine neue Version deployen.
    *   Gehe zum "**Deployments**" Tab und schaue dir die Logs an. Du solltest sehen, dass der Bot erfolgreich startet!

---

## FERTIG! 🎉

Dein ICT Alert Bot läuft jetzt **24/7 in der Cloud** und überwacht EUR/USD für dich. Du erhältst ab sofort eine Telegram-Nachricht, sobald eines der ICT-Setups erkannt wird.

Du musst nichts weiter tun. Dein PC kann ausgeschaltet sein, der Bot läuft weiter.

Wenn du Fragen hast oder etwas nicht klappt, sag einfach Bescheid!
