# -*- coding: utf-8 -*-
"""**박한선 트레이딩 — 풀백 S+/S/A · 돌파 · 역추세 금지** 실측 (2026-09-17 요청).

영상: 「매매 노하우, 30분동안 쉬지 않고 떠들었습니다」 (youtube Zp3ED8ErFKA)

⚠ **영상은 비트코인 15분봉·5분봉 데이트레이딩**이다. 우리 패널은 **일봉**이고 보유는 며칠~몇 주다.
   조건을 일봉으로 옮기므로 뜻이 달라질 수 있다 — 영상의 '진짜' 성과가 아니라 **그 생각을
   일봉 국내·미장 주식에 옮겼을 때**의 성과를 잰다.

영상의 매매법(원문에서 옮김):
  **원칙 1** "추세 구조물을 먼저 컨펌하고, 그다음 캔들·거래량을 본다. 역추세 타점으로 바닥을
         잡으려는 행동은 확률적으로 높을 수가 없다."
  **모멘텀 캔들** "최근 음봉 캔들 네다섯 개가 내렸던 거를 한 번에 올리는 상승 캔들"
  **풀백 S+** "강한 추세가 처음 출현 → 조정이 매우 약하게 흐르면서 캔들 크기가 작아짐 → 모멘텀 캔들"
  **풀백 S**  "조정이 추세 방향대로 저점을 계속 올린다 → 모멘텀 캔들.
             반대로 아래로 슬금슬금 흘러내리면 조정이 약해 보여도 모멘텀 캔들 전엔 보수적으로"
  **풀백 A**  "강한 추세 뒤 가격 조정(되돌림) → 모멘텀 캔들. 없으면 거래량 실린 망치형·아래꼬리 캔들"
  **돌파**    "박스권 횡보 → 돌파 캔들을 (상위 봉) 종가로 컨펌" · "수렴 패턴은 캔들이 방향을 보여줘야 완성"
  **추격 금지** "강한 추세 뒤 25·50 이평선까지 되돌림을 기다린다"
  **종목 선택** "상대강도 — 시장이 흘러내릴 때 옆으로 기며 저점을 높이는 종목"

일봉 번역:
  강한 추세      최근 25일 안에 20일 수익률이 +20% 이상이었던 적이 있다
  조정 깊이      어제 종가 / 최근 15일 최고 종가 - 1   (S+·S: -3~-10% · A: -10~-25%)
  모멘텀 캔들    양봉 · 오늘 종가 ≥ 4일 전 종가 · 직전 4일 중 음봉 3개↑ · 몸통 ≥ 20일 평균의 1.5배
  캔들 축소      직전 5일 평균 고저폭 ≤ 그 앞 10일 평균의 70%
  저점 상승      직전 3일 최저가 > 그 앞 3일 최저가
  망치형         아래꼬리 ≥ 몸통 2배 · 윗꼬리 ≤ 몸통 · 거래량 ≥ 20일 평균 1.5배
  추세 구조      상승: 종가 > 20일선 · 20일선이 5일 전보다 높다 / 하락: 반대
  박스           20일 고저폭 ≤ 15% · 종가가 20일 최고가를 넘는다
  수렴           최근 10일 고점 < 그 앞 10일 고점 · 최근 10일 저점 > 그 앞 10일 저점 · 종가가 10일 고점 돌파
  이평 눌림목    강한 추세 · 종가가 20일선 ±2% · 양봉이며 전일보다 오름
  상대강도       지수 5일 수익 < 0 인데 종목 5일 수익이 지수보다 +3%p↑ · 저점 상승

판정은 2026-09-16 부터의 새 기준([[rule-test-unconstrained]]):
  무제한 자금 · 전 신호 동일금액 · **유니버스 초과는 안 본다** · 중앙+절삭 · 연도별 양수 ·
  구간 분리 · **다중검정** · **기존 규칙과 ±5일 겹침률**
국내는 홀드아웃(05~15)까지 3구간, 미장은 생존편향 때문에 2016~26 만([[kr-holdout-2005-2015]]).

    python yt_pullback_momentum.py
"""
import io, os, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
_REAL = sys.stdout
from vp_lib import Runner
from verdict import deflated_sharpe
import FinanceDataReader as fdr

W = 150
OUT = []
t0 = time.time()
NTRY = [0]


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def sec(t):
    P("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


def roll(s, key, n, fn):
    r = s.groupby(key, sort=False).rolling(n, min_periods=n)
    r = getattr(r, fn)()
    return r.reset_index(level=0, drop=True).reindex(s.index)


def gshift(s, key, k):
    return s.groupby(key, sort=False).shift(k)


def features(A, ix_close):
    """A: ticker·date 정렬, o h l c v 열. ix_close: {date: 지수 종가}."""
    tk = A.ticker
    o, h, l, c, v = A.o, A.h, A.l, A.c, A.v
    F = {}
    absb = (c - o).abs()
    avgb = gshift(roll(absb, tk, 20, "mean"), tk, 1)
    neg = (c < o).astype(float)
    neg4 = gshift(roll(neg, tk, 4, "sum"), tk, 1)
    c4 = gshift(c, tk, 4)
    F["mom"] = ((c > o) & (c >= c4) & (neg4 >= 3) & (absb >= 1.5 * avgb)).fillna(False)
    r20 = c / gshift(c, tk, 20) - 1
    F["imp"] = (gshift(roll(r20, tk, 25, "max"), tk, 1) >= 0.20).fillna(False)
    hi15 = gshift(roll(c, tk, 15, "max"), tk, 1)
    pb = gshift(c, tk, 1) / hi15 - 1
    F["pb_s"] = ((pb <= -0.03) & (pb >= -0.10)).fillna(False)
    F["pb_a"] = ((pb < -0.10) & (pb >= -0.25)).fillna(False)
    rng = h - l
    shr = gshift(roll(rng, tk, 5, "mean"), tk, 1) / gshift(roll(rng, tk, 10, "mean"), tk, 6)
    F["shrink"] = (shr <= 0.70).fillna(False)
    lo3 = gshift(roll(l, tk, 3, "min"), tk, 1)
    lo3p = gshift(roll(l, tk, 3, "min"), tk, 4)
    F["upl"] = (lo3 > lo3p).fillna(False)
    F["dnl"] = (lo3 < lo3p).fillna(False)
    lw = np.minimum(o, c) - l
    uw = h - np.maximum(o, c)
    v20 = gshift(roll(v, tk, 20, "mean"), tk, 1)
    F["ham"] = ((lw >= 2 * absb) & (uw <= absb) & (rng > 0) & (v >= 1.5 * v20)).fillna(False)
    ma20 = roll(c, tk, 20, "mean")
    ma20p = gshift(ma20, tk, 5)
    F["up_st"] = ((c > ma20) & (ma20 > ma20p)).fillna(False)
    F["dn_st"] = ((c < ma20) & (ma20 < ma20p)).fillna(False)
    hh20 = gshift(roll(h, tk, 20, "max"), tk, 1)
    ll20 = gshift(roll(l, tk, 20, "min"), tk, 1)
    F["box_brk"] = (((hh20 / ll20 - 1) <= 0.15) & (c > hh20) & (c > o)).fillna(False)
    hh10 = gshift(roll(h, tk, 10, "max"), tk, 1)
    hh10p = gshift(roll(h, tk, 10, "max"), tk, 11)
    ll10 = gshift(roll(l, tk, 10, "min"), tk, 1)
    ll10p = gshift(roll(l, tk, 10, "min"), tk, 11)
    F["conv_brk"] = ((hh10 < hh10p) & (ll10 > ll10p) & (c > hh10) & (c > o)).fillna(False)
    F["ma_pull"] = (F["imp"] & ((c / ma20 - 1).abs() <= 0.02) & (c > o)
                    & (c > gshift(c, tk, 1))).fillna(False)
    # 지수 5일 수익은 **지수 달력으로** 센다 — 종목 행을 5칸 밀면 거래정지 종목에서 어긋난다
    _ix = pd.Series(ix_close).sort_index()
    ir5 = A.date.map((_ix / _ix.shift(5) - 1).to_dict())
    sr5 = c / gshift(c, tk, 5) - 1
    F["rs"] = ((ir5 < 0) & ((sr5 - ir5) >= 0.03)).fillna(False)
    return F


def rules(F):
    return [
        ("원칙1 · 모멘텀캔들 + 상승추세 (추세 일치)", F["mom"] & F["up_st"]),
        ("원칙1 · 모멘텀캔들 + 하락추세 (역추세)", F["mom"] & F["dn_st"]),
        ("풀백 S+ · 강추세·약조정·캔들축소·모멘텀", F["imp"] & F["pb_s"] & F["shrink"] & F["mom"]),
        ("풀백 S  · 강추세·약조정·저점상승·모멘텀", F["imp"] & F["pb_s"] & F["upl"] & F["mom"]),
        ("  └ 대조: 저점하락 (영상이 피하라는 쪽)", F["imp"] & F["pb_s"] & F["dnl"] & F["mom"]),
        ("풀백 A  · 강추세·깊은조정·모멘텀", F["imp"] & F["pb_a"] & F["mom"]),
        ("풀백 A' · 강추세·깊은조정·거래량 망치형", F["imp"] & F["pb_a"] & F["ham"]),
        ("박스 종가돌파", F["box_brk"]),
        ("수렴 종가돌파", F["conv_brk"]),
        ("이평 눌림목 · 강추세·20일선±2%·양봉", F["ma_pull"]),
        ("상대강도 풀백 · 지수약세·종목강세·저점상승", F["imp"] & F["upl"] & F["rs"]
         & (F["pb_s"] | F["pb_a"])),
    ]


def overlap(Y, OLD, di_of):
    """새 신호 중 기존 규칙과 ±5거래일 같은 종목인 비율."""
    if OLD is None or not len(Y):
        return np.nan
    key = {}
    for t, d in zip(OLD.ticker.values, OLD.date.values):
        if d in di_of:
            key.setdefault(t, []).append(di_of[d])
    hit = 0
    for t, d in zip(Y.ticker.values, Y.date.values):
        i = di_of.get(d)
        if i is not None and any(abs(i - x) <= 5 for x in key.get(t, [])):
            hit += 1
    return hit / len(Y) * 100


SEGS_KR = [("홀드05~15", "20050101", "20151231"), ("학습16~22", "20160101", "20221231"),
           ("검증23~26", "20230101", "20301231")]
SEGS_US = [("학습16~22", "20160101", "20221231"), ("검증23~26", "20230101", "20301231")]


def evaluate(R, tag, cond, hold, segs, OLD, di_of, keep):
    NTRY[0] += 1
    m = R.run(tag, cond, hold=hold, minn=30, quiet=True)
    if not m:
        n = int((R.uni & cond.fillna(False)).sum())
        return "  %-44s%4d일 %s" % (tag, hold, "(표본 부족 · 원시 %s건)" % f"{n:,}")
    Y = m["Y"]
    v = Y.r
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() else np.nan
    cells = ""
    for lbl, a, b in segs:
        z = Y[(Y.date >= a) & (Y.date <= b)].r
        cells += ("%9.2f" % z.median()) if len(z) >= 15 else "%9s" % ("n%d" % len(z))
    ov = overlap(Y, OLD, di_of)
    ok = m["med"] > 0 and m["trim"] > 0 and m["pos"] / max(m["ny"], 1) >= 0.6
    mo = Y.groupby("ym").r.mean()
    keep.append((tag, hold, mo, ok))
    return ("  %-44s%4d일%7s%8.2f%8.2f%6.0f%%%9.0f%%%s%7d/%-3d%6.1f%8.0f%%%s"
            % (tag, hold, f"{m['n']:,}", m["med"], m["trim"], m["win"], t5, cells,
               m["pos"], m["ny"], m["per"], ov, "  ◎" if ok else ""))


def market(name, A, uni, since, segs, ix_close, OLD, di_of):
    sec("【%s】" % name)
    log("%s 재료 만드는 중" % name)
    F = features(A, ix_close)
    R = Runner(A, uni, name, since=since)
    hdr = ("  %-44s%6s%7s%8s%8s%7s%10s" % ("규칙", "보유", "n", "중앙", "절삭", "승률", "상위5%기여")
           + "".join("%9s" % s[0] for s in segs) + "%10s%6s%9s" % ("양수해", "월", "겹침"))
    P(hdr)
    keep = []
    for tag, cond in rules(F):
        for hold in (5, 10, 20):
            P(evaluate(R, tag, cond, hold, segs, OLD, di_of, keep))
            log("  %s %d일" % (tag[:18], hold))
        P()
    P("  ※ ◎ = 중앙·절삭 둘 다 양수 · 양수해 60%↑ (1차 관문일 뿐이다 — 아래 다중검정을 넘어야 한다)")
    P("  ※ 겹침 = 기존 규칙과 ±5거래일 같은 종목 비율. 높으면 새 정보가 아니다.")
    return keep


# ═══ 국내 ═══════════════════════════════════════════════════════════════
log("국내: 기존 규칙 신호(겹침 비교용)")
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
exec(compile(MID, "portfolio.py", "exec"), ns)
OLD_KR = ns["S"][["date", "ticker"]].copy()
IXK = ns["IX"]
IXK_CLOSE = dict(zip(IXK.date, IXK.Close))
del ns

log("국내 패널")
K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K["o"], K["h"], K["l"], K["c"], K["v"] = K.open, K.high, K.low, K.close, K.volume
UNI_K = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
DI_K = {d: i for i, d in enumerate(sorted(K.date.unique()))}
KEEP_KR = market("국내 · 코스피+코스닥 · 거래대금 상위 40%", K, UNI_K, "20050101", SEGS_KR,
                 IXK_CLOSE, OLD_KR, DI_K)
del K, UNI_K

# ═══ 미장 ═══════════════════════════════════════════════════════════════
log("미장 패널 (us_scan + panel_us 수정주가 OHLC)")
U = pd.read_pickle(BASE / "data/us_scan.pkl")
U = U[((~U.pref.fillna(False)) & (U.rawclose >= 3)).fillna(False)]
PU = pd.read_pickle(BASE / "data/panel_us.pkl")[["ticker", "date", "p_open", "p_high", "p_low", "px", "volume"]]
PU = PU.rename(columns={"volume": "vol_p"})
n0 = len(U)
U = U.merge(PU, on=["ticker", "date"], how="left")
del PU
assert len(U) == n0
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
U = U[U.px.notna()].reset_index(drop=True)
U["o"], U["h"], U["l"], U["c"], U["v"] = U.p_open, U.p_high, U.p_low, U.px, U.vol_p
UNI_U = (U.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
IXU = fdr.DataReader("US500", "2004-06-01")
IXU = IXU[IXU.Close > 0]
IXU_CLOSE = dict(zip(IXU.index.strftime("%Y%m%d"), IXU.Close))
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    OLD_US = pickle.load(f)["S"][["date", "ticker"]]
DI_U = {d: i for i, d in enumerate(sorted(U.date.unique()))}
KEEP_US = market("미장 · 거래대금 상위 40% (2016~ · 생존편향 때문)", U, UNI_U, "20160101", SEGS_US,
                 IXU_CLOSE, OLD_US, DI_U)
del U, UNI_U

# ═══ 다중검정 ═══════════════════════════════════════════════════════════
sec("다중검정 보정 — 이번에 돌린 칸 %d개 · 1차 관문(◎)을 넘은 것만" % NTRY[0])
P("  %-8s%-44s%6s%8s%9s%10s%12s%10s" % ("시장", "규칙", "보유", "월수", "샤프", "문턱샤프", "진짜일확률", "판정"))
any_ok = False
for mk, keep in (("국내", KEEP_KR), ("미장", KEEP_US)):
    for tag, hold, mo, ok in keep:
        if not ok:
            continue
        any_ok = True
        d = deflated_sharpe(mo, NTRY[0])
        if not d:
            P("  %-8s%-44s%5d일  (못 잼)" % (mk, tag, hold)); continue
        P("  %-8s%-44s%5d일%8d%9.3f%10.3f%11.1f%%%10s"
          % (mk, tag, hold, d["T"], d["sr"], d["sr0"], d["dsr"] * 100,
             "통과" if d["dsr"] >= 0.95 else "**기각**"))
if not any_ok:
    P("  1차 관문을 넘은 칸이 없다.")

P("\n총 %.0f초" % (time.time() - t0))
io.open(BASE / "_yt_pm_out.txt", "w", encoding="utf-8").write("\n".join(OUT))
log("결과를 _yt_pm_out.txt 에 썼다")
