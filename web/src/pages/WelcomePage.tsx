import { Link } from 'react-router-dom';
import { useAuth } from '../auth/context';
import { ResearchNotice, Wordmark } from '../components/Brand';

/**
 * An illustration of what Today draws: readings up to now, then the forecast fan widening over
 * the next hour across the glucose zones. y = 300 − mg/dL, so the zone edges sit at 50, 120,
 * 230 and 246.
 */
function FanIllustration() {
  return (
    <svg
      className="fan-art"
      viewBox="0 0 480 260"
      role="img"
      aria-label="Example: a line of readings up to now, then a shaded forecast range that widens over the next hour."
      preserveAspectRatio="none"
    >
      <rect className="art-very-high" x="0" y="0" width="480" height="50" />
      <rect className="art-high" x="0" y="50" width="480" height="70" />
      <rect className="art-target" x="0" y="120" width="480" height="110" />
      <rect className="art-low" x="0" y="230" width="480" height="16" />
      <rect className="art-very-low" x="0" y="246" width="480" height="14" />
      <line className="art-rule-high" x1="0" x2="480" y1="120" y2="120" />
      <line className="art-rule-low" x1="0" x2="480" y1="230" y2="230" />
      <path className="art-outer" d="M340 176 L383 164 L427 155 L470 148 L470 228 L427 215 L383 196 Z" />
      <path className="art-mid" d="M340 176 L383 170 L427 167 L470 164 L470 212 L427 203 L383 190 Z" />
      <path className="art-inner" d="M340 176 L383 175 L427 176 L470 176 L470 200 L427 194 L383 185 Z" />
      <path className="art-median" d="M340 176 L383 180 L427 185 L470 188" />
      <polyline
        className="art-reading"
        points="0,150 31,142 62,135 93,130 124,132 155,140 185,148 216,153 247,160 278,165 309,172 340,176"
      />
      <line className="art-now" x1="340" x2="340" y1="14" y2="260" />
      <circle className="art-dot" cx="340" cy="176" r="4.5" />
    </svg>
  );
}

export function WelcomePage() {
  const { notice } = useAuth();
  return (
    <div className="auth-page welcome">
      <header className="auth-top">
        <Wordmark />
        <p className="auth-switch">
          Have an account? <Link to="/signin">Sign in</Link>
        </p>
      </header>
      <main id="main" className="welcome-main">
        {notice ? (
          <p className="form-notice welcome-notice" role="status">
            {notice}
          </p>
        ) : null}
        <section className="welcome-hero" aria-labelledby="welcome-title">
          <div className="welcome-copy">
            <h1 id="welcome-title">Where will your glucose be in an hour?</h1>
            <p className="welcome-lede">
              GlucoRAG reads the last two hours of your CGM readings and forecasts the next hour as a shaded range, drawn the way
              an AGP report draws it. If a low or a high looks likely, it tells you when, and how low or high you could go.
            </p>
            <div className="welcome-actions">
              <Link className="button button-primary button-large" to="/signup">
                Create account
              </Link>
              <Link className="button button-large" to="/signin">
                Sign in
              </Link>
            </div>
            <ResearchNotice className="notice-block" />
          </div>
          <figure className="welcome-figure">
            <FanIllustration />
            <figcaption className="welcome-figure-caption" aria-hidden="true">
              <span>Readings so far</span>
              <span>Now, and the next hour</span>
            </figcaption>
          </figure>
        </section>

        <section className="welcome-steps" aria-labelledby="steps-title">
          <h2 id="steps-title">How it works</h2>
          <ol>
            <li>
              <h3>Tell it about yourself</h3>
              <p>Diabetes type, age, sex and BMI: the four facts the model uses next to your readings.</p>
            </li>
            <li>
              <h3>Add your readings</h3>
              <p>
                Stream them live from the GlucoRAG phone app, import a FreeStyle LibreView or Dexcom Clarity export, type a reading,
                or try a 48-hour sample.
              </p>
            </li>
            <li>
              <h3>See your next hour</h3>
              <p>Your value now, which way it is heading, and the range you will most likely be in over the next hour.</p>
            </li>
          </ol>
        </section>

        <section className="welcome-who" aria-labelledby="who-title">
          <h2 id="who-title">Who it is for</h2>
          <p>
            Adults with type 1 or type 2 diabetes who wear a continuous glucose monitor. The forecasting model learned from
            112 adults in Shanghai (12 with type 1, 100 with type 2), so it may be less accurate for people unlike them.
            Values show in mg/dL or mmol/L, whichever you read.
          </p>
        </section>
      </main>
    </div>
  );
}
