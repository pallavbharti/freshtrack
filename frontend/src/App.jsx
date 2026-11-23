import { useCallback, useEffect, useState } from "react";
import { api, getSession, logout, setUnauthorizedHandler } from "./api";
import Login from "./components/Login";
import Recommendations from "./components/Recommendations";
import StockTable from "./components/StockTable";
import ForecastChart from "./components/ForecastChart";
import QuickActions from "./components/QuickActions";

export default function App() {
  const [session, setSession] = useState(getSession());

  useEffect(() => {
    setUnauthorizedHandler(() => setSession(null));
  }, []);

  if (!session) return <Login onLogin={setSession} />;
  return (
    <Dashboard
      session={session}
      onLogout={() => {
        logout();
        setSession(null);
      }}
    />
  );
}

function Dashboard({ session, onLogout }) {
  const [products, setProducts] = useState([]);
  const [stock, setStock] = useState([]);
  const [recs, setRecs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setError("");
    try {
      const [p, s, r] = await Promise.all([api.products(), api.stock(), api.recommendations()]);
      setProducts(p);
      setStock(s);
      setRecs(r);
      setSelected((cur) => cur ?? p[0]?.id ?? null);
    } catch (e) {
      setError(`Could not load data from the API (${e.message})`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const count = (action) => recs.filter((r) => r.action === action).length;
  const waste = recs.reduce((sum, r) => sum + r.expected_waste, 0);

  return (
    <div className="page">
      <header>
        <div>
          <h1>FreshTrack</h1>
          <p className="muted">Demand forecast, stock and expiry for perishable items</p>
        </div>
        <div className="row">
          <span className="muted small user">
            {session.username} ({session.role})
          </span>
          <button onClick={load} disabled={loading}>Refresh</button>
          <button className="secondary" onClick={onLogout}>Sign out</button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <section className="tiles">
        <Tile label="Products" value={products.length} />
        <Tile label="Need reorder" value={count("REORDER")} tone="reorder" />
        <Tile label="Expiry risk" value={count("EXPIRY_RISK")} tone="risk" />
        <Tile label="Units likely to expire (7 days)" value={waste} tone="risk" />
      </section>

      <div className="grid">
        <section className="card wide">
          <h2>Recommendations</h2>
          <Recommendations items={recs} onSelect={setSelected} selected={selected} />
        </section>

        <section className="card wide">
          <div className="card-head">
            <h2>Demand forecast</h2>
            <select value={selected ?? ""} onChange={(e) => setSelected(Number(e.target.value))}>
              {products.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </div>
          {selected && <ForecastChart productId={selected} />}
        </section>

        <section className="card">
          <h2>Stock by batch</h2>
          <StockTable rows={stock} />
        </section>

        <section className="card">
          <h2>Quick actions</h2>
          {session.role === "manager" ? (
            <QuickActions products={products} onDone={load} />
          ) : (
            <p className="muted">Viewers can see everything but cannot change stock or sales.</p>
          )}
        </section>
      </div>
    </div>
  );
}

function Tile({ label, value, tone }) {
  return (
    <div className={`tile ${tone || ""}`}>
      <span className="tile-value">{value}</span>
      <span className="tile-label">{label}</span>
    </div>
  );
}
