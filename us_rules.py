# -*- coding: utf-8 -*-
"""한국 아홉 규칙을 미국에 그대로 대입해 본다.

사용자 요청(2026-09-09): "국내 주식 규칙 만들 때 쓴 데이터들 대입해서 미국 주식으로도
데이터 만들 수 있는 거 만들어놔줘."

원칙 — **조건을 마음대로 고치지 않는다.**
  · 미국에 있는 재료는 한국과 **같은 문턱**으로 그대로 쓴다(업종 -20%, 이격 -10% 등).
  · 미국에 없는 재료(외국인·기관 순매수, 신용잔고, 증자공시, 자사주, 내부자)는
    **뺀다**. 빼면 조건이 느슨해지므로 '몇 개를 뺐는지' 를 규칙마다 표시한다.
  · 단위가 다른 것만 환산한다 — 주가 하한(1,000원 → $3)과 거래대금(억원 → 백만달러).
  · 국면 게이트는 코스피 60일선 → **S&P500 60일선**.

판정도 한국과 같은 잣대를 쓴다 — 유니버스 대비 초과 · 중앙값 · 상위5% 절삭 ·
학습 2016~22 / 검증 2023~26 · 월블록 CI · 양수해 비율. 그래야 두 시장을 나란히 놓을 수 있다.

  python us_rules.py            # 규칙별 성적
  python us_rules.py --acct     # 계좌 시뮬까지
"""
import io, sys, time, argparse, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
TR0, TR1, VA0 = "20160101", "20221231", "20230101"


def log(m):
    print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)


K = pd.read_pickle(BASE / "data" / "panel_us.pkl")
log(f"미국 패널 {len(K):,}행 · {K.ticker.nunique():,}종목 · {K.date.min()}~{K.date.max()}")

# ── 국면 게이트 — S&P500 60일선 ──────────────────────────────────────
import FinanceDataReader as fdr
IX = fdr.DataReader("US500", "2004-06-01")
IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d")
IX["ma60"] = IX.Close.rolling(60).mean()
UP60 = dict(zip(IX.date, IX.Close > IX.ma60))
K["up60"] = K.date.map(UP60)
dn60 = K.up60 == False
up60 = K.up60 == True
log(f"  S&P500 60일선 게이트 · 하락 구간 비중 {dn60.mean()*100:.0f}%")


def base(amt):
    """한국 base() 대응. 1,000원 → $3, 억원 → 백만달러(대략 1억원 ≈ $0.073M 이지만
    시장 규모가 달라 절대 환산은 무의미하다. **유니버스 통과 비율**을 한국과 맞춘다:
    한국 base(K,3) 은 전체의 약 60% 를 남긴다)."""
    return (~K.pref) & (K.close >= 3) & (K.amt20.fillna(0) >= amt)


# 한국 amt 문턱(억원) → 미국(백만달러). 통과 비율을 맞추려고 잡은 값이다.
AMT = {3: 1.0, 5: 2.0, 10: 5.0, 200: 100.0}
for kr, us in AMT.items():
    log(f"  거래대금 {kr}억원 → ${us}M · 통과 비율 {base(us).mean()*100:.0f}%")

# ══════════════════════════════════════════════════════════════════════
# 아홉 규칙 — 옮길 수 있는 조건만. 뺀 조건은 dropped 에 적는다.
# ══════════════════════════════════════════════════════════════════════
RULES = {
 "P1": dict(name="조용한 신고가", hold=40, trail=0.08, pct=12, mx=7,
            cond=lambda: base(100.0) & (K.fromhi >= -10) & (K.vol20 <= 2)
                         & (K.above20 <= 70) & (K.r16 <= 120),
            drop=["외국인 5일 ≥3%", "공매도 비중 ≤0.5%", "1년수익 120% 조건"]),
 "P2": dict(name="조정매집", hold=10, trail=None, pct=15, mx=2,
            cond=lambda: base(1.0) & (K.ret3 <= -5) & (K.ret10 < 0)
                         & (K.rw1 >= 200) & (K.r16 <= 30),
            drop=["외인/거래량 ≥2%"]),
 "P3": dict(name="폭락반등", hold=20, trail=None, pct=5, mx=3,
            cond=lambda: base(1.0) & dn60 & (K.ret20 <= -25),
            drop=["신용잔고 -15%↓", "기타 수급"]),
 "P4": dict(name="업종붕괴 이탈", hold=5, trail=0.08, pct=3, mx=4,
            cond=lambda: base(5.0) & dn60 & (K.u <= -20) & (K.dma20 <= -10)
                         & (K.mdd60 <= -40),
            drop=["공매도 비중 감소(2019 이전 결측)"]),
 "P5": dict(name="자사주 낙폭", hold=10, trail=None, pct=5, mx=3,
            cond=lambda: None, drop=["자사주 취득공시 — EDGAR 파싱 필요. 대입 불가"]),
 "P6": dict(name="깊은 이격", hold=5, trail=0.08, pct=4, mx=4,
            cond=lambda: base(5.0) & dn60 & (K.dev25 <= -25) & (K.u <= -20),
            drop=[]),
 "P7": dict(name="외인 매집", hold=60, trail=None, pct=4, mx=5,
            cond=lambda: None, drop=["외국인 순매수 — 미국에 없음. 대입 불가"]),
 "D1": dict(name="낙폭과대", hold=20, trail=None, pct=5, mx=3,
            cond=lambda: base(2.0) & dn60 & (K.ret20 <= -30) & (K.su1 >= 2)
                         & (K.u <= -10) & (K["부채비율"].isna() | (K["부채비율"] <= 200)),
            drop=["외국인 60일 ≥1%", "기관 20일 ≥0%"]),
 "D2": dict(name="저PBR 낙폭", hold=40, trail=None, pct=5, mx=3,
            cond=lambda: base(2.0) & dn60 & (K.PBR > 0) & (K.PBR <= 0.8)
                         & (K.ret20 <= -10) & (K.su1 >= 2) & (K.u <= -10),
            drop=["기관 20일 ≥0%", "공매도 비중 감소"]),
}

# ══════════════════════════════════════════════════════════════════════
# 미장 고유 규칙 [상승장 신고가] — 한국에서 옮긴 게 아니라 미국 데이터에서 직접 찾은 것
# ══════════════════════════════════════════════════════════════════════
# 왜 따로 짓나: 한국 아홉 규칙 중 통과한 둘은 **둘 다 하락장 규칙**이다. 그런데 축 정찰
# (us_scan.py)로 보면 미장은 국면에 따라 축의 부호가 뒤집히고 상승 국면(74%)에서 폭이 가장
# 크다. 국내는 상승장에도 '빠지고 터지고 출렁이는' 게 좋은데 미국은 정확히 반대로
# '고점 근처·조용하고·저변동'이 좋다. 그래서 옮기지 않고 새로 지었다(why_kr_us.py).
#
# 유동성은 **절대 문턱이 아니라 그날 미장 전체 대비 백분위**로 건다. 미장 전체 거래대금
# 중앙값이 2016년 $5.0M → 2026년 $11.5M 로 두 배가 넘게 커져서, 같은 $10M 문턱이 2016년엔
# 40%를 2026년엔 51%를 통과시켰다. 백분위는 해가 바뀌어도 뜻이 같다(us_liq.py).
#
# 한때 [상승장 추세지속](20일선 위 비율 상위 40%)을 N2 로 함께 뒀으나 **폐기했다** —
# [상승장 신고가]와 월별 상관이 0.80 이라 분산이 아니라 집중이었고, N2 를 빼고 대신
# 자리를 늘리면 같은 투입에서 자산은 같거나 크고 낙폭이 6%p 작았다(us_liq.py ③).
BASE3 = (~K.pref) & (K.close >= 3)                    # 주가 ≥$3 · 우선주 제외
K["amt_q"] = K[BASE3].groupby("date").amt20.rank(pct=True)      # 그날 미장 전체 대비 거래대금 백분위
UNI_N = (BASE3 & (K.amt_q >= 0.6)).fillna(False)                # 거래대금 상위 40%
_s = pd.Series(np.nan, index=K.index)
_s[UNI_N] = K[UNI_N].groupby("date").fromhi.rank(pct=True)
K["fromhi_q"] = _s
# 이벤트형(2026-09-10 채택): 52주 고점 대비 -5% 이내에 **오늘 처음** 들어온 날(최근 20거래일은 밖).
#   상태형(고점 상위30% 안에 있음)은 상승장에 하루 436종목이 매일 다시 걸렸다. 사건형은 9.6종목.
#   문턱 -1/-3/-5% × 창 0/10/20/40일 12칸 전부 초과 양수(us_n1_reduce2.py). 상태 이력은 유동성
#   조건을 빼고 계산한다 — 수집기(collect_us_daily.py metrics)가 종목 자기 이력만으로 만드는 것과 맞춘다.
_within = (BASE3 & (K.fromhi >= -5)).fillna(False)
_seen = (_within.groupby(K.ticker).shift(1).fillna(False).astype(bool)
         .groupby(K.ticker).transform(lambda s: s.rolling(20, min_periods=1).max()).fillna(0) > 0)
# 조용한 진입 — 최근 3일 평균 거래량 ≤ 최근 한 달 평균(3일 전부터 20일).
_a20 = K.groupby('ticker', sort=False).volume.transform(lambda s: s.shift(3).rolling(20).mean())
_remo = K.vm3 / _a20 * 100
N1_COND = (UNI_N & up60 & _within & ~_seen & (_remo <= 100))
RULES["N1"] = dict(name="상승장 신고가", hold=40, trail=None, pct=5, mx=8,
                   cond=lambda: N1_COND, drop=[])

UNI = {h: K[base(1.0)].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean()
       for h in (5, 10, 20, 40, 60)}


def measure(rid, r):
    cond = r["cond"]()
    if cond is None:
        return None
    h = r["hold"]
    m = cond.fillna(False)
    g = K.groupby("ticker", sort=False)
    C = np.column_stack([g.px.shift(-i).values for i in range(1, h + 1)])
    buy = K.buy.values
    hit = np.zeros_like(C, dtype=bool); px = C.copy()
    if r["trail"]:
        # ⚠ 낙관적 체결 가정 — 고점 대비 -trail 가격에 그대로 팔린다고 본다.
        #   집안 규율(한국 [trailing-stop])은 '종가로 판정하고 다음날 시가에 판다' 이다.
        #   2026-09-09 us_trail_check.py 로 비교했더니 차이가 결정적이었다:
        #     낙폭과대 평균 무손절 +6.03 / 낙관트레일 +4.36 / **보수트레일 -0.58**
        #     저PBR낙폭 평균 무손절 +8.41 / 낙관트레일 +4.68 / **보수트레일 +0.73**
        #   즉 이 가정 위에서 나온 트레일 성적(P1·P4·P6, 그리고 계좌 시뮬의 트레일판)은
        #   과대평가다. 트레일을 실제로 채택하려면 보수판으로 다시 재야 한다.
        run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
        hh = C <= run * (1 - r["trail"]); hit |= hh
        px = np.where(hh & ~np.isnan(C), run * (1 - r["trail"]), px)
    ok = hit.any(axis=1)
    first = np.where(ok, hit.argmax(axis=1), h - 1)
    ex = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
    mv = m.values
    X = K[m].copy()
    X["ret"] = (ex[mv] / X.buy - 1) * 100 - X.cost
    X["hold"] = (first + 1)[mv]
    X = X.dropna(subset=["ret"])
    X = X[(X.buy > 0) & (X.date >= TR0)]
    if len(X) < 30:
        return dict(n=len(X), few=True)
    # 중복신호 제거
    di = {d: i for i, d in enumerate(sorted(K.date.unique()))}
    X["di"] = X.date.map(di); X = X.sort_values("di")
    keep, last = [], {}
    for t, i, ix in zip(X.ticker.values, X.di.values, X.index):
        if last.get(t, -10 ** 9) >= i:
            continue
        last[t] = i + h; keep.append(ix)
    X = X.loc[keep]
    if len(X) < 30:
        return dict(n=len(X), few=True)
    u = UNI.get(h, UNI[20])
    X["ex"] = X.ret - X.date.map(u)
    tr, va = X[X.date <= TR1], X[X.date >= VA0]
    yr = X.assign(y=X.date.str[:4]).groupby("y").ret.median()
    return dict(n=len(X), few=False, ret=X.ret.mean(), med=X.ret.median(),
                trim=X.ret[X.ret <= X.ret.quantile(0.95)].mean(),
                win=(X.ret > 0).mean() * 100, ex=X.ex.mean(), exmed=X.ex.median(),
                trm=tr.ret.median() if len(tr) else np.nan,
                vam=va.ret.median() if len(va) else np.nan,
                ci=verdict.boot_ci(X.assign(mm=X.date.str[:6]).groupby("mm").ret.mean(), 0.10),
                pos=int((yr > 0).sum()), ny=len(yr), X=X)


print("\n" + "=" * 126)
print("한국 아홉 규칙을 미국에 대입 — 조건은 그대로, 없는 재료만 뺀다 (2016~, 비용차감)")
print("=" * 126)
print(f"  {'규칙':<16}{'건수':>7}{'절대평균':>9}{'중앙':>8}{'절삭':>8}{'승률':>6}"
      f"{'초과':>8}{'학습중앙':>9}{'검증중앙':>9}{'월CI':>8}{'양수해':>7}  뺀 조건")
RES = {}
for rid, r in RULES.items():
    z = measure(rid, r)
    if z is None:
        print(f"  {r['name']:<16}{'—':>7}{'':<66}대입 불가: {r['drop'][0]}")
        continue
    if z.get("few"):
        print(f"  {r['name']:<16}{z['n']:>7,}  표본부족")
        continue
    RES[rid] = z
    print(f"  {r['name']:<16}{z['n']:>7,}{z['ret']:>+9.2f}{z['med']:>+8.2f}{z['trim']:>+8.2f}"
          f"{z['win']:>5.0f}%{z['ex']:>+8.2f}{z['trm']:>+9.2f}{z['vam']:>+9.2f}"
          f"{z['ci']:>+8.2f}{z['pos']:>4}/{z['ny']}  {len(r['drop'])}개")

print("\n" + "=" * 126)
print("한국 원본과 나란히 (한국 건별 평균은 2016~ 기준)")
print("=" * 126)
KR = {"P1": 7.02, "P2": 11.81, "P3": 33.02, "P4": 10.68, "P5": 10.20,
      "P6": 10.76, "P7": 15.36, "D1": 42.54, "D2": 40.87}
print(f"  {'규칙':<16}{'한국 평균':>10}{'미국 평균':>10}{'차이':>9}   판정")
for rid, r in RULES.items():
    if rid not in RES or rid not in KR:      # N1·N2 는 한국 원본이 없다(미장 고유)
        continue
    z = RES[rid]
    ok = (z["med"] > 0 and z["trim"] > 0 and z["trm"] > 0 and z["vam"] > 0
          and z["ci"] > 0 and z["pos"] / z["ny"] >= 0.7)
    print(f"  {r['name']:<16}{KR[rid]:>+9.2f}%{z['ret']:>+9.2f}%{z['ret']-KR[rid]:>+8.2f}p"
          f"   {'✅ 통과' if ok else '❌ 기각'}")

print("")
print("  " + '── 미장 고유 규칙 (한국 원본 없음) ──')
for rid in ("N1",):
    if rid in RES:
        z = RES[rid]
        ok = (z["ex"] > 0 and z["ci"] > 0 and z["pos"] / z["ny"] >= 0.7)
        print(f"    {RULES[rid]['name']:<16}{z['ret']:>+9.2f}%  초과 {z['ex']:>+6.2f}p"
              f"  월CI {z['ci']:>+6.2f}  양수해 {z['pos']}/{z['ny']}   {'OK' if ok else '△'}")

print("\n  ── 대입 불가 ──")
for rid, r in RULES.items():
    if rid not in RES:
        print(f"    {r['name']} — {r['drop'][0]}")
print("\n  ── 뺀 조건(있으면 더 엄격해졌을 것) ──")
for rid, r in RULES.items():
    if rid in RES and r["drop"]:
        print(f"    {r['name']}: " + " · ".join(r["drop"]))
