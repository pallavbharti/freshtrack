import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";
import { setSession } from "./api";
import { mockFetch } from "./test/helpers";

const data = {
  "GET /products": [200, [{ id: 1, sku: "MLK", name: "Milk", category: "Dairy", shelf_life_days: 3,
    lead_time_days: 1, unit_price: 50 }]],
  "GET /stock": [200, []],
  "GET /recommendations": [200, []],
  "GET /sales": [200, []],
  "GET /forecast/1": [200, { product_id: 1, sku: "MLK", days: 7, total_predicted: 0, points: [] }],
};

describe("App", () => {
  beforeEach(() => setSession(null));

  it("shows the login screen without a session", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("hides write actions from a viewer", async () => {
    setSession({ token: "t", role: "viewer", username: "viewer" });
    mockFetch(data);
    render(<App />);
    expect(await screen.findByText("viewer (viewer)")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Receive delivery" })).not.toBeInTheDocument();
    expect(screen.getByText(/Viewers can see everything/)).toBeInTheDocument();
  });

  it("shows write actions to a manager", async () => {
    setSession({ token: "t", role: "manager", username: "manager" });
    mockFetch(data);
    render(<App />);
    expect(await screen.findByRole("button", { name: "Receive delivery" })).toBeInTheDocument();
  });
});
