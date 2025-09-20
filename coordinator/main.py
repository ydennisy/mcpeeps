import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fasta2a import FastA2A, Worker
from fasta2a.broker import InMemoryBroker
from fasta2a.schema import Artifact, Message, TaskIdParams, TaskSendParams, TextPart
from fasta2a.storage import InMemoryStorage

Context = list[Message]

class InMemoryWorker(Worker[Context]):
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
        await self.storage.update_task(task['id'], state='completed',
                                       new_messages=[message], new_artifacts=artifacts)

    async def cancel_task(self, params: TaskIdParams) -> None: ...
    def build_message_history(self, history: list[Message]) -> list[Any]: ...
    def build_artifacts(self, result: Any) -> list[Artifact]: ...

storage = InMemoryStorage()
broker = InMemoryBroker()
worker = InMemoryWorker(storage=storage, broker=broker)

@asynccontextmanager
async def lifespan(a2a_app: FastA2A) -> AsyncIterator[None]:
    async with a2a_app.task_manager:
        async with worker.run():
            yield

a2a_app = FastA2A(storage=storage, broker=broker, lifespan=lifespan)

api = FastAPI(title="My API + A2A")

@api.get("/health")
def health():
    return {"ok": True}

api.mount("/a2a", a2a_app)
