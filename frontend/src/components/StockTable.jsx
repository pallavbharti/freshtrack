function expiryText(days) {
  if (days < 0) return `expired ${-days}d ago`;
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

export default function StockTable({ rows }) {
  if (!rows.length) return <p className="muted">No stock recorded.</p>;

  return (
    <table>
      <thead>
        <tr>
          <th>Product</th>
          <th className="num">Qty</th>
          <th>Expires</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((b) => (
          <tr key={b.id} className={`expiry-${b.status}`}>
            <td>{b.product_name}</td>
            <td className="num">{b.quantity}</td>
            <td>
              <span className="dot" /> {expiryText(b.days_to_expiry)}
              <span className="muted small"> ({b.expiry_date})</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
