# -*- coding: utf-8 -*-
"""유튜브 kjbeDZRTCCI '단타 실수 6가지' (2026-10-07 사용자 링크) — 영상의 '이렇게 쓰면 맞다' 주장을 1분봉으로 잰다.
  ① RSI 다이버전스: 60분봉 상승 다이버전스(가격 저점↓·RSI 저점↑) 단독 vs 다음 봉이 신호 봉 고가를 넘는 '확인' 뒤 진입
  ② 이평 겹침 지지: 5분봉 이평 5·20·60 이 0.3% 안에 모인 자리까지 내려왔다가 그 위로 다시 마감(확인 뒤 진입) vs 이평 20 하나 닿기
  ③ 볼린저: 1분봉 하단 터치+망치형 매수(영상이 말한 '흔한 실수') vs 밴드 넓어지며 상단을 꼬리 없는 장대 양봉으로 뚫을 때 매수(영상의 '제대로')
  ④ 큰 봉 확인: ③ 하단 터치 매수를 60분봉 22이평 기울기 위/아래로 나눔
  ⑤ 수익 50% 지키기 스톱: 위 진입 모두에 '최고 수익의 50% 를 지키는 스톱(수익 난 뒤부터)' vs 장 끝 정리를 나란히
청산 기본: 손절 = 신호 봉 저점 · 장 끝 정리. 비용·표본·판정은 yt_scalp 와 같음(국장 무작위 300 · 미장 대형주 · 같은 봉 손절 우선).
    python research/yt_scalp6.py
"""
import json, sys, time, random
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(BASE))
import yt_scalp as Y
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def exits(o, h, l, c, i, px, stop):
    """(장 끝 정리, 수익 50% 지키기) 두 가지 — 반환 [(이름, 비용 전 %, 미끄러짐 횟수)]."""
    out = []
    r, s = Y.run_trade(o, h, l, c, i, px, stop, None); out.append(("장 끝", r, s))
    st = stop; peak = px
    for j in range(i + 1, len(c)):
        if l[j] <= st:
            out.append(("수익 50% 지키기", (min(st, o[j]) / px - 1) * 100, 1)); return out
        peak = max(peak, h[j])
        if peak > px * 1.002: st = max(st, px + 0.5 * (peak - px))     # 수익 난 뒤부터 최고 수익의 50% 를 지킨다
    out.append(("수익 50% 지키기", (c[-1] / px - 1) * 100, 0)); return out


def agg(g, k):
    n = np.arange(len(g)) // k
    return g.groupby(n).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last")).reset_index(drop=True)


def one(arg):
    mk, f = arg
    try: D = Y.load(mk, f)
    except Exception: return []
    T = []
    days = [(d, g) for d, g in D.groupby("date", sort=True) if len(g) >= 300]
    # 60분봉 연속(이평22·RSI) — 날을 넘겨 이어 계산
    H = pd.concat([agg(g, 60).assign(date=d) for d, g in days], ignore_index=True) if days else None
    if H is None or len(H) < 40: return []
    H["ma22"] = H.c.rolling(22).mean(); H["slope"] = H.ma22 - H.ma22.shift(3); H["rsi"] = Y.rsi(H.c.values)
    hidx = H.groupby("date").apply(lambda z: z.index.values).to_dict()
    for d, g in days:
        o, h, l, c = g.o.values, g.h.values, g.l.values, g.c.values
        hi = hidx.get(d, np.array([], int))
        # ── ④ 60분봉 추세(그날 첫 60분봉이 끝나기 전엔 전날 마지막 기울기) ──
        def slope_at(m):                                      # 1분봉 m 번째 시점에서 끝난 60분봉 기울기
            k = m // 60 - 1
            idx = hi[k] if 0 <= k < len(hi) else (hi[0] - 1 if len(hi) else -1)
            return H.slope.values[idx] if idx >= 0 else np.nan
        # ── ③ 볼린저(1분봉 20·2) ──
        s = pd.Series(c); mid = s.rolling(20).mean().values; sd = s.rolling(20).std().values
        up, dn = mid + 2 * sd, mid - 2 * sd; bw = (up - dn) / mid; bwm = pd.Series(bw).rolling(20).mean().values
        busy = -1
        for i in range(40, len(c) - 1):
            if i <= busy or np.isnan(dn[i]): continue
            body = abs(c[i] - o[i]); rng = h[i] - l[i]
            if l[i] <= dn[i] and c[i] > o[i] and (min(o[i], c[i]) - l[i]) >= 2 * body and rng > 0:
                sl = slope_at(i); tag = "60분 추세 위" if sl > 0 else ("60분 추세 아래" if sl < 0 else "60분 추세 모름")
                for nm, r, k in exits(o, h, l, c, i, c[i], l[i] * 0.999):
                    T.append(("③ 볼린저 하단+망치형 매수(흔한 실수) · %s · %s" % (tag, nm), d, r, 1 + k))
                busy = i + 10
            elif c[i] > up[i] and bw[i] > bwm[i] * 1.2 and c[i] > o[i] and (h[i] - c[i]) <= 0.1 * rng and body >= 0.7 * rng and rng > 0:
                for nm, r, k in exits(o, h, l, c, i, c[i], l[i] * 0.999):
                    T.append(("③ 볼린저 확장+상단 장대양봉 돌파(영상 방식) · %s" % nm, d, r, 1 + k))
                busy = i + 10
        # ── ② 이평 겹침(5분봉) ──
        b = agg(g, 5); bo, bh, bl, bc = b.o.values, b.h.values, b.l.values, b.c.values
        sb = pd.Series(bc); m5, m20, m60 = sb.rolling(5).mean().values, sb.rolling(20).mean().values, sb.rolling(60).mean().values
        busy = -1
        for i in range(60, len(bc) - 1):
            if i <= busy or np.isnan(m60[i]): continue
            hiM, loM = max(m5[i], m20[i], m60[i]), min(m5[i], m20[i], m60[i])
            up_tr = m20[i] > m60[i]
            if up_tr and (hiM - loM) / loM <= 0.003 and bl[i] <= hiM and bc[i] > hiM and bc[i] > bo[i]:
                for nm, r, k in exits(bo, bh, bl, bc, i, bc[i], min(bl[i], loM) * 0.999):
                    T.append(("② 이평 3개 겹친 자리 되찾음(상승 중) · %s" % nm, d, r, 1 + k))
                busy = i + 6
            elif up_tr and bl[i] <= m20[i] and bc[i] > m20[i] and bc[i] > bo[i]:
                for nm, r, k in exits(bo, bh, bl, bc, i, bc[i], bl[i] * 0.999):
                    T.append(("② 이평20 하나 닿고 반등(흔한 실수) · %s" % nm, d, r, 1 + k))
                busy = i + 6
    # ── ① 60분봉 RSI 상승 다이버전스(며칠에 걸침) → 진입 봉 이후 그날 끝 / 수익 50% ──
    hl, hr, hh, hc, hd = H.l.values, H.rsi.values, H.h.values, H.c.values, H.date.values
    dd = dict(days)
    for i in range(30, len(H) - 2):
        w = slice(i - 20, i - 2)
        k = (i - 20) + int(np.argmin(hl[w]))
        if hl[i] < hl[k] and hr[i] > hr[k] and hr[i] < 40 and hl[i] == hl[max(0, i - 3): i + 1].min():
            for lab, j in (("단독(신호 봉 종가 매수)", i), ("확인(다음 봉이 신호 봉 고가 넘김)", i + 1 if hc[i + 1] > hh[i] else None)):
                if j is None or hd[j] != hd[i] and lab.startswith("단독"): continue
                d = hd[j]; g = dd.get(d)
                if g is None: continue
                # 그날 1분봉에서 j 번째 60분봉이 끝난 시점 이후로 청산
                pos = list(hidx[d]).index(j) if j in hidx[d] else None
                if pos is None: continue
                m = (pos + 1) * 60 - 1
                o, h, l, c = g.o.values, g.h.values, g.l.values, g.c.values
                if m >= len(c) - 1: continue
                for nm, r, kk in exits(o, h, l, c, m, c[m], hl[i] * 0.999):
                    T.append(("① 60분 RSI 상승 다이버전스 %s · %s" % (lab, nm), d, r, 1 + kk))
    return [(mk,) + x for x in T]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    done = json.loads((BASE / "data" / "m1" / "backfill_state.json").read_text(encoding="utf-8"))["done"]
    kr = sorted(k.split(":")[1] for k in done if k.startswith("KR:")); random.seed(7); kr = random.sample(kr, 300)
    us = sorted(k.split(":")[1] for k in done if k.startswith("US:"))
    jobs = [("KR", BASE / "data/m1/KR/bf" / (s + ".parquet")) for s in kr] + [("US", BASE / "data/m1/US/bf" / (s + ".parquet")) for s in us]
    jobs = [j for j in jobs if j[1].exists()]
    rows = []
    with ProcessPoolExecutor(6) as ex:
        for i, r in enumerate(ex.map(one, jobs, chunksize=2)):
            rows += r
            if (i + 1) % 100 == 0: print("  %d/%d · %.1f분" % (i + 1, len(jobs), (time.time() - t0) / 60), flush=True)
    R = pd.DataFrame(rows, columns=["mk", "s", "date", "raw", "nslip"])
    R.to_pickle(ROOT / "cache" / "yt_scalp6.pkl")
    P("# 유튜브 '단타 실수 6가지' 실측(1분봉) · %s" % time.strftime("%Y-%m-%d")); P("")
    P("- 국장 무작위 %d종목 · 미장 대형주 %d종목 · 비용 뒤(국장 0.23%%+미끄러짐 0.05%% · 미장 0.20%%+0.02%%) · 같은 봉 손절 우선" % (
        len([j for j in jobs if j[0] == "KR"]), len([j for j in jobs if j[0] == "US"]))); P("")
    for mk in ("KR", "US"):
        Z = R[R.mk == mk].copy()
        if Z.empty: continue
        fee, sl = Y.COST[mk]; Z["ret"] = Z.raw - fee - sl * Z.nslip
        P("## %s" % ("국장" if mk == "KR" else "미장")); P("")
        P("| 진입 · 청산 | 건수 | 비용 전 평균 | 학습 ~24: 평균·승률 | 검증 25~: 평균·승률 | 해마다(23·24·25·26) |"); P("|---|---|---|---|---|---|")
        for s, z in Z.groupby("s", sort=True):
            cell = []
            for a, b in (("20221201", "20241231"), ("20250101", "20991231")):
                y = z[(z.date >= a) & (z.date <= b)]
                cell.append("%d건 %+.3f%% · %.0f%%" % (len(y), y.ret.mean(), (y.ret > 0).mean() * 100) if len(y) else "-")
            yr = z.groupby(z.date.str[:4]).ret.mean(); yr = yr[yr.index >= "2023"]
            P("| %s | %d | %+.3f%% | %s | %s | %s |" % (s, len(z), z.raw.mean(), cell[0], cell[1], " ".join("%+.2f" % v for v in yr.values)))
        P("")
    P("(%.1f분)" % ((time.time() - t0) / 60))
    from verdict import log_trials
    log_trials("yt_scalp6_%s" % time.strftime("%Y%m%d"), int(R.groupby(["mk", "s"]).ngroups))
    (ROOT / "reports" / ("yt_scalp6_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
