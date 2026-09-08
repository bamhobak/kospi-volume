# -*- coding: utf-8 -*-
"""초단기 3단계 — 체결 밀림을 제대로 먹이고, 계좌에서 자리 경쟁까지 붙여 판정한다.

⚠ 2단계(short_build.py)의 밀림 검사는 틀렸다. 유니버스 기준선에도 같은 밀림을 먹여
   차감이 상쇄됐다(+1.52% → +1.52%). 실제로는 **우리만** 밀린다. 여기서는
   '밀린 신호 수익 − 안 밀린 유니버스' 로 잰다.

그리고 규칙 단위 통과는 절반이다. 우리 계좌는 규칙마다 자리 상한이 있고 비중이 정해져 있다.
초단기는 하루면 자리가 비므로 자리 효율이 좋을 수 있다 — 그게 실제로 계좌를 올리는지 본다.
  ① 밀림 0.0 / 0.3 / 0.5 / 1.0% 에서 초과가 살아남는가
  ② 신규 규칙으로 계좌에 넣었을 때 (비중·자리 상한을 몇으로 잡아야 하나)
  ③ 기존 9규칙과 겹치는가 (같은 종목·같은 날을 이미 사고 있으면 새 규칙이 아니다)
"""
import io, sys, warnings, sqlite3
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
SEEDS = 12
TR0, TR1, VA0 = "20160101", "20221231", "20230101"

src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, TRAIL, base, dn60 = ns["KP"], ns["KQ"], ns["RULES"], ns["TRAIL"], ns["base"], ns["dn60"]

for K in (KP, KQ):
    g = K.groupby("ticker", sort=False)
    K["dev25x"] = (K.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
    nxt_o, nxt_c = g.open.shift(-1), g.close.shift(-1)
    for slip, tag in ((0.0, ""), (0.003, "s3"), (0.005, "s5"), (0.010, "s10")):
        K[f"r1{tag}"] = (nxt_c / (nxt_o * (1 + slip)) - 1) * 100 - K.cost

# 기준선은 **밀림 없는** 유니버스. 우리만 밀리기 때문이다.
UNI = {mk: K.dropna(subset=["r1"]).groupby("date").r1.mean()
       for K, mk in ((KP, "KOSPI"), (KQ, "KOSDAQ"))}

CAND = {
    "코스피 갭-3 + 업종붕괴 + 이격": (KP, "KOSPI",
        base(KP, 3) & (KP.gap <= -3) & (KP.u <= -10) & (KP.dev25x <= -12)),
    "코스피 갭-5 + 하락장": (KP, "KOSPI",
        base(KP, 3) & (KP.gap <= -5) & dn60(KP)),
    "코스피 갭-3 + 신용 -15%↓": (KP, "KOSPI",
        base(KP, 3) & (KP.gap <= -3) & (KP.cr_chg20 <= -15)),
    "코스닥 갭-5 + 하락장": (KQ, "KOSDAQ",
        base(KQ, 3) & (KQ.gap <= -5) & dn60(KQ)),
    "코스닥 갭-5 + 기관20일 0%↑": (KQ, "KOSDAQ",
        base(KQ, 3) & (KQ.gap <= -5) & (KQ.ow20 >= 0)),
    "코스닥 갭-5 + 하락장 + 이격": (KQ, "KOSDAQ",
        base(KQ, 3) & (KQ.gap <= -5) & dn60(KQ) & (KQ.dev25x <= -12)),
}

print("=" * 118)
print("① 체결 밀림 — 밀린 신호 수익 vs 안 밀린 유니버스 (2단계의 상쇄 버그 수정)")
print("=" * 118)
print(f"  {'후보':<28}{'건수':>7}{'밀림0':>9}{'0.3%':>9}{'0.5%':>9}{'1.0%':>9}"
      f"{'중앙(0.5%)':>11}{'절삭(0.5%)':>11}")
NT = 0
for nm, (K, mk, cond) in CAND.items():
    X = K[cond.fillna(False)].copy()
    X = X[(X.date >= TR0)].dropna(subset=["r1"])
    u = X.date.map(UNI[mk])
    cells = ""
    for tag in ("", "s3", "s5", "s10"):
        NT += 1
        cells += f"{(X[f'r1{tag}'] - u).mean():>+8.2f}%"
    e5 = X.r1s5 - u
    print(f"  {nm:<28}{len(X):>7,}{cells}{e5.median():>+10.2f}%"
          f"{e5[e5 <= e5.quantile(0.95)].mean():>+10.2f}%")

# ══════════════════════════════════════════════════════════════════════
# ② 계좌 — 밀림 0.5% 를 기본값으로 삼아 신규 규칙을 넣어 본다
# ══════════════════════════════════════════════════════════════════════
adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}

def base_signals():
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
        ex = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
        m = cond.fillna(False).values
        X = K[m].copy()
        X["exit"] = ex[m]; X["hold"] = (first + 1)[m]
        X["rid"] = rid; X["pct"] = pct; X["mx"] = mx
        X["ret"] = (X.exit / X.buy - 1) * 100 - X.cost
        X = X.dropna(subset=["ret"])
        X = X[X.buy > 0]
        out.append(X[["date", "ticker", "hold", "rid", "pct", "mx", "ret"]])
    return pd.concat(out, ignore_index=True)

S0 = base_signals()

def add_new(nm, pct, mx, slip="s5"):
    K, mk, cond = CAND[nm]
    X = K[cond.fillna(False)].copy().dropna(subset=[f"r1{slip}"])
    X["hold"] = 1; X["rid"] = "S1"; X["pct"] = pct; X["mx"] = mx
    X["ret"] = X[f"r1{slip}"]
    return pd.concat([S0, X[["date", "ticker", "hold", "rid", "pct", "mx", "ret"]]],
                     ignore_index=True)

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
DS = {pn: [d for d in adates if lo <= d <= hi] for pn, lo, hi in PER}

print("\n" + "=" * 118)
print("② 계좌 짝 비교 — 신규 초단기 규칙을 넣으면 (밀림 0.5% 반영 · 시드 12)")
print("=" * 118)
print(f"  {'안':<30}" + "".join(f"{p[0]:>21}" for p in PER))
print(f"  {'':<30}" + "".join(f"{'자산':>9}{'낙폭':>5}{'시드승':>7}" for p in PER))
B = {}
row = ""
for pn, _, _ in PER:
    R = [sim(S0, DS[pn], k) for k in range(SEEDS)]
    B[pn] = [x[0] for x in R]
    row += f"{np.median(B[pn]):>8.2f}배{np.median([x[1] for x in R]):>4.0f}%{'기준':>7}"
print(f"  {'현행 9규칙':<30}{row}")

for nm in CAND:
    for pct, mx in ((5, 3), (10, 3), (5, 5)):
        NT += 1
        S = add_new(nm, pct, mx)
        row = ""
        for pn, _, _ in PER:
            R = [sim(S, DS[pn], k) for k in range(SEEDS)]
            nav = [x[0] for x in R]
            w = sum(a > b for a, b in zip(nav, B[pn]))
            row += f"{np.median(nav):>8.2f}배{np.median([x[1] for x in R]):>4.0f}%{w:>5}/{SEEDS}"
        print(f"  +{nm[:20]:<21}비중{pct}·{mx}자리{row}")

# ══════════════════════════════════════════════════════════════════════
# ③ 기존 규칙과 겹치는가
# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 118)
print("③ 기존 9규칙과 겹침 — 같은 (종목,날짜)를 이미 사고 있나")
print("=" * 118)
old = set(zip(S0.ticker, S0.date))
for nm, (K, mk, cond) in CAND.items():
    X = K[cond.fillna(False)]
    X = X[X.date >= TR0]
    dup = sum((t, d) in old for t, d in zip(X.ticker, X.date))
    print(f"  {nm:<30}{len(X):>7,}건 중 겹침 {dup:>5,}건 ({dup / max(len(X),1) * 100:>4.1f}%)")

verdict.log_trials("초단기 계좌검증", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
