const TOKEN_STORAGE_KEY = "raisa-synapse-access-token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  else window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(body.message || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export type LoginResponse = { access_token: string; token_type: string };
export type CurrentUser = {
  id: string;
  organization_id: string;
  email: string;
  name: string;
  status: string;
  theme_preference: string;
};

export const api = {
  login: (organization_slug: string, email: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ organization_slug, email, password }),
    }),
  me: () => request<CurrentUser>("/auth/me"),
  organization: () => request("/organizations/me"),
  users: () => request("/users"),
  auditEvents: () => request("/audit"),
  // Layer 2
  products: () => request<RegulatoryProduct[]>("/products"),
  dossiers: (productId?: string) => request<RegulatoryDossier[]>(`/dossiers${productId ? `?product_id=${productId}` : ""}`),
  transitionDossier: (dossierId: string, new_status: string, reason?: string) =>
    request<RegulatoryDossier>(`/dossiers/${dossierId}/transition`, {
      method: "POST",
      body: JSON.stringify({ new_status, reason }),
    }),
};

export type RegulatoryProduct = {
  id: string;
  name: string;
  active_ingredient: string | null;
  dosage_form: string | null;
  development_status: string;
  status: string;
};

export type RegulatoryDossier = {
  id: string;
  product_id: string;
  region: string;
  ctd_standard: string;
  standard_version: string;
  status: string;
};

// Layer 3
export type IntelligenceItem = {
  id: string;
  organization_id: string;
  scope: string;
  intelligence_type: string;
  title: string;
  summary: string;
  authority_id: string | null;
  country_region: string | null;
  publication_date: string | null;
  effective_date: string | null;
  status: string;
  impact_level: string;
  impact_reason: string;
  therapeutic_area: string | null;
};

export const intelligenceApi = {
  list: (filters: { intelligence_type?: string; impact_level?: string; status_filter?: string; limit?: number } = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => v !== undefined && params.set(k, String(v)));
    const qs = params.toString();
    return request<IntelligenceItem[]>(`/intelligence${qs ? `?${qs}` : ""}`);
  },
};
