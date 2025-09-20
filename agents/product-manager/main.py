from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from ddgs import DDGS
from fasta2a import FastA2A, Worker
from fasta2a.broker import InMemoryBroker
from fasta2a.schema import Message, TextPart, TaskSendParams, TaskIdParams, Artifact
from fasta2a.storage import InMemoryStorage
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

# A2A setup for progress streaming
storage = InMemoryStorage()
broker = InMemoryBroker()


@agent.tool
async def search_web(
    ctx: RunContext[dict],
    query: str,
    max_results: int = 5,
) -> str:
    """Search the web for product insights and summarize the top findings."""

    cleaned_query = query.strip()
    if not cleaned_query:
        return "Please provide a non-empty search query."

    limit = max(1, min(max_results, 10))

    # Get task ID from context if available (when running via A2A)
    task_id = getattr(ctx, 'task_id', None) if hasattr(ctx, 'task_id') else ctx.deps.get('task_id') if ctx.deps else None

    # Emit progress update about starting search
    if task_id:
        try:
            await storage.update_task(
                task_id,
                state='working',
                new_messages=[Message(
                    role="agent",
                    kind="message",
                    message_id=str(uuid.uuid4()),
                    parts=[TextPart(kind="text", text=f"🔍 Starting web search for: '{cleaned_query}'")]
                )],
            )
        except Exception:
            pass  # Don't fail the search if progress update fails

    def _perform_search() -> list[dict[str, Any]]:
        with DDGS() as ddgs:
            return list(ddgs.text(cleaned_query, max_results=limit))

    try:
        results = await asyncio.to_thread(_perform_search)
    except Exception as exc:  # pragma: no cover - network/runtime guard
        # Emit error progress update
        if task_id:
            try:
                await storage.update_task(
                    task_id,
                    state='working',
                    new_messages=[Message(
                        role="agent",
                        kind="message",
                        message_id=str(uuid.uuid4()),
                        parts=[TextPart(kind="text", text=f"❌ Web search failed for '{cleaned_query}': {exc}")]
                    )],
                )
            except Exception:
                pass
        return f"Web search failed: {exc}"

    if not results:
        # Emit no results progress update
        if task_id:
            try:
                await storage.update_task(
                    task_id,
                    state='working',
                    new_messages=[Message(
                        role="agent",
                        kind="message",
                        message_id=str(uuid.uuid4()),
                        parts=[TextPart(kind="text", text=f"📭 No search results found for: '{cleaned_query}'")]
                    )],
                )
            except Exception:
                pass
        return "No search results were found for that query."

    # Emit success progress update
    if task_id:
        try:
            await storage.update_task(
                task_id,
                state='working',
                new_messages=[Message(
                    role="agent",
                    kind="message",
                    message_id=str(uuid.uuid4()),
                    parts=[TextPart(kind="text", text=f"✅ Found {len(results)} results for search: '{cleaned_query}'")]
                )],
            )
        except Exception:
            pass

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


class ProductManagerWorker(Worker[list[Message]]):
    """Custom worker that injects task_id into agent context for progress updates."""

    async def run_task(self, params: TaskSendParams) -> None:
        task = await self.storage.load_task(params["id"])
        await self.storage.update_task(task["id"], state="working")

        # Load context and add history
        context = await self.storage.load_context(task["context_id"]) or []
        context.extend(task.get("history", []))

        # Run the agent with task_id injected into deps
        run_result = await agent.run(
            user_prompt=params["message"]["parts"][0]["text"],
            message_history=context,
            deps={"task_id": task["id"]}
        )

        # Create final message and complete task
        final_message = Message(
            role="agent",
            kind="message",
            message_id=str(uuid.uuid4()),
            parts=[TextPart(kind="text", text=run_result.data)]
        )

        # Update context and complete task
        context.append(final_message)
        await self.storage.update_context(task["context_id"], context)
        await self.storage.update_task(
            task["id"],
            state="completed",
            new_messages=[final_message],
        )

    async def cancel_task(self, params: TaskIdParams) -> None:
        await self.storage.update_task(params["id"], state="canceled")

    def build_message_history(self, history: list[Message]) -> list[Any]:
        return []

    def build_artifacts(self, result: Any) -> list[Artifact]:
        return []


@asynccontextmanager
async def lifespan(app: FastA2A):
    async with app.task_manager, ProductManagerWorker(storage=storage, broker=broker).run():
        yield


app = FastA2A(storage=storage, broker=broker, lifespan=lifespan)
