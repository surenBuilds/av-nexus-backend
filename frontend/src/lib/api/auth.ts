import { request, setSession } from "./client";
import type { MeResponse, TokenResponse } from "../types/domain";

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  org_name: string;
}

export function login(input: LoginInput): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", { method: "POST", body: input }, false);
}

export function register(input: RegisterInput): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/register", { method: "POST", body: input }, false);
}

export function getMe(): Promise<MeResponse> {
  return request<MeResponse>("/auth/me");
}

export function saveSession(response: TokenResponse, me: MeResponse): void {
  setSession(response.access_token, JSON.stringify(me));
}