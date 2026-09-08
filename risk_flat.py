# -*- coding: utf-8 -*-
"""균등 비중 리스크 곡선 — 사용자의 **실제 방식**으로 다시 잰다.

risk_curve.py 는 portfolio.py 의 규칙별 비중(P1 12 / P2 15 / P3 5 / P4 3 / P5 5 /
P6 4 / P7 4 / D1 5 / D2 5)을 전제로 계산한다. 그러나 사용자는 2026-09 부터 실전에서
**종목당 300만원 균등**으로 거래하고 있다. 비중이 다르면 낙폭도 배수도 달라지므로
그 숫자를 그대로 쓰면 안 된다.

여기서는 종목당 비중 w 를 계좌의 몇 %로 볼지에 따라 나눠 잰다.
  · w 가 작으면 안전하지만 자본이 놀고, 크면 수익이 커지는 대신 낙폭이 깊어진다.
  · 300만원이 계좌의 몇 % 인지에 따라 자기 위치를 찾으면 된다.
    예) 계좌 3,000만원이면 w=10%, 6,000만원이면 w=5%.

⚠ 균등 비중은 **모델보다 자리를 많이 쓴다**. 자리 상한 합이 34개라 최악의 경우
   34 × w 만큼 투입된다(w=10% 면 340%). 그래서 '동시 보유 상한' 을 같이 잰다 —
   현금이 모자라 못 사는 상황이 실제로 얼마나 자주 생기는지.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
SEEDS = 24
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, TRAIL = ns["KP"], ns["KQ"], ns["RULES"], ns["TRAIL"]
adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}


def signals():
    out = []
    for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
        g = K.groupby("ticker", sort=False)
        C = np.column_stack([g.close.shift(-i).values for i in range(1, hold + 1)])
        buy = K.buy.values
        t = TRAIL.get(rid)
        hit = np.zeros_like(C, dtype=bool); px = C.copy()
        if t:
            run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
            h = C <= run * (1 - t); hit |= h
            px = np.where(h & ~np.isnan(C), run * (1 - t), px)
        elif stop:
            h = C <= buy[:, None] * (1 - stop); hit |= h
            px = np.where(h, buy[:, None] * (1 - stop), px)
        ok = hit.any(axis=1)
        first = np.where(ok, hit.argmax(axis=1), hold - 1)
        exit_px = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
        m = cond.fillna(False).values
        X = K[m].copy()
        X["exit"] = exit_px[m]; X["hold"] = (first + 1)[m]
        X["rid"] = rid; X["mx"] = mx
        X["ret"] = (X.exit / X.buy - 1) * 100 - X.cost
        X = X.dropna(subset=["ret"])
        X = X[X.buy > 0]
        out.append(X[["date", "ticker", "name", "hold", "rid", "mx", "ret"]])
    S = pd.concat(out, ignore_index=True)
    S["di"] = S.date.map(ADI)
    return S.dropna(subset=["di"]).sort_values("di").reset_index(drop=True)


S = signals()
MX = {rid: RULES[rid][4] for rid in RULES}
print(f"자리 상한 합 {sum(MX.values())}개 (규칙별: " +
      " ".join(f"{k}:{v}" for k, v in MX.items()) + ")\n")


def run(ds, seed, w, cash_cap=1.0):
    """종목당 비중 w(계좌 대비 %)로 균등 투입. 현금이 모자라면 못 산다."""
    rng = np.random.default_rng(seed)
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    curve = []
    blocked = taken = 0
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            v = held.pop(k)
            nav *= 1 + v[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        curve.append((d, nav, len(held)))
        g = byd.get(d)
        if g is None:
            continue
        for r in g.sample(frac=1, random_state=int(rng.integers(1 << 30))).itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            if (len(held) + 1) * w / 100 > cash_cap:      # 현금 부족
                blocked += 1
                continue
            held[k] = (di + int(r.hold), r.ret * w / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
            taken += 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    C = pd.DataFrame(curve, columns=["date", "nav", "n"])
    return C, blocked, taken


def stats(C):
    v = C.nav.values
    pk = np.maximum.accumulate(v)
    dd = float((v / pk - 1).min() * 100)
    b = c = 0
    for u in (v < pk):
        c = c + 1 if u else 0
        b = max(b, c)
    return v[-1], dd, b


for lab, lo in (("전구간 2005~26", "20050101"), ("2016~26", "20160101")):
    ds = [d for d in adates if d >= lo]
    yrs = len(ds) / 250
    print("=" * 108)
    print(f"[{lab}] 종목당 균등 비중 — 300만원이 계좌의 몇 %인지로 자기 자리를 찾으면 된다")
    print("=" * 108)
    print(f"  {'비중':<8}{'예시 계좌':<14}{'자산':>9}{'연복리':>8}{'최대낙폭':>9}"
          f"{'제자리':>9}{'최대보유':>9}{'평균보유':>9}{'못산 신호':>10}")
    keep = {}
    for w in (3, 5, 8, 10, 15, 20):
        R = [run(ds, k, w) for k in range(SEEDS)]
        ST = np.array([stats(C) for C, _, _ in R])
        navs, dds, unds = ST[:, 0], ST[:, 1], ST[:, 2]
        mxn = np.median([C.n.max() for C, _, _ in R])
        avn = np.median([C.n.mean() for C, _, _ in R])
        blk = np.median([b / max(b + t, 1) * 100 for _, b, t in R])
        acct = 300 / (w / 100) / 10000        # 300만원이 w% 이면 계좌는? (억)
        cagr = (np.median(navs) ** (1 / yrs) - 1) * 100
        print(f"  {w:>2}%{'':<5}{acct*10000:>7,.0f}만원  {np.median(navs):>8.2f}배"
              f"{cagr:>7.1f}%{np.median(dds):>8.1f}%{np.median(unds)/250:>8.1f}년"
              f"{mxn:>9.0f}{avn:>9.1f}{blk:>9.0f}%")
        keep[w] = R
    # 실제 사용 비중대(5~10%)에 대해 경로 분포까지
    for w in (5, 10):
        R = keep[w]
        fin = np.array([C.nav.iloc[-1] for C, _, _ in R])
        mid = int(np.argsort(fin)[len(fin) // 2])
        Cm = R[mid][0]
        M = Cm.assign(m=Cm.date.str[:6]).groupby("m").nav.last()
        mr = M.pct_change().dropna() * 100
        _, a_dd, a_un = stats(Cm)
        verdict.path_report(mr, f"{lab} · 비중 {w}% · 일어날 수 있었던 경로",
                            actual=dict(mdd=a_dd, under=a_un / 21))
    print()
