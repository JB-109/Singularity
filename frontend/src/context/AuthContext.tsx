import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';

const API_URL = 'http://localhost:8000';

interface User {
    user_id: string;
    username: string;
}

interface AuthContextType {
    user: User | null;
    token: string | null;
    isLoading: boolean;
    login: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
    register: (username: string, password: string) => Promise<{ success: boolean; error?: string }>;
    logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);

    // Check for existing token on mount
    useEffect(() => {
        const storedToken = localStorage.getItem('auth_token');
        const storedUser = localStorage.getItem('auth_user');

        if (storedToken && storedUser) {
            setToken(storedToken);
            setUser(JSON.parse(storedUser));
        }
        setIsLoading(false);
    }, []);

    const login = async (username: string, password: string) => {
        try {
            const response = await fetch(`${API_URL}/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await response.json();

            if (data.success) {
                const userData = { user_id: data.user_id, username: data.username };
                setToken(data.token);
                setUser(userData);
                localStorage.setItem('auth_token', data.token);
                localStorage.setItem('auth_user', JSON.stringify(userData));
                return { success: true };
            } else {
                return { success: false, error: data.error };
            }
        } catch {
            return { success: false, error: 'Failed to connect to server' };
        }
    };

    const register = async (username: string, password: string) => {
        try {
            const response = await fetch(`${API_URL}/api/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await response.json();

            if (data.success) {
                const userData = { user_id: data.user_id, username: data.username };
                setToken(data.token);
                setUser(userData);
                localStorage.setItem('auth_token', data.token);
                localStorage.setItem('auth_user', JSON.stringify(userData));
                return { success: true };
            } else {
                return { success: false, error: data.error };
            }
        } catch {
            return { success: false, error: 'Failed to connect to server' };
        }
    };

    const logout = () => {
        if (token) {
            fetch(`${API_URL}/api/logout`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
            });
        }
        setToken(null);
        setUser(null);
        localStorage.removeItem('auth_token');
        localStorage.removeItem('auth_user');
    };

    return (
        <AuthContext.Provider value={{ user, token, isLoading, login, register, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
