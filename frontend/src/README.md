# Frontend Source Guide

```text
src/
├─ main.tsx                     # React 앱 시작점
├─ App.tsx                      # 화면 상태·사진 입력·후보·상세 화면
├─ styles.css                   # 모바일 중심 공통 스타일
└─ components/
   └─ LanguageSelector.tsx      # 언어 선택 UI
```

## 수정 기준

- 화면 변경 전 `../docs/ui-flow.md`, `../docs/screen-spec.md`를 확인한다.
- API 요청·응답 타입 변경 전 `../docs/api-client.md`를 함께 검토한다.
- 사용자에게 보이는 영어 문구는 `../docs/content-style.md` 기준을 따른다.
- API 주소는 `VITE_API_BASE_URL` 환경변수로만 받는다.

## 주석 원칙

프론트엔드 소스 파일을 만들거나 수정할 때는 초급 팀원도 이해할 수 있는 주석을 남긴다.

- 컴포넌트와 함수의 역할
- 화면 상태가 바뀌는 이유
- API 응답을 화면 데이터로 변환하는 이유
- 카메라 권한, 업로드, 오류, 임시 처리처럼 판단이 필요한 이유

코드를 단순히 번역하는 주석보다 **왜 이 코드가 필요한지**를 설명한다.
