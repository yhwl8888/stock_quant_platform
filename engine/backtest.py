import numpy as np
from .indicators import ATR
from .strategies import get_strategy


def run_backtest(close: list, high: list, low: list, open: list = None, volume: list = None,
                 initial_capital: float = 10000,
                 atr_period: int = 14,
                 atr_stop_mult: float = 2.0,
                 atr_take_mult: float = 3.0,
                 trade_days: int = 60,
                 strategy_name: str = "ma_crossover",
                 **strategy_kwargs) -> dict:
    close = np.array(close, dtype=float)
    high = np.array(high, dtype=float)
    low = np.array(low, dtype=float)
    open_arr = np.array(open, dtype=float) if open else close
    volume_arr = np.array(volume, dtype=float) if volume else np.ones_like(close)
    n = len(close)

    if n < max(atr_period + 1, trade_days):
        return {"error": "数据不足"}

    strategy = get_strategy(strategy_name)
    params = dict(strategy["params"])
    params.update(strategy_kwargs)
    params["atr_stop_mult"] = atr_stop_mult
    params["atr_take_mult"] = atr_take_mult

    end = n
    start = max(0, n - trade_days)

    atr_vals = ATR(high, low, close, atr_period)
    cash = initial_capital
    position = 0
    entry_price = 0
    entry_bar = 0
    trades = []
    equity_curve = []

    for i in range(start, end):
        if i < atr_period or np.isnan(atr_vals[i]):
            equity_curve.append(cash)
            continue

        current_atr = atr_vals[i]

        # 把 volume 放入 params 字典中传递给策略
        params_with_volume = dict(params)
        params_with_volume["volume"] = volume_arr
        sig = strategy["signal"](close, high, low, open_arr, i, position, **params_with_volume)
        exit_sig = strategy["exit"](close, high, low, i, entry_price, position, entry_bar, **params)

        if exit_sig != 0 and position != 0:
            pnl = position * (close[i] - entry_price)
            trades.append({
                "date": str(i),
                "action": "sell",
                "price": round(close[i], 2),
                "shares": int(abs(position)),
                "pnl": round(pnl, 2),
                "reason": "策略平仓",
            })
            cash += position * close[i]
            position = 0
            entry_price = 0

        want_long = sig > 0
        want_short = sig < 0
        should_open = (want_long and position <= 0) or (want_short and position >= 0)

        if should_open and sig != 0:
            if position != 0:
                pnl = position * (close[i] - entry_price)
                trades.append({
                    "date": str(i),
                    "action": "sell" if position > 0 else "cover",
                    "price": round(close[i], 2),
                    "shares": int(abs(position)),
                    "pnl": round(pnl, 2),
                    "reason": "反转平仓",
                })
                cash += position * close[i]
                position = 0
                entry_price = 0

            pos_size = cash * 0.95 / close[i]
            pos_size = (pos_size // 100) * 100 if pos_size >= 100 else int(pos_size)
            if pos_size >= 1:
                position = pos_size if sig > 0 else -pos_size
                entry_price = close[i]
                entry_bar = i
                if sig > 0:
                    cash -= abs(position) * entry_price
                else:
                    cash += abs(position) * entry_price

                stop_price = entry_price - atr_stop_mult * current_atr if sig > 0 else entry_price + atr_stop_mult * current_atr
                take_price = entry_price + atr_take_mult * current_atr if sig > 0 else entry_price - atr_take_mult * current_atr
                trades.append({
                    "date": str(i),
                    "action": "buy" if sig > 0 else "short",
                    "price": round(entry_price, 2),
                    "shares": int(abs(position)),
                    "stop": round(stop_price, 2),
                    "take": round(take_price, 2),
                })
            else:
                position = 0

        if position > 0:
            stop_price = entry_price - atr_stop_mult * current_atr
            take_price = entry_price + atr_take_mult * current_atr
            if close[i] <= stop_price:
                pnl = position * (close[i] - entry_price)
                trades.append({"date": str(i), "action": "sell", "price": round(close[i], 2), "shares": int(position), "pnl": round(pnl, 2), "reason": "止损"})
                cash += position * close[i]
                position = 0
                entry_price = 0
            elif close[i] >= take_price:
                pnl = position * (close[i] - entry_price)
                trades.append({"date": str(i), "action": "sell", "price": round(close[i], 2), "shares": int(position), "pnl": round(pnl, 2), "reason": "止盈"})
                cash += position * close[i]
                position = 0
                entry_price = 0
        elif position < 0:
            stop_price = entry_price + atr_stop_mult * current_atr
            take_price = entry_price - atr_take_mult * current_atr
            if close[i] >= stop_price:
                pnl = position * (close[i] - entry_price)
                trades.append({"date": str(i), "action": "cover", "price": round(close[i], 2), "shares": int(abs(position)), "pnl": round(pnl, 2), "reason": "止损"})
                cash += position * close[i]
                position = 0
                entry_price = 0
            elif close[i] <= take_price:
                pnl = position * (close[i] - entry_price)
                trades.append({"date": str(i), "action": "cover", "price": round(close[i], 2), "shares": int(abs(position)), "pnl": round(pnl, 2), "reason": "止盈"})
                cash += position * close[i]
                position = 0
                entry_price = 0

        equity = cash + position * close[i]
        equity_curve.append(equity)

    # Close any open position at end
    if position > 0:
        pnl = position * (close[-1] - entry_price)
        trades.append({
            "date": str(end - 1),
            "action": "sell",
            "price": round(close[-1], 2),
            "shares": int(position),
            "pnl": round(pnl, 2),
            "reason": "平仓",
        })
        cash += position * close[-1]
        position = 0
        equity_curve[-1] = cash
    elif position < 0:
        shares = abs(int(position))
        pnl = position * (close[-1] - entry_price)
        trades.append({
            "date": str(end - 1),
            "action": "cover",
            "price": round(close[-1], 2),
            "shares": shares,
            "pnl": round(pnl, 2),
            "reason": "平仓",
        })
        cash -= shares * close[-1]
        position = 0
        equity_curve[-1] = cash

    # Calculate metrics
    final_value = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_value - initial_capital) / initial_capital

    equity_arr = np.array(equity_curve)
    daily_returns = np.diff(equity_arr) / equity_arr[:-1] if len(equity_arr) > 1 else np.array([0])

    win_trades = [t for t in trades if t.get("pnl", 0) > 0]
    loss_trades = [t for t in trades if t.get("pnl", 0) < 0]
    win_rate = len(win_trades) / (len(win_trades) + len(loss_trades)) if (len(win_trades) + len(loss_trades)) > 0 else 0

    avg_win = np.mean([t["pnl"] for t in win_trades]) if win_trades else 0
    avg_loss = abs(np.mean([t["pnl"] for t in loss_trades])) if loss_trades else 0
    profit_factor = round(sum(t["pnl"] for t in win_trades) / abs(sum(t["pnl"] for t in loss_trades)), 2) if loss_trades and sum(t["pnl"] for t in loss_trades) != 0 else None
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    cummax = np.maximum.accumulate(equity_arr)
    drawdowns = (equity_arr - cummax) / cummax
    max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0

    sharpe = 0
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)

    return {
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(final_value, 2),
        "total_return": round(total_return * 100, 2),
        "total_return_str": f"{total_return * 100:.2f}%",
        "win_rate": round(win_rate * 100, 2),
        "win_rate_str": f"{win_rate * 100:.2f}%",
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "win_loss_ratio": round(win_loss_ratio, 2),
        "max_drawdown": round(max_drawdown * 100, 2),
        "max_drawdown_str": f"{max_drawdown * 100:.2f}%",
        "sharpe_ratio": round(sharpe, 2),
        "total_trades": len([t for t in trades if t.get("action") in ("sell", "cover")]),
        "trades": trades,
        "equity_curve": [round(v, 2) for v in equity_curve],
    }
