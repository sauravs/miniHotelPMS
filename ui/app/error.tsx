"use client";
/**
 * What a reader sees when a page could not be built - most often because the engine is not
 * running, or refused the request.
 *
 * OURS, NOT NEXT'S, for the same reason as not-found.tsx: the default is built from inline
 * `style` attributes this surface's CSP refuses. Found by stopping the engine and loading a page.
 * It must be a client component (Next renders error boundaries in the browser), and like every
 * client component here it never imports lib/api - it cannot run anything, only offer a retry.
 *
 * The message is deliberately generic: in production Next replaces the error's text with a
 * digest, so the reader is told what usually causes this rather than shown a stack.
 */
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="card blocked" role="alert">
      <p className="sentence">This page could not be built.</p>
      <p>
        The control engine did not answer, or refused the request. If it is not running, start it
        with <code>python3 -m hotelcontrols.web.server</code> and try again. Nothing was run and
        nothing was saved.
      </p>
      <p>
        <button type="button" onClick={reset}>
          Try again
        </button>
      </p>
    </div>
  );
}
