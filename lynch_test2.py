# -*- coding: utf-8 -*-
"""피터 린치 영상 실측 2부 — 우리 규칙 위에서 재는 세 가지.

  L3 "꽃을 뽑고 잡초에 물을 준다" — 보유 중간 시점에 오른 종목과 물린 종목을 갈라
     **남은 구간** 수익을 비교한다. 오른 쪽이 낫다면 일찍 파는 건 손해다.
     계좌로도 확인 — ⓐ 이익 중인 것을 조기 청산 ⓑ 손실 중인 것을 조기 청산.
  L4 "매도는 가격이 아니라 **산 이유**가 사라졌을 때" — 우리 하락장 규칙이 산 이유는
     '코스피 60일선 아래의 공포' 다. 60일선 위로 복귀한 날 청산해 본다.
  L5 "10루타는 엉덩이가 만든다" — 보유기간을 1.5배·2배로 늘리면 좋아지는가.

⚠ shift 는 반드시 종목별 groupby 로. 절대 배수는 이 스크립트 자체 시뮬 기준이라
   다른 스크립트의 배수와 직접 비교하면 안 된다(같은 표 안에서만 유효).
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
KP, KQ, KB, RULES, TRAIL, UP60 = ns["KP"], ns["KQ"], ns["KB"], ns["RULES"], ns["TRAIL"], ns["UP60"]

adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}
for K in (KP, KQ, KB):
    K["up60"] = K.date.map(UP60).fillna(False)      # 코스피가 60일선 위 = 산 이유가 사라진 날

# ══════════════════════════════════════════════════════════════════════
# L3. 꽃과 잡초 — 중간 시점 손익으로 갈라 남은 구간을 본다
# ══════════════════════════════════════════════════════════════════════
print("=" * 104)
print("L3. 꽃을 뽑고 잡초에 물 주기 — 보유 중간에 오른 것과 물린 것, 남은 구간은 누가 나은가")
print("=" * 104)
print(f"  {'규칙':<6}{'보유':>4}{'분기':>4}  {'오른 것(꽃)':>26}  {'물린 것(잡초)':>26}   차이")
for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
    g = K.groupby("ticker", sort=False)
    half = max(1, hold // 2)
    m = cond.fillna(False)
    px_h = g.close.shift(-half)                      # 중간 시점 종가
    px_e = g.close.shift(-hold)                      # 만기 종가
    X = K[m].copy()
    X["mid"] = (px_h.reindex(X.index) / X.buy - 1) * 100
    X["rest"] = (px_e.reindex(X.index) / px_h.reindex(X.index) - 1) * 100
    X = X.dropna(subset=["mid", "rest"])
    if len(X) < 60:
        print(f"  {rid:<6}{hold:>4}{half:>4}  표본부족 {len(X)}건"); continue
    f = X[X.mid > 0]; w = X[X.mid <= 0]
    print(f"  {rid:<6}{hold:>4}{half:>4}  {len(f):>5}건 남은구간 {f.rest.mean():>+6.2f}% "
          f"중앙{f.rest.median():>+6.2f}  {len(w):>5}건 남은구간 {w.rest.mean():>+6.2f}% "
          f"중앙{w.rest.median():>+6.2f}  {f.rest.mean() - w.rest.mean():>+6.2f}%p")

# ══════════════════════════════════════════════════════════════════════
# 계좌 맞대기 — L3(조기청산 방향) · L4(이유 소멸) · L5(보유 연장)
# ══════════════════════════════════════════════════════════════════════
def build(mode, mult=1.0):
    out = []
    for rid, (K, hold0, stop, pct, mx, cond) in RULES.items():
        hold = max(1, int(round(hold0 * mult)))
        g = K.groupby("ticker", sort=False)
        C = np.column_stack([g.close.shift(-i).values for i in range(1, hold + 1)])
        buy = K.buy.values
        t = TRAIL.get(rid)
        hit = np.zeros_like(C, dtype=bool)
        px = C.copy()
        if t:                                        # 트레일링은 늘 그대로 둔다
            run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
            h = C <= run * (1 - t)
            hit |= h
            px = np.where(h & ~np.isnan(C), run * (1 - t), px)
        elif stop:
            h = C <= buy[:, None] * (1 - stop)
            hit |= h
            px = np.where(h, buy[:, None] * (1 - stop), px)
        half = max(1, hold // 2)
        if mode == "cut_win":                        # 중간에 이익이면 판다(꽃 뽑기)
            h = np.zeros_like(C, dtype=bool)
            h[:, half - 1] = C[:, half - 1] > buy
            hit |= h; px = np.where(h, C, px)
        if mode == "cut_lose":                       # 중간에 손실이면 판다(잡초 뽑기)
            h = np.zeros_like(C, dtype=bool)
            h[:, half - 1] = C[:, half - 1] <= buy
            hit |= h; px = np.where(h, C, px)
        if mode == "reason":                         # 산 이유(하락장 공포)가 사라지면 판다
            R = np.column_stack([g.up60.shift(-i).fillna(False).values.astype(bool)
                                 for i in range(1, hold + 1)])
            hit |= R; px = np.where(R, C, px)
        ok = hit.any(axis=1)
        first = np.where(ok, hit.argmax(axis=1), hold - 1)
        exit_px = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
        mm = cond.fillna(False).values
        X = K[mm].copy()
        X["exit"] = exit_px[mm]; X["hold"] = (first + 1)[mm]
        X["rid"] = rid; X["pct"] = pct; X["mx"] = mx
        X = X.dropna(subset=["exit", "buy", "cost"])
        X = X[X.buy > 0]
        out.append(X[["date", "ticker", "buy", "exit", "hold", "cost", "rid", "pct", "mx"]])
    S = pd.concat(out, ignore_index=True)
    S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
    S["di"] = S.date.map(ADI)
    return S.dropna(subset=["di"]).sort_values("di").reset_index(drop=True)

def sim(S, ds, seed):
    rng = np.random.default_rng(seed)
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd = 1.0, 0.0
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        g = byd.get(d)
        if g is None: continue
        for r in g.sample(frac=1, random_state=int(rng.integers(1 << 30))).itertuples():
            if cnt.get(r.rid, 0) >= r.mx: continue
            k = (r.rid, r.ticker, d)
            if k in held: continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    return nav, mdd * 100

PER = [("학습 2016~22", "20160101", "20221231"), ("검증 2023~26", "20230101", "20991231"),
       ("기준 2016~", "20160101", "20991231"), ("전구간 2005~26", "20050101", "20991231")]
VAR = [("현행", "cur", 1.0),
       ("L3ⓐ 이익 중이면 조기청산", "cut_win", 1.0),
       ("L3ⓑ 손실 중이면 조기청산", "cut_lose", 1.0),
       ("L4 산 이유 사라지면 청산", "reason", 1.0),
       ("L5 보유 1.5배", "cur", 1.5),
       ("L5 보유 2배", "cur", 2.0)]

print("\n" + "=" * 104)
print("계좌 짝 비교 (시드 12) — ※ 절대 배수는 이 스크립트 시뮬 기준, 표 안에서만 비교")
print("=" * 104)
print(f"  {'안':<26}" + "".join(f"{p[0]:>24}" for p in PER))
print(f"  {'':<26}" + "".join(f"{'자산':>10}{'낙폭':>7}{'시드승':>7}" for p in PER))
BASE_N = {}
for nm, mode, mult in VAR:
    S = build(mode, mult)
    row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        nav = [x[0] for x in R]
        md = np.median([x[1] for x in R])
        if nm == "현행":
            BASE_N[pn] = nav; w = "기준"
        else:
            w = f"{sum(a > b for a, b in zip(nav, BASE_N[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{md:>6.0f}%{w:>7}"
    print(f"  {nm:<26}{row}")
    print(f"    평균 보유 {S.hold.mean():>4.1f}일 · {len(S):>6,}건 · 건별 평균 {S.ret.mean():+.2f}%")
