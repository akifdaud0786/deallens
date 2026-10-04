import type { Card, PageState, ProductResponse } from "../types/deallens";

// Read-only: GET requests to the local DealLens API only.
async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${path} returned ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  status: () => get<PageState>("/api/status"),
  products: () => get<Card[]>("/api/products"),
  product: (key: string) => get<ProductResponse>(`/api/products/${encodeURIComponent(key)}`),
};
