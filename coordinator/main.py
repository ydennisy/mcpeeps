import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from fasta2a import FastA2A, Worker
from fasta2a.broker import InMemoryBroker
from fasta2a.schema import Artifact, Message, TaskIdParams, TaskSendParams, TextPart
from fasta2a.storage import InMemoryStorage

Context = list[Message]

class AgentRegistry:
    def __init__(self):
        self.agents = [
            {"name": "game-tester", "url": "http://localhost:8001"},
        ]

    def get_all_agents(self):
        return self.agents

    async def check_agent_health(self, agent_url: str) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{agent_url}/health", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

class NetworkWorker(Worker[Context]):
    def __init__(self, storage, broker, agent_registry: AgentRegistry):
        super().__init__(storage=storage, broker=broker)
        self.agent_registry = agent_registry
        self.http_client = httpx.AsyncClient()

    async def run_task(self, params: TaskSendParams) -> None:
        print(f"NetworkWorker processing task: {params}")
        task = await self.storage.load_task(params['id'])
        print(f"Task details: {task}")
        assert task is not None

        await self.storage.update_task(task['id'], state='working')

        context = await self.storage.load_context(task['context_id']) or []
        context.extend(task.get('history', []))

        agents = self.agent_registry.get_all_agents()
        agent_responses = []

        for agent in agents:
            try:
                agent_response = await self._send_to_agent(agent, task, context)
                agent_responses.append(agent_response)
            except Exception as e:
                print(f"Failed to communicate with agent {agent['name']}: {e}")
                agent_responses.append(f"Error from {agent['name']}: {str(e)}")

        response_text = f"Sent message to {len(agents)} agents. Responses: {'; '.join(agent_responses)}"

        message = Message(
            role='agent',
            parts=[TextPart(text=response_text, kind='text')],
            kind='message',
            message_id=str(uuid.uuid4()),
        )

        context.append(message)
        artifacts = self.build_artifacts(agent_responses)
        await self.storage.update_context(task['context_id'], context)
        await self.storage.update_task(task['id'], state='completed',
                                       new_messages=[message], new_artifacts=artifacts)

    async def _send_to_agent(self, agent: dict, task: dict, context: list[Message]) -> str:
        message_data = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Process this task from coordinator"}],
                    "contextId": task['context_id'],
                    "kind": "message",
                    "messageId": str(uuid.uuid4())
                },
                "configuration": {
                    "blocking": True,
                    "acceptedOutputModes": ["text"]
                }
            }
        }

        response = await self.http_client.post(
            f"{agent['url']}/",
            json=message_data,
            timeout=30.0
        )
        response.raise_for_status()
        result = response.json()
        return f"{agent['name']}: {result.get('result', {}).get('message', 'No response')}"

    async def cancel_task(self, params: TaskIdParams) -> None:
        pass

    def build_message_history(self, history: list[Message]) -> list[Any]:
        return []

    def build_artifacts(self, result: Any) -> list[Artifact]:
        return []

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
agent_registry = AgentRegistry()
worker = NetworkWorker(storage=storage, broker=broker, agent_registry=agent_registry)

# Track all context IDs
context_tracker = set()

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
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MCPeeps Coordinator</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .form-group { margin-bottom: 15px; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input[type="text"] { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            button { background-color: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background-color: #0056b3; }
            .result { margin-top: 20px; padding: 10px; background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; }
            .context-id { font-weight: bold; color: #28a745; }
            .messages { margin-top: 20px; }
            .message { margin-bottom: 10px; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
            .message.user { background-color: #e3f2fd; }
            .message.agent { background-color: #f3e5f5; }
            .message-header { font-weight: bold; margin-bottom: 5px; }
            .refresh-btn { margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>MCPeeps Coordinator</h2>

            <div class="form-group">
                <label for="message">Message:</label>
                <input type="text" id="message" />
            </div>

            <button onclick="triggerAgents()">Trigger Agents</button>

            <div id="result" class="result" style="display: none;"></div>

            <div class="messages">
                <h2>All Messages</h2>
                <button class="refresh-btn" onclick="loadMessages()">Refresh Messages</button>
                <div id="messages"></div>
            </div>
        </div>

        <script>
            async function triggerAgents() {
                const message = document.getElementById('message').value;
                const resultDiv = document.getElementById('result');

                try {
                    const response = await fetch('/trigger', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/x-www-form-urlencoded',
                        },
                        body: 'message=' + encodeURIComponent(message)
                    });

                    const data = await response.json();

                    resultDiv.innerHTML = `
                        <h3>Trigger Result</h3>
                        <p><span class="context-id">Context ID: ${data.context_id}</span></p>
                        <p>Status: ${data.status}</p>
                        <p>Agents contacted: ${data.agents}</p>
                        <div>
                            <strong>Responses:</strong>
                            <ul>
                                ${data.responses.map(resp => `<li>${resp}</li>`).join('')}
                            </ul>
                        </div>
                    `;
                    resultDiv.style.display = 'block';

                    // Automatically refresh messages after trigger
                    setTimeout(loadMessages, 1000);

                } catch (error) {
                    resultDiv.innerHTML = `<p style="color: red;">Error: ${error.message}</p>`;
                    resultDiv.style.display = 'block';
                }
            }

            async function loadMessages() {
                const messagesDiv = document.getElementById('messages');

                try {
                    const response = await fetch('/messages');
                    const data = await response.json();

                    if (data.error) {
                        messagesDiv.innerHTML = `<p style="color: red;">Error loading messages: ${data.error}</p>`;
                        return;
                    }

                    if (data.messages.length === 0) {
                        messagesDiv.innerHTML = '<p>No messages yet. Trigger some agents to see messages here.</p>';
                        return;
                    }

                    const messagesHtml = data.messages.map(msg => `
                        <div class="message ${msg.role}">
                            <div class="message-header">
                                ${msg.role.toUpperCase()} - Context: ${msg.context_id.substring(0, 8)}...
                            </div>
                            <div>${msg.text}</div>
                        </div>
                    `).join('');

                    messagesDiv.innerHTML = `
                        <h3>Messages (${data.messages.length})</h3>
                        ${messagesHtml}
                    `;

                } catch (error) {
                    messagesDiv.innerHTML = `<p style="color: red;">Error loading messages: ${error.message}</p>`;
                }
            }

            // Load messages on page load
            document.addEventListener('DOMContentLoaded', loadMessages);
        </script>
    </body>
    </html>
    """
    return html_content


@api.post("/trigger")
async def trigger_agents(message: str = Form()):
    message = message.strip()
    context_id = f"trigger-{uuid.uuid4()}"
    agents = agent_registry.get_all_agents()
    agent_responses = []

    # Store the initial user message
    user_message = Message(
        role='user',
        parts=[TextPart(text=message, kind='text')],
        kind='message',
        message_id=str(uuid.uuid4()),
    )

    await storage.update_context(context_id, [user_message])
    context_tracker.add(context_id)

    for agent in agents:
        try:
            message_data = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": message}],
                        "contextId": context_id,
                        "kind": "message",
                        "messageId": str(uuid.uuid4())
                    },
                    "configuration": {
                        "blocking": True,
                        "acceptedOutputModes": ["text"]
                    }
                }
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{agent['url']}/",
                    json=message_data,
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                agent_responses.append(f"{agent['name']}: {result}")

                # Store agent response
                agent_message = Message(
                    role='agent',
                    parts=[TextPart(text=f"{agent['name']}: {result}", kind='text')],
                    kind='message',
                    message_id=str(uuid.uuid4()),
                )

                current_context = await storage.load_context(context_id) or []
                current_context.append(agent_message)
                await storage.update_context(context_id, current_context)

        except Exception as e:
            error_msg = f"{agent['name']}: Error - {str(e)}"
            agent_responses.append(error_msg)

            # Store error message
            error_message = Message(
                role='agent',
                parts=[TextPart(text=error_msg, kind='text')],
                kind='message',
                message_id=str(uuid.uuid4()),
            )

            current_context = await storage.load_context(context_id) or []
            current_context.append(error_message)
            await storage.update_context(context_id, current_context)

    return {"status": "triggered", "context_id": context_id, "agents": len(agents), "responses": agent_responses}

@api.get("/messages")
async def get_all_messages():
    all_messages = []
    try:
        for context_id in context_tracker:
            context = await storage.load_context(context_id)
            if context:
                for message in context:
                    # Handle both Message objects and dict objects
                    if hasattr(message, 'message_id'):
                        # It's a Message object
                        all_messages.append({
                            "context_id": context_id,
                            "message_id": message.message_id,
                            "role": message.role,
                            "text": message.parts[0].text if message.parts else "",
                            "kind": message.kind
                        })
                    elif isinstance(message, dict):
                        # It's a dict object
                        all_messages.append({
                            "context_id": context_id,
                            "message_id": message.get('message_id', 'unknown'),
                            "role": message.get('role', 'unknown'),
                            "text": str(message),
                            "kind": message.get('kind', 'unknown')
                        })
                    else:
                        # Fallback for any other type
                        all_messages.append({
                            "context_id": context_id,
                            "message_id": "unknown",
                            "role": "unknown",
                            "text": str(message),
                            "kind": "unknown"
                        })
        return {"messages": all_messages}
    except Exception as e:
        return {"error": str(e), "messages": []}

api.mount("/a2a", a2a_app)
