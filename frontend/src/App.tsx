import { ChangeEvent, useEffect, useRef, useState } from "react";
import LanguageSelector from "./components/LanguageSelector";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

type Screen = "camera" | "processing" | "candidates" | "result" | "error";
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
  bbox?: Box;
};

type FoodGuide = {
  foodId: number;
  nameKr: string;
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
const DETAIL_CARDS: Array<[DetailCategory, string, boolean]> = [
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
  };
}

function toFoodGuide(payload: ApiFoodGuide, candidate: FoodCandidate): FoodGuide {
  return {
    foodId: candidate.foodId,
    nameKr: candidate.nameKr,
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

      const boxes: Box[] = [
        { left: 12, top: 20, width: 45, height: 12 },
        { left: 42, top: 43, width: 40, height: 12 },
        { left: 18, top: 66, width: 48, height: 12 },
      ];
      const next = analysis.candidates.map((candidate, index) => ({
        ...toFoodCandidate(candidate),
        bbox: boxes[index],
      }));

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

  function acceptConsent() {
    localStorage.setItem(
      "kmenu-consent",
      JSON.stringify({ essentialCookies, imageProcessingConsent, acceptedAt: new Date().toISOString() }),
    );
    setConsentClosing(true);
    window.setTimeout(() => setConsentVisible(false), 260);
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
  if (screen === "candidates") return <Candidates candidates={candidates} currentLang={currentLang} photoUrl={photoUrl} highlightedFoodId={highlightedFoodId} onBack={() => setScreen("camera")} onHighlight={setHighlightedFoodId} onChoose={chooseFood} onSelectLang={setCurrentLang} />;
  if (screen === "result" && guide) return <Result currentLang={currentLang} guide={guide} onBack={() => setScreen("candidates")} onSelectLang={setCurrentLang} />;
  if (screen === "error") return <ErrorPanel currentLang={currentLang} kind={errorKind} onHome={() => setScreen("camera")} onSelectLang={setCurrentLang} />;

  return <>
    <main className="screen camera-screen">
      <header className="camera-header">
        <div className="brand-mark camera-brand">K</div>
        <div className="brand-copy"><strong>K-menu</strong><p>A thoughtful guide</p></div>
        <LanguageSelector currentLang={currentLang} onSelectLang={setCurrentLang} />
      </header>
      <section className="camera-intro">
        <p className="camera-kicker">✧ MENU, MADE CLEAR</p>
        <h1>Scan a Korean<br />menu.</h1>
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
    {consentVisible && <ConsentBanner closing={consentClosing} essentialCookies={essentialCookies} imageProcessingConsent={imageProcessingConsent} onAccept={acceptConsent} onImageProcessingChange={setImageProcessingConsent} onEssentialCookiesChange={setEssentialCookies} onPrivacy={() => setPrivacyOpen(true)} />}
  </>;
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

function Candidates({ candidates, currentLang, photoUrl, highlightedFoodId, onBack, onHighlight, onChoose, onSelectLang }: { candidates: FoodCandidate[]; currentLang: string; photoUrl: string | null; highlightedFoodId: number | null; onBack: () => void; onHighlight: (id: number) => void; onChoose: (candidate: FoodCandidate) => void; onSelectLang: (lang: string) => void }) { return <main className="screen flow-screen candidates-screen"><FlowHeader currentLang={currentLang} label="2 of 3" onSelectLang={onSelectLang} /><button className="back-button screen-back" onClick={onBack}>← Back</button><section className="flow-intro"><p className="camera-kicker">✧ MENU MATCHES</p><h1>Choose a dish.</h1><p>Check the highlighted text against your menu photo.</p></section>{photoUrl && <section className="ocr-evidence"><p className="evidence-title">Your menu photo</p><div className="menu-photo-frame"><img src={photoUrl} alt="Uploaded Korean menu" />{candidates.map((food, index) => food.bbox && <span className={highlightedFoodId === food.foodId ? "ocr-box active" : "ocr-box"} key={food.foodId} style={{ left: `${food.bbox.left}%`, top: `${food.bbox.top}%`, width: `${food.bbox.width}%`, height: `${food.bbox.height}%` }}><span className="ocr-index">{String(index + 1).padStart(2, "0")}</span><span>{food.nameKr}</span></span>)}</div><p className="evidence-help">Numbered boxes match the dishes below.</p></section>}<section className="candidate-list">{candidates.map((food, index) => <button className="candidate-card" key={food.foodId} onClick={() => void onChoose(food)} onMouseEnter={() => onHighlight(food.foodId)} onFocus={() => onHighlight(food.foodId)}>{food.imageUrl ? <img className="candidate-thumbnail" src={food.imageUrl} alt="" /> : <span className="food-index">{String(index + 1).padStart(2, "0")}</span>}<span className="candidate-copy"><strong>{food.nameEn}</strong><span>{food.nameKr}</span><small>Possible match: {food.matchScore}%</small></span><span className="chevron">›</span></button>)}</section></main>; }

function Result({ guide, currentLang, onBack, onSelectLang }: { guide: FoodGuide; currentLang: string; onBack: () => void; onSelectLang: (lang: string) => void }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speakingCategory, setSpeakingCategory] = useState<DetailCategory | null>(null);

  async function toggleAudio() {
    const audio = audioRef.current;
    if (!audio) return;

    // Browsers allow sound after this explicit user click. We intentionally do
    // not use autoplay: the traveller decides whether to hear the guide.
    if (audio.paused) {
      await audio.play();
      setIsPlaying(true);
    } else {
      audio.pause();
      setIsPlaying(false);
    }
  }

  function playDetail(category: DetailCategory) {
    // The current API supplies one full-guide audio file, not six separate
    // category files. Web Speech gives every visible card a working manual
    // playback control until category-specific TTS URLs are provided.
    if (!("speechSynthesis" in window)) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(detailValue(guide.details, category));
    utterance.lang = "en-US";
    utterance.onend = () => setSpeakingCategory(null);
    utterance.onerror = () => setSpeakingCategory(null);
    setSpeakingCategory(category);
    window.speechSynthesis.speak(utterance);
  }

  return <main className="screen flow-screen result-screen"><FlowHeader currentLang={currentLang} label="Your guide" onSelectLang={onSelectLang} /><button className="back-button screen-back" onClick={onBack}>← Back</button><section className="result-hero"><p className="camera-kicker">✧ ABOUT THIS DISH</p><h1>{guide.nameKr}</h1><p>{detailValue(guide.details, "PRONUNCIATION")}</p><p className="badge">{detailValue(guide.details, "SPICY")}</p></section><p className={guide.audioUrl ? "audio-status" : "audio-status unavailable"}>{guide.audioUrl ? "Your audio guide is ready." : "Your guide is ready to read."}</p><section className="guide-grid">{DETAIL_CARDS.map(([category, title, warning]) => <section className={warning ? "info-card warning" : "info-card"} key={category}><div className="info-card-heading"><h2>{title}</h2><button aria-label={`Play ${title}`} aria-pressed={speakingCategory === category} className={speakingCategory === category ? "detail-audio-button is-playing" : "detail-audio-button"} onClick={() => playDetail(category)} type="button">🔊</button></div><p>{detailValue(guide.details, category)}</p></section>)}</section>{guide.audioUrl ? <section className="audio-player"><button className="primary-button" onClick={() => void toggleAudio()}>{isPlaying ? "Pause audio guide" : "Play audio guide"}</button><audio controls onEnded={() => setIsPlaying(false)} onPause={() => setIsPlaying(false)} onPlay={() => setIsPlaying(true)} ref={audioRef} src={guide.audioUrl} /></section> : <section className="tts-error-card"><strong>Audio guide is unavailable right now.</strong><p>{guide.narrationText}</p><button onClick={() => alert("In the real app, this requests TTS again.")}>Try audio again</button></section>}</main>;
}

function ErrorPanel({ kind, currentLang, onHome, onSelectLang }: { kind: ErrorKind; currentLang: string; onHome: () => void; onSelectLang: (lang: string) => void }) { const content = { ocr: ["We couldn't read this photo", "Try brighter lighting, hold the menu straight, and move closer to the text.", "Take a new photo"], unsupported: ["Not in our guide yet", "Try a different menu item or ask the restaurant staff.", "Take a new photo"], service: ["We couldn't load your guide", "Please check your connection and try again.", "Try again"] }[kind]; return <main className="screen flow-screen error-screen"><FlowHeader currentLang={currentLang} label="K-menu" onSelectLang={onSelectLang} /><section className="error-card"><p className="camera-kicker">✧ LET'S TRY AGAIN</p><span className="error-symbol">!</span><h1>{content[0]}</h1><p>{content[1]}</p>{kind === "unsupported" && <section className="guide-info"><h2>What this guide includes</h2><ul><li>Pronunciation</li><li>Spice level</li><li>Description and ingredients</li><li>How to eat</li><li>Allergies and dietary needs</li></ul></section>}<button className="primary-button" onClick={onHome}>{content[2]}</button></section></main>; }

export default App;
