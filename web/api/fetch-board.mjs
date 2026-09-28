// 교육청 게시판을 서울에서 대신 받아 주는 중계.
//
// 한국 공공기관 사이트 상당수가 해외 IP를 막는다. GitHub Actions는 미국에서
// 돌기 때문에 기관이 하나씩 차례로 막히고 있다(세종 9/7, 인천·충북 9/28 확인).
// 막히는 방식도 제각각이다 — 연결 자체가 안 되기도 하고, 200을 주면서 목록만
// 비워 보내기도 한다. 그래서 기관을 하나씩 등록하는 대신 전부 이 길로 보낸다.
//
// 이 함수는 vercel.json의 regions=["icn1"] 덕에 서울에서 실행되므로 한국 IP를 쓴다.
// 아무 주소나 받아 주면 공개 프록시가 되므로 수집 대상 기관 주소만 통과시킨다.

const ALLOWED_HOSTS = new Set([
  "www.moe.go.kr", // 교육부
  "www.jbe.go.kr", // 전북
  "enews.sen.go.kr", // 서울
  "www.goe.go.kr", // 경기
  "www.pen.go.kr", // 부산
  "www.dge.go.kr", // 대구
  "www.ice.go.kr", // 인천
  "www.jngjedu.kr", // 전남광주통합
  "www.dje.go.kr", // 대전
  "use.go.kr", // 울산
  "www.sje.go.kr", // 세종
  "gwe.go.kr", // 강원
  "www.gwe.go.kr",
  "www.cbe.go.kr", // 충북
  "news.cne.go.kr", // 충남
  "www.gbe.kr", // 경북
  "www.gne.go.kr", // 경남
  "www.jje.go.kr", // 제주
]);

// 쿠키가 없으면 SSO 화면으로 튕겨내는 사이트. 본 요청 전에 같은 호출 안에서
// 아래 주소들을 먼저 훑어 세션을 만든 뒤, 받은 쿠키를 그대로 붙여 보낸다.
// (수집기 쪽 예열은 직접 나가므로 중계를 거치면 쿠키가 따로 놀아 소용이 없다.)
const WARMUP = {
  "www.dge.go.kr": [
    "https://www.dge.go.kr/",
    "https://www.dge.go.kr/main/main.do",
    "https://www.dge.go.kr/main/sso/index.do",
  ],
};

const FETCH_TIMEOUT_MS = 25_000;
const MAX_BYTES = 8_000_000;

function collectCookies(response, jar) {
  const raw = response.headers.getSetCookie?.() ?? [];
  for (const line of raw) {
    const [pair] = line.split(";");
    const index = pair.indexOf("=");
    if (index > 0) jar.set(pair.slice(0, index).trim(), pair.slice(index + 1).trim());
  }
}

async function warmUp(hostname, headers, signal) {
  const urls = WARMUP[hostname];
  if (!urls) return "";
  const jar = new Map();
  for (const url of urls) {
    try {
      const res = await fetch(url, {
        headers: { ...headers, ...(jar.size ? { Cookie: cookieHeader(jar) } : {}) },
        redirect: "follow",
        signal,
      });
      collectCookies(res, jar);
      await res.arrayBuffer(); // 연결을 확실히 닫는다
    } catch {
      // 예열 실패는 치명적이지 않다. 본 요청에서 판가름난다.
    }
  }
  return cookieHeader(jar);
}

function cookieHeader(jar) {
  return [...jar].map(([k, v]) => `${k}=${v}`).join("; ");
}

export const config = { maxDuration: 40 };

function text(body, status) {
  return new Response(body, {
    status,
    headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
  });
}

export async function GET(request) {
  const raw = new URL(request.url).searchParams.get("url");
  if (!raw) return text("url 쿼리 값이 필요합니다.", 400);

  let target;
  try {
    target = new URL(raw);
  } catch {
    return text("주소 형식이 올바르지 않습니다.", 400);
  }
  if (target.protocol !== "https:" && target.protocol !== "http:") {
    return text("http(s)만 허용합니다.", 400);
  }
  if (!ALLOWED_HOSTS.has(target.hostname)) {
    return text(`허용되지 않은 주소입니다: ${target.hostname}`, 403);
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  const baseHeaders = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
  };
  try {
    const cookie = await warmUp(target.hostname, baseHeaders, controller.signal);
    const upstream = await fetch(target, {
      signal: controller.signal,
      redirect: "follow",
      headers: cookie ? { ...baseHeaders, Cookie: cookie } : baseHeaders,
    });
    const buffer = await upstream.arrayBuffer();
    if (buffer.byteLength > MAX_BYTES) return text("응답이 너무 큽니다.", 502);
    return new Response(buffer, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") || "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Proxy-Region": process.env.VERCEL_REGION || "unknown",
      },
    });
  } catch (error) {
    return text(`가져오기 실패: ${error.name} ${error.message}`, 502);
  } finally {
    clearTimeout(timer);
  }
}
