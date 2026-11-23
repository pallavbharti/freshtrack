import { describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import Recommendations from "./Recommendations";
import StockTable from "./StockTable";

const rec = (id, name, action, extra = {}) => ({
  product_id: id, sku: `S${id}`, name, action, qty: 0, on_hand: 10, usable_stock: 10,
  expected_waste: 0, forecast_demand: 20, lead_time_demand: 5, safety_stock: 2, reason: "r", ...extra,
});

describe("Recommendations", () => {
  it("lists the most urgent action first", () => {
    render(
      <Recommendations
        items={[rec(1, "Eggs", "OK"), rec(2, "Spinach", "EXPIRY_RISK", { expected_waste: 4 }),
          rec(3, "Milk", "REORDER", { qty: 12 })]}
        onSelect={vi.fn()}
        selected={null}
      />
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0].textContent)).toEqual(["Milk", "Spinach", "Eggs"]);
    expect(within(rows[0]).getByText("Reorder")).toBeInTheDocument();
    expect(within(rows[0]).getByText("12")).toBeInTheDocument();
  });

  it("says so when there is nothing to show", () => {
    render(<Recommendations items={[]} onSelect={vi.fn()} selected={null} />);
    expect(screen.getByText("No recommendations yet.")).toBeInTheDocument();
  });
});

describe("StockTable", () => {
  it("describes expiry in plain words", () => {
    const b = (id, days, status) => ({
      id, product_id: 1, product_name: `P${id}`, quantity: 5, received_date: "2026-01-01",
      expiry_date: "2026-01-05", days_to_expiry: days, status,
    });
    render(<StockTable rows={[b(1, -2, "expired"), b(2, 0, "expiring_soon"), b(3, 1, "expiring_soon"), b(4, 6, "fresh")]} />);
    expect(screen.getByText(/expired 2d ago/)).toBeInTheDocument();
    expect(screen.getByText(/today/)).toBeInTheDocument();
    expect(screen.getByText(/tomorrow/)).toBeInTheDocument();
    expect(screen.getByText(/in 6 days/)).toBeInTheDocument();
  });
});
