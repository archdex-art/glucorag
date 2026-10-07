import { ZONES } from '../lib/zones';

/** Explains the range strip once per page: zones with thresholds, the marks, and the scale. */
export function ZoneLegend() {
  return (
    <div className="zone-legend">
      <ul className="legend-zones" aria-label="Glucose zones in mg/dL">
        {ZONES.map((z) => (
          <li key={z.key} className={`zone-${z.key}`}>
            <span className="swatch" aria-hidden="true" />
            {z.label} <span className="num legend-range">{z.range}</span>
          </li>
        ))}
      </ul>
      <ul className="legend-marks" aria-label="Strip marks">
        <li>
          <svg className="mark" width="10" height="10" aria-hidden="true">
            <circle className="strip-dot" cx="5" cy="5" r="4" />
          </svg>
          Now
        </li>
        <li>
          <svg className="mark" width="18" height="10" aria-hidden="true">
            <rect className="strip-band" x="0" y="0" width="18" height="10" rx="2" />
          </svg>
          Next hour
        </li>
        <li>
          <svg className="mark" width="4" height="12" aria-hidden="true">
            <rect className="strip-ink" x="1" y="0" width="2" height="12" />
          </svg>
          60-min median
        </li>
        <li className="legend-scale">Log scale</li>
      </ul>
    </div>
  );
}
