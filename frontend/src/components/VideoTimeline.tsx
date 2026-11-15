/* Compare: the video's phases on a time axis with a playhead that follows the video. Clicking the
   axis, or a phase button under it, seeks the video, and the 3D flame follows. Phase times were
   read off the video by the team (compareVideo.ts). */
import type { MouseEvent } from "react";
import { PHASES, SOURCES, formatTime, phaseAt, phaseEnd } from "./compareVideo";

interface Props {
  time: number; // seconds into the video
  duration: number | null; // null until the player knows the video's length
  onSeek?: (seconds: number) => void; // undefined = the player isn't available, so no seeking
}

export function VideoTimeline({ time, duration, onSeek }: Props) {
  // Until the player reports the length, draw the last phase a little past its start, open-ended.
  const lastFrom = PHASES[PHASES.length - 1].from;
  const end = duration ?? lastFrom * 1.2;
  const W = 560, L = 8, R = W - 8, BAR_T = 20, BAR_B = 44, H = 64;
  const x = (t: number) => L + (Math.min(Math.max(t, 0), end) / end) * (R - L);
  const current = phaseAt(time);
  // Roughly how wide a label is at 11px (the bars hide labels that don't fit; the buttons below
  // list every phase anyway), and which start times are far enough apart to print.
  const fits = (label: string, width: number) => label.length * 6.4 + 12 <= width;
  const tickShown = PHASES.map((phase, i) => i === 0 || x(phase.from) - x(PHASES[i - 1].from) >= 34);
  const seekAt = (e: MouseEvent<SVGRectElement>) => {
    const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect(); // the SVG scales with the page
    onSeek?.(((((e.clientX - box.left) / box.width) * W - L) / (R - L)) * end);
  };
  return (
    <figure className="m-0 video-timeline">
      <p className="label m-0">Video timeline · flame in the 3D</p>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Video phases. Now at ${formatTime(time)}: ${PHASES[current].label}.`}>
        {PHASES.map((phase, i) => {
          const to = phaseEnd(i, duration) ?? end;
          const width = x(to) - x(phase.from);
          const label = [phase.label, phase.short].find(text => fits(text, width));
          return (
            <g key={phase.from}>
              <rect x={x(phase.from)} y={BAR_T} width={Math.max(0, width - 2)} height={BAR_B - BAR_T} rx={4}
                className={`phase phase-${phase.flame}${i === current ? " phase-now" : ""}`} />
              {label && <text x={x(phase.from) + 6} y={BAR_T + 15} className="phase-label">{label}</text>}
              {tickShown[i] && <text x={x(phase.from)} y={H - 6} className="tick" textAnchor={i === 0 ? "start" : "middle"}>{formatTime(phase.from)}</text>}
            </g>
          );
        })}
        {duration != null && <text x={R} y={H - 6} className="tick" textAnchor="end">{formatTime(duration)}</text>}
        <g pointerEvents="none">
          <line x1={x(time)} y1={BAR_T - 6} x2={x(time)} y2={BAR_B + 4} className="playhead" />
          <text x={Math.min(Math.max(x(time), L + 20), R - 20)} y={BAR_T - 9} textAnchor="middle" className="readout">{formatTime(time)}</text>
        </g>
        {onSeek && <rect x={L} y={BAR_T - 6} width={R - L} height={BAR_B - BAR_T + 10} fill="transparent" className="seek-area" onClick={seekAt} />}
      </svg>
      <figcaption className="phase-buttons">
        {PHASES.map((phase, i) => (
          <button key={phase.from} type="button" className="chip" aria-current={i === current} disabled={!onSeek}
            onClick={() => onSeek?.(phase.from)}>
            <span className="mono">{formatTime(phase.from)}</span> {phase.label}
          </button>
        ))}
        <span className="note">{SOURCES.team}. Clicking a phase, or the bar, moves the video and the 3D there.</span>
      </figcaption>
    </figure>
  );
}
