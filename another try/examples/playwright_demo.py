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


#Excel

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



#excel builder serviuce 
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