import { CircleCheck, CircleX } from 'lucide-react';
import type { ReactNode } from 'react';
import { useModel, useModelAccuracy } from '../api/hooks';
import type { ModelInfo } from '../api/types';
import { Facts } from '../components/Facts';
import { LiveAccuracy } from '../components/LiveAccuracy';
import { MetricsTable } from '../components/MetricsTable';
import { PageHeader } from '../components/PageHeader';
import { ErrorState, Skeleton } from '../components/States';
import { TimeInRanges } from '../components/TimeInRanges';
import { ICON } from '../components/icon';
import { useRefresh } from '../components/refresh';
import { asNumber, fmtNumber, fmtPValue, fmtQuantile, humanize, isRecord } from '../lib/format';
import { asHorizonMetrics, asMeanStd, fmtMeanStd, type MeanStd } from '../lib/metrics';
import { PAPER_CV_RMSE, PAPER_DATASET, PAPER_RMSE, PAPER_SOURCE, type PaperValue } from '../lib/paper';
import { roundToHundred } from '../lib/tir';
import { formatApiTime } from '../lib/time';

type Rec = Record<string, unknown>;

/** Significance entries per horizon (minutes), sorted. */
function significance(m: ModelInfo): [string, Rec][] {
  const sig = m.evaluation && isRecord(m.evaluation.significance) ? m.evaluation.significance : {};
  return Object.entries(sig)
    .filter((e): e is [string, Rec] => isRecord(e[1]))
    .sort((a, b) => Number(a[0]) - Number(b[0]));
}

const pText = (p: number | null) => (p === null ? 'p not reported' : p < 0.01 ? 'p < 0.01' : `p = ${p.toFixed(2)}`);

function joinAnd(parts: string[]): string {
  if (parts.length < 2) return parts.join('');
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

function verdictReason(m: ModelInfo): string {
  const last = m.release.last_promotion;
  if (m.release.promoted) {
    const when = last && typeof last.promoted_at === 'string' ? ` on ${formatApiTime(last.promoted_at)}` : '';
    return `It passed the release gates${when} and is the version the service serves.`;
  }
  const failing = significance(m).filter(([, s]) => s.significant === false);
  if (failing.length) {
    const comparators = [...new Set(failing.map(([, s]) => String(s.comparator ?? 'the baseline')))];
    const parts = failing.map(([h, s]) => `${/^\d+$/.test(h) ? `${h} min` : h} (${pText(asNumber(s.t_p))})`);
    return `Not significantly better than ${joinAnd(comparators)} at ${joinAnd(parts)}.`;
  }
  const gates = last && Array.isArray(last.gates) ? last.gates.filter(isRecord) : [];
  const failed = gates.filter((g) => !g.passed && !g.waived).map((g) => String(g.gate));
  if (failed.length) return `It failed the ${joinAnd(failed)} release ${failed.length > 1 ? 'gates' : 'gate'}.`;
  return 'No promotion record exists for this version.';
}

function Verdict({ m }: { m: ModelInfo }) {
  const promoted = m.release.promoted;
  const Icon = promoted ? CircleCheck : CircleX;
  return (
    <section className="sheet-section verdict" aria-labelledby="verdict-heading">
      <h2 id="verdict-heading" className={promoted ? 'zt-target' : 'zt-very_low'}>
        <Icon {...ICON} size={20} />
        {m.version} is {promoted ? 'promoted' : 'not promoted'}
      </h2>
      <p className="verdict-reason">{verdictReason(m)}</p>
      <p className="caption num">
        EPS-TFT quantile forecaster trained on the {m.dataset === PAPER_DATASET ? 'ShanghaiDM' : m.dataset} dataset, created{' '}
        {formatApiTime(m.created_at)}. The service registry points to{' '}
        {m.release.current_version ? m.release.current_version : 'no promoted version'}.
      </p>
    </section>
  );
}

/** Lower RMSE is better: signed difference plus the word. */
function Difference({ ours, paper }: { ours: MeanStd | null; paper: PaperValue }) {
  if (!ours) return <>—</>;
  const d = ours.mean - paper.mean;
  const word = Math.abs(d) < 0.05 ? 'same' : d < 0 ? 'better' : 'worse';
  return (
    <>
      {d > 0 ? '+' : d < 0 ? '−' : ''}
      {fmtNumber(Math.abs(d), 1)} <span className={`verdict-word ${word}`}>{word}</span>
    </>
  );
}

const paperText = (p: PaperValue) => (p.std === null ? fmtNumber(p.mean, 1) : `${fmtNumber(p.mean, 1)} ± ${fmtNumber(p.std, 1)}`);

function Accuracy({ m }: { m: ModelInfo }) {
  const summary = m.evaluation ? asHorizonMetrics(m.evaluation.summary) : null;
  const cv = m.cross_individual_cv;
  const pooled = cv ? asHorizonMetrics(cv.pooled) : null;
  const foldMeans = cv && isRecord(cv.mean_of_fold_means) ? cv.mean_of_fold_means : {};
  const test = (h: string) => summary?.find((r) => r.horizon === h)?.metrics.RMSE ?? null;
  const crossVal = (h: string) => pooled?.find((r) => r.horizon === h)?.metrics.RMSE ?? asMeanStd(foldMeans[h]);
  const withPaper = m.dataset === PAPER_DATASET;
  const rows: [string, MeanStd | null, PaperValue][] = [
    ['30-min RMSE', test('30'), PAPER_RMSE[30]],
    ['60-min RMSE', test('60'), PAPER_RMSE[60]],
    ['Cross-validation, 30 min', crossVal('30'), PAPER_CV_RMSE[30]],
    ['Cross-validation, 60 min', crossVal('60'), PAPER_CV_RMSE[60]],
  ];
  return (
    <section className="sheet-section" aria-labelledby="accuracy-heading">
      <h2 id="accuracy-heading">{withPaper ? 'Accuracy against the paper' : 'Accuracy'}</h2>
      <div className="table-wrap">
        <table className="table table-num">
          <caption>
            RMSE in mg/dL, mean ± SD across patients. Lower is better.
            {withPaper ? ` Paper: ${PAPER_SOURCE}, Table II and cross-validation.` : ''}
          </caption>
          <thead>
            <tr>
              <th scope="col">Measure</th>
              <th scope="col">This model</th>
              {withPaper ? (
                <>
                  <th scope="col">Paper</th>
                  <th scope="col">Difference</th>
                </>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, ours, paper]) => (
              <tr key={label}>
                <th scope="row">{label}</th>
                <td>{fmtMeanStd(ours ?? undefined)}</td>
                {withPaper ? (
                  <>
                    <td>{paperText(paper)}</td>
                    <td>
                      <Difference ours={ours} paper={paper} />
                    </td>
                  </>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const ARM_LABEL: Record<string, string> = { open_loop: 'Open loop', plgm: 'Predictive suspend (PLGM)' };

const cvga = (arm: unknown, zone: string) => (isRecord(arm) && isRecord(arm.cvga) ? asNumber(arm.cvga[zone]) : null);

function Change({ from, to, lowerIsBetter }: { from: number | null; to: number | null; lowerIsBetter: boolean }) {
  if (from === null || to === null) return <>—</>;
  const d = to - from;
  const better = lowerIsBetter ? d < 0 : d > 0;
  const word = Math.abs(d) < 0.05 ? 'same' : better ? 'better' : 'worse';
  return (
    <>
      {d > 0 ? '+' : d < 0 ? '−' : ''}
      {fmtNumber(Math.abs(d), 1)} points, <span className={`verdict-word ${word}`}>{word}</span>
    </>
  );
}

function InSilico({ m }: { m: ModelInfo }) {
  const sim = m.in_silico;
  const agg = sim && isRecord(sim.aggregate) ? sim.aggregate : null;
  if (!sim || !agg) {
    return (
      <section className="sheet-section" aria-labelledby="sim-heading">
        <h2 id="sim-heading">In-silico trial</h2>
        <p className="muted">No trial report for this model version.</p>
      </section>
    );
  }
  const paper = isRecord(sim.paper) ? sim.paper : {};
  const arms = ['open_loop', 'plgm'].filter((a) => isRecord(agg[a]));
  const paperArm = (a: string): Rec => (isRecord(paper[a]) ? paper[a] : {});
  const paperReduction = asNumber(paper.d_plus_e_reduction_pct_points);
  const ab = { ol: cvga(agg.open_loop, 'A+B'), pl: cvga(agg.plgm, 'A+B') };
  const de = { ol: cvga(agg.open_loop, 'D+E'), pl: cvga(agg.plgm, 'D+E') };
  const paperAb = { ol: asNumber(paperArm('open_loop')['A+B']), pl: asNumber(paperArm('plgm')['A+B']) };

  return (
    <section className="sheet-section" aria-labelledby="sim-heading">
      <h2 id="sim-heading">In-silico trial</h2>
      <div className="sim-bars">
        {arms.map((a) => {
          const arm = agg[a] as Rec;
          const [low = 0, target = 0, high = 0] = roundToHundred([
            asNumber(arm.tbr_pct) ?? 0,
            asNumber(arm.tir_pct) ?? 0,
            asNumber(arm.tar_pct) ?? 0,
          ]);
          const p = paperArm(a);
          const pTir = asNumber(p.tir_pct);
          const pTbr = asNumber(p.tbr_pct);
          return (
            <div key={a} className="sim-arm">
              <h3>{ARM_LABEL[a] ?? humanize(a)}</h3>
              <TimeInRanges
                title={`${ARM_LABEL[a] ?? humanize(a)}, time in ranges`}
                segments={[
                  { zone: 'low', label: 'Low', range: 'under 70', pct: low },
                  { zone: 'target', label: 'Target', range: '70–180', pct: target },
                  { zone: 'high', label: 'High', range: 'over 180', pct: high },
                ]}
                caption={
                  pTir !== null && pTbr !== null ? (
                    <>
                      Paper: {fmtNumber(pTir, 1)}% in range, {fmtNumber(pTbr, 1)}% low.
                    </>
                  ) : undefined
                }
              />
            </div>
          );
        })}
      </div>
      <p className="caption">
        The trial reports three ranges only: low covers everything under 70 mg/dL and high everything over 180.
      </p>
      <div className="table-wrap">
        <table className="table table-num">
          <caption>Control-variability grid (CVGA), percent of patient-days, open loop to predictive suspend.</caption>
          <thead>
            <tr>
              <th scope="col">Zones</th>
              <th scope="col">Open loop</th>
              <th scope="col">PLGM</th>
              <th scope="col">Change</th>
              <th scope="col">Paper change</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th scope="row">
                A+B <span className="muted">higher is better</span>
              </th>
              <td>{fmtNumber(ab.ol, 1)}</td>
              <td>{fmtNumber(ab.pl, 1)}</td>
              <td>
                <Change from={ab.ol} to={ab.pl} lowerIsBetter={false} />
              </td>
              <td>
                <Change from={paperAb.ol} to={paperAb.pl} lowerIsBetter={false} />
              </td>
            </tr>
            <tr>
              <th scope="row">
                D+E <span className="muted">lower is better</span>
              </th>
              <td>{fmtNumber(de.ol, 1)}</td>
              <td>{fmtNumber(de.pl, 1)}</td>
              <td>
                <Change from={de.ol} to={de.pl} lowerIsBetter />
              </td>
              <td>
                {paperReduction !== null ? <Change from={paperReduction} to={0} lowerIsBetter /> : '—'}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Detail({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="sheet-section disclosure-section">
      <summary>{title}</summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}

function SignificanceTable({ rows }: { rows: [string, Rec][] }) {
  return (
    <div className="table-wrap">
      <table className="table table-num">
        <caption>
          Paired per-patient RMSE comparison. The release rule needs normal differences and a paired t-test p below α.
        </caption>
        <thead>
          <tr>
            <th scope="col">Horizon</th>
            <th scope="col">Comparison</th>
            <th scope="col">Patients</th>
            <th scope="col">Mean difference</th>
            <th scope="col">Shapiro p</th>
            <th scope="col">t-test p</th>
            <th scope="col">Wilcoxon p</th>
            <th scope="col">α</th>
            <th scope="col">Result</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([h, s]) => (
            <tr key={h}>
              <th scope="row">{/^\d+$/.test(h) ? `${h} min` : h}</th>
              <td>
                {String(s.reference ?? 'model')} against {String(s.comparator ?? 'baseline')}
              </td>
              <td>{String(s.n ?? '—')}</td>
              <td>{fmtNumber(asNumber(s.mean_difference), 3)}</td>
              <td>
                {fmtPValue(asNumber(s.shapiro_p))}
                {typeof s.differences_normal === 'boolean' ? (
                  <span className="muted"> {s.differences_normal ? 'normal' : 'not normal'}</span>
                ) : null}
              </td>
              <td>{fmtPValue(asNumber(s.t_p))}</td>
              <td>{fmtPValue(asNumber(s.wilcoxon_p))}</td>
              <td>{String(s.alpha ?? '—')}</td>
              <td>{s.significant === true ? 'Significant' : s.significant === false ? 'Not significant' : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function scalar(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(5)));
  if (Array.isArray(v)) return v.map(scalar).join(', ');
  if (isRecord(v)) return Object.entries(v).map(([k, x]) => `${k} ${scalar(x)}`).join(', ');
  return String(v);
}

function Details({ m }: { m: ModelInfo }) {
  const ev = m.evaluation;
  const summary = ev ? asHorizonMetrics(ev.summary) : null;
  const sig = significance(m);
  const cv = m.cross_individual_cv;
  const pooled = cv ? asHorizonMetrics(cv.pooled) : null;
  const foldMeans = cv && isRecord(cv.mean_of_fold_means) ? Object.entries(cv.mean_of_fold_means) : [];
  const agg = m.in_silico && isRecord(m.in_silico.aggregate) ? m.in_silico.aggregate : null;
  const arms = agg ? Object.keys(agg).filter((k) => isRecord(agg[k])) : [];
  const zones = arms[0] && agg && isRecord(agg[arms[0]]) ? (agg[arms[0]] as Rec).cvga : null;
  const gates = m.release.last_promotion && Array.isArray(m.release.last_promotion.gates)
    ? m.release.last_promotion.gates.filter(isRecord)
    : [];

  return (
    <>
      <Detail title="Test metrics">
        {summary ? (
          <MetricsTable rows={summary} caption="Test split, per-patient mean ± SD. MAE, RMSE and gRMSE in mg/dL; MAPE in %." />
        ) : (
          <p className="muted">No test-set evaluation recorded.</p>
        )}
        {ev ? (
          <Facts
            items={[
              ['Evaluated', formatApiTime(typeof ev.evaluated_at === 'string' ? ev.evaluated_at : null)],
              ['Report', typeof ev.report === 'string' ? <code>{ev.report}</code> : '—'],
            ]}
          />
        ) : null}
      </Detail>
      <Detail title="Significance details">
        {sig.length ? <SignificanceTable rows={sig} /> : <p className="muted">No significance test recorded.</p>}
      </Detail>
      <Detail title="Cross-validation detail">
        {cv ? (
          <>
            <Facts
              items={[
                ['Folds', scalar(cv.n_folds)],
                ['Seed', scalar(cv.seed)],
                ...foldMeans.map(([h, v]): [string, ReactNode] => [`Mean of fold RMSE, ${h} min`, fmtNumber(asNumber(v), 2)]),
                ...(isRecord(cv.train_config) ? [['Fold training', scalar(cv.train_config)] as [string, ReactNode]] : []),
              ]}
            />
            {pooled ? <MetricsTable rows={pooled} caption="Pooled held-out patients, mean ± SD." /> : null}
          </>
        ) : (
          <p className="muted">No cross-validation recorded.</p>
        )}
      </Detail>
      <Detail title="CVGA zones">
        {isRecord(zones) && agg ? (
          <div className="table-wrap">
            <table className="table table-num">
              <caption>Control-variability grid zones, percent of patient-days.</caption>
              <thead>
                <tr>
                  <th scope="col">Zone</th>
                  {arms.map((a) => (
                    <th key={a} scope="col">
                      {ARM_LABEL[a] ?? humanize(a)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {Object.keys(zones).map((z) => (
                  <tr key={z}>
                    <th scope="row">{z}</th>
                    {arms.map((a) => (
                      <td key={a}>{fmtNumber(cvga(agg[a], z), 1)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">No trial report for this model version.</p>
        )}
      </Detail>
      <Detail title="Hyperparameters">
        <Facts
          items={[
            ['Sampling interval', `${m.interval_min} min`],
            ['Look-back', `${m.lookback_min} min`],
            ['Forecast horizon', `${m.horizon_min} min`],
            ['Quantiles', m.quantiles.map(fmtQuantile).join(', ')],
            ['Static features', m.static_features.length ? m.static_features.map(humanize).join(', ') : 'None'],
            ...Object.entries(m.hyperparameters).map(([k, v]): [string, ReactNode] => [humanize(k), scalar(v)]),
          ]}
        />
      </Detail>
      <Detail title="Integrity">
        <Facts
          items={[
            ['Weights SHA-256', <code className="hash">{m.weights_sha256}</code>],
            ['Training data hash', <code className="hash">{m.data_hash}</code>],
          ]}
        />
        {gates.length ? (
          <div className="table-wrap">
            <table className="table">
              <caption>Release gates at the last promotion attempt.</caption>
              <thead>
                <tr>
                  <th scope="col">Gate</th>
                  <th scope="col">Result</th>
                  <th scope="col">Detail</th>
                </tr>
              </thead>
              <tbody>
                {gates.map((g) => (
                  <tr key={String(g.gate)}>
                    <th scope="row">{String(g.gate)}</th>
                    <td>{g.passed ? 'Passed' : g.waived ? `Waived: ${String(g.waived)}` : 'Failed'}</td>
                    <td>{String(g.detail ?? '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Detail>
    </>
  );
}

export function ModelPage() {
  const { paused } = useRefresh();
  const model = useModel();
  const accuracy = useModelAccuracy(paused);
  return (
    <>
      <PageHeader title="Model" refresh={{ updatedAt: accuracy.dataUpdatedAt }} />
      <div className="sheet">
        {model.isPending ? <Skeleton label="Loading the model card" variant="block" rows={3} /> : null}
        {model.isError ? (
          <div className="sheet-pad">
            <ErrorState error={model.error} title="The model card could not be loaded." onRetry={() => void model.refetch()} />
          </div>
        ) : null}
        {model.data ? (
          <>
            <Verdict m={model.data} />
            <Accuracy m={model.data} />
          </>
        ) : null}
        <LiveAccuracy query={accuracy} />
        {model.data ? (
          <>
            <InSilico m={model.data} />
            <Details m={model.data} />
          </>
        ) : null}
      </div>
    </>
  );
}
