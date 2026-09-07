import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "../pages/LoginPage";
import { AuthProvider } from "../auth/AuthContext";
import type { MeResponse, TokenResponse } from "../lib/types/domain";

const login = vi.fn();
const register = vi.fn();
const getMe = vi.fn();

vi.mock("../lib/api/auth", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api/auth")>();
  return {
    ...actual,
    login: (...args: unknown[]) => login(...args),
    register: (...args: unknown[]) => register(...args),
    getMe: (...args: unknown[]) => getMe(...args),
  };
});

vi.mock("../lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api/client")>();
  return {
    ...actual,
    getToken: () => null,
  };
});

const token: TokenResponse = { access_token: "t", token_type: "bearer", expires_in: 3600 };
const me: MeResponse = {
  user: { id: "u1", email: "chair@example.com", full_name: "Chair", role: "chairman", can_authorize_level4: true },
  organization: { id: "o1", name: "Artiswon", slug: "artiswon", is_demo: true },
};

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    login.mockResolvedValue(token);
    register.mockResolvedValue(token);
    getMe.mockResolvedValue(me);
  });

  it("renders both authentication modes", () => {
    renderPage();
    expect(screen.getByRole("tab", { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /create account/i })).toBeInTheDocument();
  });

  it("signs in via the real auth endpoint and stores the session", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByLabelText(/email/i), "chair@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(login).toHaveBeenCalledWith({ email: "chair@example.com", password: "supersecret" });
    });
    expect(localStorage.getItem("avnexus_token")).toBe("t");
  });

  it("switches to registration mode", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("tab", { name: /create account/i }));
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    await user.type(screen.getByLabelText(/full name/i), "New Chair");
    await user.type(screen.getByLabelText(/email/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => {
      expect(register).toHaveBeenCalledWith({
        email: "new@example.com",
        password: "supersecret",
        full_name: "New Chair",
        org_name: "Artiswon",
      });
    });
  });

  it("shows an error message when authentication fails", async () => {
    const user = userEvent.setup();
    login.mockRejectedValue(new Error("Invalid credentials"));
    renderPage();
    await user.type(screen.getByLabelText(/email/i), "bad@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "secret123");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await screen.findByRole("alert");
    expect(screen.getByRole("alert")).toHaveTextContent("Invalid credentials");
  });
});