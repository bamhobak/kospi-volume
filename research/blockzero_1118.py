# -*- coding: utf-8 -*-
"""코덱스 제안 2번(2026-11-18 사용자 "테스트는 너가 해줘. 2 6 해줘") — 블록딜(시간외 매도) 뒤 매도자 잔고가 0 이 된 종목.
가설: 같은 블록딜이라도 매도자가 다 털었으면 그 사람에게서 다음 물량이 안 나온다 → 공시 다음 날 시가 매수, 5거래일 보유.
사건 = DART 임원·주요주주 소유상황보고서(data/dart/insider.db tx) 사유 '시간외매매(-)' 보통주. 공시일 D = rcept_dt.
  같은 종목·같은 공시일은 한 사건으로 묶는다(가족이 같이 파는 경우). 잔고 0 = 판 사람 전원의 끝 잔고 0 · 일부 남김 = 전원 잔고 > 0 · 섞임.
  금액 = Σ 판 주식 × 신고 단가(없으면 D 종가). 말한 판 = 금액 10억↑ · D+1 시가 → D+5 종가. 대조 = 같은 조건의 '일부 남김'.
앞선 기록 H0281(10-03): 블록딜 뒤 절대 중앙 -3~-5% — 이번엔 '잔고 0' 으로 가른 것만 새로 본다.
    python research/memguard.py research/blockzero_1118.py → research/reports/blockzero_1118.md"""
import sqlite3
from evlib_1118 import *

c = sqlite3.connect("file:%s?mode=ro" % (BASE / "data" / "dart" / "insider.db"), uri=True)
T = pd.read_sql("select rowid rid, rcept_no, ticker, rcept_dt, reporter, chg_dt, before_qty, delta, after_qty, price from tx "
                "where reason like '%시간외매매(-)%' and kind='보통주' and delta<0 and rcept_dt>='20151001'", c); c.close()
T = T.sort_values(["ticker", "rcept_dt", "reporter", "chg_dt", "rid"])
g = T.groupby(["ticker", "rcept_dt", "reporter"], sort=False)
R = g.agg(sold=("delta", lambda s: -s.sum()), last=("after_qty", "last"), first=("before_qty", "first"), chg=("chg_dt", "max"),
          val=("delta", lambda s: float((-s * T.loc[s.index, "price"].fillna(0)).sum()))).reset_index()
R["zs"] = np.where(R["last"] == 0, R.sold, 0)
E = R.groupby(["ticker", "rcept_dt"]).agg(sold=("sold", "sum"), zs=("zs", "sum"), val=("val", "sum"), chg=("chg", "max"), n=("reporter", "size"), held=("first", "sum")).reset_index()
E["grp"] = np.where(E.zs == E.sold, "잔고 0", np.where(E.zs == 0, "일부 남김", "섞임"))
E = E[E.ticker.isin(ti)].copy()
E["j"] = E.ticker.map(ti); E["i"] = E.rcept_dt.map(on_or_before); E = E[(E.i >= 6) & (E.i < nd - 1)]
E["day"] = calA[E.i.values]
E["c0"] = CL[E.i.values, E.j.values]; E = E[E.c0 >= 1000]
E["amt"] = np.where(E.val > 0, E.val, E.sold * E.c0) / 1e8                      # 억원
E["keep"] = 1 - E.sold / E.held.replace(0, np.nan)                               # 판 뒤 남긴 비율(신고 기준)
E["ic"] = E.chg.map(on_or_before)                                                # 거래일(체결일) 색인
E["lag"] = E.i - E.ic                                                            # 거래일 → 공시일 거래일 수
ok = (E.ic >= 1) & (E.ic <= E.i)
E["disc"] = np.where((E.val > 0) & ok, (E.val / E.sold) / CL[np.clip(E.ic.values - 1, 0, nd - 1), E.j.values] * 100 - 100, np.nan)   # 신고 단가 ÷ 거래 전날 종가
E["pre"] = np.where(ok, (CL[E.i.values, E.j.values] / CL[np.clip(E.ic.values - 1, 0, nd - 1), E.j.values] - 1) * 100, np.nan)       # 거래 전날 종가 → 공시일 종가
E["gap"] = (OP[np.clip(E.i.values + 1, 0, nd - 1), E.j.values] / E.c0 - 1) * 100
E["p20"] = (E.c0 / CL[np.clip(E.i.values - 20, 0, nd - 1), E.j.values] - 1) * 100

RET = {"D+1 시가→D+5 종가(말한 판)": fwd(sh(OP, 1), sh(CL, 5)), "D+1 시가→당일 종가": fwd(sh(OP, 1), sh(CL, 1)), "D+1 시가→D+3 종가": fwd(sh(OP, 1), sh(CL, 3)),
       "D+1 시가→D+10 종가": fwd(sh(OP, 1), sh(CL, 10)), "D+1 시가→D+20 종가": fwd(sh(OP, 1), sh(CL, 20)), "D+1 종가→D+5 종가": fwd(sh(CL, 1), sh(CL, 5))}
HOLD = {"D+1 시가→D+5 종가(말한 판)": 5, "D+1 시가→당일 종가": 1, "D+1 시가→D+3 종가": 3, "D+1 시가→D+10 종가": 10, "D+1 시가→D+20 종가": 20, "D+1 종가→D+5 종가": 5}
MK = {k: mkt(v) for k, v in RET.items()}

P_("# 코덱스 2번 — 블록딜(시간외 매도) 뒤 매도자 잔고 0 (2026-11-18)\n")
P_("사건(2015-10~, 보통주·종가 1,000원↑): %d건 · 금액 중앙 %.1f억 · 묶음별 %s" % (len(E), E.amt.median(), E.grp.value_counts().to_dict()))
P_("거래일 → 공시일 거래일 수: 중앙 %d · 같은 날 %.0f%% · 1일 뒤 %.0f%% · 3일↑ %.0f%%" % (E.lag.median(), (E.lag == 0).mean() * 100, (E.lag == 1).mean() * 100, (E.lag >= 3).mean() * 100))
P_("\n## 사건 성질(금액 10억↑)\n\n| 묶음 | 건 | 금액 중앙(억) | 신고 단가 할인 중앙 | 거래 전날→공시일 종가 중앙 | 공시 다음 날 시가 갭 중앙 | 직전 20일 등락 중앙 |\n|---|---|---|---|---|---|---|")
B = E[E.amt >= 10]
for gname in ("잔고 0", "일부 남김", "섞임"):
    z = B[B.grp == gname]
    P_("| %s | %d | %.0f | %+.1f%% | %+.1f%% | %+.2f%% | %+.1f%% |" % (gname, len(z), z.amt.median(), z.disc.median(), z.pre.median(), z.gap.median(), z.p20.median()))

def table(title, base, rets=RET):
    P_("\n## %s\n\n| 묶음 | 판 %s\n|---|---|---|---|---|---|---|---|---|---|" % (title, HEAD))
    for gname in ("잔고 0", "일부 남김"):
        for k, A in rets.items():
            Z = nodup(base[base.grp == gname], HOLD[k]).copy()
            Z["r"] = A[Z.i.values, Z.j.values]; Z["m"] = MK[k][Z.i.values]
            P_("| %s | %s | %s |" % (gname, k, both(Z)))

table("말한 판과 보유 기간 변형 — 금액 10억↑", B)
k0 = "D+1 시가→D+5 종가(말한 판)"
P_("\n## 금액 문턱 변형 — %s\n\n| 금액 | 묶음 %s\n|---|---|---|---|---|---|---|---|---|---|" % (k0, HEAD))
for lo in (1, 5, 10, 30, 100):
    for gname in ("잔고 0", "일부 남김"):
        Z = nodup(E[(E.amt >= lo) & (E.grp == gname)], 5).copy(); Z["r"] = RET[k0][Z.i.values, Z.j.values]; Z["m"] = MK[k0][Z.i.values]
        P_("| %d억↑ | %s | %s |" % (lo, gname, both(Z)))
P_("\n## 잔고 0 − 일부 남김(금액 10억↑, 같은 판) 차이\n\n| 판 | 학습 차이(%p) | 검증 차이(%p) |\n|---|---|---|")
for k, A in RET.items():
    out = []
    for _, a, b in SPLIT:
        zz = []
        for gname in ("잔고 0", "일부 남김"):
            Z = nodup(B[(B.grp == gname) & (B.day >= a) & (B.day <= b)], HOLD[k]); zz.append(pd.Series(A[Z.i.values, Z.j.values]).dropna())
        x, y = zz
        se = math.sqrt(x.var(ddof=1) / max(len(x), 1) + y.var(ddof=1) / max(len(y), 1)) if len(x) > 2 and len(y) > 2 else float("nan")
        out.append("%+.2f (t%.1f · %d vs %d건)" % (x.mean() - y.mean(), (x.mean() - y.mean()) / se if se == se and se > 0 else 0, len(x), len(y)))
    P_("| %s | %s | %s |" % (k, out[0], out[1]))
P_("\n## 잔고 0 · 금액 10억↑ · 말한 판 해마다\n\n| 해 | 건 | 건당 | 중앙 | 승률 | 시장 대비 |\n|---|---|---|---|---|---|")
Z = nodup(B[B.grp == "잔고 0"], 5).copy(); Z["r"] = RET[k0][Z.i.values, Z.j.values]; Z["m"] = MK[k0][Z.i.values]; Z = Z.dropna(subset=["r"])
for y, z in Z.groupby(Z.day.str[:4]):
    P_("| %s | %d | %+.2f%% | %+.2f%% | %.0f%% | %+.2f |" % (y, len(z), z.r.mean(), z.r.median(), (z.r > 0).mean() * 100, (z.r - z.m).mean()))
P_("\n## 덧붙인 변형 — 잔고 0 안에서\n\n| 조건 | 판 %s\n|---|---|---|---|---|---|---|---|---|---|" % HEAD)
VAR = {"공시 다음 날 시가 갭 ≤ -1%": B.gap <= -1, "거래 전날→공시일 -5%↓(이미 많이 빠짐)": B.pre <= -5, "거래 전날→공시일 > -5%": B.pre > -5,
       "직전 20일 -10%↓": B.p20 <= -10, "거래 당일 공시(늦지 않음)": B.lag == 0, "금액 30억↑": B.amt >= 30}
for nm, m in VAR.items():
    for k in (k0, "D+1 시가→D+10 종가"):
        Z = nodup(B[m & (B.grp == "잔고 0")], HOLD[k]).copy(); Z["r"] = RET[k][Z.i.values, Z.j.values]; Z["m"] = MK[k][Z.i.values]
        P_("| %s | %s | %s |" % (nm, k, both(Z)))
P_("\n- 비용 0.23% 뺀 값. 날 바구니 = 같은 날 사건을 하루 한 표본으로. 시장 대비 = 같은 날 종가 1,000원↑ 전 종목 평균을 뺀 값.")
P_("- 임원·주요주주(10%↑) 신고만 있다 — 5% 보고(대량보유)로만 드러나는 블록딜은 빠져 있다. 경영권 이전 거래를 따로 가르지 못했다.")
save("blockzero_1118.md")
