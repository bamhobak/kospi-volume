# -*- coding: utf-8 -*-
"""점검 현황 페이지 자료 — 2026-11-12 사용자 "자동으로 돌아가고 체크하는 것들 … 버튼 하나 만들어서 세세하게 그러나 보기 쉽게".
30분마다(예약 \\BamhobakFactory\\OpsStatus) 서버에 흩어진 자동 작업 상태를 모아 Supabase '__ops__' 에 올린다 → 사이트 ops.html(점검 현황).
  작업표: \\Bamhobak* 예약 작업 전부 + 연구 수집 — 마지막 실행·결과·다음 실행 · 하는 일 한 줄
  시스템별: 사전 등록 판정 · 실전-연구 대조 · 검토관 · 밤 연구 일꾼 · 녹화 넓히기 · 밤 과거 받기 · 체결 손해 · 아침 브리핑 · 점검기(스스로 고친 것) · 공장 그림자
읽기만 한다(주문·파일 고치기 없음).  python research/ops_status.py [dry]
"""
import glob, json, os, re, subprocess, sys, time, datetime as dt
from pathlib import Path
HERE = Path(__file__).resolve().parent; BASE = HERE.parent
sys.path.insert(0, str(BASE)); sys.path.insert(0, str(HERE / "factory"))
LOG = BASE / "data" / "ops_status.log"
if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
import pandas as pd

PS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
D = BASE / "data"

# 작업 → (묶음, 하는 일). 없는 이름은 '기타'
TASK_INFO = {
    "\\BamhobakDay\\NxtPre": ("데이 매매", "[장전 되돌림] 08:00 준비 → 08:41 NXT 장전 지정가 매수 → 08:50 시가 매도 주문"),
    "\\BamhobakDay\\Brief": ("알림", "아침 브리핑 한 통(특이일·시가 매도 예정·어제 실전·매수 가능 금액)"),
    "\\BamhobakDay\\Morning": ("데이 매매", "[갭하락]·[미장 폭락] 장전 예상 갭 → 후보·지정가 시가 주문"),
    "\\BamhobakDay\\Sync": ("데이 매매", "시가 체결 확인·원장 맞추기"),
    "\\BamhobakDay\\CloseWatch": ("데이 매매", "지킴이 — 데이 보유 종가 단일가 매도"),
    "\\BamhobakDay\\CloseWatch2": ("데이 매매", "지킴이 두 번째(못 판 것 다시)"),
    "\\BamhobakDay\\Review": ("데이 매매", "데이 채점·가상 매도·사이트 기록"),
    "\\BamhobakDay\\NxtPreReview": ("데이 매매", "[장전 되돌림] 채점"),
    "\\BamhobakDay\\AuditLive": ("점검", "실전-연구 대조 감사관(원장 왕복 vs 연구 가정가)"),
    "\\BamhobakDay\\AerrMorning": ("데이 매매", "[예상 하회] 매수(11-12 뺌 — 꺼둠)"),
    "\\BamhobakDay\\AerrClose": ("데이 매매", "[예상 하회] 가상 매도(11-12 뺌 — 꺼둠)"),
    "\\BamhobakNxt\\Pick": ("데이 매매", "[장후 낙폭] 19:50 고르기·19:51 NXT 장후 지정가 매수"),
    "\\BamhobakNxt\\Fill": ("데이 매매", "[장후 낙폭] 19:59 못 산 주문 취소·체결 확인"),
    "\\BamhobakNxt\\Close": ("데이 매매", "[장후 낙폭] 마감 처리"),
    "\\BamhobakNxt\\SellOpen": ("데이 매매", "[장후 낙폭] 다음 날 08:50 시가 매도 주문"),
    "\\BamhobakNxt\\Review": ("데이 매매", "[장후 낙폭] 그림자·실전 채점"),
    "\\BamhobakNxt\\Report": ("알림", "[장후 낙폭] 주간 성적표"),
    "\\BamhobakNxt\\DayTop3": ("데이 매매", "[갭하락] 하루 위 3개 그림자(11-12 중단 — 꺼둠)"),
    "\\BamhobakAutoTrade\\KR": ("스윙 매매", "국장 스윙 매수(신호 → 주문)"),
    "\\BamhobakAutoTrade\\SellKR": ("스윙 매매", "국장 스윙 매도"), "\\BamhobakAutoTrade\\SellKR2": ("스윙 매매", "국장 스윙 매도 두 번째"),
    "\\BamhobakAutoTrade\\SellKR3": ("스윙 매매", "국장 스윙 매도 세 번째"),
    "\\BamhobakAutoTrade\\US1": ("스윙 매매", "미장 스윙 매수"), "\\BamhobakAutoTrade\\US2": ("스윙 매매", "미장 스윙 매수 두 번째"),
    "\\BamhobakM1\\DailyKR": ("자료 모으기", "국장 1분봉 그날 전 종목"), "\\BamhobakM1\\DailyUS": ("자료 모으기", "미장 1분봉"),
    "\\BamhobakM1\\Backfill": ("자료 모으기", "1분봉 과거 채우기"), "\\BamhobakM1\\KrxDay": ("자료 모으기", "KRX 정규장 시고저종·수급 올리기(18:40)"),
    "\\BamhobakM1\\KrxDayRefresh": ("자료 모으기", "KRX 지난 날 다시 올리기(14:10)"),
    "\\BamhobakM1\\NightFill": ("자료 모으기", "밤 과거 자료 받기(NXT 장전·장후 1분봉, 20:10~07:30)"),
    "\\BamhobakFactory\\Morning": ("규칙 공장", "전이표(미장 밤사이 → 국장 아침 예상 갭)·장전 호가 녹화"),
    "\\BamhobakFactory\\OpenTick": ("자료 모으기", "녹화 넓히기 — NXT 장전 호가 10단계(08:12·08:25)·시가 직후 체결가"),
    "\\BamhobakFactory\\Check": ("점검", "공장 점검기 + 스스로 고치기"),
    "\\BamhobakFactory\\Close": ("규칙 공장", "마감 단일가 호가 녹화"),
    "\\BamhobakFactory\\Evening": ("규칙 공장", "정답지 역추적·그림자 성적"),
    "\\BamhobakFactory\\ImpactRefit": ("점검", "체결 손해 모형 다시 맞추기(호가 사다리)"),
    "\\BamhobakFactory\\Prereg": ("점검", "사전 등록 자동 판정"),
    "\\BamhobakFactory\\PanelDaily": ("자료 모으기", "연구 패널 매일 잇기"),
    "\\BamhobakFactory\\Night": ("규칙 공장", "AI 수집·깔때기·진화기·밤 보고서·후보 페이지"),
    "\\BamhobakFactory\\HealM1": ("점검", "점검기가 예약한 1분봉 다시 받기(한 번짜리)"),
    "\\BamhobakFactory\\OpsStatus": ("점검", "이 페이지 자료 올리기(30분마다)"),
    "\\kospi-volume-research-daily": ("자료 모으기", "투자자 수급·연구 자료(20:30)"),
    "\\BamhobakInsiderDaily": ("자료 모으기", "내부자 거래 수집"),
}
for i in range(1, 6): TASK_INFO["\\BamhobakAutoTrade\\SellUS%d" % i] = ("스윙 매매", "미장 스윙 매도 %d" % i)
for k in list(TASK_INFO):
    if k.startswith("\\BamhobakFactory\\") and "NightLab" not in k: pass
TASK_INFO.setdefault("\\BamhobakFactory\\NightLab", ("점검", "밤 연구 일꾼(대기 목록 → 사전 등록 → 검토관)"))
TASK_INFO.setdefault("\\BamhobakFactory\\RedTeam", ("점검", "적대적 검토관"))
TASK_INFO.setdefault("\\BamhobakFactory\\NightLabBrief", ("알림", "밤 연구 일꾼 결과 한 줄(돌린 게 있을 때만)"))


def tasks():
    ps = ("Get-ScheduledTask | Where-Object { $_.TaskPath -like '\\Bamhobak*' -or $_.TaskName -in @('kospi-volume-research-daily','BamhobakInsiderDaily') } | ForEach-Object { "
          "$i = $_ | Get-ScheduledTaskInfo; [pscustomobject]@{p=$_.TaskPath + $_.TaskName; st=[string]$_.State; "
          "last=$i.LastRunTime.ToString('yyyy-MM-dd HH:mm'); res=$i.LastTaskResult; nxt=$i.NextRunTime.ToString('yyyy-MM-dd HH:mm')} } | ConvertTo-Json")
    out = subprocess.run([PS, "-NoProfile", "-Command", ps], capture_output=True, timeout=90, creationflags=0x08000000).stdout.decode("utf-8", "replace")
    J = json.loads(out or "[]"); J = J if isinstance(J, list) else [J]
    rows = []
    for x in J:
        g, what = TASK_INFO.get(x["p"], ("기타", ""))
        res = int(x.get("res") or 0)
        last = x.get("last") or ""
        ok = "꺼짐" if x["st"] == "Disabled" else "실행 중" if res == 267009 or x["st"] == "Running" else "첫 실행 전" if last[:4] < "2001" else "정상" if res == 0 else "오류"
        rows.append(dict(path=x["p"], name=x["p"].split("\\")[-1], group=g, what=what, state=ok, res=res,
                         last=last if last[:4] >= "2001" else "", next=(x.get("nxt") or "") if (x.get("nxt") or "")[:4] >= "2001" else ""))
    order = ["데이 매매", "스윙 매매", "자료 모으기", "규칙 공장", "점검", "알림", "기타"]
    rows.sort(key=lambda r: (order.index(r["group"]) if r["group"] in order else 99, r["next"] or "9", r["name"]))
    return rows


def jl(p, d=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return d


def mtime(p):
    try: return dt.datetime.fromtimestamp(Path(p).stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception: return ""


def prereg():
    R = jl(BASE / "research" / "prereg" / "registry.json", {}) or {}
    return [dict(id=i["id"], name=i["name"], status=i.get("status"), start=i.get("start"), need=i.get("need"), extend=i.get("extend"),
                 now=(i.get("last") or {}).get("text") or i.get("why") or "", at=(i.get("last") or {}).get("at", ""),
                 history=i.get("history") or [], doc=i.get("doc", "")) for i in R.get("items", [])]


def audit():
    f = D / "audit" / "live.csv"
    if not f.exists(): return {}
    A = pd.read_csv(f, dtype={"buy_day": str, "sell_day": str, "t": str})
    rn = {"T1": "갭하락", "T2": "갭하락+", "T3": "갭하락++", "T4": "미장 폭락", "T5": "장전 되돌림", "T6": "장후 낙폭"}

    def tab(Z):
        out = []
        for rid, z in Z.groupby("rid"):
            ic = z.in_cond.dropna()
            out.append(dict(rule=rn.get(rid, rid), n=int(len(z)), live=round(float(z.live.mean()), 2), research=round(float(z.research.mean()), 2),
                            gap=round(float(z.gap.mean()), 2), slip_buy=round(float(-z.slip_buy.mean()), 2), slip_sell=round(float(-z.slip_sell.mean()), 2),   # + = 연구보다 유리
                            out=(round(float((ic == 0).mean() * 100)) if len(ic) else None), out_n="%d/%d" % (int((ic == 0).sum()), len(ic)) if len(ic) else ""))
        return out
    days = sorted(A.sell_day.unique())
    last5 = A[A.sell_day.isin(days[-5:])]
    daily = []
    for d in days[-10:][::-1]:
        z = A[A.sell_day == d]
        daily.append(dict(d=d, n=int(len(z)), live=round(float(z.live.mean()), 2), research=round(float(z.research.mean()), 2)))
    return dict(all=tab(A), last5=tab(last5), daily=daily, upd=mtime(f), first=days[0] if days else "", lastday=days[-1] if days else "")


def redteam():
    out = []
    for f in sorted(glob.glob(str(BASE / "research" / "reports" / "redteam" / "*.json")), key=os.path.getmtime)[-12:][::-1]:
        J = jl(f, {}) or {}
        out.append(dict(name=J.get("name") or Path(f).stem, at=J.get("at", ""), verdict=J.get("verdict", ""),
                        text=(J.get("text") or "")[:1200], checks=[dict(name=c.get("name"), level=c.get("level"), note=c.get("note")) for c in (J.get("checks") or [])]))
    return out


def nightlab():
    q = []
    f = BASE / "research" / "nightlab" / "queue.jsonl"
    if f.exists():
        for l in f.read_text(encoding="utf-8").splitlines():
            if l.strip():
                try:
                    x = json.loads(l)
                    q.append(dict(id=x.get("id", ""), title=x.get("title", ""), status=x.get("status", ""), asked=x.get("asked", ""), hypothesis=x.get("hypothesis", ""),
                                  result=x.get("result") or x.get("last") or ""))
                except Exception: pass
    reps = [dict(name=Path(p).name, at=mtime(p)) for p in sorted(glob.glob(str(BASE / "research" / "reports" / "nightlab" / "*.md")), key=os.path.getmtime)[-8:][::-1]]
    return dict(queue=q, reports=reps)


def opentick():
    out = []
    for kind, lab in (("nxtbook", "NXT 장전 호가 10단계"), ("open", "시가 직후 체결가"), ("am", "장전 호가(기존)"), ("pm", "마감 호가(기존)"), ("nxt", "NXT 장전 체결가(기존)")):
        fs = sorted(glob.glob(str(D / "factory" / "auction" / ("KR_*_%s.parquet" % kind))))
        if not fs: out.append(dict(kind=lab, days=0)); continue
        last = fs[-1]
        try:
            X = pd.read_parquet(last); n, tk = len(X), (X.ticker.nunique() if "ticker" in X else (X.t.nunique() if "t" in X else None))
        except Exception: n, tk = None, None
        out.append(dict(kind=lab, days=len(fs), first=Path(fs[0]).name[3:11], last=Path(last).name[3:11], rows=n, tickers=tk,
                        mb=round(sum(os.path.getsize(x) for x in fs) / 1e6, 1)))
    return out


def impact():
    J = jl(D / "factory" / "impact_fit.json", {}) or {}
    rows = []
    for k in ("30만", "50만", "100만", "300만", "1000만"):
        a = ((J.get("auction") or {}).get("by_amt") or {}).get(k) or {}; c = ((J.get("cont") or {}).get("by_amt") or {}).get(k) or {}
        rows.append(dict(amt=k, real=a.get("real"), auction=a.get("loss"), cont=c.get("loss"), short=a.get("short")))
    return dict(use=J.get("use"), cont={k: (J.get("cont") or {}).get(k) for k in ("a", "b", "n", "days")}, date=J.get("date") or J.get("made"), rows=rows)


def health():
    H = D / "factory" / "health"
    fs = sorted(H.glob("2*.md"))
    last = fs[-1].read_text(encoding="utf-8") if fs else ""
    sec = lambda title: [l[2:] for l in (last.split("## " + title)[1].split("\n## ")[0].splitlines() if ("## " + title) in last else []) if l.startswith("- ")]
    hist = []
    if (H / "health.csv").exists():
        X = pd.read_csv(H / "health.csv", dtype={"date": str}).tail(14)
        hist = [dict(d=r.date, n=int(r.n), crit=int(r.crit), fix=int(r.fix) if "fix" in X and r.fix == r.fix else 0, first=str(r.first) if r.first == r.first else "") for r in X.itertuples()][::-1]
    return dict(date=fs[-1].stem if fs else "", problems=sec("문제"), fixed=sec("스스로 고친 것"), ok=sec("정상 확인"), hist=hist)


def brief():
    j = jl(D / "day" / "brief_last.json", {}) or {}
    return dict(at=j.get("at", ""), text=re.sub(r"<[^>]+>", "", j.get("text", "")))


def shadow():
    B = jl(D / "factory" / "board.json", {}) or {}
    return B.get("shadow") or []


def nightfill():
    s = jl(D / "backfill" / "state.json", {}) or {}
    J = jl(BASE / "research" / "backfill" / "jobs.json", {}) or {}
    names = {}
    for j in (J.get("jobs") if isinstance(J, dict) else J) or []:
        if isinstance(j, dict): names[j.get("id") or j.get("name")] = j.get("title") or j.get("desc") or j.get("name")
    return [dict(id=k, name=names.get(k, k), **{kk: v.get(kk) for kk in ("total", "left", "rate_per_s", "eta_hours", "rows", "updated")}) for k, v in s.items() if isinstance(v, dict)]


def build():
    out = dict(made=time.strftime("%Y-%m-%d %H:%M"))
    for k, fn in (("tasks", tasks), ("prereg", prereg), ("audit", audit), ("redteam", redteam), ("nightlab", nightlab), ("rec", opentick),
                  ("impact", impact), ("health", health), ("brief", brief), ("shadow", shadow), ("nightfill", nightfill)):
        try: out[k] = fn()
        except Exception as ex: out[k] = None; out.setdefault("err", {})[k] = repr(ex)[:200]
    return out


def main(dry=False):
    J = build()
    s = json.dumps(J, ensure_ascii=False, default=str)
    print(time.strftime("%Y-%m-%d %H:%M"), "점검 현황 %.0fKB · 작업 %d · 오류 %s" % (len(s) / 1e3, len(J.get("tasks") or []), J.get("err")), flush=True)
    if dry:
        print(s[:3000]); return
    import board
    board.supa_set("__ops__", json.loads(s))


if __name__ == "__main__":
    main(dry=(sys.argv[1:2] == ["dry"]))
