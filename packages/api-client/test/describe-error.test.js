import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, createApiClient, describeError } from "../src/index.js";

function apiError(status, code, payload = null, url = "http://cloud.test/x") {
  return new ApiError(status, code, payload, { method: "POST", url });
}

test("密码错误说密码错误，不说会话过期", () => {
  const view = describeError(
    apiError(401, "invalid_credentials", { detail: "invalid_credentials" }, "http://c/auth/login")
  );
  assert.equal(view.title, "邮箱或密码不对");
  assert.match(view.hint, /邮箱拼写和密码大小写/);
  assert.ok(!/失效/.test(view.hint));
});

test("受保护接口的 401 才提示登录失效", () => {
  const view = describeError(apiError(401, "invalid_token", { detail: "invalid_token" }));
  assert.equal(view.title, "登录状态已失效");
  assert.equal(apiError(401, "invalid_token").isSessionExpired, true);
});

test("登录接口的 401 不算会话过期", () => {
  const error = apiError(
    401,
    "invalid_credentials",
    { detail: "invalid_credentials" },
    "http://c/auth/login"
  );
  assert.equal(error.isSessionExpired, false);
  assert.equal(apiError(401, null, null, "http://c/auth/login").isSessionExpired, false);
});

test("邮箱已注册、待办缺失都有各自的说法", () => {
  assert.equal(describeError(apiError(409, "email_exists")).title, "这个邮箱已经注册过");
  assert.equal(
    describeError(apiError(404, "no_pending_intervention")).title,
    "现在没有待完成的动作"
  );
  assert.equal(describeError(apiError(404, "action_not_found")).title, "动作库里没找到这个动作");
});

test("未开放能力不再显示裸状态码", () => {
  assert.equal(describeError(apiError(501, "not_implemented")).title, "这项能力还没开放");
  assert.equal(describeError(apiError(501, "local_mode_unavailable")).title, "这项能力暂未开放");
});

test("对象型 detail 不会渲染成 [object Object]", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: false,
    status: 503,
    text: async () =>
      JSON.stringify({ detail: { error: "modelarts_unavailable", reason: "timeout" } }),
  });
  try {
    const client = createApiClient({ baseUrl: "http://c", getToken: async () => null });
    const error = await client.postureInfer({ posture_class: "forward_head" }).catch((e) => e);
    assert.ok(error instanceof ApiError);
    assert.equal(error.code, "modelarts_unavailable");
    const view = describeError(error);
    assert.equal(view.title, "云端姿态模型暂时不可用");
    assert.ok(!/object/i.test(String(view.detail ?? "")));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("本机命令的英文错误被翻译", () => {
  const view = describeError(new Error("threshold must be between 30 and 60 minutes"));
  assert.equal(view.title, "提醒间隔超出范围");
  assert.match(view.hint, /30–60/);
});

test("未知错误保留一行技术细节但不裸露成正文", () => {
  const view = describeError(new Error("boom"));
  assert.equal(view.title, "这一步没完成");
  assert.match(view.hint, /再试一次/);
  assert.equal(view.detail, "boom");
});
