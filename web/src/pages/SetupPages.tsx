import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/errors';
import { ME_KEY } from '../api/hooks';
import { useAccount, useApi, useAuth } from '../auth/context';
import { AddDataChoices } from '../components/AddDataChoices';
import { AuthFrame } from '../components/AuthFrame';
import { ProfileForm, type ProfileValues } from '../components/ProfileForm';

function SignOutLink() {
  const { signOut } = useAuth();
  return (
    <button type="button" className="button button-quiet" onClick={() => void signOut()}>
      Sign out
    </button>
  );
}

/** Set-up 1: the four facts the model reads, and the unit. */
export function SetupProfilePage() {
  const api = useApi();
  const account = useAccount();
  const { refresh } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  async function save(values: ProfileValues) {
    setError(null);
    try {
      await api.saveProfile({ ...values, sensitivity: 'standard' });
      await queryClient.invalidateQueries({ queryKey: [ME_KEY] });
      await refresh();
      navigate('/setup/data');
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <AuthFrame wide aside={<SignOutLink />}>
      <h1>About you</h1>
      <p className="auth-lede">
        Step 1 of 2. The forecast reads these four facts together with your readings. They stay in your account.
      </p>
      <ProfileForm
        initial={null}
        unit={account.unit}
        withUnits
        submitLabel="Continue"
        busyLabel="Saving"
        onSubmit={save}
        error={error}
      />
    </AuthFrame>
  );
}

/** Set-up 2: the phone app first, then the other ways to get readings in. */
export function SetupDataPage() {
  return (
    <AuthFrame wide aside={<SignOutLink />}>
      <h1>Add your data</h1>
      <p className="auth-lede">Step 2 of 2. Get your first readings in. You can add the other ways later.</p>
      <AddDataChoices />
      <p className="setup-skip">
        <Link to="/">Skip for now</Link>
      </p>
    </AuthFrame>
  );
}
