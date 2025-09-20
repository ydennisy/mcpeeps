"""Application wiring for the coordinator service."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Form, Query, BackgroundTasks
from fastapi.responses import HTMLResponse
from fasta2a import FastA2A
from fasta2a.broker import InMemoryBroker
from fasta2a.schema import Message, TextPart
from fasta2a.storage import InMemoryStorage

from .agent_comm import (
    AgentReply,
    broadcast_agent_reply,
    build_agent_message,
    send_message_and_collect,
)
from .registry import AgentRegistry
from .ui import render_ui
from .workers import NetworkWorker


storage = InMemoryStorage()
broker = InMemoryBroker()
agent_registry = AgentRegistry()
worker = NetworkWorker(storage=storage, broker=broker, agent_registry=agent_registry)

# Track all context IDs
context_tracker: set[str] = set()

# Track background conversation tasks
conversation_tasks: dict[str, dict] = {}


@asynccontextmanager
async def lifespan(a2a_app: FastA2A) -> AsyncIterator[None]:
    async with a2a_app.task_manager:
        async with worker.run():
            yield


a2a_app = FastA2A(storage=storage, broker=broker, lifespan=lifespan)

api = FastAPI(title="MCPeeps")


async def process_conversation_background(
    context_id: str,
    user_message: Message,
    agents: list[dict[str, str]],
) -> None:
    """Process agent conversation in the background with real-time updates."""

    # Initialize task status
    conversation_tasks[context_id] = {
        "status": "running",
        "round": 0,
        "max_rounds": 3,
        "agents_contacted": len(agents),
        "responses": [],
        "total_messages": 0,
    }

    context = await storage.load_context(context_id) or []
    collected_replies: list[AgentReply] = []

    async def record_reply(reply: AgentReply) -> None:
        # Update task status
        if reply.texts:
            conversation_tasks[context_id]["responses"].extend(
                f"{reply.agent_name}: {text}" for text in reply.texts
            )
        else:
            conversation_tasks[context_id]["responses"].append(
                f"{reply.agent_name}: (no visible text)"
            )

        if reply.messages:
            context.extend(reply.messages)
            await storage.update_context(context_id, context)
            conversation_tasks[context_id]["total_messages"] += len(reply.messages)

        collected_replies.append(reply)

    try:
        async with httpx.AsyncClient() as client:
            # Initial agent contact
            for agent in agents:
                try:
                    reply = await send_message_and_collect(
                        agent=agent,
                        message=user_message,
                        context_id=context_id,
                        http_client=client,
                    )
                except Exception as exc:
                    error_text = f"Error contacting agent: {exc}"
                    error_message = build_agent_message(agent['name'], error_text, 'failed')
                    await record_reply(
                        AgentReply(
                            agent_name=agent['name'],
                            texts=[error_text],
                            messages=[error_message],
                            artifacts=[],
                            status='failed',
                            original_sender=None,
                        )
                    )
                    continue

                await record_reply(reply)

            # Multi-round conversation
            idx = 0
            round_count = 0
            max_rounds = 3

            while idx < len(collected_replies) and round_count < max_rounds:
                reply = collected_replies[idx]
                new_replies = await broadcast_agent_reply(
                    reply=reply,
                    agents=agents,
                    context_id=context_id,
                    http_client=client,
                )
                for new_reply in new_replies:
                    await record_reply(new_reply)
                idx += 1

                # Increment round count when we've processed all current replies
                if idx >= len(collected_replies) and new_replies:
                    round_count += 1
                    conversation_tasks[context_id]["round"] = round_count

        # Mark as completed
        conversation_tasks[context_id]["status"] = "completed"
        conversation_tasks[context_id]["round"] = round_count

    except Exception as exc:
        conversation_tasks[context_id]["status"] = "failed"
        conversation_tasks[context_id]["error"] = str(exc)


@api.get("/health")
def health():
    return {"ok": True}


@api.get("/", response_class=HTMLResponse)
async def get_ui():
    return render_ui()


@api.post("/trigger")
async def trigger_agents(
    background_tasks: BackgroundTasks,
    message: str = Form(),
    context_id: str | None = Form(default=None)
):
    """Start agent conversation processing in the background."""
    message = message.strip()
    resolved_context_id = (context_id or "").strip() or f"trigger-{uuid.uuid4()}"
    agents = agent_registry.get_all_agents()

    user_message = Message(
        role='user',
        parts=[TextPart(text=message, kind='text')],
        kind='message',
        message_id=str(uuid.uuid4()),
        metadata={
            'agent_name': 'user',
            'raw_text': message,
            'status': 'completed',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    )

    # Save user message immediately
    context = await storage.load_context(resolved_context_id) or []
    context.append(user_message)
    await storage.update_context(resolved_context_id, context)
    context_tracker.add(resolved_context_id)

    # Start background processing
    background_tasks.add_task(
        process_conversation_background,
        resolved_context_id,
        user_message,
        agents
    )

    return {
        "status": "started",
        "context_id": resolved_context_id,
        "agents": len(agents),
        "message": "Conversation processing started in background"
    }


@api.get("/conversation-status")
async def get_conversation_status(context_id: str = Query(..., description="Context ID to check status for")):
    """Get the current status of a background conversation."""
    if context_id not in conversation_tasks:
        return {"context_id": context_id, "status": "not_found"}

    task_info = conversation_tasks[context_id].copy()
    task_info["context_id"] = context_id
    return task_info


@api.get("/agents")
async def get_agents():
    """Get agent registry information including emojis."""
    agents = agent_registry.get_all_agents()
    return {"agents": agents}


@api.get("/messages")
async def get_all_messages(context_id: str = Query(..., description="Context ID to load messages for")):
    try:
        context = await storage.load_context(context_id)
        if not context:
            return {"context_id": context_id, "messages": []}

        messages = []
        for message in context:
            # Extract basic message info
            message_id = "unknown"
            role = "unknown"
            text = ""
            kind = "unknown"
            agent_name = "unknown"
            status = "unknown"
            timestamp = None

            if hasattr(message, 'message_id'):
                # New message format with proper attributes
                message_id = message.message_id
                role = message.role
                kind = message.kind

                # Extract text from parts
                if message.parts:
                    text = message.parts[0].text if message.parts[0].text else ""

                # Extract metadata if available
                metadata = getattr(message, 'metadata', {}) or {}
                agent_name = metadata.get('agent_name', role)
                status = metadata.get('status', 'completed')
                timestamp = metadata.get('timestamp')

                # Clean up text for agent messages (remove "agent-name: " prefix)
                raw_text = metadata.get('raw_text', text)
                if raw_text and agent_name != 'user':
                    # Use the raw text instead of the prefixed display text
                    text = raw_text
                elif agent_name != 'user' and text.startswith(f"{agent_name}: "):
                    # Fallback: strip the prefix if it exists
                    text = text[len(f"{agent_name}: "):]

            elif isinstance(message, dict):
                # Dictionary format - extract what we can
                message_id = message.get('message_id', 'unknown')
                role = message.get('role', 'unknown')
                kind = message.get('kind', 'unknown')

                # Try to extract text properly
                if 'parts' in message and message['parts']:
                    text = message['parts'][0].get('text', '') if isinstance(message['parts'][0], dict) else str(message['parts'][0])
                else:
                    text = message.get('text', '')

                # Extract metadata
                metadata = message.get('metadata', {}) or {}
                agent_name = metadata.get('agent_name', role)
                status = metadata.get('status', 'completed')
                timestamp = metadata.get('timestamp')

                # Clean up text
                raw_text = metadata.get('raw_text', text)
                if raw_text:
                    text = raw_text

            else:
                # Fallback for unknown message formats
                text = str(message)
                agent_name = "unknown"
                status = "unknown"

            messages.append({
                "context_id": context_id,
                "message_id": message_id,
                "role": role,
                "text": text,
                "kind": kind,
                "agent_name": agent_name,
                "status": status,
                "timestamp": timestamp,
            })

        return {"context_id": context_id, "messages": messages}
    except Exception as e:
        return {"error": str(e), "messages": []}


api.mount("/a2a", a2a_app)
