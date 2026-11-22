import { useState } from "react";
import { api } from "../api";

const today = () => new Date().toISOString().slice(0, 10);

function addDays(dateStr, n) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default function QuickActions({ products, onDone }) {
  const [productId, setProductId] = useState("");
  const [qty, setQty] = useState(10);
  const [msg, setMsg] = useState(null);

  const product = products.find((p) => p.id === Number(productId)) || products[0];

  async function run(kind) {
    if (!product) return;
    setMsg(null);
    try {
      if (kind === "stock") {
        await api.addStock({
          product_id: product.id,
          quantity: Number(qty),
          received_date: today(),
          expiry_date: addDays(today(), product.shelf_life_days),
        });
        setMsg({ ok: true, text: `Added ${qty} x ${product.name}` });
      } else {
        await api.recordSale({ product_id: product.id, sale_date: today(), quantity: Number(qty) });
        setMsg({ ok: true, text: `Sold ${qty} x ${product.name}` });
      }
      onDone();
    } catch (e) {
      setMsg({ ok: false, text: e.message });
    }
  }

  return (
    <div className="actions">
      <label>
        Product
        <select value={product?.id ?? ""} onChange={(e) => setProductId(e.target.value)}>
          {products.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
      </label>
      <label>
        Quantity
        <input type="number" min="1" value={qty} onChange={(e) => setQty(e.target.value)} />
      </label>
      <div className="row">
        <button onClick={() => run("stock")}>Receive delivery</button>
        <button className="secondary" onClick={() => run("sale")}>Record sale</button>
      </div>
      {product && (
        <p className="muted small">
          New deliveries expire after {product.shelf_life_days} days. Sales are taken from the
          batch that expires first.
        </p>
      )}
      {msg && <p className={msg.ok ? "success" : "error"}>{msg.text}</p>}
    </div>
  );
}
