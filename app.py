from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import json
import os
import time
from functools import lru_cache

from data.fetcher import fetch_realtime_quote, fetch_kline, search_stocks
from engine.indicators import MA, MACD, RSI, KDJ, BOLL, OBV, ATR, detect_support_resistance
from engine.scoring import comprehensive_score
from engine.backtest import run_backtest
from engine.strategies import STRATEGIES
from engine.optimizer import optimize, get_param_grid

app = Flask(__name__)
CORS(app)

# 简单 TTL 缓存：只缓存成功结果，失败不缓存
_kline_cache = {}
_CACHE_TTL = 300  # 5分钟

def get_kline_cached(code: str, days: int):
    cache_key = f"{code}:{days}"
    now = time.time()
    if cache_key in _kline_cache:
        cached_time, cached_data = _kline_cache[cache_key]
        if now - cached_time < _CACHE_TTL and cached_data:
            return cached_data
    result = fetch_kline(code, days)
    if result:  # 只缓存成功结果
        _kline_cache[cache_key] = (now, result)
    return result

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/search")
def search():
    kw = request.args.get("q", "")
    if not kw:
        return jsonify({"data": []})
    results = search_stocks(kw)
    return jsonify({"data": results})

@app.route("/api/quote/<code>")
def quote(code: str):
    data = fetch_realtime_quote(code)
    if data:
        return jsonify(data)
    return jsonify({"error": "无法获取行情"}), 404

@app.route("/api/kline/<code>")
def kline(code: str):
    days = request.args.get("days", 250, type=int)
    data = get_kline_cached(code, days)
    if data:
        return jsonify({"data": data})
    return jsonify({"data": [], "error": "无法获取K线数据"})

@app.route("/api/indicators/<code>")
def indicators(code: str):
    days = request.args.get("days", 250, type=int)
    kline_data = get_kline_cached(code, days)
    if not kline_data:
        return jsonify({"error": "无法获取K线数据"}), 404

    close = [d["close"] for d in kline_data]
    high = [d["high"] for d in kline_data]
    low = [d["low"] for d in kline_data]
    volume = [d["volume"] for d in kline_data]

    import numpy as np
    close_arr = np.array(close, dtype=float)
    high_arr = np.array(high, dtype=float)
    low_arr = np.array(low, dtype=float)
    vol_arr = np.array(volume, dtype=float)

    ma5 = MA(close_arr, 5)
    ma10 = MA(close_arr, 10)
    ma20 = MA(close_arr, 20)
    ma60 = MA(close_arr, 60)
    dif, dea, macd_hist = MACD(close_arr)
    rsi_vals = RSI(close_arr)
    k, d, j = KDJ(high_arr, low_arr, close_arr)
    upper, middle, lower = BOLL(close_arr)
    atr_vals = ATR(high_arr, low_arr, close_arr)
    obv_vals = OBV(close_arr, vol_arr)
    supports, resistances = detect_support_resistance(high_arr, low_arr, close_arr)

    def _clean_series(arr):
        import numpy as np
        if arr is None:
            return []
        return [None if np.isnan(v) else round(float(v), 4) for v in arr]

    return jsonify({
        "ma5": _clean_series(ma5),
        "ma10": _clean_series(ma10),
        "ma20": _clean_series(ma20),
        "ma60": _clean_series(ma60),
        "macd_dif": _clean_series(dif),
        "macd_dea": _clean_series(dea),
        "macd_hist": _clean_series(macd_hist),
        "rsi": _clean_series(rsi_vals),
        "kdj_k": _clean_series(k),
        "kdj_d": _clean_series(d),
        "kdj_j": _clean_series(j),
        "boll_upper": _clean_series(upper),
        "boll_middle": _clean_series(middle),
        "boll_lower": _clean_series(lower),
        "atr": _clean_series(atr_vals),
        "obv": _clean_series(obv_vals),
        "support": supports,
        "resistance": resistances,
    })

@app.route("/api/analysis/<code>")
def analysis(code: str):
    days = request.args.get("days", 250, type=int)
    kline_data = get_kline_cached(code, days)
    if not kline_data:
        return jsonify({"error": "无法获取K线数据"}), 404

    df = {
        "close": [d["close"] for d in kline_data],
        "high": [d["high"] for d in kline_data],
        "low": [d["low"] for d in kline_data],
        "volume": [d["volume"] for d in kline_data],
        "open": [d["open"] for d in kline_data],
    }

    score_result = comprehensive_score(df)
    return jsonify(score_result)

@app.route("/api/backtest", methods=["POST"])
def backtest():
    body = request.get_json()
    code = body.get("code", "")
    days = int(body.get("days", 250))
    initial_capital = float(body.get("capital", 10000))
    atr_stop = float(body.get("atr_stop", 2.0))
    atr_take = float(body.get("atr_take", 3.0))
    trade_days = int(body.get("trade_days", 60))
    strategy = body.get("strategy", "ma_crossover")

    kline_data = get_kline_cached(code, days)
    if not kline_data:
        return jsonify({"error": "无法获取K线数据"}), 404

    close = [d["close"] for d in kline_data]
    high = [d["high"] for d in kline_data]
    low = [d["low"] for d in kline_data]
    open_p = [d["open"] for d in kline_data]
    volume = [d["volume"] for d in kline_data]

    result = run_backtest(
        close=close,
        high=high,
        low=low,
        open=open_p,
        volume=volume,
        initial_capital=initial_capital,
        atr_stop_mult=atr_stop,
        atr_take_mult=atr_take,
        trade_days=trade_days,
        strategy_name=strategy,
    )
    return jsonify(result)


@app.route("/api/optimize", methods=["POST"])
def optimize_endpoint():
    body = request.get_json()
    code = body.get("code", "")
    days = int(body.get("days", 250))
    initial_capital = float(body.get("capital", 10000))
    trade_days = int(body.get("trade_days", 60))
    strategy = body.get("strategy", "ma_crossover")
    metric = body.get("metric", "sharpe_ratio")

    kline_data = get_kline_cached(code, days)
    if not kline_data:
        return jsonify({"error": "无法获取K线数据"}), 404

    close = [d["close"] for d in kline_data]
    high = [d["high"] for d in kline_data]
    low = [d["low"] for d in kline_data]
    open_p = [d["open"] for d in kline_data]
    volume = [d["volume"] for d in kline_data]

    result = optimize(
        close=close,
        high=high,
        low=low,
        open=open_p,
        volume=volume,
        initial_capital=initial_capital,
        strategy_name=strategy,
        trade_days=trade_days,
        metric=metric,
    )
    return jsonify(result)


@app.route("/api/strategies")
def list_strategies():
    data = {k: {"name": v["name"], "desc": v["desc"], "params": v["params"]} for k, v in STRATEGIES.items()}
    return jsonify(data)


@app.route("/api/strategies/<name>/params")
def strategy_params(name: str):
    grid = get_param_grid(name)
    return jsonify(grid)


@app.route("/api/support-resistance/<code>")
def support_resistance(code: str):
    days = request.args.get("days", 250, type=int)
    kline_data = get_kline_cached(code, days)
    if not kline_data:
        return jsonify({"error": "无法获取K线数据"}), 404

    import numpy as np
    high = np.array([d["high"] for d in kline_data], dtype=float)
    low = np.array([d["low"] for d in kline_data], dtype=float)
    close = np.array([d["close"] for d in kline_data], dtype=float)

    supports, resistances = detect_support_resistance(high, low, close)
    return jsonify({
        "support": supports,
        "resistance": resistances,
        "current_price": round(float(close[-1]), 2),
    })

port = int(os.environ.get("PORT", 8000))
try:
    from waitress import serve
    serve(app, host="0.0.0.0", port=port)
except ImportError:
    app.run(host="0.0.0.0", port=port, debug=False)
