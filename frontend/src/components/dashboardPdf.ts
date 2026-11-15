import type { jsPDF } from "jspdf";
import type { SimulateOut } from "../api/types";
import type { Session } from "../store/useScenario";
import {
  buildResearchReport, evidenceIds, reportInputs, reportPercent, reportTimestamp,
  type ReportSession, type ResearchReport,
} from "./sessionReport";

const PAPER = "#F5F2EA", INK = "#514331", MUTED = "#726A5D", LINE = "#B5AA97", LIGHT = "#E6E0D4";
const MARGIN = 16, WIDTH = 178, BOTTOM = 273;
const printText = (value: string) => value
  .replace(/₂/g, "2").replace(/→/g, " to ").replace(/[–—]/g, "-")
  .replace(/[“”]/g, '"').replace(/[‘’]/g, "'").replace(/[^\S\n]+/g, " ")
  .replace(/[\u0000-\u0008\u000b-\u001f]/g, "");

class ResearchPages {
  y = 0;
  private page = 0;
  private sessionId = 0;
  constructor(readonly pdf: jsPDF, private report: ResearchReport) {}

  startSession(id: number) {
    this.sessionId = id;
    this.newPage(true);
  }

  private newPage(first = false) {
    if (this.page++) this.pdf.addPage();
    const p = this.pdf;
    p.setFillColor(PAPER);
    p.rect(0, 0, 210, 297, "F");
    p.setTextColor(INK);
    if (first) {
      p.setFont("times", "bold"); p.setFontSize(25);
      p.text(["FireTwin", "Session Research"], MARGIN, 25, { lineHeightFactor: 1.05 });
      p.setFont("helvetica", "bold"); p.setFontSize(10);
      p.text(`SESSION ${this.sessionId}`, 127, 21);
      p.setFont("helvetica", "normal"); p.setFontSize(8);
      p.text(["NASA Space Apps 2026", '"Flame in Freefall"', `${this.report.sessions.length} saved session(s) in this report`], 127, 27, { lineHeightFactor: 1.6 });
      this.y = 46;
    } else {
      p.setFont("times", "bold"); p.setFontSize(16);
      p.text(`FireTwin / Session ${this.sessionId}`, MARGIN, 21);
      p.setFont("helvetica", "normal"); p.setFontSize(8);
      p.text("Research record / continued", 194, 21, { align: "right" });
      this.y = 29;
    }
    p.setDrawColor(LINE); p.setLineWidth(0.35);
    p.line(MARGIN, this.y, 194, this.y);
    this.y += 7;
  }

  private ensure(height: number) {
    if (this.y + height > BOTTOM) this.newPage();
  }

  text(value: string, options: { size?: number; bold?: boolean; muted?: boolean; url?: string } = {}) {
    const p = this.pdf, size = options.size ?? 8.5, height = size * 0.3528 * 1.45;
    p.setFont("helvetica", options.bold ? "bold" : "normal"); p.setFontSize(size);
    const lines = p.splitTextToSize(printText(value), WIDTH) as string[];
    if (options.bold) this.ensure(Math.min(24, (lines.length + 2) * height));
    for (const line of lines) {
      this.ensure(height);
      p.setFont("helvetica", options.bold ? "bold" : "normal"); p.setFontSize(size);
      p.setTextColor(options.muted ? MUTED : INK);
      p.text(line, MARGIN, this.y + height * 0.75);
      if (options.url) p.link(MARGIN, this.y, p.getTextWidth(line), height, { url: options.url });
      this.y += height;
    }
    this.y += 1.8;
  }

  section(title: string) {
    this.ensure(24); this.y += 3;
    const p = this.pdf;
    p.setDrawColor(LINE); p.line(MARGIN, this.y + 4, 194, this.y + 4);
    p.setFont("helvetica", "bold"); p.setFontSize(10);
    const w = Math.min(WIDTH, p.getTextWidth(title) + 16);
    p.setFillColor(PAPER); p.roundedRect(MARGIN, this.y, w, 8, 4, 4, "FD");
    p.setTextColor(INK); p.text(title, MARGIN + 8, this.y + 5.5);
    this.y += 13;
  }

  cards(left: [string, string[]], right: [string, string[]]) {
    const p = this.pdf, w = 85;
    p.setFont("helvetica", "normal"); p.setFontSize(8.2);
    const content = [left, right].map(([title, lines]) => ({
      title, lines: lines.flatMap(line => p.splitTextToSize(printText(line), w - 12) as string[]),
    }));
    const h = Math.max(...content.map(c => c.lines.length)) * 4.1 + 19;
    if (h > 100) {
      for (const [title, lines] of [left, right]) { this.section(title); lines.forEach(line => this.text(line)); }
      return;
    }
    this.ensure(h + 6);
    content.forEach((card, i) => {
      const x = MARGIN + i * 93;
      p.setDrawColor(LINE); p.setFillColor(PAPER); p.roundedRect(x, this.y, w, h, 4, 4, "FD");
      p.setTextColor(INK); p.setFont("helvetica", "bold"); p.setFontSize(10);
      p.text(card.title, x + 6, this.y + 8);
      p.setFont("helvetica", "normal"); p.setFontSize(8.2);
      card.lines.forEach((line, j) => p.text(line, x + 6, this.y + 16 + j * 4.1));
    });
    this.y += h + 6;
  }

  probabilityChart(initial: number, final: number) {
    this.ensure(35);
    const p = this.pdf;
    p.setDrawColor(LINE); p.roundedRect(MARGIN, this.y, WIDTH, 30, 4, 4, "S");
    p.setFont("helvetica", "bold"); p.setFontSize(9); p.setTextColor(INK);
    p.text("MODEL BURN PROBABILITY", MARGIN + 6, this.y + 7);
    [["At ignition", initial], ["Last recorded", final]].forEach(([label, value], i) => {
      const y = this.y + 12 + i * 8;
      p.setFont("helvetica", "normal"); p.setFontSize(8);
      p.text(String(label), MARGIN + 6, y + 3.5);
      p.setFillColor(LIGHT); p.roundedRect(62, y, 100, 4.5, 1, 1, "F");
      const probability = Number(value);
      if (Number.isFinite(probability) && probability > 0) {
        p.setFillColor(INK); p.rect(62, y, Math.max(0, Math.min(1, probability)) * 100, 4.5, "F");
      }
      p.text(reportPercent(probability), 169, y + 3.5);
    });
    this.y += 36;
  }

  sourceUrl(url: string) {
    let safe = false;
    try { safe = ["http:", "https:"].includes(new URL(url).protocol); } catch { /* plain text */ }
    this.text(url || "Source URL not recorded", { size: 7.5, muted: true, url: safe ? url : undefined });
  }

  finish() {
    const p = this.pdf, count = p.getNumberOfPages();
    for (let i = 1; i <= count; i++) {
      p.setPage(i); p.setDrawColor(LINE); p.line(MARGIN, 281, 194, 281);
      p.setFont("helvetica", "normal"); p.setFontSize(7); p.setTextColor(MUTED);
      p.text("Flame is illustrative; verdicts come from NASA PSI data.", MARGIN, 286);
      p.text(`${i} / ${count}`, 194, 286, { align: "right" });
      p.text(`Exported ${reportTimestamp(this.report.generatedAt)}`, MARGIN, 291);
    }
  }
}

const predictionLines = (result: SimulateOut) => [
  `Verdict: ${result.state.toUpperCase()} (model)`,
  `Burn probability: ${reportPercent(result.burn_probability)}`,
  `Trust: ${result.trust} | ${result.extrapolated ? "OUTSIDE TESTED RANGE" : "Within recorded model ranges"}`,
  `Spread: ${result.spread_rate_mm_s === null ? "Not modeled / no recorded estimate" : `${result.spread_rate_mm_s} mm/s (model)`}`,
];

function drawSession(pages: ResearchPages, session: ReportSession) {
  const { initial, final } = session;
  pages.startSession(session.id);
  pages.text(`Recorded start: ${reportTimestamp(session.startedAt)}`, { size: 8, muted: true });
  pages.text(`Scenario ID: ${initial.scenario_id}`, { size: 8, muted: true });
  if (session.synthetic) pages.text("SYNTHETIC DATA PRESENT - fixture evidence is marked below.", { bold: true });
  pages.cards(["Research objective", [
    "Explore how oxygen, airflow and material affect sustained combustion in the ISS lab.",
    "This report preserves saved browser sessions, model predictions and their cited test rows.",
  ]], ["Values used at ignition", [
    `Material: ${initial.inputs.material}`, `Module: ${initial.inputs.module}`,
    `Oxygen: ${initial.inputs.o2_pct}% | Pressure: ${initial.inputs.pressure_kpa} kPa`,
    `Airflow: ${initial.inputs.flow_speed_cm_s} cm/s`, `Direction: [${initial.inputs.flow_dir.join(", ")}]`,
  ]]);
  pages.cards(["Ignition prediction", predictionLines(initial)], ["Final recorded result", predictionLines(final)]);
  pages.probabilityChart(initial.burn_probability, final.burn_probability);
  pages.section("Analysis & conclusion");
  const actions = session.steps.filter(step => step.kind === "apply").length;
  pages.text(`Final recorded model verdict: ${final.state.toUpperCase()}. ${actions} suppression action(s) applied. Burn probability: ${reportPercent(initial.burn_probability)} at ignition to ${reportPercent(final.burn_probability)} at the last saved prediction.`);
  pages.text(`Derived change in model burn probability: ${((final.burn_probability - initial.burn_probability) * 100).toFixed(1)} percentage points. Final material and conditions: ${reportInputs(final.inputs)}.`);
  pages.section("Method & evidence");
  pages.text("Probabilities and spread are model estimates, not measurements. NASA rows in the evidence register are the supporting observations. Trust and range flags are preserved from each response.");
  pages.text(`Initial evidence: ${evidenceIds(session, initial.nearest_tests)}. Final evidence: ${evidenceIds(session, final.nearest_tests)}.`);
  pages.text("Step timestamps are browser response-recording times in UTC, not NASA experiment times. Only data saved before export is included.", { size: 7.5, muted: true });
  pages.section("Suppression strategies");
  if (!session.rankings.length) pages.text("No suppression ranking was recorded for this session. Alternatives and probabilities were not recomputed for export.");
  session.rankings.forEach((ranking, i) => {
    pages.text(`Assessment ${i + 1} | ${reportTimestamp(ranking.at)}`, { bold: true });
    pages.text(`Recommended at that assessment: ${ranking.result.recommended}`);
    pages.text(ranking.inputs ? `Input snapshot: ${reportInputs(ranking.inputs)}` : "Ranking input snapshot not recorded for this older session.", { size: 7.5, muted: true });
    ranking.result.actions.forEach((action, j) => {
      pages.text(`${j + 1}. ${action.label} (${action.action})${action.action === ranking.result.recommended ? " - RECOMMENDED" : ""}`, { bold: true });
      pages.text(`Extinction probability (model): ${reportPercent(action.extinction_probability)} | Crew risk index (assumed): ${action.crew_risk.toFixed(3)} | Ranking score: ${action.score.toFixed(4)}`);
      pages.text(`Data support: ${action.data_support} | Evidence: ${evidenceIds(session, action.sources)}`, { size: 7.5 });
      pages.text(`Proposed values: ${reportInputs(action.new_inputs)}`, { size: 7.5 });
      pages.text(action.explanation || "Explanation not recorded.", { size: 7.8, muted: true });
    });
  });
  pages.section("Timestamped results");
  session.steps.forEach((step, i) => {
    pages.text(`${i + 1}. ${step.kind.toUpperCase()}${step.action ? ` / ${step.action}` : ""} | ${reportTimestamp(step.at)}`, { bold: true });
    if (step.prediction) {
      const result = step.prediction;
      if (step.kind === "apply" && !step.action) pages.text("Applied action name not recorded in this older session.", { size: 7.5, muted: true });
      pages.text(reportInputs(result.inputs), { size: 7.8 });
      pages.text(`${result.state.toUpperCase()} | Burn (model): ${reportPercent(result.burn_probability)} | Trust: ${result.trust} | ${result.extrapolated ? "OUTSIDE TESTED RANGE" : "Within recorded model ranges"}`);
      pages.text(`Evidence: ${evidenceIds(session, result.nearest_tests)}. ${result.explanation || "No explanation recorded."}`, { size: 7.8, muted: true });
    }
    if (step.detection) {
      const d = step.detection;
      pages.text(d.detected ? `Modeled alarm: ${d.detector_id ?? "Detector not recorded"} | Delay: ${d.time_to_detect_s === null ? "Not recorded" : `${d.time_to_detect_s} s`}` : "No modeled alarm detected.");
      pages.text(d.note, { size: 7.8, muted: true });
    }
  });
  pages.section("NASA evidence register");
  if (!session.evidence.length) pages.text("No test references were saved. Supporting measurements are unavailable for this session.");
  session.evidence.forEach((ref, i) => {
    pages.text(`[E${i + 1}] ${ref.test_id} / ${ref.investigation} | ${ref.fuel_type} | ${ref.outcome}${ref.is_synthetic ? " [SYNTHETIC - NOT A NASA MEASUREMENT]" : ""}`, { size: 8, bold: true });
    pages.text(`Test O2: ${ref.o2_pct === null ? "Not recorded" : `${ref.o2_pct}%`} | Pressure: ${ref.pressure_kpa === null ? "Not recorded" : `${ref.pressure_kpa} kPa`} | Airflow: ${ref.flow_cm_s === null ? "Not recorded" : `${ref.flow_cm_s} cm/s`}`, { size: 7.8 });
    pages.sourceUrl(ref.source_url);
  });
  pages.text("Recommendations are the saved assessments above; an untried alternative is not an observed session outcome. Missing steps, times or evidence are not filled in with estimates.", { size: 7.5, muted: true });
}

/** Selectable text, linked evidence and flowing portrait pages, rather than a screenshot. */
export async function createResearchPdf(report: ResearchReport): Promise<jsPDF> {
  const { jsPDF } = await import("jspdf");
  const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
  pdf.setProperties({ title: "FireTwin - Session research report", subject: "Saved conditions, model results, suppression and NASA evidence", creator: "FireTwin" });
  const pages = new ResearchPages(pdf, report);
  report.sessions.forEach(session => drawSession(pages, session));
  pages.finish();
  return pdf;
}

export async function downloadDashboardPdf(sessions: readonly Session[]) {
  const report = buildResearchReport(sessions);
  const pdf = await createResearchPdf(report);
  pdf.save(`firetwin-research-${new Date(report.generatedAt).toISOString().slice(0, 10)}.pdf`);
}
