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
//     index: { kospi|kosdaq: {now,chg,pct,at,status} } }

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const TG_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN") ?? "";
const TG_CHAT = Deno.env.get("TELEGRAM_CHAT_ID") ?? "";
const SITE = "https://bamhobak.github.io/kospi-volume";
const NAVER = { "User-Agent": "Mozilla/5.0" };

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
};

// 규칙별 청산 — index.html FILTERS 의 rule 과 같아야 한다
const RULES: Record<string, { stop: number | null; target: number | null; hold: number }> = {
  P1: { stop: 0.15, target: null, hold: 40 },
  P2: { stop: null, target: null, hold: 10 },
  P3: { stop: null, target: null, hold: 20 },
  P4: { stop: 0.15, target: null, hold: 5 },
  P5: { stop: null, target: null, hold: 10 },
  P6: { stop: 0.10, target: null, hold: 5 },
  P7: { stop: null, target: null, hold: 60 },
  D1: { stop: null, target: null, hold: 20 },
  D2: { stop: null, target: null, hold: 40 },
  P0: { stop: null, target: 0.20, hold: 10 },   // 폐기된 옛 P1 — 이력 보존용
};
const LEGACY: Record<string, string> = { "1": "P0", "2": "P2", "3": "P3", "4": "P1" };
// 알림에는 내부 id 대신 이름을 쓴다 — 화면의 번호는 사용자가 순서를 바꾸면 달라지기 때문
const RNAME: Record<string, string> = {
  P1: "조용한 신고가", P2: "조정매집", P3: "폭락반등", P4: "업종붕괴 이탈",
  P5: "자사주 낙폭", P6: "깊은 이격", P7: "외인 매집",
  D1: "낙폭과대", D2: "저PBR 낙폭", P0: "옛 상승초입(폐기)",
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

/** 종목의 매수일 이후 일별 종가 — 사이트가 이미 배포한 JSON 을 서버에서 읽는다 */
async function history(code: string): Promise<[string, number][]> {
  try {
    const r = await fetch(`${SITE}/data/stock/${code}.json`);
    if (!r.ok) return [];
    const d = await r.json();
    if (!Array.isArray(d?.rows) || !Array.isArray(d?.dates)) return [];
    return d.rows.map((x: any[]) => [d.dates[x[0]], x[1]] as [string, number]);
  } catch { return []; }
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

    // 1) 보유 종목 (모든 PIN, 미매도)
    const positions: any[] = (await rpc("kospi_state_positions", {})) ?? [];
    const codes = [...new Set(positions.map((p) => p.code).filter(Boolean))] as string[];

    // 2) 종목 시세 · 3) 지수 — 실패한 항목은 건너뛴다
    const prices: Record<string, any> = {};
    const index: Record<string, any> = {};
    await Promise.all([
      ...codes.map(async (c) => {
        try {
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
        const rows = (await history(p.code)).filter(([d]) => d >= buy);
        const liveToday = String(lv.at).slice(0, 10).replace(/-/g, "") === today;
        const days = rows.filter(([d]) => d < today).length + (liveToday ? 1 : 0);
        const hi = Math.max(price, ...rows.map(([, c]) => c), liveToday && lv.high ? lv.high : 0);

        const now = lv.now, ret = (now / price - 1) * 100;
        const nm = p.name ?? p.code, id = p.id ?? p.code;
        const line = rule.stop ? price * (1 - rule.stop) : null;
        const tgt = rule.target ? price * (1 + rule.target) : null;

        if (line && now <= line && !sent.has(`${id}:stop`)) {
          await telegram(`🛑 <b>${nm}</b> 손절선 이탈 (-${(rule.stop! * 100).toFixed(0)}%)\n` +
            `현재가 ${fmt(now)} (매수 ${fmt(price)}, ${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%)\n` +
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
        if (rid === "P7" && stk >= 2 && ret > 0 && !sent.has(`${id}:add`)) {
          await telegram(`🔥 <b>${nm}</b> 추가매수 고려 — 신호 ${stk}일째 유지 + 이익 중 (+${ret.toFixed(1)}%)
` +
            `현재가 ${fmt(now)} (매수 ${fmt(price)}) · 보유 ${days}거래일 · 규칙 ${RNAME[rid] ?? rid}
` +
            `최초 매수와 같은 비중으로 한 번만 · 매도는 이 매수분 기준 60거래일`);
          sent.add(`${id}:add`); fired++;
        }
        if (days >= rule.hold && hour >= 12 && !sent.has(`${id}:hold`)) {
          await telegram(`⏰ <b>${nm}</b> 보유 ${days}거래일째 — 규칙상 매도일\n` +
            `현재가 ${fmt(now)} (매수 ${fmt(price)}, ${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%)\n` +
            `고점 ${fmt(hi)} · 규칙 ${RNAME[rid] ?? rid} (${rule.hold}거래일 보유)`);
          sent.add(`${id}:hold`); fired++;
        }
      }
      if (sent.size !== before) {
        await rpc("kospi_state_set", { p_pin: "__alerts__", p_data: { sent: [...sent].sort(), updated: stamp } });
      }
    }

    return new Response(JSON.stringify({
      ...payload,
      _meta: { codes: codes.length, ok: Object.keys(prices).length, alerts: fired, ms: Date.now() - t0 },
    }), { headers: { ...CORS, "Content-Type": "application/json" } });
  } catch (e) {
    console.error(e);
    return new Response(JSON.stringify({ error: String(e).slice(0, 300) }), {
      status: 500, headers: { ...CORS, "Content-Type": "application/json" },
    });
  }
});
