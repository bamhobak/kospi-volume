# -*- coding: utf-8 -*-
"""생산중단 공시 본문 분류(2026-11-18, 코덱스 제안 3번). Claude 가 공시 본문만 읽고(다른 회사·주가는 안 줌) 사유·돌발 여부·제품·정상 공급 언급을 뽑는다.
→ research/cache/halt_lab_1118.pkl · 비용 기록 data/factory/llm_usage_research.jsonl(공장 한도와 따로)
    python research/halt_label_1118.py [개수]"""
import json, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
sys.stdout.reconfigure(encoding="utf-8")
MODEL = "claude-opus-5-5"; PRICE = (4.0, 20.0)
KINDS = ["사고·재해", "당국 명령", "설비 고장", "정기보수·계획 중단", "수요 감소·감산", "사업 철수·구조조정", "공장 이전·설비 교체", "파업·노사", "원재료·협력사", "기타"]
SYSTEM = """상장사의 '생산중단' 공시 본문을 읽고 사실만 뽑는다. 본문에 없는 것은 짐작하지 않는다.

- kind: 생산중단 사유 한 가지.
  사고·재해(화재·폭발·붕괴·침수·인명 사고로 멈춤) / 당국 명령(고용노동부 작업중지 명령, 영업정지·제조정지·조업정지 같은 행정처분) /
  설비 고장(예고 없는 설비 이상) / 정기보수·계획 중단(대정비·정기 점검·미리 잡힌 휴업) / 수요 감소·감산(판매 부진·재고 조정·수익성 악화로 줄임) /
  사업 철수·구조조정(사업 정리·매각·폐쇄·품목 단종) / 공장 이전·설비 교체(이전·증설·라인 교체·통합) / 파업·노사 / 원재료·협력사(부품·원료 공급 차질) / 기타
- sudden: 회사가 미리 계획한 게 아니라 갑자기 멈춘 것이면 true(사고·재해, 당국 명령, 설비 고장, 파업 돌입, 협력사 문제 등). 스스로 정한 중단이면 false.
- products: 멈춘 분야에서 만드는 제품을 일반 명사로 1~4개. 상표·모델명·공장 이름 말고, 같은 물건을 만드는 다른 회사의 사업보고서에도 그대로 나올 낱말로(예: 철근, 폴리실리콘, 자동차 범퍼, 라면). 알 수 없으면 빈 목록.
- share_pct: '최근 매출총액 대비(%)' 같은 칸의 숫자. 없으면 null.
- supply_ok: 본문이 재고·다른 공장·대체 생산·외주 등으로 공급이나 매출에 차질이 없다(또는 작다)고 밝혔으면 true. 그런 말이 없거나 차질이 있다고 했으면 false.
- whole: 회사(또는 그 사업)의 그 제품 생산이 전부 멈춘 것이면 true, 여러 공장·라인 중 일부만이면 false. 모르면 false.
- resume: 생산재개 예정일(YYYYMMDD). 미정·없음이면 빈 글자."""
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["kind", "sudden", "products", "share_pct", "supply_ok", "whole", "resume"],
          "properties": {"kind": {"type": "string", "enum": KINDS}, "sudden": {"type": "boolean"}, "products": {"type": "array", "items": {"type": "string"}},
                         "share_pct": {"type": ["number", "null"]}, "supply_ok": {"type": "boolean"}, "whole": {"type": "boolean"}, "resume": {"type": "string"}}}

def env():
    e = {}
    for f in (BASE / ".env", BASE.parent / ".claude_api.env"):
        if f.exists():
            for ln in f.read_text(encoding="utf-8").splitlines():
                if "=" in ln and not ln.strip().startswith("#"):
                    k, v = ln.split("=", 1); e.setdefault(k.strip(), v.strip())
    return e

def body(t):
    i = t.find("생산중단 분야")
    if i < 0: i = max(t.rfind("}") + 1, 0)
    return t[max(i - 40, 0):][:3500]

def main():
    import anthropic
    cl = anthropic.Anthropic(api_key=env()["ANTHROPIC_API_KEY"], timeout=60.0, max_retries=3)
    X = pd.read_pickle(ROOT / "cache" / "halt_kr_1118.pkl")
    out = ROOT / "cache" / "halt_lab_1118.pkl"
    done = pd.read_pickle(out).to_dict("records") if out.exists() else []
    have = {r["rcept_no"] for r in done}
    todo = X[~X.rcept_no.isin(have)]
    if len(sys.argv) > 1: todo = todo.head(int(sys.argv[1]))
    print("분류할 것 %d · 이미 %d" % (len(todo), len(have)), flush=True)
    usd = [0.0]
    def one(r):
        try:
            m = cl.messages.create(model=MODEL, max_tokens=1500, system=SYSTEM, output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                                   messages=[{"role": "user", "content": "공시 제목: %s\n\n본문:\n%s" % (r.report_nm, body(r.text))}])
            usd[0] += (m.usage.input_tokens * PRICE[0] + m.usage.output_tokens * PRICE[1]) / 1e6
            if m.stop_reason != "end_turn": return None
            j = json.loads("".join(b.text for b in m.content if getattr(b, "type", "") == "text"))
            return dict(rcept_no=r.rcept_no, **j)
        except Exception as ex:
            print("  실패", r.rcept_no, repr(ex)[:120], flush=True); return None
    with ThreadPoolExecutor(6) as ex:
        res = [x for x in ex.map(one, list(todo.itertuples())) if x]
    done += res
    pd.DataFrame(done).to_pickle(out)
    with open(BASE / "data" / "factory" / "llm_usage_research.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": MODEL, "task": "생산중단 분류(halt_label_1118)", "n": len(res), "usd": round(usd[0], 4)}, ensure_ascii=False) + "\n")
    L = pd.DataFrame(done).merge(X[["rcept_no", "corp", "date", "report_nm"]], on="rcept_no")
    print("끝 · 분류 %d건 · 이번 비용 $%.2f" % (len(L), usd[0]))
    print(L.kind.value_counts().to_string()); print("돌발", int(L.sudden.sum()), "· 정상 공급 언급", int(L.supply_ok.sum()), "· 제품 있음", int((L.products.str.len() > 0).sum()))
    for r in L.sample(min(8, len(L)), random_state=1).itertuples():
        print(" ", r.date, r.corp, "|", r.kind, "돌발" if r.sudden else "계획", "|", r.products, "|", r.share_pct, "| 공급OK" if r.supply_ok else "|", "전부" if r.whole else "일부")

if __name__ == "__main__":
    main()
