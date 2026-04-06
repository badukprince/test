from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.analysis import AnalysisResponse, FenAnalyzeRequest
from app.services.chess_engine import evaluate_fen, get_piece_counts
from app.services.image_processing import extract_board_from_image_bytes

router = APIRouter(prefix="/analyze", tags=["analysis"])


def _translate_reasoning_to_korean(text: str) -> str:
    translated = text
    replacements = [
        ("material score", "기물 점수"),
        ("center control bonus", "중앙 장악 보너스"),
        ("positional bonus (center occupancy)", "위치 점수 보너스(중앙 점유)"),
        ("checkmate detected: white to move is mated", "체크메이트: 백 차례이며 백이 메이트 상태"),
        ("checkmate detected: black to move is mated", "체크메이트: 흑 차례이며 흑이 메이트 상태"),
        ("white king is in check", "백 킹이 체크 상태"),
        ("black king is in check", "흑 킹이 체크 상태"),
        ("Detected", "검출됨:"),
        ("occupied squares", "점유 칸"),
        ("cell background subtraction + contour/texture scoring", "칸 배경 차분 + 윤곽/텍스처 점수"),
        ("Piece letters are light/dark approximations, not exact piece classification.", "기물 문자는 밝기 기반 근사이며, 정확한 기물 종류 분류는 아닙니다."),
        ("No clear pieces detected from image heuristic", "이미지 휴리스틱에서 명확한 기물이 검출되지 않았습니다"),
        ("Please provide FEN for accurate evaluation.", "정확한 평가를 위해 FEN을 입력해 주세요."),
    ]
    for en, ko in replacements:
        translated = translated.replace(en, ko)
    return translated


def _count_from_matrix(board_matrix: list[list[str]]) -> tuple[int, int, int]:
    white = sum(1 for row in board_matrix for cell in row if cell.isupper())
    black = sum(1 for row in board_matrix for cell in row if cell.islower())
    return white + black, white, black


@router.post("/image", response_model=AnalysisResponse)
async def analyze_image(image: UploadFile = File(...)) -> AnalysisResponse:
    image_bytes = await image.read()
    try:
        board_matrix, extracted_fen, note = extract_board_from_image_bytes(image_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if extracted_fen is None:
        total, white, black = _count_from_matrix(board_matrix)
        reason_en = f"{note}. Please provide FEN for accurate evaluation."
        return AnalysisResponse(
            score=0.0,
            advantage="equal",
            reasoning=reason_en,
            reasoning_ko=_translate_reasoning_to_korean(reason_en),
            total_pieces=total,
            white_pieces=white,
            black_pieces=black,
            is_check=False,
            is_checkmate=False,
            check_side="none",
            fen=None,
            board_matrix=board_matrix,
            source="image",
        )

    try:
        score, advantage, reasoning, status = evaluate_fen(extracted_fen)
        total, white, black = get_piece_counts(extracted_fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Extracted FEN invalid: {exc}") from exc

    reason_en = f"{note}. " + " | ".join(reasoning)
    return AnalysisResponse(
        score=score,
        advantage=advantage,
        reasoning=reason_en,
        reasoning_ko=_translate_reasoning_to_korean(reason_en),
        total_pieces=total,
        white_pieces=white,
        black_pieces=black,
        is_check=bool(status["is_check"]),
        is_checkmate=bool(status["is_checkmate"]),
        check_side=str(status["check_side"]),
        fen=extracted_fen,
        board_matrix=board_matrix,
        source="image",
    )


@router.post("/fen", response_model=AnalysisResponse)
def analyze_fen(payload: FenAnalyzeRequest) -> AnalysisResponse:
    try:
        score, advantage, reasoning, status = evaluate_fen(payload.fen)
        total, white, black = get_piece_counts(payload.fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}") from exc

    reason_en = " | ".join(reasoning)
    return AnalysisResponse(
        score=score,
        advantage=advantage,
        reasoning=reason_en,
        reasoning_ko=_translate_reasoning_to_korean(reason_en),
        total_pieces=total,
        white_pieces=white,
        black_pieces=black,
        is_check=bool(status["is_check"]),
        is_checkmate=bool(status["is_checkmate"]),
        check_side=str(status["check_side"]),
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
        score, advantage, reasoning, status = evaluate_fen(final_fen)
        total, white, black = get_piece_counts(final_fen)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid FEN: {exc}") from exc

    full_reasoning = " | ".join(reasoning)
    if image_note:
        full_reasoning = f"{image_note}. {full_reasoning}"

    return AnalysisResponse(
        score=score,
        advantage=advantage,
        reasoning=full_reasoning,
        reasoning_ko=_translate_reasoning_to_korean(full_reasoning),
        total_pieces=total,
        white_pieces=white,
        black_pieces=black,
        is_check=bool(status["is_check"]),
        is_checkmate=bool(status["is_checkmate"]),
        check_side=str(status["check_side"]),
        fen=final_fen,
        board_matrix=board_matrix,
        source="+".join(source) if source else "fen",
    )
