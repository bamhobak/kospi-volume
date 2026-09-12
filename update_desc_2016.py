# -*- coding: utf-8 -*-
"""사이트 규칙 설명문을 새 기준(학습 2016~22 / 검증 2023~26)으로 갱신한다.

2026-09-07 사용자 결정으로 학습 시점이 2016년이 됐다. index.html 의 stats 블록과 desc 안에 박힌
"학습(2018~22) → 검증(2023~26)" · "백테스트 2018~26(9년…)" 숫자가 실제와 달라졌다.
data/stats_2016.json(stats_2016.py 산출)을 읽어 규칙마다 다시 쓴다.
자동 치환은 stats 블록과 '학습/백테스트' 머리말까지만 한다 — desc 뒷부분의 개별 실험 서술은
그때의 측정이라 손대지 않고, 대신 앞머리에 새 기준 요약을 붙인다.
사용: python update_desc_2016.py
"""
import io, json, re, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
S = json.load(open(BASE/"data"/"stats_2016.json", encoding="utf-8"))
NAME = {"P7":"외인 매집","P1":"조용한 신고가","P4":"업종붕괴 이탈","P6":"깊은 이격","P3":"폭락반등",
        "P2":"조정매집","D1":"낙폭과대","D2":"저PBR 낙폭","P5":"자사주 낙폭"}
# 규칙마다 숫자만으로는 못 읽는 사정 — years 끝에 붙인다(재생성해도 남도록 여기 둔다).
NOTE = {
 "D2": ("  —  ⚠ **최악 -97.4% 는 데이터 오류가 아니라 실제 상장폐지입니다** — 2016-02-23 매수한"
        " 플렉스컴(065270)이 보유 중 거래정지·정리매매를 거쳐 2016-04-11 폐지됐습니다"
        "(1,595원 → 73원, 정리매매 7거래일). 저PBR·낙폭 조건은 부실기업을 같이 집으므로"
        " **이 규칙은 폐지 위험을 안고 가는 규칙**입니다. 종목당 비중 5% 가 그 대비입니다"),
}
p = BASE/"index.html"; s = p.read_text(encoding="utf-8")
n_stats = n_head = 0
for rid, d in S.items():
    tr, va, al = d["학습2016~22"], d["검증2023~26"], d["기준2016~"]
    st = d["스트레스2005~15"]
    yr = d["yearly"]
    # ── ① stats 블록 (검증 구간 기준 대표 성적 + years 요약)
    i = s.index(f"{{id:'{rid}',")
    j = s.index("stats:{", i); k = s.index("}", s.index("years:", j))
    ydet = " / ".join(f"{y} {v['avg']:+.1f}%({v['n']}건)" for y, v in sorted(yr.items()) if y >= "2023")
    # 월 건수는 '난 달 수 / 전체 달 수' 로 적는다 — 단순 나눗셈은 신호 쏠림을 감춘다
    dist = (f"신호가 난 달은 **{va['span']}개월 중 {va['months']}개월**"
            f"(난 달 기준 중앙 {va['permo_med']:.0f}건, 가장 많았던 달 {va['top_mo'][:4]}-{va['top_mo'][4:]} {va['top_n']}건)")
    # 트레일링 규칙은 '최악 -8%대' 가 체결 가정이라 그대로 믿으면 안 된다(2026-09-12).
    cons = ""
    if "avg_c" in al:
        cons = (f"  —  ⚠ **최악 {al['worst']:.1f}% 는 체결 가정입니다** — 트레일이 걸린 날"
                f" 「고점×0.92 **그 가격에** 팔린다」고 봅니다. 실제로는 종가를 보고 알게 되므로,"
                f" **다음날 시가에 파는 보수판**으로 같은 구간을 다시 재면 평균 {al['avg_c']:+.2f}%"
                f" · 중앙값 {al['med_c']:+.2f}% · 승률 {al['win_c']:.0f}% · **최악 {al['worst_c']:.1f}%** 입니다."
                f" 트레일링이 꼬리를 잘라주는 것은 맞지만 -8% 가 바닥은 아닙니다")
    years = (f"'**검증기간(2023~26) · 실거래 기준** · {ydet}  —  {dist}"
             f"  —  **기준구간(2016~26, 11년)** {al['n']}건 평균 {al['avg']:+.2f}% · 중앙값 {al['med']:+.2f}%"
             f" · 승률 {al['win']:.0f}% · PF {al['pf']:.2f} · 최악 {al['worst']:.1f}% · 월 신뢰구간 하한 {al['ci']:+.1f}%"
             + cons
             + f"  —  **학습(2016~22)** {tr['n']}건 {tr['avg']:+.2f}%(승률 {tr['win']:.0f}%, CI하한 {tr['ci']:+.1f}%)"
             f"  —  참고 **스트레스(2005~15)** " +
             (f"{st['n']}건 {st['avg']:+.2f}%(승률 {st['win']:.0f}%)" if st else "신호 없음") +
             " — 공매도·가격제한폭 제도가 지금과 달라 채택 근거로는 쓰지 않습니다"
             + NOTE.get(rid, "") + "'")
    # perMonth 는 '월 평균' 그대로 둔다 — 화면 하단 빈도 예측이 이 값에 이격도 배율을 곱하기
    # 때문이다(배율이 평균 기준으로 산출돼 있어 중앙값을 넣으면 과대추정된다).
    # 대신 화면 표시용으로 실제 분포(난 달 수·전체 달 수·최다월)를 따로 넘긴다.
    new = (f"stats:{{n:{va['n']}, perMonth:{va['n']/va['span']:.1f}, monthsActive:{va['months']},"
           f" spanMonths:{va['span']}, medPerActive:{va['permo_med']:.0f}, topMonth:'{va['top_mo']}',"
           f" topN:{va['top_n']}, win:{va['win']:.0f}, pf:{min(va['pf'],999):.2f},"
           f" avg:{va['avg']:.2f}, years:{years}}}")
    s = s[:j] + new + s[k+1:]; n_stats += 1
    # ── ② desc 머리말의 백테스트/학습 문구
    i2 = s.index(f"{{id:'{rid}',"); j2 = s.index("desc:'", i2)
    seg_end = s.index("',\n", j2) if "',\n" in s[j2:j2+40000] else j2+40000
    seg = s[j2:seg_end]
    seg2 = re.sub(r"백테스트 201[0-9]~26\((\d+)년", "백테스트 2016~26(11년", seg)
    seg2 = re.sub(r"\*\*학습\(2018~22\) \+?-?[\d.]+% → 검증\(2023~26\) \+?-?[\d.]+%\*\*",
                  f"**학습(2016~22) {tr['avg']:+.2f}% → 검증(2023~26) {va['avg']:+.2f}%**", seg2)
    seg2 = seg2.replace("학습(2018~22)", "학습(2016~22)")
    if seg2 != seg: n_head += 1
    s = s[:j2] + seg2 + s[seg_end:]
p.write_text(s, encoding="utf-8")
print(f"stats 블록 {n_stats}개 · desc 머리말 {n_head}개 갱신")
