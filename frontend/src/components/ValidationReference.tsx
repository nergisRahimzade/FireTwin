import { useEffect, useState } from "react";
import type { TestRef } from "../api/types";
import { useScenario } from "../store/useScenario";

const EMPTY_TESTS: ReadonlyArray<TestRef> = Object.freeze([]);

const NASA_REFERENCES = {
  bass: {
    title: "BASS / BASS-II · airflow and oxygen",
    source: "https://ntrs.nasa.gov/citations/20210011385",
    video: "https://www.youtube-nocookie.com/embed/rsc-v3WoroU",
    note: "NASA Johnson's BASS-II experiment overview. This is an interview about the experiment, not a test-run clip.",
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
    video: "https://www.youtube-nocookie.com/embed/lvJ78l9ZJ_E",
    note: "NASA Saffire IV footage used as series-level context for this NASA article.",
  },
  flex: {
    title: "FLEX / FLEX-2 · fuel droplets",
    source: "https://www.youtube.com/watch?v=fQESHK4RIQU",
    video: "https://www.youtube-nocookie.com/embed/fQESHK4RIQU",
    note: "NASA FLEX-2 footage showing a spherical microgravity droplet flame.",
  },
} as const;

type ReferenceKey = keyof typeof NASA_REFERENCES;
const isReferenceKey = (key: string): key is ReferenceKey => Object.prototype.hasOwnProperty.call(NASA_REFERENCES, key);
const FALLBACK_REFERENCES: { key: ReferenceKey; label: string }[] = [
  { key: "bass", label: "BASS-II · airflow / oxygen" },
  { key: "saffire", label: "Saffire I–VI · materials" },
  { key: "saffire2", label: "Saffire series · NASA reference" },
  { key: "flex", label: "FLEX / FLEX-2 · droplets" },
];

function referenceForInvestigation(investigation?: string | null): ReferenceKey | null {
  const name = (investigation ?? "").toLowerCase();
  if (name.includes("bass")) return "bass";
  if (name.includes("saffire")) return /saffire[ -]ii\b/.test(name) ? "saffire2" : "saffire";
  if (name.includes("flex")) return "flex";
  return null;
}

export function ValidationReference() {
  const nearestTests = useScenario(s => s.simulate?.nearest_tests ?? EMPTY_TESTS);
  const syntheticTests = nearestTests.filter(test => test?.is_synthetic);
  const optionsKey = syntheticTests.map(test => test?.test_id ?? "").join("|");
  const preferredTest = syntheticTests.find(test => referenceForInvestigation(test.investigation) === "bass");
  const defaultSelection = preferredTest ? `test:${preferredTest.test_id}`
    : syntheticTests[0] ? `test:${syntheticTests[0].test_id}` : "ref:bass";
  const [selected, setSelected] = useState("ref:bass");

  useEffect(() => setSelected(defaultSelection), [optionsKey]);

  const selectedTest = selected.startsWith("test:")
    ? syntheticTests.find(test => test.test_id === selected.slice(5))
    : undefined;
  const selectedReference = selected.startsWith("ref:") ? selected.slice(4) : "";
  const referenceKey = selectedTest
    ? referenceForInvestigation(selectedTest.investigation)
    : isReferenceKey(selectedReference) ? selectedReference : null;
  const reference = referenceKey ? NASA_REFERENCES[referenceKey] : null;

  return (
    <div className="glass compare-reference">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="label m-0">NASA visual reference</p>
        <select className="sel" aria-label="Select a synthetic test or NASA reference" value={selected}
          onChange={event => setSelected(event.target.value)}>
          {syntheticTests.length ? syntheticTests.map(test => (
            <option key={test.test_id} value={`test:${test.test_id}`}>
              {test.investigation} · {test.test_id} · synthetic
            </option>
          )) : FALLBACK_REFERENCES.map(option => (
            <option key={option.key} value={`ref:${option.key}`}>{option.label}</option>
          ))}
        </select>
      </div>
      {selectedTest && <p className="note m-0">Selected NASA test: {selectedTest.test_id ?? "Unknown test"}<span className="badge badge-synth"> synthetic</span></p>}
      {reference ? (
        <>
          <iframe className="validation-video" src={reference.video} title={reference.title}
            allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture; fullscreen; web-share"
            referrerPolicy="strict-origin-when-cross-origin" loading="lazy" allowFullScreen />
          <p className="note m-0">{reference.note} Visual reference only; it is not a frame-by-frame validation of the model output.</p>
          <a className="cite" href={reference.source} target="_blank" rel="noreferrer">Open NASA reference ↗</a>
        </>
      ) : (
        <div className="validation-placeholder" role="status">
          <strong>{selectedTest?.investigation ?? "Reference unavailable"}</strong>
          <p className="note m-0">No clip is mapped for this investigation yet.</p>
          {selectedTest?.source_url && <a className="cite" href={selectedTest.source_url} target="_blank" rel="noreferrer">Open test source ↗</a>}
        </div>
      )}
    </div>
  );
}
