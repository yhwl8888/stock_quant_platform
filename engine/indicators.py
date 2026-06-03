import numpy as np
import pandas as pd


def MA(close: np.ndarray, period: int) -> np.ndarray:
    result = np.full_like(close, np.nan)
    if len(close) < period:
        return result
    for i in range(period - 1, len(close)):
        result[i] = np.mean(close[i - period + 1:i + 1])
    return result


def EMA(close: np.ndarray, period: int) -> np.ndarray:
    result = np.full_like(close, np.nan)
    if len(close) < 1:
        return result
    alpha = 2 / (period + 1)
    result[0] = close[0]
    for i in range(1, len(close)):
        result[i] = close[i] * alpha + result[i - 1] * (1 - alpha)
    return result


def MACD(close: np.ndarray, fast: int = 12, slow: int = 26, signal_period: int = 9):
    ema_fast = EMA(close, fast)
    ema_slow = EMA(close, slow)
    dif = ema_fast - ema_slow
    full_dea = np.full_like(dif, np.nan)
    valid = ~np.isnan(dif)
    if np.sum(valid) > signal_period:
        dea_vals = EMA(dif[valid], signal_period)
        full_dea[valid] = dea_vals
    macd_hist = 2 * (dif - full_dea)
    return dif, full_dea, macd_hist


def RSI(close: np.ndarray, period: int = 14) -> np.ndarray:
    result = np.full_like(close, np.nan)
    if len(close) < period + 1:
        return result
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
    result[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, len(close)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
        result[i] = 100 - (100 / (1 + rs))
    return result


def KDJ(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 9):
    n = len(close)
    k_vals = np.full(n, np.nan)
    d_vals = np.full(n, np.nan)
    j_vals = np.full(n, np.nan)
    if n < period:
        return k_vals, d_vals, j_vals
    k = 50.0
    d = 50.0
    for i in range(n):
        start = max(0, i - period + 1)
        hh = np.max(high[start:i + 1])
        ll = np.min(low[start:i + 1])
        denom = hh - ll
        rsv = (close[i] - ll) / denom * 100 if denom != 0 else 50
        if i >= period - 1:
            k = 2 / 3 * k + 1 / 3 * rsv
            d = 2 / 3 * d + 1 / 3 * k
            j = 3 * k - 2 * d
            k_vals[i] = k
            d_vals[i] = d
            j_vals[i] = j
    return k_vals, d_vals, j_vals


def BOLL(close: np.ndarray, period: int = 20, std_mult: float = 2.0):
    middle = MA(close, period)
    upper = np.full_like(middle, np.nan)
    lower = np.full_like(middle, np.nan)
    for i in range(period - 1, len(close)):
        window = close[i - period + 1:i + 1]
        std = np.std(window)
        upper[i] = middle[i] + std_mult * std
        lower[i] = middle[i] - std_mult * std
    return upper, middle, lower


def ATR(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    result = np.full_like(close, np.nan)
    if len(close) < period + 1:
        return result
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    result[period - 1] = np.mean(tr[:period])
    for i in range(period, len(close)):
        result[i] = (result[i - 1] * (period - 1) + tr[i]) / period
    return result


def OBV(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    obv = np.zeros(len(close))
    obv[0] = 0
    for i in range(1, len(close)):
        if close[i] > close[i - 1]:
            obv[i] = obv[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            obv[i] = obv[i - 1] - volume[i]
        else:
            obv[i] = obv[i - 1]
    return obv


def detect_support_resistance(high: np.ndarray, low: np.ndarray, close: np.ndarray, lookback: int = 60):
    n = len(close)
    if n < lookback:
        start = 0
    else:
        start = n - lookback
    prices = np.concatenate([high[start:], low[start:], close[start:]])
    hist, edges = np.histogram(prices, bins=30)
    peaks = []
    for i in range(1, len(hist) - 1):
        if hist[i] > hist[i - 1] and hist[i] > hist[i + 1] and hist[i] > 1:
            level = (edges[i] + edges[i + 1]) / 2
            peaks.append(round(level, 2))
    peaks = sorted(set(peaks))
    current = close[-1]
    support = [p for p in peaks if p < current][-3:] if [p for p in peaks if p < current] else []
    resistance = [p for p in peaks if p > current][:3] if [p for p in peaks if p > current] else []
    return support, resistance
