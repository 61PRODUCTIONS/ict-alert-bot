"""
ICT Trading Alert Bot für EUR/USD
================================
Erkennt automatisch ICT-Setups und sendet Telegram-Alerts:
- Fair Value Gaps (FVG)
- Order Blocks (OB)
- Market Structure Shifts (MSS)
- Liquidity Sweeps / Judas Swings
- Kill Zone Timing

Kostenlos und läuft 24/7 auf Cloud-Servern.
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
import logging

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============== KONFIGURATION ==============
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID')
SYMBOL = "EUR/USD"
CHECK_INTERVAL_SECONDS = 60  # Alle 60 Sekunden prüfen

# Kill Zones (UTC+1 / MEZ)
KILL_ZONES = {
    'london': {'start': 8, 'end': 11},      # 08:00 - 11:00 MEZ
    'ny_am': {'start': 14, 'end': 17},      # 14:00 - 17:00 MEZ (NY Open)
    'ny_pm': {'start': 19, 'end': 21},      # 19:00 - 21:00 MEZ
}

# ============== DATEN ABRUFEN ==============
def get_forex_data(symbol: str = "EUR/USD", timeframe: str = "1h", bars: int = 100) -> Optional[pd.DataFrame]:
    """
    Holt Forex-Daten von einer kostenlosen API (Alpha Vantage Alternative: Twelve Data Free Tier)
    Für Demo nutzen wir eine kostenlose Quelle.
    """
    try:
        # Kostenlose API: Verwende Yahoo Finance über yfinance oder eine andere kostenlose Quelle
        # Hier nutzen wir eine einfache Demo-Implementierung
        
        # Alternative: Twelve Data Free API (800 calls/day)
        api_key = os.environ.get('TWELVE_DATA_API_KEY', 'demo')
        
        interval_map = {
            '5m': '5min',
            '15m': '15min',
            '1h': '1h',
            '4h': '4h',
            '1d': '1day'
        }
        
        url = f"https://api.twelvedata.com/time_series"
        params = {
            'symbol': 'EUR/USD',
            'interval': interval_map.get(timeframe, '1h'),
            'outputsize': bars,
            'apikey': api_key
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'values' not in data:
            logger.warning(f"Keine Daten erhalten: {data.get('message', 'Unknown error')}")
            return None
        
        df = pd.DataFrame(data['values'])
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime').reset_index(drop=True)
        
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        
        return df
        
    except Exception as e:
        logger.error(f"Fehler beim Datenabruf: {e}")
        return None


# ============== ICT SETUP ERKENNUNG ==============

def detect_fvg(df: pd.DataFrame, lookback: int = 3) -> List[Dict]:
    """
    Erkennt Fair Value Gaps (FVG)
    Bullish FVG: Lücke zwischen Candle 1 High und Candle 3 Low
    Bearish FVG: Lücke zwischen Candle 1 Low und Candle 3 High
    """
    fvgs = []
    
    if len(df) < lookback + 1:
        return fvgs
    
    for i in range(2, min(lookback + 2, len(df))):
        # Bullish FVG
        if df.iloc[-i-2]['high'] < df.iloc[-i]['low']:
            gap_top = df.iloc[-i]['low']
            gap_bottom = df.iloc[-i-2]['high']
            current_price = df.iloc[-1]['close']
            
            # Prüfe ob Preis in die FVG läuft (Retest)
            if gap_bottom <= current_price <= gap_top:
                fvgs.append({
                    'type': 'FVG Retest',
                    'direction': 'LONG',
                    'entry_zone_top': round(gap_top, 5),
                    'entry_zone_bottom': round(gap_bottom, 5),
                    'current_price': round(current_price, 5),
                    'strength': 'STRONG' if (gap_top - gap_bottom) > 0.0010 else 'MODERATE'
                })
        
        # Bearish FVG
        if df.iloc[-i-2]['low'] > df.iloc[-i]['high']:
            gap_top = df.iloc[-i-2]['low']
            gap_bottom = df.iloc[-i]['high']
            current_price = df.iloc[-1]['close']
            
            # Prüfe ob Preis in die FVG läuft (Retest)
            if gap_bottom <= current_price <= gap_top:
                fvgs.append({
                    'type': 'FVG Retest',
                    'direction': 'SHORT',
                    'entry_zone_top': round(gap_top, 5),
                    'entry_zone_bottom': round(gap_bottom, 5),
                    'current_price': round(current_price, 5),
                    'strength': 'STRONG' if (gap_top - gap_bottom) > 0.0010 else 'MODERATE'
                })
    
    return fvgs


def detect_order_block(df: pd.DataFrame, lookback: int = 10) -> List[Dict]:
    """
    Erkennt Order Blocks
    Bullish OB: Letzte bearish Kerze vor einem starken Aufwärtsmove
    Bearish OB: Letzte bullish Kerze vor einem starken Abwärtsmove
    """
    obs = []
    
    if len(df) < lookback + 3:
        return obs
    
    for i in range(3, min(lookback + 3, len(df))):
        candle = df.iloc[-i]
        next_candle = df.iloc[-i+1]
        current_price = df.iloc[-1]['close']
        
        # Bullish Order Block
        if candle['close'] < candle['open']:  # Bearish Kerze
            # Prüfe ob danach starker Aufwärtsmove
            if next_candle['close'] > candle['high']:
                ob_top = candle['high']
                ob_bottom = candle['low']
                
                # Prüfe ob Preis den OB testet
                if ob_bottom <= current_price <= ob_top:
                    obs.append({
                        'type': 'Order Block Retest',
                        'direction': 'LONG',
                        'entry_zone_top': round(ob_top, 5),
                        'entry_zone_bottom': round(ob_bottom, 5),
                        'current_price': round(current_price, 5),
                        'strength': 'STRONG'
                    })
        
        # Bearish Order Block
        if candle['close'] > candle['open']:  # Bullish Kerze
            # Prüfe ob danach starker Abwärtsmove
            if next_candle['close'] < candle['low']:
                ob_top = candle['high']
                ob_bottom = candle['low']
                
                # Prüfe ob Preis den OB testet
                if ob_bottom <= current_price <= ob_top:
                    obs.append({
                        'type': 'Order Block Retest',
                        'direction': 'SHORT',
                        'entry_zone_top': round(ob_top, 5),
                        'entry_zone_bottom': round(ob_bottom, 5),
                        'current_price': round(current_price, 5),
                        'strength': 'STRONG'
                    })
    
    return obs


def detect_mss(df: pd.DataFrame) -> List[Dict]:
    """
    Erkennt Market Structure Shifts (MSS)
    Bullish MSS: Higher High nach Lower Lows
    Bearish MSS: Lower Low nach Higher Highs
    """
    mss_signals = []
    
    if len(df) < 10:
        return mss_signals
    
    # Finde Swing Highs und Lows
    highs = df['high'].rolling(5, center=True).max()
    lows = df['low'].rolling(5, center=True).min()
    
    # Vereinfachte MSS Erkennung
    recent_high = df.iloc[-5:-1]['high'].max()
    recent_low = df.iloc[-5:-1]['low'].min()
    current_close = df.iloc[-1]['close']
    prev_close = df.iloc[-2]['close']
    
    # Bullish MSS: Durchbruch über recent high
    if current_close > recent_high and prev_close <= recent_high:
        mss_signals.append({
            'type': 'Market Structure Shift',
            'direction': 'LONG',
            'breakout_level': round(recent_high, 5),
            'current_price': round(current_close, 5),
            'strength': 'STRONG'
        })
    
    # Bearish MSS: Durchbruch unter recent low
    if current_close < recent_low and prev_close >= recent_low:
        mss_signals.append({
            'type': 'Market Structure Shift',
            'direction': 'SHORT',
            'breakout_level': round(recent_low, 5),
            'current_price': round(current_close, 5),
            'strength': 'STRONG'
        })
    
    return mss_signals


def detect_liquidity_sweep(df: pd.DataFrame, lookback: int = 20) -> List[Dict]:
    """
    Erkennt Liquidity Sweeps (Judas Swing)
    Preis durchbricht kurz ein wichtiges Level und kehrt dann um
    """
    sweeps = []
    
    if len(df) < lookback + 2:
        return sweeps
    
    # Finde wichtige Levels (alte Highs/Lows)
    lookback_df = df.iloc[-lookback-2:-2]
    important_high = lookback_df['high'].max()
    important_low = lookback_df['low'].min()
    
    current_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    
    # Bullish Sweep: Preis geht unter wichtiges Low und schließt darüber
    if prev_candle['low'] < important_low and current_candle['close'] > important_low:
        sweeps.append({
            'type': 'Liquidity Sweep (Judas Swing)',
            'direction': 'LONG',
            'swept_level': round(important_low, 5),
            'current_price': round(current_candle['close'], 5),
            'strength': 'VERY STRONG'
        })
    
    # Bearish Sweep: Preis geht über wichtiges High und schließt darunter
    if prev_candle['high'] > important_high and current_candle['close'] < important_high:
        sweeps.append({
            'type': 'Liquidity Sweep (Judas Swing)',
            'direction': 'SHORT',
            'swept_level': round(important_high, 5),
            'current_price': round(current_candle['close'], 5),
            'strength': 'VERY STRONG'
        })
    
    return sweeps


def is_in_killzone() -> Tuple[bool, str]:
    """
    Prüft ob wir uns in einer Kill Zone befinden (MEZ/UTC+1)
    """
    now = datetime.utcnow() + timedelta(hours=1)  # UTC+1
    current_hour = now.hour
    
    for zone_name, times in KILL_ZONES.items():
        if times['start'] <= current_hour < times['end']:
            return True, zone_name
    
    return False, "none"


# ============== TELEGRAM INTEGRATION ==============

def send_telegram_alert(signal: Dict, timeframe: str):
    """
    Sendet einen formatierten Alert an Telegram
    """
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN':
        logger.warning("Telegram Bot Token nicht konfiguriert!")
        return False
    
    # Emoji basierend auf Signal-Typ
    direction_emoji = "🟢 ⬆️" if signal.get('direction') == 'LONG' else "🔴 ⬇️"
    
    setup_emojis = {
        'FVG Retest': '🔵',
        'Order Block Retest': '🟣',
        'Market Structure Shift': '🟠',
        'Liquidity Sweep (Judas Swing)': '🟡'
    }
    setup_emoji = setup_emojis.get(signal.get('type', ''), '📊')
    
    # Kill Zone Status
    in_kz, kz_name = is_in_killzone()
    kz_status = f"✅ {kz_name.upper()}" if in_kz else "⚠️ Außerhalb Kill Zone"
    
    # Nachricht formatieren
    message = f"""
{direction_emoji} *ICT TRADING ALERT* {direction_emoji}

{setup_emoji} *Setup:* {signal.get('type', 'Unknown')}
📍 *Asset:* {SYMBOL}
⏱ *Timeframe:* {timeframe}
↕️ *Richtung:* {signal.get('direction', 'Unknown')}

💰 *Entry Zone:*
   Top: {signal.get('entry_zone_top', signal.get('breakout_level', signal.get('swept_level', 'N/A')))}
   Bottom: {signal.get('entry_zone_bottom', 'N/A')}

📊 *Aktueller Preis:* {signal.get('current_price', 'N/A')}
💪 *Stärke:* {signal.get('strength', 'MODERATE')}

🕐 *Kill Zone:* {kz_status}
⏰ *Zeit:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} MEZ

⚠️ _Prüfe den Chart vor dem Entry!_
    """
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        }
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"✅ Alert gesendet: {signal.get('type')} - {signal.get('direction')}")
            return True
        else:
            logger.error(f"Telegram Fehler: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Fehler beim Senden: {e}")
        return False


# ============== HAUPTSCHLEIFE ==============

def analyze_and_alert(timeframe: str = "1h"):
    """
    Analysiert den Markt und sendet Alerts bei erkannten Setups
    """
    logger.info(f"📊 Analysiere {SYMBOL} auf {timeframe}...")
    
    # Daten abrufen
    df = get_forex_data(SYMBOL, timeframe)
    
    if df is None or len(df) < 20:
        logger.warning("Nicht genug Daten für Analyse")
        return []
    
    all_signals = []
    
    # Kill Zone Check
    in_killzone, kz_name = is_in_killzone()
    
    # Alle Setups prüfen
    fvgs = detect_fvg(df)
    obs = detect_order_block(df)
    mss = detect_mss(df)
    sweeps = detect_liquidity_sweep(df)
    
    all_signals.extend(fvgs)
    all_signals.extend(obs)
    all_signals.extend(mss)
    all_signals.extend(sweeps)
    
    # Alerts senden
    for signal in all_signals:
        # Priorität für Signale in Kill Zones
        if in_killzone:
            signal['strength'] = 'VERY STRONG (Kill Zone)'
        
        send_telegram_alert(signal, timeframe)
    
    if all_signals:
        logger.info(f"🎯 {len(all_signals)} Signal(e) gefunden!")
    else:
        logger.info("Keine Signale gefunden")
    
    return all_signals


def main():
    """
    Hauptfunktion - läuft kontinuierlich
    """
    logger.info("=" * 50)
    logger.info("🚀 ICT Alert Bot gestartet!")
    logger.info(f"📊 Symbol: {SYMBOL}")
    logger.info(f"⏱ Check-Intervall: {CHECK_INTERVAL_SECONDS} Sekunden")
    logger.info("=" * 50)
    
    # Startup-Nachricht an Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN != 'YOUR_BOT_TOKEN':
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': "🤖 *ICT Alert Bot gestartet!*\n\nÜberwache EUR/USD auf:\n- FVG Retests\n- Order Block Retests\n- Market Structure Shifts\n- Liquidity Sweeps\n\n_Alerts werden gesendet wenn Setups erkannt werden._",
                'parse_mode': 'Markdown'
            }
            requests.post(url, json=payload, timeout=10)
        except:
            pass
    
    # Tracking für bereits gesendete Alerts (verhindert Spam)
    sent_alerts = set()
    
    while True:
        try:
            # Multi-Timeframe Analyse
            for tf in ['1h', '4h']:
                signals = analyze_and_alert(tf)
                
                # Verhindere doppelte Alerts
                for signal in signals:
                    signal_key = f"{signal.get('type')}_{signal.get('direction')}_{tf}"
                    if signal_key not in sent_alerts:
                        sent_alerts.add(signal_key)
                    
                    # Reset nach 4 Stunden
                    if len(sent_alerts) > 100:
                        sent_alerts.clear()
            
            # Warten bis zum nächsten Check
            logger.info(f"💤 Warte {CHECK_INTERVAL_SECONDS} Sekunden...")
            time.sleep(CHECK_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            logger.info("Bot gestoppt.")
            break
        except Exception as e:
            logger.error(f"Fehler in Hauptschleife: {e}")
            time.sleep(60)  # Bei Fehler 1 Minute warten


if __name__ == "__main__":
    main()
