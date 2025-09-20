"""Utilities for sending messages to agents and normalizing their responses."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, cast

import httpx
from fasta2a.schema import Artifact, CancelTaskRequest, GetTaskRequest, Message, Task, TaskState, TextPart

try:  # pragma: no cover - compatibility for older schema versions
    from fasta2a.schema import cancel_task_request_ta, get_task_request_ta, get_task_response_ta
except ImportError:  # pragma: no cover - fallback when type adapters are unavailable
    from fasta2a.schema import CancelTaskRequest as CancelTaskRequestType, GetTaskResponse, TypeAdapter

    get_task_request_ta = TypeAdapter(GetTaskRequest)
    get_task_response_ta = TypeAdapter(GetTaskResponse)
    cancel_task_request_ta = TypeAdapter(CancelTaskRequestType)


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


def build_agent_message(agent_name: str, text: str, status: str = "completed", task_id: str | None = None) -> Message:
    """Create an A2A message for storage in shared context."""

    display = f"{agent_name}: {text}" if text else f"{agent_name}: (no visible content)"
    timestamp = datetime.now(timezone.utc).isoformat()

    metadata = {
        'agent_name': agent_name,
        'raw_text': text,
        'status': status,
        'timestamp': timestamp,
    }

    if task_id:
        metadata['task_id'] = task_id

    return Message(
        role='agent',
        parts=[TextPart(text=display, kind='text')],
        kind='message',
        message_id=str(uuid.uuid4()),
        metadata=metadata
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
    timeout: float = 300.0,
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
    poll_timeout: float = 300.0,
    poll_interval: float = 0.5,
) -> Task:
    """Poll an agent until a submitted task finishes."""

    loop = asyncio.get_running_loop()
    deadline = loop.time() + poll_timeout

    while True:
        task_request: GetTaskRequest = {
            'jsonrpc': '2.0',
            'id': str(uuid.uuid4()),
            'method': 'tasks/get',
            'params': {'id': task_id},
        }
        serialized_request = get_task_request_ta.dump_python(task_request, by_alias=True)
        response = await http_client.post(
            f"{agent_url}/", json=serialized_request, timeout=min(poll_timeout, 30.0)
        )
        response.raise_for_status()
        payload = get_task_response_ta.validate_python(response.json())

        error = payload.get('error')
        if error:
            raise RuntimeError(f"Agent returned error while fetching task: {error}")

        result = payload.get('result')
        if result is None:
            raise RuntimeError('Agent response missing task payload.')
        latest_task = cast(Task, result)

        state = normalize_task_state((latest_task.get('status') or {}).get('state'))
        if state in TERMINAL_TASK_STATES:
            return latest_task

        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(f'Timed out waiting for task {task_id} to complete (last state: {state}).')
        await asyncio.sleep(min(poll_interval, max(remaining, 0)))


async def cancel_agent_task(
    *,
    agent: dict[str, str],
    task_id: str,
    http_client: httpx.AsyncClient,
    reason: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Issue a cancel request for a task to the given agent."""

    request: CancelTaskRequest = {
        'jsonrpc': '2.0',
        'id': str(uuid.uuid4()),
        'method': 'tasks/cancel',
        'params': {'id': task_id},
    }

    if reason:
        request['params']['metadata'] = {'reason': reason}

    serialized_request = cancel_task_request_ta.dump_python(request, by_alias=True)
    response = await http_client.post(
        f"{agent['url']}/",
        json=serialized_request,
        timeout=min(timeout, 30.0),
    )
    response.raise_for_status()
    payload = response.json()

    if 'error' in payload:
        error = payload['error']
        raise RuntimeError(
            f"Agent returned error while canceling task {task_id}: {error.get('message', error)}"
        )

    result = payload.get('result')
    if isinstance(result, dict):
        return cast(dict[str, Any], result)
    return {}


async def send_message_and_submit_task(
    *,
    agent: dict[str, str],
    message: Message,
    context_id: str,
    http_client: httpx.AsyncClient,
    poll_timeout: float = 300.0,
) -> AgentReply:
    """Send a message to an agent and return immediately with task submission info."""

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

    response = await http_client.post(f"{agent['url']}/", json=request_payload, timeout=min(poll_timeout, 30.0))
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

        # Return immediately with submitted status - don't wait for completion
        pending_message = build_agent_message(agent['name'], f"Task {task_id[:8]}... submitted", 'submitted', task_id)
        return AgentReply(
            agent_name=agent['name'],
            texts=[f"Task {task_id[:8]}... submitted"],
            messages=[pending_message],
            artifacts=[],
            status='submitted',
            task_id=task_id,
        )

    raise RuntimeError(f"Unsupported agent result kind: {result.get('kind')}")


async def poll_task_update(
    *,
    agent: dict[str, str],
    task_id: str,
    http_client: httpx.AsyncClient,
    poll_timeout: float = 300.0,
    poll_interval: float = 0.5,
) -> AgentReply:
    """Poll for task completion and return the final result."""

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

    messages = [build_agent_message(agent['name'], text, state, task_id) for text in agent_texts]
    artifacts = final_task.get('artifacts', []) or []

    return AgentReply(
        agent_name=agent['name'],
        texts=agent_texts,
        messages=messages,
        artifacts=artifacts,
        status=state,
        task_id=task_id,
    )


async def send_message_and_collect(
    *,
    agent: dict[str, str],
    message: Message,
    context_id: str,
    http_client: httpx.AsyncClient,
    poll_timeout: float = 300.0,
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

        messages = [build_agent_message(agent['name'], text, state, task_id) for text in agent_texts]
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


async def poll_task_update(
    *,
    agent: dict[str, str],
    task_id: str,
    http_client: httpx.AsyncClient,
    poll_timeout: float = 300.0,
    poll_interval: float = 0.5,
) -> AgentReply:
    """Poll for task completion and return the final result."""

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

    messages = [build_agent_message(agent['name'], text, state, task_id) for text in agent_texts]
    artifacts = final_task.get('artifacts', []) or []

    return AgentReply(
        agent_name=agent['name'],
        texts=agent_texts,
        messages=messages,
        artifacts=artifacts,
        status=state,
        task_id=task_id,
    )
