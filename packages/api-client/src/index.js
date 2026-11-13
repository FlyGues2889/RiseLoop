export class ApiError extends Error {
  constructor(status, code, payload, meta = {}) {
    super(code || `request_failed_${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.payload = payload;
    this.method = meta.method ?? "GET";
    this.url = meta.url ?? "";
  }

  get isNetworkError() {
    return this.status === 0;
  }

  get isSafetyShortCircuit() {
    return this.status === 403 && this.payload?.error === "safety_short_circuit";
  }

  get isSessionExpired() {
    // 密码错误也是 401，但它属于“凭据不对”，不该被当成会话过期踢出登录。
    return (
      this.status === 401 &&
      this.code !== "invalid_credentials" &&
      !/\/auth\/(login|register)/.test(this.url ?? "")
    );
  }
}

// 标题给结论，hint 给一句人话 + 下一步；detail 只放错误码这类技术信息。
// 键是后端返回的 error code：同一个 401，密码错误和会话过期要分开说。
const CODE_VIEWS = {
  invalid_credentials: {
    title: "邮箱或密码不对",
    hint: "检查邮箱拼写和密码大小写；忘记密码可以换一个邮箱重新创建账号。",
  },
  email_exists: {
    title: "这个邮箱已经注册过",
    hint: "直接用这个邮箱登录就行。",
  },
  missing_token: {
    title: "还需要先登录",
    hint: "完成登录再试一次。",
  },
  invalid_token: {
    title: "登录状态已失效",
    hint: "重新登录即可继续，本机已有的评估和记录不会丢。",
  },
  token_expired: {
    title: "登录已经过期",
    hint: "太久没使用，重新登录就能接着用。",
  },
  no_pending_intervention: {
    title: "现在没有待完成的动作",
    hint: "等下一次久坐提醒，或在计时栏点“立即开始活动”。",
  },
  action_not_found: {
    title: "动作库里没找到这个动作",
    hint: "云端记录的动作和动作库对不上，再触发一次提醒会重新匹配。",
  },
  not_implemented: {
    title: "这项能力还没开放",
    hint: "不影响评估、计时、干预、反馈这条主线。",
  },
  local_mode_unavailable: {
    title: "本地模式没有这项能力",
    hint: "需要这项能力时切回云端模式。",
  },
  modelarts_unavailable: {
    title: "云端姿态模型暂时不可用",
    hint: "已退回端侧模式，稍后会自动重试。",
  },
  validation_error: {
    title: "提交的内容不完整",
    hint: "检查标红的字段后重试。",
  },
};

const STATUS_VIEWS = {
  401: {
    title: "需要重新登录",
    hint: "云端要求先确认身份，重新登录后即可继续。",
  },
  403: {
    title: "这一步被安全策略拦下",
    hint: "确认账号没错；反复出现就把这条提示发给我们。",
  },
  404: {
    title: "找不到要用的数据",
    hint: "服务端可能已清理这条记录，刷新或重新走一遍流程。",
  },
  409: {
    title: "数据状态对不上",
    hint: "服务端当前的记录和这次请求冲突，刷新后重试。",
  },
  422: {
    title: "提交的内容不完整",
    hint: "有字段缺失或格式不对，检查后重试。",
  },
  429: {
    title: "请求有点频繁",
    hint: "短时间内调用超过上限，等一分钟再试。",
  },
};

// 本机命令（Rust 侧）返回普通字符串，同样翻译成一句人话。
const INVOKE_VIEWS = [
  {
    match: /threshold must be between/i,
    title: "提醒间隔超出范围",
    hint: "久坐阈值只能在 30–60 分钟之间，改成区间内的数字再试。",
  },
  {
    match: /keyring|credential|NoEntry|钥匙串/i,
    title: "系统钥匙串没有响应",
    hint: "登录凭证没能读写成，这次只在本次运行有效，重启后可重新登录。",
  },
];

export function describeError(error) {
  if (!(error instanceof ApiError)) {
    return describePlainError(error);
  }

  if (error.isNetworkError) {
    return {
      title: "连不上云服务",
      hint: "检查网络或服务地址后重试，也可以先切到本地模式。",
      message: null,
      detail: `${error.method} ${error.url}`,
    };
  }

  const code = typeof error.code === "string" ? error.code : null;
  // 登录接口的 401 是凭据不对，不是“会话过期”，按接口语义兜一层。
  const codeView =
    CODE_VIEWS[code] ??
    (error.status === 401 && !error.isSessionExpired ? CODE_VIEWS.invalid_credentials : null);
  if (codeView) return finish(codeView, error, code);

  if (error.status >= 500) {
    return finish(
      {
        title: `服务端暂时出错（${error.status}）`,
        hint: "稍等再试；一直失败就把时间点告诉我们。",
      },
      error,
      code
    );
  }

  const statusView = STATUS_VIEWS[error.status];
  if (statusView) return finish(statusView, error, code);

  return finish(
    {
      title: `请求没成功（${error.status}）`,
      hint: "服务端返回了没预料到的结果，重试一次；反复出现就把这条提示发给我们。",
    },
    error,
    code
  );
}

function finish(view, error, code) {
  const fieldErrors = fieldErrorText(error);
  return {
    title: view.title,
    hint: view.hint ?? null,
    message: null,
    detail: fieldErrors ?? (code ? `错误码：${code}` : null),
  };
}

function fieldErrorText(error) {
  const detail = error.payload?.detail;
  if (!Array.isArray(detail)) return null;
  return detail
    .map((item) => item?.msg ?? String(item))
    .filter(Boolean)
    .join("；");
}

function describePlainError(error) {
  const text = String(error?.message ?? error ?? "");
  const known = INVOKE_VIEWS.find((item) => item.match.test(text));
  if (known) {
    return { title: known.title, hint: known.hint, message: null, detail: null };
  }
  return {
    title: "这一步没完成",
    hint: "本机操作没有执行成功，再试一次；反复失败就把这条提示发给我们。",
    message: null,
    detail: text || null,
  };
}

// 后端 detail 可能是字符串、对象（如 503 的 {error, reason}）或校验数组，
// 统一压成 code，否则前端只能拿到 [object Object]。
function normalizeCode(payload) {
  if (!payload) return null;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return "validation_error";
  if (detail && typeof detail === "object") {
    return detail.error ?? detail.code ?? normalizeCode({ detail: payload.error });
  }
  return typeof payload.error === "string" ? payload.error : null;
}

export function createApiClient({ baseUrl, getBaseUrl, getToken }) {
  const resolveBaseUrl = getBaseUrl ?? (() => baseUrl);

  async function request(path, { method = "GET", body, auth = true } = {}) {
    const headers = { Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (auth) {
      const token = await getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }

    const url = `${resolveBaseUrl()}${path}`;
    let response;
    try {
      response = await fetch(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      throw new ApiError(0, "network_unreachable", { cause: String(error) }, { method, url });
    }

    const text = await response.text();
    const payload = text ? safeParse(text) : null;
    if (!response.ok) {
      throw new ApiError(response.status, normalizeCode(payload), payload, { method, url });
    }
    return payload;
  }

  return {
    health: () => request("/health/live", { auth: false }),
    register: (email, password) =>
      request("/auth/register", { method: "POST", body: { email, password }, auth: false }),
    login: (email, password) =>
      request("/auth/login", { method: "POST", body: { email, password }, auth: false }),
    assessment: (payload) => request("/assessment", { method: "POST", body: payload }),
    heartbeat: (payload) => request("/sitting/heartbeat", { method: "POST", body: payload }),
    postureRisk: (payload) => request("/posture/risk", { method: "POST", body: payload }),
    postureInfer: (payload) => request("/posture/infer", { method: "POST", body: payload }),
    currentIntervention: () => request("/intervention/current"),
    feedback: (payload) => request("/intervention/feedback", { method: "POST", body: payload }),
    askQuestion: (payload) => request("/qa/ask", { method: "POST", body: payload }),
    weeklyReview: (days = 7) => request(`/review/weekly?days=${days}`),
    actions: (state, { bodyPart, maxMinutes } = {}) => {
      const query = new URLSearchParams();
      if (bodyPart) query.set("body_part", bodyPart);
      if (maxMinutes) query.set("max_minutes", String(maxMinutes));
      const qs = query.toString();
      const suffix = qs ? `?${qs}` : "";
      return request(`/actions/${state}${suffix}`);
    },
  };
}

function safeParse(text) {
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}
