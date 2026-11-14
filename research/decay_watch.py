# -*- coding: utf-8 -*-
"""규칙 효율화 감시 — 2026-11-14 사용자 "다른 사람도 AI 로 같은 규칙을 찾으면 데이 규칙 이득이 약해질 텐데" → "응 다 해줘".
데이 규칙마다 '연구 정의' 날 바구니(그날 신호 종목 평균, 비용 뒤)를 매일 이어 붙이고,
최근 W 신호일 평균이 과거 같은 길이 구간들 가운데 몇 % 자리인지 본다.
  정상 ≥ 25% · 주의 < 25% · 경고 < 10%.  텔레그램(핵심만): 경고가 된 날 · 주의가 10신호일 넘게 이어질 때 · 알린 뒤 정상으로 돌아올 때.
금액 자동 축소는 안 함(지금 1주 시험 · 실금액 전환 때 사용자와 정함) — 알림·보고서만.
규칙과 자료:
  [갭하락]       research/cache/factory_kr.pkl(공장 재료, 매일 밤 다시 만듦) — 연구판 rgap ≤ -1.5 · 갭 하위 40% · 거래량 하위 30% · 크기 ≤ 2/3 · 시가→종가, 2016~
  [장전 되돌림]  과거 = data/decay/base_T5.csv(t5_full_panel_1114 · 순위 4 · 신호 10개↑ 날 쉼 · VWAP 기준) + 매일 = data/nxtpre/log.csv '고름'=1 의 'VWAP 기준 수익'
  [장후 낙폭]    과거 = data/decay/base_T6.csv(nxt_full0_panel · 장후 -2.5%↓ · 낮 ±1% 빼기 · 19:51~20:00 VWAP→다음 날 시가) + 매일 = data/nxt/log.csv grp=picks 'r_vwap'
    python research/decay_watch.py            (매일 17:40 예약 \\BamhobakFactory\\DecayWatch)
    python research/decay_watch.py --build    (과거 바구니 base_T5·base_T6 한 번 만들기)
    python research/decay_watch.py --quiet    (텔레그램 없이)"""
import json, sys, time
from pathlib import Path
import numpy as np, pandas as pd
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "decay"; OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "run.log"
if sys.stdout is not None:
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
W = {"T1": 60, "T5": 40, "T6": 60}
NAME = {"T1": "갭하락", "T5": "장전 되돌림", "T6": "장후 낙폭"}
WARN, CAUT, CAUT_RUN = 0.10, 0.25, 10
COST = 0.23


def log(*a):
    s = time.strftime("%m-%d %H:%M:%S ") + " ".join(str(x) for x in a)
    try:
        with open(LOG, "a", encoding="utf-8") as f: f.write(s + "\n")
    except Exception: pass
    if sys.stdout is not None:
        try: print(s, flush=True)
        except Exception: pass


def build():
    Z = pd.read_pickle(r"C:\temp\kp\nxt_full0_panel.pkl")
    T6 = Z[(Z.AH50 <= -2.5) & ~((Z.dayr.abs() <= 1.0).fillna(False))].dropna(subset=["g_vw"])
    b6 = T6.groupby(T6.d.astype(str)).g_vw.mean().rename("r"); b6.index.name = "date"; b6.to_csv(OUT / "base_T6.csv")
    S = pd.read_pickle(r"C:\temp\kp\t5_full_panel_1114.pkl")
    m = (S.rpre <= -3) & (S.cum <= 1_019_060_000) & S.r_vwhs.notna()
    X = S[m].copy(); X["rk"] = X.groupby("d").rpre.rank(method="first"); X["ns"] = X.groupby("d").rpre.transform("size")
    X = X[(X.rk <= 4) & (X.ns < 10)]
    b5 = X.groupby(X.d.astype(str)).r_vwhs.mean().rename("r"); b5.index.name = "date"; b5.to_csv(OUT / "base_T5.csv")
    log("과거 바구니 만듦 — T6 %d날(%s~%s) · T5 %d날(%s~%s)" % (len(b6), b6.index.min(), b6.index.max(), len(b5), b5.index.min(), b5.index.max()))


def series():
    S = {}
    U = pd.read_pickle(BASE / "research" / "cache" / "factory_kr.pkl")
    m = (U.rgap <= -1.5) & (U.q_gap <= 0.40) & (U.q_vm.fillna(1) <= 0.30) & (U.liq <= 2 / 3) & U.oc.notna()
    S["T1"] = (U.loc[m, "oc"].clip(-60, 60) - COST).groupby(U.loc[m, "date"].astype(str)).mean()
    del U
    for rid, f, live in (("T5", "base_T5.csv", None), ("T6", "base_T6.csv", None)):
        b = pd.read_csv(OUT / f, dtype={"date": str}).set_index("date").r
        if rid == "T5":
            L = pd.read_csv(BASE / "data" / "nxtpre" / "log.csv", encoding="utf-8-sig", dtype={"날짜": str})
            L = L[(pd.to_numeric(L["고름"], errors="coerce") == 1)]
            cur = pd.to_numeric(L["VWAP 기준 수익"], errors="coerce").groupby(L["날짜"]).mean().dropna()
        else:
            L = pd.read_csv(BASE / "data" / "nxt" / "log.csv", encoding="utf-8-sig", dtype={"pick_day": str})
            L = L[L.grp == "picks"]
            cur = pd.to_numeric(L.r_vwap, errors="coerce").groupby(L.pick_day).mean().dropna()
        S[rid] = pd.concat([b[b.index < (cur.index.min() if len(cur) else "99999999")], cur]).sort_index()
    return S


def judge(s, w):
    s = s.dropna()
    if len(s) < w * 3: return None
    cur = float(s.iloc[-w:].mean())
    hist = s.iloc[:-w].rolling(w).mean().dropna()
    pct = float((hist < cur).mean())
    st = "경고" if pct < WARN else "주의" if pct < CAUT else "정상"
    return dict(cur=cur, pct=pct, st=st, last=s.index[-1], first=s.index[-w], allmean=float(s.mean()), n=len(s),
                p25=float(hist.quantile(0.25)), p50=float(hist.quantile(0.5)))


def main():
    if "--build" in sys.argv: build(); return
    quiet = "--quiet" in sys.argv
    S = series()
    sf = OUT / "state.json"
    st0 = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
    rows, msgs, st1 = [], [], {}
    for rid, s in S.items():
        R = judge(s, W[rid])
        if R is None: log(rid, "자료 부족"); continue
        p = st0.get(rid, {})
        run = (p.get("run", 0) + 1) if R["st"] != "정상" and p.get("last") != R["last"] else (p.get("run", 0) if R["st"] != "정상" else 0)
        alerted = p.get("alerted", False)
        nm = NAME[rid]
        line = "[%s] 최근 %d신호일 %+.2f%% · 과거 %.0f%% 자리" % (nm, W[rid], R["cur"], R["pct"] * 100)
        if R["st"] == "경고" and p.get("st") != "경고":
            msgs.append("📉 " + line + " — 경고"); alerted = True
        elif R["st"] == "주의" and run >= CAUT_RUN and not alerted:
            msgs.append("📉 " + line + " — 주의 %d신호일째" % run); alerted = True
        elif R["st"] == "정상" and alerted:
            msgs.append("📈 " + line + " — 정상 복귀"); alerted = False
        st1[rid] = dict(st=R["st"], run=run, alerted=alerted, last=R["last"], pct=R["pct"], cur=R["cur"])
        rows.append((rid, R))
        with open(OUT / "history.csv", "a", encoding="utf-8") as f:
            f.write("%s,%s,%s,%.4f,%.4f,%s,%d\n" % (time.strftime("%Y%m%d"), rid, R["last"], R["cur"], R["pct"], R["st"], run))
    sf.write_text(json.dumps(st1, ensure_ascii=False, indent=1), encoding="utf-8")
    md = ["# 규칙 효율화 감시 (%s)" % time.strftime("%Y-%m-%d %H:%M"), "",
          "연구 정의 날 바구니(비용 뒤) · 최근 구간 평균이 과거 같은 길이 구간들 가운데 몇 % 자리인가 · 정상 ≥25% · 주의 <25% · 경고 <10%", "",
          "| 규칙 | 최근 구간 | 최근 평균 | 과거 구간 중앙 · 하위 25% 선 | 자리 | 상태 | 주의 이어진 신호일 |", "|---|---|---|---|---|---|---|"]
    for rid, R in rows:
        md.append("| [%s] | %s~%s (%d신호일) | %+.2f%% | %+.2f%% · %+.2f%% | %.0f%% | %s | %d |" % (NAME[rid], R["first"], R["last"], W[rid], R["cur"], R["p50"], R["p25"],
                  R["pct"] * 100, R["st"], st1[rid]["run"]))
    (BASE / "research" / "reports" / "decay_watch.md").write_text("\n".join(md), encoding="utf-8")
    log("감시 끝 — " + " · ".join("%s %s(%.0f%%)" % (NAME[r], R["st"], R["pct"] * 100) for r, R in rows))
    if msgs and not quiet:
        try:
            sys.path.insert(0, str(BASE)); import day_alert as D
            D.telegram("🔍 효율화 감시\n" + "\n".join(msgs))
        except Exception as ex: log("텔레그램 실패", repr(ex)[:150])


if __name__ == "__main__":
    try: main()
    except Exception as ex:
        import traceback; log("오류", traceback.format_exc()[-800:]); raise
