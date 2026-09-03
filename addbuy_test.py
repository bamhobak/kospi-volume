# -*- coding: utf-8 -*-
"""추가매수(피라미딩) 실측 — '신호가 계속 살아 있고 이미 이익 중이면 더 산다' 가 맞나.

옛 알림이 쓰던 조건('이익 중 + 신호 4일 연속 유지')은 지금은 폐기된 옛 규칙의
것이었고 표본도 11건이었다. 현재 9규칙 데이터로 다시 잰다.

무엇을 재나
  최초분  = 규칙 신호가 처음 뜬 날 매수 (지금 우리가 하는 것)
  추가분  = 신호가 k일 연속 유지되는 중이고, 최초 매수분이 이익 중일 때 더 매수
  둘을 같은 잣대(보유기간·손절)로 재고, 추가분이 최초분만 못하면 할 이유가 없다.

판정 기준은 우리가 늘 쓰는 것
  학습 2018~22 / 검증 2023~ · 월블록 부트스트랩 CI · 중앙값 · 상위5% 제거 평균
  (한두 종목의 대박이 평균을 끌어올린 것인지 보려면 중앙값과 절삭평균이 필요하다)

사용: python addbuy_test.py
"""
import io, sys, gc
from pathlib import Path
import numpy as np, pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES = ns["KP"], ns["KQ"], ns["RULES"]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}

def boot(v, k, seed=127, n=2000):
    if len(v) < 20: return None
    rng = np.random.default_rng(seed); d = pd.DataFrame({"r": v, "ym": k})
    by = {m: g.r.to_numpy() for m, g in d.groupby("ym")}; ms = list(by)
    if len(ms) < 3: return None
    return np.percentile([np.concatenate([by[x] for x in rng.choice(ms, len(ms), replace=True)]).mean()
                          for _ in range(n)], [2.5, 97.5])

def trimmed(v):
    """상위 5% 를 떼고 낸 평균 — 소수의 대박에 기댄 결과인지 본다"""
    if len(v) < 20: return np.nan
    return v[v <= np.percentile(v, 95)].mean()

def ret_of(K, hold, stop):
    """보유기간·손절을 반영한 1건 수익률 (portfolio.py 와 같은 방식)"""
    col = f"n{hold}"
    if col not in K.columns: return None
    if stop:
        g = K.groupby("ticker", sort=False)
        lo = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((lo <= K.buy * (1 - stop)).fillna(False), -stop * 100 - K.cost, K[col])
        del lo; gc.collect()
        return pd.Series(r, index=K.index)
    return K[col]

def report(nm, Z, hold):
    if Z is None or len(Z) < 20: return None
    v = Z["_r"].to_numpy()
    zi, zo = Z[Z.date < "20230101"], Z[Z.date >= "20230101"]
    ci = boot(zi._r.values, zi.date.str[:6]) if len(zi) >= 20 else None
    top = Z.groupby(Z.date.str[:4])._r.size().max() / len(Z) * 100
    f = f"[{ci[0]:+.1f},{ci[1]:+.1f}]" if ci is not None else "-"
    print(f"    {nm:<22} {len(Z):>5} {v.mean():>+7.2f}% {(v > 0).mean() * 100:>4.0f}% "
          f"{np.median(v):>+7.2f}% {trimmed(v):>+7.2f}% "
          f"{zi._r.mean() if len(zi) else np.nan:>+7.2f}% {zo._r.mean() if len(zo) else np.nan:>+7.2f}% "
          f"{top:>4.0f}% {f:>14}")
    return dict(n=len(Z), avg=v.mean(), med=np.median(v), trim=trimmed(v),
                ci_lo=ci[0] if ci is not None else np.nan,
                os=zo._r.mean() if len(zo) else np.nan)

print("  신호가 이어지는 동안 더 사는 게 이득인가 (streak = 신호 연속 유지 일수)\n")
print(f"    {'구분':<22} {'건수':>5} {'평균':>8} {'승률':>5} {'중앙':>8} {'절삭':>8} "
      f"{'학습':>8} {'검증':>8} {'최다年':>5} {'학습CI':>14}")
SUM = {}
for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
    c = cond.fillna(False)
    K = K.copy(); K["_c"] = c.values
    r = ret_of(K, hold, stop)
    if r is None: continue
    K["_r"] = r.values
    # 연속 유지 일수: 같은 종목에서 조건이 끊기지 않고 이어진 날수
    g = K.groupby("ticker", sort=False)
    blk = (~K._c).groupby(K.ticker).cumsum()
    K["_stk"] = K.groupby(["ticker", blk]).cumcount() + 1
    K.loc[~K._c, "_stk"] = 0
    # 최초 신호의 매수가를 그 연속 구간 내내 들고 간다
    first_buy = K.where(K._stk == 1)["buy"].groupby([K.ticker, blk]).transform("first")
    K["_win"] = (K.close / first_buy - 1) * 100        # 최초 매수분의 현재 손익
    Z = K[K._c & K._r.notna()]
    print(f"  [{NAME[rid]}] · {hold}거래일 보유" + (f" · 손절 -{stop*100:.0f}%" if stop else ""))
    a = report("최초 신호 (streak=1)", Z[Z._stk == 1], hold)
    for k in (2, 3, 4):
        b = report(f"추가: streak≥{k} & 이익중", Z[(Z._stk >= k) & (Z._win > 0)], hold)
        if a and b: SUM.setdefault(k, []).append((rid, a, b))
    print()
print("\n  요약 — 추가분이 최초분보다 나은 규칙 수")
for k, rows in sorted(SUM.items()):
    better = [r for r in rows if r[2]["avg"] > r[1]["avg"]]
    solid = [r for r in rows if r[2]["ci_lo"] > 0 and r[2]["med"] > 0 and r[2]["trim"] > 0]
    print(f"    streak≥{k}: 평균 우위 {len(better)}/{len(rows)}규칙 · "
          f"게이트 통과(학습CI>0·중앙>0·절삭>0) {len(solid)}/{len(rows)}")
    for rid, a, b in rows:
        mark = "✅" if (b["ci_lo"] > 0 and b["med"] > 0 and b["trim"] > 0 and b["avg"] > a["avg"]) else "  "
        print(f"      {mark} [{NAME[rid]}] 최초 {a['avg']:+.2f}%({a['n']}건) → 추가 {b['avg']:+.2f}%({b['n']}건)")
