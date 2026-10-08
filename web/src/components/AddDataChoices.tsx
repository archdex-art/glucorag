import { useQueryClient } from '@tanstack/react-query';
import { FileUp, PencilLine, QrCode, Smartphone, Sparkles } from 'lucide-react';
import { useId, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ME_KEY } from '../api/hooks';
import { errorMessage } from '../api/errors';
import { useAccount, useApi } from '../auth/context';
import { rememberSource } from '../lib/source';
import { PairingPanel } from './PairingPanel';
import { ICON } from './icon';
import { usePhonePairing } from './usePhonePairing';

type Level = 2 | 3;

/**
 * The recommended way in: readings stream from the phone app. "Connect a phone" opens the
 * pairing panel right here, so set-up never sends anyone off to Settings.
 */
export function PhoneChoice({ headingLevel = 2 }: { headingLevel?: Level }) {
  const pair = usePhonePairing();
  const { pathname, search } = useLocation();
  const headingId = useId();
  const H = headingLevel === 2 ? 'h2' : 'h3';

  return (
    <section className="choice-featured" aria-labelledby={headingId}>
      <div className="choice-featured-head">
        <Smartphone {...ICON} className="choice-icon" />
        <H id={headingId} className="choice-title">
          Live from your phone
        </H>
        <span className="chip chip-recommended">Recommended</span>
      </div>
      <p>
        Readings arrive by themselves from Juggluco or xDrip+ on your Android phone, and your watch can show the forecast. Get
        the GlucoRAG phone app, then connect it by scanning a code. No typing needed.
      </p>
      {pair.open ? (
        <PairingPanel pairing={pair} />
      ) : (
        <div className="choice-actions">
          <Link className="button button-primary" to="/help/phone" state={{ from: `${pathname}${search}` }}>
            <Smartphone {...ICON} />
            Get the phone app
          </Link>
          <button type="button" className="button" disabled={!pair.devices.data} onClick={pair.start}>
            <QrCode {...ICON} />
            Connect a phone
          </button>
        </div>
      )}
      {pair.connected ? (
        <p role="status" className="choice-connected">
          {pair.connected} New readings show on <Link to="/">Today</Link> as they arrive.
        </p>
      ) : null}
    </section>
  );
}

/** Loads the bundled 48-hour trace, then opens Today. Only for an account without readings. */
export function SampleDataButton({ className = 'button' }: { className?: string }) {
  const api = useApi();
  const account = useAccount();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadSample() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.loadSample();
      rememberSource(account.email, 'sample', result.last);
      await queryClient.invalidateQueries({ queryKey: [ME_KEY] });
      navigate('/');
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <>
      <button type="button" className={className} disabled={busy} onClick={() => void loadSample()}>
        <Sparkles {...ICON} />
        {busy ? 'Loading sample data' : 'Try sample data'}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </>
  );
}

/** Set-up step 2 and an empty Today: the phone first, the other three ways below it. */
export function AddDataChoices({ headingLevel = 2 }: { headingLevel?: Level }) {
  const moreId = useId();
  const H = headingLevel === 2 ? 'h2' : 'h3';
  return (
    <div className="choices">
      <PhoneChoice headingLevel={headingLevel} />
      <section className="choice-more" aria-labelledby={moreId}>
        <H id={moreId} className="choice-more-title">
          Or start another way
        </H>
        <ul className="choice-secondary">
          <li>
            <Link className="button" to="/add?tab=import">
              <FileUp {...ICON} />
              Import a file
            </Link>
            <p>A LibreView or Dexcom Clarity export, or any file with a time and a glucose column.</p>
          </li>
          <li>
            <Link className="button" to="/add">
              <PencilLine {...ICON} />
              Type a reading
            </Link>
            <p>From your meter or sensor app. Forecasts start after 2 hours of readings.</p>
          </li>
          <li>
            <SampleDataButton />
            <p>48 hours from one person, ending now. Delete them any time in Settings.</p>
          </li>
        </ul>
      </section>
    </div>
  );
}
