# SCOUT Performance Report

- date: 2026-06-10
- evaluated candidates: 33 / 36
- actually bought: 0
- avg D20 return: None
- verdicts: {'FAILED_FAST': 6, 'WINNER': 4, 'WATCH': 5, 'PENDING': 18}

## Aggregates

### by_lane
- strength: n=27, avgD20=None, winner=0.111, failed_fast=0.222, bought=0
- pullback: n=3, avgD20=None, winner=0.333, failed_fast=0.0, bought=0
- left_side: n=3, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_lane_status
- STRONG_PASS: n=29, avgD20=None, winner=0.138, failed_fast=0.207, bought=0
- STAGE2_STRONG_PASS: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STAGE2_PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_theme_industry
- SUPPORT: n=27, avgD20=None, winner=0.148, failed_fast=0.148, bought=0
- STRONG_SUPPORT: n=4, avgD20=None, winner=0.0, failed_fast=0.5, bought=0
- NO_MAPPING: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=20, avgD20=None, winner=0.1, failed_fast=0.25, bought=0
- QUALITY_SUPPORT: n=10, avgD20=None, winner=0.2, failed_fast=0.1, bought=0
- NEUTRAL: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- not_checked: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_catalyst
- unknown: n=13, avgD20=None, winner=0.154, failed_fast=0.077, bought=0
- POSITIVE_REVALUATION: n=12, avgD20=None, winner=0.0, failed_fast=0.417, bought=0
- NOISE: n=8, avgD20=None, winner=0.25, failed_fast=0.0, bought=0

## LLM Override Comparison
- counts: dropped=3, added=4, kept=32
- avg D5: dropped=-1.29, added=1.41, kept=0.27
- avg D20: dropped=None, added=None, kept=None

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=None MFE=5.01 MAE=-15.06 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=None MFE=3.02 MAE=-12.91 lane=strength:STRONG_PASS
- 2026-06-04 AKAM PENDING D5=None D20=None MFE=1.2 MAE=-16.61 lane=strength:STRONG_PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=None MFE=8.63 MAE=-1.41 lane=strength:STRONG_PASS
- 2026-05-29 VMI WATCH D5=2.69 D20=None MFE=5.6 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=None MFE=2.6 MAE=-7.91 lane=strength:STRONG_PASS
- 2026-06-04 DAC PENDING D5=None D20=None MFE=0.95 MAE=-2.14 lane=strength:STRONG_PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=None MFE=0.27 MAE=-12.26 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=None MFE=16.04 MAE=-13.19 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=None MFE=8.63 MAE=-1.41 bought=False lane=strength catalyst=
- 2026-05-29 DTM WATCH D20=None MFE=2.73 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC WATCH D20=None MFE=4.63 MAE=-4.89 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WATCH D20=None MFE=5.6 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=None MFE=4.48 MAE=-9.97 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=None MFE=1.53 MAE=-8.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=None MFE=8.67 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=None MFE=13.37 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO WATCH D20=None MFE=5.04 MAE=-2.46 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=None MFE=2.6 MAE=-7.91 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL WATCH D20=None MFE=3.23 MAE=-1.25 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=None MFE=14.87 MAE=-9.79 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO WINNER D20=None MFE=10.32 MAE=-2.78 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS PENDING D20=None MFE=2.28 MAE=-19.03 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS PENDING D20=None MFE=4.49 MAE=-23.29 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA PENDING D20=None MFE=5.19 MAE=-1.66 bought=False lane=left_side catalyst=
- 2026-06-04 NVT PENDING D20=None MFE=1.21 MAE=-10.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO PENDING D20=None MFE=17.98 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC PENDING D20=None MFE=0.95 MAE=-2.14 bought=False lane=strength catalyst=
- 2026-06-05 IRM PENDING D20=None MFE=3.74 MAE=-1.82 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP PENDING D20=None MFE=2.35 MAE=-1.28 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW PENDING D20=None MFE=2.33 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX PENDING D20=None MFE=3.44 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO PENDING D20=None MFE=2.11 MAE=-4.59 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC PENDING D20=None MFE=6.14 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL PENDING D20=None MFE=2.41 MAE=-1.65 bought=False lane=strength catalyst=
- 2026-06-08 CALY PENDING D20=None MFE=3.01 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK PENDING D20=None MFE=3.2 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD PENDING D20=None MFE=3.52 MAE=-0.1 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH PENDING D20=None MFE=4.06 MAE=-0.43 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX PENDING D20=None MFE=1.34 MAE=-1.18 bought=False lane=strength catalyst=
- 2026-06-10 NGG PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=
