#!/usr/bin/env bash
# 웹 화면을 Hugging Face Space(HJU5022/K_Menu_Web)에 배포한다.
#
# 이 Space에는 **빌드 결과물만** 올라간다. 소스는 GitHub에 있고, 여기에 올리는 것은
# `pnpm run build`가 만든 index.html·JS·CSS와 Space 설정 README 하나뿐이다.
# 그래서 커밋 이력을 쌓지 않고 매번 한 개의 커밋으로 통째로 덮어쓴다(--force).
# 되돌릴 일이 생기면 GitHub에서 그 시점 소스를 다시 빌드해 올리면 된다.
#
# 서버 주소는 **빌드 시점에 JS 안에 박힌다**(Vite의 VITE_ 규칙). 그래서 주소를 바꾸려면
# 다시 빌드해야 한다 — Space에 환경변수를 넣는 것으로는 바뀌지 않는다.
#
# 쓰는 법:
#   frontend/space/deploy.sh
#   frontend/space/deploy.sh https://다른-api-주소       (주소를 바꿔 배포할 때)
#
# 처음 한 번은 Hugging Face 로그인이 필요하다. 토큰은 huggingface.co/settings/tokens에서
# write 권한으로 만들고, git이 물어보면 사용자명은 HF 아이디, 비밀번호 자리에 토큰을 넣는다.

set -euo pipefail

API_BASE_URL="${1:-https://hju5022-k-menu.hf.space}"
SPACE_URL="https://huggingface.co/spaces/HJU5022/K_Menu_Web"

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$FRONTEND_DIR/dist/public"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT

echo "==> 빌드 (API 주소: $API_BASE_URL)"
cd "$FRONTEND_DIR"
VITE_API_BASE_URL="$API_BASE_URL" npx --yes pnpm@10 run build

if [ ! -f "$BUILD_DIR/index.html" ]; then
  echo "빌드 결과가 없다: $BUILD_DIR/index.html" >&2
  exit 1
fi

echo "==> 올릴 파일 준비"
cp -R "$BUILD_DIR"/. "$STAGING_DIR"/
cp "$FRONTEND_DIR/space/README.md" "$STAGING_DIR/README.md"
ls -la "$STAGING_DIR"

echo "==> Space에 올리기"
cd "$STAGING_DIR"
git init -q
git add -A
git -c user.email="deploy@kmenu.local" -c user.name="K-Menu Deploy" \
    commit -q -m "deploy: 웹 화면 정적 빌드 (API: $API_BASE_URL)"
git branch -M main
git remote add space "$SPACE_URL"
git push --force space main

echo
echo "완료. 확인: https://hju5022-k-menu-web.hf.space"
