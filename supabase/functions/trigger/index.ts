// 수집 트리거 — 네이버에 당일 투자자 데이터가 올라왔는지 **GitHub 바깥에서** 확인하고,
// 준비됐을 때만 워크플로를 깨운다.
//
// 왜 만들었나(2026-09-11):
//   전에는 cron-job.org 가 18:00 에 GitHub 을 바로 때리고, 러너 안에서 collect.wait_for_today()
//   가 21:00 까지 10분 간격으로 자면서 기다렸다. 공개 저장소일 때는 Actions 가 공짜라 괜찮았지만
//   비공개로 바꾸면 **그 대기가 전부 과금**된다. 실측 중앙 108분/일 × 22거래일 = 2,376분으로
//   무료 2,000분을 넘긴다(실제 일하는 시간은 13~18분뿐이다).
//
//   그래서 '기다리는 일' 을 여기로 옮겼다. cron-job.org 가 17:40~21:00 사이 20분 간격으로
//   이 함수를 부르고, 함수는 네이버를 한 번 보고 아직이면 그냥 돌아간다. 데이터가 올라온
//   그 회차에만 repository_dispatch 를 쏜다. Actions 는 실제로 일할 때만 돈다.
//   창을 17:40 부터 여는 건 네이버 반영 시각이 들쭉날쭉해서다(실측 17:25·19:35·20:21·20:47).
//
// 중복 발사 방지: kospi_state 의 __collect__ 핀에 '오늘 쐈다' 를 적는다.
//   ⚠ 이게 없으면 20분마다 계속 쏘게 되고, 워크플로의 concurrency(cancel-in-progress)가
//     **돌고 있던 수집을 취소**해 그날 데이터가 통째로 날아간다(2026-09-07 과 같은 사고).
//
// 실패해도 굶지 않는다: 워크플로에 21:30·07:00 예약이 남아 있어 여기가 죽어도 그날 수집은 된다.
// 그쪽은 --wait 를 그대로 쓰지만 그 시각엔 데이터가 이미 있어 즉시 통과한다.

const SB_URL = Deno.env.get("SUPABASE_URL")!;
const SB_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const GH_TOKEN = Deno.env.get("GH_DISPATCH_TOKEN") ?? "";
const GH_REPO = Deno.env.get("GH_REPO") ?? "bamhobak/kospi-volume";
// 아무나 눌러 수집을 깨우지 못하게 하는 공유 비밀. 안 넣으면 검사하지 않는다.
const HOOK_KEY = Deno.env.get("TRIGGER_KEY") ?? "";

const NAVER = { "User-Agent": "Mozilla/5.0" };
const JSONH = { "Content-Type": "application/json; charset=utf-8" };

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

/** KST 기준 날짜·시각 */
function kst() {
  const k = new Date(Date.now() + 9 * 3600 * 1000);
  const iso = k.toISOString();
  return {
    stamp: iso.slice(0, 16).replace("T", " "),
    today: iso.slice(0, 10).replace(/-/g, ""),
    hhmm: iso.slice(11, 16),
    dow: k.getUTCDay(), // 0=일 … 6=토
  };
}

/** 네이버가 당일 투자자 데이터를 올렸는가 — collect.wait_for_today() 와 같은 엔드포인트를 본다.
 *  (다른 곳을 보면 여기서 '됐다' 하고 쐈는데 워크플로가 또 기다리는 엇갈림이 생긴다) */
async function naverBizdate(): Promise<string> {
  const r = await fetch(
    "https://m.stock.naver.com/api/stock/005930/trend?pageSize=1&page=1",
    { headers: NAVER },
  );
  if (!r.ok) throw new Error(`naver ${r.status}`);
  const d = (await r.json())?.[0];
  if (!d?.bizdate) throw new Error("naver 빈 응답");
  return String(d.bizdate);
}

async function dispatch(): Promise<void> {
  const r = await fetch(`https://api.github.com/repos/${GH_REPO}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "kospi-volume-trigger",
      "Content-Type": "application/json",
    },
    // ready:true 는 "네이버에 오늘 데이터가 있는 걸 보고 부른다" 는 표시다.
    // 워크플로는 이게 있을 때만 러너 대기 상한을 20분으로 줄인다(없으면 예전대로 21:00).
    body: JSON.stringify({ event_type: "collect", client_payload: { ready: true } }),
  });
  // 204 가 정상이다. 그 외에는 본문을 그대로 올려 보내 원인이 보이게 한다.
  if (r.status !== 204) throw new Error(`dispatch ${r.status} ${(await r.text()).slice(0, 200)}`);
}

Deno.serve(async (req) => {
  const u = new URL(req.url);
  const t = kst();
  const out = (o: Record<string, unknown>, code = 200) =>
    new Response(JSON.stringify({ at: t.stamp, ...o }, null, 1), { status: code, headers: JSONH });

  if (HOOK_KEY && u.searchParams.get("key") !== HOOK_KEY) return out({ error: "key" }, 403);

  // ⚠ **쏘는 건 POST 로만** 한다. GET 은 무조건 진단이다.
  //   주소에 키가 들어가는 구조라 링크가 어딘가에 남으면 누가 눌러서 수집이 돈다.
  //   실제로 2026-09-11 에 대화에 붙여둔 주소를 눌러 수집이 한 번 더 돌았다.
  //   사람이 누르는 것뿐 아니라 **메신저·채팅앱의 링크 미리보기 봇**이 긁기만 해도
  //   발사된다 — 그쪽은 전부 GET 이라 이 한 줄로 막힌다. cron-job.org 는 POST 를 보낸다.
  const diag = u.searchParams.get("diag") === "1" || req.method === "GET";
  const force = u.searchParams.get("force") === "1";

  let state: Record<string, unknown> = {};
  try { state = (await rpc("kospi_state_get", { p_pin: "__collect__" })) ?? {}; }
  catch (e) { return out({ error: "state", detail: String(e).slice(0, 200) }, 500); }

  let biz = "", err = "";
  try { biz = await naverBizdate(); } catch (e) { err = String(e).slice(0, 200); }

  const base = {
    today: t.today, hhmm: t.hhmm, dow: t.dow,
    naverBizdate: biz || null, naverError: err || null,
    firedOn: state.fired ?? null, hasToken: !!GH_TOKEN, repo: GH_REPO,
  };
  if (diag) {
    // 토큰이 실제로 통하는지 **쏘지 않고** 본다. force=1 로 시험하면 진짜 수집이 돌아
    // 데이터가 없는 시각엔 러너가 21시까지 기다린다 — 그게 바로 없애려는 낭비다.
    let tok = "미설정";
    if (GH_TOKEN) {
      try {
        const r = await fetch(`https://api.github.com/repos/${GH_REPO}`, {
          headers: {
            Authorization: `Bearer ${GH_TOKEN}`, Accept: "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "kospi-volume-trigger",
          },
        });
        // 저장소가 보이면 인증은 통과다. 쓰기 권한까지는 여기서 알 수 없어 dispatch 응답으로 갈린다.
        tok = r.ok ? `ok ${r.status} (private=${(await r.json()).private})` : `실패 ${r.status}`;
      } catch (e) { tok = `실패 ${String(e).slice(0, 80)}`; }
    }
    return out({
      diag: true, method: req.method,
      note: req.method === "GET" ? "GET 은 진단만 한다. 쏘려면 POST 로 불러라." : undefined,
      tokenCheck: tok, ...base,
    });
  }

  if (t.dow === 0 || t.dow === 6) return out({ skip: "주말", ...base });
  if (state.fired === t.today && !force) return out({ skip: "오늘 이미 발사", ...base });
  if (err) return out({ skip: "네이버 확인 실패 — 다음 회차에 다시 본다", ...base });
  if (biz !== t.today && !force) return out({ skip: "당일 데이터 아직 없음", ...base });

  if (!GH_TOKEN) return out({ error: "GH_DISPATCH_TOKEN 미설정", ...base }, 500);
  try { await dispatch(); } catch (e) { return out({ error: "dispatch", detail: String(e).slice(0, 200), ...base }, 502); }

  // 쏜 뒤에 적는다 — 먼저 적으면 발사가 실패했을 때 그날 수집이 통째로 빠진다
  try { await rpc("kospi_state_set", { p_pin: "__collect__", p_data: { fired: t.today, at: t.stamp } }); }
  catch (e) { return out({ fired: true, warn: "상태 기록 실패 — 중복 발사 가능", detail: String(e).slice(0, 200), ...base }); }

  return out({ fired: true, ...base });
});
