import { request } from "./client";
import type { Task, TaskCreatePayload, TaskRunResponse } from "../types/domain";

export function createTask(payload: TaskCreatePayload): Promise<Task> {
  return request<Task>("/tasks", { method: "POST", body: payload });
}

export function getTask(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${encodeURIComponent(taskId)}`);
}

export function runTask(taskId: string): Promise<TaskRunResponse> {
  return request<TaskRunResponse>(`/tasks/${encodeURIComponent(taskId)}/run`, { method: "POST" });
}

/** Create a task routed to `capability` and immediately run it — the common
 * case for the ad-hoc "run this agent now" panel. */
export async function runAgentNow(
  capability: string,
  goal: string,
  inputJson: Record<string, unknown>,
  title?: string,
): Promise<TaskRunResponse> {
  const task = await createTask({
    title: title || goal.slice(0, 80),
    goal,
    capability,
    input_json: inputJson,
  });
  return runTask(task.id);
}
