type HealthCardProps = {
  apiUrl: string;
  detail: string;
  status: "ok" | "degraded" | "unreachable";
};

export function HealthCard({ apiUrl, detail, status }: HealthCardProps) {
  return (
    <section className="panel health-card">
      <div className="section-heading">
        <p className="eyebrow">Stack Status</p>
        <span className={`status-badge status-${status}`}>{status}</span>
      </div>
      <p className="panel-copy">{detail}</p>
      <a className="health-link" href={`${apiUrl}/health`} target="_blank" rel="noreferrer">
        Open API health endpoint
      </a>
    </section>
  );
}
