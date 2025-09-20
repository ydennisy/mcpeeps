from __future__ import annotations

import asyncio
import logging
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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are a product manager.
You are in a chat room with other humans & agents:
- @ceo
- @swe
- @tester
You can address them by using @, e.g @swe
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
    logger.info(f"search_web called with query '{cleaned_query}', task_id: {task_id}")

    # Emit progress update about starting search
    if task_id:
        try:
            logger.info(f"Emitting start search progress for task {task_id}")
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
            logger.info(f"Successfully emitted start search progress for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to emit start search progress for task {task_id}: {e}")
            pass  # Don't fail the search if progress update fails

    def _perform_search() -> list[dict[str, Any]]:
        with DDGS() as ddgs:
            return list(ddgs.text(cleaned_query, max_results=limit))

    try:
        logger.info(f"Performing search for '{cleaned_query}'")
        results = await asyncio.to_thread(_perform_search)
        logger.info(f"Search completed, found {len(results) if results else 0} results")
    except Exception as exc:  # pragma: no cover - network/runtime guard
        logger.error(f"Search failed for '{cleaned_query}': {exc}")
        # Emit error progress update
        if task_id:
            try:
                logger.info(f"Emitting search error progress for task {task_id}")
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
            except Exception as e:
                logger.error(f"Failed to emit search error progress for task {task_id}: {e}")
                pass
        return f"Web search failed: {exc}"

    if not results:
        logger.info(f"No results found for '{cleaned_query}'")
        # Emit no results progress update
        if task_id:
            try:
                logger.info(f"Emitting no results progress for task {task_id}")
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
            except Exception as e:
                logger.error(f"Failed to emit no results progress for task {task_id}: {e}")
                pass
        return "No search results were found for that query."

    # Emit success progress update
    if task_id:
        try:
            logger.info(f"Emitting success progress for task {task_id}")
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
            logger.info(f"Successfully emitted success progress for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to emit success progress for task {task_id}: {e}")
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
        task_id = params["id"]
        logger.info(f"ProductManagerWorker starting task: {task_id}")

        try:
            task = await self.storage.load_task(task_id)
            logger.info(f"Loaded task {task_id}: {task}")

            await self.storage.update_task(task_id, state="working")
            logger.info(f"Updated task {task_id} to working state")

            # Load context and add history
            context = await self.storage.load_context(task["context_id"]) or []
            context.extend(task.get("history", []))
            logger.info(f"Context for task {task_id} has {len(context)} messages")

            # Extract user prompt from message parts
            user_prompt = params["message"]["parts"][0]["text"]
            logger.info(f"Running agent for task {task_id} with prompt: {user_prompt}")

            # Run the agent with task_id injected into deps
            run_result = await agent.run(
                user_prompt=user_prompt,
                message_history=context,
                deps={"task_id": task_id}
            )
            # Get the result data - in PydanticAI AgentRunResult has 'output' attribute
            result_text = str(run_result.output)
            logger.info(f"Agent completed for task {task_id}, result: {result_text}")

            # Create final message and complete task
            final_message = Message(
                role="agent",
                kind="message",
                message_id=str(uuid.uuid4()),
                parts=[TextPart(kind="text", text=result_text)]
            )

            # Update context and complete task
            context.append(final_message)
            await self.storage.update_context(task["context_id"], context)
            await self.storage.update_task(
                task_id,
                state="completed",
                new_messages=[final_message],
            )
            logger.info(f"Task {task_id} completed successfully")

        except Exception as exc:
            logger.error(f"Task {task_id} failed with exception: {exc}", exc_info=True)
            try:
                await self.storage.update_task(task_id, state="failed")
                logger.info(f"Updated task {task_id} to failed state")
            except Exception as update_exc:
                logger.error(f"Failed to update task {task_id} to failed state: {update_exc}")
            raise

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
