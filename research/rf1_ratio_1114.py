# -*- coding: utf-8 -*-
"""2026-11-14 새 규칙 찾기 1번 '자료 강제 짝짓기' — '물량 ÷ 받아 줄 유동성' 꼴 비율 재료를 격자로 만들어 공장 판정(lab.judge)에 그대로 넣는다.
분자(원, 그날 장 끝나고 앎): 외인·기관·개인 순매수 1일·5일(investor.db flow11, 2018~) · 신용 잔고·하루 변화(market.db credit, 2거래일 늦춤)
     · 공매도 잔고·하루 변화(krx_daily short_balance, T+2 공개 → 2거래일 늦춤) · 공매도 거래량(krx_daily short_volume, 그날)
분모: 20일 평균 거래대금 · 그날 거래대금 · 시가총액.  11 × 3 = 33 재료, 이름 rx_분자_분모.
재료는 d 날 장 끝나고 아는 값 → d+1 날 행에 붙여 '장전(pre)' 재료로 등록(FT.FEATS) — 미래 정보 없음. 수급 재료는 FT.FLOW 에도 넣어 학습 2018~.
명세: 재료 위 10% / 아래 10% × 방식 oc(다음 날 시가→종가) · sw5 · sw20  + 같은 걸 '어제 등락 하위 20%(많이 빠진 종목)'과 붙인 판.
판정 = 공장 깔때기 그대로(G1 학습 + ⑪ 학습 거울 · G2 검증 VA_MIN·중앙 · 다중검정(공장 누적 시험수) · 관문 4종). 시행 수는 verdict.log_trials 에 적음.
    python research/memguard.py research/rf1_ratio_1114.py   → research/reports/rf1_ratio_1114.md"""
import sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path[:0] = [str(ROOT / "factory"), str(ROOT)]
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
import lab, feats as FT, gates as GT
from verdict import log_trials
OUT = []; P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
t0 = time.time()
BUILD = "--build" in sys.argv
RF = Path(r"C:/temp/kp/rf1_ratio_1114.pkl")
if True:
    U0 = pd.read_pickle(lab.HIST)
    D = U0[["ticker", "date", "amt20", "amtt", "mcap"]].copy(); CAL = sorted(U0.date.astype(str).unique()); del U0
PX = pd.read_pickle(BASE / "research" / "cache" / "factory_px.pkl")[["ticker", "date", "close"]]
PX = PX[PX.date >= "20151101"].copy(); PX["ticker"] = PX.ticker.astype(str); PX["date"] = PX.date.astype(str)
c = sqlite3.connect("file:" + str(BASE / "data" / "investor.db") + "?mode=ro", uri=True)
F = pd.read_sql("SELECT ticker, date, frgn AS f, indiv AS p, (COALESCE(fin,0)+COALESCE(ins,0)+COALESCE(tru,0)+COALESCE(pef,0)+COALESCE(bank,0)+COALESCE(ofin,0)+COALESCE(pens,0)) AS i FROM flow11", c)
m = sqlite3.connect("file:" + str(BASE / "data" / "kis" / "market.db") + "?mode=ro", uri=True, timeout=600)
CR = pd.read_sql("SELECT ticker, date, loan_rmnd FROM credit WHERE date >= '20151101'", m)
k = sqlite3.connect("file:" + str(BASE / "data" / "krx_daily.db") + "?mode=ro", uri=True)
SB = pd.read_sql("SELECT ticker, date, bal_qty FROM short_balance", k)
SV = pd.read_sql("SELECT ticker, date, short_vol FROM short_volume WHERE date >= '20151101'", k)
D["ticker"] = D.ticker.astype(str); D["date"] = D.date.astype(str)
X = PX.merge(D, on=["ticker", "date"], how="inner")
for T in (F, CR, SB, SV):
    T["ticker"] = T.ticker.astype(str); T["date"] = T.date.astype(str)
    X = X.merge(T, on=["ticker", "date"], how="left")
X = X.sort_values(["ticker", "date"]).reset_index(drop=True)
g = X.groupby("ticker", sort=False)
for a in "fip": X[a + "5"] = g[a].transform(lambda s: s.rolling(5, min_periods=3).sum())
X["loan_rmnd"] = g.loan_rmnd.shift(2); X["bal_qty"] = g.bal_qty.shift(2)
g = X.groupby("ticker", sort=False)
NUM = {"외인1": X.f, "외인5": X.f5, "기관1": X.i, "기관5": X.i5, "개인1": X.p, "개인5": X.p5,
       "신용잔고": X.loan_rmnd * X.close, "신용변화": g.loan_rmnd.diff() * X.close,
       "공매잔고": X.bal_qty * X.close, "공매변화": g.bal_qty.diff() * X.close, "공매거래": X.short_vol * X.close}
DEN = {"a20": X.amt20 * 1e8, "amt": X.amtt * 1e8, "cap": X.mcap * 1e8}
KEY = {"외인1": "f1", "외인5": "f5", "기관1": "i1", "기관5": "i5", "개인1": "p1", "개인5": "p5", "신용잔고": "cl", "신용변화": "cd", "공매잔고": "sl", "공매변화": "sd", "공매거래": "sv"}
R = X[["ticker", "date"]].copy(); names = []
for nn, nv in NUM.items():
    for dn, dv in DEN.items():
        f = "rx_%s_%s" % (KEY[nn], dn)
        R[f] = (nv / dv.where(dv > 0)).astype(np.float32); names.append(f)
        FT.FEATS[f] = ("%s ÷ %s(전날 장 끝 기준)" % (nn, {"a20": "20일 거래대금", "amt": "그날 거래대금", "cap": "시가총액"}[dn]), "pre", "s")
        if KEY[nn][0] in "fip": FT.FLOW.add(f)
NXT = dict(zip(CAL[:-1], CAL[1:]))
R["date"] = R.date.map(NXT); R = R.dropna(subset=["date"]).drop_duplicates(["ticker", "date"])
R.to_pickle(RF); del X, NUM, DEN, F, CR, SB, SV, PX, D
import gc; gc.collect()
print("비율 재료 저장 %d행 · %.1f분" % (len(R), (time.time() - t0) / 60), flush=True)
U = lab.hist()
ix = pd.MultiIndex.from_arrays([U.ticker.astype(str).values, U.date.astype(str).values])
R = R.set_index(["ticker", "date"])
for f in names:
    U[f] = R[f].reindex(ix).values
    U["q_" + f] = U.groupby("date")[f].rank(pct=True).astype(np.float32)
del R; gc.collect()
lab._U = U
print("재료 %d개 붙임 · %.1f분 · 채움률 예 %s" % (len(names), (time.time() - t0) / 60, {f: round(float(U[f].notna().mean()), 2) for f in names[::6]}), flush=True)
SPECS = []
for f in names:
    for side, op, v in (("위 10%", ">=", 0.9), ("아래 10%", "<=", 0.1)):
        for mode in ("oc", "sw5", "sw20"):
            SPECS.append(dict(name="%s %s" % (f, side), origin="ratio", mode=mode, conds=[{"f": f, "q": True, "op": op, "v": v}]))
            if mode in ("oc", "sw5"):
                SPECS.append(dict(name="%s %s + 어제 많이 빠짐" % (f, side), origin="ratio", mode=mode,
                                  conds=[{"f": f, "q": True, "op": op, "v": v}, {"f": "r1", "q": True, "op": "<=", "v": 0.2}]))
SPECS = [s for s in SPECS if lab.check(s) is None]
log_trials("rulefind_ratio_1114", len(SPECS))
print("명세 %d개" % len(SPECS), flush=True)
res = []
for i, s in enumerate(SPECS):
    try: Rj = lab.judge(s, U)
    except Exception as ex: res.append(dict(s=s, stage=-1, why=repr(ex)[:100])); continue
    res.append(dict(s=s, stage=Rj["stage"], why=Rj["why"], tr=Rj.get("tr"), va=Rj.get("va"), dsr=Rj.get("dsr"), gates=Rj.get("gates"), mtr=Rj.get("mirror_tr")))
    if i % 25 == 0: print("  %d/%d · %.1f분" % (i, len(SPECS), (time.time() - t0) / 60), flush=True)
from collections import Counter
st = Counter(r["stage"] for r in res)
P("# 자료 강제 짝짓기 — 물량 ÷ 유동성 비율 재료 (11-14)\n")
P("- 재료 %d개(분자 11 × 분모 3) · 명세 %d개(위·아래 10%% × oc·sw5·sw20 + '어제 많이 빠짐' 붙인 판) · 공장 깔때기 그대로" % (len(names), len(SPECS)))
P("- 결과: 학습 탈락 %d · ⑪ 학습 거울 탈락 %d · 검증 탈락 %d · **통과 %d** · 오류 %d\n" % (
    sum(1 for r in res if r["stage"] == 0 and not str(r["why"]).startswith("⑪")), sum(1 for r in res if r["stage"] == 0 and str(r["why"]).startswith("⑪")),
    st.get(1, 0), st.get(2, 0), st.get(-1, 0)))
import re as _re
P("떨어진 이유(숫자 지움) 많은 순: " + " · ".join("%s %d" % kv for kv in Counter(_re.sub(r"[-+]?[0-9][0-9.,]*", "#", str(r["why"]).split(" · ")[0])[:30] for r in res if r["stage"] < 2).most_common(8)))
TRB = sorted([r for r in res if r.get("tr")], key=lambda r: -(r["tr"].get("t") or 0))[:15]
P("\n## 학습 하루 t 높은 순(참고 — 학습 기준 미달이어도)\n")
P("| 명세 | 방식 | 학습 건수·건당·t·플러스 해 | 떨어진 이유 |"); P("|---|---|---|---|")
for r in TRB:
    t = r["tr"]; P("| %s | %s | %s건 %+.2f%% t%.1f %d/%d해 | %s |" % (r["s"]["name"], r["s"]["mode"], t["n"], t["mean"], t["t"], t["ypos"], t["ny"], str(r["why"])[:90]))
P("")
P("## 학습 통과(G1) 명세 — 검증 성적 순\n")
P("| 명세 | 방식 | 학습 건수·건당·t | 검증 건수·건당·중앙 | 다중검정 | 판정 / 걸린 이유 |"); P("|---|---|---|---|---|---|")
G1 = sorted([r for r in res if r["stage"] >= 1], key=lambda r: -((r["va"] or {}).get("mean") or -99))
for r in G1[:40]:
    t, v = r["tr"] or {}, r["va"] or {}
    P("| %s | %s | %s건 %+.2f%% t%.1f | %s건 %+.2f%% / %+.2f%% | %s | %s |" % (r["s"]["name"], r["s"]["mode"], t.get("n", 0), t.get("mean", 0), t.get("t", 0),
      v.get("n", 0), v.get("mean", 0) or 0, v.get("med", 0) or 0, ("%.2f" % r["dsr"]) if r["dsr"] is not None else "-",
      "**통과** " + GT.fmt(r["gates"]) if r["stage"] >= 2 else str(r["why"])[:110]))
fams = Counter(r["s"]["conds"][0]["f"].split("_")[1] for r in res if r["stage"] >= 1)
P("\n학습 통과 분자별 수: " + str(dict(fams)))
P("\n⑪ 학습 거울로 떨어진 것 예: " + " · ".join("%s(%s) 거울 %+.2f" % (r["s"]["name"], r["s"]["mode"], (r["mtr"] or {}).get("inv_mean") or (r["mtr"] or {}).get("inv_ex") or 0)
                                         for r in res if str(r["why"]).startswith("⑪"))[:600])
(ROOT / "reports" / "rf1_ratio_1114.md").write_text("\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
