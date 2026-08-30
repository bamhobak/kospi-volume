# -*- coding: utf-8 -*-
"""섹터 × 종목상태 실측
   ① 업종/테마 매핑 → ② 종목 상태 분류(고점갱신·저점갱신·횡보) → ③ 섹터 상태 → ④ 교차 실측
   ★ sector.csv 는 오늘 기준 스냅샷 1개뿐 → 테마는 미래참조 위험이 커서 '참고'로만 본다.
     업종(KRX 표준산업분류)은 거의 바뀌지 않아 과거 적용이 비교적 안전.
"""
import io, sys, csv, time
from collections import defaultdict
import numpy as np, pandas as pd
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
T0 = time.time()
def log(m): print(f"[{time.time()-T0:4.0f}s] {m}", flush=True)

D = pd.read_pickle("data/swing.pkl")
D = D[~D.bad].sort_values(["ticker", "date"]).reset_index(drop=True)
log(f"{len(D):,}행 · {D.ticker.nunique()}종목")

# ── 경로 배열 (청산 시뮬레이션) ──────────────────────────────
tk = D.ticker.values
u, idx0 = np.unique(tk, return_index=True)
starts = dict(zip(u, idx0)); ends = dict(zip(u, np.append(idx0[1:], len(tk))))
OP, HI, LO, CL = (D[c].values.astype(float) for c in ("open", "high", "low", "close"))
BASE0 = np.array([starts[t] for t in tk]); LEN = np.array([ends[t] - starts[t] for t in tk])
LOC = np.arange(len(D)) - BASE0
COST, YR = D.cost.values, D.y.values

def simulate(sig, hold=10):
    s = np.flatnonzero(sig); s = s[LOC[s] + 1 < LEN[s]]
    if len(s) == 0: return None
    buy = OP[s + 1]; ok = buy > 0; s, buy = s[ok], buy[ok]
    end = np.minimum(s + hold, BASE0[s] + LEN[s] - 1)
    return dict(r=(CL[end] / buy - 1) * 100 - COST[s], y=YR[s], i=s)

def stat(res, mn=30):
    if res is None or len(res["r"]) < mn: return None
    r, y = res["r"], res["y"]
    ism, osm = r[y <= 2022], r[y >= 2023]
    if len(ism) < 5 or len(osm) < 5: return None
    rs = np.sort(r); yy = pd.Series(r).groupby(y).agg(["mean", "size"]); yy = yy[yy["size"] >= 3]
    return dict(n=len(r), ret=r.mean(), med=np.median(r), win=(r > 0).mean()*100,
                pf=(r[r>0].sum()/abs(r[r<=0].sum())) if (r<=0).any() else 99.,
                is_=ism.mean(), os_=osm.mean(), t5=rs[:-5].mean() if len(rs) > 5 else np.nan,
                pos=int((yy["mean"] > 0).sum()), ny=len(yy))

HDR = ("| 구분 | 신호 | 절대수익 | 초과(기준선대비) | 중앙값 | 승률 | PF | 상위5제외 | 학습 | 검증 | +연도 |\n"
       "|---|---|---|---|---|---|---|---|---|---|---|")
BASELINE = {}
def row(lab, res, hold=10):
    s = stat(res)
    if not s: return print(f"| {lab} | {0 if res is None else len(res['r'])} | 부족 |" + " - |" * 8)
    ex = s["ret"] - BASELINE.get(hold, 0)
    print(f"| {lab} | {s['n']:,} | **{s['ret']:+.2f}%** | **{ex:+.2f}%p** | {s['med']:+.2f}% | {s['win']:.0f}% | "
          f"{s['pf']:.2f} | {s['t5']:+.2f}% | {s['is_']:+.2f}% | **{s['os_']:+.2f}%** | {s['pos']}/{s['ny']} |")

# ── 섹터 매핑 ────────────────────────────────────────────────
UP, TH = {}, defaultdict(list)
for r in csv.DictReader(open("data/sector.csv", encoding="utf-8")):
    if r["kind"] == "upjong": UP[r["ticker"]] = r["gname"]
    else: TH[r["ticker"]].append(r["gname"])
D["up"] = D.ticker.map(UP)
log(f"업종 매핑 {D.up.notna().sum():,}행 / {D[D.up.notna()].ticker.nunique()}종목 · 미분류 {D[D.up.isna()].ticker.nunique()}종목")

LIQ = (D.amt20 >= 10) & D.up.notna()
b = stat(simulate(LIQ.values, 10))
BASELINE[10] = b["ret"]; BASELINE[20] = stat(simulate(LIQ.values, 20))["ret"]
print(f"\n기준선(업종 있는 종목·대금10억↑): 10일 **{BASELINE[10]:+.2f}%** · 20일 **{BASELINE[20]:+.2f}%**\n")

# ── 종목 상태 분류 ───────────────────────────────────────────
D["st"] = np.select(
    [D.fromhi120 >= -0.03, D.fromlo120 <= 0.03, (D.boxw60 <= 0.30) & D.fib.between(0.3, 0.7)],
    ["고점갱신", "저점갱신", "횡보"], default="중간")
print("## ① 종목 상태별 (전 업종 합산)\n"); print(HDR)
for s_ in ("고점갱신", "저점갱신", "횡보", "중간"):
    row(s_, simulate((LIQ & (D.st == s_)).values, 10))

# ── 섹터 상태 ────────────────────────────────────────────────
d1 = D[LIQ].groupby(["date", "up"]).agg(sret20=("ret20", "mean"), sret60=("ret60", "mean"),
                                        nhi=("st", lambda x: (x == "고점갱신").mean()),
                                        nlo=("st", lambda x: (x == "저점갱신").mean()),
                                        cnt=("ticker", "size")).reset_index()
d1 = d1[d1.cnt >= 5]
mk = D[LIQ].groupby("date").ret20.mean().rename("mret20")
d1 = d1.merge(mk, on="date")
d1["srs"] = d1.sret20 - d1.mret20                                  # 업종 상대강도
d1["rank"] = d1.groupby("date").srs.rank(pct=True)                 # 당일 업종 중 백분위
D = D.merge(d1[["date", "up", "sret20", "sret60", "srs", "rank", "nhi", "nlo"]], on=["date", "up"], how="left")
LIQ = (D.amt20 >= 10) & D.up.notna() & D["rank"].notna()
log(f"업종-일자 {len(d1):,}건")

print("\n## ② 업종 강도별 (당일 업종 상대강도 백분위)\n"); print(HDR)
for lab, m in [("최강 업종 (상위20%)", D["rank"] >= 0.8), ("상위 20~40%", D["rank"].between(0.6, 0.8)),
               ("중간 40~60%", D["rank"].between(0.4, 0.6)), ("하위 20~40%", D["rank"].between(0.2, 0.4)),
               ("최약 업종 (하위20%)", D["rank"] <= 0.2)]:
    row(lab, simulate((LIQ & m).values, 10))

print("\n## ③ 업종 강도 × 종목 상태 (10일 보유)\n")
print("| 업종\\종목 | 고점갱신 | 저점갱신 | 횡보 |\n|---|---|---|---|")
for slab, sm in [("최강(상위20%)", D["rank"] >= 0.8), ("중간(40~60%)", D["rank"].between(0.4, 0.6)),
                 ("최약(하위20%)", D["rank"] <= 0.2)]:
    cells = []
    for st in ("고점갱신", "저점갱신", "횡보"):
        s = stat(simulate((LIQ & sm & (D.st == st)).values, 10))
        cells.append(f"**{s['ret']:+.2f}%**<br>{s['n']:,}건 승률{s['win']:.0f}%" if s else "부족")
    print(f"| {slab} | " + " | ".join(cells) + " |")

print("\n## ④ 업종 바닥 반등 · 종목 위치 조합 (10일 보유)\n"); print(HDR)
for lab, m in [
    ("업종 60일 -20%↓ (업종 폭락)", D.sret60 <= -20),
    ("업종 폭락 + 종목 저점갱신", (D.sret60 <= -20) & (D.st == "저점갱신")),
    ("업종 폭락 + 종목 저점갱신 + 거래량3배", (D.sret60 <= -20) & (D.st == "저점갱신") & (D.vr20 >= 3)),
    ("업종 폭락 + 종목 고점갱신 (독립 강세)", (D.sret60 <= -20) & (D.st == "고점갱신")),
    ("업종 내 신저가 종목 50%↑ (업종 전멸)", D.nlo >= 0.5),
    ("업종 전멸 + 종목 저점갱신 + 양봉", (D.nlo >= 0.5) & (D.st == "저점갱신") & (D.body > 1)),
    ("업종 내 신고가 종목 30%↑ (업종 과열)", D.nhi >= 0.3),
    ("업종 과열 + 종목 횡보 (후발주)", (D.nhi >= 0.3) & (D.st == "횡보")),
    ("업종 과열 + 종목 저점갱신 (소외주)", (D.nhi >= 0.3) & (D.st == "저점갱신")),
]:
    row(lab, simulate((LIQ & m).values, 10))
log("완료")
