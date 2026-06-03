import numpy as np
from .indicators import MA as _ma, EMA as _ema, MACD as _macd, RSI as _rsi, BOLL as _boll


def multi_factor_resonance(close, high, low, open_arr, i, position, **params):
    """多因子共振策略：趋势+动量+成交量"""
    if i < 60 or position != 0:
        return 0
    
    ma_short = params.get("ma_short", 5)
    ma_mid = params.get("ma_mid", 20)
    ma_long = params.get("ma_long", 60)
    volume_ratio = params.get("volume_ratio", 1.5)
    
    close_slice = close[:i + 1]
    volume_slice = params.get("volume", np.ones_like(close_slice))
    
    ma5 = _ma(close_slice, ma_short)
    ma20 = _ma(close_slice, ma_mid)
    ma60 = _ma(close_slice, ma_long)
    
    if np.isnan(ma5[i]) or np.isnan(ma20[i]) or np.isnan(ma60[i]):
        return 0
    
    trend_up = ma5[i] > ma20[i] and ma20[i] > ma60[i]
    ma5_cross_ma20 = ma5[i - 1] <= ma20[i - 1] and ma5[i] > ma20[i]
    
    if i >= 10:
        avg_vol = np.mean(volume_slice[i - 10:i])
        vol_confirm = volume_slice[i] > avg_vol * volume_ratio
    else:
        vol_confirm = False
    
    momentum = (close[i] - close[i - 5]) / close[i - 5] > 0.02
    
    if trend_up and ma5_cross_ma20 and vol_confirm and momentum:
        return 1
    return 0


def multi_factor_resonance_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    if position <= 0:
        return 0
    ma_short = params.get("ma_short", 5)
    ma_mid = params.get("ma_mid", 20)
    hold_days = params.get("hold_days", 10)
    
    ma5 = _ma(close[:i + 1], ma_short)
    ma20 = _ma(close[:i + 1], ma_mid)
    
    if i >= entry_bar + hold_days:
        return -1
    if not np.isnan(ma5[i]) and not np.isnan(ma20[i]) and ma5[i] < ma20[i]:
        return -1
    return 0


def macd_rsi_volume(close, high, low, open_arr, i, position, **params):
    """MACD金叉+RSI超卖+成交量放大"""
    if i < 30 or position != 0:
        return 0
    
    rsi_period = params.get("rsi_period", 14)
    rsi_low = params.get("rsi_low", 30)
    volume_ratio = params.get("volume_ratio", 1.3)
    
    close_slice = close[:i + 1]
    volume_slice = params.get("volume", np.ones_like(close_slice))
    
    dif, dea, hist = _macd(close_slice)
    rsi = _rsi(close_slice, rsi_period)
    
    if np.isnan(dif[i]) or np.isnan(dea[i]) or np.isnan(rsi[i]):
        return 0
    
    macd_cross = dif[i - 1] <= dea[i - 1] and dif[i] > dea[i]
    rsi_oversold = rsi[i] < rsi_low
    
    if i >= 10:
        avg_vol = np.mean(volume_slice[i - 10:i])
        vol_confirm = volume_slice[i] > avg_vol * volume_ratio
    else:
        vol_confirm = False
    
    if macd_cross and rsi_oversold and vol_confirm:
        return 1
    return 0


def macd_rsi_volume_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    if position <= 0:
        return 0
    rsi_high = params.get("rsi_high", 70)
    hold_days = params.get("hold_days", 8)
    
    rsi = _rsi(close[:i + 1], params.get("rsi_period", 14))
    
    if i >= entry_bar + hold_days:
        return -1
    if not np.isnan(rsi[i]) and rsi[i] > rsi_high:
        return -1
    return 0


def boll_rsi_mean_reversion(close, high, low, open_arr, i, position, **params):
    """布林带RSI均值回归策略：跌破下轨+RSI超卖买入"""
    if i < 30 or position != 0:
        return 0
    
    boll_period = params.get("boll_period", 20)
    boll_std = params.get("boll_std", 2.0)
    rsi_period = params.get("rsi_period", 14)
    rsi_low = params.get("rsi_low", 25)
    
    close_slice = close[:i + 1]
    upper, middle, lower = _boll(close_slice, boll_period, boll_std)
    rsi = _rsi(close_slice, rsi_period)
    
    if np.isnan(lower[i]) or np.isnan(rsi[i]):
        return 0
    
    touch_lower = close[i] <= lower[i]
    rsi_oversold = rsi[i] < rsi_low
    prev_above_lower = close[i - 1] > lower[i - 1]
    
    if touch_lower and rsi_oversold and prev_above_lower:
        return 1
    return 0


def boll_rsi_mean_reversion_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    if position <= 0:
        return 0
    boll_period = params.get("boll_period", 20)
    boll_std = params.get("boll_std", 2.0)
    rsi_high = params.get("rsi_high", 75)
    hold_days = params.get("hold_days", 6)
    
    close_slice = close[:i + 1]
    upper, middle, _ = _boll(close_slice, boll_period, boll_std)
    rsi = _rsi(close_slice, params.get("rsi_period", 14))
    
    if i >= entry_bar + hold_days:
        return -1
    if not np.isnan(upper[i]) and close[i] >= upper[i]:
        return -1
    if not np.isnan(rsi[i]) and rsi[i] > rsi_high:
        return -1
    return 0


def turtle_trading(close, high, low, open_arr, i, position, **params):
    """海龟交易法则：突破20日高点买入，跌破10日低点卖出"""
    if i < 20 or position != 0:
        return 0
    
    entry_period = params.get("entry_period", 20)
    
    high_slice = high[:i + 1]
    entry_high = np.max(high_slice[i - entry_period + 1:i])
    
    if close[i] > entry_high and high[i] > entry_high:
        return 1
    return 0


def turtle_trading_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    if position <= 0:
        return 0
    exit_period = params.get("exit_period", 10)
    
    low_slice = low[:i + 1]
    exit_low = np.min(low_slice[i - exit_period + 1:i])
    
    if close[i] < exit_low and low[i] < exit_low:
        return -1
    return 0


def rsi_reversal_volume(close, high, low, open_arr, i, position, **params):
    """RSI超卖反转+成交量确认策略"""
    if i < 20 or position != 0:
        return 0
    
    rsi_period = params.get("rsi_period", 14)
    rsi_low = params.get("rsi_low", 20)
    volume_ratio = params.get("volume_ratio", 1.8)
    
    close_slice = close[:i + 1]
    volume_slice = params.get("volume", np.ones_like(close_slice))
    
    rsi = _rsi(close_slice, rsi_period)
    
    if np.isnan(rsi[i]) or np.isnan(rsi[i - 1]):
        return 0
    
    rsi_enter = rsi[i - 1] < rsi_low and rsi[i] > rsi[i - 1]
    
    if i >= 5:
        avg_vol = np.mean(volume_slice[i - 5:i])
        vol_spike = volume_slice[i] > avg_vol * volume_ratio
    else:
        vol_spike = False
    
    price_stop_falling = close[i] > close[i - 1]
    
    if rsi_enter and vol_spike and price_stop_falling:
        return 1
    return 0


def rsi_reversal_volume_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    if position <= 0:
        return 0
    rsi_high = params.get("rsi_high", 70)
    take_profit = params.get("take_profit_pct", 0.06)
    hold_days = params.get("hold_days", 5)
    
    rsi = _rsi(close[:i + 1], params.get("rsi_period", 14))
    
    if i >= entry_bar + hold_days:
        return -1
    if (close[i] - entry_price) / entry_price >= take_profit:
        return -1
    if not np.isnan(rsi[i]) and rsi[i] > rsi_high:
        return -1
    return 0


def ma_crossover(close, high, low, open_arr, i, position, **params):
    if i < 20 or position != 0:
        return 0
    ma5 = np.mean(close[i - 4:i + 1])
    ma20 = np.mean(close[i - 19:i + 1])
    ma5_prev = np.mean(close[i - 5:i])
    ma20_prev = np.mean(close[i - 20:i])
    if ma5_prev <= ma20_prev and ma5 > ma20:
        return 1
    return 0


def ma_crossover_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    if position > 0 and i >= entry_bar + 5:
        ma5 = np.mean(close[i - 4:i + 1])
        ma20 = np.mean(close[i - 19:i + 1])
        if ma5 < ma20:
            return -1
    return 0


def dual_thrust(close, high, low, open_arr, i, position, **params):
    if i < 5 or position != 0:
        return 0
    prev_high = high[i - 4:i + 1]
    prev_low = low[i - 4:i + 1]
    prev_close = close[i - 4:i + 1]
    hh = np.max(prev_high)
    lc = np.min(prev_close)
    hc = np.max(prev_close)
    ll = np.min(prev_low)
    r1 = hh - lc
    r2 = hc - ll
    r = max(r1, r2)
    if r == 0:
        return 0
    k = params.get("k", 0.5)
    upper = close[i - 1] + k * r
    lower = close[i - 1] - (1 - k) * r
    if close[i] > upper:
        return 1
    elif close[i] < lower:
        return -1
    return 0


def dual_thrust_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    lookback = params.get("dual_thrust_hold", 3)
    if position != 0 and i >= entry_bar + lookback:
        return -position
    if position > 0:
        stop_loss = entry_price * (1 - params.get("stop_loss_pct", 0.03))
        if close[i] < stop_loss:
            return -1
        take_profit = entry_price * (1 + params.get("take_profit_pct", 0.05))
        if close[i] > take_profit:
            return -1
    return 0


_ha_cache = {}

def _get_ha_arrays(close, high, low):
    cache_key = id(close)
    if cache_key in _ha_cache:
        return _ha_cache[cache_key]
    n = len(close)
    ha_open = np.full(n, np.nan)
    ha_close = np.full(n, np.nan)
    ha_open[0] = close[0]
    ha_close[0] = (close[0] + close[0] + high[0] + low[0]) / 4
    for j in range(1, n):
        ha_open[j] = (ha_open[j - 1] + ha_close[j - 1]) / 2
        ha_close[j] = (ha_open[j] + close[j] + high[j] + low[j]) / 4
    _ha_cache.clear()
    _ha_cache[cache_key] = (ha_open, ha_close)
    return ha_open, ha_close


def heikin_ashi(close, high, low, open_arr, i, position, **params):
    if i < 2:
        return 0

    ha_open, ha_close = _get_ha_arrays(close, high, low)

    ha_high = max(ha_open[i], ha_close[i], high[i])
    ha_low = min(ha_open[i], ha_close[i], low[i])

    body = abs(ha_open[i] - ha_close[i])
    body_prev = abs(ha_open[i - 1] - ha_close[i - 1])

    is_green = ha_close[i] > ha_open[i]
    is_red = ha_open[i] > ha_close[i]
    is_marubozu_green = is_green and ha_open[i] == ha_low
    is_marubozu_red = is_red and ha_open[i] == ha_high
    body_growing = body > body_prev

    if is_marubozu_green and body_growing and ha_open[i - 1] > ha_close[i - 1]:
        return 1
    if position < 0:
        if is_marubozu_red and ha_open[i - 1] < ha_close[i - 1]:
            return 1
    if is_marubozu_red and body_growing and ha_open[i - 1] < ha_close[i - 1]:
        return -1
    if position > 0:
        if is_marubozu_green and ha_open[i - 1] > ha_close[i - 1]:
            return -1
    return 0


def heikin_ashi_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    return 0


_sar_cache = {}

def _get_sar_arrays(close, high, low):
    cache_key = id(close)
    if cache_key in _sar_cache:
        return _sar_cache[cache_key]
    n = len(close)
    sar = np.zeros(n)
    trend = np.zeros(n, dtype=int)
    ep = np.zeros(n)
    af = np.zeros(n)

    initial_af = 0.02
    step_af = 0.02
    end_af = 0.2

    if n < 2:
        _sar_cache.clear()
        _sar_cache[cache_key] = (sar, trend)
        return sar, trend

    trend[1] = 1 if close[1] > close[0] else -1
    sar[1] = low[0] if trend[1] > 0 else high[0]
    ep[1] = high[1] if trend[1] > 0 else low[1]
    af[1] = initial_af

    for j in range(2, n):
        temp = sar[j - 1] + af[j - 1] * (ep[j - 1] - sar[j - 1])
        if trend[j - 1] < 0:
            sar[j] = max(temp, high[j - 1], high[j - 2])
            trend[j] = 1 if sar[j] < high[j] else trend[j - 1] - 1
        else:
            sar[j] = min(temp, low[j - 1], low[j - 2])
            trend[j] = -1 if sar[j] > low[j] else trend[j - 1] + 1

        if trend[j] < 0:
            ep[j] = min(low[j], ep[j - 1]) if trend[j] != -1 else low[j]
        else:
            ep[j] = max(high[j], ep[j - 1]) if trend[j] != 1 else high[j]

        if abs(trend[j]) == 1:
            af[j] = initial_af
        else:
            if ep[j] == ep[j - 1]:
                af[j] = af[j - 1]
            else:
                af[j] = min(end_af, af[j - 1] + step_af)

    _sar_cache.clear()
    _sar_cache[cache_key] = (sar, trend)
    return sar, trend


def parabolic_sar(close, high, low, open_arr, i, position, **params):
    if i < 3:
        return 0

    sar_vals, trend = _get_sar_arrays(close, high, low)

    if trend[i] > 0 and sar_vals[i] < close[i]:
        if position <= 0:
            return 1
    elif trend[i] < 0 and sar_vals[i] > close[i]:
        if position >= 0:
            return -1
    return 0


def parabolic_sar_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    return 0


def ema_crossover(close, high, low, open_arr, i, position, **params):
    if i < 2 or position != 0:
        return 0

    fast = params.get("ema_fast", 12)
    slow = params.get("ema_slow", 26)

    ema_fast = _ema(close[:i + 1], fast)
    ema_slow = _ema(close[:i + 1], slow)

    if np.isnan(ema_fast[i]) or np.isnan(ema_slow[i]) or np.isnan(ema_fast[i - 1]) or np.isnan(ema_slow[i - 1]):
        return 0

    if ema_fast[i - 1] <= ema_slow[i - 1] and ema_fast[i] > ema_slow[i]:
        return 1
    if ema_fast[i - 1] >= ema_slow[i - 1] and ema_fast[i] < ema_slow[i]:
        return -1
    return 0


def ema_crossover_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    return 0


def shooting_star(close, high, low, open_arr, i, position, **params):
    if i < 3:
        return 0

    body = abs(open_arr[i] - close[i])
    upper_wick = high[i] - max(open_arr[i], close[i])
    lower_wick = min(open_arr[i], close[i]) - low[i]

    body_size_pct = params.get("body_size", 0.5)
    wick_multiple = params.get("wick_multiple", 2.0)

    avg_change = np.mean(np.abs(np.diff(close[max(0, i - 20):i + 1]))) if i > 20 else close[i] * 0.01

    if position <= 0:
        is_red = open_arr[i] > close[i]
        has_small_body = body < avg_change * body_size_pct
        has_long_upper = upper_wick >= wick_multiple * body and body > 0
        has_small_lower = lower_wick < body * 0.3
        uptrend = i >= 2 and close[i] >= close[i - 1] and close[i - 1] >= close[i - 2]

        if is_red and has_small_body and has_long_upper and has_small_lower and uptrend:
            return -1

    if position >= 0:
        is_green = close[i] > open_arr[i]
        has_small_body = body < avg_change * body_size_pct
        has_long_lower = lower_wick >= wick_multiple * body and body > 0
        has_small_upper = upper_wick < body * 0.3
        downtrend = i >= 2 and close[i] <= close[i - 1] and close[i - 1] <= close[i - 2]

        if is_green and has_small_body and has_long_lower and has_small_upper and downtrend:
            return 1

    return 0


def shooting_star_exit(close, high, low, i, entry_price, position, entry_bar, **params):
    hold = params.get("shooting_hold", 5)
    stop = params.get("shooting_stop", 0.05)
    if position != 0 and i >= entry_bar + hold:
        return -position
    if position != 0 and entry_price > 0:
        pnl = abs((close[i] - entry_price) / entry_price)
        if pnl > stop:
            return -position
    return 0


STRATEGIES = {
    "ma_crossover": {
        "name": "MA5/MA20 金叉",
        "desc": "MA5上穿MA20买入，下穿卖出",
        "signal": ma_crossover,
        "exit": ma_crossover_exit,
        "params": {},
        "default": True,
    },
    "dual_thrust": {
        "name": "Dual Thrust 通道突破",
        "desc": "基于前N日高低收范围设定突破通道",
        "signal": dual_thrust,
        "exit": dual_thrust_exit,
        "params": {"k": 0.5, "dual_thrust_hold": 3, "stop_loss_pct": 0.03, "take_profit_pct": 0.05},
    },
    "heikin_ashi": {
        "name": "Heikin-Ashi 均值K线",
        "desc": "Heikin-Ashi蜡烛图形态识别",
        "signal": heikin_ashi,
        "exit": heikin_ashi_exit,
        "params": {},
    },
    "parabolic_sar": {
        "name": "Parabolic SAR 抛物线",
        "desc": "抛物线指标趋势跟踪",
        "signal": parabolic_sar,
        "exit": parabolic_sar_exit,
        "params": {},
    },
    "ema_crossover": {
        "name": "EMA(12/26) 交叉",
        "desc": "EMA12上穿EMA26做多，下穿做空",
        "signal": ema_crossover,
        "exit": ema_crossover_exit,
        "params": {"ema_fast": 12, "ema_slow": 26},
    },
    "shooting_star": {
        "name": "流星线/锤子线",
        "desc": "K线形态识别: 流星线(做空)/锤子线(做多)",
        "signal": shooting_star,
        "exit": shooting_star_exit,
        "params": {"body_size": 0.5, "wick_multiple": 2.0, "shooting_hold": 5, "shooting_stop": 0.05},
    },
    "multi_factor_resonance": {
        "name": "多因子共振",
        "desc": "趋势(MA5>MA20>MA60)+金叉+放量+动量",
        "signal": multi_factor_resonance,
        "exit": multi_factor_resonance_exit,
        "params": {"ma_short": 5, "ma_mid": 20, "ma_long": 60, "volume_ratio": 1.5, "hold_days": 10},
    },
    "macd_rsi_volume": {
        "name": "MACD+RSI+成交量",
        "desc": "MACD金叉+RSI超卖+成交量放大",
        "signal": macd_rsi_volume,
        "exit": macd_rsi_volume_exit,
        "params": {"rsi_period": 14, "rsi_low": 30, "rsi_high": 70, "volume_ratio": 1.3, "hold_days": 8},
    },
    "boll_rsi_mean_reversion": {
        "name": "布林带RSI均值回归",
        "desc": "跌破下轨+RSI超卖买入，触及上轨/RSI超买卖出",
        "signal": boll_rsi_mean_reversion,
        "exit": boll_rsi_mean_reversion_exit,
        "params": {"boll_period": 20, "boll_std": 2.0, "rsi_period": 14, "rsi_low": 25, "rsi_high": 75, "hold_days": 6},
    },
    "turtle_trading": {
        "name": "海龟交易法则",
        "desc": "经典趋势跟踪：突破20日高买入，跌破10日低卖出",
        "signal": turtle_trading,
        "exit": turtle_trading_exit,
        "params": {"entry_period": 20, "exit_period": 10},
    },
    "rsi_reversal_volume": {
        "name": "RSI反转+成交量",
        "desc": "RSI超卖反转+成交量暴增确认",
        "signal": rsi_reversal_volume,
        "exit": rsi_reversal_volume_exit,
        "params": {"rsi_period": 14, "rsi_low": 20, "rsi_high": 70, "volume_ratio": 1.8, "take_profit_pct": 0.06, "hold_days": 5},
    },
}


def get_strategy(name):
    if name in STRATEGIES:
        return STRATEGIES[name]
    return STRATEGIES["ma_crossover"]