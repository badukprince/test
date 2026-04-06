from typing import List, Optional

from pydantic import BaseModel, Field


class FenAnalyzeRequest(BaseModel):
    fen: str = Field(..., description="FEN string to evaluate")


class AnalysisResponse(BaseModel):
    score: float = Field(..., description="Positive: white advantage, negative: black advantage")
    advantage: str = Field(..., description="white | black | equal")
    reasoning: str
    reasoning_ko: str = Field(..., description="Korean translated reasoning")
    total_pieces: int = Field(..., description="Total piece count on board")
    white_pieces: int = Field(..., description="White piece count")
    black_pieces: int = Field(..., description="Black piece count")
    fen: Optional[str] = Field(default=None, description="Final FEN used for analysis")
    board_matrix: Optional[List[List[str]]] = Field(
        default=None, description="8x8 board representation from image heuristic"
    )
    source: str = Field(..., description="image | fen | image+fen")
