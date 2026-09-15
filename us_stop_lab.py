# -*- coding: utf-8 -*-
"""**미장 규칙에 손절·트레일을 달면** (2026-09-15 요청).

사용자 지적: "미장 규칙들 최악 마이너스가 너무 깊다"(-62.8% ~ -98.3%). 맞는 지적이다.

⚠ 그런데 이 프로젝트는 **바로 여기서 두 번 크게 데였다.**
  · 국내 트레일 -8% 는 낙관 체결에서 5.64→7.24배로 좋아 보였으나, 보수 체결로 다시 재니
    없는 쪽이 더 나았다 → **2026-09-12 전면 폐지**([[trailing-stop]] · [[tiebreak-trail]]).
  · 미국은 더 심하다 — 낙관 -8% 에서 [낙폭과대] +4.36 인데 **보수판은 -0.58**,
    [저PBR 낙폭] +4.68 → **+0.73** 이었다([[us-trail-fill-artifact]]).
  체결 가정 한 줄이 부호를 바꾼다. 그래서 여기서는 **보수 체결을 기본**으로 재고,
  낙관 체결은 '얼마나 부풀려지는가' 를 보여주려고 나란히만 둔다.

  보수 체결 = 그날 **종가**로 손절·트레일 발동을 판정하고 **다음날 시가**에 판다.
              (우리 백테스트가 종가 기준이라 실전도 그렇게만 할 수 있다)

  ① 최악값의 정체 — -98% 같은 건 손절로 막히는 종류인가
  ② 고정 손절 -10~-30% · 규칙별 (보수 vs 낙관)
  ③ 트레일 -10~-25% · 규칙별 (보수 vs 낙관)
  ④ 계좌 — 최악값이 줄어든 대가로 무엇을 잃나

    python us_stop_lab.py
"""
import pickle, sys, time, warnings
warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
import numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).parent
NS = 30
W = 118
NM = {"N1": "상승장 신고가", "N2": "낙폭과대", "N3": "저PBR 낙폭",
      "N4": "자사주 낙폭", "N5": "잔잔한 급등주"}
HOLD = {"N1": 40, "N2": 20, "N3": 40, "N4": 60, "N5": 60}
t0 = time.time()


def sec(t):
    print("\n" + "=" * W + "\n" + t + "\n" + "=" * W)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), flush=True)


# ── 패널: 종가·시가 경로가 필요하다 ──────────────────────────────────────
log("us_scan.pkl")
K = pd.read_pickle(BASE / "data/us_scan.pkl")
K = K[((~K.pref.fillna(False)) & (K.rawclose >= 3)).fillna(False)]
# ⚠ **us_scan 의 close 를 쓴다.** 처음엔 panel_us 의 close 를 붙였다가 헛값을 봤다 —
#   us_scan.buy 는 **수정주가** 기준 익일 시가인데 panel_us.close 는 **원주가**다
#   (AAPL 2024-01-02: buy 182.00 / us_scan.close 183.40 / panel_us.close 185.64).
#   기준이 다른 둘을 나누면 분할·배당이 많은 종목에서 수익률이 통째로 망가진다.
#   손절 -30% 를 달았는데 평균이 +1.45→+22.77% 로 **늘어난** 것이 그 증상이었다.
K = K[["ticker", "date", "buy", "cost", "amt20", "close"]].copy()
K = K.sort_values(["ticker", "date"]).reset_index(drop=True)
K = K[K.close.notna()]
ud = sorted(K.date.unique())
DD = {d: i for i, d in enumerate(ud)}
K["di"] = K.date.map(DD).astype(np.int32)
g = K.groupby("ticker", sort=False)
log("  %s행" % f"{len(K):,}")

# 보유 구간의 미래 종가·시가를 미리 쌓아 둔다 (최대 60일)
MAXH = 60
CL = np.column_stack([g.close.shift(-i).values for i in range(1, MAXH + 1)])   # 1..60일 뒤 종가
OP = np.column_stack([g.buy.shift(-i).values for i in range(0, MAXH + 1)])     # 0..60일 뒤 '익일 시가'
log("  경로 %s × %d 완성" % (f"{len(K):,}", MAXH))

POS = {(t, d): i for i, (t, d) in enumerate(zip(K.ticker.values, K.date.values))}

# ── 신호는 정본 캐시에서 ─────────────────────────────────────────────────
with open(BASE / "data" / "sector_drop_us_sig.pkl", "rb") as f:
    C = pickle.load(f)
S0, DS, ADI, PCT = C["S"], C["DS"], C["ADI"], C["PCT"]
S0 = S0.copy()
S0["row"] = [POS.get((t, d), -1) for t, d in zip(S0.ticker.values, S0.date.values)]
miss = int((S0.row < 0).sum())
S0 = S0[S0.row >= 0].reset_index(drop=True)
log("신호 %s건 (경로 못 찾아 버린 것 %d)" % (f"{len(S0):,}", miss))
ROW = S0.row.values
BUY = K.buy.values[ROW]
COST = K.cost.values[ROW]
HLD = S0.hold.values.astype(int)


def apply_exit(stop=None, trail=None, cons=True):
    """손절·트레일을 적용한 수익률(%). cons=True 면 보수 체결(종가 판정 → 익일 시가).

    stop  : 매수가 대비 -stop 아래로 **종가**가 내려온 첫날
    trail : 보유 중 종가 최고점(시작값 매수가) 대비 -trail 아래로 **종가**가 내려온 첫날
    """
    out = np.empty(len(S0))
    for h in sorted(set(HLD)):
        m = HLD == h
        idx = ROW[m]
        c = CL[idx, :h]                      # 1..h일 뒤 종가
        b = BUY[m][:, None]
        if trail is not None:
            run = np.maximum.accumulate(np.concatenate([b, c], axis=1), axis=1)[:, 1:]
            hit = c <= run * (1 - trail)
        elif stop is not None:
            hit = c <= b * (1 - stop)
        else:
            hit = np.zeros_like(c, dtype=bool)
        ok = hit.any(axis=1)
        first = np.where(ok, hit.argmax(axis=1), h - 1)
        if cons:
            # 보수: 발동일 **다음날 시가**. OP[:,k] = k일 뒤의 '익일 시가'
            px = np.where(ok, OP[idx, np.minimum(first + 1, MAXH)], c[np.arange(len(c)), h - 1])
        else:
            # 낙관: 발동 가격 그대로 (트레일은 run*(1-t), 손절은 매수가*(1-s))
            if trail is not None:
                run2 = np.maximum.accumulate(np.concatenate([b, c], axis=1), axis=1)[:, 1:]
                px = np.where(ok, run2[np.arange(len(c)), first] * (1 - trail),
                              c[np.arange(len(c)), h - 1])
            else:
                px = np.where(ok, b[:, 0] * (1 - stop), c[np.arange(len(c)), h - 1])
        px = np.where(np.isnan(px), c[np.arange(len(c)), h - 1], px)
        r = (px / BUY[m] - 1) * 100 - COST[m]
        # 경로가 끝까지 없는 소수(최근 신호 등)는 캐시의 값을 그대로 쓴다 —
        # 안 그러면 NaN 하나가 계좌 전체를 nan 으로 만든다(2026-09-15에 그랬다).
        out[m] = np.where(np.isnan(r), S0.ret.astype(float).values[m], r)
    return out


# ── 자기검증: 아무 조건 없이 돌린 값이 캐시의 ret 과 같아야 한다 ───────────
_chk = apply_exit()
_d = np.abs(_chk - S0.ret.astype(float).values)
_ok = np.nanmedian(_d)
log("자기검증 — 조건 없이 돌린 값 vs 캐시 ret : 중앙 차이 %.4f%%p · 최대 %.2f%%p"
    % (_ok, np.nanmax(_d)))
if _ok > 0.05:
    log("  ❌ 경로 계산이 캐시와 어긋난다 — 여기서 멈춘다")
    sys.exit(1)
log("  ✅ 일치 — 손절·트레일 계산을 믿을 수 있다")


def stat(v):
    v = pd.Series(v).dropna()
    trim = v[v <= v.quantile(0.95)].mean()
    return v.mean(), v.median(), (v > 0).mean() * 100, trim, v.min()


sec("① 최악값의 정체 — 손절로 막히는 종류인가")
base = S0.ret.astype(float).values
print("  %-16s%9s%11s%11s   매수 다음날 이미 그 밑인 건수" % ("규칙", "최악%", "-50%보다↓", "-30%보다↓"))
for r in ["N1", "N2", "N3", "N4", "N5"]:
    m = (S0.rid == r).values
    v = base[m]
    idx = ROW[m]
    d1 = (CL[idx, 0] / BUY[m] - 1) * 100
    print("  %-16s%+9.1f%11s%11s   -30%% 밑 %s건 · -50%% 밑 %s건"
          % (NM[r], np.nanmin(v), f"{int((v <= -50).sum()):,}", f"{int((v <= -30).sum()):,}",
             f"{int(np.nansum(d1 <= -30)):,}", f"{int(np.nansum(d1 <= -50)):,}"))
print("  ※ '매수 다음날 이미 그 밑' = 첫날 종가가 벌써 -30/-50%. 이런 건 **손절로 못 막는다**.")

sec("② 고정 손절 — 보수 체결(종가 판정·익일 시가) vs 낙관 체결")
print("  %-16s%-12s%9s%9s%8s%9s%9s   %s" % ("규칙", "설정", "평균%", "중앙%", "승률", "절삭%", "최악%", "낙관이면 평균"))
RES = {}
for r in ["N1", "N2", "N3", "N4", "N5"]:
    m = (S0.rid == r).values
    for lbl, kw in [("없음(지금)", {}), ("손절 -10%", dict(stop=0.10)), ("손절 -15%", dict(stop=0.15)),
                    ("손절 -20%", dict(stop=0.20)), ("손절 -25%", dict(stop=0.25)),
                    ("손절 -30%", dict(stop=0.30))]:
        v = apply_exit(cons=True, **kw)[m] if kw else base[m]
        vo = apply_exit(cons=False, **kw)[m] if kw else base[m]
        a, md, w, tr, mn = stat(v)
        RES[(r, lbl)] = v
        print("  %-16s%-12s%+9.2f%+9.2f%7.0f%%%+9.2f%+9.1f   %+9.2f"
              % (NM[r] if lbl == "없음(지금)" else "", lbl, a, md, w, tr, mn, np.nanmean(vo)))
    print()

sec("③ 트레일 — 보수 체결 vs 낙관 체결")
print("  %-16s%-12s%9s%9s%8s%9s%9s   %s" % ("규칙", "설정", "평균%", "중앙%", "승률", "절삭%", "최악%", "낙관이면 평균"))
for r in ["N1", "N2", "N3", "N4", "N5"]:
    m = (S0.rid == r).values
    for lbl, kw in [("없음(지금)", {}), ("트레일 -10%", dict(trail=0.10)), ("트레일 -15%", dict(trail=0.15)),
                    ("트레일 -20%", dict(trail=0.20)), ("트레일 -25%", dict(trail=0.25))]:
        v = apply_exit(cons=True, **kw)[m] if kw else base[m]
        vo = apply_exit(cons=False, **kw)[m] if kw else base[m]
        a, md, w, tr, mn = stat(v)
        RES[(r, lbl)] = v
        print("  %-16s%-12s%+9.2f%+9.2f%7.0f%%%+9.2f%+9.1f   %+9.2f"
              % (NM[r] if lbl == "없음(지금)" else "", lbl, a, md, w, tr, mn, np.nanmean(vo)))
    print()


# ── ④ 계좌 ───────────────────────────────────────────────────────────────
def sim(S, ds, seed=None, cash_cap=1.0):
    rng = np.random.default_rng(seed) if seed is not None else None
    nav, held, cnt = 1.0, {}, {}
    byd = {d: gg for d, gg in S[S.date.isin(set(ds))].groupby("date")}
    peak, mdd, inv = 1.0, 0.0, []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            nav *= 1 + held.pop(k)[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
        inv.append(sum(PCT[k[0]] for k in held) / 100)
        gg = byd.get(d)
        if gg is None:
            continue
        gg = (gg.sample(frac=1, random_state=int(rng.integers(1 << 30))) if rng is not None
              else gg.sort_values("amt20", ascending=False, na_position="last"))
        for r in gg.itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            if sum(PCT[x[0]] for x in held) / 100 + r.pct / 100 > cash_cap:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    for v in held.values():
        nav *= 1 + v[1] / 100
    return nav, mdd * 100, float(np.mean(inv))


sec("④ 계좌 — 전 규칙에 같은 설정을 달면 (보수 체결 · %d시드)" % NS)
print("  %-16s%9s%9s%12s%12s%9s%9s" % ("설정", "자산", "낙폭", "시드중앙", "시드최악낙폭", "자산승", "낙폭승"))
b30 = [sim(S0, DS, seed=k) for k in range(NS)]
BN = [x[0] for x in b30]
BM = [x[1] for x in b30]
n0, m0, _ = sim(S0, DS)
print("  %-16s%8.2f배%8.1f%%%11.2f배%11.1f%%%9s%9s"
      % ("없음(지금)", n0, m0, np.median(BN), min(BM), "—", "—"))
for lbl, kw in [("손절 -15%", dict(stop=0.15)), ("손절 -20%", dict(stop=0.20)),
                ("손절 -25%", dict(stop=0.25)), ("손절 -30%", dict(stop=0.30)),
                ("트레일 -15%", dict(trail=0.15)), ("트레일 -20%", dict(trail=0.20)),
                ("트레일 -25%", dict(trail=0.25))]:
    S = S0.copy()
    S["ret"] = apply_exit(cons=True, **kw)
    a, mm, _ = sim(S, DS)
    rr = [sim(S, DS, seed=k) for k in range(NS)]
    wn = sum(1 for x, y in zip(rr, b30) if x[0] > y[0])
    wm = sum(1 for x, y in zip(rr, b30) if x[1] > y[1])
    print("  %-16s%8.2f배%8.1f%%%11.2f배%11.1f%%%7d/%d%7d/%d"
          % (lbl, a, mm, np.median([x[0] for x in rr]), min(x[1] for x in rr), wn, NS, wm, NS))
print("\n총 %.0f초" % (time.time() - t0))
