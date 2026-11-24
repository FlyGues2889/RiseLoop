import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, createApiClient } from "../src/index.js";

function reply(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  };
}

function stub(object) {
  const original = globalThis.fetch;
  globalThis.fetch = object;
  return () => {
    globalThis.fetch = original;
  };
}

test("访问令牌过期时自动续期并重放原请求", async () => {
  const calls = [];
  let token = "stale";
  const restore = stub(async (url, init) => {
    calls.push(init.headers.Authorization ?? url);
    if (init.headers.Authorization === "Bearer stale") {
      return reply(401, { detail: "token_expired" });
    }
    return reply(200, { days: 7 });
  });
  try {
    let refreshed = 0;
    const client = createApiClient({
      baseUrl: "http://c",
      getToken: async () => token,
      onRefresh: async () => {
        refreshed += 1;
        token = "fresh";
        return token;
      },
    });
    const body = await client.weeklyReview(7);
    assert.deepEqual(body, { days: 7 });
    assert.equal(refreshed, 1);
    assert.equal(calls.length, 2);
  } finally {
    restore();
  }
});

test("并发请求同时撞上过期，只续期一次", async () => {
  let token = "stale";
  let refreshed = 0;
  const restore = stub(async (url, init) => {
    if (init.headers.Authorization === "Bearer fresh") return reply(200, { ok: true });
    return reply(401, { detail: "token_expired" });
  });
  try {
    const client = createApiClient({
      baseUrl: "http://c",
      getToken: async () => token,
      onRefresh: async () => {
        refreshed += 1;
        await new Promise((resolve) => setTimeout(resolve, 5));
        token = "fresh";
        return token;
      },
    });
    await Promise.all([client.weeklyReview(7), client.weeklyReview(7)]);
    assert.equal(refreshed, 1);
  } finally {
    restore();
  }
});

test("续期失败时把错误抛回调用方，由它决定退回登录", async () => {
  const restore = stub(async (url, init) => {
    if (init.headers.Authorization === "Bearer stale") return reply(401, { detail: "token_expired" });
    return reply(200, { ok: true });
  });
  try {
    const client = createApiClient({
      baseUrl: "http://c",
      getToken: async () => "stale",
      onRefresh: async () => {
        throw new ApiError(401, "invalid_refresh_token", { detail: "invalid_refresh_token" }, {
          method: "POST",
          url: "http://c/auth/refresh",
        });
      },
    });
    await assert.rejects(
      () => client.weeklyReview(7),
      (error) => error.status === 401 && error.code === "invalid_refresh_token"
    );
  } finally {
    restore();
  }
});

test("没有续期能力时保持原有行为，不自动重试", async () => {
  let calls = 0;
  const restore = stub(async () => {
    calls += 1;
    return reply(401, { detail: "token_expired" });
  });
  try {
    const client = createApiClient({ baseUrl: "http://c", getToken: async () => "stale" });
    await assert.rejects(() => client.weeklyReview(7), (error) => error.status === 401);
    assert.equal(calls, 1);
  } finally {
    restore();
  }
});
