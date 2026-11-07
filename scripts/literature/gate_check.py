#!/usr/bin/env python3
"""G1 门禁：校验 docs/theory/run-2026-11-07/g1-plan.json 是否可放行 Phase 2。

G1 是“人工确认检索式与来源”，本脚本只判定确认单是否完整、自洽，不代替人做判断。
唯一能改变状态的操作是 --sign，且必须由人提供署名；实名模式还必须提供真实邮箱。

采集身份两种模式：
    anonymous  —— contact 必须为 null；User-Agent 不含邮箱；速率 ≤1 req/s；单批 ≤20 条
    identified —— contact.email 必填且格式合法；速率仍 ≤1 req/s

用法：
    python scripts/literature/gate_check.py
    python scripts/literature/gate_check.py --sign --by "张三"
    python scripts/literature/gate_check.py --sign --by "张三" --mode identified --email "z@example.com"

退出码：0 = G1 通过；1 = 有未满足项；2 = 文件缺失或参数错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "theory" / "run-2026-11-07" / "g1-plan.json"

EXPECTED_TOPICS = {
    "sedentary-threshold": "久坐阈值与打断频率",
    "micro-break-workplace": "微休息与工作场所干预",
    "neck-shoulder": "颈肩不适",
    "low-back": "腰背不适",
    "safety-redflag": "安全红线与就医边界",
    "bct": "行为改变技术（BCT）",
}
EXPECTED_SOURCES = {
    "pubmed", "crossref", "openalex", "who", "cdc", "niosh", "nhc", "cnki-wanfang"
}
NO_CRAWL_SOURCES = {"nhc", "cnki-wanfang"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RATE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*req/s")


def contact_email(plan: dict) -> str:
    """兼容 contact 为 null / {email} / 字符串三种写法。"""
    contact = plan.get("contact")
    if isinstance(contact, dict):
        return str(contact.get("email") or "").strip()
    if isinstance(contact, str):
        return contact.strip()
    return ""


def source_rate(source: dict) -> float | None:
    match = RATE_RE.search(str(source.get("rate_limit", "")))
    return float(match.group(1)) if match else None


def check(plan: dict) -> tuple[list[str], list[str]]:
    ok: list[str] = []
    errors: list[str] = []

    # 1. 签字状态
    if plan.get("status") != "confirmed":
        errors.append(f"status 不是 confirmed（当前 {plan.get('status')!r}），G1 未签字")
    else:
        ok.append("status=confirmed")
    if not str(plan.get("confirmed_by") or "").strip():
        errors.append("confirmed_by 为空，无法追溯确认人")
    else:
        ok.append(f"confirmed_by={plan['confirmed_by']}")
    confirmed_at = plan.get("confirmed_at")
    if not isinstance(confirmed_at, str) or not DATE_RE.match(confirmed_at):
        errors.append("confirmed_at 缺失或不是 YYYY-MM-DD")
    else:
        try:
            date.fromisoformat(confirmed_at)
            ok.append(f"confirmed_at={confirmed_at}")
        except ValueError:
            errors.append(f"confirmed_at 非法日期：{confirmed_at}")

    # 2. 采集身份模式
    mode = plan.get("api_mode")
    contact_text = contact_email(plan)
    if mode == "anonymous":
        if contact_text:
            errors.append(f"api_mode=anonymous 时 contact 必须为 null，实际含邮箱 {contact_text}")
        else:
            ok.append("api_mode=anonymous，contact=null")
        if plan.get("contact") not in (None, ""):
            errors.append("api_mode=anonymous 时 contact 字段必须为 null（不接受对象或字符串）")
    elif mode == "identified":
        if not contact_text:
            errors.append("api_mode=identified 时必须提供 contact.email")
        elif not EMAIL_RE.match(contact_text):
            errors.append(f"contact.email 不是合法邮箱：{contact_text!r}")
        else:
            ok.append(f"api_mode=identified，contact.email={contact_text}")
    else:
        errors.append(f"api_mode 必须是 anonymous 或 identified，实际 {mode!r}")

    # 3. 速率与批量（两种模式共同底线）
    rate = plan.get("rate_limit_per_second")
    if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate <= 0:
        errors.append(f"rate_limit_per_second 必须是正数，实际 {rate!r}")
    elif rate > 1:
        errors.append(f"rate_limit_per_second 必须 ≤1，实际 {rate}")
    else:
        ok.append(f"rate_limit_per_second={rate}")

    batch_size = plan.get("batch_size")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 20:
        errors.append(f"batch_size 必须是 1–20 的整数，实际 {batch_size!r}")
    else:
        ok.append(f"batch_size={batch_size}")

    # 4. User-Agent 不得泄露身份
    ua = str(plan.get("user_agent") or "")
    if not ua.strip():
        errors.append("缺 user_agent")
    elif "@" in ua or "mailto" in ua.lower() or "email" in ua.lower():
        errors.append(f"User-Agent 不得包含邮箱或 mailto：{ua!r}")
    else:
        ok.append(f"user_agent={ua}")

    # 5. 主题覆盖与检索式
    topics = plan.get("topics") or []
    got_ids = {topic.get("id") for topic in topics if isinstance(topic, dict)}
    missing = sorted(set(EXPECTED_TOPICS) - got_ids)
    extra = sorted(got_ids - set(EXPECTED_TOPICS))
    if missing:
        errors.append(f"缺主题：{missing}")
    if extra:
        errors.append(f"出现未登记主题：{extra}")
    if not missing and not extra:
        ok.append("六主题齐全")

    for topic in topics:
        tid = topic.get("id", "?")
        queries = topic.get("queries") or {}
        if not isinstance(topic.get("target"), int) or topic["target"] <= 0:
            errors.append(f"{tid}: target 必须是正整数")
        if not str(queries.get("pubmed", "")).strip():
            errors.append(f"{tid}: 缺 PubMed 检索式")
        openalex = queries.get("openalex") or {}
        if not str(openalex.get("search", "")).strip() or not str(openalex.get("filter", "")).strip():
            errors.append(f"{tid}: 缺 OpenAlex search 或 filter")
        if not str(queries.get("crossref", "")).strip():
            errors.append(f"{tid}: 缺 Crossref 检索式")
        zh = queries.get("zh_manual") or []
        if not zh or not all(str(item).strip() for item in zh):
            errors.append(f"{tid}: 缺中文人工检索式（每主题至少 1 条）")

    # 6. 规模
    if topics and all(isinstance(topic.get("target"), int) for topic in topics):
        total = sum(topic["target"] for topic in topics)
        target = plan.get("target_records") or {}
        low = target.get("min_acceptable", 30)
        high = target.get("max_acceptable", 50)
        if total < low or total > high:
            errors.append(f"主题目标合计 {total} 条，超出可接受区间 {low}–{high}")
        else:
            ok.append(f"目标合计 {total} 条（区间 {low}–{high}）")
        if target.get("guidelines_min", 0) < 3:
            errors.append("指南下限少于 3 条，不满足 G5")

    # 7. 来源、速率与模式一致性
    sources = {s.get("id"): s for s in (plan.get("sources") or []) if isinstance(s, dict)}
    if set(sources) != EXPECTED_SOURCES:
        errors.append(
            f"来源清单不完整：缺 {sorted(EXPECTED_SOURCES - set(sources))} / 多 {sorted(set(sources) - EXPECTED_SOURCES)}"
        )
    for sid in sorted(EXPECTED_SOURCES & set(sources)):
        source = sources[sid]
        if not str(source.get("rate_limit", "")).strip():
            errors.append(f"{sid}: 缺 rate_limit")
        if source.get("mode") != mode:
            errors.append(f"{sid}: mode={source.get('mode')!r} 与 api_mode={mode!r} 不一致")
        if sid in NO_CRAWL_SOURCES:
            if source.get("crawl_allowed") is not False:
                errors.append(f"{sid}: 必须 crawl_allowed=false（无公开 API，只允许人工导出）")
            if source.get("rate_limit") != "不采集":
                errors.append(f"{sid}: 必须 rate_limit=不采集")
        else:
            parsed_rate = source_rate(source)
            if parsed_rate is None:
                errors.append(f"{sid}: rate_limit 无法解析出 req/s")
            elif parsed_rate > 1:
                errors.append(f"{sid}: rate_limit {parsed_rate} req/s 超过 1")
    if not any(e.startswith("来源清单") for e in errors):
        ok.append("来源清单与模式一致")

    # 8. 分批计划
    batches = plan.get("batches") or []
    if len(batches) > 3:
        errors.append(f"分批 {len(batches)} 批，超过并行上限 3")
    for batch in batches:
        if not isinstance(batch.get("records_max"), int) or batch["records_max"] > 20:
            errors.append(f"{batch.get('id', '?')}: records_max 必须是 ≤20 的整数")
        if not batch.get("topics"):
            errors.append(f"{batch.get('id', '?')}: 未指定 topics")

    # 9. 时间窗
    window = plan.get("date_window") or {}
    if not DATE_RE.match(str(window.get("from", ""))):
        errors.append("date_window.from 缺失或格式错误")
    else:
        try:
            date.fromisoformat(window["from"])
        except ValueError:
            errors.append(f"date_window.from 非法日期：{window['from']}")

    # 10. 未决项
    for item in plan.get("open_items") or []:
        if item.get("blocking") and item.get("status") != "closed":
            errors.append(f"未决项未关闭：{item.get('id')} {item.get('item')}")

    return ok, errors


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="RiseLoop 文献工作流 G1 门禁")
    parser.add_argument("--plan", default=str(PLAN), help="g1-plan.json 路径")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--sign", action="store_true", help="由人签字放行（需给 --by）")
    parser.add_argument("--by", default="", help="确认人姓名与角色")
    parser.add_argument("--mode", choices=["anonymous", "identified"], default="anonymous")
    parser.add_argument("--email", default="", help="实名模式下的项目联系人邮箱")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[FATAL] 找不到确认单：{plan_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"[FATAL] 确认单不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    if args.sign:
        if not args.by.strip():
            print("[FATAL] --sign 必须提供 --by（确认人姓名与角色）", file=sys.stderr)
            return 2
        email = args.email.strip()
        if args.mode == "identified":
            if not email or not EMAIL_RE.match(email):
                print("[FATAL] identified 模式必须提供合法 --email", file=sys.stderr)
                return 2
            plan["contact"] = {"email": email}
        else:
            plan["contact"] = None
        plan["api_mode"] = args.mode
        for source in plan.get("sources") or []:
            if isinstance(source, dict):
                source["mode"] = args.mode
        plan["status"] = "confirmed"
        plan["confirmed_by"] = args.by.strip()
        plan["confirmed_at"] = date.today().isoformat()
        for item in plan.get("open_items") or []:
            if item.get("id") == "O1" and args.mode == "anonymous":
                item["status"] = "closed"
                item["detail"] = f"已于 {plan['confirmed_at']} 决定匿名采集，不发送邮箱"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"已签字：{plan['confirmed_by']} @ {plan['confirmed_at']}，模式 {args.mode}")

    ok, errors = check(plan)

    if not args.quiet:
        print(f"G1 确认单：{plan_path}")
        for item in ok:
            print(f"[PASS] {item}")
    for item in errors:
        print(f"[FAIL] {item}")

    if errors:
        print(f"{len(errors)} 项未通过 — 禁止进入 Phase 2")
        return 1
    print(f"G1 通过 — 可进入 Phase 2 采集（{plan.get('api_mode')} 模式，1 req/s，单批 ≤20）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
