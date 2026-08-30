# 구글폼 문항 — 영어·한국어 병기판

폼은 **하나만** 만듭니다. 한 문항 안에 영어와 한국어를 같이 넣어, 세 분이 같은
폼에 응답하게 합니다. 그래야 CSV가 하나로 나오고 집계가 한 번에 끝납니다.

**옮겨 넣는 법**

- 굵은 줄이 **질문 제목**입니다. 영어 줄 뒤에 줄바꿈(`Shift+Enter`)하고 한국어 줄을
  이어 붙이세요. 구글폼 질문 제목 칸은 줄바꿈을 지원합니다.
- `[대괄호]` 줄은 **문항 유형 안내**이며 폼에 넣지 않습니다.
- `> 도움말:` 로 시작하는 줄은 구글폼의 **설명(Description)** 칸에 넣습니다.
- 선형 배율은 양 끝에만 라벨을 달 수 있습니다. 지정한 대로 넣으세요.

**폼 제목**

```
K-Menu Voice Guide — User Test / 사용자 테스트
```

**폼 설명**

```
Thank you for testing K-Menu Voice Guide. This survey takes about 5 minutes.
Please answer after you have used the app and listened to all three dishes.
Honest low scores are more useful to us than polite high ones.

K-Menu Voice Guide 테스트에 참여해 주셔서 감사합니다. 설문은 약 5분 걸립니다.
앱을 사용하고 음식 세 개의 음성을 모두 들으신 뒤에 답해 주세요.
배려해서 높게 주신 점수보다 솔직한 낮은 점수가 저희에게 훨씬 도움이 됩니다.
```

총 **24문항, 7개 섹션**.

---

## Section 1 — About you / 참여자 정보

**1. Which participant number were you given?**
**배정받으신 참여자 번호는?**
`[Multiple choice 객관식 · required 필수]`
- P1
- P2
- P3

**2. Which language did you set the app to?**
**앱 언어를 무엇으로 설정하셨나요?**
`[Multiple choice 객관식 · required 필수]`
- English
- 한국어 (Korean)

**3. Have you ever been to South Korea?**
**한국에 가보신 적이 있나요?**
`[Multiple choice 객관식 · required 필수]`
- Yes / 예
- No / 아니오

**4. How familiar are you with Korean food?**
**한국 음식에 얼마나 익숙하신가요?**
`[Linear scale 선형 배율 1–5 · required 필수]`
- 1 = Not at all familiar / 전혀 모른다
- 5 = Very familiar / 매우 익숙하다

---

## Section 2 — Voice quality: Kalguksu / 음성 품질: 칼국수

> 도움말 (섹션 설명 칸에 넣기):
> These questions are about the audio you heard on the **Kalguksu** page.
> 5 = Excellent, 4 = Good, 3 = Fair, 2 = Poor, 1 = Bad.
>
> **칼국수** 화면에서 들으신 음성에 대한 질문입니다.
> 5 = 매우 좋음, 4 = 좋음, 3 = 보통, 2 = 나쁨, 1 = 매우 나쁨.

**5. How natural did the voice sound?**
**음성이 얼마나 자연스럽게 들렸나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

**6. How easy was it to understand every word?**
**모든 단어를 알아듣기가 얼마나 쉬웠나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

**7. How well did the voice pronounce the Korean dish name?**
**한국어 음식 이름 발음은 얼마나 잘 되었나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

---

## Section 3 — Voice quality: Agujjim / 음성 품질: 아귀찜

> 도움말: Same three questions, for the **Agujjim** audio.
> **아귀찜** 음성에 대한 같은 세 문항입니다.

**8. How natural did the voice sound?**
**음성이 얼마나 자연스럽게 들렸나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

**9. How easy was it to understand every word?**
**모든 단어를 알아듣기가 얼마나 쉬웠나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

**10. How well did the voice pronounce the Korean dish name?**
**한국어 음식 이름 발음은 얼마나 잘 되었나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

---

## Section 4 — Voice quality: Gamjajeon / 음성 품질: 감자전

> 도움말: Same three questions, for the **Gamjajeon** audio.
> **감자전** 음성에 대한 같은 세 문항입니다.

**11. How natural did the voice sound?**
**음성이 얼마나 자연스럽게 들렸나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

**12. How easy was it to understand every word?**
**모든 단어를 알아듣기가 얼마나 쉬웠나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

**13. How well did the voice pronounce the Korean dish name?**
**한국어 음식 이름 발음은 얼마나 잘 되었나요?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

---

## Section 5 — The voice overall / 음성 전반

**14. Taking all three clips together, how would you rate the voice quality?**
**세 음성을 통틀어, 음성 품질을 몇 점으로 평가하시겠습니까?**
`[Linear scale 1–5 · required]` — 1 = Bad 매우 나쁨, 5 = Excellent 매우 좋음

**15. Was there anything about the voice that stood out — good or bad?**
**음성에서 특별히 눈에 띈 점이 있었나요? (좋은 점이든 나쁜 점이든)**
`[Paragraph 장문형 · optional 선택]`

> 도움말: For example: a word it mispronounced, an odd pause, a part that sounded
> surprisingly human.
> 예를 들어 잘못 발음한 단어, 어색한 멈춤, 의외로 사람 같았던 부분 등.

---

## Section 6 — Using the app / 앱 사용 경험

> 도움말: 1 = Strongly disagree, 5 = Strongly agree.
> 1 = 전혀 그렇지 않다, 5 = 매우 그렇다.

**16. It was easy to figure out how to use the app without help.**
**도움 없이도 앱 사용법을 쉽게 파악할 수 있었다.**
`[Linear scale 1–5 · required]`

**17. Overall, I am satisfied with this app.**
**전반적으로 이 앱에 만족한다.**
`[Linear scale 1–5 · required]`

**18. The explanation helped me understand what the dish actually is.**
**설명을 듣고 그 음식이 어떤 음식인지 이해할 수 있었다.**
`[Linear scale 1–5 · required]`

**19. If I saw this dish on a real menu, the app gave me enough information to decide whether to order it.**
**실제 메뉴판에서 이 음식을 봤다면, 앱이 준 정보만으로 주문 여부를 결정할 수 있었을 것이다.**
`[Linear scale 1–5 · required]`

**20. The waiting time after uploading the photo was acceptable.**
**사진을 올린 뒤 기다린 시간은 견딜 만했다.**
`[Linear scale 1–5 · required]`

**21. I would use this app on a real trip to South Korea.**
**실제로 한국을 여행한다면 이 앱을 쓸 것 같다.**
`[Linear scale 1–5 · required]`

**22. The order screen — the list written in Korean that you show to staff — would be useful in a real restaurant.**
**주문 화면(직원에게 보여주는 한국어 주문 목록)은 실제 식당에서 쓸모 있을 것 같다.**
`[Linear scale 1–5 · required]`

---

## Section 7 — In your own words / 자유롭게

**23. What did you like most?**
**가장 마음에 든 점은 무엇인가요?**
`[Paragraph 장문형 · required 필수]`

**24. What was most confusing, frustrating, or missing?**
**가장 헷갈렸거나, 불편했거나, 아쉬웠던 점은 무엇인가요?**
`[Paragraph 장문형 · required 필수]`

> 도움말: Anything that went wrong, anything you expected and did not get, anything
> you had to guess at. This is the most useful question on the form.
> 잘못된 점, 기대했는데 없었던 것, 추측해서 넘어가야 했던 것 무엇이든.
> 이 설문에서 가장 도움이 되는 문항입니다.

---

## 폼 설정

- **이메일 주소 수집: 끄기** — 필요 없고, 켜면 관리해야 할 개인정보가 생깁니다.
- **응답 1회로 제한: 끄기** — 참여자가 로그인하지 않습니다.
- **진행률 표시줄: 켜기** — 7개 섹션이면 끝이 보여야 합니다.
- **질문 순서 섞기: 끄기** — 음식 순서가 고정되어야 하고, `analyze_results.py`가
  문항 순서에 의존합니다.
