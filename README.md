# ICT Alert Bot v8.0 - ULTIMATE

Ein automatisierter Forex-Alert-Bot, der auf **ICT (Inner Circle Trader) Konzepten** basiert. Der Bot scannt 8 Währungspaare auf mehreren Zeitebenen und sendet Telegram-Alerts, wenn High-Probability-Setups erkannt werden.

## Strategie-Übersicht

Der Bot implementiert eine Multi-Timeframe-Analyse nach ICT-Prinzipien:

| Timeframe | Funktion | Analyse |
|-----------|----------|---------|
| **Daily** | Trend-Filter | Nur Trades in Richtung des Daily Trends |
| **H4** | Bias-Bestimmung | BOS/CHoCH, Swing-Struktur (HH/HL, LH/LL) |
| **H1** | POI-Erkennung | Fair Value Gaps, Order Blocks, Liquidity |
| **M15** | Zone-Entry | Prüfung ob Preis in POI-Zone läuft |
| **M5** | Trigger | **Du machst den M5-Trigger selbst im Chart!** |

## Features

**Confluence Score (A+ bis C):** Jedes Setup wird mit bis zu 8 Punkten bewertet, basierend auf Daily Trend, H4 Bias, Zone-Qualität, Kill Zone, Pair-Typ und mehr.

**Alert-Priorität:**
- 🔴 **URGENT** - A/A+ Grade in Kill Zone
- 🟡 **NORMAL** - A/A+/B+/B Grade
- ⚪ **INFO** - Alle anderen

**Kill Zones:**
- London Open: 08:00-11:00 MEZ
- New York: 14:00-17:00 MEZ
- London Close: 17:00-19:00 MEZ
- Asian Session: 01:00-04:00 MEZ (nur JPY)

**Weitere Features:**
- Fixer Stop-Loss (18 Pips)
- Zone-Cooldown (2h pro Zone)
- Premium/Discount basierend auf Daily Range
- Mitigierte Zonen werden ignoriert
- Nur 1 POI pro Paar (der relevanteste)

## Unterstützte Paare

| Hauptpaare | Sekundärpaare |
|------------|---------------|
| EUR/USD | EUR/GBP |
| GBP/USD | USD/CAD |
| USD/JPY | NZD/USD |
| AUD/USD | USD/CHF |

## Installation

### 1. Repository klonen
```bash
git clone https://github.com/61PRODUCTIONS/ict-alert-bot.git
cd ict-alert-bot
```

### 2. Dependencies installieren
```bash
pip install -r requirements.txt
```

### 3. Environment Variables setzen
```bash
export TELEGRAM_BOT_TOKEN="dein_bot_token"
export TELEGRAM_CHAT_ID="deine_chat_id"
export TWELVE_DATA_API_KEY="dein_api_key"  # Optional, Yahoo Finance als Fallback
```

### 4. Bot starten
```bash
python ict_alert_bot.py
```

## Deployment auf Render

1. Forke dieses Repository
2. Erstelle einen neuen "Background Worker" auf [Render](https://render.com)
3. Verbinde dein GitHub Repository
4. Setze die Environment Variables (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TWELVE_DATA_API_KEY)
5. Deploy!

Die `render.yaml` ist bereits konfiguriert.

## Alert-Format

```
🔴 URGENT
━━━━━━━━━━━━━━━━━━━━━━

🟢 LONG - EUR/USD
⭐ HAUPTPAAR
Grade: A+ (7/8 Punkte)

━━━━━━━━━━━━━━━━━━━━━━
📊 ANALYSE:
━━━━━━━━━━━━━━━━━━━━━━

Daily: BULLISH (HH + HL)
H4: BULLISH (BOS 3B/1S)
Kill Zone: London Open
Zeit: PRIME TIME

━━━━━━━━━━━━━━━━━━━━━━
🎯 POINT OF INTEREST:
━━━━━━━━━━━━━━━━━━━━━━

Typ: Fair Value Gap
Zone: 1.08500 - 1.08550
Qualität: DISCOUNT (Ideal)

━━━━━━━━━━━━━━━━━━━━━━
💰 TRADE DETAILS:
━━━━━━━━━━━━━━━━━━━━━━

Entry: 1.08550
SL: 1.08370 (18 Pips)
TP1 (1:1): 1.08730
TP2 (1:1.5): 1.08820
TP3 (1:2): 1.08910

━━━━━━━━━━━━━━━━━━━━━━
⏰ WARTE AUF M5 TRIGGER!
━━━━━━━━━━━━━━━━━━━━━━
Suche: MSS, BOS, CHoCH, Engulfing
```

## Wichtiger Hinweis

**Dies ist ein Alert-System, kein automatischer Trading-Bot!**

Der Bot zeigt dir, WANN und WO ein potenzielles Setup existiert. Du musst dann:
1. Den M5-Chart öffnen
2. Auf einen Trigger warten (MSS, BOS, CHoCH, Engulfing)
3. Selbst entscheiden, ob du den Trade eingehst

## Lizenz

MIT License

## Autor

Erstellt mit Manus AI
