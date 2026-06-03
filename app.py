from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import os
import re
import time
import threading
import numpy as np
from data.fetcher import fetch_realtime_quote, fetch_kline, search_stocks
from engine.indicators import MA, MACD, RSI, KDJ, BOLL, OBV, ATR, detect_support_resistance
from engine.scoring import comprehensive_score
from engine.backtest import run_backtest
from engine.strategies import STRATEGIES
from engine.optimizer import optimize, get_param_grid
from engine.walkforward import walk_forward
from engine.scanner import scan_pool, PRESET_POOLS, DYNAMIC_POOL_SLUGS, _gen_dynamic_codes, get_preset_pools

app = Flask(__name__)
CORS(app)

_kline_cache = {}
_CACHE_TTL = 300
_CACHE_MAX_SIZE = 100
_kline_locks = {}
_locks_guard = threading.Lock()

_VALID_CODE_RE = re.compile(r"^(?:sh|sz|bj)?\d{4,6}$", re.IGNORECASE)

def _is_valid_code(code: str) -> bool:
    return bool(code) and bool(_VALID_CODE_RE.match(code.strip()))

def get_kline_cached(code: str, days: int):
    cache_key = f"{code}:{days}"
    now = time.time()
    if cache_key in _kline_cache:
        cached_time, cached_data = _kline_cache[cache_key]
        if now - cached_time < _CACHE_TTL and cached_data:
            return cached_data

    with _locks_guard:
        lock = _kline_locks.setdefault(cache_key, threading.Lock())

    with lock:
        if cache_key in _kline_cache:
            cached_time, cached_data = _kline_cache[cache_key]
            if time.time() - cached_time < _CACHE_TTL and cached_data:
                return cached_data
        result = fetch_kline(code, days)
        if result:
            if len(_kline_cache) >= _CACHE_MAX_SIZE:
                oldest_key = min(_kline_cache, key=lambda k: _kline_cache[k][0])
                del _kline_cache[oldest_key]
            _kline_cache[cache_key] = (time.time(), result)
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
    if not _is_valid_code(code):
        return jsonify({"data": [], "error": "非法股票代码"}), 400
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
        open_prices=open_p,
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
    oos_ratio = float(body.get("oos_ratio", 0.2))

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
        open_prices=open_p,
        volume=volume,
        initial_capital=initial_capital,
        strategy_name=strategy,
        trade_days=trade_days,
        metric=metric,
        oos_ratio=oos_ratio,
    )
    return jsonify(result)


@app.route("/api/strategies")
def list_strategies():
    data = {k: {"name": v["name"], "desc": v["desc"], "params": v["params"]} for k, v in STRATEGIES.items()}
    return jsonify(data)


@app.route("/api/walkforward", methods=["POST"])
def walkforward_endpoint():
    body = request.get_json()
    code = body.get("code", "")
    if not _is_valid_code(code):
        return jsonify({"error": "非法股票代码"}), 400
    days = int(body.get("days", 500))
    initial_capital = float(body.get("capital", 10000))
    strategy = body.get("strategy", "ma_crossover")
    metric = body.get("metric", "sharpe_ratio")
    n_windows = int(body.get("n_windows", 4))
    train_ratio = float(body.get("train_ratio", 0.67))

    kline_data = get_kline_cached(code, days)
    if not kline_data:
        return jsonify({"error": "无法获取K线数据"}), 404

    close = [d["close"] for d in kline_data]
    high = [d["high"] for d in kline_data]
    low = [d["low"] for d in kline_data]
    open_p = [d["open"] for d in kline_data]
    volume = [d["volume"] for d in kline_data]

    result = walk_forward(
        close=close, high=high, low=low,
        open_prices=open_p, volume=volume,
        initial_capital=initial_capital,
        strategy_name=strategy,
        metric=metric,
        n_windows=n_windows,
        train_ratio=train_ratio,
    )
    return jsonify(result)


@app.route("/api/strategies/<name>/params")
def strategy_params(name: str):
    grid = get_param_grid(name)
    return jsonify(grid)


@app.route("/api/scan/pools")
def list_scan_pools():
    return jsonify(get_preset_pools())


@app.route("/api/scan", methods=["POST"])
def scan_endpoint():
    body = request.get_json()
    strategy = body.get("strategy", "ma_crossover")
    min_score = int(body.get("min_score", 60))
    days = int(body.get("days", 200))
    pool_name = body.get("pool", "")
    codes = body.get("codes") or []
    max_workers = int(body.get("max_workers", 4))

    MAX_CODES = 500
    DYNAMIC_MAP = {
        "all_sh60": ("60", 4500),
        "all_sh68": ("688", 700),
        "all_sz00": ("00", 3000),
        "all_sz30": ("30", 1400),
    }

    if pool_name:
        if pool_name in DYNAMIC_POOL_SLUGS and pool_name in DYNAMIC_MAP:
            prefix, count = DYNAMIC_MAP[pool_name]
            # 动态生成代码 → 但要对超出部分做采样以减少扫描时间
            all_codes = _gen_dynamic_codes(prefix, count)
            if len(all_codes) > MAX_CODES:
                import random
                random.seed(42)
                random.shuffle(all_codes)
                all_codes = all_codes[:MAX_CODES]
            codes = all_codes
        else:
            codes = PRESET_POOLS.get(pool_name, [])

    codes = [c for c in codes if _is_valid_code(c)]
    if not codes:
        return jsonify({"error": "未指定有效股票池"}), 400

    result = scan_pool(codes, strategy_name=strategy,
                       min_total_score=min_score, days=days,
                       max_workers=max_workers)
    return jsonify(result)


@app.route("/api/support-resistance/<code>")
def support_resistance(code: str):
    days = request.args.get("days", 250, type=int)
    kline_data = get_kline_cached(code, days)
    if not kline_data:
        return jsonify({"error": "无法获取K线数据"}), 404

    high = np.array([d["high"] for d in kline_data], dtype=float)
    low = np.array([d["low"] for d in kline_data], dtype=float)
    close = np.array([d["close"] for d in kline_data], dtype=float)

    supports, resistances = detect_support_resistance(high, low, close)
    return jsonify({
        "support": supports,
        "resistance": resistances,
        "current_price": round(float(close[-1]), 2),
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port)
    except ImportError:
        app.run(host="0.0.0.0", port=port, debug=False)
