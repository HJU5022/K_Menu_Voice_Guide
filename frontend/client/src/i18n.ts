// 화면 문구 두 벌 — 영어와 한국어.
//
// **음식 설명·나레이션은 여기 없다.** 그건 서버가 DB에서 가져오는데 지금은 영어만
// 들어 있다. 한국어를 넣으려면 food_details·food_narration에 언어 칸을 더하고 서버가
// 그 값으로 고르게 해야 한다(food_id만으로는 같은 음식·같은 항목이 두 줄이 되어
// 어느 것이 어느 언어인지 가릴 수 없다). 그건 별도 작업이다.
//
// 여기 있는 것은 **화면이 스스로 적는 말**뿐이다 — 버튼, 제목, 안내, 오류 문구.
//
// 새 문구를 넣을 때: en에 넣으면 ko에도 넣어야 한다. 타입이 그것을 강제한다.

export type Lang = "en" | "ko";

const en = {
  // 머리말
  brandTagline: "A thoughtful guide",
  language: "Language",
  settings: "Settings",
  goHome: "Go to the start",

  // 랜딩 — 처음 들어온 사람이 무엇을 해주는 서비스인지 먼저 알게 하는 화면.
  //
  // **heroTitle·heroLead는 한국어가 원본이다.** 영어를 먼저 쓰고 옮기면 "아는 음식을 찾아"
  // 처럼 한국어에서 뜻이 뒤집히는 문장이 나온다(누가 아는 음식인지 읽는 사람은 모른다).
  // 이 두 줄을 고칠 때는 ko를 먼저 자연스럽게 쓰고 en을 거기서 옮긴다.
  //
  // heroEyebrow·heroLead·privacyNote는 예전에 촬영 화면 위에 얹혀 있던 것을 여기로 **옮긴**
  // 것이다. 두 화면에 같은 말을 겹쳐 두면 "Get started"를 눌러도 제자리인 줄 안다.
  heroEyebrow: "MENU, MADE CLEAR",
  heroTitle: "Know what you're ordering.",
  heroLead:
    "Photograph a Korean menu. We find the dishes we can guide you through and explain each one — what it is, what goes in it, and how spicy.",
  privacyNote: "Your photo is used only to identify menu text. It is not stored.",
  // 세 단계는 **제목만** 적는다. 이 화면이 하는 일은 설득이 아니라 "이렇게 쓰면 된다"를
  // 5초 안에 보여주는 것이고, 설명을 붙이면 폰에서 CTA가 화면 밖으로 밀린다.
  landingStepsEyebrow: "HOW IT WORKS",
  landingStep1: "Photograph the menu",
  landingStep2: "Pick a dish",
  landingStep3: "Listen in English",
  landingCta: "Get started",

  // 촬영/업로드 — 서비스 설명은 랜딩이 끝냈다. 여기는 사진을 넣는 일만 한다.
  cameraTitle: "Scan the menu.",
  cameraLead: "Fit the whole menu in the frame, or upload a photo you already have.",
  takePhoto: "Take a photo",
  uploadPhoto: "Upload a menu photo",
  cameraHelper: "Read the Korean original before ordering. We help you understand the choice.",

  // 읽는 중
  processingEyebrow: "READING YOUR MENU",
  processingTitle: "Finding dishes worth knowing.",
  processingBody:
    "We are looking at names, prices, and the details that make ordering easier.",

  // 후보 목록
  back: "Back",
  photoReady: "Menu photo",
  photoReadyStrong: "ready to compare",
  notLocated: (missing: number, total: number) =>
    `${missing} of ${total} could not be located on the photo`,
  matchesFound: (n: number) => `${n} MATCH${n === 1 ? "" : "ES"} FOUND`,
  candidatesTitle: "What would you like to know?",
  candidatesLead: "Add a dish to your list, or open one for a closer guide.",
  menuLinePrefix: "Menu",
  viewGuide: "View guide",
  addOne: (name: string) => `Add one ${name}`,
  removeOne: (name: string) => `Remove one ${name}`,
  enlargePhoto: (name: string) => `Enlarge photo of ${name}`,
  enlargeMenuPhoto: "Open the menu photo larger",
  zoomIn: "Zoom in",
  zoomOut: "Zoom out",
  reset: "Reset",
  cameraOpening: "Opening the camera…",
  uploadInstead: "Upload instead",

  // 장바구니
  cartEyebrow: "YOUR SHORTLIST",
  cartTitle: "Your cart",
  cartHelpLabel: "What is this list?",
  cartHelp:
    "This list is only for showing the staff when you order. Nothing is sent to the restaurant, and nothing is charged here.",
  cartEmpty: "Nothing here yet. Use + on a dish to add it.",
  cartTotal: "Total",
  order: "Order",
  clearCart: "Clear",

  // 주문 확인 — 여행자가 읽는 부분만. 종업원이 읽는 줄은 늘 한국어다.
  orderEyebrow: "SHOW THIS TO THE STAFF",
  orderTitle: "Your order",
  orderLead:
    "This app does not send anything to the restaurant. Show this screen when you order.",
  orderUnpriced:
    "Some dishes had no readable price on the photo, so they are not counted in the total.",
  orderWarning: "Confirm the dishes, prices, and any allergies with the staff before you order.",
  backToDishes: "Back to dishes",

  // 설정
  settingsHowItWorks: "How it works",
  settingsStep1: "You photograph a menu. The photo is read for text and is not stored.",
  settingsStep2: "We match the Korean names against the dishes in our guide.",
  settingsStep3: "Each match gets an English explanation and a spoken Korean name.",
  settingsCredit:
    "Dish photos come from the AI Hub Tourism Menu Board Dataset (NIA) and are shown with their credit.",
  supportedDishes: "Supported dishes",
  supportedLoading: "Loading…",
  supportedError: "Could not load the supported dishes list.",
  close: "Close",
  privacyTitle: "Privacy Notice",
  privacyBody:
    "K-Menu Voice Guide respects your privacy. Photos are processed in real time to identify Korean menu text and are not stored on our permanent database.",
  termsTitle: "Terms of Use",
  termsBody:
    "This service is an informational guide only. Before ordering, confirm ingredients, preparation methods, and possible cross-contact directly with the restaurant.",
  privacy: "Privacy",
  terms: "Terms",

  // 실패 안내 — 서버가 주는 status에 따라 고른다.
  errOcrEmptyTitle: "We couldn't read this photo",
  errOcrEmptyHint: "Try brighter lighting, hold the menu straight, and move closer to the text.",
  errNotAMenuTitle: "We couldn't find a menu here",
  errNotAMenuHint: "Point the camera at a printed menu with prices, then take the photo again.",
  errUnsupportedTitle: "Not in our guide yet",
  errUnsupportedHint: "Try a different menu item or ask the restaurant staff.",
  // 서버에 닿지 못했거나 서버가 5xx를 준 경우. **사진 이야기를 하면 안 된다** —
  // 사진을 다시 찍어도 서버가 살아나지는 않는다. 한때 이 자리에 "더 밝게 다시 찍으세요"가
  // 적혀 있어서, 서버가 죽어도·PDF를 올려도·12MB를 올려도 전부 같은 안내가 나갔다
  // (실측 2026-08-26). errOcrEmpty*와 문장이 겹치지 않게 유지할 것.
  errServiceTitle: "We can't reach the service",
  errServiceHint: "The server may still be waking up. Wait a moment, then try again.",
  // 올린 파일 자체가 문제인 경우(400·413). 여기서는 **다시 찍으라고 하지 않는다** —
  // 12MB 사진은 다시 찍어도 12MB고, PDF는 다시 찍어도 PDF다. 고를 것을 바꿔야 한다.
  errBadUploadTitle: "That file won't work",
  errBadUploadHint: "Choose a photo of a menu — an image file under 10 MB.",
  chooseAnotherPhoto: "Choose another photo",
  takeNewPhoto: "Take a new photo",
  cartUnavailable: "Cart is unavailable right now.",
  cartChangeFailed: "Could not update the cart. Check your connection and try again.",
  cartClearFailed: "Could not empty the cart. Check your connection and try again.",
};

/** 한국어. 영어를 옮긴 것이 아니라 **한국어로 자연스러운 말**로 적는다.
 *  읽는 사람은 한국어 화자이므로 "당신의 사진" 같은 번역투를 피한다. */
const ko: typeof en = {
  brandTagline: "메뉴판을 읽어주는 안내",
  language: "언어",
  settings: "설정",
  goHome: "처음 화면으로",

  heroEyebrow: "메뉴판, 알아보기 쉽게",
  heroTitle: "무슨 음식인지 알고 주문하세요.",
  heroLead:
    "한국어 메뉴판을 사진으로 찍어보세요. 안내할 수 있는 음식을 찾아 하나씩 설명해 드립니다 — 어떤 음식인지, 무엇이 들어가는지, 얼마나 매운지.",
  privacyNote: "사진은 메뉴 글자를 읽는 데만 쓰고 저장하지 않습니다.",
  landingStepsEyebrow: "이렇게 씁니다",
  landingStep1: "메뉴판 촬영하기",
  landingStep2: "음식 선택하기",
  landingStep3: "영어 설명 듣기",
  landingCta: "시작하기",

  cameraTitle: "메뉴판을 촬영해 주세요.",
  cameraLead: "메뉴판 전체가 화면에 들어오게 찍거나, 가지고 있는 사진을 올려주세요.",
  takePhoto: "사진 찍기",
  uploadPhoto: "메뉴판 사진 올리기",
  cameraHelper: "주문 전에 한국어 원문을 함께 확인하세요. 고르는 것을 돕는 안내입니다.",

  processingEyebrow: "메뉴판을 읽는 중",
  processingTitle: "알 만한 음식을 찾고 있습니다.",
  processingBody: "이름과 가격, 주문에 도움이 되는 것들을 살펴보고 있습니다.",

  back: "뒤로",
  photoReady: "올린 메뉴판",
  photoReadyStrong: "비교해 보세요",
  notLocated: (missing: number, total: number) =>
    `${total}개 중 ${missing}개는 사진에서 자리를 찾지 못했습니다`,
  matchesFound: (n: number) => `${n}개를 찾았습니다`,
  candidatesTitle: "무엇이 궁금하세요?",
  candidatesLead: "담아두거나, 눌러서 자세히 볼 수 있습니다.",
  menuLinePrefix: "메뉴판",
  viewGuide: "자세히",
  addOne: (name: string) => `${name} 하나 담기`,
  removeOne: (name: string) => `${name} 하나 빼기`,
  enlargePhoto: (name: string) => `${name} 사진 크게 보기`,
  enlargeMenuPhoto: "메뉴판 사진 크게 보기",
  zoomIn: "확대",
  zoomOut: "축소",
  reset: "원래대로",
  cameraOpening: "카메라를 여는 중…",
  uploadInstead: "사진 올리기",

  cartEyebrow: "담아둔 메뉴",
  cartTitle: "장바구니",
  cartHelpLabel: "이 목록은 무엇인가요?",
  cartHelp:
    "주문할 때 직원에게 보여주기 위한 목록입니다. 식당으로 전송되지 않고, 결제도 되지 않습니다.",
  cartEmpty: "아직 비어 있습니다. 음식의 + 를 눌러 담아보세요.",
  cartTotal: "합계",
  order: "주문 보여주기",
  clearCart: "비우기",

  orderEyebrow: "직원에게 보여주세요",
  orderTitle: "주문 내역",
  orderLead: "이 앱은 주문을 식당으로 보내지 않습니다. 주문할 때 이 화면을 보여주세요.",
  orderUnpriced: "사진에서 가격을 읽지 못한 메뉴가 있어 합계에 넣지 않았습니다.",
  orderWarning: "주문 전에 메뉴와 가격, 알레르기 여부를 직원과 직접 확인해 주세요.",
  backToDishes: "메뉴 다시 보기",

  settingsHowItWorks: "어떻게 동작하나요",
  settingsStep1: "메뉴판을 찍으면 글자만 읽고, 사진은 저장하지 않습니다.",
  settingsStep2: "읽어낸 한국어 이름을 안내할 수 있는 음식과 맞춰봅니다.",
  settingsStep3: "찾은 음식마다 영어 설명과 한국어 발음을 들려드립니다.",
  settingsCredit:
    "음식 사진은 AI Hub 관광 음식메뉴판 데이터셋(NIA)에서 가져왔으며 출처와 함께 보여드립니다.",
  supportedDishes: "안내할 수 있는 음식",
  supportedLoading: "불러오는 중…",
  supportedError: "음식 목록을 불러오지 못했습니다.",
  close: "닫기",
  privacyTitle: "개인정보 안내",
  privacyBody:
    "올린 사진은 메뉴 글자를 알아보는 데만 실시간으로 쓰이고, 저장소에 남기지 않습니다.",
  termsTitle: "이용 안내",
  termsBody:
    "이 서비스는 참고용 안내입니다. 주문 전에 재료와 조리 방식, 알레르기 가능성은 식당에 직접 확인해 주세요.",
  privacy: "개인정보",
  terms: "이용약관",

  errOcrEmptyTitle: "사진에서 글자를 읽지 못했습니다",
  errOcrEmptyHint: "밝은 곳에서 메뉴판을 똑바로, 글자가 크게 보이도록 찍어주세요.",
  errNotAMenuTitle: "메뉴판을 찾지 못했습니다",
  errNotAMenuHint: "가격이 적힌 메뉴판이 화면에 들어오도록 다시 찍어주세요.",
  errUnsupportedTitle: "아직 안내할 수 없는 메뉴입니다",
  errUnsupportedHint: "다른 메뉴를 찍어보거나 직원에게 물어보세요.",
  errServiceTitle: "서비스에 연결할 수 없습니다",
  errServiceHint: "서버가 아직 깨어나는 중일 수 있습니다. 잠시 후 다시 시도해주세요.",
  errBadUploadTitle: "이 파일은 사용할 수 없습니다",
  errBadUploadHint: "메뉴판 사진을 골라주세요 — 10MB 이하 이미지 파일이어야 합니다.",
  chooseAnotherPhoto: "다른 사진 고르기",
  takeNewPhoto: "다시 찍기",
  cartUnavailable: "장바구니를 불러오지 못했습니다.",
  cartChangeFailed: "장바구니를 고치지 못했습니다. 연결을 확인하고 다시 시도해 주세요.",
  cartClearFailed: "장바구니를 비우지 못했습니다. 연결을 확인하고 다시 시도해 주세요.",
};

export type Strings = typeof en;
export const STRINGS: Record<Lang, Strings> = { en, ko };
