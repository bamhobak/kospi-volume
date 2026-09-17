# -*- coding: utf-8 -*-
"""**돈무한 — 하이킨아시 리본 단타** 실측 (2026-09-17 요청).

영상: 「단 2달만에 400만 원 → 3억으로 만든 하이킨아시 단타매매 전략 [5분봉]」 (youtube O7D7rRK9-5o)

⚠ 영상은 **비트코인 5분봉 선물(롱·숏)** 이다. 여기서는 **일봉 · 롱만**으로 옮긴다
   (국내는 공매도 불가). "2달 400만→3억" 은 레버리지 코인 선물의 골라 보인 사례라 기대치가 아니다.

영상 규칙(원문에서 옮김):
  리본   하이킨아시(시고저종 평균으로 그린 캔들)에 **평균을 한 번 더** 낸 지표. 초록=롱만 · 빨강=숏만
  대기   "색이 바뀌는 순간 들어가면 휩소에 물린다" — 가격이 **리본 근처까지 눌릴 때까지** 기다린다
  신호   리본 근처에서 **도지형 캔들**: "몸통이 캔들 전체 길이의 **25% 이하**,
         캔들 전체 크기가 **직전 두 캔들 중 하나보다 크면**" · 종가 마감 확인
  진입   "다음 캔들이 도지 **꼬리 고점을 위로 돌파하는 순간**"
  손절   "도지형 캔들의 **아래꼬리 끝**"
  익절   "리본이 초록인 동안 들고 가다가 **처음으로 빨갛게 바뀌면 전량 정리**"

'평균을 한 번 더' 의 정확한 계산은 영상에 없다 → 세 가지로 잰다.
  기본HA    하이킨아시 한 번 (종가=(시+고+저+종)/4 · 시가=직전 (시가+종가)/2)
  HA×2      하이킨아시로 만든 캔들에 하이킨아시를 한 번 더 — '평균 낸 걸 또 평균' 문자 그대로
  SmoothHA  트레이딩뷰에 흔한 Smoothed Heikin Ashi — 시고저종에 EMA10 → HA → 다시 EMA10

일봉 번역:
  리본 근처  도지 저가 ≤ 리본 윗변(max(HA시,HA종)) · 도지 종가 ≥ 리본 아랫변
  체결(현실적으로)
    진입  다음날 고가 > 도지 고가 이면 max(시가, 도지 고가) — 갭 상승이면 시가
    손절  저가 ≤ 도지 저가 이면 min(시가, 도지 저가) — 갭 하락이면 시가. 진입 당일 닿으면 손절로 본다
    익절  리본이 빨강으로 마감한 날의 **다음날 시가**
  같은 종목은 보유 중에 다시 사지 않는다.

비교 칸:
  원안           리본·도지·돌파 진입 · 도지저가 손절 · 리본 빨강 익절
  손절 없음      위에서 손절만 뺌
  고정 10·20일   같은 진입 · 손절 없이 N일 뒤 종가 — 청산 규칙이 값을 하나
  대조: 리본 무시     도지 돌파만(리본 조건 없음) · 고정 10일
  대조: 색 전환 즉시  리본이 초록으로 바뀐 다음날 시가 진입 · 리본 빨강 익절 — 영상이 하지 말라는 방식

판정: 새 기준 — 무제한 자금 · 전 신호 동일금액 · 유니버스 초과 안 봄 · 중앙+절삭 · 연도별 양수 ·
구간 분리(국내 05~15/16~22/23~26 · 미장 16~22/23~26) · 다중검정 · 기존 규칙과 ±5일 겹침.
보유기간이 거래마다 달라서 **평균 보유일과 일당 수익**도 같이 낸다.

    python yt_heikin_ribbon.py
"""
import io, os, pickle, sys, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
_REAL = sys.stdout
from verdict import deflated_sharpe, boot_ci

W = 160
OUT = []
t0 = time.time()
NTRY = [0]


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def sec(t):
    P("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


def gshift(s, tk, k):
    return s.groupby(tk, sort=False).shift(k)


def gewm(s, tk, **kw):
    return s.groupby(tk, sort=False).ewm(adjust=False, **kw).mean().reset_index(level=0, drop=True).reindex(s.index)


def heikin(O, H, L, C, tk):
    """하이킨아시. HA시가[t] = (HA시가[t-1] + HA종가[t-1]) / 2 → α=0.5 지수평균으로 풀린다."""
    hc = (O + H + L + C) / 4
    x = gshift(hc, tk, 1)
    first = x.isna()
    x = x.where(~first, (O + C) / 2)
    ho = gewm(x, tk, alpha=0.5)
    hh = pd.concat([H, ho, hc], axis=1).max(axis=1)
    hl = pd.concat([L, ho, hc], axis=1).min(axis=1)
    return ho, hh, hl, hc


def ribbons(A):
    tk = A.ticker
    O, H, L, C = A.o, A.h, A.l, A.c
    out = {}
    ho, hh, hl, hc = heikin(O, H, L, C, tk)
    out["기본HA"] = (ho, hc)
    ho2, hh2, hl2, hc2 = heikin(ho, hh, hl, hc, tk)
    out["HA×2"] = (ho2, hc2)
    so, sh, sl, sc = (gewm(s, tk, span=10) for s in (O, H, L, C))
    ho3, _, _, hc3 = heikin(so, sh, sl, sc, tk)
    out["SmoothHA"] = (gewm(ho3, tk, span=10), gewm(hc3, tk, span=10))
    return out


def trades(A, uni, green, ho, hc, mode, hold=None, use_stop=True, since="20050101"):
    """mode: 'doji' 원안 진입 · 'doji_noribbon' 리본 무시 · 'flip' 초록 전환 즉시."""
    n = len(A)
    tkv = A.ticker.values
    o, h, l, c = A.o.values, A.h.values, A.l.values, A.c.values
    cost = A.cost.fillna(0).values.astype(float)
    date = A.date.values
    g = green.values
    # 종목 끝 인덱스
    starts = np.r_[0, np.flatnonzero(tkv[1:] != tkv[:-1]) + 1]
    ends = np.r_[starts[1:] - 1, n - 1]
    tend = np.repeat(ends, np.diff(np.r_[starts, n]))
    # 리본이 빨강인 가장 가까운 인덱스(>= i) — 종목을 넘으면 '없음'
    idx = np.arange(n)
    red_idx = np.where(~g, idx, n + 10)
    nextred = np.minimum.accumulate(red_idx[::-1])[::-1]

    body = np.abs(c - o)
    rng = h - l
    r1 = pd.Series(rng).groupby(tkv, sort=False).shift(1).values
    r2 = pd.Series(rng).groupby(tkv, sort=False).shift(2).values
    up_edge = np.maximum(ho.values, hc.values)
    lo_edge = np.minimum(ho.values, hc.values)
    doji = (rng > 0) & (body <= 0.25 * rng) & (rng > np.fmin(r1, r2))
    near = (l <= up_edge) & (c >= lo_edge)
    u = uni.values & (date >= since)
    if mode == "doji":
        sig = doji & near & g & u
    elif mode == "doji_noribbon":
        sig = doji & u
    elif mode == "flip":
        gprev = pd.Series(g).groupby(tkv, sort=False).shift(1).fillna(True).values.astype(bool)
        sig = g & ~gprev & u
    sig = np.flatnonzero(sig)

    rows = []
    busy_until = {}
    for s in sig:
        e = s + 1
        if e > tend[s]:
            continue
        tk = tkv[s]
        if busy_until.get(tk, -1) >= e:
            continue
        if mode == "flip":
            px_in = o[e]
            stop = np.nan
        else:
            if not (h[e] > h[s]):
                continue                       # 다음 봉이 돌파 못 하면 신호 소멸
            px_in = max(o[e], h[s])
            stop = l[s]
        if not np.isfinite(px_in) or px_in <= 0:
            continue
        te = tend[s]
        if hold is not None:
            k_end = e + hold - 1
            if k_end > te:
                continue
            out_k, px_out = k_end, c[k_end]
            if use_stop and np.isfinite(stop):
                seg = l[e:k_end + 1] <= stop
                if seg.any():
                    k = e + int(np.argmax(seg))
                    out_k, px_out = k, (stop if k == e else min(o[k], stop))
        else:
            r = nextred[e]
            if r > te:
                continue                       # 끝까지 빨강이 안 나옴 — 미완결은 버린다
            exit_k = r + 1
            if exit_k > te:
                continue
            out_k, px_out = exit_k, o[exit_k]
            if use_stop and np.isfinite(stop):
                seg = l[e:exit_k + 1] <= stop
                if seg.any():
                    k = e + int(np.argmax(seg))
                    out_k, px_out = k, (stop if k == e else min(o[k], stop))
        if not np.isfinite(px_out) or px_out <= 0:
            continue
        ret = (px_out / px_in - 1) * 100 - cost[s]
        rows.append((date[s], tk, ret, out_k - e + 1))
        busy_until[tk] = out_k
    return pd.DataFrame(rows, columns=["date", "ticker", "r", "days"])


def overlap(T, OLD, di_of):
    if OLD is None or not len(T):
        return np.nan
    key = {}
    for t, d in zip(OLD.ticker.values, OLD.date.values):
        if d in di_of:
            key.setdefault(t, []).append(di_of[d])
    hit = 0
    for t, d in zip(T.ticker.values, T.date.values):
        i = di_of.get(d)
        if i is not None and any(abs(i - x) <= 5 for x in key.get(t, [])):
            hit += 1
    return hit / len(T) * 100


def report(tag, T, segs, OLD, di_of, keep, nmon):
    NTRY[0] += 1
    if len(T) < 30:
        return "  %-40s  (표본 부족 %d건)" % (tag, len(T))
    v = T.r
    tr = v[v <= v.quantile(0.95)].mean()
    t5 = v.nlargest(max(1, len(v) // 20)).sum() / v.sum() * 100 if v.sum() else np.nan
    T = T.assign(yr=T.date.str[:4], ym=T.date.str[:6])
    yr = T.groupby("yr").r.median()
    pos, ny = int((yr > 0).sum()), len(yr)
    cells = ""
    for lbl, a, b in segs:
        z = T[(T.date >= a) & (T.date <= b)].r
        cells += ("%9.2f" % z.median()) if len(z) >= 15 else "%9s" % ("n%d" % len(z))
    dd = T.days.mean()
    ov = overlap(T, OLD, di_of)
    ok = v.median() > 0 and tr > 0 and pos / max(ny, 1) >= 0.6
    keep.append((tag, T.groupby("ym").r.mean(), ok))
    return ("  %-40s%8s%8.2f%8.2f%8.2f%6.0f%%%9.0f%%%7.1f일%8.3f%s%7d/%-3d%6.1f%7.0f%%%s"
            % (tag, f"{len(v):,}", v.mean(), v.median(), tr, (v > 0).mean() * 100, t5,
               dd, tr / dd, cells, pos, ny, len(v) / nmon, ov, "  ◎" if ok else ""))


def market(name, A, uni, since, segs, OLD, di_of):
    sec("【%s】" % name)
    log("%s 리본 만드는 중" % name)
    RB = ribbons(A)
    nmon = len({d[:6] for d in A.date[A.date >= since].unique()}) or 1
    P("  %-40s%8s%8s%8s%8s%7s%10s%8s%8s" % ("구성", "n", "평균", "중앙", "절삭", "승률", "상위5%기여", "보유", "일당")
      + "".join("%9s" % s[0] for s in segs) + "%10s%6s%8s" % ("양수해", "월", "겹침"))
    keep = []
    for rb, (ho, hc) in RB.items():
        green = (hc > ho).fillna(False)
        P("  [리본: %s]" % rb)
        for lab, kw in [("원안 (도지저가 손절·리본 빨강 익절)", dict(mode="doji")),
                        ("손절 없음 (리본 빨강 익절만)", dict(mode="doji", use_stop=False)),
                        ("같은 진입 · 고정 10일", dict(mode="doji", hold=10, use_stop=False)),
                        ("같은 진입 · 고정 20일", dict(mode="doji", hold=20, use_stop=False))]:
            T = trades(A, uni, green, ho, hc, since=since, **kw)
            P(report("  " + lab, T, segs, OLD, di_of, keep, nmon))
            log("  %s %s %d건" % (rb, lab[:10], len(T)))
        if rb == "HA×2":
            T = trades(A, uni, green, ho, hc, mode="doji_noribbon", hold=10, use_stop=False, since=since)
            P(report("  대조: 리본 무시 · 도지돌파 · 10일", T, segs, OLD, di_of, keep, nmon))
            T = trades(A, uni, green, ho, hc, mode="flip", use_stop=False, since=since)
            P(report("  대조: 초록 전환 즉시 진입 (영상 금지)", T, segs, OLD, di_of, keep, nmon))
        P()
    P("  ※ 보유 = 평균 보유 거래일 · 일당 = 절삭평균 ÷ 평균 보유일 (%/일)")
    P("  ※ ◎ = 중앙·절삭 둘 다 양수 · 양수해 60%↑ — 1차 관문일 뿐, 아래 다중검정을 넘어야 한다")
    P("  ※ 참고로 우리 국내 규칙 일당(절삭÷보유일)은 [업종붕괴 이탈] +1.2 · [낙폭과대] +1.6 · [외인 매집] +0.1 수준이다")
    return keep


# ═══ 국내 ═══
log("국내: 기존 규칙 신호(겹침 비교용)")
SRC = (BASE / "portfolio.py").read_text(encoding="utf-8")
HEAD, REST = SRC.split("# 신호를 한 표로 모은다", 1)
MID = "# 신호를 한 표로 모은다" + REST.split("# @@ANALYSIS", 1)[0]
ns = {"__file__": str(BASE / "portfolio.py")}
exec(compile(HEAD, "portfolio.py", "exec"), ns)
exec(compile(MID, "portfolio.py", "exec"), ns)
OLD_KR = ns["S"][["date", "ticker"]].copy()
del ns

K = pd.read_pickle(BASE / "data/kr_scan.pkl")
K = K[((K.close >= 1000) & (~K.pref.fillna(False))).fillna(False)]
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K["o"], K["h"], K["l"], K["c"] = K.open, K.high, K.low, K.close
UNI_K = (K.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
DI_K = {d: i for i, d in enumerate(sorted(K.date.unique()))}
SEGS_KR = [("홀드05~15", "20050101", "20151231"), ("학습16~22", "20160101", "20221231"),
           ("검증23~26", "20230101", "20301231")]
KEEP_KR = market("국내 · 거래대금 상위 40%", K, UNI_K, "20050101", SEGS_KR, OLD_KR, DI_K)
del K, UNI_K

# ═══ 미장 ═══
log("미장 패널")
U = pd.read_pickle(BASE / "data/us_scan.pkl")
U = U[((~U.pref.fillna(False)) & (U.rawclose >= 3)).fillna(False)][["ticker", "date", "amt20", "cost", "rawclose"]]
PU = pd.read_pickle(BASE / "data/panel_us.pkl")[["ticker", "date", "p_open", "p_high", "p_low", "px"]]
U = U.merge(PU, on=["ticker", "date"], how="inner")
del PU
U = U.sort_values(["ticker", "date"]).reset_index(drop=True)
U["o"], U["h"], U["l"], U["c"] = U.p_open, U.p_high, U.p_low, U.px
UNI_U = (U.groupby("date").amt20.rank(pct=True) >= 0.60).fillna(False)
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    OLD_US = pickle.load(f)["S"][["date", "ticker"]]
DI_U = {d: i for i, d in enumerate(sorted(U.date.unique()))}
SEGS_US = [("학습16~22", "20160101", "20221231"), ("검증23~26", "20230101", "20301231")]
KEEP_US = market("미장 · 거래대금 상위 40% (2016~ · 생존편향 때문)", U, UNI_U, "20160101", SEGS_US, OLD_US, DI_U)
del U, UNI_U

sec("다중검정 보정 — 돌린 칸 %d개 · 1차 관문(◎) 통과만" % NTRY[0])
P("  %-6s%-42s%8s%9s%10s%12s%10s" % ("시장", "구성", "월수", "샤프", "문턱샤프", "진짜일확률", "판정"))
hit = False
for mk, keep in (("국내", KEEP_KR), ("미장", KEEP_US)):
    for tag, mo, ok in keep:
        if not ok:
            continue
        hit = True
        d = deflated_sharpe(mo, NTRY[0])
        if not d:
            P("  %-6s%-42s  (못 잼)" % (mk, tag)); continue
        P("  %-6s%-42s%8d%9.3f%10.3f%11.1f%%%10s"
          % (mk, tag, d["T"], d["sr"], d["sr0"], d["dsr"] * 100, "통과" if d["dsr"] >= 0.95 else "**기각**"))
if not hit:
    P("  1차 관문을 넘은 칸이 없다.")

P("\n총 %.0f초" % (time.time() - t0))
io.open(BASE / "_yt_ha_out.txt", "w", encoding="utf-8").write("\n".join(OUT))
log("결과를 _yt_ha_out.txt 에 썼다")
