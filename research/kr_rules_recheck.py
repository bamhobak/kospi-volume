# -*- coding: utf-8 -*-
"""국장 규칙 다시 실측 — 규칙 성적 + 같은 보유기간 지수(코스피/코스닥) 견줌 (2026-10-07 사용자 "국장 규칙들도 다시 체크, 있으나 마나한 거 조이거나 정리").
거래 목록 = stats_2016.py 의 take()(portfolio.py 규칙 정의·트레일링·손절 반영 · 패널 cost 0.23% 세율 반영판 · 폐지 포함).
지수 = 같은 매수일(신호 다음날) 시가 → 같은 매도일(신호일 + 보유일) 종가 · 코스피 규칙은 KOSPI, 코스닥 규칙은 KOSDAQ, 공통 규칙은 그 종목 시장 지수.
  ⚠ 트레일링·손절로 일찍 나간 거래도 지수는 보유일 끝까지로 잰다(규칙 쪽이 실제로 쓴 기간보다 길게 잡힘 — 근사).
기간: 스트레스 2005~15 · 학습 2016~22 · 검증 2023~.
    python research/kr_rules_recheck.py
"""
import io, os, re, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
import requests

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path.insert(0, str(BASE))
src = (BASE / "stats_2016.py").read_text(encoding="utf-8")
src = src.split("OUT = {}")[0]
ns = {"__file__": str(BASE / "stats_2016.py")}
real = sys.stdout
sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
exec(compile(src, "stats_2016.py", "exec"), ns)
sys.stdout = real; sys.stdout.reconfigure(encoding="utf-8")
take, RULES, NAME, DISP, ORDER = ns["take"], ns["RULES"], ns["NAME"], ns["DISP"], ns["ORDER"]
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))
t0 = time.time()


def idx(sym):
    u = ("https://api.finance.naver.com/siseJson.naver?symbol=%s&requestType=1&startTime=20040101&endTime=%s&timeframe=day"
         % (sym, time.strftime("%Y%m%d")))
    r = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"})
    rows = re.findall(r'\["(\d{8})",\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)', r.text)
    return {d: (float(o), float(c)) for d, o, h, l, c in rows if float(c) > 0}


IX = {"KOSPI": idx("KOSPI"), "KOSDAQ": idx("KOSDAQ")}
PER = (("스트레스 2005~15", "20050101", "20151231"), ("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))
P("# 국장 규칙 다시 실측 — 규칙 성적 + 같은 보유기간 지수 · %s" % time.strftime("%Y-%m-%d")); P("")
P("- portfolio.py 규칙 정의 · 폐지 포함 패널 · 비용 0.23%+미끄러짐(패널 cost) · 신호 나면 다 산다 · 지수 = 같은 매수일 시가→보유일 끝 종가"); P("")
P("| 규칙(화면) | 보유 | 기간 | 건수 | 평균 | 중앙 | 승률 | 같은 기간 지수 | 초과 평균 | 지수 이긴 비율 |"); P("|---|---|---|---|---|---|---|---|---|---|")
ALL = {}
for rid in ORDER:
    Z, hold, stop = take(rid)
    K = RULES[rid][0]
    ud = np.array(sorted(K.date.unique()))
    mk = "KOSDAQ" if rid.startswith("D") else None
    rows = []
    mkcol = Z["mk"].values if "mk" in Z.columns else np.array(["KOSPI"] * len(Z))
    for dt_, tk_, rr_, di_, mk_ in zip(Z.date.values, Z.ticker.values, Z._r.values, Z.di.values, mkcol):
        i = int(di_)
        if i + hold >= len(ud): continue
        d_in, d_out = ud[i + 1], ud[i + hold]
        m = mk or ("KOSDAQ" if mk_ == "KOSDAQ" else "KOSPI")
        a, b = IX[m].get(d_in), IX[m].get(d_out)
        ir = (b[1] / a[0] - 1) * 100 if a and b else np.nan
        rows.append((dt_, tk_, rr_, ir))
    T = pd.DataFrame(rows, columns=["date", "ticker", "ret", "idx"]); ALL[rid] = (T, hold)
    lab = "[%s](%s)" % (NAME[rid], DISP[rid])
    for pn, lo, hi in PER:
        z = T[(T.date >= lo) & (T.date <= hi)]
        if not len(z): P("| %s | %d일 | %s | 0 | | | | | | |" % (lab, hold, pn)); continue
        zi = z.dropna(subset=["idx"])
        P("| %s | %d일 | %s | %d | %+.2f%% | %+.2f%% | %.0f%% | %+.2f%% | **%+.2f%%p** | %.0f%% |" % (
            lab, hold, pn, len(z), z.ret.mean(), z.ret.median(), (z.ret > 0).mean() * 100, zi.idx.mean(), (zi.ret - zi.idx).mean(), (zi.ret > zi.idx).mean() * 100))
P("")
P("## 해마다(2016~) — 규칙 평균 / 같은 기간 지수 (건수)"); P("")
yrs = [str(y) for y in range(2016, 2027)]
P("| 규칙 | " + " | ".join(yrs) + " |"); P("|---|" + "---|" * len(yrs))
for rid in ORDER:
    T, _ = ALL[rid]; z = T[T.date >= "20160101"].dropna(subset=["idx"]); g = z.groupby(z.date.str[:4])
    P("| [%s] | %s |" % (NAME[rid], " | ".join(("%+.1f / %+.1f (%d)" % (g.get_group(y).ret.mean(), g.get_group(y).idx.mean(), len(g.get_group(y)))) if y in g.groups else "-" for y in yrs)))
P(""); P("(%.1f분)" % ((time.time() - t0) / 60))
pd.to_pickle(ALL, ROOT / "cache" / "kr_rules_recheck.pkl")
(ROOT / "reports" / ("kr_rules_recheck_%s.md" % time.strftime("%Y%m%d"))).write_text("\n".join(OUT) + "\n", encoding="utf-8")
