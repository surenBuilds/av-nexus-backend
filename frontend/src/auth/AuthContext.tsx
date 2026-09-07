import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { MeResponse } from "../lib/types/domain";
import { clearSession, getToken } from "../lib/api/client";
import { getMe, saveSession, type LoginInput, type RegisterInput, login as apiLogin, register as apiRegister } from "../lib/api/auth";

interface AuthContextValue {
  token: string | null;
  me: MeResponse | null;
  loading: boolean;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getToken());
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(() => Boolean(getToken()));

  useEffect(() => {
    if (!token) {
      setMe(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    getMe()
      .then((value) => {
        if (!cancelled) {
          setMe(value);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearSession();
          setToken(null);
          setMe(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      me,
      loading,
      login: async (input) => {
        const response = await apiLogin(input);
        const current = await getMe();
        saveSession(response, current);
        setToken(response.access_token);
        setMe(current);
      },
      register: async (input) => {
        const response = await apiRegister(input);
        const current = await getMe();
        saveSession(response, current);
        setToken(response.access_token);
        setMe(current);
      },
      logout: () => {
        clearSession();
        setToken(null);
        setMe(null);
      },
    }),
    [token, me, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}