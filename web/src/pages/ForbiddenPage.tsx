import { Link } from 'react-router-dom';
import { useAccount } from '../auth/context';
import { PageHeader } from '../components/PageHeader';
import { homePath } from '../lib/access';

/** A person reached a staff page (the API would answer 403). */
export function ForbiddenPage() {
  const account = useAccount();
  return (
    <>
      <PageHeader title="This page is for clinical staff" />
      <div className="sheet sheet-pad prose-block">
        <p>
          Your account shows your own readings and forecasts. The ward, alerts, model and system pages need a clinician
          account.
        </p>
        <p>
          <Link className="button button-primary" to={homePath({ role: account.role, hasProfile: account.has_profile })}>
            Go to Today
          </Link>
        </p>
      </div>
    </>
  );
}
