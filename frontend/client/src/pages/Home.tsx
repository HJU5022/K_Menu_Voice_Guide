// Hanok Editorial: asymmetric editorial layout, cream surfaces, teal trust, coral safety cues.
// Data layer connects to the real K_Menu_Talk.py API via ../lib/api — see that module for
// the HTTP contract. This file only owns screen state and rendering.
import { useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, Camera, Check, ChevronDown, CircleHelp, Flame,
  Image as ImageIcon, Minus, Plus, Settings, ShieldCheck, Volume2, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LangContext, useT } from "@/lang";
import { STRINGS, type Lang, type Strings } from "@/i18n";
import Landing from "./Landing";
import {
  analyzeMenu, changeCartItem, clearCart, getCart, getFoodDetail, listSupportedFoods, resolveAudioUrl,
  EMPTY_CART, apiBaseUrl, isUsingCustomApi,
  type ApiCandidate, type CartItemRef, type CartLine, type CartResponse, type FoodDetail, type SupportedFood,
} from "@/lib/api";

/** 화면 흐름 — landing → camera → candidates → result ↔ order.
 *
 * **새 URL을 만들지 않는다.** 배포처인 Hugging Face static Space에는 SPA fallback이 없어서
 * `/landing` 같은 경로는 새로고침이나 직접 접근 한 번에 404가 된다(App.tsx가 "/index.html"을
 * 따로 받는 것도 같은 이유다). 화면 이동은 전부 이 상태값 하나로 한다. */
type Screen = "landing" | "camera" | "processing" | "candidates" | "order" | "result" | "error";

/** 헤더가 동작하는 데 필요한 것들.
 *
 * 예전에는 화면마다 <Header lang="EN" setLang={() => {}} onSettings={() => {}} /> 처럼
 * **아무것도 하지 않는 함수**를 넘겼다. 그래서 첫 화면 말고는 톱니바퀴를 눌러도 반응이
 * 없었고 언어도 바꿀 수 없었다. 실제 동작을 화면마다 넘긴다. */
type HeaderProps = {
  lang: string;
  setLang: (v: string) => void;
  onSettings: () => void;
  onHome: () => void;
};
type Modal = "settings" | "privacy" | "terms" | null;

/** 고를 수 있는 언어.
 *
 * 예전에는 EN/KR/JP 세 글자만 있었고 **골라도 아무 일도 일어나지 않았다.** 줄임말은
 * 그 언어를 쓰는 사람이 오히려 못 알아본다(한국어 화자에게 "KR"은 우리말이 아니다).
 * 각 언어를 그 언어로 적고, 아직 안 되는 것은 고를 수 없게 두어 기대를 만들지 않는다. */
const LANGUAGES = [
  { code: "en", label: "English", ready: true },
  { code: "ko", label: "한국어", ready: true },
  { code: "zh", label: "中文", ready: false },
] as const;
// Where "Scan another menu" / retry on the error screen should send the traveller —
// a failed photo goes back to the camera, a failed detail fetch goes back to the list
// they already have (no reason to make them re-photograph the menu).
type ErrorRetryTarget = "camera" | "candidates";

// Real hero photo, served locally (client/public/assets) instead of the
// /manus-storage/... proxy path, which only resolves inside Manus's own hosted preview.
const CAMERA_HERO_IMAGE = "url('/assets/kmenu-menu-table.jpg')";

/** 사진 위 상자와 목록 번호에 돌려 쓰는 색.
 *
 * 앱 `mobile/lib/screens/menu_photo_overlay.dart`의 팔레트와 **같은 값**이어야 한다.
 * 사진의 상자와 목록의 배지가 같은 색·같은 번호일 때만 "이 카드가 사진의 저기"를
 * 눈으로 이을 수 있다. 6개를 넘으면 색이 돌지만 번호가 같이 붙어 헷갈리지 않는다. */
const BOX_COLORS = ["#D32F2F", "#1976D2", "#388E3C", "#F57C00", "#7B1FA2", "#0097A7"];
const boxColor = (index: number) => BOX_COLORS[index % BOX_COLORS.length];
/** 번호는 두 자리로 적는다(01, 02 …) — 앱과 같게 맞춘다. */
const boxLabel = (index: number) => String(index + 1).padStart(2, "0");

const formatWon = (value: number | null) => (value === null ? "Price not shown" : `₩${value.toLocaleString("en-US")}`);

// Copy for the two OCR statuses — reused verbatim from app.py's ERROR_MESSAGES /
// docs/content-style.md so the wording stays identical across every client.
/** 서버가 준 status에 맞는 안내 문구를 고른다.
 *
 * 셋을 갈라두는 이유: 원인이 다르면 사용자가 할 일도 다르다. 흐리게 찍혔으면 다시 찍으면
 * 되고, 메뉴판이 아니면 다른 것을 찍어야 하고, 아는 음식이 없으면 다시 찍어도 소용없다. */
function ocrErrorCopy(t: Strings, status: "ocr_empty" | "not_a_menu" | "unsupported_food") {
  if (status === "ocr_empty") return { heading: t.errOcrEmptyTitle, hint: t.errOcrEmptyHint };
  if (status === "not_a_menu") return { heading: t.errNotAMenuTitle, hint: t.errNotAMenuHint };
  return { heading: t.errUnsupportedTitle, hint: t.errUnsupportedHint };
}

const DETAIL_CARDS: [key: string, label: string][] = [
  ["DESCRIPTION", "Description"],
  ["HOW_TO_EAT", "How to eat"],
  ["INGREDIENT", "Ingredients"],
  ["ALLERGY", "Allergies & dietary needs"],
  ["PRONUNCIATION", "Pronunciation"],
  ["SPICY", "Spice level"],
];

export default function Home() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [modal, setModal] = useState<Modal>(null);
  const [lang, setLang] = useState("en");
  // Home은 Provider 바깥이라 useT()가 기본값을 읽는다. 여기서는 고른 언어로 직접 꺼낸다.
  const t = STRINGS[lang as Lang];

  // 문서에 지금 언어를 적어둔다. 글꼴과 줄바꿈 규칙이 언어마다 달라야 하는데(한국어는
  // 단어 중간에서 줄이 바뀌면 안 된다), CSS가 그것을 알 방법이 이것뿐이다.
  // 화면 읽기 프로그램도 이 값을 보고 발음을 고른다.
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<ApiCandidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<ApiCandidate | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<FoodDetail | null>(null);

  const [cart, setCart] = useState<CartResponse>(EMPTY_CART);
  const [cartError, setCartError] = useState("");

  const [errorHeading, setErrorHeading] = useState(STRINGS.en.errServiceTitle);
  const [errorHint, setErrorHint] = useState(STRINGS.en.errServiceHint);
  const [errorRetryTarget, setErrorRetryTarget] = useState<ErrorRetryTarget>("camera");

  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const [camera, setCamera] = useState(false);
  const [cameraNotice, setCameraNotice] = useState<CameraFailure | null>(null);

  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  // A cart outlives a single scan, so it loads once on start rather than after each photo.
  useEffect(() => {
    getCart()
      .then(setCart)
      .catch(() => setCartError(t.cartUnavailable));
  }, []);

  function goToError(heading: string, hint: string, retryTarget: ErrorRetryTarget) {
    setErrorHeading(heading);
    setErrorHint(hint);
    setErrorRetryTarget(retryTarget);
    setScreen("error");
  }

  async function handlePhoto(file: File) {
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    setPhotoUrl(URL.createObjectURL(file));
    setScreen("processing");

    try {
      const result = await analyzeMenu(file);
      if (result.status === "candidates_found") {
        setCandidates(result.candidates);
        setScreen("candidates");
        // A new menu means a new restaurant — clear the cart so dishes from the last
        // place don't linger. A failed/unsupported read below is not a new restaurant,
        // so the cart is left untouched in those branches.
        clearCart().then(setCart).catch(() => {});
      } else {
        const copy = ocrErrorCopy(t, result.status);
        goToError(copy.heading, copy.hint, "camera");
      }
    } catch {
      goToError(t.errServiceTitle, t.errServiceHint, "camera");
    }
  }

  async function goDetail(candidate: ApiCandidate) {
    setSelectedCandidate(candidate);
    setScreen("processing");
    try {
      const detail = await getFoodDetail(candidate.food_id);
      setSelectedDetail(detail);
      setScreen("result");
    } catch {
      goToError(t.errServiceTitle, t.errServiceHint, "candidates");
    }
  }

  // Every +/- replaces the whole cart with what the server returns, so the cards and the
  // cart panel can never drift apart. The merge/zero-quantity rules live only on the
  // server (src/cart/store.py) — nothing here recomputes them.
  async function updateCount(item: CartItemRef, quantityDelta: number) {
    try {
      setCart(await changeCartItem(item, quantityDelta));
      setCartError("");
    } catch {
      setCartError(t.cartChangeFailed);
    }
  }

  async function handleClearCart() {
    try {
      setCart(await clearCart());
      setCartError("");
    } catch {
      setCartError(t.cartClearFailed);
    }
  }

  const quantityOf = (foodId: number) => cart.items.find((line) => line.food_id === foodId)?.quantity ?? 0;

  const header: HeaderProps = {
    lang,
    setLang,
    onSettings: () => setModal("settings"),
    onHome: () => setScreen("landing"),
  };

  // 설정·개인정보 창은 어느 화면에서 열든 같은 것이어야 한다. 예전에는 첫 화면의
  // return 안에만 있어서, 다른 화면에서는 띄울 창 자체가 없었다. 화면마다 이걸 덧붙인다.
  const modalNode = modal ? <Modal type={modal} lang={lang} setLang={setLang} onClose={() => setModal(null)} /> : null;
  // 고른 언어를 화면 전체가 함께 보게 감싼다. 안쪽 조각들은 useT()로 직접 꺼내 쓴다.
  const withModal = (node: React.ReactNode) => (
    <LangContext.Provider value={lang as Lang}>{node}{modalNode}</LangContext.Provider>
  );

  // 랜딩은 껍데기·머리말·꼬리말을 촬영 화면과 **똑같이** 쓴다(언어 선택과 설정이
  // 화면마다 달라지지 않게). 알맹이만 Landing.tsx가 그린다.
  if (screen === "landing")
    return withModal(
      <div className="app-shell">
        <Header {...header} />
        <Landing onStart={() => setScreen("camera")} />
        <SiteFooter onPrivacy={() => setModal("privacy")} onTerms={() => setModal("terms")} />
      </div>
    );
  if (screen === "processing") return withModal(<Processing />);
  if (screen === "candidates")
    return withModal(
      <Candidates
        header={header}
        candidates={candidates}
        cart={cart}
        cartError={cartError}
        photoUrl={photoUrl}
        quantityOf={quantityOf}
        onBack={() => setScreen("camera")}
        onOrder={() => cart.item_count > 0 && setScreen("order")}
        onDetail={goDetail}
        onQuantityChange={updateCount}
        onClearCart={handleClearCart}
      />
    );
  if (screen === "order") return withModal(<Order header={header} cart={cart} onBack={() => setScreen("candidates")} />);
  if (screen === "result" && selectedCandidate && selectedDetail)
    return withModal(<Result header={header} candidate={selectedCandidate} detail={selectedDetail} onBack={() => setScreen("candidates")} onRefreshDetail={goDetail} />);
  if (screen === "error")
    return withModal(
      <ErrorState
        heading={errorHeading}
        hint={errorHint}
        onRetry={() => setScreen(errorRetryTarget)}
      />
    );

  return withModal(
    <div className="app-shell">
      <Header {...header} />
      <main className="camera-layout">
        <section className="camera-copy reveal">
          <h1>{t.cameraTitle}</h1>
          {/* 서비스 설명(heroEyebrow·heroLead)과 사진 처리 안내(privacyNote)는 랜딩으로
              옮겼다. 여기서 같은 말을 되풀이하면 "Get started"를 눌렀는데 제자리인 것처럼
              읽힌다. 이 자리에는 **좋은 사진을 얻는 법**만 남긴다 — 메뉴판이 화면 밖으로
              잘리면 OCR이 그 줄을 통째로 놓친다. */}
          <p className="lead">{t.cameraLead}</p>
        </section>
        <section className="camera-panel reveal delay-1">
          <div className="photo-frame" style={{ backgroundImage: CAMERA_HERO_IMAGE }}>
            <div className="photo-wash" />
            <div className="scan-corners" aria-hidden="true"><i /><i /><i /><i /></div>
            <div className="plate-label">MENU PLATE · 01</div><div className="frame-caption"><span className="live-dot" /> Point at the menu <b>·</b> live guide</div>
          </div>
          <div className="camera-actions">
            {/* 촬영은 이 서비스의 핵심 동작이다 — 식당에서 메뉴판을 찍는 것.
                카메라를 직접 열어 찍는다. 권한이 거부되거나 카메라가 없는 기기에서는
                파일 선택으로 넘어간다(아래 CameraCapture 설명 참고). */}
            <Button className="primary-button" onClick={() => { setCameraNotice(null); setCamera(true); }}><Camera size={18} /> {t.takePhoto}</Button>
            <Button variant="outline" className="secondary-button" onClick={() => uploadInputRef.current?.click()}><ImageIcon size={18} /> {t.uploadPhoto}</Button>
          </div>
          {cameraNotice && (
            <p className="camera-notice" role="status">
              {cameraNotice === "denied"
                ? "Camera access is blocked. Allow the camera for this site in your browser (usually a icon in the address bar), then tap Take a photo again."
                : cameraNotice === "none"
                  ? "No camera found on this device."
                  : "This browser can't open the camera here."}
              {" "}
              <button type="button" className="link-button" onClick={() => cameraInputRef.current?.click()}>
                Choose a photo instead
              </button>
            </p>
          )}
          <p className="helper">{t.cameraHelper}</p>
        </section>
      </main>
      <SiteFooter onPrivacy={() => setModal("privacy")} onTerms={() => setModal("terms")} />
      {camera && (
        <CameraCapture
          onClose={() => setCamera(false)}
          onCaptured={(file) => { setCamera(false); setCameraNotice(null); handlePhoto(file); }}
          onUnavailable={(reason) => { setCamera(false); setCameraNotice(reason); }}
          onPickFile={() => { setCamera(false); cameraInputRef.current?.click(); }}
        />
      )}
      {/* Hidden real inputs behind the styled buttons above — capture="environment" opens
          the rear camera directly on a phone, the plain input opens the gallery/file picker. */}
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        style={{ display: "none" }}
        onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) handlePhoto(file); }}
      />
      <input
        ref={uploadInputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) handlePhoto(file); }}
      />
    </div>
  );
}

function Header({ lang, setLang, onSettings, onHome }: HeaderProps) {
  const t = useT();
  // 로고는 어느 사이트에서나 "첫 화면으로"를 뜻한다. 눌러도 아무 일이 없으면 고장으로
  // 읽히므로 button으로 만든다(div는 키보드로 누를 수 없다).
  return <header className="topbar"><button type="button" className="brand" onClick={onHome} aria-label={t.goHome}><div className="brand-symbol" aria-hidden="true"><span /></div><div><strong><span className="wordmark-k">K</span><i>-</i>menu</strong><span>{t.brandTagline}</span></div></button><div className="top-actions"><label className="language"><span>{t.language}</span><select value={lang} onChange={(e) => setLang(e.target.value)}>{LANGUAGES.map((l) => <option key={l.code} value={l.code} disabled={!l.ready}>{l.ready ? l.label : `${l.label} (coming soon)`}</option>)}</select><ChevronDown size={14} /></label><button className="icon-button" aria-label={t.settings} onClick={onSettings}><Settings size={18} /></button></div>{isUsingCustomApi && <CustomApiNotice />}</header>;
}

/** 꼬리말 — 랜딩과 촬영 화면이 같은 것을 쓴다.
 *
 * 예전에는 촬영 화면의 return 안에 직접 적혀 있었다. 랜딩이 생기면서 두 곳이 필요해졌는데,
 * 같은 마크업을 두 벌 두면 한쪽만 고쳐져 개인정보·이용약관 링크가 화면마다 달라진다. */
function SiteFooter({ onPrivacy, onTerms }: { onPrivacy: () => void; onTerms: () => void }) {
  const t = useT();
  return <footer className="site-footer"><span>© 2026 K-Menu Voice Guide</span><span><button onClick={onPrivacy}>{t.privacy}</button><b>·</b><button onClick={onTerms}>{t.terms}</button></span></footer>;
}

/** 기본 서버가 아닌 곳을 보고 있을 때만 뜨는 알림.
 *
 * 주소창의 `?api=`로 서버를 바꿔놓고 잊으면, 나중에 "왜 결과가 다르지"의 원인을 찾기가
 * 아주 어렵다. 지금 어디를 보고 있는지 화면에 계속 붙여둔다. 누르면 원래대로 돌아간다. */
function CustomApiNotice() {
  return (
    <button
      className="custom-api-notice"
      title="기본 서버로 되돌리려면 누르세요"
      onClick={() => {
        window.localStorage.removeItem("kmenu-api-base-url");
        window.location.href = window.location.pathname;
      }}
    >
      server: {apiBaseUrl.replace(/^https?:\/\//, "")} ×
    </button>
  );
}

function Processing() {
  const t = useT();
  return <div className="center-state"><div className="processing-card"><div className="spinner-ring" /><p className="eyebrow">{t.processingEyebrow}</p><h2>{t.processingTitle}</h2><p>{t.processingBody}</p><div className="progress-line"><span /></div></div></div>;
}

function Candidates({
  header, candidates, cart, cartError, photoUrl, quantityOf, onBack, onOrder, onDetail, onQuantityChange, onClearCart,
}: {
  header: HeaderProps;
  candidates: ApiCandidate[];
  cart: CartResponse;
  cartError: string;
  photoUrl: string | null;
  quantityOf: (foodId: number) => number;
  onBack: () => void;
  onOrder: () => void;
  onDetail: (c: ApiCandidate) => void;
  onQuantityChange: (item: CartItemRef, delta: number) => void;
  onClearCart: () => void;
}) {
  const t = useT();
  const [lightbox, setLightbox] = useState<{ url: string; attribution: string | null } | null>(null);
  const [viewer, setViewer] = useState<string | null>(null);

  // 메뉴판에 인쇄된 순서(line_no)로 늘어놓는다. 서버가 주는 순서는 점수 순이라 사진과
  // 목록의 순서가 어긋나 눈으로 짝짓기 어려웠다. 줄 번호가 없는 후보는 뒤로 보낸다
  // (이름이 여러 글자 조각에 걸쳐 잘리면 서버가 줄을 특정하지 못한다).
  // **사진 위 상자와 카드가 반드시 같은 목록을 봐야** 번호와 색이 어긋나지 않는다.
  const ordered = [...candidates].sort(
    (a, b) => (a.line_no ?? Number.MAX_SAFE_INTEGER) - (b.line_no ?? Number.MAX_SAFE_INTEGER),
  );

  return (
    <div className="app-shell">
      <Header {...header} />
      <main className="content-shell">
        <div className="obang-ribbon" aria-hidden="true"><i /><i /><i /><i /><i /></div>
        <button className="back-link" onClick={onBack}><ArrowLeft size={16} /> {t.back}</button>
        {/* The uploaded menu photo is the main visual here — the traveller compares it
            against the candidate cards, so it leads the page instead of sitting as a
            small corner chip. */}
        {photoUrl && (
          <div className="menu-photo-hero">
            {/* 상자는 사진 **자체의 크기**를 기준으로 얹어야 한다. 그래서 사진을 감싸는
                칸이 사진 크기에 딱 맞아야 한다(inline-block). 칸이 사진보다 크면 남는
                여백만큼 상자가 밀린다. */}
            {/* 눌러서 크게 볼 수 있다. 메뉴판은 글자가 작아 화면에 맞춰 줄이면 읽기
                어려운데, 사용자가 확인하고 싶은 것이 바로 그 글자다. */}
            <button
              type="button"
              className="menu-photo-frame"
              onClick={() => setViewer(photoUrl)}
              aria-label={t.enlargeMenuPhoto}
            >
              <img src={photoUrl} alt="Uploaded menu" />
              {ordered.map((candidate, index) =>
                candidate.source ? (
                  <span
                    key={`${candidate.food_id}-${index}`}
                    className="menu-photo-box"
                    style={{
                      left: `${candidate.source.left * 100}%`,
                      top: `${candidate.source.top * 100}%`,
                      width: `${candidate.source.width * 100}%`,
                      height: `${candidate.source.height * 100}%`,
                      borderColor: boxColor(index),
                    }}
                  >
                    <b style={{ background: boxColor(index) }}>{boxLabel(index)}</b>
                  </span>
                ) : null,
              )}
            </button>
            <p>
              {t.photoReady} <b>{t.photoReadyStrong}</b>
              {/* 상자가 안 붙은 줄이 있으면 그 수를 밝힌다. 상자가 2개인데 목록이 6줄이면
                  "왜 4개는 표시가 없지"가 되는데, 이름이 여러 글자 조각에 걸쳐 잘리면
                  서버가 위치를 특정하지 못해 생기는 정상 동작이다. */}
              {ordered.some((c) => !c.source) && (
                <span className="photo-note">
                  {" "}· {t.notLocated(ordered.filter((c) => !c.source).length, ordered.length)}
                </span>
              )}
            </p>
          </div>
        )}
        <div className="section-heading">
          <div>
            <p className="eyebrow">{t.matchesFound(candidates.length)}</p>
            <h1>{t.candidatesTitle}</h1>
            <p className="lead">{t.candidatesLead}</p>
          </div>
        </div>
        <div className="candidate-layout">
          <div className="dish-list">
            {ordered.map((candidate, index) => (
              <DishCard
                // The same dish can legitimately appear as two candidates (matched from two
                // separate menu lines, e.g. two sizes/variants) sharing one food_id — index
                // keeps the React key unique even though the food_id repeats.
                key={`${candidate.food_id}-${index}`}
                candidate={candidate}
                index={index}
                count={quantityOf(candidate.food_id)}
                onQuantityChange={onQuantityChange}
                onDetail={onDetail}
                onOpenImage={setLightbox}
                featured={index === 0}
              />
            ))}
          </div>
          <CartPanel cart={cart} error={cartError} onQuantityChange={onQuantityChange} onOrder={onOrder} onClearCart={onClearCart} />
        </div>
      </main>
      {lightbox && <Lightbox image={lightbox} onClose={() => setLightbox(null)} />}
      {viewer && <PhotoViewer url={viewer} onClose={() => setViewer(null)} />}
    </div>
  );
}

/** 카메라를 직접 열어 메뉴판을 찍는 창.
 *
 * 예전에는 `<input capture="environment">`에 기댔다. 그 속성은 **모바일에서만 뜻이 있어**
 * 데스크톱 브라우저는 그냥 파일 선택창을 열었고, 노트북으로는 촬영 자체가 불가능했다.
 * getUserMedia로 카메라를 직접 열면 데스크톱(웹캠)과 폰(후면 카메라)에서 모두 찍을 수 있다.
 *
 * **권한을 거부하거나 카메라가 없으면** 조용히 실패하지 않고 파일 선택으로 넘긴다 —
 * 사용자는 어떻게든 사진을 올릴 수 있어야 한다.
 *
 * 스트림은 창을 닫을 때 반드시 멈춘다. 안 그러면 카메라 표시등이 계속 켜져 있어
 * "이 사이트가 나를 보고 있나" 하는 인상을 준다. */
type CameraFailure = "denied" | "none" | "unsupported";

function CameraCapture({
  onClose, onCaptured, onUnavailable, onPickFile,
}: {
  onClose: () => void;
  onCaptured: (file: File) => void;
  // 카메라가 안 열린 경우 — 왜 안 됐는지 부모가 안내한다.
  onUnavailable: (reason: CameraFailure) => void;
  // 창 안의 "대신 사진 올리기" — 실패가 아니라 사용자가 고른 것이라 안내를 띄우지 않는다.
  onPickFile: () => void;
}) {
  const t = useT();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function open() {
      try {
        // 뒷면 카메라를 **선호**하되 강제하지 않는다(ideal). 웹캠뿐인 기기에서
        // exact로 걸면 카메라가 아예 안 열린다.
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" } },
          audio: false,
        });
        if (cancelled) { stream.getTracks().forEach((track) => track.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
        setReady(true);
      } catch (err) {
        // 왜 못 열었는지까지 올려보낸다. 예전에는 이유를 삼키고 조용히 파일 선택창을
        // 열었는데, 사용자에게는 "촬영을 눌렀더니 업로드 창이 뜬다"로만 보였다
        // (실측 2026-08-26). 권한 거부는 사용자가 직접 풀 수 있는 문제라, 무엇이
        // 막혔는지 알려주지 않으면 고칠 방법이 없다.
        if (cancelled) return;
        const name = (err as { name?: string } | null)?.name;
        if (name === "NotAllowedError" || name === "SecurityError") onUnavailable("denied");
        else if (name === "NotFoundError" || name === "OverconstrainedError") onUnavailable("none");
        else onUnavailable("unsupported");
      }
    }

    open();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
    // onUnavailable은 부모가 매번 새로 만들지만, 이 효과는 창이 열릴 때 한 번만 돈다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function shoot() {
    const video = videoRef.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        onCaptured(new File([blob], "menu.jpg", { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  }

  return (
    <div className="modal-backdrop camera-backdrop" onClick={onClose}>
      <div className="camera-stage" onClick={(e) => e.stopPropagation()}>
        <video ref={videoRef} autoPlay playsInline muted />
        {!ready && <p className="camera-waiting">{t.cameraOpening}</p>}
        <div className="camera-tools">
          <button type="button" onClick={onClose}>{t.close}</button>
          <button type="button" className="camera-shutter" onClick={shoot} disabled={!ready} aria-label={t.takePhoto} />
          <button type="button" onClick={onPickFile}>{t.uploadInstead}</button>
        </div>
      </div>
    </div>
  );
}

/** 올린 메뉴판 사진을 크게 보는 창 — 확대·축소·이동.
 *
 * 메뉴판은 글자가 작아서 화면에 맞춰 줄이면 읽을 수 없는데, 사용자가 확인하고 싶은 것이
 * 바로 그 글자다("내가 찍은 게 제대로 읽혔나").
 *
 * 마우스와 손가락을 모두 받는다 — 휠/손가락 두 개로 확대, 끌어서 이동, 두 번 눌러 원래대로.
 * 배율이 1일 때는 이동을 막는다. 화면에 다 들어와 있는데 끌리면 고장으로 읽힌다. */
function PhotoViewer({ url, onClose }: { url: string; onClose: () => void }) {
  const t = useT();
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  // 끄는 동안의 시작점. 화면을 다시 그리지 않아도 되는 값이라 ref에 둔다.
  const drag = useRef<{ x: number; y: number } | null>(null);
  const pinch = useRef<number | null>(null);

  const reset = () => { setScale(1); setOffset({ x: 0, y: 0 }); };
  const zoomBy = (delta: number) =>
    setScale((current) => {
      const next = Math.min(6, Math.max(1, current + delta));
      if (next === 1) setOffset({ x: 0, y: 0 });
      return next;
    });

  function touchDistance(touches: React.TouchList) {
    const [a, b] = [touches[0], touches[1]];
    return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
  }

  return (
    <div className="modal-backdrop photo-viewer-backdrop" onClick={onClose}>
      <div
        className="photo-viewer"
        onClick={(e) => e.stopPropagation()}
        onWheel={(e) => zoomBy(e.deltaY > 0 ? -0.3 : 0.3)}
        onDoubleClick={reset}
        onMouseDown={(e) => { if (scale > 1) drag.current = { x: e.clientX - offset.x, y: e.clientY - offset.y }; }}
        onMouseMove={(e) => { if (drag.current) setOffset({ x: e.clientX - drag.current.x, y: e.clientY - drag.current.y }); }}
        onMouseUp={() => { drag.current = null; }}
        onMouseLeave={() => { drag.current = null; }}
        onTouchStart={(e) => {
          if (e.touches.length === 2) pinch.current = touchDistance(e.touches);
          else if (scale > 1) drag.current = { x: e.touches[0].clientX - offset.x, y: e.touches[0].clientY - offset.y };
        }}
        onTouchMove={(e) => {
          if (e.touches.length === 2 && pinch.current) {
            const now = touchDistance(e.touches);
            zoomBy((now - pinch.current) / 200);
            pinch.current = now;
          } else if (drag.current) {
            setOffset({ x: e.touches[0].clientX - drag.current.x, y: e.touches[0].clientY - drag.current.y });
          }
        }}
        onTouchEnd={() => { drag.current = null; pinch.current = null; }}
      >
        <img
          src={url}
          alt=""
          draggable={false}
          style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`, cursor: scale > 1 ? "grab" : "default" }}
        />
      </div>
      <div className="photo-viewer-tools" onClick={(e) => e.stopPropagation()}>
        <button type="button" onClick={() => zoomBy(-0.5)} aria-label={t.zoomOut}><Minus size={18} /></button>
        <span>{Math.round(scale * 100)}%</span>
        <button type="button" onClick={() => zoomBy(0.5)} aria-label={t.zoomIn}><Plus size={18} /></button>
        <button type="button" onClick={reset}>{t.reset}</button>
        <button type="button" onClick={onClose} aria-label={t.close}><X size={18} /></button>
      </div>
    </div>
  );
}

// Tapping a candidate's thumbnail opens the dish's real photo full-size with its credit
// overlaid — the source dataset requires attribution shown alongside the image itself.
function Lightbox({ image, onClose }: { image: { url: string; attribution: string | null }; onClose: () => void }) {
  return (
    <div className="modal-backdrop lightbox-backdrop" onClick={onClose}>
      <figure className="lightbox-figure" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close lightbox-close" onClick={onClose} aria-label="Close"><X size={18} /></button>
        <img src={image.url} alt="" />
        {image.attribution && <figcaption className="lightbox-caption">{image.attribution}</figcaption>}
      </figure>
    </div>
  );
}

function DishCard({
  candidate, index, count, onQuantityChange, onDetail, onOpenImage, featured,
}: {
  candidate: ApiCandidate;
  /** 목록에서 몇 번째인가 — 사진 위 상자와 짝을 맞추는 데 쓴다. */
  index: number;
  count: number;
  onQuantityChange: (item: CartItemRef, delta: number) => void;
  onDetail: (c: ApiCandidate) => void;
  onOpenImage: (image: { url: string; attribution: string | null }) => void;
  featured: boolean;
}) {
  const t = useT();
  const lang = useContext(LangContext);
  const cartRef: CartItemRef = { food_id: candidate.food_id, name_kr: candidate.name_kr, name_en: candidate.name_en, price_krw: candidate.price_krw };
  // 맵기를 먼저, 재료를 뒤에 놓는다. 맵기는 "먹을 수 있는가"를 가르는 정보라 먼저 보여야 한다.
  // 어느 쪽에서 왔는지(kind)를 들고 다니는 이유는 색을 다르게 주기 위해서다 — tier 유무로
  // 판별하면 맵기인데 tier가 비어 있는 행이 재료로 섞인다.
  const mods = [
    ...candidate.modifiers.spice.map((m) => ({ ...m, kind: "spice" as const })),
    ...candidate.modifiers.ingredient.map((m) => ({ ...m, kind: "ingredient" as const })),
  ];
  return (
    <article className={`dish-card ${featured ? "featured" : ""}`}>
      {/* 사진 위 상자와 같은 번호·같은 색. 이것이 카드와 사진을 잇는 유일한 단서다. */}
      <span className="dish-index" style={{ background: boxColor(index) }}>{boxLabel(index)}</span>
      {candidate.thumbnail_url ? (
        <button
          type="button"
          className="dish-thumb-button"
          onClick={() => onOpenImage({ url: candidate.thumbnail_url!, attribution: candidate.thumbnail_attribution ?? null })}
          aria-label={t.enlargePhoto(candidate.name_en)}
        >
          <img className="dish-thumb" src={candidate.thumbnail_url} alt="" />
        </button>
      ) : (
        // No photo on this food row — reuse the same slot/sizing with a plain initial
        // instead of a broken <img>, using only colors already defined in index.css.
        <div className="dish-thumb" style={{ background: "var(--sand)", display: "grid", placeItems: "center", color: "var(--muted)", fontSize: 28, fontWeight: 800 }}>
          {candidate.name_en.charAt(0)}
        </div>
      )}
      <div className="dish-info">
        <div className="dish-title">
          {/* 읽는 사람이 영어권 여행자라 영어 이름을 크게, 한국어를 보조로 둔다.
              앱(candidates_screen.dart)과 같은 순서다.
              "Best match / Menu match" 라벨은 뺐다 — 무엇에 견줘 최고인지 알 수 없어
              외국인에게는 "이게 더 정확한가?"라는 오해만 남겼다. */}
          <div>
            <p className="dish-name-en">{candidate.name_en}</p>
            <p className="dish-name-kr">{candidate.name_kr}</p>
            {/* 메뉴판에 실제로 인쇄된 글자. 등록 이름과 다를 때만 보여준다 — 같으면 같은
                말을 두 번 적는 꼴이다. 이 줄이 없으면 "족발 ₩31,000"과 "족발 ₩33,000"이
                같은 메뉴가 두 번 뜬 것처럼 보인다(실제로는 반반족발과 족발처럼 다른 줄이다). */}
            {/* 메뉴 줄에 붙어 있던 수식어를 **읽는 사람의 언어로** 보여준다.
                같은 음식이 여러 줄 나올 때(돼지김치찌개 / 참치김치찌개) 지금까지는 아래
                한국어 줄이 유일한 구분 수단이었는데, 이 서비스를 쓰는 사람은 그 글자를
                읽지 못한다. Kimchi Jjigae가 둘 떠 있어도 [Pork]와 [Tuna]로 고를 수 있게 한다. */}
            {mods.length > 0 && (
              <ul className="dish-mods">
                {mods.map((m) => (
                  <li key={`${m.kind}-${m.keyword}`} className={`dish-mod dish-mod-${m.kind}`}>
                    {lang === "ko" ? m.keyword : m.keyword_en ?? m.keyword}
                  </li>
                ))}
              </ul>
            )}
            {candidate.name_text && candidate.name_text !== candidate.name_kr && (
              <p className="dish-menu-text" lang="ko">{t.menuLinePrefix}: {candidate.name_text}</p>
            )}
          </div>
        </div>
        <div className="dish-meta">
          <span>{formatWon(candidate.price_krw)}</span>
          {candidate.spice_level != null && (
            <span className="spice-mini">{Array.from({ length: 5 }, (_, i) => <Flame key={i} size={13} fill={i < candidate.spice_level! ? "currentColor" : "none"} />)}</span>
          )}
        </div>
        <div className="dish-actions">
          <div className="stepper">
            <button aria-label={t.removeOne(candidate.name_en)} onClick={() => onQuantityChange(cartRef, -1)} disabled={count === 0}><Minus size={15} /></button>
            <b>{count}</b>
            <button aria-label={t.addOne(candidate.name_en)} onClick={() => onQuantityChange(cartRef, 1)}><Plus size={15} /></button>
          </div>
          <Button variant="outline" className="small-button" onClick={() => onDetail(candidate)}>{t.viewGuide} <ArrowRight size={15} /></Button>
        </div>
      </div>
    </article>
  );
}

function CartPanel({
  cart, error, onQuantityChange, onOrder, onClearCart,
}: {
  cart: CartResponse;
  error: string;
  onQuantityChange: (item: CartItemRef, delta: number) => void;
  onOrder: () => void;
  onClearCart: () => void;
}) {
  const t = useT();
  const [showHelp, setShowHelp] = useState(false);

  return (
    <aside className="cart-panel">
      <div className="cart-heading">
        <div><p className="eyebrow">{t.cartEyebrow}</p><h2>{t.cartTitle} <span>{cart.item_count}</span></h2></div>
        {/* 예전에는 물음표가 **그림일 뿐** 눌러도 아무 일이 없었다. 누를 수 있게 보이는데
            반응이 없으면 고장으로 읽힌다. 눌러서 이 목록이 무엇인지 여닫게 한다. */}
        <button
          type="button"
          className="cart-help-button"
          aria-expanded={showHelp}
          aria-label={t.cartHelpLabel}
          onClick={() => setShowHelp((open) => !open)}
        >
          <CircleHelp size={18} />
        </button>
      </div>
      {showHelp && (
        <p className="cart-help-text">
          {t.cartHelp}
        </p>
      )}
      {error && <p className="price-note">{error}</p>}
      {cart.items.length === 0 ? (
        <div className="empty-cart"><span>＋</span><p>{t.cartEmpty}</p></div>
      ) : (
        <div className="cart-lines">
          {cart.items.map((line) => (
            <div className="cart-line" key={line.food_id}>
              <div><b>{line.name_kr}</b><span>{line.name_en}</span></div>
              <div className="line-right">
                <strong>{line.line_total_display ?? "—"}</strong>
                <div className="mini-stepper">
                  <button onClick={() => onQuantityChange(line, -1)}><Minus size={12} /></button>
                  <span>{line.quantity}</span>
                  <button onClick={() => onQuantityChange(line, 1)}><Plus size={12} /></button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="cart-total"><span>Total</span><b>{cart.total_krw_display}</b></div>
      {cart.has_unpriced_items && <p className="price-note">{t.orderUnpriced}</p>}
      <Button
        variant="outline"
        className="secondary-button"
        style={{ width: "100%", marginBottom: 10 }}
        disabled={cart.item_count === 0}
        onClick={onClearCart}
      >
        {t.clearCart}
      </Button>
      <Button className="primary-button order-button" disabled={cart.item_count === 0} onClick={onOrder}>{t.order} <ArrowRight size={17} /></Button>
    </aside>
  );
}

// This screen is handed to Korean restaurant staff, not read by the traveller — every
// label on it is fixed Korean regardless of the app's own English UI language.
function Order({ header, cart, onBack }: { header: HeaderProps; cart: CartResponse; onBack: () => void }) {
  const t = useT();
  return (
    <div className="app-shell">
      <Header {...header} />
      <main className="order-shell">
        <div className="obang-ribbon" aria-hidden="true"><i /><i /><i /><i /><i /></div>
        <button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back</button>
        {/* 이 화면은 **두 사람이 읽는다.** 화면을 든 여행자와, 건네받아 보는 종업원이다.
            예전에는 전부 한국어라 정작 주문하는 사람이 자기 주문을 읽지 못했다.
            읽는 사람을 기준으로 나눈다 — 여행자에게 하는 말은 영어로, 종업원이 봐야 하는
            부분(메뉴 이름·수량·합계)은 한국어로 둔다. 둘 다 필요한 곳에만 나란히 적는다. */}
        <div className="order-sheet">
          <div className="order-intro">
            <p className="eyebrow">{t.orderEyebrow}</p>
            <h1>{t.orderTitle}</h1>
            <p className="lead order-summary-line">{t.orderLead}</p>
          </div>

          {/* 여기서부터 종업원이 읽는 자리. 한국어로 둔다. */}
          <p className="order-staff-note" lang="ko">아래는 손님이 고른 메뉴입니다.</p>
          <div className="order-lines">
            {cart.items.map((line) => (
              <div className="order-line" key={line.food_id}>
                {/* 이 줄은 두 사람이 함께 본다 — 종업원은 한국어를 읽고, 손님은 자기가
                  무엇을 시키는지 확인한다. 한쪽만 적으면 둘 중 하나는 읽지 못한다. */}
              <div><b lang="ko">{line.name_kr}</b><span className="order-line-en">{line.name_en}</span></div>
                <strong>{line.quantity}개 <em>{line.line_total_display ?? "—"}</em></strong>
              </div>
            ))}
          </div>
          <div className="order-total"><span lang="ko">총합 <small>{t.cartTotal}</small></span><b>{cart.total_krw_display}</b></div>

          {/* 아래는 다시 여행자에게 하는 말이다. */}
          {cart.has_unpriced_items && (
            <p className="price-note">{t.orderUnpriced}</p>
          )}
          <div className="order-warning">
            <ShieldCheck size={18} />
            <p>{t.orderWarning}</p>
          </div>
          <Button variant="outline" className="secondary-button" onClick={onBack}><ArrowLeft size={16} /> {t.backToDishes}</Button>
        </div>
      </main>
    </div>
  );
}

function Result({
  header, candidate, detail, onBack, onRefreshDetail,
}: {
  header: HeaderProps;
  candidate: ApiCandidate;
  detail: FoodDetail;
  onBack: () => void;
  onRefreshDetail: (c: ApiCandidate) => void;
}) {
  // 소리가 두 갈래다 — 이름만 읽는 것(이름 옆 스피커)과 설명 전체(아래 재생바).
  // 서버가 각각 다른 파일로 주므로(name_audio_path / narration_audio_path) 하나를
  // 재생하면 다른 하나는 멈춘다. 겹쳐 나오면 둘 다 안 들린다.
  const nameAudioRef = useRef<HTMLAudioElement | null>(null);
  const narrationRef = useRef<HTMLAudioElement | null>(null);
  const [isNamePlaying, setIsNamePlaying] = useState(false);
  const spiceLevel = detail.spice_level ?? candidate.spice_level;
  const narrationUrl = useMemo(
    () => (detail.tts_status === "ok" ? resolveAudioUrl(detail.narration_audio_path) : null),
    [detail.tts_status, detail.narration_audio_path],
  );
  const nameUrl = useMemo(
    () => resolveAudioUrl(detail.name_audio_path ?? null),
    [detail.name_audio_path],
  );

  function toggleName() {
    if (!nameUrl) {
      // 아직 만들어지지 않았다(상세를 받아올 때 TTS가 준비되지 않았던 경우).
      // "TTS만 다시" 하는 엔드포인트를 따로 만들지 않고 상세를 다시 받는다.
      onRefreshDetail(candidate);
      return;
    }
    narrationRef.current?.pause();
    if (!nameAudioRef.current) nameAudioRef.current = new Audio(nameUrl);
    if (nameAudioRef.current.src !== nameUrl) nameAudioRef.current.src = nameUrl;
    if (isNamePlaying) {
      nameAudioRef.current.pause();
      setIsNamePlaying(false);
      return;
    }
    nameAudioRef.current.onended = () => setIsNamePlaying(false);
    nameAudioRef.current.play();
    setIsNamePlaying(true);
  }

  function stopName() {
    nameAudioRef.current?.pause();
    setIsNamePlaying(false);
  }

  return (
    <div className="app-shell">
      <Header {...header} />
      <main className="result-shell">
        <button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back</button>
        <section className="result-hero">
          <div>
            <p className="eyebrow">A CLOSER GUIDE</p>
            <h1><span className="kr-display">{detail.name_kr}</span></h1>
            {/* 이름 옆 스피커 — 이 버튼은 이름만 읽는다. 설명은 아래 재생바가 맡는다.
                화면에는 로마자(Galbitang)가 보이지만 소리는 한글 이름을 읽은 것이다. */}
            <p className="result-en">
              {detail.name_en}
              <button
                type="button"
                className={`name-speaker${isNamePlaying ? " is-playing" : ""}`}
                onClick={toggleName}
                aria-pressed={isNamePlaying}
                aria-label={nameUrl ? `Hear how to say ${detail.name_en}` : "Name audio is not ready — tap to try again"}
                title={nameUrl ? "Hear the name" : "Not ready — tap to try again"}
              >
                <Volume2 size={16} />
              </button>
            </p>
            <div className="result-pills"><span>{formatWon(candidate.price_krw)}</span></div>
          </div>
          <div className="result-image">
            {candidate.thumbnail_url ? (
              <img src={candidate.thumbnail_url} alt="" />
            ) : (
              <div style={{ width: "100%", height: 310, background: "var(--sand)" }} />
            )}
          </div>
        </section>
        {/* 듣는 문장을 눈으로도 따라갈 수 있게 나레이션 원문을 같이 놓는다.
            재생바는 이름 스피커와 떨어뜨려 둔다 — 무엇을 누르면 무엇이 나오는지 헷갈리면
            이름만 듣고 싶은 사람이 설명을 통째로 듣게 된다. */}
        <section className="narration-block">
          <p className="narration-text">{detail.narration_text}</p>
          {narrationUrl ? (
            <audio
              ref={narrationRef}
              className="narration-player"
              controls
              preload="none"
              src={narrationUrl}
              onPlay={stopName}
            />
          ) : (
            <button className="audio-button" onClick={() => onRefreshDetail(candidate)}>
              <Volume2 size={18} /> Try audio again
            </button>
          )}
        </section>
        <div className="obang-ribbon" aria-hidden="true"><i /><i /><i /><i /><i /></div>
        <div className="detail-grid">
          {DETAIL_CARDS.map(([key, title]) => (
            <article className={`detail-card ${key === "ALLERGY" ? "alert-card" : ""}`} key={key}>
              <p className="card-label">{title}</p>
              {key === "SPICY" ? (
                <>
                  {spiceLevel != null && (
                    <div className="flames">{Array.from({ length: 5 }, (_, i) => <Flame key={i} size={20} fill={i < spiceLevel ? "currentColor" : "none"} />)}</div>
                  )}
                  <p>{detail.details[key] ?? ""}</p>
                </>
              ) : (
                <p>{detail.details[key] ?? ""}</p>
              )}
            </article>
          ))}
        </div>
      </main>
    </div>
  );
}

function ErrorState({ heading, hint, onRetry }: { heading: string; hint: string; onRetry: () => void }) {
  const t = useT();
  return (
    <div className="center-state">
      <div className="error-card">
        <div className="error-icon"><X size={24} /></div>
        <p className="eyebrow">LET'S TRY THAT AGAIN</p>
        <h2>{heading}</h2>
        <p>{hint}</p>
        <Button className="primary-button" onClick={onRetry}>{t.takeNewPhoto}</Button>
      </div>
    </div>
  );
}

function Modal({ type, lang, setLang, onClose }: { type: Exclude<Modal, null>; lang: string; setLang: (v: string) => void; onClose: () => void }) {
  const t = useT();
  const title = type === "settings" ? t.settings : type === "privacy" ? t.privacyTitle : t.termsTitle;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}><X size={18} /></button>
        <p className="eyebrow">K-MENU VOICE GUIDE</p>
        <h2>{title}</h2>
        {type === "settings" ? (
          <>
            {/* 헤더의 선택과 같은 값을 쓴다. 예전에는 여기만 따로 놀아서, 설정에서 바꿔도
                헤더는 그대로였다. */}
            <label className="setting-row"><span>{t.language}</span><select value={lang} onChange={(e) => setLang(e.target.value)}>{LANGUAGES.map((l) => <option key={l.code} value={l.code} disabled={!l.ready}>{l.ready ? l.label : `${l.label} (coming soon)`}</option>)}</select></label>

            {/* 체크박스 두 개("Camera & Image Processing", "Essential Cookies & Analytics")를
                뺐다. 켜고 끌 수 있는 것처럼 보였지만 아무 데도 이어져 있지 않았고, 끄면
                서비스가 아예 동작하지 않는 것들이라 애초에 고를 일이 아니다. 대신 무슨 일이
                일어나는지 아래에 사실대로 적는다. */}
            <HowItWorksSection />
            <SupportedFoodsSection />
          </>
        ) : (
          <p>{type === "privacy" ? t.privacyBody : t.termsBody}</p>
        )}
        <Button className="primary-button" onClick={onClose}>{t.close}</Button>
      </section>
    </div>
  );
}

/** 이 서비스가 무엇을 하는지, 사진이 어떻게 다뤄지는지.
 *
 * 예전 설정창에는 켤 수도 끌 수도 없는 체크박스만 있었다. 여행자가 알고 싶은 것은
 * "끌 수 있나"가 아니라 "내 사진이 어떻게 되나"다. 그래서 사실을 그대로 적는다.
 * 음식 사진의 출처도 여기 둔다 — 데이터셋이 출처 표기를 요구한다. */
function HowItWorksSection() {
  const t = useT();
  return (
    <div className="setting-row" style={{ display: "block", cursor: "default" }}>
      <span>{t.settingsHowItWorks}</span>
      <ol style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 12, lineHeight: 1.7, color: "var(--muted)" }}>
        <li>{t.settingsStep1}</li>
        <li>{t.settingsStep2}</li>
        <li>{t.settingsStep3}</li>
      </ol>
      <small style={{ display: "block", marginTop: 10 }}>
        {t.settingsCredit}
      </small>
    </div>
  );
}

// What this service can recognize — shown from the settings gear so a traveller can
// check before photographing whether their dish is covered at all.
function SupportedFoodsSection() {
  const t = useT();
  const [foods, setFoods] = useState<SupportedFood[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listSupportedFoods()
      .then(setFoods)
      .catch(() => setError(t.supportedError));
  }, []);

  return (
    <div className="setting-row" style={{ display: "block", cursor: "default" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {t.supportedDishes}
        {foods && (
          <span style={{ padding: "2px 9px", borderRadius: 999, color: "var(--teal)", background: "var(--sand)", fontSize: 11, fontWeight: 800 }}>
            {foods.length}
          </span>
        )}
      </span>
      {error && <small style={{ color: "var(--coral)" }}>{error}</small>}
      {!foods && !error && <small>{t.supportedLoading}</small>}
      {foods && (
        <ul style={{ listStyle: "none", margin: "10px 0 0", padding: 0, maxHeight: 220, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 4 }}>
          {foods.map((food) => (
            <li key={food.food_id} style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "8px 12px", borderTop: "1px solid var(--line)" }}>
              <strong style={{ color: "var(--teal-dark)", fontSize: 13 }}>{food.name_kr}</strong>
              <span style={{ color: "var(--muted)", fontSize: 12 }}>{food.name_en}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
