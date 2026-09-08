# -*- coding: utf-8 -*-
"""L5 후속 — '보유 1.5배' 가 12/12 로 나온 게 어느 규칙 덕인지 갈라본다.

lynch_test2.py 에서 9규칙 보유일을 한꺼번에 1.5배로 늘렸더니 검증 12/12·기준 11/12 가
나왔다. 그러나 아홉을 동시에 바꾼 결과라 그대로 채택하면 뭐가 효과인지 모른 채
아홉 곳을 건드리는 셈이다. **한 규칙씩** 늘려 누가 끌고 가는지 본다.
  ① 규칙별 단독 연장 (1.5배 · 2배) — 계좌 짝 비교
  ② 통과한 규칙만 모아 다시 계좌 (조합했을 때도 남는가)
  ③ 규칙 단위 건별 성적 — 연장이 수익을 늘리는지 자리만 오래 잡는지

⚠ 시험 조합 수를 verdict 에 기록한다(다중검정 보정).
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
SEEDS = 12
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, TRAIL = ns["KP"], ns["KQ"], ns["RULES"], ns["TRAIL"]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}
adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}


def build(mults):
    """mults: {rid: 배율}. 없는 규칙은 1.0."""
    out = []
    for rid, (K, hold0, stop, pct, mx, cond) in RULES.items():
        hold = max(1, int(round(hold0 * mults.get(rid, 1.0))))
        g = K.groupby("ticker", sort=False)
        C = np.column_stack([g.close.shift(-i).values for i in range(1, hold + 1)])
        buy = K.buy.values
        t = TRAIL.get(rid)
        hit = np.zeros_like(C, dtype=bool)
        px = C.copy()
        if t:
            run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
            h = C <= run * (1 - t)
            hit |= h
            px = np.where(h & ~np.isnan(C), run * (1 - t), px)
        elif stop:
            h = C <= buy[:, None] * (1 - stop)
            hit |= h
            px = np.where(h, buy[:, None] * (1 - stop), px)
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
DS = {pn: [d for d in adates if lo <= d <= hi] for pn, lo, hi in PER}


def run(nm, mults, base_n=None):
    S = build(mults)
    row, navs = "", {}
    for pn, _, _ in PER:
        R = [sim(S, DS[pn], k) for k in range(SEEDS)]
        nav = [x[0] for x in R]; navs[pn] = nav
        md = np.median([x[1] for x in R])
        w = "기준" if base_n is None else f"{sum(a > b for a, b in zip(nav, base_n[pn]))}/{SEEDS}"
        row += f"{np.median(nav):>9.2f}배{md:>6.0f}%{w:>7}"
    print(f"  {nm:<28}{row}")
    return navs, S


print("=" * 112)
print("① 규칙 하나씩 보유 연장 — 누가 12/12 를 끌고 왔나 (시드 12)")
print("=" * 112)
print(f"  {'안':<28}" + "".join(f"{p[0]:>22}" for p in PER))
print(f"  {'':<28}" + "".join(f"{'자산':>9}{'낙폭':>6}{'시드승':>7}" for p in PER))
B, S0 = run("현행", {})
H0 = {rid: RULES[rid][1] for rid in RULES}
NT = 0
res = {}
PROBE = {rid: (1.5, 2.0) for rid in RULES}
if __import__("os").environ.get("NEIGHBOR"):
    # 이웃 확인 — [깊은 이격] 5일만 6·7·8·9·10 으로 촘촘히. 8일만 이기면 우연이다.
    PROBE = {"P6": (1.2, 1.4, 1.6, 1.8, 2.0)}
for rid in PROBE:
    for mult in PROBE[rid]:
        NT += 1
        h = max(1, int(round(H0[rid] * mult)))
        navs, _ = run(f"[{NAME[rid]}] {H0[rid]}→{h}일", {rid: mult}, B)
        res[(rid, mult)] = {pn: sum(a > b for a, b in zip(navs[pn], B[pn])) for pn, _, _ in PER}

print("\n" + "=" * 112)
print("② 통과 후보 — 검증 8/12 이상 & 기준 8/12 이상 & 전구간 6/12 이상")
print("=" * 112)
win = [(rid, m) for (rid, m), v in res.items()
       if v["검증 2023~26"] >= 8 and v["기준 2016~"] >= 8 and v["전구간 2005~26"] >= 6]
for rid, m in sorted(win):
    v = res[(rid, m)]
    print(f"  [{NAME[rid]}] x{m}  학습 {v['학습 2016~22']}/12 · 검증 {v['검증 2023~26']}/12 · "
          f"기준 {v['기준 2016~']}/12 · 전구간 {v['전구간 2005~26']}/12")
if not win:
    print("  없음 — 규칙 단독으로는 아무도 문턱을 넘지 못했다")
else:
    print("\n  통과한 것만 한꺼번에 적용하면:")
    print(f"  {'':<28}" + "".join(f"{p[0]:>22}" for p in PER))
    best = {}
    for rid, m in win:
        best[rid] = max(best.get(rid, 0), m)
    run("통과 규칙만 연장", best, B)

print("\n" + "=" * 112)
print("③ 건별 성적 — 연장이 수익을 늘리나, 자리만 오래 잡나")
print("=" * 112)
print(f"  {'규칙':<16}{'현행':>28}{'x1.5':>28}{'x2.0':>28}")
for rid in RULES:
    cells = ""
    for m in (1.0, 1.5, 2.0):
        S = build({rid: m}) if m != 1.0 else S0
        z = S[S.rid == rid]
        cells += f"{len(z):>6,}건 {z.ret.mean():>+6.2f}% 보유{z.hold.mean():>5.1f}일"
    print(f"  {NAME[rid]:<16}{cells}")

verdict.log_trials("lynch(보유연장)", NT)
print(f"\n시험 조합 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
