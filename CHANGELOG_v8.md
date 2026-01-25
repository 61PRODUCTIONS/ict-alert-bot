# ICT Alert Bot - CHANGELOG

## Version 8.1 - ULTIMATE 10/10 (Jan 23, 2026)

Dies ist das finale "10/10"-Release mit M5 Entry Zones für präzisere Entries.

### ✨ Neue Features in v8.1

**EUR/CHF hinzugefügt:** Das 9. Währungspaar ist jetzt verfügbar. EUR/CHF ist als Sekundärpaar klassifiziert und hat eine spezielle Kill-Zone-Erkennung für die Zürich/London Session.

**M5 FVG Entry Zones:** Der Bot scannt jetzt M5 FVGs innerhalb der HTF POI Zone und zeigt diese im Alert an. Das ermöglicht präzisere Entries wie in deinem Trade-Beispiel vom 21.08.24.

**Alert-Format erweitert:** Der Alert zeigt jetzt zusätzlich zur HTF Zone auch die M5 Entry Zones mit Level-Kennzeichnung (LVL.1, LVL.2, etc.).

**Confluence Score angepasst:** M5 FVG gibt jetzt +1 Bonus-Punkt zum Confluence Score, da ein M5 FVG innerhalb der HTF Zone ein stärkeres Setup bedeutet.

**Trigger-Hinweis geändert:** Der Alert sagt jetzt "Warte auf M1 Trigger" statt "M5 Trigger", da du mit den M5 Entry Zones bereits den M5 hast und nur noch M1 für den finalen Entry brauchst.

### 📊 Strategie-Flow v8.1

```
Daily Trend → H4 Bias → H1 POI → M15 Zone Entry → M5 FVG (NEU!) → Du: M1 Trigger
```

### 🎯 Alert-Beispiel mit M5 Zones

```
🎯 HTF POINT OF INTEREST:
Typ: Fair Value Gap
Zone: 0.95056 - 0.95085
Qualität: DISCOUNT (Ideal)

📍 M5 ENTRY ZONES:

🎯 M5 FVG LVL.1
   Zone: 0.95056 - 0.95070

🎯 M5 FVG LVL.2
   Zone: 0.95072 - 0.95080
```

---

## Version 8.0 - ULTIMATE (Jan 23, 2026)

Das erste "10/10"-Release mit allen Kernoptimierungen.

### Features v8.0

- Daily Trend Filter
- H4 Bias (BOS/CHoCH)
- H1 POI (FVG/OB)
- M15 Zone Entry Check
- Premium/Discount (Daily Range)
- Kill Zones + Asian Session
- Confluence Score (A+ bis C)
- Alert-Priorität (URGENT/NORMAL/INFO)
- Fixer SL (18 Pips)
- Zone Cooldown (2h)
- Mindest-Zonengröße (5 Pips)
- Mitigierte Zonen ignoriert
- 8 Forex-Paare
- TwelveData + Yahoo Fallback
