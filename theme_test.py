"""테마 단위 거래량 급등 신호 테스트
기존 1번 필터 로직(2개월 거래량 < 1년의 50% → 최근 3일 ≥ 2개월의 200%)을
개별 종목이 아니라 '테마 전체 거래대금' 기준으로 적용
python theme_test.py
"""
import io, sys, sqlite3, pickle
from pathlib import Path
import numpy as np, pandas as pd
import FinanceDataReader as fdr
import collect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
W, Q, B = 3, 40, 240
MIN_MEMBERS = 4          # 테마 내 코스피 종목 최소 수

con = sqlite3.connect(f"file:{collect.DB}?mode=ro", uri=True)
snap = con.execute("SELECT max(snap) FROM sector").fetchone()[0]
th = {}
for t, g in con.execute("SELECT ticker, gname FROM sector WHERE snap=? AND kind='theme'", (snap,)):
    th.setdefault(g, []).append(t)
df = pd.read_sql("""SELECT date,ticker,close,open,high,low,volume,amount,frgn
                    FROM daily WHERE date>='20220101' AND ticker LIKE '%0' ORDER BY date""", con)
kospi = fdr.DataReader("KS11", "2022-06-01", "2026-08-28")
kospi["ma20"] = kospi["Close"].rolling(20).mean()
K = {d.strftime("%Y%m%d"): bool(r["Close"] > r["ma20"]) for d, r in kospi.iterrows()}
con.close()

have = set(df["ticker"].unique())
themes = {g: [c for c in cs if c in have] for g, cs in th.items()}
themes = {g: cs for g, cs in themes.items() if len(cs) >= MIN_MEMBERS}
print(f"테마 {len(themes)}개 (코스피 {MIN_MEMBERS}종목 이상) · 스냅샷 {snap}", file=sys.stderr)

# 종목별 시계열 (수익률 계산용)
px = {t: g.set_index("date")[["open", "high", "low", "close", "amount"]] for t, g in df.groupby("ticker")}
dates = sorted(df["date"].unique())
didx = {d: i for i, d in enumerate(dates)}

# 테마별 일자별 거래대금·외국인 합계
amt_piv = df.pivot_table(index="date", columns="ticker", values="amount", aggfunc="sum")
frgn_piv = df.pivot_table(index="date", columns="ticker", values="frgn", aggfunc="sum")
vol_piv = df.pivot_table(index="date", columns="ticker", values="volume", aggfunc="sum")

SIG = []
for g, cs in themes.items():
    cols = [c for c in cs if c in amt_piv.columns]
    if len(cols) < MIN_MEMBERS: continue
    a = amt_piv[cols].sum(axis=1)                      # 테마 총 거래대금
    f = frgn_piv[cols].sum(axis=1); v = vol_piv[cols].sum(axis=1)
    quiet = a.shift(W).rolling(Q).mean() / a.shift(W + Q).rolling(B).mean()
    surge = a.rolling(W).mean() / a.shift(W).rolling(Q).mean()
    fwp = f.rolling(5).sum() / v.rolling(5).sum() * 100
    m = (quiet < 0.5) & (surge >= 2) & (a.index >= "20230101")
    idx = [d for d in a.index[m.fillna(False).values]]
    last = -99
    for d in idx:
        i = didx.get(d)
        if i is None or i - last < 15 or i + 1 >= len(dates): continue
        last = i
        SIG.append(dict(g=g, d=d, y=int(d[:4]), members=cols,
                        surge=float(surge.loc[d]), quiet=float(quiet.loc[d]),
                        fwp=float(fwp.loc[d]) if not np.isnan(fwp.loc[d]) else 0.0,
                        amt=float(a.loc[d] / 1e8), k20=K.get(d, False)))
print(f"테마 신호 {len(SIG)}건", file=sys.stderr)

def cost(a): return 0.18 + (0.30 if a >= 50 else 0.50)
def basket_ret(s, hold, sl=None):
    """신호 다음날 시가에 테마 편입 종목 균등 매수 → hold일 뒤 종가"""
    i = didx[s["d"]]
    if i + 1 + hold >= len(dates): return None
    bd, ed = dates[i + 1], dates[i + 1 + hold]
    rs = []
    for c in s["members"]:
        p = px.get(c)
        if p is None or bd not in p.index or ed not in p.index: continue
        o = p.at[bd, "open"]
        if not o or o <= 0: continue
        am = p.at[bd, "amount"] or 0
        if sl:
            lo = p.loc[bd:ed, "low"].min()
            if lo <= o * (1 - sl / 100):
                rs.append(-sl - cost(am / 1e8)); continue
        rs.append((p.at[ed, "close"] / o - 1) * 100 - cost(am / 1e8))
    return float(np.mean(rs)) if len(rs) >= MIN_MEMBERS else None

def st(S, hold, sl=None):
    r = [x for x in (basket_ret(s, hold, sl) for s in S) if x is not None]
    if len(r) < 10: return None
    r = np.array(r); w = r[r > 0]; l = r[r <= 0]
    return dict(n=len(r), avg=r.mean(), win=len(w) / len(r) * 100, pf=(w.sum() / abs(l.sum())) if len(l) else 99)
def f(s): return f"{s['avg']:+.2f}% / {s['win']:.0f}% / {s['pf']:.2f} ({s['n']})" if s else "-"

print("# 테마 단위 거래대금 급등 신호 — 편입 종목 균등 매수 백테스트\n")
print(f"테마 {len(themes)}개 · 신호 {len(SIG)}건 · 표기: 평균수익 / 승률(테마 바스켓 기준) / PF\n")
print("※ 테마 구성은 2026-08-28 스냅샷 기준(과거에도 동일하다고 가정) · 코스피 편입 종목만 집계\n")

print("## 1) 보유기간별\n\n| 조건 | 5일 | 10일 | 15일 | 20일 | 40일 |\n|---|---|---|---|---|---|")
print("| 전체 | " + " | ".join(f(st(SIG, h)) for h in (5, 10, 15, 20, 40)) + " |")
UP = [s for s in SIG if s["k20"]]
print("| 코스피 20일선 위 | " + " | ".join(f(st(UP, h)) for h in (5, 10, 15, 20, 40)) + " |")
FW = [s for s in SIG if s["fwp"] >= 1]
print("| 외국인 순매수 1%↑ | " + " | ".join(f(st(FW, h)) for h in (5, 10, 15, 20, 40)) + " |")

print("\n## 2) 연도별 (10일 보유)\n\n| 그룹 | 2023 | 2024 | 2025 | 2026 |\n|---|---|---|---|---|")
for nm, S in (("전체", SIG), ("코스피 20일선 위", UP)):
    print(f"| {nm} | " + " | ".join(f(st([s for s in S if s["y"] == y], 10)) for y in (2023, 2024, 2025, 2026)) + " |")

print("\n## 3) 급등 배율·잠잠 정도별 (10일 보유)\n\n| 조건 | 건수 | 성과 |\n|---|---|---|")
for lab, fn in (("급등 2~3배", lambda s: s["surge"] < 3), ("급등 3배↑", lambda s: s["surge"] >= 3),
                ("잠잠 <30%", lambda s: s["quiet"] < 0.3), ("잠잠 30~50%", lambda s: s["quiet"] >= 0.3),
                ("테마 거래대금 1000억↑", lambda s: s["amt"] >= 1000)):
    S = [s for s in SIG if fn(s)]
    print(f"| {lab} | {len(S)} | {f(st(S, 10))} |")

print("\n## 4) 손절 적용 (10일 보유)\n\n| 손절 | 성과 |\n|---|---|")
for sl in (None, 10, 15):
    print(f"| {'없음' if sl is None else f'-{sl}%'} | {f(st(SIG, 10, sl))} |")

print("\n## 5) 신호가 많이 나온 테마 TOP10\n\n| 테마 | 신호 수 | 편입(코스피) |\n|---|---|---|")
from collections import Counter
cnt = Counter(s["g"] for s in SIG)
for g, c in cnt.most_common(10):
    print(f"| {g} | {c} | {len(themes[g])} |")
