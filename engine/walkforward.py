import itertools
import logging
import numpy as np
from .backtest import run_backtest
from .optimizer import get_param_grid

logger = logging.getLogger(__name__)


def _grid_combos(strategy_name: str, max_combos: int = 100):
    grid = get_param_grid(strategy_name)
    if not grid:
        return [], []
    names = list(grid.keys())
    vals = [grid[n]["values"] for n in names]
    total = 1
    for v in vals:
        total *= len(v)
    combos = list(itertools.product(*vals))
    if total > max_combos:
        import random
        random.seed(42)
        random.shuffle(combos)
        combos = combos[:max_combos]
    return names, combos


def _run_one(close, high, low, open_prices, volume,
             initial_capital, strategy_name, trade_days, params: dict):
    p = dict(params)
    atr_stop = p.pop("atr_stop_mult", 2.0)
    atr_take = p.pop("atr_take_mult", 3.0)
    return run_backtest(
        close=close, high=high, low=low,
        open_prices=open_prices, volume=volume,
        initial_capital=initial_capital,
        atr_stop_mult=atr_stop, atr_take_mult=atr_take,
        trade_days=trade_days,
        strategy_name=strategy_name,
        **p,
    )


def walk_forward(close, high, low, open_prices=None, volume=None,
                 initial_capital: float = 10000,
                 strategy_name: str = "ma_crossover",
                 metric: str = "sharpe_ratio",
                 n_windows: int = 4,
                 train_ratio: float = 0.67) -> dict:
    """N 段滚动验证：每段前 train_ratio 调参，剩余 1-train_ratio 用最优参数评估。"""
    n = len(close)
    if n < 120:
        return {"error": "数据不足，至少需要 120 个交易日"}

    names, combos = _grid_combos(strategy_name, max_combos=60)
    if not combos:
        return {"error": f"策略 {strategy_name} 无优化参数"}

    window_size = n // n_windows
    if window_size < 60:
        n_windows = max(2, n // 60)
        window_size = n // n_windows

    windows_result = []
    is_returns = []
    oos_returns = []
    is_sharpes = []
    oos_sharpes = []
    oos_trade_counts = []

    for w in range(n_windows):
        w_start = w * window_size
        w_end = min(w_start + window_size, n)
        if w_end - w_start < 60:
            continue
        train_len = int((w_end - w_start) * train_ratio)
        test_len = w_end - w_start - train_len
        if train_len < 30 or test_len < 15:
            continue

        train_end = w_start + train_len
        train_close = close[:train_end]
        train_high = high[:train_end]
        train_low = low[:train_end]
        train_open = open_prices[:train_end] if open_prices is not None else None
        train_vol = volume[:train_end] if volume is not None else None

        best_score = -np.inf
        best_params = None
        best_is = None
        for combo in combos:
            params = {names[i]: combo[i] for i in range(len(names))}
            try:
                r = _run_one(train_close, train_high, train_low, train_open, train_vol,
                             initial_capital, strategy_name, train_len, params)
            except Exception as e:
                logger.debug(f"train fail: {e}")
                continue
            if "error" in r:
                continue
            score = r.get(metric, 0)
            if np.isnan(score) or np.isinf(score):
                continue
            if score > best_score:
                best_score = score
                best_params = params
                best_is = r

        if best_params is None:
            continue

        test_end = w_end
        full_close = close[:test_end]
        full_high = high[:test_end]
        full_low = low[:test_end]
        full_open = open_prices[:test_end] if open_prices is not None else None
        full_vol = volume[:test_end] if volume is not None else None
        oos = _run_one(full_close, full_high, full_low, full_open, full_vol,
                       initial_capital, strategy_name, test_len, best_params)
        if "error" in oos:
            continue

        is_returns.append(best_is["total_return"])
        oos_returns.append(oos["total_return"])
        is_sharpes.append(best_is["sharpe_ratio"])
        oos_sharpes.append(oos["sharpe_ratio"])
        oos_trade_counts.append(oos["total_trades"])

        windows_result.append({
            "window": w + 1,
            "train_range": [w_start, train_end],
            "test_range": [train_end, test_end],
            "best_params": best_params,
            "is_return": best_is["total_return"],
            "is_sharpe": best_is["sharpe_ratio"],
            "is_trades": best_is["total_trades"],
            "oos_return": oos["total_return"],
            "oos_sharpe": oos["sharpe_ratio"],
            "oos_win_rate": oos["win_rate"],
            "oos_max_dd": oos["max_drawdown"],
            "oos_trades": oos["total_trades"],
        })

    if not windows_result:
        return {"error": "所有窗口均未产生有效结果"}

    return {
        "strategy": strategy_name,
        "metric": metric,
        "n_windows": len(windows_result),
        "train_ratio": train_ratio,
        "summary": {
            "is_return_avg": round(float(np.mean(is_returns)), 2),
            "oos_return_avg": round(float(np.mean(oos_returns)), 2),
            "is_sharpe_avg": round(float(np.mean(is_sharpes)), 2),
            "oos_sharpe_avg": round(float(np.mean(oos_sharpes)), 2),
            "oos_total_trades": int(np.sum(oos_trade_counts)),
            "degradation_pct": round(float(np.mean(is_returns) - np.mean(oos_returns)), 2),
        },
        "windows": windows_result,
    }
