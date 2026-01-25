#!/usr/bin/env python3
"""
ICT Alert Bot v8.7 - SMART ALIGNMENT EDITION

NEU in v8.7:
- Daily als übergeordneter Filter
- H4 NEUTRAL erlaubt wenn H1 = Daily
- Intelligentere Alignment-Logik

Features:
- Daily Trend Filter (übergeordnet)
- H4 Bias (BOS/CHoCH)
- H1 POI (FVG/OB)
- M15 Zone Entry Check
- M5 FVG innerhalb HTF Zone
- Premium/Discount
- Kill Zones
- Confluence Score (A+ bis C)
- Fixer SL (18 Pips)
- Zone Cooldown (2h)
- News Filter (30 Min)
- Zone Status Anzeige
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
SCAN_INTERVAL = 5

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
    m5_entry_zones: List[M5EntryZone] = field(default_factory=list)

@dataclass
class TradeSetup:
    symbol: str
    symbol_type: str
    direction: str
    poi: PointOfInterest
    entry_price: float
    sl_price: float
    tp1_price: float
    tp2_price: float
    tp3_price: float
    confluence_score: int
    grade: str
    priority: AlertPriority
    time_quality: str
    warnings: List[str]
    daily_trend: str
    h4_bias: str
    h1_bias: str
    kill_zone: str
    current_price: float
    zone_status: str
    alignment_status: str
    m5_entry_zones: List[M5EntryZone] = field(default_factory=list)
    news_status: str = ""

alerted_zones: Dict[str, datetime] = {}

def get_forex_data_yahoo(symbol: str, interval: str, outputsize: int = 100) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf
        yahoo_symbol = SYMBOLS[symbol]['yahoo']
        interval_map = {'D1': '1d', 'H4': '1h', 'H1': '1h', 'M15': '15m', 'M5': '5m'}
        yf_interval = interval_map.get(interval, '1h')
        period = '1mo' if interval in ['D1', 'H4', 'H1'] else '5d'
        
        ticker = yf.Ticker(yahoo_symbol)
        df = ticker.history(period=period, interval=yf_interval)
        if df.empty:
            return None
        
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        if 'datetime' not in df.columns and 'date' in df.columns:
            df['datetime'] = df['date']
        
        if interval == 'H4' and yf_interval == '1h':
            df['group'] = df.index // 4
            df = df.groupby('group').agg({
                'datetime': 'first', 'open': 'first', 'high': 'max',
                'low': 'min', 'close': 'last'
            }).reset_index(drop=True)
        
        return df.tail(outputsize)
    except Exception as e:
        return None

def get_forex_data(symbol: str, interval: str, outputsize: int = 100) -> Optional[pd.DataFrame]:
    return get_forex_data_yahoo(symbol, interval, outputsize)

def get_daily_trend(df: pd.DataFrame) -> Tuple[Bias, str]:
    if df is None or len(df) < 10:
        return Bias.NEUTRAL, "Keine Daten"
    
    recent = df.tail(20)
    ema10 = recent['close'].ewm(span=10).mean().iloc[-1]
    ema20 = recent['close'].ewm(span=20).mean().iloc[-1]
    close = recent['close'].iloc[-1]
    
    if close > ema10 > ema20:
        return Bias.BULLISH, "Über EMAs"
    elif close < ema10 < ema20:
        return Bias.BEARISH, "Unter EMAs"
    return Bias.NEUTRAL, "Kein Trend"

def determine_bias_h4(df: pd.DataFrame) -> Tuple[Bias, str]:
    if df is None or len(df) < 20:
        return Bias.NEUTRAL, "Keine Daten"
    return get_daily_trend(df)

def determine_bias_h1(df: pd.DataFrame) -> Tuple[Bias, str]:
    if df is None or len(df) < 20:
        return Bias.NEUTRAL, "Keine Daten"
    
    recent = df.tail(20)
    ema10 = recent['close'].ewm(span=10).mean().iloc[-1]
    ema20 = recent['close'].ewm(span=20).mean().iloc[-1]
    close = recent['close'].iloc[-1]
    
    if close > ema10 > ema20:
        return Bias.BULLISH, "Preis > EMA10 > EMA20"
    elif close < ema10 < ema20:
        return Bias.BEARISH, "Preis < EMA10 < EMA20"
    return Bias.NEUTRAL, "EMAs kreuzen"

def check_smart_alignment(daily: Bias, h4: Bias, h1: Bias) -> Tuple[bool, str, str]:
    """
    v8.7 Smart Alignment:
    - Daily muss klar sein
    - H1 muss = Daily sein
    - H4 darf NEUTRAL sein (Pullback)
    """
    if daily == Bias.NEUTRAL:
        return False, "", "❌ Daily NEUTRAL"
    
    if h1 != daily:
        if h1 == Bias.NEUTRAL:
            return False, "", "❌ H1 NEUTRAL"
        return False, "", f"❌ H1 ({h1.value}) ≠ Daily ({daily.value})"
    
    if h4 == daily:
        direction = "LONG" if daily == Bias.BULLISH else "SHORT"
        return True, direction, f"✅ PERFEKT: Daily = H4 = H1 ({daily.value})"
    elif h4 == Bias.NEUTRAL:
        direction = "LONG" if daily == Bias.BULLISH else "SHORT"
        return True, direction, f"⚠️ H4 NEUTRAL - Daily & H1 sind {daily.value}"
    else:
        return False, "", f"❌ H4 ({h4.value}) ≠ Daily ({daily.value})"

def calculate_premium_discount(df: pd.DataFrame) -> Tuple[float, float, float]:
    if df is None or len(df) < 5:
        return 0, 0, 0
    r = df.tail(20)
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

def find_pois(df: pd.DataFrame, bias: Bias, symbol: str, prem: float, eq: float, disc: float) -> List[PointOfInterest]:
    if df is None or len(df) < 20:
        return []
    
    pois = []
    pip = SYMBOLS[symbol]['pip']
    direction = "LONG" if bias == Bias.BULLISH else "SHORT"
    
    for i in range(2, len(df) - 1):
        if direction == "LONG":
            if df.iloc[i-2]['high'] < df.iloc[i]['low']:
                zone_top = df.iloc[i]['low']
                zone_bottom = df.iloc[i-2]['high']
                size = (zone_top - zone_bottom) / pip
                if size >= MIN_ZONE_SIZE_PIPS:
                    quality = get_zone_quality(zone_bottom, prem, eq, disc, direction)
                    pois.append(PointOfInterest(POIType.FVG, direction, zone_top, zone_bottom, quality))
        else:
            if df.iloc[i-2]['low'] > df.iloc[i]['high']:
                zone_top = df.iloc[i-2]['low']
                zone_bottom = df.iloc[i]['high']
                size = (zone_top - zone_bottom) / pip
                if size >= MIN_ZONE_SIZE_PIPS:
                    quality = get_zone_quality(zone_top, prem, eq, disc, direction)
                    pois.append(PointOfInterest(POIType.FVG, direction, zone_top, zone_bottom, quality))
    
    return pois[-5:] if len(pois) > 5 else pois

def get_nearest_poi(pois: List[PointOfInterest], price: float) -> Optional[PointOfInterest]:
    if not pois:
        return None
    for poi in pois:
        poi.distance_to_price = abs(price - (poi.zone_top + poi.zone_bottom) / 2)
    return min(pois, key=lambda x: x.distance_to_price)

def find_m5_fvgs_in_zone(df_m5: pd.DataFrame, poi: PointOfInterest, symbol: str) -> List[M5EntryZone]:
    if df_m5 is None or len(df_m5) < 10:
        return []
    
    m5_zones = []
    pip = SYMBOLS[symbol]['pip']
    level = 1
    
    for i in range(2, len(df_m5) - 1):
        if poi.direction == "LONG":
            if df_m5.iloc[i-2]['high'] < df_m5.iloc[i]['low']:
                fvg_top = df_m5.iloc[i]['low']
                fvg_bottom = df_m5.iloc[i-2]['high']
                if fvg_bottom <= poi.zone_top and fvg_top >= poi.zone_bottom:
                    size = (fvg_top - fvg_bottom) / pip
                    if size >= 3:
                        m5_zones.append(M5EntryZone(fvg_top, fvg_bottom, level))
                        level += 1
        else:
            if df_m5.iloc[i-2]['low'] > df_m5.iloc[i]['high']:
                fvg_top = df_m5.iloc[i-2]['low']
                fvg_bottom = df_m5.iloc[i]['high']
                if fvg_bottom <= poi.zone_top and fvg_top >= poi.zone_bottom:
                    size = (fvg_top - fvg_bottom) / pip
                    if size >= 3:
                        m5_zones.append(M5EntryZone(fvg_top, fvg_bottom, level))
                        level += 1
    
    return m5_zones[:3]

def check_zone_entry(df: pd.DataFrame, poi: PointOfInterest, symbol: str) -> Tuple[bool, str]:
    if df is None or len(df) < 5:
        return False, "Keine Daten"
    
    pip = SYMBOLS[symbol]['pip']
    tolerance = 3 * pip
    
    for i in range(min(10, len(df))):
        candle = df.iloc[-(i+1)]
        if poi.direction == "LONG":
            if candle['low'] <= poi.zone_top + tolerance:
                return True, "Zone berührt"
        else:
            if candle['high'] >= poi.zone_bottom - tolerance:
                return True, "Zone berührt"
    
    return False, "Preis nicht in Zone"

def get_zone_status(current_price: float, poi: PointOfInterest, symbol: str) -> str:
    pip = SYMBOLS[symbol]['pip']
    if poi.zone_bottom <= current_price <= poi.zone_top:
        return "✅ IN DER ZONE"
    elif current_price > poi.zone_top:
        dist = (current_price - poi.zone_top) / pip
        return f"⚠️ {dist:.1f} Pips ÜBER Zone"
    else:
        dist = (poi.zone_bottom - current_price) / pip
        return f"📍 {dist:.1f} Pips UNTER Zone"

def is_zone_on_cooldown(symbol: str, poi: PointOfInterest) -> bool:
    key = f"{symbol}_{poi.zone_top:.5f}_{poi.zone_bottom:.5f}"
    if key in alerted_zones:
        if datetime.now() - alerted_zones[key] < timedelta(seconds=ZONE_COOLDOWN_SECONDS):
            return True
    return False

def mark_zone_alerted(symbol: str, poi: PointOfInterest):
    key = f"{symbol}_{poi.zone_top:.5f}_{poi.zone_bottom:.5f}"
    alerted_zones[key] = datetime.now()

def get_kill_zone(symbol: str) -> Tuple[str, bool]:
    now = datetime.utcnow()
    hour = now.hour
    
    if 7 <= hour < 10:
        return "London Open (07:00-10:00 UTC)", True
    if 13 <= hour < 16:
        return "New York (13:00-16:00 UTC)", True
    if 15 <= hour < 17:
        return "London Close (15:00-17:00 UTC)", True
    
    return "Außerhalb Kill Zone", False

def check_high_impact_news() -> Tuple[bool, str]:
    now = datetime.utcnow()
    if now.weekday() == 4 and now.day <= 7 and 13 <= now.hour <= 14:
        return True, "⚠️ NFP heute!"
    if now.weekday() == 2 and 18 <= now.hour <= 20:
        return True, "⚠️ Mögliche FOMC!"
    return False, "✅ Keine High Impact News"

def calculate_trade_setup(symbol, poi, price, daily, daily_r, h4, h4_r, h1, h1_r, 
                          entry_q, kz, in_kz, m5_zones, alignment_status) -> TradeSetup:
    pip = SYMBOLS[symbol]['pip']
    direction = poi.direction
    
    if direction == "LONG":
        entry = poi.zone_top
        sl = entry - (FIXED_SL_PIPS * pip)
        tp1 = entry + (FIXED_SL_PIPS * pip)
        tp2 = entry + (FIXED_SL_PIPS * 1.5 * pip)
        tp3 = entry + (FIXED_SL_PIPS * 2 * pip)
    else:
        entry = poi.zone_bottom
        sl = entry + (FIXED_SL_PIPS * pip)
        tp1 = entry - (FIXED_SL_PIPS * pip)
        tp2 = entry - (FIXED_SL_PIPS * 1.5 * pip)
        tp3 = entry - (FIXED_SL_PIPS * 2 * pip)
    
    score = 0
    warnings = []
    
    if daily != Bias.NEUTRAL:
        score += 2
    if h4 == daily:
        score += 2
    elif h4 == Bias.NEUTRAL:
        score += 1
        warnings.append("H4 NEUTRAL (Pullback)")
    if h1 == daily:
        score += 1
    if "Ideal" in poi.zone_quality:
        score += 1
    if in_kz:
        score += 1
    if m5_zones:
        score += 1
    
    has_news, news_msg = check_high_impact_news()
    if not has_news:
        score += 1
    else:
        warnings.append(news_msg)
    
    if score >= 8: grade = "A+"
    elif score >= 7: grade = "A"
    elif score >= 6: grade = "B+"
    elif score >= 5: grade = "B"
    else: grade = "C"
    
    if grade in ["A+", "A"] and in_kz:
        priority = AlertPriority.URGENT
    elif grade in ["B+", "B"]:
        priority = AlertPriority.NORMAL
    else:
        priority = AlertPriority.INFO
    
    zone_status = get_zone_status(price, poi, symbol)
    
    return TradeSetup(
        symbol=symbol, symbol_type=SYMBOLS[symbol]['type'], direction=direction,
        poi=poi, entry_price=entry, sl_price=sl, tp1_price=tp1, tp2_price=tp2, tp3_price=tp3,
        confluence_score=score, grade=grade, priority=priority, time_quality=entry_q,
        warnings=warnings, daily_trend=f"{daily.value} ({daily_r})",
        h4_bias=f"{h4.value} ({h4_r})", h1_bias=f"{h1.value} ({h1_r})",
        kill_zone=kz, current_price=price, zone_status=zone_status,
        alignment_status=alignment_status, m5_entry_zones=m5_zones, news_status=news_msg
    )

def send_telegram_alert(setup: TradeSetup):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    priority_emoji = {AlertPriority.URGENT: "🔴", AlertPriority.NORMAL: "🟡", AlertPriority.INFO: "⚪"}
    
    m5_text = ""
    if setup.m5_entry_zones:
        m5_text = "\n\n📍 M5 ENTRY ZONES:\n"
        for zone in setup.m5_entry_zones:
            m5_text += f"• LVL.{zone.level}: {zone.zone_bottom:.5f} - {zone.zone_top:.5f}\n"
    
    warnings_text = ""
    if setup.warnings:
        warnings_text = "\n⚠️ " + " | ".join(setup.warnings)
    
    msg = f"""{priority_emoji[setup.priority]} ICT ALERT v8.7 {priority_emoji[setup.priority]}

📊 {setup.symbol} | {setup.direction} | {setup.grade}

📈 ALIGNMENT:
Daily: {setup.daily_trend}
H4: {setup.h4_bias}
H1: {setup.h1_bias}
{setup.alignment_status}

🎯 H1 FVG ZONE:
{setup.poi.zone_bottom:.5f} - {setup.poi.zone_top:.5f}
{setup.poi.zone_quality}

📍 STATUS:
Preis: {setup.current_price:.5f}
{setup.zone_status}
{m5_text}
💰 VORSCHLAG:
Entry: {setup.entry_price:.5f}
SL: {setup.sl_price:.5f} ({FIXED_SL_PIPS} Pips)
TP1: {setup.tp1_price:.5f} (1:1)

📊 Score: {setup.confluence_score}/10
🕐 {setup.kill_zone}
📰 {setup.news_status}
{warnings_text}

⏰ Warte auf M5/M1 Trigger!"""
    
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={'chat_id': TELEGRAM_CHAT_ID, 'text': msg},
            timeout=10
        )
    except:
        pass

def analyze_symbol(symbol: str) -> Optional[TradeSetup]:
    print(f"\n--- {symbol} ---")
    
    df_d = get_forex_data(symbol, 'D1', 30)
    df_h4 = get_forex_data(symbol, 'H4', 100)
    df_h1 = get_forex_data(symbol, 'H1', 100)
    df_m15 = get_forex_data(symbol, 'M15', 50)
    df_m5 = get_forex_data(symbol, 'M5', 100)
    
    if df_h4 is None or df_h1 is None:
        print("  Keine Daten")
        return None
    
    price = df_h1['close'].iloc[-1]
    
    daily, daily_r = get_daily_trend(df_d)
    h4, h4_r = determine_bias_h4(df_h4)
    h1, h1_r = determine_bias_h1(df_h1)
    
    print(f"  Daily: {daily.value} | H4: {h4.value} | H1: {h1.value}")
    
    is_valid, direction, alignment_status = check_smart_alignment(daily, h4, h1)
    print(f"  {alignment_status}")
    
    if not is_valid:
        return None
    
    prem, eq, disc = calculate_premium_discount(df_d)
    bias = Bias.BULLISH if direction == "LONG" else Bias.BEARISH
    pois = find_pois(df_h1, bias, symbol, prem, eq, disc)
    print(f"  POIs: {len(pois)}")
    
    if not pois:
        return None
    
    poi = get_nearest_poi(pois, price)
    if not poi or is_zone_on_cooldown(symbol, poi):
        return None
    
    entry, entry_q = check_zone_entry(df_m15, poi, symbol)
    if not entry:
        return None
    
    m5_zones = find_m5_fvgs_in_zone(df_m5, poi, symbol)
    kz, in_kz = get_kill_zone(symbol)
    
    if not in_kz:
        print(f"  Außerhalb Kill Zone")
        return None
    
    setup = calculate_trade_setup(symbol, poi, price, daily, daily_r, h4, h4_r,
                                   h1, h1_r, entry_q, kz, in_kz, m5_zones, alignment_status)
    print(f"  ✅ {setup.grade} ({setup.confluence_score}/10)")
    return setup

def main():
    print("=" * 50)
    print("ICT Alert Bot v8.7 - SMART ALIGNMENT")
    print("=" * 50)
    
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={'chat_id': TELEGRAM_CHAT_ID, 'text': '🚀 ICT Alert Bot v8.7 gestartet!\n\nSMART ALIGNMENT:\n• Daily = übergeordnet\n• H4 NEUTRAL erlaubt wenn H1 = Daily'},
                timeout=10
            )
        except:
            pass
    
    while True:
        try:
            print(f"\nScan: {datetime.now()}")
            for symbol in SYMBOLS:
                setup = analyze_symbol(symbol)
                if setup:
                    send_telegram_alert(setup)
                    mark_zone_alerted(symbol, setup.poi)
                time.sleep(2)
            
            print(f"Nächster Scan in {SCAN_INTERVAL} Min...")
            time.sleep(SCAN_INTERVAL * 60)
        except Exception as e:
            print(f"Fehler: {e}")
            time.sleep(60)

if __name__ == "__main__":
    main()
