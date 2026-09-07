import { request } from "./client";
import type { Agent, AgentMessage, AgentRun, Task } from "../types/domain";

export function listAgents(): Promise<Agent[]> {
  return request<Agent[]>("/agents");
}

export function getAgent(agentId: string): Promise<Agent> {
  return request<Agent>(`/agents/${encodeURIComponent(agentId)}`);
}

export function listAgentRuns(agentId: string): Promise<AgentRun[]> {
  return request<AgentRun[]>(`/agents/${encodeURIComponent(agentId)}/runs`);
}

export function listAgentMessages(agentId: string): Promise<AgentMessage[]> {
  return request<AgentMessage[]>(`/agents/${encodeURIComponent(agentId)}/messages`);
}

export function listTasks(agentId?: string): Promise<Task[]> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
  return request<Task[]>(`/tasks${query}`);
}