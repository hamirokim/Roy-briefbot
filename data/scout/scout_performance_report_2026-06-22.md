# SCOUT Performance Report

- date: 2026-06-22
- evaluated candidates: 57 / 66
- actually bought: 0
- avg D20 return: None
- verdicts: {'FAILED_FAST': 16, 'WINNER': 15, 'WATCH': 10, 'PENDING': 16}

## Aggregates

### by_lane
- strength: n=33, avgD20=None, winner=0.273, failed_fast=0.364, bought=0
- pullback: n=18, avgD20=None, winner=0.333, failed_fast=0.167, bought=0
- left_side: n=6, avgD20=None, winner=0.0, failed_fast=0.167, bought=0

### by_lane_status
- STRONG_PASS: n=47, avgD20=None, winner=0.298, failed_fast=0.298, bought=0
- PASS: n=4, avgD20=None, winner=0.25, failed_fast=0.25, bought=0
- STAGE2_PASS: n=3, avgD20=None, winner=0.0, failed_fast=0.0, bought=0
- STAGE2_STRONG_PASS: n=3, avgD20=None, winner=0.0, failed_fast=0.333, bought=0

### by_theme_industry
- SUPPORT: n=33, avgD20=None, winner=0.303, failed_fast=0.303, bought=0
- NO_MAPPING: n=17, avgD20=None, winner=0.235, failed_fast=0.235, bought=0
- STRONG_SUPPORT: n=6, avgD20=None, winner=0.167, failed_fast=0.333, bought=0
- SECTOR_UNSUPPORTED: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=26, avgD20=None, winner=0.308, failed_fast=0.269, bought=0
- QUALITY_SUPPORT: n=14, avgD20=None, winner=0.357, failed_fast=0.357, bought=0
- not_checked: n=8, avgD20=None, winner=0.25, failed_fast=0.25, bought=0
- NEUTRAL: n=7, avgD20=None, winner=0.0, failed_fast=0.286, bought=0
- DATA_LIGHT: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_catalyst
- unknown: n=24, avgD20=None, winner=0.375, failed_fast=0.125, bought=0
- POSITIVE_REVALUATION: n=18, avgD20=None, winner=0.167, failed_fast=0.5, bought=0
- NOISE: n=13, avgD20=None, winner=0.231, failed_fast=0.308, bought=0
- NO_DATA: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

## LLM Override Comparison
- counts: dropped=5, added=13, kept=53
- avg D5: dropped=-6.42, added=2.59, kept=1.04
- avg D20: dropped=None, added=None, kept=None

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=None MFE=5.01 MAE=-17.73 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=None MFE=3.02 MAE=-13.46 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=None MFE=1.2 MAE=-22.78 lane=strength:STRONG_PASS
- 2026-06-13 MNST PENDING D5=None D20=None MFE=0.74 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB PENDING D5=None D20=None MFE=None MAE=None lane=strength:STRONG_PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=None MFE=8.72 MAE=-1.44 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=2.69 D20=None MFE=11.54 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=None MFE=2.6 MAE=-13.18 lane=strength:STRONG_PASS
- 2026-06-04 DAC WATCH D5=0.09 D20=None MFE=2.16 MAE=-4.42 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS WINNER D5=5.88 D20=None MFE=14.24 MAE=-5.73 lane=pullback:PASS
- 2026-06-12 036570.KS WATCH D5=5.32 D20=None MFE=7.41 MAE=-2.66 lane=pullback:STRONG_PASS
- 2026-06-13 KT PENDING D5=None D20=None MFE=0.74 MAE=-3.93 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM PENDING D5=None D20=None MFE=6.28 MAE=-7.09 lane=strength:PASS
- 2026-06-16 005940.KS PENDING D5=None D20=None MFE=2.28 MAE=-7.15 lane=pullback:PASS
- 2026-06-17 017670.KS PENDING D5=None D20=None MFE=1.01 MAE=-7.37 lane=pullback:STRONG_PASS
- 2026-06-18 REGN PENDING D5=None D20=None MFE=1.03 MAE=-1.93 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT PENDING D5=None D20=None MFE=None MAE=None lane=pullback:PASS
- 2026-06-20 012330.KS PENDING D5=None D20=None MFE=None MAE=None lane=pullback:PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=None MFE=0.27 MAE=-14.75 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=None MFE=16.04 MAE=-13.19 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=None MFE=8.72 MAE=-1.44 bought=False lane=strength catalyst=
- 2026-05-29 DTM WATCH D20=None MFE=3.06 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC FAILED_FAST D20=None MFE=4.63 MAE=-7.74 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WINNER D20=None MFE=11.54 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=None MFE=4.48 MAE=-10.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=None MFE=15.38 MAE=-10.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=None MFE=15.12 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=None MFE=14.99 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO FAILED_FAST D20=None MFE=5.04 MAE=-9.83 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=None MFE=2.6 MAE=-13.18 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL WINNER D20=None MFE=3.91 MAE=-4.28 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=None MFE=14.87 MAE=-12.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO FAILED_FAST D20=None MFE=10.8 MAE=-8.42 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=None MFE=38.94 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=None MFE=4.49 MAE=-25.89 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WATCH D20=None MFE=5.19 MAE=-4.85 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=None MFE=2.96 MAE=-12.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=None MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC WATCH D20=None MFE=2.16 MAE=-4.42 bought=False lane=strength catalyst=
- 2026-06-05 IRM WATCH D20=None MFE=4.85 MAE=-1.82 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP WATCH D20=None MFE=2.73 MAE=-3.4 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WATCH D20=None MFE=5.03 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=None MFE=8.7 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=None MFE=2.11 MAE=-11.8 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=None MFE=9.52 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL WATCH D20=None MFE=3.49 MAE=-4.67 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=None MFE=18.35 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=None MFE=11.19 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=None MFE=3.52 MAE=-24.39 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH WINNER D20=None MFE=13.86 MAE=-0.67 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX WATCH D20=None MFE=4.11 MAE=-2.8 bought=False lane=strength catalyst=
- 2026-06-10 NGG WATCH D20=None MFE=3.18 MAE=-2.02 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS WINNER D20=None MFE=32.71 MAE=-5.02 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS WINNER D20=None MFE=36.34 MAE=-5.9 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS WINNER D20=None MFE=14.24 MAE=-5.73 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS FAILED_FAST D20=None MFE=22.5 MAE=-7.4 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS FAILED_FAST D20=None MFE=5.19 MAE=-12.52 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS WINNER D20=None MFE=8.57 MAE=-2.8 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI PENDING D20=None MFE=0.57 MAE=-9.79 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS WATCH D20=None MFE=7.41 MAE=-2.66 bought=False lane=pullback catalyst=
- 2026-06-13 KT PENDING D20=None MFE=0.74 MAE=-3.93 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM PENDING D20=None MFE=6.28 MAE=-7.09 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO PENDING D20=None MFE=2.01 MAE=-2.69 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST PENDING D20=None MFE=0.74 MAE=-2.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX PENDING D20=None MFE=5.44 MAE=-0.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR PENDING D20=None MFE=5.33 MAE=-1.13 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS PENDING D20=None MFE=1.49 MAE=-10.52 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS PENDING D20=None MFE=2.28 MAE=-7.15 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS PENDING D20=None MFE=1.78 MAE=-6.72 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS PENDING D20=None MFE=1.44 MAE=-6.01 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS PENDING D20=None MFE=4.64 MAE=-4.64 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS PENDING D20=None MFE=1.01 MAE=-7.37 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ PENDING D20=None MFE=9.69 MAE=-9.52 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS PENDING D20=None MFE=2.14 MAE=-5.1 bought=False lane=pullback catalyst=
- 2026-06-18 REGN PENDING D20=None MFE=1.03 MAE=-1.93 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
- 2026-06-19 TRGP PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=NO_DATA
