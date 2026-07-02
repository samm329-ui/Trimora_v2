const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${String(input)}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export { API_BASE, request };
