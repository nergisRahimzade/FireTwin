/* FE-10: ask about the fire. POST /chat with the current scenario when one exists; each answer lists
   its NASA citations as links. Starter questions from the plan send at one click. */
import { type FormEvent, useState } from "react";
import { useScenario } from "../store/useScenario";
import { STARTER_QUESTIONS, citationUrl } from "./chat.logic";

export function ChatPanel() {
  const chat = useScenario(s => s.chat);
  const ask = useScenario(s => s.ask);
  const busy = useScenario(s => s.loading.chat);
  const hasScenario = useScenario(s => s.simulate != null);
  const [text, setText] = useState("");

  const send = (q: string) => {
    const message = q.trim();
    if (!message || busy) return;
    setText("");
    void ask(message);
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
  };

  return (
    <section className="area-chat glass panel" aria-label="Chat">
      <h2 className="panel-title m-0">Ask about this fire</h2>
      <p className="note">{hasScenario ? "Questions include the current scenario." : "General questions about NASA fire tests."}</p>
      <ol className="chat-list">
        {chat.map((turn, i) => (
          <li key={i}>
            <p className="chat-q m-0">{turn.question}</p>
            <p className="chat-a m-0">{turn.reply.answer}</p>
            {turn.reply.citations.length > 0 && (
              <span className="chips">
                {turn.reply.citations.map((c, j) => {
                  const url = citationUrl(c.source_url);
                  const label = `${c.investigation} · ${c.title}`;
                  return (
                    <span key={j} className="cite">
                      {url ? <a href={url} target="_blank" rel="noreferrer">{label}</a> : label}
                    </span>
                  );
                })}
              </span>
            )}
          </li>
        ))}
        {busy && <li className="note">Thinking…</li>}
      </ol>
      {chat.length === 0 && (
        <div className="chips">
          {STARTER_QUESTIONS.map(q => (
            <button key={q} type="button" className="chip" disabled={busy} onClick={() => send(q)}>{q}</button>
          ))}
        </div>
      )}
      <form className="chat-form" onSubmit={onSubmit}>
        <input
          value={text} onChange={e => setText(e.target.value)} placeholder="Ask a question…"
          aria-label="Question" disabled={busy}
        />
        <button type="submit" className="btn-primary" disabled={busy || !text.trim()}>Ask</button>
      </form>
    </section>
  );
}
