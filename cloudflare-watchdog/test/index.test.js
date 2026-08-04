import assert from "node:assert/strict";
import test from "node:test";

import { keepAwakeOnce } from "../src/index.js";

test("checks status and sends a CSRF-protected resume request", async () => {
  const requests = [];
  const fakeFetch = async (url, options) => {
    requests.push({ url, options });
    if (requests.length === 1) {
      return new Response(JSON.stringify({ status: 5 }), {
        status: 200,
        headers: {
          "content-type": "application/json",
          "set-cookie": "_streamlit_csrf=cookie-value; Path=/; Secure",
          "x-csrf-token": "header-value",
        },
      });
    }
    return new Response(null, { status: 204 });
  };

  const result = await keepAwakeOnce(
    "https://example.streamlit.app/ignored",
    fakeFetch,
  );

  assert.deepEqual(result, { status: 5, resumeHttp: 204 });
  assert.equal(requests[0].url, "https://example.streamlit.app/api/v2/app/status");
  assert.equal(requests[1].url, "https://example.streamlit.app/api/v2/app/resume");
  assert.equal(requests[1].options.method, "POST");
  assert.equal(requests[1].options.headers.Cookie, "_streamlit_csrf=cookie-value");
  assert.equal(requests[1].options.headers["X-CSRF-TOKEN"], "header-value");
});

test("rejects an invalid Streamlit status response", async () => {
  const fakeFetch = async () =>
    new Response(JSON.stringify({ status: 5 }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  await assert.rejects(
    keepAwakeOnce("https://example.streamlit.app", fakeFetch),
    /missing control-plane data/,
  );
});
