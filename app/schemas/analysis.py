from typing import List, Optional

from pydantic import BaseModel, Field


class FenAnalyzeRequest(BaseModel):
    fen: str = Field(..., description="FEN string to evaluate")


class AnalysisResponse(BaseModel):
    score: float = Field(..., description="Positive: white advantage, negative: black advantage")
    advantage: str = Field(..., description="white | black | equal")
    reasoning: str
    fen: Optional[str] = Field(default=None, description="Final FEN used for analysis")
    board_matrix: Optional[List[List[str]]] = Field(
        default=None, description="8x8 board representation from image heuristic"
    )
    source: str = Field(..., description="image | fen | image+fen")
