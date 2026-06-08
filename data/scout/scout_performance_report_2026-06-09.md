# SCOUT Performance Report

- date: 2026-06-09
- evaluated candidates: 30 / 33
- actually bought: 0
- avg D20 return: None
- verdicts: {'FAILED_FAST': 3, 'WATCH': 7, 'WINNER': 2, 'PENDING': 18}

## Aggregates

### by_lane
- strength: n=25, avgD20=None, winner=0.04, failed_fast=0.12, bought=0
- pullback: n=3, avgD20=None, winner=0.333, failed_fast=0.0, bought=0
- left_side: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_lane_status
- STRONG_PASS: n=27, avgD20=None, winner=0.074, failed_fast=0.111, bought=0
- PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STAGE2_PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STAGE2_STRONG_PASS: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_theme_industry
- SUPPORT: n=24, avgD20=None, winner=0.083, failed_fast=0.042, bought=0
- STRONG_SUPPORT: n=4, avgD20=None, winner=0.0, failed_fast=0.5, bought=0
- NO_MAPPING: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=19, avgD20=None, winner=0.053, failed_fast=0.158, bought=0
- QUALITY_SUPPORT: n=9, avgD20=None, winner=0.111, failed_fast=0.0, bought=0
- NEUTRAL: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_catalyst
- unknown: n=12, avgD20=None, winner=0.083, failed_fast=0.0, bought=0
- POSITIVE_REVALUATION: n=11, avgD20=None, winner=0.0, failed_fast=0.273, bought=0
- NOISE: n=7, avgD20=None, winner=0.143, failed_fast=0.0, bought=0

## LLM Override Comparison
- counts: dropped=3, added=4, kept=29
- avg D5: dropped=-1.29, added=1.41, kept=-0.18
- avg D20: dropped=None, added=None, kept=None

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=None MFE=5.01 MAE=-10.36 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=None MFE=3.02 MAE=-7.95 lane=strength:STRONG_PASS
- 2026-06-04 AKAM PENDING D5=None D20=None MFE=1.2 MAE=-11.13 lane=strength:STRONG_PASS

### Added by LLM
- 2026-05-28 ELV WATCH D5=4.25 D20=None MFE=7.19 MAE=-1.41 lane=strength:STRONG_PASS
- 2026-05-29 VMI WATCH D5=2.69 D20=None MFE=5.6 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST WATCH D5=-2.71 D20=None MFE=2.6 MAE=-3.74 lane=strength:STRONG_PASS
- 2026-06-04 DAC PENDING D5=None D20=None MFE=0.95 MAE=-1.65 lane=strength:STRONG_PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=None MFE=0.27 MAE=-11.17 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=None MFE=16.04 MAE=-9.61 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WATCH D20=None MFE=7.19 MAE=-1.41 bought=False lane=strength catalyst=
- 2026-05-29 DTM WATCH D20=None MFE=2.71 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC WATCH D20=None MFE=4.63 MAE=-3.37 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WATCH D20=None MFE=5.6 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG WATCH D20=None MFE=4.48 MAE=-4.83 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=None MFE=1.53 MAE=-7.39 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=None MFE=8.01 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=None MFE=9.96 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO WATCH D20=None MFE=5.04 MAE=-1.02 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST WATCH D20=None MFE=2.6 MAE=-3.74 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL PENDING D20=None MFE=3.23 MAE=-1.04 bought=False lane=strength catalyst=
- 2026-06-02 STRL PENDING D20=None MFE=14.87 MAE=-4.3 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO PENDING D20=None MFE=5.9 MAE=-2.78 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS PENDING D20=None MFE=2.28 MAE=-19.03 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS PENDING D20=None MFE=4.49 MAE=-15.72 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA PENDING D20=None MFE=5.19 MAE=-1.66 bought=False lane=left_side catalyst=
- 2026-06-04 NVT PENDING D20=None MFE=1.21 MAE=-7.34 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO PENDING D20=None MFE=2.06 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC PENDING D20=None MFE=0.95 MAE=-1.65 bought=False lane=strength catalyst=
- 2026-06-05 IRM PENDING D20=None MFE=3.74 MAE=-1.06 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP PENDING D20=None MFE=1.14 MAE=-1.28 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW PENDING D20=None MFE=0.7 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX PENDING D20=None MFE=1.49 MAE=-1.33 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO PENDING D20=None MFE=2.07 MAE=-1.05 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC PENDING D20=None MFE=3.73 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL PENDING D20=None MFE=0.8 MAE=-0.76 bought=False lane=strength catalyst=
- 2026-06-08 CALY PENDING D20=None MFE=0.96 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK PENDING D20=None MFE=1.08 MAE=-0.91 bought=False lane=strength catalyst=
- 2026-06-09 AD PENDING D20=None MFE=None MAE=None bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
