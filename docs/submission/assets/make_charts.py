"""제출물 8번(모델 비교 실험)의 그래프를 그린다.

원본 데이터는 전부 eval/ 안에 있다. 이 스크립트는 값을 새로 만들지 않고
CSV·JSON을 읽어 그리기만 한다. 수치를 바꾸려면 eval/ 쪽을 고쳐야 한다.

실행: python docs/submission/assets/make_charts.py
"""

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[3]
EVAL = ROOT / "eval"
OUT = Path(__file__).resolve().parent

# 한글 라벨이 깨지지 않게 시스템에 있는 한글 폰트를 찾는다. 없으면 영문 라벨로 떨어진다.
_KO_CANDIDATES = ["Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"]
_installed = {f.name for f in font_manager.fontManager.ttflist}
KO_FONT = next((n for n in _KO_CANDIDATES if n in _installed), None)
if KO_FONT:
    plt.rcParams["font.family"] = KO_FONT
plt.rcParams["axes.unicode_minus"] = False

# 학습 회차 표시 이름 (eval/TTS_MODULE.md 3절의 차수와 맞춘다)
RUN_LABELS = {
    "lr5e-6_ep40": "3차 lr5e-6 (기준선)",
    "lr1e-5_ep40": "4차 lr1e-5",
    "lr2e-5_ep40": "5차 lr2e-5 (공식 기본값)",
    "lr5e-6_r32_ep40": "6차 rank32",
    "lr5e-6_ep100": "7차 100epoch",
    "final_respelled_lr5e-6_ep40": "8차 리스펠링 반영",
}


def chart_val_loss() -> None:
    """에폭별 Val Loss 곡선 — eval/training_log.csv (3~8차 6개 run)."""
    runs = defaultdict(list)
    with (EVAL / "training_log.csv").open(encoding="utf-8") as fp:
        for row in csv.DictReader(fp):
            runs[row["run_id"]].append((int(row["epoch"]), float(row["val_loss"])))

    # 3·7·8차는 lr 5e-6 · rank 16으로 하이퍼파라미터가 같아 40epoch까지 곡선이 거의 포개진다
    # (7차는 그 뒤로 100epoch까지 이어지고, 8차는 학습 텍스트만 다르다). 같은 굵기·실선으로
    # 그리면 먼저 그린 곡선이 사라진 것처럼 보이므로 셋을 다르게 그린다.
    STYLES = {
        "lr5e-6_ep40": dict(linewidth=5.0, alpha=0.30, linestyle="-", zorder=1),
        "lr5e-6_ep100": dict(linewidth=1.6, linestyle="-", zorder=3),
        "final_respelled_lr5e-6_ep40": dict(linewidth=2.2, linestyle="--", zorder=4),
    }

    fig, ax = plt.subplots(figsize=(9, 5.2))
    for run_id, points in runs.items():
        points.sort()
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        style = STYLES.get(run_id, dict(linewidth=1.8, linestyle="-", zorder=2))
        ax.plot(xs, ys, label=RUN_LABELS.get(run_id, run_id), **style)

    ax.annotate(
        "3·7·8차는 하이퍼파라미터가 같아\n40epoch까지 곡선이 겹친다",
        xy=(30, 8.9),
        xytext=(44, 9.6),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", linewidth=1.0, color="dimgray"),
        color="dimgray",
    )

    ax.set_xlabel("epoch")
    ax.set_ylabel("Val Loss (낮을수록 좋음)")
    ax.set_title("TTS LoRA 학습 회차별 Val Loss — 3~8차 (9차는 로그 미보존)")
    ax.set_ylim(8.5, 14)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "chart-tts-val-loss.png", dpi=150)
    plt.close(fig)


def chart_digits() -> None:
    """가격 숫자 인식 — eval/measure_digits.json."""
    data = json.loads((EVAL / "measure_digits.json").read_text(encoding="utf-8"))
    keys = ["base", "finetuned", "production"]
    labels = ["base\n(PaddleOCR 기본)", "파인튜닝 단독\n(체크포인트)", "production\n(실제 배포 경로)"]
    exact = [data[k]["digit_exact"] * 100 for k in keys]
    parsed = [data[k]["price_parsed_ok"] * 100 for k in keys]
    n = data["base"]["samples"]

    fig, ax = plt.subplots(figsize=(8, 5))
    xs = range(len(keys))
    ax.bar([x - 0.19 for x in xs], exact, width=0.38, label="숫자 완전일치")
    ax.bar([x + 0.19 for x in xs], parsed, width=0.38, label="파서가 금액 복원")
    for x, v in zip(xs, exact):
        ax.text(x - 0.19, v + 1.5, f"{v:.2f}%", ha="center", fontsize=9)
    for x, v in zip(xs, parsed):
        ax.text(x + 0.19, v + 1.5, f"{v:.2f}%", ha="center", fontsize=9)

    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels)
    ax.set_ylabel("%")
    ax.set_ylim(0, 112)
    ax.set_title(f"가격 숫자 인식 — 파인튜닝이 잃은 것과 하이브리드 복구 (합성 이미지 n={n})")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "chart-ocr-digits.png", dpi=150)
    plt.close(fig)


def chart_ocr_categories() -> None:
    """난이도별 OCR 성능 — eval/measure_ocr_final.json."""
    data = json.loads((EVAL / "measure_ocr_final.json").read_text(encoding="utf-8"))
    order = ["01_normal", "02_multi_food", "03_low_quality", "__all__"]
    names = ["01 일반\n(20장)", "02 다중음식\n(15장)", "03 저화질\n(10장)*", "전체\n(50장)"]
    recall = [data["summary"][k]["match_recall"] * 100 for k in order]
    hit = [data["summary"][k]["label_hit"] * 100 for k in order]

    fig, ax = plt.subplots(figsize=(8, 5))
    xs = range(len(order))
    ax.bar([x - 0.19 for x in xs], recall, width=0.38, label="매칭 재현율 (OCR+RapidFuzz)")
    ax.bar([x + 0.19 for x in xs], hit, width=0.38, label="라벨 완전일치 (OCR 단독)")
    for x, v in zip(xs, recall):
        ax.text(x - 0.19, v + 1.5, f"{v:.1f}", ha="center", fontsize=9)
    for x, v in zip(xs, hit):
        ax.text(x + 0.19, v + 1.5, f"{v:.1f}", ha="center", fontsize=9)

    ax.axhline(90, linestyle="--", linewidth=1.2, color="gray")
    ax.text(len(order) - 0.5, 91.5, "목표 90%", fontsize=9, color="gray", ha="right")
    ax.set_xticks(list(xs))
    ax.set_xticklabels(names)
    ax.set_ylabel("%")
    ax.set_ylim(0, 112)
    ax.set_title("OCR 난이도별 성능 — 글자를 틀려도 매칭이 건진다")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "chart-ocr-categories.png", dpi=150)
    plt.close(fig)


def chart_latency() -> None:
    """TTFB 비교 — eval/model_comparison.md 3절의 실측값.

    캐시 히트(1.8ms)와 콜드 라이브 생성(61.3초)은 4자릿수 차이라 로그 축이 아니면
    같은 그림에 그릴 수 없다. 축을 나눠야 보인다는 것 자체가 Plan B 전환의 근거다.
    """
    labels = ["라이브 콜드\n61.3초", "라이브 워밍업 후\n33초", "목표 상한\n7초", "캐시 히트\n1.8ms"]
    values = [61.3, 33.0, 7.0, 0.0018]
    colors = ["#c0504d", "#c0504d", "#7f7f7f", "#4f81bd"]

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(labels, values, color=colors, width=0.55)
    ax.set_yscale("log")
    ax.set_ylabel("초 (로그 축)")
    ax.set_ylim(0.001, 200)
    # 기본 로그 눈금은 지수 표기($10^{-2}$)를 쓰는데, mathtext 폰트에 마이너스 글리프가 없어
    # 한글 폰트 환경에서 깨진다. 사람이 읽는 단위로 직접 적는 편이 어차피 더 낫다.
    ax.set_yticks([0.001, 0.01, 0.1, 1, 10, 100])
    ax.set_yticklabels(["1ms", "10ms", "0.1초", "1초", "10초", "100초"])
    ax.minorticks_off()
    for bar, v in zip(bars, values):
        txt = f"{v*1000:.1f}ms" if v < 1 else f"{v:g}초"
        ax.text(bar.get_x() + bar.get_width() / 2, v * 1.3, txt, ha="center", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    ax.set_title("TTS 응답 시간 — 라이브 생성 vs 사전 생성 캐시 (로컬 실측)")
    fig.tight_layout()
    fig.savefig(OUT / "chart-tts-latency.png", dpi=150)
    plt.close(fig)


def chart_perso() -> None:
    """Perso.ai 대비 UTMOS — eval/TTS_MODULE.md 6-4절 (n=1, 리스펠링 문장 기준)."""
    styles = ["GUIDE", "CAUTION"]
    ours = [4.2916, 4.4408]
    perso = [4.1135, 4.1556]

    fig, ax = plt.subplots(figsize=(7, 4.8))
    xs = range(len(styles))
    ax.bar([x - 0.18 for x in xs], ours, width=0.36, label="우리 모델 (9차 epoch-31)")
    ax.bar([x + 0.18 for x in xs], perso, width=0.36, label="Perso.ai (상용)")
    for x, v in zip(xs, ours):
        ax.text(x - 0.18, v + 0.04, f"{v:.2f}", ha="center", fontsize=9)
    for x, v in zip(xs, perso):
        ax.text(x + 0.18, v + 0.04, f"{v:.2f}", ha="center", fontsize=9)

    ax.set_xticks(list(xs))
    ax.set_xticklabels(styles)
    ax.set_ylabel("UTMOS22 (자동 MOS 예측, 1~5)")
    ax.set_ylim(0, 5.2)
    ax.set_title("상용 서비스 대비 UTMOS — 스타일당 1문장(n=1), 통계적 유의성 없음")
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "chart-tts-perso.png", dpi=150)
    plt.close(fig)


def check_mos() -> str:
    """사람 MOS 분포 그래프는 원본이 비어 있으면 그리지 않는다."""
    rows = list(csv.DictReader((EVAL / "mos_scores.csv").open(encoding="utf-8")))
    if not rows:
        return "MOS 분포 그래프: 미생성 — eval/mos_scores.csv가 헤더만 있고 채점 데이터가 없다"
    return f"MOS 분포 그래프: 채점 {len(rows)}행 확인됨 — 그래프 코드 추가 필요"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    chart_val_loss()
    chart_digits()
    chart_ocr_categories()
    chart_latency()
    chart_perso()
    print(f"한글 폰트: {KO_FONT or '없음 (라벨이 깨질 수 있다)'}")
    print(check_mos())
    print("생성 완료:", ", ".join(sorted(p.name for p in OUT.glob("chart-*.png"))))
