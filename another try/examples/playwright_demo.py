import asyncio
from playwright.async_api import async_playwright
from agent_visualizer.visualizer import AgentVisualizer


async def run_agent():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # Step 1: Open Google
        await page.goto("https://www.google.com")

        await page.fill("textarea[name='q']", "Playwright Python tutorial")
        await page.keyboard.press("Enter")

        await page.wait_for_timeout(2000)

        await page.click("h3")

        await page.wait_for_timeout(3000)
        await browser.close()


if __name__ == "__main__":
    with AgentVisualizer() as visualizer:
        print("Live View URL:", visualizer.get_live_view_url())
        asyncio.run(run_agent())





"""
Class-based stateless service for QA Review Excel generation.
"""

import io
from itertools import groupby
from dataclasses import dataclass, field
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ── Palette ───────────────────────────────────────────────────────────────────
DARK_HEADER  = "1F3864"
MID_HEADER   = "2F5496"
LIGHT_HEADER = "D6E4F7"
YELLOW_INPUT = "FFFF00"
GREY_LEGEND  = "D9D9D9"
WHITE        = "FFFFFF"
ALT_ROW      = "EBF3FB"

# ── Fixed column definitions ──────────────────────────────────────────────────
LEFT_COLS = [
    ("Sample #",             8),
    ("Create Date",         12),
    ("Item\nType",           7),
    ("Business Unit",       14),
    ("Assigned To",         16),
    ("Step",                22),
    ("Work Item ID",        18),
    ("ECN #",               16),
    ("WCIS ID",             12),
    ("Customer Legal Name", 28),
    ("Event Type",          20),
]

RIGHT_COLS = [
    ("No Exception\nNoted/ Exception",          18),
    ("Prelim Quality-Assurance\nTeam Comments",  22),
    ("LOB Agrees/Disagree\nwith Exception",      18),
    ("LOB Response",                             18),
    ("Final Quality-Assurance\nTeam Comments",   22),
    ("Final Quality\nAssurance Decision",        18),
    ("Date Exception\nRemediated\n(if applicable)", 18),
]

LEFT_KEY_ORDER = [
    "sample_number", "create_date", "item_type", "business_unit",
    "assigned_to", "step", "work_item_id", "ecn_number",
    "wcis_id", "customer_legal_name", "event_type",
]

RIGHT_KEY_ORDER = [
    "exception_noted", "prelim_qa_comments", "lob_agrees",
    "lob_response", "final_qa_comments", "final_qa_decision",
    "date_exception_remediated",
]


# ── Pydantic / dataclass models ───────────────────────────────────────────────
@dataclass
class QAColumn:
    section: str
    attribute_code: str
    attribute_name: str
    sub_attribute: str


@dataclass
class QARecord:
    sample_number: int
    create_date: str
    item_type: str
    business_unit: str
    assigned_to: str
    step: str
    work_item_id: str
    ecn_number: str
    wcis_id: str
    customer_legal_name: str
    event_type: str
    qa_results: dict = field(default_factory=dict)
    exception_noted: str = ""
    prelim_qa_comments: str = ""
    lob_agrees: str = ""
    lob_response: str = ""
    final_qa_comments: str = ""
    final_qa_decision: str = ""
    date_exception_remediated: str = ""


@dataclass
class ExcelSchema:
    metadata: dict[str, Any]
    qa_columns: list[QAColumn]
    records: list[QARecord]

    @classmethod
    def from_dict(cls, data: dict) -> "ExcelSchema":
        return cls(
            metadata=data.get("metadata", {}),
            qa_columns=[QAColumn(**c) for c in data.get("qa_columns", [])],
            records=[QARecord(**r) for r in data.get("records", [])],
        )


# ── Service ───────────────────────────────────────────────────────────────────
class ExcelBuilderService:
    """Stateless service. Instantiate once via DI, call methods per request."""

    # ── Public methods ────────────────────────────────────────────────────────

    def build_excel(self, schema: ExcelSchema) -> bytes:
        wb = Workbook()
        wb.remove(wb.active)
        self._build_summary_sheet(wb, schema.metadata)
        self._build_status_sheet(wb, schema)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def build_sample_excel(self) -> bytes:
        schema = ExcelSchema.from_dict({**self._sample_schema(), "records": []})
        return self.build_excel(schema)

    def get_sample_schema(self) -> dict:
        return self._sample_schema()

    # ── Sheet: Summary ────────────────────────────────────────────────────────

    def _build_summary_sheet(self, wb: Workbook, meta: dict):
        ws = wb.create_sheet("Summary")
        ws.sheet_view.showGridLines = False
        ws.column_dimensions["A"].width = 3
        ws.column_dimensions["B"].width = 28
        ws.column_dimensions["C"].width = 60

        meta_rows = [
            ("QA Review Program",      meta.get("qa_review_program",      "")),
            ("Review being Performed",  meta.get("review_being_performed", "")),
            ("Month Testing Performed", meta.get("month_testing_performed","")),
            ("Consultant",              meta.get("consultant",             "")),
            ("Production Month",        meta.get("production_month",       "")),
            ("Population Size",         meta.get("population_size",        "")),
            ("Sample Size",             meta.get("sample_size",            "")),
            ("Sample Size Methodology", meta.get("sample_size_methodology","")),
        ]
        for i, (label, value) in enumerate(meta_rows, start=1):
            lbl = ws.cell(row=i, column=2, value=label)
            val = ws.cell(row=i, column=3, value=value)
            lbl.font      = self._font(bold=True, size=10)
            lbl.fill      = self._fill(GREY_LEGEND)
            lbl.alignment = self._align(h="right")
            lbl.border    = self._border()
            val.font      = self._font(size=10)
            val.fill      = self._fill(GREY_LEGEND)
            val.alignment = self._align(h="left")
            val.border    = self._border()
            ws.row_dimensions[i].height = 28 if label == "Sample Size Methodology" else 18

        legend_start = len(meta_rows) + 3
        legend_items = [
            ("Testing Legend", "",     True),
            ("Y =", "Yes – Attribute Satisfied; No exception noted.", False),
            ("N =", "No – Attribute NOT Satisfied; Exception noted.", False),
            ("NA",  "Test procedure not applicable to sample.",       False),
        ]
        for j, (code, desc, is_header) in enumerate(legend_items, start=legend_start):
            c = ws.cell(row=j, column=2, value=code)
            d = ws.cell(row=j, column=3, value=desc)
            for cell in (c, d):
                cell.fill   = self._fill(GREY_LEGEND)
                cell.border = self._border()
                cell.font   = self._font(bold=is_header, size=10)
            if is_header:
                ws.merge_cells(start_row=j, start_column=2, end_row=j, end_column=3)
                c.alignment = self._align(h="center")
            else:
                c.alignment = self._align(h="center")
                d.alignment = self._align(h="left")
            ws.row_dimensions[j].height = 18

    # ── Sheet: Event Closed Status ────────────────────────────────────────────

    def _build_status_sheet(self, wb: Workbook, schema: ExcelSchema):
        ws = wb.create_sheet("Event Closed Status")
        ws.freeze_panes = "A5"
        ws.sheet_view.showGridLines = False

        qa_cols  = schema.qa_columns
        records  = schema.records
        n_left   = len(LEFT_COLS)
        n_qa     = len(qa_cols)
        n_right  = len(RIGHT_COLS)
        total    = n_left + n_qa + n_right

        # column widths
        for i, (_, w) in enumerate(LEFT_COLS, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for i in range(n_qa):
            ws.column_dimensions[get_column_letter(n_left + 1 + i)].width = 16
        for i, (_, w) in enumerate(RIGHT_COLS):
            ws.column_dimensions[get_column_letter(n_left + n_qa + 1 + i)].width = w

        # row heights
        ws.row_dimensions[1].height = 40
        ws.row_dimensions[2].height = 70
        ws.row_dimensions[3].height = 90
        ws.row_dimensions[4].height = 14

        self._write_section_row(ws, qa_cols, n_left, n_right)
        self._write_attribute_row(ws, qa_cols, n_left, n_right)
        self._write_subattribute_row(ws, qa_cols, n_left, n_right)

        # blank filter row
        for col in range(1, total + 1):
            c = ws.cell(row=4, column=col, value="")
            c.fill   = self._fill(LIGHT_HEADER)
            c.border = self._border()

        for row_idx, rec in enumerate(records, start=5):
            self._write_data_row(ws, rec, qa_cols, n_left, row_idx)

        ws.auto_filter.ref = f"A4:{get_column_letter(total)}4"

    def _write_section_row(self, ws, qa_cols, n_left, n_right):
        self._merge_cell(ws, 1, 1, 1, n_left, "", DARK_HEADER, "FFFFFF", bold=True)
        col_cursor = n_left + 1
        for section_name, group in self._group_sections(qa_cols):
            span = len(group)
            self._merge_cell(ws, 1, col_cursor, 1, col_cursor + span - 1,
                             section_name, DARK_HEADER, "FFFFFF", bold=True)
            col_cursor += span
        right_start = n_left + len(qa_cols) + 1
        self._merge_cell(ws, 1, right_start, 1, right_start + n_right - 1,
                         "", DARK_HEADER, "FFFFFF", bold=True)

    def _write_attribute_row(self, ws, qa_cols, n_left, n_right):
        for i, (label, _) in enumerate(LEFT_COLS, start=1):
            self._header_cell(ws, 2, i, label, MID_HEADER)
        for i, col in enumerate(qa_cols):
            label = f"{col.attribute_code}: {col.attribute_name}"
            self._header_cell(ws, 2, n_left + 1 + i, label, MID_HEADER, size=8)
        right_start = n_left + len(qa_cols) + 1
        for i, (label, _) in enumerate(RIGHT_COLS):
            self._header_cell(ws, 2, right_start + i, label, MID_HEADER)

    def _write_subattribute_row(self, ws, qa_cols, n_left, n_right):
        for i, (label, _) in enumerate(LEFT_COLS, start=1):
            self._header_cell(ws, 3, i, label, LIGHT_HEADER, font_color="000000")
        for i, col in enumerate(qa_cols):
            c = ws.cell(row=3, column=n_left + 1 + i, value=col.sub_attribute)
            c.font      = self._font(size=8)
            c.fill      = self._fill(YELLOW_INPUT)
            c.alignment = self._align()
            c.border    = self._border()
        right_start = n_left + len(qa_cols) + 1
        for i, (label, _) in enumerate(RIGHT_COLS):
            self._header_cell(ws, 3, right_start + i, label, LIGHT_HEADER, font_color="000000")

    def _write_data_row(self, ws, rec: QARecord, qa_cols, n_left, row_idx):
        row_fill = ALT_ROW if row_idx % 2 == 0 else WHITE
        for col_idx, key in enumerate(LEFT_KEY_ORDER):
            col = col_idx + 1
            val = getattr(rec, key, "")
            c = ws.cell(row=row_idx, column=col, value=val)
            c.font      = self._font(size=9)
            c.fill      = self._fill(row_fill)
            c.alignment = self._align(h="left" if col_idx == 9 else "center")
            c.border    = self._border()
        for i, col_def in enumerate(qa_cols):
            col = n_left + 1 + i
            val = rec.qa_results.get(col_def.attribute_code, "")
            c = ws.cell(row=row_idx, column=col, value=val)
            c.font      = self._font(size=9)
            c.fill      = self._fill(YELLOW_INPUT)
            c.alignment = self._align()
            c.border    = self._border()
        right_start = n_left + len(qa_cols) + 1
        for col_idx, key in enumerate(RIGHT_KEY_ORDER):
            col = right_start + col_idx
            val = getattr(rec, key, "")
            c = ws.cell(row=row_idx, column=col, value=val)
            c.font      = self._font(size=9)
            c.fill      = self._fill(row_fill)
            c.alignment = self._align()
            c.border    = self._border()

    # ── Style helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _font(bold=False, color="000000", size=9, name="Arial") -> Font:
        return Font(bold=bold, color=color, size=size, name=name)

    @staticmethod
    def _fill(hex_color: str) -> PatternFill:
        return PatternFill("solid", fgColor=hex_color)

    @staticmethod
    def _align(h="center", v="center", wrap=True) -> Alignment:
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    @staticmethod
    def _border() -> Border:
        t = Side(border_style="thin", color="000000")
        return Border(left=t, right=t, top=t, bottom=t)

    def _header_cell(self, ws, row, col, value, bg,
                     font_color="FFFFFF", bold=True, size=9):
        c = ws.cell(row=row, column=col, value=value)
        c.font      = self._font(bold=bold, color=font_color, size=size)
        c.fill      = self._fill(bg)
        c.alignment = self._align()
        c.border    = self._border()
        return c

    def _merge_cell(self, ws, r1, c1, r2, c2, value,
                    bg, font_color="000000", bold=False, size=10):
        if r1 != r2 or c1 != c2:
            ws.merge_cells(start_row=r1, start_column=c1,
                           end_row=r2,   end_column=c2)
        cell = ws.cell(row=r1, column=c1, value=value)
        cell.font      = self._font(bold=bold, color=font_color, size=size)
        cell.fill      = self._fill(bg)
        cell.alignment = self._align()
        cell.border    = self._border()
        return cell

    # ── Section grouping ──────────────────────────────────────────────────────

    @staticmethod
    def _group_sections(qa_cols: list[QAColumn]):
        result = []
        for key, group in groupby(qa_cols, key=lambda x: x.section):
            result.append((key, list(group)))
        return result

    # ── Sample schema ─────────────────────────────────────────────────────────

    @staticmethod
    def _sample_schema() -> dict:
        return {
            "metadata": {
                "qa_review_program": "Event Driven Reviews (EDR)",
                "review_being_performed": "Event Closed",
                "month_testing_performed": "January",
                "consultant": "Firas Faraj & Keishia Lindsey",
                "production_month": "December",
                "population_size": 1670,
                "sample_size": 145,
                "sample_size_methodology": (
                    "Utilizes the Wells Fargo Independent Risk Management (IRM) "
                    "Sample Size Calculator to determine sample sizes when conducting reviews."
                ),
            },
            "qa_columns": [
                {
                    "section": "Event Creation",
                    "attribute_code": "A1",
                    "attribute_name": "Validate Event Description is complete",
                    "sub_attribute": "A1a – Validate the event description is complete (for purposes of review)",
                },
                {
                    "section": "Event Creation",
                    "attribute_code": "A2",
                    "attribute_name": "Validate Recommendation Rationale aligns with Recommended Action",
                    "sub_attribute": "A2a – If EDR Event type is not Priority FC Business Referral, validate the recommendation rationale aligns with risk action recommendation type",
                },
                {
                    "section": "Event Creation",
                    "attribute_code": "A3",
                    "attribute_name": "Validate Recommendation Rationale aligns with Event Description",
                    "sub_attribute": "A3a – If EDR event type is not Priority FC Business Referral, validate the recommendation rationale aligns with the event description",
                },
                {
                    "section": "Level 1 Review (Priority FC Business)",
                    "attribute_code": "B1",
                    "attribute_name": "Validate Recommendation Rationale aligns with Recommended Action",
                    "sub_attribute": "B1a – Validate the recommendation rationale aligns with risk action recommendation type",
                },
                {
                    "section": "Level 1 Review (Priority FC Business)",
                    "attribute_code": "B2",
                    "attribute_name": "Validate Recommendation Rationale aligns with Event Description",
                    "sub_attribute": "B2a – Validate the recommendation rationale is reasonable based on the details of the event description",
                },
                {
                    "section": "Level 2 Review",
                    "attribute_code": "C1",
                    "attribute_name": "Validate the decision rationale aligns with decision type",
                    "sub_attribute": "C1a – Validate the decision rationale aligns with the risk decision type",
                },
                {
                    "section": "Level 2 Review",
                    "attribute_code": "C2",
                    "attribute_name": "Validate the decision rationale aligns with Event Description and Recommended Action Rationale",
                    "sub_attribute": "C2a – Validate the decision rationale aligns with Event Description and Recommended Action Rationale",
                },
                {
                    "section": "Level 2 Review",
                    "attribute_code": "C3",
                    "attribute_name": "Validate Level 2 Rationale does not list incorrect group that made recommendation",
                    "sub_attribute": "C3a – Based on the above grid, either ensure no reference is made to recommending group or the correct group is referenced in rationale, based on Event Type and Brokerage field",
                },
                {
                    "section": "Level 2 Review",
                    "attribute_code": "C4",
                    "attribute_name": "Validate if all the Elevated Approvals 1 obtained per requirements",
                    "sub_attribute": "C4a – Confirm if approver decision and rationale were obtained for all Elevated Approvals 1",
                },
                {
                    "section": "Initiation of Decision Execution",
                    "attribute_code": "D1",
                    "attribute_name": "Validate if the profile refresh request was referred to the appropriate process",
                    "sub_attribute": "D1a – Is the profile refresh referred to the appropriate group and evidence provided to QA",
                },
                {
                    "section": "Initiation of Decision Execution",
                    "attribute_code": "D2",
                    "attribute_name": "Validate if the Risk Rating Override request was referred to the appropriate process",
                    "sub_attribute": "D2a – Is a risk rating override request present in the risk rating override appropriate group and Actimize workflow for this event (Actimize only)",
                },
                {
                    "section": "Initiation of Decision Execution",
                    "attribute_code": "D3",
                    "attribute_name": "Validate if customer exit request was referred to the appropriate process",
                    "sub_attribute": "D3a – Is the Exit referred to the appropriate group and evidence provided to QA",
                },
            ],
            "records": [],
        }


#excel.py
"""
Excel generation endpoints.

Endpoints:
    GET  /api/v1/excel/sample   – Download blank sample Excel
    POST /api/v1/excel/generate – Generate filled Excel from JSON schema
    GET  /api/v1/excel/schema   – Return example JSON schema
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from typing import Any

from src.application.services.excel_builder_service import (
    ExcelBuilderService,
    ExcelSchema,
)

logger = logging.getLogger(__name__)

# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(
    prefix="/excel",
    tags=["excel"],
)

# ── Dependency: singleton service via FastAPI DI ──────────────────────────────
_service_instance = ExcelBuilderService()


def get_excel_service() -> ExcelBuilderService:
    return _service_instance


# ── Pydantic request model ────────────────────────────────────────────────────
class QAColumnRequest(BaseModel):
    section: str
    attribute_code: str
    attribute_name: str
    sub_attribute: str


class QARecordRequest(BaseModel):
    sample_number: int
    create_date: str
    item_type: str
    business_unit: str
    assigned_to: str = ""
    step: str
    work_item_id: str
    ecn_number: str
    wcis_id: str
    customer_legal_name: str
    event_type: str
    qa_results: dict[str, str] = Field(default_factory=dict)
    exception_noted: str = ""
    prelim_qa_comments: str = ""
    lob_agrees: str = ""
    lob_response: str = ""
    final_qa_comments: str = ""
    final_qa_decision: str = ""
    date_exception_remediated: str = ""


class GenerateExcelRequest(BaseModel):
    metadata: dict[str, Any]
    qa_columns: list[QAColumnRequest]
    records: list[QARecordRequest]


# ── Helper: stream Excel bytes ────────────────────────────────────────────────
def _excel_response(excel_bytes: bytes, filename: str) -> StreamingResponse:
    import io
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/sample",
    summary="Download blank sample Excel",
    response_description="Returns a .xlsx file with the QA review format and no data rows",
    status_code=status.HTTP_200_OK,
)
def download_sample(
    service: ExcelBuilderService = Depends(get_excel_service),
):
    """
    Download a blank sample Excel workbook that demonstrates
    the full QA review format — useful for previewing the
    expected structure before uploading real data.
    """
    logger.info("Sample Excel download requested")
    try:
        excel_bytes = service.build_sample_excel()
        logger.info("Sample Excel generated successfully, size=%d bytes", len(excel_bytes))
        return _excel_response(excel_bytes, "QA_Review_Sample_Format.xlsx")
    except Exception as exc:
        logger.exception("Failed to generate sample Excel")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Excel generation failed: {exc}",
        )


@router.post(
    "/generate",
    summary="Generate filled Excel from JSON schema",
    response_description="Returns a filled .xlsx file based on the provided schema",
    status_code=status.HTTP_200_OK,
)
def generate_excel(
    payload: GenerateExcelRequest,
    service: ExcelBuilderService = Depends(get_excel_service),
):
    """
    Accepts a JSON schema containing metadata, dynamic QA columns,
    and data records, then returns a fully formatted Excel workbook.

    The `qa_columns` array is **dynamic** — add or remove attribute
    objects to grow or shrink the yellow QA section automatically.
    """
    logger.info(
        "Excel generation requested | records=%d, qa_columns=%d",
        len(payload.records),
        len(payload.qa_columns),
    )
    try:
        schema = ExcelSchema.from_dict(payload.model_dump())
        excel_bytes = service.build_excel(schema)
        production_month = payload.metadata.get("production_month", "Report")
        filename = f"QA_Review_{production_month}.xlsx"
        logger.info("Excel generated successfully | file=%s, size=%d bytes",
                    filename, len(excel_bytes))
        return _excel_response(excel_bytes, filename)
    except Exception as exc:
        logger.exception("Failed to generate Excel from schema")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Excel generation failed: {exc}",
        )


@router.get(
    "/schema",
    summary="Get example JSON schema",
    response_description="Returns the full example request schema for /generate",
    status_code=status.HTTP_200_OK,
)
def get_schema_example(
    service: ExcelBuilderService = Depends(get_excel_service),
):
    """
    Returns a complete example JSON payload that can be sent
    to `POST /excel/generate`, pre-populated with sample data
    including all supported QA columns.
    """
    logger.info("Schema example requested")
    return JSONResponse(content=service.get_sample_schema())


# ── Health sub-check (reachable at GET /excel/health) ────────────────────────
@router.get(
    "/health",
    summary="Excel service health check",
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
def excel_health():
    return {
        "service": "excel",
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }