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
    months = max(va["months"], 1)
    years = (f"'**검증기간(2023~26) · 실거래 기준** · {ydet}"
             f"  —  **기준구간(2016~26, 11년)** {al['n']}건 평균 {al['avg']:+.2f}% · 중앙값 {al['med']:+.2f}%"
             f" · 승률 {al['win']:.0f}% · PF {al['pf']:.2f} · 최악 {al['worst']:.1f}% · 월 신뢰구간 하한 {al['ci']:+.1f}%"
             f"  —  **학습(2016~22)** {tr['n']}건 {tr['avg']:+.2f}%(승률 {tr['win']:.0f}%, CI하한 {tr['ci']:+.1f}%)"
             f"  —  참고 **스트레스(2005~15)** " +
             (f"{st['n']}건 {st['avg']:+.2f}%(승률 {st['win']:.0f}%)" if st else "신호 없음") +
             " — 공매도·가격제한폭 제도가 지금과 달라 채택 근거로는 쓰지 않습니다'")
    new = (f"stats:{{n:{va['n']}, perMonth:{va['n']/44:.1f}, win:{va['win']:.0f}, pf:{min(va['pf'],999):.2f},"
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
