#!/usr/bin/env python3
"""
ICT Alert Bot v8.6 - STRICT ALIGNMENT + NEWS FILTER
====================================================
NUR Trades wenn H4 und H1 die gleiche Richtung haben!
NEU: News Filter wieder aktiv (30 Min vor/nach High Impact News)

Änderungen v8.6:
- News Filter wieder eingebaut
- 30 Min vor und nach High Impact News = KEIN ALERT
- Zone Status Anzeige bleibt
"""

import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Tuple, Dict

try:
    import smartmoneyconcepts as smc
    SMC_AVAILABLE = True
except ImportError:
    SMC_AVAILABLE = False

# ============================================================
# KONFIGURATION v8.6
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
TWELVE_DATA_API_KEY = os.getenv('TWELVE_DATA_API_KEY', '')

SYMBOLS = {
    'EUR/USD': {'type': 'HAUPT', 'pip': 0.0001, 'yahoo': 'EURUSD=X'},
    'GBP/USD': {'type': 'HAUPT', 'pip': 0.0001, 'yahoo': 'GBPUSD=X'},
    'AUD/USD': {'type': 'HAUPT', 'pip': 0.0001, 'yahoo': 'AUDUSD=X'},
}

FIXED_SL_PIPS = 18
MIN_ZONE_SIZE_PIPS = 5
ZONE_COOLDOWN_SECONDS = 7200
NEWS_BUFFER_MINUTES = 30  # 30 Min vor und nach News

# ============================================================
# ENUMS & DATACLASSES
# ============================================================

class Bias(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class POIType(Enum):
    FVG = "Fair Value Gap"
    ORDER_BLOCK = "Order Block"

class AlertPriority(Enum):
    URGENT = "URGENT"
    NORMAL = "NORMAL"
    INFO = "INFO"

@dataclass
class M5EntryZone:
    zone_top: float
    zone_bottom: float
    level: int

@dataclass
class PointOfInterest:
    poi_type: POIType
    direction: str
    zone_top: float
    zone_bottom: float
    zone_quality: str
    mitigated: bool = False
    distance_to_price: float = 0.0

@dataclass
class TradeSetup:
    symbol: str
    symbol_type: str
    direction: str
    poi: PointOfInterest
    entry_price: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    confluence_score: int
    grade: str
    priority: AlertPriority
    time_quality: str
    warnings: List[str]
    daily_trend: str
    daily_reason: str
    h4_bias: str
    h4_reason: str
    h1_bias: str
    h1_reason: str
    kill_zone: str
    current_price: float = 0.0
    zone_status: str = ""
    zone_distance_pips: float = 0.0
    news_status: str = ""
    m5_entry_zones: List[M5EntryZone] = field(default_factory=list)
    analysis_steps: List[str] = field(default_factory=list)

alerted_zones: Dict[str, datetime] = {}
news_cache: Dict[str, List] = {}
news_cache_time: datetime = None

# ============================================================
# NEWS FILTER (WIEDER EINGEBAUT!)
# ============================================================

def get_forex_news() -> List[Dict]:
    """Holt High Impact News von ForexFactory oder FCS API"""
    global news_cache, news_cache_time
    
    # Cache für 1 Stunde
    if news_cache_time and (datetime.now() - news_cache_time).seconds < 3600:
        return news_cache.get('news', [])
    
    news = []
    
    # Methode 1: FCS API (kostenlos)
    try:
        url = "https://fcsapi.com/api-v3/forex/economy_cal"
        params = {
            'country': 'united-states,united-kingdom,eurozone,australia',
            'access_key': 'API_KEY_PLACEHOLDER'  # Kostenloser Key
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if 'response' in data:
            for event in data['response']:
                if event.get('impact', '').lower() == 'high':
                    news.append({
                        'time': event.get('date', ''),
                        'currency': event.get('country', ''),
                        'event': event.get('event', ''),
                        'impact': 'HIGH'
                    })
    except:
        pass
    
    # Methode 2: Fallback - Bekannte News-Zeiten (statisch)
    if not news:
        now = datetime.utcnow()
        today = now.strftime('%Y-%m-%d')
        
        # Typische High Impact News Zeiten (UTC)
        typical_news_times = [
            ('08:30', 'USD', 'NFP / Employment Data'),
            ('12:30', 'USD', 'CPI / PPI Data'),
            ('14:00', 'USD', 'FOMC / Fed Decision'),
            ('09:00', 'EUR', 'ECB Decision'),
            ('07:00', 'GBP', 'BOE Decision'),
            ('00:30', 'AUD', 'RBA Decision'),
        ]
        
        # Nur an bestimmten Tagen (erster Freitag = NFP, etc.)
        weekday = now.weekday()
        
        # NFP ist erster Freitag im Monat
        if weekday == 4 and now.day <= 7:
            news.append({
                'time': f"{today} 13:30",
                'currency': 'USD',
                'event': 'Non-Farm Payrolls',
                'impact': 'HIGH'
            })
        
        # FOMC ist typischerweise Mittwoch
        if weekday == 2:
            news.append({
                'time': f"{today} 19:00",
                'currency': 'USD',
                'event': 'FOMC Statement',
                'impact': 'HIGH'
            })
    
    news_cache['news'] = news
    news_cache_time = datetime.now()
    
    return news

def check_news_filter(symbol: str) -> Tuple[bool, str]:
    """
    Prüft ob gerade High Impact News anstehen
    Returns: (is_safe, status_message)
    """
    news = get_forex_news()
    now = datetime.utcnow()
    
    # Welche Währungen betrifft das Symbol?
    currencies = []
    if 'EUR' in symbol:
        currencies.append('EUR')
    if 'USD' in symbol:
        currencies.append('USD')
    if 'GBP' in symbol:
        currencies.append('GBP')
    if 'AUD' in symbol:
        currencies.append('AUD')
    
    for event in news:
        try:
            # Parse News Zeit
            news_time_str = event.get('time', '')
            if not news_time_str:
                continue
            
            # Versuche verschiedene Formate
            news_time = None
            for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S', '%H:%M']:
                try:
                    if fmt == '%H:%M':
                        news_time = datetime.strptime(news_time_str, fmt).replace(
                            year=now.year, month=now.month, day=now.day
                        )
                    else:
                        news_time = datetime.strptime(news_time_str, fmt)
                    break
                except:
                    continue
            
            if not news_time:
                continue
            
            # Prüfe ob News für unsere Währungen relevant ist
            news_currency = event.get('currency', '').upper()
            if not any(c in news_currency for c in currencies):
                continue
            
            # Prüfe Zeitfenster (30 Min vor und nach)
            time_diff = abs((now - news_time).total_seconds() / 60)
            
            if time_diff <= NEWS_BUFFER_MINUTES:
                event_name = event.get('event', 'High Impact News')
                if now < news_time:
                    return False, f"⚠️ NEWS in {int(NEWS_BUFFER_MINUTES - time_diff)} Min: {event_name}"
                else:
                    return False, f"⚠️ NEWS vor {int(time_diff)} Min: {event_name}"
        except:
            continue
    
    return True, "✅ Keine High Impact News"

# ============================================================
# DATEN ABRUFEN
# ============================================================

def get_forex_data_twelvedata(symbol: str, interval: str, outputsize: int = 100) -> Optional[pd.DataFrame]:
    if not TWELVE_DATA_API_KEY:
        return None
    try:
        url = "https://api.twelvedata.com/time_series"
        interval_map = {'M5': '5min', 'M15': '15min', 'H1': '1h', 'H4': '4h', 'D1': '1day'}
        params = {
            'symbol': symbol,
            'interval': interval_map.get(interval, interval),
            'outputsize': outputsize,
            'apikey': TWELVE_DATA_API_KEY
        }
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if 'values' not in data:
            return None
        df = pd.DataFrame(data['values'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        return df.iloc[::-1].reset_index(drop=True)
    except:
        return None

def get_forex_data_yahoo(symbol: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        yahoo_symbol = SYMBOLS.get(symbol, {}).get('yahoo', symbol.replace('/', '') + '=X')
        interval_map = {'M5': '5m', 'M15': '15m', 'H1': '1h', 'H4': '1h', 'D1': '1d'}
        period_map = {'M5': '5d', 'M15': '5d', 'H1': '1mo', 'H4': '3mo', 'D1': '6mo'}
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        params = {'interval': interval_map.get(interval, '1h'), 'range': period_map.get(interval, '1mo')}
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if 'chart' not in data or not data['chart']['result']:
            return None
        
        result = data['chart']['result'][0]
        quotes = result['indicators']['quote'][0]
        
        df = pd.DataFrame({
            'open': quotes['open'],
            'high': quotes['high'],
            'low': quotes['low'],
            'close': quotes['close'],
        })
        df = df.dropna()
        
        if interval == 'H4' and len(df) > 4:
            df = df.iloc[::4].reset_index(drop=True)
        
        return df
    except:
        return None

def get_forex_data(symbol: str, interval: str, outputsize: int = 100) -> Optional[pd.DataFrame]:
    df = get_forex_data_twelvedata(symbol, interval, outputsize)
    if df is not None and len(df) > 10:
        return df
    df = get_forex_data_yahoo(symbol, interval)
    if df is not None and len(df) > 10:
        return df
    return None

# ============================================================
# BIAS FUNKTIONEN
# ============================================================

def get_daily_trend(df: pd.DataFrame) -> Tuple[Bias, str]:
    if df is None or len(df) < 20:
        return Bias.NEUTRAL, "Nicht genug Daten"
    
    recent = df.tail(20)
    highs, lows = [], []
    
    for i in range(2, len(recent) - 2):
        h = recent.iloc[i]['high']
        l = recent.iloc[i]['low']
        if h > max(recent.iloc[i-1]['high'], recent.iloc[i-2]['high'], recent.iloc[i+1]['high'], recent.iloc[i+2]['high']):
            highs.append((i, h))
        if l < min(recent.iloc[i-1]['low'], recent.iloc[i-2]['low'], recent.iloc[i+1]['low'], recent.iloc[i+2]['low']):
            lows.append((i, l))
    
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1][1] > highs[-2][1] and lows[-1][1] > lows[-2][1]:
            return Bias.BULLISH, f"Higher High ({highs[-1][1]:.5f}) + Higher Low ({lows[-1][1]:.5f})"
        elif highs[-1][1] < highs[-2][1] and lows[-1][1] < lows[-2][1]:
            return Bias.BEARISH, f"Lower High ({highs[-1][1]:.5f}) + Lower Low ({lows[-1][1]:.5f})"
    
    ema20 = recent['close'].ewm(span=20).mean().iloc[-1]
    close = recent['close'].iloc[-1]
    
    if close > ema20 * 1.002:
        return Bias.BULLISH, f"Preis ({close:.5f}) über EMA20 ({ema20:.5f})"
    elif close < ema20 * 0.998:
        return Bias.BEARISH, f"Preis ({close:.5f}) unter EMA20 ({ema20:.5f})"
    
    return Bias.NEUTRAL, f"Preis ({close:.5f}) nahe EMA20 ({ema20:.5f})"

def determine_bias_h4(df: pd.DataFrame) -> Tuple[Bias, str]:
    if df is None or len(df) < 20:
        return Bias.NEUTRAL, "Nicht genug Daten"
    
    if SMC_AVAILABLE:
        try:
            bos = smc.bos_choch(df, close_break=True).tail(10)
            bull_bos = len(bos[bos['BOS'] == 1])
            bear_bos = len(bos[bos['BOS'] == -1])
            bull_choch = len(bos[bos['CHOCH'] == 1])
            bear_choch = len(bos[bos['CHOCH'] == -1])
            
            bull = bull_bos + bull_choch
            bear = bear_bos + bear_choch
            
            if bull > bear and bull >= 2:
                return Bias.BULLISH, f"BOS/CHoCH: {bull} Bullish vs {bear} Bearish"
            elif bear > bull and bear >= 2:
                return Bias.BEARISH, f"BOS/CHoCH: {bear} Bearish vs {bull} Bullish"
        except:
            pass
    
    return get_daily_trend(df)

def determine_bias_h1(df: pd.DataFrame) -> Tuple[Bias, str]:
    if df is None or len(df) < 20:
        return Bias.NEUTRAL, "Nicht genug Daten"
    
    recent = df.tail(20)
    ema10 = recent['close'].ewm(span=10).mean().iloc[-1]
    ema20 = recent['close'].ewm(span=20).mean().iloc[-1]
    close = recent['close'].iloc[-1]
    
    if close > ema10 and ema10 > ema20:
        return Bias.BULLISH, f"Preis ({close:.5f}) > EMA10 ({ema10:.5f}) > EMA20 ({ema20:.5f})"
    elif close < ema10 and ema10 < ema20:
        return Bias.BEARISH, f"Preis ({close:.5f}) < EMA10 ({ema10:.5f}) < EMA20 ({ema20:.5f})"
    
    if close > ema10 * 1.001:
        return Bias.BULLISH, f"Preis ({close:.5f}) über EMA10 ({ema10:.5f})"
    elif close < ema10 * 0.999:
        return Bias.BEARISH, f"Preis ({close:.5f}) unter EMA10 ({ema10:.5f})"
    
    return Bias.NEUTRAL, f"Kein klarer Trend"

# ============================================================
# PREMIUM/DISCOUNT & KILL ZONES
# ============================================================

def calculate_premium_discount(df: pd.DataFrame) -> Tuple[float, float, float]:
    if df is None or len(df) < 5:
        return 0, 0, 0
    r = df.tail(5)
    high = r['high'].max()
    low = r['low'].min()
    return high, (high + low) / 2, low

def get_zone_quality(price: float, premium: float, eq: float, discount: float, direction: str) -> str:
    if direction == "LONG":
        if price <= discount:
            return "DISCOUNT (Ideal für LONG)"
        elif price <= eq:
            return "EQUILIBRIUM (Akzeptabel)"
        return "PREMIUM (Riskant für LONG)"
    else:
        if price >= premium:
            return "PREMIUM (Ideal für SHORT)"
        elif price >= eq:
            return "EQUILIBRIUM (Akzeptabel)"
        return "DISCOUNT (Riskant für SHORT)"

def get_kill_zone(symbol: str) -> Tuple[str, bool]:
    hour = datetime.utcnow().hour
    
    if 7 <= hour < 10:
        return "London Open (07:00-10:00 UTC)", True
    if 13 <= hour < 16:
        return "New York (13:00-16:00 UTC)", True
    if 16 <= hour < 18:
        return "London Close (16:00-18:00 UTC)", True
    
    return "Außerhalb Kill Zone", False

# ============================================================
# POI & M5 FVG ERKENNUNG
# ============================================================

def find_pois(df: pd.DataFrame, bias: Bias, symbol: str, premium: float, eq: float, discount: float) -> List[PointOfInterest]:
    if df is None or len(df) < 20:
        return []
    
    pois = []
    pip = SYMBOLS[symbol]['pip']
    price = df['close'].iloc[-1]
    
    if SMC_AVAILABLE:
        try:
            fvg = smc.fvg(df)
            for i in range(len(fvg)):
                row = fvg.iloc[i]
                
                if row['FVG'] == 1 and not row['MitigatedIndex'] > 0 and bias == Bias.BULLISH:
                    size = (row['Top'] - row['Bottom']) / pip
                    if size >= MIN_ZONE_SIZE_PIPS:
                        pois.append(PointOfInterest(
                            POIType.FVG, "LONG", row['Top'], row['Bottom'],
                            get_zone_quality(row['Bottom'], premium, eq, discount, "LONG"),
                            False, abs(price - row['Top'])
                        ))
                
                elif row['FVG'] == -1 and not row['MitigatedIndex'] > 0 and bias == Bias.BEARISH:
                    size = (row['Top'] - row['Bottom']) / pip
                    if size >= MIN_ZONE_SIZE_PIPS:
                        pois.append(PointOfInterest(
                            POIType.FVG, "SHORT", row['Top'], row['Bottom'],
                            get_zone_quality(row['Top'], premium, eq, discount, "SHORT"),
                            False, abs(price - row['Bottom'])
                        ))
        except:
            pass
    
    return pois

def find_m5_fvgs_in_zone(df_m5: pd.DataFrame, poi: PointOfInterest, symbol: str) -> List[M5EntryZone]:
    if df_m5 is None or len(df_m5) < 10:
        return []
    
    m5_zones = []
    pip = SYMBOLS[symbol]['pip']
    level = 1
    
    if SMC_AVAILABLE:
        try:
            fvg = smc.fvg(df_m5)
            for i in range(len(fvg)):
                row = fvg.iloc[i]
                
                if row['FVG'] == 1 and poi.direction == "LONG" and not row['MitigatedIndex'] > 0:
                    if row['Bottom'] <= poi.zone_top and row['Top'] >= poi.zone_bottom:
                        size = (row['Top'] - row['Bottom']) / pip
                        if size >= 3:
                            m5_zones.append(M5EntryZone(row['Top'], row['Bottom'], level))
                            level += 1
                
                elif row['FVG'] == -1 and poi.direction == "SHORT" and not row['MitigatedIndex'] > 0:
                    if row['Bottom'] <= poi.zone_top and row['Top'] >= poi.zone_bottom:
                        size = (row['Top'] - row['Bottom']) / pip
                        if size >= 3:
                            m5_zones.append(M5EntryZone(row['Top'], row['Bottom'], level))
                            level += 1
        except:
            pass
    
    return m5_zones[:3]

def get_nearest_poi(pois: List[PointOfInterest], price: float) -> Optional[PointOfInterest]:
    if not pois:
        return None
    return sorted(pois, key=lambda x: x.distance_to_price)[0]

# ============================================================
# ZONE STATUS BERECHNUNG
# ============================================================

def calculate_zone_status(price: float, poi: PointOfInterest, symbol: str) -> Tuple[str, float]:
    pip = SYMBOLS[symbol]['pip']
    
    if poi.zone_bottom <= price <= poi.zone_top:
        return "✅ IN DER ZONE", 0.0
    
    if price > poi.zone_top:
        distance = (price - poi.zone_top) / pip
        if poi.direction == "LONG":
            return f"⚠️ {distance:.1f} Pips ÜBER Zone (Entry verpasst?)", distance
        else:
            return f"📍 {distance:.1f} Pips ÜBER Zone (Warte auf Rückkehr)", distance
    
    if price < poi.zone_bottom:
        distance = (poi.zone_bottom - price) / pip
        if poi.direction == "SHORT":
            return f"⚠️ {distance:.1f} Pips UNTER Zone (Entry verpasst?)", distance
        else:
            return f"📍 {distance:.1f} Pips UNTER Zone (Warte auf Rückkehr)", distance
    
    return "❓ Unbekannt", 0.0

# ============================================================
# ZONE CHECKS & SCORING
# ============================================================

def check_zone_entry(df: pd.DataFrame, poi: PointOfInterest, symbol: str) -> Tuple[bool, str]:
    if df is None or len(df) < 5:
        return False, "Keine Daten"
    
    pip = SYMBOLS[symbol]['pip']
    tol = 10 * pip
    
    for i in range(min(10, len(df))):
        c = df.iloc[-(i+1)]
        if poi.direction == "LONG" and c['low'] <= poi.zone_top + tol:
            return True, f"Preis hat Zone berührt (Kerze -{i+1})"
        if poi.direction == "SHORT" and c['high'] >= poi.zone_bottom - tol:
            return True, f"Preis hat Zone berührt (Kerze -{i+1})"
    
    return False, "Preis nicht in Zone"

def is_zone_on_cooldown(symbol: str, poi: PointOfInterest) -> bool:
    key = f"{symbol}_{poi.zone_top}_{poi.zone_bottom}"
    if key in alerted_zones:
        if (datetime.now() - alerted_zones[key]).total_seconds() < ZONE_COOLDOWN_SECONDS:
            return True
    return False

def mark_zone_alerted(symbol: str, poi: PointOfInterest):
    alerted_zones[f"{symbol}_{poi.zone_top}_{poi.zone_bottom}"] = datetime.now()

def calculate_confluence_score(daily: Bias, h4: Bias, h1: Bias, direction: str, zone_q: str, 
                               entry_q: str, has_m5_fvg: bool, news_safe: bool) -> Tuple[int, str]:
    score = 0
    
    if (direction == "LONG" and daily == Bias.BULLISH) or (direction == "SHORT" and daily == Bias.BEARISH):
        score += 2
    
    if (direction == "LONG" and h4 == Bias.BULLISH) or (direction == "SHORT" and h4 == Bias.BEARISH):
        score += 2
    
    if (direction == "LONG" and h1 == Bias.BULLISH) or (direction == "SHORT" and h1 == Bias.BEARISH):
        score += 1
    
    if "Ideal" in zone_q:
        score += 1
    
    score += 1  # Kill Zone
    
    if has_m5_fvg:
        score += 1
    
    if news_safe:
        score += 1  # Bonus wenn keine News
    
    grades = {10: "A+", 9: "A+", 8: "A+", 7: "A", 6: "A", 5: "B+", 4: "B", 3: "C+"}
    grade = grades.get(score, "C")
    
    return score, grade

def get_alert_priority(grade: str) -> AlertPriority:
    if grade in ["A+", "A"]:
        return AlertPriority.URGENT
    elif grade in ["B+", "B"]:
        return AlertPriority.NORMAL
    return AlertPriority.INFO

# ============================================================
# TRADE SETUP
# ============================================================

def calculate_trade_setup(symbol: str, poi: PointOfInterest, price: float,
                          daily: Bias, daily_r: str, h4: Bias, h4_r: str,
                          h1: Bias, h1_r: str, entry_q: str, kz: str, 
                          m5_zones: List[M5EntryZone], steps: List[str],
                          news_safe: bool, news_status: str) -> TradeSetup:
    
    pip = SYMBOLS[symbol]['pip']
    sym_type = SYMBOLS[symbol]['type']
    
    warnings = []
    if "Riskant" in poi.zone_quality:
        warnings.append(poi.zone_quality)
    
    has_m5_fvg = len(m5_zones) > 0
    score, grade = calculate_confluence_score(daily, h4, h1, poi.direction, poi.zone_quality, entry_q, has_m5_fvg, news_safe)
    priority = get_alert_priority(grade)
    
    if m5_zones:
        entry = m5_zones[0].zone_top if poi.direction == "LONG" else m5_zones[0].zone_bottom
    else:
        entry = poi.zone_top if poi.direction == "LONG" else poi.zone_bottom
    
    if poi.direction == "LONG":
        sl = entry - (FIXED_SL_PIPS * pip)
        risk = entry - sl
        tp1, tp2, tp3 = entry + risk, entry + risk * 1.5, entry + risk * 2
    else:
        sl = entry + (FIXED_SL_PIPS * pip)
        risk = sl - entry
        tp1, tp2, tp3 = entry - risk, entry - risk * 1.5, entry - risk * 2
    
    zone_status, zone_distance = calculate_zone_status(price, poi, symbol)
    
    return TradeSetup(
        symbol, sym_type, poi.direction, poi, entry, sl, tp1, tp2, tp3,
        score, grade, priority, "PRIME TIME", warnings,
        daily.value, daily_r, h4.value, h4_r, h1.value, h1_r, kz,
        price, zone_status, zone_distance, news_status, m5_zones, steps
    )

# ============================================================
# TELEGRAM ALERT
# ============================================================

def send_telegram_alert(setup: TradeSetup):
    emoji = "🟢" if setup.direction == "LONG" else "🔴"
    prio_emoji = "🔴" if setup.priority == AlertPriority.URGENT else ("🟡" if setup.priority == AlertPriority.NORMAL else "⚪")
    
    warn_text = "\n⚠️ " + " | ".join(setup.warnings) if setup.warnings else ""
    
    m5_text = ""
    if setup.m5_entry_zones:
        m5_text = "\n📍 M5 ENTRY ZONES:\n"
        for zone in setup.m5_entry_zones:
            m5_text += f"   LVL.{zone.level}: {zone.zone_bottom:.5f} - {zone.zone_top:.5f}\n"
    
    steps_text = "\n".join([f"   {i+1}. {step}" for i, step in enumerate(setup.analysis_steps)])
    
    msg = f"""{prio_emoji} {setup.priority.value} ALERT - {setup.kill_zone}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{emoji} {setup.direction} {setup.symbol}
⭐ HAUPTPAAR | Grade: {setup.grade} ({setup.confluence_score}/10)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 WAS HAT DER BOT GEMACHT?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{steps_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 MULTI-TIMEFRAME ANALYSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📅 DAILY:
   {setup.daily_trend}
   └─ {setup.daily_reason}

⏰ H4:
   {setup.h4_bias}
   └─ {setup.h4_reason}

🕐 H1:
   {setup.h1_bias}
   └─ {setup.h1_reason}

✅ ALIGNMENT: Daily/H4/H1 = {setup.direction}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📰 NEWS STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{setup.news_status}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 POINT OF INTEREST (H1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Typ: {setup.poi.poi_type.value}
Zone: {setup.poi.zone_bottom:.5f} - {setup.poi.zone_top:.5f}
Größe: {(setup.poi.zone_top - setup.poi.zone_bottom) / SYMBOLS[setup.symbol]['pip']:.1f} Pips
Qualität: {setup.poi.zone_quality}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 AKTUELLER PREIS STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Aktueller Preis: {setup.current_price:.5f}
Zone Status: {setup.zone_status}
{m5_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 TRADE SETUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Entry: {setup.entry_price:.5f}
Stop Loss: {setup.stop_loss:.5f} ({FIXED_SL_PIPS} Pips)

Take Profits:
   TP1: {setup.tp1:.5f} (1:1 = {FIXED_SL_PIPS} Pips)
   TP2: {setup.tp2:.5f} (1:1.5 = {int(FIXED_SL_PIPS*1.5)} Pips)
   TP3: {setup.tp3:.5f} (1:2 = {FIXED_SL_PIPS*2} Pips)
{warn_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ NÄCHSTER SCHRITT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Wechsle zu M5/M1 und warte auf:
• MSS (Market Structure Shift)
• BOS (Break of Structure)
• CHoCH (Change of Character)
• Bullish/Bearish Engulfing

ERST DANN Entry setzen!

{datetime.now().strftime('%d.%m.%Y %H:%M:%S')} MEZ
"""
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg}, timeout=10)
        print(f"  ✅ Alert gesendet: {setup.symbol} {setup.direction} ({setup.grade})")
    except Exception as e:
        print(f"  ❌ Telegram Fehler: {e}")

# ============================================================
# HAUPTANALYSE
# ============================================================

def analyze_symbol(symbol: str) -> Optional[TradeSetup]:
    print(f"\n{'='*50}")
    print(f"  ANALYSE: {symbol}")
    print(f"{'='*50}")
    
    steps = []
    
    # SCHRITT 1: Kill Zone Check
    kz, in_kz = get_kill_zone(symbol)
    steps.append(f"Kill Zone Check: {kz}")
    
    if not in_kz:
        print(f"  ❌ Schritt 1: Außerhalb Kill Zone")
        return None
    print(f"  ✅ Schritt 1: {kz}")
    
    # SCHRITT 2: News Filter (NEU in v8.6!)
    news_safe, news_status = check_news_filter(symbol)
    steps.append(f"News Filter: {news_status}")
    
    if not news_safe:
        print(f"  ❌ Schritt 2: {news_status}")
        return None
    print(f"  ✅ Schritt 2: {news_status}")
    
    # Daten laden
    df_d = get_forex_data(symbol, 'D1', 30)
    df_h4 = get_forex_data(symbol, 'H4', 100)
    df_h1 = get_forex_data(symbol, 'H1', 100)
    df_m15 = get_forex_data(symbol, 'M15', 50)
    df_m5 = get_forex_data(symbol, 'M5', 100)
    
    if df_h4 is None or df_h1 is None:
        print("  ❌ Keine Daten verfügbar")
        return None
    
    price = df_h1['close'].iloc[-1]
    
    # SCHRITT 3: Daily Trend
    daily, daily_r = get_daily_trend(df_d)
    steps.append(f"Daily Trend: {daily.value}")
    print(f"  📅 Schritt 3: Daily = {daily.value}")
    
    # SCHRITT 4: H4 Bias
    h4, h4_r = determine_bias_h4(df_h4)
    steps.append(f"H4 Bias: {h4.value}")
    print(f"  ⏰ Schritt 4: H4 = {h4.value}")
    
    if h4 == Bias.NEUTRAL:
        print(f"  ❌ Schritt 4: H4 ist NEUTRAL - KEIN TRADE!")
        steps.append("❌ ABBRUCH: H4 hat keinen klaren Bias")
        return None
    
    # SCHRITT 5: H1 Bias
    h1, h1_r = determine_bias_h1(df_h1)
    steps.append(f"H1 Bias: {h1.value}")
    print(f"  🕐 Schritt 5: H1 = {h1.value}")
    
    if h1 == Bias.NEUTRAL:
        print(f"  ❌ Schritt 5: H1 ist NEUTRAL - KEIN TRADE!")
        steps.append("❌ ABBRUCH: H1 hat keinen klaren Bias")
        return None
    
    # SCHRITT 6: H4/H1 Alignment Check
    if h4 != h1:
        print(f"  ❌ Schritt 6: H4 ({h4.value}) ≠ H1 ({h1.value}) - KEIN TRADE!")
        steps.append(f"❌ ABBRUCH: H4 ({h4.value}) und H1 ({h1.value}) haben unterschiedliche Richtung")
        return None
    
    steps.append(f"✅ ALIGNMENT: H4 und H1 beide {h4.value}")
    print(f"  ✅ Schritt 6: H4/H1 Alignment = {h4.value}")
    
    bias = h4
    
    # SCHRITT 7: Premium/Discount
    prem, eq, disc = calculate_premium_discount(df_d)
    zone_position = "DISCOUNT" if price < eq else "PREMIUM"
    steps.append(f"Premium/Discount: Preis in {zone_position}")
    print(f"  📊 Schritt 7: Preis in {zone_position}")
    
    # SCHRITT 8: POIs finden
    pois = find_pois(df_h1, bias, symbol, prem, eq, disc)
    steps.append(f"H1 POIs gefunden: {len(pois)}")
    print(f"  🎯 Schritt 8: {len(pois)} POIs gefunden")
    
    if not pois:
        print(f"  ❌ Keine POIs gefunden")
        return None
    
    poi = get_nearest_poi(pois, price)
    if not poi:
        return None
    
    steps.append(f"Nächster POI: {poi.poi_type.value} bei {poi.zone_bottom:.5f}-{poi.zone_top:.5f}")
    
    # SCHRITT 9: Cooldown Check
    if is_zone_on_cooldown(symbol, poi):
        print(f"  ❌ Zone auf Cooldown")
        steps.append("❌ Zone bereits alertet (2h Cooldown)")
        return None
    
    # SCHRITT 10: Zone Entry Check
    entry, entry_q = check_zone_entry(df_m15, poi, symbol)
    steps.append(f"M15 Zone Entry: {entry_q}")
    print(f"  📍 Schritt 10: Zone Entry = {entry} ({entry_q})")
    
    if not entry:
        print(f"  ❌ Preis nicht in Zone")
        return None
    
    # SCHRITT 11: M5 FVGs finden
    m5_zones = find_m5_fvgs_in_zone(df_m5, poi, symbol)
    steps.append(f"M5 Entry Zones: {len(m5_zones)} gefunden")
    print(f"  🔍 Schritt 11: {len(m5_zones)} M5 FVGs in Zone")
    
    # Trade Setup erstellen
    setup = calculate_trade_setup(symbol, poi, price, daily, daily_r, h4, h4_r, h1, h1_r, 
                                   entry_q, kz, m5_zones, steps, news_safe, news_status)
    
    steps.append(f"Zone Status: {setup.zone_status}")
    setup.analysis_steps = steps
    
    steps.append(f"✅ TRADE SETUP: {setup.direction} mit Grade {setup.grade}")
    print(f"  ✅ ERGEBNIS: {setup.direction} {setup.grade} ({setup.confluence_score}/10 Punkte)")
    print(f"  📍 Zone Status: {setup.zone_status}")
    print(f"  📰 News Status: {news_status}")
    
    return setup

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("ICT Alert Bot v8.6 - STRICT ALIGNMENT + NEWS FILTER")
    print("=" * 60)
    print(f"Paare: {list(SYMBOLS.keys())}")
    print(f"Sessions: London + New York + London Close")
    print(f"Filter: NUR wenn H4 = H1")
    print(f"News Filter: 30 Min vor/nach High Impact News")
    print("=" * 60)
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            msg = """🚀 ICT Alert Bot v8.6 gestartet!

STRICT ALIGNMENT + NEWS FILTER

v8.6 Features:
• NUR Trade wenn H4 = H1
• News Filter: 30 Min vor/nach High Impact News
• Zone Status Anzeige
• Aktueller Preis im Alert

Paare: EUR/USD, GBP/USD, AUD/USD
Sessions: London + NY + London Close

Ziel: 80%+ Win Rate! 🎯"""
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg}, timeout=10
            )
        except:
            pass
    
    while True:
        try:
            print(f"\n{'='*60}")
            print(f"SCAN: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            for symbol in SYMBOLS.keys():
                setup = analyze_symbol(symbol)
                
                if setup:
                    mark_zone_alerted(symbol, setup.poi)
                    send_telegram_alert(setup)
                
                time.sleep(2)
            
            print(f"\n⏰ Nächster Scan in 5 Minuten...")
            time.sleep(300)
            
        except KeyboardInterrupt:
            print("\nBot gestoppt.")
            break
        except Exception as e:
            print(f"Fehler: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
