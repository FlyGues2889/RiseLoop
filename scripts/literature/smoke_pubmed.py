#!/usr/bin/env python3
"""匿名模式连通性冒烟：对 PubMed esearch 发一次请求，验证 200 与检索式可解析。

只做一次请求，不采集记录、不写台账。用于 G1 后、Phase 2 前的链路自检。

用法：
    python scripts/literature/smoke_pubmed.py
    python scripts/literature/smoke_pubmed.py --term "sedentary behavior"

退出码：0 = HTTP 200；1 = 非 200 或网络异常。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
UA = "RiseLoop-lit-ledger/1.0"
DEFAULT_TERM = (
    '("sedentary behavior"[MeSH Terms] OR "sedentary time"[Title/Abstract] '
    'OR "sitting time"[Title/Abstract]) AND ("breaks"[Title/Abstract] '
    'OR "breaking up"[Title/Abstract] OR "bout duration"[Title/Abstract]) '
    "AND 2010:2026[dp] AND humans[MeSH Terms]"
)


def fetch(term: str, timeout: float) -> tuple[int, dict]:
    query = urllib.parse.urlencode(
        {"db": "pubmed", "term": term, "retmax": 2, "retmode": "json", "tool": "RiseLoop-lit-ledger"}
    )
    request = urllib.request.Request(f"{BASE}?{query}", headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="PubMed 匿名连通性冒烟")
    parser.add_argument("--term", default=DEFAULT_TERM)
    parser.add_argument("--timeout", type=float, default=45.0)
    args = parser.parse_args()

    for attempt in (1, 2):
        started = time.monotonic()
        try:
            status, payload = fetch(args.term, args.timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"[FAIL] attempt={attempt} {type(exc).__name__}: {exc}")
            if attempt == 1:
                time.sleep(2)
                continue
            return 1

        elapsed = time.monotonic() - started
        result = payload.get("esearchresult", {})
        print(f"attempt={attempt} status={status} elapsed={elapsed:.2f}s")
        print(f"count={result.get('count')} ids={','.join(result.get('idlist', []))}")
        if result.get("warninglist"):
            print(f"warninglist={result['warninglist']}")
        if result.get("error"):
            print(f"esearch_error={result['error']}")
        if status == 200:
            print("OK — 匿名 UA 可达，检索式可被 PubMed 解析")
            return 0
        print("[FAIL] 非 200")
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
