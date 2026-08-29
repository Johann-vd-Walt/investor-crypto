"""Rule-based strategy auditor.

Examines the current settings, a fresh momentum backtest (Deflated Sharpe +
benchmark), and the bot's real/paper track record, and returns honest findings
and suggestions. It applies sound principles and the app's own honesty metrics —
it does NOT invent alpha or promise edge. Most of the time its honest verdict is
"no established edge; buy-and-hold is the baseline".
"""

from __future__ import annotations

from sqlalchemy import select  # noqa: F401  (kept for parity with repo style)

from app.bot import performance as bot_perf
from app.repositories import macro as macro_repo
from app.repositories import prices as prices_repo
from app.repositories import securities as securities_repo
from app.services import settings as settings_service
from app.signals import backtest as bt
from app.signals import robustness as rob

_ORDER = {"critical": 0, "warn": 1, "good": 2, "info": 3}


def audit(db) -> dict:
    s = settings_service.get_effective_settings(db)
    findings: list[dict] = []

    def add(severity: str, title: str, detail: str, suggestion: str | None = None) -> None:
        findings.append({"severity": severity, "title": title, "detail": detail, "suggestion": suggestion})

    # --- config sanity ---
    wsum = s.weight_technical + s.weight_macro + s.weight_sentiment + s.weight_momentum + s.weight_flow
    if abs(wsum - 1.0) > 0.05:
        add("warn", "Layer weights don't sum to ~1", f"They total {wsum:.2f}. The engine renormalises, "
            "but keep them clean so the blend is what you intend.", "Adjust weights to total 1.00 on the Strategy tab.")
    if s.weight_flow > 0.2:
        add("warn", "Heavy weight on real-time flow", f"weight_flow = {s.weight_flow}. Flow is "
            "unbacktestable and chasing movers often buys the top right before it reverses.",
            "Lower weight_flow to ≤0.1, or 0 to ignore real-time flow.")
    if s.buy_threshold < 0.15:
        add("warn", "Low buy threshold", f"buy_threshold = {s.buy_threshold} fires many weak BUYs — "
            "more trades, more fees, lower quality.", "Raise it toward 0.3 for fewer, stronger signals.")
    if float(s.brokerage_pct + s.slippage_pct) < 0.1:
        add("critical", "Unrealistically low costs", f"Total per-side cost is "
            f"{float(s.brokerage_pct + s.slippage_pct)}% — that flatters every backtest.",
            "Use ≥0.1%/side (real taker + slippage) so results stay honest.")
    if float(s.risk_per_trade_pct) > 2:
        add("warn", "Aggressive risk per trade", f"{s.risk_per_trade_pct}% risk per trade is high; a "
            "losing streak compounds fast.", "1% is the typical/conservative default.")

    # --- performance: fresh momentum backtest with current settings ---
    metrics = None
    ids = prices_repo.security_ids_with_bars(db)
    bars = {}
    for i in ids:
        sec = securities_repo.get_by_id(db, i)
        if sec:
            b = prices_repo.get_bars(db, security_id=i)
            if len(b) >= 2:
                bars[sec.ticker] = b
    res = bt.momentum_portfolio_backtest(bars, settings=s, top_k=10, rebalance_days=21)
    if res.full.n_rebalances > 0:
        r = rob.robustness(res.full.returns, trials=1)
        starts = [b[0].bar_datetime.date() for b in bars.values() if b]
        ends = [b[-1].bar_datetime.date() for b in bars.values() if b]
        btc_pct = None
        if starts and ends:
            btc = macro_repo.get_series(db, series_code="BTC", start=min(starts), end=max(ends))
            if len(btc) >= 2 and float(btc[0].value) != 0:
                btc_pct = (float(btc[-1].value) / float(btc[0].value) - 1.0) * 100.0
        tot = res.full.total_return_pct
        dsr = r["deflated_sharpe"]
        metrics = {
            "total_return_pct": tot, "sharpe": res.full.sharpe, "psr": r["psr"],
            "deflated_sharpe": dsr, "btc_buyhold_pct": btc_pct, "rebalances": res.full.n_rebalances,
        }
        if dsr is not None and dsr < 0.95:
            add("critical", "Edge not statistically established", f"Deflated Sharpe is {dsr*100:.0f}% "
                "(<95%). After accounting for sample size, the momentum edge is indistinguishable from luck.",
                "Don't trust the backtest return; keep live size tiny — or don't trade it.")
        elif dsr is not None:
            add("good", "Edge is statistically plausible", f"Deflated Sharpe {dsr*100:.0f}% — the edge "
                "clears the bar on this window. Still re-check the walk-forward on the Backtest page.", None)
        if btc_pct is not None and tot is not None and tot < btc_pct:
            add("critical", "Buy-and-hold beat the strategy", f"Strategy returned {tot:.0f}% vs simply "
                f"holding BTC {btc_pct:.0f}% over the window.",
                "The honest baseline is holding BTC — beat it before risking real money.")
    else:
        add("info", "Not enough data to backtest", "The momentum backtest produced no rebalances "
            "(insufficient price history). Let the ingester run, then re-audit.", None)

    # --- bot track record (real preferred) ---
    live = bot_perf.venue_stats(db, "luno")
    paper = bot_perf.venue_stats(db, "paper")
    if live["sample"] >= 10 and live["win_rate"] is not None and live["win_rate"] < 0.5:
        add("critical", "Live (Luno) track record is losing", f"{live['wins']}/{live['sample']} wins, "
            f"total P&L ${live['total_pnl']:.2f}.", "Reduce size or stop live trading — real results confirm no edge.")
    elif paper["sample"] >= 10 and paper["win_rate"] is not None and paper["win_rate"] < 0.45:
        add("warn", "Paper win-rate is weak", f"{paper['wins']}/{paper['sample']} wins in paper trading.",
            "Improve/validate the strategy before going live.")

    if not any(f["severity"] in ("critical", "warn") for f in findings):
        add("info", "No red flags found", "Config looks sane and the backtest didn't trip the honesty "
            "checks on this data — but no edge is ever guaranteed.", None)

    findings.sort(key=lambda f: _ORDER.get(f["severity"], 9))
    return {"findings": findings, "metrics": metrics}
