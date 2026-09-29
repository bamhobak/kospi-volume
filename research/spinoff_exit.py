# -*- coding: utf-8 -*-
"""미국 분사주(H0243) — **매도 타이밍·트레일링·손절·익절** 정밀 조사 (2026-09-29 사용자 요청).

진입: 상장 21일째 다음날 시가(spinoff.py 와 같다) · 폐지 포함 패널(us_full_2007) · 비용 = 패널 왕복 비용.
청산 판정은 **종가**, 체결은 **다음날 시가**(보수판 — 트레일링 체결 가정이 낙관적이었던 교훈 [[us-trail-fill-artifact]]).
폐지되면 마지막 거래가로 청산. 자료 끝(2026-09)에 아직 보유 중이면 그 거래는 '미완료' 로 빼고 센다.

비교 항목(미리 고정)
  고정 보유 60·120·180·250·375·500일
  트레일링(보유 중 최고 종가 대비) -15·-20·-25·-30·-40% (최대 500일)
  고정 손절(매수가 대비) -20·-30% (최대 250일)
  익절 +30·+50·+100% (최대 250일)
  혼합: 250일 보유 뒤 트레일링 -15% (최대 500일)
지표: 거래 수익(평균·중앙·상위5% 뺀 평균·승률·최악) · 같은 구간 유니버스 동일가중 대비 초과(중앙) · 평균 보유일 ·
      1년 환산 효율(중앙 수익 ÷ 평균 보유일 × 252) · 보유 중 최대 하락(MAE) 분포.

    python research/spinoff_exit.py
"""
import io, json, re, sys, time, warnings, zipfile, contextlib
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
from verdict import log_trials


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


src = (ROOT / "spinoff.py").read_text(encoding="utf-8")
body = src.split("def main():", 1)[1].split('    uq = K.amt20.groupby', 1)[0]
exec("def _events():\n" + body.replace("    sys.stdout.reconfigure(encoding=\"utf-8\")\n", "") + "    return E, K, idx, ev\n")

ENTRY = 21
RULES = [("고정 %d일" % h, dict(hold=h)) for h in (60, 120, 180, 250, 375, 500)]
RULES += [("트레일링 -%d%% (최대 500일)" % t, dict(hold=500, trail=t)) for t in (15, 20, 25, 30, 40)]
RULES += [("손절 -%d%% (최대 250일)" % s, dict(hold=250, stop=s)) for s in (20, 30)]
RULES += [("익절 +%d%% (최대 250일)" % g, dict(hold=250, take=g)) for g in (30, 50, 100)]
RULES += [("250일 뒤 트레일링 -15% (최대 500일)", dict(hold=500, trail=15, trail_after=250))]


def simulate(pxp, buyp, rule):
    """pxp: 보유 1일째~ 종가 배열(매수가 기준 비율 아님, 원가), buyp: 다음날 시가 배열(같은 길이). 반환 (수익비, 보유일, 끝남여부)"""
    b0 = rule.get("_b0")
    h = rule["hold"]; n = len(pxp)
    peak = b0
    for d in range(min(h, n)):
        c = pxp[d]
        if not (c == c and c > 0):
            continue
        peak = max(peak, c)
        k = d + 1                                                # 보유 k일째 종가
        trig = False
        if "trail" in rule and k >= rule.get("trail_after", 0) and c <= peak * (1 - rule["trail"] / 100):
            trig = True
        if "stop" in rule and c <= b0 * (1 - rule["stop"] / 100):
            trig = True
        if "take" in rule and c >= b0 * (1 + rule["take"] / 100):
            trig = True
        if trig:
            ex = buyp[d] if d < len(buyp) and buyp[d] == buyp[d] and buyp[d] > 0 else c   # 다음날 시가(없으면 그날 종가)
            return ex / b0, k + 1, True
    if n >= h:
        return pxp[h - 1] / b0, h, True
    return pxp[-1] / b0, n, False                                # 자료 끝 또는 폐지(아래서 가름)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    E, K, idx, ev = _events()
    px, buy, cost, dates = K.px.values, K.buy.values, K.cost.values, K.date.values
    last_date = dates.max()
    # 유니버스 동일가중 지수(유동성 상위 40%, 매일 재조정) — 같은 구간 비교용
    uq = K.amt20.groupby(K.date).rank(pct=True)
    rr = K.px.groupby(K.ticker, sort=False).pct_change().clip(-0.5, 0.5)
    liq = (uq.groupby(K.ticker, sort=False).shift(1) >= 0.6).fillna(False)
    EW = (1 + rr[liq].groupby(K.date[liq]).mean()).cumprod()
    ewd = np.array([str(x) for x in EW.index]); ewv = EW.values

    def ewat(d):
        i = np.searchsorted(ewd, str(d), "right") - 1
        return ewv[max(i, 0)]
    TR = []
    for t in E.ticker:
        ix = idx[t]
        if len(ix) <= ENTRY:
            continue
        s = ix[ENTRY - 1]
        b0 = buy[s]
        if not (b0 == b0 and b0 > 0):
            continue
        hold_ix = ix[ENTRY:]                                     # 보유 1일째(매수일) ~
        dead = dates[ix[-1]] < last_date
        TR.append(dict(t=t, d0=dates[s], b0=b0, cost=cost[s], pxp=px[hold_ix], buyp=buy[hold_ix],
                       dts=dates[hold_ix], dead=dead))
    log("거래 %d건" % len(TR))
    O = ["# 미국 분사주 — 매도 타이밍·트레일링·손절·익절 · %s" % time.strftime("%Y-%m-%d"), "",
         "분사주 %d건 · 상장 21일째 다음날 시가 매수 · 청산 판정 종가 → **다음날 시가 체결** · 비용 차감 · 폐지는 마지막 거래가." % len(TR),
         "초과 = 같은 보유 구간 유니버스 동일가중(유동성 상위 40%) 대비. 효율 = 중앙 수익 ÷ 평균 보유일 × 252(1년 환산).", "",
         "| 청산 | 끝난 거래 | 평균 | 중앙 | 상위5% 뺀 평균 | 승률 | 최악 | 초과 중앙 | 평균 보유일 | 1년 환산 효율 | 08~15 초과 | 16~22 초과 | 23~ 초과 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for nm, rule in RULES:
        rows = []
        for x in TR:
            r = dict(rule); r["_b0"] = x["b0"]
            ratio, days, fin = simulate(x["pxp"], x["buyp"], r)
            if not fin and not x["dead"]:
                continue                                          # 아직 보유 중(자료 끝) — 뺀다
            ret = (ratio - 1) * 100 - x["cost"]
            d_end = x["dts"][min(days, len(x["dts"])) - 1]
            ex = ret - (ewat(d_end) / ewat(x["d0"]) - 1) * 100
            rows.append((x["d0"], ret, ex, days))
        Z = pd.DataFrame(rows, columns=["d", "r", "ex", "days"])
        seg = lambda lo, hi: Z[(Z.d >= lo) & (Z.d <= hi)].ex.median()
        O.append("| %s | %d | %+.1f%% | %+.1f%% | %+.1f%% | %.0f%% | %.0f%% | **%+.1f%%p** | %.0f | %+.1f%% | %+.1f | %+.1f | %+.1f |" % (
            nm, len(Z), Z.r.mean(), Z.r.median(), Z.r[Z.r <= Z.r.quantile(0.95)].mean(), (Z.r > 0).mean() * 100, Z.r.min(),
            Z.ex.median(), Z.days.mean(), Z.r.median() / Z.days.mean() * 252,
            seg("20080101", "20151231"), seg("20160101", "20221231"), seg("20230101", "20991231")))
    # 보유 중 최대 하락(MAE)과 최종(250일)
    mae, fin = [], []
    for x in TR:
        p = x["pxp"][:250]
        if len(p) < 250 and not x["dead"]:
            continue
        mae.append((np.nanmin(p) / x["b0"] - 1) * 100); fin.append((p[-1] / x["b0"] - 1) * 100)
    mae, fin = np.array(mae), np.array(fin)
    O += ["", "## 보유 중 최대 하락(250일) — 트레일링이 좋은 거래를 자르나", "",
          "| 최대 하락 구간 | 거래 비율 | 250일 최종 평균 | 최종 중앙 |", "|---|---|---|---|"]
    for lo, hi in ((0, -10), (-10, -20), (-20, -30), (-30, -40), (-40, -1000)):
        m = (mae <= lo) & (mae > hi)
        if m.sum():
            O.append("| %d%% ~ %s | %.0f%% | %+.1f%% | %+.1f%% |" % (lo, ("%d%%" % hi) if hi > -1000 else "그 아래", m.mean() * 100, fin[m].mean(), np.median(fin[m])))
    O += ["", "보유 중 최대 하락 중앙 %.1f%% · -20%% 이하 닿은 거래 %.0f%% · -30%% 이하 %.0f%%" % (np.median(mae), (mae <= -20).mean() * 100, (mae <= -30).mean() * 100)]
    log_trials("spinoff_exit_%s" % time.strftime("%Y%m%d"), len(RULES))
    rp = ROOT / "reports" / ("spinoff_exit_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(O) + "\n", encoding="utf-8")
    print("\n".join(O))


if __name__ == "__main__":
    main()
