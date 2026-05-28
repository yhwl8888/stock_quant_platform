import itertools
import numpy as np
from .backtest import run_backtest


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
        "boll_std": {"values": [1.5, 2.0], "label": "布林带标准差"},
        "rsi_period": {"values": [14], "label": "RSI周期"},
        "rsi_low": {"values": [20, 30], "label": "RSI超卖阈值"},
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


def optimize(close, high, low, open=None, volume=None,
             initial_capital=10000,
             strategy_name="ma_crossover",
             trade_days=60,
             metric="sharpe_ratio") -> dict:
    grid = get_param_grid(strategy_name)
    if not grid:
        return {"error": f"策略 {strategy_name} 无优化参数"}

    param_names = list(grid.keys())
    param_values = [grid[p]["values"] for p in param_names]

    best_score = -np.inf
    best_params = None
    best_result = None
    all_results = []

    total = 1
    for v in param_values:
        total *= len(v)
    
    # 限制最大组合数，防止超时
    MAX_COMBINATIONS = 200
    if total > MAX_COMBINATIONS:
        # 如果组合太多，就随机采样
        import random
        random.seed(42)
        all_combos = list(itertools.product(*param_values))
        random.shuffle(all_combos)
        combos = all_combos[:MAX_COMBINATIONS]
        total_display = f"{MAX_COMBINATIONS}/{total}"
    else:
        combos = itertools.product(*param_values)
        total_display = str(total)

    count = 0
    for combo in combos:
        # 只把策略参数和标准的回测参数分开
        strategy_params = {param_names[i]: combo[i] for i in range(len(param_names))}
        
        atr_stop = strategy_params.pop("atr_stop_mult", 2.0)
        atr_take = strategy_params.pop("atr_take_mult", 3.0)

        try:
            result = run_backtest(
                close=close,
                high=high,
                low=low,
                open=open,
                volume=volume,
                initial_capital=initial_capital,
                atr_stop_mult=atr_stop,
                atr_take_mult=atr_take,
                trade_days=trade_days,
                strategy_name=strategy_name,
                **strategy_params
            )
        except Exception:
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

    return {
        "strategy": strategy_name,
        "metric": metric,
        "total_combinations": total_display,
        "tested": len(all_results),
        "best": best_result,
        "best_params": best_params,
        "top": top_n,
    }