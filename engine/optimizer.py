import itertools
import logging
import numpy as np
from .backtest import run_backtest

logger = logging.getLogger(__name__)


PARAM_GRID = {
    "ma_crossover": {
        "fast_ma": {"values": [5, 10], "label": "快线周期"},
        "slow_ma": {"values": [20, 60], "label": "慢线周期"},
        "atr_stop_mult": {"values": [1.5, 2.5], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [2.0, 3.5], "label": "ATR止盈倍数"},
    },
    "dual_thrust": {
        "k": {"values": [0.4, 0.6], "label": "K值(通道系数)"},
        "dual_thrust_hold": {"values": [3, 7], "label": "持有时长(天)"},
        "stop_loss_pct": {"values": [0.03, 0.05], "label": "止损比例"},
        "take_profit_pct": {"values": [0.05, 0.08], "label": "止盈比例"},
    },
    "heikin_ashi": {
        "atr_stop_mult": {"values": [1.5, 2.5], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [2.0, 3.5], "label": "ATR止盈倍数"},
    },
    "parabolic_sar": {
        "atr_stop_mult": {"values": [1.5, 2.5], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [2.0, 3.5], "label": "ATR止盈倍数"},
    },
    "ema_crossover": {
        "ema_fast": {"values": [10, 12], "label": "快线EMA周期"},
        "ema_slow": {"values": [26, 50], "label": "慢线EMA周期"},
        "atr_stop_mult": {"values": [1.5, 2.5], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [2.0, 3.5], "label": "ATR止盈倍数"},
    },
    "shooting_star": {
        "body_size": {"values": [0.3, 0.7], "label": "实体比例"},
        "wick_multiple": {"values": [1.5, 3.0], "label": "影线倍数"},
        "shooting_hold": {"values": [3, 7], "label": "持有天数"},
    },
    "multi_factor_resonance": {
        "ma_short": {"values": [5, 8], "label": "短周期MA"},
        "ma_mid": {"values": [20], "label": "中周期MA"},
        "ma_long": {"values": [60], "label": "长周期MA"},
        "volume_ratio": {"values": [1.3, 1.6], "label": "量比"},
        "hold_days": {"values": [7, 15], "label": "持有天数"},
        "atr_stop_mult": {"values": [2.0], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [3.0], "label": "ATR止盈倍数"},
    },
    "macd_rsi_volume": {
        "rsi_period": {"values": [14], "label": "RSI周期"},
        "rsi_low": {"values": [25, 35], "label": "RSI超卖阈值"},
        "rsi_high": {"values": [65, 75], "label": "RSI超买阈值"},
        "volume_ratio": {"values": [1.3, 1.8], "label": "量比"},
        "hold_days": {"values": [6, 12], "label": "持有天数"},
        "atr_stop_mult": {"values": [2.0], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [3.0], "label": "ATR止盈倍数"},
    },
    "boll_rsi_mean_reversion": {
        "boll_period": {"values": [20], "label": "布林带周期"},
        "boll_std": {"values": [1.2, 1.5, 2.0], "label": "布林带标准差"},
        "rsi_period": {"values": [14], "label": "RSI周期"},
        "rsi_low": {"values": [20, 25, 30, 35, 40], "label": "RSI超卖阈值"},
        "rsi_high": {"values": [70, 80], "label": "RSI超买阈值"},
        "hold_days": {"values": [5, 8], "label": "持有天数"},
        "atr_stop_mult": {"values": [1.5, 2.0], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [2.0, 3.0], "label": "ATR止盈倍数"},
    },
    "turtle_trading": {
        "entry_period": {"values": [20, 30], "label": "入场突破周期"},
        "exit_period": {"values": [10, 15], "label": "出场跌破周期"},
        "atr_stop_mult": {"values": [2.0, 3.0], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [3.0, 4.0], "label": "ATR止盈倍数"},
    },
    "rsi_reversal_volume": {
        "rsi_period": {"values": [14], "label": "RSI周期"},
        "rsi_low": {"values": [15, 25], "label": "RSI超卖阈值"},
        "rsi_high": {"values": [65, 75], "label": "RSI超买阈值"},
        "volume_ratio": {"values": [1.5, 2.0], "label": "量比"},
        "take_profit_pct": {"values": [0.05, 0.08], "label": "止盈比例"},
        "hold_days": {"values": [4, 7], "label": "持有天数"},
        "atr_stop_mult": {"values": [1.5, 2.0], "label": "ATR止损倍数"},
        "atr_take_mult": {"values": [2.0, 2.5], "label": "ATR止盈倍数"},
    },
}


def get_param_grid(strategy_name: str):
    return PARAM_GRID.get(strategy_name, {})


def optimize(close, high, low, open_prices=None, volume=None,
             initial_capital=10000,
             strategy_name="ma_crossover",
             trade_days=60,
             metric="sharpe_ratio",
             oos_ratio: float = 0.2) -> dict:
    """80/20 切分：前 80% 做参数搜索（IS），后 20% 用最优参数验证（OOS）。"""
    grid = get_param_grid(strategy_name)
    if not grid:
        return {"error": f"策略 {strategy_name} 无优化参数"}

    n = len(close)
    if n < 80:
        return {"error": "数据不足，至少需要 80 个交易日"}

    oos_ratio = max(0.0, min(0.5, oos_ratio))
    split = int(n * (1 - oos_ratio)) if oos_ratio > 0 else n
    is_close = close[:split]
    is_high = high[:split]
    is_low = low[:split]
    is_open = open_prices[:split] if open_prices is not None else None
    is_vol = volume[:split] if volume is not None else None

    is_trade_days = min(trade_days, max(30, split - 30))

    param_names = list(grid.keys())
    param_values = [grid[p]["values"] for p in param_names]

    best_score = -np.inf
    best_params = None
    best_result = None
    all_results = []

    total = 1
    for v in param_values:
        total *= len(v)

    MAX_COMBINATIONS = 200
    if total > MAX_COMBINATIONS:
        import random
        random.seed(42)
        all_combos = list(itertools.product(*param_values))
        random.shuffle(all_combos)
        combos = all_combos[:MAX_COMBINATIONS]
        total_display = f"{MAX_COMBINATIONS}/{total}"
    else:
        combos = list(itertools.product(*param_values))
        total_display = str(total)

    count = 0
    for combo in combos:
        strategy_params = {param_names[i]: combo[i] for i in range(len(param_names))}

        atr_stop = strategy_params.pop("atr_stop_mult", 2.0)
        atr_take = strategy_params.pop("atr_take_mult", 3.0)

        try:
            result = run_backtest(
                close=is_close, high=is_high, low=is_low,
                open_prices=is_open, volume=is_vol,
                initial_capital=initial_capital,
                atr_stop_mult=atr_stop, atr_take_mult=atr_take,
                trade_days=is_trade_days,
                strategy_name=strategy_name,
                **strategy_params
            )
        except Exception as e:
            logger.warning(f"回测异常 (组合 {count+1}): {type(e).__name__}: {e}")
            count += 1
            continue

        if "error" in result:
            count += 1
            continue

        score = result.get(metric, 0)
        if np.isnan(score) or score == float("inf") or score == float("-inf"):
            score = -999

        entry = {
            "params": {param_names[i]: combo[i] for i in range(len(param_names))},
            "metrics": {
                "total_return": result["total_return"],
                "sharpe_ratio": result["sharpe_ratio"],
                "max_drawdown": result["max_drawdown"],
                "win_rate": result["win_rate"],
                "profit_factor": result["profit_factor"],
                "win_loss_ratio": result["win_loss_ratio"],
                "total_trades": result["total_trades"],
                "final_capital": result["final_capital"],
            },
            "score": round(score, 4),
        }
        all_results.append(entry)

        if score > best_score:
            best_score = score
            best_params = {param_names[i]: combo[i] for i in range(len(param_names))}
            best_result = entry

        count += 1

    all_results.sort(key=lambda x: x["score"], reverse=True)
    top_n = [r for r in all_results[:10] if r["score"] > -999]

    oos_result = None
    if best_params and oos_ratio > 0 and split < n:
        oos_params = dict(best_params)
        atr_stop = oos_params.pop("atr_stop_mult", 2.0)
        atr_take = oos_params.pop("atr_take_mult", 3.0)
        oos_trade_days = n - split
        try:
            oos_run = run_backtest(
                close=close, high=high, low=low,
                open_prices=open_prices, volume=volume,
                initial_capital=initial_capital,
                atr_stop_mult=atr_stop, atr_take_mult=atr_take,
                trade_days=oos_trade_days,
                strategy_name=strategy_name,
                **oos_params,
            )
            if "error" not in oos_run:
                oos_result = {
                    "total_return": oos_run["total_return"],
                    "sharpe_ratio": oos_run["sharpe_ratio"],
                    "max_drawdown": oos_run["max_drawdown"],
                    "win_rate": oos_run["win_rate"],
                    "total_trades": oos_run["total_trades"],
                    "final_capital": oos_run["final_capital"],
                    "trade_days": oos_trade_days,
                }
        except Exception as e:
            logger.warning(f"OOS 回测异常: {e}")

    degradation = None
    overfit_warn = False
    if best_result and oos_result:
        is_ret = best_result["metrics"]["total_return"]
        oos_ret = oos_result["total_return"]
        degradation = round(is_ret - oos_ret, 2)
        if oos_ret < 0 and is_ret > 0:
            overfit_warn = True
        elif is_ret > 0 and degradation > is_ret * 0.5:
            overfit_warn = True

    return {
        "strategy": strategy_name,
        "metric": metric,
        "total_combinations": total_display,
        "tested": len(all_results),
        "best": best_result,
        "best_params": best_params,
        "top": top_n,
        "oos": oos_result,
        "oos_ratio": oos_ratio,
        "is_trade_days": is_trade_days,
        "degradation_pct": degradation,
        "overfit_warning": overfit_warn,
    }