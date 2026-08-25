#!/usr/bin/env bash
# 백엔드(FastAPI + OCR + TTS)를 Hugging Face Space에 배포한다.
#
# 지금까지는 윈도우의 `deploy/api-space` 브랜치에서 올렸다. 그 브랜치에는 배포 전용
# 커밋이 쌓여 있어 무엇이 실제로 돌고 있는지 GitHub만 봐서는 알 수 없었다. 이 스크립트는
# **GitHub의 브랜치(기본 main)를 그대로 꺼내서** 올리므로, 배포본 = 그 브랜치가 된다.
#
# 쓰는 법:
#   deploy/api-space/deploy.sh                       main을 HJU5022/K_Menu에 배포
#   deploy/api-space/deploy.sh feat/무언가            다른 브랜치를 배포
#   deploy/api-space/deploy.sh main HJU5022/다른Space
#
# **대상 Space를 통째로 덮어쓴다(--force).**
#
# 처음 한 번은 Hugging Face 로그인이 필요하다:
#   ocr_test_env/bin/hf auth login      (git credential 등록에 y)

set -euo pipefail

REF="${1:-main}"
SPACE_ID="${2:-HJU5022/K_Menu}"
SPACE_URL="https://huggingface.co/spaces/$SPACE_ID"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT

# 이 Space는 **계산만** 한다. 서버가 실행에 쓰지 않는 것은 올리지 않는다.
#
# 바이너리를 품고 있어 반드시 빼야 하는 것 — Hugging Face는 LFS 없이 올라오는
# 바이너리를 거부한다:
#   mobile/    Flutter 앱 (iOS 리소스·아이콘)
#   eval/      평가 스크립트와 결과 이미지
#   frontend/  React 웹 화면 — 별도 Space로 배포한다(frontend/space/deploy.sh)
#
# 실행에 안 쓰여서 빼는 것 (2.4MB 중 1.1MB를 차지한다):
#   tests/       테스트
#   docs/        문서
#   app.py       Streamlit 웹 화면 — 화면은 React로 옮겼고, 이 서버와 무관하다
#   .streamlit/  Streamlit 테마 설정
#
# models/ 와 data/ 는 README 한 장씩(각 4KB)이라 남긴다 — 코드 주석이 그 문서를
# 가리키므로, 컨테이너 안에서 코드를 읽을 때 링크가 끊기지 않는다.
EXCLUDE_PATHS=(
  ':(exclude)mobile' ':(exclude)eval' ':(exclude)frontend'
  ':(exclude)tests' ':(exclude)docs' ':(exclude)app.py' ':(exclude).streamlit'
)

echo "==> 대상 Space: $SPACE_ID"
echo "    올릴 것: $REF (이 Space의 기존 내용은 통째로 덮어쓴다)"

cd "$REPO_DIR"
echo "==> $REF 의 파일을 꺼낸다"
# git archive는 **커밋에 들어 있는 파일만** 꺼낸다. 작업 중인 수정이나 추적되지 않는
# 파일이 섞이지 않으므로, 올라간 것이 그 커밋과 정확히 같다고 말할 수 있다.
# 제외할 폴더는 꺼낸 뒤 지우는 게 아니라 **애초에 꺼내지 않는다.** 파일을 지우는 명령을
# 배포 절차에 두면, 경로가 하나 잘못됐을 때 지우면 안 되는 것을 지운다.
git archive "$REF" -- . "${EXCLUDE_PATHS[@]}" | tar -x -C "$STAGING_DIR"

echo "==> Space 설정 README로 교체"
cp "$REPO_DIR/deploy/api-space/README.md" "$STAGING_DIR/README.md"

# 미리 만들어둔 안내 음성 50개. .gitignore에 걸려 GitHub에는 없지만, 이게 없으면
# 요청마다 TTS를 새로 돌려 음식 하나에 60초 이상 걸린다(캐시가 있으면 0.8초).
echo "==> 음성 캐시 넣기"
if [ ! -d "$REPO_DIR/static/tts_cache" ]; then
  echo "static/tts_cache 가 없다. 음성 캐시 없이 배포하면 응답이 매우 느려진다." >&2
  exit 1
fi
mkdir -p "$STAGING_DIR/static/tts_cache"
cp "$REPO_DIR/static/tts_cache"/*.wav "$STAGING_DIR/static/tts_cache/"
echo "    wav $(ls "$STAGING_DIR/static/tts_cache" | wc -l | tr -d ' ')개"

echo "==> Space에 올리기"
cd "$STAGING_DIR"
git init -q

# 음성 파일은 Git LFS로 보낸다. .gitattributes는 git add보다 **먼저** 있어야 한다.
git lfs install --local >/dev/null
cat > .gitattributes <<'ATTRS'
*.wav filter=lfs diff=lfs merge=lfs -text
*.jpg filter=lfs diff=lfs merge=lfs -text
*.png filter=lfs diff=lfs merge=lfs -text
ATTRS

git add -A
# 저장소의 .gitignore에 `static/`이 들어 있고, 그 파일이 여기까지 딸려 나온다. 그래서
# 음성 캐시를 복사해 두어도 git이 무시해 버린다(실측 2026-08-25: wav 0개로 배포됐다).
# -f로 그 무시를 넘어선다. 이 임시 저장소에는 우리가 넣은 것만 있으므로 안전하다.
git add -f static

# 올라가야 할 음성이 실제로 담겼는지 확인한다. 없이 배포되면 서버는 뜨지만 음식 하나에
# 60초 이상 걸려서, 배포한 뒤에야 느리다는 것을 알게 된다.
staged_wav=$(git diff --cached --name-only | grep -c '\.wav$' || true)
if [ "$staged_wav" -eq 0 ]; then
  echo "음성 캐시가 하나도 담기지 않았다. 중단한다." >&2
  exit 1
fi
echo "    담긴 wav: ${staged_wav}개"

git -c user.email="deploy@kmenu.local" -c user.name="K-Menu Deploy" \
    commit -q -m "deploy: 백엔드 스냅샷 ($REF @ $(git -C "$REPO_DIR" rev-parse --short "$REF"))"
git branch -M main
git remote add space "$SPACE_URL"
git push --force space main

echo
echo "완료. Space가 다시 빌드된다 — 컨테이너 준비에 몇 분 걸린다."
echo "  진행 상황: $SPACE_URL?logs=build"
echo "  확인:      https://$(echo "$SPACE_ID" | tr '/_' '--' | tr 'A-Z' 'a-z').hf.space/api/foods"
