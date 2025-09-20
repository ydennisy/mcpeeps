"""Application wiring for the coordinator service."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Form, Query
from fastapi.responses import HTMLResponse
from fasta2a import FastA2A
from fasta2a.broker import InMemoryBroker
from fasta2a.schema import Message, TextPart
from fasta2a.storage import InMemoryStorage

from .agent_comm import build_agent_message, send_message_and_collect
from .registry import AgentRegistry
from .ui import render_ui
from .workers import NetworkWorker


storage = InMemoryStorage()
broker = InMemoryBroker()
agent_registry = AgentRegistry()
worker = NetworkWorker(storage=storage, broker=broker, agent_registry=agent_registry)

# Track all context IDs
context_tracker: set[str] = set()


@asynccontextmanager
async def lifespan(a2a_app: FastA2A) -> AsyncIterator[None]:
    async with a2a_app.task_manager:
        async with worker.run():
            yield


a2a_app = FastA2A(storage=storage, broker=broker, lifespan=lifespan)

api = FastAPI(title="MCPeeps")


@api.get("/health")
def health():
    return {"ok": True}


@api.get("/", response_class=HTMLResponse)
async def get_ui():
    return render_ui()


@api.post("/trigger")
async def trigger_agents(message: str = Form(), context_id: str | None = Form(default=None)):
    message = message.strip()
    resolved_context_id = (context_id or "").strip() or f"trigger-{uuid.uuid4()}"
    agents = agent_registry.get_all_agents()
    agent_responses = []

    user_message = Message(
        role='user',
        parts=[TextPart(text=message, kind='text')],
        kind='message',
        message_id=str(uuid.uuid4()),
    )

    context = await storage.load_context(resolved_context_id) or []
    context.append(user_message)

    await storage.update_context(resolved_context_id, context)
    context_tracker.add(resolved_context_id)

    async with httpx.AsyncClient() as client:
        for agent in agents:
            try:
                reply = await send_message_and_collect(
                    agent=agent,
                    message=user_message,
                    context_id=resolved_context_id,
                    http_client=client,
                )
            except Exception as exc:
                error_text = f"Error contacting agent: {exc}"
                agent_responses.append(f"{agent['name']}: {error_text}")
                error_message = build_agent_message(agent['name'], error_text)
                context.append(error_message)
                await storage.update_context(resolved_context_id, context)
                continue

            if reply.texts:
                agent_responses.extend(f"{reply.agent_name}: {text}" for text in reply.texts)
            else:
                agent_responses.append(f"{reply.agent_name}: (no visible text)")

            if reply.messages:
                context.extend(reply.messages)
                await storage.update_context(resolved_context_id, context)

    return {
        "status": "triggered",
        "context_id": resolved_context_id,
        "agents": len(agents),
        "responses": agent_responses,
    }


@api.get("/messages")
async def get_all_messages(context_id: str = Query(..., description="Context ID to load messages for")):
    try:
        context = await storage.load_context(context_id)
        if not context:
            return {"context_id": context_id, "messages": []}

        messages = []
        for message in context:
            if hasattr(message, 'message_id'):
                messages.append({
                    "context_id": context_id,
                    "message_id": message.message_id,
                    "role": message.role,
                    "text": message.parts[0].text if message.parts else "",
                    "kind": message.kind,
                })
            elif isinstance(message, dict):
                messages.append({
                    "context_id": context_id,
                    "message_id": message.get('message_id', 'unknown'),
                    "role": message.get('role', 'unknown'),
                    "text": str(message),
                    "kind": message.get('kind', 'unknown'),
                })
            else:
                messages.append({
                    "context_id": context_id,
                    "message_id": "unknown",
                    "role": "unknown",
                    "text": str(message),
                    "kind": "unknown",
                })

        return {"context_id": context_id, "messages": messages}
    except Exception as e:
        return {"error": str(e), "messages": []}


api.mount("/a2a", a2a_app)
