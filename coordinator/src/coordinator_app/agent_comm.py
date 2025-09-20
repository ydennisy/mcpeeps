"""Utilities for sending messages to agents and normalizing their responses."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, cast

import httpx
from fasta2a.schema import Artifact, Message, TaskState, TextPart


ALL_TASK_STATES: set[TaskState] = cast(
    set[TaskState],
    {
        'submitted',
        'working',
        'input-required',
        'completed',
        'canceled',
        'failed',
        'rejected',
        'auth-required',
        'unknown',
    },
)

TERMINAL_TASK_STATES: set[TaskState] = cast(
    set[TaskState],
    {
        'completed',
        'failed',
        'canceled',
        'rejected',
        'input-required',
        'auth-required',
    },
)

FAILURE_REPLY_STATES: set[TaskState] = cast(
    set[TaskState],
    {
        'failed',
        'canceled',
        'rejected',
    },
)


logger = logging.getLogger(__name__)


@dataclass
class AgentReply:
    """Normalized response returned from an agent."""

    agent_name: str
    texts: list[str]
    messages: list[Message]
    artifacts: list[Artifact]
    status: TaskState
    task_id: str | None = None
    original_sender: str | None = None


def normalize_task_state(state: Any) -> TaskState:
    """Convert external task states into the canonical TaskState literal."""

    if isinstance(state, str):
        if state in ALL_TASK_STATES:
            return cast(TaskState, state)
        logger.warning("Received unexpected task state '%s'; defaulting to 'unknown'.", state)
    elif state is not None:
        logger.debug("Received non-string task state %r; defaulting to 'unknown'.", state)
    return cast(TaskState, 'unknown')


def parts_to_text(parts: list[dict[str, Any]]) -> str:
    """Combine visible text parts, skipping internal thinking content."""

    visible_chunks: list[str] = []
    for part in parts:
        if part.get('kind') != 'text':
            continue
        metadata = part.get('metadata') or {}
        if metadata.get('type') == 'thinking':
            continue
        text = part.get('text', '').strip()
        if text:
            visible_chunks.append(text)
    return '\n'.join(visible_chunks).strip()


def extract_agent_texts(task: dict[str, Any]) -> list[str]:
    """Pull visible agent text from a task payload."""

    texts: list[str] = []
    for message in task.get('history', []) or []:
        if message.get('role') != 'agent':
            continue
        text = parts_to_text(message.get('parts', []))
        if text:
            texts.append(text)
    return texts


def extract_status_text(task: dict[str, Any]) -> str | None:
    """Return any text embedded in the task status message."""

    status = task.get('status') or {}
    status_message = status.get('message')
    if not isinstance(status_message, dict):
        return None
    return parts_to_text(status_message.get('parts', [])) or None


def build_agent_message(agent_name: str, text: str, status: str = "completed") -> Message:
    """Create an A2A message for storage in shared context."""

    display = f"{agent_name}: {text}" if text else f"{agent_name}: (no visible content)"
    timestamp = datetime.now(timezone.utc).isoformat()

    return Message(
        role='agent',
        parts=[TextPart(text=display, kind='text')],
        kind='message',
        message_id=str(uuid.uuid4()),
        metadata={
            'agent_name': agent_name,
            'raw_text': text,
            'status': status,
            'timestamp': timestamp,
        }
    )


def convert_part_to_payload(part: dict[str, Any]) -> dict[str, Any]:
    """Translate stored A2A parts into JSON payloads for outbound messages."""

    kind = part.get('kind')
    if kind == 'text':
        payload: dict[str, Any] = {'kind': 'text', 'text': part.get('text', '')}
        if part.get('metadata'):
            payload['metadata'] = part['metadata']
        return payload
    raise NotImplementedError(f'Unsupported message part kind: {kind}')


def build_message_payload(message: Message, context_id: str) -> dict[str, Any]:
    """Prepare the JSON payload to send a message to an agent."""

    parts_payload = [convert_part_to_payload(part) for part in message.get('parts', [])]
    payload: dict[str, Any] = {
        'role': message.get('role', 'user'),
        'parts': parts_payload,
        'kind': message.get('kind', 'message'),
        'messageId': message.get('message_id', str(uuid.uuid4())),
        'contextId': context_id,
    }
    if message.get('metadata'):
        payload['metadata'] = message['metadata']
    return payload


async def broadcast_agent_reply(
    *,
    reply: AgentReply,
    agents: list[dict[str, str]],
    context_id: str,
    http_client: httpx.AsyncClient,
    timeout: float = 30.0,
) -> list[AgentReply]:
    """Relay an agent's reply to peers and collect their responses synchronously."""

    if reply.status in FAILURE_REPLY_STATES:
        return []

    # Exclude both the current agent and the original sender from recipients
    excluded_agents = {reply.agent_name}
    if reply.original_sender:
        excluded_agents.add(reply.original_sender)

    recipients = [agent for agent in agents if agent.get('name') and agent['name'] not in excluded_agents]
    if not recipients:
        return []

    texts_to_forward: list[str] = list(reply.texts)
    if not texts_to_forward and reply.messages:
        for message in reply.messages:
            for part in message.parts:
                text = getattr(part, 'text', '').strip()
                if text:
                    texts_to_forward.append(text)
    if not texts_to_forward:
        return []

    collected: list[AgentReply] = []

    for recipient in recipients:
        for text in texts_to_forward:
            if text.startswith(f"{reply.agent_name}:"):
                outgoing_text = text
            else:
                outgoing_text = f"{reply.agent_name}: {text}"

            outgoing_message = Message(
                role='user',
                parts=[TextPart(text=outgoing_text, kind='text')],
                kind='message',
                message_id=str(uuid.uuid4()),
            )

            try:
                forward_reply = await send_message_and_collect(
                    agent=recipient,
                    message=outgoing_message,
                    context_id=context_id,
                    http_client=http_client,
                    poll_timeout=timeout,
                )
                # Track the original sender to prevent circular messaging
                forward_reply.original_sender = reply.original_sender or reply.agent_name
            except Exception as exc:  # pragma: no cover - log and continue
                logger.warning(
                    "Failed to relay message from %s to %s: %s",
                    reply.agent_name,
                    recipient.get('name', '<unknown>'),
                    exc,
                )
                error_text = f"Error contacting agent: {exc}"
                collected.append(
                    AgentReply(
                        agent_name=recipient.get('name', 'unknown'),
                        texts=[error_text],
                        messages=[build_agent_message(recipient.get('name', 'unknown'), error_text, 'failed')],
                        artifacts=[],
                        status='failed',
                        original_sender=reply.original_sender or reply.agent_name,
                    )
                )
                continue

            collected.append(forward_reply)

    return collected


async def wait_for_task_completion(
    *,
    agent_url: str,
    task_id: str,
    http_client: httpx.AsyncClient,
    poll_timeout: float = 30.0,
    poll_interval: float = 0.5,
) -> dict[str, Any]:
    """Poll an agent until a submitted task finishes."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + poll_timeout

    while True:
        task_request = {
            'jsonrpc': '2.0',
            'id': str(uuid.uuid4()),
            'method': 'tasks/get',
            'params': {'id': task_id},
        }
        response = await http_client.post(f"{agent_url}/", json=task_request, timeout=poll_timeout)
        response.raise_for_status()
        payload = response.json()
        if 'error' in payload:
            raise RuntimeError(f"Agent returned error while fetching task: {payload['error']}")

        latest_task = payload.get('result')
        if not isinstance(latest_task, dict):
            raise RuntimeError('Agent returned an unexpected task payload.')

        state = normalize_task_state((latest_task.get('status') or {}).get('state'))
        if state in TERMINAL_TASK_STATES:
            return latest_task

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f'Timed out waiting for task {task_id} to complete (last state: {state}).')
        await asyncio.sleep(min(poll_interval, max(remaining, 0)))


async def send_message_and_collect(
    *,
    agent: dict[str, str],
    message: Message,
    context_id: str,
    http_client: httpx.AsyncClient,
    poll_timeout: float = 30.0,
    poll_interval: float = 0.5,
) -> AgentReply:
    """Send a message to an agent and gather its response in a normalized format."""

    message_payload = build_message_payload(message, context_id)
    request_payload = {
        'jsonrpc': '2.0',
        'id': str(uuid.uuid4()),
        'method': 'message/send',
        'params': {
            'message': message_payload,
            'configuration': {
                'blocking': True,
                'acceptedOutputModes': ['text'],
            },
        },
    }

    response = await http_client.post(f"{agent['url']}/", json=request_payload, timeout=poll_timeout)
    response.raise_for_status()
    payload = response.json()

    if 'error' in payload:
        error = payload['error']
        raise RuntimeError(f"Agent error {error.get('code')}: {error.get('message')}")

    result = payload.get('result')
    if not isinstance(result, dict):
        raise RuntimeError('Agent response missing result payload.')

    if result.get('kind') == 'message':
        text = parts_to_text(result.get('parts', [])) or '(no visible text)'
        message_obj = build_agent_message(agent['name'], text, 'completed')
        return AgentReply(
            agent_name=agent['name'],
            texts=[text],
            messages=[message_obj],
            artifacts=[],
            status='completed',
        )

    if result.get('kind') == 'task':
        task_id = result.get('id')
        if not isinstance(task_id, str):
            raise RuntimeError('Agent task response missing id field.')

        final_task = await wait_for_task_completion(
            agent_url=agent['url'],
            task_id=task_id,
            http_client=http_client,
            poll_timeout=poll_timeout,
            poll_interval=poll_interval,
        )

        state = normalize_task_state((final_task.get('status') or {}).get('state'))
        agent_texts = extract_agent_texts(final_task)
        if not agent_texts:
            status_text = extract_status_text(final_task)
            if status_text:
                agent_texts = [status_text]
        if not agent_texts:
            agent_texts = [f'(no visible text; final state: {state})']

        messages = [build_agent_message(agent['name'], text) for text in agent_texts]
        artifacts = final_task.get('artifacts', []) or []

        return AgentReply(
            agent_name=agent['name'],
            texts=agent_texts,
            messages=messages,
            artifacts=artifacts,
            status=state,
            task_id=task_id,
        )

    raise RuntimeError(f"Unsupported agent result kind: {result.get('kind')}")
