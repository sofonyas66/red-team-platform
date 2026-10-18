'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import api, { setAuthToken, setOrgId, getAuthToken } from './api-client';
import { AuthUser, LoginRequest, LoginResponse, UserClaims } from './types/auth';

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function decodeJWT<T>(token: string): T | null {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
      return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
    }).join(''));
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const handleAuth = useCallback((token: string, username?: string) => {
    const claims = decodeJWT<UserClaims>(token);
    if (claims) {
      const authUser: AuthUser = {
        ...claims,
        username: username || localStorage.getItem('user_username') || 'Operator',
      };
      
      setToken(token);
      setUser(authUser);
      setAuthToken(token);
      setOrgId(claims.org_id);
      
      if (username) {
        localStorage.setItem('user_username', username);
      }
    }
  }, []);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setAuthToken(null);
    setOrgId(null);
    localStorage.removeItem('user_username');
    router.push('/login');
  }, [router]);

  const login = async (credentials: LoginRequest) => {
    try {
      const response = await api.post<LoginResponse>('/auth/login', credentials);
      const { access_token } = response.data;
      handleAuth(access_token, credentials.username);
      router.push('/');
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  };

  // Initial load
  useEffect(() => {
    const initAuth = async () => {
      const storedToken = getAuthToken();
      if (storedToken) {
        const claims = decodeJWT<UserClaims>(storedToken);
        if (claims) {
          const isExpired = claims.exp ? claims.exp * 1000 < Date.now() : false;
          if (!isExpired) {
            handleAuth(storedToken);
          } else {
            logout();
          }
        } else {
          logout();
        }
      }
      setIsLoading(false);
    };

    initAuth();
  }, [handleAuth, logout]);

  // Protected route handling
  useEffect(() => {
    if (!isLoading && !token && pathname !== '/login') {
      router.replace('/login');
    }
  }, [isLoading, token, pathname, router]);

  return (
    <AuthContext.Provider value={{ user, token, isLoading, login, logout, isAuthenticated: !!token }}>
      {!isLoading || pathname === '/login' ? children : (
        <div className="min-h-screen app-shell flex items-center justify-center">
          <div className="text-center">
            <div className="brand-mark h-8 gap-1 mb-4 mx-auto justify-center">
              <span className="h-4 opacity-50 w-1.5" />
              <span className="h-7 w-1.5" />
              <span className="h-5 opacity-80 w-1.5" />
            </div>
            <p className="text-xs font-bold tracking-widest text-[#35d399] animate-pulse uppercase">
              Initializing Secure Session...
            </p>
          </div>
        </div>
      )}
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
