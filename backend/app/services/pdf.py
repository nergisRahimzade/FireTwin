"""BE-09: render saved scenario results as a ReportLab PDF. No HTTP or LLM calls."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from app.schemas import ResultsOut, ScenarioIn, SuppressOut, TestRef
from app.services import predictor, store, suppressor
from ml.pipeline import model
from ml.pipeline.types import TestRef as MlTestRef

log = logging.getLogger(__name__)
HONESTY_LINE = "Flame is illustrative; verdicts come from NASA PSI data."
COLUMNS = ("step", "inputs", "state", "probability", "trust", "detection_s", "action", "sources")


def export_scenario(scenario_id: str) -> bytes:
    """Take one store snapshot; keep its history intact while adding labeled export context."""
    snapshot = store.get(scenario_id)  # ScenarioNotFound belongs to the router's 404 handler.
    inputs = snapshot["inputs"].model_copy(deep=True)
    results = ResultsOut(scenario_id=scenario_id, rows=snapshot["history"])
    recommendation = None
    try:
        recommendation = suppressor.suppress(scenario_id, inputs)
    except (OSError, ValueError, KeyError):
        log.warning("PDF recommendation unavailable for %s", scenario_id, exc_info=True)

    source_ids = list(dict.fromkeys(s for row in results.rows for s in row["sources"]))
    sources: dict[str, TestRef] = {}
    if source_ids:
        try:
            table = model.load_table()
            for row in table.loc[table["test_id"].isin(source_ids)].to_dict("records"):
                ref = predictor.to_test_ref(MlTestRef(**{k: row[k] for k in TestRef.model_fields}))
                sources[ref.test_id] = ref
        except (OSError, ValueError, KeyError):
            log.warning("PDF source metadata unavailable for %s", scenario_id, exc_info=True)
    if recommendation:
        chosen = next(a for a in recommendation.actions if a.action == recommendation.recommended)
        for ref in chosen.sources:
            sources.setdefault(ref.test_id, ref)
    return render_report(results, inputs, recommendation, list(sources.values()))


def render_report(
    results: ResultsOut,
    inputs: ScenarioIn,
    recommendation: SuppressOut | None,
    sources: list[TestRef],
    *,
    generated_at: datetime | None = None,
) -> bytes:
    """Render all eight history columns without rounding, truncating or changing saved values."""
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=32,
        rightMargin=32,
        topMargin=32,
        bottomMargin=32,
        title="FireTwin scenario report",
        author="FireTwin",
        pageCompression=0,
    )
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("HistoryCell", fontSize=7, leading=9, splitLongWords=True)

    def paragraph(value: str, style: str = "BodyText") -> Paragraph:
        return Paragraph(escape(value).replace("\n", "<br/>"), styles[style])

    story = [paragraph("FireTwin scenario report", "Title")]
    timestamp = (generated_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    story += [
        paragraph(f"Generated at (UTC): {timestamp}"),
        paragraph(f"Scenario: {results.scenario_id}"),
    ]
    story.append(paragraph(HONESTY_LINE))
    story.append(
        paragraph(
            "Probabilities and trust are model outputs, not measured outcomes. Detection times are "
            "illustrative estimates. Historical values below are copied from /results."
        )
    )
    refs = {ref.test_id: ref for ref in sources}

    def source_label(test_id: str) -> str:
        ref = refs.get(test_id)
        if ref is None:
            return f"{test_id} [UNVERIFIED: metadata unavailable; synthetic status unknown]"
        return f"{test_id} [SYNTHETIC; is_synthetic=true]" if ref.is_synthetic else test_id

    if any(ref.is_synthetic for ref in sources):
        story.append(
            paragraph("SYNTHETIC DATA: labeled sources are placeholders, not NASA evidence.")
        )
    story += [
        paragraph("Current scenario inputs", "Heading2"),
        paragraph(json.dumps(inputs.model_dump(mode="json"), ensure_ascii=True)),
        paragraph("Recorded results", "Heading2"),
    ]
    if not results.rows:
        story.append(paragraph("No recorded steps."))
    else:
        rows = [[Paragraph(name, cell_style) for name in COLUMNS]]
        for row in results.rows:
            cells = []
            for name in COLUMNS:
                value = (
                    "; ".join(source_label(s) for s in row[name]) or "[]"
                    if name == "sources"
                    else json.dumps(row[name], ensure_ascii=True)
                )
                cells.append(Paragraph(escape(value), cell_style))
            rows.append(cells)
        # Leave room for full float representations without splitting a number across lines.
        widths = [0.065, 0.25, 0.085, 0.13, 0.065, 0.13, 0.09, 0.185]
        table = LongTable(
            rows, colWidths=[doc.width * w for w in widths], repeatRows=1, splitInRow=1
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5edf3")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(table)

    story.append(paragraph("Recommended action", "Heading2"))
    if recommendation is None:
        story.append(paragraph("Unavailable: model or data not available. No action was invented."))
    else:
        chosen = next(a for a in recommendation.actions if a.action == recommendation.recommended)
        story.append(
            paragraph(
                "Calculated at export time for the current inputs; not a recorded history step. "
                "Ranking includes illustrative crew-risk and detection-delay assumptions."
            )
        )
        story.append(
            paragraph(f"{chosen.label} ({chosen.action}); data support: {chosen.data_support}")
        )
        story.append(paragraph(chosen.explanation))
        story.append(
            paragraph(
                "Sources: " + ("; ".join(source_label(s.test_id) for s in chosen.sources) or "none")
            )
        )

    story.append(paragraph("Sources with URLs", "Heading2"))
    story.append(
        paragraph(
            "Metadata is resolved from the current unified test table at export time; historical "
            "rows store only test IDs. Unresolved IDs have no verified URL or synthetic status."
        )
    )
    ids = list(dict.fromkeys([s for row in results.rows for s in row["sources"]] + list(refs)))
    if not ids:
        story.append(paragraph("No sources recorded."))
    for test_id in ids:
        ref = refs.get(test_id)
        story.append(paragraph(source_label(test_id)))
        if ref:
            story.append(paragraph(f"{ref.investigation}; {ref.fuel_type}; outcome: {ref.outcome}"))
            story.append(paragraph(f"Source URL: {ref.source_url or 'unavailable'}"))
        story.append(Spacer(1, 5))
    doc.build(story)
    return output.getvalue()
