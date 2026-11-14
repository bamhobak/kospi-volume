# -*- coding: utf-8 -*-
"""2026-11-15 사용자 "지금 규칙들을 방식은 비슷하게, 자료는 다른 걸 쓰면서 겹침은 줄이면서" — ④⑤ 스윙 형제.
portfolio.py 규칙식 그대로에서 **조건 하나만 다른 자료로** 바꾼 형제 규칙을 RULES 에 덧붙여 같은 방식(매수가·청산·비용·자리)으로 잰다.
  ④ 수급 주체 바꾸기(investor.db flow11, 2018~ · 금액 ÷ 같은 기간 거래대금 %):
     [외인 매집] P7 의 '외국인 20일 ≥ 1% · 기관 60일 < 0.4%' → 투신(t)·사모(s)·연기금(n) 20일 · x 판은 '외국인 20일 < 1%'(원래 규칙과 안 겹치게)
     [폭락반등] P3 · D1 의 '외국인 60일 ≥ 1%' → 투신·사모·연기금 60일
  ⑤ 싼 종목 기준 바꾸기(krx_daily fundamental): [저PBR 낙폭] D2 의 'PBR ≤ 0.8' → PER(e)·배당수익률(d) · x 판은 'PBR > 0.8'(안 겹치게)
  문턱 = 원래 조건이 걸리는 비율과 같은 분위(그 패널 2018~ 전체 행 기준)로 맞춤 — 신호 수가 원래와 비슷하게.
판정: 거래 단위(학습 2018~22 / 검증 2023~, portfolio 의 비용 뒤 수익) · 겹침(같은 종목에 원래 규칙 신호가 ±5거래일 안) ·
      계좌(1억, portfolio 비중·자리 그대로 · 금액 체결 손해 0.143+1.321√p · 매일 종가 평가) 9규칙 vs 9규칙 + 형제 하나.
    python research/memguard.py research/sib_swing_1115.py → research/reports/sib_swing_1115.md"""
import io, os, sys, time, math, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parent.parent
os.chdir(BASE); sys.path.insert(0, str(BASE)); sys.path.insert(0, str(BASE / "research" / "factory"))
t0 = time.time()
os.environ.setdefault("PANEL_KP", "slim/panel_kp.pkl"); os.environ.setdefault("PANEL_KQ", "slim/panel_kq.pkl")
sys.argv = sys.argv[:1]
OUT = []
src = (BASE / "portfolio.py").read_text(encoding="utf-8").split("# @@ANALYSIS")[0]
_OLD_CR = '''    _M = _K.merge(_CR[["date","ticker","cr_chg20"]], on=["ticker","date"], how="left")
    assert len(_M) == _n
    _K["cr_chg20"] = _M.cr_chg20.values'''
_NEW_CR = '''    _M = None
    _K["cr_chg20"] = _CR.drop_duplicates(["ticker","date"]).set_index(["ticker","date"]).cr_chg20.reindex(pd.MultiIndex.from_arrays([_K.ticker.values, _K.date.values])).values'''
assert src.count(_OLD_CR) == 1
src = src.replace(_OLD_CR, _NEW_CR)

INJECT = r'''
# ── (sib_swing 11-15) 형제 규칙 재료: 수급 주체별 20·60일 금액 ÷ 거래대금 % · PER · 배당수익률
_fc = sqlite3.connect(f"file:{BASE}/data/investor.db?mode=ro", uri=True)
_F = pd.read_sql("SELECT ticker, date, frgn, tru, pef, pens FROM flow11 WHERE date >= '20170901'", _fc); _fc.close()
_F = _F.sort_values(["ticker", "date"]); _g = _F.groupby("ticker", sort=False)
for _c in ("frgn", "tru", "pef", "pens"):
    for _h in (20, 60): _F["%s%d" % (_c, _h)] = _g[_c].transform(lambda s, h=_h: s.rolling(h, min_periods=int(h * 0.7)).sum())
_F = _F.drop_duplicates(["ticker", "date"]).set_index(["ticker", "date"])
_kc = sqlite3.connect(f"file:{BASE}/data/krx_daily.db?mode=ro", uri=True)
_V = pd.read_sql("SELECT ticker, date, per, div FROM fundamental WHERE date >= '20170901'", _kc); _kc.close()
_V = _V.drop_duplicates(["ticker", "date"]).set_index(["ticker", "date"])
for _K in (KP, KQ):
    _ix = pd.MultiIndex.from_arrays([_K.ticker.values, _K.date.values])
    _den = (_K.amt20.values * 1e8)
    for _c in ("frgn", "tru", "pef", "pens"):
        for _h in (20, 60): _K["x%s%d" % (_c, _h)] = (_F["%s%d" % (_c, _h)].reindex(_ix).values / (_den * _h) * 100).astype(np.float32)
    _K["per"] = _V.per.reindex(_ix).values.astype(np.float32); _K["divy"] = _V["div"].reindex(_ix).values.astype(np.float32)
del _F, _V, _g; import gc as _gc2; _gc2.collect()
def _qmatch(K, base_mask, col, hi=True, lo0=False):
    """원래 조건이 걸리는 비율(2018~ 행)만큼 col 의 위(hi) 또는 아래 분위 문턱"""
    m = K.date >= "20180101"; q = float(base_mask[m].mean()); v = K.loc[m, col]
    if lo0: v = v[v > 0]
    return float(v.quantile(1 - q) if hi else v.quantile(q)), q
SIBTH = {}
'''
SIBS = r'''
# ── (sib_swing 11-15) 형제 규칙 — 원래 규칙식 그대로, 조건 하나만 바꿈
_p7rest = base(KP,30)&up60(KP)&(KP["cap조"]>=1)&(KP["cap조"]<10)&(KP.r16>=100)&(KP.r16<150)&(KP.fromhi>=-15)&(KP.fromlo>=70)&(KP.ins60.fillna(0)>0)
for _c, _s in (("tru", "t"), ("pef", "s"), ("pens", "n")):
    _th, _q = _qmatch(KP, KP.fw20 >= 1, "x%s20" % _c); SIBTH["P7" + _s] = (_th, _q)
    RULES["P7" + _s] = (KP, 60, None, 4.8, 5, _p7rest & (KP["x%s20" % _c] >= _th))
    RULES["P7" + _s + "x"] = (KP, 60, None, 4.8, 5, _p7rest & (KP["x%s20" % _c] >= _th) & ~(KP.fw20 >= 1))
    _th3, _q3 = _qmatch(KP, KP.fw60 >= 1, "x%s60" % _c); SIBTH["P3" + _s] = (_th3, _q3)
    RULES["P3" + _s] = (KP, 20, None, 6, 3, base(KP,3)&dn60(KP)&(KP.ret20<=-25)&(KP.su1>=1.5)&(KP["x%s60" % _c]>=_th3)&(KP.u<=-10)&(KP.srd==True)&(KP.cr_chg20<=-15))
    _thd, _qd = _qmatch(KQ, KQ.fw60 >= 1, "x%s60" % _c); SIBTH["D1" + _s] = (_thd, _qd)
    RULES["D1" + _s] = (KQ, 20, None, 6, 3, base(KQ,2)&dn60(KQ)&(KQ.ret20<=-30)&(KQ.su1>=1.5)&(KQ["x%s60" % _c]>=_thd)&(KQ.u<=-20)&(KQ.srd==True)&(KQ.ow20>=0)&(KQ['부채비율'].isna()|(KQ['부채비율']<=200)))
_d2rest = base(KQ,5)&dn60(KQ)&(KQ.ret20<=-10)&(KQ.su1>=2)&(KQ.u<=-10)&(KQ.ow20>=0)&(KQ.srd==True)
_pbr = (KQ.PBR>0)&(KQ.PBR<=0.8)
_the, _qe = _qmatch(KQ, _pbr, "per", hi=False, lo0=True); SIBTH["D2e"] = (_the, _qe)
_thv, _qv = _qmatch(KQ, _pbr, "divy", hi=True); SIBTH["D2d"] = (_thv, _qv)
RULES["D2e"] = (KQ, 40, None, 6, 3, _d2rest & (KQ.per > 0) & (KQ.per <= _the))
RULES["D2ex"] = (KQ, 40, None, 6, 3, _d2rest & (KQ.per > 0) & (KQ.per <= _the) & ~_pbr)
RULES["D2d"] = (KQ, 40, None, 6, 3, _d2rest & (KQ.divy >= _thv))
RULES["D2dx"] = (KQ, 40, None, 6, 3, _d2rest & (KQ.divy >= _thv) & ~_pbr)
'''
K1 = chr(10) + "RULES = {"
K2 = "# 규칙을 빼고 돌려보는 스위치"
assert src.count(K1) == 1 and src.count(K2) == 1
src = src.replace(K1, chr(10) + INJECT + K1).replace(K2, SIBS + K2)
ns = {"__file__": str(BASE / "portfolio.py"), "__name__": "x"}
_real = sys.stdout; sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
try:
    exec(compile(src, "portfolio.py", "exec"), ns)
finally:
    sys.stdout = _real
sys.stdout.reconfigure(encoding="utf-8")
P = lambda s="": (OUT.append(str(s)), print(s, flush=True))
S, dates, KP, KQ, SIBTH = ns["S"], ns["dates"], ns["KP"], ns["KQ"], ns["SIBTH"]
print("portfolio %.1f분 · 신호 %d" % ((time.time() - t0) / 60, len(S)), flush=True)
BASE9 = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "D1", "D2"]
SIB = [r for r in S.rid.unique() if r not in BASE9]
PARENT = lambda r: r[:2]
NM = {"P7": "[외인 매집]", "P3": "[폭락반등]", "D1": "[폭락반등 코스닥]", "D2": "[저PBR 낙폭]"}
WHO = {"t": "투신", "s": "사모", "n": "연기금", "e": "PER", "d": "배당"}
lab = lambda r: "%s 형제 · %s%s" % (NM.get(PARENT(r), PARENT(r)), WHO.get(r[2], r[2]), " · 원래와 안 겹치게" if r.endswith("x") else "")
S = S[S.date >= "20180101"].copy()
S["ret"] = (S.exit / S.buy - 1) * 100 - S.cost
DI = {d: i for i, d in enumerate(dates)}
from verdict import log_trials
log_trials("sibling_swing_1115", len(SIB))
P("# 스윙 형제 규칙 — 같은 원리 · 다른 자료 (2026-11-15)\n")
P("- portfolio.py 규칙식에서 조건 하나만 바꿈 · 2018~ (수급 자료가 2018~) · 학습 2018~22 / 검증 2023~ · 비용 뒤 · 문턱 = 원래 조건과 같은 비율 분위\n")
P("| 형제 | 바꾼 조건(문턱) | 학습 건수·건당·승률 | 검증 건수·건당·승률 | 원래 규칙 검증 건당 | 겹침(원래 신호 ±5일) |"); P("|---|---|---|---|---|---|")
sig = {r: g for r, g in S.groupby("rid")}
def ovl(r):
    a = sig.get(r); b = sig.get(PARENT(r))
    if a is None or b is None or not len(a): return np.nan
    bi = b.groupby("ticker").di.apply(np.array).to_dict()
    return np.mean([any(abs(x - y) <= 5 for y in bi.get(t, [])) for t, x in zip(a.ticker, a.di)]) * 100
ST = {}
for r in sorted(SIB):
    g = sig[r]; a = g[g.date < "20230101"]; b = g[g.date >= "20230101"]; pb = sig.get(PARENT(r)); pbv = pb[pb.date >= "20230101"] if pb is not None else None
    th = SIBTH.get(r.rstrip("x"), (np.nan, np.nan))
    ST[r] = dict(na=len(a), ma=a.ret.mean(), nb=len(b), mb=b.ret.mean(), ov=ovl(r))
    P("| %s | %s ≥ %.2f%s | %d · %+.2f%% · %.0f%% | %d · %+.2f%% · %.0f%% | %s | %.0f%% |" % (
        lab(r), WHO.get(r[2], r[2]), th[0], "(원래 조건 %.1f%% 분위)" % (th[1] * 100) if th[1] == th[1] else "", len(a), a.ret.mean() if len(a) else np.nan, (a.ret > 0).mean() * 100 if len(a) else 0,
        len(b), b.ret.mean() if len(b) else np.nan, (b.ret > 0).mean() * 100 if len(b) else 0,
        "%+.2f%% (%d)" % (pbv.ret.mean(), len(pbv)) if pbv is not None and len(pbv) else "-", ST[r]["ov"]))
P("\n(PER 은 '≤' 문턱 — 표의 '≥' 는 PER 만 거꾸로 읽을 것)")

# ── 계좌: 9규칙 vs 9규칙 + 형제 하나
KB = pd.concat([KP[["ticker", "date", "close"]], KQ[["ticker", "date", "close"]]], ignore_index=True).drop_duplicates(["ticker", "date"])
KB = KB[KB.date >= "20171201"]
TK = np.array(sorted(KB.ticker.unique())); TI = {t: i for i, t in enumerate(TK)}
ND = len(dates); CL = np.full((ND, len(TK)), np.nan, np.float32)
di_ = KB.date.map(DI); ok = di_.notna().values
CL[di_.values[ok].astype(int), KB.ticker.map(TI).values[ok]] = KB.close.values[ok]
CLf = pd.DataFrame(CL).ffill().values; del CL, KB
S["ti"] = S.ticker.map(TI); UNIT = 1e8 if S.amt20.median() < 1e5 else 1.0
imp = lambda p: max(0.0, 0.143 + 1.321 * math.sqrt(p))
def sim(rids, C=1e8, d0="20180102", d1="20261008"):
    Z = S[S.rid.isin(rids)]; TOD = {i: g for i, g in Z.groupby("di")}
    i0, i1 = DI[min(d for d in dates if d >= d0)], DI[max(d for d in dates if d <= d1)]
    eq = C; pos = []; nav = []
    for i in range(i0, i1 + 1):
        still = []
        for p in pos:
            if p["x"] <= i: eq += p["amt"] * ((p["exit"] / p["buy"] - 1) * 100 - p["cost"] - p["imp"]) / 100
            else: still.append(p)
        pos = still; T = TOD.get(i)
        if T is not None:
            inv = sum(p["amt"] for p in pos)
            for t in T.itertuples():
                w = eq * t.pct / 100
                if sum(1 for p in pos if p["rid"] == t.rid) >= t.mx or inv + w > eq or any(p["tk"] == t.ticker for p in pos): continue
                pi = w / (t.amt20 * UNIT) * 100 if t.amt20 and t.amt20 > 0 else 50
                pos.append(dict(rid=t.rid, tk=t.ticker, ti=t.ti, buy=t.buy, exit=t.exit, cost=t.cost, imp=imp(pi), amt=w, x=i + t.hold, d0=i)); inv += w
        un = sum(p["amt"] * (CLf[i, p["ti"]] / p["buy"] - 1) for p in pos if i > p["d0"] and CLf[i, p["ti"]] == CLf[i, p["ti"]])
        nav.append(eq + un)
    x = pd.Series(nav, index=dates[i0:i1 + 1])
    a = x[x.index <= "20221231"]; b = x[x.index >= "20221229"]
    cg = lambda y: (y.iloc[-1] / y.iloc[0]) ** (250 / len(y)) - 1
    return dict(fin=x.iloc[-1] / C, ya=cg(a) * 100, yb=cg(b) * 100, mdd=(x / x.cummax() - 1).min() * 100)
P("\n## 계좌 1억 — 9규칙 vs 9규칙 + 형제 하나 (2018-01~2026-10 · 비중·자리는 원래 규칙 것 그대로)\n")
P("| 구성 | 끝 배수 | 2018~22 연 | 2023~ 연 | 최대 낙폭 |"); P("|---|---|---|---|---|")
b0 = sim(BASE9)
P("| 9규칙(지금) | %.2f배 | %+.1f%% | %+.1f%% | %.1f%% |" % (b0["fin"], b0["ya"], b0["yb"], b0["mdd"]))
for r in sorted(SIB, key=lambda r: -(ST[r]["mb"] if ST[r]["mb"] == ST[r]["mb"] else -99)):
    if not (ST[r]["nb"] >= 5 and ST[r]["mb"] > 0 and ST[r]["ma"] > 0): continue
    o = sim(BASE9 + [r])
    P("| + %s | %.2f배 (%+.2f) | %+.1f%% | %+.1f%% | %.1f%% |" % (lab(r), o["fin"], o["fin"] - b0["fin"], o["ya"], o["yb"], o["mdd"]))
    print("  계좌 %s %.1f분" % (r, (time.time() - t0) / 60), flush=True)
P("\n(학습·검증 둘 다 건당 플러스이고 검증 5건↑ 인 형제만 계좌에 넣어 봄)")
(BASE / "research" / "reports" / "sib_swing_1115.md").write_text("\n".join(OUT), encoding="utf-8")
print("끝 %.1f분" % ((time.time() - t0) / 60))
