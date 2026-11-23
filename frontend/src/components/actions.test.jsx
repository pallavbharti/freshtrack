import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import QuickActions from "./QuickActions";
import ForecastChart from "./ForecastChart";
import { mockFetch } from "../test/helpers";

const products = [
  { id: 1, sku: "MLK", name: "Milk", shelf_life_days: 3 },
  { id: 2, sku: "BRD", name: "Bread", shelf_life_days: 4 },
];

afterEach(() => vi.unstubAllGlobals());

describe("QuickActions", () => {
  it("receives a delivery with an expiry date from the shelf life", async () => {
    const fetch = mockFetch({ "POST /stock": [201, { id: 9 }] });
    const onDone = vi.fn();
    render(<QuickActions products={products} onDone={onDone} />);

    await userEvent.selectOptions(screen.getByRole("combobox"), "2");
    await userEvent.clear(screen.getByRole("spinbutton"));
    await userEvent.type(screen.getByRole("spinbutton"), "5");
    await userEvent.click(screen.getByRole("button", { name: "Receive delivery" }));

    expect(await screen.findByText("Added 5 x Bread")).toBeInTheDocument();
    const body = JSON.parse(fetch.mock.calls[0][1].body);
    expect(body).toMatchObject({ product_id: 2, quantity: 5 });
    const days = (new Date(body.expiry_date) - new Date(body.received_date)) / 86400000;
    expect(days).toBe(4);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("records a sale", async () => {
    mockFetch({ "POST /sales": [201, { id: 1 }] });
    render(<QuickActions products={products} onDone={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Record sale" }));
    expect(await screen.findByText("Sold 10 x Milk")).toBeInTheDocument();
  });

  it("shows the API error and does not report success", async () => {
    mockFetch({ "POST /sales": [403, { detail: "manager role required" }] });
    const onDone = vi.fn();
    render(<QuickActions products={products} onDone={onDone} />);
    await userEvent.click(screen.getByRole("button", { name: "Record sale" }));
    expect(await screen.findByText("403: manager role required")).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("does nothing without products", async () => {
    const fetch = mockFetch({});
    render(<QuickActions products={[]} onDone={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Receive delivery" }));
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("ForecastChart", () => {
  const sales = Array.from({ length: 14 }, (_, i) => ({
    sale_date: `2026-06-${String(i + 1).padStart(2, "0")}`, quantity: 10 + i,
  }));
  const forecast = {
    total_predicted: 84.4,
    points: Array.from({ length: 7 }, (_, i) => ({ date: `2026-06-${15 + i}`, predicted_qty: 12 })),
  };

  it("draws actual sales and the forecast with the weekly total", async () => {
    mockFetch({ "GET /sales": [200, sales], "GET /forecast/1": [200, forecast] });
    const { container } = render(<ForecastChart productId={1} />);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(await screen.findByText("Next 7 days: about 84 units")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Sales and forecast" })).toBeInTheDocument();
    expect(container.querySelector(".line-actual").getAttribute("d")).toMatch(/^M/);
    expect(container.querySelector(".future")).not.toBeNull();
  });

  it("draws only the forecast when there is no sales history", async () => {
    mockFetch({ "GET /sales": [200, []], "GET /forecast/1": [200, forecast] });
    const { container } = render(<ForecastChart productId={1} />);
    expect(await screen.findByText(/Next 7 days/)).toBeInTheDocument();
    expect(container.querySelector(".future")).toBeNull();
  });

  it("shows an error when the forecast cannot be loaded", async () => {
    mockFetch({ "GET /sales": [200, sales], "GET /forecast/1": [503, { detail: "model not loaded" }] });
    render(<ForecastChart productId={1} />);
    expect(await screen.findByText("503: model not loaded")).toBeInTheDocument();
  });
});
