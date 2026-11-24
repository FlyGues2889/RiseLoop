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

// 标题给结论，hint 给出下一步；detail 只放错误码这类技术信息。
// 键是后端返回的 error code：同一个 401，密码错误和会话过期要分开说。
const CODE_VIEWS = {
  invalid_credentials: {
    title: "邮箱或密码不正确",
    hint: "请检查邮箱拼写与密码大小写；忘记密码可更换邮箱重新创建账号。",
  },
  email_exists: {
    title: "该邮箱已注册",
    hint: "请直接使用该邮箱登录。",
  },
  missing_token: {
    title: "需要先登录",
    hint: "请完成登录后重试。",
  },
  invalid_token: {
    title: "登录状态已失效",
    hint: "重新登录即可继续，本机已有的评估与记录不会丢失。",
  },
  token_expired: {
    title: "登录已过期",
    hint: "长时间未使用，重新登录后即可继续。",
  },
  token_revoked: {
    title: "该登录已退出",
    hint: "因更换设备或退出登录，请重新登录后继续。",
  },
  invalid_refresh_token: {
    title: "登录状态需要重新确认",
    hint: "请重新登录，本机评估与记录不受影响。",
  },
  refresh_expired: {
    title: "登录已超过有效期",
    hint: "重新登录后即可继续。",
  },
  rate_limited: {
    title: "请求过于频繁",
    hint: "短时间内操作次数过多，请等待一分钟后重试。",
  },
  user_not_found: {
    title: "该账号已不存在",
    hint: "如曾删除账号，请重新注册。",
  },
  no_pending_intervention: {
    title: "当前没有待完成的动作",
    hint: "请等待下一次久坐提醒，或在计时栏点击「现在开始」。",
  },
  action_not_found: {
    title: "动作库中未找到该动作",
    hint: "云端记录的动作与动作库不一致，再次触发提醒后将重新匹配。",
  },
  not_implemented: {
    title: "该能力尚未开放",
    hint: "评估、计时、干预与反馈不受影响。",
  },
  local_mode_unavailable: {
    title: "本地模式没有这项能力",
    hint: "切换回云端模式后可使用。",
  },
  modelarts_unavailable: {
    title: "云端姿态模型暂时不可用",
    hint: "姿态判定已暂停，稍后将自动重试。",
  },
  validation_error: {
    title: "提交的内容不完整",
    hint: "请检查标记的字段后重试。",
  },
};

const STATUS_VIEWS = {
  401: {
    title: "需要重新登录",
    hint: "云端要求先确认身份，请重新登录后继续。",
  },
  403: {
    title: "操作已被安全策略拦截",
    hint: "请确认账号无误；若反复出现，请重启应用。",
  },
  404: {
    title: "未找到所需数据",
    hint: "服务端可能已清理该记录，请刷新或重新走一遍流程。",
  },
  409: {
    title: "数据状态不一致",
    hint: "服务端记录与本次请求冲突，请刷新后重试。",
  },
  422: {
    title: "提交的内容不完整",
    hint: "存在缺失或格式不正确的字段，请检查后重试。",
  },
  429: {
    title: "请求过于频繁",
    hint: "短时间内调用超过上限，请等待一分钟后重试。",
  },
};

// 本机命令（Rust 侧）返回普通字符串，同样翻译成用户能执行的一步。
const INVOKE_VIEWS = [
  {
    match: /threshold must be between/i,
    title: "提醒间隔超出范围",
    hint: "提醒间隔只能设为 30–60 分钟，请修改为区间内的数值后重试。",
  },
  {
    match: /keyring|credential|NoEntry|钥匙串/i,
    title: "登录凭证保存失败",
    hint: "本次运行期间仍可正常使用，重启后需重新登录。",
  },
];

export function describeError(error) {
  if (!(error instanceof ApiError)) {
    return describePlainError(error);
  }

  if (error.isNetworkError) {
    return {
      title: "无法连接云服务",
      hint: "请检查网络与服务地址后重试。",
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
        hint: "请稍后重试；若持续失败，请重启应用。",
      },
      error,
      code
    );
  }

  const statusView = STATUS_VIEWS[error.status];
  if (statusView) return finish(statusView, error, code);

  return finish(
    {
      title: `请求未成功（${error.status}）`,
      hint: "服务端返回了预期外的结果，请重试；若反复出现，请重启应用。",
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
    title: "操作未完成",
    hint: "本机操作未执行成功，请再试一次；若反复失败，请重启应用。",
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

export function createApiClient({ baseUrl, getBaseUrl, getToken, onRefresh }) {
  const resolveBaseUrl = getBaseUrl ?? (() => baseUrl);
  // 后台心跳、周报、反馈可能同时撞上过期的访问令牌，只换一次，
  // 否则轮换出来的刷新令牌会被后一次覆盖
  let refreshing = null;

  function refreshSession() {
    if (!onRefresh) return null;
    refreshing ??= Promise.resolve()
      .then(() => onRefresh())
      .finally(() => {
        refreshing = null;
      });
    return refreshing;
  }

  async function request(path, options = {}, retried = false) {
    const { method = "GET", body, auth = true } = options;
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
      const error = new ApiError(response.status, normalizeCode(payload), payload, { method, url });
      // 访问令牌只有一个小时寿命，久坐提醒一次就是 45 分钟：
      // 撞上过期就用刷新令牌续期，再放一遍原请求，不让用户掉登录
      if (auth && !retried && error.isSessionExpired && onRefresh) {
        const token = await refreshSession();
        if (token) return request(path, options, true);
      }
      throw error;
    }
    return payload;
  }

  return {
    health: () => request("/health/live", { auth: false }),
    register: (email, password) =>
      request("/auth/register", { method: "POST", body: { email, password }, auth: false }),
    login: (email, password) =>
      request("/auth/login", { method: "POST", body: { email, password }, auth: false }),
    refresh: (refreshToken) =>
      request("/auth/refresh", { method: "POST", body: { refresh_token: refreshToken }, auth: false }),
    logout: (refreshToken) =>
      request("/auth/logout", {
        method: "POST",
        body: refreshToken ? { refresh_token: refreshToken } : {},
      }),
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
