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
}

const STATUS_HINTS = {
  401: "登录状态已失效，请重新登录。",
  403: "当前操作被安全策略拦截。",
  404: "请求的资源不存在，可能已被重置。",
  409: "该邮箱已注册，直接登录即可。",
  422: "提交的参数不合法，请检查后重试。",
  501: "该能力尚未开放。",
};

export function describeError(error) {
  if (!(error instanceof ApiError)) {
    return {
      title: "操作失败",
      message: String(error?.message ?? error),
      detail: null,
      hint: null,
    };
  }

  if (error.isNetworkError) {
    return {
      title: "无法连接云服务",
      message: `${error.method} ${error.url} 未响应`,
      detail: error.payload?.cause ?? null,
      hint: "本地演示请先在项目根目录运行 pnpm demo；云端模式请检查服务地址与网络。",
    };
  }

  const message = detailText(error) || error.code || "未知错误";

  if (error.status >= 500) {
    return {
      title: `服务端错误（${error.status}）`,
      message,
      detail: `code: ${error.code ?? "unknown"}`,
      hint: "稍后重试；若持续出现，请查看 cloud-api 日志。",
    };
  }

  return {
    title: `请求失败（${error.status}）`,
    message,
    detail: error.code && error.code !== message ? `code: ${error.code}` : null,
    hint: STATUS_HINTS[error.status] ?? null,
  };
}

function detailText(error) {
  const detail = error.payload?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg ?? JSON.stringify(item)).join("；");
  }
  return error.payload?.message ?? null;
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
      throw new ApiError(
        response.status,
        payload?.detail || payload?.error,
        payload,
        { method, url }
      );
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