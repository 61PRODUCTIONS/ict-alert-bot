"""
ICT/SMC B-Setup Trading Alert Bot v5.0 - FINAL
================================================
Multi-Pair Support: EUR/USD, GBP/USD, USD/JPY, AUD/USD

4-Timeframe Top-Down-Analyse:
1. H4  → BIAS bestimmen (EMA 200 + Market Structure)
2. H1  → Point of Interest finden (FVG, Order Block, Liquidity Sweep)
3. M15 → Warten bis Preis IN die H1-Zone reinläuft + Konflikt-Check
4. M5  → Entry-Trigger (MSS oder Engulfing)

OPTIMIERUNGEN v5.0:
✅ Premium/Discount Zone Filter (basierend auf DAILY Range - ICT konform!)
✅ Session-spezifische Logik
✅ Unmitigated Order Block Filter
✅ FVG Mitigation Tracking (NEU!)
✅ Timeframe Konflikt-Check (NEU!) - Keine Alerts bei entgegengesetzter M15 FVG
✅ Multi-Pair Support (4 Major Pairs)

NUR wenn ALLE Bedingungen erfüllt sind, wird ein Alert gesendet!
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum
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
CHECK_INTERVAL_SECONDS = 60  # Alle 60 Sekunden prüfen

# Multi-Pair Support - 4 Major Pairs
SYMBOLS = {
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X", 
    "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X"
}

# Pip-Werte für verschiedene Paare
PIP_VALUES = {
    "EUR/USD": 0.0001,
    "GBP/USD": 0.0001,
    "USD/JPY": 0.01,
    "AUD/USD": 0.0001
}

# ============== ENUMS & DATACLASSES ==============

class Bias(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class SignalType(Enum):
    FVG = "Fair Value Gap"
    ORDER_BLOCK = "Order Block"
    LIQUIDITY_SWEEP = "Liquidity Sweep"

class EntryType(Enum):
    MSS = "Market Structure Shift"
    ENGULFING = "Engulfing Candle"

class PriceZone(Enum):
    PREMIUM = "Premium"
    DISCOUNT = "Discount"
    EQUILIBRIUM = "Equilibrium"

@dataclass
class PointOfInterest:
    """Ein Point of Interest auf H1"""
    poi_type: SignalType
    direction: str
    zone_top: float
    zone_bottom: float
    price_zone: PriceZone
    is_unmitigated: bool
    timestamp: datetime

@dataclass
class ZoneEntry:
    """Bestätigung dass M15 in die Zone eingetreten ist"""
    entry_price: float
    zone_top: float
    zone_bottom: float
    timestamp: datetime

@dataclass
class EntryTrigger:
    """Ein Entry-Trigger auf M5"""
    trigger_type: EntryType
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    timestamp: datetime

@dataclass
class TradeSetup:
    """Ein komplettes Trade-Setup"""
    symbol: str
    bias: Bias
    bias_reason: str
    kill_zone: str
    session_alignment: str
    point_of_interest: PointOfInterest
    zone_entry: ZoneEntry
    entry_trigger: EntryTrigger
    confluence_score: int

# ============== KILL ZONES (MEZ/UTC+1) ==============

KILL_ZONES = {
    'london': {
        'start_hour': 8, 'start_min': 0, 
        'end_hour': 11, 'end_min': 0, 
        'priority': 4,
        'typical_behavior': 'continuation_or_reversal',
        'best_pairs': ['EUR/USD', 'GBP/USD']
    },
    'ny_open': {
        'start_hour': 14, 'start_min': 30, 
        'end_hour': 17, 'end_min': 0, 
        'priority': 5,
        'typical_behavior': 'high_volatility',
        'best_pairs': ['EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD']
    },
    'london_close': {
        'start_hour': 17, 'start_min': 0, 
        'end_hour': 19, 'end_min': 0, 
        'priority': 3,
        'typical_behavior': 'reversal',
        'best_pairs': ['EUR/USD', 'GBP/USD']
    },
}

# ============== MITIGATION TRACKING (NEU in v5.0) ==============
# Speicher für bereits mitigierte Order Blocks UND FVGs
mitigated_obs: Dict[str, List[Tuple[float, float, datetime]]] = {symbol: [] for symbol in SYMBOLS.keys()}
mitigated_fvgs: Dict[str, List[Tuple[float, float, datetime]]] = {symbol: [] for symbol in SYMBOLS.keys()}

def cleanup_old_mitigations():
    """Entfernt Mitigations die älter als 24 Stunden sind"""
    cutoff = datetime.now() - timedelta(hours=24)
    for symbol in SYMBOLS.keys():
        mitigated_obs[symbol] = [(t, b, ts) for t, b, ts in mitigated_obs.get(symbol, []) if ts > cutoff]
        mitigated_fvgs[symbol] = [(t, b, ts) for t, b, ts in mitigated_fvgs.get(symbol, []) if ts > cutoff]

def is_zone_unmitigated(symbol: str, zone_top: float, zone_bottom: float, zone_type: str) -> bool:
    """Prüft ob eine Zone (OB oder FVG) noch nicht mitigated wurde"""
    storage = mitigated_obs if zone_type == "OB" else mitigated_fvgs
    
    for (top, bottom, _) in storage.get(symbol, []):
        # Wenn sich die Zonen überlappen, ist die Zone bereits mitigated
        if not (zone_bottom > top or zone_top < bottom):
            return False
    return True

def mark_zone_as_mitigated(symbol: str, zone_top: float, zone_bottom: float, zone_type: str):
    """Markiert eine Zone als mitigated"""
    storage = mitigated_obs if zone_type == "OB" else mitigated_fvgs
    
    if symbol not in storage:
        storage[symbol] = []
    storage[symbol].append((zone_top, zone_bottom, datetime.now()))
    
    # Behalte nur die letzten 100 mitigated Zonen
    if len(storage[symbol]) > 100:
        storage[symbol] = storage[symbol][-100:]

# ============== DATEN ABRUFEN ==============

def get_forex_data_yfinance(yf_symbol: str, interval: str, period: str = "60d") -> Optional[pd.DataFrame]:
    """Holt Forex-Daten von Yahoo Finance"""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}"
        params = {'interval': interval, 'range': period}
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        data = response.json()
        
        if 'chart' not in data or 'result' not in data['chart'] or not data['chart']['result']:
            return None
        
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quotes = result['indicators']['quote'][0]
        
        df = pd.DataFrame({
            'datetime': pd.to_datetime(timestamps, unit='s'),
            'open': quotes['open'],
            'high': quotes['high'],
            'low': quotes['low'],
            'close': quotes['close'],
        })
        
        return df.dropna().reset_index(drop=True)
        
    except Exception as e:
        logger.error(f"Datenabruf Fehler: {e}")
        return None

def get_forex_data(symbol: str, timeframe: str, bars: int = 200) -> Optional[pd.DataFrame]:
    """Hauptfunktion für Datenabruf"""
    yf_symbol = SYMBOLS.get(symbol)
    if not yf_symbol:
        return None
    
    yf_map = {
        'H4': ('1h', '60d'),
        'H1': ('1h', '30d'),
        'M15': ('15m', '5d'),
        'M5': ('5m', '5d'),
        'D1': ('1d', '1y')
    }
    
    if timeframe not in yf_map:
        return None
    
    yf_interval, period = yf_map[timeframe]
    df = get_forex_data_yfinance(yf_symbol, yf_interval, period)
    
    if timeframe == 'H4' and df is not None and len(df) > 0:
        df = df.set_index('datetime')
        df = df.resample('4h').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
        }).dropna().reset_index()
    
    if df is not None and len(df) > bars:
        df = df.tail(bars).reset_index(drop=True)
    
    return df

# ============== PREMIUM/DISCOUNT ZONE (ICT KONFORM - DAILY RANGE) ==============

def calculate_premium_discount_daily(symbol: str) -> Tuple[float, float, float]:
    """
    Berechnet Premium/Discount Zonen basierend auf der DAILY Range (ICT konform!)
    Returns: (premium_level, equilibrium, discount_level)
    """
    df_daily = get_forex_data(symbol, 'D1', 20)
    
    if df_daily is None or len(df_daily) < 5:
        # Fallback auf H4 wenn keine Daily Daten
        df_h4 = get_forex_data(symbol, 'H4', 100)
        if df_h4 is None or len(df_h4) < 20:
            return 0, 0, 0
        range_high = df_h4['high'].max()
        range_low = df_h4['low'].min()
    else:
        # Nutze die letzten 5 Tage für die Range (ICT typisch)
        recent = df_daily.tail(5)
        range_high = recent['high'].max()
        range_low = recent['low'].min()
    
    equilibrium = (range_high + range_low) / 2
    
    return range_high, equilibrium, range_low

def get_price_zone(price: float, premium: float, equilibrium: float, discount: float) -> PriceZone:
    """Bestimmt ob der Preis im Premium, Discount oder Equilibrium ist"""
    if equilibrium == 0:
        return PriceZone.EQUILIBRIUM
    
    if price > equilibrium:
        return PriceZone.PREMIUM
    elif price < equilibrium:
        return PriceZone.DISCOUNT
    else:
        return PriceZone.EQUILIBRIUM

def is_valid_zone_for_direction(price_zone: PriceZone, direction: str) -> bool:
    """
    Prüft ob die Zone zur Trade-Richtung passt (ICT Regel):
    - LONG: Nur im DISCOUNT kaufen
    - SHORT: Nur im PREMIUM verkaufen
    """
    if direction == "LONG" and price_zone == PriceZone.DISCOUNT:
        return True
    if direction == "SHORT" and price_zone == PriceZone.PREMIUM:
        return True
    return False

# ============== SCHRITT 1: BIAS BESTIMMEN (H4) ==============

def calculate_ema(df: pd.DataFrame, period: int = 200) -> pd.Series:
    return df['close'].ewm(span=period, adjust=False).mean()

def detect_trend_structure(df: pd.DataFrame, lookback: int = 20) -> Tuple[bool, bool]:
    """Erkennt HH+HL (Bullish) oder LH+LL (Bearish)"""
    if len(df) < lookback:
        return False, False
    
    recent = df.tail(lookback)
    highs, lows = [], []
    
    for i in range(2, len(recent) - 2):
        if (recent.iloc[i]['high'] > recent.iloc[i-1]['high'] and 
            recent.iloc[i]['high'] > recent.iloc[i-2]['high'] and
            recent.iloc[i]['high'] > recent.iloc[i+1]['high'] and 
            recent.iloc[i]['high'] > recent.iloc[i+2]['high']):
            highs.append(recent.iloc[i]['high'])
        
        if (recent.iloc[i]['low'] < recent.iloc[i-1]['low'] and 
            recent.iloc[i]['low'] < recent.iloc[i-2]['low'] and
            recent.iloc[i]['low'] < recent.iloc[i+1]['low'] and 
            recent.iloc[i]['low'] < recent.iloc[i+2]['low']):
            lows.append(recent.iloc[i]['low'])
    
    if len(highs) < 2 or len(lows) < 2:
        return False, False
    
    is_bullish = highs[-1] > highs[-2] and lows[-1] > lows[-2]
    is_bearish = highs[-1] < highs[-2] and lows[-1] < lows[-2]
    
    return is_bullish, is_bearish

def determine_bias_h4(df_h4: pd.DataFrame) -> Tuple[Bias, str]:
    """Bestimmt den Bias auf H4"""
    if df_h4 is None or len(df_h4) < 50:
        return Bias.NEUTRAL, "Nicht genug Daten"
    
    reasons = []
    bullish_score, bearish_score = 0, 0
    current_price = df_h4.iloc[-1]['close']
    
    # EMA Check
    ema_period = 200 if len(df_h4) >= 200 else 50
    ema = calculate_ema(df_h4, ema_period)
    ema_value = ema.iloc[-1]
    
    if current_price > ema_value:
        bullish_score += 2
        reasons.append(f"Preis > EMA{ema_period}")
    else:
        bearish_score += 2
        reasons.append(f"Preis < EMA{ema_period}")
    
    # Structure Check
    is_bullish, is_bearish = detect_trend_structure(df_h4)
    if is_bullish:
        bullish_score += 1
        reasons.append("HH+HL")
    elif is_bearish:
        bearish_score += 1
        reasons.append("LH+LL")
    
    if bullish_score > bearish_score:
        return Bias.BULLISH, " | ".join(reasons)
    elif bearish_score > bullish_score:
        return Bias.BEARISH, " | ".join(reasons)
    return Bias.NEUTRAL, "Kein klarer Bias"

# ============== SCHRITT 2: POINT OF INTEREST (H1) ==============

def find_fvg_h1(df: pd.DataFrame, bias: Bias, symbol: str, premium: float, eq: float, discount: float) -> List[PointOfInterest]:
    """Findet Fair Value Gaps auf H1 mit Premium/Discount Filter UND Mitigation Tracking"""
    pois = []
    if len(df) < 10:
        return pois
    
    for i in range(3, min(15, len(df))):
        c1, c2, c3 = df.iloc[-i-2], df.iloc[-i-1], df.iloc[-i]
        
        # Bullish FVG
        if bias == Bias.BULLISH and c1['high'] < c3['low']:
            zone_top = round(c3['low'], 5)
            zone_bottom = round(c1['high'], 5)
            zone_mid = (zone_top + zone_bottom) / 2
            price_zone = get_price_zone(zone_mid, premium, eq, discount)
            
            # Premium/Discount + Unmitigated Check
            if (is_valid_zone_for_direction(price_zone, "LONG") and 
                is_zone_unmitigated(symbol, zone_top, zone_bottom, "FVG")):
                pois.append(PointOfInterest(
                    poi_type=SignalType.FVG,
                    direction="LONG",
                    zone_top=zone_top,
                    zone_bottom=zone_bottom,
                    price_zone=price_zone,
                    is_unmitigated=True,
                    timestamp=datetime.now()
                ))
        
        # Bearish FVG
        if bias == Bias.BEARISH and c1['low'] > c3['high']:
            zone_top = round(c1['low'], 5)
            zone_bottom = round(c3['high'], 5)
            zone_mid = (zone_top + zone_bottom) / 2
            price_zone = get_price_zone(zone_mid, premium, eq, discount)
            
            # Premium/Discount + Unmitigated Check
            if (is_valid_zone_for_direction(price_zone, "SHORT") and 
                is_zone_unmitigated(symbol, zone_top, zone_bottom, "FVG")):
                pois.append(PointOfInterest(
                    poi_type=SignalType.FVG,
                    direction="SHORT",
                    zone_top=zone_top,
                    zone_bottom=zone_bottom,
                    price_zone=price_zone,
                    is_unmitigated=True,
                    timestamp=datetime.now()
                ))
    
    return pois

def find_order_block_h1(df: pd.DataFrame, bias: Bias, symbol: str, premium: float, eq: float, discount: float) -> List[PointOfInterest]:
    """Findet Order Blocks auf H1 mit Unmitigated Filter"""
    pois = []
    if len(df) < 15:
        return pois
    
    for i in range(3, min(20, len(df))):
        candle = df.iloc[-i]
        next_candle = df.iloc[-i+1]
        
        is_bearish = candle['close'] < candle['open']
        is_bullish = candle['close'] > candle['open']
        candle_size = abs(candle['close'] - candle['open'])
        
        if candle_size < 0.0001:
            continue
        
        # Bullish OB
        if bias == Bias.BULLISH and is_bearish:
            move = next_candle['close'] - candle['close']
            if move > candle_size * 1.5:
                zone_top = round(candle['high'], 5)
                zone_bottom = round(candle['low'], 5)
                zone_mid = (zone_top + zone_bottom) / 2
                price_zone = get_price_zone(zone_mid, premium, eq, discount)
                
                # Premium/Discount + Unmitigated Check
                if (is_valid_zone_for_direction(price_zone, "LONG") and 
                    is_zone_unmitigated(symbol, zone_top, zone_bottom, "OB")):
                    pois.append(PointOfInterest(
                        poi_type=SignalType.ORDER_BLOCK,
                        direction="LONG",
                        zone_top=zone_top,
                        zone_bottom=zone_bottom,
                        price_zone=price_zone,
                        is_unmitigated=True,
                        timestamp=datetime.now()
                    ))
        
        # Bearish OB
        if bias == Bias.BEARISH and is_bullish:
            move = candle['close'] - next_candle['close']
            if move > candle_size * 1.5:
                zone_top = round(candle['high'], 5)
                zone_bottom = round(candle['low'], 5)
                zone_mid = (zone_top + zone_bottom) / 2
                price_zone = get_price_zone(zone_mid, premium, eq, discount)
                
                if (is_valid_zone_for_direction(price_zone, "SHORT") and 
                    is_zone_unmitigated(symbol, zone_top, zone_bottom, "OB")):
                    pois.append(PointOfInterest(
                        poi_type=SignalType.ORDER_BLOCK,
                        direction="SHORT",
                        zone_top=zone_top,
                        zone_bottom=zone_bottom,
                        price_zone=price_zone,
                        is_unmitigated=True,
                        timestamp=datetime.now()
                    ))
    
    return pois

def find_liquidity_sweep_h1(df: pd.DataFrame, bias: Bias, symbol: str, premium: float, eq: float, discount: float) -> List[PointOfInterest]:
    """Findet Liquidity Sweeps auf H1"""
    pois = []
    if len(df) < 25:
        return pois
    
    lookback = df.iloc[-25:-5]
    important_high = lookback['high'].max()
    important_low = lookback['low'].min()
    
    for i in range(1, 5):
        candle = df.iloc[-i]
        
        # Bullish Sweep
        if bias == Bias.BULLISH:
            if candle['low'] < important_low and candle['close'] > important_low:
                zone_top = round(important_low + 0.0015, 5)
                zone_bottom = round(candle['low'], 5)
                zone_mid = (zone_top + zone_bottom) / 2
                price_zone = get_price_zone(zone_mid, premium, eq, discount)
                
                if is_valid_zone_for_direction(price_zone, "LONG"):
                    pois.append(PointOfInterest(
                        poi_type=SignalType.LIQUIDITY_SWEEP,
                        direction="LONG",
                        zone_top=zone_top,
                        zone_bottom=zone_bottom,
                        price_zone=price_zone,
                        is_unmitigated=True,
                        timestamp=datetime.now()
                    ))
        
        # Bearish Sweep
        if bias == Bias.BEARISH:
            if candle['high'] > important_high and candle['close'] < important_high:
                zone_top = round(candle['high'], 5)
                zone_bottom = round(important_high - 0.0015, 5)
                zone_mid = (zone_top + zone_bottom) / 2
                price_zone = get_price_zone(zone_mid, premium, eq, discount)
                
                if is_valid_zone_for_direction(price_zone, "SHORT"):
                    pois.append(PointOfInterest(
                        poi_type=SignalType.LIQUIDITY_SWEEP,
                        direction="SHORT",
                        zone_top=zone_top,
                        zone_bottom=zone_bottom,
                        price_zone=price_zone,
                        is_unmitigated=True,
                        timestamp=datetime.now()
                    ))
    
    return pois

def find_points_of_interest_h1(df_h1: pd.DataFrame, bias: Bias, symbol: str) -> List[PointOfInterest]:
    """Findet alle POIs auf H1 mit allen Filtern"""
    if df_h1 is None or len(df_h1) < 25:
        return []
    
    # Premium/Discount basierend auf DAILY Range (ICT konform!)
    premium, eq, discount = calculate_premium_discount_daily(symbol)
    
    if premium == 0:
        logger.warning(f"      ⚠️ Keine Daily Daten für Premium/Discount")
        return []
    
    all_pois = []
    all_pois.extend(find_fvg_h1(df_h1, bias, symbol, premium, eq, discount))
    all_pois.extend(find_order_block_h1(df_h1, bias, symbol, premium, eq, discount))
    all_pois.extend(find_liquidity_sweep_h1(df_h1, bias, symbol, premium, eq, discount))
    
    return all_pois

# ============== TIMEFRAME KONFLIKT CHECK (NEU in v5.0) ==============

def check_m15_conflict(df_m15: pd.DataFrame, poi_direction: str) -> Tuple[bool, str]:
    """
    Prüft ob im M15 eine entgegengesetzte FVG existiert.
    Wenn ja, ist das ein Konflikt und wir sollten NICHT traden.
    
    Returns: (has_conflict, reason)
    """
    if df_m15 is None or len(df_m15) < 6:
        return False, "OK"
    
    # Suche nach FVGs in den letzten M15 Kerzen
    # Wir brauchen mindestens 3 Kerzen für eine FVG (c1, c2, c3)
    # Sichere Berechnung um Index-Fehler zu vermeiden
    max_check = min(5, len(df_m15) - 4)  # Maximal 5 FVG-Checks
    
    for offset in range(max_check):
        idx = len(df_m15) - 3 - offset  # Startindex für c3
        if idx < 2:  # Sicherstellen dass c1 (idx-2) nicht negativ wird
            break
            
        c1 = df_m15.iloc[idx - 2]  # Älteste Kerze
        c2 = df_m15.iloc[idx - 1]  # Mittlere Kerze  
        c3 = df_m15.iloc[idx]      # Neueste Kerze der 3er-Gruppe
        
        # Wenn wir LONG gehen wollen, prüfe auf Bearish FVG
        if poi_direction == "LONG":
            if c1['low'] > c3['high']:  # Bearish FVG
                return True, "Bearish FVG im M15 - Konflikt!"
        
        # Wenn wir SHORT gehen wollen, prüfe auf Bullish FVG
        if poi_direction == "SHORT":
            if c1['high'] < c3['low']:  # Bullish FVG
                return True, "Bullish FVG im M15 - Konflikt!"
    
    return False, "OK"

# ============== SCHRITT 3: ZONE ENTRY (M15) ==============

def check_zone_entry_m15(df_m15: pd.DataFrame, poi: PointOfInterest, symbol: str) -> Optional[ZoneEntry]:
    """Prüft ob M15 in die Zone eingetreten ist UND ob es keinen Konflikt gibt"""
    if df_m15 is None or len(df_m15) < 5:
        return None
    
    # ZUERST: Konflikt-Check
    has_conflict, conflict_reason = check_m15_conflict(df_m15, poi.direction)
    if has_conflict:
        logger.info(f"      ⚠️ {conflict_reason}")
        return None
    
    for i in range(1, min(6, len(df_m15))):
        candle = df_m15.iloc[-i]
        
        is_in_zone = (candle['low'] <= poi.zone_top and candle['high'] >= poi.zone_bottom)
        close_in_zone = (poi.zone_bottom <= candle['close'] <= poi.zone_top)
        
        if is_in_zone or close_in_zone:
            # Markiere Zone als mitigated
            zone_type = "OB" if poi.poi_type == SignalType.ORDER_BLOCK else "FVG"
            mark_zone_as_mitigated(symbol, poi.zone_top, poi.zone_bottom, zone_type)
            
            return ZoneEntry(
                entry_price=candle['close'],
                zone_top=poi.zone_top,
                zone_bottom=poi.zone_bottom,
                timestamp=datetime.now()
            )
    
    return None

# ============== SCHRITT 4: ENTRY TRIGGER (M5) ==============

def find_mss_m5(df: pd.DataFrame, direction: str, pip_value: float) -> Optional[EntryTrigger]:
    """Findet Market Structure Shift auf M5"""
    if len(df) < 15:
        return None
    
    recent = df.tail(15)
    current = recent.iloc[-1]
    
    swing_highs, swing_lows = [], []
    
    for i in range(2, len(recent) - 2):
        if (recent.iloc[i]['high'] > recent.iloc[i-1]['high'] and 
            recent.iloc[i]['high'] > recent.iloc[i+1]['high']):
            swing_highs.append(recent.iloc[i]['high'])
        
        if (recent.iloc[i]['low'] < recent.iloc[i-1]['low'] and 
            recent.iloc[i]['low'] < recent.iloc[i+1]['low']):
            swing_lows.append(recent.iloc[i]['low'])
    
    # Bullish MSS
    if direction == "LONG" and swing_highs:
        last_sh = swing_highs[-1]
        if current['close'] > last_sh:
            entry = current['close']
            sl = min(swing_lows) if swing_lows else current['low'] - (10 * pip_value)
            risk = entry - sl
            
            if risk > 0:
                return EntryTrigger(
                    trigger_type=EntryType.MSS,
                    direction="LONG",
                    entry_price=round(entry, 5),
                    stop_loss=round(sl - (5 * pip_value), 5),
                    take_profit_1=round(entry + risk, 5),
                    take_profit_2=round(entry + risk * 1.5, 5),
                    timestamp=datetime.now()
                )
    
    # Bearish MSS
    if direction == "SHORT" and swing_lows:
        last_sl = swing_lows[-1]
        if current['close'] < last_sl:
            entry = current['close']
            sl = max(swing_highs) if swing_highs else current['high'] + (10 * pip_value)
            risk = sl - entry
            
            if risk > 0:
                return EntryTrigger(
                    trigger_type=EntryType.MSS,
                    direction="SHORT",
                    entry_price=round(entry, 5),
                    stop_loss=round(sl + (5 * pip_value), 5),
                    take_profit_1=round(entry - risk, 5),
                    take_profit_2=round(entry - risk * 1.5, 5),
                    timestamp=datetime.now()
                )
    
    return None

def find_engulfing_m5(df: pd.DataFrame, direction: str, pip_value: float) -> Optional[EntryTrigger]:
    """Findet Engulfing Candle auf M5"""
    if len(df) < 5:
        return None
    
    current, prev = df.iloc[-1], df.iloc[-2]
    
    # Bullish Engulfing
    if direction == "LONG":
        is_prev_bearish = prev['close'] < prev['open']
        is_current_bullish = current['close'] > current['open']
        is_engulfing = current['open'] <= prev['close'] and current['close'] >= prev['open']
        
        if is_prev_bearish and is_current_bullish and is_engulfing:
            entry = current['close']
            sl = min(current['low'], prev['low']) - (5 * pip_value)
            risk = entry - sl
            
            if risk > 0:
                return EntryTrigger(
                    trigger_type=EntryType.ENGULFING,
                    direction="LONG",
                    entry_price=round(entry, 5),
                    stop_loss=round(sl, 5),
                    take_profit_1=round(entry + risk, 5),
                    take_profit_2=round(entry + risk * 1.5, 5),
                    timestamp=datetime.now()
                )
    
    # Bearish Engulfing
    if direction == "SHORT":
        is_prev_bullish = prev['close'] > prev['open']
        is_current_bearish = current['close'] < current['open']
        is_engulfing = current['open'] >= prev['close'] and current['close'] <= prev['open']
        
        if is_prev_bullish and is_current_bearish and is_engulfing:
            entry = current['close']
            sl = max(current['high'], prev['high']) + (5 * pip_value)
            risk = sl - entry
            
            if risk > 0:
                return EntryTrigger(
                    trigger_type=EntryType.ENGULFING,
                    direction="SHORT",
                    entry_price=round(entry, 5),
                    stop_loss=round(sl, 5),
                    take_profit_1=round(entry - risk, 5),
                    take_profit_2=round(entry - risk * 1.5, 5),
                    timestamp=datetime.now()
                )
    
    return None

def find_entry_trigger_m5(df_m5: pd.DataFrame, direction: str, symbol: str) -> Optional[EntryTrigger]:
    """Sucht nach Entry-Trigger auf M5"""
    if df_m5 is None or len(df_m5) < 15:
        return None
    
    pip_value = PIP_VALUES.get(symbol, 0.0001)
    
    mss = find_mss_m5(df_m5, direction, pip_value)
    if mss:
        return mss
    
    engulfing = find_engulfing_m5(df_m5, direction, pip_value)
    if engulfing:
        return engulfing
    
    return None

# ============== KILL ZONE & SESSION LOGIK ==============

def get_current_killzone() -> Tuple[bool, str, int, Dict]:
    """Prüft Kill Zone mit Session-Details"""
    now = datetime.utcnow() + timedelta(hours=1)  # MEZ
    current_time = now.hour * 60 + now.minute
    
    if now.weekday() >= 5:
        return False, "weekend", 0, {}
    
    for zone_name, config in KILL_ZONES.items():
        start = config['start_hour'] * 60 + config['start_min']
        end = config['end_hour'] * 60 + config['end_min']
        
        if start <= current_time < end:
            return True, zone_name, config['priority'], config
    
    return False, "none", 0, {}

def check_session_alignment(symbol: str, kz_config: Dict) -> Tuple[bool, str]:
    """Prüft ob das Paar zur aktuellen Session passt"""
    if not kz_config:
        return False, "Keine Session"
    
    best_pairs = kz_config.get('best_pairs', [])
    
    if symbol in best_pairs:
        return True, f"Optimal fuer {kz_config.get('typical_behavior', 'trading')}"
    else:
        return True, "Akzeptabel"

# ============== TELEGRAM ==============

def send_trade_alert(setup: TradeSetup):
    """Sendet Trade-Alert an Telegram"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN':
        logger.warning("Telegram nicht konfiguriert!")
        return False
    
    dir_emoji = "LONG" if setup.entry_trigger.direction == "LONG" else "SHORT"
    
    kz_names = {
        'london': 'London (08-11)',
        'ny_open': 'New York (14:30-17)',
        'london_close': 'London Close (17-19)'
    }
    
    stars = "*" * setup.confluence_score
    
    risk = abs(setup.entry_trigger.entry_price - setup.entry_trigger.stop_loss)
    reward = abs(setup.entry_trigger.take_profit_2 - setup.entry_trigger.entry_price)
    crv = round(reward / risk, 1) if risk > 0 else 0
    
    message = f"""ICT B-SETUP ALERT v5.0

{dir_emoji} - {setup.symbol}
Confluence: {setup.confluence_score}/5 {stars}

------------------------
SCHRITT 1 - H4 BIAS:
{setup.bias.value}
{setup.bias_reason}

Kill Zone: {kz_names.get(setup.kill_zone, setup.kill_zone)}
Session: {setup.session_alignment}

------------------------
SCHRITT 2 - H1 POI:
{setup.point_of_interest.poi_type.value}
Zone: {setup.point_of_interest.zone_bottom} - {setup.point_of_interest.zone_top}
{setup.point_of_interest.price_zone.value} Zone (Daily Range)
Status: Unmitigated

------------------------
SCHRITT 3 - M15 ZONE ENTRY:
Preis in Zone bei: {setup.zone_entry.entry_price}
Kein Timeframe-Konflikt

------------------------
SCHRITT 4 - M5 TRIGGER:
{setup.entry_trigger.trigger_type.value}

------------------------
TRADE DETAILS:
Entry: {setup.entry_trigger.entry_price}
Stop-Loss: {setup.entry_trigger.stop_loss}
TP1 (1:1): {setup.entry_trigger.take_profit_1}
TP2 (1:{crv}): {setup.entry_trigger.take_profit_2}

Zeit: {datetime.now().strftime('%H:%M:%S')} MEZ

ALLE 4 BEDINGUNGEN ERFUELLT!
Pruefe den Chart vor dem Entry!
    """
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(url, json={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"ALERT GESENDET: {setup.symbol} {setup.entry_trigger.direction}")
            return True
        else:
            logger.error(f"Telegram Fehler: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Senden fehlgeschlagen: {e}")
        return False

def send_status(msg: str):
    """Sendet Status-Nachricht"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN':
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': TELEGRAM_CHAT_ID, 'text': msg}, timeout=10)
    except:
        pass

# ============== HAUPTANALYSE ==============

def analyze_symbol(symbol: str, kz_name: str, kz_priority: int, kz_config: Dict) -> Optional[TradeSetup]:
    """Analysiert ein einzelnes Symbol"""
    logger.info(f"   Analysiere {symbol}...")
    
    # Session Alignment
    session_ok, session_info = check_session_alignment(symbol, kz_config)
    
    # SCHRITT 1: H4 BIAS
    df_h4 = get_forex_data(symbol, 'H4', 200)
    bias, bias_reason = determine_bias_h4(df_h4)
    
    if bias == Bias.NEUTRAL:
        logger.info(f"      Kein klarer Bias")
        return None
    
    logger.info(f"      Bias: {bias.value}")
    
    # SCHRITT 2: H1 POI (mit Daily Range Premium/Discount)
    df_h1 = get_forex_data(symbol, 'H1', 50)
    pois = find_points_of_interest_h1(df_h1, bias, symbol)
    
    if not pois:
        logger.info(f"      Kein POI in korrekter Zone")
        return None
    
    logger.info(f"      {len(pois)} POI(s) gefunden")
    
    # SCHRITT 3 & 4: M15 Zone Entry (mit Konflikt-Check) + M5 Trigger
    df_m15 = get_forex_data(symbol, 'M15', 30)
    df_m5 = get_forex_data(symbol, 'M5', 30)
    
    for poi in pois:
        zone_entry = check_zone_entry_m15(df_m15, poi, symbol)
        
        if zone_entry:
            trigger = find_entry_trigger_m5(df_m5, poi.direction, symbol)
            
            if trigger:
                # Confluence Score
                confluence = 3
                confluence += 1 if trigger.trigger_type == EntryType.MSS else 0
                confluence += 1 if kz_priority >= 4 else 0
                
                return TradeSetup(
                    symbol=symbol,
                    bias=bias,
                    bias_reason=bias_reason,
                    kill_zone=kz_name,
                    session_alignment=session_info,
                    point_of_interest=poi,
                    zone_entry=zone_entry,
                    entry_trigger=trigger,
                    confluence_score=min(confluence, 5)
                )
    
    logger.info(f"      Kein vollstaendiges Setup")
    return None

def analyze_all_markets() -> List[TradeSetup]:
    """Analysiert alle Märkte"""
    logger.info("=" * 50)
    logger.info("STARTE MULTI-PAIR TOP-DOWN-ANALYSE v5.0")
    
    # Cleanup alte Mitigations
    cleanup_old_mitigations()
    
    # Kill Zone Check
    in_kz, kz_name, kz_priority, kz_config = get_current_killzone()
    
    if not in_kz:
        logger.info(f"Ausserhalb Kill Zone ({kz_name})")
        return []
    
    logger.info(f"Kill Zone: {kz_name} (Prioritaet: {kz_priority})")
    
    setups = []
    
    for symbol in SYMBOLS.keys():
        try:
            setup = analyze_symbol(symbol, kz_name, kz_priority, kz_config)
            if setup:
                setups.append(setup)
        except Exception as e:
            logger.error(f"Fehler bei {symbol}: {e}")
    
    return setups

# ============== MAIN ==============

def main():
    logger.info("=" * 60)
    logger.info("ICT ALERT BOT v5.0 FINAL - MULTI-PAIR")
    logger.info("=" * 60)
    logger.info(f"Symbole: {', '.join(SYMBOLS.keys())}")
    logger.info("")
    logger.info("ANALYSE-STRUKTUR:")
    logger.info("   H4  -> Bias (EMA + Struktur)")
    logger.info("   H1  -> POI (FVG/OB/Sweep) + Premium/Discount (DAILY)")
    logger.info("   M15 -> Zone Entry + Konflikt-Check")
    logger.info("   M5  -> Entry Trigger (MSS/Engulfing)")
    logger.info("")
    logger.info("OPTIMIERUNGEN v5.0:")
    logger.info("   Premium/Discount basierend auf DAILY Range (ICT konform)")
    logger.info("   Session-spezifische Logik")
    logger.info("   Unmitigated OB Filter")
    logger.info("   FVG Mitigation Tracking (NEU)")
    logger.info("   Timeframe Konflikt-Check (NEU)")
    logger.info("   Multi-Pair Support")
    logger.info("=" * 60)
    
    send_status(
        "ICT Alert Bot v5.0 FINAL gestartet!\n\n"
        "4 Waehrungspaare:\n"
        "EUR/USD, GBP/USD, USD/JPY, AUD/USD\n\n"
        "4-Timeframe Top-Down:\n"
        "H4 > H1 > M15 > M5\n\n"
        "NEU in v5.0:\n"
        "- Premium/Discount auf DAILY Range\n"
        "- FVG Mitigation Tracking\n"
        "- Timeframe Konflikt-Check\n\n"
        "Alert nur bei ALLEN Bedingungen!"
    )
    
    while True:
        try:
            setups = analyze_all_markets()
            
            for setup in setups:
                send_trade_alert(setup)
            
            logger.info(f"Warte {CHECK_INTERVAL_SECONDS}s...")
            time.sleep(CHECK_INTERVAL_SECONDS)
            
        except KeyboardInterrupt:
            logger.info("Bot gestoppt.")
            break
        except Exception as e:
            logger.error(f"Fehler: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
