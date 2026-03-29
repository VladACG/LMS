const API_BASE = import.meta.env.VITE_API_BASE ?? '';
const TOKEN_KEY = 'lms_access_token';

let accessToken: string | null = typeof window !== 'undefined' ? window.localStorage.getItem(TOKEN_KEY) : null;

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function setAuthToken(token: string | null): void {
  accessToken = token;
  if (typeof window === 'undefined') {
    return;
  }
  if (token) {
    window.localStorage.setItem(TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_KEY);
  }
}

export function getAuthToken(): string | null {
  return accessToken;
}

function buildHeaders(contentType = true): Record<string, string> {
  const headers: Record<string, string> = {};
  if (contentType) {
    headers['Content-Type'] = 'application/json';
  }
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return headers;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) {
        detail = body.detail;
      }
    } catch {
      // keep default message when body is not JSON
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) {
    return null as T;
  }

  return (await response.json()) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: buildHeaders(false),
  });
  return parseResponse<T>(response);
}

export async function apiPost<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: buildHeaders(true),
    body: JSON.stringify(payload),
  });
  return parseResponse<T>(response);
}

export async function apiGetBlob(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: buildHeaders(false),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body?.detail) {
        detail = body.detail;
      }
    } catch {
      // keep default detail
    }
    throw new ApiError(detail, response.status);
  }

  const contentDisposition = response.headers.get('content-disposition') ?? '';
  const match = contentDisposition.match(/filename=([^;]+)/i);
  const filename = match ? match[1].replace(/"/g, '').trim() : null;
  return { blob: await response.blob(), filename };
}
