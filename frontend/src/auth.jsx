import { createContext, useContext, useEffect, useState } from "react";
import { apiGet, getAuthExpiredEvent, getEntityId, getStoredUser, logout as clearSession, storeSession } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser());
  const [brand, setBrand] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authRequired, setAuthRequired] = useState(false);

  const refresh = async () => {
    try {
      const health = await fetch(
        `${import.meta.env.VITE_API_URL || ""}/api/health`
      ).then((r) => r.json());
      setAuthRequired(Boolean(health.auth_required));

      const config = await apiGet("/config");
      setBrand(config.brand || null);

      if (!health.auth_required) {
        const me = await apiGet("/auth/me");
        setUser(me);
        return;
      }

      const token = localStorage.getItem(`${getEntityId()}_token`);
      if (!token) {
        setUser(null);
        return;
      }
      const me = await apiGet("/auth/me");
      setUser(me);
      storeSession(token, me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    const onExpired = () => setUser(null);
    window.addEventListener(getAuthExpiredEvent(), onExpired);
    return () => window.removeEventListener(getAuthExpiredEvent(), onExpired);
  }, []);

  const login = (token, userData) => {
    storeSession(token, userData);
    setUser(userData);
  };

  const logout = () => {
    clearSession();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, brand, loading, authRequired, login, logout, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
