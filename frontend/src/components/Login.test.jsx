import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Login from "./Login";
import { mockFetch } from "../test/helpers";

async function fillAndSubmit(user, password = "pw") {
  await user.type(screen.getByLabelText("Username"), "manager");
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("Login", () => {
  it("logs in and reports the role", async () => {
    mockFetch({ "POST /auth/login": [200, { access_token: "t", role: "manager", expires_in: 1800 }] });
    const onLogin = vi.fn();
    render(<Login onLogin={onLogin} />);
    await fillAndSubmit(userEvent.setup());
    expect(onLogin).toHaveBeenCalledWith({ token: "t", role: "manager", username: "manager" });
  });

  it("shows a generic error on a wrong password", async () => {
    mockFetch({ "POST /auth/login": [401, { detail: "wrong username or password" }] });
    const onLogin = vi.fn();
    render(<Login onLogin={onLogin} />);
    await fillAndSubmit(userEvent.setup(), "bad");
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong username or password.");
    expect(onLogin).not.toHaveBeenCalled();
  });

  it("explains the lockout when rate limited", async () => {
    mockFetch({ "POST /auth/login": [429, { detail: "too many failed logins" }] });
    render(<Login onLogin={vi.fn()} />);
    await fillAndSubmit(userEvent.setup(), "bad");
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many failed attempts");
  });
});
