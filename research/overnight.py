# -*- coding: utf-8 -*-
"""**하룻밤 보유** — 오늘 종가(동시호가)에 사서 다음날 시가에 판다 (2026-09-26, 외국 기법 후속 ①).

run_spec 은 '다음날 시가 매수 · 최소 5일' 만 잰다. 외국 자료 중 숫자가 제일 좋았던 건 전부 하룻밤짜리였다:
  · 일본 寄り底大陽線(systemtrade-kabu 25년 전수): 시가=저가 & +10% 이상 마감 → 종가 매수·익일 시가 매도 +3.66%·승률 54%
    (같은 날 시가→종가는 -0.81% — 낮 동안의 추격은 지고, 밤사이 갭만 먹는다)
  · 인도 Open=Low BTST(TradingQnA): 시가=저가 & 양봉 → 종가 매수·다음날 매도
  · 인도네시아 BSJP(Stockbit): 장중 +10%·고가권 마감·거래대금 2배 → 오후 매수·아침 매도
패널 두 개에 오늘 종가와 다음날 시가(buy)가 다 있어서 바로 잴 수 있다.

수익: 밤 = 다음날 시가 ÷ 오늘 종가 − 1 · 하루 = 다음날 종가 ÷ 오늘 종가 − 1(참고)
비용: 패널의 왕복 비용(국내 거래세 0.15%+슬리피지, 미장 슬리피지) 그대로 — 종가 동시호가 체결은 시가보다 덜 밀리므로 보수적.
유니버스: 거래대금 상위 40%(run_spec 과 같다) · 국내 주가 1,000원↑ · 미장 $3↑.
⚠ 국내 상한가 종가 매수는 매도 잔량이 없어 **체결이 안 될 수 있다** — 성적이 좋아도 실행 가능성은 따로 봐야 한다.

    python research/overnight.py KR
    python research/overnight.py US
"""
import sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import log_trials, boot_ci

OUT = []


def P(x=""):
    OUT.append(x)


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def stats(z):
    if len(z) < 30:
        return None
    net = z.ovn
    yr = z.groupby(z.date.str[:4]).ovn.mean()
    ym = z.groupby(z.date.str[:6]).ovn.mean()
    return dict(n=len(z), g=z.ov.mean(), gm=z.ov.median(), m=net.mean(), md=net.median(), win=(net > 0).mean() * 100,
                d1=z.d1n.mean(), pos=int((yr > 0).sum()), ny=len(yr),
                ci=boot_ci(ym) if len(ym) >= 12 else np.nan)


def row(lbl, s):
    if not s:
        return "| %s | 표본 부족 | | | | | | | | |" % lbl
    return "| %s | %s | %+.2f | %+.2f | **%+.2f** | %+.2f | %.0f%% | %+.2f | %d/%d | %s |" % (
        lbl, f"{s['n']:,}", s["g"], s["gm"], s["m"], s["md"], s["win"], s["d1"], s["pos"], s["ny"],
        ("%+.2f" % s["ci"]) if s["ci"] == s["ci"] else "-")


def main():
    sys.stdout.reconfigure(encoding="utf-8"); t0 = time.time()
    mk = (sys.argv[1] if len(sys.argv) > 1 else "KR").upper()
    log("%s 패널" % mk)
    A, uni, since = R.load_market(mk)
    g = A.groupby("ticker", sort=False)
    pc = g.close.shift(1)
    A["r1"] = (A.close / pc - 1) * 100
    A["pos"] = (A.close - A.low) / (A.high - A.low + 1e-9)
    A["ov"] = (A.buy / A.close - 1) * 100                           # buy = 다음날 시가(매수 불가일은 결측)
    A["ovn"] = A.ov - A.cost
    nc = g.close.shift(-1)
    A["d1n"] = (nc / A.close - 1) * 100 - A.cost
    A.loc[A.buy.isna(), "d1n"] = np.nan
    A["amt"] = A.close * A.volume
    A["ma10"] = g.close.transform(lambda s: s.rolling(10).mean()); A["ma20"] = g.close.transform(lambda s: s.rolling(20).mean())
    A["ma200"] = g.close.transform(lambda s: s.rolling(200).mean())
    A["amtav"] = A.amt.groupby(A.ticker, sort=False).transform(lambda s: s.shift(1).rolling(20).mean())
    lim = 29 if mk == "KR" else 20
    OL = A.low >= A.open * 0.998                                    # 시가=저가(호가 단위 여유 0.2%)
    C = {
        "기준: 유니버스 전체 밤": pd.Series(True, index=A.index),
        "寄り底大陽線 시가=저가 & +10%↑": OL & (A.r1 >= 10),
        "  └ +7%↑": OL & (A.r1 >= 7),
        "  └ +15%↑": OL & (A.r1 >= 15),
        "  └ +10%↑ 인데 시가=저가 조건 없음(대조)": (A.r1 >= 10),
        "Open=Low BTST 시가=저가 & 양봉": OL & (A.close > A.open),
        "  └ + 200일선 위": OL & (A.close > A.open) & (A.close > A.ma200),
        "  └ + 52주 고가 -10% 이내": OL & (A.close > A.open) & (A.fromhi >= -10),
        "BSJP 장중+10%·고가권·거래대금2배·10/20일선 위": (A.pos >= 0.8) & (A.amt >= 2 * A.amtav) & (A.close > A.ma10)
                                                      & (A.close > A.ma20) & (A.high >= 1.1 * pc) & (A.r1 > 2),
        "상한가(국내 +29%·미장 +20%) 고가 마감": (A.r1 >= lim) & (A.close >= A.high * 0.999),
        "종가 위치 상위 10%(pos≥0.9) & +5%↑": (A.pos >= 0.9) & (A.r1 >= 5),
        "종가 위치 하위 10%(pos≤0.1) & -5%↓(대조)": (A.pos <= 0.1) & (A.r1 <= -5),
    }
    SEG = [("전체 16~", "20160101", "20991231"), ("학습 16~22", "20160101", "20221231"), ("검증 23~", "20230101", "20991231")]
    if mk == "KR":
        SEG.insert(0, ("홀드아웃 05~15", "20050101", "20151231"))
    base = A[uni & A.ovn.notna()]
    P("# 하룻밤 보유(종가 매수 → 다음날 시가 매도) · %s · %s" % ("국내" if mk == "KR" else "미장", time.strftime("%Y-%m-%d"))); P("")
    P("거래대금 상위 40% · 수익은 %%. **순 = 왕복 비용 차감**(국내 0.35~1.15%%, 미장 0.10~0.60%%). 하루 = 다음날 종가 청산(참고, 순)."); P("")
    P("| 조건 · 구간 | n | 밤 평균(비용 전) | 밤 중앙(전) | **밤 평균(순)** | 밤 중앙(순) | 순 승률 | 하루 평균(순) | 양수해 | 월CI 하한 |")
    P("|---|---|---|---|---|---|---|---|---|---|")
    for nm, c in C.items():
        z0 = base[c.reindex(base.index).fillna(False)]
        for lbl, lo, hi in SEG:
            z = z0[(z0.date >= lo) & (z0.date <= hi)]
            P(row("%s · %s" % (nm, lbl), stats(z)))
    # 비용 구간별 — 비용이 승부를 가르는지
    P(""); P("## 寄り底大陽線(+10%) — 거래대금(비용) 구간별 · 2016~"); P("")
    P("| 20일 평균 거래대금 구간 | n | 밤 평균(전) | 비용 | 밤 평균(순) | 순 승률 |"); P("|---|---|---|---|---|---|")
    z = base[C["寄り底大陽線 시가=저가 & +10%↑"].reindex(base.index).fillna(False) & (base.date >= "20160101")]
    for q, gq in z.groupby(pd.qcut(z.amt20.rank(method="first"), 4, labels=["하위25", "25~50", "50~75", "상위25"])):
        P("| %s | %s | %+.2f | %.2f | %+.2f | %.0f%% |" % (q, f"{len(gq):,}", gq.ov.mean(), gq.cost.mean(), gq.ovn.mean(), (gq.ovn > 0).mean() * 100))
    P(""); P("총 %.0f초" % (time.time() - t0))
    log_trials("overnight_%s_%s" % (mk.lower(), time.strftime("%Y%m%d")), len(C) - 1)
    rp = ROOT / "reports" / ("overnight_%s_%s.md" % (mk.lower(), time.strftime("%Y%m%d")))
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT)); print("\n보고서:", rp)


if __name__ == "__main__":
    main()
