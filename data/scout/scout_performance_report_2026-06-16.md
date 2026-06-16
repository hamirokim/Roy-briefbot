# SCOUT Performance Report

- date: 2026-06-16
- evaluated candidates: 51 / 51
- actually bought: 0
- avg D20 return: None
- verdicts: {'FAILED_FAST': 11, 'WINNER': 9, 'WATCH': 10, 'PENDING': 21}

## Aggregates

### by_lane
- strength: n=31, avgD20=None, winner=0.226, failed_fast=0.323, bought=0
- pullback: n=15, avgD20=None, winner=0.133, failed_fast=0.067, bought=0
- left_side: n=5, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_lane_status
- STRONG_PASS: n=42, avgD20=None, winner=0.214, failed_fast=0.238, bought=0
- PASS: n=4, avgD20=None, winner=0.0, failed_fast=0.25, bought=0
- STAGE2_STRONG_PASS: n=3, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STAGE2_PASS: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_theme_industry
- SUPPORT: n=33, avgD20=None, winner=0.273, failed_fast=0.212, bought=0
- NO_MAPPING: n=12, avgD20=None, winner=0.0, failed_fast=0.167, bought=0
- STRONG_SUPPORT: n=5, avgD20=None, winner=0.0, failed_fast=0.4, bought=0
- SECTOR_UNSUPPORTED: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=25, avgD20=None, winner=0.2, failed_fast=0.24, bought=0
- QUALITY_SUPPORT: n=14, avgD20=None, winner=0.286, failed_fast=0.214, bought=0
- not_checked: n=8, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- NEUTRAL: n=3, avgD20=None, winner=0.0, failed_fast=0.667, bought=0
- DATA_LIGHT: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_catalyst
- unknown: n=22, avgD20=None, winner=0.273, failed_fast=0.045, bought=0
- POSITIVE_REVALUATION: n=18, avgD20=None, winner=0.056, failed_fast=0.444, bought=0
- NOISE: n=10, avgD20=None, winner=0.2, failed_fast=0.2, bought=0
- NO_DATA: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

## LLM Override Comparison
- counts: dropped=4, added=9, kept=42
- avg D5: dropped=-6.42, added=1.08, kept=0.72
- avg D20: dropped=None, added=None, kept=None

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=None MFE=5.01 MAE=-15.06 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=None MFE=3.02 MAE=-13.46 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=None MFE=1.2 MAE=-19.81 lane=strength:STRONG_PASS
- 2026-06-13 MNST PENDING D5=None D20=None MFE=0.06 MAE=-1.91 lane=strength:STRONG_PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=None MFE=8.72 MAE=-1.41 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=2.69 D20=None MFE=7.44 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=None MFE=2.6 MAE=-11.86 lane=strength:STRONG_PASS
- 2026-06-04 DAC WATCH D5=0.09 D20=None MFE=2.16 MAE=-2.14 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS PENDING D5=None D20=None MFE=9.13 MAE=-5.73 lane=pullback:PASS
- 2026-06-12 036570.KS PENDING D5=None D20=None MFE=3.61 MAE=-2.66 lane=pullback:STRONG_PASS
- 2026-06-13 KT PENDING D5=None D20=None MFE=0.66 MAE=-1.11 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM PENDING D5=None D20=None MFE=6.27 MAE=-1.59 lane=strength:PASS
- 2026-06-16 005940.KS PENDING D5=None D20=None MFE=0.46 MAE=-0.61 lane=pullback:PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=None MFE=0.27 MAE=-14.75 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=None MFE=16.04 MAE=-13.19 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=None MFE=8.72 MAE=-1.41 bought=False lane=strength catalyst=
- 2026-05-29 DTM WATCH D20=None MFE=3.06 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC FAILED_FAST D20=None MFE=4.63 MAE=-7.74 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WINNER D20=None MFE=7.44 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=None MFE=4.48 MAE=-10.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=None MFE=15.38 MAE=-10.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=None MFE=11.4 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=None MFE=14.99 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO WATCH D20=None MFE=5.04 MAE=-5.72 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=None MFE=2.6 MAE=-11.86 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL WATCH D20=None MFE=3.23 MAE=-4.28 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=None MFE=14.87 MAE=-12.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO WINNER D20=None MFE=10.8 MAE=-2.78 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=None MFE=5.88 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=None MFE=4.49 MAE=-23.29 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WATCH D20=None MFE=5.19 MAE=-1.66 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=None MFE=1.21 MAE=-12.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=None MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC WATCH D20=None MFE=2.16 MAE=-2.14 bought=False lane=strength catalyst=
- 2026-06-05 IRM WATCH D20=None MFE=3.74 MAE=-1.82 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP WATCH D20=None MFE=2.73 MAE=-1.28 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WATCH D20=None MFE=3.83 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WATCH D20=None MFE=6.98 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=None MFE=2.11 MAE=-7.78 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=None MFE=9.52 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL WATCH D20=None MFE=2.66 MAE=-4.67 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=None MFE=13.94 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=None MFE=8.42 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD PENDING D20=None MFE=3.52 MAE=-22.13 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH PENDING D20=None MFE=8.0 MAE=-0.67 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX PENDING D20=None MFE=1.34 MAE=-2.8 bought=False lane=strength catalyst=
- 2026-06-10 NGG PENDING D20=None MFE=1.95 MAE=-0.01 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS PENDING D20=None MFE=11.81 MAE=-5.02 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS PENDING D20=None MFE=36.34 MAE=-5.9 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS PENDING D20=None MFE=9.13 MAE=-5.73 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS PENDING D20=None MFE=22.5 MAE=-7.4 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS PENDING D20=None MFE=5.19 MAE=-12.52 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS PENDING D20=None MFE=8.57 MAE=-0.49 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI PENDING D20=None MFE=0.57 MAE=-3.57 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS PENDING D20=None MFE=3.61 MAE=-2.66 bought=False lane=pullback catalyst=
- 2026-06-13 KT PENDING D20=None MFE=0.66 MAE=-1.11 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM PENDING D20=None MFE=6.27 MAE=-1.59 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO PENDING D20=None MFE=2.01 MAE=-0.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST PENDING D20=None MFE=0.06 MAE=-1.91 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX PENDING D20=None MFE=0.83 MAE=-0.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR PENDING D20=None MFE=1.48 MAE=-1.09 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS PENDING D20=None MFE=0.44 MAE=-0.18 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS PENDING D20=None MFE=0.46 MAE=-0.61 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS PENDING D20=None MFE=0.19 MAE=-0.39 bought=False lane=pullback catalyst=
