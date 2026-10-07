/** Errors raised by the API client; components branch on these classes. */

export class ApiError extends Error {
  readonly status: number;
  /** FastAPI's `detail`, or the whole JSON body when it carries more (e.g. `{reason, detail}`). */
  readonly detail: unknown;
  /** Seconds from a Retry-After header (429), if any. */
  readonly retryAfter: number | null;

  constructor(status: number, message: string, detail?: unknown, retryAfter: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.retryAfter = retryAfter;
  }
}

/** 401: no session, or it ended. */
export class UnauthorizedError extends ApiError {
  constructor(message = 'Not signed in') {
    super(401, message);
    this.name = 'UnauthorizedError';
  }
}

/** 404: unknown patient, or no forecast produced yet. */
export class NotFoundError extends ApiError {
  constructor(message: string, detail?: unknown) {
    super(404, message, detail);
    this.name = 'NotFoundError';
  }
}

/** The request never produced an HTTP response (server down, connection refused, aborted). */
export class NetworkError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = 'NetworkError';
  }
}

export const SESSION_ENDED = 'Your session ended. Sign in again.';

/** The problem and, where the reader can act, the fix. */
export function errorMessage(err: unknown): string {
  if (err instanceof NetworkError) {
    return 'Cannot reach GlucoRAG. Check that this device is online, then try again.';
  }
  if (err instanceof UnauthorizedError) return SESSION_ENDED;
  if (err instanceof ApiError && err.status >= 500) {
    return `The service failed to answer (${err.status}: ${err.message}). Try again in a moment.`;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
