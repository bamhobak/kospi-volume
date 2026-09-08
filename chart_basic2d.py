# -*- coding: utf-8 -*-
"""강의 2편 곁가지 — '12평 깨지면 매도' 를 **청산 규칙**으로 써보면?

영상은 12평 이탈을 진입이 아니라 **매도 신호**로 강조했다(588: "깨졌을 때 나가기만 하면
향후 하락은 굳이 감내하지 않아도 된다"). 우리는 지금 그 자리에 트레일링 -8% 를 쓴다
([[trailing-stop]], 2026-09-08 채택). 그러니 같은 자리를 놓고 머리를 맞대면 된다.

**맞대는 자리는 트레일링을 쓰는 세 규칙(P1·P4·P6)뿐이다.** 고정 손절을 쓰는 규칙까지
같이 건드리면 두 가지를 한꺼번에 바꾸는 셈이라 무엇이 효과인지 못 가린다.
  ① 현행: 트레일링 -8%
  ② 240일선 이탈 매도 — 보유 중 종가가 240일 이평 아래로 내려온 날 종가에 청산
  ③ 20일선 이탈 매도 — 240일은 하락장 규칙엔 너무 느릴 수 있으니 짧은 것도
  ④ 트레일링 + 240일선 이탈 중 먼저 닿는 쪽
  ⑤ 참고: 조기청산 없이 만기까지 (트레일링이 실제로 값을 하는지 바닥 확인)

⚠ shift 는 반드시 **종목별 groupby** 로 건다. 패널이 ticker·date 순이라 그냥 shift 하면
   종목 끝에서 다음 종목 가격을 끌어온다(2026-09-08 첫 구현의 버그).
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SEEDS = 12
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, TRAIL, KB = ns["KP"], ns["KQ"], ns["RULES"], ns["TRAIL"], ns["KB"]

for K in (KP, KQ, KB):
    g = K.groupby("ticker", sort=False)
    K["ma240"] = g.close.transform(lambda s: s.rolling(240, min_periods=240).mean())
    K["ma20x"] = g.close.transform(lambda s: s.rolling(20, min_periods=20).mean())
    K["b240"] = (K.close < K.ma240).where(K.ma240.notna(), False)
    K["b20"] = (K.close < K.ma20x).where(K.ma20x.notna(), False)

adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}


def build_exit(mode):
    """규칙별 신호표. 트레일링을 쓰는 규칙(P1·P4·P6)의 조기청산만 mode 로 갈아끼운다."""
    out = []
    for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
        g = K.groupby("ticker", sort=False)                     # ⚠ 종목별로 shift
        C = np.column_stack([g.close.shift(-i).values for i in range(1, hold + 1)])
        buy = K.buy.values
        t = TRAIL.get(rid)
        hit = np.zeros_like(C, dtype=bool)
        px = C.copy()

        def flags(col):
            return np.column_stack([g[col].shift(-i).fillna(False).values.astype(bool)
                                    for i in range(1, hold + 1)])

        if t is None:
            # 트레일링 안 쓰는 규칙 — 원래 방식 그대로 둔다(고정 손절 또는 무손절)
            if stop:
                h = C <= buy[:, None] * (1 - stop)
                hit |= h
                px = np.where(h, buy[:, None] * (1 - stop), px)
        else:
            run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
            if mode in ("cur", "both"):
                h = C <= run * (1 - t)
                hit |= h
                px = np.where(h & ~np.isnan(C), run * (1 - t), px)
            if mode in ("ma240", "both"):
                h = flags("b240")
                hit |= h
                px = np.where(h, C, px)
            if mode == "ma20":
                h = flags("b20")
                hit |= h
                px = np.where(h, C, px)
            # mode == "none" 이면 아무것도 안 걸어 만기까지 간다
        ok = hit.any(axis=1)
        first = np.where(ok, hit.argmax(axis=1), hold - 1)
        exit_px = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
        m = cond.fillna(False).values
        X = K[m].copy()
        X["exit"] = exit_px[m]
        X["hold"] = (first + 1)[m]
        X["rid"] = rid
        X["pct"] = pct
        X["mx"] = mx
        X = X.dropna(subset=["exit", "buy", "cost"])
        X = X[X.buy > 0]
        out.append(X[["date", "ticker", "buy", "exit", "hold", "cost", "rid", "pct", "mx"]])
    S = pd.concat(out, ignore_index=True)
    S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
    S["di"] = S.date.map(ADI)
    return S.dropna(subset=["di"]).sort_values("di").reset_index(drop=True)


def sim2(S, ds, seed):
    rng = np.random.default_rng(seed)
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd = 1.0, 0.0
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            r = held.pop(k)[1]
            nav *= 1 + r / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        g = byd.get(d)
        if g is None:
            continue
        g = g.sample(frac=1, random_state=int(rng.integers(1 << 30)))
        for r in g.itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    return nav, mdd * 100


PER = [("학습 2016~22", "20160101", "20221231"), ("검증 2023~26", "20230101", "20991231"),
       ("기준 2016~", "20160101", "20991231"), ("전구간 2005~26", "20050101", "20991231")]
VAR = [("현행(트레일링 -8%)", "cur"), ("240일선 이탈 매도", "ma240"),
       ("20일선 이탈 매도", "ma20"), ("트레일링 + 240 이탈", "both"),
       ("참고: 조기청산 없음", "none")]

print("=" * 108)
print("청산 규칙 맞대기 — '12평 깨지면 매도' 를 트레일링 자리(P1·P4·P6)에 넣으면 (시드 12)")
print("=" * 108)
print(f"  {'안':<22}" + "".join(f"{p[0]:>24}" for p in PER))
print(f"  {'':<22}" + "".join(f"{'자산':>10}{'낙폭':>7}{'시드승':>7}" for p in PER))
BASE_N = {}
for nm, mode in VAR:
    S = build_exit(mode)
    row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim2(S, ds, k) for k in range(SEEDS)]
        nav = [x[0] for x in R]
        md = np.median([x[1] for x in R])
        if mode == "cur":
            BASE_N[pn] = nav; w = "기준"
        else:
            w = f"{sum(a > b for a, b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{md:>6.0f}%{w:>7}"
    print(f"  {nm:<22}{row}")
    T = S[S.rid.isin(TRAIL)]
    print(f"    트레일링 3규칙: 평균 보유 {T.hold.mean():>4.1f}일 · {len(T):>6,}건 · 건별 평균 {T.ret.mean():+.2f}%")
