/* Compare mode, right pane: the NASA FLEX-2 droplet-flame video ("Amazing Flame Comes to Life in
   Space Station Microgravity Combustion Science"), as a YouTube player whose time drives the 3D
   flame on the left (useYouTubePlayer). If the player can't load (offline, blocked), a link still
   opens the video on YouTube, and the 3D stays at the start. */
import type { RefObject } from "react";
import { VIDEO, formatTime } from "./compareVideo";

interface Props {
  hostRef: RefObject<HTMLDivElement>; // where the player puts its iframe
  status: "loading" | "ready" | "error";
  time: number;
  playing: boolean;
}

export function ValidationReference({ hostRef, status, time, playing }: Props) {
  return (
    <div className="glass compare-reference">
      <p className="label m-0">NASA video · FLEX-2 · {VIDEO.channel}</p>
      <div ref={hostRef} className="validation-video" aria-label={`Video: ${VIDEO.title}`} />
      <p className="note m-0 compare-caption" role="status">
        {status === "loading" && "Loading the video player…"}
        {status === "ready" && `${playing ? "Playing" : "Paused"} at ${formatTime(time)}: the 3D follows the video, including when you skip.`}
        {status === "error" && "The video player couldn't load here, so the 3D can't follow it."}{" "}
        Visual reference only, not a validation of the model output.{" "}
        <a href={VIDEO.watch} target="_blank" rel="noreferrer">Watch on YouTube ↗</a>
      </p>
    </div>
  );
}
