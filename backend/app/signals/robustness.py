"""Backtest honesty metrics (Tier 3): Probabilistic & Deflated Sharpe.

The point of these is not to promise edge — it's to tell you whether an observed
edge is real or an artefact of a short sample and of trying many configurations.

- Sharpe (per-trade): mean/stdev of trade returns (scale-invariant).
- PSR  : Probabilistic Sharpe Ratio — P(true Sharpe > 0) given sample size,
         skew and kurtosis (Bailey & López de Prado). Non-normal returns are
         handled honestly; fat left tails lower it.
- DSR  : Deflated Sharpe — PSR measured against the Sharpe you'd EXPECT to get
         by luck alone after trying ``trials`` configurations. If you tuned the
         strategy across many settings, DSR is the number that matters.

Pure functions, no heavy deps (no scipy). The trial-dispersion used by DSR is
approximated by the Sharpe estimator's standard error — a documented
simplification when the full set of trial Sharpes isn't tracked.
"""

from __future__ import annotations

import math
from statistics import mean, pstdev

_EULER = 0.5772156649015329


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's algorithm). p in (0,1)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _std_moment(x: list[float], k: int) -> float:
    m, sd = mean(x), pstdev(x)
    if sd == 0:
        return 0.0
    return mean(((xi - m) / sd) ** k for xi in x)


def sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    sd = pstdev(returns)
    return (mean(returns) / sd) if sd > 0 else None


def _psr(returns: list[float], sr: float, sr_star: float) -> float | None:
    n = len(returns)
    if n < 3:
        return None
    g3 = _std_moment(returns, 3)
    g4 = _std_moment(returns, 4)  # non-excess kurtosis (normal -> 3)
    denom = 1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr * sr
    if denom <= 0:
        return None
    z = ((sr - sr_star) * math.sqrt(n - 1)) / math.sqrt(denom)
    return _norm_cdf(z)


def robustness(returns: list[float], *, trials: int = 1) -> dict:
    """Return {sharpe, psr, deflated_sharpe, sr0, trials, n, note}."""
    n = len(returns)
    out = {"sharpe": None, "psr": None, "deflated_sharpe": None,
           "sr0": None, "trials": trials, "n": n, "note": ""}
    sr = sharpe(returns)
    if sr is None or n < 3:
        out["note"] = "Too few trades for a reliable robustness estimate (need >=3)."
        return out
    out["sharpe"] = sr
    out["psr"] = _psr(returns, sr, 0.0)

    # Deflated benchmark: expected max Sharpe under the null across `trials`.
    g3 = _std_moment(returns, 3)
    g4 = _std_moment(returns, 4)
    var_sr = (1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr * sr) / (n - 1)
    if trials and trials > 1 and var_sr > 0:
        K = float(trials)
        sr0 = math.sqrt(var_sr) * (
            (1 - _EULER) * _norm_ppf(1 - 1.0 / K) + _EULER * _norm_ppf(1 - 1.0 / (K * math.e))
        )
    else:
        sr0 = 0.0
    out["sr0"] = sr0
    out["deflated_sharpe"] = _psr(returns, sr, sr0)
    out["note"] = (
        f"Per-trade Sharpe {sr:.2f}. PSR = P(true Sharpe>0) = "
        f"{(out['psr'] or 0)*100:.0f}%. Deflated for {trials} trial(s): "
        f"{(out['deflated_sharpe'] or 0)*100:.0f}%. Treat <95% as not established."
    )
    return out
