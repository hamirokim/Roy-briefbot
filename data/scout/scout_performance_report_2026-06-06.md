# SCOUT Performance Report

- date: 2026-06-06
- evaluated candidates: 24 / 27
- actually bought: 0
- avg D20 return: None
- verdicts: {'FAILED_FAST': 2, 'WATCH': 4, 'PENDING': 18}

## Aggregates

### by_lane
- strength: n=20, avgD20=None, winner=0.0, failed_fast=0.1, bought=0
- pullback: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- left_side: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_lane_status
- STRONG_PASS: n=21, avgD20=None, winner=0.0, failed_fast=0.095, bought=0
- PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STAGE2_PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STAGE2_STRONG_PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_theme_industry
- SUPPORT: n=19, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STRONG_SUPPORT: n=3, avgD20=None, winner=0.0, failed_fast=0.667, bought=0
- NO_MAPPING: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=13, avgD20=None, winner=0.0, failed_fast=0.154, bought=0
- QUALITY_SUPPORT: n=9, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- NEUTRAL: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_catalyst
- POSITIVE_REVALUATION: n=10, avgD20=None, winner=0.0, failed_fast=0.2, bought=0
- unknown: n=8, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- NOISE: n=6, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

## LLM Override Comparison
- counts: dropped=3, added=4, kept=23
- avg D5: dropped=-1.29, added=3.47, kept=-2.32
- avg D20: dropped=None, added=None, kept=None

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=None MFE=5.01 MAE=-10.36 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=None MFE=3.02 MAE=-7.95 lane=strength:STRONG_PASS
- 2026-06-04 AKAM PENDING D5=None D20=None MFE=1.2 MAE=-7.04 lane=strength:STRONG_PASS

### Added by LLM
- 2026-05-28 ELV WATCH D5=4.25 D20=None MFE=6.06 MAE=-1.41 lane=strength:STRONG_PASS
- 2026-05-29 VMI WATCH D5=2.69 D20=None MFE=5.6 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST PENDING D5=None D20=None MFE=2.6 MAE=-2.47 lane=strength:STRONG_PASS
- 2026-06-04 DAC PENDING D5=None D20=None MFE=0.95 MAE=-1.57 lane=strength:STRONG_PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=None MFE=0.27 MAE=-10.3 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=None MFE=16.04 MAE=-9.61 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WATCH D20=None MFE=6.06 MAE=-1.41 bought=False lane=strength catalyst=
- 2026-05-29 DTM WATCH D20=None MFE=2.65 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC WATCH D20=None MFE=4.63 MAE=-3.37 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WATCH D20=None MFE=5.6 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG PENDING D20=None MFE=4.48 MAE=-4.83 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU PENDING D20=None MFE=1.53 MAE=-7.39 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX PENDING D20=None MFE=8.01 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC PENDING D20=None MFE=9.96 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO PENDING D20=None MFE=5.04 MAE=-1.02 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST PENDING D20=None MFE=2.6 MAE=-2.47 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL PENDING D20=None MFE=3.23 MAE=-1.04 bought=False lane=strength catalyst=
- 2026-06-02 STRL PENDING D20=None MFE=14.87 MAE=-4.3 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO PENDING D20=None MFE=3.23 MAE=-2.78 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS PENDING D20=None MFE=2.28 MAE=-9.99 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS PENDING D20=None MFE=4.49 MAE=-6.38 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA PENDING D20=None MFE=5.19 MAE=-1.66 bought=False lane=left_side catalyst=
- 2026-06-04 NVT PENDING D20=None MFE=1.21 MAE=-7.34 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO PENDING D20=None MFE=2.06 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC PENDING D20=None MFE=0.95 MAE=-1.57 bought=False lane=strength catalyst=
- 2026-06-05 IRM PENDING D20=None MFE=3.74 MAE=-0.39 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP PENDING D20=None MFE=0.97 MAE=-1.07 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW PENDING D20=None MFE=0.5 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
