// Backend API client — the only module in this app that talks HTTP to K_Menu_Talk.py.
// Contract source: docs/specs/api-layer.md and docs/specs/cart.md in the main project repo.
import axios from "axios";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

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

export type ApiCandidate = {
  food_id: number;
  name_kr: string;
  name_en: string;
  score: number;
  modifiers: { spice: string[]; ingredient: string[] };
  thumbnail_url: string | null;
  thumbnail_attribution: string | null;
  source: CandidateSource | null;
  price_krw: number | null;
  price_krw_display: string | null;
  // 1-5, or null when the food row has no spice_level (docs/specs/api-layer.md, added 2026-08-22).
  spice_level: number | null;
};

export type AnalyzeStatus = "ocr_empty" | "unsupported_food" | "candidates_found";

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
