import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, getSession, login, setSession, setUnauthorizedHandler } from "./api";
import { mockFetch } from "./test/helpers";

describe("api client", () => {
  beforeEach(() => setSession(null));

  it("sends the bearer token once logged in", async () => {
    const fetch = mockFetch({
      "POST /auth/login": [200, { access_token: "tok123", role: "viewer", expires_in: 1800 }],
      "GET /products": [200, []],
    });
    await login("viewer", "pw");
    await api.products();
    const [, opts] = fetch.mock.calls[1];
    expect(opts.headers.Authorization).toBe("Bearer tok123");
    expect(getSession().role).toBe("viewer");
  });

  it("sends no token before login", async () => {
    const fetch = mockFetch({ "GET /products": [401, { detail: "not authenticated" }] });
    await expect(api.products()).rejects.toThrow("401");
    expect(fetch.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("drops the session and calls the handler on 401", async () => {
    setSession({ token: "expired", role: "manager", username: "manager" });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch({ "GET /stock": [401, { detail: "not authenticated" }] });
    await expect(api.stock()).rejects.toThrow("401");
    expect(getSession()).toBeNull();
    expect(handler).toHaveBeenCalledOnce();
  });

  it("does not keep a session when login fails", async () => {
    mockFetch({ "POST /auth/login": [401, { detail: "wrong username or password" }] });
    await expect(login("manager", "bad")).rejects.toThrow("401");
    expect(getSession()).toBeNull();
  });
});
