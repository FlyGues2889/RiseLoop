// 跨语言一致性测试的 JS 侧桥接脚本（Node）。
// 用法：node scripts/engine_dump.mjs < cases.json
// 输入：JSON 数组，每项为 { state, feedback, counters? }
// 输出：JSON 数组，逐项为 local-engine decide() 的完整输出
// 仅导入 packages/local-engine/src/machine.js 纯函数，不发网络请求、不落盘。
import { decide, emptyCounters } from "../packages/local-engine/src/machine.js";

const chunks = [];
process.stdin.on("data", (chunk) => chunks.push(chunk));
process.stdin.on("end", () => {
  let cases;
  try {
    cases = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch (error) {
    process.stderr.write(`invalid input json: ${error.message}\n`);
    process.exit(1);
  }
  const outputs = cases.map(({ state, feedback, counters }) =>
    decide(state, feedback, counters ?? emptyCounters())
  );
  process.stdout.write(JSON.stringify(outputs));
});
