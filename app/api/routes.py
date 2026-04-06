from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.analysis import AnalysisResponse, FenAnalyzeRequest
from app.services.chess_engine import evaluate_fen
from app.services.image_processing import extract_board_from_image_bytes

router = APIRouter(prefix="/analyze", tags=["analysis"])


@router.post("/image", response_model=AnalysisResponse)
async def analyze_image(image: UploadFile = File(...)) -> AnalysisResponse:
    image_bytes = await image.read()
    try:
        board_matrix, extracted_fen, note = extract_board_from_image_bytes(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if extracted_fen is None:
        return AnalysisResponse(
            score=0.0,
            advantage="equal",
            reasoning=f"{note}. Please provide FEN for accurate evaluation.",
            fen=None,
            board_matrix=board_matrix,
            source="image",
        )

    try:
        score, advantage, reasoning = evaluate_fen(extracted_fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Extracted FEN invalid: {exc}") from exc

    return AnalysisResponse(
        score=score,
        advantage=advantage,
        reasoning=f"{note}. " + " | ".join(reasoning),
        fen=extracted_fen,
        board_matrix=board_matrix,
        source="image",
    )


@router.post("/fen", response_model=AnalysisResponse)
def analyze_fen(payload: FenAnalyzeRequest) -> AnalysisResponse:
    try:
        score, advantage, reasoning = evaluate_fen(payload.fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}") from exc

    return AnalysisResponse(
        score=score,
        advantage=advantage,
        reasoning=" | ".join(reasoning),
        fen=payload.fen,
        board_matrix=None,
        source="fen",
    )


@router.post("", response_model=AnalysisResponse)
async def analyze_combined(
    image: Optional[UploadFile] = File(default=None),
    fen: Optional[str] = Form(default=None),
) -> AnalysisResponse:
    board_matrix = None
    extracted_fen = None
    source = []
    image_note = ""

    if image is not None:
        image_bytes = await image.read()
        try:
            board_matrix, extracted_fen, image_note = extract_board_from_image_bytes(image_bytes)
            source.append("image")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    final_fen = fen or extracted_fen
    if fen:
        source.append("fen")

    if not final_fen:
        raise HTTPException(status_code=400, detail="Either image or fen must be provided")

    try:
        score, advantage, reasoning = evaluate_fen(final_fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}") from exc

    full_reasoning = " | ".join(reasoning)
    if image_note:
        full_reasoning = f"{image_note}. {full_reasoning}"

    return AnalysisResponse(
        score=score,
        advantage=advantage,
        reasoning=full_reasoning,
        fen=final_fen,
        board_matrix=board_matrix,
        source="+".join(source) if source else "fen",
    )
