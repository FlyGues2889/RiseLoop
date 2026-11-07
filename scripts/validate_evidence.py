#!/usr/bin/env python3
"""G4 门禁：校验 data/knowledge/evidence.json。

只依赖标准库，执行 evidence.schema.json 中的最小 JSON Schema 子集：
type / required / properties / additionalProperties(false) / items /
minItems / maxItems / uniqueItems / enum / const / minLength / maxLength /
minimum / maximum / pattern / format(date, uri) / anyOf / oneOf / allOf。

除 Schema 外还检查两条台账规则：
1. id、doi、pmid 全表唯一（空值不参与）；
2. verified=false 时 notes 必须非空（说明未核验原因）。

用法：
    python scripts/validate_evidence.py
    python scripts/validate_evidence.py --data data/knowledge/evidence.json
    python scripts/validate_evidence.py --schema path/to/schema.json --quiet

退出码：0 = 0 error；1 = 有 error；2 = 文件读取或 Schema 结构问题。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "data" / "knowledge" / "evidence.schema.json"
DEFAULT_DATA = ROOT / "data" / "knowledge" / "evidence.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_type(value: object, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if name == "object":
        return isinstance(value, dict)
    if name == "array":
        return isinstance(value, list)
    if name == "string":
        return isinstance(value, str)
    if name == "boolean":
        return isinstance(value, bool)
    if name == "null":
        return value is None
    return True  # 未知类型名不阻塞，交由 Schema 自检时报告


def check_format(value: str, fmt: str, path: str, errors: list[str]) -> None:
    if fmt == "date":
        if not DATE_RE.match(value):
            errors.append(f"{path}: 日期须为 YYYY-MM-DD，实际 {value!r}")
            return
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            errors.append(f"{path}: 非法日期 {value!r}")
    elif fmt == "uri":
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append(f"{path}: 须为 http(s) 绝对地址，实际 {value!r}")
    elif fmt == "email":
        if not EMAIL_RE.match(value):
            errors.append(f"{path}: 不是合法邮箱，实际 {value!r}")


def validate(value: object, schema: dict, path: str, errors: list[str]) -> None:
    if not isinstance(schema, dict):
        errors.append(f"{path}: schema 片段不是对象")
        return

    expected = schema.get("type")
    if expected is not None:
        names = [expected] if isinstance(expected, str) else list(expected)
        if not any(is_type(value, name) for name in names):
            actual = "null" if value is None else type(value).__name__
            errors.append(f"{path}: 类型应为 {'/'.join(names)}，实际 {actual}")
            return

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: 应恒为 {schema['const']!r}，实际 {value!r}")

    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: 取值 {value!r} 不在枚举 {schema['enum']} 内")

    for sub in schema.get("allOf", []):
        validate(value, sub, path, errors)

    if "anyOf" in schema:
        branches = []
        for sub in schema["anyOf"]:
            branch_errors: list[str] = []
            validate(value, sub, path, branch_errors)
            branches.append(branch_errors)
        if all(branch for branch in branches):
            errors.append(f"{path}: 不满足 anyOf 任一分支：{value!r}")

    if "oneOf" in schema:
        passed = 0
        diagnostics: list[list[str]] = []
        for sub in schema["oneOf"]:
            branch_errors: list[str] = []
            validate(value, sub, path, branch_errors)
            diagnostics.append(branch_errors)
            if not branch_errors:
                passed += 1
        if passed != 1:
            errors.append(f"{path}: oneOf 需恰好命中 1 个分支，实际命中 {passed} 个")
            if passed == 0:
                # 命中 0 个时补一条真实原因，避免只报“oneOf 不满足”而无从修起
                for branch_errors in diagnostics:
                    for item in branch_errors:
                        if "类型应为" not in item:
                            errors.append(item)

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{path}: 长度 {len(value)} 小于 minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: 长度 {len(value)} 超过 maxLength {schema['maxLength']}（{value[:20]}…）")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: 不匹配 pattern {schema['pattern']}，实际 {value!r}")
        if "format" in schema:
            check_format(value, schema["format"], path, errors)
        return

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} 小于 minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} 大于 maximum {schema['maximum']}")
        return

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: 元素数 {len(value)} 少于 minItems {schema['minItems']}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: 元素数 {len(value)} 超过 maxItems {schema['maxItems']}")
        if schema.get("uniqueItems"):
            seen: list[str] = []
            for index, item in enumerate(value):
                key = json.dumps(item, ensure_ascii=False, sort_keys=True)
                if key in seen:
                    errors.append(f"{path}[{index}]: 重复元素（uniqueItems）")
                seen.append(key)
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                validate(item, item_schema, f"{path}[{index}]", errors)
        return

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: 缺必填字段 {key}")
        props = schema.get("properties", {})
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in props:
                validate(item, props[key], child_path, errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: 出现未定义字段 {key}")
            elif isinstance(schema.get("additionalProperties"), dict):
                validate(item, schema["additionalProperties"], child_path, errors)


def uniqueness_errors(records: list[dict]) -> list[str]:
    errors: list[str] = []
    for field, label in (("id", "id"), ("doi", "DOI"), ("pmid", "PMID")):
        seen: dict[str, int] = {}
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                continue
            key = record.get(field)
            if not isinstance(key, str) or not key:
                continue
            if key.lower() in seen:
                errors.append(
                    f"$[{index}].{field}: {label} 重复（与 $[{seen[key.lower()]}].{field} 相同：{key}）"
                )
            else:
                seen[key.lower()] = index
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        if record.get("verified") is False and not (record.get("notes") or "").strip():
            errors.append(f"$[{index}].notes: verified=false 时必须写明未核验原因")
    return errors


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="校验 RiseLoop 文献台账")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="evidence.json 路径")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA), help="evidence.schema.json 路径")
    parser.add_argument("--quiet", action="store_true", help="只输出结果行")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    data_path = Path(args.data)

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[FATAL] 找不到 Schema：{schema_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"[FATAL] Schema 不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    if not isinstance(schema, dict) or schema.get("type") != "array":
        print("[FATAL] Schema 顶层必须是 type=array", file=sys.stderr)
        return 2

    try:
        records = json.loads(data_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"[FATAL] 找不到台账：{data_path}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"[FATAL] 台账不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    if not isinstance(records, list):
        print("[FATAL] 台账顶层必须是数组", file=sys.stderr)
        return 2

    errors: list[str] = []
    for index, record in enumerate(records):
        validate(record, schema["items"], f"$[{index}]", errors)
    errors.extend(uniqueness_errors(records))

    if not args.quiet:
        print(f"Schema : {schema_path}")
        print(f"Data   : {data_path}")
        print(f"Records: {len(records)}")

    if errors:
        for item in errors:
            print(f"[ERROR] {item}")
        print(f"{len(errors)} error — 不满足 G4，禁止写入 evidence.json")
        return 1

    print("0 error — G4 通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
