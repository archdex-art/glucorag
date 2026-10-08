import { ArrowLeft, Download, ExternalLink } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useDownloads } from '../api/hooks';
import { useAuth } from '../auth/context';
import { AuthFrame } from '../components/AuthFrame';
import { ErrorState, Skeleton } from '../components/States';
import { ICON } from '../components/icon';

const PLATFORM_TOOLS_URL = 'https://developer.android.com/tools/releases/platform-tools';

/** Where "Back" goes: the page that linked here (it passes `state.from`), else home. */
function useBackPath(): string {
  const { state } = useLocation();
  const { account } = useAuth();
  const from = state && typeof state === 'object' && 'from' in state && typeof state.from === 'string' ? state.from : null;
  return from ?? (account ? '/' : '/welcome');
}

/** Open to anyone: set-up, Settings and signed-out visitors all land here. */
function HelpFrame({ children }: { children: ReactNode }) {
  const back = useBackPath();
  return (
    <AuthFrame
      wide
      aside={
        <Link className="button button-quiet" to={back}>
          <ArrowLeft {...ICON} />
          Back
        </Link>
      }
    >
      {children}
    </AuthFrame>
  );
}

function ReleasesLink({ url, children }: { url: string; children: ReactNode }) {
  return (
    <a href={url} target="_blank" rel="noreferrer">
      {children}
      <ExternalLink {...ICON} className="link-icon" />
      <span className="visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

/** `/help/phone`: download the Android app from this server, or from the project's releases. */
export function PhoneHelpPage() {
  const downloads = useDownloads();
  const back = useBackPath();
  const d = downloads.data;

  return (
    <HelpFrame>
      <h1>Get the phone app</h1>
      <p className="auth-lede">
        The GlucoRAG app runs on Android phones. It picks up your readings from Juggluco or xDrip+ and sends them here, so your
        forecast keeps itself up to date.
      </p>
      {downloads.isPending ? <Skeleton label="Looking for the app" rows={4} /> : null}
      {downloads.isError ? (
        <ErrorState error={downloads.error} title="Could not check where to get the app." onRetry={() => void downloads.refetch()} />
      ) : null}
      {d ? (
        <ol className="help-steps">
          {d.phone_apk ? (
            <li>
              <p>
                <strong>Download the app on your phone.</strong> If you are reading this on a computer, open this page in your
                phone&apos;s browser instead.
              </p>
              <p className="help-actions">
                <a className="button button-primary" href={d.phone_apk} download>
                  <Download {...ICON} />
                  Download the phone app
                </a>
              </p>
            </li>
          ) : (
            <li>
              <p>
                <strong>Download the app on your phone</strong> from the <ReleasesLink url={d.releases_url}>GlucoRAG releases page</ReleasesLink>.
                Under the newest release, tap the file whose name ends in <code>phone.apk</code>.
              </p>
            </li>
          )}
          <li>
            <p>
              <strong>Allow installing from your browser.</strong> Android may say it can&apos;t install apps from this source.
              Tap Settings, turn on Allow from this source, then go back.
            </p>
          </li>
          <li>
            <p>
              <strong>Open the downloaded file and tap Install.</strong> You find it in your browser&apos;s downloads or in the
              Files app.
            </p>
          </li>
          <li>
            <p>
              <strong>Connect the phone.</strong> Open GlucoRAG on the phone and tap Scan QR code. On this site, choose Connect a
              phone and point the phone at the code.
            </p>
            <p className="help-actions">
              <Link className="button" to={back}>
                Back to Connect a phone
              </Link>
            </p>
          </li>
        </ol>
      ) : null}
      <p className="help-note">
        Keep Juggluco or xDrip+ running on the same phone: GlucoRAG reads your sensor through it. Have a Galaxy Watch or another
        Wear OS watch? <Link to="/help/watch" state={{ from: back }}>Install the watch app</Link> too.
      </p>
    </HelpFrame>
  );
}

/** `/help/watch`: side-load the Wear OS app from a computer over Wi-Fi. */
export function WatchHelpPage() {
  const downloads = useDownloads();
  const back = useBackPath();
  const d = downloads.data;

  return (
    <HelpFrame>
      <h1>Install the watch app</h1>
      <p className="auth-lede">
        The watch app shows your forecast on a Galaxy Watch or another Wear OS watch. Watches can&apos;t install an app from a
        file by themselves, so you send it from a computer over Wi-Fi. It takes about 10 minutes, and you only do it once.
      </p>
      <p className="help-note">
        Before you start: <Link to="/help/phone" state={{ from: back }}>get the phone app</Link> and connect it, and have the
        watch and the computer on the same Wi-Fi.
      </p>
      {downloads.isPending ? <Skeleton label="Looking for the app" rows={4} /> : null}
      {downloads.isError ? (
        <ErrorState error={downloads.error} title="Could not check where to get the app." onRetry={() => void downloads.refetch()} />
      ) : null}
      {d ? (
        <ol className="help-steps">
          <li>
            {d.watch_apk ? (
              <>
                <p>
                  <strong>Download the watch app to your computer.</strong> Remember where it is saved.
                </p>
                <p className="help-actions">
                  <a className="button button-primary" href={d.watch_apk} download>
                    <Download {...ICON} />
                    Download the watch app
                  </a>
                </p>
              </>
            ) : (
              <p>
                <strong>Download the watch app to your computer</strong> from the{' '}
                <ReleasesLink url={d.releases_url}>GlucoRAG releases page</ReleasesLink>: under the newest release, the file whose
                name ends in <code>watch.apk</code>. Remember where it is saved.
              </p>
            )}
          </li>
          <li>
            <p>
              <strong>Turn on Developer options on the watch.</strong> Open Settings, then About watch, then Software. Tap
              Software version 5 times, until the watch says developer mode is on.
            </p>
          </li>
          <li>
            <p>
              <strong>Let the computer reach the watch.</strong> In Settings, open Developer options and turn on ADB debugging
              and Debug over Wi-Fi. The watch then shows an address such as <code>192.168.1.23:5555</code>. Keep it on screen.
            </p>
          </li>
          <li>
            <p>
              <strong>Get Android&apos;s install tool on the computer.</strong> Download{' '}
              <ReleasesLink url={PLATFORM_TOOLS_URL}>SDK Platform-Tools</ReleasesLink> for your computer and unzip it. It is a
              free tool from Google.
            </p>
          </li>
          <li>
            <p>
              <strong>Connect to the watch.</strong> Open a terminal in the unzipped <code>platform-tools</code> folder (Terminal
              on a Mac, Command Prompt on Windows) and type the address from the watch:
            </p>
            <pre className="help-command">
              <code>adb connect 192.168.1.23:5555</code>
            </pre>
            <p>When the watch asks whether to allow debugging, tap Allow.</p>
          </li>
          <li>
            <p>
              <strong>Install the app.</strong> Type the command below, with the path to the file you downloaded. You can drag
              the file into the terminal window instead of typing its path.
            </p>
            <pre className="help-command">
              <code>adb install watch.apk</code>
            </pre>
            <p>The terminal says Success when it is done.</p>
          </li>
          <li>
            <p>
              <strong>Open GlucoRAG on the watch.</strong> It shows the forecast your phone receives. You can turn ADB debugging
              off again in Developer options.
            </p>
          </li>
        </ol>
      ) : null}
      <p className="help-note">
        Watch shows Wireless debugging with a pairing code instead? Tap Pair new device, then type{' '}
        <code>adb pair</code> followed by the address and port the watch shows, enter the code, and continue with the connect step.
      </p>
    </HelpFrame>
  );
}
