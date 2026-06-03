import numpy as np
from .indicators import ATR
from .strategies import get_strategy

COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_TAX_RATE = 0.0005
SLIPPAGE_RATE = 0.001


def _buy_price(price: float) -> float:
    return price * (1 + SLIPPAGE_RATE)


def _sell_price(price: float) -> float:
    return price * (1 - SLIPPAGE_RATE)


def _buy_cost(shares: int, exec_price: float) -> float:
    notional = shares * exec_price
    commission = max(notional * COMMISSION_RATE, COMMISSION_MIN)
    return notional + commission


def _sell_proceeds(shares: int, exec_price: float) -> float:
    notional = shares * exec_price
    commission = max(notional * COMMISSION_RATE, COMMISSION_MIN)
    stamp = notional * STAMP_TAX_RATE
    return notional - commission - stamp


def run_backtest(close: list, high: list, low: list, open_prices: list = None, volume: list = None,
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
    open_arr = np.array(open_prices, dtype=float) if open_prices is not None else close
    volume_arr = np.array(volume, dtype=float) if volume is not None else np.ones_like(close)
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
    entry_cost = 0.0
    trades = []
    equity_curve = []
    total_costs = 0.0

    def _open_long(i, price_ref):
        nonlocal cash, position, entry_price, entry_bar, entry_cost, total_costs
        exec_p = _buy_price(price_ref)
        pos_size = (cash * 0.95) / exec_p
        pos_size = int((pos_size // 100) * 100) if pos_size >= 100 else int(pos_size)
        if pos_size < 1:
            return False
        cost = _buy_cost(pos_size, exec_p)
        if cost > cash:
            pos_size = int(((cash / exec_p) // 100) * 100)
            if pos_size < 1:
                return False
            cost = _buy_cost(pos_size, exec_p)
        cash -= cost
        commission = max(pos_size * exec_p * COMMISSION_RATE, COMMISSION_MIN)
        total_costs += commission
        position = pos_size
        entry_price = exec_p
        entry_cost = cost
        entry_bar = i
        return True

    def _open_short(i, price_ref):
        nonlocal cash, position, entry_price, entry_bar, entry_cost, total_costs
        exec_p = _sell_price(price_ref)
        pos_size = (cash * 0.95) / exec_p
        pos_size = int((pos_size // 100) * 100) if pos_size >= 100 else int(pos_size)
        if pos_size < 1:
            return False
        commission = max(pos_size * exec_p * COMMISSION_RATE, COMMISSION_MIN)
        stamp = pos_size * exec_p * STAMP_TAX_RATE
        cash += pos_size * exec_p - commission - stamp
        total_costs += commission + stamp
        position = -pos_size
        entry_price = exec_p
        entry_cost = pos_size * exec_p
        entry_bar = i
        return True

    def _close_long(i, price_ref, reason):
        nonlocal cash, position, entry_price, entry_cost, total_costs
        shares = position
        exec_p = _sell_price(price_ref)
        proceeds = _sell_proceeds(shares, exec_p)
        commission = max(shares * exec_p * COMMISSION_RATE, COMMISSION_MIN)
        stamp = shares * exec_p * STAMP_TAX_RATE
        total_costs += commission + stamp
        pnl = proceeds - entry_cost
        cash += proceeds
        trades.append({
            "date": str(i), "action": "sell",
            "price": round(exec_p, 2), "shares": int(shares),
            "pnl": round(pnl, 2), "reason": reason,
        })
        position = 0
        entry_price = 0
        entry_cost = 0.0

    def _close_short(i, price_ref, reason):
        nonlocal cash, position, entry_price, entry_cost, total_costs
        shares = abs(position)
        exec_p = _buy_price(price_ref)
        cost = _buy_cost(shares, exec_p)
        commission = max(shares * exec_p * COMMISSION_RATE, COMMISSION_MIN)
        total_costs += commission
        pnl = entry_cost - cost
        cash -= cost
        trades.append({
            "date": str(i), "action": "cover",
            "price": round(exec_p, 2), "shares": int(shares),
            "pnl": round(pnl, 2), "reason": reason,
        })
        position = 0
        entry_price = 0
        entry_cost = 0.0

    for i in range(start, end):
        if i < atr_period or np.isnan(atr_vals[i]):
            equity_curve.append(cash)
            continue

        current_atr = atr_vals[i]

        params_with_volume = dict(params)
        params_with_volume["volume"] = volume_arr
        sig = strategy["signal"](close, high, low, open_arr, i, position, **params_with_volume)
        exit_sig = strategy["exit"](close, high, low, i, entry_price, position, entry_bar, **params)

        if exit_sig != 0 and position != 0:
            if position > 0:
                _close_long(i, close[i], "策略平仓")
            else:
                _close_short(i, close[i], "策略平仓")

        want_long = sig > 0
        want_short = sig < 0
        should_open = (want_long and position <= 0) or (want_short and position >= 0)

        if should_open and sig != 0:
            if position > 0:
                _close_long(i, close[i], "反转平仓")
            elif position < 0:
                _close_short(i, close[i], "反转平仓")

            opened = _open_long(i, close[i]) if sig > 0 else _open_short(i, close[i])
            if opened:
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

        if position > 0:
            stop_price = entry_price - atr_stop_mult * current_atr
            take_price = entry_price + atr_take_mult * current_atr
            if close[i] <= stop_price:
                _close_long(i, close[i], "止损")
            elif close[i] >= take_price:
                _close_long(i, close[i], "止盈")
        elif position < 0:
            stop_price = entry_price + atr_stop_mult * current_atr
            take_price = entry_price - atr_take_mult * current_atr
            if close[i] >= stop_price:
                _close_short(i, close[i], "止损")
            elif close[i] <= take_price:
                _close_short(i, close[i], "止盈")

        if position > 0:
            equity = cash + position * _sell_price(close[i]) - max(position * _sell_price(close[i]) * COMMISSION_RATE, COMMISSION_MIN) - position * _sell_price(close[i]) * STAMP_TAX_RATE
        elif position < 0:
            equity = cash - abs(position) * _buy_price(close[i]) - max(abs(position) * _buy_price(close[i]) * COMMISSION_RATE, COMMISSION_MIN)
        else:
            equity = cash
        equity_curve.append(equity)

    if position > 0:
        _close_long(end - 1, close[-1], "期末平仓")
        equity_curve[-1] = cash
    elif position < 0:
        _close_short(end - 1, close[-1], "期末平仓")
        equity_curve[-1] = cash

    final_value = equity_curve[-1] if equity_curve else initial_capital
    total_return = (final_value - initial_capital) / initial_capital

    equity_arr = np.array(equity_curve)
    if len(equity_arr) > 1:
        prev = equity_arr[:-1]
        prev_safe = np.where(prev == 0, 1, prev)
        daily_returns = np.diff(equity_arr) / prev_safe
    else:
        daily_returns = np.array([0])

    win_trades = [t for t in trades if t.get("pnl", 0) > 0]
    loss_trades = [t for t in trades if t.get("pnl", 0) < 0]
    win_rate = len(win_trades) / (len(win_trades) + len(loss_trades)) if (len(win_trades) + len(loss_trades)) > 0 else 0

    avg_win = np.mean([t["pnl"] for t in win_trades]) if win_trades else 0
    avg_loss = abs(np.mean([t["pnl"] for t in loss_trades])) if loss_trades else 0
    profit_factor = round(sum(t["pnl"] for t in win_trades) / abs(sum(t["pnl"] for t in loss_trades)), 2) if loss_trades and sum(t["pnl"] for t in loss_trades) != 0 else None
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    cummax = np.maximum.accumulate(equity_arr) if len(equity_arr) > 0 else np.array([initial_capital])
    cummax_safe = np.where(cummax == 0, 1, cummax)
    drawdowns = (equity_arr - cummax) / cummax_safe
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
        "total_costs": round(total_costs, 2),
        "trades": trades,
        "equity_curve": [round(v, 2) for v in equity_curve],
    }
