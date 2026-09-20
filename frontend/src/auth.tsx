/* Auth context and hooks for managing authentication state. */
import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

export interface User {
  id: string;
  email: string;
  name: string;
  role: "admin" | "engineer" | "viewer";
  organization_id: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  subscription_tier: "free" | "pro" | "enterprise";
}

export interface APIKey {
  id: string;
  name: string;
  key_hash: string;
  organization_id: string;
  scopes: string[];
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface Asset {
  id: string;
  name: string;
  rpm: number;
  bearing_type: string;
  baseline: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

interface AuthState {
  user: User | null;
  organization: Organization | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

const API_BASE = import.meta.env.VITE_API_URL || "";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const refreshAuth = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
        credentials: "include",
      });
      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setOrganization(data.organization);
        setIsAuthenticated(true);
      } else {
        setUser(null);
        setOrganization(null);
        setIsAuthenticated(false);
      }
    } catch {
      setUser(null);
      setOrganization(null);
      setIsAuthenticated(false);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Login failed");
    }
    await refreshAuth();
  };

  const logout = async () => {
    await fetch(`${API_BASE}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    setUser(null);
    setOrganization(null);
    setIsAuthenticated(false);
  };

  useEffect(() => {
    refreshAuth();
  }, [refreshAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        organization,
        isLoading,
        isAuthenticated,
        login,
        logout,
        refreshAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}