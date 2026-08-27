# SCOUT Performance Report

- date: 2026-08-27
- evaluated candidates: 135 / 135
- actually bought: 0
- avg D20 return: -3.44
- avg alpha: {'d5': 0.31, 'd10': -0.01, 'd20': 1.15}
- positive alpha rate: {'d5': 0.545, 'd10': 0.552, 'd20': 0.547}
- verdicts: {'FAILED_FAST': 77, 'WINNER': 49, 'NEUTRAL': 7, 'PENDING': 1, 'WATCH': 1}
- execution: first executable session open; no same-day close entry
- benchmark: stored lane benchmark, with country fallback

## Aggregates

### by_lane
- strength: n=62, avgD20=-4.32, avgAlphaD20=-1.01, winner=0.355, failed_fast=0.548, bought=0
- pullback: n=41, avgD20=-5.39, avgAlphaD20=1.13, winner=0.268, failed_fast=0.732, bought=0
- left_side: n=32, avgD20=1.68, avgAlphaD20=6.23, winner=0.5, failed_fast=0.406, bought=0

### by_lane_status
- STRONG_PASS: n=79, avgD20=-3.86, avgAlphaD20=0.05, winner=0.342, failed_fast=0.582, bought=0
- PASS: n=23, avgD20=-7.08, avgAlphaD20=0.1, winner=0.261, failed_fast=0.739, bought=0
- STAGE2_PASS: n=19, avgD20=3.7, avgAlphaD20=9.41, winner=0.421, failed_fast=0.526, bought=0
- STAGE2_STRONG_PASS: n=12, avgD20=-5.62, avgAlphaD20=-6.77, winner=0.667, failed_fast=0.167, bought=0
- WAIT_CONFIRM: n=1, avgD20=7.33, avgAlphaD20=23.92, winner=0.0, failed_fast=1.0, bought=0
- WAIT: n=1, avgD20=-21.01, avgAlphaD20=-20.96, winner=0.0, failed_fast=1.0, bought=0

### by_theme_industry
- SUPPORT: n=66, avgD20=0.74, avgAlphaD20=0.37, winner=0.515, failed_fast=0.364, bought=0
- NO_MAPPING: n=37, avgD20=-13.37, avgAlphaD20=4.0, winner=0.027, failed_fast=0.973, bought=0
- STRONG_SUPPORT: n=20, avgD20=-0.37, avgAlphaD20=-0.67, winner=0.4, failed_fast=0.6, bought=0
- SECTOR_UNSUPPORTED: n=10, avgD20=1.05, avgAlphaD20=-1.25, winner=0.5, failed_fast=0.5, bought=0
- SECTOR_NEUTRAL: n=2, avgD20=3.01, avgAlphaD20=1.11, winner=0.5, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=56, avgD20=1.96, avgAlphaD20=3.03, winner=0.446, failed_fast=0.446, bought=0
- QUALITY_SUPPORT: n=38, avgD20=-6.44, avgAlphaD20=-0.78, winner=0.342, failed_fast=0.658, bought=0
- not_checked: n=25, avgD20=-1.33, avgAlphaD20=1.51, winner=0.4, failed_fast=0.48, bought=0
- NEUTRAL: n=13, avgD20=-17.65, avgAlphaD20=-0.9, winner=0.077, failed_fast=0.923, bought=0
- DATA_LIGHT: n=3, avgD20=-12.63, avgAlphaD20=-0.5, winner=0.0, failed_fast=1.0, bought=0

### by_catalyst
- unknown: n=59, avgD20=-1.67, avgAlphaD20=1.82, winner=0.458, failed_fast=0.458, bought=0
- POSITIVE_REVALUATION: n=39, avgD20=-3.66, avgAlphaD20=-2.83, winner=0.333, failed_fast=0.564, bought=0
- NOISE: n=32, avgD20=-5.18, avgAlphaD20=2.95, winner=0.281, failed_fast=0.719, bought=0
- NO_DATA: n=5, avgD20=-9.49, avgAlphaD20=12.75, winner=0.0, failed_fast=1.0, bought=0

### by_market_regime
- BULL: n=60, avgD20=2.05, avgAlphaD20=2.2, winner=0.467, failed_fast=0.433, bought=0
- MIXED: n=49, avgD20=-2.68, avgAlphaD20=0.43, winner=0.429, failed_fast=0.51, bought=0
- POSITIVE: n=17, avgD20=-14.48, avgAlphaD20=2.61, winner=0.0, failed_fast=1.0, bought=0
- NEGATIVE: n=8, avgD20=-19.55, avgAlphaD20=-4.88, winner=0.0, failed_fast=1.0, bought=0
- BEAR: n=1, avgD20=-16.02, avgAlphaD20=4.41, winner=0.0, failed_fast=1.0, bought=0

## LLM Override Comparison
- counts: dropped=7, added=19, kept=116
- avg D5: dropped=-1.26, added=-1.81, kept=-0.52
- avg D20: dropped=-9.89, added=-4.38, kept=-3.28

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.32 D20=-15.31 MFE=4.75 MAE=-21.0 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-6.78 D20=4.83 MFE=5.02 MAE=-15.81 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-15.67 D20=-28.23 MFE=2.43 MAE=-30.71 lane=strength:STRONG_PASS
- 2026-06-13 MNST WINNER D5=0.49 D20=4.66 MFE=6.35 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB FAILED_FAST D5=7.13 D20=-24.86 MFE=17.36 MAE=-31.96 lane=strength:STRONG_PASS
- 2026-06-24 NUVL PENDING D5=None D20=None MFE=0.02 MAE=-0.01 lane=strength:STRONG_PASS
- 2026-06-27 DELL FAILED_FAST D5=5.96 D20=-0.44 MFE=17.69 MAE=-8.87 lane=pullback:PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.58 D20=0.94 MFE=9.06 MAE=-2.62 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=1.47 D20=8.99 MFE=11.33 MAE=-4.0 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.8 D20=-16.15 MFE=2.51 MAE=-17.2 lane=strength:STRONG_PASS
- 2026-06-04 DAC NEUTRAL D5=1.69 D20=-2.01 MFE=3.79 MAE=-6.18 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS FAILED_FAST D5=7.21 D20=-20.53 MFE=15.67 MAE=-22.34 lane=pullback:PASS
- 2026-06-12 036570.KS FAILED_FAST D5=4.33 D20=-6.4 MFE=6.4 MAE=-14.31 lane=pullback:STRONG_PASS
- 2026-06-13 KT FAILED_FAST D5=-4.66 D20=-7.02 MFE=1.77 MAE=-8.15 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM FAILED_FAST D5=-7.81 D20=1.61 MFE=19.37 MAE=-15.24 lane=strength:PASS
- 2026-06-16 005940.KS FAILED_FAST D5=-12.08 D20=-8.87 MFE=4.28 MAE=-18.65 lane=pullback:PASS
- 2026-06-17 017670.KS FAILED_FAST D5=-8.91 D20=-14.91 MFE=0.1 MAE=-17.72 lane=pullback:STRONG_PASS
- 2026-06-18 REGN WINNER D5=3.4 D20=9.82 MFE=12.92 MAE=-2.81 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT FAILED_FAST D5=-2.02 D20=-5.62 MFE=2.94 MAE=-8.3 lane=pullback:PASS
- 2026-06-20 012330.KS FAILED_FAST D5=-16.19 D20=-19.95 MFE=0.17 MAE=-24.54 lane=pullback:PASS
- 2026-06-24 AMGN WINNER D5=3.83 D20=6.75 MFE=8.78 MAE=-0.57 lane=pullback:PASS
- 2026-06-25 KT NEUTRAL D5=-2.1 D20=2.71 MFE=3.38 MAE=-5.2 lane=left_side:STAGE2_PASS
- 2026-06-27 003230.KS FAILED_FAST D5=-2.14 D20=5.44 MFE=11.05 MAE=-8.29 lane=left_side:STAGE2_PASS
- 2026-07-02 IBM FAILED_FAST D5=1.56 D20=-21.01 MFE=10.12 MAE=-29.65 lane=pullback:WAIT
- 2026-07-10 088350.KS FAILED_FAST D5=0.47 D20=7.33 MFE=11.29 MAE=-8.5 lane=left_side:WAIT_CONFIRM
- 2026-07-15 426030.KS FAILED_FAST D5=-4.29 D20=-4.32 MFE=0.03 MAE=-19.98 lane=pullback:PASS

## Outcome Memory Comparison
- evidence status: COLLECTING_UNTOUCHED_WINDOW
- counterfactual proven: False
- winner declared: False
- NONE: n=131/131, alpha={'d5': 0.1, 'd10': -0.43, 'd20': 1.15}, positiveAlpha={'d5': 0.531, 'd10': 0.538, 'd20': 0.547}
- SUPPORT: n=4/4, alpha={'d5': 6.87, 'd10': 13.52, 'd20': None}, positiveAlpha={'d5': 1.0, 'd10': 1.0, 'd20': None}

## Precision Shadow Comparison
- left_side_context_v1: n=36/36, avgD5=2.6, avgD10=8.59, avgD20=None, alphaD20=None
- pre_entry_v1: n=20/22, avgD5=-1.11, avgD10=None, avgD20=None, alphaD20=None
- us_precision_v1: n=51/51, avgD5=2.1, avgD10=3.56, avgD20=7.38, alphaD20=4.2

## Support Resistance Engine Comparison
- evidence status: COLLECTING_FORWARD_EVIDENCE
- winner declared: False
- atr_reversal_v1: resolved=28/79, target=21, stop=7, late=19, avgR=0.12
- confirmed_swings_v1: resolved=54/252, target=21, stop=33, late=16, avgR=-0.34
- prominence_reaction_v2: resolved=29/79, target=19, stop=10, late=17, avgR=0.1
- rolling_extrema_v1: resolved=3/79, target=2, stop=1, late=1, avgR=0.13

## Policy Comparison
- evidence status: COLLECTING_FORWARD_EVIDENCE
- winner declared: False
- reason: 정책별 동일 기간의 만기 초과수익 표본을 축적 중이며 자동 승자 선언은 하지 않음
- baseline:radar_top3_not_selected: n=234/237, alpha={'d5': 0.7, 'd10': 1.35, 'd20': 5.51}, positiveAlpha={'d5': 0.577, 'd10': 0.614, 'd20': 0.621}
- production:integrity_v1: n=6/6, alpha={'d5': 5.46, 'd10': 15.55, 'd20': None}, positiveAlpha={'d5': 1.0, 'd10': 1.0, 'd20': None}
- production:integrity_v1_unversioned: n=3/3, alpha={'d5': -2.24, 'd10': -3.0, 'd20': -4.17}, positiveAlpha={'d5': 0.333, 'd10': 0.333, 'd20': 0.333}
- production:legacy_recorded: n=126/126, alpha={'d5': 0.12, 'd10': -0.69, 'd20': 1.28}, positiveAlpha={'d5': 0.528, 'd10': 0.536, 'd20': 0.552}
- production_lane:integrity_v1:left_side: n=6/6, alpha={'d5': 5.46, 'd10': 15.55, 'd20': None}, positiveAlpha={'d5': 1.0, 'd10': 1.0, 'd20': None}
- production_lane:integrity_v1_unversioned:strength: n=3/3, alpha={'d5': -2.24, 'd10': -3.0, 'd20': -4.17}, positiveAlpha={'d5': 0.333, 'd10': 0.333, 'd20': 0.333}
- production_lane:legacy_recorded:left_side: n=26/26, alpha={'d5': 1.18, 'd10': 2.92, 'd20': 6.23}, positiveAlpha={'d5': 0.615, 'd10': 0.731, 'd20': 0.692}
- production_lane:legacy_recorded:pullback: n=41/41, alpha={'d5': -2.76, 'd10': -6.02, 'd20': 1.13}, positiveAlpha={'d5': 0.317, 'd10': 0.317, 'd20': 0.488}
- production_lane:legacy_recorded:strength: n=59/59, alpha={'d5': 1.69, 'd10': 1.46, 'd20': -0.84}, positiveAlpha={'d5': 0.638, 'd10': 0.603, 'd20': 0.534}
- production_lane_status:integrity_v1:left_side:STAGE2_STRONG_PASS: n=6/6, alpha={'d5': 5.46, 'd10': 15.55, 'd20': None}, positiveAlpha={'d5': 1.0, 'd10': 1.0, 'd20': None}
- production_lane_status:integrity_v1_unversioned:strength:STRONG_PASS: n=3/3, alpha={'d5': -2.24, 'd10': -3.0, 'd20': -4.17}, positiveAlpha={'d5': 0.333, 'd10': 0.333, 'd20': 0.333}
- production_lane_status:legacy_recorded:left_side:STAGE2_PASS: n=19/19, alpha={'d5': 2.19, 'd10': 4.57, 'd20': 9.41}, positiveAlpha={'d5': 0.632, 'd10': 0.737, 'd20': 0.789}
- production_lane_status:legacy_recorded:left_side:STAGE2_STRONG_PASS: n=6/6, alpha={'d5': -4.22, 'd10': -4.58, 'd20': -6.77}, positiveAlpha={'d5': 0.5, 'd10': 0.667, 'd20': 0.333}
- production_lane_status:legacy_recorded:left_side:WAIT_CONFIRM: n=1/1, alpha={'d5': 14.19, 'd10': 16.6, 'd20': 23.92}, positiveAlpha={'d5': 1.0, 'd10': 1.0, 'd20': 1.0}
- production_lane_status:legacy_recorded:pullback:PASS: n=20/20, alpha={'d5': -3.4, 'd10': -4.82, 'd20': 1.36}, positiveAlpha={'d5': 0.3, 'd10': 0.4, 'd20': 0.6}
- production_lane_status:legacy_recorded:pullback:STRONG_PASS: n=20/20, alpha={'d5': -2.3, 'd10': -6.3, 'd20': 2.02}, positiveAlpha={'d5': 0.3, 'd10': 0.25, 'd20': 0.4}
- production_lane_status:legacy_recorded:pullback:WAIT: n=1/1, alpha={'d5': 0.55, 'd10': -24.34, 'd20': -20.96}, positiveAlpha={'d5': 1.0, 'd10': 0.0, 'd20': 0.0}
- production_lane_status:legacy_recorded:strength:PASS: n=3/3, alpha={'d5': -7.82, 'd10': -2.89, 'd20': -8.27}, positiveAlpha={'d5': 0.333, 'd10': 0.333, 'd20': 0.333}
- production_lane_status:legacy_recorded:strength:STRONG_PASS: n=56/56, alpha={'d5': 2.2, 'd10': 1.7, 'd20': -0.44}, positiveAlpha={'d5': 0.655, 'd10': 0.618, 'd20': 0.545}
- shadow:left_side_context_v1: n=36/36, alpha={'d5': 2.09, 'd10': 7.76, 'd20': None}, positiveAlpha={'d5': 0.486, 'd10': 0.708, 'd20': None}
- shadow:pre_entry_v1: n=20/22, alpha={'d5': 0.26, 'd10': None, 'd20': None}, positiveAlpha={'d5': 0.625, 'd10': None, 'd20': None}
- shadow:us_precision_v1: n=51/51, alpha={'d5': 1.5, 'd10': 1.65, 'd20': 4.2}, positiveAlpha={'d5': 0.583, 'd10': 0.564, 'd20': 0.588}

## Decision And Abstention Audit
- snapshots: 79
- abstentions: {'MISSED_OPPORTUNITY': 25, 'DEGRADED_DATA': 2, 'PENDING': 5}
- D20 selected nonpositive alpha: 58
- D20 rejected positive alpha: 606
- avg D20 opportunity cost: 8.51
- avg D20 ex-post upper-bound gap: 26.12

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=-14.54 alphaD20=-11.71 MFE=0.91 MAE=-17.16 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=-13.33 alphaD20=-10.5 MFE=17.54 MAE=-13.61 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=0.94 alphaD20=3.77 MFE=9.06 MAE=-2.62 bought=False lane=strength catalyst=
- 2026-05-29 DTM NEUTRAL D20=3.54 alphaD20=5.51 MFE=6.43 MAE=-3.51 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC FAILED_FAST D20=-5.38 alphaD20=-3.41 MFE=4.1 MAE=-8.21 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WINNER D20=8.99 alphaD20=10.96 MFE=11.33 MAE=-4.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=9.26 alphaD20=10.4 MFE=9.95 MAE=-12.13 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=6.11 alphaD20=7.25 MFE=14.36 MAE=-11.66 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=22.3 alphaD20=23.44 MFE=22.72 MAE=-2.04 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=9.43 alphaD20=10.57 MFE=19.76 MAE=-1.86 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO FAILED_FAST D20=-1.93 alphaD20=-0.79 MFE=4.73 MAE=-10.14 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=-16.15 alphaD20=-15.01 MFE=2.51 MAE=-17.2 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL FAILED_FAST D20=-1.47 alphaD20=0.02 MFE=2.57 MAE=-9.93 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=-8.03 alphaD20=-6.54 MFE=19.11 MAE=-8.93 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO FAILED_FAST D20=3.97 alphaD20=5.46 MFE=11.92 MAE=-7.5 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=13.21 alphaD20=24.52 MFE=62.51 MAE=-20.19 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=-29.69 alphaD20=-18.38 MFE=9.81 MAE=-39.5 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA FAILED_FAST D20=-3.8 alphaD20=-2.04 MFE=9.58 MAE=-10.51 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=-8.98 alphaD20=-8.87 MFE=7.12 MAE=-13.07 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=0.14 alphaD20=0.25 MFE=25.65 MAE=-4.33 bought=False lane=strength catalyst=
- 2026-06-04 DAC NEUTRAL D20=-2.01 alphaD20=-1.9 MFE=3.79 MAE=-6.18 bought=False lane=strength catalyst=
- 2026-06-05 IRM FAILED_FAST D20=-10.3 alphaD20=-9.69 MFE=4.37 MAE=-11.15 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP WINNER D20=-0.88 alphaD20=-0.27 MFE=9.24 MAE=-2.19 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WINNER D20=5.25 alphaD20=5.86 MFE=7.93 MAE=-0.41 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=-0.5 alphaD20=-0.77 MFE=13.14 MAE=-2.7 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=8.31 alphaD20=8.04 MFE=8.54 MAE=-12.08 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=5.0 alphaD20=4.73 MFE=12.33 MAE=-5.81 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL FAILED_FAST D20=-0.89 alphaD20=-1.16 MFE=2.96 MAE=-9.58 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=21.28 alphaD20=21.01 MFE=29.93 MAE=-1.41 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=9.52 alphaD20=9.25 MFE=18.23 MAE=-2.58 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=-32.28 alphaD20=-33.37 MFE=2.5 MAE=-33.0 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH WINNER D20=24.5 alphaD20=23.41 MFE=25.55 MAE=-3.2 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX NEUTRAL D20=2.3 alphaD20=1.21 MFE=4.02 MAE=-3.23 bought=False lane=strength catalyst=
- 2026-06-10 NGG WINNER D20=2.48 alphaD20=-0.46 MFE=4.36 MAE=-2.27 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS FAILED_FAST D20=-11.8 alphaD20=-3.53 MFE=29.2 MAE=-14.85 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS FAILED_FAST D20=-18.66 alphaD20=-10.39 MFE=34.02 MAE=-21.05 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS FAILED_FAST D20=-20.53 alphaD20=-17.63 MFE=15.67 MAE=-22.34 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS FAILED_FAST D20=-8.28 alphaD20=-5.38 MFE=29.06 MAE=-14.29 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS FAILED_FAST D20=1.0 alphaD20=3.9 MFE=18.07 MAE=-10.84 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS FAILED_FAST D20=-27.95 alphaD20=-18.42 MFE=3.78 MAE=-31.73 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI FAILED_FAST D20=5.8 alphaD20=4.3 MFE=5.96 MAE=-9.85 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS FAILED_FAST D20=-6.4 alphaD20=3.13 MFE=6.4 MAE=-14.31 bought=False lane=pullback catalyst=
- 2026-06-13 KT FAILED_FAST D20=-7.02 alphaD20=-7.41 MFE=1.77 MAE=-8.15 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM FAILED_FAST D20=1.61 alphaD20=1.22 MFE=19.37 MAE=-15.24 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO FAILED_FAST D20=-8.8 alphaD20=-9.19 MFE=0.27 MAE=-10.07 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST WINNER D20=4.66 alphaD20=4.27 MFE=6.35 MAE=-2.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX NEUTRAL D20=4.83 alphaD20=4.44 MFE=4.98 MAE=-2.38 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR WINNER D20=4.27 alphaD20=3.88 MFE=9.62 MAE=-0.66 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS FAILED_FAST D20=15.67 alphaD20=36.82 MFE=28.96 MAE=-20.42 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS FAILED_FAST D20=-8.87 alphaD20=12.28 MFE=4.28 MAE=-18.65 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS FAILED_FAST D20=-22.26 alphaD20=-1.11 MFE=0.19 MAE=-27.04 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS FAILED_FAST D20=-19.08 alphaD20=-3.57 MFE=1.93 MAE=-25.24 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS FAILED_FAST D20=-11.32 alphaD20=4.19 MFE=11.09 MAE=-21.02 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS FAILED_FAST D20=-14.91 alphaD20=0.6 MFE=0.1 MAE=-17.72 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ FAILED_FAST D20=-26.55 alphaD20=-3.44 MFE=23.77 MAE=-37.58 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS FAILED_FAST D20=-23.68 alphaD20=-0.45 MFE=3.96 MAE=-25.88 bought=False lane=pullback catalyst=
- 2026-06-18 REGN WINNER D20=9.82 alphaD20=10.58 MFE=12.92 MAE=-2.81 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT FAILED_FAST D20=-5.62 alphaD20=-5.7 MFE=2.94 MAE=-8.3 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV WINNER D20=6.52 alphaD20=6.44 MFE=13.36 MAE=-0.54 bought=False lane=strength catalyst=
- 2026-06-19 TRGP WINNER D20=7.4 alphaD20=7.32 MFE=9.71 MAE=-1.87 bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ FAILED_FAST D20=0.21 alphaD20=21.53 MFE=44.76 MAE=-8.92 bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ FAILED_FAST D20=-35.98 alphaD20=-14.66 MFE=7.93 MAE=-39.94 bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS FAILED_FAST D20=-19.95 alphaD20=4.69 MFE=0.17 MAE=-24.54 bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS FAILED_FAST D20=-25.1 alphaD20=-0.46 MFE=4.21 MAE=-29.16 bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ FAILED_FAST D20=-22.55 alphaD20=-1.23 MFE=18.56 MAE=-36.23 bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS FAILED_FAST D20=-13.51 alphaD20=11.13 MFE=1.78 MAE=-18.13 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-23 080220.KQ FAILED_FAST D20=-43.74 alphaD20=-22.09 MFE=0.0 MAE=-47.79 bought=False lane=strength catalyst=NO_DATA
- 2026-06-23 TW FAILED_FAST D20=-0.52 alphaD20=-2.37 MFE=5.4 MAE=-8.0 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-23 001040.KS FAILED_FAST D20=-21.81 alphaD20=3.35 MFE=0.47 MAE=-25.67 bought=False lane=left_side catalyst=NOISE
- 2026-06-24 CPRX PENDING D20=None alphaD20=None MFE=0.08 MAE=0.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 GH WINNER D20=12.79 alphaD20=12.38 MFE=30.72 MAE=-0.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 AMGN WINNER D20=6.75 alphaD20=6.34 MFE=8.78 MAE=-0.57 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-25 KT NEUTRAL D20=2.71 alphaD20=2.71 MFE=3.38 MAE=-5.2 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-25 WMB NEUTRAL D20=-2.53 alphaD20=-2.53 MFE=4.06 MAE=-5.02 bought=False lane=strength catalyst=
- 2026-06-25 TRGP WINNER D20=5.55 alphaD20=5.55 MFE=9.2 MAE=-3.94 bought=False lane=strength catalyst=
- 2026-06-26 HEI WINNER D20=4.47 alphaD20=3.08 MFE=8.08 MAE=-2.08 bought=False lane=strength catalyst=
- 2026-06-26 PANW WINNER D20=7.51 alphaD20=6.12 MFE=24.95 MAE=-1.74 bought=False lane=strength catalyst=NOISE
- 2026-06-26 ROKU WINNER D20=6.19 alphaD20=4.8 MFE=8.3 MAE=-0.17 bought=False lane=strength catalyst=
- 2026-06-27 NU WINNER D20=10.71 alphaD20=10.12 MFE=11.95 MAE=-2.41 bought=False lane=left_side catalyst=
- 2026-06-27 APD WINNER D20=5.57 alphaD20=4.98 MFE=13.5 MAE=-2.63 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-27 003230.KS FAILED_FAST D20=5.44 alphaD20=33.68 MFE=11.05 MAE=-8.29 bought=False lane=left_side catalyst=NO_DATA
- 2026-06-29 AMD FAILED_FAST D20=-13.05 alphaD20=-13.64 MFE=11.84 MAE=-15.41 bought=False lane=strength catalyst=
- 2026-06-29 ASML FAILED_FAST D20=-12.01 alphaD20=-12.6 MFE=11.17 MAE=-13.64 bought=False lane=strength catalyst=
- 2026-06-29 FTNT WINNER D20=-1.95 alphaD20=-2.54 MFE=11.36 MAE=-4.48 bought=False lane=strength catalyst=NOISE
- 2026-06-30 TSM FAILED_FAST D20=-17.77 alphaD20=-16.17 MFE=5.13 MAE=-18.19 bought=False lane=strength catalyst=NOISE
- 2026-06-30 CRWD WINNER D20=-2.58 alphaD20=-0.98 MFE=18.13 MAE=-5.42 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-30 PENG FAILED_FAST D20=-35.68 alphaD20=-34.08 MFE=32.26 MAE=-35.81 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 009150.KS FAILED_FAST D20=-60.93 alphaD20=-26.04 MFE=1.87 MAE=-61.56 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 TIGO WINNER D20=6.51 alphaD20=6.95 MFE=12.76 MAE=-1.51 bought=False lane=strength catalyst=
- 2026-07-01 MRVL FAILED_FAST D20=-35.11 alphaD20=-34.67 MFE=3.55 MAE=-42.33 bought=False lane=strength catalyst=NOISE
- 2026-07-02 F WINNER D20=6.22 alphaD20=6.27 MFE=17.87 MAE=-4.34 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 IBM FAILED_FAST D20=-21.01 alphaD20=-20.96 MFE=10.12 MAE=-29.65 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 098460.KQ FAILED_FAST D20=-16.02 alphaD20=4.41 MFE=0.77 MAE=-34.98 bought=False lane=pullback catalyst=
- 2026-07-03 DDOG WINNER D20=9.53 alphaD20=8.34 MFE=11.6 MAE=-4.85 bought=False lane=strength catalyst=
- 2026-07-03 OKTA FAILED_FAST D20=-1.86 alphaD20=-3.05 MFE=8.83 MAE=-10.56 bought=False lane=strength catalyst=
- 2026-07-03 PANW FAILED_FAST D20=2.41 alphaD20=1.22 MFE=8.8 MAE=-8.97 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-04 001800.KS WINNER D20=0.4 alphaD20=22.73 MFE=10.87 MAE=-4.74 bought=False lane=pullback catalyst=
- 2026-07-04 A WINNER D20=7.53 alphaD20=6.34 MFE=9.55 MAE=-3.85 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-04 069960.KS FAILED_FAST D20=-33.71 alphaD20=-11.38 MFE=2.74 MAE=-38.75 bought=False lane=strength catalyst=NOISE
- 2026-07-06 003230.KS FAILED_FAST D20=8.55 alphaD20=30.88 MFE=17.72 MAE=-8.37 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 PUK WINNER D20=8.17 alphaD20=6.98 MFE=11.59 MAE=-2.38 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 029780.KS FAILED_FAST D20=-7.09 alphaD20=15.24 MFE=3.19 MAE=-7.98 bought=False lane=left_side catalyst=NOISE
- 2026-07-07 CPNG FAILED_FAST D20=-13.42 alphaD20=-16.23 MFE=0.77 MAE=-22.81 bought=False lane=left_side catalyst=
- 2026-07-07 F WINNER D20=3.56 alphaD20=0.75 MFE=18.47 MAE=-3.71 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-07 FLEX FAILED_FAST D20=-4.69 alphaD20=-7.5 MFE=9.38 MAE=-25.15 bought=False lane=pullback catalyst=
- 2026-07-08 EQT FAILED_FAST D20=-1.25 alphaD20=-4.83 MFE=5.65 MAE=-7.59 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-08 326030.KS FAILED_FAST D20=-1.76 alphaD20=13.75 MFE=1.53 MAE=-14.12 bought=False lane=left_side catalyst=NOISE
- 2026-07-08 000240.KS FAILED_FAST D20=0.57 alphaD20=16.08 MFE=1.33 MAE=-9.14 bought=False lane=pullback catalyst=
- 2026-07-09 XPO WINNER D20=-2.99 alphaD20=-5.83 MFE=8.94 MAE=-4.17 bought=False lane=pullback catalyst=
- 2026-07-09 A WINNER D20=9.4 alphaD20=6.56 MFE=10.24 MAE=-3.24 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-09 HPE WINNER D20=14.26 alphaD20=11.42 MFE=19.06 MAE=-5.63 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-10 AVGO FAILED_FAST D20=7.34 alphaD20=4.52 MFE=8.12 MAE=-10.21 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-10 EXE WINNER D20=4.73 alphaD20=1.91 MFE=7.74 MAE=-4.13 bought=False lane=left_side catalyst=NOISE
- 2026-07-10 088350.KS FAILED_FAST D20=7.33 alphaD20=23.92 MFE=11.29 MAE=-8.5 bought=False lane=left_side catalyst=NOISE
- 2026-07-11 INTU WINNER D20=20.0 alphaD20=17.27 MFE=20.9 MAE=-2.51 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-11 AMZN FAILED_FAST D20=13.65 alphaD20=10.92 MFE=17.38 MAE=-7.57 bought=False lane=pullback catalyst=NOISE
- 2026-07-11 FOX WINNER D20=14.54 alphaD20=11.81 MFE=16.27 MAE=-1.2 bought=False lane=left_side catalyst=
- 2026-07-13 FLEX FAILED_FAST D20=-9.66 alphaD20=-12.39 MFE=2.39 MAE=-24.91 bought=False lane=pullback catalyst=
- 2026-07-13 MRVL FAILED_FAST D20=-8.84 alphaD20=-11.57 MFE=1.41 MAE=-28.8 bought=False lane=pullback catalyst=NOISE
- 2026-07-13 204320.KS FAILED_FAST D20=9.4 alphaD20=23.79 MFE=12.03 MAE=-23.96 bought=False lane=left_side catalyst=NOISE
- 2026-07-14 XPO FAILED_FAST D20=-3.95 alphaD20=-6.57 MFE=4.12 MAE=-8.41 bought=False lane=pullback catalyst=
- 2026-07-14 AON NEUTRAL D20=-2.15 alphaD20=-4.77 MFE=4.95 MAE=-3.86 bought=False lane=left_side catalyst=
- 2026-07-14 FOXA WINNER D20=13.17 alphaD20=10.55 MFE=17.06 MAE=-0.93 bought=False lane=left_side catalyst=
- 2026-07-15 GOOG FAILED_FAST D20=-3.83 alphaD20=-6.25 MFE=7.25 MAE=-11.55 bought=False lane=pullback catalyst=
- 2026-07-15 HWM WINNER D20=1.07 alphaD20=-1.35 MFE=11.25 MAE=-4.63 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-15 426030.KS FAILED_FAST D20=-4.32 alphaD20=-4.57 MFE=0.03 MAE=-19.98 bought=False lane=pullback catalyst=
- 2026-07-29 SLGN FAILED_FAST D20=-4.7 alphaD20=-8.23 MFE=1.49 MAE=-11.67 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-29 KTB FAILED_FAST D20=-11.1 alphaD20=-14.63 MFE=1.19 MAE=-14.08 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-29 SNOW WINNER D20=13.89 alphaD20=10.36 MFE=23.49 MAE=0.0 bought=False lane=strength catalyst=
- 2026-08-04 ZS WINNER D20=None alphaD20=None MFE=24.17 MAE=-0.04 bought=False lane=left_side catalyst=
- 2026-08-10 GFI WINNER D20=None alphaD20=None MFE=21.59 MAE=-2.9 bought=False lane=left_side catalyst=
- 2026-08-10 EQX WINNER D20=None alphaD20=None MFE=22.43 MAE=-3.65 bought=False lane=left_side catalyst=
- 2026-08-11 CDE WINNER D20=None alphaD20=None MFE=21.08 MAE=-0.66 bought=False lane=left_side catalyst=
- 2026-08-12 CMCSA WINNER D20=None alphaD20=None MFE=7.09 MAE=-1.84 bought=False lane=left_side catalyst=
- 2026-08-12 RCI WATCH D20=None alphaD20=None MFE=5.63 MAE=-0.54 bought=False lane=left_side catalyst=
