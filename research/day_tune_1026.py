# -*- coding: utf-8 -*-
"""[갭 하락 조용주](T1=H.t1) 안 해본 각도 — 체결 현실성(거래대금·가격 바닥)·안정성 필터 (2026-10-26).
라이브 신호 H.t1 을 베이스로, day2 에서 T1 에 안 걸어본 재료(mcap·vol20·age·px·amt20 절대·52주저고·장기이평·ATR정규화갭)별로
시가→종가(비용 0.22%)를 학습16~22/검증23~/참고10~15 로 비교. 칸 = 건수·건당%·승률·날바구니%·t·플러스해.
    py314 day_tune_1026.py
"""
import sys, time
from pathlib import Path
ROOT = Path(r'C:\vscode\kospi-volume\research')
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'factory')); sys.path.insert(0, str(ROOT.parent))
sys.stdout.reconfigure(encoding='utf-8')
import numpy as np, pandas as pd
import lab

COST = 0.22
PERS = [("참고10~15", "20100101", "20151231"), ("학습16~22", "20160101", "20221231"), ("검증23~", "20230101", "20991231")]
OUT = []
P = lambda s="": (OUT.append(s), print(s, flush=True))


def cell(z):
    if len(z) < 30:
        return "-"
    dd = z.groupby("date").ocn.mean()
    if len(dd) < 20:
        return "-"
    t = dd.mean() / (dd.std() / np.sqrt(len(dd))) if dd.std() > 0 else 0
    yr = dd.groupby(dd.index.str[:4]).mean()
    nperday = len(z) / z.date.nunique()
    return "%d·건%+.2f·승%.0f·날%+.3f·t%.1f·%d/%d해·%.1f종" % (
        len(z), z.ocn.mean(), (z.ocn > 0).mean() * 100, dd.mean(), t, (yr > 0).sum(), len(yr), nperday)


def row(label, Z):
    cells = [cell(Z[(Z.date >= lo) & (Z.date <= hi)]) for _, lo, hi in PERS]
    P("| %s | %s |" % (label, " | ".join(cells)))


def head(title):
    P(""); P("### " + title); P("")
    P("| 조건 | 참고10~15 | 학습16~22 (건수·건당%·승률·날%·t·플러스해·하루종목) | 검증23~ |"); P("|---|---|---|---|")


def main():
    t0 = time.time()
    H = lab.hist()
    H = H[H.t1].copy()
    H["ocn"] = H.oc.clip(-60, 60) - COST
    H = H.dropna(subset=["ocn"])
    P("# [갭 하락 조용주] 새 각도 · %s (비용 %.2f%%)" % (time.strftime("%Y-%m-%d"), COST))
    P("베이스 T1(H.t1) 건수: 전체 %d · 검증23~ %d" % (len(H), (H.date >= "20230101").sum()))
    # 단위 감 잡기
    P("\n단위 감: amt20(억) %s · px %s · mcap %s · age %s" % (
        H.amt20.describe(percentiles=[.1, .5, .9]).round(1).to_dict(),
        H.px.describe(percentiles=[.1, .5, .9]).round(0).to_dict() if "px" in H else "?",
        H.mcap.describe(percentiles=[.1, .5, .9]).round(0).to_dict() if "mcap" in H else "?",
        H.age.describe(percentiles=[.1, .5, .9]).round(0).to_dict() if "age" in H else "?"))
    row0 = lambda: row("기본(전체 T1)", H)
    head("0) 기본")
    row0()

    head("1) 거래대금 바닥 amt20 (억) — 체결 현실성")
    for fl in (0, 3, 5, 10, 20, 30, 50, 100):
        row("amt20 ≥ %d억" % fl, H[H.amt20 >= fl])

    head("2) 가격대 px (저가주 제외)")
    for fl in (0, 500, 1000, 2000, 5000):
        row("px ≥ %d원" % fl, H[H.px >= fl])

    head("3) 시가총액 mcap 10분위 (조용 소형이 핵심인가)")
    H["qm"] = H.groupby("date").mcap.rank(pct=True)
    for lab_, lo_, hi_ in (("하위30%(초소형)", 0, .3), ("중간30~70%", .3, .7), ("상위30%(대형)", .7, 1.01)):
        row(lab_, H[(H.qm > lo_) & (H.qm <= hi_)])

    head("4) 종목 변동성 vol20 10분위 (더 조용할수록?)")
    for lab_, lo_, hi_ in (("변동성 하위30%(잔잔)", 0, .3), ("중간", .3, .7), ("상위30%(출렁)", .7, 1.01)):
        row(lab_, H[(H.q_vol20 > lo_) & (H.q_vol20 <= hi_)])

    head("5) ATR 정규화 갭 = 갭 ÷ 어제 고저폭 (변동성 대비 놀람)")
    H["gapn"] = H.gap / H.rng.replace(0, np.nan)
    gq = H.gapn.rank(pct=True)
    for lab_, lo_, hi_ in (("갭/변동성 깊음 하위30%", 0, .3), ("중간", .3, .7), ("얕음 상위30%", .7, 1.01)):
        row(lab_, H[(gq > lo_) & (gq <= hi_)])

    head("6) 상장 나이 age (신규주 제외)")
    for lab_, c in (("age < 120", H.age < 120), ("120~250", (H.age >= 120) & (H.age < 250)), ("age ≥ 250", H.age >= 250)):
        row(lab_, H[c])

    head("7) 52주 저점 대비 q_lo250 (신저가 근처인가)")
    for lab_, lo_, hi_ in (("저점 근처 하위30%", 0, .3), ("중간", .3, .7), ("저점서 먼 상위30%", .7, 1.01)):
        row(lab_, H[(H.q_lo250 > lo_) & (H.q_lo250 <= hi_)])

    head("8) 장기 추세 d120 (120일선 대비) — 장기 하락/상승 중")
    if "q_d120" in H:
        for lab_, lo_, hi_ in (("120일선 많이 아래 하위30%", 0, .3), ("중간", .3, .7), ("위 상위30%", .7, 1.01)):
            row(lab_, H[(H.q_d120 > lo_) & (H.q_d120 <= hi_)])

    head("9) 거래대금 바닥 × 하루 깊은 순 N개 (H0362 best=top3 과 결합)")
    H["mdep"] = H.rgap  # 시장 대비 갭(깊을수록 음수) — 깊은 순
    for fl in (0, 10, 30):
        for topn in (3, 5, 10, 999):
            sub = H[H.amt20 >= fl].copy()
            sub["rk"] = sub.groupby("date").mdep.rank(method="first")
            z = sub[sub.rk <= topn]
            row("amt20≥%d억 · 하루 깊은 %s개" % (fl, "전부" if topn == 999 else topn), z)

    log = ROOT / "reports" / ("day_tune_%s.md" % time.strftime("%Y%m%d"))
    log.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    P(""); P("(%.0f초) → %s" % (time.time() - t0, log))


if __name__ == "__main__":
    main()
