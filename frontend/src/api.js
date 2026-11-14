/* Backend wiring.
   Copied from the earlier flame-in-freefall repo, where search() and summarize() were Python
   functions (its contract v1.10). They are NOT in the FireTwin contract yet (backend/app/schemas.py,
   BE-05); move this file to that contract when it lands. Until then it is only used when
   VITE_API_URL (see .env.example) points to a server that exposes:
     GET  {VITE_API_URL}/search?q=...&k=5          -> search():    [{id, text, source, page, score, experiment}]
     POST {VITE_API_URL}/summarize {question, passages} -> summarize(): {takeaways: [{text, source, chunk_id}], not_found}
   Without it, or when a call fails, answers come from the bundled demo data (src/data/fallback.json). */
const API = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
export const usingApi = Boolean(API);

// Returns {q, src, results: [{id, exp, text, score}], summary: [[text, source, page]]}, or null for "not found".
export async function askReports(q, local) {
  if (!API) {
    await new Promise(r => setTimeout(r, 300)); // same short pause as the prototype, so loading states show
    return local(q);
  }
  try {
    const res = await fetch(`${API}/search?` + new URLSearchParams({ q, k: "5" }));
    if (!res.ok) throw new Error(`search returned ${res.status}`);
    const passages = await res.json();
    if (!passages.length) return null;
    const sres = await fetch(`${API}/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q, passages }),
    });
    const sum = sres.ok ? await sres.json() : { takeaways: [], not_found: false };
    if (sum.not_found) return null;
    const pageOf = Object.fromEntries(passages.map(p => [p.id, p.page]));
    const top = passages[0];
    return {
      q,
      src: top.experiment,
      results: passages.map(p => ({ id: p.id, exp: p.experiment, text: p.text, score: p.score })),
      summary: sum.takeaways.length
        ? sum.takeaways.map(t => [t.text, t.source, pageOf[t.chunk_id] ?? 1])
        : [[top.text.slice(0, 220), top.experiment, top.page]],
    };
  } catch (err) {
    console.warn("Backend unavailable, answering from bundled data:", err);
    return local(q);
  }
}
