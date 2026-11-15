import { useEffect, useState } from "react";
import { useScenario } from "../store/useScenario";

const NASA_REFERENCES = {
  bass: {
    title: "BASS / BASS-II · airflow and oxygen",
    source: "https://ntrs.nasa.gov/citations/20210011385",
    video: null,
    note: "NASA's BASS-II report covers flame spread and extinction as airflow and oxygen are varied. A direct clip URL is not available here yet.",
  },
  saffire: {
    title: "Saffire I–VI · material flammability",
    source: "https://www.nasa.gov/centers-and-facilities/glenn/nasa-ignites-fire-experiment-aboard-space-cargo-ship/",
    video: "https://www.youtube-nocookie.com/embed/lvJ78l9ZJ_E",
    note: "NASA Saffire IV footage shown as a series-level visual reference.",
  },
  saffire2: {
    title: "Saffire series · NASA reference",
    source: "https://www.nasa.gov/centers-and-facilities/glenn/flame-burns-out-on-nasas-long-running-spacecraft-fire-experiment/",
    video: null,
    note: "NASA article and video reference for the Saffire series.",
  },
  flex: {
    title: "FLEX / FLEX-2 · fuel droplets",
    source: "https://www.youtube.com/watch?v=fQESHK4RIQU",
    video: "https://www.youtube-nocookie.com/embed/fQESHK4RIQU",
    note: "NASA FLEX-2 footage showing a spherical microgravity droplet flame.",
  },
} as const;

type ReferenceKey = keyof typeof NASA_REFERENCES;
const FALLBACK_REFERENCES: { key: ReferenceKey; label: string }[] = [
  { key: "bass", label: "BASS-II · airflow / oxygen" },
  { key: "saffire", label: "Saffire I–VI · materials" },
  { key: "saffire2", label: "Saffire series · NASA reference" },
  { key: "flex", label: "FLEX / FLEX-2 · droplets" },
];

function referenceForInvestigation(investigation: string): ReferenceKey | null {
  const name = investigation.toLowerCase();
  if (name.includes("bass")) return "bass";
  if (name.includes("saffire")) return /saffire[ -]ii\b/.test(name) ? "saffire2" : "saffire";
  if (name.includes("flex")) return "flex";
  return null;
}

export function ValidationReference() {
  const syntheticTests = useScenario(s => s.simulate?.nearest_tests.filter(test => test.is_synthetic) ?? []);
  const optionsKey = syntheticTests.map(test => test.test_id).join("|");
  const preferredTest = syntheticTests.find(test => referenceForInvestigation(test.investigation) === "bass");
  const defaultSelection = preferredTest?.test_id ?? syntheticTests[0]?.test_id ?? "ref:bass";
  const [selected, setSelected] = useState("ref:bass");

  useEffect(() => setSelected(defaultSelection), [optionsKey]);

  const selectedTest = syntheticTests.find(test => test.test_id === selected);
  const referenceKey = selectedTest
    ? referenceForInvestigation(selectedTest.investigation)
    : selected.replace("ref:", "") as ReferenceKey;
  const reference = referenceKey ? NASA_REFERENCES[referenceKey] : null;

  return (
    <div className="glass compare-reference">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="label m-0">NASA visual reference</p>
        <select className="sel" aria-label="Select a synthetic test or NASA reference" value={selected}
          onChange={event => setSelected(event.target.value)}>
          {syntheticTests.length ? syntheticTests.map(test => (
            <option key={test.test_id} value={test.test_id}>
              {test.investigation} · {test.test_id} · synthetic
            </option>
          )) : FALLBACK_REFERENCES.map(option => (
            <option key={option.key} value={`ref:${option.key}`}>{option.label}</option>
          ))}
        </select>
      </div>
      {selectedTest && <p className="note m-0">Selected NASA test: {selectedTest.test_id}<span className="badge badge-synth"> synthetic</span></p>}
      {reference ? (
        <>
          {reference.video ? (
            <iframe className="validation-video" src={reference.video} title={reference.title}
              allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; web-share"
              referrerPolicy="strict-origin-when-cross-origin" allowFullScreen />
          ) : (
            <div className="validation-placeholder" role="status">
              <strong>{reference.title}</strong>
              <p className="note m-0">Video placeholder · use the NASA source link for reference footage.</p>
            </div>
          )}
          <p className="note m-0">{reference.note} Visual reference only; it is not a frame-by-frame validation of the model output.</p>
          <a className="cite" href={reference.source} target="_blank" rel="noreferrer">Open NASA reference ↗</a>
        </>
      ) : (
        <div className="validation-placeholder" role="status">
          <strong>{selectedTest?.investigation ?? "Reference unavailable"}</strong>
          <p className="note m-0">No clip is mapped for this investigation yet.</p>
          {selectedTest && <a className="cite" href={selectedTest.source_url} target="_blank" rel="noreferrer">Open test source ↗</a>}
        </div>
      )}
    </div>
  );
}
