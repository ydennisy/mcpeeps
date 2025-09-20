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
    send_message_and_submit_task,
    poll_task_update,
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

# Track active tasks for task ID -> context mapping
active_tasks: dict[str, dict] = {}


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

    existing_task = conversation_tasks.get(context_id)
    cancel_requested_initial = bool(existing_task and existing_task.get("cancel_requested"))
    cancel_reason_initial = existing_task.get("cancel_reason") if existing_task else None

    task_state = {
        "status": "cancel_requested" if cancel_requested_initial else "running",
        "round": 0,
        "max_rounds": 3,
        "agents_contacted": len(agents),
        "responses": [],
        "total_messages": 0,
        "cancel_requested": cancel_requested_initial,
        "cancel_reason": cancel_reason_initial,
    }
    conversation_tasks[context_id] = task_state

    context = await storage.load_context(context_id) or []
    collected_replies: list[AgentReply] = []

    round_count = 0
    max_rounds = task_state["max_rounds"]

    def is_cancel_requested() -> bool:
        task = conversation_tasks.get(context_id)
        return bool(task and task.get("cancel_requested"))

    def mark_canceled(reason: str) -> None:
        task = conversation_tasks.get(context_id)
        if not task:
            return
        task["status"] = "canceled"
        task["cancel_requested"] = True
        task["cancel_reason"] = reason
        task["round"] = round_count

    if cancel_requested_initial:
        mark_canceled(cancel_reason_initial or "Canceled by user request")
        return

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
            # Check if this is a completed task that should replace a submitted message
            if reply.task_id and reply.status != 'submitted':
                print(f"[DEBUG] Looking to replace submitted message for task {reply.task_id} (status: {reply.status})")
                # Find and replace any submitted message with the same task_id
                replaced = False
                for i, existing_msg in enumerate(context):
                    # Handle both Message objects and dictionary format
                    if hasattr(existing_msg, 'metadata'):
                        existing_metadata = existing_msg.metadata or {}
                    elif isinstance(existing_msg, dict):
                        existing_metadata = existing_msg.get('metadata', {}) or {}
                    else:
                        continue

                    if (existing_metadata.get('task_id') == reply.task_id and
                        existing_metadata.get('status') == 'submitted'):
                        # Replace the submitted message with the completed one
                        print(f"[DEBUG] Replacing submitted message for task {reply.task_id} with completed message")
                        context[i] = reply.messages[0]  # Use the first (main) message
                        replaced = True
                        break

                if replaced:
                    await storage.update_context(context_id, context)
                    collected_replies.append(reply)
                    return

            # If no submitted message to replace, append normally
            context.extend(reply.messages)
            await storage.update_context(context_id, context)
            conversation_tasks[context_id]["total_messages"] += len(reply.messages)

        collected_replies.append(reply)

    try:
        async with httpx.AsyncClient() as client:
            # Initial agent contact - submit tasks immediately
            pending_tasks = []
            for agent in agents:
                if is_cancel_requested():
                    mark_canceled("Canceled by user request")
                    return

                try:
                    # First, submit the task and get immediate response
                    reply = await send_message_and_submit_task(
                        agent=agent,
                        message=user_message,
                        context_id=context_id,
                        http_client=client,
                    )
                    await record_reply(reply)

                    # If it's a task, track it for polling
                    if reply.task_id:
                        pending_tasks.append((agent, reply.task_id))
                        active_tasks[reply.task_id] = {
                            'context_id': context_id,
                            'agent': agent,
                            'status': 'submitted'
                        }

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

            # Now poll for task completions
            for agent, task_id in pending_tasks:
                try:
                    print(f"[DEBUG] Polling for completion of task {task_id}")
                    final_reply = await poll_task_update(
                        agent=agent,
                        task_id=task_id,
                        http_client=client,
                    )
                    print(f"[DEBUG] Task {task_id} completed with status {final_reply.status}")
                    await record_reply(final_reply)

                    # Update active task status
                    if task_id in active_tasks:
                        active_tasks[task_id]['status'] = final_reply.status

                except Exception as exc:
                    error_text = f"Error polling task {task_id}: {exc}"
                    error_message = build_agent_message(agent['name'], error_text, 'failed')
                    await record_reply(
                        AgentReply(
                            agent_name=agent['name'],
                            texts=[error_text],
                            messages=[error_message],
                            artifacts=[],
                            status='failed',
                            task_id=task_id,
                            original_sender=None,
                        )
                    )
                    if task_id in active_tasks:
                        active_tasks[task_id]['status'] = 'failed'

            # Multi-round conversation
            idx = 0

            while idx < len(collected_replies) and round_count < max_rounds:
                if is_cancel_requested():
                    mark_canceled("Canceled by user request")
                    return

                reply = collected_replies[idx]
                new_replies = await broadcast_agent_reply(
                    reply=reply,
                    agents=agents,
                    context_id=context_id,
                    http_client=client,
                )
                for new_reply in new_replies:
                    await record_reply(new_reply)
                    if is_cancel_requested():
                        mark_canceled("Canceled by user request")
                        return
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

    # Initialize task entry immediately so cancellation can be requested before processing starts
    conversation_tasks[resolved_context_id] = {
        "status": "pending",
        "round": 0,
        "max_rounds": 3,
        "agents_contacted": len(agents),
        "responses": [],
        "total_messages": len(context),
        "cancel_requested": False,
        "cancel_reason": None,
    }

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


@api.post("/cancel")
async def cancel_conversation(
    context_id: str = Form(..., description="Context ID to cancel")
):
    """Request cancellation of a running conversation."""

    context_id = context_id.strip()
    if not context_id:
        return {"status": "error", "message": "context_id is required"}

    task = conversation_tasks.get(context_id)
    if not task:
        return {"context_id": context_id, "status": "not_found", "message": "No conversation found for this context."}

    status = task.get("status")
    if status in {"completed", "failed", "canceled"}:
        return {
            "context_id": context_id,
            "status": status,
            "message": f"Conversation already {status}.",
            "round": task.get("round", 0),
            "max_rounds": task.get("max_rounds", 3),
            "cancel_requested": task.get("cancel_requested", False),
            "cancel_reason": task.get("cancel_reason"),
        }

    task["cancel_requested"] = True
    task["status"] = "cancel_requested"
    task.setdefault("cancel_reason", "Cancellation requested by user.")

    return {
        "context_id": context_id,
        "status": task["status"],
        "message": "Cancellation requested.",
        "round": task.get("round", 0),
        "max_rounds": task.get("max_rounds", 3),
        "cancel_requested": True,
        "cancel_reason": task.get("cancel_reason"),
    }


@api.get("/conversation-status")
async def get_conversation_status(context_id: str = Query(..., description="Context ID to check status for")):
    """Get the current status of a background conversation."""
    if context_id not in conversation_tasks:
        return {"context_id": context_id, "status": "not_found"}

    task_info = conversation_tasks[context_id].copy()
    task_info["context_id"] = context_id
    return task_info


@api.get("/task-status")
async def get_task_status(task_id: str = Query(..., description="Task ID to check status for")):
    """Get the current status of an active task."""
    if task_id not in active_tasks:
        return {"task_id": task_id, "status": "not_found"}

    task_info = active_tasks[task_id].copy()
    task_info["task_id"] = task_id
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
                task_id = metadata.get('task_id')

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
                task_id = metadata.get('task_id')

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
                "task_id": task_id,
            })

        return {"context_id": context_id, "messages": messages}
    except Exception as e:
        return {"error": str(e), "messages": []}


api.mount("/a2a", a2a_app)
