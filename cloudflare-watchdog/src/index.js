const STATUS_PATH = "/api/v2/app/status";
const RESUME_PATH = "/api/v2/app/resume";

function baseUrl(appUrl) {
  const parsed = new URL(appUrl);
  if (parsed.protocol !== "https:") {
    throw new Error("STREAMLIT_APP_URL must use https");
  }
  return parsed.origin;
}

function responseCookies(headers) {
  const values =
    typeof headers.getSetCookie === "function"
      ? headers.getSetCookie()
      : [headers.get("set-cookie")].filter(Boolean);
  return values.map((value) => value.split(";", 1)[0]).join("; ");
}

export async function keepAwakeOnce(appUrl, fetchImpl = fetch) {
  const origin = baseUrl(appUrl);
  const statusResponse = await fetchImpl(`${origin}${STATUS_PATH}`, {
    headers: {
      Accept: "application/json",
      "User-Agent": "StylePick-Cloudflare-Watchdog/1.0",
    },
    redirect: "manual",
  });
  if (!statusResponse.ok) {
    throw new Error(`Streamlit status returned HTTP ${statusResponse.status}`);
  }

  const csrfToken = statusResponse.headers.get("x-csrf-token");
  const cookie = responseCookies(statusResponse.headers);
  const statusPayload = await statusResponse.json();
  if (!csrfToken || !cookie || !Number.isInteger(statusPayload.status)) {
    throw new Error("Streamlit status response is missing control-plane data");
  }

  const resumeResponse = await fetchImpl(`${origin}${RESUME_PATH}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      Cookie: cookie,
      "X-CSRF-TOKEN": csrfToken,
      "User-Agent": "StylePick-Cloudflare-Watchdog/1.0",
    },
    redirect: "manual",
  });
  if (!resumeResponse.ok) {
    throw new Error(`Streamlit resume returned HTTP ${resumeResponse.status}`);
  }

  return {
    status: statusPayload.status,
    resumeHttp: resumeResponse.status,
  };
}

async function runThirtySecondPair(env) {
  const first = await keepAwakeOnce(env.STREAMLIT_APP_URL);
  console.log("Streamlit keep-awake check", { sequence: 1, ...first });
  await scheduler.wait(30_000);
  const second = await keepAwakeOnce(env.STREAMLIT_APP_URL);
  console.log("Streamlit keep-awake check", { sequence: 2, ...second });
}

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(runThirtySecondPair(env));
  },

  async fetch(_request, env) {
    try {
      const result = await keepAwakeOnce(env.STREAMLIT_APP_URL);
      return Response.json({ ok: true, ...result });
    } catch (error) {
      return Response.json(
        { ok: false, error: error instanceof Error ? error.message : String(error) },
        { status: 503 },
      );
    }
  },
};
