import numpy as np
from .indicators import MA, MACD, RSI, KDJ, BOLL, OBV, ATR, detect_support_resistance


def score_trend(df: dict) -> tuple:
    close = np.array(df["close"], dtype=float)
    high = np.array(df["high"], dtype=float)
    low = np.array(df["low"], dtype=float)
    n = len(close)
    if n < 60:
        return 0, {"error": "数据不足"}

    ma5 = MA(close, 5)
    ma10 = MA(close, 10)
    ma20 = MA(close, 20)
    ma60 = MA(close, 60)
    dif, dea, macd_hist = MACD(close)

    score = 15
    details = {}

    # MA alignment (12 pts)
    ma_score = 0
    if not np.isnan(ma5[-1]) and not np.isnan(ma20[-1]):
        if ma5[-1] > ma10[-1] > ma20[-1] > ma60[-1]:
            ma_score = 12
        elif ma5[-1] > ma10[-1] > ma20[-1]:
            ma_score = 8
        elif ma5[-1] > ma20[-1]:
            ma_score = 4
        elif ma5[-1] < ma10[-1] < ma20[-1] < ma60[-1]:
            ma_score = -6
        elif ma5[-1] < ma20[-1]:
            ma_score = -3
    score += ma_score
    details["均线排列"] = {"score": ma_score, "desc": f"MA5={ma5[-1]:.2f} MA10={ma10[-1]:.2f} MA20={ma20[-1]:.2f}"}

    # MACD state (10 pts)
    macd_score = 0
    if n > 30 and not np.isnan(macd_hist[-1]):
        latest_hist = macd_hist[~np.isnan(macd_hist)]
        if len(latest_hist) >= 3:
            if latest_hist[-1] > 0 and latest_hist[-1] > latest_hist[-2]:
                macd_score = 10
            elif latest_hist[-1] > 0 and latest_hist[-1] < latest_hist[-2]:
                macd_score = 5
            elif latest_hist[-1] < 0 and latest_hist[-1] > latest_hist[-2]:
                macd_score = 3
            elif latest_hist[-1] < 0 and latest_hist[-1] < latest_hist[-2]:
                macd_score = -4
            else:
                macd_score = 0
    score += macd_score
    details["MACD状态"] = {"score": macd_score, "desc": f"DIF={dif[-1]:.2f} DEA={dea[-1]:.2f} MACD={macd_hist[-1]:.2f}"}

    # Trend consistency (8 pts)
    cons_score = 0
    short_trend = 0.0
    long_trend = 0.0
    if n > 20:
        short_trend = (ma5[-1] - ma5[-5]) / ma5[-5] * 100 if not np.isnan(ma5[-5]) else 0
        long_trend = (ma20[-1] - ma20[-10]) / ma20[-10] * 100 if not np.isnan(ma20[-10]) else 0
        if short_trend > 0 and long_trend > 0:
            cons_score = 8
        elif short_trend > 0 or long_trend > 0:
            cons_score = 4
        elif short_trend < 0 and long_trend < 0:
            cons_score = -4
        else:
            cons_score = 0
    score += cons_score
    details["趋势一致性"] = {"score": cons_score, "desc": f"短期趋势={short_trend:.2f}% 长期趋势={long_trend:.2f}%"}

    return max(0, min(30, score)), details


def score_overbought_oversold(df: dict) -> tuple:
    close = np.array(df["close"], dtype=float)
    high = np.array(df["high"], dtype=float)
    low = np.array(df["low"], dtype=float)
    n = len(close)
    if n < 15:
        return 0, {}

    k, d, j = KDJ(high, low, close)
    rsi_vals = RSI(close)

    score = 13
    details = {}

    # KDJ (13 pts)
    kdj_score = 0
    if not np.isnan(j[-1]) and not np.isnan(k[-1]) and not np.isnan(d[-1]):
        if j[-1] < 0:
            kdj_score = 13
        elif j[-1] < 20 and k[-1] > d[-1]:
            kdj_score = 10
        elif j[-1] < 20:
            kdj_score = 7
        elif j[-1] > 100:
            kdj_score = -8
        elif j[-1] > 80 and k[-1] < d[-1]:
            kdj_score = -5
        elif j[-1] > 80:
            kdj_score = -3
        else:
            kdj_score = 2
    score += kdj_score
    details["KDJ"] = {"score": kdj_score, "desc": f"K={k[-1]:.1f} D={d[-1]:.1f} J={j[-1]:.1f}"}

    # RSI (12 pts)
    rsi_score = 0
    if not np.isnan(rsi_vals[-1]):
        r = rsi_vals[-1]
        if r < 30:
            rsi_score = 12
        elif r < 40:
            rsi_score = 8
        elif 40 <= r <= 60:
            rsi_score = 3
        elif 60 < r <= 70:
            rsi_score = 0
        elif 70 < r <= 80:
            rsi_score = -4
        else:
            rsi_score = -8
    score += rsi_score
    details["RSI"] = {"score": rsi_score, "desc": f"RSI(14)={rsi_vals[-1]:.1f}"}

    return max(0, min(25, score)), details


def score_volume_price(df: dict) -> tuple:
    close = np.array(df["close"], dtype=float)
    volume = np.array(df["volume"], dtype=float)
    high = np.array(df["high"], dtype=float)
    low = np.array(df["low"], dtype=float)
    n = len(close)
    if n < 20:
        return 0, {}

    score = 13
    details = {}

    # Volume pattern (13 pts)
    vol_score = 0
    avg_vol_5 = 0.0
    avg_vol_20 = 0.0
    if n >= 10:
        avg_vol_5 = np.mean(volume[-5:])
        avg_vol_20 = np.mean(volume[-20:]) if n >= 20 else avg_vol_5
        price_change_5 = (close[-1] - close[-5]) / close[-5] * 100

        if avg_vol_5 < avg_vol_20 * 0.7 and price_change_5 > 2:
            vol_score = 13
        elif price_change_5 > 3 and volume[-1] > avg_vol_20 * 1.5:
            vol_score = 10
        elif avg_vol_5 > avg_vol_20 * 1.5 and price_change_5 < -1:
            vol_score = -6
        elif avg_vol_5 > avg_vol_20 * 1.8 and abs(price_change_5) < 1:
            vol_score = -4
        elif avg_vol_5 < avg_vol_20 * 0.8 and price_change_5 < -2:
            vol_score = -3
        elif avg_vol_5 > avg_vol_20 * 1.5:
            vol_score = 3
        elif avg_vol_5 < avg_vol_20 * 0.8:
            vol_score = 2
        else:
            vol_score = 0
    score += vol_score
    details["成交量形态"] = {"score": vol_score, "desc": f"5日均量={avg_vol_5:.0f} 20日均量={avg_vol_20:.0f}"}

    # OBV (12 pts)
    obv_score = 0
    obv_slope = 0.0
    obv_vals = OBV(close, volume)
    if n >= 10:
        obv_slope = (obv_vals[-1] - obv_vals[-5]) / obv_vals[-5] * 100 if obv_vals[-5] != 0 else 0
        price_dir = close[-1] - close[-5]
        if obv_slope > 2 and price_dir > 0:
            obv_score = 12
        elif obv_slope > 1 and price_dir > 0:
            obv_score = 8
        elif obv_slope > 2 and price_dir < 0:
            obv_score = 6
        elif obv_slope < -2 and price_dir > 0:
            obv_score = -6
        elif obv_slope < -1 and price_dir < 0:
            obv_score = -3
        else:
            obv_score = 1
    score += obv_score
    details["OBV资金流向"] = {"score": obv_score, "desc": f"OBV斜率={obv_slope:.2f}%"}

    return max(0, min(25, score)), details


def score_position_movement(df: dict) -> tuple:
    close = np.array(df["close"], dtype=float)
    high = np.array(df["high"], dtype=float)
    low = np.array(df["low"], dtype=float)
    n = len(close)
    if n < 20:
        return 0, {}

    score = 10
    details = {}

    # Bollinger position (10 pts)
    boll_score = 0
    pos = 0.5
    upper, middle, lower = BOLL(close)
    if not np.isnan(upper[-1]):
        pos = (close[-1] - lower[-1]) / (upper[-1] - lower[-1]) if upper[-1] != lower[-1] else 0.5
        if pos < 0.1:
            boll_score = 10
        elif pos < 0.25:
            boll_score = 7
        elif 0.25 <= pos <= 0.75:
            boll_score = 2
        elif pos > 0.9:
            boll_score = -6
        elif pos > 0.75:
            boll_score = -3
        else:
            boll_score = 0
    score += boll_score
    details["布林带位置"] = {"score": boll_score, "desc": f"位置={pos:.1%} 上轨={upper[-1]:.2f} 中轨={middle[-1]:.2f} 下轨={lower[-1]:.2f}"}

    # Support/Resistance (10 pts)
    sr_score = 0
    supports, resistances = detect_support_resistance(high, low, close)
    if supports:
        nearest_support = max(supports)
        dist_to_support = (close[-1] - nearest_support) / close[-1] * 100
        if dist_to_support < 2:
            sr_score += 5
        elif dist_to_support < 5:
            sr_score += 3
    if resistances:
        nearest_resistance = min(resistances)
        dist_to_resistance = (resistances[0] - close[-1]) / close[-1] * 100
        if dist_to_resistance < 2:
            sr_score -= 3
    if not supports and not resistances:
        sr_score = 0
    score += sr_score
    supports_str = [float(s) for s in supports]
    resistances_str = [float(r) for r in resistances]
    details["支撑阻力"] = {"score": sr_score, "desc": f"支撑={supports_str} 阻力={resistances_str}"}

    return max(0, min(20, score)), details


def comprehensive_score(df: dict) -> dict:
    trend_s, trend_d = score_trend(df)
    oos_s, oos_d = score_overbought_oversold(df)
    vp_s, vp_d = score_volume_price(df)
    pm_s, pm_d = score_position_movement(df)

    total = trend_s + oos_s + vp_s + pm_s

    if total >= 75:
        signal = "strong_buy"
        signal_cn = "强买入"
    elif total >= 60:
        signal = "weak_buy"
        signal_cn = "弱买入"
    elif total >= 40:
        signal = "neutral"
        signal_cn = "观望"
    elif total >= 25:
        signal = "weak_sell"
        signal_cn = "弱卖出"
    else:
        signal = "strong_sell"
        signal_cn = "强卖出"

    return {
        "总分": total,
        "信号": signal,
        "信号中文": signal_cn,
        "趋势": {"score": trend_s, "max": 30, "details": trend_d},
        "超买超卖": {"score": oos_s, "max": 25, "details": oos_d},
        "量价分析": {"score": vp_s, "max": 25, "details": vp_d},
        "运动与位置": {"score": pm_s, "max": 20, "details": pm_d},
    }
