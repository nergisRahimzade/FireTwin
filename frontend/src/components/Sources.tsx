/* FE-07 / FE-08: NASA test chips (investigation + test_id, linked to source_url). Synthetic seed rows
   show a "synthetic" badge and no link (their source_url is a placeholder, not a page). */
import type { TestRef } from "../api/types";

export function Sources({ sources }: { sources: TestRef[] }) {
  if (!sources.length) return <span className="note">No NASA tests nearby.</span>;
  return (
    <span className="chips">
      {sources.map((t, i) => {
        const text = `${t.investigation} · ${t.test_id}`;
        return (
          <span key={`${i}-${t.test_id}`} className="cite">
            {/^https?:\/\//.test(t.source_url) ? (
              <a href={t.source_url} target="_blank" rel="noreferrer">{text}</a>
            ) : text}
            {t.is_synthetic && <span className="badge-synth"> synthetic</span>}
          </span>
        );
      })}
    </span>
  );
}
