"""
A-Share Intelligent Analysis System — Web Dashboard
FastAPI + Jinja2 + SSE real-time task progress
"""
from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from loguru import logger
from pydantic import BaseModel

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from src.analysis.analyzer import TechnicalAnalyzer
from src.ai.features import FeatureEngineer
from src.ai.sklearn_predictor import SklearnPredictor
from src.data.akshare_fetcher import AkshareFetcher
from src.data.sqlite_storage import SQLiteStorage
from src.pipeline.orchestrator import PipelineOrchestrator
from src.utils.logger import setup_logging

# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

setup_logging()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Preload stock search cache on startup."""
    asyncio.create_task(asyncio.to_thread(_load_stock_list))
    yield


app = FastAPI(title="A股智能分析", version="0.1.0", lifespan=lifespan)

PROJECT_ROOT = Path(__file__).resolve().parent
_tpl_env = Environment(loader=FileSystemLoader(str(PROJECT_ROOT / "templates")))

static_dir = PROJECT_ROOT / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ---------------------------------------------------------------------------
# Dependency wiring (lazy)
# ---------------------------------------------------------------------------

_orchestrator: Optional[PipelineOrchestrator] = None
_task_store: dict[str, dict] = {}  # task_id → status/result


def _get_orchestrator() -> PipelineOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        settings.model_dir.mkdir(parents=True, exist_ok=True)
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        fetcher = AkshareFetcher()
        storage = SQLiteStorage()
        analyzer = TechnicalAnalyzer()
        predictor = SklearnPredictor()
        feature_engineer = FeatureEngineer()
        _orchestrator = PipelineOrchestrator(fetcher, storage, analyzer, predictor, feature_engineer)
    return _orchestrator


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tmpl = _tpl_env.get_template("index.html")
    return HTMLResponse(tmpl.render(request=request))


# ---------------------------------------------------------------------------
# Routes — Stock list (full cache, for client-side search)
# ---------------------------------------------------------------------------


@app.get("/api/v1/stock/stocks")
async def stock_list():
    """Return full cached stock list [{code, name}, ...] for client-side search."""
    return JSONResponse(_load_stock_list())


# ---------------------------------------------------------------------------
# Routes — Stock search (server-side, fallback)
# ---------------------------------------------------------------------------


@app.get("/api/v1/stock/search")
async def stock_search(q: str = Query("", min_length=1)):
    """Return matching stocks {code, name} — uses akshare with em_datacenter fallback."""
    q_lower = q.strip().lower()
    results = _search_via_akshare(q_lower)
    if not results:
        results = _search_via_em_datacenter(q_lower)
    return JSONResponse(results[:10])


def _search_via_akshare(q_lower: str) -> list[dict]:
    try:
        orch = _get_orchestrator()
        stock_list = orch._fetcher.fetch_stock_list()
    except Exception:
        return []
    results = []
    for s in stock_list:
        if q_lower in s.code or q_lower in s.name.lower():
            results.append({"code": s.code, "name": s.name})
            if len(results) >= 10:
                break
    return results


_STOCK_LIST_CACHE: list[dict] | None = None


def _load_stock_list() -> list[dict]:
    """Load full stock list from em_datacenter API with pagination, cache in memory."""
    global _STOCK_LIST_CACHE
    if _STOCK_LIST_CACHE is not None:
        return _STOCK_LIST_CACHE
    import requests as _requests
    results: list[dict] = []
    page, page_size = 1, 500
    try:
        while True:
            url = "https://data.eastmoney.com/dataapi/xuangu/list"
            params = {
                "st": "SECURITY_CODE", "sr": "1", "ps": str(page_size), "p": str(page),
                "sty": "SECURITY_CODE,SECURITY_NAME_ABBR",
                "filter": '(MARKET+in+("上交所主板","深交所主板","深交所创业板","上交所科创板","北交所"))',
                "source": "SELECT_SECURITIES", "client": "WEB",
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://data.eastmoney.com/xuangu/",
            }
            resp = _requests.get(url, params=params, headers=headers, timeout=30)
            data = resp.json()
            if not data.get("success"):
                break
            r = data.get("result", {})
            for item in r.get("data", []):
                results.append({"code": str(item.get("SECURITY_CODE", "")), "name": str(item.get("SECURITY_NAME_ABBR", ""))})
            total = int(r.get("count", 0))
            if page * page_size >= total:
                break
            page += 1
        logger.info(f"Loaded {len(results)} stocks for search cache")
    except Exception as e:
        logger.warning(f"Stock list load failed: {e}")
    _STOCK_LIST_CACHE = results
    return results


def _search_via_em_datacenter(q_lower: str) -> list[dict]:
    """Search stock list (cached from em_datacenter)."""
    results = []
    for s in _load_stock_list():
        if q_lower in s["code"].lower() or q_lower in s["name"].lower():
            results.append(s)
            if len(results) >= 10:
                break
    return results


# ---------------------------------------------------------------------------
# Routes — Analysis (async with SSE)
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    code: str


@app.post("/api/v1/analysis/analyze")
async def trigger_analysis(req: AnalyzeRequest):
    """Start analysis, return cached result if available for today."""
    import uuid

    code = req.code
    today = date.today()
    orch = _get_orchestrator()

    # Check SQLite cache for today's result
    cached = orch._storage.get_cached_result(code, today)
    if cached:
        task_id = "cached"
        _task_store[task_id] = {"status": "completed", "code": code, "result": cached}
        return JSONResponse({"task_id": task_id, "status": "completed", "cached": True})

    task_id = str(uuid.uuid4())[:8]
    _task_store[task_id] = {"status": "pending", "code": code, "result": None}
    asyncio.create_task(_run_analysis(task_id, code))
    return JSONResponse({"task_id": task_id, "status": "pending"})


async def _run_analysis(task_id: str, code: str):
    """Background analysis runner — updates _task_store and persists to cache."""
    orch = _get_orchestrator()
    try:
        _task_store[task_id]["status"] = "collecting"
        orch.collect_data([code], incremental=True)

        _task_store[task_id]["status"] = "analyzing"
        orch.compute_indicators([code])

        _task_store[task_id]["status"] = "training"
        orch.train_model(code)

        _task_store[task_id]["status"] = "predicting"
        result = orch.predict(code)

        df = orch._storage.get_merged_dataframe(code)
        latest = df.iloc[-1] if len(df) > 0 else None

        _task_store[task_id]["status"] = "completed"
        payload = {
            "code": result.code,
            "date": result.predict_date.isoformat(),
            "trend": result.predicted_trend,
            "confidence": round(result.confidence, 4),
            "model": result.model_name,
            "features_count": len(result.features_used),
            "latest_price": float(latest["close"]) if latest is not None else None,
            "latest_ma5": float(latest["ma_5"]) if latest is not None and not pd.isna(latest.get("ma_5")) else None,
            "latest_rsi": float(latest["rsi_14"]) if latest is not None and not pd.isna(latest.get("rsi_14")) else None,
            "latest_macd_dif": float(latest["macd_dif"]) if latest is not None and not pd.isna(latest.get("macd_dif")) else None,
            "latest_macd_bar": float(latest["macd_bar"]) if latest is not None and not pd.isna(latest.get("macd_bar")) else None,
        }
        _task_store[task_id]["result"] = payload
        # Cache for today
        orch._storage.set_cached_result(code, date.today(), payload)
    except Exception as e:
        _task_store[task_id]["status"] = "failed"
        _task_store[task_id]["error"] = str(e)


@app.get("/api/v1/analysis/status/{task_id}")
async def task_status_stream(task_id: str):
    """SSE endpoint for real-time task progress updates."""

    async def event_stream():
        last_status = None
        while True:
            task = _task_store.get(task_id)
            if task is None:
                yield f"event: error\ndata: task not found\n\n"
                break
            current_status = task["status"]
            if current_status != last_status:
                yield f"event: status\ndata: {json.dumps(task)}\n\n"
                last_status = current_status
            if current_status in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Routes — Chart data
# ---------------------------------------------------------------------------


@app.get("/api/v1/stocks/{code}/chart")
async def stock_chart_data(code: str, days: int = Query(90, ge=30, le=365)):
    """Return daily data as JSON for Plotly chart rendering."""
    orch = _get_orchestrator()
    df = orch._storage.get_merged_dataframe(code)
    if df.empty:
        return JSONResponse({"error": "no data"}, status_code=404)
    df = df.tail(days)
    return JSONResponse({
        "dates": df["date"].astype(str).tolist(),
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
        "ma_5": [None if pd.isna(v) else v for v in df.get("ma_5", [])] if "ma_5" in df.columns else [],
        "ma_20": [None if pd.isna(v) else v for v in df.get("ma_20", [])] if "ma_20" in df.columns else [],
        "rsi_14": [None if pd.isna(v) else v for v in df.get("rsi_14", [])] if "rsi_14" in df.columns else [],
        "macd_dif": [None if pd.isna(v) else v for v in df.get("macd_dif", [])] if "macd_dif" in df.columns else [],
        "macd_dea": [None if pd.isna(v) else v for v in df.get("macd_dea", [])] if "macd_dea" in df.columns else [],
        "macd_bar": [None if pd.isna(v) else v for v in df.get("macd_bar", [])] if "macd_bar" in df.columns else [],
        "bb_upper": [None if pd.isna(v) else v for v in df.get("bb_upper", [])] if "bb_upper" in df.columns else [],
        "bb_middle": [None if pd.isna(v) else v for v in df.get("bb_middle", [])] if "bb_middle" in df.columns else [],
        "bb_lower": [None if pd.isna(v) else v for v in df.get("bb_lower", [])] if "bb_lower" in df.columns else [],
    })


@app.get("/api/v1/stocks/{code}/info")
async def stock_info(code: str):
    """Return basic stock info: name, latest price, change."""
    orch = _get_orchestrator()
    df = orch._storage.get_merged_dataframe(code)
    if df.empty:
        return JSONResponse({"error": "no data"}, status_code=404)
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    change_pct = (latest["close"] - prev["close"]) / prev["close"] * 100 if prev["close"] > 0 else 0
    return JSONResponse({
        "code": code,
        "date": str(latest["date"]),
        "open": float(latest["open"]),
        "high": float(latest["high"]),
        "low": float(latest["low"]),
        "close": float(latest["close"]),
        "volume": int(latest["volume"]),
        "amount": float(latest["amount"]),
        "change_pct": round(float(change_pct), 2),
    })


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Routes — AlphaSift screening
# ---------------------------------------------------------------------------


@app.get("/api/v1/screen/strategies")
async def list_strategies():
    """List available screening strategies."""
    try:
        from alphasift import list_strategies as _ls
        result = []
        for s in _ls():
            result.append({"name": s.name, "category": s.category, "description": s.description})
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/v1/screen/run")
async def run_screening(req: dict):
    """Run screening with given strategy."""
    try:
        from alphasift import screen as _screen
        strategy = req.get("strategy", "dual_low")
        result = _screen(strategy, use_llm=False)
        picks = []
        for p in result.picks[:20]:
            picks.append({
                "code": p.code, "name": p.name, "price": p.price,
                "pe_ratio": p.pe_ratio, "pb_ratio": p.pb_ratio,
                "change_pct": p.change_pct, "final_score": round(p.final_score, 1),
                "total_mv": p.total_mv, "turnover_rate": p.turnover_rate,
                "industry": p.industry,
            })
        return JSONResponse({
            "strategy": result.strategy,
            "snapshot_source": result.snapshot_source,
            "snapshot_count": result.snapshot_count,
            "after_filter_count": result.after_filter_count,
            "picks_count": len(picks),
            "picks": picks,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Routes — Stock profile & industry
# ---------------------------------------------------------------------------


@app.get("/api/v1/stocks/{code}/full")
async def stock_full(code: str):
    """Aggregate all enrichment data in one call: profile + platform + sentiment + research + news."""
    result: dict = {}
    try:
        result["profile"] = await _get_profile(code)
    except Exception:
        result["profile"] = {}
    try:
        result["platform"] = await _get_platform(code)
    except Exception:
        result["platform"] = {}
    try:
        result["sentiment"] = await _get_sentiment(code)
    except Exception:
        result["sentiment"] = {}
    try:
        result["research"] = await _get_research(code)
    except Exception:
        result["research"] = []
    try:
        result["news"] = await _get_news(code)
    except Exception:
        result["news"] = []
    return JSONResponse(result)


# Inline helpers so /full can call internals without HTTP
async def _get_profile(code: str) -> dict:
    import akshare as ak
    info = ak.stock_individual_info_em(symbol=code)
    r = {}
    if info is not None and not info.empty:
        for _, row in info.iterrows():
            k, v = str(row["item"]), str(row["value"])
            if "行业" in k: r["industry"] = v
            if "总市值" in k: r["total_mv"] = v
            if "市盈率" in k: r["pe"] = v
            if "市净率" in k: r["pb"] = v
            if "上市时间" in k: r["listed_date"] = v
    try:
        df = ak.stock_board_industry_name_em()
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                if r.get("industry", "") and r["industry"] in str(row.get("板块名称", "")):
                    r["industry_change_pct"] = str(row.get("涨跌幅", "--"))
                    break
    except Exception:
        pass
    return r


async def _get_platform(code: str) -> dict:
    import akshare as ak
    from src.utils.helpers import determine_market
    r = {}
    try:
        market = determine_market(code)
        flow = ak.stock_individual_fund_flow(stock=code, market=market)
        if flow is not None and not flow.empty:
            r["main_5d_net"] = f"{flow.tail(5).iloc[:,2].astype(float).sum()/1e8:.2f}亿"
    except Exception:
        pass
    try:
        hot = ak.stock_hot_rank_em()
        if hot is not None and not hot.empty:
            m = hot[hot["代码"] == code]
            r["em_hot_rank"] = str(m.iloc[0, 0]) if not m.empty else "未上榜"
    except Exception:
        pass
    try:
        market = determine_market(code)
        sym = {"sh": f"SH{code}", "sz": f"SZ{code}", "bj": f"BJ{code}"}.get(market, f"SZ{code}")
        xq = ak.stock_hot_follow_xq(symbol=sym)
        if xq is not None and not xq.empty:
            r["xq_followers"] = str(xq.iloc[0, 0])
    except Exception:
        pass
    return r


async def _get_sentiment(code: str) -> dict:
    import akshare as ak
    r = {}
    try:
        df = ak.stock_hsgt_individual_em(symbol=code)
        if df is not None and not df.empty:
            lat = df.iloc[-1]
            r["north_hold_value"] = str(lat.get("持股市值", ""))
            recent = df.tail(10)
            try:
                sv, ev = float(recent.iloc[0, 4]), float(recent.iloc[-1, 4])
                r["north_10d_change_pct"] = f"{((ev-sv)/sv*100):+.1f}%" if sv > 0 else "--"
            except Exception:
                pass
    except Exception:
        pass
    try:
        df2 = ak.stock_report_fund_hold_detail(symbol=code, date="20250930")
        if df2 is not None and not df2.empty:
            r["fund_count"] = str(len(df2))
    except Exception:
        pass
    try:
        df3 = ak.stock_hsgt_hist_em().dropna(subset=["当日成交净买额"])
        if df3 is not None and not df3.empty:
            r["market_north_5d"] = f"{df3.tail(5)['当日成交净买额'].astype(float).sum()/1e8:+.2f}亿"
    except Exception:
        pass
    return r


async def _get_research(code: str, limit: int = 8) -> list[dict]:
    import akshare as ak
    df = ak.stock_research_report_em(symbol=code)
    if df is None or df.empty:
        return []
    return [{"date": str(r["日期"]), "org": str(r["评级机构"]), "title": str(r["报告名称"]), "rating": str(r["评级"])} for _, r in df.head(limit).iterrows()]


async def _get_news(code: str, limit: int = 8) -> list[dict]:
    import akshare as ak
    df = ak.stock_news_em(symbol=code)
    if df is None or df.empty:
        return []
    return [{"time": str(r.get("发布时间", "")), "title": str(r.get("标题", ""))} for _, r in df.head(limit).iterrows()]


@app.get("/api/v1/stocks/{code}/profile")
async def stock_profile(code: str):
    """Return stock profile info including industry, market cap, PE, PB."""
    try:
        import akshare as ak
        # Get individual info
        info = ak.stock_individual_info_em(symbol=code)
        result = {}
        if info is not None and not info.empty:
            for _, row in info.iterrows():
                key = str(row["item"])
                val = str(row["value"])
                # Map common keys
                if "行业" in key: result["industry"] = val
                if "总市值" in key: result["total_mv"] = val
                if "流通市值" in key: result["circ_mv"] = val
                if "市盈率" in key: result["pe"] = val
                if "市净率" in key: result["pb"] = val
                if "上市时间" in key: result["listed_date"] = val
                if "总股本" in key: result["total_shares"] = val

        # Try to get sector ranking
        try:
            df = ak.stock_board_industry_name_em()
            if df is not None and not df.empty:
                # Find the row for our stock's industry
                industry_name = result.get("industry", "")
                for _, row in df.iterrows():
                    if industry_name and industry_name in str(row.get("板块名称", "")):
                        result["industry_change_pct"] = str(row.get("涨跌幅", "--"))
                        result["industry_rank"] = str(row.get("排名", "--"))
                        break
        except Exception:
            pass

        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Routes — Macro fundamentals
# ---------------------------------------------------------------------------


@app.get("/api/v1/macro/overview")
async def macro_overview():
    """Return key macro indicators: China PMI, CPI, LPR, US rates, etc."""
    result: dict = {}
    try:
        import akshare as ak

        # --- China PMI ---
        try:
            pmi = ak.macro_china_pmi()
            if pmi is not None and not pmi.empty:
                latest = pmi.iloc[-1]
                result["pmi_manufacturing"] = str(latest.get("制造业", latest.iloc[1]))
                result["pmi_non_manufacturing"] = str(latest.get("非制造业", latest.iloc[2] if len(pmi.columns) > 2 else ""))
        except Exception:
            pass

        # --- China CPI ---
        try:
            cpi = ak.macro_china_cpi_monthly()
            if cpi is not None and not cpi.empty:
                result["cpi_yoy"] = str(cpi.iloc[-1].get("全国-同比增长", cpi.iloc[-1, 1]))
                result["cpi_date"] = str(cpi.iloc[-1].get("日期", cpi.index[-1] if hasattr(cpi.index, '__getitem__') else ""))
        except Exception:
            pass

        # --- China LPR ---
        try:
            lpr = ak.macro_china_lpr()
            if lpr is not None and not lpr.empty:
                latest_lpr = lpr.iloc[-1]
                result["lpr_1y"] = str(latest_lpr.get("1年期", latest_lpr.iloc[1]))
                result["lpr_5y"] = str(latest_lpr.get("5年期", latest_lpr.iloc[2] if len(lpr.columns) > 2 else ""))
                result["lpr_date"] = str(latest_lpr.get("日期", lpr.index[-1] if hasattr(lpr.index, '__getitem__') else ""))
        except Exception:
            pass

        # --- China Money Supply ---
        try:
            m2 = ak.macro_china_money_supply()
            if m2 is not None and not m2.empty:
                latest_m2 = m2.iloc[-1]
                result["m2_yoy"] = str(latest_m2.get("M2-同比增长", latest_m2.iloc[2] if len(m2.columns) > 2 else ""))
        except Exception:
            pass

        # --- US Federal Funds Rate ---
        try:
            fed = ak.macro_usa_interest_rate()
            if fed is not None and not fed.empty:
                latest_fed = fed.iloc[-1]
                result["fed_rate"] = str(latest_fed.get("值", latest_fed.iloc[2] if len(fed.columns) > 2 else fed.iloc[-1]))
                result["fed_date"] = str(latest_fed.get("日期", fed.index[-1] if hasattr(fed.index, '__getitem__') else ""))
        except Exception:
            pass

        # --- US Treasury 10Y ---
        try:
            import yfinance as yf
            t10 = yf.download("^TNX", period="1mo", progress=False)
            if t10 is not None and not t10.empty:
                result["us_10y_yield"] = str(round(float(t10.iloc[-1]["Close"]), 2)) + "%"
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return JSONResponse(result)


@app.get("/api/v1/news/headlines")
async def market_headlines(q: str = Query("", max_length=50)):
    """Return top market headlines, optionally filtered by keyword."""
    try:
        import akshare as ak
        all_news = []
        # Try multiple news sources
        sources = [
            ("stock_info_global_em", lambda: ak.stock_info_global_em()),
            ("stock_news_em", lambda: ak.stock_news_em(symbol=q or "000001")),
        ]
        for name, fn in sources:
            try:
                df = fn()
                if df is not None and not df.empty:
                    cols = list(df.columns)
                    for _, row in df.head(15).iterrows():
                        title = str(row.get("标题", row.iloc[1] if len(cols) > 1 else ""))
                        time_val = str(row.get("发布时间", row.get("时间", row.iloc[0] if len(cols) > 0 else "")))
                        if title and title not in [n["title"] for n in all_news]:
                            all_news.append({"title": title, "time": time_val, "source": name})
            except Exception:
                continue

        if q and all_news:
            ql = q.lower()
            all_news = [n for n in all_news if ql in n["title"].lower() or ql in n.get("source", "").lower()]

        return JSONResponse(all_news[:15])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/v1/stocks/{code}/financials")
async def stock_financials(code: str):
    """Return financial data for charting: revenue, profit, ROE, valuation."""
    result: dict = {"revenue": [], "profit": [], "roe": [], "book_value": [], "valuation": []}
    try:
        import akshare as ak

        # --- 财务数据 ---
        try:
            df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
            if df is not None and not df.empty:
                recent = df.tail(20)
                for _, row in recent.iterrows():
                    period = str(row.get("报告期", ""))
                    rev = _parse_financial_val(str(row.get("营业总收入", "0")))
                    profit = _parse_financial_val(str(row.get("净利润", "0")))
                    roe = _parse_financial_val(str(row.get("净资产收益率", "0")))
                    bv = _parse_financial_val(str(row.get("每股净资产", "0")))
                    result["revenue"].append({"date": period, "value": rev})
                    result["profit"].append({"date": period, "value": profit})
                    result["roe"].append({"date": period, "value": roe})
                    result["book_value"].append({"date": period, "value": bv})
        except Exception:
            pass

        # --- 估值水位 (总市值趋势) ---
        try:
            df2 = ak.stock_zh_valuation_baidu(symbol=code)
            if df2 is not None and not df2.empty:
                result["valuation"] = [
                    {"date": str(r["date"]), "value": float(r["value"])}
                    for _, r in df2.tail(500).iterrows()
                ]
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return JSONResponse(result)


def _parse_financial_val(raw: str) -> float:
    """Parse financial values like '337.09亿', '2.80%', '22.48'."""
    try:
        raw = raw.replace(",", "").strip()
        if "亿" in raw:
            return float(raw.replace("亿", ""))
        if "万" in raw:
            return float(raw.replace("万", "")) / 10000
        if "%" in raw:
            return float(raw.replace("%", ""))
        return float(raw)
    except (ValueError, TypeError):
        return 0


@app.get("/api/v1/stocks/{code}/sentiment")
async def stock_sentiment(code: str):
    """North-bound capital + institutional fund attitude for a stock."""
    result: dict = {}
    try:
        import akshare as ak

        # --- 北向资金持仓 ---
        try:
            df = ak.stock_hsgt_individual_em(symbol=code)
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                result["north_hold_date"] = str(latest.get("日期", ""))
                result["north_hold_shares"] = str(latest.get("持股数", ""))
                result["north_hold_value"] = str(latest.get("持股市值", ""))
                result["north_hold_pct"] = str(latest.get("占流通股比例", latest.iloc[5] if len(df.columns) > 5 else ""))
                # Last 10 days trend
                recent = df.tail(10)
                try:
                    val_col = df.columns[4]  # 持股市值
                    start_val = float(recent.iloc[0][val_col])
                    end_val = float(recent.iloc[-1][val_col])
                    change = ((end_val - start_val) / start_val * 100) if start_val > 0 else 0
                    result["north_10d_change_pct"] = f"{change:+.1f}%"
                except Exception:
                    pass
        except Exception:
            pass

        # --- 机构基金持仓 ---
        try:
            df2 = ak.stock_report_fund_hold_detail(symbol=code, date="20250930")
            if df2 is not None and not df2.empty:
                result["fund_count"] = str(len(df2))
                total_val = df2["持股市值"].astype(float).sum() / 1e8
                result["fund_total_value"] = f"{total_val:.2f}亿"
                total_pct = df2["占流通股本比例"].astype(float).sum()
                result["fund_total_pct"] = f"{total_pct:.2f}%"
        except Exception:
            pass

        # --- 北向资金大盘流向 ---
        try:
            df3 = ak.stock_hsgt_hist_em()
            if df3 is not None and not df3.empty:
                # Find latest row with valid data
                df3_valid = df3.dropna(subset=["当日成交净买额"])
                if not df3_valid.empty:
                    latest_north = df3_valid.iloc[-1]
                    result["market_north_date"] = str(latest_north.get("日期", ""))
                    result["market_north_net"] = str(latest_north.get("当日成交净买额", ""))
                    # Last 5 days
                    recent5 = df3_valid.tail(5)
                    total5 = recent5["当日成交净买额"].astype(float).sum() / 1e8
                    result["market_north_5d"] = f"{total5:+.2f}亿"
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return JSONResponse(result)


@app.get("/api/v1/stocks/{code}/patience")
async def patience_chart(code: str):
    """Return patience metrics: holder count trend, turnover, IRM activity."""
    result: dict = {"holders": [], "turnover": [], "irm": []}
    try:
        import akshare as ak

        # --- 股东人数变化 (holder concentration) ---
        try:
            dh = ak.stock_zh_a_gdhs_detail_em(symbol=code)
            if dh is not None and not dh.empty:
                holders = dh[["股东人数统计截止日", "股东人数-本期", "股东人数-变动"]].copy()
                holders.columns = ["date", "count", "change"]
                # Compute cumulative change rate
                holders["cum_change_pct"] = holders["change"].astype(float).rolling(4).sum()
                result["holders"] = holders.tail(24).to_dict(orient="records")
        except Exception:
            pass

        # --- 换手率趋势 (turnover patience) ---
        try:
            orch = _get_orchestrator()
            df = orch._storage.get_daily_data(code)
            if df:
                import pandas as pd
                daily_df = pd.DataFrame([d.model_dump() for d in df])
                daily_df = daily_df.sort_values("date")
                recent = daily_df.tail(120)
                result["turnover"] = [
                    {"date": str(r["date"]), "value": r.get("turnover") or 0}
                    for _, r in recent.iterrows()
                ]
        except Exception:
            pass

        # --- 董秘回复活跃度 (IRM activity by month) ---
        try:
            irm = ak.stock_irm_cninfo(symbol=code)
            if irm is not None and not irm.empty:
                # Count questions by month
                irm["month"] = irm["提问时间"].astype(str).str[:7]
                monthly = irm.groupby("month").size().reset_index(name="count")
                # Answer rate
                answered = irm[irm["回答内容"].notna()].shape[0]
                total = irm.shape[0]
                result["irm_rate"] = f"{answered}/{total}" if total > 0 else "0/0"
                result["irm_monthly"] = monthly.tail(12).to_dict(orient="records")
        except Exception:
            pass

    except Exception as e:
        result["error"] = str(e)

    return JSONResponse(result)


@app.get("/api/v1/stocks/{code}/platform")
async def platform_data(code: str):
    """Cross-platform info: fund flow, hot ranking, Xueqiu followers."""
    result: dict = {}
    try:
        import akshare as ak
        from src.utils.helpers import determine_market
        try:
            market = determine_market(code)
            flow = ak.stock_individual_fund_flow(stock=code, market=market)
            if flow is not None and not flow.empty:
                latest = flow.iloc[-1]
                result["fund_flow_date"] = str(latest.get("日期", ""))
                result["main_net_inflow"] = str(latest.get("主力净流入-净额", latest.iloc[-1]))
                recent = flow.tail(5)
                try:
                    total_main = recent.iloc[:, 2].astype(float).sum() / 1e8
                    result["main_5d_net"] = f"{total_main:.2f}亿"
                except Exception:
                    pass
        except Exception:
            pass
        try:
            hot = ak.stock_hot_rank_em()
            if hot is not None and not hot.empty:
                match = hot[hot["代码"] == code]
                result["em_hot_rank"] = str(match.iloc[0].get("排名", match.iloc[0, 0])) if not match.empty else "未上榜"
        except Exception:
            pass
        try:
            symbol_map = {"sh": f"SH{code}", "sz": f"SZ{code}", "bj": f"BJ{code}"}
            market = determine_market(code)
            xq_symbol = symbol_map.get(market, f"SZ{code}")
            xq = ak.stock_hot_follow_xq(symbol=xq_symbol)
            if xq is not None and not xq.empty:
                result["xq_followers"] = str(xq.iloc[0, 0])
        except Exception:
            pass
    except Exception as e:
        result["error"] = str(e)
    return JSONResponse(result)


@app.get("/api/v1/stocks/{code}/research")
async def stock_research(code: str, limit: int = Query(10, ge=1, le=50)):
    """Return recent research reports for a stock."""
    try:
        import akshare as ak
        df = ak.stock_research_report_em(symbol=code)
        if df is None or df.empty:
            return JSONResponse([])
        df = df.head(limit)
        results = []
        for _, row in df.iterrows():
            results.append({
                "date": str(row.get("日期", "")),
                "org": str(row.get("评级机构", "")),
                "title": str(row.get("报告名称", "")),
                "rating": str(row.get("评级", "")),
                "industry": str(row.get("行业", "")),
            })
        return JSONResponse(results)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/v1/stocks/{code}/news")
async def stock_news(code: str, limit: int = Query(10, ge=1, le=50)):
    """Return recent news for a stock."""
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        if df is None or df.empty:
            return JSONResponse([])
        df = df.head(limit)
        results = []
        for _, row in df.iterrows():
            results.append({
                "time": str(row.get("发布时间", df.columns[0] if len(df.columns) > 0 else "")),
                "title": str(row.get("标题", df.columns[1] if len(df.columns) > 1 else "")),
                "url": str(row.get("新闻链接", df.columns[2] if len(df.columns) > 2 else "")),
            })
        return JSONResponse(results)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web:app", host="127.0.0.1", port=8000, reload=True)
