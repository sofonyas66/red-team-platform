import axios, { AxiosInstance } from 'axios';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export function getAuthToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('token');
}

export function setAuthToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  if (token) {
    localStorage.setItem('token', token);
  } else {
    localStorage.removeItem('token');
  }
}

export function getOrgId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('org_id');
}

export function setOrgId(orgId: string | null): void {
  if (typeof window === 'undefined') return;
  if (orgId) {
    localStorage.setItem('org_id', orgId);
  } else {
    localStorage.removeItem('org_id');
  }
}

export function getEngagementId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('engagement_id');
}

export function setEngagementId(id: string | null): void {
  if (typeof window === 'undefined') return;
  if (id) {
    localStorage.setItem('engagement_id', id);
  } else {
    localStorage.removeItem('engagement_id');
  }
  // Notify React components listening for changes
  try {
    window.dispatchEvent(new CustomEvent('engagement-change'));
  } catch {}
}

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = getAuthToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (typeof window !== 'undefined' && error.response?.status === 401) {
      const url = error.config?.url || '';
      const isLoginRequest = url.includes('/auth/login');
      const isLoginPage = window.location.pathname.startsWith('/login');

      if (!isLoginRequest && !isLoginPage) {
        setAuthToken(null);
        setOrgId(null);
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;
