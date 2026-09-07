"""Agent registry: dynamic discovery by capability."""

from __future__ import annotations

from av_nexus.agents.base import BaseAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        if agent.agent_id in self._agents:
            raise ValueError(f"Agent already registered: {agent.agent_id}")
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> BaseAgent | None:
        return self._agents.get(agent_id)

    def require(self, agent_id: str) -> BaseAgent:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise KeyError(f"Unknown agent: {agent_id}")
        return agent

    def all(self) -> list[BaseAgent]:
        return list(self._agents.values())

    def find_by_capability(self, capability: str) -> list[BaseAgent]:
        return [a for a in self._agents.values() if capability in a.capabilities]

    def snapshot(self) -> list[dict[str, object]]:
        return [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "role": a.role,
                "description": a.description,
                "capabilities": a.capabilities,
                "tools": a.tools,
                "permissions": a.permissions,
                "status": "idle",
                "performance_score": 0.0,
                "tasks_completed": 0,
            }
            for a in self.all()
        ]

    def count(self) -> int:
        return len(self._agents)

    def agent_ids(self) -> list[str]:
        return sorted(self._agents)
