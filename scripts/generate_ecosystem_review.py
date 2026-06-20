#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ROOT / "automation" / "ecosystem-sources.json"
DEFAULT_OUTPUT = ROOT / "ecosystem-review.md"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


def load_sources(path: Path = DEFAULT_SOURCES) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("ecosystem sources must include a sources list")
    normalized: list[dict[str, str]] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        source_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or source_id).strip()
        url = str(item.get("url") or "").strip()
        area = str(item.get("area") or "general").strip()
        if source_id and name and url:
            normalized.append({"id": source_id, "name": name, "url": url, "area": area})
    return normalized


def fetch_source_status(sources: list[dict[str, str]], timeout_seconds: float = 6.0) -> list[dict[str, str]]:
    statuses: list[dict[str, str]] = []
    for source in sources:
        request = urllib.request.Request(
            source["url"],
            headers={
                "User-Agent": "AcrossAgentsAssistantEcosystemReview/1.0",
                "Accept": "text/html,application/json,text/plain;q=0.8,*/*;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                statuses.append(
                    {
                        **source,
                        "status": str(response.status),
                        "last_modified": response.headers.get("Last-Modified", ""),
                    }
                )
        except Exception as exc:
            statuses.append({**source, "status": "unavailable", "last_modified": "", "error": type(exc).__name__})
    return statuses


def _extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()
    parts: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(part.strip() for part in parts if part.strip())


def run_openai_web_research(sources: list[dict[str, str]], *, model: str, api_key: str | None) -> str:
    if not api_key:
        return (
            "Live web research was not run because OPENAI_API_KEY is not configured. "
            "The scheduled workflow still records the source registry and review checklist."
        )
    source_lines = "\n".join(f"- {source['name']} ({source['area']}): {source['url']}" for source in sources)
    prompt = textwrap.dedent(
        f"""
        You are preparing an engineering ecosystem review for Across Agents Assistant.
        Search the web when useful and produce a concise, source-grounded digest.

        Focus areas:
        - agent workflow automation
        - agent observability, tracing, and evaluation
        - GitHub Actions automation and issue/PR workflows
        - macOS Swift client implications
        - Python backend and Node plugin ecosystem implications

        Known source registry:
        {source_lines}

        Output exactly these sections:
        1. Notable changes worth tracking
        2. Candidate integrations for AAA / Orchestrator / Context
        3. Risks or reasons to wait
        4. Suggested next issue or RFC
        """
    ).strip()
    body = json.dumps(
        {
            "model": model,
            "tools": [{"type": "web_search"}],
            "input": prompt,
            "max_output_tokens": 1800,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        return f"Live web research failed with HTTP {exc.code}: {detail}"
    except Exception as exc:
        return f"Live web research failed with {type(exc).__name__}: {exc}"
    return _extract_response_text(payload) or "Live web research returned no text."


def build_report(
    *,
    sources: list[dict[str, str]],
    statuses: list[dict[str, str]],
    web_research: str,
    generated_at: str,
    mode: str,
) -> str:
    lines = [
        "# Across Ecosystem Review",
        "",
        f"Generated at: {generated_at}",
        f"Mode: {mode}",
        "",
        "## Source Registry",
        "",
    ]
    for source in statuses:
        status = source.get("status", "not_checked")
        modified = source.get("last_modified") or "unknown"
        lines.append(f"- {source['name']} ({source['area']}): {status}, last modified {modified}")
        lines.append(f"  - {source['url']}")
    lines.extend(
        [
            "",
            "## Web Research Digest",
            "",
            web_research.strip(),
            "",
            "## Review Checklist",
            "",
            "- [ ] Decide whether any item needs an RFC before code.",
            "- [ ] If code is warranted, map ownership to AAA, Orchestrator, or Context.",
            "- [ ] Require local tests and GitHub CI before merge.",
            "- [ ] Require Live E2E evidence before an AAA release.",
            "- [ ] Keep protocol/runtime changes out of auto-merge unless explicitly approved.",
            "",
            "## Automation Policy",
            "",
            "- Default action: create a review issue and attach this report.",
            "- Low-risk allowed automation: docs, dependency hygiene, and generated reports.",
            "- Gated automation: runtime protocols, release tags, secrets, signing, and cross-repo version pins.",
            "- Release automation must preserve the existing release process and evidence chain.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Across ecosystem review report.")
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--mode", default="scheduled")
    parser.add_argument("--fetch", action="store_true", help="Fetch source status metadata.")
    parser.add_argument("--web-research", action="store_true", help="Use OpenAI Responses web search when configured.")
    parser.add_argument("--model", default=os.environ.get("ACROSS_ECOSYSTEM_REVIEW_MODEL", "gpt-5.1-mini"))
    args = parser.parse_args(argv)

    sources = load_sources(args.sources)
    statuses = fetch_source_status(sources) if args.fetch else [{**source, "status": "not_checked", "last_modified": ""} for source in sources]
    if args.web_research:
        web_research = run_openai_web_research(sources, model=args.model, api_key=os.environ.get("OPENAI_API_KEY"))
    else:
        web_research = "Live web research was not requested for this run."
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report = build_report(
        sources=sources,
        statuses=statuses,
        web_research=web_research,
        generated_at=generated_at,
        mode=args.mode,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
