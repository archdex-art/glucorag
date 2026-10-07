import { Link } from 'react-router-dom';
import { useAccount } from '../auth/context';
import { PageHeader } from '../components/PageHeader';
import { homePath } from '../lib/access';

export function NotFoundPage() {
  const account = useAccount();
  const staff = account.role === 'clinician';
  return (
    <>
      <PageHeader title="Page not found" />
      <div className="sheet sheet-pad prose-block">
        <p>
          There is no page at this address. Go back to{' '}
          <Link to={homePath({ role: account.role, hasProfile: account.has_profile })}>{staff ? 'the ward' : 'Today'}</Link>.
        </p>
      </div>
    </>
  );
}
