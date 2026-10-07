import { fmtMeanStd, metricNames, type HorizonMetrics } from '../lib/metrics';

export function MetricsTable({ rows, caption }: { rows: HorizonMetrics; caption: string }) {
  const names = metricNames(rows);
  return (
    <div className="table-wrap">
      <table className="table table-num">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Horizon</th>
            {names.map((n) => (
              <th key={n} scope="col">
                {n}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.horizon}>
              <th scope="row">{/^\d+$/.test(r.horizon) ? `${r.horizon} min` : r.horizon}</th>
              {names.map((n) => (
                <td key={n}>{fmtMeanStd(r.metrics[n])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
