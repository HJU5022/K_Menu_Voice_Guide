# Spec — 실패 원인을 로그로 구분한다

## Why

- **페르소나**: 배포·디버깅을 맡는 팀원, 그리고 문제를 진단하는 AI 에이전트.
- **상황**: 2026-08-23 밤 ~ 08-24 오전 HF Spaces 배포 중 TTS가 세 번 서로 다른 이유로
  실패했다 — 라이브러리 버전 충돌(torch가 paddle과 충돌해 2.0.1까지 내려감), C 컴파일러
  부재(Triton 즉석 컴파일 실패), 로컬에 TTS 전용 가상환경이 없음. **셋 다 API 응답에
  `tts_status: "not_ready"` 한 단어로만 나타났다.**
- **문제**:
  1. `src/pipeline.py`에 예외를 잡고 아무것도 남기지 않는 지점이 3곳 있다(`_kill_worker`
     85행, `_readline_with_timeout`의 읽기 스레드 101행, `_synthesize_via_subprocess`
     131행). 세 번째가 결정적이다 — 모든 TTS 실패가 이 한 곳을 거쳐 `not_ready`로
     뭉개진다.
  2. stderr를 파일(`logs/tts_worker.log`)로만 보내는데, 배포된 Space는 셸 접근이 없어
     그 파일을 열 방법이 없다. Space 로그 화면(Container 탭)에는 stdout만 보인다.
  3. 원인을 알아내려고 진단용 임시 엔드포인트(`/debug/tts-log`, `/debug/gpu`,
     `/debug/tts-run`, `/debug/tts-bench`)를 만들어 재배포하는 왕복을 4번 했다(빌드
     3~15분/회). 이 엔드포인트들은 배포 브랜치(`deploy/api-space`)에만 있고 이 저장소
     (main)에는 없다 — 재사용 가능한 자산이 아니라 그때그때 버려지는 코드였다.
  4. 프로세스가 강제 종료(`kill()`)되면 파이썬 traceback이 안 남는다 — 로그가 문장
     중간에 끊긴 사례가 있었다(A-2).
  5. **로그에 이미 민감정보가 새고 있다.** Supabase(`httpx`가 내부적으로 찍는 INFO
     로그)의 요청 URL이 공개 Space 로그 화면에 그대로 보인다.
- **측정 지표**: 다음 배포 실패에서, **재배포 없이 Space 로그 화면만 보고** 원인을
  구분할 수 있는가. 이번엔 4번 재배포해야 했다 — 목표는 0번.

## Goal

- **해결 목표**: `src/pipeline.py`·`K_Menu_Talk.py`가 실패를 삼키지 않고 로그로 남기게
  하고, 그 로그가 컨테이너 셸 없이 Space 로그 화면에서 바로 보이게 한다. 임시 디버그
  엔드포인트가 다시 필요하지 않게 하는 것이 성공의 기준이다.
- **성공 기준**:
  1. `except Exception`으로 예외를 처리하는 지점 3곳이 전부 예외 종류와 traceback을
     로그로 남긴다. `pass`로 끝나는 지점이 없다.
  2. 그 로그가 **stdout으로도** 나가 Space Container 로그 화면에서 실시간으로 보인다.
     재시작 전까지는 셸 접근 없이도 확인 가능하다.
  3. 로그 레벨(WARNING/ERROR)이 구분돼 있어, 정상 동작 로그(uvicorn 액세스 로그 등)와
     실패가 한눈에 갈린다.
  4. Supabase 요청 URL 등 민감정보가 로그에 평문으로 안 남는다.
  5. API 응답(`tts_status` 등)은 지금처럼 안전한 요약만 담는다 — 로그와 응답은 분리된
     채널이다. traceback을 클라이언트에 노출하지 않는다.
- **Out of Scope**:
  - 로그 수집·모니터링 SaaS 연동(Sentry, Datadog 등) — 필요해지면 별도 Spec.
  - 로그 로테이션·보존 정책. 컨테이너가 재시작되면 로그가 사라지는 지금 구조는 그대로
    둔다. (재시작 전까지만 보이면 이번 문제는 해결된다 — 사후 분석이 꼭 필요해지면
    별도로 다룬다.)
  - 임시 디버그 엔드포인트를 정식 기능으로 만드는 것. **지우고 로깅으로 대체하기로
    결정했다(2026-08-24).** 이 엔드포인트들은 main에는 없으므로 이 저장소에서 지울
    코드는 없다 — Windows PC의 `deploy/api-space` 브랜치를 다음에 갱신할 때 그쪽에서
    빼는 일이다(이 세션에서 그 브랜치에 손댈 수 없다).
  - OCR·음식 매칭 버그(메뉴 아닌 줄이 잡히는 것, 가격이 옆 열에서 붙는 것) — 이건 로깅
    부재가 아니라 로직 버그이고, 별도 작업이다.
  - 웹(`app.py`)·모바일 앱 쪽 클라이언트 로깅. 이번엔 서버(`K_Menu_Talk.py`,
    `src/pipeline.py`) 범위만 다룬다.
  - Space Dev mode(SSH 접속)로 컨테이너 내부에 직접 들어가는 방법 — 되는지 안 되는지
    확인 안 됐다(불확실 목록). 이번 설계는 그게 안 된다는 전제로 간다.

## What

**실패가 났을 때 지금 벌어지는 일 (Happy Path가 아니라 "실패 경로")**

1. TTS 워커(`src/tts/worker.py`)가 실행 중 예외를 던진다.
2. `_synthesize_via_subprocess()`의 `except Exception`이 그것을 잡는다.
3. 예외 종류·메시지·traceback을 **로그로 남긴다**(ERROR 레벨, `exc_info` 포함).
4. 그 로그가 stdout으로 나가 Space Container 로그 화면에 바로 보인다.
5. `_kill_worker()`를 호출하고 `{"status": "not_ready", ...}`를 돌려준다 — API 응답은
   지금과 동일하다(클라이언트가 보는 것은 안 바뀐다).
6. 팀원이 Space 로그 화면만 보고 "라이브러리 충돌인지, 컴파일러 부재인지, 다른 것인지"를
   구분한다 — 재배포하지 않는다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | `_kill_worker()`에서 `.kill()` 자체가 실패(85행) | WARNING 레벨로 예외를 남긴다. 이미 죽었거나 죽어가는 프로세스에 흔한 경로라 ERROR로 올리지 않는다. 상위 로직은 그대로 진행한다(워커 참조는 어차피 버려진다) |
| EC-02 | 응답 읽기 스레드에서 `readline()` 실패(101행) | WARNING 레벨로 남긴다. `_kill_worker()`가 파이프를 닫으면서 정상적으로도 발생할 수 있는 경로라 로그가 실패를 과장하지 않게 한다 |
| EC-03 | `_synthesize_via_subprocess()` 전체 실패(131행) | ERROR 레벨로 예외 전체(타입+traceback)를 남긴 뒤 `not_ready`를 반환한다 — 이번 Spec의 핵심 지점 |
| EC-04 | 로그에 메뉴 이름 등 사용자 텍스트가 섞임 | 개인정보가 아니므로 그대로 남긴다. 단 자격증명·URL·키는 절대 남기지 않는다(EC-05) |
| EC-05 | `httpx`(Supabase 클라이언트가 내부적으로 씀)가 요청 URL을 INFO로 찍음 | `httpx` 로거의 레벨을 WARNING 이상으로 올려 억제한다. 진짜 실패(4xx/5xx)는 예외로 올라오므로 우리 쪽 예외 로깅에서 여전히 잡힌다 |
| EC-06 | 같은 예외가 짧은 시간에 반복됨(워커가 계속 죽는 경우) | 이번 범위에서는 그대로 반복 출력한다. 반복 억제(디듀프·레이트리밋)는 Out of Scope — 지금 필요한 건 "안 보이던 걸 보이게" 하는 것이지 "너무 많이 보이는 걸 줄이는" 것이 아니다 |
| EC-07 | 기존 `logs/tts_worker.log` 파일 | 그대로 유지한다. stdout이 주 채널이 되지만, 파일도 남겨 두면 사후 대조에 쓸 수 있다. 이번 Spec은 이 파일을 없애지 않는다 |

## How

**대상 파일**: `src/pipeline.py`, `K_Menu_Talk.py`. `src/` 아래 다른 모듈은 건드리지 않는다.

**표준 `logging` 모듈을 쓴다.** 새 의존성을 추가하지 않는다(파이썬 표준 라이브러리).

```python
# src/pipeline.py 상단
import logging

logger = logging.getLogger(__name__)
```

**세 지점의 처리**:

```python
# _kill_worker() — 85행
except Exception:
    logger.warning("워커 종료 실패", exc_info=True)

# _readline_with_timeout()의 _read() — 101행
except Exception:
    logger.warning("워커 응답 읽기 실패", exc_info=True)
    answer.put("")

# _synthesize_via_subprocess() — 131행 (핵심)
except Exception:
    logger.error("TTS 합성 실패 (style=%s, text=%r)", style, text[:80], exc_info=True)
    _kill_worker()
    return dict(_TTS_FAILED)
```

`exc_info=True`가 traceback 전체를 로그에 싣는다. A-2(traceback 없이 끊긴 사례)는 워커
프로세스 자체가 죽어 stderr가 끊긴 것이지 이 지점의 문제는 아니었다 — 이 세 지점은 부모
프로세스(FastAPI) 안에서 도는 코드라 `exc_info=True`로 잡히는 traceback은 안 끊긴다.

**로깅 설정은 `K_Menu_Talk.py`에서, `import torch`(WinError 127 방지용, 최상단 고정) 바로
다음, 다른 `src.*` import보다 먼저 한다** — 순서가 어긋나면 다른 라이브러리가 먼저
`logging.basicConfig()`를 호출해(흔한 일이다) 우리 설정이 무시된다:

```python
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
# Supabase 클라이언트(httpx)가 요청 URL을 INFO로 찍어 공개 Space 로그에 그대로
# 노출된다(실측 2026-08-24) — WARNING 이상만 남긴다.
logging.getLogger("httpx").setLevel(logging.WARNING)
```

**민감정보 판단 기준**: URL·토큰·키·경로 안의 사용자명은 로그에 남기지 않는다. 메뉴
이름·가격처럼 이 서비스가 다루는 일반 텍스트는 남겨도 된다(개인정보가 아니다).

**임시 디버그 엔드포인트**: 이 저장소(main)에는 없으므로 지울 코드가 없다. 이 Spec이
merge된 뒤, Windows PC에서 `deploy/api-space` 브랜치를 다음에 갱신할 때 그쪽 4개
엔드포인트를 빼는 것을 권고한다 — 이번 로깅이 그 역할을 대신한다.

## AC

**AC-01 · TTS 합성 실패가 로그에 남는다**
- GIVEN: TTS 워커가 예외를 던진다(어떤 원인이든).
- WHEN: `_synthesize_via_subprocess()`가 그 예외를 잡는다.
- THEN: ERROR 레벨 로그가 남고, 그 안에 예외 타입과 전체 traceback이 포함된다.
  API 응답은 지금과 동일하게 `{"status": "not_ready", ...}`다.

**AC-02 · 로그가 stdout으로 나가 Space 로그 화면에서 보인다**
- GIVEN: 위 실패가 배포된 컨테이너 안에서 발생했다.
- WHEN: Space 페이지의 Logs → Container 탭을 연다.
- THEN: 해당 ERROR 로그가 재배포 없이 그 화면에서 보인다.

**AC-03 · Supabase 요청 URL이 로그에 안 남는다**
- GIVEN: 서버가 정상적으로 Supabase에 여러 번 조회 요청을 보낸다.
- WHEN: 그 요청들이 성공적으로 끝난다(4xx/5xx 아님).
- THEN: 로그에 그 요청들의 URL이 INFO 레벨로 찍히지 않는다.

**AC-04 · 워커 종료·읽기 실패는 덜 시끄러운 레벨로 남는다**
- GIVEN: `_kill_worker()`의 `.kill()` 또는 읽기 스레드의 `readline()`이 실패한다.
- WHEN: 그 예외가 잡힌다.
- THEN: WARNING 레벨로 남고(ERROR 아님), 상위 로직(재시도·`not_ready` 반환)은 그대로
  진행된다 — 이 두 지점의 실패가 전체 요청을 막지 않는다.

**AC-05 · 클라이언트에는 traceback이 노출되지 않는다**
- GIVEN: 위 AC-01의 실패 상황이다.
- WHEN: `GET /api/foods/{id}` 응답을 클라이언트가 받는다.
- THEN: 응답 본문에 예외 메시지나 traceback 문자열이 없다 — `tts_status`·
  `narration_audio_path` 같은 필드만 있다(기존 계약, `docs/specs/api-layer.md` 유지).
