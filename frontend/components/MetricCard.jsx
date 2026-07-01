export default function MetricCard({ label, value, className = "" }) {
  return (
    <div className={`model-stat ${className}`}>
      <div className="model-stat-label">{label}</div>
      <div className="model-stat-val">{value}</div>
    </div>
  );
}