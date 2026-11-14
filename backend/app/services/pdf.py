"""PDF export (BE-09): the results table of one scenario as a PDF, built with ReportLab.

Built from the same history rows as GET /results, so the PDF always matches the dashboard.
No FastAPI imports.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import ScenarioIn
from ml.pipeline import model

log = logging.getLogger(__name__)

HONESTY_LINE = "Flame is illustrative; verdicts come from NASA PSI data."
COLUMNS = ("step", "action", "state", "probability", "trust", "detection_s", "inputs", "sources")


def _cell(key: str, value) -> str:
    if value is None:
        return "-"
    if key == "probability":
        return f"{value:.2f}"
    if key == "inputs":
        return (
            f"{value['material']}, O2 {value['o2_pct']:g} %, {value['pressure_kpa']:g} kPa, "
            f"flow {value['flow_speed_cm_s']:g} cm/s"
        )
    if key == "sources":
        return ", ".join(value) or "-"
    return str(value)


def _source_lines(rows: list[dict]) -> list[str]:
    """One line per cited test: id, investigation, URL, and a SYNTHETIC tag where it applies."""
    ids = list(dict.fromkeys(test_id for row in rows for test_id in row.get("sources") or []))
    if not ids:
        return []
    table = model.load_table().set_index("test_id")
    lines = []
    for test_id in ids:
        if test_id not in table.index:
            lines.append(f"{test_id}: not found in the test table")
            continue
        row = table.loc[test_id]
        tag = " [SYNTHETIC placeholder, not a NASA test]" if bool(row["is_synthetic"]) else ""
        lines.append(f"{test_id} ({row['investigation']}): {row['source_url']}{tag}")
    return lines


def build_pdf(
    scenario_id: str, inputs: ScenarioIn, rows: list[dict], recommended: str | None
) -> bytes:
    """Return the PDF bytes for one scenario's history."""
    try:
        styles = getSampleStyleSheet()
        body = styles["BodyText"]
        small = body.clone("small", fontSize=7, leading=9)
        data = [list(COLUMNS)] + [
            [Paragraph(_cell(key, row.get(key)), small) for key in COLUMNS] for row in rows
        ]
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        flow = [
            Paragraph("FireTwin results", styles["Title"]),
            Paragraph(f"Scenario {scenario_id} - generated {stamp}", body),
            Paragraph("Scenario inputs", styles["Heading2"]),
            Paragraph(_cell("inputs", inputs.model_dump()), body),
            Paragraph("Results", styles["Heading2"]),
            table,
            Spacer(1, 8),
            Paragraph("Recommended action", styles["Heading2"]),
            Paragraph(recommended or "none (no suppression ranking was possible)", body),
            Paragraph("Sources", styles["Heading2"]),
            *[Paragraph(line, small) for line in (_source_lines(rows) or ["No sources recorded."])],
            Spacer(1, 8),
            Paragraph(HONESTY_LINE, body),
        ]
        buffer = io.BytesIO()
        SimpleDocTemplate(buffer, pagesize=landscape(A4), title="FireTwin results").build(flow)
        return buffer.getvalue()
    except Exception:
        log.exception("pdf.build_pdf failed for scenario_id=%s (%d rows)", scenario_id, len(rows))
        raise
