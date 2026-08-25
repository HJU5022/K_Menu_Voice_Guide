// Hanok Editorial: asymmetric editorial layout, cream surfaces, teal trust, coral safety cues.
// Data layer connects to the real K_Menu_Talk.py API via ../lib/api — see that module for
// the HTTP contract. This file only owns screen state and rendering.
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft, ArrowRight, Camera, Check, ChevronDown, CircleHelp, Flame,
  Image as ImageIcon, Minus, Plus, Settings, ShieldCheck, Sparkles, Volume2, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  analyzeMenu, changeCartItem, clearCart, getCart, getFoodDetail, listSupportedFoods, resolveAudioUrl,
  EMPTY_CART, apiBaseUrl, isUsingCustomApi,
  type ApiCandidate, type CartItemRef, type CartLine, type CartResponse, type FoodDetail, type SupportedFood,
} from "@/lib/api";

type Screen = "camera" | "processing" | "candidates" | "order" | "result" | "error";

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
// Where "Scan another menu" / retry on the error screen should send the traveller —
// a failed photo goes back to the camera, a failed detail fetch goes back to the list
// they already have (no reason to make them re-photograph the menu).
type ErrorRetryTarget = "camera" | "candidates";

// Real hero photo, served locally (client/public/assets) instead of the
// /manus-storage/... proxy path, which only resolves inside Manus's own hosted preview.
const CAMERA_HERO_IMAGE = "url('/assets/kmenu-menu-table.jpg')";

const formatWon = (value: number | null) => (value === null ? "Price not shown" : `₩${value.toLocaleString("en-US")}`);

// Copy for the two OCR statuses — reused verbatim from app.py's ERROR_MESSAGES /
// frontend/docs/content-style.md so the wording stays identical across every client.
const OCR_ERROR_COPY: Record<"ocr_empty" | "not_a_menu" | "unsupported_food", { heading: string; hint: string }> = {
  ocr_empty: {
    heading: "We couldn't read this photo",
    hint: "Try brighter lighting, hold the menu straight, and move closer to the text.",
  },
  not_a_menu: {
    heading: "We couldn't find a menu here",
    hint: "Point the camera at a printed menu with prices, then take the photo again.",
  },
  unsupported_food: {
    heading: "Not in our guide yet",
    hint: "Try a different menu item or ask the restaurant staff.",
  },
};
const SERVICE_ERROR_COPY = { heading: "We could not read that menu.", hint: "Try a brighter, steadier photo with the full menu in frame." };

const DETAIL_CARDS: [key: string, label: string][] = [
  ["DESCRIPTION", "Description"],
  ["HOW_TO_EAT", "How to eat"],
  ["INGREDIENT", "Ingredients"],
  ["ALLERGY", "Allergies & dietary needs"],
  ["PRONUNCIATION", "Pronunciation"],
  ["SPICY", "Spice level"],
];

export default function Home() {
  const [screen, setScreen] = useState<Screen>("camera");
  const [modal, setModal] = useState<Modal>(null);
  const [lang, setLang] = useState("EN");

  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<ApiCandidate[]>([]);
  const [selectedCandidate, setSelectedCandidate] = useState<ApiCandidate | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<FoodDetail | null>(null);

  const [cart, setCart] = useState<CartResponse>(EMPTY_CART);
  const [cartError, setCartError] = useState("");

  const [errorHeading, setErrorHeading] = useState(SERVICE_ERROR_COPY.heading);
  const [errorHint, setErrorHint] = useState(SERVICE_ERROR_COPY.hint);
  const [errorRetryTarget, setErrorRetryTarget] = useState<ErrorRetryTarget>("camera");

  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  // A cart outlives a single scan, so it loads once on start rather than after each photo.
  useEffect(() => {
    getCart()
      .then(setCart)
      .catch(() => setCartError("Cart is unavailable right now."));
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
        const copy = OCR_ERROR_COPY[result.status];
        goToError(copy.heading, copy.hint, "camera");
      }
    } catch {
      goToError(SERVICE_ERROR_COPY.heading, SERVICE_ERROR_COPY.hint, "camera");
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
      goToError(SERVICE_ERROR_COPY.heading, "Please try opening this dish again.", "candidates");
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
      setCartError("Could not update the cart. Check your connection and try again.");
    }
  }

  async function handleClearCart() {
    try {
      setCart(await clearCart());
      setCartError("");
    } catch {
      setCartError("Could not empty the cart. Check your connection and try again.");
    }
  }

  const quantityOf = (foodId: number) => cart.items.find((line) => line.food_id === foodId)?.quantity ?? 0;

  const header: HeaderProps = {
    lang,
    setLang,
    onSettings: () => setModal("settings"),
    onHome: () => setScreen("camera"),
  };

  // 설정·개인정보 창은 어느 화면에서 열든 같은 것이어야 한다. 예전에는 첫 화면의
  // return 안에만 있어서, 다른 화면에서는 띄울 창 자체가 없었다. 화면마다 이걸 덧붙인다.
  const modalNode = modal ? <Modal type={modal} onClose={() => setModal(null)} /> : null;
  const withModal = (node: React.ReactNode) => <>{node}{modalNode}</>;

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
          <p className="eyebrow"><Sparkles size={14} /> MENU, MADE CLEAR</p>
          <h1>Scan a Korean menu.</h1>
          <p className="lead">A clearer way to choose dinner, one dish at a time.</p>
          <div className="trust-note"><ShieldCheck size={17} /><span>Your photo is used only to identify menu text. It is not stored.</span></div>
        </section>
        <section className="camera-panel reveal delay-1">
          <div className="photo-frame" style={{ backgroundImage: CAMERA_HERO_IMAGE }}>
            <div className="photo-wash" />
            <div className="scan-corners" aria-hidden="true"><i /><i /><i /><i /></div>
            <div className="plate-label">MENU PLATE · 01</div><div className="frame-caption"><span className="live-dot" /> Point at the menu <b>·</b> live guide</div>
          </div>
          <div className="camera-actions">
            <Button className="primary-button" onClick={() => cameraInputRef.current?.click()}><Camera size={18} /> Take a photo</Button>
            <Button variant="outline" className="secondary-button" onClick={() => uploadInputRef.current?.click()}><ImageIcon size={18} /> Upload a menu photo</Button>
          </div>
          <p className="helper">Read the Korean original before ordering. We help you understand the choice.</p>
        </section>
      </main>
      <footer className="site-footer"><span>© 2026 K-Menu Voice Guide</span><span><button onClick={() => setModal("privacy")}>Privacy</button><b>·</b><button onClick={() => setModal("terms")}>Terms</button></span></footer>
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
  // 로고는 어느 사이트에서나 "첫 화면으로"를 뜻한다. 눌러도 아무 일이 없으면 고장으로
  // 읽히므로 button으로 만든다(div는 키보드로 누를 수 없다).
  return <header className="topbar"><button type="button" className="brand" onClick={onHome} aria-label="Go to the start"><div className="brand-symbol" aria-hidden="true"><span /></div><div><strong><span className="wordmark-k">K</span><i>-</i>menu</strong><span>A thoughtful guide</span></div></button><div className="top-actions"><label className="language"><span>Language</span><select value={lang} onChange={(e) => setLang(e.target.value)}><option>EN</option><option>KR</option><option>JP</option></select><ChevronDown size={14} /></label><button className="icon-button" aria-label="Settings" onClick={onSettings}><Settings size={18} /></button></div>{isUsingCustomApi && <CustomApiNotice />}</header>;
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
  return <div className="center-state"><div className="processing-card"><div className="spinner-ring" /><p className="eyebrow">READING YOUR MENU</p><h2>Finding dishes worth knowing.</h2><p>We are looking at names, prices, and the details that make ordering easier.</p><div className="progress-line"><span /></div></div></div>;
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
  const [lightbox, setLightbox] = useState<{ url: string; attribution: string | null } | null>(null);

  return (
    <div className="app-shell">
      <Header {...header} />
      <main className="content-shell">
        <div className="obang-ribbon" aria-hidden="true"><i /><i /><i /><i /><i /></div>
        <button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back</button>
        {/* The uploaded menu photo is the main visual here — the traveller compares it
            against the candidate cards, so it leads the page instead of sitting as a
            small corner chip. */}
        {photoUrl && (
          <div className="menu-photo-hero">
            <img src={photoUrl} alt="Uploaded menu" />
            <p>Menu photo <b>ready to compare</b></p>
          </div>
        )}
        <div className="section-heading">
          <div>
            <p className="eyebrow">{candidates.length} MATCH{candidates.length === 1 ? "" : "ES"} FOUND</p>
            <h1>What would you like to know?</h1>
            <p className="lead">Add a dish to your list, or open one for a closer guide.</p>
          </div>
        </div>
        <div className="candidate-layout">
          <div className="dish-list">
            {candidates.map((candidate, index) => (
              <DishCard
                // The same dish can legitimately appear as two candidates (matched from two
                // separate menu lines, e.g. two sizes/variants) sharing one food_id — index
                // keeps the React key unique even though the food_id repeats.
                key={`${candidate.food_id}-${index}`}
                candidate={candidate}
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
  candidate, count, onQuantityChange, onDetail, onOpenImage, featured,
}: {
  candidate: ApiCandidate;
  count: number;
  onQuantityChange: (item: CartItemRef, delta: number) => void;
  onDetail: (c: ApiCandidate) => void;
  onOpenImage: (image: { url: string; attribution: string | null }) => void;
  featured: boolean;
}) {
  const cartRef: CartItemRef = { food_id: candidate.food_id, name_kr: candidate.name_kr, name_en: candidate.name_en, price_krw: candidate.price_krw };
  return (
    <article className={`dish-card ${featured ? "featured" : ""}`}>
      {candidate.thumbnail_url ? (
        <button
          type="button"
          className="dish-thumb-button"
          onClick={() => onOpenImage({ url: candidate.thumbnail_url!, attribution: candidate.thumbnail_attribution ?? null })}
          aria-label={`Enlarge photo of ${candidate.name_en}`}
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
          <div><p className="dish-name-en">{candidate.name_en}</p><p className="dish-name-kr">{candidate.name_kr}</p></div>
        </div>
        <div className="dish-meta">
          <span>{formatWon(candidate.price_krw)}</span>
          {candidate.spice_level != null && (
            <span className="spice-mini">{Array.from({ length: 5 }, (_, i) => <Flame key={i} size={13} fill={i < candidate.spice_level! ? "currentColor" : "none"} />)}</span>
          )}
        </div>
        <div className="dish-actions">
          <div className="stepper">
            <button aria-label={`Remove one ${candidate.name_en}`} onClick={() => onQuantityChange(cartRef, -1)} disabled={count === 0}><Minus size={15} /></button>
            <b>{count}</b>
            <button aria-label={`Add one ${candidate.name_en}`} onClick={() => onQuantityChange(cartRef, 1)}><Plus size={15} /></button>
          </div>
          <Button variant="outline" className="small-button" onClick={() => onDetail(candidate)}>View guide <ArrowRight size={15} /></Button>
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
  return (
    <aside className="cart-panel">
      <div className="cart-heading"><div><p className="eyebrow">YOUR SHORTLIST</p><h2>Your cart <span>{cart.item_count}</span></h2></div><CircleHelp size={18} /></div>
      {error && <p className="price-note">{error}</p>}
      {cart.items.length === 0 ? (
        <div className="empty-cart"><span>＋</span><p>Nothing here yet. Use + on a dish to add it.</p></div>
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
      {cart.has_unpriced_items && <p className="price-note">Some dishes had no price on your photo, so they are not in this total.</p>}
      <Button
        variant="outline"
        className="secondary-button"
        style={{ width: "100%", marginBottom: 10 }}
        disabled={cart.item_count === 0}
        onClick={onClearCart}
      >
        Clear cart
      </Button>
      <Button className="primary-button order-button" disabled={cart.item_count === 0} onClick={onOrder}>Order <ArrowRight size={17} /></Button>
    </aside>
  );
}

// This screen is handed to Korean restaurant staff, not read by the traveller — every
// label on it is fixed Korean regardless of the app's own English UI language.
function Order({ header, cart, onBack }: { header: HeaderProps; cart: CartResponse; onBack: () => void }) {
  return (
    <div className="app-shell">
      <Header {...header} />
      <main className="order-shell">
        <div className="obang-ribbon" aria-hidden="true"><i /><i /><i /><i /><i /></div>
        <button className="back-link" onClick={onBack}><ArrowLeft size={16} /> Back</button>
        <div className="order-sheet">
          <div className="order-intro">
            <p className="eyebrow">직원에게 보여주세요</p>
            <h1>주문 내역</h1>
            <p className="lead order-summary-line">테이블 주문 요약입니다. 이 앱에서 주문이 직접 전달되지 않습니다.</p>
          </div>
          <div className="order-lines">
            {cart.items.map((line) => (
              <div className="order-line" key={line.food_id}>
                <div><b>{line.name_kr}</b></div>
                <strong>{line.quantity}개 <em>{line.line_total_display ?? "—"}</em></strong>
              </div>
            ))}
          </div>
          <div className="order-total"><span>총합</span><b>{cart.total_krw_display}</b></div>
          {cart.has_unpriced_items && <p className="price-note">사진에서 가격을 확인하지 못한 메뉴가 있어 총합에 포함되지 않았습니다.</p>}
          <div className="order-warning">
            <ShieldCheck size={18} />
            <p>이 앱은 주문을 식당으로 전송하지 않습니다. 주문 전 메뉴, 가격, 알레르기 여부를 직원과 직접 확인해 주세요.</p>
          </div>
          <Button variant="outline" className="secondary-button" onClick={onBack}><ArrowLeft size={16} /> 메뉴 다시 보기</Button>
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
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const spiceLevel = detail.spice_level ?? candidate.spice_level;
  const audioUrl = useMemo(() => resolveAudioUrl(detail.narration_audio_path), [detail.narration_audio_path]);

  function toggleAudio() {
    if (detail.tts_status !== "ok" || !audioUrl) {
      // Nothing to play yet (TTS wasn't ready when details were fetched) — ask for the
      // detail again rather than inventing a separate "retry TTS" endpoint.
      onRefreshDetail(candidate);
      return;
    }
    if (!audioRef.current) audioRef.current = new Audio(audioUrl);
    if (audioRef.current.src !== audioUrl) audioRef.current.src = audioUrl;
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.onended = () => setIsPlaying(false);
      audioRef.current.play();
      setIsPlaying(true);
    }
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
            <p className="result-en">{detail.name_en}</p>
            <div className="result-pills"><span>{formatWon(candidate.price_krw)}</span></div>
          </div>
          <div className="result-image">
            {candidate.thumbnail_url ? (
              <img src={candidate.thumbnail_url} alt="" />
            ) : (
              <div style={{ width: "100%", height: 310, background: "var(--sand)" }} />
            )}
            <button className="audio-button" onClick={toggleAudio}>
              <Volume2 size={18} /> {detail.tts_status === "ok" ? (isPlaying ? "Pause" : "Hear the name") : "Try audio again"}
            </button>
          </div>
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
  return (
    <div className="center-state">
      <div className="error-card">
        <div className="error-icon"><X size={24} /></div>
        <p className="eyebrow">LET'S TRY THAT AGAIN</p>
        <h2>{heading}</h2>
        <p>{hint}</p>
        <Button className="primary-button" onClick={onRetry}>Take a new photo</Button>
      </div>
    </div>
  );
}

function Modal({ type, onClose }: { type: Exclude<Modal, null>; onClose: () => void }) {
  const title = type === "settings" ? "Settings" : type === "privacy" ? "Privacy Notice" : "Terms of Use";
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal-card" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}><X size={18} /></button>
        <p className="eyebrow">K-MENU VOICE GUIDE</p>
        <h2>{title}</h2>
        {type === "settings" ? (
          <>
            <label className="setting-row"><span>Language</span><select defaultValue="EN"><option>EN</option><option>KR</option><option>JP</option></select></label>
            <label className="setting-row"><span>Camera & Image Processing<small>Allows menu images to be processed in memory for OCR.</small></span><input type="checkbox" defaultChecked /></label>
            <label className="setting-row"><span>Essential Cookies & Analytics<small>Allows session continuity and basic performance measurement.</small></span><input type="checkbox" defaultChecked /></label>
            <SupportedFoodsSection />
          </>
        ) : (
          <p>{type === "privacy" ? "K-Menu Voice Guide respects your privacy. Photos are processed in real time to identify Korean menu text and are not stored on our permanent database." : "This service is an informational guide only. Before ordering, confirm ingredients, preparation methods, and possible cross-contact directly with the restaurant."}</p>
        )}
        <Button className="primary-button" onClick={onClose}>Close</Button>
      </section>
    </div>
  );
}

// What this service can recognize — shown from the settings gear so a traveller can
// check before photographing whether their dish is covered at all.
function SupportedFoodsSection() {
  const [foods, setFoods] = useState<SupportedFood[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    listSupportedFoods()
      .then(setFoods)
      .catch(() => setError("Could not load the supported dishes list."));
  }, []);

  return (
    <div className="setting-row" style={{ display: "block", cursor: "default" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
        Supported dishes
        {foods && (
          <span style={{ padding: "2px 9px", borderRadius: 999, color: "var(--teal)", background: "var(--sand)", fontSize: 11, fontWeight: 800 }}>
            {foods.length}
          </span>
        )}
      </span>
      {error && <small style={{ color: "var(--coral)" }}>{error}</small>}
      {!foods && !error && <small>Loading…</small>}
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
