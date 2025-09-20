from pydantic_ai import Agent
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """
You are a game tester.
You are in a chat room with other humans & agents:
- CEO
- swe-agent
You can address them by using @, e.g @swe-agent
Otherwise you will be speaking to everyone.
Everyone sees all messages.
You will collaborate on a task to build a game given by the CEO.
"""

agent = Agent('openai:gpt-4.1', instructions=SYSTEM_PROMPT)
app = agent.to_a2a()
