# -*- coding: utf-8 -*-
"""규칙 조건이 참조하는 필드가 실제로 화면 데이터에 존재하는지 검사.

index.html 의 FILTERS 는 view.rows(=prep() 결과)를 받는다. prep() 는 필드를
화이트리스트로 옮기므로, 거기 빠진 필드는 조건에서 undefined 가 되어
'조건에 닿았는데도 신호가 안 나오는' 조용한 실패가 된다.
table.json(수출) → prep(매핑) → FILTERS(사용) 세 단계를 대조한다.
"""
import io, json, re, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
H = (BASE / "index.html").read_text(encoding="utf-8")

# 1) prep() 이 만들어 주는 필드
i = H.find("function prep()")
prep_block = H[i:H.find("function val(", i)]
prep_fields = set(re.findall(r"\b([A-Za-z_]\w*)\s*:", prep_block))

# 2) FILTERS 각 규칙의 fn 이 참조하는 r.xxx
fs = H.find("const FILTERS=")
fe = H.find("const LEGACY_ID", fs)
if fe < 0: fe = H.find("function passes(", fs)
blk = H[fs:fe]
rules = re.findall(r"\{id:'([^']+)'.*?name:'([^']*)'.*?fn:(.*?)(?=\n  \{id:'|\n\];)", blk, re.S)

# 3) table.json 이 실제로 담고 있는 키
tj = BASE / "site" / "data" / "table.json"
have = set()
if tj.exists():
    T = json.loads(tj.read_text(encoding="utf-8"))
    if T.get("rows"): have = set(T["rows"][0].keys())

SAFE = {"mk", "pref", "ticker", "name", "close", "change", "th", "vols", "avg", "total",
        "ratio", "indiv", "organ", "frgn", "last", "chpct", "fwp", "fw", "v5"}
print(f"prep() 제공 필드 {len(prep_fields)}개 · table.json 키 {len(have)}개\n")
print(f"  {'규칙':<22} {'참조 필드':<52} {'문제'}")
bad = 0
for rid, nm, fn in rules:
    used = sorted(set(re.findall(r"\br\.([A-Za-z_]\w*)", fn)))
    miss_prep = [u for u in used if u not in prep_fields and u not in SAFE]
    miss_json = [u for u in used if have and u not in have and u not in SAFE
                 and u not in ("r16", "rw1", "fwp", "streak", "dilu")]
    prob = []
    if miss_prep: prob.append("prep 누락: " + ", ".join(miss_prep))
    if miss_json: prob.append("table.json 누락: " + ", ".join(miss_json))
    if prob: bad += 1
    label = nm.split(" · ")[-1] if " · " in nm else nm
    print(f"  [{label}]{'':<{max(0,19-len(label))}} {','.join(used)[:50]:<52} "
          + ("❌ " + " / ".join(prob) if prob else "정상"))
print(f"\n문제 규칙 {bad}개")
