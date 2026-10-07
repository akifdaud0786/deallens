import type { Card, PageState, ProductResponse } from "../types/deallens";

// Read-only GETs. Paths are relative `.json` files so the same build works against the local API
// (`deallens.cli serve`, which answers these names) and the static GitHub Pages site (`export-static`).
async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${path} returned ${res.status}`);
  return (await res.json()) as T;
}

export const api = {
  status: () => get<PageState>("api/status.json"),
  products: () => get<Card[]>("api/products.json"),
  product: (key: string) => get<ProductResponse>(`api/products/${encodeURIComponent(key)}.json`),
};
