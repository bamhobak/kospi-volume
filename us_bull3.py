# -*- coding: utf-8 -*-
"""미장 상승장 규칙 2호 찾기 — 가격 축은 이미 소진됐다. **비가격 재료**만 정찰한다.

왜 비가격인가: us_bull.py 의 축 정찰에서 상승 국면의 가격 축(고점 근접·얕은 낙폭·추세 지속·
저변동·모멘텀·거래량 침체)이 **전부 한 덩어리**로 나왔고, 다 얹어도 성적이 안 늘었다.
그 하나가 지금의 [상승장 신고가](N1)다. 같은 축을 또 파면 N1 의 사촌이 나올 뿐이고,
목적은 **N1 의존을 낮추는 것**이라 성격이 다른 축이어야 한다.

⚠ 시행 장부가 15,813건이다(data/trials.json). 무작정 훑으면 다중검정에 걸린다.
   그래서 **가설을 먼저 적고** 그에 맞는 축만 십분위로 본다. 셀 수를 세어 기록한다.

정찰할 비가격 재료 (전부 시점 기준 — 공시일/보고일로 붙인다)
  ① 주식수 변화   SEC XBRL shares 시계열. 자사주 소각으로 **줄어드는** 회사 vs 증자로 희석되는 회사.
                 국내는 유상증자·CB 를 '배제 조건' 으로만 쓰는데, 미국은 시계열이 있어 연속 축이 된다.
                 → 한 번도 안 쓴 재료
  ② 이익·EPS     ni/eps 시계열. 성장·흑자전환. 미장에서 안 씀
  ③ 내부자 매수   상승장 단독 초과 +0.70~0.73(21년 안정). 절삭평균이 -0.17 이라 단독은 약함
  ④ 자사주 집행   N4 가 낙폭 쪽으로 쓴다. 상승장 단독은 약했음(초과 +0.43)
  ⑤ 재무 비율     PBR·부채비율 (있는 것 확인만)
  ⑥ 업종 상대강도 sr60 — 업종이 강한가

판정: 상승 국면(S&P 60일선 위) · 거래대금 상위 40% · $3 이상 · 우선주 제외 안에서
      40거래일 앞선 수익의 **같은날 유니버스 대비 초과**를 십분위로 본다.
      방향이 단조로운 축만 다음 단계(조합·문턱)로 넘긴다.

    python us_bull3.py
"""
import sys, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd, FinanceDataReader as fdr

BASE = Path(__file__).parent
K = pd.read_pickle(BASE / "data/us_ins.pkl")          # 내부자 재료가 이미 붙어 있는 패널
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
IX = fdr.DataReader("US500", "2004-06-01"); IX = IX[IX.Close > 0].copy()
IX["date"] = IX.index.strftime("%Y%m%d"); IX["ma60"] = IX.Close.rolling(60).mean()
K["ixup"] = K.date.map(dict(zip(IX.date, IX.Close > IX.ma60)))
ud = sorted(K.date.unique()); ADI = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(ADI).astype(np.int32)
K["amt_q"] = K.groupby("date").amt20.rank(pct=True)
UNI = (K.amt_q >= 0.6).fillna(False); UP = K.ixup == True

# ── ① 주식수·이익 — SEC XBRL(fin.pkl)을 **공시일(filed)** 로 붙인다 ────────────
F = pd.read_pickle(BASE / "data/us/fin.pkl")
F = F.dropna(subset=["ticker", "filed"]).copy()
F["filed"] = F.filed.astype(str)
def latest(col):
    """종목·공시일별 최신 보고값 (같은 날 여러 건이면 마지막)."""
    z = F.dropna(subset=[col]).sort_values(["ticker", "filed", "end"])
    return z.drop_duplicates(["ticker", "filed"], keep="last")[["ticker", "filed", col]]
SH = latest("shares").rename(columns={"filed": "date", "shares": "shr"})
NI = latest("ni").rename(columns={"filed": "date", "ni": "ni_"})
EP = latest("eps").rename(columns={"filed": "date", "eps": "eps_"})
K = K.merge(SH, on=["ticker", "date"], how="left").merge(NI, on=["ticker", "date"], how="left") \
     .merge(EP, on=["ticker", "date"], how="left")
g = K.groupby("ticker", sort=False)
for c in ("shr", "ni_", "eps_"):
    K[c] = g[c].ffill()                    # 다음 보고 전까지는 마지막 보고값이 최신이다
# 주식수 변화율 — 1년 전(250거래일) 대비. 음수면 자사주 소각 등으로 줄어든 것.
K["shr_y"] = g.shr.shift(250)
K["dshr"] = (K.shr / K.shr_y - 1) * 100
K["eps_y"] = g.eps_.shift(250)
K["deps"] = np.where((K.eps_y.abs() > 0.01), (K.eps_ - K.eps_y) / K.eps_y.abs() * 100, np.nan)
K["ni_y"] = g.ni_.shift(250)
K["dni"] = np.where((K.ni_y.abs() > 1e5), (K.ni_ - K.ni_y) / K.ni_y.abs() * 100, np.nan)

# ── ④ 자사주 집행 상태 ────────────────────────────────────────────────
B = pd.read_pickle(BASE / "data/us/buyback.pkl")
SP = B[B.tag == "spend"].copy()
SP["days"] = (pd.to_datetime(SP.end, errors="coerce") - pd.to_datetime(SP.start, errors="coerce")).dt.days
SP = SP[(SP.days >= 60) & (SP.days <= 200) & (SP.val > 0)]
SP = SP.sort_values("days").drop_duplicates(["ticker", "filed"], keep="first")
SP = SP.rename(columns={"filed": "date"})[["ticker", "date", "val"]].rename(columns={"val": "bbv"})
K = K.merge(SP, on=["ticker", "date"], how="left")
g = K.groupby("ticker", sort=False)
K["sp60"] = g.bbv.transform(lambda s: s.rolling(60, min_periods=1).count()) > 0
K["bbcap"] = g.bbv.transform(lambda s: s.rolling(60, min_periods=1).max()) / (K.marcap * 1e6) * 100

BEN = {h: K[UNI].dropna(subset=[f"n{h}"]).groupby("date")[f"n{h}"].mean() for h in (20, 40, 60)}
Z = K[(UNI & UP).fillna(False)].dropna(subset=["n40"]).copy()
Z = Z[Z.date >= "20160101"]
Z["ex"] = Z.n40 - Z.date.map(BEN[40])
print(f"상승 국면 유니버스 {len(Z):,}행 · 티커 {Z.ticker.nunique():,} · {Z.date.min()}~{Z.date.max()}")

AX = [("주식수 1년 변화 dshr", "dshr", "음수=소각"),
      ("EPS 1년 성장 deps", "deps", "높을수록 성장"),
      ("순이익 1년 성장 dni", "dni", "높을수록 성장"),
      ("EPS 수준", "eps_", "흑자 여부"),
      ("내부자 60일 매수액 bv60", "bv60", "클수록 매수"),
      ("내부자 60일 순매수 net60", "net60", "양수=순매수"),
      ("자사주 60일 집행/시총 bbcap", "bbcap", "클수록 집행"),
      ("PBR", "PBR", "낮을수록 싸다"),
      ("PER", "PER", "낮을수록 싸다"),
      ("부채비율", "부채비율", "낮을수록 건전"),
      ("업종 60일 sr60", "sr60", "높을수록 강한 업종")]
print(f"\n{'축':<26}{'결측':>6}  " + " ".join(f"{i+1:>6}" for i in range(10)) + "     ρ(단조)   방향")
print("-" * 118)
for nm, col, note in AX:
    if col not in Z.columns:
        print(f"{nm:<26}  (열 없음)"); continue
    v = pd.to_numeric(Z[col], errors="coerce")
    if v.notna().sum() < 2000:
        print(f"{nm:<26}{v.isna().mean()*100:>5.0f}%  (표본 부족 {int(v.notna().sum()):,})"); continue
    sub = Z[v.notna()].copy(); sub["v"] = v[v.notna()]
    try: q = pd.qcut(sub.v.rank(method="first"), 10, labels=False)
    except Exception: print(f"{nm:<26}  (분위 불가)"); continue
    m = sub.groupby(q).ex.mean()
    rho = np.corrcoef(np.arange(10), m.reindex(range(10)).values)[0, 1]   # 십분위 단조성
    print(f"{nm:<26}{v.isna().mean()*100:>5.0f}%  "
          + " ".join(f"{m.get(i, np.nan):>6.2f}" for i in range(10))
          + f"   {rho:>+7.2f}   {note}")
print("\n※ ρ 는 십분위 번호와 초과수익의 상관 — 1 에 가까울수록 '높을수록 좋다' 가 단조롭다는 뜻.")
print("   ±0.7 넘는 축만 다음 단계(문턱·조합)로 넘긴다.")
try:
    import verdict; verdict.log_trials("us_bull2nd", 11)
except Exception as e: print(e)
