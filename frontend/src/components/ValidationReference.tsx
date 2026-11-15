/* Compare mode, right pane: one fixed visual reference, the FLEX-2 droplet-flame video
   ("Spherical Flame Comes to Life in Microgravity Experiment"), next to the 3D simulation. */

const FLEX2 = {
  title: "FLEX / FLEX-2 · fuel droplets",
  video: "https://www.youtube-nocookie.com/embed/fQESHK4RIQU",
  watch: "https://www.youtube.com/watch?v=fQESHK4RIQU",
};

export function ValidationReference() {
  return (
    <div className="glass compare-reference">
      <p className="label m-0">NASA visual reference · {FLEX2.title}</p>
      <iframe className="validation-video" src={FLEX2.video} title={FLEX2.title}
        allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen; web-share"
        referrerPolicy="strict-origin-when-cross-origin" loading="lazy" allowFullScreen />
      <p className="note m-0 compare-caption">
        FLEX-2 footage of a spherical microgravity droplet flame. Visual reference only, not a
        validation of the model output. <a href={FLEX2.watch} target="_blank" rel="noreferrer">Watch on YouTube ↗</a>
      </p>
    </div>
  );
}
