/**
 * Which rule judged a run - or, honestly, that nobody recorded it (slice 16, G6b).
 *
 * The engine stores the rule's `version` beside the SHA-256 of what that version says, because a
 * version a person keeps by hand can lie and a digest cannot. Both are shown: two runs that each
 * claim v2 but carry different digests were judged by two different rules.
 *
 * NULL IS NOT TODAY'S VERSION. A run stored before rules carried a version has neither, and it
 * says "version not recorded". Filling the gap with the current version would be a claim nobody
 * established - the freshness rule, applied to identity.
 */
import type { HistoryRow } from "@/lib/types";

/** The first twelve hex characters, as the engine's own page shows them. Display only. */
export function shortDigest(digest: string): string {
  const hex = digest.slice(digest.indexOf(":") + 1);
  return hex.slice(0, 12);
}

export function Policy({ version, digest }: { version: number | null; digest: string | null }) {
  if (version === null) {
    return (
      <>
        <strong>Version not recorded</strong> · this run was stored before rules carried a version,
        so which version of the rule judged it cannot be said
      </>
    );
  }
  return (
    <>
      Judged under <strong>v{version}</strong> of this rule
      {digest ? (
        <>
          {" "}
          · digest <code>{shortDigest(digest)}</code>
        </>
      ) : null}
    </>
  );
}

/**
 * History rows grouped by the rule that judged them, keeping their order: groups in the order of
 * their newest run, rows newest first inside each. By version AND digest, so a rule edited
 * without its bump forms its own group rather than hiding inside the reviewed one. The engine's
 * `policy_groups` does the same for its page.
 */
export function policyGroups(rows: HistoryRow[]): { key: string; rows: HistoryRow[] }[] {
  const groups = new Map<string, HistoryRow[]>();
  for (const row of rows) {
    const key = `${row.policy_version ?? "none"}|${row.policy_digest ?? "none"}`;
    const members = groups.get(key);
    if (members) members.push(row);
    else groups.set(key, [row]);
  }
  return [...groups].map(([key, members]) => ({ key, rows: members }));
}
