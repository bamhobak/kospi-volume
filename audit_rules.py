# -*- coding: utf-8 -*-
"""규칙 자동 감사 — 화면에 적힌 것과 실제가 어긋나지 않았는지 점검한다.

규칙은 index.html(사이트 판정) · notify_new.py(알림 판정) · portfolio.py(백테스트)
세 곳에 각각 적혀 있고, 성적표(stats)는 손으로 갱신한다. 조건을 고치고 다른 곳을
빠뜨리면 화면은 멀쩡해 보이는데 판정이나 숫자가 틀린다. 실제로 그런 일이 있었다:
 · prep() 필드 누락으로 3규칙이 신호를 낼 수 없었다(2026-09-02)
 · [외인 매집] 은 조건을 두 번 바꾸는 동안 stats 가 옛 값으로 남아 있었다

세 가지를 본다.
 1) 필드   — 조건이 쓰는 필드가 table.json 과 prep() 에 다 있는가(없으면 조용히 0건)
 2) 조건   — index.html · notify_new.py · portfolio.py 의 문턱값이 서로 같은가
 3) 성적표 — 화면 stats 가 지금 조건으로 다시 잰 값과 맞는가

사용: python audit_rules.py
"""
import io, json, re, sys
from pathlib import Path
import numpy as np, pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
H = (BASE / "index.html").read_text(encoding="utf-8")
NV = (BASE / "notify_new.py").read_text(encoding="utf-8")
PF = (BASE / "portfolio.py").read_text(encoding="utf-8")
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}
ok_all = True
def bad(msg):
    global ok_all; ok_all = False; print(msg)

# ── index.html 에서 규칙별 fn·stats 를 뽑는다 ──────────────────────
fs = H.find("const FILTERS="); fe = H.find("const LEGACY_ID", fs)
BLK = H[fs:fe]
RULES_JS, STATS = {}, {}
for m in re.finditer(r"\{id:'([^']+)'.*?fn:(.*?)(?=\n   stats:|\n  \{id:'|\n\];)", BLK, re.S):
    RULES_JS[m.group(1)] = re.sub(r"\s+", " ", m.group(2))
for m in re.finditer(r"\{id:'([^']+)'", BLK):
    rid = m.group(1)
    seg = BLK[m.start():m.start() + 20000]
    s = re.search(r"stats:\{n:(\d+),\s*perMonth:([\d.]+),\s*win:([\d.]+),\s*pf:([\d.]+),\s*avg:([-\d.]+)", seg)
    if s: STATS[rid] = dict(n=int(s.group(1)), perMonth=float(s.group(2)), win=float(s.group(3)),
                            pf=float(s.group(4)), avg=float(s.group(5)))

# ── 1) 필드 존재 ────────────────────────────────────────────────
i = H.find("function prep()")
prep_fields = set(re.findall(r"\b([A-Za-z_]\w*)\s*:", H[i:H.find("function val(", i)]))
tj = BASE / "site" / "data" / "table.json"
have = set(json.loads(tj.read_text(encoding="utf-8"))["rows"][0].keys()) if tj.exists() else set()
SAFE = {"mk", "pref", "ticker", "name", "close", "change", "th", "vols", "avg", "total", "ratio",
        "indiv", "organ", "frgn", "last", "chpct", "fwp", "fw", "v5", "r16", "rw1", "streak", "dilu"}
print("## 1) 조건이 쓰는 필드가 데이터에 있는가")
for rid, fn in RULES_JS.items():
    used = sorted(set(re.findall(r"\br\.([A-Za-z_]\w*)", fn)))
    mp = [u for u in used if u not in prep_fields and u not in SAFE]
    mj = [u for u in used if have and u not in have and u not in SAFE]
    if mp or mj:
        bad(f"  ❌ [{NAME[rid]}] " + (f"prep 누락 {mp} " if mp else "") + (f"table.json 누락 {mj}" if mj else ""))
print("  " + ("✅ 9규칙 모두 정상" if ok_all else ""))

# ── 2) 세 곳의 문턱값이 같은가 ───────────────────────────────────
def thr(txt):
    """'필드 비교 숫자' 쌍을 집합으로. 표기 차이를 흡수하려 별칭을 통일한다."""
    A = {"vs1": "su1", "sr60": "u", "srDown": "srd", "dilu": "dil", "pbrd": "PBR",
         "r3m": "ret60", "cap": "marcap", "cap조": "marcap", "c": "close", "fw": "fw5",
         "a1": "r16", "a6": "r16", "aw": "rw1", "dbt": "부채비율"}
    out = set()
    for f, op, v in re.findall(r"[r.\[\"']*\b([A-Za-z_]\w*)[\"'\]]*\s*(<=|>=|<|>)\s*(-?[\d.]+)", txt):
        f = A.get(f, f)
        if f in ("length", "slice", "index"): continue
        try: out.add((f, op, float(v)))
        except ValueError: pass
    return out
print("\n## 2) index.html · notify_new.py · portfolio.py 조건이 일치하는가")
NV_R = {m.group(1): m.group(2) for m in
        re.finditer(r'\("(P\d|D\d)",\s*"[^"]*",\s*(lambda r:.*?)\),\n    \("', NV, re.S)}
m = re.search(r"RULES = \{(.*?)\n\}", PF, re.S)
PF_R = {}
if m:
    for r in re.finditer(r'"(P\d|D\d)":\s*\((.*?)\),\n(?= "|\})', m.group(1), re.S):
        PF_R[r.group(1)] = r.group(2)
for rid in RULES_JS:
    js = thr(RULES_JS[rid])
    for src, tbl in (("notify_new", NV_R), ("portfolio", PF_R)):
        if rid not in tbl: continue
        other = thr(tbl[rid])
        only_js = {x for x in js if x[0] in {y[0] for y in other}} - other
        only_ot = {x for x in other if x[0] in {y[0] for y in js}} - js
        # base(K,amt) 안에 들어 있거나 표기가 달라 정규식으로 못 잡는 것들
        SILENT = {"close", "marcap", "fw5", "r16", "rw1", "amt20", "amt"}
        miss = ({x[0] for x in js} - {y[0] for y in other}) - SILENT
        if only_js or only_ot or miss:
            d = []
            if only_js or only_ot: d.append(f"값 다름 site={sorted(only_js)} {src}={sorted(only_ot)}")
            if miss: d.append(f"{src} 에 없는 조건 {sorted(miss)}")
            bad(f"  ❌ [{NAME[rid]}] " + " / ".join(d))
# 시장 범위(코스피/코스닥/공통)가 세 곳에서 같은가 — 문턱값 비교로는 안 잡힌다
def scope(txt, py):
    kp = ("KOSPI" in txt); kq = ("KOSDAQ" in txt)
    return "공통" if not (kp or kq) else ("코스피" if kp else "코스닥")
for rid in RULES_JS:
    a = scope(RULES_JS[rid], False)
    b = scope(NV_R.get(rid, ""), True) if rid in NV_R else None
    c = ("코스피" if re.match(r"\s*KP", PF_R.get(rid, "")) else
         "코스닥" if re.match(r"\s*KQ", PF_R.get(rid, "")) else None) if rid in PF_R else None
    got = {x for x in (a, b, c) if x}
    if len(got) > 1:
        bad(f"  ❌ [{NAME[rid]}] 시장 범위 불일치 — site={a} / notify={b} / portfolio={c}")
    # 메타데이터(mkt)와 실제 판정이 어긋나는가
    mm = re.search(rf"\{{id:'{rid}'[^}}]*?mkt:'([^']+)'", BLK)
    if mm:
        meta = {"KOSPI": "코스피", "KOSDAQ": "코스닥"}.get(mm.group(1), mm.group(1))
        if a == "공통" and meta != "공통":
            bad(f"  ❌ [{NAME[rid]}] 화면 분류는 {meta} 인데 판정 함수는 시장을 가리지 않음(공통)")
print("  (표기 차이를 흡수하지 못해 오탐이 날 수 있음 — 실제로 다른지 눈으로 확인할 것)")

# ── 3) 화면 성적표가 지금 조건과 맞는가 ──────────────────────────
print("\n## 3) 화면 stats 가 지금 조건으로 잰 값과 맞는가 (검증기간 2023~)")
import FinanceDataReader as fdr
IX = fdr.DataReader("KS11", "2017-01-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
UP20 = dict(zip(IX.date, IX.Close > IX.Close.rolling(20).mean()))
UP60 = dict(zip(IX.date, IX.Close > IX.Close.rolling(60).mean()))
INS = pd.read_pickle(BASE / "data/insider_feat.pkl")[["ticker", "date", "ins60"]]
import sqlite3
con = sqlite3.connect(BASE / "data/dart/disclosures.db")
D = pd.read_sql("SELECT stock_code AS ticker, rcept_dt AS dt, report_nm FROM disclosure "
                "WHERE length(stock_code)=6 AND rcept_dt>='20180101' AND report_nm LIKE '%자기주식취득결정%'", con)
con.close()
nm_ = D.report_nm.str.replace(" ", "", regex=False)
BB = set(zip(*D[~nm_.str.contains("신탁") & ~nm_.str.contains("정정")][["ticker", "dt"]].values.T))

def load(f, mk):
    K = pd.read_pickle(BASE / "data" / f).sort_values(["ticker", "date"]).reset_index(drop=True)
    K["mk"] = mk; K["pref"] = ~K.ticker.str.endswith("0")
    K.loc[K.marcap / 1e4 > 2000, "marcap"] = np.nan
    g = K.groupby("ticker", sort=False)
    K["dev25"] = (K.close / g.close.transform(lambda s: s.rolling(25, min_periods=25).mean()) - 1) * 100
    K["bb"] = [(t, d) in BB for t, d in zip(K.ticker, K.date)]
    K = K.merge(INS, on=["ticker", "date"], how="left")
    K["up20"] = K.date.map(UP20).fillna(False); K["up60"] = K.date.map(UP60).fillna(False)
    K["yr"] = K.date.str[:4]
    return K
KP, KQ = load("kp_ow.pkl", "KOSPI"), load("kq_ow.pkl", "KOSDAQ")
gp = lambda K, c: K[c] if c in K.columns else pd.Series(np.nan, index=K.index)
NO = lambda K: ~K.dil.fillna(False)
def R(K):
    """index.html FILTERS 를 그대로 옮긴다. 사이트에 없는 필드(above20·ret250·disc)는 생략."""
    P = (~K.pref) & NO(K)
    return {
     "P1": (40, None, P & (K.fromhi >= -10) & (K.r16 < 120) & (gp(K,"rw1") <= 120) & (K.fw5 >= 3)
            & (K.fw60 >= 1) & (K.vol20 <= 2) & (K.sr20 <= 0.5) & (K.ret20 <= 5) & (K.amt20 >= 200)),
     "P2": (10, None, P & (K.r16 < 30) & (gp(K,"rw1") >= 200) & (K.fw5 >= 2) & (K.amt >= 3)
            & (K.ret3 <= -5) & (K.ret10 <= 0) & (~K.up20) & (K.srd == True)),
     "P3": (20, None, P & (K.ret20 <= -20) & (K.su1 >= 1.5) & (K.fw60 >= 1) & (K.amt20 >= 3)
            & (~K.up60) & (K.u <= -10) & (K.srd == True)),
     "P4": (5, 15, P & (~K.up60) & (K.u <= -20) & (K.dma20 <= -10) & (K.mdd60 <= -40)
            & (K.srd == True) & (K.amt20 >= 10) & (K.close >= 1000)),
     "P5": (10, None, (~K.pref) & (K.bb == True) & (K.ret60 <= -20) & (~K.up60)),
     "P6": (5, 10, P & (~K.up60) & (K.dev25 <= -25) & (K.u <= -20) & (K.amt20 >= 10) & (K.close >= 1000)),
     "P7": (60, None, P & K.up60 & (K.marcap >= 10000) & (K.marcap < 100000) & (K.fw20 >= 1)
            & (K.ow60 < 0.4) & (K.r16 >= 100) & (K.r16 < 150) & (K.fromhi >= -15)
            & (K.fromlo >= 70) & (K.ins60.fillna(0) > 0)),
     "D1": (20, None, P & (K.ret20 <= -20) & (K.su1 >= 1.5) & (K.fw60 >= 1) & (K.amt20 >= 2)
            & (~K.up60) & (K.u <= -20) & (K.srd == True) & (K.close >= 1000) & (K.ow20 >= 0)
            & (gp(K,"부채비율").isna() | (gp(K,"부채비율") <= 200))),
     "D2": (40, None, P & (K.PBR <= 0.5) & (K.ret20 <= -10) & (K.su1 >= 2) & (K.u <= -10)
            & (~K.up60) & (K.ow20 >= 0) & (K.srd == True) & (K.amt20 >= 5) & (K.close >= 1000)),
    }
def measure(K, hold, stop, cond):
    g = K.groupby("ticker", sort=False)
    col = f"n{hold}"
    if col not in K.columns: return None
    if stop:
        lo = pd.concat([g.low.shift(-i) for i in range(hold)], axis=1).min(axis=1)
        r = np.where((lo <= K.buy * (1 - stop / 100)).fillna(False), -stop - K.cost, K[col])
    else:
        r = K[col].values
    X = K[cond.fillna(False)].copy(); X["r"] = r[cond.fillna(False).values]
    X = X.dropna(subset=["r"])
    d = sorted(K.date.unique()); di = {x: i for i, x in enumerate(d)}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10**9) >= i: continue
        last[t] = i + hold; keep.append(ix)
    Z = X.loc[keep]
    V = Z[Z.date >= "20230101"]
    if len(V) < 5: return None
    pos, neg = V.r[V.r > 0].sum(), -V.r[V.r <= 0].sum()
    return dict(n=len(V), perMonth=round(len(V) / 44, 1), win=round((V.r > 0).mean() * 100),
                pf=round(pos / neg, 2) if neg else 99.0, avg=round(V.r.mean(), 2))
print(f"  {'규칙':<16} {'항목':<9} {'화면':>9} {'실측':>9}  {'판정'}")
# [자사주 낙폭] 은 코스피·코스닥 공통 규칙이라 두 시장을 합쳐서 잰다
BOTH = pd.concat([KP, KQ], ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
for K in (KP, KQ, BOTH):
    tag = "BOTH" if K is BOTH else K.mk.iloc[0]
    for rid, (hold, stop, cond) in R(K).items():
        if rid not in STATS: continue
        want = "BOTH" if rid == "P5" else ("KOSDAQ" if rid.startswith("D") else "KOSPI")
        if tag != want: continue
        got = measure(K, hold, stop, cond)
        if got is None: print(f"  [{NAME[rid]}] 측정 불가(보유기간 컬럼 없음 또는 표본 부족)"); continue
        s = STATS[rid]; diffs = []
        for k, tol in (("n", .35), ("perMonth", .35), ("win", .18), ("pf", .60), ("avg", .60)):
            a, b = s[k], got[k]
            if a == 0 and b == 0: continue
            rel = abs(b - a) / max(abs(a), 1e-9)
            if rel > tol: diffs.append((k, a, b))
        if diffs:
            for k, a, b in diffs:
                bad(f"  ❌[{NAME[rid]}]{'':<{max(0,13-len(NAME[rid]))}} {k:<9} {a:>9} {b:>9}  차이 큼")
        else:
            print(f"  ✅[{NAME[rid]}]{'':<{max(0,13-len(NAME[rid]))}} {'n/승률/평균':<9} "
                  f"{s['n']}/{s['win']:.0f}%/{s['avg']:+.1f}".rjust(9)
                  + f"{got['n']}/{got['win']:.0f}%/{got['avg']:+.1f}".rjust(11) + "  맞음")
print(f"\n{'✅ 감사 통과' if ok_all else '❌ 위 항목을 확인하세요'}")
sys.exit(0 if ok_all else 1)
