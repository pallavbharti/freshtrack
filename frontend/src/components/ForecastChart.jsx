import { useEffect, useState } from "react";
import { api } from "../api";

const W = 720;
const H = 240;
const PAD = { top: 16, right: 16, bottom: 28, left: 40 };

export default function ForecastChart({ productId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setError("");
    Promise.all([api.sales(productId, 28), api.forecast(productId, 7)])
      .then(([sales, fc]) => {
        if (cancelled) return;
        setData({
          actual: sales.map((s) => ({ date: s.sale_date, qty: s.quantity })),
          forecast: fc.points.map((p) => ({ date: p.date, qty: p.predicted_qty })),
          total: fc.total_predicted,
        });
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [productId]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading...</p>;

  const all = [...data.actual, ...data.forecast];
  const maxY = Math.max(...all.map((d) => d.qty), 1) * 1.15;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i) => PAD.left + (i / Math.max(all.length - 1, 1)) * innerW;
  const y = (v) => PAD.top + innerH - (v / maxY) * innerH;

  const line = (points, offset) =>
    points.map((p, i) => `${i ? "L" : "M"}${x(i + offset).toFixed(1)},${y(p.qty).toFixed(1)}`).join(" ");

  const n = data.actual.length;
  const fcPoints = n ? [data.actual[n - 1], ...data.forecast] : data.forecast;
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(maxY * t));

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Sales and forecast">
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} className="grid-line" />
            <text x={PAD.left - 6} y={y(t) + 4} textAnchor="end" className="axis">{t}</text>
          </g>
        ))}
        {n > 0 && (
          <rect x={x(n - 1)} y={PAD.top} width={W - PAD.right - x(n - 1)} height={innerH} className="future" />
        )}
        <path d={line(data.actual, 0)} className="line-actual" />
        <path d={line(fcPoints, n ? n - 1 : 0)} className="line-forecast" />
        {all.map((d, i) =>
          i % 7 === 0 ? (
            <text key={d.date} x={x(i)} y={H - 8} textAnchor="middle" className="axis">
              {d.date.slice(5)}
            </text>
          ) : null
        )}
      </svg>
      <div className="legend">
        <span><i className="key actual" /> Actual sales</span>
        <span><i className="key forecast" /> Forecast</span>
        <span className="muted">Next 7 days: about {Math.round(data.total)} units</span>
      </div>
    </div>
  );
}
