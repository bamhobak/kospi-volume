# -*- coding: utf-8 -*-
"""DART 공시 이벤트 실측 — 공시 접수일 다음날 시가 매수 · 지수 대비 초과수익 · 비용 반영
   미래참조 없음: rcept_dt(접수일)는 그날 장 마감 전후 공개되므로 다음 거래일 시가 매수로 처리"""
import io, sqlite3, sys
import numpy as np, pandas as pd
import FinanceDataReader as fdr
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
NB = 70
con = sqlite3.connect("file:data/kospi.db?mode=ro", uri=True)
df = pd.read_sql("""SELECT date,ticker,close,volume,open,high,low FROM daily
   WHERE market='KOSPI' AND close IS NOT NULL AND open>0 ORDER BY ticker,date""", con)
dates = [r[0] for r in con.execute("SELECT DISTINCT date FROM daily ORDER BY date")]; con.close()
POS = {d: i for i, d in enumerate(dates)}
ki = fdr.DataReader("KS11", "2017-12-01"); ki = ki[ki.Close > 0]; ki.index = ki.index.strftime("%Y%m%d")
KO, KC = ki["Open"].to_dict(), ki["Close"].to_dict()
d = sqlite3.connect("file:data/dart/disclosures.db?mode=ro", uri=True)
disc = pd.read_sql("SELECT stock_code AS ticker, rcept_dt, report_nm FROM disclosure", d); d.close()
disc["nm"] = disc.report_nm.str.replace(" ", "")
disc = disc[~disc.nm.str.contains("기재정정|첨부정정|첨부추가|철회", na=False)]   # 정정·철회 공시 제외
print(f"공시 {len(disc):,}건 (정정 제외)")

# 종목별 가격 배열
PX = {}
for t, g in df.groupby("ticker", sort=False):
    if not t.endswith("0"): continue
    g = g.reset_index(drop=True)
    V = g.volume.values.astype(float); C = g.close.values.astype(float)
    amt = pd.Series(V * C).rolling(20).mean().values / 1e8
    PX[t] = dict(d={x: i for i, x in enumerate(g.date.values)}, O=g.open.values.astype(float),
                 H=g.high.values.astype(float), L=g.low.values.astype(float), C=C, amt=amt, n=len(g))

def cost(a):
    a = a or 3
    return 0.18 + (0.20 if a >= 100 else 0.30 if a >= 50 else 0.50 if a >= 20 else 0.70 if a >= 10 else 1.00)

def signals(pattern):
    sub = disc[disc.nm.str.contains(pattern, na=False, regex=True)]
    out = []; seen = set()
    for r in sub.itertuples():
        p = PX.get(r.ticker)
        if not p: continue
        # 접수일 이후 첫 거래일을 j(신호일)로, 그 다음날 시가 매수
        dd = [x for x in (r.rcept_dt,) if x in p["d"]]
        if dd: j = p["d"][dd[0]]
        else:
            later = [x for x in p["d"] if x > r.rcept_dt]
            if not later: continue
            j = p["d"][min(later)]
        key = (r.ticker, j)
        if key in seen or j + 1 >= p["n"]: continue
        seen.add(key)
        o0 = p["O"][j + 1]
        if not np.isfinite(o0) or o0 <= 0: continue
        e = min(j + 1 + NB, p["n"])
        dt_ = [k for k, v in p["d"].items() if v == j][0]
        out.append(dict(t=r.ticker, d=dt_, y=int(dt_[:4]), amt=p["amt"][j] if np.isfinite(p["amt"][j]) else 0.0,
                        H=(p["H"][j+1:e]/o0-1)*100, L=(p["L"][j+1:e]/o0-1)*100, C=(p["C"][j+1:e]/o0-1)*100))
    return out

def ev2(s, h):
    C = s["C"]; n = min(h, len(C) - 1)
    return C[n] - cost(s["amt"]), n
def mkt(s, hh):
    p = POS.get(s["d"])
    if p is None or p + 1 + hh >= len(dates): return None
    o, c = KO.get(dates[p + 1]), KC.get(dates[p + 1 + hh])
    return None if not o or not c else (c / o - 1) * 100
def A(P, h, mn=20):
    rows = []
    for s in P:
        if len(s["C"]) < 2: continue
        r, hh = ev2(s, h); m = mkt(s, hh)
        if m is None: continue
        rows.append((s["y"], r, r - m))
    if len(rows) < mn: return None
    dd = pd.DataFrame(rows, columns=["y", "ret", "al"])
    yy = dd.groupby("y").al.mean(); cnt = dd.groupby("y").size(); ok = yy[cnt >= 3]
    return dict(n=len(dd), ret=dd.ret.mean(), al=dd.al.mean(), med=dd.al.median(),
                win=(dd.ret > 0).mean() * 100, alwin=(dd.al > 0).mean() * 100, pos=f"{(ok>0).sum()}/{len(ok)}")

EVENTS = [
    ("자기주식 취득결정", "자기주식취득결정"),
    ("자기주식 취득 신탁계약 체결", "자기주식취득신탁계약체결"),
    ("자기주식 소각", "주식소각"),
    ("자기주식 처분결정", "자기주식처분결정"),
    ("무상증자 결정", "무상증자결정"),
    ("유상증자 결정", "유상증자결정"),
    ("전환사채 발행", "전환사채권발행결정"),
    ("현금·현물배당 결정", "현금ㆍ현물배당결정|현금·현물배당결정"),
    ("단일판매·공급계약", "단일판매.{0,3}공급계약"),
    ("손익구조 30% 변동", "손익구조30"),
    ("최대주주 변경", "최대주주변경(?!.*신고)"),
    ("회사합병 결정", "회사합병결정"),
    ("타법인 주식 취득", "타법인주식및출자증권취득결정"),
    ("타법인 주식 처분", "타법인주식및출자증권처분결정"),
    ("영업정지", "영업정지"),
    ("불성실공시", "불성실공시"),
]
HOR = (1, 3, 5, 10, 20, 60)
print("\n## 공시 이벤트별 초과수익 (접수 다음날 시가 매수 · 우선주 제외)\n")
print("| 이벤트 | 건수 | " + " | ".join(f"{h}일" for h in HOR) + " | 20일 초과+연도 |")
print("|---|---|" + "---|" * len(HOR) + "---|")
res = {}
for lab, pat in EVENTS:
    S = [s for s in signals(pat) if s["amt"] >= 3]
    res[lab] = S
    cells = []
    a20 = None
    for h in HOR:
        a = A(S, h)
        if h == 20: a20 = a
        cells.append("-" if not a else (f"**{a['al']:+.2f}**" if abs(a["al"]) > 1 else f"{a['al']:+.2f}"))
    print(f"| {lab} | {len(S):,} | " + " | ".join(cells) + f" | {a20['pos'] if a20 else '-'} |")

# 상위 후보 상세
print("\n## 유망 이벤트 연도별 (20일 보유)\n")
for lab in ("자기주식 소각", "자기주식 취득결정", "무상증자 결정", "단일판매·공급계약"):
    S = res.get(lab, [])
    rows = []
    for s in S:
        if len(s["C"]) < 2: continue
        r, hh = ev2(s, 20); m = mkt(s, hh)
        if m is not None: rows.append((s["y"], r - m))
    if len(rows) < 20: continue
    dd = pd.DataFrame(rows, columns=["y", "al"])
    ys = " · ".join(f"{y}:{g.al.mean():+.1f}({len(g)})" for y, g in dd.groupby("y"))
    print(f"**{lab}** ({len(dd)}건, 전체 {dd.al.mean():+.2f}%)\n  {ys}\n")
