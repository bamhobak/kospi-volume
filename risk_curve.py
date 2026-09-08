# -*- coding: utf-8 -*-
"""내가 리스크 곡선 어디에 있는가 — 이 시스템을 들고 살면 실제로 뭘 견뎌야 하는가.

유튜브 마음가짐 영상(x1A-FOI5GRY, 차마스 팔리하피티야 7원칙) 세 번째 원칙:
"내가 리스크 곡선 어디에 있는지도 모른다면 그곳에 있으면 안 된다."
우리는 '낙폭 -17.8% · 샤프 1.71' 같은 **요약**은 갖고 있지만, 실제로 겪을 **경험**은
재본 적이 없다. 요약은 견딜 수 있는지를 알려주지 않는다. 아래를 숫자로 낸다.

  ① 최악의 낙폭 — 얼마나 깊고, **얼마나 오래** 물려 있었나(회복까지)
  ② 제자리 구간 — 새 고점을 못 넘고 지나간 가장 긴 기간
  ③ 연속 손실 — 몇 달 연속으로 잃어봤나
  ④ 한 종목 최악 — 개별 거래에서 최대 얼마를 잃나 (그리고 그게 계좌에 얼마인가)
  ⑤ 최악의 해 · 연도별 성적 — '나쁜 해' 가 어느 정도인가
  ⑥ 신호 가뭄 — 아무것도 안 사고 지나간 가장 긴 기간(그때 뭘 하고 있어야 하나)
  ⑦ 시드별 편차 — 같은 규칙인데 운에 따라 결과가 얼마나 갈리나
  ⑧ **일어날 수 있었던 일** — 시드 24개는 어떤 신호를 담느냐만 다르고 시장이 흘러온
     순서는 전부 같다(2005~26 의 역사는 하나뿐이다). 월 블록 재추출로 경로를 다시 만들어
     '낙폭이 여기까지 갈 수도 있었다' 를 낸다(verdict.path_report).

판단이 아니라 **각오할 목록**을 만드는 게 목적이다.
"""
import io, sys, warnings
warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from pathlib import Path
import numpy as np, pandas as pd
import verdict

BASE = Path(__file__).parent
SEEDS = 24
src = (BASE / "portfolio.py").read_text(encoding="utf-8")
ns = {"__file__": str(BASE / "portfolio.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src.split("# 신호를 한 표로 모은다")[0], "portfolio.py", "exec"), ns)
sys.stdout = real
KP, KQ, RULES, TRAIL = ns["KP"], ns["KQ"], ns["RULES"], ns["TRAIL"]
NAME = {"P1": "조용한 신고가", "P2": "조정매집", "P3": "폭락반등", "P4": "업종붕괴 이탈",
        "P5": "자사주 낙폭", "P6": "깊은 이격", "P7": "외인 매집",
        "D1": "낙폭과대", "D2": "저PBR 낙폭"}
adates = sorted(set(KP.date) | set(KQ.date))
ADI = {d: i for i, d in enumerate(adates)}


def signals():
    out = []
    for rid, (K, hold, stop, pct, mx, cond) in RULES.items():
        g = K.groupby("ticker", sort=False)
        C = np.column_stack([g.close.shift(-i).values for i in range(1, hold + 1)])
        buy = K.buy.values
        t = TRAIL.get(rid)
        hit = np.zeros_like(C, dtype=bool); px = C.copy()
        if t:
            run = np.maximum.accumulate(np.column_stack([buy, C]), axis=1)[:, 1:]
            h = C <= run * (1 - t); hit |= h
            px = np.where(h & ~np.isnan(C), run * (1 - t), px)
        elif stop:
            h = C <= buy[:, None] * (1 - stop); hit |= h
            px = np.where(h, buy[:, None] * (1 - stop), px)
        ok = hit.any(axis=1)
        first = np.where(ok, hit.argmax(axis=1), hold - 1)
        exit_px = np.where(ok, px[np.arange(len(C)), first], C[:, -1])
        m = cond.fillna(False).values
        X = K[m].copy()
        X["exit"] = exit_px[m]; X["hold"] = (first + 1)[m]
        X["rid"] = rid; X["pct"] = pct; X["mx"] = mx
        X["ret"] = (X.exit / X.buy - 1) * 100 - X.cost
        X = X.dropna(subset=["ret"])
        X = X[X.buy > 0]
        out.append(X[["date", "ticker", "name", "hold", "rid", "pct", "mx", "ret"]])
    S = pd.concat(out, ignore_index=True)
    S["di"] = S.date.map(ADI)
    return S.dropna(subset=["di"]).sort_values("di").reset_index(drop=True)


S = signals()


def run(ds, seed):
    """계좌 곡선과 체결 내역을 함께 돌려준다."""
    rng = np.random.default_rng(seed)
    nav, held, cnt = 1.0, {}, {}
    byd = {d: g for d, g in S[S.date.isin(set(ds))].groupby("date")}
    curve, trades = [], []
    for d in ds:
        di = ADI[d]
        for k in [k for k, v in held.items() if v[0] <= di]:
            v = held.pop(k)
            nav *= 1 + v[1] / 100
            cnt[k[0]] = cnt.get(k[0], 0) - 1
            trades.append((d, k[0], k[1], v[2], v[1]))     # 청산일·규칙·종목·건별수익·계좌기여
        curve.append((d, nav, len(held)))
        g = byd.get(d)
        if g is None:
            continue
        for r in g.sample(frac=1, random_state=int(rng.integers(1 << 30))).itertuples():
            if cnt.get(r.rid, 0) >= r.mx:
                continue
            k = (r.rid, r.ticker, d)
            if k in held:
                continue
            held[k] = (di + int(r.hold), r.ret * r.pct / 100, r.ret)
            cnt[r.rid] = cnt.get(r.rid, 0) + 1
    C = pd.DataFrame(curve, columns=["date", "nav", "n"])
    T = pd.DataFrame(trades, columns=["date", "rid", "ticker", "ret", "contrib"])
    return C, T


PER = (("전구간 2005~26", "20050101"), ("2016~26", "20160101"))
for lab, lo in PER:
    ds = [d for d in adates if d >= lo]
    print("=" * 104)
    print(f"[{lab}] 시드 {SEEDS}개 · 이 시스템을 들고 살면 실제로 겪는 것")
    print("=" * 104)
    CS, TS = [], []
    for k in range(SEEDS):
        C, T = run(ds, k)
        CS.append(C); TS.append(T)

    # ① 최악의 낙폭과 지속
    rows = []
    for C in CS:
        v = C.nav.values
        pk = np.maximum.accumulate(v)
        dd = v / pk - 1
        i = int(dd.argmin())
        # 그 낙폭이 시작된 고점과, 회복까지 걸린 거래일
        st = int(np.where(v[:i + 1] == pk[i])[0][-1])
        rec = np.where(v[i:] >= pk[i])[0]
        rows.append((dd[i] * 100, C.date.iloc[st], C.date.iloc[i],
                     int(rec[0]) if len(rec) else None, i - st))
    D = pd.DataFrame(rows, columns=["dd", "peak", "bottom", "rec", "fall"])
    med = D.dd.median()
    w = D.loc[D.dd.idxmin()]
    print(f"\n① 최악의 낙폭  중앙 {med:.1f}% · 최악 시드 {D.dd.min():.1f}%")
    print(f"   가장 나빴던 경우: {w.peak} 고점 → {w.bottom} 바닥 ({int(w.fall)}거래일 하락) · "
          + (f"회복까지 {int(w.rec)}거래일(약 {int(w.rec)/250:.1f}년)" if w.rec else "기간 내 미회복"))
    print(f"   낙폭 -10% 이상을 겪은 시드 {(D.dd <= -10).sum()}/{SEEDS} · "
          f"-15% 이상 {(D.dd <= -15).sum()}/{SEEDS} · -20% 이상 {(D.dd <= -20).sum()}/{SEEDS}")

    # ② 제자리 구간 — 새 고점을 못 넘고 지나간 최장 기간
    flat = []
    for C in CS:
        v = C.nav.values
        pk = np.maximum.accumulate(v)
        under = v < pk
        best, cur, bi, bs = 0, 0, 0, 0
        for i, u in enumerate(under):
            if u:
                cur += 1
                if cur > best:
                    best, bi, bs = cur, i, i - cur + 1
            else:
                cur = 0
        flat.append((best, C.date.iloc[bs], C.date.iloc[bi]))
    F = pd.DataFrame(flat, columns=["days", "from", "to"])
    fw = F.loc[F.days.idxmax()]
    print(f"\n② 제자리 구간  새 고점을 못 넘고 지나간 최장: 중앙 {F.days.median():.0f}거래일"
          f"(약 {F.days.median()/250:.1f}년) · 최악 {F.days.max()}거래일({F.days.max()/250:.1f}년)")
    print(f"   가장 길었던 경우: {fw['from']} ~ {fw['to']}")

    # ③ 연속 손실 개월
    streaks = []
    for C in CS:
        M = C.assign(m=C.date.str[:6]).groupby("m").nav.last()
        r = M.pct_change().dropna()
        best, cur = 0, 0
        for x in r:
            cur = cur + 1 if x < 0 else 0
            best = max(best, cur)
        streaks.append((best, (r < 0).mean() * 100, r.min() * 100))
    ST = pd.DataFrame(streaks, columns=["run", "loss_rate", "worst_m"])
    print(f"\n③ 연속 손실  최장 {ST.run.median():.0f}개월 연속(최악 {ST.run.max()}개월) · "
          f"지는 달 비율 {ST.loss_rate.median():.0f}% · 최악의 달 {ST.worst_m.median():.1f}%")

    # ④ 한 종목 최악
    T = pd.concat(TS)
    bad = T.nsmallest(8, "ret")
    print(f"\n④ 한 종목 최악  건별 최악 {T.ret.min():.1f}% · 하위 1% {T.ret.quantile(0.01):.1f}% · "
          f"지는 거래 비율 {(T.ret < 0).mean()*100:.0f}%")
    print(f"   계좌에 미친 타격(비중 반영) 최악 {T.contrib.min():.2f}% · "
          f"-2% 이상 때린 거래 {(T.contrib <= -2).sum()/SEEDS:.0f}건/시드")
    print("   최악 사례: " + " · ".join(
        f"{r.date[:6]} {NAME[r.rid]} {r.ret:.0f}%" for r in bad.head(4).itertuples()))

    # ⑤ 연도별
    print("\n⑤ 연도별 (시드 중앙값, %)")
    YS = []
    for C in CS:
        Y = C.assign(y=C.date.str[:4]).groupby("y").nav.last()
        YS.append((Y / Y.shift(1).fillna(1.0) - 1) * 100)
    Y = pd.concat(YS, axis=1).median(axis=1)
    print("   " + "  ".join(f"{i}:{v:+.0f}" for i, v in Y.items()))
    print(f"   지는 해 {int((Y < 0).sum())}/{len(Y)}개 · 최악 {Y.min():+.0f}% ({Y.idxmin()}) · "
          f"중앙 {Y.median():+.0f}%")

    # ⑥ 신호 가뭄 — 아무것도 안 들고 있던 최장 기간
    dry = []
    for C in CS:
        z = (C.n == 0).values
        best, cur, bi = 0, 0, 0
        for i, u in enumerate(z):
            cur = cur + 1 if u else 0
            if cur > best:
                best, bi = cur, i
        dry.append((best, C.date.iloc[bi], (C.n == 0).mean() * 100, C.n.mean()))
    DR = pd.DataFrame(dry, columns=["days", "at", "empty_rate", "avg_n"])
    print(f"\n⑥ 빈 계좌  아무것도 안 들고 있던 최장 {DR.days.median():.0f}거래일"
          f"(최악 {DR.days.max()}일, {DR.loc[DR.days.idxmax(),'at']} 무렵) · "
          f"빈 날 비율 {DR.empty_rate.median():.0f}% · 평균 보유 {DR.avg_n.median():.1f}종목")

    # ⑦ 시드 편차 — 운의 폭
    fin = np.array([C.nav.iloc[-1] for C in CS])
    print(f"\n⑦ 운의 폭  같은 규칙인데 시드에 따라 {fin.min():.2f}배 ~ {fin.max():.2f}배 "
          f"(중앙 {np.median(fin):.2f}배) · 최고/최저 {fin.max()/fin.min():.1f}배 차이")

    # ⑧ 일어날 수 있었던 일 — 월 블록 재추출로 경로를 다시 만든다.
    # 시드 중앙값 경로의 월 수익률을 재료로 쓴다. 낱개 거래가 아니라 **월** 단위로 뽑아야
    # 폭락장에서 아홉 규칙이 한꺼번에 지는 동시성이 유지된다(verdict.block_paths 주석 참고).
    mid = int(np.argsort(fin)[len(fin) // 2])
    Cm = CS[mid]
    M = Cm.assign(m=Cm.date.str[:6]).groupby("m").nav.last()
    mr = M.pct_change().dropna() * 100
    v = Cm.nav.values
    pk = np.maximum.accumulate(v)
    a_mdd = float((v / pk - 1).min() * 100)
    b = c = 0
    for u in (v < pk):
        c = c + 1 if u else 0
        b = max(b, c)
    verdict.path_report(mr, f"{lab} · 일어날 수 있었던 경로",
                        actual=dict(mdd=a_mdd, under=b / 21))   # 거래일 → 개월
    print()
