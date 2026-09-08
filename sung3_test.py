# -*- coding: utf-8 -*-
"""성승현 3편(Ayw6mZTMwJE) — 새로운 주장만 골라 실측.

핵심 주장(월봉 12평 돌파매수·이탈매도)은 **이미 기각했다**(chart_basic2.py, 2026-09-08):
개별종목 전 시총대에서 항상보유에 지고 낙폭도 더 깊었다(코스피 상위100 2.45배/-64%
vs 4.67배/-51%). "우량주에 한해서" 라는 그의 단서도 시총 상위 100·300 으로 이미 확인했다.
그래서 여기서는 **이 영상에만 있는 새 주장 둘**만 잰다.

  ① 저승사자 캔들 — "월봉 12평을 깨면 바로 다음 달 장대음봉이 온다"
     → 이탈 직후 달의 수익률이 정말 특히 나쁜가? 아니면 그냥 하락장이라 나쁜가?
       유니버스 대비 초과로 재야 '이탈' 자체의 정보가 있는지 알 수 있다.
  ② 탑다운 지수 — "미국 3대 지수부터 보고 한국을 보라"
     → 나스닥·S&P·다우 월봉 12평 상태를 게이트로 쓰면 우리 계좌가 나아지나?
       (코스피 지수 12평 게이트는 이미 48전 48패로 기각. 해외 지수는 안 해봤다.)
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import verdict

BASE = Path(__file__).parent
SEEDS = 12
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, KB, RULES, TRAIL = ns["KP"], ns["KQ"], ns["KB"], ns["RULES"], ns["TRAIL"]


def base(K, amt=3):
    return ((~K.pref) & (K.close >= 1000) & (~K.dil.fillna(False)) & (K.amt20.fillna(0) >= amt))


# ══════════════════════════════════════════════════════════════════════
# ① 저승사자 캔들 — 월봉 12평 이탈 직후 달이 정말 특히 나쁜가
# ══════════════════════════════════════════════════════════════════════
print("=" * 112)
print("① 저승사자 캔들 — '월봉 12평을 깨면 다음 달 장대음봉' (유니버스 대비 초과로 판정)")
print("=" * 112)
NT = 0
for K, mk in ((KP, "코스피"), (KQ, "코스닥")):
    Z = K[base(K)].copy()
    Z["m"] = Z.date.str[:6]
    last = Z.groupby(["ticker", "m"], sort=False).tail(1).copy().sort_values(["ticker", "m"])
    g = last.groupby("ticker", sort=False)
    last["ma12"] = g.close.transform(lambda s: s.rolling(12, min_periods=12).mean())
    last["P"] = last.buy                              # 월말 다음 거래일 시가 = 체결가
    last["above"] = last.close > last.ma12
    last["prev"] = g.above.shift(1)
    for k in (1, 2, 3):
        last[f"r{k}"] = (g.P.shift(-k) / last.P - 1) * 100
    L = last.dropna(subset=["ma12", "prev", "r1"])
    L = L[L.m >= "201601"]
    # 유니버스 기준선 — 같은 달에 살아 있던 모든 종목의 평균
    U = {k: L.groupby("m")[f"r{k}"].mean() for k in (1, 2, 3)}
    br = L[(L.prev == True) & (~L.above)]             # 이번 달에 깬 것(직전엔 위였다)
    keep = L[L.above == True]                          # 계속 위에 있는 것
    print(f"\n  [{mk}] 이탈 {len(br):,}건 · 유지 {len(keep):,}건 · 월 {L.m.nunique()}개")
    print(f"    {'구분':<12}" + "".join(f"{f'{k}개월 뒤':>26}" for k in (1, 2, 3)))
    for nm, X in (("이탈 직후", br), ("계속 위", keep)):
        row = ""
        for k in (1, 2, 3):
            NT += 1
            e = X[f"r{k}"] - X.m.map(U[k])
            row += (f"{X[f'r{k}'].mean():>+8.2f}%(초과{e.mean():>+6.2f})"
                    f"승{(X[f'r{k}'] > 0).mean()*100:>3.0f}%")
        print(f"    {nm:<12}{row}")
    # 장대음봉 주장 직접 확인 — 다음 달 -10% 이하가 얼마나 자주 나오나
    NT += 1
    a = (br.r1 <= -10).mean() * 100
    b = (keep.r1 <= -10).mean() * 100
    c = (L.r1 <= -10).mean() * 100
    print(f"    다음 달 -10% 이하 비율: 이탈 직후 {a:.0f}% · 계속 위 {b:.0f}% · 전체 {c:.0f}%")

# ══════════════════════════════════════════════════════════════════════
# ② 탑다운 — 해외 지수 월봉 12평을 계좌 게이트로
# ══════════════════════════════════════════════════════════════════════
def ixgate(code, start="1990-01-01"):
    D = fdr.DataReader(code, start)
    D = D[D.Close > 0].copy()
    D["m"] = D.index.strftime("%Y%m")
    M = D.groupby("m").Close.last().to_frame("c")
    M["ma12"] = M.c.rolling(12, min_periods=12).mean()
    on = (M.c > M.ma12).shift(1)                      # 지난달 말 판정으로 이번 달을 산다
    return dict(zip(M.index, on))


GATES = {}
for code, nm in (("IXIC", "나스닥"), ("US500", "S&P500"), ("DJI", "다우")):
    try:
        GATES[nm] = ixgate(code, "1985-01-01")
        print(f"\n  {nm} 게이트 준비 ({len(GATES[nm])}개월)")
    except Exception as e:
        print(f"\n  {nm} 실패: {e}")

for K in (KP, KQ, KB):
    K["_mm"] = K.date.str[:6]
for nm, G in GATES.items():
    for K in (KP, KQ, KB):
        K[f"g_{nm}"] = K._mm.map(G)
# 셋 다 위일 때만
for K in (KP, KQ, KB):
    K["g_셋다"] = np.logical_and.reduce([K[f"g_{nm}"] == True for nm in GATES])

adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}
rel = (BASE / "rules_relation.py").read_text(encoding="utf-8")
exec(rel[rel.index("def build(R):"):rel.index("S = build(RULES)")], globals())
ta = (BASE / "trail_acct.py").read_text(encoding="utf-8")
exec(ta[ta.index("def build2(trail):"):ta.index("PER = [")].replace(
    "def build2(trail):", "def build2(trail, col=None, want=True):").replace(
    "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():",
    "for rid, (K, hold, stop, pct, mx, cond) in RULES.items():\n"
    "        if col is not None: cond = cond & ((K[col] == True) if want else (K[col] != True))"),
    globals())

PER = [("학습 2016~22", "20160101", "20221231"), ("검증 2023~26", "20230101", "20991231"),
       ("기준 2016~", "20160101", "20991231"), ("전구간 2005~26", "20050101", "20991231")]
print("\n" + "=" * 112)
print("② 탑다운 게이트 — 해외 지수 월봉 12평 위에서만 매수 (시드 12)")
print("=" * 112)
print(f"  {'안':<24}" + "".join(f"{p[0]:>22}" for p in PER))
print(f"  {'':<24}" + "".join(f"{'자산':>9}{'낙폭':>6}{'시드승':>7}" for p in PER))
B = {}
row = ""
S0 = build2(TRAIL)
for pn, lo, hi in PER:
    ds = [d for d in adates if lo <= d <= hi]
    R = [sim(S0, ds, k) for k in range(SEEDS)]
    B[pn] = [x[0] for x in R]
    row += f"{np.median(B[pn]):>8.2f}배{np.median([x[1] for x in R]):>5.0f}%{'기준':>7}"
print(f"  {'현행(게이트 없음)':<24}{row}")
for nm in list(GATES) + ["셋다"]:
    for want, lab in ((True, "위에서만"), (False, "아래에서만")):
        NT += 1
        S = build2(TRAIL, f"g_{nm}", want)
        row = ""
        for pn, lo, hi in PER:
            ds = [d for d in adates if lo <= d <= hi]
            R = [sim(S, ds, k) for k in range(SEEDS)]
            nav = [x[0] for x in R]
            w = sum(a > b for a, b in zip(nav, B[pn]))
            row += f"{np.median(nav):>8.2f}배{np.median([x[1] for x in R]):>5.0f}%{w:>5}/{SEEDS}"
        print(f"  {nm + ' ' + lab:<24}{row}")

verdict.log_trials("성승현3편", NT)
print(f"\n시험 {NT}개 기록 · 누적 {verdict.trial_count():,}개")
