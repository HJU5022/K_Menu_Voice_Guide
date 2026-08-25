// 지금 고른 언어를 화면 전체가 함께 보게 한다.
//
// 언어 값은 Home이 가지고 있는데, 화면 조각들(카드·장바구니·설정창)은 그 아래 여러 겹에
// 흩어져 있다. 값을 층층이 넘기면 중간 조각들이 쓰지도 않는 것을 받아 나르게 된다.
// Context는 "필요한 곳에서 직접 꺼내 쓰는" 통로다.
//
// 쓰는 법: 조각 안에서 `const t = useT();` 하고 `t.back` 처럼 쓴다.
import { createContext, useContext } from "react";

import { STRINGS, type Lang } from "./i18n";

export const LangContext = createContext<Lang>("en");

/** 지금 언어의 문구 묶음. */
export function useT() {
  return STRINGS[useContext(LangContext)];
}
