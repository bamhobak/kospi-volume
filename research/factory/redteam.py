# -*- coding: utf-8 -*-
"""적대적 검토관 — 규칙 후보를 '깨 보려고' 정해 둔 함정 검사를 스크립트로 전부 돌린다 (2026-11-12 사용자 아이디어 ③).

계기: [예상 하회](F1659)를 오른 장 3일 그림자만 보고 채택 → 녹화 23일로 다시 재니 100만 실금액이면 손해(같은 날 뺌).
원칙: **숫자는 전부 이 스크립트가 낸다. AI 는 그 숫자(JSON)를 읽고 판정 문장만 쓴다** — 문장 속 숫자가 JSON 에 없으면 그 문장을 버리고
      스크립트 요약으로 갈음한다(지어낸 숫자 차단).
함정(메모리 backtest-pitfalls + 11-12 교훈):
  ① 표본 날 수          ② 고른 기간과 시험 기간 겹침(그 구간 빼고 다시)   ③ 뒤집은 짝도 버는가
  ④ 같은 날 시장 대비    ⑤ 체결 손해 뒤(50만·100만)                       ⑥ 오른 장/내린 장 나눠서
  ⑦ 위 10건 빼고         ⑧ 하루·한 달 몰림                                 ⑨ 다중검정(공장 누적 시험 수, 하루 초과 시계열)
  ⑩ 미래 정보 섞임(재료 시각 vs 매수 시각)   ⑪ 같은 종목 겹쳐 세기(보유 중 재신호)   ⑫ 체결 불가(상·하한가 근처)
판정: 빨강 하나라도 → '막음' · 노랑만 → '주의' · 없으면 '통과'.
쓰는 곳: fshadow 통과 직전(review_spec) · 밤 연구 일꾼 결과(review) · 손으로 `python research/factory/redteam.py spec F1659` / `case-f1659`.
기록: research/reports/redteam/<이름>_<날짜>.md·.json · AI 비용은 data/factory/llm_usage.jsonl(task '검토관…') — 검토관+밤 연구 합쳐 한 달 $20 묶음.
"""
import json, math, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent.parent
for p in (str(HERE), str(BASE)):
    if p not in sys.path: sys.path.insert(0, p)
import numpy as np, pandas as pd

RD = BASE / "research" / "reports" / "redteam"; RD.mkdir(parents=True, exist_ok=True)
USAGE = BASE / "data" / "factory" / "llm_usage.jsonl"
MONTH_CAP = 20.0                                    # 검토관 + 밤 연구 일꾼 API 합계(달러/달) — 구독(claude -p)은 0 원
CAP_TASKS = ("검토관", "밤 연구")
AMTS = (50e4, 100e4)
IMP_A, IMP_B, FILL_C = 0.143, 1.321, 3.0            # t1_size_liq_1021 실측 맞춤(11-12) — fshadow 와 같은 값
# 문턱 — 결과 보기 전에 정한 값(11-12). 바꾸면 이 줄에 날짜·이유를 남길 것.
TH = dict(days_red=10, days_yel=20, overlap_red=0.5, ex_t_yel=2.0, top10_drop_yel=0.5, day_share_red=0.5, day_share_yel=0.3,
          month_share_red=0.6, up_share_red=0.7, dsr_red=0.5, dsr_yel=0.9, lim_red=0.05, repeat_yel=0.3)


# ── 숫자 ─────────────────────────────────────────────────────────────
def _impact(T, amt):
    a = T["amt20"].astype(float) * 1e8 if "amt20" in T.columns else pd.Series(np.nan, index=T.index)
    if a.isna().all(): return None
    a = a.fillna(a.median())
    p = amt / a * 100
    loss = np.maximum(0, IMP_A + IMP_B * np.sqrt(p)); fill = 1 / (1 + FILL_C * p)
    net = T.ret.astype(float) - loss
    daily = (amt * fill * net / 100).groupby(T.date).sum()
    sd = daily.std(ddof=1) if len(daily) > 1 else np.nan
    return dict(net=float((net * fill).sum() / fill.sum()), pnl=float(daily.mean()), t=float(daily.mean() / sd * math.sqrt(len(daily))) if sd and sd > 0 else 0.0,
                worst=float(daily.min()), buy_max=float(amt * T.groupby("date").size().max()))


def _ex(T, mkt):
    b = T.groupby("date").ret.mean()
    e = (b - mkt.reindex(b.index)).dropna() if mkt is not None else pd.Series(dtype=float)
    if not len(e): return None, e
    sd = e.std(ddof=1) if len(e) > 1 else np.nan
    return dict(ex=float(e.mean()), t=float(e.mean() / sd * math.sqrt(len(e))) if sd and sd > 0 else 0.0, pos=int((e > 0).sum()), days=int(len(e))), e


def _basic(T):
    d = T.groupby("date").ret.mean()
    return dict(n=int(len(T)), days=int(T.date.nunique()), mean=float(T.ret.mean()), win=float((T.ret > 0).mean() * 100),
                perday=float(len(T) / max(T.date.nunique(), 1)), dmean=float(d.mean()))


def _when_ok(conds, mode):
    """재료 시각이 매수 시각보다 늦지 않은가 — (빨강 목록, 노랑 목록)."""
    try:
        import feats as FT
    except Exception:
        return [], []
    allow = (FT.MODES.get(mode) or (None, set()))[1]
    red, yel = [], []
    for c in conds or []:
        f = c.get("f"); w = (FT.FEATS.get(f) or (None, None))[1]
        if w == "live": w = "open" if f.startswith("a_") else "close" if f.startswith("c_") else w
        if w and allow and w not in allow: red.append("%s(%s)" % (f, w))
        elif w == "open" and mode in ("oc",) or (w == "open" and mode.startswith("sw")):
            yel.append(f)
    return red, yel


def checks(T, mkt=None, twin=None, sel=None, mode="oc", conds=None, n_trials=None, hold=1):
    """T: date(str)·ticker·ret(비용 뒤 %)·[amt20 억원]·[gap %] · mkt: date→같은 날 시장 평균(같은 비용) · twin: 뒤집은 짝 T · sel: (고른 기간 시작, 끝)."""
    T = T.copy(); T["date"] = T.date.astype(str)
    if mkt is not None: mkt = pd.Series(mkt).copy(); mkt.index = mkt.index.astype(str)
    R = dict(basic=_basic(T), checks=[])
    add = lambda k, name, lvl, val, note: R["checks"].append(dict(k=k, name=name, level=lvl, val=val, note=note))
    b = R["basic"]
    # ① 날 수
    add("days", "표본 날 수", "빨강" if b["days"] < TH["days_red"] else "노랑" if b["days"] < TH["days_yel"] else "초록",
        dict(days=b["days"], n=b["n"]), "%d일 · %d건 (빨강 < %d일 · 노랑 < %d일)" % (b["days"], b["n"], TH["days_red"], TH["days_yel"]))
    exd, e = _ex(T, mkt)
    R["ex"] = exd
    # ② 고른 기간 겹침
    if sel:
        ins = T.date.between(str(sel[0]), str(sel[1]))
        share = float(T[ins].date.nunique() / max(b["days"], 1))
        out = _ex(T[~ins], mkt)[0] if (~ins).any() else None
        lvl = "빨강" if share >= TH["overlap_red"] and (out is None or out["ex"] <= 0 or out["days"] < TH["days_red"]) else "노랑" if share > 0 else "초록"
        add("overlap", "고른 기간과 겹침", lvl, dict(share=share, sel=list(map(str, sel)), out=out),
            "시험 날의 %.0f%%가 고른 기간(%s~%s) 안 · 그 구간 뺀 시장 대비 %s" % (share * 100, sel[0], sel[1],
            ("%+.2f%%p(%d일)" % (out["ex"], out["days"])) if out else "남는 날 없음"))
    # ③ 뒤집은 짝
    if twin is not None and len(twin):
        tw = twin.copy(); tw["date"] = tw.date.astype(str)
        tx = _ex(tw, mkt)[0]; tb = _basic(tw)
        own = (exd or {}).get("ex")
        lvl = "빨강" if (tx and own is not None and tx["ex"] >= own) else "노랑" if tb["mean"] > 0 else "초록"
        add("twin", "뒤집은 짝", lvl, dict(twin_mean=tb["mean"], twin_ex=(tx or {}).get("ex"), own_ex=own),
            "짝 건당 %+.2f%% · 시장 대비 %s (내 쪽 %s) — 짝도 벌면 장이 오른 것" % (tb["mean"], ("%+.2f%%p" % tx["ex"]) if tx else "-", ("%+.2f%%p" % own) if own is not None else "-"))
    # ④ 시장 대비
    if exd:
        add("market", "같은 날 시장 대비", "빨강" if exd["ex"] <= 0 else "노랑" if exd["t"] < TH["ex_t_yel"] else "초록", exd,
            "%+.2f%%p · t %.1f · 플러스 날 %d/%d" % (exd["ex"], exd["t"], exd["pos"], exd["days"]))
    else:
        add("market", "같은 날 시장 대비", "노랑", None, "시장 값 없음 — 못 잼")
    # ⑤ 체결 손해
    imp = {int(a / 1e4): _impact(T, a) for a in AMTS}
    R["impact"] = imp
    i50, i100 = imp.get(50), imp.get(100)
    if i50:
        lvl = "빨강" if i50["pnl"] <= 0 else "노랑" if (i100 and i100["pnl"] <= 0) else "초록"
        add("impact", "체결 손해 뒤", lvl, imp, "50만씩 건당 %+.2f%% · 하루 %+.1f만(t %.1f) / 100만씩 건당 %+.2f%% · 하루 %+.1f만 · 매수 대기 최대 %.0f만" % (
            i50["net"], i50["pnl"] / 1e4, i50["t"], i100["net"], i100["pnl"] / 1e4, i100["buy_max"] / 1e4))
    else:
        add("impact", "체결 손해 뒤", "노랑", None, "거래대금 값 없음 — 못 잼")
    # ⑥ 오른 장 / 내린 장
    if mkt is not None:
        d = T.groupby("date").ret.mean(); m = mkt.reindex(d.index)
        up, dn = d[m > 0], d[m <= 0]
        upshare = float(len(up) / max(len(d), 1))
        exu = float((up - m[up.index]).mean()) if len(up) else None; exn = float((dn - m[dn.index]).mean()) if len(dn) else None
        lvl = "빨강" if (upshare >= TH["up_share_red"] and (not len(dn) or dn.mean() < 0)) else "노랑" if (exn is not None and exn <= 0) or (exu is not None and exu <= 0) else "초록"
        add("regime", "오른 장/내린 장", lvl, dict(up_days=int(len(up)), down_days=int(len(dn)), up_share=upshare, up_mean=float(up.mean()) if len(up) else None,
            down_mean=float(dn.mean()) if len(dn) else None, up_ex=exu, down_ex=exn),
            "오른 날 %d일 건당 %s · 내린 날 %d일 건당 %s (오른 날 비율 %.0f%%)" % (len(up), ("%+.2f%%" % up.mean()) if len(up) else "-", len(dn),
            ("%+.2f%%" % dn.mean()) if len(dn) else "-", upshare * 100))
    # ⑦ 위 10건 빼고
    if len(T) > 20:
        cut = float(T.ret.sort_values().iloc[:-10].mean())
        drop = (b["mean"] - cut) / b["mean"] if b["mean"] > 0 else 0.0
        add("top10", "위 10건 빼고", "빨강" if cut <= 0 else "노랑" if drop >= TH["top10_drop_yel"] else "초록", dict(mean=b["mean"], cut=cut),
            "건당 %+.2f%% → %+.2f%%" % (b["mean"], cut))
    # ⑧ 몰림
    pos = T.groupby("date").ret.sum()
    if pos.sum() > 0:
        dsh = float(pos.max() / pos.sum())
        mon = pos.groupby(pos.index.str[:6]).sum(); msh = float(mon.max() / mon.sum()) if mon.sum() > 0 and len(mon) > 1 else None
        lvl = "빨강" if dsh >= TH["day_share_red"] or (msh is not None and msh >= TH["month_share_red"]) else "노랑" if dsh >= TH["day_share_yel"] else "초록"
        add("conc", "하루·한 달 몰림", lvl, dict(best_day_share=dsh, best_month_share=msh, best_day=str(pos.idxmax())),
            "가장 좋은 날(%s) 몫 %s%s" % (pos.idxmax(), "그날 빼면 합계 마이너스" if dsh > 1 else "%.0f%%" % (dsh * 100),
            (" · 가장 좋은 달 몫 %s" % ("그 달 빼면 합계 마이너스" if msh > 1 else "%.0f%%" % (msh * 100))) if msh is not None else ""))
    else:
        add("conc", "하루·한 달 몰림", "빨강", None, "합계가 0 이하")
    # ⑨ 다중검정
    try:
        from verdict import deflated_sharpe, trial_count
        N = n_trials or max(trial_count("factory"), 1)
        dd = deflated_sharpe(e if len(e) else T.groupby("date").ret.mean(), N)
    except Exception:
        N, dd = n_trials, None
    if dd:
        add("dsr", "다중검정", "빨강" if dd["dsr"] < TH["dsr_red"] else "노랑" if dd["dsr"] < TH["dsr_yel"] else "초록", dict(dsr=dd["dsr"], n_trials=N, T=dd["T"]),
            "진짜일 확률 %.2f (시험 %s개 기준 · 하루 초과 %d개)" % (dd["dsr"], f"{N:,}" if N else "-", dd["T"]))
    else:
        add("dsr", "다중검정", "노랑", dict(n_trials=N), "날 수 12 미만 — 못 잼")
    # ⑩ 미래 정보
    red, yel = _when_ok(conds, mode)
    if conds is not None:
        add("lookahead", "미래 정보", "빨강" if red else "노랑" if yel else "초록", dict(late=red, at_open=yel),
            ("매수 뒤에야 아는 재료 " + ", ".join(red)) if red else ("시가로 고르고 시가에 산다고 침(실전은 몇 초 뒤) " + ", ".join(yel)) if yel else "재료 시각 문제 없음")
    # ⑪ 겹쳐 세기
    if hold > 1:
        S = T.sort_values(["ticker", "date"]); ds = sorted(T.date.unique()); di = {d: i for i, d in enumerate(ds)}
        gaps = S.groupby("ticker").date.apply(lambda z: np.diff([di[x] for x in z])).explode().dropna()
        rep = float((gaps.astype(int) < hold).mean()) if len(gaps) else 0.0
        add("repeat", "같은 종목 겹쳐 세기", "노랑" if rep >= TH["repeat_yel"] else "초록", dict(share=rep, uniq=int(T.ticker.nunique())),
            "보유 중 재신호 %.0f%% · 고유 종목 %d" % (rep * 100, T.ticker.nunique()))
    # ⑫ 체결 불가
    if "gap" in T.columns:
        lim = float((T.gap.astype(float).abs() >= 29).mean())
        add("limit", "체결 불가(상·하한가)", "빨강" if lim >= TH["lim_red"] else "초록", dict(share=lim), "시가가 ±29%% 근처 %.1f%%" % (lim * 100))
    lv = [c["level"] for c in R["checks"]]
    R["verdict"] = "막음" if "빨강" in lv else "주의" if "노랑" in lv else "통과"
    R["th"] = TH
    return R


# ── 문장(AI) ─────────────────────────────────────────────────────────
def _nums(o, out):
    if isinstance(o, dict): [_nums(v, out) for v in o.values()]
    elif isinstance(o, (list, tuple)): [_nums(v, out) for v in o]
    elif isinstance(o, (int, float)) and o == o and not isinstance(o, bool):
        out.add(float(o))
    elif isinstance(o, str):
        for m in re.findall(r"[-+]?\d[\d,]*\.?\d*", o):
            try: out.add(float(m.replace(",", "")))
            except ValueError: pass
    return out


def _num_ok(text, R):
    """문장 속 숫자가 전부 R(스크립트 결과) 안의 숫자와 맞나(표시 반올림·%·만원·배율 허용)."""
    pool = _nums(R, set())
    cand = set()
    for v in pool:
        for k in (1, 100, 1e-4):                       # 그대로 · 비율→% · 원→만원
            cand.add(round(v * k, 2)); cand.add(round(v * k, 1)); cand.add(round(v * k)); cand.add(abs(round(v * k, 2))); cand.add(abs(round(v * k, 1))); cand.add(abs(round(v * k)))
    bad = []
    for m in re.findall(r"[-+]?\d[\d,]*\.?\d*", text):
        try: x = float(m.replace(",", ""))
        except ValueError: continue
        if x in (1, 2, 3, 4, 5, 10) or any(abs(abs(x) - abs(c)) <= max(0.051, abs(c) * 0.005) for c in cand): continue
        bad.append(m)
    return not bad, bad


def _cap_spent(ym=None):
    ym = ym or time.strftime("%Y-%m")
    if not USAGE.exists(): return 0.0
    s = 0.0
    for l in USAGE.read_text(encoding="utf-8").splitlines():
        try: j = json.loads(l)
        except Exception: continue
        if j.get("ts", "")[:7] == ym and str(j.get("task", "")).startswith(CAP_TASKS): s += float(j.get("usd") or 0)
    return s


SYS = ("너는 주식 데이 규칙 후보를 '깨 보려는' 검토관이다. 아래 JSON 은 스크립트가 실제로 잰 함정 검사 결과다.\n"
       "할 일: 한국어 반말로 3~5줄. 첫 줄은 '막음/주의/통과' 판정과 가장 큰 이유 하나. 그다음 줄마다 빨강·노랑 함정을 쉬운 말로.\n"
       "규칙: 숫자는 JSON 에 있는 것만 그대로 쓴다(새 숫자·추정·계산 금지). 전문용어 금지. 칭찬·존댓말·설명 꼬리 금지. 판정(verdict)을 바꾸지 마라.")


def _plain(R):
    bad = [c for c in R["checks"] if c["level"] != "초록"]
    bad.sort(key=lambda c: c["level"] != "빨강")
    return "\n".join(["%s — %s" % (R["verdict"], bad[0]["name"] if bad else "함정 없음")] + ["%s %s: %s" % ("🔴" if c["level"] == "빨강" else "🟡", c["name"], c["note"]) for c in bad[:6]])


def sentence(R, ai=True):
    """(문장, 출처) — 구독 sonnet 먼저(돈 0) → 안 되면 API 하이쿠(한 달 $20 묶음) → 안 되면 스크립트 요약."""
    if not ai: return _plain(R), "스크립트"
    user = json.dumps(dict(verdict=R["verdict"], basic=R["basic"], checks=R["checks"]), ensure_ascii=False, default=str)
    txt, src = None, None
    try:
        import claude_sub as CS
        t0 = time.time(); ok, out = CS.run(SYS + "\n\n---\n" + user, model="sonnet", timeout=300, effort="low")
        if ok:
            txt, src = out.strip(), "구독"
            with open(USAGE, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "model": "구독(claude -p)", "task": "검토관(구독)", "in": len(user), "out": len(out),
                                    "cw": 0, "cr": 0, "usd": 0.0, "sec": round(time.time() - t0, 1)}, ensure_ascii=False) + "\n")
    except Exception:
        txt = None
    if txt is None and _cap_spent() < MONTH_CAP:
        try:
            import harvest
            txt, src = harvest.ask("claude-haiku-5-5", SYS, user, task="검토관", max_tokens=800, think=False).strip(), "API"
        except Exception:
            txt = None
    if not txt: return _plain(R), "스크립트"
    ok, bad = _num_ok(txt, R)
    if not ok:
        return _plain(R) + "\n(AI 문장은 JSON 에 없는 숫자 %s 를 써서 버림)" % ", ".join(bad[:5]), "스크립트"
    if R["verdict"] not in txt.splitlines()[0]:
        return _plain(R) + "\n(AI 문장이 판정을 바꿔 버림)", "스크립트"
    return txt, src


# ── 묶음 ─────────────────────────────────────────────────────────────
def review(name, T, mkt=None, twin=None, sel=None, mode="oc", conds=None, n_trials=None, hold=1, ai=True, tag=None, note=""):
    """함정 검사 + 판정 문장 → 보고서. 반환 R(verdict·checks·text·md 경로)."""
    R = checks(T, mkt=mkt, twin=twin, sel=sel, mode=mode, conds=conds, n_trials=n_trials, hold=hold)
    R["text"], R["text_src"] = sentence(R, ai=ai)
    R["name"] = name; R["at"] = time.strftime("%Y-%m-%d %H:%M"); R["note"] = note
    stem = re.sub(r"[^\w가-힣.-]+", "_", "%s_%s%s" % (name, time.strftime("%Y%m%d_%H%M"), ("_" + tag) if tag else ""))
    L = ["# 검토관 — %s (%s)" % (name, R["at"]), "", "**판정: %s**%s" % (R["verdict"], (" · " + note) if note else ""), "",
         "건수 %d · 날 %d · 건당 %+.2f%% · 승률 %.0f%% · 하루 %.1f종목" % (R["basic"]["n"], R["basic"]["days"], R["basic"]["mean"], R["basic"]["win"], R["basic"]["perday"]), "",
         "| 함정 | 판정 | 숫자 |", "|---|---|---|"] + ["| %s | %s | %s |" % (c["name"], c["level"], c["note"]) for c in R["checks"]] + \
        ["", "## 검토관 말 (%s)" % R["text_src"], "", R["text"], "", "> 숫자는 전부 스크립트(redteam.py checks)가 낸 값 · 문턱 TH 는 11-12 미리 정함"]
    md = RD / (stem + ".md"); md.write_text("\n".join(L) + "\n", encoding="utf-8")
    (RD / (stem + ".json")).write_text(json.dumps(R, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    R["md"] = str(md)
    return R


def tg_line(R):
    """텔레그램 한 줄(핵심만)."""
    red = [c["name"] for c in R["checks"] if c["level"] == "빨강"]; yel = [c["name"] for c in R["checks"] if c["level"] == "노랑"]
    return "🛡 검토관 %s: %s%s%s" % (R["name"], R["verdict"], (" · 🔴 " + "·".join(red)) if red else "", (" · 🟡 " + "·".join(yel[:4])) if yel else "")


# ── 공장 그림자 명세용 ───────────────────────────────────────────────
def sel_of(x, dates):
    """명세가 '고른 기간' — 정답지(최근 20거래일)면 만든 날 앞 20거래일, 깔때기(학습·검증 통과)면 그 학습·검증 구간."""
    src = str(x.get("source") or "")
    if x.get("origin") in ("answer", "invert") or "최근" in src:
        cr = str(x.get("created") or "")[:10].replace("-", "")
        m = re.search(r"최근\s*(\d+)\s*거래일", src) or (re.search(r"최근\s*(\d+)\s*거래일", str((x.get("res") or {}).get("why") or "")))
        k = int(m.group(1)) if m else 20
        before = [d for d in dates if d < cr]
        return (before[-k], before[-1]) if len(before) >= 1 else None
    try:
        import lab
        _, TR, VA = lab.periods(x)
        return (TR[0], VA[1])
    except Exception:
        return None


def review_spec(x, L, allT, M, dates=None, ai=True):
    """fshadow 판정 직전에 부른다 — x: 명세 · L: 전체 명세 · allT: shadow_trades · M: shadow_mkt. 반환 R(verdict)."""
    import fshadow as F
    T = allT[allT.id == x["id"]].copy()
    tw = F.twin_of(x, L)
    TW = allT[allT.id == tw["id"]].copy() if tw is not None else None
    mk = M[M["mode"] == x["mode"]].set_index("date").mkt if M is not None and len(M) else None
    dates = dates or sorted(set(allT.date.astype(str)))
    hold = int(x["mode"][2:]) if x["mode"].startswith("sw") else 1
    R = review(x["id"], T, mkt=mk, twin=TW, sel=sel_of(x, dates), mode=x["mode"], conds=x.get("conds"), hold=hold, ai=ai, tag="shadow",
               note=(x.get("desc") or "")[:120])
    x["redteam"] = dict(verdict=R["verdict"], md=R["md"], at=R["at"])
    return R


def review_lab(x, U=None, ai=True):
    """깔때기(G1·G2) 통과로 '검토 대기'가 된 명세 — 검증 구간(2023~) 거래로 함정 검사. 고른 기간 = 학습 구간."""
    import lab, feats as FT
    U = lab.hist() if U is None else U
    _, TR, VA = lab.periods(x)
    tgt = FT.TARGET[x["mode"]]
    cost = FT.COST if x["mode"] in ("oc", "on") else (FT.COST + FT.INTRA_SLIP) if x["mode"].startswith("m") else 0.0
    T = lab.seg(lab.trades(U, x), *VA)
    TW = lab.seg(lab.trades(U, lab.invert(x)), *VA)
    Uv = U[(U.date >= VA[0]) & (U.date <= VA[1])]
    mk = Uv.groupby("date")[tgt].apply(lambda z: z.astype(float).clip(-60, 60).mean()) - cost
    cols = [c for c in ("date", "ticker", "ret", "amt20", "gap") if c in T.columns or c in ("amt20", "gap")]
    if "amt20" not in T.columns or "gap" not in T.columns:
        T = T.merge(Uv[["date", "ticker"] + [c for c in ("amt20", "gap") if c in Uv.columns and c not in T.columns]], on=["date", "ticker"], how="left")
    hold = int(x["mode"][2:]) if x["mode"].startswith("sw") else 1
    R = review(x["id"], T[[c for c in cols if c in T.columns]], mkt=mk, twin=TW, sel=(TR[0], TR[1]), mode=x["mode"], conds=x.get("conds"), hold=hold, ai=ai,
               tag="review", note=(x.get("desc") or "")[:120])
    x["redteam"] = dict(verdict=R["verdict"], md=R["md"], at=R["at"])
    return R


def notify_review(xs, U=None):
    """run.py night 의 '검토 대기 새로' 뒤에 부른다 — 명세마다 검토관 한 줄 텔레그램(중요한 것만: 검토 대기 자체가 드묾)."""
    if not xs: return
    import common as C
    for x in xs:
        try:
            C.tg(tg_line(review_lab(x, U=U)))
        except Exception as ex:
            C.log("검토관 실패", x.get("id"), repr(ex)[:300])


# ── 오늘 사례 ────────────────────────────────────────────────────────
def case_f1659(ai=True):
    """F1659 를 ⓐ 채택 때 본 그림자 3일(11-09~11) ⓑ 녹화 23일 전체로 — 검토관이 ⓐ에서 막았을지."""
    A = pd.read_pickle(BASE / "data" / "a5_tighten_1112.pkl")
    A["date"] = A.date.astype(str); A = A.rename(columns={"t": "ticker"}); A["amt20"] = A.a20 / 1e8
    mkt = A.groupby("date").ret.mean()
    top, bot = A[A.q >= 0.9], A[A.q <= 0.1]
    conds = [{"f": "a_err", "q": True, "op": ">=", "v": 0.9}]
    sel = ("20261009", "20261106")                    # 11-07 01:37 생성 · '최근 20거래일' 정답지
    out = []
    for lab_, d0 in (("ⓐ 채택 때(그림자 3일)", "20261109"), ("ⓑ 녹화 23일 전체", "20261012")):
        T = top[top.date >= d0]; TW = bot[bot.date >= d0]
        R = review("F1659 " + lab_, T[["date", "ticker", "ret", "amt20", "gap"]], mkt=mkt, twin=TW[["date", "ticker", "ret", "amt20"]], sel=sel, mode="oc",
                   conds=conds, ai=ai, tag="case")
        out.append(R)
        print("\n" + tg_line(R)); print(R["text"]); print("→", R["md"])
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[:1] == ["case-f1659"]:
        case_f1659(ai="--no-ai" not in a)
    elif a[:1] == ["spec"] and len(a) > 1:
        import lab, fshadow as F
        L = lab.load(); x = next(y for y in L if y["id"] == a[1])
        allT = pd.read_csv(F.TRF, dtype={"date": str, "ticker": str})
        M = pd.read_csv(F.MKF, dtype={"date": str}) if F.MKF.exists() else None
        R = review_spec(x, L, allT, M, ai="--no-ai" not in a)
        print(tg_line(R)); print(R["text"]); print("→", R["md"])
    else:
        print(__doc__)
