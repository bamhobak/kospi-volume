# -*- coding: utf-8 -*-
"""규칙 설명문을 '신호가 나는 조건' 만 남기고 줄인다.

사용자 요청(2026-09-07): "규칙들 여기 상세설명, 모든 내용을 다 넣을필요없어,
해당 규칙이 발생하는 조건내용만 넣어줘".
desc 는 조건 나열 뒤에 ▶ 매매/백테스트/왜/⚠ 주의가 길게 붙어 있었다(전 9규칙 19,051자).
첫 '▶' 앞까지만 남긴다 — 매매 방식은 별도 필드(ruleText)로 화면에 이미 나오고,
성적은 stats 로 나온다. 잘라낸 근거 문단은 data/rule_desc_full.json 에 보관한다(git 이력에도 남는다).
사용: python trim_desc.py [--restore]
"""
import io, json, re, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
P = BASE/"index.html"; FULL = BASE/"data"/"rule_desc_full.json"
s = P.read_text(encoding="utf-8")
if "--restore" in sys.argv:
    old = json.load(open(FULL, encoding="utf-8"))
    for rid, d in old.items():
        m = re.search(r"\{id:'"+rid+r"',regime:", s)
        i = s.index("desc:'", m.start()); j = s.index("',\n", i)
        s = s[:i+6] + d + s[j:]
    P.write_text(s, encoding="utf-8"); print(f"복원 완료 — {len(old)}개 규칙"); raise SystemExit
keep, cut = {}, 0
for m in list(re.finditer(r"\{id:'([A-Z0-9]+)',regime:", s))[::-1]:   # 뒤에서부터 고쳐야 위치가 안 밀린다
    rid = m.group(1)
    i = s.index("desc:'", m.start()); j = s.index("',\n", i)
    d = s[i+6:j]; keep[rid] = d
    k = d.find("▶")
    if k <= 0: continue
    short = d[:k].rstrip(" ·　")
    cut += len(d) - len(short)
    s = s[:i+6] + short + s[j:]
if not FULL.exists():
    json.dump({k: keep[k] for k in sorted(keep)}, open(FULL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"원본 보관 → {FULL.name}")
P.write_text(s, encoding="utf-8")
print(f"설명문 {cut:,}자 삭제 · 남은 조건부만 유지")
for rid in sorted(keep):
    m = re.search(r"\{id:'"+rid+r"',regime:", s)
    i = s.index("desc:'", m.start()); j = s.index("',\n", i)
    print(f"  {rid}: {len(keep[rid]):>5}자 → {j-i-6:>4}자")
