// 动作示意图：AI 生成的插画统一 4:3，构建时被 Vite 收进产物（本地包，不走网络）。
const FILES = import.meta.glob("../assets/actions/*.webp", {
  eager: true,
  query: "?url",
  import: "default",
});

const IMAGES = {};
for (const [path, url] of Object.entries(FILES)) {
  const id = path.split("/").pop().replace(/\.webp$/, "");
  IMAGES[id] = url;
}

/** 取动作示意图地址；没有对应图时返回空串，调用方据此隐藏。 */
export function actionImage(id) {
  return id ? IMAGES[id] ?? "" : "";
}
