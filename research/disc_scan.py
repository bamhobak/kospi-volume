# -*- coding: utf-8 -*-
"""**공시 유형 전수 스캔** (2026-09-29, 사용자 제안 목록 2번 · 등록부 '보유 데이터 안 쓴 축' 1순위).

data/dart/disclosures.db(190만 건, 2005~) 공시 **제목만**으로 사건형 유형을 뽑아 run_spec 과 같은 잣대로 잰다.
  · 유형 명단은 결과를 보기 전에 고정(아래 TYPES) — 가격에 영향이 있을 만한 사건형만, 정정 공시는 뺀다
  · 신호일 = 공시일(휴일이면 다음 거래일) · 다음날 시가 매수 · 비용 차감 · 한 종목 보유 중 재신호 무시
  · 유형마다 두 칸: 공시만 / 공시 + 20일 -10% 이하 낙폭([자사주 낙폭] 선례 — 공시 + 가격 조건)
  · 보유 20·60일 · 유니버스 = 거래대금 상위 40%(run_spec 과 같다)
  · 판정: run_spec 2단계(학습 중앙·절삭·월CI·연도 60%) + 4단계(검증 중앙·최근 두 해·다중검정 **전체 칸 수** 기준·60일 드리프트)
    + 5단계 겹침(기존 9규칙 ±5일 50%↑ 탈락)
  · 이 스캔은 '후보' 만 고른다 — 채택·비중은 사람이 정한다.

    python research/disc_scan.py
"""
import re, sqlite3, sys, time, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(ROOT))
import run_spec as R
from verdict import deflated_sharpe, log_trials

# 결과 보기 전에 고정한 명단 — (이름, 제목 정규식)
TYPES = [
    ("자사주 소각 결정", r"주식소각결정"), ("자사주 취득 결정(참고: 기존 규칙 재료)", r"자기주식취득결정"),
    ("자사주 신탁계약 체결", r"자기주식취득신탁계약체결결정"), ("자사주 처분 결정", r"자기주식처분결정"),
    ("액면분할", r"주식분할결정"), ("주식병합", r"주식병합결정"), ("무상증자", r"무상증자결정"),
    ("유상증자", r"유상증자결정"), ("감자", r"감자결정"), ("주식배당", r"주식배당결정"),
    ("최대주주 변경", r"최대주주변경(?!을)"), ("경영권 양수도 계약", r"최대주주변경을수반하는주식양수도계약체결"),
    ("경영권 변경 계약", r"경영권변경등에관한계약체결"), ("공개매수 신고", r"공개매수신고서"),
    ("합병 결정", r"회사합병결정"), ("분할 결정", r"회사분할결정"), ("영업양수", r"영업양수결정"), ("영업양도", r"영업양도결정"),
    ("자회사 편입(지주사)", r"지주회사의자회사편입(?!ㆍ)"), ("타법인 주식 취득", r"타법인주식및출자증권취득결정"),
    ("타법인 주식 처분", r"타법인주식및출자증권처분결정"), ("유형자산 취득", r"유형자산취득결정"),
    ("유형자산 처분", r"유형자산처분결정"), ("신규시설투자", r"신규시설투자등"), ("특허권 취득", r"특허권취득"),
    ("단일판매·공급계약(참고: 회피 신호 기록)", r"단일판매ㆍ공급계약체결"), ("공급계약 해지", r"단일판매ㆍ공급계약해지"),
    ("현금배당 결정(참고)", r"현금ㆍ현물배당결정"), ("기업가치 제고 계획(밸류업)", r"기업가치제고계획(?!예고)"),
    ("기업설명회(IR) 개최", r"기업설명회(\(IR\))?개최(?!결과)"), ("풍문·보도 해명", r"풍문또는보도에대한해명"),
    ("조회공시 요구", r"조회공시요구(?!에대한)"), ("CB 만기 전 취득(발행사가 되사옴)", r"전환사채(\([^)]*\))?발행후만기전사채취득"),
    ("전환청구권 행사(희석)", r"전환청구권행사"), ("횡령·배임 혐의", r"횡령ㆍ배임혐의발생"),
    ("소송 제기", r"소송등의제기ㆍ신청"), ("생산중단", r"생산중단"), ("생산재개", r"생산재개"),
    ("거래정지 해제", r"주권매매거래정지해제"), ("불성실공시법인 지정", r"불성실공시법인지정(?!예고)"),
    ("회생절차 개시", r"회생절차개시결정"), ("주식매수선택권 부여", r"주식매수선택권부여에관한신고"),
]
HOLDS = (20, 60)
OUT = []; P = OUT.append


def log(m):
    print("%s %s" % (time.strftime("%H:%M:%S"), m), file=sys.stderr, flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8"); t0 = time.time()
    log("공시 읽기")
    c = sqlite3.connect(BASE / "data" / "dart" / "disclosures.db")
    D = pd.read_sql("select stock_code, rcept_dt, report_nm from disclosure where stock_code is not null and stock_code != ''", c)
    D = D[~D.report_nm.str.contains(r"\[[^\]]*정정\]|\[발행조건확정\]", regex=True)]
    # ⚠ 주요사항보고서는 유형이 괄호 안에 있다 — '주요사항보고서(자기주식취득결정)'. 괄호를 지우면 유형이 사라진다(2026-09-29 첫 실행 실수).
    D["t"] = D.report_nm.str.replace(r"\[[^\]]*\]", "", regex=True).str.replace(" ", "", regex=False)
    log("  %s건" % f"{len(D):,}")
    log("패널")
    A, uni, since = R.load_market("KR")
    cal = np.array(sorted(A.date.unique()))
    D["sd"] = [cal[i] if i < len(cal) else None for i in np.searchsorted(cal, D.rcept_dt.values, "left")]
    D = D.dropna(subset=["sd"])
    key = A.ticker + "|" + A.date
    J = R.Judge(A, uni, since)
    dd = A.ret20 <= -10
    cells = []   # (유형, 칸, 보유, Y)
    for nm, rx in TYPES:
        ev = D[D.t.str.contains(rx, regex=True)]
        ek = set(ev.stock_code + "|" + ev.sd)
        m = key.isin(ek)
        for sub, cond in (("공시만", m), ("공시+20일 -10%", m & dd)):
            for h in HOLDS:
                Y = J.run(cond, h)
                cells.append((nm, sub, h, Y, len(ev)))
        log("  %s: 공시 %s건" % (nm, f"{len(ev):,}"))
    NC = J.cells
    log("판정 · 전체 칸 %d" % NC)
    OLD = R.old_signals("KR")
    P("# 공시 유형 전수 스캔 · 국내 · %s" % time.strftime("%Y-%m-%d")); P("")
    P("공시 %s건(정정 제외) · 유형 %d개 × (공시만 / 공시+20일 -10%%) × 보유 20·60일 = **%d칸**. 다중검정은 전체 칸 수로 보정." % (
        f"{len(D):,}", len(TYPES), NC)); P("")
    P("수익 = 공시일 다음날 시가 매수 · 비용 차감(%). 기준 = 같은 날 유니버스 아무거나 중앙. 판정은 run_spec 2·4·5단계."); P("")
    P("| 유형 | 칸 | 보유 | 전체 16~ n | 중앙 | 절삭 | 승률 | 기준 대비 | 홀드아웃 05~15 중앙 | 학습 중앙 | 검증 중앙 | 최근 두 해 | 진짜일 확률 | 판정 |")
    P("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    passed = []
    for nm, sub, h, Y, ne in cells:
        st = lambda z: J.stats(z)
        a = st(Y[Y.date >= R.TR0]); ho = st(Y[Y.date < R.TR0]); tr = st(Y[(Y.date >= R.TR0) & (Y.date <= R.TR1)])
        va = Y[Y.date >= R.VA0]
        if not a:
            P("| %s | %s | %d일 | %d | 표본 부족 | | | | | | | | | |" % (nm, sub, h, len(Y[Y.date >= R.TR0]))); continue
        ok2, _ = J.pass2(Y)
        yrs = sorted(Y.yr.unique())[-2:]
        rec = {y: Y[Y.yr == y].r.median() for y in yrs if (Y.yr == y).sum() >= 10}
        d = deflated_sharpe(Y[Y.date >= R.TR0].groupby("ym").r.mean(), NC)
        dsr = d["dsr"] if d else float("nan")
        z = Y[Y.date >= R.TR0]
        ex = z.r.median() - z.date.map(J.bench(h)).median()
        why = []
        if not ok2: why.append("2단계")
        if not (len(va) >= 20 and va.r.median() > 0): why.append("검증")
        if any(v < 0 for v in rec.values()): why.append("최근 해")
        if not (dsr >= R.DSR_MIN): why.append("다중검정")
        if h >= 40 and ex <= 0: why.append("드리프트")
        verdict = "통과" if not why else "✗ " + "·".join(why)
        if not why:
            ov = R.overlap(z, OLD, J.di)
            if ov >= 50:
                verdict = "✗ 겹침 %.0f%%" % ov
            else:
                verdict = "✅ 후보 (겹침 %.0f%%)" % ov; passed.append((nm, sub, h))
        P("| %s | %s | %d일 | %s | %+.2f | %+.2f | %.0f%% | %+.2f | %s | %s | %s | %s | %.2f | %s |" % (
            nm, sub, h, f"{a['n']:,}", a["med"], a["trim"], a["win"], ex,
            ("%+.2f" % ho["med"]) if ho else "-", ("%+.2f" % tr["med"]) if tr else "-",
            ("%+.2f" % va.r.median()) if len(va) >= 20 else "-", " ".join("%s %+.1f" % kv for kv in rec.items()), dsr, verdict))
    P(""); P("**후보 %d칸**: %s" % (len(passed), ", ".join("%s(%s·%d일)" % p for p in passed) or "없음"))
    P(""); P("총 %.0f분" % ((time.time() - t0) / 60))
    log_trials("disc_scan_%s" % time.strftime("%Y%m%d"), NC)
    rp = ROOT / "reports" / ("disc_scan_%s.md" % time.strftime("%Y%m%d"))
    rp.write_text("\n".join(OUT) + "\n", encoding="utf-8")
    print("\n".join(OUT))


if __name__ == "__main__":
    main()
