"""파이프라인 테스트 — src/pipeline.py가 블록들(OCR·텍스트·TTS)을 올바른 순서로 잇는지 확인한다.

여기서 검사하는 건 "각 블록이 잘 동작하나"가 아니라 **연결 방식**이다.
- 어떤 함수를 어떤 인자로 부르는가 (예: 매칭된 food_id를 TTS에 그대로 넘기는가)
- 앞 단계가 실패하면 뒷 단계를 건너뛰는가 (예: 음식 못 찾으면 TTS를 아예 안 부름)
- 실패해도 서비스가 죽지 않고 fallback 값을 주는가

그래서 OCR·TTS 실제 함수는 전부 patch로 가짜로 바꾼다. GPU도 DB도 필요 없다.

실행: python -m pytest tests/test_pipeline.py
"""

import json
import unittest
from unittest.mock import patch

from src import pipeline


class PipelineTests(unittest.TestCase):
    """create_tts_response() — 음식 하나에 대해 내레이션 텍스트 + 음성을 만들어 합치는 함수."""

    @patch("src.pipeline._synthesize_via_subprocess")
    @patch("src.pipeline.get_narration")
    def test_create_tts_response_combines_text_and_tts_results(
        self, mock_get_narration, mock_synthesize
    ):
        """텍스트 생성 결과와 TTS 결과가 하나의 응답으로 합쳐지는지 (필드명 포함)."""
        mock_get_narration.return_value = {
            "text": "This is Bibimbap.",
            "style": "GUIDE",
        }
        mock_synthesize.return_value = {
            "audio_path": None,
            "status": "not_ready",
            "latency_ms": 1.25,
        }

        result = pipeline.create_tts_response(1)

        mock_get_narration.assert_called_once_with(1)
        # 텍스트 생성이 정한 style이 TTS로 그대로 넘어가야 톤(GUIDE/CAUTION)이 맞는다
        mock_synthesize.assert_called_once_with("This is Bibimbap.", "GUIDE")
        # 내부 이름(audio_path/status/latency_ms)이 API용 이름(narration_audio_path 등)으로 바뀐다
        self.assertEqual(
            result,
            {
                "narration_text": "This is Bibimbap.",
                "style": "GUIDE",
                "narration_audio_path": None,
                "tts_status": "not_ready",
                "tts_latency_ms": 1.25,
            },
        )

    @patch("src.pipeline._synthesize_via_subprocess")
    @patch("src.pipeline.get_narration")
    def test_create_tts_response_falls_back_when_subprocess_reports_not_ready(
        self, mock_get_narration, mock_synthesize
    ):
        """TTS가 실패해도(not_ready) 텍스트는 살아서 나가야 한다 — 음성 없이도 화면은 보여야 하므로."""
        mock_get_narration.return_value = {
            "text": "This is Bibimbap.",
            "style": "GUIDE",
        }
        mock_synthesize.return_value = {
            "audio_path": None,
            "status": "not_ready",
            "latency_ms": 0.0,
        }

        result = pipeline.create_tts_response(1)

        self.assertEqual(
            result,
            {
                "narration_text": "This is Bibimbap.",
                "style": "GUIDE",
                "narration_audio_path": None,
                "tts_status": "not_ready",
                "tts_latency_ms": 0.0,
            },
        )


class FakeWorker:
    """상주 워커 프로세스 흉내 — 실제 자식 프로세스를 띄우지 않고 파이프 동작만 재현한다.

    진짜 워커는 stdin으로 요청 한 줄을 받고 stdout으로 응답 한 줄을 돌려준다. 여기서는
    미리 준비해둔 응답을 순서대로 내주고, 무엇을 받았는지(written)와 죽었는지(killed)를
    기록해둔다. subprocess.Popen과 같은 규칙으로 poll()·kill()도 흉내낸다.
    """

    def __init__(self, responses, alive=True):
        self._responses = list(responses)
        self._alive = alive
        self.written = []
        self.killed = False
        self.stdin = self._Stdin(self)
        self.stdout = self._Stdout(self)

    class _Stdin:
        def __init__(self, owner):
            self._owner = owner

        def write(self, data):
            self._owner.written.append(data)

        def flush(self):
            pass

    class _Stdout:
        def __init__(self, owner):
            self._owner = owner

        def readline(self):
            # 준비된 응답이 떨어지면 ""를 준다 = 파이프가 닫혔다(워커가 끝났다)는 뜻
            return self._owner._responses.pop(0) if self._owner._responses else ""

    def poll(self):
        """None이면 살아있음, 숫자면 이미 종료됨 (subprocess.Popen과 같은 규칙)."""
        return None if self._alive else 1

    def kill(self):
        self.killed = True
        self._alive = False


class SynthesizeViaSubprocessTests(unittest.TestCase):
    """_synthesize_via_subprocess()는 **상주 워커**(src/tts/worker.py)와의 대화를 감싼다.

    워커를 별도 프로세스로 띄우는 이유는 paddle(OCR)과 torch(TTS)를 같은 프로세스에
    못 올리는 문제(WinError 127) 때문이고, 그 프로세스를 죽이지 않고 재사용하는 이유는
    요청마다 모델을 다시 GPU에 올리면 90초 이상 걸리기 때문이다.

    여기서 검사하는 건 그 대화 규칙이다 — 한 줄 보내고 한 줄 받기, 워커 재사용,
    죽은 워커 감지·재시작, 그리고 어떤 실패든 서비스를 죽이지 않고 not_ready로 떨어지는지.
    """

    def setUp(self):
        # 워커 핸들이 모듈 전역이라, 앞 테스트가 남긴 값이 다음 테스트로 새면 결과가 꼬인다
        pipeline._worker = None

    def tearDown(self):
        pipeline._worker = None

    def test_returns_parsed_result_on_success(self):
        """정상 응답 한 줄을 파싱해서 돌려주는지, 그리고 요청이 한 줄로 제대로 나갔는지."""
        fake = FakeWorker(
            [json.dumps({"audio_path": "answer.wav", "status": "ok", "latency_ms": 42.0}) + "\n"]
        )
        with patch("src.pipeline._start_worker", return_value=fake):
            result = pipeline._synthesize_via_subprocess("text", "GUIDE")

        self.assertEqual(result, {"audio_path": "answer.wav", "status": "ok", "latency_ms": 42.0})
        # 개행으로 끝나야 워커의 readline이 요청을 끊어 읽을 수 있다
        self.assertEqual(fake.written, ['{"text": "text", "style": "GUIDE"}\n'])

    def test_reuses_worker_across_calls(self):
        """이 구조의 핵심 — 두 번째 요청은 워커를 새로 띄우지 않고 그대로 재사용한다."""
        fake = FakeWorker(
            [
                json.dumps({"audio_path": "a.wav", "status": "ok", "latency_ms": 1.0}) + "\n",
                json.dumps({"audio_path": "b.wav", "status": "ok", "latency_ms": 2.0}) + "\n",
            ]
        )
        with patch("src.pipeline._start_worker", return_value=fake) as mock_start:
            first = pipeline._synthesize_via_subprocess("text one", "GUIDE")
            second = pipeline._synthesize_via_subprocess("text two", "CAUTION")

        self.assertEqual(first["audio_path"], "a.wav")
        self.assertEqual(second["audio_path"], "b.wav")
        # 두 번 불렸다면 매 요청마다 모델을 다시 올리는 것 = 이 변경이 무의미해진다
        mock_start.assert_called_once()

    def test_restarts_worker_when_previous_one_died(self):
        """죽은 워커를 붙들고 있으면 이후 요청이 전부 실패한다 — 감지해서 새로 띄워야 한다."""
        dead = FakeWorker([], alive=False)
        alive = FakeWorker(
            [json.dumps({"audio_path": "c.wav", "status": "ok", "latency_ms": 3.0}) + "\n"]
        )
        pipeline._worker = dead

        with patch("src.pipeline._start_worker", return_value=alive) as mock_start:
            result = pipeline._synthesize_via_subprocess("text", "GUIDE")

        mock_start.assert_called_once()
        self.assertEqual(result["audio_path"], "c.wav")

    def test_falls_back_when_worker_times_out(self):
        """정해진 시간 안에 응답이 없으면 not_ready로 떨어지고, 그 워커는 버린다."""
        fake = FakeWorker([])
        with (
            patch("src.pipeline._start_worker", return_value=fake),
            patch("src.pipeline._readline_with_timeout", return_value=None),
        ):
            result = pipeline._synthesize_via_subprocess("text", "GUIDE")

        self.assertEqual(result, {"audio_path": None, "status": "not_ready", "latency_ms": 0.0})
        # 응답이 밀린 워커를 그대로 두면 다음 요청의 응답과 어긋난다
        self.assertTrue(fake.killed)
        self.assertIsNone(pipeline._worker)

    def test_falls_back_on_malformed_output(self):
        """JSON이 아닌 줄이 와도(라이브러리 경고가 섞이는 경우) 죽지 않고 not_ready."""
        fake = FakeWorker(["not json\n"])
        with patch("src.pipeline._start_worker", return_value=fake):
            result = pipeline._synthesize_via_subprocess("text", "GUIDE")

        self.assertEqual(result, {"audio_path": None, "status": "not_ready", "latency_ms": 0.0})
        self.assertTrue(fake.killed)

    def test_falls_back_when_worker_closes_pipe(self):
        """워커가 응답 없이 파이프를 닫아도(빈 문자열) 실패로 처리한다."""
        fake = FakeWorker([])
        with patch("src.pipeline._start_worker", return_value=fake):
            result = pipeline._synthesize_via_subprocess("text", "GUIDE")

        self.assertEqual(result, {"audio_path": None, "status": "not_ready", "latency_ms": 0.0})


class PipelineRunAndAnalyzeTests(unittest.TestCase):
    """run()과 analyze_image() — 이미지 한 장을 받아 처리하는 두 진입 함수.

    run(): 이미지 → 음식 1개 확정까지 한 번에 (초기 버전)
    analyze_image(): 이미지 → 후보 목록까지만 (사용자가 고르는 흐름, 지금 API가 쓰는 쪽)
    """

    @patch("src.pipeline.get_details")
    @patch("src.pipeline.create_tts_response")
    @patch("src.pipeline.match_food")
    @patch("src.pipeline.recognize")
    def test_run_returns_full_response_when_matched(
        self, mock_recognize, mock_match_food, mock_create_tts_response, mock_get_details
    ):
        """음식을 찾았을 때 — OCR 결과가 매칭으로, 매칭된 id가 상세·TTS로 이어지는 사슬 검사."""
        mock_recognize.return_value = "비빔밥 8000원"
        mock_match_food.return_value = {"food_id": 1, "name_kr": "비빔밥", "score": 100.0}
        mock_create_tts_response.return_value = {
            "narration_text": "This is Bibimbap.",
            "style": "GUIDE",
            "narration_audio_path": None,
            "tts_status": "not_ready",
            "tts_latency_ms": 1.25,
        }
        mock_get_details.return_value = {"DESCRIPTION": "A bowl of rice."}

        result = pipeline.run("dummy.jpg")

        # 각 단계의 출력이 다음 단계의 입력으로 정확히 전달됐는지 하나씩 확인
        mock_recognize.assert_called_once_with("dummy.jpg")
        mock_match_food.assert_called_once_with("비빔밥 8000원")
        mock_create_tts_response.assert_called_once_with(1)
        mock_get_details.assert_called_once_with(1)
        self.assertEqual(result["matched_food"], {"food_id": 1, "name_kr": "비빔밥", "score": 100.0})
        self.assertEqual(result["details"], {"DESCRIPTION": "A bowl of rice."})
        self.assertEqual(result["narration_text"], "This is Bibimbap.")

    @patch("src.pipeline.get_details")
    @patch("src.pipeline.create_tts_response")
    @patch("src.pipeline.match_food")
    @patch("src.pipeline.recognize")
    def test_run_returns_none_matched_food_when_no_match(
        self, mock_recognize, mock_match_food, mock_create_tts_response, mock_get_details
    ):
        """못 찾았으면 거기서 멈춘다 — 없는 음식에 GPU를 쓰면 시간·비용 낭비."""
        mock_recognize.return_value = "알수없는글자"
        mock_match_food.return_value = None

        result = pipeline.run("dummy.jpg")

        self.assertEqual(result, {"matched_food": None})
        # assert_not_called = "이 함수는 아예 불리면 안 된다"
        mock_create_tts_response.assert_not_called()
        mock_get_details.assert_not_called()

    @patch("src.pipeline.match_food_candidates")
    @patch("src.pipeline.recognize")
    def test_analyze_image_returns_ocr_empty_without_matching(self, mock_recognize, mock_match_candidates):
        """글자를 하나도 못 읽었으면(공백뿐) 매칭도 시도하지 않고 ocr_empty로 끝낸다."""
        mock_recognize.return_value = "   "  # 공백만 있는 결과

        result = pipeline.analyze_image("dummy.jpg")

        self.assertEqual(
            result,
            {"status": "ocr_empty", "ocr_text": "", "candidates": []},
        )
        mock_match_candidates.assert_not_called()

    @patch("src.pipeline.match_food_candidates")
    @patch("src.pipeline.recognize")
    def test_analyze_image_returns_unsupported_food_with_ocr_text(
        self, mock_recognize, mock_match_candidates
    ):
        """글자는 읽었는데 등록 음식이 없으면 unsupported_food.

        ocr_empty와 구분해야 한다 — 프론트가 "다시 찍어주세요"와 "미지원 음식입니다"
        중 어떤 안내를 띄울지 이 status로 결정하기 때문이다.
        """
        mock_recognize.return_value = "미지원음식"
        mock_match_candidates.return_value = []

        result = pipeline.analyze_image("dummy.jpg")

        self.assertEqual(
            result,
            {"status": "unsupported_food", "ocr_text": "미지원음식", "candidates": []},
        )
        mock_match_candidates.assert_called_once_with("미지원음식")

    @patch("src.pipeline._synthesize_via_subprocess")
    @patch("src.pipeline.get_details")
    @patch("src.pipeline.match_food_candidates")
    @patch("src.pipeline.recognize")
    def test_analyze_image_returns_candidates_without_creating_response(
        self, mock_recognize, mock_match_candidates, mock_get_details, mock_synthesize
    ):
        """후보를 찾아도 여기서 상세·음성까지 만들지는 않는다.

        사용자가 후보 중 하나를 고른 뒤에야 그 음식만 TTS를 돌려야 한다.
        미리 다 만들면 안 고른 음식까지 GPU를 쓰게 된다(요청당 90초 이상 걸리는 작업).
        """
        candidates = [
            {"food_id": 2, "name_kr": "닭갈비", "score": 100, "modifiers": {}},
            {"food_id": 1, "name_kr": "갈비", "score": 95, "modifiers": {}},
        ]
        mock_recognize.return_value = "닭갈비 갈비"
        mock_match_candidates.return_value = candidates

        result = pipeline.analyze_image("dummy.jpg")

        self.assertEqual(
            result,
            {"status": "candidates_found", "ocr_text": "닭갈비 갈비", "candidates": candidates},
        )
        mock_get_details.assert_not_called()
        mock_synthesize.assert_not_called()
