/**
 * AutoJob AI — Auth Context
 * Global authentication state with persistent token storage.
 */

"use client";

import {
    createContext,
    useContext,
    useEffect,
    useState,
    useCallback,
    type ReactNode,
} from "react";
import { authApi, type UserProfile } from "@/lib/api";

interface AuthState {
    user: UserProfile | null;
    token: string | null;
    isLoading: boolean;
    isAuthenticated: boolean;
}

interface AuthContextValue extends AuthState {
    login: (token: string, user: UserProfile) => void;
    logout: () => void;
    refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [state, setState] = useState<AuthState>({
        user: null,
        token: null,
        isLoading: true,
        isAuthenticated: false,
    });

    /** Restore session from localStorage on mount */
    useEffect(() => {
        const savedToken = localStorage.getItem("token");
        if (!savedToken) {
            setState((s) => ({ ...s, isLoading: false }));
            return;
        }

        // Validate token by fetching /me
        authApi
            .getMe()
            .then((user) => {
                setState({
                    user,
                    token: savedToken,
                    isLoading: false,
                    isAuthenticated: true,
                });
            })
            .catch(() => {
                localStorage.removeItem("token");
                setState({ user: null, token: null, isLoading: false, isAuthenticated: false });
            });
    }, []);

    const login = useCallback((token: string, user: UserProfile) => {
        localStorage.setItem("token", token);
        setState({ user, token, isLoading: false, isAuthenticated: true });
    }, []);

    const logout = useCallback(() => {
        localStorage.removeItem("token");
        setState({ user: null, token: null, isLoading: false, isAuthenticated: false });
    }, []);

    const refreshUser = useCallback(async () => {
        try {
            const user = await authApi.getMe();
            setState((s) => ({ ...s, user }));
        } catch {
            logout();
        }
    }, [logout]);

    return (
        <AuthContext.Provider
            value={{ ...state, login, logout, refreshUser }}
        >
            {children}
        </AuthContext.Provider>
    );
}

/** Hook to access auth state and actions */
export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used within AuthProvider");
    return ctx;
}
