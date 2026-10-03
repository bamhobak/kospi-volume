# -*- coding: utf-8 -*-
"""공개 GitHub 매매 규칙 실측용 공용 틀 (2026-10-04, 사용자: "공개 깃헙 단타·스윙 규칙 실측").

규칙 하나 = 진입 조건(그날 종가까지 아는 값) + 진입 가격 + 청산 방식. 같은 잣대로 잰다:
  - 유니버스: 20일 평균 거래대금 상위 40% (우리 규칙과 같음) · 국장 1,000원↑·우선주 제외 · 미장 $3↑
  - 비용: 스윙 = 패널 cost(우리 규칙과 같은 보수적 왕복: 국장 0.35~1.15% · 미장 0.10~0.60%) · 데이 = 국장 0.30% · 미장 0.25%
  - 같은 종목은 보유 중 재신호 무시
  - 구간: 학습 2016~22 · 검증 2023~ · 참고 2005~15 — 건당 평균·중앙·승률·PF·해별 플러스, 같은 날 같은 보유 '아무 종목' 대비 초과
청산 방식:
  hold(H)              — 진입 후 H거래일째 종가(진입일 = 1일째)
  nextopen             — 다음날 시가(변동성 돌파류)
  sameclose            — 같은 날 종가(장중 진입 → 종가 청산)
  cond(mask, maxh)     — 보유 중 mask 가 참인 날 다음날 시가(최대 maxh 일, 그 뒤엔 종가)
  stop/target(%)       — 장중 고저로 판정(같은 날 둘 다 닿으면 손절 먼저 — 보수적)
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import run_spec as R

DAYCOST = {"KR": 0.30, "US": 0.25}
PER = (("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231"), ("참고 05~15", "20050101", "20151231"))


def load_us_full():
    """미장 **폐지 포함** 패널(us_full_2007 · 2007~) — us_scan 은 살아남은 종목만이라 '빠진 종목 사기' 규칙이 부푼다(2026-10-04 확인:
    us_scan 5,983종목 중 폐지 4 · full 13,151종목 중 6,061). 가격은 수정주가 px 기준으로 맞춘다."""
    F = pd.read_pickle(BASE / "data" / "us_full_2007.pkl").sort_values(["ticker", "date"]).reset_index(drop=True)
    f = (F.px / F.rawclose).replace([np.inf, -np.inf], np.nan)
    A = pd.DataFrame({"ticker": F.ticker, "date": F.date, "close": F.px, "high": F.high * f, "low": F.low * f, "volume": F.volume,
                      "amt20": F.amt20, "cost": F.cost, "PBR": F.PBR, "marcap": F.marcap, "rawclose": F.rawclose})
    for n in (5, 10, 20, 40, 60): A["n%d" % n] = F["n%d" % n]
    A["open"] = F.groupby("ticker").buy.shift(1)              # buy = 다음날 시가(수정) → 오늘 시가
    A["high"] = np.maximum(A.high, np.maximum(A.open.fillna(A.close), A.close)); A["low"] = np.minimum(A.low, np.minimum(A.open.fillna(A.close), A.close))
    A = A[A.rawclose >= 3].reset_index(drop=True)
    A["uni"] = (A.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False).to_numpy()
    keep = set(A.ticker[A.uni])                               # 한 번도 유니버스에 안 든 종목은 계산할 필요가 없다(메모리)
    A = A[A.ticker.isin(keep)].reset_index(drop=True)
    for c in A.columns:
        if A[c].dtype == np.float64: A[c] = A[c].astype(np.float32)
    A["ret5"] = (A.close / A.groupby("ticker").close.shift(5) - 1) * 100
    A["vol20"] = A.groupby("ticker").close.transform(lambda s: s.pct_change().rolling(20).std() * 100)
    return A


def load(mk, full=False):
    if mk == "US" and full:
        A = load_us_full()
    else:
        A, uni, since = R.load_market(mk)               # load_market 이 이미 (종목, 날짜) 순으로 정렬해 둔다 — uni 는 그 순서
        A["uni"] = np.asarray(uni, dtype=bool)
    g = A.groupby("ticker", sort=False)
    A["pc"] = g.close.shift(1); A["ph"] = g.high.shift(1); A["pl"] = g.low.shift(1); A["po"] = g.open.shift(1)
    A["vol"] = A.volume
    for n in (3, 5, 10, 20, 50, 60, 120, 200):
        A["ma%d" % n] = g.close.transform(lambda s: s.rolling(n, min_periods=n).mean())
    # RSI(14, Wilder) · RSI(2)
    d = g.close.diff()
    for n in (2, 14):
        up = d.clip(lower=0).groupby(A.ticker).transform(lambda s: s.ewm(alpha=1 / n, adjust=False).mean())
        dn = (-d.clip(upper=0)).groupby(A.ticker).transform(lambda s: s.ewm(alpha=1 / n, adjust=False).mean())
        A["rsi%d" % n] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    # 볼린저(20, 2)
    sd = g.close.transform(lambda s: s.rolling(20, min_periods=20).std())
    A["bbu"] = A.ma20 + 2 * sd; A["bbl"] = A.ma20 - 2 * sd
    A["hh20"] = g.high.transform(lambda s: s.rolling(20).max()); A["ll10"] = g.low.transform(lambda s: s.rolling(10).min())
    A["hh55"] = g.high.transform(lambda s: s.rolling(55).max()); A["ll20"] = g.low.transform(lambda s: s.rolling(20).min())
    A["vma20"] = g.volume.transform(lambda s: s.rolling(20).mean())
    A["ret1"] = (A.close / A.pc - 1) * 100
    A["di"] = g.cumcount()
    return A


def _arr(A, c):
    return A[c].to_numpy(dtype=float)


def simulate(A, sig, mk, entry="nextopen_buy", exit="hold", H=5, exit_mask=None, maxh=60, stop=None, target=None,
             entry_px=None, day=False):
    """sig: 진입 신호(bool, 행 기준). entry:
         'nextopen_buy' — 신호 다음날 시가 매수(스윙 기본)
         'intraday'     — 신호가 난 그날 entry_px(배열)에 매수(돌파형). sig 는 그날 장중에 닿았는지까지 포함해야 한다.
       exit: 'hold' | 'nextopen' | 'sameclose' | 'cond'"""
    tk = A.ticker.to_numpy(); dt = A.date.to_numpy()
    O, Hh, L, C = _arr(A, "open"), _arr(A, "high"), _arr(A, "low"), _arr(A, "close")
    cost = (np.full(len(A), DAYCOST[mk]) if day else _arr(A, "cost"))
    em = exit_mask.to_numpy() if exit_mask is not None else None
    ex_px = entry_px.to_numpy(dtype=float) if entry_px is not None else None
    sig = sig.fillna(False).to_numpy(dtype=bool) & A.uni.to_numpy(dtype=bool)
    idx = np.flatnonzero(sig)
    # 종목 경계
    start = np.r_[0, np.flatnonzero(tk[1:] != tk[:-1]) + 1]; end = np.r_[start[1:], len(A)]
    bnd_end = np.empty(len(A), dtype=np.int64)
    for s, e in zip(start, end): bnd_end[s:e] = e
    out = []; busy_until = {}
    for i in idx:
        t = tk[i]
        if busy_until.get(t, -1) >= i: continue
        e_end = bnd_end[i]
        if entry == "nextopen_buy":
            j = i + 1
            if j >= e_end or not np.isfinite(O[j]): continue
            px = O[j]; d0 = j
        else:
            px = ex_px[i]; d0 = i
            if not np.isfinite(px): continue
        # 청산
        k = None; xp = np.nan
        if exit == "sameclose":
            k = d0; xp = C[d0]
        elif exit == "nextopen":
            k = d0 + 1
            if k >= e_end: continue
            xp = O[k]
        else:
            last = min(d0 + (H if exit == "hold" else maxh) - 1, e_end - 1)
            for m in range(d0, last + 1):
                lo_hit = stop is not None and L[m] <= px * (1 - stop / 100)
                hi_hit = target is not None and Hh[m] >= px * (1 + target / 100)
                if lo_hit:
                    k = m; xp = min(px * (1 - stop / 100), O[m] if m > d0 else px * (1 - stop / 100)); break
                if hi_hit:
                    k = m; xp = max(px * (1 + target / 100), O[m]) if m > d0 else px * (1 + target / 100); break
                if exit == "cond" and m > d0 and em is not None and em[m]:
                    if m + 1 < e_end: k = m + 1; xp = O[m + 1]
                    else: k = m; xp = C[m]
                    break
            if k is None:
                if exit == "hold" and d0 + H - 1 >= e_end: continue          # 보유가 안 끝났다
                k = last; xp = C[last]
        if not (np.isfinite(xp) and xp > 0 and px > 0): continue
        r = (xp / px - 1) * 100 - cost[i]
        out.append((dt[i], t, r, k - d0 + 1))
        busy_until[t] = k
    Y = pd.DataFrame(out, columns=["date", "ticker", "r", "days"])
    Y["r"] = Y.r.clip(-95, 400)
    return Y


def bench(A, H):
    """같은 날 유니버스 아무 종목을 다음날 시가에 사서 H일 보유(비용 뺀) 중앙 — 초과 잣대."""
    c = "n%d" % H if ("n%d" % H) in A.columns else None
    if c is None: return None
    return A[A.uni].dropna(subset=[c]).groupby("date")[c].median()


def report(Y, lab, bm=None):
    rows = []
    for nm, a, b in PER:
        z = Y[(Y.date >= a) & (Y.date <= b)]
        if len(z) < 30:
            rows.append(None); continue
        yr = z.groupby(z.date.str[:4]).r.mean()
        ex = (z.r - z.date.map(bm)).median() if bm is not None else np.nan
        pf = z.r[z.r > 0].sum() / max(-z.r[z.r < 0].sum(), 1e-9)
        rows.append(dict(n=len(z), m=z.r.mean(), med=z.r.median(), win=(z.r > 0).mean() * 100, pf=pf, ex=ex, yp=(yr > 0).sum(), ny=len(yr),
                         perm=len(z) / max(z.date.str[:6].nunique(), 1), days=z.days.mean()))
    tr, va = rows[0], rows[1]
    ok = bool(tr and va and tr["m"] > 0 and va["m"] > 0 and tr["med"] > 0 and tr["yp"] / tr["ny"] >= 0.6
              and (np.isnan(tr["ex"]) or tr["ex"] > 0) and (np.isnan(va["ex"]) or va["ex"] > 0))
    return dict(lab=lab, rows=rows, ok=ok)


def fmt(s):
    if not s: return "-"
    ex = "" if np.isnan(s["ex"]) else " · 초과 %+.2f" % s["ex"]
    return "%d건 · 평균 %+.2f · 중앙 %+.2f · 승률 %.0f%% · PF %.2f%s · %d/%d해 · 평균 %.0f일" % (
        s["n"], s["m"], s["med"], s["win"], s["pf"], ex, s["yp"], s["ny"], s["days"])


def ew_index(A):
    """유니버스 동일가중 일간 지수(종가→종가) — 조건 청산처럼 보유 기간이 제각각인 규칙의 '같은 기간 시장' 잣대."""
    r = (A.close / A.pc - 1).where(A.uni).clip(-0.5, 1.0)
    d = r.groupby(A.date).mean().fillna(0)
    return (1 + d).cumprod()


def add_excess(Y, A, idx):
    """거래마다 같은 기간 유니버스 동일가중 수익을 빼 초과(%p)를 붙인다. 진입일 전날 종가 → 청산일 종가로 근사."""
    dates = idx.index.to_numpy(); pos = {d: i for i, d in enumerate(dates)}
    v = idx.to_numpy()
    ex = []
    for d, n in zip(Y.date, Y.days):
        i = pos.get(d)
        if i is None or i + n >= len(v): ex.append(np.nan); continue
        ex.append((v[min(i + n, len(v) - 1)] / v[i] - 1) * 100)
    Y = Y.copy(); Y["mkt"] = ex; Y["ex"] = Y.r - Y.mkt
    return Y
