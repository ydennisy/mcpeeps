"""Worker implementations for coordinating agent communication."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fasta2a import Worker
from fasta2a.schema import Artifact, Message, TaskIdParams, TaskSendParams, TaskState, TextPart

from .agent_comm import AgentReply, broadcast_agent_reply, build_agent_message, send_message_and_collect

Context = list[Message]

SummaryEntry = tuple[str, TaskState, str]


class NetworkWorker(Worker[Context]):
    """Worker that forwards tasks to remote agents over HTTP."""

    def __init__(self, storage, broker, agent_registry, *, http_client: httpx.AsyncClient | None = None):
        super().__init__(storage=storage, broker=broker)
        self.agent_registry = agent_registry
        self.http_client = http_client or httpx.AsyncClient()

    async def run_task(self, params: TaskSendParams) -> None:
        print(f"NetworkWorker processing task: {params}")
        task = await self.storage.load_task(params['id'])
        print(f"Task details: {task}")
        assert task is not None

        await self.storage.update_task(task['id'], state='working')

        context = await self.storage.load_context(task['context_id']) or []
        context.extend(task.get('history', []))

        outgoing_message: Message = params['message']

        agents = self.agent_registry.get_all_agents()
        agent_replies: list[AgentReply] = []

        for agent in agents:
            try:
                reply = await send_message_and_collect(
                    agent=agent,
                    message=outgoing_message,
                    context_id=task['context_id'],
                    http_client=self.http_client,
                )
            except Exception as exc:
                print(f"Failed to communicate with agent {agent['name']}: {exc}")
                fallback_text = f"Error contacting agent: {exc}"
                reply = AgentReply(
                    agent_name=agent['name'],
                    texts=[fallback_text],
                    messages=[build_agent_message(agent['name'], fallback_text)],
                    artifacts=[],
                    status='failed',
                )
            agent_replies.append(reply)

        all_replies: list[AgentReply] = []
        new_messages: list[Message] = []
        new_artifacts: list[Artifact] = []
        summary_entries: list[SummaryEntry] = []

        def capture_reply(reply: AgentReply) -> None:
            if reply.texts:
                summary_entries.extend(
                    (reply.agent_name, reply.status, text) for text in reply.texts
                )
            else:
                summary_entries.append((reply.agent_name, reply.status, '(no visible text)'))
            new_messages.extend(reply.messages)
            new_artifacts.extend(reply.artifacts)
            all_replies.append(reply)

        for reply in agent_replies:
            capture_reply(reply)

        idx = 0
        while idx < len(all_replies):
            reply = all_replies[idx]
            new_replies = await broadcast_agent_reply(
                reply=reply,
                agents=agents,
                context_id=task['context_id'],
                http_client=self.http_client,
            )
            for new_reply in new_replies:
                capture_reply(new_reply)
            idx += 1

        if not new_messages:
            placeholder = 'No agent responses were received.'
            fallback_message = build_agent_message('coordinator', placeholder)
            new_message_reply = AgentReply(
                agent_name='coordinator',
                texts=[placeholder],
                messages=[fallback_message],
                artifacts=[],
                status='completed',
            )
            capture_reply(new_message_reply)

        context.extend(new_messages)

        summary_display = '; '.join(
            f"{name} [{status}]: {text}" for name, status, text in summary_entries
        )
        print(f"Agent replies: {summary_display}")

        await self.storage.update_context(task['context_id'], context)
        await self.storage.update_task(
            task['id'],
            state='completed',
            new_messages=new_messages,
            new_artifacts=new_artifacts,
        )

    async def cancel_task(self, params: TaskIdParams) -> None:
        pass

    def build_message_history(self, history: list[Message]) -> list[Any]:
        return []

    def build_artifacts(self, result: Any) -> list[Artifact]:
        return []


class InMemoryWorker(Worker[Context]):
    """Simple example worker that replies locally."""

    async def run_task(self, params: TaskSendParams) -> None:
        print(params)
        task = await self.storage.load_task(params['id'])
        print(task)
        assert task is not None

        await self.storage.update_task(task['id'], state='working')

        context = await self.storage.load_context(task['context_id']) or []
        context.extend(task.get('history', []))

        message = Message(
            role='agent',
            parts=[TextPart(text=f'Your context is {len(context) + 1} messages long.', kind='text')],
            kind='message',
            message_id=str(uuid.uuid4()),
        )

        context.append(message)

        artifacts = self.build_artifacts(123)
        await self.storage.update_context(task['context_id'], context)
        await self.storage.update_task(
            task['id'], state='completed', new_messages=[message], new_artifacts=artifacts
        )

    async def cancel_task(self, params: TaskIdParams) -> None: ...

    def build_message_history(self, history: list[Message]) -> list[Any]: ...

    def build_artifacts(self, result: Any) -> list[Artifact]: ...
