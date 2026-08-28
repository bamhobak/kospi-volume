"""기준봉(거래대금 300억+ 장대양봉) 시가 지지 매매 실측
- 기준봉: 당일 거래대금 ≥300억 · 장대양봉 · 종가가 120일선 위
- 매수: 이후 주가가 기준봉 시가 부근까지 눌렸다가 지지받는 날 → 다음날 시가
- 동일 기준봉 기준 회차별(1~4차+) 성과 비교
python basecandle_test.py
"""
import io, sys, sqlite3, pickle
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
CF = BASE / "data" / "basecandle_cache.pkl"
BODY_MIN = 5.0        # 장대양봉 몸통 최소 %
AMT_MIN = 300         # 기준봉 거래대금 최소(억)
TOUCH = 2.0           # 시가 터치 허용 %
VALID = 60            # 기준봉 유효기간(거래일)

if CF.exists():
    TR = pickle.load(open(CF, "rb"))
else:
    con = sqlite3.connect(f"file:{collect.DB}?mode=ro", uri=True)
    df = pd.read_sql("""SELECT date,ticker,name,open,high,low,close,volume,amount
                        FROM daily WHERE ticker LIKE '%0' AND date>='20220601' AND open IS NOT NULL AND amount IS NOT NULL
                        ORDER BY ticker,date""", con)
    kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28"); kospi["ma20"] = kospi["Close"].rolling(20).mean()
    K = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma20"]) for d, r in kospi.iterrows()}
    TR = []
    for t, g in df.groupby("ticker"):
        g = g.reset_index(drop=True)
        if len(g) < 200: continue
        O, H, L, C = [g[k].astype(float).values for k in ("open", "high", "low", "close")]
        AM = g["amount"].astype(float).values / 1e8
        ma120 = pd.Series(C).rolling(120).mean().values
        e20 = pd.Series(C).ewm(span=20, adjust=False).mean().values
        D = g["date"].values; N = len(g)
        # 기준봉 찾기
        bases = []
        for i in range(120, N - 1):
            if AM[i] < AMT_MIN: continue
            body = (C[i] / O[i] - 1) * 100
            if body < BODY_MIN: continue
            if np.isnan(ma120[i]) or C[i] <= ma120[i]: continue
            bases.append(dict(i=i, o=float(O[i]), amt=float(AM[i]), body=body,
                              first120=bool(C[i - 1] <= ma120[i - 1])))     # 120일선 첫 돌파 여부
        for b in bases:
            i0, base_o = b["i"], b["o"]
            cnt = 0; last_touch = i0
            for j in range(i0 + 2, min(i0 + 2 + VALID, N - 1)):
                if j - last_touch < 3: continue
                # 시가 부근 터치 후 지지: 저가가 시가 ±TOUCH% 이내로 내려왔고 종가는 시가 위에서 마감
                if not (L[j] <= base_o * (1 + TOUCH / 100) and C[j] >= base_o * 0.98): continue
                if C[j] < base_o * 0.95: continue                # 명확 이탈은 제외
                if O[j + 1] <= 0: continue
                cnt += 1; last_touch = j
                nb = min(61, N - (j + 1))
                if nb < 11: break
                k0 = j + 1
                TR.append(dict(t=t, d=str(D[j]), y=int(str(D[j])[:4]), seq=cnt,
                               o=float(O[k0]), base_o=base_o, amt=b["amt"], body=b["body"],
                               first120=b["first120"], gap_from_base=(O[k0] / base_o - 1) * 100,
                               days_since=j - i0,
                               H=(H[k0:k0 + nb] / O[k0] - 1) * 100, L=(L[k0:k0 + nb] / O[k0] - 1) * 100,
                               C=(C[k0:k0 + nb] / O[k0] - 1) * 100, OP=(O[k0:k0 + nb] / O[k0] - 1) * 100,
                               e20=(e20[k0:k0 + nb] / O[k0] - 1) * 100,
                               base_line=(base_o / O[k0] - 1) * 100,      # 기준봉 시가의 상대 위치(손절선)
                               k20=K.get(str(D[j]), False)))
                if cnt >= 5: break
    pickle.dump(TR, open(CF, "wb"))
print(f"신호 {len(TR)}건", file=sys.stderr)

def cost(a):
    slip = 0.20 if a >= 300 else 0.30
    return 0.18 + slip
def run(s, hold=20, sl=None, tp=None, base_stop=False, exit_e20=False):
    H, L, C, OP = s["H"], s["L"], s["C"], s["OP"]
    n = min(hold, len(C) - 1)
    stop_lv = s["base_line"] - 3 if base_stop else (-sl if sl else None)   # 기준봉 시가 -3% 이탈
    for i in range(n + 1):
        if stop_lv is not None and L[i] <= stop_lv: return stop_lv - cost(s["amt"])
        if tp and H[i] >= tp: return tp - cost(s["amt"])
        if exit_e20 and i > 0 and C[i] < s["e20"][i]:
            k = min(i + 1, len(OP) - 1); return OP[k] - cost(s["amt"])
        if i == n: return C[i] - cost(s["amt"])
def st(S, **kw):
    r = [x for x in (run(s, **kw) for s in S) if x is not None]
    if len(r) < 15: return None
    r = np.array(r); w = r[r > 0]; l = r[r <= 0]
    return dict(n=len(r), avg=r.mean(), win=len(w) / len(r) * 100, pf=(w.sum() / abs(l.sum())) if len(l) else 99,
                med=np.median(r), worst=r.min())
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / {s['pf']:.2f} ({s['n']})" if s else "-"

print("# 기준봉(거래대금 300억+ 장대양봉) 시가 지지 매매 실측 — 2023~2026, 슬리피지·수수료 반영\n")
print(f"총 신호 {len(TR)}건 · 표기: 순수익 / 승률 / PF (건수)\n")

print("## 1) 청산 방식 비교 (전체)\n")
print("| 청산 | 전체 | 2023 | 2024 | 2025 | 2026 |\n|---|---|---|---|---|---|")
for lab, kw in (("10일 보유", dict(hold=10)), ("20일 보유", dict(hold=20)), ("40일 보유", dict(hold=40)),
                ("20일 + 기준봉시가-3% 손절", dict(hold=20, base_stop=True)),
                ("20일 + 손절 -7%", dict(hold=20, sl=7)),
                ("익절 +10% / 기준봉 손절", dict(hold=40, tp=10, base_stop=True)),
                ("익절 +20% / 기준봉 손절", dict(hold=40, tp=20, base_stop=True)),
                ("20EMA 이탈", dict(hold=60, exit_e20=True))):
    ys = [f(st([s for s in TR if s["y"] == y], **kw)) for y in (2023, 2024, 2025, 2026)]
    print(f"| {lab} | {f(st(TR, **kw))} | " + " | ".join(ys) + " |")

print("\n## 2) 회차별 성과 — '최대 3회' 주장 검증 (20일 보유 + 기준봉 손절)\n")
print("| 회차 | 건수 | 성과 |\n|---|---|---|")
for q in (1, 2, 3, 4, 5):
    S = [s for s in TR if s["seq"] == q]
    print(f"| {q}차 | {len(S)} | {f(st(S, hold=20, base_stop=True))} |")
S123 = [s for s in TR if s["seq"] <= 3]; S4 = [s for s in TR if s["seq"] >= 4]
print(f"| **1~3차 합산** | {len(S123)} | {f(st(S123, hold=20, base_stop=True))} |")
print(f"| **4차 이상** | {len(S4)} | {f(st(S4, hold=20, base_stop=True))} |")

print("\n## 3) 추가 조건 효과 (1~3차, 20일 보유 + 기준봉 손절)\n")
print("| 조건 | 건수 | 성과 |\n|---|---|---|")
for lab, fn in (("없음", lambda s: True),
                ("120일선 첫 돌파 기준봉", lambda s: s["first120"]),
                ("거래대금 500억↑", lambda s: s["amt"] >= 500), ("거래대금 1000억↑", lambda s: s["amt"] >= 1000),
                ("몸통 10%↑ (강한 양봉)", lambda s: s["body"] >= 10),
                ("코스피 20일선 위", lambda s: s["k20"]),
                ("기준봉 후 20일 이내 터치", lambda s: s["days_since"] <= 20),
                ("매수가가 기준봉 시가 +3% 이내", lambda s: s["gap_from_base"] <= 3)):
    S = [s for s in S123 if fn(s)]
    print(f"| {lab} | {len(S)} | {f(st(S, hold=20, base_stop=True))} |")

print("\n## 4) 최적 조합 탐색 (1~3차)\n")
best = []
for lab, fn in (("기본", lambda s: True), ("500억↑", lambda s: s["amt"] >= 500),
                ("첫돌파", lambda s: s["first120"]), ("500억↑+코스피20일선", lambda s: s["amt"] >= 500 and s["k20"]),
                ("500억↑+시가근접", lambda s: s["amt"] >= 500 and s["gap_from_base"] <= 3)):
    for hlab, kw in (("20일+기준봉손절", dict(hold=20, base_stop=True)), ("40일+기준봉손절", dict(hold=40, base_stop=True)),
                     ("익절20%+기준봉손절", dict(hold=40, tp=20, base_stop=True)), ("20EMA이탈", dict(hold=60, exit_e20=True))):
        S = [s for s in S123 if fn(s)]
        r = st(S, **kw)
        if r: best.append((r["pf"], lab, hlab, r))
best.sort(reverse=True, key=lambda x: x[0])
print("| 조건 | 청산 | 성과 | 중앙값 | 최악 |\n|---|---|---|---|---|")
for pf, lab, hlab, r in best[:8]:
    print(f"| {lab} | {hlab} | {f(r)} | {r['med']:+.2f}% | {r['worst']:+.1f}% |")
