#!/usr/bin/env bash
# 웹 화면을 Hugging Face Space에 배포한다(기본 대상: hajeongun/K_Menu_react).
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
#   frontend/space/deploy.sh                                     기본 Space에 배포
#   frontend/space/deploy.sh hajeongun/실험용Space                  다른 Space에 배포
#   frontend/space/deploy.sh hajeongun/K_Menu_react https://다른-api-주소
#
# 기본값이 K_Menu_react인 이유: 실제로 서비스되고 있는 웹이 이 Space다
# (https://hajeongun-k-menu-react.static.hf.space). 예전에는 K_Menu_Web이 기본값이었는데
# 그 이름의 Space가 없어서, 인자 없이 실행하면 존재하지 않는 곳으로 밀어 넣으려다 실패했다.
#
# **이 스크립트는 대상 Space를 통째로 덮어쓴다(--force).** 기존 Streamlit 화면이 올라가
# 있는 Space를 대상으로 하면 그 화면이 사라진다. 검증 중이라면 새 Space를 만들어
# 그쪽으로 올리고, 확인이 끝난 뒤에 옮기는 편이 안전하다.
#
# 처음 한 번은 Hugging Face 로그인이 필요하다. 토큰은 huggingface.co/settings/tokens에서
# write 권한으로 만들고, git이 물어보면 사용자명은 HF 아이디, 비밀번호 자리에 토큰을 넣는다.

set -euo pipefail

SPACE_ID="${1:-hajeongun/K_Menu_react}"
API_BASE_URL="${2:-https://hajeongun-k-menu.hf.space}"
SPACE_URL="https://huggingface.co/spaces/$SPACE_ID"

FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$FRONTEND_DIR/dist/public"
STAGING_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGING_DIR"' EXIT

echo "==> 대상 Space: $SPACE_ID"
echo "    이 Space의 기존 내용은 통째로 덮어쓴다."
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

# Hugging Face는 일반 git으로 올라오는 바이너리 파일을 거부한다("Your push was rejected
# because it contains binary files"). 배경 이미지 두 장과 데모 모드의 메뉴판·음성(demo/)이
# 여기 걸리므로 Git LFS로 올린다.
# .gitattributes는 **git add보다 먼저** 있어야 한다 — 파일을 담는 시점에 이 규칙을 보고
# LFS로 보낼지 정하기 때문이다.
git lfs install --local >/dev/null
cat > .gitattributes <<'ATTRS'
*.jpg  filter=lfs diff=lfs merge=lfs -text
*.jpeg filter=lfs diff=lfs merge=lfs -text
*.png  filter=lfs diff=lfs merge=lfs -text
*.webp filter=lfs diff=lfs merge=lfs -text
*.gif  filter=lfs diff=lfs merge=lfs -text
*.m4a  filter=lfs diff=lfs merge=lfs -text
ATTRS

git add -A
git -c user.email="deploy@kmenu.local" -c user.name="K-Menu Deploy" \
    commit -q -m "deploy: 웹 화면 정적 빌드 (API: $API_BASE_URL)"
git branch -M main
git remote add space "$SPACE_URL"
git push --force space main

echo
# static SDK는 일반 Space와 도메인이 다르다 — 가운데에 .static 이 들어간다.
echo "완료. 확인: https://$(echo "$SPACE_ID" | tr '/_' '--' | tr 'A-Z' 'a-z').static.hf.space"
