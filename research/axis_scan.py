# -*- coding: utf-8 -*-
"""**축 스캔** — 보유 재료를 **하나씩**(조합 없이) 줄 세워 계단이 깔끔한지만 본다 (2026-09-19).

왜 조합이 아니라 한 축씩인가: 55개 항목 × 문턱 × 보유기간을 섞으면 수백만 칸이 되고 운으로 좋아 보이는
조합이 수백 개 나온다(상승장 1만2천 셀 탐색에서 1개 채택). 한 축을 10등분해서 **1→10 으로 갈수록
수익이 계단처럼 한 방향으로 변하는지**는 우연으로 잘 안 나온다. 계단이 나온 축만 이유를 붙여
명세(run_spec.py)로 넘긴다.

방법
  · 그날의 유니버스(거래대금 상위 40% · 1,000원↑ · 우선주 제외) 안에서 재료를 **날짜별 10등분**
    (0 이 30%↑ 인 희소 재료는 0 / 음수 3구간 / 양수 3구간)
  · 각 칸의 5일·20일 뒤 수익 **중앙값**(익일 시가 매수·비용 차감, 패널 n5·n20) — 행 단위, 중복 제거 없음
  · 전체 / 하락장(코스피 60일선 아래) 따로 — 우리 규칙이 버는 곳이 하락장이다
  · 계단 판정: 학습(2016~22) 순위상관 |ρ| ≥ 0.8 · 검증(2023~) 같은 방향 |ρ| ≥ 0.5 ·
               해마다 양 끝 차이의 방향이 같은 해 70%↑
  · 계단이면 좋은 쪽 끝의 **절대 수익**(학습·검증 중앙 둘 다 > 0)을 따로 본다 — 음수면 매수 규칙은 못 되고
    '회피 신호' 후보다. 유니버스 대비 초과는 안 본다([[goal-not-beating-index]]).

돌린 칸(재료 × 보유 × 국면 × 칸 수)은 전부 trials.json 에 적는다.

    python research/axis_scan.py            → research/reports/axis_scan_YYYYMMDD.md
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import features as FT
from verdict import log_trials

TR0, TR1, VA0 = "20160101", "20221231", "20230101"
HOLDS = (5, 20)
OUT = []


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def regime_down():
    cp = ROOT / "cache" / "ks11.pkl"
    cp.parent.mkdir(exist_ok=True)
    if cp.exists() and time.time() - cp.stat().st_mtime < 86400:
        IX = pd.read_pickle(cp)
    else:
        import FinanceDataReader as fdr
        IX = fdr.DataReader("KS11", "2004-06-01")[["Close"]]
        IX.to_pickle(cp)
    IX = IX.copy()
    IX["ma60"] = IX.Close.rolling(60).mean()
    IX["date"] = IX.index.strftime("%Y%m%d")
    return dict(zip(IX.date, IX.Close < IX.ma60))           # True = 하락장(portfolio.py dn60 과 같은 정의)


def buckets(df, col):
    """날짜별 10등분. 0 이 30%↑ 이면 0 / 음수 3 / 양수 3 구간(전체 분위)."""
    x = df[col]
    nz = x.dropna()
    if len(nz) and (nz == 0).mean() >= 0.30:
        b = pd.Series(np.nan, index=x.index)
        b[x == 0] = 0
        pos = x[x > 0]; neg = x[x < 0]
        if len(pos) >= 30:
            b[pos.index] = pd.qcut(pos.rank(method="first"), 3, labels=[1, 2, 3]).astype(float)
        if len(neg) >= 30:
            b[neg.index] = pd.qcut(neg.rank(method="first"), 3, labels=[-3, -2, -1]).astype(float)
        return b, "희소"
    r = x.groupby(df.date).rank(pct=True)
    cnt = x.groupby(df.date).transform("count")
    b = np.ceil(r * 10).clip(1, 10)
    b[cnt < 50] = np.nan
    return b, "10등분"


def spear(a, b):
    s = pd.Series(a).rank(); t = pd.Series(b).rank()
    return float(np.corrcoef(s, t)[0, 1]) if len(s) >= 3 and s.std() > 0 and t.std() > 0 else np.nan


def scan_one(df, col, h):
    c = "n%d" % h
    z = df[[col, "date", c]].dropna()
    if len(z) < 3000:
        return None
    z = z.assign(b=buckets(z, col)[0]).dropna(subset=["b"])
    tr = z[(z.date >= TR0) & (z.date <= TR1)]; va = z[z.date >= VA0]
    if len(tr) < 2000 or len(va) < 500:
        return None
    mt = tr.groupby("b")[c].median(); mv = va.groupby("b")[c].median()
    ks = [k for k in mt.index if k in mv.index]
    if len(ks) < 4:
        return None
    rt = spear(ks, mt[ks].values); rv = spear(ks, mv[ks].values)
    lo, hi = min(ks), max(ks)
    good, bad = (hi, lo) if rt > 0 else (lo, hi)
    z["yr"] = z.date.str[:4]
    ends = z[z.b.isin([lo, hi])]
    yy = ends.groupby(["yr", "b"])[c].agg(["median", "size"]).reset_index()
    cons = []
    for y, g in yy.groupby("yr"):
        if len(g) == 2 and g["size"].min() >= 20:
            m = dict(zip(g.b, g["median"]))
            cons.append(np.sign(m[hi] - m[lo]) == np.sign(rt))
    cons = float(np.mean(cons)) if cons else np.nan
    stair = (abs(rt) >= 0.8 and np.sign(rv) == np.sign(rt) and abs(rv) >= 0.5 and cons >= 0.7)
    return dict(rt=rt, rv=rv, cons=cons, ny=len(cons) if isinstance(cons, list) else yy.yr.nunique(),
                g_tr=mt[good], g_va=mv[good], b_tr=mt[bad], b_va=mv[bad], all_tr=tr[c].median(),
                all_va=va[c].median(), n=len(z), kb=len(ks), stair=stair,
                buy=stair and mt[good] > 0 and mv[good] > 0,
                curve_tr=[round(mt[k], 2) for k in ks], keys=ks, good=good)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    log("국내 패널")
    A = pd.read_pickle(BASE / "data/kr_scan.pkl")
    A = A[((A.close >= 1000) & (~A.pref.fillna(False))).fillna(False)]
    A = A.sort_values(["ticker", "date"]).reset_index(drop=True)
    uni = (A.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
    cal = sorted(A.date.unique())
    A = A[uni & (A.date >= TR0)].reset_index(drop=True)          # 먼저 거르고 붙인다(메모리)
    log("재료 붙이는 중")
    cols = FT.attach(A, cal=cal)
    down = A.date.map(regime_down()).fillna(False).astype(bool)
    log("붙인 재료 %d개 · 스캔 행 %s" % (len(cols), f"{len(A):,}"))

    rows = []; cells = 0
    for col in cols:
        for h in HOLDS:
            for reg, m in (("전체", slice(None)), ("하락장", down.values)):
                r = scan_one(A.loc[m], col, h)
                if r is None:
                    continue
                cells += r["kb"]
                rows.append(dict(col=col, h=h, reg=reg, **r))
        log("  %-10s 끝" % col)

    R = pd.DataFrame(rows)
    P("# 축 스캔 · 국내 · %s" % time.strftime("%Y-%m-%d"))
    P("")
    P("재료 %d개 × 보유 %s × 국면(전체·하락장) — 계단 판정: 학습 |ρ|≥0.8 · 검증 같은 방향 |ρ|≥0.5 · 해마다 같은 방향 70%%↑."
      % (len(cols), "/".join("%d일" % h for h in HOLDS)))
    P("좋은 쪽 = 계단의 수익이 높은 끝. **매수 후보**는 좋은 쪽 절대 수익이 학습·검증 둘 다 양수, "
      "**회피 후보**는 계단이지만 좋은 쪽도 음수(나쁜 쪽을 피하는 데만 쓸모).")
    P("")
    for title, sub in (("매수 후보", R[R.buy]), ("회피 후보(계단이나 절대수익 음수)", R[R.stair & ~R.buy])):
        P("## %s — %d개" % (title, len(sub)))
        if not len(sub):
            P("없음"); P(""); continue
        P("| 재료 | 설명 | 보유 | 국면 | ρ학습 | ρ검증 | 같은방향해 | 좋은쪽 학습/검증 | 나쁜쪽 학습/검증 | 칸별 학습 중앙 |")
        P("|---|---|---|---|---|---|---|---|---|---|")
        for _, r in sub.sort_values("rt", key=abs, ascending=False).iterrows():
            P("| %s | %s | %d일 | %s | %+.2f | %+.2f | %.0f%% | %+.2f / %+.2f | %+.2f / %+.2f | %s |" % (
                r.col, FT.DESC[r.col][1], r.h, r.reg, r.rt, r.rv, r.cons * 100, r.g_tr, r.g_va,
                r.b_tr, r.b_va, " ".join("%+.1f" % v for v in r.curve_tr)))
        P("")
    P("## 전체 (|ρ학습| 순)")
    P("| 재료 | 보유 | 국면 | ρ학습 | ρ검증 | 같은방향해 | 좋은쪽 학습/검증 | 전체 학습/검증 | 계단 |")
    P("|---|---|---|---|---|---|---|---|---|")
    for _, r in R.sort_values("rt", key=abs, ascending=False).iterrows():
        P("| %s | %d일 | %s | %+.2f | %+.2f | %s | %+.2f / %+.2f | %+.2f / %+.2f | %s |" % (
            r.col, r.h, r.reg, r.rt, r.rv, ("%.0f%%" % (r.cons * 100)) if r.cons == r.cons else "-",
            r.g_tr, r.g_va, r.all_tr, r.all_va, "매수" if r.buy else ("회피" if r.stair else "")))
    P("")
    P("돌린 칸 %d개(재료×보유×국면×칸) · %.0f초" % (cells, time.time() - t0))
    log_trials("axis_scan_kr_%s" % time.strftime("%Y%m%d"), cells)
    rp = ROOT / "reports" / ("axis_scan_%s.md" % time.strftime("%Y%m%d"))
    rp.parent.mkdir(exist_ok=True)
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT[:60]))
    print("\n보고서: %s" % rp)


if __name__ == "__main__":
    main()
