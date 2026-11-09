const CLOUD_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export const MODES = {
  cloud: {
    id: "cloud",
    label: "云端模式",
    baseUrl: CLOUD_BASE,
    badge: "",
    aiEnabled: true,
    demoAccount: null,
  },
  demo: {
    id: "demo",
    label: "本地模式",
    baseUrl: null,
    badge: "本地模式",
    aiEnabled: false,
    demoAccount: {
      email: "demo@riseloop.app",
      password: "riseloop-demo-pass",
    },
  },
};

export const DEMO_UNAVAILABLE = [
  "智能问答与周报洞察",
  "云端周报汇总",
  "跨设备同步",
];