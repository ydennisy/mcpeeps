from pydantic_ai import Agent
from dotenv import load_dotenv

load_dotenv()

agent = Agent('openai:gpt-4.1')
app = agent.to_a2a()
