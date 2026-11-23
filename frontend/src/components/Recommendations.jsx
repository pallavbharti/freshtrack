const LABELS = {
  REORDER: "Reorder",
  EXPIRY_RISK: "Expiry risk",
  OK: "OK",
};

const ORDER = { REORDER: 0, EXPIRY_RISK: 1, OK: 2 };

export default function Recommendations({ items, onSelect, selected }) {
  if (!items.length) return <p className="muted">No recommendations yet.</p>;

  const sorted = [...items].sort((a, b) => ORDER[a.action] - ORDER[b.action]);

  return (
    <table>
      <thead>
        <tr>
          <th>Product</th>
          <th>Action</th>
          <th className="num">Order qty</th>
          <th className="num">On hand</th>
          <th className="num">Usable</th>
          <th className="num">Likely waste</th>
          <th className="num">7-day demand</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => (
          <tr
            key={r.product_id}
            className={r.product_id === selected ? "selected clickable" : "clickable"}
            onClick={() => onSelect(r.product_id)}
          >
            <td>{r.name}</td>
            <td>
              <span className={`badge ${r.action.toLowerCase()}`}>{LABELS[r.action]}</span>
            </td>
            <td className="num">{r.qty || "-"}</td>
            <td className="num">{r.on_hand}</td>
            <td className="num">{r.usable_stock}</td>
            <td className="num">{r.expected_waste || "-"}</td>
            <td className="num">{Math.round(r.forecast_demand)}</td>
            <td className="muted small">{r.reason}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
