# -*- coding: utf-8 -*-
"""데이 [갭 하락 조용주] 실행 방법 실측기 (2026-10-14 사용자: "데이 규칙 각 50·100·200·300·500만원 매수·매도하는 걸로
어떤 매수 방법·매도 방법이 좋을지 계속 실측 테스트 — 나중에 금액 올릴 때 바로 적용하게").

실제로 큰돈을 사고팔지 않고, **실제 호가창에 우리 주문을 더해 단일가 균형가격을 다시 계산**한다(녹화기 auction.eq_price).
  기준 = 우리 주문이 없었을 때의 실제 KRX 시가·종가(1분봉). 비용 = 우리 체결가가 기준보다 얼마나 불리한가(%).
  모형 오차 보정: 호가창으로 계산한 '우리 없을 때 균형가'와 '우리 넣었을 때 균형가'의 차이만 실제 가격에 얹는다.
매수(시가 단일가): B1 시장가 · B2 지정가(규칙 지정가 — 균형가가 지정가를 넘으면 못 사거나 일부만)
매도: S1 종가 단일가 시장가(지금) · S2 종가 단일가 하한 지정가(15:19:50 가격 -1%, 못 팔면 그 몫은 체결률로)
      S3 15:00~15:20 나눠 팔기(분당 그 분 거래량의 10% 까지, 1분봉 가격에서 반 호가 손해, 남은 몫은 종가 단일가 시장가)
      S4 반은 나눠 팔기 · 반은 종가 단일가 시장가
대상 = 그날 후보 중 실제 시가가 지정가 이하(규칙대로라면 사졌을 것). 호가 = data/day/book_날짜_am|pm(08:59:30·15:29:30 후보 스냅샷)
       없으면 녹화기 마지막 회차(08:56:15·15:27:20). 결과는 data/day/exec_lab.jsonl 에 쌓고 요약은 data/day/exec_lab.md.
    python day_exec.py 20261013           (그날 1분봉 파일·녹화가 있어야 — 리뷰 16:25 뒤 자동)
    python day_exec.py summary
"""
import json, math, sys
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent
DAY = BASE / "data" / "day"
REC = BASE / "data" / "factory" / "auction"
OUT = DAY / "exec_lab.jsonl"
SIZES = [50, 100, 150, 200, 300, 500]     # 만원 · 150 은 10-21 사용자 추가(지난 날도 다시 돌려 채움)
COST = 0.23
sys.path.insert(0, str(BASE / "research" / "factory"))


def eq_price(P, V, S):
    from auction import eq_price as E
    return E(P, V, S)


def _book(day, part, tickers):
    """{ticker: (P, V, S)} — 후보 스냅샷이 있으면 그것, 없으면 녹화기 마지막 회차."""
    f = DAY / ("book_%s_%s.parquet" % (day, part))
    src = "후보 스냅샷"
    if f.exists():
        D = pd.read_parquet(f)
    else:
        g = REC / ("KR_%s_%s.parquet" % (day, part))
        if not g.exists(): return {}, "없음"
        D = pd.read_parquet(g); D = D[D.tag == D.tag.max()]; src = "녹화기 %s" % D.tag.max()
    D = D[D.ticker.isin(tickers)]
    return {t: (g.price.values.astype(float), g.vol.values.astype(float), g.side.values) for t, g in D.groupby("ticker")}, src


def _matched(P, V, S, p):
    a, b = S == "A", S == "B"
    return V[b & (P >= p)].sum(), V[a & (P <= p)].sum()


ALPHA = 0.5          # 단일가 체결량 중 우리가 '먼저 체결돼 밀어낼 수 있는' 몫 — 시장가·더 높은 지정가는 그 값 지정가보다 우선(10-14 가정)


def walk_m(P, V, S, side, qty, ref, matched, px=None, alpha=ALPHA):
    """단일가 체결량(matched 주)을 반영한 추정: 우리 수량 중 alpha×matched 까지는 같은 값(ref)에서 기존 주문을 밀어내고 체결 →
    가격 그대로. 넘는 몫만 잔량을 먹어 간다(walk). 반환 (평균 체결가, 체결 수량, 호가 밖?)"""
    free = alpha * max(matched or 0, 0)
    if qty <= free: return float(ref), int(qty), False
    p, f, beyond = walk(P, V, S, side, qty - free, ref, px)
    if not f: return (float(ref), int(free), False) if free >= 1 else (np.nan, 0, beyond)
    return float(p), int(free + f), beyond                              # 단일가 — 넘친 몫 때문에 값이 움직이면 전량 그 값


def walk(P, V, S, side, qty, ref, px=None):
    """토스 단일가 호가 = 체결되고 **남은 잔량**만 보인다(매수·매도가 겹치지 않음 · 최우선 매도 = 실제 시가인 날이 많다 — 10-14 확인).
    그래서 균형가 재계산 대신 잔량을 먹어 간다: 매수는 기준가(실제 시가) 이상 매도 잔량을, 매도는 기준가 이하 매수 잔량을
    우리 수량만큼 쌓아 닿는 가격에 전량 체결(단일가라 모두 같은 값). 안 보이는 체결 물량을 무시하니 비용이 **조금 크게(보수적)** 나온다.
    px(지정가)가 있으면 그 값까지만 먹는다 → 일부 체결. 반환 (체결가, 체결 수량, 보이는 호가를 다 먹고도 모자람?)"""
    if side == "B":
        m = (S == "A") & (P >= ref - 1e-9); order = np.argsort(P[m])
        lv, vol = P[m][order], V[m][order]
        if px is not None: keep = lv <= px + 1e-9; lv, vol = lv[keep], vol[keep]
    else:
        m = (S == "B") & (P <= ref + 1e-9); order = np.argsort(-P[m])
        lv, vol = P[m][order], V[m][order]
        if px is not None: keep = lv >= px - 1e-9; lv, vol = lv[keep], vol[keep]
    if not len(lv):
        return (np.nan, 0, True) if px is None else (np.nan, 0, False)
    cum = np.cumsum(vol)
    k = np.searchsorted(cum, qty)
    if k < len(lv): return float(lv[k]), int(qty), False
    if px is not None: return float(lv[-1]), int(cum[-1]), False      # 지정가까지 있는 잔량만큼만
    return float(lv[-1]), int(qty), True                               # 시장가 — 보이는 호가 밖(실제는 더 불리)


def _bars(day):
    f = BASE / "data" / "m1" / "KR" / "day" / ("%s.parquet" % day)
    if not f.exists(): return None
    D = pd.read_parquet(f, columns=["t", "ts", "o", "h", "l", "c", "v"])
    D = D[D.v > 0].sort_values(["t", "ts"])
    D["hm"] = (pd.to_datetime(D.ts, unit="s") + pd.Timedelta(hours=9)).dt.strftime("%H%M")
    return D


def run(day, quiet=False):
    snap = json.loads((DAY / ("snap_%s.json" % day)).read_text(encoding="utf-8"))
    B = _bars(day)
    if B is None:
        print("1분봉 파일 없음 — 건너뜀:", day); return []
    g = B.groupby("t")
    op, cl = g.o.first(), g.c.last()
    cand = [x for x in snap.get("cand") or [] if x.get("t1", True) and x.get("lim") and x["t"] in op.index and op[x["t"]] <= x["lim"]]   # T4(미장 폭락) 후보는 빼고 [갭 하락 조용주]만
    T = [x["t"] for x in cand]
    am, am_src = _book(day, "am", T)
    pm, pm_src = _book(day, "pm", T)
    pxf = REC / ("KR_%s_pmpx.parquet" % day)
    p1520 = pd.read_parquet(pxf).set_index("ticker").price.to_dict() if pxf.exists() else {}
    rows = []
    for x in cand:
        t, lim = x["t"], float(x["lim"]); o, c = float(op[t]), float(cl[t])
        bb = B[(B.t == t) & (B.hm >= "1501") & (B.hm <= "1520")]
        bt = B[B.t == t]
        v_open = float(bt.v.iloc[0]) if len(bt) and bt.hm.iloc[0] == "0901" else 0.0          # 09:01 봉 = 시가 단일가 + 첫 1분
        v_close = float(bt.v.iloc[-1]) if len(bt) and bt.hm.iloc[-1] == "1531" else 0.0       # 15:31 봉 = 종가 단일가 체결량(정확)
        for amt in SIZES:
            q = int(amt * 1e4 // o)
            if q < 1: continue
            r = dict(day=day, t=t, name=x["name"], amt=amt, qty=q, open=o, close=c, lim=lim, book_am=am_src, book_pm=pm_src)
            # ── 매수(시가 단일가) — 기준 = 실제 시가 o
            if t in am:
                P, V, S = am[t]
                for nm, px in (("B1", None), ("B2", lim)):
                    pb, f, beyond = walk_m(P, V, S, "B", q, o, v_open * 0.5, px)          # 시가 봉 절반을 단일가 체결량으로 가정
                    if px is not None and np.isfinite(pb) and pb > px: f = 0
                    r[nm] = dict(price=pb, fill=f / q, cost=(pb / o - 1) * 100 if f else None, beyond=beyond)
                    pc_, fc_, _ = walk(P, V, S, "B", q, o, px)                           # 보수적(잔량만)
                    r[nm]["cost_cons"] = (pc_ / o - 1) * 100 if fc_ else None
                a_, b_ = S == "A", S == "B"
                if a_.any() and b_.any(): r["model_err"] = ((P[a_].min() + P[b_].max()) / 2 / o - 1) * 100   # 호가 가운데 vs 실제 시가
            # ── 매도 — 기준 = 실제 종가 c
            if t in pm:
                P, V, S = pm[t]
                def close_mkt(n):
                    if n <= 0: return c, 1.0, False
                    ps, f, beyond = walk_m(P, V, S, "A", n, c, v_close, None)
                    return (ps if f else np.nan), f / n, beyond
                p1, f1, bz = close_mkt(q)
                r["S1"] = dict(price=p1, fill=f1, cost=(1 - p1 / c) * 100 if f1 else None, beyond=bz)
                pc_, fc_, _ = walk(P, V, S, "A", q, c, None)
                r["S1"]["cost_cons"] = (1 - pc_ / c) * 100 if fc_ else None
                r["v_open"], r["v_close"] = v_open, v_close
                floor = (p1520.get(t) or c) * 0.99
                p2, f2, _ = walk_m(P, V, S, "A", q, c, v_close, floor)
                r["S2"] = dict(price=p2, fill=f2 / q, cost=(1 - p2 / c) * 100 if f2 else None)
                a_, b_ = S == "A", S == "B"
                spr = 0.0
                if a_.any() and b_.any() and P[a_].min() > P[b_].max():
                    spr = (P[a_].min() - P[b_].max()) / ((P[a_].min() + P[b_].max()) / 2) * 100
                for nm, share in (("S3", 1.0), ("S4", 0.5)):
                    n_tw = int(q * share); left = n_tw; got, val = 0, 0.0
                    per = max(1, math.ceil(n_tw / max(len(bb), 1)))
                    for bar in bb.itertuples():
                        if left <= 0: break
                        k = int(min(per, left, bar.v * 0.10))
                        if k <= 0: continue
                        val += k * bar.c * (1 - spr / 200); got += k; left -= k
                    rest = q - got
                    pr, fr, _ = close_mkt(rest)
                    if rest and np.isfinite(pr): val += rest * fr * pr
                    sold = got + (rest * fr if rest else 0)
                    pavg = val / sold if sold else np.nan
                    r[nm] = dict(price=pavg, fill=sold / q, cost=(1 - pavg / c) * 100 if sold else None, twap_share=got / q)
            rows.append(r)
    if rows:
        with open(OUT, "a", encoding="utf-8") as f:
            for r in rows: f.write(json.dumps(r, ensure_ascii=False, default=lambda v: None if (isinstance(v, float) and not np.isfinite(v)) else v) + "\n")
    if not quiet: print("%s: 대상 %d종목 × %d금액 = %d줄 (호가 %s / %s)" % (day, len(cand), len(SIZES), len(rows), am_src, pm_src))
    return rows


def summary(write=True):
    if not OUT.exists(): return "아직 기록 없음"
    L = [json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip()]
    L = list({(r["day"], r["t"], r["amt"]): r for r in L}.values())            # 같은 날 다시 돌린 건 마지막 것
    days = sorted({r["day"] for r in L})
    lines = ["# 데이 실행 방법 실측 (%s~%s · %d일 · %d종목-일)" % (days[0], days[-1], len(days), len({(r["day"], r["t"]) for r in L})), "",
             "비용 = 우리 주문 없을 때의 실제 시가·종가 대비 불리한 정도(%, 클수록 손해). 체결 = 원하는 수량 중 체결 비율. "
             "순수익 = 실제 시가→종가(비용 0.23 뒤) − 매수 비용 − 매도 비용(체결된 몫 기준).", ""]
    errs = [r["model_err"] for r in L if r.get("model_err") is not None]
    if errs: lines.append("호가 모형 정확도: 장전 호가 균형가 vs 실제 시가 평균 절대 %.2f%% (작을수록 계산을 믿을 만함)" % np.mean(np.abs(errs)))
    lines += ["", "| 금액 | 매수 | 매수 비용 | 매수 체결 | 매도 | 매도 비용 | 매도 체결 | 순수익(건당) |", "|---|---|---|---|---|---|---|---|"]
    best = {}
    for amt in SIZES:
        R = [r for r in L if r["amt"] == amt]
        if not R: continue
        for bm in ("B1", "B2"):
            for sm in ("S1", "S2", "S3", "S4"):
                X = [r for r in R if r.get(bm) and r.get(sm) and r[bm].get("cost") is not None and r[sm].get("cost") is not None]
                if not X: continue
                bc = np.mean([r[bm]["cost"] for r in X]); bf = np.mean([r[bm]["fill"] for r in X if r.get(bm)])
                sc = np.nanmean([r[sm]["cost"] for r in X]); sf = np.mean([r[sm]["fill"] for r in X])
                net = np.nanmean([(r["close"] / r["open"] - 1) * 100 - COST - r[bm]["cost"] - (r[sm]["cost"] or 0) for r in X if r[bm]["fill"] > 0])
                lines.append("| %d만 | %s | %+.2f%% | %.0f%% | %s | %+.2f%% | %.0f%% | %+.2f%% |" % (amt, bm, bc, bf * 100, sm, sc, sf * 100, net))
                if bf >= 0.9 and sf >= 0.9 and (amt not in best or net > best[amt][2]): best[amt] = (bm, sm, net)
    for amt in SIZES:
        R = [r for r in L if r["amt"] == amt and r.get("B1") and r.get("S1")]
        cb = [r["B1"].get("cost_cons") for r in R if r["B1"].get("cost_cons") is not None]
        cs = [r["S1"].get("cost_cons") for r in R if r["S1"].get("cost_cons") is not None]
        if cb and cs:
            lines.append("보수적(잔량만, 체결량 밀어내기 없음) %d만: 시가 시장가 %+.2f%% · 종가 시장가 %+.2f%%" % (amt, np.mean(cb), np.mean(cs)))
    names = {"B1": "시가 시장가", "B2": "시가 지정가", "S1": "종가 시장가", "S2": "종가 하한 지정가(-1%)", "S3": "15:00~20 나눠 팔기", "S4": "나눠 팔기 반+종가 반"}
    lines += ["", "**금액별 지금까지 가장 나은 조합(체결 90%↑ 중)**: " + " · ".join("%d만 = %s + %s (%+.2f%%)" % (a, names[b], names[s], n) for a, (b, s, n) in sorted(best.items()))]
    txt = "\n".join(lines)
    if write: (DAY / "exec_lab.md").write_text(txt + "\n", encoding="utf-8")
    return txt


def brief():
    """데이 결과 알림에 붙일 한 줄 — 누적 며칠·100만·500만 원의 매수·매도 비용."""
    if not OUT.exists(): return "실행 방법 실측: 아직 기록 없음"
    L = list({(r["day"], r["t"], r["amt"]): r for r in (json.loads(l) for l in OUT.read_text(encoding="utf-8").splitlines() if l.strip())}.values())
    nd = len({r["day"] for r in L})
    out = []
    for amt in (100, 500):
        R = [r for r in L if r["amt"] == amt]
        m = lambda k, f="cost": np.nanmean([r[k][f] for r in R if r.get(k) and r[k].get(f) is not None]) if R else np.nan
        out.append("%d만 매수 시장가 %+.2f%%·지정가 %+.2f%%(체결 %.0f%%) / 매도 종가 %+.2f%%·나눠 %+.2f%%" % (
            amt, m("B1"), m("B2"), m("B2", "fill") * 100, m("S1"), m("S3")))
    return "🧪 실행 방법 실측(누적 %d일, 비용=불리한 정도): " % nd + " · ".join(out)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "summary": print(summary())
    else:
        for d in a: run(d)
        print(summary())
