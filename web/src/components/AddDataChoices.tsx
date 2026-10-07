import { useQueryClient } from '@tanstack/react-query';
import { FileUp, PencilLine, Smartphone, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ME_KEY } from '../api/hooks';
import { errorMessage } from '../api/errors';
import { useAccount, useApi } from '../auth/context';
import { rememberSource } from '../lib/source';
import { ICON } from './icon';

/** The four equal ways to get readings in: import, sample, type them, or stream from the phone app. */
export function AddDataChoices({ headingLevel = 2 }: { headingLevel?: 2 | 3 }) {
  const api = useApi();
  const account = useAccount();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const H = headingLevel === 2 ? 'h2' : 'h3';

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
    <div className="choices">
      <ul className="choice-list">
        <li className="choice">
          <FileUp {...ICON} className="choice-icon" />
          <H className="choice-title">Import from your sensor</H>
          <p>A CSV export from FreeStyle LibreView or Dexcom Clarity, or any file with a time and a glucose column.</p>
          <Link className="button button-primary" to="/add?tab=import">
            Import file
          </Link>
        </li>
        <li className="choice">
          <Sparkles {...ICON} className="choice-icon" />
          <H className="choice-title">Try with sample data</H>
          <p>48 hours of readings from one person, moved so the last one is now. Delete them any time in Settings.</p>
          <button type="button" className="button button-primary" disabled={busy} onClick={() => void loadSample()}>
            {busy ? 'Loading sample data' : 'Load sample data'}
          </button>
        </li>
        <li className="choice">
          <PencilLine {...ICON} className="choice-icon" />
          <H className="choice-title">Enter readings yourself</H>
          <p>Type a value from your meter or sensor app. Forecasts start once there are 2 hours of readings.</p>
          <Link className="button button-primary" to="/add">
            Add reading
          </Link>
        </li>
        <li className="choice">
          <Smartphone {...ICON} className="choice-icon" />
          <H className="choice-title">Live from your phone</H>
          <p>
            Readings stream from Juggluco or xDrip+ on your Android phone, and your watch shows the forecast. Install the GlucoRAG
            phone app, then scan the code from Settings to sign it in. No typing needed.
          </p>
          <Link className="button button-primary" to="/settings#devices">
            Connect a phone
          </Link>
        </li>
      </ul>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
