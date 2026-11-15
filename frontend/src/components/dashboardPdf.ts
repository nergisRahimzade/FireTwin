import html2canvas from "html2canvas";
import { jsPDF } from "jspdf";
import type { TimelineEvent } from "../store/useScenario";

export async function downloadDashboardPdf(element: HTMLElement, timeline: TimelineEvent[]) {
  const canvas = await html2canvas(element, {
    backgroundColor: "#080b11",
    scale: 1.5,
    ignoreElements: node => node.classList.contains("export-menu"),
  });
  const pdf = new jsPDF({ orientation: "landscape", unit: "mm", format: "a4" });
  const margin = 10;
  const maxWidth = pdf.internal.pageSize.getWidth() - margin * 2;
  const maxHeight = pdf.internal.pageSize.getHeight() - margin * 2 - 10;
  const scale = Math.min(maxWidth / canvas.width, maxHeight / canvas.height);
  const imageWidth = canvas.width * scale;
  const imageHeight = canvas.height * scale;

  pdf.setFontSize(16);
  pdf.text("FireTwin dashboard snapshot", margin, margin + 4);
  pdf.addImage(canvas.toDataURL("image/png"), "PNG", (pdf.internal.pageSize.getWidth() - imageWidth) / 2, margin + 8, imageWidth, imageHeight);

  pdf.addPage();
  pdf.setFontSize(16);
  pdf.text("Session timeline", margin, margin + 4);
  pdf.setFontSize(9);
  let y = margin + 12;
  const lineHeight = 4.5;
  const pageHeight = pdf.internal.pageSize.getHeight();

  for (const event of timeline) {
    const timestamp = new Date(event.at).toLocaleString();
    const transition = event.from === null
      ? event.value ?? "(removed)"
      : `${event.from} → ${event.value ?? "(removed)"}`;
    const entry = `${timestamp} | ${event.action.toUpperCase()} | ${event.variable}: ${transition} | ${event.context}`;
    const lines = pdf.splitTextToSize(entry, maxWidth);
    if (y + lines.length * lineHeight > pageHeight - margin) {
      pdf.addPage();
      y = margin + 6;
    }
    pdf.text(lines, margin, y);
    y += lines.length * lineHeight + 2;
  }
  if (!timeline.length) pdf.text("No variable use or change events recorded this session.", margin, y);

  pdf.save("firetwin-session.pdf");
}
