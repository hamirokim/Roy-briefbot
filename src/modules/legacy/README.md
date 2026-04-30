# Legacy Modules — 폐기 박제 (Z3-4)

## 박제 (D82~D85)

이 폴더의 모든 파일은 **호출 0건 죽은 코드**입니다. 운영 영향 0이지만 코드 정합성을 위해 `src/modules/` 루트에서 격리.

| 파일 | 폐기 사유 | 박제 D# | 흡수 위치 |
|---|---|---|---|
| `m3_contrarian.py` | Z1 v3.0 LangGraph 재설계 시 SCOUT 5신호 시스템에 흡수. 옛 코드 방치 | **D82** | `src/agents/scout.py` |
| `m4_tracker.py` | GUARD 에이전트가 직접 보유 종목 모니터 흡수 | **D83** | `src/agents/guard.py` |
| `m5_risk.py` | REGIME 에이전트가 VIX/매크로 리스크 직접 처리 | **D84** | `src/agents/regime.py` |
| `m1_briefing.py` | REGIME 에이전트가 매크로/환율/일정 직접 처리 | **D85** | `src/agents/regime.py` |

## 발견 경위 (Z3-4)

`m1_5_buyquestions.py` 통합 검증 중 grep으로 호출 위치 검색 → **8개 모듈 중 6개 죽은 코드 발견**:
- m1_5 (살림: Z3-4 SCOUT 통합)
- m6 (재설계: SCOUT 추적용 D86)
- m1/m3/m4/m5 (4개 = 이 폴더)

## 살아있는 모듈 (4개)

```
src/modules/
├── m1_5_buyquestions.py   # SCOUT 후보 LLM 풀 분석 (D81)
├── m2_rotation.py         # RRG 섹터 분면 (REGIME 호출)
├── m6_feedback.py         # SCOUT 추적 (DIGEST 호출, D86)
├── m7_correlation.py      # 보유 상관 (GUARD 호출)
└── legacy/                # 이 폴더
```

## 복구 (필요 시)

만약 m6의 옛 디자인이 필요하면 `legacy/m4_tracker.py` 또는 다른 파일에서 패턴 참고. 단 호출 추가 = SCOUT/agents와 충돌 가능성 → 신중.

## SSOT v4.6 정합

§20 죽은 코드 감사 박제 + D82~D85 박제. v4.7+ 갱신 시 이 폴더 동기화 필수.

---
**작성**: Z3-4, 2026-04-30  
**원칙**: D74 (1년 견고함) + D89 (코드 read 우선)
