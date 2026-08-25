// Backend API client — the only module in this app that talks HTTP to K_Menu_Talk.py.
// Contract source: docs/specs/api-layer.md and docs/specs/cart.md in the main project repo.
import axios from "axios";

// 서버 주소는 빌드할 때 JS 안에 박힌다(Vite의 VITE_ 규칙). 그래서 배포본이 다른 서버를
// 보게 하려면 원래는 다시 빌드해야 했다.
//
// 주소창에 `?api=...`를 붙이면 그 주소를 대신 쓰고, 브라우저에 기억해 둔다. 쓰임새는 둘이다.
//   - 시험: HF의 GPU는 유료라 꺼둘 때가 많다. 그때 개인 GPU를 cloudflared 터널로 열어
//     `?api=https://xxx.trycloudflare.com`으로 붙이면 재배포 없이 그쪽을 본다.
//   - 대비: 시연 중 서버 Space가 죽어도 주소 하나로 예비 서버로 옮길 수 있다.
// `?api=` 만 붙이면(값 없이) 기억을 지우고 원래 주소로 돌아간다.
//
// 이 값은 **이 브라우저에서만** 쓰인다. 다른 사람이 보는 화면에는 영향이 없다.
// 다만 https 페이지는 http 주소를 부를 수 없으므로(브라우저가 막는다), 넘기는 주소도
// https여야 한다.
const API_OVERRIDE_KEY = "kmenu-api-base-url";

function resolveBaseUrl(): string {
  const builtIn = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

  // 서버에서 미리 그려두는 화면이 아니라 브라우저에서만 도는 앱이지만, 혹시 window가
  // 없는 곳(테스트 등)에서 불려도 죽지 않게 한다.
  if (typeof window === "undefined") return builtIn;

  const asked = new URLSearchParams(window.location.search).get("api");
  if (asked !== null) {
    const trimmed = asked.trim().replace(/\/+$/, "");
    if (trimmed) {
      window.localStorage.setItem(API_OVERRIDE_KEY, trimmed);
    } else {
      window.localStorage.removeItem(API_OVERRIDE_KEY);
    }
  }

  return window.localStorage.getItem(API_OVERRIDE_KEY) || builtIn;
}

const API_BASE_URL = resolveBaseUrl();

/** 지금 어느 서버를 보고 있는지. 기본값이 아니면 화면에 알린다. */
export const apiBaseUrl = API_BASE_URL;
export const isUsingCustomApi =
  API_BASE_URL !== (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

const client = axios.create({ baseURL: API_BASE_URL });

// There is no sign-in, so a cart belongs to this browser. The id is generated once and
// kept in localStorage; the server treats an unknown id as an empty cart (no 404).
const CART_ID_KEY = "kmenu-cart-id";

function cartId(): string {
  const stored = localStorage.getItem(CART_ID_KEY);
  if (stored) return stored;
  const created = crypto.randomUUID();
  localStorage.setItem(CART_ID_KEY, created);
  return created;
}

function cartHeaders() {
  return { "X-Cart-Id": cartId() };
}

// ---------------------------------------------------------------------------
// Types — mirror the Pydantic response models in K_Menu_Talk.py exactly.
// ---------------------------------------------------------------------------

export type CandidateSource = { text: string; left: number; top: number; width: number; height: number };

// 메뉴 줄에 붙은 수식어 하나. 서버는 한국어 키워드와 **영어 번역을 함께** 보낸다
// (menu_modifiers 테이블). 화면에 내보내는 것은 keyword_en 쪽이다 — 읽는 사람이
// 한국어를 못 읽는 여행자이고, 같은 음식이 여러 줄 나올 때(돼지김치찌개/참치김치찌개)
// 이것이 서로를 구분할 수 있는 유일한 수단이기 때문이다.
// tier(1~5)는 category='spice'에만 있고 재료에는 없다.
export type Modifier = { keyword: string; keyword_en: string | null; tier?: number | null };

export type ApiCandidate = {
  food_id: number;
  name_kr: string;
  name_en: string;
  score: number;
  modifiers: { spice: Modifier[]; ingredient: Modifier[] };
  thumbnail_url: string | null;
  thumbnail_attribution: string | null;
  source: CandidateSource | null;
  price_krw: number | null;
  price_krw_display: string | null;
  // 1-5, or null when the food row has no spice_level (docs/specs/api-layer.md, added 2026-08-22).
  spice_level: number | null;
  // 이 후보가 나온 메뉴판 줄의 글자 그대로. 같은 음식이 여러 줄에 있으면 후보도 여러 개
  // 나오는데(반반족발 / 마늘족발 → 둘 다 "족발"), 그때 무엇이 다른지 알려주는 유일한
  // 단서다. 이걸 안 보여주면 화면에는 같은 이름이 두 번 뜬 것처럼 보인다.
  menu_text: string | null;
  // 같은 줄에서 가격만 뗀 것. 화면은 가격을 따로 보여주므로 이름 자리에는 이쪽을 쓴다.
  name_text: string | null;
  // 메뉴판에서 위에서부터 센 줄 번호. 화면을 메뉴판에 인쇄된 순서로 늘어놓는 데 쓴다.
  line_no: number | null;
};

// not_a_menu는 글자는 읽혔지만 가격 붙은 메뉴 줄이 하나도 없을 때다. 얼굴이나 풍경을
// 찍어도 OCR이 잡음 글자를 만들어내 ocr_empty로는 잡히지 않는데, 이쪽은 **다시 찍으면
// 해결되고** unsupported_food는 다시 찍어도 결과가 같다 — 안내가 달라야 하는 이유다.
export type AnalyzeStatus = "ocr_empty" | "not_a_menu" | "unsupported_food" | "candidates_found";

export type AnalyzeResponse = {
  status: AnalyzeStatus;
  ocr_text: string;
  candidates: ApiCandidate[];
};

export type SupportedFood = { food_id: number; name_kr: string; name_en: string };

export type FoodDetail = {
  food_id: number;
  name_kr: string;
  name_en: string;
  spice_level: number | null;
  details: Record<string, string>;
  narration_text: string;
  style: "GUIDE" | "CAUTION";
  tts_status: "ok" | "not_ready";
  narration_audio_path: string | null;
  tts_latency_ms: number;
  // 음식 이름만 읽은 음성. 나레이션과 별개 파일이라 이름 옆 스피커를 눌러도 설명이
  // 같이 나오지 않는다. 서버가 아직 옛 버전이면 없을 수 있어 optional로 둔다.
  name_audio_path?: string | null;
  name_tts_status?: "ok" | "not_ready";
};

export type CartLine = {
  food_id: number;
  name_kr: string;
  name_en: string;
  price_krw: number | null;
  price_krw_display: string | null;
  quantity: number;
  line_total_krw: number | null;
  line_total_display: string | null;
};

export type CartResponse = {
  cart_id: string;
  items: CartLine[];
  item_count: number;
  total_krw: number;
  total_krw_display: string;
  has_unpriced_items: boolean;
};

export const EMPTY_CART: CartResponse = {
  cart_id: "",
  items: [],
  item_count: 0,
  total_krw: 0,
  total_krw_display: "₩0",
  has_unpriced_items: false,
};

// What the cart endpoint needs to identify a line. A candidate card and a cart line both
// satisfy this shape, so the same updateCount() call works from either place.
export type CartItemRef = { food_id: number; name_kr: string; name_en: string; price_krw: number | null };

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

export async function analyzeMenu(image: File): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("image", image);
  const { data } = await client.post<AnalyzeResponse>("/api/analyze", form);
  return data;
}

export async function listSupportedFoods(): Promise<SupportedFood[]> {
  const { data } = await client.get<SupportedFood[]>("/api/foods");
  return data;
}

export async function getFoodDetail(foodId: number): Promise<FoodDetail> {
  const { data } = await client.get<FoodDetail>(`/api/foods/${foodId}`);
  return data;
}

export async function getCart(): Promise<CartResponse> {
  const { data } = await client.get<CartResponse>("/api/cart", { headers: cartHeaders() });
  return data;
}

// The server owns every cart rule (merge by food_id, no negative quantities, drop the
// line at zero) and always answers with the whole cart, so the caller never reconciles
// partial state itself — it just replaces its cart state with this response.
export async function changeCartItem(item: CartItemRef, quantityDelta: number): Promise<CartResponse> {
  const { data } = await client.post<CartResponse>(
    "/api/cart/items",
    { food_id: item.food_id, name_kr: item.name_kr, name_en: item.name_en, price_krw: item.price_krw, quantity_delta: quantityDelta },
    { headers: cartHeaders() },
  );
  return data;
}

export async function clearCart(): Promise<CartResponse> {
  const { data } = await client.delete<CartResponse>("/api/cart", { headers: cartHeaders() });
  return data;
}

// narration_audio_path comes back as a relative path ("/audio/xxx.wav"); the API base
// has to be prepended before the browser can play it.
export function resolveAudioUrl(path: string | null): string | null {
  if (!path) return null;
  return `${API_BASE_URL}${path}`;
}
