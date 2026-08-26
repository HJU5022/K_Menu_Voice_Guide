// Hanok Editorial: 랜딩도 촬영 화면과 **같은** 종이·먹빛·오방색을 쓴다. 다른 디자인으로
// 시작하면 "Get started"를 누른 뒤 딴 서비스로 넘어온 것처럼 읽힌다.
//
// 이 파일은 화면 알맹이(<main>)만 만든다. 껍데기(.app-shell)와 머리말·꼬리말은 Home이
// 씌운다 — 랜딩만 제 머리말을 따로 두면 언어 선택·설정이 화면마다 달라진다.
import { ArrowRight, Camera, ChevronDown, FileText, ScanSearch, ShieldCheck, Sparkles, Volume2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useT } from "@/lang";

// 이미 저장소에 있는 사진을 그대로 쓴다(client/public/assets). 촬영 화면이 쓰는 것과
// 같은 사진이라 두 화면이 한 벌로 읽힌다. `/manus-storage/...` 같은 외부 경로는 배포본에서
// 깨지므로 쓰지 않는다.
const LANDING_HERO_IMAGE = "url('/assets/kmenu-menu-table.jpg')";

export default function Landing({ onStart }: { onStart: () => void }) {
  const t = useT();

  /** 쓰는 순서 세 단계.
   *
   * 번호를 두 자리로 적는 것(01·02·03)은 후보 목록에서 사진 위 상자에 붙는 번호와 같은
   * 표기다 — 이 서비스에서 "몇 번째"는 늘 같은 모양으로 적힌다. */
  const steps = [
    { icon: <Camera size={16} />, label: t.landingStep1, body: t.landingStep1Body },
    { icon: <ScanSearch size={16} />, label: t.landingStep2, body: t.landingStep2Body },
    { icon: <Volume2 size={16} />, label: t.landingStep3, body: t.landingStep3Body },
    { icon: <FileText size={16} />, label: t.landingStep4, body: t.landingStep4Body },
  ];

  return (
    <main className="landing-layout">
      <section className="landing-copy reveal">
        <p className="eyebrow"><Sparkles size={14} /> {t.heroEyebrow}</p>
        <h1>{t.heroTitle}</h1>
        <p className="lead">{t.heroLead}</p>
        {/* 이 화면에서 누를 곳은 하나뿐이다. 처음 온 사람이 "어디부터 눌러야 하지"를
            고민하는 순간, 식당에서 폰을 든 채로 줄이 밀린다. */}
        <Button className="primary-button landing-cta" onClick={onStart}>
          {t.landingCta} <ArrowRight size={18} />
        </Button>
        {/* 사진을 달라고 하기 **전에** 그 사진을 어떻게 다루는지 먼저 밝힌다. 크게 외치지
            않고 시작 단추 바로 아래 작은 글씨로 둔다 — 겁을 주려는 말이 아니다. */}
        <div className="trust-note"><ShieldCheck size={17} /><span>{t.privacyNote}</span></div>
      </section>

      {/* 세 단계는 사진보다 **먼저** 읽혀야 한다. 폰에서는 적힌 순서대로 쌓이고, 넓은
          화면에서만 사진이 오른쪽으로 올라간다(index.css의 grid-template-areas). */}
      <section className="landing-steps-section reveal delay-1">
        <p className="eyebrow">{t.landingStepsEyebrow}</p>
        <ol className="landing-steps">
          {steps.map((step, index) => (
            <li className="landing-step" key={step.label}>
              {/* <details>를 쓴다. 열고 닫는 것을 브라우저가 맡으므로 상태를 들고 있을
                  필요가 없고, 키보드(Enter/Space)와 화면 읽기 프로그램이 그냥 동작한다.
                  새 라이브러리도 필요 없다. */}
              <details className="landing-step-detail">
                <summary>
                  <span className="landing-step-no">{String(index + 1).padStart(2, "0")}</span>
                  <span className="landing-step-icon" aria-hidden="true">{step.icon}</span>
                  <span className="landing-step-label">{step.label}</span>
                  <ChevronDown className="landing-step-chevron" size={16} strokeWidth={2.5} aria-hidden="true" />
                </summary>
                {/* 줄 목록이라 <ul>로 적는다. 화면 읽기 프로그램이 "항목 3개"라고 미리
                    알려주므로, 줄바꿈한 문단보다 따라가기 쉽다. */}
                <ul className="landing-step-body">
                  {step.body.map((line) => <li key={line}>{line}</li>)}
                </ul>
              </details>
            </li>
          ))}
        </ol>
      </section>

      {/* 촬영 화면의 조준선(scan-corners)·상태 표시는 여기 두지 않는다. 그것은 "지금 찍는
          중"이라는 신호라, 아직 아무것도 시작하지 않은 이 화면에서는 거짓말이 된다. */}
      <figure className="camera-panel landing-visual reveal delay-1">
        <div className="photo-frame landing-photo" style={{ backgroundImage: LANDING_HERO_IMAGE }}>
          <div className="photo-wash" />
        </div>
      </figure>
    </main>
  );
}
