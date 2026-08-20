import { ChangeEvent, useEffect, useRef, useState } from "react";
import LanguageSelector from "./components/LanguageSelector";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type Screen = "camera" | "processing" | "candidates" | "result" | "error";
type ErrorKind = "ocr" | "unsupported" | "service";
type Box = { left: number; top: number; width: number; height: number };
type FoodCandidate = { foodId: number; foodKo: string; foodEn: string; matchScore: number; bbox?: Box };
type FoodGuide = { foodId: number; foodKo: string; foodEn: string; pronunciation: string; spicy: string; description: string; ingredient: string; howToEat: string; allergy: string; narrationText: string; audioUrl: string | null };

const SUPPORTED_DISHES = [
  ["비빔밥", "Bibimbap"], ["불고기", "Bulgogi"], ["김치찌개", "Kimchi jjigae"], ["떡볶이", "Tteokbokki"], ["잡채", "Japchae"], ["순두부찌개", "Sundubu jjigae"], ["삼겹살", "Samgyeopsal"], ["갈비", "Galbi"], ["김밥", "Gimbap"], ["라면", "Ramyun"], ["냉면", "Naengmyeon"], ["비빔냉면", "Bibim naengmyeon"], ["칼국수", "Kalguksu"], ["수제비", "Sujebi"], ["파전", "Pajeon"], ["김치전", "Kimchi jeon"], ["된장찌개", "Doenjang jjigae"], ["갈비탕", "Galbitang"], ["설렁탕", "Seolleongtang"], ["삼계탕", "Samgyetang"], ["곱창전골", "Gopchang jeongol"], ["부대찌개", "Budae jjigae"], ["닭갈비", "Dakgalbi"], ["찜닭", "Jjimdak"], ["제육볶음", "Jeyuk bokkeum"], ["오징어볶음", "Ojingeo bokkeum"], ["두부김치", "Dubukimchi"], ["감자탕", "Gamjatang"], ["해장국", "Haejangguk"], ["육개장", "Yukgaejang"], ["김치", "Kimchi"], ["후라이드치킨", "Korean Fried Chicken"], ["양념치킨", "Yangnyeom Chicken"], ["짜장면", "Jajangmyeon"], ["만두", "Mandu"], ["어묵", "Eomuk"], ["순대", "Sundae"], ["닭강정", "Dakgangjeong"], ["호떡", "Hotteok"], ["붕어빵", "Bungeoppang"], ["한국식 핫도그", "Korean Corn Dog"], ["보쌈", "Bossam"], ["족발", "Jokbal"], ["갈비찜", "Galbijjim"], ["계란찜", "Gyeran-jjim"], ["김치볶음밥", "Kimchi Bokkeumbap"], ["떡국", "Tteokguk"], ["잔치국수", "Janchi-guksu"], ["콩국수", "Kongguksu"], ["빙수", "Bingsu"],
] as const;

// 백엔드(K_Menu_Talk.py, docs/specs/api-layer.md) 응답 스키마 — snake_case, details는 카테고리별 dict.
type BackendCandidate = { food_id: number; name_kr: string; name_en: string; score: number; modifiers: unknown };
type AnalyzeApiResponse = { status: "ocr_empty" | "unsupported_food" | "candidates_found"; ocr_text: string; candidates: BackendCandidate[] };
type FoodDetailApiResponse = { food_id: number; name_kr: string; name_en: string; details: Record<string, string>; narration_text: string; style: string; tts_status: string; narration_audio_path: string | null; tts_latency_ms: number };

class AnalyzeStatusError extends Error { status: AnalyzeApiResponse["status"]; constructor(status: AnalyzeApiResponse["status"]) { super(status); this.status = status; } }

async function analyzeMenu(image: File): Promise<FoodCandidate[]> {
  const form = new FormData(); form.append("image", image);
  const res = await fetch(`${API_BASE_URL}/api/analyze`, { method: "POST", body: form });
  if (!res.ok) throw new Error("analysis failed");
  const data: AnalyzeApiResponse = await res.json();
  if (data.status !== "candidates_found") throw new AnalyzeStatusError(data.status);
  return data.candidates.map((food) => ({ foodId: food.food_id, foodKo: food.name_kr, foodEn: food.name_en, matchScore: food.score }));
}
async function fetchFoodGuide(foodId: number): Promise<FoodGuide> {
  const res = await fetch(`${API_BASE_URL}/api/foods/${foodId}`);
  if (!res.ok) throw new Error("guide failed");
  const data: FoodDetailApiResponse = await res.json();
  return {
    foodId: data.food_id, foodKo: data.name_kr, foodEn: data.name_en,
    pronunciation: data.details.PRONUNCIATION ?? "", spicy: data.details.SPICY ?? "",
    description: data.details.DESCRIPTION ?? "", ingredient: data.details.INGREDIENT ?? "",
    howToEat: data.details.HOW_TO_EAT ?? "", allergy: data.details.ALLERGY ?? "",
    narrationText: data.narration_text,
    audioUrl: data.narration_audio_path ? `${API_BASE_URL}${data.narration_audio_path}` : null,
  };
}

function App() {
  const [screen, setScreen] = useState<Screen>("camera");
  const [currentLang, setCurrentLang] = useState("EN");
  const [candidates, setCandidates] = useState<FoodCandidate[]>([]);
  const [guide, setGuide] = useState<FoodGuide | null>(null);
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [highlightedFoodId, setHighlightedFoodId] = useState<number | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [errorKind, setErrorKind] = useState<ErrorKind>("service");
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const [termsOpen, setTermsOpen] = useState(false);
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

  function stopCamera() { streamRef.current?.getTracks().forEach((track) => track.stop()); streamRef.current = null; setCameraReady(false); }
  async function startCamera() {
    setCameraError("");
    if (!imageProcessingConsent) {
      setCameraError("Please enable Camera & Image Processing consent before using the camera.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      streamRef.current = stream;
      setCameraReady(true);
    } catch { setCameraError("Camera access is unavailable. Upload a menu photo instead."); }
  }
  async function processImage(image: File) {
    try {
      setScreen("processing"); setPhotoUrl(URL.createObjectURL(image));
      const boxes: Box[] = [{ left: 12, top: 20, width: 45, height: 12 }, { left: 42, top: 43, width: 40, height: 12 }, { left: 18, top: 66, width: 48, height: 12 }];
      const next = (await analyzeMenu(image)).map((food, index) => ({ ...food, bbox: boxes[index] }));
      setCandidates(next); setHighlightedFoodId(next[0]?.foodId ?? null); setScreen("candidates");
    } catch (err) {
      setErrorKind(err instanceof AnalyzeStatusError && err.status === "unsupported_food" ? "unsupported" : "ocr");
      setScreen("error");
    }
  }
  function capturePhoto() {
    const video = videoRef.current; if (!video || !video.videoWidth) return;
    const canvas = document.createElement("canvas"); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => { if (!blob) return; stopCamera(); void processImage(new File([blob], "menu-camera.jpg", { type: "image/jpeg" })); }, "image/jpeg", 0.92);
  }
  function handleUpload(event: ChangeEvent<HTMLInputElement>) { const image = event.target.files?.[0]; if (!image) return; if (!imageProcessingConsent) { setCameraError("Please enable Camera & Image Processing consent before uploading a photo."); event.target.value = ""; return; } stopCamera(); void processImage(image); }
  function acceptConsent() { localStorage.setItem("kmenu-consent", JSON.stringify({ essentialCookies, imageProcessingConsent, acceptedAt: new Date().toISOString() })); setConsentClosing(true); window.setTimeout(() => setConsentVisible(false), 260); }
  async function chooseFood(id: number) { try { setScreen("processing"); setGuide(await fetchFoodGuide(id)); setScreen("result"); } catch { setErrorKind("service"); setScreen("error"); } }

  if (screen === "processing") return <Processing onCancel={() => setScreen("camera")} />;
  if (screen === "candidates") return <Candidates candidates={candidates} photoUrl={photoUrl} highlightedFoodId={highlightedFoodId} onBack={() => setScreen("camera")} onHighlight={setHighlightedFoodId} onChoose={chooseFood} />;
  if (screen === "result" && guide) return <Result guide={guide} onBack={() => setScreen("candidates")} />;
  if (screen === "error") return <ErrorPanel kind={errorKind} onHome={() => setScreen("camera")} />;

  return <>
    <main className="screen camera-screen">
      <header className="camera-header">
        <div className="brand-mark camera-brand">K</div>
        <div className="brand-copy"><strong>K-menu</strong><p>A thoughtful guide</p></div>
        <LanguageSelector currentLang={currentLang} onSelectLang={setCurrentLang} />
      </header>
      <section className="camera-intro">
        <p className="camera-kicker">✧ MENU, MADE CLEAR</p>
        <h1>Point your<br />camera at the<br />menu.</h1>
        <p>Take a photo of the Korean item you want to understand. We only show dishes we can identify with confidence.</p>
      </section>
      <section className="camera-card">
        <button className={cameraReady ? "camera-viewer is-ready" : "camera-viewer"} aria-label={cameraReady ? "Camera preview" : "Enable camera"} onClick={() => { if (!cameraReady) void startCamera(); }} type="button">
          {cameraReady ? <video ref={videoRef} autoPlay muted playsInline /> : <div className="camera-placeholder"><span aria-hidden="true">▣</span><p>Tap this frame to enable your camera</p></div>}
          <span className="camera-prompt">{cameraReady ? "Camera ready" : "Point at the menu"}</span>
          <span className="scan-corner top-left" aria-hidden="true" /><span className="scan-corner top-right" aria-hidden="true" /><span className="scan-corner bottom-left" aria-hidden="true" /><span className="scan-corner bottom-right" aria-hidden="true" />
        </button>
        <div className="camera-actions">
          <button className="capture-button" disabled={!cameraReady} onClick={capturePhoto}><span aria-hidden="true">▣</span> Take photo</button>
          <label className="secondary-button upload-button"><span aria-hidden="true" className="upload-icon" />Upload<input accept="image/*" onChange={handleUpload} type="file" /></label>
        </div>
      </section>
      {cameraError && <p className="camera-error">{cameraError}</p>}
      <p className="camera-helper">Your photo is used only to identify the menu text. Read the Korean original before ordering.</p>
      <details className="practice-tools"><summary>Preview error states</summary><button onClick={() => { setErrorKind("ocr"); setScreen("error"); }}>OCR failed</button><button onClick={() => { setErrorKind("unsupported"); setScreen("error"); }}>Unsupported dish</button><button onClick={() => { setErrorKind("service"); setScreen("error"); }}>GPU / DB failed</button></details>
    </main>
    <footer className={consentVisible ? "camera-footer is-obscured" : "camera-footer"}>
      <p>Your photos are safe. They are processed instantly for OCR and not stored.</p>
      <p>© 2026 K-Menu Voice Guide · <button onClick={() => setPrivacyOpen(true)}>Privacy</button> · <button onClick={() => setTermsOpen(true)}>Terms</button></p>
    </footer>
    {privacyOpen && <PrivacyModal onClose={() => setPrivacyOpen(false)} />}
    {termsOpen && <TermsModal onClose={() => setTermsOpen(false)} />}
    {consentVisible && <ConsentBanner closing={consentClosing} essentialCookies={essentialCookies} imageProcessingConsent={imageProcessingConsent} onAccept={acceptConsent} onImageProcessingChange={setImageProcessingConsent} onEssentialCookiesChange={setEssentialCookies} onPrivacy={() => setPrivacyOpen(true)} />}
  </>;
}

function PrivacyModal({ onClose }: { onClose: () => void }) { return <div className="modal-backdrop" onMouseDown={onClose} role="presentation"><section aria-labelledby="privacy-title" aria-modal="true" className="privacy-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog"><button aria-label="Close privacy notice" className="modal-close" onClick={onClose}>×</button><p className="eyebrow">K-MENU VOICE GUIDE</p><h2 id="privacy-title">Privacy Notice</h2><p><em>K-Menu Voice Guide respects your privacy.</em></p><ol><li><strong>Camera &amp; Photos:</strong> Images you capture or upload are processed in real-time solely to detect Korean menu text. Images are not stored on our permanent database.</li><li><strong>Voice Audio:</strong> Generated audio guides are streamed to your device.</li><li><strong>Analytics:</strong> We do not track your personal identity.</li></ol><button className="modal-confirm" onClick={onClose}>Close</button></section></div>; }

function TermsModal({ onClose }: { onClose: () => void }) { return <div className="modal-backdrop" onMouseDown={onClose} role="presentation"><section aria-labelledby="terms-title" aria-modal="true" className="privacy-modal terms-modal" onMouseDown={(event) => event.stopPropagation()} role="dialog"><button aria-label="Close terms of use" className="modal-close" onClick={onClose}>×</button><p className="eyebrow">K-MENU VOICE GUIDE</p><h2 id="terms-title">Terms of Use</h2><section className="terms-section"><h3>1. Service purpose</h3><p>K-Menu Voice Guide helps visitors understand Korean menu items through OCR-based dish matching, English descriptions, and audio guides. It is an informational guide only and does not replace advice from restaurant staff, medical professionals, or other qualified experts.</p></section><section className="terms-section allergy-disclaimer"><h3>2. Allergy and dietary disclaimer</h3><p className="terms-order-warning"><strong>Before you order, you must confirm ingredients, preparation methods, and possible cross-contact directly with the restaurant.</strong></p><p>Allergy, ingredient, vegetarian, spice, and dietary information is provided for general reference only. Recipes, ingredients, sauces, garnishes, portion preparation, and cross-contact risks can vary between restaurants and may change without notice.</p><p>Do not rely on this service as a guarantee that a dish is free from any allergen or suitable for a medical, religious, or dietary requirement. If you have a severe allergy or dietary condition, use extra caution and choose food only after receiving confirmation from the restaurant.</p><p>If you think you are having an allergic reaction, seek emergency medical assistance immediately.</p></section><section className="terms-section"><h3>3. Your use of the service</h3><p>You are responsible for your menu choices and for using the service lawfully. Please upload only menu photos you are permitted to capture and do not use the service to submit harmful, unlawful, or unrelated content.</p></section><section className="terms-section"><h3>4. Availability and changes</h3><p>Dish recognition, translations, audio guides, and service availability may be incomplete or unavailable at times. We may update, change, or discontinue features as the service develops.</p></section><section className="terms-section"><h3>5. Contact</h3><p>For questions about these terms or the service, please contact the K-Menu Voice Guide team through the project contact channel.</p></section><button className="modal-confirm" onClick={onClose}>I understand</button></section></div>; }

function ConsentBanner({ closing, essentialCookies, imageProcessingConsent, onAccept, onEssentialCookiesChange, onImageProcessingChange, onPrivacy }: { closing: boolean; essentialCookies: boolean; imageProcessingConsent: boolean; onAccept: () => void; onEssentialCookiesChange: (value: boolean) => void; onImageProcessingChange: (value: boolean) => void; onPrivacy: () => void }) { return <aside aria-label="Privacy choices" className={closing ? "consent-banner is-closing" : "consent-banner"}><div className="consent-copy"><p className="consent-title">Your privacy choices</p><p>Choose how K-Menu Voice Guide may process your session and menu photos.</p></div><div className="consent-options"><label><input checked={essentialCookies} onChange={(event) => onEssentialCookiesChange(event.target.checked)} type="checkbox" /><span><strong>Essential Cookies &amp; Analytics</strong><small>Allows session continuity and basic performance measurement.</small></span></label><label><input checked={imageProcessingConsent} onChange={(event) => onImageProcessingChange(event.target.checked)} type="checkbox" /><span><strong>Camera &amp; Image Processing</strong><small>Allows menu images to be processed in memory for OCR. Images are not permanently stored.</small></span></label></div><div className="consent-actions"><button className="consent-privacy" onClick={onPrivacy}>Privacy Policy</button><button className="consent-accept" onClick={onAccept}>Accept &amp; Continue</button></div></aside>; }

function FlowHeader({ label }: { label: string }) { return <header className="flow-header"><div className="brand-mark camera-brand">K</div><div className="brand-copy"><strong>K-menu</strong><p>A thoughtful guide</p></div><span>{label}</span></header>; }

function Processing({ onCancel }: { onCancel: () => void }) { return <main className="screen flow-screen processing-screen"><FlowHeader label="Reading menu" /><button className="text-button screen-back" onClick={onCancel}>← Cancel analysis</button><section className="processing-panel"><p className="camera-kicker">✧ MENU, MADE CLEAR</p><div className="spinner" /><h1>Reading your<br />menu.</h1><p>Finding Korean dish names and matching them with our food guide.</p><div className="progress-list"><p>✓ Photo received</p><p>✓ Reading Korean text</p><p className="current-step">◌ Matching dishes</p></div></section></main>; }

function Candidates({ candidates, photoUrl, highlightedFoodId, onBack, onHighlight, onChoose }: { candidates: FoodCandidate[]; photoUrl: string | null; highlightedFoodId: number | null; onBack: () => void; onHighlight: (id: number) => void; onChoose: (id: number) => void }) { return <main className="screen flow-screen candidates-screen"><FlowHeader label="Step 2 of 3" /><button className="text-button screen-back" onClick={onBack}>← Scan another menu</button><section className="flow-intro"><p className="camera-kicker">✧ MENU MATCHES</p><h1>Which dish would<br />you like to know?</h1><p>Compare the highlighted text with your original menu photo.</p></section>{photoUrl && <section className="ocr-evidence"><p className="evidence-title">Your original menu photo</p><div className="menu-photo-frame"><img src={photoUrl} alt="Original uploaded Korean menu" />{candidates.map((food) => food.bbox && <span className={highlightedFoodId === food.foodId ? "ocr-box active" : "ocr-box"} key={food.foodId} style={{ left: `${food.bbox.left}%`, top: `${food.bbox.top}%`, width: `${food.bbox.width}%`, height: `${food.bbox.height}%` }}>{food.foodKo}</span>)}</div><p className="evidence-help">Outlined labels are demonstration boxes. Real OCR will return exact locations.</p></section>}<section className="candidate-list">{candidates.map((food, index) => <button className="candidate-card" key={food.foodId} onClick={() => void onChoose(food.foodId)} onMouseEnter={() => onHighlight(food.foodId)} onFocus={() => onHighlight(food.foodId)}><span className="food-index">{String(index + 1).padStart(2, "0")}</span><span className="candidate-copy"><strong>{food.foodKo}</strong><span>{food.foodEn}</span><small>{food.matchScore}% match</small></span><span className="chevron">›</span></button>)}</section></main>; }

function Result({ guide, onBack }: { guide: FoodGuide; onBack: () => void }) { const cards = [["Description", guide.description], ["How to eat", guide.howToEat], ["Ingredients", guide.ingredient], ["Allergy notice", guide.allergy], ["Pronunciation", guide.pronunciation], ["Spice level", guide.spicy]]; return <main className="screen flow-screen result-screen"><FlowHeader label="Your guide" /><button className="text-button screen-back" onClick={onBack}>← Back to dishes</button><section className="result-hero"><p className="camera-kicker">✧ YOUR FOOD GUIDE</p><h1>{guide.foodEn}</h1><p>{guide.foodKo} · {guide.pronunciation}</p><p className="badge">{guide.spicy}</p></section><p className={guide.audioUrl ? "audio-status" : "audio-status unavailable"}>{guide.audioUrl ? "Voice guide is ready to play." : "Text guide is ready to read."}</p><section className="guide-grid">{cards.map(([title, text]) => <section className={title === "Allergy notice" ? "info-card warning" : "info-card"} key={title}><div><h2>{title}</h2><p>{text}</p></div></section>)}</section>{guide.audioUrl ? <audio src={guide.audioUrl} autoPlay controls /> : <section className="tts-error-card"><strong>Voice guide is unavailable right now.</strong><p>Your food details are still ready to read.</p><button onClick={() => alert("In the real app, this requests TTS again.")}>Try voice guide again</button></section>}</main>; }

function ErrorPanel({ kind, onHome }: { kind: ErrorKind; onHome: () => void }) { const content = { ocr: ["We couldn't read the menu", "Try brighter lighting, hold the menu straight, and move closer to the text.", "Take another photo"], unsupported: ["This dish is not supported yet", "We currently support 50 popular Korean dishes. Please choose another item.", "Scan another menu"], service: ["We couldn't prepare your food guide", "Please check your connection and try again.", "Try again"] }[kind]; return <main className="screen flow-screen error-screen"><FlowHeader label="K-menu" /><section className="error-card"><p className="camera-kicker">✧ LET'S TRY AGAIN</p><span className="error-symbol">!</span><h1>{content[0]}</h1><p>{content[1]}</p>{kind === "unsupported" && <><details className="support-details"><summary>Supported dishes (50)</summary><ul className="dish-list">{SUPPORTED_DISHES.map(([ko, en]) => <li key={en}><strong>{ko}</strong><span>{en}</span></li>)}</ul></details><section className="guide-info"><h2>What can I learn?</h2><ul><li>Pronunciation</li><li>Spice level: five flames and SHU reference</li><li>Description and ingredients</li><li>How to eat</li><li>Allergies and vegetarian information</li></ul></section></>}<button className="primary-button" onClick={onHome}>{content[2]}</button></section></main>; }

export default App;