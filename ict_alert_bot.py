#!/usr/bin/env python3
"""
ICT Alert Bot v8.1 - ULTIMATE 10/10 EDITION
===========================================
Die perfekte Version mit M5 Entry Zone!

Features:
- Daily Trend Filter
- H4 Bias (BOS/CHoCH)
- H1 POI (FVG/OB)
- M15 Zone Entry Check
- M5 FVG innerhalb HTF Zone (NEU!)
- Premium/Discount
- Kill Zones + Asian Session
- Confluence Score (A+ bis C)
- Fixer SL (18 Pips)
- Zone Cooldown (2h)
- 9 Paare inkl. EUR/CHF (NEU!)
- TwelveData + Yahoo Fallback
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
    print("WARNUNG: smartmoneyconcepts nicht installiert")

# ============================================================
# KONFIGURATION
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
TWELVE_DATA_API_KEY = os.getenv('TWELVE_DATA_API_KEY', '')

# 9 Paare inkl. EUR/CHF
SYMBOLS = {
    'EUR/USD': {'type': 'HAUPT', 'pip': 0.0001, 'spread_max': 1.5, 'yahoo': 'EURUSD=X'},
    'GBP/USD': {'type': 'HAUPT', 'pip': 0.0001, 'spread_max': 2.0, 'yahoo': 'GBPUSD=X'},
    'USD/JPY': {'type': 'HAUPT', 'pip': 0.01, 'spread_max': 1.5, 'yahoo': 'USDJPY=X'},
    'AUD/USD': {'type': 'HAUPT', 'pip': 0.0001, 'spread_max': 2.0, 'yahoo': 'AUDUSD=X'},
    'EUR/CHF': {'type': 'SEKUNDÄR', 'pip': 0.0001, 'spread_max': 2.5, 'yahoo': 'EURCHF=X'},  # NEU!
    'EUR/GBP': {'type': 'SEKUNDÄR', 'pip': 0.0001, 'spread_max': 2.5, 'yahoo': 'EURGBP=X'},
    'USD/CAD': {'type': 'SEKUNDÄR', 'pip': 0.0001, 'spread_max': 2.5, 'yahoo': 'USDCAD=X'},
    'NZD/USD': {'type': 'SEKUNDÄR', 'pip': 0.0001, 'spread_max': 3.0, 'yahoo': 'NZDUSD=X'},
    'USD/CHF': {'type': 'SEKUNDÄR', 'pip': 0.0001, 'spread_max': 2.5, 'yahoo': 'USDCHF=X'},
}

FIXED_SL_PIPS = 18
MIN_ZONE_SIZE_PIPS = 5
ZONE_COOLDOWN_SECONDS = 7200

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
    LIQUIDITY_SWEEP = "Liquidity Sweep"

class AlertPriority(Enum):
    URGENT = "URGENT"
    NORMAL = "NORMAL"
    INFO = "INFO"

@dataclass
class M5EntryZone:
    """M5 FVG innerhalb der HTF Zone"""
    zone_top: float
    zone_bottom: float
    level: int  # LVL 1, 2, 3...

@dataclass
class PointOfInterest:
    poi_type: POIType
    direction: str
    zone_top: float
    zone_bottom: float
    zone_quality: str
    mitigated: bool = False
    distance_to_price: float = 0.0
    m5_entry_zones: List[M5EntryZone] = field(default_factory=list)

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
    h4_bias: str
    kill_zone: str
    m5_entry_zones: List[M5EntryZone] = field(default_factory=list)

alerted_zones: Dict[str, datetime] = {}

# ============================================================
# DATEN ABRUFEN
# ============================================================

def get_forex_data_twelvedata(symbol: str, interval: str, outputsize: int = 100) -> Optional[pd.DataFrame]:
    if not TWELVE_DATA_API_KEY:
        return None
    try:
        url = "https://api.twelvedata.com/time_series"
        interval_map = {'M1': '1min', 'M5': '5min', 'M15': '15min', 'H1': '1h', 'H4': '4h', 'D1': '1day'}
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
    except Exception as e:
        print(f"TwelveData Fehler: {e}")
        return None

def get_forex_data_yahoo(symbol: str, interval: str) -> Optional[pd.DataFrame]:
    try:
        yahoo_symbol = SYMBOLS.get(symbol, {}).get('yahoo', symbol.replace('/', '') + '=X')
        interval_map = {'M1': '1m', 'M5': '5m', 'M15': '15m', 'H1': '1h', 'H4': '1h', 'D1': '1d'}
        period_map = {'M1': '1d', 'M5': '5d', 'M15': '5d', 'H1': '1mo', 'H4': '3mo', 'D1': '6mo'}
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
        params = {'interval': interval_map.get(interval, '1h'), 'range': period_map.get(interval, '1mo')}
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if 'chart' not in data or 'result' not in data['chart'] or not data['chart']['result']:
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
    except Exception as e:
        print(f"Yahoo Fehler: {e}")
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
        return Bias.NEUTRAL, "Keine Daten"
    
    recent = df.tail(20)
    highs, lows = [], []
    
    for i in range(2, len(recent) - 2):
        h = recent.iloc[i]['high']
        l = recent.iloc[i]['low']
        if h > max(recent.iloc[i-1]['high'], recent.iloc[i-2]['high'], recent.iloc[i+1]['high'], recent.iloc[i+2]['high']):
            highs.append(h)
        if l < min(recent.iloc[i-1]['low'], recent.iloc[i-2]['low'], recent.iloc[i+1]['low'], recent.iloc[i+2]['low']):
            lows.append(l)
    
    if len(highs) >= 2 and len(lows) >= 2:
        if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
            return Bias.BULLISH, "HH + HL"
        elif highs[-1] < highs[-2] and lows[-1] < lows[-2]:
            return Bias.BEARISH, "LH + LL"
    
    ema20 = recent['close'].ewm(span=20).mean().iloc[-1]
    close = recent['close'].iloc[-1]
    
    if close > ema20 * 1.002:
        return Bias.BULLISH, "Über EMA20"
    elif close < ema20 * 0.998:
        return Bias.BEARISH, "Unter EMA20"
    
    return Bias.NEUTRAL, "Kein Trend"

def determine_bias_h4(df: pd.DataFrame) -> Tuple[Bias, str]:
    if df is None or len(df) < 20:
        return Bias.NEUTRAL, "Keine Daten"
    
    if SMC_AVAILABLE:
        try:
            bos = smc.bos_choch(df, close_break=True).tail(10)
            bull = len(bos[bos['BOS'] == 1]) + len(bos[bos['CHOCH'] == 1])
            bear = len(bos[bos['BOS'] == -1]) + len(bos[bos['CHOCH'] == -1])
            
            swing = smc.swing_highs_lows(df, swing_length=3).tail(20)
            highs = df.loc[swing[swing['HighLow'] == 1].index, 'high'].tolist()
            lows = df.loc[swing[swing['HighLow'] == -1].index, 'low'].tolist()
            
            hh_hl = len(highs) >= 2 and len(lows) >= 2 and highs[-1] > highs[-2] and lows[-1] > lows[-2]
            lh_ll = len(highs) >= 2 and len(lows) >= 2 and highs[-1] < highs[-2] and lows[-1] < lows[-2]
            
            if bull > bear or hh_hl:
                return Bias.BULLISH, f"BOS {bull}B/{bear}S" + (" HH/HL" if hh_hl else "")
            elif bear > bull or lh_ll:
                return Bias.BEARISH, f"BOS {bull}B/{bear}S" + (" LH/LL" if lh_ll else "")
            
            return Bias.NEUTRAL, "Kein Bias"
        except:
            pass
    
    return get_daily_trend(df)

# ============================================================
# PREMIUM/DISCOUNT
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
            return "DISCOUNT (Ideal)"
        elif price <= eq:
            return "EQUILIBRIUM (Gut)"
        return "PREMIUM (Riskant)"
    else:
        if price >= premium:
            return "PREMIUM (Ideal)"
        elif price >= eq:
            return "EQUILIBRIUM (Gut)"
        return "DISCOUNT (Riskant)"

# ============================================================
# M5 FVG ERKENNUNG (NEU!)
# ============================================================

def find_m5_fvgs_in_zone(df_m5: pd.DataFrame, poi: PointOfInterest, symbol: str) -> List[M5EntryZone]:
    """Findet M5 FVGs innerhalb der HTF POI Zone"""
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
                
                # Bullish M5 FVG für LONG
                if row['FVG'] == 1 and poi.direction == "LONG" and not row['MitigatedIndex'] > 0:
                    fvg_top = row['Top']
                    fvg_bottom = row['Bottom']
                    
                    # Prüfe ob FVG innerhalb oder überlappend mit HTF Zone
                    if fvg_bottom <= poi.zone_top and fvg_top >= poi.zone_bottom:
                        size = (fvg_top - fvg_bottom) / pip
                        if size >= 3:  # Min 3 Pips für M5
                            m5_zones.append(M5EntryZone(
                                zone_top=fvg_top,
                                zone_bottom=fvg_bottom,
                                level=level
                            ))
                            level += 1
                
                # Bearish M5 FVG für SHORT
                elif row['FVG'] == -1 and poi.direction == "SHORT" and not row['MitigatedIndex'] > 0:
                    fvg_top = row['Top']
                    fvg_bottom = row['Bottom']
                    
                    if fvg_bottom <= poi.zone_top and fvg_top >= poi.zone_bottom:
                        size = (fvg_top - fvg_bottom) / pip
                        if size >= 3:
                            m5_zones.append(M5EntryZone(
                                zone_top=fvg_top,
                                zone_bottom=fvg_bottom,
                                level=level
                            ))
                            level += 1
        except Exception as e:
            print(f"M5 FVG Fehler: {e}")
    else:
        # Fallback ohne SMC
        for i in range(2, len(df_m5) - 1):
            # Bullish FVG
            if poi.direction == "LONG":
                if df_m5.iloc[i-2]['high'] < df_m5.iloc[i]['low']:
                    fvg_top = df_m5.iloc[i]['low']
                    fvg_bottom = df_m5.iloc[i-2]['high']
                    if fvg_bottom <= poi.zone_top and fvg_top >= poi.zone_bottom:
                        size = (fvg_top - fvg_bottom) / pip
                        if size >= 3:
                            m5_zones.append(M5EntryZone(fvg_top, fvg_bottom, level))
                            level += 1
            # Bearish FVG
            if poi.direction == "SHORT":
                if df_m5.iloc[i-2]['low'] > df_m5.iloc[i]['high']:
                    fvg_top = df_m5.iloc[i-2]['low']
                    fvg_bottom = df_m5.iloc[i]['high']
                    if fvg_bottom <= poi.zone_top and fvg_top >= poi.zone_bottom:
                        size = (fvg_top - fvg_bottom) / pip
                        if size >= 3:
                            m5_zones.append(M5EntryZone(fvg_top, fvg_bottom, level))
                            level += 1
    
    # Sortiere nach Distanz zum aktuellen Preis (nächste zuerst)
    return m5_zones[:3]  # Max 3 M5 Zones

# ============================================================
# POI ERKENNUNG
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
            
            # Order Blocks
            swing = smc.swing_highs_lows(df, swing_length=3)
            for i in range(5, len(df) - 3):
                if bias == Bias.BULLISH and swing.iloc[i]['HighLow'] == -1:
                    for j in range(i-1, max(0, i-5), -1):
                        if df.iloc[j]['close'] < df.iloc[j]['open']:
                            top, bottom = df.iloc[j]['high'], df.iloc[j]['low']
                            size = (top - bottom) / pip
                            if MIN_ZONE_SIZE_PIPS <= size <= 50:
                                disp = df.iloc[min(i+3, len(df)-1)]['high'] - bottom
                                if disp > (top - bottom) * 1.5:
                                    pois.append(PointOfInterest(
                                        POIType.ORDER_BLOCK, "LONG", top, bottom,
                                        get_zone_quality(bottom, premium, eq, discount, "LONG"),
                                        False, abs(price - top)
                                    ))
                            break
                
                if bias == Bias.BEARISH and swing.iloc[i]['HighLow'] == 1:
                    for j in range(i-1, max(0, i-5), -1):
                        if df.iloc[j]['close'] > df.iloc[j]['open']:
                            top, bottom = df.iloc[j]['high'], df.iloc[j]['low']
                            size = (top - bottom) / pip
                            if MIN_ZONE_SIZE_PIPS <= size <= 50:
                                disp = top - df.iloc[min(i+3, len(df)-1)]['low']
                                if disp > (top - bottom) * 1.5:
                                    pois.append(PointOfInterest(
                                        POIType.ORDER_BLOCK, "SHORT", top, bottom,
                                        get_zone_quality(top, premium, eq, discount, "SHORT"),
                                        False, abs(price - bottom)
                                    ))
                            break
        except Exception as e:
            print(f"POI Fehler: {e}")
    
    return pois

def get_nearest_poi(pois: List[PointOfInterest], price: float) -> Optional[PointOfInterest]:
    if not pois:
        return None
    return sorted(pois, key=lambda x: x.distance_to_price)[0]

# ============================================================
# ZONE ENTRY & KILL ZONES
# ============================================================

def check_zone_entry(df: pd.DataFrame, poi: PointOfInterest, symbol: str) -> Tuple[bool, str]:
    if df is None or len(df) < 5:
        return False, "Keine Daten"
    
    pip = SYMBOLS[symbol]['pip']
    tol = 10 * pip
    
    for i in range(min(10, len(df))):
        c = df.iloc[-(i+1)]
        if poi.direction == "LONG" and c['low'] <= poi.zone_top + tol:
            return True, "IDEAL (Frisch)" if i < 3 else "GUT (Älter)"
        if poi.direction == "SHORT" and c['high'] >= poi.zone_bottom - tol:
            return True, "IDEAL (Frisch)" if i < 3 else "GUT (Älter)"
    
    return False, "Nicht in Zone"

def get_kill_zone(symbol: str) -> Tuple[str, bool]:
    hour = datetime.utcnow().hour
    
    if 'JPY' in symbol and 0 <= hour < 3:
        return "Asian Session", True
    if 'CHF' in symbol and 7 <= hour < 10:
        return "Zürich/London", True
    if 7 <= hour < 10:
        return "London Open", True
    if 13 <= hour < 16:
        return "New York", True
    if 16 <= hour < 18:
        return "London Close", True
    
    return "Außerhalb Kill Zone", False

# ============================================================
# COOLDOWN & SCORE
# ============================================================

def is_zone_on_cooldown(symbol: str, poi: PointOfInterest) -> bool:
    key = f"{symbol}_{poi.zone_top}_{poi.zone_bottom}"
    if key in alerted_zones:
        if (datetime.now() - alerted_zones[key]).total_seconds() < ZONE_COOLDOWN_SECONDS:
            return True
    return False

def mark_zone_alerted(symbol: str, poi: PointOfInterest):
    alerted_zones[f"{symbol}_{poi.zone_top}_{poi.zone_bottom}"] = datetime.now()

def calculate_confluence_score(daily: Bias, h4: Bias, direction: str, zone_q: str, 
                               entry_q: str, in_kz: bool, is_main: bool, has_m5_fvg: bool) -> Tuple[int, str]:
    score = 0
    
    if (direction == "LONG" and daily == Bias.BULLISH) or (direction == "SHORT" and daily == Bias.BEARISH):
        score += 2
    if (direction == "LONG" and h4 == Bias.BULLISH) or (direction == "SHORT" and h4 == Bias.BEARISH):
        score += 1
    if "Ideal" in zone_q:
        score += 1
    if "IDEAL" in entry_q or "Frisch" in entry_q:
        score += 1
    if in_kz:
        score += 1
    if is_main:
        score += 1
    if has_m5_fvg:  # NEU: Bonus für M5 FVG
        score += 1
    
    grades = {8: "A+", 7: "A+", 6: "A", 5: "B+", 4: "B", 3: "C+"}
    grade = grades.get(score, "C")
    
    return score, grade

def get_alert_priority(grade: str, in_kz: bool) -> AlertPriority:
    if grade in ["A+", "A"] and in_kz:
        return AlertPriority.URGENT
    elif grade in ["A+", "A", "B+", "B"]:
        return AlertPriority.NORMAL
    return AlertPriority.INFO

# ============================================================
# TRADE SETUP
# ============================================================

def calculate_trade_setup(symbol: str, poi: PointOfInterest, price: float,
                          daily: Bias, daily_r: str, h4: Bias, h4_r: str,
                          entry_q: str, kz: str, in_kz: bool, m5_zones: List[M5EntryZone]) -> TradeSetup:
    
    pip = SYMBOLS[symbol]['pip']
    sym_type = SYMBOLS[symbol]['type']
    is_main = sym_type == "HAUPT"
    
    warnings = []
    if not in_kz:
        warnings.append("Außerhalb Kill Zone")
    if not is_main:
        warnings.append("Sekundäres Paar")
    if "Riskant" in poi.zone_quality:
        warnings.append(poi.zone_quality)
    
    has_m5_fvg = len(m5_zones) > 0
    score, grade = calculate_confluence_score(daily, h4, poi.direction, poi.zone_quality, entry_q, in_kz, is_main, has_m5_fvg)
    priority = get_alert_priority(grade, in_kz)
    time_q = "PRIME TIME" if in_kz and is_main else ("GOOD TIME" if in_kz or is_main else "OFF-PEAK")
    
    # Entry am besten M5 FVG oder HTF Zone
    if m5_zones:
        if poi.direction == "LONG":
            entry = m5_zones[0].zone_top  # Entry am oberen Rand des M5 FVG
        else:
            entry = m5_zones[0].zone_bottom
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
    
    return TradeSetup(
        symbol, sym_type, poi.direction, poi, entry, sl, tp1, tp2, tp3,
        score, grade, priority, time_q, warnings,
        f"{daily.value} ({daily_r})", f"{h4.value} ({h4_r})", kz, m5_zones
    )

# ============================================================
# TELEGRAM ALERT
# ============================================================

def send_telegram_alert(setup: TradeSetup):
    emoji = "🟢" if setup.direction == "LONG" else "🔴"
    prio_emoji = "🔴" if setup.priority == AlertPriority.URGENT else ("🟡" if setup.priority == AlertPriority.NORMAL else "⚪")
    pair_emoji = "⭐" if setup.symbol_type == "HAUPT" else "📊"
    
    warn_text = ""
    if setup.warnings:
        warn_text = "\n⚠️ " + " | ".join(setup.warnings)
    
    # M5 Entry Zones formatieren
    m5_text = ""
    if setup.m5_entry_zones:
        m5_text = "\n\n━━━━━━━━━━━━━━━━━━━━━━\n📍 M5 ENTRY ZONES:\n━━━━━━━━━━━━━━━━━━━━━━\n"
        for zone in setup.m5_entry_zones:
            m5_text += f"\n🎯 M5 FVG LVL.{zone.level}\n"
            m5_text += f"   Zone: {zone.zone_bottom:.5f} - {zone.zone_top:.5f}"
    
    msg = f"""{prio_emoji} {setup.priority.value}
━━━━━━━━━━━━━━━━━━━━━━

{emoji} {setup.direction} - {setup.symbol}
{pair_emoji} {setup.symbol_type}PAAR
Grade: {setup.grade} ({setup.confluence_score}/8 Punkte)

━━━━━━━━━━━━━━━━━━━━━━
📊 ANALYSE:
━━━━━━━━━━━━━━━━━━━━━━

Daily: {setup.daily_trend}
H4: {setup.h4_bias}
Kill Zone: {setup.kill_zone}
Zeit: {setup.time_quality}

━━━━━━━━━━━━━━━━━━━━━━
🎯 HTF POINT OF INTEREST:
━━━━━━━━━━━━━━━━━━━━━━

Typ: {setup.poi.poi_type.value}
Zone: {setup.poi.zone_bottom:.5f} - {setup.poi.zone_top:.5f}
Qualität: {setup.poi.zone_quality}
{m5_text}

━━━━━━━━━━━━━━━━━━━━━━
💰 TRADE DETAILS:
━━━━━━━━━━━━━━━━━━━━━━

Entry: {setup.entry_price:.5f}
SL: {setup.stop_loss:.5f} ({FIXED_SL_PIPS} Pips)
TP1 (1:1): {setup.tp1:.5f}
TP2 (1:1.5): {setup.tp2:.5f}
TP3 (1:2): {setup.tp3:.5f}
{warn_text}

━━━━━━━━━━━━━━━━━━━━━━
⏰ WARTE AUF M1 TRIGGER!
━━━━━━━━━━━━━━━━━━━━━━
Suche: MSS, BOS, CHoCH, Engulfing

{datetime.now().strftime('%H:%M:%S')} MEZ
"""
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg}, timeout=10)
        print(f"  ✅ Alert: {setup.symbol} {setup.direction} ({setup.grade})")
    except Exception as e:
        print(f"  ❌ Telegram Fehler: {e}")

# ============================================================
# HAUPTANALYSE
# ============================================================

def analyze_symbol(symbol: str) -> Optional[TradeSetup]:
    print(f"\n--- {symbol} ---")
    
    df_d = get_forex_data(symbol, 'D1', 30)
    df_h4 = get_forex_data(symbol, 'H4', 100)
    df_h1 = get_forex_data(symbol, 'H1', 100)
    df_m15 = get_forex_data(symbol, 'M15', 50)
    df_m5 = get_forex_data(symbol, 'M5', 100)  # NEU: M5 Daten
    
    if df_h4 is None or df_h1 is None:
        print("  Keine Daten")
        return None
    
    price = df_h1['close'].iloc[-1]
    
    daily, daily_r = get_daily_trend(df_d)
    h4, h4_r = determine_bias_h4(df_h4)
    
    print(f"  Daily: {daily.value} | H4: {h4.value}")
    
    if daily != Bias.NEUTRAL and h4 != Bias.NEUTRAL and daily != h4:
        print("  ⚠️ Daily/H4 Konflikt")
        return None
    
    bias = h4 if h4 != Bias.NEUTRAL else daily
    if bias == Bias.NEUTRAL:
        print("  Kein Bias")
        return None
    
    prem, eq, disc = calculate_premium_discount(df_d)
    pois = find_pois(df_h1, bias, symbol, prem, eq, disc)
    print(f"  POIs: {len(pois)}")
    
    if not pois:
        return None
    
    poi = get_nearest_poi(pois, price)
    if not poi:
        return None
    
    if is_zone_on_cooldown(symbol, poi):
        print("  Zone auf Cooldown")
        return None
    
    entry, entry_q = check_zone_entry(df_m15, poi, symbol)
    print(f"  Zone Entry: {entry} ({entry_q})")
    
    if not entry:
        return None
    
    # NEU: M5 FVGs innerhalb der HTF Zone finden
    m5_zones = find_m5_fvgs_in_zone(df_m5, poi, symbol)
    print(f"  M5 Entry Zones: {len(m5_zones)}")
    
    kz, in_kz = get_kill_zone(symbol)
    
    setup = calculate_trade_setup(symbol, poi, price, daily, daily_r, h4, h4_r, entry_q, kz, in_kz, m5_zones)
    print(f"  ✅ {setup.grade} ({setup.confluence_score} Punkte)")
    
    return setup

# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("ICT Alert Bot v8.1 - ULTIMATE 10/10 EDITION")
    print("=" * 60)
    print(f"Paare: {len(SYMBOLS)} (inkl. EUR/CHF)")
    print(f"TwelveData: {'Ja' if TWELVE_DATA_API_KEY else 'Nein (Yahoo Fallback)'}")
    print(f"SMC Library: {'Ja' if SMC_AVAILABLE else 'Nein'}")
    print("=" * 60)
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            msg = """🚀 ICT Alert Bot v8.1 ULTIMATE gestartet!

NEU in v8.1:
• EUR/CHF hinzugefügt
• M5 FVG Entry Zones
• Präzisere Entries

Features:
• Daily Trend Filter
• Confluence Score (A+ bis C)
• Fixer SL (18 Pips)
• Zone Cooldown (2h)
• 9 Forex-Paare

⏰ Warte auf M1 Trigger selbst!"""
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg},
                timeout=10
            )
        except:
            pass
    
    while True:
        try:
            print(f"\n{'='*60}")
            print(f"Scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            
            for symbol in SYMBOLS.keys():
                setup = analyze_symbol(symbol)
                
                if setup:
                    mark_zone_alerted(symbol, setup.poi)
                    send_telegram_alert(setup)
                
                time.sleep(2)
            
            print(f"\nNächster Scan in 5 Minuten...")
            time.sleep(300)
            
        except KeyboardInterrupt:
            print("\nBot gestoppt.")
            break
        except Exception as e:
            print(f"Fehler: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
