"""이름 음성(``name_{id}.wav``)이 쓸 만한지 판정하는 기준과 계산.

``src/tts/pregenerate.py``(만들 때)와 ``eval/verify_name_audio.py``(배포 전 검증)가 **같은
기준**을 써야 해서 여기 모아둔다. 두 곳에 따로 두면 한쪽만 고쳤을 때 배치가 통과시킨 파일을
검증이 떨어뜨리는(또는 그 반대) 상황이 된다.

무겁게 만들지 않는다 — torch도 paddle도 임포트하지 않고 wav만 읽는다. 검증 스크립트가
음성 인식만 하려고 이 모듈을 부를 때 GPU 스택을 통째로 끌어오지 않게 하기 위해서다.
numpy·soundfile도 모듈 수준이 아니라 함수 안에서 늦게 임포트한다.

## 이름 앞의 밑줄에 대해

``_wav_stats``·``_tail_strength``·``_name_audio_problem``은 밑줄로 시작하지만 **다른 모듈이
쓰라고 만든 것**이다(위 두 파일이 실제로 임포트한다). 이 모듈에서 처음 떼어낼 때 원래 있던
이름을 그대로 옮겨오면서 남은 흔적이라, 파이썬 관례대로라면 밑줄을 떼는 게 맞다. 지금 바꾸면
부르는 쪽 두 곳을 같이 고쳐야 해서 남겨뒀다 — 새로 추가하는 공용 이름에는 붙이지 말 것.
(``normalize_loudness``와 상수들은 처음부터 공개 이름으로 뒀다.)
"""

from pathlib import Path


# 이름 음성(name_{id}.wav) 품질 검사 기준 —
#
# 이 모델은 오디오 토큰을 샘플링으로 뽑는데, 음식 이름처럼 짧은 입력은 문맥이 거의 없어서
# 마지막 음절 직전에 EOS가 조기에 나온다. 2026-08-27 실측: 캐시 50개 중 28개가 끝 음절을
# 잃었고(평균 0.91음절 부족), 그중엔 0.14초짜리 잡음과 완전 무음도 있었다. 문장으로 된
# 나레이션 50개에는 같은 증상이 없다 — 그래서 검사도 이름 음성에만 건다.
#
# 0.222초/글자는 멀쩡했던 22개에서 잰 발화 속도다. 여기 0.7을 곱한 값보다 짧으면 음절이
# 빠진 것으로 본다 — 정상 22개는 전부 이 선을 넘고 불량 28개는 대부분 못 넘는다.
SEC_PER_SYLLABLE = 0.222
# 0.8인 이유 — 음절 하나가 통째로 빠지면 3글자는 67%, 4글자는 75%까지 떨어진다. 반대로
# 정상 파일은 84~105%에 들어온다(2026-08-27 그리디 50개 실측, 84~88%짜리 7개도 ASR이
# 전부 정확히 읽었다). 그 사이인 0.8이 "빠졌다"와 "빠르게 읽었다"를 가르는 선이다.
# 0.7은 한 음절 빠진 파일을 통과시켰고, 0.9는 멀쩡한 파일 7개를 걸러냈다.
MIN_DURATION_RATIO = 0.8
MIN_PEAK = 0.05  # 이보다 조용하면 발화가 아니라 무음/잡음이다 (실제 불량 예: 피크 0.02)

# 마지막 음절이 전체 평균 세기의 몇 배인가. 길이도 맞고 소리도 있는데 **끝 음절만 유독
# 약한** 경우가 있어서 따로 본다 — 2026-08-27에 "콩국수"가 길이 96%·피크 0.59로 두 검사를
# 다 통과했는데 귀로는 끝이 잘려 들렸고, 이 값이 23%였다(50개 중앙값 83%). 0.55는 그
# 8개를 걸러내면서 정상 파일은 건드리지 않는 선이다.
MIN_TAIL_STRENGTH = 0.55


def _wav_stats(path: Path) -> tuple[float | None, float | None]:
    """wav의 (길이 초, 최대 진폭). 재지 못한 값은 None으로 돌려준다.

    soundfile이 있으면 그걸 쓴다 — float 포맷 wav도 읽고 샘플까지 준다. 없으면 표준 wave
    모듈로 떨어지는데 그건 PCM만 읽으므로, 진폭은 16bit PCM일 때만 잰다. 둘 다 실패하면
    (None, None)이고 호출 쪽이 판단을 포기한다.
    """
    try:
        import soundfile as sf
        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data[:, 0]
        if len(data) == 0:
            return 0.0, 0.0
        return len(data) / sample_rate, float(abs(data).max())
    except Exception:
        pass
    try:
        import wave
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            sample_rate = w.getframerate()
            width = w.getsampwidth()
            raw = w.readframes(frames)
        duration = frames / sample_rate if frames else 0.0
        if width != 2 or not frames:
            return duration, None
        import numpy as np
        samples = np.frombuffer(raw, dtype="<i2")
        return duration, float(abs(samples).max()) / 32768.0
    except Exception:
        return None, None


def _tail_strength(path: Path, syllables: int) -> float | None:
    """마지막 음절 구간의 평균 세기 ÷ 발화 전체의 평균 세기. 못 재면 None.

    소리가 나는 구간을 음절 수로 나눠 마지막 토막만 본다. 끝이 제대로 발음되면 1에 가깝고,
    흐지부지 사라지면 0에 가까워진다 (위 MIN_TAIL_STRENGTH 주석에 실측 근거).
    """
    try:
        import numpy as np
        import soundfile as sf

        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        if getattr(data, "ndim", 1) > 1:
            data = data[:, 0]
        win = max(int(sample_rate * 0.02), 1)
        frames = len(data) // win
        if frames < syllables:
            return None
        rms = np.array([
            np.sqrt(np.mean(data[j * win:(j + 1) * win].astype(np.float64) ** 2))
            for j in range(frames)
        ])
        voiced = np.where(rms > 0.02)[0]
        if len(voiced) == 0:
            return None
        segment = rms[voiced[0]:voiced[-1] + 1]
        chunk = max(1, len(segment) // syllables)
        whole = segment.mean()
        return float(segment[-chunk:].mean() / whole) if whole > 0 else None
    except Exception:
        return None


def _name_audio_problem(path: Path, name_kr: str) -> str | None:
    """이름 음성이 쓸 만한지 본다. 괜찮으면 None, 아니면 사람이 읽을 이유를 돌려준다."""
    duration, peak = _wav_stats(path)
    if duration is None:
        # 길이조차 못 재는 환경이면 검사를 포기한다 — 멀쩡한 음성을 버리는 쪽이 더 나쁘다.
        return None
    if peak is not None and peak < MIN_PEAK:
        return f"거의 무음 (피크 {peak:.3f})"
    expected = SEC_PER_SYLLABLE * len(name_kr)
    if duration < expected * MIN_DURATION_RATIO:
        return f"너무 짧음 ({duration:.2f}초, 기대 {expected:.2f}초)"
    tail = _tail_strength(path, len(name_kr))
    if tail is not None and tail < MIN_TAIL_STRENGTH:
        return f"끝 음절이 약함 (전체 대비 {tail:.0%})"
    return None


# 음량 정규화 —
#
# 이 모델은 출력 음량을 맞춰주지 않는다. 2026-08-27 실측: 이름 음성 50개의 RMS가 0.034~0.136
# (4배), 피크가 0.15~0.77(5.3배)까지 벌어졌고, 나레이션도 RMS 0.027~0.117이었다. 그래서
# 어떤 음식은 이름이 안 들릴 만큼 작게 나온다("만두" 피크 0.15로 최저).
#
# 목표 RMS 0.09는 지금 파일들의 중앙값(이름 0.076·나레이션 0.086) 언저리다 — 전체를 크게
# 키우지 않으면서 조용한 쪽만 끌어올린다. 피크 상한 0.9는 클리핑을 막고, 이득 상한 8배는
# 거의 무음인 실패작을 증폭해 잡음만 키우는 것을 막는다(그런 파일은 어차피 검사에서 걸린다).
NORMALIZE_TARGET_RMS = 0.09
NORMALIZE_PEAK_CEILING = 0.9
NORMALIZE_MAX_GAIN = 8.0


def normalize_loudness(samples):
    """음량을 목표 RMS에 맞춘다. 클리핑이 나지 않도록 피크 상한도 같이 건다.

    이득만 곱하므로 소리의 내용은 바뀌지 않는다 — 이미 만들어둔 캐시 파일에 나중에 적용해도
    안전하다. 무음이거나 계산이 불가능하면 원본을 그대로 돌려준다.
    """
    import numpy as np

    if samples is None or len(samples) == 0:
        return samples
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    if peak <= 0 or rms <= 0:
        return samples
    gain = min(NORMALIZE_TARGET_RMS / rms, NORMALIZE_PEAK_CEILING / peak, NORMALIZE_MAX_GAIN)
    return samples * gain
