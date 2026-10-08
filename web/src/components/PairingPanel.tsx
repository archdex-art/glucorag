import { RefreshCw, X } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import { formatCountdown, secondsLeft } from '../lib/pairing';
import { Skeleton } from './States';
import { ICON } from './icon';
import type { PhonePairing } from './usePhonePairing';

/** The pairing QR and code with a live countdown; mounted only while open. */
export function PairingPanel({ pairing }: { pairing: PhonePairing }) {
  const headingId = useId();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const code = pairing.pairing;
  const left = code ? secondsLeft(code.expires_at, now) : 0;
  const expired = code !== null && left === 0;

  return (
    <div className="pair-panel" role="region" aria-labelledby={headingId}>
      <div className="pair-top">
        <h3 id={headingId}>Connect a phone</h3>
        <button type="button" className="button button-quiet" onClick={pairing.close}>
          <X {...ICON} />
          Close
        </button>
      </div>
      <p className="pair-steps">Open GlucoRAG on your phone and tap Scan QR code. Or point your phone&apos;s camera at the code.</p>
      {pairing.error ? (
        <p className="form-error" role="alert">
          {pairing.error}
        </p>
      ) : null}
      {code === null && pairing.busy ? <Skeleton label="Making a pairing code" rows={3} variant="block" /> : null}
      {code ? (
        <div className="pair-body">
          {/* The CSP allows data: images, and an <img> never runs script inside an SVG. */}
          <img
            className={expired ? 'pair-qr pair-qr-expired' : 'pair-qr'}
            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(code.qr_svg)}`}
            alt={`QR code for pairing code ${code.code}`}
          />
          <dl className="pair-facts">
            <div>
              <dt>Pairing code</dt>
              <dd className="pair-code">{code.code}</dd>
              <dd className="pair-expiry num">{expired ? 'Expired' : `Expires in ${formatCountdown(left)}`}</dd>
            </div>
            <div>
              <dt>Server address</dt>
              <dd className="pair-server">
                <code>{code.server_url}</code>
              </dd>
              {code.server_url_guessed ? <dd className="pair-note">Your phone must be on the same Wi-Fi as this computer.</dd> : null}
            </div>
          </dl>
        </div>
      ) : null}
      <p role="status" className="pair-status">
        {expired ? 'This code has expired. Make a new one.' : code ? 'Waiting for your phone. This updates when it connects.' : null}
      </p>
      <div>
        <button type="button" className="button" disabled={pairing.busy} onClick={pairing.renew}>
          <RefreshCw {...ICON} />
          {pairing.busy ? 'Making a new code' : 'Make a new code'}
        </button>
      </div>
    </div>
  );
}
