# Chess Analyzer MLOps Backend

체스판 이미지를 업로드하거나 FEN 문자열을 입력해 보드 상태를 분석하고, 어느 쪽이 유리한지 평가하는 FastAPI 백엔드 프로젝트입니다.

이 프로젝트는 완벽한 체스 인식보다 **현실적인 타협형 구조**를 목표로 합니다.

- 이미지 분석은 OpenCV 기반 heuristic 방식 (근사)
- 필요 시 사용자가 FEN으로 보정
- 평가 로직은 python-chess + 결정론적 점수 함수
- Docker 및 GitHub Actions 기반 CI/CD 포함

## 프로젝트 구조

```text
project/
├── main.py
├── requirements.txt
├── Dockerfile
├── README.md
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── .github/
│   └── workflows/
│       └── ci.yml
└── app/
    ├── api/
    │   └── routes.py
    ├── core/
    │   └── config.py
    ├── services/
    │   ├── image_processing.py
    │   └── chess_engine.py
    └── schemas/
        └── analysis.py
```

## 로컬 실행 방법

1) 의존성 설치

```bash
pip install -r requirements.txt
```

2) 서버 실행

```bash
uvicorn main:app --reload
```

3) 문서 확인

- Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

4) 웹 UI

- 브라우저에서 `http://localhost:8000/` 접속
- 통합 분석(이미지+FEN), FEN 전용, 이미지 전용 탭에서 호출 가능

## API 개요

### 1) 이미지 분석

- Endpoint: `POST /analyze/image`
- Input: multipart/form-data, `image` 파일
- 동작:
  - 이미지를 8x8 grid로 분할
  - edge density + 밝기 기반으로 occupancy를 근사 추정
  - 추정 결과를 간단한 FEN으로 변환 후 평가

예시:

```bash
curl -X POST "http://localhost:8000/analyze/image" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "image=@board.jpg"
```

### 2) FEN 분석

- Endpoint: `POST /analyze/fen`
- Input(JSON):

```json
{
  "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
}
```

- 평가 요소:
  - 기물 점수: pawn=1, knight=3, bishop=3, rook=5, queen=9
  - 체크/체크메이트 가중치
  - 중앙 장악 보너스(간단)

### 3) 통합 분석

- Endpoint: `POST /analyze`
- Input:
  - `image` (optional, file)
  - `fen` (optional, form field)
- 동작:
  - image가 있으면 우선 보드 추출 시도
  - 불완전하거나 보정 필요 시 fen 사용
  - 최종 FEN 기준으로 평가 결과 반환

예시:

```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "image=@board.jpg" \
  -F "fen=rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
```

## Docker 실행

1) 이미지 빌드

```bash
docker build -t chess-analyzer-api .
```

2) 컨테이너 실행

```bash
docker run --rm -p 8000:8000 chess-analyzer-api
```

## GitHub Actions CI/CD

워크플로 파일: `.github/workflows/ci.yml`

자동화 동작:

- **PR to `main`**
  - Python 의존성 설치
  - 컴파일 sanity check
  - FastAPI 스모크 테스트 (`/health`, `/analyze/fen`)
  - Docker build 검증
- **push to `main` / `develop`**
  - 위 CI 검증 실행
- **push to `main` 또는 `v*` 태그**
  - CI 통과 후 Docker Hub 이미지 push (CD)
- **push to `main` (self-hosted runner 실행 호스트)**
  - Docker Hub 최신 이미지 pull
  - 기존 `chess-analyzer` 컨테이너 중지/삭제
  - 새 컨테이너 자동 실행(`--restart unless-stopped`)
  - `/health` 자동 확인

필요한 GitHub Secrets:

- `DOCKER_USERNAME`
- `DOCKER_PASSWORD`

이미지 이름 포맷:

- `${DOCKER_USERNAME}/chess-analyzer-api`

권장 릴리즈 방식:

- 메인 배포: `main` 브랜치 push
- 버전 배포: `git tag v1.0.0 && git push origin v1.0.0`

로컬 자동 배포 전제 조건:

- self-hosted runner가 배포 대상 로컬 PC에서 실행 중이어야 함
- 로컬 PC에 Docker Desktop(또는 Docker Engine) 실행 중이어야 함
- `8000` 포트를 다른 프로세스가 점유하지 않아야 함
