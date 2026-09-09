# -*- coding: utf-8 -*-
"""미국 계좌 시뮬 — 규칙 단위 통과는 절반이다.

`us_rules.py` 에서 [낙폭과대]·[저PBR 낙폭] 둘이 규칙 단위로 통과했다. 그러나 한국에서
수없이 봤듯 **규칙에서 통과해도 계좌에서 자리 경쟁으로 기각되는 일이 흔하다**
([[short-program-combo]] 5.74배 · [[stock-feargreed]] 전량 기각 · 초단기 갭 등).
그래서 같은 방식으로 계좌를 돌린다 — 자리 상한·비중·현금 제약·시드 12.

비교 대상
  ① 통과 둘만으로 구성한 미국 계좌
  ② 대입 가능한 일곱 규칙 전부(기각분 포함) — 섞으면 나아지는지
  ③ 벤치마크: 같은 기간 S&P500 (기준선이 아니라 참고용. 판정은 절대 수익으로 한다)
"""
import io, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
SEEDS = 12
_src = open(BASE / "us_rules.py", encoding="utf-8").read().split('print("\\n" + "=" * 126)')[0]
import re
_src = re.sub(r"^\s*sys\.stdout\s*=.*$", "", _src, flags=re.M)
exec(_src)          # K · RULES · base · measure · UNI 를 그대로 재사용
# ⚠ us_rules.measure 는 TR0(2016) 이전을 잘라낸다. 계좌는 2005~ 전구간도 봐야 하므로
#   여기서는 TR0 를 2005 로 낮춘다(구간 자르기는 sim 의 ds 가 맡는다).
#   이걸 안 하면 '전구간' 칸이 '기준구간' 과 똑같은 값으로 나온다(2026-09-09 실수).
TR0 = "20050101"

adates = sorted(K.date.unique())
ADI = {d: i for i, d in enumerate(adates)}


def build(rids):
    out = []
    for rid in rids:
        r = RULES[rid]
        z = measure(rid, r)
        if z is None or z.get("few"):
            continue
        X = z["X"].copy()
        X["rid"] = rid
        X["pct"] = r["pct"]
        X["mx"] = r["mx"]
        out.append(X[["date", "ticker", "hold", "rid", "pct", "mx", "ret", "amt20"]])
    S = pd.concat(out, ignore_index=True)
    S["di"] = S.date.map(ADI)
    return S.dropna(subset=["di"]).sort_values("di").reset_index(drop=True)


def sim(S, ds, seed, cash_cap=1.0):
    rng = np.random.default_rng(seed)
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd = 1.0, 0.0
    inv = []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav); mdd = min(mdd, nav / peak - 1)
        inv.append(sum(RULES[k[0]]["pct"] for k in held) / 100)
        g = byd.get(d)
        if g is None:
            continue
        # 매수 선택은 **거래대금 큰 순** — 실전에서 무엇을 살지 정하는 규칙이다(us_pick.py).
        # 랜덤으로 고르면 같은 규칙인데도 계좌가 2.14~8.96배까지 갈린다.
        for r in g.sort_values("amt20", ascending=False, na_position="last").itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            if sum(RULES[x[0]]["pct"] for x in held) / 100 + r.pct / 100 > cash_cap:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(inv))


PER = [("학습 2016~22", "20160101", "20221231"), ("검증 2023~26", "20230101", "20991231"),
       ("기준 2016~", "20160101", "20991231"), ("전구간 2005~26", "20050101", "20991231")]
SETS = [("통과 둘 (낙폭과대+저PBR)", ["D1", "D2"]),
        ("통과 둘 + [상승장 신고가]", ["D1", "D2", "N1"]),
        ("대입 가능 일곱 전부", ["P1", "P2", "P3", "P4", "P6", "D1", "D2"]),
        ("낙폭 계열 넷", ["P3", "P4", "P6", "D1"]),
        ("낙폭+밸류 다섯", ["P3", "P4", "P6", "D1", "D2"])]

print("\n" + "=" * 112)
print("미국 계좌 시뮬 (시드 12) — 자리 상한·비중은 한국과 같은 값을 쓴다")
print("=" * 112)
print(f"  {'구성':<26}" + "".join(f"{p[0]:>21}" for p in PER))
print(f"  {'':<26}" + "".join(f"{'자산':>10}{'낙폭':>6}{'투입':>5}" for p in PER))
for nm, rids in SETS:
    S = build(rids)
    row = ""
    for pn, lo, hi in PER:
        ds = [d for d in adates if lo <= d <= hi]
        R = [sim(S, ds, k) for k in range(SEEDS)]
        row += (f"{np.median([x[0] for x in R]):>9.2f}배"
                f"{np.median([x[1] for x in R]):>5.0f}%"
                f"{np.median([x[2] for x in R])*100:>4.0f}%")
    print(f"  {nm:<26}{row}")
    print(f"    신호 {len(S):,}건 · 규칙 {len(rids)}개")

# 참고 — 같은 기간 S&P500 을 그냥 들고 있었으면
import FinanceDataReader as fdr
sp = fdr.DataReader("US500", "2005-01-01")
sp = sp[sp.Close > 0].copy()
sp["date"] = sp.index.strftime("%Y%m%d")
print("\n  참고 — S&P500 그냥 보유 (판정 기준이 아니라 눈금용)")
for pn, lo, hi in PER:
    z = sp[(sp.date >= lo) & (sp.date <= hi)]
    if len(z) < 100:
        continue
    m = z.Close.iloc[-1] / z.Close.iloc[0]
    dd = float((z.Close / z.Close.cummax() - 1).min() * 100)
    print(f"    {pn:<16}{m:>7.2f}배 · 낙폭 {dd:.0f}%")
