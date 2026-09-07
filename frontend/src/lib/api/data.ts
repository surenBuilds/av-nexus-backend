import { request } from "./client";
import type { DashboardSummary } from "../types/dashboard";
import type { ActivityItem, Decision, Opportunity, Company, Approval } from "../types/domain";

export function getDashboard(): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard");
}

export function listOpportunities(): Promise<Opportunity[]> {
  return request<Opportunity[]>("/opportunities");
}

export function listCompanies(): Promise<Company[]> {
  return request<Company[]>("/companies");
}

export function listApprovals(): Promise<Approval[]> {
  return request<Approval[]>("/approvals");
}

export function decideApproval(
  approvalId: string,
  decision: "approve" | "reject",
  reason?: string,
): Promise<Approval> {
  return request<Approval>(`/approvals/${approvalId}/${decision}`, {
    method: "POST",
    body: { decision, reason: reason ?? "" },
  });
}

export function listDecisions(): Promise<Decision[]> {
  return request<Decision[]>("/decisions");
}

export function listActivity(): Promise<ActivityItem[]> {
  return request<ActivityItem[]>("/activity");
}