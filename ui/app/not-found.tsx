/**
 * The page for anything the engine does not know: an unknown control, a run id nobody stored,
 * a path nobody routed.
 *
 * OURS, NOT NEXT'S. Next's default 404 is built from inline `style` attributes, which this
 * surface's Content-Security-Policy refuses - so until this file existed every 404 rendered
 * half-styled with a console full of violations. Found by driving the history page live. The
 * engine's surface states an absence rather than shrugging at it; this does the same.
 */
export default function NotFound() {
  return (
    <div className="card">
      <p className="sentence">There is nothing here.</p>
      <p>
        No control, stored run or page answers to this address. A run id only exists once the run
        has been made, and the engine keeps runs for as long as it is running.
      </p>
      <p className="meta">
        <a href="/">Every control is listed here.</a>
      </p>
    </div>
  );
}
