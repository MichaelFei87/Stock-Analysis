"""tavily_search.py — Tavily Search API wrapper for stock-analyze skill.

Thin wrapper around Tavily REST API. Falls back gracefully when API key is
missing (returns empty list + stderr hint). No extra dependencies beyond
`requests` (already required by pdf_reader).

Usage:
    python3 -m scripts.tavily_search "贵州茅台 2025年年度报告" --domains cninfo.com.cn
    python3 -m scripts.tavily_search "腾讯控股 游戏业务" --max-results 10 --depth advanced
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass

import requests

from . import config

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


@dataclass
class SearchResult:
    title: str
    url: str
    content: str
    score: float

    def __str__(self) -> str:
        return f"[{self.score:.2f}] {self.title}\n    {self.url}\n    {self.content[:200]}"


def tavily_search(
    query: str,
    *,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    search_depth: str = "basic",
    timeout: int = 15,
) -> list[SearchResult]:
    """Search via Tavily API. Returns empty list on any failure (graceful degradation).

    Args:
        query: Search query string (same syntax as Google/WebSearch).
        max_results: Number of results to return (1-20).
        include_domains: Restrict results to these domains (e.g. ["cninfo.com.cn"]).
        search_depth: "basic" (fast, cheaper) or "advanced" (deeper, costs 2 credits).
        timeout: Request timeout in seconds.

    Returns:
        List of SearchResult sorted by relevance score (descending).
    """
    api_key = config.TAVILY_API_KEY
    if not api_key:
        print("[tavily] ⚠️ TAVILY_API_KEY 未设置,跳过 Tavily 搜索", file=sys.stderr)
        return []

    payload: dict = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
    }
    if include_domains:
        payload["include_domains"] = include_domains

    try:
        resp = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[tavily] ❌ 请求失败: {e}", file=sys.stderr)
        return []
    except (ValueError, KeyError) as e:
        print(f"[tavily] ❌ 响应解析失败: {e}", file=sys.stderr)
        return []

    results: list[SearchResult] = []
    for item in data.get("results", []):
        results.append(
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=item.get("score", 0.0),
            )
        )
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Tavily Search API wrapper")
    ap.add_argument("query", help="Search query")
    ap.add_argument("--max-results", type=int, default=5, help="Max results (default 5)")
    ap.add_argument("--domains", help="Comma-separated domain filter (e.g. cninfo.com.cn,hkex.com.hk)")
    ap.add_argument("--depth", choices=["basic", "advanced"], default="basic", help="Search depth")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    domains = [d.strip() for d in args.domains.split(",")] if args.domains else None
    results = tavily_search(
        args.query,
        max_results=args.max_results,
        include_domains=domains,
        search_depth=args.depth,
    )

    if not results:
        print("(无结果)")
        return 0

    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        for i, r in enumerate(results, 1):
            print(f"\n--- 结果 {i} ---")
            print(r)

    print(f"\n共 {len(results)} 条结果", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
