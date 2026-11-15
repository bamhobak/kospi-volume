# -*- coding: utf-8 -*-
"""공시 제목 AI 분류로 [갭하락 조용주] 공시 거르개 다듬기 — 2026-11-15 사용자 "남는 API 크레딧 활용 1번 해줘".

지금(H0395, 11-10~ 실전): 갭 구간(전날 15:30 뒤~당일 09:00 전)에 공시가 하나라도 있으면 통째로 안 산다(16% 빠짐).
11-09 실측에서 정규식 '악재형'은 '아무 공시'보다 더 잘 가르지 못했다 → 제목 뜻을 AI(Claude Opus 5.5)가 읽으면 가를 수 있나?

가설(등록부 H0423, 시험 전 등록): 제목을 '하락을 정당화하는 정도(sev 0~3)'로 매기면
  ① 가벼운 공시만(sev ≤ 1) 있는 거래는 공시 없는 거래와 되돌림이 같다 → 빼지 말고 산다
  ② 무거운 공시(sev ≥ 2)가 있는 거래만 약하다 → 이것만 뺀다
AI 에겐 제목만 준다(회사 이름·날짜·주가 없음 = 미래 정보 없음). 같은 제목은 한 번만 묻는다.

    python research/kind_llm_1115.py titles     # 거래별 갭 구간 공시 제목 → C:/temp/kp/kind/llm_titles.pkl
    python research/kind_llm_1115.py submit     # 묶음 처리(Batch API, 반값) 보내기 — 첫 줄 N 이면 앞 N 묶음만(시험)
    python research/kind_llm_1115.py fetch      # 결과 받기 → C:/temp/kp/kind/llm_labels.pkl · 크레딧 기록
    python research/kind_llm_1115.py rep        # 판정표 → research/reports/kind_llm_1115.md
"""
import json, os, re, sys, time, pickle, sqlite3, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parent; BASE = ROOT.parent
os.chdir(BASE); sys.path[:0] = [str(ROOT), str(ROOT / "factory"), str(BASE)]
sys.stdout.reconfigure(encoding="utf-8")
OUTD = Path("C:/temp/kp/kind"); OUTD.mkdir(parents=True, exist_ok=True)
FT, FL, FB = OUTD / "llm_titles.pkl", OUTD / "llm_labels.pkl", OUTD / "llm_batch.json"
USAGE = ROOT / "cache" / "kind_llm_usage.jsonl"          # 공장 한도(FACTORY_LLM_MONTHLY)와 따로 센다 — 공장 밤 일을 막지 않게
MODEL = "claude-opus-5-5"
PRICE = (4.0, 20.0)                                       # 백만 토큰당 $ (입력, 출력) — 묶음 처리는 반값
PER_REQ = 60                                              # 한 요청에 제목 60개
cmd = sys.argv[1] if len(sys.argv) > 1 else "rep"

CATS = ["희석", "신뢰", "실적악화", "호재", "일상", "기타"]
SYSTEM = """너는 한국 주식시장(유가증권·코스닥) 공시를 오래 읽어 온 분석가다.
공시 제목 목록을 받는다. 각 공시가 '전 거래일 장 마감 뒤부터 다음 날 장 시작 전 사이'에 나왔고, 그 종목이 다음 날 시가에 갭 하락으로 출발했다고 가정한다.
제목마다 두 가지를 매겨라.

cat (하나만):
- 희석: 유상증자, 전환사채·신주인수권부사채·교환사채 발행, 감자, 신주 추가상장·전환청구 등 주식 가치를 묽게 하는 자금 조달
- 신뢰: 소송, 횡령·배임, 감사의견 비적정, 관리종목·상장적격성·상장폐지, 매매거래정지, 불성실공시, 조회공시 요구, 투자경고·위험, 회생·부도, 최대주주 변경·담보 처분 등 회사 신뢰를 흔드는 일
- 실적악화: 영업손실·적자 전환·매출 감소, 손상차손, 공급계약 해지·축소, 영업정지 등 돈 버는 힘이 줄었다는 소식
- 호재: 실적 개선, 공급계약 체결, 자기주식 취득, 무상증자, 배당 확대, 특허, 투자 유치 등 좋은 소식
- 일상: 정기보고서(사업·분기·반기), 지분 공시(대량보유·임원 소유), 주주총회·IR·의결권, 기재정정, 증권발행실적 등 주가와 거의 상관없는 실무 공시
- 기타: 위 어디에도 안 맞음

sev (0~3) — 이 공시 하나가 다음 날 갭 하락을 '정당화'하는 정도:
- 0: 하락과 상관없음(일상·호재)
- 1: 약간 부정적일 수 있으나 대개 영향 작음
- 2: 하락 이유가 될 만한 분명한 악재(희석, 실적 악화, 계약 해지 등)
- 3: 회사 존립·신뢰가 걸린 심각한 악재(거래정지, 상장폐지 사유, 횡령, 감사의견 거절, 회생 등)

정정 공시는 원래 공시 내용으로 판단하되, 단순 기재정정이면 무게를 한 단계 낮춰라.
목록의 번호 i 를 그대로 돌려주고, 모든 제목에 빠짐없이 답하라."""
SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
    "i": {"type": "integer"}, "cat": {"type": "string", "enum": CATS}, "sev": {"type": "integer", "enum": [0, 1, 2, 3]}},
    "required": ["i", "cat", "sev"], "additionalProperties": False}}}, "required": ["items"], "additionalProperties": False}


def kind_events(cal):
    """kind_filter_1109.kind_events 와 같은 규칙(장전=그날 시가 · 장중=그날 종가 · 장후·휴일=다음 거래일 시가)."""
    c = sqlite3.connect(BASE / "data" / "dart" / "kind_time.db")
    E = pd.read_sql("select day, hm, kcode, market, title from kind where market in ('유가증권','코스닥')", c)
    E["title"] = E.title.fillna("")
    cal = np.array(sorted(cal)); calset = set(cal)
    hm = E.hm.astype(int); trd = E.day.isin(calset)
    nxt = cal[np.minimum(np.searchsorted(cal, E.day.values, side="right"), len(cal) - 1)]
    E["gapday"] = np.where(trd & (hm < 900), E.day, np.where(trd & (hm >= 900) & (hm <= 1530), "", nxt))
    return E


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def titles():
    d1 = pickle.load(open(OUTD / "t1.pkl", "rb"))
    T, cal = d1["T"].copy(), d1["cal"]
    E = kind_events(cal)
    E = E[E.gapday != ""]
    E["t"] = E.title.map(norm)
    G = E.groupby(["kcode", "gapday"]).t.apply(list)
    T["k5"] = T.ticker.str[:5]
    T["titles"] = [G.get((k, d), []) for k, d in zip(T.k5, T.date)]
    U = sorted({t for L in T.titles for t in L})
    nh = int((T.titles.str.len() > 0).sum())
    print("T1 거래 %d · 갭 구간 공시 있음 %d (%.1f%%) · 공시 %d건 · 서로 다른 제목 %d" % (
        len(T), nh, nh / len(T) * 100, int(T.titles.str.len().sum()), len(U)))
    pickle.dump(dict(T=T[["ticker", "date", "gap", "rgap", "r", "titles"]], U=U), open(FT, "wb"))


def _client():
    import anthropic, common as C
    return anthropic.Anthropic(api_key=C.env()["ANTHROPIC_API_KEY"])


def submit():
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    U = pickle.load(open(FT, "rb"))["U"]
    done = set(pickle.load(open(FL, "rb"))) if FL.exists() else set()
    todo = [t for t in U if t not in done]
    chunks = [todo[i:i + PER_REQ] for i in range(0, len(todo), PER_REQ)]
    lim = int(sys.argv[2]) if len(sys.argv) > 2 else len(chunks)
    chunks = chunks[:lim]
    est_in = sum(len(SYSTEM) + sum(len(t) + 6 for t in ch) for ch in chunks) / 1.5     # 한글 대략 1.5자/토큰
    est_out = sum(len(ch) * 22 for ch in chunks)
    print("제목 %d개 · 요청 %d개 · 예상 입력 %.0f천·출력 %.0f천 토큰 → 약 $%.2f(묶음 반값, 생각 토큰 제외)" % (
        sum(map(len, chunks)), len(chunks), est_in / 1e3, est_out / 1e3, (est_in * PRICE[0] + est_out * PRICE[1]) / 1e6 / 2))
    if not chunks: return
    reqs, idmap = [], {}
    for k, ch in enumerate(chunks):
        cid = "c%05d" % k; idmap[cid] = ch
        body = "\n".join("%d: %s" % (i, t) for i, t in enumerate(ch))
        reqs.append(Request(custom_id=cid, params=MessageCreateParamsNonStreaming(
            model=MODEL, max_tokens=16000, system=SYSTEM, output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": "공시 제목 %d개:\n%s" % (len(ch), body)}])))
    b = _client().messages.batches.create(requests=reqs)
    FB.write_text(json.dumps({"id": b.id, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "idmap": idmap}, ensure_ascii=False), encoding="utf-8")
    print("보냄:", b.id, b.processing_status)


def fetch():
    J = json.loads(FB.read_text(encoding="utf-8"))
    cl = _client()
    b = cl.messages.batches.retrieve(J["id"])
    print("상태:", b.processing_status, b.request_counts)
    if b.processing_status != "ended": return
    lab = pickle.load(open(FL, "rb")) if FL.exists() else {}
    tin = tout = 0; bad = 0
    for res in cl.messages.batches.results(J["id"]):
        ch = J["idmap"][res.custom_id]
        if res.result.type != "succeeded": bad += len(ch); print("실패", res.custom_id, res.result.type); continue
        m = res.result.message
        tin += m.usage.input_tokens; tout += m.usage.output_tokens
        if m.stop_reason != "end_turn": bad += len(ch); print("멈춤", res.custom_id, m.stop_reason); continue
        txt = next((x.text for x in m.content if x.type == "text"), "")
        try: items = json.loads(txt)["items"]
        except Exception: bad += len(ch); print("JSON 오류", res.custom_id); continue
        got = {int(x["i"]): x for x in items if 0 <= int(x["i"]) < len(ch)}
        for i, t in enumerate(ch):
            if i in got: lab[t] = (got[i]["cat"], int(got[i]["sev"]))
            else: bad += 1
    usd = (tin * PRICE[0] + tout * PRICE[1]) / 1e6 / 2
    with open(USAGE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "batch": J["id"], "model": MODEL, "in": tin, "out": tout, "usd": round(usd, 4)}) + "\n")
    pickle.dump(lab, open(FL, "wb"))
    print("라벨 %d개(이번 빠짐 %d) · 토큰 입력 %d·출력 %d · $%.2f" % (len(lab), bad, tin, tout, usd))


# ── 판정 ──
def pair_stats(z, h):
    """h=True(문제 거래) vs False. 같은 날 짝 = 날마다 (False 평균 - True 평균)."""
    y, n = z.r[h], z.r[~h]
    dd = z.assign(h=h).groupby(["date", "h"]).r.mean().unstack()
    pdiff = (dd[False] - dd[True]).dropna() if (True in dd.columns and False in dd.columns) else pd.Series(dtype=float)
    t = pdiff.mean() / pdiff.std() * np.sqrt(len(pdiff)) if len(pdiff) > 5 and pdiff.std() > 0 else np.nan
    return dict(nh=int(h.sum()), yes=y.mean() if len(y) else np.nan, no=n.mean() if len(n) else np.nan,
                win=(y > 0).mean() * 100 if len(y) else np.nan, pair=pdiff.mean() if len(pdiff) else np.nan, npair=len(pdiff), t=t)


def rep():
    from verdict import log_trials
    D = pickle.load(open(FT, "rb")); T = D["T"].copy(); lab = pickle.load(open(FL, "rb"))
    miss = [t for t in D["U"] if t not in lab]
    T["sevs"] = [[lab[t][1] for t in L if t in lab] for L in T.titles]
    T["cats"] = [[lab[t][0] for t in L if t in lab] for L in T.titles]
    T["has"] = T.titles.str.len() > 0
    T["smax"] = [max(s) if s else -1 for s in T.sevs]
    S = (("학습 2016~22", "20160101", "20221231"), ("검증 2023~", "20230101", "20991231"))
    out = []; P = lambda s="": (out.append(s), print(s, flush=True))
    P("# 공시 제목 AI 분류 × [갭하락 조용주] — H0423 · 2026-11-15"); P("")
    P("- 모델 %s(묶음 처리) · 서로 다른 제목 %d개 중 라벨 %d개(빠짐 %d) · 제목만 줌(회사·날짜·주가 없음)" % (MODEL, len(D["U"]), len(lab), len(miss)))
    P("- 거래 %d건(연구 일봉판, 시가 매수 → 종가 매도, 비용 0.23 뒤) · 갭 구간 공시 있음 %d건" % (len(T), int(T.has.sum()))); P("")
    # 라벨 분포
    LT = pd.DataFrame([(t, c, s) for t, (c, s) in lab.items()], columns=["t", "cat", "sev"])
    P("## 라벨 분포(서로 다른 제목 기준)"); P("")
    P("| 분류 | 제목 수 | sev 0 | 1 | 2 | 3 |"); P("|---|---|---|---|---|---|")
    for c in CATS:
        z = LT[LT.cat == c]
        P("| %s | %d | %s |" % (c, len(z), " | ".join(str(int((z.sev == s).sum())) for s in range(4))))
    P("")
    P("## ① 무게별 성적(거래 단위, 거래의 가장 무거운 공시 기준)"); P("")
    P("| 구간 | 공시 없음 | 가장 무거운 sev 0 | 1 | 2 | 3 |"); P("|---|---|---|---|---|---|")
    for nm, a, b in S:
        z = T[(T.date >= a) & (T.date <= b)]
        cells = ["%+.2f (%d)" % (z.r[~z.has].mean(), int((~z.has).sum()))]
        for s in range(4):
            k = z.smax == s; cells.append("%+.2f (%d)" % (z.r[k].mean(), int(k.sum())) if k.any() else "-")
        P("| %s | %s |" % (nm, " | ".join(cells)))
    P("")
    P("## ② 미리 정한 판정 — 같은 날 짝(없음 평균 − 비교 쪽 평균, 플러스 = 비교 쪽이 약함)"); P("")
    P("| 비교 | 구간 | 비교 쪽 건수 | 비교 쪽 평균 | 공시 없음 평균 | 승률 | 같은 날 짝 | 날 | t |"); P("|---|---|---|---|---|---|---|---|---|")
    R = {}
    tests = (("가벼운 공시만(sev≤1) vs 공시 없음", lambda z: z[(~z.has) | (z.smax.between(0, 1))], lambda z: z.has.values),
             ("무거운 공시(sev≥2) vs 공시 없음", lambda z: z[(~z.has) | (z.smax >= 2)], lambda z: z.has.values),
             ("무거운(sev≥2) vs 가벼운(sev≤1)", lambda z: z[z.has & (z.smax >= 0)], lambda z: (z.smax >= 2).values))
    for tn, sel, hf in tests:
        for nm, a, b in S:
            z = sel(T[(T.date >= a) & (T.date <= b)])
            r = pair_stats(z, hf(z)); R[(tn, nm)] = r
            P("| %s | %s | %d | %+.2f | %+.2f | %.0f%% | %+.2f | %d | %.1f |" % (tn, nm, r["nh"], r["yes"], r["no"], r["win"], r["pair"], r["npair"], r["t"]))
    P("")
    P("## ③ 분류별(거래에 그 분류 공시가 하나라도 있으면)"); P("")
    P("| 분류 | 학습 건수·평균 | 검증 건수·평균 |"); P("|---|---|---|")
    for c in CATS:
        cells = []
        for nm, a, b in S:
            z = T[(T.date >= a) & (T.date <= b)]; k = np.array([c in L for L in z.cats])
            cells.append("%d · %+.2f" % (k.sum(), z.r[k].mean()) if k.any() else "0")
        P("| %s | %s |" % (c, " | ".join(cells)))
    P("")
    a1, a2 = R[("가벼운 공시만(sev≤1) vs 공시 없음", S[0][0])], R[("가벼운 공시만(sev≤1) vs 공시 없음", S[1][0])]
    h1, h2 = R[("무거운 공시(sev≥2) vs 공시 없음", S[0][0])], R[("무거운 공시(sev≥2) vs 공시 없음", S[1][0])]
    okA = all(x["pair"] <= 0.15 and (np.isnan(x["t"]) or x["t"] < 1.5) for x in (a1, a2))
    okB = h1["pair"] > 0 and h1["t"] >= 2 and h2["pair"] > 0
    P("## 판정(미리 정한 기준)"); P("")
    P("- ① 가벼운 공시만 있는 거래가 공시 없는 거래와 같은가(학습·검증 둘 다 같은 날 짝 ≤ +0.15 이고 t < 1.5): **%s** (학습 %+.2f t%.1f · 검증 %+.2f t%.1f)" % (
        "통과" if okA else "실패", a1["pair"], a1["t"], a2["pair"], a2["t"]))
    P("- ② 무거운 공시 거래가 약한가(학습 짝 > 0·t ≥ 2, 검증 짝 > 0): **%s** (학습 %+.2f t%.1f · 검증 %+.2f t%.1f)" % (
        "통과" if okB else "실패", h1["pair"], h1["t"], h2["pair"], h2["t"]))
    P("- 둘 다 통과해야 '무거운 공시만 빼기'로 바꿀 후보(다음 단계 = 계좌 시험 kind_t1_acct 방식). 하나라도 실패면 지금(공시 있으면 전부 빼기) 유지.")
    (ROOT / "reports" / "kind_llm_1115.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    log_trials("kind_llm_1115", 6)                                # H0423 3비교×2구간
    print("보고서 research/reports/kind_llm_1115.md")


if __name__ == "__main__":
    {"titles": titles, "submit": submit, "fetch": fetch, "rep": rep}[cmd]()
