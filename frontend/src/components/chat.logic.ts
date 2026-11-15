/* FE-10: pure helpers for the chat panel. */

export const STARTER_QUESTIONS = [
  "Why did fans off work?",
  "Which NASA tests support this?",
  "What happens at Moon base oxygen levels?",
];

/** The first http(s) URL in a citation's source_url (the backend can send "source_url: https://…"). */
export function citationUrl(sourceUrl: string): string | null {
  const m = sourceUrl.match(/https?:\/\/\S+/);
  return m ? m[0] : null;
}
