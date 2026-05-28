# SCOUT Top3 LLM Review Design

Date: 2026-05-28

## Verdict

LLM 보조 심사는 바로 전체 93개 관찰풀에 걸지 않는다. 규칙 기반 Top3 엔진이 만든 상위 후보 8~12개만 LLM에 넘겨 최종 Top3를 재검토하는 방식이 비용, 안정성, 설명력의 균형이 가장 좋다.

## Why Not 93 Candidates

93개 전체를 넣으면 다음 문제가 생긴다.

- 비용과 지연이 매일 누적된다.
- 입력 길이가 길어져 LLM이 핵심 후보의 과열, 레인 균형, 촉매 품질을 놓칠 수 있다.
- 모든 후보를 다시 심사하면 규칙 기반 감사관의 역할이 흐려진다.
- 후보가 많을수록 출력 일관성이 떨어져 사후 성과표와 원인 분석이 어려워진다.

LLM은 “발굴기”가 아니라 “최종 심사관”으로 쓰는 편이 맞다.

## Recommended Scope

LLM 입력 범위:

1. Top3 규칙 엔진 선발 후보 3개
2. 규칙 엔진 기준 차순위 WATCHLIST 5개
3. 각 레인별 최고점 후보 1개씩, 이미 포함된 종목 제외
4. RISK_CATALYST 리뷰풀은 개수와 대표 2개만 요약 제공, Top3 후보 입력에서는 제외

실제 입력 후보 수는 보통 8~12개로 제한한다. 상한은 12개가 적당하다.

## LLM Inputs

후보별 필수 입력:

- ticker, name, country, sector, market_cap
- selection_tier, primary_lane, primary_lane_status, lane_rank
- opportunity_score
- price metrics: drawdown_from_high, ret_20d, ret_5d, volume_ratio_5d_20d, ATR%
- catalyst: classification, freshness, price_volume_reaction, headline summary
- theme/industry: status, sector RRG, theme group support, peer confirmation
- quality: auditor status, source, score, major flags
- risk flags: overextended_20d, near_52w_high, low_liquidity_buffer, risk catalyst

시장 맥락 필수 입력:

- VIX regime
- USD/KRW pressure
- sector RRG summary
- theme RRG summary
- SCOUT pool counts by tier/lane

## Decision Prompt Principles

LLM은 다음 순서로 판단한다.

1. RISK_CATALYST는 Top3 불가, 리뷰풀
2. 과열 추격 후보는 촉매와 거래량 반응이 둘 다 강하지 않으면 감점
3. 강세 후보만 3개 채우지 말고, 품질이 비슷하면 강세/눌림/좌측거래 균형을 본다
4. 촉매가 신선하더라도 섹터/테마와 가격 반응이 충돌하면 감점
5. 레인 PASS 자체보다 “지금 관찰 가치가 있는 자리인가”를 우선한다
6. 최종 Top3와 함께 탈락 후보의 탈락 이유를 반드시 남긴다

## 93 Candidates: Loose Gate Or Healthy Radar Pool?

93개가 통과됐다는 사실만으로 공통 문지기와 레인 기준이 느슨하다고 보긴 어렵다. 현재 구조에서 93개는 “매수 후보 93개”가 아니라 “감사관 판정이 붙은 관찰 가능 표본 93개”다.

### Tighten Common Gate / Lane Criteria

장점:

- 브리핑 전 후보 수가 줄어 로그와 시트가 단순해진다.
- 품질 낮은 관찰 표본이 줄어든다.
- API 비용이 낮아질 수 있다.

단점:

- 좌측거래와 초기 눌림 후보를 너무 일찍 버릴 수 있다.
- 사후 성과표 학습 데이터가 부족해진다.
- 기준을 빨리 빡빡하게 만들면 “좋은데 아직 덜 예쁜 후보”를 놓칠 가능성이 크다.

### Keep Radar Pool Broad, Tighten Top3

장점:

- 넓은 후보군을 사후 성과표로 검증할 수 있다.
- 레인/촉매/품질 공식의 개선 데이터가 쌓인다.
- Top3는 엄격하게, WATCHLIST는 학습용으로 분리할 수 있다.

단점:

- 관찰풀 자체가 커서 운영자가 혼란스러울 수 있다.
- 로그와 스냅샷 파일이 커진다.
- Top3 심사가 약하면 넓은 풀의 노이즈가 브리핑까지 올라온다.

## Recommendation

현재 단계에서는 공통 문지기와 레인 기준을 더 빡빡하게 만들지 않는다. 대신 Top3 선발 단계를 더 엄격하게 한다.

이유:

- 아직 사후 성과표 표본이 부족하다.
- 새 감사관 8개가 막 구현된 상태라 어떤 조건이 실제 수익 후보를 잘 설명하는지 데이터가 없다.
- 관찰풀은 넓게 유지해야 “진입 당시 조건 → 이후 결과” 쌍이 쌓인다.
- 로이가 실제로 보는 브리핑 Top3와 WATCHLIST만 엄격히 다루면 운영 부담은 통제된다.

운영 기준:

- Radar Pool: 최대 100개 유지
- WATCHLIST: 5개 유지
- LLM Review Input: 8~12개
- Telegram Top3: 최대 3개
- RISK_CATALYST: Top3 불가, 리뷰풀

## When To Tighten Gates Later

다음 조건이 4주 이상 반복되면 공통 문지기/레인 기준을 재조정한다.

- WATCHLIST 20거래일 성과가 계속 시장 대비 음수
- 특정 레인에서 FALSE_POSITIVE 비율이 50% 이상
- Tier A가 매일 20개 이상 나오는데 WINNER 비율이 낮음
- 과열 플래그 후보가 Top3에 자주 들어가고 성과가 나쁨

이때 조정 대상은 공통 문지기가 아니라 먼저 레인별 보정이다.

- 강세 레인: overextended_20d 감점 강화
- 눌림 레인: volume dry-up + support near 동시 요구 강화
- 좌측거래 레인: Stage2 PASS 조건 유지, WAIT 후보는 Top3 금지

