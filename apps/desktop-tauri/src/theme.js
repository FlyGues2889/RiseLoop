import { isTauri } from "@tauri-apps/api/core";

const DARK_QUERY = "(prefers-color-scheme: dark)";

export function applyTheme(dark) {
  const root = document.documentElement;
  root.classList.toggle("dark-theme", dark);
  root.classList.toggle("light-theme", !dark);
  root.style.colorScheme = dark ? "dark" : "light";
}

/**
 * 跟随系统亮暗色；Tauri 下额外监听窗口 theme 变化（Windows 更可靠）。
 * 返回清理函数，便于测试或多实例场景。
 */
export function initSystemTheme() {
  const media = typeof window !== "undefined" ? window.matchMedia?.(DARK_QUERY) : null;
  const apply = (dark) => applyTheme(Boolean(dark));

  apply(media?.matches ?? false);
  const onChange = (event) => apply(event.matches);
  media?.addEventListener?.("change", onChange);

  let unlisten = null;
  if (isTauri()) {
    import("@tauri-apps/api/window")
      .then(({ getCurrentWindow }) => {
        const current = getCurrentWindow();
        current
          .theme()
          .then((theme) => {
            if (theme) apply(theme === "dark");
          })
          .catch(() => {});
        current
          .onThemeChanged(({ payload }) => {
            if (payload) apply(payload === "dark");
          })
          .then((dispose) => {
            unlisten = dispose;
          })
          .catch(() => {});
      })
      .catch(() => {});
  }

  return () => {
    media?.removeEventListener?.("change", onChange);
    if (typeof unlisten === "function") unlisten();
  };
}
