import { vi } from "vitest";

export function mockFetch(routes) {
  const fn = vi.fn(async (url, opts = {}) => {
    const method = (opts.method || "GET").toUpperCase();
    const path = url.replace(/^\/api/, "");
    const key = Object.keys(routes).find((k) => `${method} ${path}`.startsWith(k));
    const [status, body] = key ? routes[key] : [404, { detail: "not found" }];
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: String(status),
      json: async () => body,
    };
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
