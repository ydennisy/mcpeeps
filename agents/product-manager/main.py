from __future__ import annotations

import asyncio
from typing import Any

from dotenv import load_dotenv
from duckduckgo_search import DDGS
from pydantic_ai import Agent, RunContext

load_dotenv()

SYSTEM_PROMPT = """
You are a product manager.
You are in a chat room with other humans & agents:
- CEO
- swe-agent
- game-tester
You can address them by using @, e.g @swe-agent
Otherwise you will be speaking to everyone.
Everyone sees all messages.
You will collaborate on a task to build a game given by the CEO.

Approach each request with a product strategy mindset:
- Clarify the desired player outcomes, business goals, and success metrics.
- Coordinate requirements across engineering and QA, highlighting trade-offs and next steps.
- When more context is needed, ask concise follow-up questions.
- Keep updates structured with key decisions, open questions, and recommended actions.

You can use the `search_web` tool to perform quick market or reference research. Summarize findings and cite sources inline.
"""


agent = Agent("openai:gpt-4.1", instructions=SYSTEM_PROMPT)


@agent.tool
async def search_web(
    _ctx: RunContext[None],
    query: str,
    max_results: int = 5,
) -> str:
    """Search the web for product insights and summarize the top findings."""

    cleaned_query = query.strip()
    if not cleaned_query:
        return "Please provide a non-empty search query."

    limit = max(1, min(max_results, 10))

    def _perform_search() -> list[dict[str, Any]]:
        with DDGS() as ddgs:
            return list(ddgs.text(cleaned_query, max_results=limit))

    try:
        results = await asyncio.to_thread(_perform_search)
    except Exception as exc:  # pragma: no cover - network/runtime guard
        return f"Web search failed: {exc}"

    if not results:
        return "No search results were found for that query."

    lines: list[str] = [f"Top {len(results)} results for: {cleaned_query}"]
    for idx, item in enumerate(results, start=1):
        title = item.get("title") or "(no title)"
        url = item.get("href") or "(no url)"
        snippet = (item.get("body") or "").strip()
        if snippet:
            snippet = snippet.replace("\n", " ")
        lines.append(f"{idx}. {title}\n   URL: {url}")
        if snippet:
            lines.append(f"   Notes: {snippet}")

    return "\n".join(lines)


app = agent.to_a2a()
