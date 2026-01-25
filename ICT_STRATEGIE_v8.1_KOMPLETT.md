# ICT Alert Bot v8.1 - Komplette Strategie-Dokumentation

## Übersicht

Der ICT Alert Bot v8.1 ist ein automatisiertes Alert-System für Forex-Trading basierend auf **Inner Circle Trader (ICT) Konzepten**. Der Bot scannt 9 Währungspaare auf mehreren Zeitebenen und sendet Telegram-Alerts, wenn High-Probability-Setups erkannt werden.

**Wichtig:** Dies ist ein **Alert-System**, kein automatischer Trading-Bot. Du erhältst Alerts mit allen relevanten Informationen und machst den finalen M1-Entry selbst.

---

## Währungspaare (9 Stück)

### Hauptpaare (4)
| Paar | Pip-Wert | Max Spread | Besonderheit |
|------|----------|------------|--------------|
| EUR/USD | 0.0001 | 1.5 Pips | Liquidestes Paar |
| GBP/USD | 0.0001 | 2.0 Pips | Volatil |
| USD/JPY | 0.01 | 1.5 Pips | Asian Session |
| AUD/USD | 0.0001 | 2.0 Pips | - |

### Sekundärpaare (5)
| Paar | Pip-Wert | Max Spread | Besonderheit |
|------|----------|------------|--------------|
| **EUR/CHF** | 0.0001 | 2.5 Pips | **NEU! Zürich/London KZ** |
| EUR/GBP | 0.0001 | 2.5 Pips | - |
| USD/CAD | 0.0001 | 2.5 Pips | - |
| NZD/USD | 0.0001 | 3.0 Pips | - |
| USD/CHF | 0.0001 | 2.5 Pips | - |

---

## Multi-Timeframe Analyse

### Der komplette Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    DAILY TIMEFRAME                               │
│  ➜ Trend-Filter: Nur in Richtung des Daily Trends traden        │
│  ➜ Methode: Swing-Struktur (HH/HL = Bullish, LH/LL = Bearish)   │
│  ➜ Fallback: EMA20 Vergleich                                    │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      H4 TIMEFRAME                                │
│  ➜ Bias-Bestimmung: BOS/CHoCH mit smartmoneyconcepts Library    │
│  ➜ Swing-Analyse: Higher Highs/Lows oder Lower Highs/Lows       │
│  ➜ KONFLIKT-CHECK: Daily und H4 müssen übereinstimmen!          │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      H1 TIMEFRAME                                │
│  ➜ POI-Erkennung: Fair Value Gaps (FVG) und Order Blocks (OB)   │
│  ➜ Nur 1 POI pro Paar: Der nächste zum aktuellen Preis          │
│  ➜ Mindestgröße: 5 Pips                                         │
│  ➜ Mitigierte Zonen: Werden komplett ignoriert                  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     M15 TIMEFRAME                                │
│  ➜ Zone Entry Check: Ist der Preis in/nahe der HTF Zone?        │
│  ➜ Toleranz: 10 Pips                                            │
│  ➜ Qualität: IDEAL (letzte 3 Kerzen) oder GUT (älter)           │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      M5 TIMEFRAME (NEU!)                         │
│  ➜ M5 FVG Scan: Sucht FVGs innerhalb der HTF Zone               │
│  ➜ Max 3 Zones: LVL.1, LVL.2, LVL.3                             │
│  ➜ Mindestgröße: 3 Pips                                         │
│  ➜ Entry wird am besten M5 FVG berechnet                        │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    🚨 TELEGRAM ALERT 🚨                          │
│  ➜ Du erhältst: HTF Zone + M5 Entry Zones + Entry/SL/TP         │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      M1 TIMEFRAME (DU!)                          │
│  ➜ Dein Job: Warte auf Trigger im M1 Chart                      │
│  ➜ Trigger: MSS, BOS, CHoCH, Engulfing                          │
│  ➜ Entry: Am M5 FVG Level aus dem Alert                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## POI-Typen (Points of Interest)

### 1. Fair Value Gap (FVG)

**Definition:** Eine Preislücke zwischen drei aufeinanderfolgenden Kerzen, wo die Wicks nicht überlappen.

**Bullish FVG:**
```
Kerze 1: High = 1.0800
Kerze 2: (Impulskerze)
Kerze 3: Low = 1.0820
➜ Gap zwischen 1.0800 und 1.0820
```

**Bearish FVG:**
```
Kerze 1: Low = 1.0850
Kerze 2: (Impulskerze)
Kerze 3: High = 1.0830
➜ Gap zwischen 1.0830 und 1.0850
```

**Erkennung:** smartmoneyconcepts Library mit Mitigation-Tracking

### 2. Order Block (OB)

**Definition:** Die letzte gegensätzliche Kerze vor einer starken Bewegung (Displacement).

**Bullish Order Block:**
- Letzte bearishe Kerze vor einem Swing Low
- Gefolgt von starker bullisher Bewegung (>1.5x Kerzengröße)

**Bearish Order Block:**
- Letzte bullishe Kerze vor einem Swing High
- Gefolgt von starker bearisher Bewegung (>1.5x Kerzengröße)

**Mindestgröße:** 5-50 Pips

---

## Premium/Discount Zonen

Basierend auf der **Daily Range** (letzte 5 Tage):

```
Premium Zone (oberes Drittel)
─────────────────────────────── Range High
        ▲
        │  PREMIUM = Ideal für SHORT
        │
─────────────────────────────── Equilibrium (50%)
        │
        │  DISCOUNT = Ideal für LONG
        ▼
─────────────────────────────── Range Low
Discount Zone (unteres Drittel)
```

**Zone-Qualität im Alert:**
- `DISCOUNT (Ideal)` - LONG in Discount Zone
- `PREMIUM (Ideal)` - SHORT in Premium Zone
- `EQUILIBRIUM (Gut)` - Mittlerer Bereich
- `PREMIUM/DISCOUNT (Riskant)` - Gegen die Zone

---

## Kill Zones (Handelszeiten)

| Kill Zone | UTC Zeit | MEZ Zeit | Paare |
|-----------|----------|----------|-------|
| **Asian Session** | 00:00-03:00 | 01:00-04:00 | JPY-Paare |
| **Zürich/London** | 07:00-10:00 | 08:00-11:00 | CHF-Paare |
| **London Open** | 07:00-10:00 | 08:00-11:00 | Alle |
| **New York** | 13:00-16:00 | 14:00-17:00 | Alle |
| **London Close** | 16:00-18:00 | 17:00-19:00 | Alle |

**Außerhalb Kill Zone:** Setup wird trotzdem gesendet, aber mit Warnung und niedrigerem Score.

---

## Confluence Score System

Jedes Setup wird mit **0-8 Punkten** bewertet:

| Kriterium | Punkte | Beschreibung |
|-----------|--------|--------------|
| Daily Trend | +2 | Trade in Richtung Daily Trend |
| H4 Bias | +1 | Trade in Richtung H4 Bias |
| Zone Qualität | +1 | Ideal (Discount für LONG, Premium für SHORT) |
| Entry Qualität | +1 | Frischer M15 Entry (letzte 3 Kerzen) |
| Kill Zone | +1 | In aktiver Kill Zone |
| Hauptpaar | +1 | EUR/USD, GBP/USD, USD/JPY, AUD/USD |
| M5 FVG | +1 | M5 FVG innerhalb HTF Zone gefunden |
| **Gesamt** | **8** | **Maximum** |

### Grade-Einstufung

| Punkte | Grade | Bedeutung |
|--------|-------|-----------|
| 7-8 | **A+** | Perfektes Setup |
| 6 | **A** | Sehr gutes Setup |
| 5 | **B+** | Gutes Setup |
| 4 | **B** | Akzeptables Setup |
| 3 | **C+** | Schwaches Setup |
| 0-2 | **C** | Sehr schwaches Setup |

---

## Alert-Priorität

| Priorität | Emoji | Bedingung |
|-----------|-------|-----------|
| **URGENT** | 🔴 | Grade A+ oder A UND in Kill Zone |
| **NORMAL** | 🟡 | Grade A+, A, B+ oder B |
| **INFO** | ⚪ | Grade C+ oder C |

---

## Trade-Parameter

### Stop-Loss
- **Fix:** 18 Pips vom Entry
- **Nicht** zonenabhängig für konsistentes Risk-Management

### Take-Profits
| TP | Ratio | Berechnung |
|----|-------|------------|
| TP1 | 1:1 | Entry + 18 Pips |
| TP2 | 1:1.5 | Entry + 27 Pips |
| TP3 | 1:2 | Entry + 36 Pips |

### Entry-Berechnung
- **Mit M5 FVG:** Entry am oberen Rand (LONG) oder unteren Rand (SHORT) des besten M5 FVG
- **Ohne M5 FVG:** Entry am Rand der HTF Zone

---

## Zone-Cooldown

Nach einem Alert wird die Zone für **2 Stunden** gesperrt, um Spam zu vermeiden.

---

## Beispiel-Alert (v8.1)

```
🔴 URGENT
━━━━━━━━━━━━━━━━━━━━━━

🟢 LONG - EUR/CHF
📊 SEKUNDÄRPAAR
Grade: A+ (7/8 Punkte)

━━━━━━━━━━━━━━━━━━━━━━
📊 ANALYSE:
━━━━━━━━━━━━━━━━━━━━━━

Daily: BULLISH (HH + HL)
H4: BULLISH (BOS 3B/1S HH/HL)
Kill Zone: Zürich/London
Zeit: GOOD TIME

━━━━━━━━━━━━━━━━━━━━━━
🎯 HTF POINT OF INTEREST:
━━━━━━━━━━━━━━━━━━━━━━

Typ: Fair Value Gap
Zone: 0.95056 - 0.95085
Qualität: DISCOUNT (Ideal)

━━━━━━━━━━━━━━━━━━━━━━
📍 M5 ENTRY ZONES:
━━━━━━━━━━━━━━━━━━━━━━

🎯 M5 FVG LVL.1
   Zone: 0.95056 - 0.95070

🎯 M5 FVG LVL.2
   Zone: 0.95072 - 0.95080

━━━━━━━━━━━━━━━━━━━━━━
💰 TRADE DETAILS:
━━━━━━━━━━━━━━━━━━━━━━

Entry: 0.95070
SL: 0.94890 (18 Pips)
TP1 (1:1): 0.95250
TP2 (1:1.5): 0.95340
TP3 (1:2): 0.95430

━━━━━━━━━━━━━━━━━━━━━━
⏰ WARTE AUF M1 TRIGGER!
━━━━━━━━━━━━━━━━━━━━━━
Suche: MSS, BOS, CHoCH, Engulfing

14:32:15 MEZ
```

---

## Dein Workflow nach Alert

1. **Alert erhalten** → Prüfe Grade und Priorität
2. **Chart öffnen** → Gehe zum M1 Timeframe
3. **M5 FVG Zone markieren** → Die Zone aus dem Alert
4. **Warte auf Trigger:**
   - MSS (Market Structure Shift)
   - BOS (Break of Structure)
   - CHoCH (Change of Character)
   - Engulfing Candle
5. **Entry setzen** → Am M5 FVG Level
6. **SL/TP setzen** → Wie im Alert angegeben
7. **Trade managen** → Partials bei TP1, TP2

---

## Technische Details

### Datenquellen
1. **TwelveData API** (primär) - Benötigt API-Key
2. **Yahoo Finance** (Fallback) - Kostenlos

### Libraries
- `smartmoneyconcepts` - FVG, BOS/CHoCH, Swing-Erkennung
- `pandas` - Datenverarbeitung
- `requests` - API-Aufrufe

### Scan-Intervall
- Alle **5 Minuten** werden alle 9 Paare gescannt
- **2 Sekunden** Pause zwischen Paaren (Rate Limiting)

---

## Zusammenfassung: Warum 10/10?

| Aspekt | Status | Begründung |
|--------|--------|------------|
| Multi-Timeframe | ✅ | Daily → H4 → H1 → M15 → M5 |
| ICT-Konzepte | ✅ | FVG, OB, Premium/Discount, Kill Zones |
| Confluence | ✅ | 8-Punkte-System mit Grade |
| Präzision | ✅ | M5 FVG Entry Zones |
| Risk-Management | ✅ | Fixer SL, klare TPs |
| Spam-Schutz | ✅ | Zone Cooldown |
| Flexibilität | ✅ | 9 Paare, alle Sessions |
| Benutzerfreundlich | ✅ | Klare Alerts, du machst M1 |

**Die Strategie entspricht exakt deinem Trade-Beispiel vom 21.08.24 auf EUR/CHF!**
