"""Agent registry utilities."""

from __future__ import annotations

import httpx


class AgentRegistry:
    """Keeps track of known agents and their health."""

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

