import { ChangeEvent, useEffect, useRef, useState } from "react";
import LanguageSelector from "./components/LanguageSelector";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

type Screen = "camera" | "processing" | "candidates" | "result" | "order" | "error";
type ErrorKind = "ocr" | "unsupported" | "service";
type Box = { left: number; top: number; width: number; height: number };
type DetailCategory = "DESCRIPTION" | "HOW_TO_EAT" | "INGREDIENT" | "ALLERGY" | "PRONUNCIATION" | "SPICY";

type ApiCandidate = {
  food_id: number;
  name_kr: string;
  name_en: string;
  score: number;
  // This name matches Supabase foods.thumbnail_url. It stays optional because
  // a dish can still be matched even when its image has not been registered.
  thumbnail_url?: string | null;
  // Photo credit shown next to the thumbnail (e.g. dataset name). Required by
  // the dataset's usage terms whenever the image itself is displayed.
  thumbnail_attribution?: string | null;
  // Read directly from the menu photo (near the dish name), not looked up from a
  // price list. Both fields are null when no price was printed near the dish.
  price_krw?: number | null;
  price_krw_display?: string | null;
  // Where on the uploaded photo this candidate came from, and what the OCR actually
  // read there. Coordinates are ratios (0-1) of the original photo, so they can be
  // laid over the picture at any display size. Null when the dish name was split
  // across detection boxes and no single position could be pinned down.
  source?: {
    text: string;
    left: number;
    top: number;
    width: number;
    height: number;
  } | null;
  modifiers: Record<string, unknown>;
};

type AnalyzeResponse = {
  status: "ocr_empty" | "unsupported_food" | "candidates_found";
  ocr_text: string;
  candidates: ApiCandidate[];
};

type ApiFoodGuide = {
  details: Partial<Record<DetailCategory, string>>;
  narration_text: string;
  style: "GUIDE" | "CAUTION";
  tts_status: "ok" | "not_ready";
  narration_audio_path: string | null;
  tts_latency_ms: number;
};

type FoodCandidate = {
  foodId: number;
  nameKr: string;
  nameEn: string;
  matchScore: number;
  imageUrl?: string | null;
  imageAttribution?: string | null;
  priceKrw?: number | null;
  priceKrwDisplay?: string | null;
  // The OCR text this match came from, and its box on the photo. Both absent when
  // the backend could not tie the dish name to one place in the picture.
  sourceText?: string | null;
  bbox?: Box;
};

type ApiCartLine = {
  food_id: number;
  name_kr: string;
  name_en: string;
  price_krw: number | null;
  price_krw_display: string | null;
  quantity: number;
  line_total_krw: number | null;
  line_total_display: string | null;
};

// The server owns every cart rule (merge by dish, no negatives, drop at zero) and
// answers each request with the whole cart, so the screen never has to reconcile
// partial updates - it just replaces this object.
type ApiCart = {
  cart_id: string;
  items: ApiCartLine[];
  item_count: number;
  total_krw: number;
  total_krw_display: string;
  has_unpriced_items: boolean;
};

type CartLine = {
  foodId: number;
  nameKr: string;
  nameEn: string;
  priceKrw: number | null;
  priceKrwDisplay: string | null;
  quantity: number;
  lineTotalDisplay: string | null;
};

// What the cart API needs to identify a dish. Both a menu-card candidate and a line
// already in the cart satisfy it, so one +/- handler serves the card and the cart.
type CartItemRef = {
  foodId: number;
  nameKr: string;
  nameEn: string;
  priceKrw?: number | null;
};

type Cart = {
  lines: CartLine[];
  itemCount: number;
  totalDisplay: string;
  hasUnpricedItems: boolean;
};

const EMPTY_CART: Cart = { lines: [], itemCount: 0, totalDisplay: "₩0", hasUnpricedItems: false };

type FoodGuide = {
  foodId: number;
  nameKr: string;
  nameEn: string;
  // Carried over from the menu photo, not looked up — absent when the photo showed
  // no price for this dish.
  priceKrwDisplay?: string | null;
  details: Partial<Record<DetailCategory, string>>;
  narrationText: string;
  style: "GUIDE" | "CAUTION";
  ttsStatus: "ok" | "not_ready";
  narrationAudioPath: string | null;
  audioUrl: string | null;
  ttsLatencyMs: number;
};

// The uppercase category keys are internal API values. The labels beside them are
// the short English names travellers see on the result screen. The boolean keeps
// allergy information visually distinct because it needs extra attention.
const DETAIL_SECTIONS: Array<[DetailCategory, string, boolean]> = [
  ["DESCRIPTION", "Description", false],
  ["HOW_TO_EAT", "How to eat", false],
  ["INGREDIENT", "Ingredients", false],
  ["ALLERGY", "Allergies & dietary needs", true],
  ["PRONUNCIATION", "Pronunciation", false],
  ["SPICY", "Spice level", false],
];

function toFoodCandidate(candidate: ApiCandidate): FoodCandidate {
  return {
    foodId: candidate.food_id,
    nameKr: candidate.name_kr,
    nameEn: candidate.name_en,
    matchScore: candidate.score,
    imageUrl: candidate.thumbnail_url,
    imageAttribution: candidate.thumbnail_attribution,
    priceKrw: candidate.price_krw,
    priceKrwDisplay: candidate.price_krw_display,
    sourceText: candidate.source?.text,
    // Ratios become percentages so the box can be positioned inside the photo frame.
    bbox: candidate.source
      ? {
          left: candidate.source.left * 100,
          top: candidate.source.top * 100,
          width: candidate.source.width * 100,
          height: candidate.source.height * 100,
        }
      : undefined,
  };
}

function toCart(payload: ApiCart): Cart {
  return {
    lines: payload.items.map((item) => ({
      foodId: item.food_id,
      nameKr: item.name_kr,
      nameEn: item.name_en,
      priceKrw: item.price_krw,
      priceKrwDisplay: item.price_krw_display,
      quantity: item.quantity,
      lineTotalDisplay: item.line_total_display,
    })),
    itemCount: payload.item_count,
    totalDisplay: payload.total_krw_display,
    hasUnpricedItems: payload.has_unpriced_items,
  };
}

function toFoodGuide(payload: ApiFoodGuide, candidate: FoodCandidate): FoodGuide {
  return {
    foodId: candidate.foodId,
    nameKr: candidate.nameKr,
    nameEn: candidate.nameEn,
    priceKrwDisplay: candidate.priceKrwDisplay,
    details: payload.details,
    narrationText: payload.narration_text,
    style: payload.style,
    ttsStatus: payload.tts_status,
    narrationAudioPath: payload.narration_audio_path,
    audioUrl: payload.narration_audio_path ? `${API_BASE_URL}${payload.narration_audio_path}` : null,
    ttsLatencyMs: payload.tts_latency_ms,
  };
}

function detailValue(details: FoodGuide["details"], category: DetailCategory) {
  return details[category] ?? "Information is not available for this item.";
}

// Speech synthesis is what says the dish name. Where it is missing the name button is
// not rendered at all, rather than shown as a control that does nothing.
const canSpeak = typeof window !== "undefined" && "speechSynthesis" in window;

function formatTime(seconds: number) {
  // Duration reads NaN until the browser has the metadata, and Infinity for a stream.
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

async function analyzeMenu(image: File): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("image", image);

  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: "POST",
    body: form,
  });

  if (!response.ok) {
    throw new Error("analysis failed");
  }

  return response.json() as Promise<AnalyzeResponse>;
}

async function fetchFoodGuide(candidate: FoodCandidate): Promise<FoodGuide> {
  const response = await fetch(`${API_BASE_URL}/api/foods/${candidate.foodId}`);

  if (!response.ok) {
    throw new Error("guide failed");
  }

  const payload = (await response.json()) as ApiFoodGuide;
  return toFoodGuide(payload, candidate);
}

type SupportedFood = { foodId: number; nameKr: string; nameEn: string };

async function fetchSupportedFoods(): Promise<SupportedFood[]> {
  const response = await fetch(`${API_BASE_URL}/api/foods`);

  if (!response.ok) {
    throw new Error("supported food list failed");
  }

  const payload = (await response.json()) as Array<{ food_id: number; name_kr: string; name_en: string }>;
  return payload.map((food) => ({ foodId: food.food_id, nameKr: food.name_kr, nameEn: food.name_en }));
}

// There is no sign-in, so a cart belongs to this browser. The id is generated once
// and kept in localStorage; the server treats an unknown id as an empty cart.
function cartId(): string {
  const stored = localStorage.getItem("kmenu-cart-id");
  if (stored) {
    return stored;
  }
  const created = crypto.randomUUID();
  localStorage.setItem("kmenu-cart-id", created);
  return created;
}

async function fetchCart(): Promise<Cart> {
  const response = await fetch(`${API_BASE_URL}/api/cart`, { headers: { "X-Cart-Id": cartId() } });

  if (!response.ok) {
    throw new Error("cart read failed");
  }

  return toCart((await response.json()) as ApiCart);
}

async function changeCartItem(item: CartItemRef, quantityDelta: number): Promise<Cart> {
  const response = await fetch(`${API_BASE_URL}/api/cart/items`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Cart-Id": cartId() },
    body: JSON.stringify({
      food_id: item.foodId,
      name_kr: item.nameKr,
      name_en: item.nameEn,
      price_krw: item.priceKrw ?? null,
      quantity_delta: quantityDelta,
    }),
  });

  if (!response.ok) {
    throw new Error("cart update failed");
  }

  return toCart((await response.json()) as ApiCart);
}

async function emptyCart(): Promise<Cart> {
  const response = await fetch(`${API_BASE_URL}/api/cart`, {
    method: "DELETE",
    headers: { "X-Cart-Id": cartId() },
  });

  if (!response.ok) {
    throw new Error("cart clear failed");
  }

  return toCart((await response.json()) as ApiCart);
}

function App() {
  const [screen, setScreen] = useState<Screen>("camera");
  const [currentLang, setCurrentLang] = useState("EN");
  const [candidates, setCandidates] = useState<FoodCandidate[]>([]);
  const [cart, setCart] = useState<Cart>(EMPTY_CART);
  const [cartError, setCartError] = useState("");
  const [guide, setGuide] = useState<FoodGuide | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [highlightedFoodId, setHighlightedFoodId] = useState<number | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [errorKind, setErrorKind] = useState<ErrorKind>("service");
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [termsOpen, setTermsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [consentVisible, setConsentVisible] = useState(() => localStorage.getItem("kmenu-consent") === null);
  const [consentClosing, setConsentClosing] = useState(false);
  const [essentialCookies, setEssentialCookies] = useState(true);
  const [imageProcessingConsent, setImageProcessingConsent] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  useEffect(() => {
    if (cameraReady && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
    }
  }, [cameraReady]);

  // A cart outlives a single scan, so it is loaded once on start rather than after
  // each photo. A failure here leaves the empty cart in place; the traveller can
  // still browse dishes, and the next +/- will surface the problem.
  useEffect(() => {
    fetchCart()
      .then(setCart)
      .catch(() => setCartError("Cart is unavailable right now."));
  }, []);

  // Every +/- replaces the whole cart with what the server returns, so the cards and
  // the cart section can never drift apart. On failure the current cart is kept.
  async function changeQuantity(item: CartItemRef, quantityDelta: number) {
    try {
      setCart(await changeCartItem(item, quantityDelta));
      setCartError("");
    } catch {
      setCartError("Could not update the cart. Check your connection and try again.");
    }
  }

  async function clearCart() {
    try {
      setCart(await emptyCart());
      setCartError("");
    } catch {
      setCartError("Could not empty the cart. Check your connection and try again.");
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraReady(false);
  }

  async function startCamera() {
    setCameraError("");
    if (!imageProcessingConsent) {
      setCameraError("Please enable Camera & Image Processing consent before using the camera.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      setCameraReady(true);
    } catch {
      setCameraError("Camera access is unavailable. Upload a menu photo instead.");
    }
  }

  async function processImage(image: File) {
    try {
      // The waiting screen appears before the upload begins so a traveller knows
      // the menu photo was accepted and does not submit the same photo twice.
      setScreen("processing");
      setPhotoUrl(URL.createObjectURL(image));

      const analysis = await analyzeMenu(image);
      if (analysis.status === "ocr_empty") {
        setErrorKind("ocr");
        setScreen("error");
        return;
      }

      if (analysis.status === "unsupported_food" || analysis.candidates.length === 0) {
        setErrorKind("unsupported");
        setScreen("error");
        return;
      }

      // A new menu means a new restaurant, so the cart starts empty. Without this the
      // cart belongs to the browser rather than to the meal, and dishes from the last
      // place stay in the list while you order at this one.
      //
      // Only a successful read clears it: a blurred photo or an unsupported menu is a
      // failed attempt, not a new restaurant, and those paths return above with the
      // cart untouched so a retake does not cost the traveller what they already added.
      await clearCart();

      const next = analysis.candidates.map(toFoodCandidate);

      setCandidates(next);
      setHighlightedFoodId(next[0]?.foodId ?? null);
      setScreen("candidates");
    } catch {
      setErrorKind("service");
      setScreen("error");
    }
  }

  function capturePhoto() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) {
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          return;
        }
        stopCamera();
        void processImage(new File([blob], "menu-camera.jpg", { type: "image/jpeg" }));
      },
      "image/jpeg",
      0.92,
    );
  }

  function handleUpload(event: ChangeEvent<HTMLInputElement>) {
    const image = event.target.files?.[0];
    if (!image) {
      return;
    }
    if (!imageProcessingConsent) {
      setCameraError("Please enable Camera & Image Processing consent before uploading a photo.");
      event.target.value = "";
      return;
    }
    stopCamera();
    void processImage(image);
  }

  function persistConsent(nextEssentialCookies: boolean, nextImageProcessingConsent: boolean) {
    localStorage.setItem(
      "kmenu-consent",
      JSON.stringify({
        essentialCookies: nextEssentialCookies,
        imageProcessingConsent: nextImageProcessingConsent,
        acceptedAt: new Date().toISOString(),
      }),
    );
  }

  function acceptConsent() {
    persistConsent(essentialCookies, imageProcessingConsent);
    setConsentClosing(true);
    window.setTimeout(() => setConsentVisible(false), 260);
  }

  // Settings screen toggles apply immediately (no separate "Save" step), unlike the
  // first-run consent banner which only persists once the traveller taps Accept.
  function updateEssentialCookies(value: boolean) {
    setEssentialCookies(value);
    persistConsent(value, imageProcessingConsent);
  }

  function updateImageProcessingConsent(value: boolean) {
    setImageProcessingConsent(value);
    persistConsent(essentialCookies, value);
  }

  async function chooseFood(candidate: FoodCandidate) {
    try {
      setScreen("processing");
      setGuide(await fetchFoodGuide(candidate));
      setScreen("result");
    } catch {
      setErrorKind("service");
      setScreen("error");
    }
  }

  // One state controls one full-page screen. This keeps the user journey easy to
  // follow: photo input → waiting → matches → guide, or a recoverable error.
  if (screen === "processing") return <Processing currentLang={currentLang} photoUrl={photoUrl} onCancel={() => setScreen("camera")} onSelectLang={setCurrentLang} />;
  if (screen === "candidates") return <Candidates candidates={candidates} cart={cart} cartError={cartError} currentLang={currentLang} photoUrl={photoUrl} highlightedFoodId={highlightedFoodId} onBack={() => setScreen("camera")} onHighlight={setHighlightedFoodId} onChoose={chooseFood} onClearCart={clearCart} onOrder={() => setScreen("order")} onQuantityChange={changeQuantity} onSelectLang={setCurrentLang} />;
  if (screen === "order") return <OrderSummary cart={cart} currentLang={currentLang} onBack={() => setScreen("candidates")} onSelectLang={setCurrentLang} />;
  if (screen === "result" && guide) return <Result currentLang={currentLang} guide={guide} onBack={() => setScreen("candidates")} onSelectLang={setCurrentLang} />;
  if (screen === "error") return <ErrorPanel currentLang={currentLang} kind={errorKind} onHome={() => setScreen("camera")} onSelectLang={setCurrentLang} />;

  return <>
    <main className="screen camera-screen">
      <header className="camera-header">
        <div className="brand-mark camera-brand">K</div>
        <div className="brand-copy"><strong>K-menu</strong><p>A thoughtful guide</p></div>
        <div className="camera-header-actions">
          <LanguageSelector currentLang={currentLang} onSelectLang={setCurrentLang} />
          <button aria-label="Settings" className="settings-button" onClick={() => setSettingsOpen(true)} type="button">⚙</button>
        </div>
      </header>
      <section className="camera-intro">
        <p className="camera-kicker">✧ MENU, MADE CLEAR</p>
        <h1>Scan a Korean menu.</h1>
        <p>Take a clear photo to find dishes we can guide.</p>
      </section>
      <section className="camera-card">
        <button className={cameraReady ? "camera-viewer is-ready" : "camera-viewer"} aria-label={cameraReady ? "Camera preview" : "Enable camera"} onClick={() => { if (!cameraReady) void startCamera(); }} type="button">
          {cameraReady ? <video ref={videoRef} autoPlay muted playsInline /> : <div className="camera-placeholder"><span aria-hidden="true">▣</span><p>Enable camera</p></div>}
          <span className="camera-prompt">{cameraReady ? "Camera ready" : "Point at the menu"}</span>
          <span className="scan-corner top-left" aria-hidden="true" /><span className="scan-corner top-right" aria-hidden="true" /><span className="scan-corner bottom-left" aria-hidden="true" /><span className="scan-corner bottom-right" aria-hidden="true" />
        </button>
        <div className="camera-actions">
          <button className="capture-button" disabled={!cameraReady} onClick={capturePhoto}><span aria-hidden="true">▣</span> Take photo</button>
          <label className="secondary-button upload-button"><span aria-hidden="true" className="upload-icon" />Upload a menu photo<input accept="image/*" onChange={handleUpload} type="file" /></label>
        </div>
      </section>
      {cameraError && <p className="camera-error">{cameraError}</p>}
      <p className="camera-helper">Your photo is used only to identify the menu text. Read the Korean original before ordering.</p>
      {/* Development-only controls for checking error layouts. They are not part of
          the traveller-facing flow and should be removed or hidden before release. */}
      <details className="practice-tools"><summary>Preview error states</summary><button onClick={() => { setErrorKind("ocr"); setScreen("error"); }}>OCR failed</button><button onClick={() => { setErrorKind("unsupported"); setScreen("error"); }}>Unsupported dish</button><button onClick={() => { setErrorKind("service"); setScreen("error"); }}>GPU / DB failed</button></details>
    </main>
    <footer className={consentVisible ? "camera-footer is-obscured" : "camera-footer"}>
      <p>Your photos are safe. They are processed instantly for OCR and not stored.</p>
      <p>© 2026 K-Menu Voice Guide · <button onClick={() => setPrivacyOpen(true)}>Privacy</button> · <button onClick={() => setTermsOpen(true)}>Terms</button></p>
    </footer>
    {privacyOpen && <PrivacyModal onClose={() => setPrivacyOpen(false)} />}
    {termsOpen && <TermsModal onClose={() => setTermsOpen(false)} />}
    {settingsOpen && (
      <SettingsModal
        currentLang={currentLang}
        essentialCookies={essentialCookies}
        imageProcessingConsent={imageProcessingConsent}
        onClose={() => setSettingsOpen(false)}
        onEssentialCookiesChange={updateEssentialCookies}
        onImageProcessingChange={updateImageProcessingConsent}
        onOpenPrivacy={() => { setSettingsOpen(false); setPrivacyOpen(true); }}
        onOpenTerms={() => { setSettingsOpen(false); setTermsOpen(true); }}
        onSelectLang={setCurrentLang}
      />
    )}
    {consentVisible && <ConsentBanner closing={consentClosing} essentialCookies={essentialCookies} imageProcessingConsent={imageProcessingConsent} onAccept={acceptConsent} onImageProcessingChange={setImageProcessingConsent} onEssentialCookiesChange={setEssentialCookies} onPrivacy={() => setPrivacyOpen(true)} />}
  </>;
}

function SettingsModal({
  currentLang,
  essentialCookies,
  imageProcessingConsent,
  onClose,
  onEssentialCookiesChange,
  onImageProcessingChange,
  onOpenPrivacy,
  onOpenTerms,
  onSelectLang,
}: {
  currentLang: string;
  essentialCookies: boolean;
  imageProcessingConsent: boolean;
  onClose: () => void;
  onEssentialCookiesChange: (value: boolean) => void;
  onImageProcessingChange: (value: boolean) => void;
  onOpenPrivacy: () => void;
  onOpenTerms: () => void;
  onSelectLang: (lang: string) => void;
}) {
  const [supportedFoods, setSupportedFoods] = useState<SupportedFood[] | null>(null);
  const [foodsError, setFoodsError] = useState("");

  // Loaded when the dialog mounts, i.e. every time it is opened, so a dish added to
  // the database shows up without a page reload. Null means "still loading" and is
  // deliberately distinct from an empty list, which would mean "nothing supported".
  useEffect(() => {
    fetchSupportedFoods()
      .then(setSupportedFoods)
      .catch(() => setFoodsError("The dish list could not be loaded right now."));
  }, []);

  return (
    <div className="modal-backdrop" onMouseDown={onClose} role="presentation">
      <section aria-labelledby="settings-title" aria-modal="true" className="privacy-modal settings-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog">
        <button aria-label="Close settings" className="modal-close" onClick={onClose}>×</button>
        <p className="eyebrow">K-MENU VOICE GUIDE</p>
        <h2 id="settings-title">Settings</h2>

        <section className="terms-section">
          <h3>App settings</h3>
          <label className="settings-row">
            <span>Language</span>
            <LanguageSelector currentLang={currentLang} onSelectLang={onSelectLang} />
          </label>
          <label className="settings-row">
            <input checked={imageProcessingConsent} onChange={(event) => onImageProcessingChange(event.target.checked)} type="checkbox" />
            <span><strong>Camera &amp; Image Processing</strong><small>Allows menu images to be processed in memory for OCR. Images are not permanently stored.</small></span>
          </label>
          <label className="settings-row">
            <input checked={essentialCookies} onChange={(event) => onEssentialCookiesChange(event.target.checked)} type="checkbox" />
            <span><strong>Essential Cookies &amp; Analytics</strong><small>Allows session continuity and basic performance measurement.</small></span>
          </label>
        </section>

        <section className="terms-section">
          <h3>
            Supported dishes
            {supportedFoods && <span className="settings-count">{supportedFoods.length}</span>}
          </h3>
          <p>These are the dishes we can currently recognise on a menu and describe for you.</p>
          {foodsError && <p className="settings-error">{foodsError}</p>}
          {!foodsError && !supportedFoods && <p className="settings-loading">Loading…</p>}
          {supportedFoods && supportedFoods.length === 0 && (
            <p className="settings-loading">No dishes are registered yet.</p>
          )}
          {supportedFoods && supportedFoods.length > 0 && (
            // Scrolls inside itself: fifty dishes must not push the rest of the
            // settings dialog out of reach.
            <ul className="supported-foods">
              {supportedFoods.map((food) => (
                <li key={food.foodId}>
                  <strong>{food.nameEn}</strong>
                  <span>{food.nameKr}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="terms-section">
          <h3>App info</h3>
          <p><strong>K-menu Voice Guide</strong> · Checkpoint demo (React)</p>
          <p>Point your camera at a Korean menu to get English descriptions, spice level, allergy notes, and a spoken voice guide — built for travellers unfamiliar with Korean menus.</p>
          <div className="settings-links">
            <button className="text-button" onClick={onOpenPrivacy}>Privacy Policy</button>
            <button className="text-button" onClick={onOpenTerms}>Terms of Use</button>
          </div>
        </section>

        <button className="modal-confirm" onClick={onClose}>Close</button>
      </section>
    </div>
  );
}

function PrivacyModal({ onClose }: { onClose: () => void }) { return <div className="modal-backdrop" onMouseDown={onClose} role="presentation"><section aria-labelledby="privacy-title" aria-modal="true" className="privacy-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog"><button aria-label="Close privacy notice" className="modal-close" onClick={onClose}>×</button><p className="eyebrow">K-MENU VOICE GUIDE</p><h2 id="privacy-title">Privacy Notice</h2><p><em>K-Menu Voice Guide respects your privacy.</em></p><ol><li><strong>Camera &amp; Photos:</strong> Images you capture or upload are processed in real-time solely to detect Korean menu text. Images are not stored on our permanent database.</li><li><strong>Voice Audio:</strong> Generated audio guides are streamed to your device.</li><li><strong>Analytics:</strong> We do not track your personal identity.</li></ol><button className="modal-confirm" onClick={onClose}>Close</button></section></div>; }

function TermsModal({ onClose }: { onClose: () => void }) { return <div className="modal-backdrop" onMouseDown={onClose} role="presentation"><section aria-labelledby="terms-title" aria-modal="true" className="privacy-modal terms-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog"><button aria-label="Close terms of use" className="modal-close" onClick={onClose}>×</button><p className="eyebrow">K-MENU VOICE GUIDE</p><h2 id="terms-title">Terms of Use</h2><section className="terms-section"><h3>1. Service purpose</h3><p>K-Menu Voice Guide helps visitors understand Korean menu items through OCR-based dish matching, English descriptions, and audio guides. It is an informational guide only and does not replace advice from restaurant staff, medical professionals, or other qualified experts.</p></section><section className="terms-section allergy-disclaimer"><h3>2. Allergy and dietary disclaimer</h3><p className="terms-order-warning"><strong>Before you order, you must confirm ingredients, preparation methods, and possible cross-contact directly with the restaurant.</strong></p><p>Allergy, ingredient, vegetarian, spice, and dietary information is provided for general reference only. Recipes, ingredients, sauces, garnishes, portion preparation, and cross-contact risks can vary between restaurants and may change without notice.</p><p>Do not rely on this service as a guarantee that a dish is free from any allergen or suitable for a medical, religious, or dietary requirement. If you have a severe allergy or dietary condition, use extra caution and choose food only after receiving confirmation from the restaurant.</p><p>If you think you are having an allergic reaction, seek emergency medical assistance immediately.</p></section><section className="terms-section"><h3>3. Your use of the service</h3><p>You are responsible for your menu choices and for using the service lawfully. Please upload only menu photos you are permitted to capture and do not use the service to submit harmful, unlawful, or unrelated content.</p></section><section className="terms-section"><h3>4. Availability and changes</h3><p>Dish recognition, translations, audio guides, and service availability may be incomplete or unavailable at times. We may update, change, or discontinue features as the service develops.</p></section><section className="terms-section"><h3>5. Contact</h3><p>For questions about these terms or the service, please contact the K-Menu Voice Guide team through the project contact channel.</p></section><button className="modal-confirm" onClick={onClose}>I understand</button></section></div>; }

function ConsentBanner({ closing, essentialCookies, imageProcessingConsent, onAccept, onEssentialCookiesChange, onImageProcessingChange, onPrivacy }: { closing: boolean; essentialCookies: boolean; imageProcessingConsent: boolean; onAccept: () => void; onEssentialCookiesChange: (value: boolean) => void; onImageProcessingChange: (value: boolean) => void; onPrivacy: () => void }) { return <aside aria-label="Privacy choices" className={closing ? "consent-banner is-closing" : "consent-banner"}><div className="consent-copy"><p className="consent-title">Your privacy choices</p><p>Choose how K-Menu Voice Guide may process your session and menu photos.</p></div><div className="consent-options"><label><input checked={essentialCookies} onChange={(event) => onEssentialCookiesChange(event.target.checked)} type="checkbox" /><span><strong>Essential Cookies &amp; Analytics</strong><small>Allows session continuity and basic performance measurement.</small></span></label><label><input checked={imageProcessingConsent} onChange={(event) => onImageProcessingChange(event.target.checked)} type="checkbox" /><span><strong>Camera &amp; Image Processing</strong><small>Allows menu images to be processed in memory for OCR. Images are not permanently stored.</small></span></label></div><div className="consent-actions"><button className="consent-privacy" onClick={onPrivacy}>Privacy Policy</button><button className="consent-accept" onClick={onAccept}>Accept &amp; Continue</button></div></aside>; }

function FlowHeader({ label, currentLang, onSelectLang }: { label: string; currentLang: string; onSelectLang: (lang: string) => void }) { return <header className="flow-header"><div className="brand-mark camera-brand">K</div><div className="brand-copy"><strong>K-menu</strong><p>A thoughtful guide</p></div><div className="flow-header-actions"><span>{label}</span><LanguageSelector currentLang={currentLang} onSelectLang={onSelectLang} /></div></header>; }

function Processing({ currentLang, photoUrl, onCancel, onSelectLang }: { currentLang: string; photoUrl: string | null; onCancel: () => void; onSelectLang: (lang: string) => void }) {
  const [activeStep, setActiveStep] = useState(0);
  const steps = [
    ["Image received", "Preparing your menu photo"],
    ["Reading Korean text", "Extracting visible menu text"],
    ["Matching dishes", "Finding dishes in our guide"],
  ];

  useEffect(() => {
    // The API reports one final result, not three live server events. These
    // timed states make the wait understandable and stop as soon as the API
    // response changes the screen to matches or an error screen.
    const secondStep = window.setTimeout(() => setActiveStep(1), 650);
    const thirdStep = window.setTimeout(() => setActiveStep(2), 1350);
    return () => { window.clearTimeout(secondStep); window.clearTimeout(thirdStep); };
  }, []);

  return <main className="screen flow-screen processing-screen"><FlowHeader currentLang={currentLang} label="Reading your menu" onSelectLang={onSelectLang} /><button className="cancel-button screen-back" onClick={onCancel}>Cancel</button><section className="analysis-widget">{photoUrl ? <img alt="Menu being analyzed" src={photoUrl} /> : <div className="analysis-photo-placeholder" />}<div className="analysis-overlay"><p className="analysis-kicker">LIVE MENU ANALYSIS</p><div className="analysis-loader" /><h1>Reading your menu.</h1><p>We&apos;re finding dishes in your menu photo.</p><div className="analysis-progress" aria-hidden="true"><span style={{ width: `${((activeStep + 1) / steps.length) * 100}%` }} /></div><ol className="analysis-steps">{steps.map(([title, description], index) => <li className={index < activeStep ? "done" : index === activeStep ? "active" : ""} key={title}><span>{index < activeStep ? "✓" : String(index + 1)}</span><div><strong>{title}</strong><small>{description}</small></div></li>)}</ol></div></section></main>;
}

function Candidates({
  candidates,
  cart,
  cartError,
  currentLang,
  photoUrl,
  highlightedFoodId,
  onBack,
  onHighlight,
  onChoose,
  onClearCart,
  onOrder,
  onQuantityChange,
  onSelectLang,
}: {
  candidates: FoodCandidate[];
  cart: Cart;
  cartError: string;
  currentLang: string;
  photoUrl: string | null;
  highlightedFoodId: number | null;
  onBack: () => void;
  onHighlight: (id: number) => void;
  onChoose: (candidate: FoodCandidate) => void;
  onClearCart: () => void;
  onOrder: () => void;
  onQuantityChange: (item: CartItemRef, quantityDelta: number) => void;
  onSelectLang: (lang: string) => void;
}) {
  const [enlargedFood, setEnlargedFood] = useState<FoodCandidate | null>(null);
  const quantityOf = (foodId: number) => cart.lines.find((line) => line.foodId === foodId)?.quantity ?? 0;
  const unlocatedCount = candidates.filter((food) => !food.bbox).length;

  return (
    <main className="screen flow-screen candidates-screen">
      <FlowHeader currentLang={currentLang} label="2 of 3" onSelectLang={onSelectLang} />
      {/* On a wide screen this splits into dish list + cart sidebar; on a phone it
          stays one column and the cart follows the list. */}
      <div className="candidates-layout">
        <div className="candidates-main">
          <button className="back-button screen-back" onClick={onBack}>← Back</button>
          <section className="flow-intro">
            <p className="camera-kicker">✧ MENU MATCHES</p>
            <h1>Choose a dish.</h1>
            <p>Check the highlighted text against your menu photo.</p>
          </section>
          {photoUrl && (
            <section className="ocr-evidence">
              <p className="evidence-title">Your menu photo</p>
              {/* The frame scrolls; the canvas inside is exactly the size of the photo,
                  which is what makes the percentage-positioned boxes line up with the
                  text they were read from. */}
              <div className="menu-photo-frame">
                <div className="menu-photo-canvas">
                  <img src={photoUrl} alt="Uploaded Korean menu" />
                  {candidates.map(
                    (food, index) =>
                      food.bbox && (
                        <span
                          className={highlightedFoodId === food.foodId ? "ocr-box active" : "ocr-box"}
                          key={food.foodId}
                          style={{
                            left: `${food.bbox.left}%`,
                            top: `${food.bbox.top}%`,
                            width: `${food.bbox.width}%`,
                            height: `${food.bbox.height}%`,
                          }}
                        >
                          <span className="ocr-index">{String(index + 1).padStart(2, "0")}</span>
                          <span className="ocr-box-text">{food.sourceText ?? food.nameKr}</span>
                        </span>
                      ),
                  )}
                </div>
              </div>
              <p className="evidence-help">
                Each box sits on the text it was read from, and shows exactly what the OCR saw there.
                {unlocatedCount > 0 &&
                  ` ${unlocatedCount} ${unlocatedCount === 1 ? "dish" : "dishes"} could not be pinned to one spot.`}
              </p>
            </section>
          )}
          <section className="candidate-list">
            {candidates.map((food, index) => (
              // The card is a plain element holding several controls: the dish name button
              // stretches over the whole card to open the guide, while the thumbnail and the
              // quantity stepper sit above it. Nesting those inside one big <button> would be
              // invalid HTML and would swallow their clicks.
              <div
                className="candidate-card"
                key={food.foodId}
                onMouseEnter={() => onHighlight(food.foodId)}
                onFocus={() => onHighlight(food.foodId)}
              >
                {food.imageUrl ? (
                  <button
                    aria-label={`Enlarge the photo of ${food.nameEn}`}
                    className="candidate-thumbnail-button"
                    onClick={() => setEnlargedFood(food)}
                    type="button"
                  >
                    <img className="candidate-thumbnail" src={food.imageUrl} alt="" />
                  </button>
                ) : (
                  <span className="food-index">{String(index + 1).padStart(2, "0")}</span>
                )}
                <span className="candidate-copy">
                  <span className="candidate-headline">
                    <button className="candidate-select" onClick={() => void onChoose(food)} type="button">
                      {food.nameEn}
                    </button>
                    <QuantityStepper
                      name={food.nameEn}
                      quantity={quantityOf(food.foodId)}
                      onChange={(quantityDelta) => onQuantityChange(food, quantityDelta)}
                    />
                  </span>
                  <span className="candidate-name-kr">{food.nameKr}</span>
                  {/* Price the OCR read off this menu photo. Absent when the photo
                      printed no price near the dish — never a guessed amount. */}
                  {food.priceKrwDisplay && <span className="candidate-price">{food.priceKrwDisplay}</span>}
                  {/* Combines how exactly the dish name was read with how sure the OCR
                      model was of those characters, so the number moves with photo
                      quality instead of sitting at 100. */}
                  <small className={food.matchScore === 100 ? "candidate-exact" : undefined}>
                    Possible match: {food.matchScore}%
                  </small>
                  {/* The exact OCR text behind this match — the same string the box on
                      the photo is drawn over, so a wrong match can be traced to its source. */}
                  {food.sourceText && <small className="candidate-source">Read as “{food.sourceText}”</small>}
                  {/* The photo credit lives in the lightbox instead: it is required
                      wherever the picture is shown large, but on a list card it is
                      small print competing with the dish itself. */}
                </span>
                <span className="chevron">›</span>
              </div>
            ))}
          </section>
        </div>
        <CartSection
          cart={cart}
          error={cartError}
          onClearCart={onClearCart}
          onOrder={onOrder}
          onQuantityChange={onQuantityChange}
        />
      </div>
      {enlargedFood?.imageUrl && (
        <ImageLightbox
          attribution={enlargedFood.imageAttribution}
          imageUrl={enlargedFood.imageUrl}
          name={enlargedFood.nameEn}
          onClose={() => setEnlargedFood(null)}
        />
      )}
    </main>
  );
}

// The minus button is disabled at zero rather than clamped silently, so the rule
// "quantity never goes below zero" is visible before the traveller taps. The server
// enforces the same rule, so a stale screen cannot push a quantity negative either.
function QuantityStepper({
  name,
  quantity,
  onChange,
}: {
  name: string;
  quantity: number;
  onChange: (quantityDelta: number) => void;
}) {
  return (
    <span className="quantity-stepper">
      <button
        aria-label={`Remove one ${name} from the cart`}
        className="quantity-button"
        disabled={quantity === 0}
        onClick={() => onChange(-1)}
        type="button"
      >
        −
      </button>
      <span aria-live="polite" className="quantity-value">
        {quantity}
      </span>
      <button
        aria-label={`Add one ${name} to the cart`}
        className="quantity-button"
        onClick={() => onChange(1)}
        type="button"
      >
        +
      </button>
    </span>
  );
}

function CartSection({
  cart,
  error,
  onClearCart,
  onOrder,
  onQuantityChange,
}: {
  cart: Cart;
  error: string;
  onClearCart: () => void;
  onOrder: () => void;
  onQuantityChange: (item: CartItemRef, quantityDelta: number) => void;
}) {
  const isEmpty = cart.lines.length === 0;
  return (
    <section className="cart-section">
      <header className="cart-header">
        <h2>Your cart</h2>
        <span className="cart-count">{cart.itemCount} {cart.itemCount === 1 ? "item" : "items"}</span>
      </header>

      {error && <p className="cart-error">{error}</p>}

      {isEmpty ? (
        <p className="cart-empty">Nothing here yet. Use + on a dish to add it.</p>
      ) : (
        <ul className="cart-lines">
          {cart.lines.map((line) => (
            <li className="cart-line" key={line.foodId}>
              <span className="cart-line-copy">
                <strong>{line.nameEn}</strong>
                <span>{line.nameKr}</span>
                <small>{line.priceKrwDisplay ? `${line.priceKrwDisplay} each` : "No price on the menu photo"}</small>
              </span>
              <QuantityStepper
                name={line.nameEn}
                quantity={line.quantity}
                onChange={(quantityDelta) => onQuantityChange(line, quantityDelta)}
              />
              <span className="cart-line-total">{line.lineTotalDisplay ?? "—"}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="cart-total">
        <span>Total</span>
        <strong>{cart.totalDisplay}</strong>
      </div>
      {/* The total can only add up dishes whose price was printed on the photo, so say
          when it is a partial figure instead of letting it read as the full bill. */}
      {cart.hasUnpricedItems && (
        <p className="cart-note">Some dishes had no price on your photo, so they are not in this total.</p>
      )}
      {/* Both are disabled on an empty cart: clearing nothing does nothing, and an
          empty order summary has nothing to show the staff. */}
      <div className="cart-actions">
        <button className="secondary-button" disabled={isEmpty} onClick={onClearCart} type="button">
          Clear cart
        </button>
        <button className="primary-button" disabled={isEmpty} onClick={onOrder} type="button">
          Order
        </button>
      </div>
    </section>
  );
}

// A summary to hold up to the restaurant staff — nothing is sent anywhere, so the
// wording never claims an order was placed. The Korean names lead, because they are
// the part the staff reads.
function OrderSummary({
  cart,
  currentLang,
  onBack,
  onSelectLang,
}: {
  cart: Cart;
  currentLang: string;
  onBack: () => void;
  onSelectLang: (lang: string) => void;
}) {
  return (
    <main className="screen flow-screen order-screen">
      <FlowHeader currentLang={currentLang} label="Your order" onSelectLang={onSelectLang} />
      <button className="back-button screen-back" onClick={onBack}>← Back to menu</button>
      <section className="flow-intro">
        <p className="camera-kicker">✧ READY TO ORDER</p>
        <h1>Show this to the staff.</h1>
        <p>These are the dishes you picked, written in Korean.</p>
      </section>

      <section className="order-sheet">
        {cart.lines.length === 0 ? (
          <p className="cart-empty">Your cart is empty.</p>
        ) : (
          <ul className="order-lines">
            {cart.lines.map((line) => (
              <li className="order-line" key={line.foodId}>
                <span className="order-line-copy">
                  <strong>{line.nameKr}</strong>
                  <span>{line.nameEn}</span>
                </span>
                <span className="order-line-count">×{line.quantity}</span>
                <span className="order-line-total">{line.lineTotalDisplay ?? "—"}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="cart-total">
          <span>Total</span>
          <strong>{cart.totalDisplay}</strong>
        </div>
        {cart.hasUnpricedItems && (
          <p className="cart-note">Some dishes had no price on your photo, so they are not in this total.</p>
        )}
      </section>

      <p className="order-disclaimer">
        This app does not send your order to the restaurant. Please confirm the dishes, the prices
        and any allergy questions with the staff before ordering.
      </p>
    </main>
  );
}

function ImageLightbox({
  attribution,
  imageUrl,
  name,
  onClose,
}: {
  attribution?: string | null;
  imageUrl: string;
  name: string;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop lightbox-backdrop" onMouseDown={onClose} role="presentation">
      <figure className="lightbox-figure" onMouseDown={(event) => event.stopPropagation()}>
        <button aria-label="Close photo" className="modal-close lightbox-close" onClick={onClose}>×</button>
        <img alt={name} src={imageUrl} />
        {attribution && <figcaption className="lightbox-caption">{attribution}</figcaption>}
      </figure>
    </div>
  );
}

function Result({ guide, currentLang, onBack, onSelectLang }: { guide: FoodGuide; currentLang: string; onBack: () => void; onSelectLang: (lang: string) => void }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isSpeakingName, setIsSpeakingName] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [duration, setDuration] = useState(0);

  // Two separate sound sources: the dish name goes through the browser's speech
  // synthesis, the full narration through the <audio> element. Leaving the screen
  // must silence the first one — unlike <audio>, it keeps talking after unmount.
  useEffect(() => () => window.speechSynthesis?.cancel(), []);

  function stopName() {
    window.speechSynthesis?.cancel();
    setIsSpeakingName(false);
  }

  async function toggleNarration() {
    const audio = audioRef.current;
    if (!audio) return;

    // Browsers allow sound after this explicit user click. We intentionally do
    // not use autoplay: the traveller decides whether to hear the guide.
    if (audio.paused) {
      stopName(); // never let the name and the narration talk over each other
      await audio.play();
    } else {
      audio.pause();
    }
  }

  // Says only the dish name, so a traveller can repeat it to the staff without
  // sitting through the whole guide.
  function toggleName() {
    if (!("speechSynthesis" in window)) return;
    if (isSpeakingName) {
      stopName();
      return;
    }

    audioRef.current?.pause(); // the other direction of the same rule
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(guide.nameKr);
    utterance.lang = "ko-KR";
    utterance.onend = () => setIsSpeakingName(false);
    utterance.onerror = () => setIsSpeakingName(false);
    setIsSpeakingName(true);
    window.speechSynthesis.speak(utterance);
  }

  return (
    <main className="screen flow-screen result-screen">
      <FlowHeader currentLang={currentLang} label="Your guide" onSelectLang={onSelectLang} />
      <button className="back-button screen-back" onClick={onBack}>← Back</button>
      <section className="result-hero">
        <p className="camera-kicker">✧ ABOUT THIS DISH</p>
        {/* Name, Korean original, price and the name's own speaker read as one line:
            everything that identifies the dish, sitting on a shared baseline. */}
        <div className="hero-identity">
          <h1>{guide.nameEn}</h1>
          <span className="hero-name-kr">{guide.nameKr}</span>
          {guide.priceKrwDisplay && <span className="hero-price">{guide.priceKrwDisplay}</span>}
          {canSpeak && (
            <button
              aria-label={isSpeakingName ? `Stop saying ${guide.nameKr}` : `Say ${guide.nameKr} out loud`}
              aria-pressed={isSpeakingName}
              className={isSpeakingName ? "hero-speaker is-speaking" : "hero-speaker"}
              onClick={toggleName}
              type="button"
            >
              <span aria-hidden="true">🔊</span>
            </button>
          )}
        </div>
        <div className="hero-meta">
          <p>{detailValue(guide.details, "PRONUNCIATION")}</p>
          <p className="badge">{detailValue(guide.details, "SPICY")}</p>
        </div>
      </section>

      {/* The full guide gets a labelled play bar of its own, outside the hero, so it
          cannot be mistaken for the name button sitting next to the title. */}
      {guide.audioUrl ? (
        <section className="narration-player">
          <button
            aria-label={isPlaying ? "Pause the full audio guide" : "Play the full audio guide"}
            className={isPlaying ? "narration-play is-playing" : "narration-play"}
            onClick={() => void toggleNarration()}
            type="button"
          >
            <span aria-hidden="true">{isPlaying ? "❚❚" : "▶"}</span>
          </button>
          <div className="narration-body">
            <p className="narration-label">Full audio guide</p>
            <input
              aria-label="Seek in the full audio guide"
              className="narration-seek"
              max={duration || 0}
              min={0}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (audioRef.current) audioRef.current.currentTime = next;
                setElapsed(next);
              }}
              step={0.1}
              type="range"
              value={elapsed}
            />
          </div>
          <span className="narration-time">
            {formatTime(elapsed)} / {formatTime(duration)}
          </span>
          <audio
            onEnded={() => {
              setIsPlaying(false);
              setElapsed(0);
            }}
            onLoadedMetadata={(event) => setDuration(event.currentTarget.duration)}
            onPause={() => setIsPlaying(false)}
            onPlay={() => setIsPlaying(true)}
            onTimeUpdate={(event) => setElapsed(event.currentTarget.currentTime)}
            ref={audioRef}
            src={guide.audioUrl}
          />
        </section>
      ) : (
        <section className="tts-error-card">
          <strong>Audio guide is unavailable right now.</strong>
          <p>{guide.narrationText}</p>
          <button onClick={() => alert("In the real app, this requests TTS again.")}>Try audio again</button>
        </section>
      )}
      {/* One note rather than six cards: the entries are all about the same dish, so
          dotted rules between them separate the topics without breaking the page into
          competing blocks. */}
      <section className="guide-note">
        {DETAIL_SECTIONS.map(([category, title, warning]) => (
          <article className={warning ? "note-entry warning" : "note-entry"} key={category}>
            <h2>{title}</h2>
            <p>{detailValue(guide.details, category)}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

function ErrorPanel({ kind, currentLang, onHome, onSelectLang }: { kind: ErrorKind; currentLang: string; onHome: () => void; onSelectLang: (lang: string) => void }) { const content = { ocr: ["We couldn't read this photo", "Try brighter lighting, hold the menu straight, and move closer to the text.", "Take a new photo"], unsupported: ["Not in our guide yet", "Try a different menu item or ask the restaurant staff.", "Take a new photo"], service: ["We couldn't load your guide", "Please check your connection and try again.", "Try again"] }[kind]; return <main className="screen flow-screen error-screen"><FlowHeader currentLang={currentLang} label="K-menu" onSelectLang={onSelectLang} /><section className="error-card"><p className="camera-kicker">✧ LET'S TRY AGAIN</p><span className="error-symbol">!</span><h1>{content[0]}</h1><p>{content[1]}</p>{kind === "unsupported" && <section className="guide-info"><h2>What this guide includes</h2><ul><li>Pronunciation</li><li>Spice level</li><li>Description and ingredients</li><li>How to eat</li><li>Allergies and dietary needs</li></ul></section>}<button className="primary-button" onClick={onHome}>{content[2]}</button></section></main>; }

export default App;
