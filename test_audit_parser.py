# -*- coding: utf-8 -*-
"""감사 파서 자가검증 — 오탐을 없앤 뒤에도 '진짜 어긋남' 을 잡는지 본다.

표기 차이를 흡수하다 보면 감사가 아무것도 못 잡는 쪽으로 무뎌지기 쉽다.
그러면 늘 빨간불이던 것이 늘 초록불이 될 뿐 쓸모는 똑같이 없다.
그래서 문턱값을 일부러 틀어 보고 감사가 실제로 반응하는지 확인한다.

사용: python test_audit_parser.py
"""
import io, re, sys
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = Path(__file__).parent
SRC = (BASE / "audit_rules.py").read_text(encoding="utf-8")

# audit_rules.py 를 통째로 돌리면 무거우니 파서 부분만 떼어 쓴다
i = SRC.index("# 같은 조건이 파일마다")
_end = "return {(f, d, v) for (f, d), v in out.items()}"
j = SRC.index(_end) + len(_end)
ns = {"re": re}
exec(compile(SRC[i:j], "audit_rules.py(thr)", "exec"), ns)
thr = ns["thr"]

def diff(a, b):
    """감사 2) 가 쓰는 비교 그대로 — 어긋남이 있으면 True"""
    ja, jb = thr(a), thr(b)
    only_a = {x for x in ja if x[0] in {y[0] for y in jb}} - jb
    only_b = {x for x in jb if x[0] in {y[0] for y in ja}} - ja
    SILENT = {"close", "marcap", "fw5", "r16", "rw1", "amt20", "amt"}
    miss = ({x[0] for x in ja} - {y[0] for y in jb}) - SILENT       # 사이트에만 있는 조건
    extra = ({y[0] for y in jb} - {x[0] for x in ja}) - SILENT      # 상대에만 있는 조건
    return bool(only_a or only_b or miss or extra)

CASES = [
    # (설명, 사이트 표기, 다른 파일 표기, 어긋나야 하는가)
    ("신용잔고 이름만 다름 (crc = cr_chg20)",
     "r.crc!=null&&r.crc<=-15", "KP.cr_chg20<=-15", False),
    ("신용잔고 문턱이 진짜 다름",
     "r.crc!=null&&r.crc<=-15", "KP.cr_chg20<=-25", True),
    ("시총 단위만 다름 (억 vs 조)",
     "r.cap>=10000&&r.cap<100000", '(KP["cap조"]>=1)&(KP["cap조"]<10)', False),
    ("시총 하한이 진짜 다름 (1조 vs 2조)",
     "r.cap>=10000&&r.cap<100000", '(KP["cap조"]>=2)&(KP["cap조"]<10)', True),
    ("한글 필드 + 결측 처리 (부채비율)",
     "(r.dbt==null||r.dbt<=200)", "(KQ['부채비율'].isna()|(KQ['부채비율']<=200))", False),
    ("부채비율 문턱이 진짜 다름",
     "(r.dbt==null||r.dbt<=200)", "(KQ['부채비율'].isna()|(KQ['부채비율']<=300))", True),
    ("fillna 꼬리 (내부자)",
     "r.ins60!=null&&r.ins60>0", "(KP.ins60.fillna(0)>0)", False),
    ("notify 의 r.get(...) or 0 표기",
     "r.above20>70&&r.ret250>120",
     '(r.get("above20") or 0) > 70 and (r.get("ret250") or 0) > 120', False),
    ("notify 문턱이 진짜 다름",
     "r.above20>70&&r.ret250>120",
     '(r.get("above20") or 0) > 80 and (r.get("ret250") or 0) > 120', True),
    ("외국인 5일: 비율 표기 vs 퍼센트 필드",
     "r.fw>0&&r.fw>=0.02*r.v5", "(KP.fw5>=2)", False),
    ("외국인 5일 문턱이 진짜 다름 (2% vs 3%)",
     "r.fw>0&&r.fw>=0.02*r.v5", "(KP.fw5>=3)", True),
    ("느슨한 널가드는 어긋남이 아니다",
     "r.ret20!=null&&r.ret20<=-20", "(KP.ret20<=-20)", False),
    ("보유기간·손절 같은 다른 숫자에 속지 않는가",
     "r.ret20<=-20", "(KP.ret20<=-20)", False),
    # 한쪽에만 조건이 더 붙은 경우 — 예전엔 사이트→상대 방향만 봐서 이쪽을 놓쳤다
    ("사이트에만 있는 조건", "r.ret20<=-20&&r.vs1>=1.5", "(KP.ret20<=-20)", True),
    ("상대에만 있는 조건 (알림에 몰래 남은 것)",
     "r.ret20<=-20", '(r.get("ret20") or 0) <= -20 and (r.get("streak") or 0) >= 1', True),
]
ok = True
print(f"  {'검증 항목':<38} {'기대':<6} {'결과':<6} 판정")
for nm, a, b, want in CASES:
    got = diff(a, b)
    good = (got == want)
    ok &= good
    print(f"  {'✅' if good else '❌'} {nm:<36} {'어긋남' if want else '같음':<6} "
          f"{'어긋남' if got else '같음':<6} {'' if good else '  ← 파서가 틀렸다'}")
print(f"\n{'✅ 파서 자가검증 통과 — 오탐도 없고 진짜 어긋남은 잡는다' if ok else '❌ 파서를 고쳐야 한다'}")
sys.exit(0 if ok else 1)
