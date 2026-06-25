# SCOUT Performance Report

- date: 2026-06-26
- evaluated candidates: 75 / 78
- actually bought: 0
- avg D20 return: None
- verdicts: {'FAILED_FAST': 33, 'WINNER': 14, 'WATCH': 9, 'PENDING': 19}

## Aggregates

### by_lane
- strength: n=43, avgD20=None, winner=0.233, failed_fast=0.395, bought=0
- pullback: n=23, avgD20=None, winner=0.174, failed_fast=0.609, bought=0
- left_side: n=9, avgD20=None, winner=0.0, failed_fast=0.222, bought=0

### by_lane_status
- STRONG_PASS: n=56, avgD20=None, winner=0.25, failed_fast=0.482, bought=0
- PASS: n=10, avgD20=None, winner=0.0, failed_fast=0.4, bought=0
- STAGE2_PASS: n=6, avgD20=None, winner=0.0, failed_fast=0.167, bought=0
- STAGE2_STRONG_PASS: n=3, avgD20=None, winner=0.0, failed_fast=0.333, bought=0

### by_theme_industry
- SUPPORT: n=41, avgD20=None, winner=0.317, failed_fast=0.293, bought=0
- NO_MAPPING: n=25, avgD20=None, winner=0.04, failed_fast=0.64, bought=0
- STRONG_SUPPORT: n=7, avgD20=None, winner=0.0, failed_fast=0.714, bought=0
- SECTOR_UNSUPPORTED: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=32, avgD20=None, winner=0.219, failed_fast=0.344, bought=0
- QUALITY_SUPPORT: n=20, avgD20=None, winner=0.25, failed_fast=0.4, bought=0
- not_checked: n=13, avgD20=None, winner=0.154, failed_fast=0.385, bought=0
- NEUTRAL: n=8, avgD20=None, winner=0.0, failed_fast=0.875, bought=0
- DATA_LIGHT: n=2, avgD20=None, winner=0.0, failed_fast=1.0, bought=0

### by_catalyst
- unknown: n=31, avgD20=None, winner=0.29, failed_fast=0.355, bought=0
- POSITIVE_REVALUATION: n=24, avgD20=None, winner=0.083, failed_fast=0.5, bought=0
- NOISE: n=16, avgD20=None, winner=0.188, failed_fast=0.5, bought=0
- NO_DATA: n=4, avgD20=None, winner=0.0, failed_fast=0.5, bought=0

## LLM Override Comparison
- counts: dropped=6, added=15, kept=63
- avg D5: dropped=-4.7, added=-1.34, kept=-0.61
- avg D20: dropped=None, added=None, kept=None

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=None MFE=5.01 MAE=-20.8 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=None MFE=5.71 MAE=-13.46 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=None MFE=1.2 MAE=-29.43 lane=strength:STRONG_PASS
- 2026-06-13 MNST WATCH D5=0.49 D20=None MFE=3.03 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB PENDING D5=None D20=None MFE=0.3 MAE=-12.41 lane=strength:STRONG_PASS
- 2026-06-24 NUVL PENDING D5=None D20=None MFE=0.09 MAE=-0.11 lane=strength:STRONG_PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=None MFE=8.72 MAE=-2.93 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=2.69 D20=None MFE=12.68 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=None MFE=2.6 MAE=-17.13 lane=strength:STRONG_PASS
- 2026-06-04 DAC WATCH D5=0.09 D20=None MFE=2.16 MAE=-4.82 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS FAILED_FAST D5=5.88 D20=None MFE=14.24 MAE=-10.68 lane=pullback:PASS
- 2026-06-12 036570.KS FAILED_FAST D5=5.32 D20=None MFE=7.41 MAE=-11.22 lane=pullback:STRONG_PASS
- 2026-06-13 KT FAILED_FAST D5=-5.63 D20=None MFE=0.74 MAE=-7.75 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM FAILED_FAST D5=-2.71 D20=None MFE=6.28 MAE=-10.55 lane=strength:PASS
- 2026-06-16 005940.KS FAILED_FAST D5=-12.48 D20=None MFE=2.28 MAE=-14.46 lane=pullback:PASS
- 2026-06-17 017670.KS FAILED_FAST D5=-8.08 D20=None MFE=1.01 MAE=-10.51 lane=pullback:STRONG_PASS
- 2026-06-18 REGN PENDING D5=None D20=None MFE=3.98 MAE=-2.47 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT PENDING D5=None D20=None MFE=2.75 MAE=-1.54 lane=pullback:PASS
- 2026-06-20 012330.KS PENDING D5=None D20=None MFE=5.45 MAE=-12.83 lane=pullback:PASS
- 2026-06-24 AMGN PENDING D5=None D20=None MFE=2.18 MAE=-1.55 lane=pullback:PASS
- 2026-06-25 KT PENDING D5=None D20=None MFE=1.97 MAE=-0.39 lane=left_side:STAGE2_PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=None MFE=0.27 MAE=-17.68 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=None MFE=16.04 MAE=-13.19 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=None MFE=8.72 MAE=-2.93 bought=False lane=strength catalyst=
- 2026-05-29 DTM WATCH D20=None MFE=7.89 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC FAILED_FAST D20=None MFE=4.63 MAE=-7.74 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WINNER D20=None MFE=12.68 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=None MFE=9.28 MAE=-10.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=None MFE=15.38 MAE=-10.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=None MFE=16.28 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=None MFE=18.68 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO FAILED_FAST D20=None MFE=5.04 MAE=-9.87 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=None MFE=2.6 MAE=-17.13 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL FAILED_FAST D20=None MFE=3.91 MAE=-7.19 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=None MFE=14.87 MAE=-12.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO FAILED_FAST D20=None MFE=10.8 MAE=-8.42 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=None MFE=60.84 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=None MFE=4.49 MAE=-35.7 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WATCH D20=None MFE=5.19 MAE=-5.91 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=None MFE=6.19 MAE=-12.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=None MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC WATCH D20=None MFE=2.16 MAE=-4.82 bought=False lane=strength catalyst=
- 2026-06-05 IRM WINNER D20=None MFE=8.04 MAE=-1.82 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP WATCH D20=None MFE=4.22 MAE=-3.4 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WINNER D20=None MFE=6.98 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=None MFE=9.24 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=None MFE=2.11 MAE=-11.84 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=None MFE=14.22 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL FAILED_FAST D20=None MFE=3.49 MAE=-7.56 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=None MFE=19.12 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=None MFE=18.13 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=None MFE=3.52 MAE=-30.6 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH WINNER D20=None MFE=24.52 MAE=-0.67 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX WATCH D20=None MFE=4.45 MAE=-2.8 bought=False lane=strength catalyst=
- 2026-06-10 NGG WINNER D20=None MFE=4.63 MAE=-2.02 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS WINNER D20=None MFE=32.71 MAE=-5.54 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS FAILED_FAST D20=None MFE=36.34 MAE=-11.92 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS FAILED_FAST D20=None MFE=14.24 MAE=-10.68 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS FAILED_FAST D20=None MFE=22.5 MAE=-14.33 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS FAILED_FAST D20=None MFE=5.19 MAE=-17.35 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS FAILED_FAST D20=None MFE=8.57 MAE=-18.7 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI FAILED_FAST D20=None MFE=0.57 MAE=-10.24 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS FAILED_FAST D20=None MFE=7.41 MAE=-11.22 bought=False lane=pullback catalyst=
- 2026-06-13 KT FAILED_FAST D20=None MFE=0.74 MAE=-7.75 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM FAILED_FAST D20=None MFE=6.28 MAE=-10.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO WATCH D20=None MFE=2.26 MAE=-2.69 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST WATCH D20=None MFE=3.03 MAE=-2.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX WATCH D20=None MFE=5.78 MAE=-0.6 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR WATCH D20=None MFE=7.61 MAE=-1.13 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS FAILED_FAST D20=None MFE=1.49 MAE=-13.94 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS FAILED_FAST D20=None MFE=2.28 MAE=-14.46 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS FAILED_FAST D20=None MFE=1.78 MAE=-15.81 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS FAILED_FAST D20=None MFE=1.44 MAE=-15.38 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS FAILED_FAST D20=None MFE=6.18 MAE=-10.6 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS FAILED_FAST D20=None MFE=1.01 MAE=-10.51 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ FAILED_FAST D20=None MFE=17.25 MAE=-10.54 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS FAILED_FAST D20=None MFE=4.8 MAE=-13.9 bought=False lane=pullback catalyst=
- 2026-06-18 REGN PENDING D20=None MFE=3.98 MAE=-2.47 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT PENDING D20=None MFE=2.75 MAE=-1.54 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV PENDING D20=None MFE=0.62 MAE=-2.45 bought=False lane=strength catalyst=
- 2026-06-19 TRGP PENDING D20=None MFE=4.07 MAE=-3.07 bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ PENDING D20=None MFE=6.6 MAE=-11.43 bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ PENDING D20=None MFE=10.62 MAE=-24.84 bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS PENDING D20=None MFE=5.45 MAE=-12.83 bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS PENDING D20=None MFE=1.86 MAE=-11.48 bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ PENDING D20=None MFE=2.5 MAE=-28.73 bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS PENDING D20=None MFE=4.19 MAE=-12.1 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-23 080220.KQ PENDING D20=None MFE=20.31 MAE=-4.96 bought=False lane=strength catalyst=NO_DATA
- 2026-06-23 TW PENDING D20=None MFE=1.6 MAE=-7.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-23 001040.KS PENDING D20=None MFE=6.6 MAE=-3.58 bought=False lane=left_side catalyst=NOISE
- 2026-06-24 CPRX PENDING D20=None MFE=0.06 MAE=-0.1 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 GH PENDING D20=None MFE=6.48 MAE=-3.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 AMGN PENDING D20=None MFE=2.18 MAE=-1.55 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-25 KT PENDING D20=None MFE=1.97 MAE=-0.39 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-25 WMB PENDING D20=None MFE=0.28 MAE=-2.29 bought=False lane=strength catalyst=
- 2026-06-25 TRGP PENDING D20=None MFE=0.67 MAE=-2.9 bought=False lane=strength catalyst=
- 2026-06-26 HEI PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
- 2026-06-26 PANW PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=NOISE
- 2026-06-26 ROKU PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=
