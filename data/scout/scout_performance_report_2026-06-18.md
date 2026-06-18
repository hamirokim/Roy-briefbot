# SCOUT Performance Report

- date: 2026-06-18
- evaluated candidates: 54 / 57
- actually bought: 0
- avg D20 return: None
- verdicts: {'FAILED_FAST': 14, 'WINNER': 13, 'WATCH': 9, 'PENDING': 18}

## Aggregates

### by_lane
- strength: n=32, avgD20=None, winner=0.281, failed_fast=0.375, bought=0
- pullback: n=17, avgD20=None, winner=0.235, failed_fast=0.059, bought=0
- left_side: n=5, avgD20=None, winner=0.0, failed_fast=0.2, bought=0

### by_lane_status
- STRONG_PASS: n=45, avgD20=None, winner=0.289, failed_fast=0.267, bought=0
- PASS: n=4, avgD20=None, winner=0.0, failed_fast=0.25, bought=0
- STAGE2_STRONG_PASS: n=3, avgD20=None, winner=0.0, failed_fast=0.333, bought=0
- STAGE2_PASS: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_theme_industry
- SUPPORT: n=33, avgD20=None, winner=0.303, failed_fast=0.303, bought=0
- NO_MAPPING: n=15, avgD20=None, winner=0.133, failed_fast=0.133, bought=0
- STRONG_SUPPORT: n=5, avgD20=None, winner=0.2, failed_fast=0.4, bought=0
- SECTOR_UNSUPPORTED: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=25, avgD20=None, winner=0.32, failed_fast=0.28, bought=0
- QUALITY_SUPPORT: n=14, avgD20=None, winner=0.214, failed_fast=0.357, bought=0
- not_checked: n=8, avgD20=None, winner=0.25, failed_fast=0.0, bought=0
- NEUTRAL: n=5, avgD20=None, winner=0.0, failed_fast=0.4, bought=0
- DATA_LIGHT: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_catalyst
- unknown: n=23, avgD20=None, winner=0.391, failed_fast=0.043, bought=0
- POSITIVE_REVALUATION: n=18, avgD20=None, winner=0.111, failed_fast=0.5, bought=0
- NOISE: n=11, avgD20=None, winner=0.182, failed_fast=0.364, bought=0
- NO_DATA: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

## LLM Override Comparison
- counts: dropped=4, added=11, kept=46
- avg D5: dropped=-6.42, added=1.08, kept=1.16
- avg D20: dropped=None, added=None, kept=None

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=None MFE=5.01 MAE=-17.73 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=None MFE=3.02 MAE=-13.46 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=None MFE=1.2 MAE=-19.81 lane=strength:STRONG_PASS
- 2026-06-13 MNST PENDING D5=None D20=None MFE=0.74 MAE=-1.91 lane=strength:STRONG_PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=None MFE=8.72 MAE=-1.41 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=2.69 D20=None MFE=10.77 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=None MFE=2.6 MAE=-11.86 lane=strength:STRONG_PASS
- 2026-06-04 DAC WATCH D5=0.09 D20=None MFE=2.16 MAE=-4.29 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS PENDING D5=None D20=None MFE=14.24 MAE=-5.73 lane=pullback:PASS
- 2026-06-12 036570.KS PENDING D5=None D20=None MFE=3.61 MAE=-2.66 lane=pullback:STRONG_PASS
- 2026-06-13 KT PENDING D5=None D20=None MFE=0.74 MAE=-3.24 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM PENDING D5=None D20=None MFE=6.28 MAE=-7.09 lane=strength:PASS
- 2026-06-16 005940.KS PENDING D5=None D20=None MFE=2.28 MAE=-2.13 lane=pullback:PASS
- 2026-06-17 017670.KS PENDING D5=None D20=None MFE=1.01 MAE=-0.51 lane=pullback:STRONG_PASS
- 2026-06-18 REGN PENDING D5=None D20=None MFE=None MAE=None lane=left_side:STAGE2_PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=None MFE=0.27 MAE=-14.75 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=None MFE=16.04 MAE=-13.19 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=None MFE=8.72 MAE=-1.41 bought=False lane=strength catalyst=
- 2026-05-29 DTM WATCH D20=None MFE=3.06 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC FAILED_FAST D20=None MFE=4.63 MAE=-7.74 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WINNER D20=None MFE=10.77 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=None MFE=4.48 MAE=-10.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=None MFE=15.38 MAE=-10.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=None MFE=13.43 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=None MFE=14.99 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO FAILED_FAST D20=None MFE=5.04 MAE=-7.68 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=None MFE=2.6 MAE=-11.86 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL WINNER D20=None MFE=3.91 MAE=-4.28 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=None MFE=14.87 MAE=-12.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO FAILED_FAST D20=None MFE=10.8 MAE=-8.42 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=None MFE=18.44 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=None MFE=4.49 MAE=-23.29 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WATCH D20=None MFE=5.19 MAE=-4.12 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=None MFE=1.21 MAE=-12.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=None MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC WATCH D20=None MFE=2.16 MAE=-4.29 bought=False lane=strength catalyst=
- 2026-06-05 IRM WATCH D20=None MFE=4.85 MAE=-1.82 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP WATCH D20=None MFE=2.73 MAE=-3.39 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WATCH D20=None MFE=3.83 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=None MFE=8.7 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=None MFE=2.11 MAE=-9.7 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=None MFE=9.52 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL WATCH D20=None MFE=3.49 MAE=-4.67 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=None MFE=13.94 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=None MFE=9.16 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=None MFE=3.52 MAE=-23.45 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH WINNER D20=None MFE=8.38 MAE=-0.67 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX WATCH D20=None MFE=3.06 MAE=-2.8 bought=False lane=strength catalyst=
- 2026-06-10 NGG WATCH D20=None MFE=3.18 MAE=-0.01 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS WINNER D20=None MFE=32.71 MAE=-5.02 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS WINNER D20=None MFE=36.34 MAE=-5.9 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS PENDING D20=None MFE=14.24 MAE=-5.73 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS PENDING D20=None MFE=22.5 MAE=-7.4 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS PENDING D20=None MFE=5.19 MAE=-12.52 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS PENDING D20=None MFE=8.57 MAE=-0.49 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI PENDING D20=None MFE=0.57 MAE=-6.29 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS PENDING D20=None MFE=3.61 MAE=-2.66 bought=False lane=pullback catalyst=
- 2026-06-13 KT PENDING D20=None MFE=0.74 MAE=-3.24 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM PENDING D20=None MFE=6.28 MAE=-7.09 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO PENDING D20=None MFE=2.01 MAE=-2.69 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST PENDING D20=None MFE=0.74 MAE=-1.91 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX PENDING D20=None MFE=4.37 MAE=-0.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR PENDING D20=None MFE=5.33 MAE=-1.13 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS PENDING D20=None MFE=1.49 MAE=-3.94 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS PENDING D20=None MFE=2.28 MAE=-2.13 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS PENDING D20=None MFE=1.78 MAE=-3.56 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS PENDING D20=None MFE=1.32 MAE=-2.4 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS PENDING D20=None MFE=0.0 MAE=-4.64 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS PENDING D20=None MFE=1.01 MAE=-0.51 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=
- 2026-06-18 REGN PENDING D20=None MFE=None MAE=None bought=False lane=left_side catalyst=NOISE
