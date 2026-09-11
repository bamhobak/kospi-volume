// 장중 시세·지수 수집 + 매도 신호 텔레그램 알림 (Edge Function)
//
// '추가매수 고려' 알림 이력: 원래 '이익 중 + 신호 4일 연속 유지'(표본 11건)였는데
// Edge Function 이관 때 연속 조건이 빠지고 '매수 후 3거래일' 이 되어 근거와 무관한
// 알림이 됐다. 2026-09-03 에 제거하고 현재 9규칙으로 다시 실측한 뒤, 근거가 확인된
// [외인 매집] 에 한해 되살렸다. 다른 규칙은 연도 쏠림이 심해(한 해에 86~90% 집중)
// 통과하지 못했다. 계좌 기준 전체·학습·검증·붐제외 네 구간 모두 수익금이 늘고
// 낙폭 악화는 -0.9%p 이내였다(자세한 근거는 addbuy_final.py).
//
// 왜 서버에서 받아야 하나: 네이버 시세 API 는 브라우저 출처를 보고 403 을 준다.
// (polling.finance.naver.com · m.stock.naver.com · api.stock.naver.com 모두 실측 403)
// 그래서 페이지가 직접 못 받고, 이 함수가 대신 받아 __prices__ 에 저장한 뒤 돌려준다.
//
// 호출 경로
//   1) 웹사이트 — 페이지를 열 때와 열어둔 동안 10분마다 (?alerts=0 으로 알림 생략)
//   2) Supabase 크론 — 평일 장중 10분마다. PC·브라우저가 꺼져 있어도 알림이 나간다.
//
// prices.py 와 저장 형식·판정이 같아야 한다(화면과 알림이 어긋나면 안 된다):
//   { updated, prices: { <코드>: {now,open,high,low,chg,vol,at,status} },
//     index: { kospi|kosdaq|nasdaq|krw: {now,chg,pct,at,status} } }

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const TG_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN") ?? "";
const TG_CHAT = Deno.env.get("TELEGRAM_CHAT_ID") ?? "";
// 사이트 주소 — 호스팅을 옮기면 Supabase 의 환경변수 SITE_URL 만 바꾸면 된다.
const SITE = (Deno.env.get("SITE_URL") ?? "https://kospi-volume.pages.dev").replace(/\/+$/, "");
// Cloudflare Access 뒤에 있으면 서비스 토큰 헤더가 있어야 통과한다.
// 없으면 로그인 화면 HTML 이 200 으로 돌아와 JSON.parse 가 조용히 깨진다 — 반드시 붙인다.
const CF_ID = Deno.env.get("CF_ACCESS_CLIENT_ID") ?? "";
const CF_SECRET = Deno.env.get("CF_ACCESS_CLIENT_SECRET") ?? "";
const siteFetch = (path: string) => fetch(`${SITE}${path}`, {
  headers: (CF_ID && CF_SECRET)
    ? { "CF-Access-Client-Id": CF_ID, "CF-Access-Client-Secret": CF_SECRET }
    : {},
});
const NAVER = { "User-Agent": "Mozilla/5.0" };

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};

// 규칙별 청산 — index.html FILTERS 의 rule 과 같아야 한다
// trail = 트레일링(보유 중 **종가** 최고점 대비). 2026-09-08 채택 — 고정 손절을 대체한다.
const RULES: Record<string, { stop: number | null; trail?: number | null; target: number | null; hold: number }> = {
  P1: { stop: null, trail: 0.08, target: null, hold: 40 },
  P2: { stop: null, target: null, hold: 10 },
  P3: { stop: null, target: null, hold: 20 },
  P4: { stop: null, trail: 0.08, target: null, hold: 5 },
  P5: { stop: null, target: null, hold: 10 },
  P6: { stop: null, trail: 0.08, target: null, hold: 5 },
  P7: { stop: null, target: null, hold: 60 },
  D1: { stop: null, target: null, hold: 20 },
  D2: { stop: null, target: null, hold: 40 },
  N1: { stop: null, target: null, hold: 40 },   // [상승장 신고가] — 미장 전용
  N2: { stop: null, target: null, hold: 20 },   // [낙폭과대] — 미장
  N3: { stop: null, target: null, hold: 40 },   // [저PBR 낙폭] — 미장
  N4: { stop: null, target: null, hold: 60 },   // [자사주 낙폭] — 미장
  N5: { stop: null, target: null, hold: 60 },   // [잔잔한 급등주] — 미장
  P0: { stop: null, target: 0.20, hold: 10 },   // 폐기된 옛 P1 — 이력 보존용
};
const LEGACY: Record<string, string> = { "1": "P0", "2": "P2", "3": "P3", "4": "P1" };
// 알림에는 내부 id 대신 이름을 쓴다 — 화면의 번호는 사용자가 순서를 바꾸면 달라지기 때문
const RNAME: Record<string, string> = {
  P1: "조용한 신고가", P2: "조정매집", P3: "폭락반등", P4: "업종붕괴 이탈",
  P5: "자사주 낙폭", P6: "깊은 이격", P7: "외인 매집",
  D1: "낙폭과대", D2: "저PBR 낙폭", P0: "옛 상승초입(폐기)",
  N1: "상승장 신고가",
  N2: "낙폭과대", N3: "저PBR 낙폭", N4: "자사주 낙폭", N5: "잔잔한 급등주",
};

const num = (s: unknown): number | null => {
  if (s === null || s === undefined) return null;
  const t = String(s).replace(/,/g, "").trim();
  if (!t || t === "-") return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};
const fmt = (n: number) => Math.round(n).toLocaleString("en-US");

async function rpc(fn: string, body: unknown) {
  const r = await fetch(`${SB_URL}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${fn} ${r.status} ${(await r.text()).slice(0, 120)}`);
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}

async function naver(path: string) {
  const r = await fetch(`https://polling.finance.naver.com/api/realtime/domestic/${path}`, { headers: NAVER });
  if (!r.ok) throw new Error(`naver ${path} ${r.status}`);
  const d = (await r.json())?.datas?.[0];
  if (!d) throw new Error(`naver ${path} 빈 응답`);
  return d;
}

async function telegram(text: string) {
  if (!TG_TOKEN || !TG_CHAT) { console.log("텔레그램 미설정:", text.replace(/\n/g, " | ")); return; }
  try {
    await fetch(`https://api.telegram.org/bot${TG_TOKEN}/sendMessage`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: TG_CHAT, text, parse_mode: "HTML", disable_web_page_preview: true }),
    });
  } catch (e) { console.error("텔레그램 실패", String(e).slice(0, 120)); }
}

/** KST 기준 값들 */
function kst() {
  const k = new Date(Date.now() + 9 * 3600 * 1000);
  const iso = k.toISOString();
  return { stamp: iso.slice(0, 16).replace("T", " "), today: iso.slice(0, 10).replace(/-/g, ""),
           hour: k.getUTCHours() };
}

/** 국내 종목코드는 6자리 숫자, 미장 티커는 글자 — 코드 모양으로 시장을 가른다 */
const isUS = (c: string) => !/^\d{6}$/.test(String(c ?? ""));

/** 미장 시세 — 야후 차트 엔드포인트(키 불필요, 서버에서만 된다).
 *  토스 Open API 는 국내 전용이라(해외 경로 전부 not-found) 여기엔 쓸 수 없다. */
async function yahoo(sym: string) {
  // range 는 넉넉히 — 연휴가 끼면 5일로는 직전 거래일을 못 담는다.
  const r = await fetch(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1d&range=1mo`,
    { headers: NAVER });
  if (!r.ok) throw new Error(`yahoo ${sym} ${r.status}`);
  const j = await r.json();
  const res = j?.chart?.result?.[0];
  const m = res?.meta;
  if (!m || m.regularMarketPrice == null) throw new Error(`yahoo ${sym} 빈 응답`);
  /* ⚠ **전일 종가를 meta 에서 읽으면 안 된다**(2026-09-12 사용자 신고로 발견).
       · `previousClose` 는 비어 있을 때가 있다(^IXIC 가 그랬다).
       · `chartPreviousClose` 는 '어제' 가 아니라 **조회 구간 시작 직전**의 종가다.
     둘을 이어 쓰다가 나스닥이 열흘 전 값과 비교돼 **+1.09% 를 -0.66% 로** 보여줬다.
     미장 종목 전일비도 같은 값을 써서 5일 전 대비로 계산되고 있었다.

     종가 배열에서 직접 고른다. 마지막 칸이 지금 값과 같으면(장중이거나 장 마감 후)
     그 칸이 **오늘**이므로 하나 앞이 전일 종가이고, 다르면(개장 전) 마지막 칸이 곧 전일이다. */
  const cl: number[] = (res?.indicators?.quote?.[0]?.close ?? []).filter((x: unknown) => x != null);
  const now = Number(m.regularMarketPrice);
  let prev: number | null = null;
  if (cl.length >= 2) {
    const lastIsToday = Math.abs(cl[cl.length - 1] - now) < Math.max(0.01, Math.abs(now) * 1e-6);
    prev = lastIsToday ? cl[cl.length - 2] : cl[cl.length - 1];
  } else if (cl.length === 1) prev = cl[0];
  if (prev == null) prev = m.previousClose ?? m.chartPreviousClose ?? null;
  return { ...m, prevClose: prev };
}

/** 미장 거래일 달력 — 보유일을 세는 데 쓴다. 한 번 부르고 재사용한다.
 *  (국내는 종목별 일봉 JSON 으로 세는데 미장은 그 파일이 없다) */
let _uscal: string[] | null = null;
/** 사이트에서 무엇을 받았는지 남긴다 — 실패를 조용히 삼키면 며칠 뒤에나 안다.
 *  Cloudflare Access 뒤에서는 헤더가 없으면 **로그인 HTML 이 200 으로** 오므로
 *  r.ok 만 보면 성공처럼 보인다. 그래서 '무엇이 왔는지' 를 따로 기록한다. */
const SITEDIAG: Record<string, string> = {};
async function siteJson(path: string): Promise<any | null> {
  try {
    const r = await siteFetch(path);
    const t = await r.text();
    if (!r.ok) { SITEDIAG[path] = `HTTP ${r.status}`; return null; }
    if (/^\s*</.test(t)) {            // HTML 이 왔다 = Access 로그인 화면
      SITEDIAG[path] = "HTML(로그인 화면?) — 서비스 토큰 확인";
      console.warn(`[site] ${path}: HTML 이 왔다 — Access 헤더를 확인하라`);
      return null;
    }
    SITEDIAG[path] = `ok ${t.length}B`;
    return JSON.parse(t);
  } catch (e) {
    SITEDIAG[path] = `실패 ${String(e).slice(0, 60)}`;
    console.warn(`[site] ${path}: ${e}`);
    return null;
  }
}
async function usCal(): Promise<string[]> {
  if (_uscal) return _uscal;
  _uscal = (await siteJson("/data/uscal.json"))?.dates ?? [];
  return _uscal!;
}

/** 종목의 매수일 이후 일별 종가 — 사이트가 이미 배포한 JSON 을 서버에서 읽는다 */
async function history(code: string): Promise<[string, number][]> {
  const d = await siteJson(`/data/stock/${code}.json`);
  if (!Array.isArray(d?.rows) || !Array.isArray(d?.dates)) return [];
  return d.rows.map((x: any[]) => [d.dates[x[0]], x[1]] as [string, number]);
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const t0 = Date.now();
  const q = new URL(req.url).searchParams;
  const wantAlerts = q.get("alerts") !== "0";
  try {
    const { stamp, today, hour } = kst();

    // ?ping=1 — 텔레그램 연결 확인용. 시세만 받아 한 줄 보내고 끝낸다.
    if (q.get("ping") === "1") {
      const kp = await naver("index/KOSPI").catch(() => null);
      await telegram(`🔔 <b>알림 연결 확인</b> (${stamp})
` +
        `이제 PC·브라우저가 꺼져 있어도 평일 09:00~15:40 10분마다 서버가 시세를 확인합니다.
` +
        `손절·익절·추가매수·매도일 조건에 걸리면 이 대화로 알려드립니다.` +
        (kp ? `
코스피 ${num(kp.closePrice)?.toLocaleString("en-US")}` : ""));
      return new Response(JSON.stringify({ ping: "sent", at: stamp, hasToken: !!TG_TOKEN, hasChat: !!TG_CHAT }),
        { headers: { ...CORS, "Content-Type": "application/json" } });
    }

    // 진단용 — ?diag=1 이면 사이트에서 실제로 받아지는지 확인만 하고 돌려준다.
    // (Access 전환 뒤 '조용히 빈 값' 인지 사람이 눈으로 볼 방법이 필요하다)
    if (q.get("diag") === "1") {
      const cal = await usCal();
      return new Response(JSON.stringify({
        site: SITE, hasToken: !!(CF_ID && CF_SECRET),
        uscalDates: cal.length, last: cal[cal.length - 1] ?? null, got: SITEDIAG,
      }), { headers: { ...CORS, "Content-Type": "application/json" } });
    }

    // 1) 보유 종목 (모든 PIN, 미매도)
    // kospi_state 를 직접 읽는다. 예전에 쓰던 kospi_state_positions RPC 는 id·code·date·
    // name·price 만 뽑아 주고 filters 와 qty 를 버려서, 모든 보유 종목이 '규칙 없이 등록된
    // 종목' 으로 취급됐다 — 손절·매도일·추가매수 알림이 통째로 나가지 않고 있었다.
    // (2026-09-03 발견. service role 이라 RLS 를 지나 전체 행을 읽는다.)
    const _sr = await fetch(`${SB_URL}/rest/v1/kospi_state?select=pin,data`,
      { headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}` } });
    const _rows: any[] = _sr.ok ? await _sr.json() : [];
    const positions: any[] = _rows
      .filter((r) => !String(r.pin ?? "").startsWith("__"))     // __filters__ 등 시스템 키 제외
      .flatMap((r) => (r.data?.positions ?? []))
      .filter((p: any) => p && p.code && !p.sell);
    const codes = [...new Set(positions.map((p) => p.code).filter(Boolean))] as string[];

    // 2) 종목 시세 · 3) 지수 — 실패한 항목은 건너뛴다
    const prices: Record<string, any> = {};
    const index: Record<string, any> = {};
    await Promise.all([
      ...codes.map(async (c) => {
        try {
          if (isUS(c)) {
            const m = await yahoo(c);
            const now = num(m.regularMarketPrice), prev = num(m.prevClose);
            // at 은 국내와 같은 모양("YYYY-MM-DD HH:MM:SS")으로 맞춘다 — 화면이 앞 10자를
            // 잘라 날짜로 쓰기 때문이다. 미장 날짜는 **뉴욕 기준**이어야 맞다.
            const ny = new Date((Number(m.regularMarketTime ?? 0)) * 1000)
              .toLocaleString("sv-SE", { timeZone: "America/New_York" });
            prices[c] = {
              now, open: num(m.regularMarketOpen), high: num(m.regularMarketDayHigh),
              low: num(m.regularMarketDayLow),
              chg: (now != null && prev != null) ? +(now - prev).toFixed(4) : null,
              vol: num(m.regularMarketVolume),
              at: ny, status: String(m.marketState ?? ""), mk: "US",
            };
            return;
          }
          const d = await naver(`stock/${c}`);
          prices[c] = {
            now: num(d.closePrice), open: num(d.openPrice), high: num(d.highPrice),
            low: num(d.lowPrice), chg: num(d.compareToPreviousClosePrice),
            vol: num(d.accumulatedTradingVolume),
            at: d.localTradedAt ?? "", status: d.marketStatus ?? "",
          };
        } catch (e) { console.error("종목 실패", c, String(e).slice(0, 100)); }
      }),
      ...([["kospi", "KOSPI"], ["kosdaq", "KOSDAQ"]] as const).map(async ([key, code]) => {
        try {
          const d = await naver(`index/${code}`);
          index[key] = {
            now: num(d.closePrice), chg: num(d.compareToPreviousClosePrice),
            pct: num(d.fluctuationsRatio), at: d.localTradedAt ?? "", status: d.marketStatus ?? "",
          };
        } catch (e) { console.error("지수 실패", code, String(e).slice(0, 100)); }
      }),
      // 달러/원 — 밤에 나스닥과 나란히 보여준다. 지수와 **같은 주기**로 갱신되게 여기 둔다
      // (uscal.json 의 환율은 하루 한 번 수집 때 받는 값이라 주기가 다르다 · 2026-09-12 요청).
      (async () => {
        // ⚠ 야후 KRW=X 는 국제 인터뱅크 호가라 **국내 앱이 보여주는 값과 다르다**
        //   (2026-09-12: 야후 1,339.77 -0.39% vs 하나은행 고시 1,340.60 -0.77%.
        //    값보다 **등락률이 두 배** 차이 났다 — 기준 전일 종가가 다르기 때문).
        //   토스·네이버가 쓰는 하나은행 고시 매매기준율을 먼저 쓰고, 실패하면 야후로 간다.
        try {
          const r = await fetch("https://api.stock.naver.com/marketindex/exchange/FX_USDKRW",
                                { headers: NAVER });
          if (!r.ok) throw new Error(`naver fx ${r.status}`);
          const e0 = (await r.json())?.exchangeInfo;
          const now = num(String(e0?.closePrice ?? "").replace(/,/g, ""));
          if (now == null) throw new Error("naver fx 빈 응답");
          index["krw"] = { now, pct: num(e0?.fluctuationsRatio),
                           chg: num(String(e0?.fluctuations ?? "").replace(/,/g, "")),
                           at: e0?.localTradedAt ?? "", src: "hana" };
        } catch (e1) {
          console.error("환율(네이버) 실패", String(e1).slice(0, 100));
          try {
            const m = await yahoo("KRW=X");
            const now = num(m.regularMarketPrice);
            const prev = num(m.prevClose);
            index["krw"] = {
              now, chg: (now != null && prev != null) ? now - prev : null,
              pct: (now != null && prev) ? (now / prev - 1) * 100 : null, src: "yahoo",
            };
          } catch (e2) { console.error("환율(야후)도 실패", String(e2).slice(0, 100)); }
        }
      })(),
      // 나스닥 — 한국 밤(20시~08시)에는 화면 위 지수를 이걸로 바꾼다(2026-09-12 요청).
      // 그 시간엔 국내 지수가 멈춰 있어 볼 것이 없고, 미장이 열려 있다.
      // 네이버 지수 API 는 국내 전용이라 야후를 쓴다(미장 시세와 같은 경로).
      (async () => {
        try {
          const m = await yahoo("^IXIC");
          const now = num(m.regularMarketPrice);
          const prev = num(m.prevClose);
          index["nasdaq"] = {
            now, chg: (now != null && prev != null) ? now - prev : null,
            pct: (now != null && prev) ? (now / prev - 1) * 100 : null,
            at: m.regularMarketTime
              ? new Date(m.regularMarketTime * 1000 + 9 * 3600 * 1000).toISOString().slice(0, 16).replace("T", " ")
              : "",
          };
        } catch (e) { console.error("나스닥 실패", String(e).slice(0, 100)); }
      })(),
    ]);

    // 4) 저장 — 전부 실패했으면 기존 값을 덮어쓰지 않는다
    const payload = { updated: stamp, prices, index };
    if (Object.keys(prices).length || Object.keys(index).length) {
      await rpc("kospi_state_set", { p_pin: "__prices__", p_data: payload });
    }

    // 5) 매도 신호 알림 (같은 키는 한 번만 — __alerts__ 에 기록)
    let fired = 0;
    if (wantAlerts && positions.length) {
      const st = (await rpc("kospi_state_get", { p_pin: "__alerts__" })) ?? {};
      const sent = new Set<string>(st.sent ?? []);
      // 규칙별 신호 연속 일수 — notify_new.py 가 매일 하루씩 누적해 둔다
      const STK: Record<string, number> =
        ((await rpc("kospi_state_get", { p_pin: "__filters__" })) ?? {}).streaks ?? {};
      const dueToSell: string[] = [];   // 매도일 도달분 — 모았다가 한 통으로
      const before = sent.size;
      for (const p of positions) {
        const lv = prices[p.code];
        if (!lv?.now) continue;
        const price = Number(p.price);
        if (!price) continue;
        // 규칙 없이 직접 등록한 종목은 남의 청산규칙으로 알리지 않는다
        const fids = (p.filters ?? []).map((f: any) => LEGACY[String(f)] ?? String(f));
        const rid = fids.find((f: string) => RULES[f]);
        if (!rid) continue;
        const rule = RULES[rid];

        const buy = String(p.date);
        const us = isUS(p.code);
        const rows = us ? [] : (await history(p.code)).filter(([d]) => d >= buy);
        // 미장은 종목별 일봉 파일이 없어 rows 가 비고, 그대로 두면 보유일이 늘 0 이라
        // 매도일 알림이 영영 안 나간다(2026-09-11 발견). 거래일 달력으로 센다.
        const liveToday = String(lv.at).slice(0, 10).replace(/-/g, "") === today;
        const days = us
          ? (await usCal()).filter((d) => d >= buy).length
          : rows.filter(([d]) => d < today).length + (liveToday ? 1 : 0);
        const hi = Math.max(price, ...rows.map(([, c]) => c), liveToday && lv.high ? lv.high : 0);

        const now = lv.now, ret = (now / price - 1) * 100;
        const nm = p.name ?? p.code, id = p.id ?? p.code;
        // 트레일링 청산선은 보유 중 **종가** 최고점 기준이다(장중 고가 lv.high 는 쓰지 않는다 —
        // 백테스트가 종가로 쟀으므로 실전도 종가로 판정해야 성적이 맞는다).
        const hiC = Math.max(price, ...rows.map(([, c]) => c));
        const line = rule.trail ? hiC * (1 - rule.trail)
                   : rule.stop ? price * (1 - rule.stop) : null;
        const tgt = rule.target ? price * (1 + rule.target) : null;

        if (line && now <= line && !sent.has(`${id}:stop`)) {
          await telegram(rule.trail
            ? `🛑 <b>${nm}</b> 트레일링 -${(rule.trail * 100).toFixed(0)}% 이탈
` +
              `현재가 ${fmt(now)} (매수 ${fmt(price)}, ${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%)
` +
              `기준선 ${fmt(line)} = 보유 중 최고 종가 ${fmt(hiC)} 대비 -${(rule.trail * 100).toFixed(0)}%
` +
              `보유 ${days}거래일 · 규칙 ${RNAME[rid] ?? rid}
` +
              `※ 판정은 종가 기준 — 종가가 이 선 아래로 끝나면 내일 시가에 파십시오`
            : `🛑 <b>${nm}</b> 손절선 이탈 (-${(rule.stop! * 100).toFixed(0)}%)
` +
              `현재가 ${fmt(now)} (매수 ${fmt(price)}, ${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%)
` +
              `손절선 ${fmt(line)} · 보유 ${days}거래일 · 규칙 ${RNAME[rid] ?? rid}`);
          sent.add(`${id}:stop`); fired++;
        }
        if (tgt && now >= tgt && !sent.has(`${id}:target`)) {
          await telegram(`🎯 <b>${nm}</b> 익절 목표 도달 (+${(rule.target! * 100).toFixed(0)}%)\n` +
            `현재가 ${fmt(now)} (매수 ${fmt(price)}, +${ret.toFixed(1)}%)\n보유 ${days}거래일 · 규칙 ${RNAME[rid] ?? rid}`);
          sent.add(`${id}:target`); fired++;
        }
        // 매도일 알림은 12시부터. 09:00 첫 체크에 보내면 시가 변동이 한창일 때 알림이 와서
        // 판단할 여유가 없다. 정오면 그날 흐름이 어느 정도 잡힌다.
        // 추가매수는 [외인 매집](P7) 에서만, 신호가 이어지는 중이고 이미 이익일 때 한 번.
        // 실측 근거: 754건 평균 +17.34%(최초 신호 +14.70%) · 학습CI +7.7~+24.0 ·
        // 중앙 +14.99% · 상위5% 제거 +13.88% · 최다연도 29%. 계좌로도 네 구간 모두 개선.
        const stk = STK[`${rid}:${p.code}`] ?? 0;
        // 종목당 한 번만. 추가매수를 하면 같은 종목이 두 줄이 되는데, sent 키가 포지션
        // id 라서 그 두 줄 각각에 또 알림이 갈 수 있었다 — 그 종목의 [외인 매집] 보유가
        // 이미 둘이면 보내지 않는다(백테스트도 종목당 1회로 쟀다).
        const nP7 = positions.filter((q: any) =>
          q.code === p.code && !q.sell &&
          (q.filters ?? []).some((f: any) => (LEGACY[String(f)] ?? String(f)) === "P7")).length;
        if (rid === "P7" && nP7 < 2 && stk >= 2 && ret > 0 && !sent.has(`${id}:add`)) {
          await telegram(`🔥 <b>${nm}</b> 추가매수 고려 — 신호 ${stk}일째 유지 + 이익 중 (+${ret.toFixed(1)}%)
` +
            `현재가 ${fmt(now)} (매수 ${fmt(price)}) · 보유 ${days}거래일 · 규칙 ${RNAME[rid] ?? rid}
` +
            `최초 매수와 같은 비중으로 한 번만 · 매도는 이 매수분 기준 60거래일`);
          sent.add(`${id}:add`); fired++;
        }
        // 매도일 알림은 **종목명 없이 한 통**으로 모아 보낸다(2026-09-10 사용자 요청).
        // 예전엔 종목마다 한 통씩 나가 하루에 여러 번 울렸다. 여기서는 모아 두고
        // 반복문이 끝난 뒤 한 번만 보낸다. sent 키는 그대로 포지션별이라 같은 종목을
        // 두 번 세지 않는다.
        if (days >= rule.hold && hour >= 12 && !sent.has(`${id}:hold`)) {
          dueToSell.push(id);
          sent.add(`${id}:hold`);
        }
      }
      if (dueToSell.length) {
        fired++;
        await telegram(
          `⏰ <b>매도일인 종목이 ${dueToSell.length}개 있습니다</b>` +
          `${String.fromCharCode(10)}장 마감 전에 매도해 주세요 — 사이트에서 확인해 주세요.` +
          `${String.fromCharCode(10)}${String.fromCharCode(10)}${SITE}/`,
        );
      }
      if (sent.size !== before) {
        await rpc("kospi_state_set", { p_pin: "__alerts__", p_data: { sent: [...sent].sort(), updated: stamp } });
      }
    }

    return new Response(JSON.stringify({
      ...payload,
      _meta: { codes: codes.length, ok: Object.keys(prices).length, alerts: fired,
               // 규칙이 붙어 있어 청산 알림을 받을 수 있는 보유 종목 수.
               // 0 이면 보유가 있어도 알림이 나가지 않는다는 뜻이라 바로 눈에 띈다.
               ruled: positions.filter((p: any) =>
                 (p.filters ?? []).some((f: any) => RULES[LEGACY[String(f)] ?? String(f)])).length,
               held: positions.length, ms: Date.now() - t0,
               // 사이트에서 무엇을 받았는지. Cloudflare Access 뒤에서 서비스 토큰이 빠지면
               // 'HTML(로그인 화면?)' 로 찍힌다 — 조용히 빈 배열이 되는 걸 막으려고 남긴다.
               site: SITE, siteGot: SITEDIAG },
    }), { headers: { ...CORS, "Content-Type": "application/json" } });
  } catch (e) {
    console.error(e);
    return new Response(JSON.stringify({ error: String(e).slice(0, 300) }), {
      status: 500, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
