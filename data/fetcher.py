import requests
import re
import json
import pandas as pd
import numpy as np
import codecs
import time
import logging
from datetime import datetime
from typing import Optional
from functools import lru_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_HISTORY_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 请求速率限制
_last_request_time = 0
_MIN_REQUEST_INTERVAL = 0.3  # 最小请求间隔（秒）

def _rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def _get_qcode(code: str) -> str:
    code = code.strip().lower()
    if code.startswith(("sh", "sz", "bj")) and len(code) == 8:
        return code
    bare = code.zfill(6)
    if bare.startswith(("6", "5", "9")):
        return f"sh{bare}"
    elif bare.startswith(("0", "3", "1")):
        return f"sz{bare}"
    elif bare.startswith(("8", "4")):
        return f"bj{bare}"
    return f"sh{bare}"


def fetch_realtime_quote(code: str) -> Optional[dict]:
    qcode = _get_qcode(code)
    market = qcode[:2]
    bare = qcode[2:]

    result = _do_fetch_quote(market, bare)
    if result:
        return result

    if bare.startswith("0") or bare.startswith("3"):
        other = "sh" if market == "sz" else "sz"
        result = _do_fetch_quote(other, bare)
        if result:
            return result

    return None


def _do_fetch_quote(market: str, bare: str) -> Optional[dict]:
    qcode = f"{market}{bare}"
    try:
        _rate_limit()
        resp = requests.get(
            TENCENT_QUOTE_URL + qcode,
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        text = resp.text
        key = f"v_{qcode}"
        if key not in text:
            logger.debug(f"Quote key not found: {qcode}")
            return None
        match = re.search(f'{key}="([^"]+)"', text)
        if not match:
            logger.debug(f"Quote regex match failed: {qcode}")
            return None
        fields = match.group(1).split("~")
        if len(fields) < 50:
            logger.debug(f"Quote fields too short: {qcode}, len={len(fields)}")
            return None
        
        try:
            return {
                "code": fields[2].strip().zfill(6),
                "name": fields[1].strip(),
                "price": float(fields[3]) if fields[3] else 0,
                "pre_close": float(fields[4]) if fields[4] else 0,
                "open": float(fields[5]) if fields[5] else 0,
                "volume": float(fields[6]) if fields[6] else 0,
                "high": float(fields[33]) if fields[33] else 0,
                "low": float(fields[34]) if fields[34] else 0,
                "change_pct": round(((float(fields[3]) - float(fields[4])) / float(fields[4]) * 100), 2) if fields[3] and fields[4] and float(fields[4]) > 0 else 0,
            }
        except (IndexError, ValueError) as e:
            logger.error(f"Quote parsing error: {qcode}, {e}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Quote request failed: {qcode}, {e}")
        return None
    except Exception as e:
        logger.error(f"Quote unexpected error: {qcode}, {e}")
        return None


def _fetch_kline_raw(code: str, days: int = 250) -> list:
    qcode = _get_qcode(code)
    market = qcode[:2]
    bare = qcode[2:]

    result = _do_fetch_kline(market, bare, days)
    if result:
        return result

    if bare.startswith("0") or bare.startswith("3"):
        other = "sh" if market == "sz" else "sz"
        result = _do_fetch_kline(other, bare, days)
        if result:
            return result

    return []


def _do_fetch_kline(market: str, bare: str, days: int) -> list:
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{bare},day,,,{days},,qfq"
    for attempt in range(3):
        try:
            _rate_limit()
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            resp.raise_for_status()
            
            try:
                data = resp.json()
            except json.JSONDecodeError:
                logger.warning(f"K线JSON解析失败: {market}{bare}, 尝试 {attempt+1}/3")
                if attempt < 2:
                    time.sleep(1)
                    continue
                return []

            if data.get("code") != 0:
                logger.warning(f"K线API返回非0 code: {data.get('code')}, url={url}")
                return []

            kline_data = data.get("data", {})
            stock_data = kline_data.get(f"{market}{bare}", kline_data)
            days_data = stock_data.get("day", [])

            if not days_data:
                logger.warning(f"K线数据为空: {market}{bare}, 尝试 {attempt+1}/3")
                if attempt < 2:
                    time.sleep(1)
                    continue
                return []

            result = []
            for item in days_data:
                try:
                    if len(item) >= 6:
                        result.append({
                            "date": str(item[0]),
                            "open": float(item[1]),
                            "close": float(item[2]),
                            "high": float(item[3]),
                            "low": float(item[4]),
                            "volume": float(item[5]),
                        })
                except (IndexError, ValueError) as e:
                    logger.debug(f"K线单条数据解析失败: {market}{bare}, {e}")
                    continue
            
            if result:
                logger.info(f"K线获取成功: {market}{bare}, {len(result)}条")
                return result
            else:
                logger.warning(f"K线数据解析后为空: {market}{bare}, 尝试 {attempt+1}/3")
                if attempt < 2:
                    time.sleep(1)
                    continue
                return []
        except requests.exceptions.Timeout:
            logger.warning(f"K线请求超时: {market}{bare}, 尝试 {attempt+1}/3")
            if attempt < 2:
                time.sleep(2)
        except requests.exceptions.RequestException as e:
            logger.error(f"K线请求失败: {market}{bare}, {e}, 尝试 {attempt+1}/3")
            if attempt < 2:
                time.sleep(1)
        except Exception as e:
            logger.error(f"K线获取异常: {market}{bare}, {type(e).__name__}: {e}, 尝试 {attempt+1}/3")
            if attempt < 2:
                time.sleep(1)
    logger.error(f"K线获取失败，已重试3次: {market}{bare}")
    return []


def fetch_kline(code: str, days: int = 250) -> list:
    """K线获取 - 不使用 lru_cache，避免缓存失败结果"""
    return _fetch_kline_raw(code, days)


def search_stocks(keyword: str) -> list:
    kw = keyword.strip()
    if not kw:
        return []

    results = []

    try:
        _rate_limit()
        url = f"https://smartbox.gtimg.cn/s3/?q={kw}&t=all"
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
        resp.raise_for_status()
        text = resp.text
        if '="' in text and not text.startswith('v_hint="N"'):
            matches = re.findall(r'"(.*?)"', text)
            for m in matches:
                entries = m.split("^")
                for entry in entries:
                    parts = entry.split("~")
                    if len(parts) >= 5 and parts[0] in ("sh", "sz", "bj"):
                        raw_name = parts[2].strip()
                        try:
                            raw_name = codecs.decode(raw_name, 'unicode_escape')
                        except Exception:
                            pass
                        try:
                            results.append({
                                "code": parts[1].strip().zfill(6),
                                "name": raw_name,
                                "market": parts[0].strip(),
                            })
                        except (IndexError, ValueError):
                            continue
    except requests.exceptions.RequestException as e:
        logger.error(f"Search request failed: {kw}, {e}")
    except Exception as e:
        logger.error(f"Search unexpected error: {kw}, {e}")

    if results:
        return results

    if kw.isdigit() and len(kw) >= 4:
        code = kw.zfill(6)
        try:
            qcode = _get_qcode(code)
            _rate_limit()
            resp = requests.get(
                TENCENT_QUOTE_URL + qcode,
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            text = resp.text
            key = f"v_{qcode}"
            if key in text:
                match = re.search(f'{key}="([^"]+)"', text)
                if match:
                    fields = match.group(1).split("~")
                    if len(fields) >= 3 and fields[1].strip():
                        results.append({
                            "code": fields[2].strip().zfill(6),
                            "name": fields[1].strip(),
                            "market": "sh" if code.startswith(("6", "5")) else "sz",
                        })
                        return results
        except requests.exceptions.RequestException as e:
            logger.debug(f"Search fallback request failed: {kw}, {e}")
        except Exception as e:
            logger.debug(f"Search fallback error: {kw}, {e}")

        name_map = {"6": "上海", "0": "深圳", "3": "创业板", "8": "北京", "4": "北京", "5": "上海"}
        prefix = code[0]
        market_name = name_map.get(prefix, "")
        results.append({
            "code": code,
            "name": f"{kw}",
            "market": "sh" if code.startswith(("6", "5", "9")) else "sz",
        })

    return results
