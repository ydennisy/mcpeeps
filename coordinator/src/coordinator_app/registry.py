"""Agent registry utilities."""

from __future__ import annotations

import httpx


class AgentRegistry:
    """Keeps track of known agents and their health."""

    def __init__(self):
        self.agents = [
            {"name": "game-tester", "url": "http://localhost:8001", "emoji": "🎮"},
            {"name": "swe-agent", "url": "http://localhost:8002", "emoji": "👨‍💻"},
            {"name": "product-manager", "url": "http://localhost:8003", "emoji": "📋"},
        ]

    def get_all_agents(self):
        return self.agents

    def get_emoji_for_agent(self, agent_name: str) -> str:
        """Get emoji for a specific agent, with fallbacks."""
        if agent_name == "user":
            return "👤"

        for agent in self.agents:
            if agent["name"] == agent_name:
                return agent.get("emoji", "🤖")

        return "🤖"  # Default fallback emoji

    def get_agent_display_name(self, agent_name: str) -> str:
        """Get display name for an agent."""
        if agent_name == "user":
            return "User"
        return agent_name

    async def check_agent_health(self, agent_url: str) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{agent_url}/health", timeout=5.0)
                return response.status_code == 200
        except Exception:
            return False

