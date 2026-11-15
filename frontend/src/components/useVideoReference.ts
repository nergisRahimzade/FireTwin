/* Compare: the two live inputs of the video view, kept out of CompareView so it stays layout only.
   - useYouTubePlayer: the YouTube IFrame Player API (loaded once from youtube.com). It reports the
     video's current time ~10x a second, so play, pause and seeking in the video all move the 3D.
   - useVideoModel: the model's verdict for the video's conditions and its O2 curve, from /preview
     (no scenario or session is created), fetched once and kept for the rest of the visit. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { MetaOut, PreviewOut } from "../api/types";
import { MODEL_INPUTS } from "./compareVideo";
import { type Point, chartSweep, chartTested } from "./dashboard.logic";

// The few YouTube player calls used here (the API has no bundled types).
interface YTPlayer {
  getCurrentTime(): number;
  getDuration(): number;
  getPlayerState(): number; // 1 = playing
  seekTo(seconds: number, allowSeekAhead: boolean): void;
  destroy(): void;
}
interface YTNamespace {
  Player: new (el: HTMLElement, options: Record<string, unknown>) => YTPlayer;
}
declare global {
  interface Window {
    YT?: YTNamespace;
    onYouTubeIframeAPIReady?: () => void;
  }
}

// One script for the whole page: later players reuse it. null = not requested yet (or it failed,
// so the next Compare visit tries again).
let apiReady: Promise<YTNamespace> | null = null;
function loadYouTubeApi(): Promise<YTNamespace> {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  apiReady ??= new Promise((resolve, reject) => {
    const previous = window.onYouTubeIframeAPIReady; // keep any other player's callback working
    window.onYouTubeIframeAPIReady = () => { previous?.(); resolve(window.YT!); };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    script.async = true;
    script.onerror = () => { apiReady = null; reject(new Error("YouTube player could not load")); };
    document.head.appendChild(script);
  });
  return apiReady;
}

export interface PlayerState {
  status: "loading" | "ready" | "error";
  time: number; // seconds into the video
  playing: boolean;
  duration: number | null; // null until the player knows it
}

const POLL_MS = 100; // how often the video's time is read: smooth enough for a 3D flame

export function useYouTubePlayer(videoId: string) {
  const hostRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const [state, setState] = useState<PlayerState>({ status: "loading", time: 0, playing: false, duration: null });

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // YouTube replaces the element it's given with its iframe, so give it a child React doesn't own.
    const mount = document.createElement("div");
    host.appendChild(mount);
    let alive = true;
    let poll: ReturnType<typeof setInterval> | undefined;
    loadYouTubeApi()
      .then(YT => {
        if (!alive) return;
        playerRef.current = new YT.Player(mount, {
          videoId,
          host: "https://www.youtube-nocookie.com", // YouTube's privacy-enhanced mode, like the old embed
          playerVars: { rel: 0, playsinline: 1 },
          events: {
            onReady: () => {
              if (!alive) return;
              // Polling (not only state events) also catches seeking while paused.
              poll = setInterval(() => {
                const p = playerRef.current;
                if (!p) return;
                const time = p.getCurrentTime() || 0;
                const playing = p.getPlayerState() === 1;
                const duration = p.getDuration() || null;
                setState(s => (Math.abs(s.time - time) < 0.05 && s.playing === playing && s.duration === duration && s.status === "ready"
                  ? s : { status: "ready", time, playing, duration }));
              }, POLL_MS);
            },
            onError: () => { if (alive) setState(s => ({ ...s, status: "error" })); },
          },
        });
      })
      .catch(() => { if (alive) setState(s => ({ ...s, status: "error" })); });
    return () => {
      alive = false;
      if (poll) clearInterval(poll);
      playerRef.current?.destroy();
      playerRef.current = null;
      mount.remove();
    };
  }, [videoId]);

  // Jump the video (and so the 3D) to a moment, e.g. from the timeline below it.
  const seek = useCallback((seconds: number) => {
    playerRef.current?.seekTo(seconds, true);
    setState(s => ({ ...s, time: seconds }));
  }, []);

  return { hostRef, ...state, seek };
}

export interface VideoModel {
  preview: PreviewOut | null; // the verdict at the video's conditions; null while loading or offline
  curve: Point[] | null; // burn probability across O2 at those conditions
  error: string | null;
}

// Kept for the whole visit: the inputs never change, so reopening Compare needn't ask again.
let cached: VideoModel | null = null;

export function useVideoModel(meta: MetaOut | null): VideoModel {
  const [model, setModel] = useState<VideoModel>(cached ?? { preview: null, curve: null, error: null });
  const tested = chartTested(meta, MODEL_INPUTS).range;
  useEffect(() => {
    if (cached || !meta) return; // wait for /meta: the sweep samples its tested O2 range's edges
    let alive = true;
    Promise.all([
      api.preview(MODEL_INPUTS),
      Promise.all(chartSweep(tested).map(o2 => api.preview({ ...MODEL_INPUTS, o2_pct: o2 }).then(r => [o2, r.burn_probability] as Point))),
    ])
      .then(([preview, curve]) => {
        cached = { preview, curve, error: null };
        if (alive) setModel(cached);
      })
      .catch(err => { if (alive) setModel({ preview: null, curve: null, error: err instanceof Error ? err.message : String(err) }); });
    return () => { alive = false; };
  }, [meta, tested?.min, tested?.max]); // the range's numbers, not the object rebuilt every render
  return model;
}
