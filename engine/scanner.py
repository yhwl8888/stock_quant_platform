import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from data.fetcher import fetch_kline, _get_qcode
from .strategies import get_strategy
from .scoring import comprehensive_score
from .indicators import ATR

logger = logging.getLogger(__name__)

PRESET_POOLS = {
    "hs300": [
        "600519", "000858", "601318", "600036", "600276", "000333", "601166",
        "600887", "600030", "600585", "601012", "600031", "600809", "002415",
        "000651", "601888", "600028", "000002", "600048", "601688", "600900",
        "601899", "601857", "600690", "000568", "002304", "300059", "300750",
        "601328", "600016", "601398", "601288", "601939", "601988", "600000",
        "601628", "601601", "600104", "000001", "002594", "688981", "300760",
        "300015", "300122", "300124", "000063", "002475", "603259", "600309",
        "601225", "601088", "600436", "000725", "002714", "600150", "601390",
        "600019", "600547", "000338", "002142", "600893", "601800", "600406",
        "002230", "600570", "601985", "600588", "002129", "600745", "601989",
        "000625", "002460", "600926", "000100", "002241", "601727", "600703",
        "600515", "601100", "000776", "600183", "300661", "300433", "002179",
        "000157", "002601", "300308", "600489", "601058", "600111", "002371",
        "000977", "600584", "600958", "300316", "600885", "000786", "600426",
        "300498", "688008", "688256", "002709", "601377", "000876", "603986",
    ],
    "zz500": [
        "000988", "002008", "300033", "600079", "002156", "300124", "600885",
        "002410", "300316", "000723", "002081", "600566", "000830", "002271",
        "300770", "600338", "002014", "300595", "002311", "600426", "002127",
        "002463", "300017", "300558", "601975", "000686", "002430", "600580",
        "002416", "600438", "600754", "600970", "603345", "002439", "300474",
        "603019", "605117", "601998", "002010", "002640", "600219", "601678",
        "002179", "000951", "000799", "300502", "300130", "688002", "600642",
        "688005", "600986", "300377", "600157", "002062", "300806", "601000",
        "603893", "600331", "605358", "002508", "601872", "603605", "600460",
        "300782", "300661", "002648", "002709", "603290", "600761", "002938",
        "002155", "300896", "603185", "600057", "000009", "300831", "002920",
        "002032", "001872", "300759", "002440", "002049", "600689", "688561",
        "300825", "688568", "600999", "601600", "000738", "600489", "600053",
        "600160", "600380", "688599", "603170", "000591", "002091",
    ],
    "shanghai50": [
        "600519", "600036", "601318", "600276", "600030", "600887", "601166",
        "601398", "600585", "601012", "600031", "601888", "600028", "600000",
        "600048", "600628", "601988", "601857", "601288", "601939",
    ],
    "sz_chuangye": [
        "300750", "300059", "300015", "300760", "300122", "300124", "300142",
        "300144", "300316", "300498", "300661", "300677", "300782", "300866",
    ],
    "hot_tech": [
        "002594", "002415", "300750", "002230", "000063", "300059",
        "300122", "300316", "600519", "600276", "300760",
    ],
}

# 按代码前缀规律生成的动态池（fetch_kline 只会对有效代码返回数据，无效代码自动过滤）
DYNAMIC_POOL_SLUGS = {
    "all_sh60": "沪市主板(60xxxx)",
    "all_sh68": "科创板(688xxx)",
    "all_sz00": "深市主板(00xxxx)",
    "all_sz30": "创业板(30xxxx)",
}


def _gen_dynamic_codes(prefix: str, count: int) -> list:
    pad = 6 - len(prefix)
    return [f"{prefix}{str(i).zfill(pad)}" for i in range(count)]


def get_preset_pools():
    info = {}
    for k, v in PRESET_POOLS.items():
        info[k] = {"name": k, "count": len(v), "codes": v[:5], "type": "static"}
    for k, v in DYNAMIC_POOL_SLUGS.items():
        info[k] = {"name": v, "count": "约 500-10000", "type": "dynamic"}
    return info


def _check_one(code: str, strategy_name: str, days: int = 200) -> dict:
    kline = fetch_kline(code, days)
    if not kline or len(kline) < 60:
        return None  # 无效/停牌/退市 stock

    close = np.array([d["close"] for d in kline], dtype=float)
    high = np.array([d["high"] for d in kline], dtype=float)
    low = np.array([d["low"] for d in kline], dtype=float)
    open_arr = np.array([d["open"] for d in kline], dtype=float)
    volume = np.array([d["volume"] for d in kline], dtype=float)
    n = len(close)
    i = n - 1

    strategy = get_strategy(strategy_name)
    params = dict(strategy["params"])
    params["volume"] = volume

    try:
        sig = strategy["signal"](close, high, low, open_arr, i, 0, **params)
    except Exception:
        return None

    df = {
        "close": close.tolist(), "high": high.tolist(),
        "low": low.tolist(), "volume": volume.tolist(),
        "open": open_arr.tolist(),
    }
    score_result = comprehensive_score(df)

    atr_vals = ATR(high, low, close, 14)
    last_atr = atr_vals[-1] if not np.isnan(atr_vals[-1]) else 0
    last_close = float(close[-1])

    return {
        "code": code,
        "signal": int(sig) if sig else 0,
        "signal_triggered": bool(sig > 0),
        "price": round(last_close, 2),
        "total_score": score_result.get("总分", 0),
        "signal_label": score_result.get("信号中文", ""),
        "atr": round(float(last_atr), 2),
        "stop_price": round(last_close - 2 * float(last_atr), 2) if last_atr else None,
        "take_price": round(last_close + 3 * float(last_atr), 2) if last_atr else None,
        "trend_score": score_result.get("趋势", {}).get("score", 0),
        "volume_score": score_result.get("量价分析", {}).get("score", 0),
    }


def scan_pool(codes: list, strategy_name: str = "ma_crossover",
              min_total_score: int = 60, days: int = 200,
              max_workers: int = 4) -> dict:
    if not codes:
        return {"error": "股票池为空"}

    signals = []
    all_ranked = []
    errors = []
    scanned_ok = 0
    scanned_skip = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_check_one, c, strategy_name, days): c for c in codes}
        for fut in as_completed(futures):
            try:
                r = fut.result(timeout=30)
            except Exception:
                scanned_skip += 1
                continue
            if r is None:
                scanned_skip += 1  # 无效代码
                continue
            scanned_ok += 1
            all_ranked.append(r)
            if r["signal_triggered"] and r["total_score"] >= min_total_score:
                signals.append(r)

    if scanned_skip > 0:
        logger.info(f"扫描 {strategy_name}: {scanned_ok} 有效 / {scanned_skip} 无效, {len(signals)} 命中")

    all_ranked.sort(key=lambda x: x["total_score"], reverse=True)
    signals.sort(key=lambda x: x["total_score"], reverse=True)

    return {
        "strategy": strategy_name,
        "pool_size": len(codes),
        "scanned": scanned_ok,
        "skipped": scanned_skip,
        "hits": signals,
        "ranked": all_ranked,
        "errors_count": len(errors),
    }
