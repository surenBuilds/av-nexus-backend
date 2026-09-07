import { request } from "./client";
import type {
  WorkflowCreatePayload,
  WorkflowDetail,
  WorkflowResultData,
  WorkflowSnapshot,
  WorkflowTaskRef,
  WorkflowTrace,
} from "../types/domain";

export const WORKFLOW_TERMINAL = new Set(["COMPLETED", "FAILED", "CANCELLED"]);
export const WORKFLOW_ACTIVE = new Set([
  "CREATED",
  "PLANNING",
  "RUNNING",
  "WAITING_FOR_DEPENDENCY",
  "WAITING_FOR_APPROVAL",
]);

export function createWorkflow(payload: WorkflowCreatePayload): Promise<WorkflowSnapshot> {
  return request<WorkflowSnapshot>("/workflows", { method: "POST", body: payload });
}

export function listWorkflows(): Promise<WorkflowSnapshot[]> {
  return request<WorkflowSnapshot[]>("/workflows");
}

export function getWorkflow(id: string): Promise<WorkflowDetail> {
  return request<WorkflowDetail>(`/workflows/${id}`);
}

export function startWorkflow(id: string, reason = ""): Promise<WorkflowSnapshot> {
  return request<WorkflowSnapshot>(`/workflows/${id}/start`, {
    method: "POST",
    body: { reason },
  });
}

export function cancelWorkflow(id: string, reason = ""): Promise<WorkflowSnapshot> {
  return request<WorkflowSnapshot>(`/workflows/${id}/cancel`, {
    method: "POST",
    body: { reason },
  });
}

export function resumeWorkflow(id: string, reason = ""): Promise<WorkflowSnapshot> {
  return request<WorkflowSnapshot>(`/workflows/${id}/resume`, {
    method: "POST",
    body: { reason },
  });
}

export function getWorkflowTasks(id: string): Promise<WorkflowTaskRef[]> {
  return request<WorkflowTaskRef[]>(`/workflows/${id}/tasks`);
}

export function getWorkflowTrace(id: string): Promise<WorkflowTrace> {
  return request<WorkflowTrace>(`/workflows/${id}/trace`);
}

export function getWorkflowResult(id: string): Promise<WorkflowResultData> {
  return request<WorkflowResultData>(`/workflows/${id}/result`);
}