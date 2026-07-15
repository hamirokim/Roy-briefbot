# SCOUT Performance Report

- date: 2026-07-16
- evaluated candidates: 117 / 117
- actually bought: 0
- avg D20 return: -3.72
- verdicts: {'WINNER': 27, 'FAILED_FAST': 57, 'NEUTRAL': 2, 'WATCH': 13, 'PENDING': 18}

## Aggregates

### by_lane
- strength: n=51, avgD20=1.22, winner=0.333, failed_fast=0.588, bought=0
- pullback: n=40, avgD20=-9.97, winner=0.125, failed_fast=0.525, bought=0
- left_side: n=26, avgD20=-7.49, winner=0.192, failed_fast=0.231, bought=0

### by_lane_status
- STRONG_PASS: n=67, avgD20=-2.04, winner=0.313, failed_fast=0.582, bought=0
- PASS: n=23, avgD20=-14.17, winner=0.043, failed_fast=0.478, bought=0
- STAGE2_PASS: n=19, avgD20=-3.41, winner=0.158, failed_fast=0.263, bought=0
- STAGE2_STRONG_PASS: n=6, avgD20=-10.21, winner=0.333, failed_fast=0.167, bought=0
- WAIT: n=1, avgD20=None, winner=0.0, failed_fast=1.0, bought=0
- WAIT_CONFIRM: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_theme_industry
- SUPPORT: n=52, avgD20=0.73, winner=0.346, failed_fast=0.346, bought=0
- NO_MAPPING: n=37, avgD20=-12.42, winner=0.054, failed_fast=0.811, bought=0
- STRONG_SUPPORT: n=16, avgD20=2.22, winner=0.312, failed_fast=0.5, bought=0
- SECTOR_UNSUPPORTED: n=10, avgD20=-6.99, winner=0.2, failed_fast=0.1, bought=0
- SECTOR_NEUTRAL: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=44, avgD20=2.18, winner=0.273, failed_fast=0.341, bought=0
- QUALITY_SUPPORT: n=32, avgD20=-8.08, winner=0.25, failed_fast=0.562, bought=0
- not_checked: n=25, avgD20=-5.54, winner=0.24, failed_fast=0.4, bought=0
- NEUTRAL: n=13, avgD20=-7.9, winner=0.077, failed_fast=0.923, bought=0
- DATA_LIGHT: n=3, avgD20=-18.13, winner=0.0, failed_fast=0.667, bought=0

### by_catalyst
- unknown: n=50, avgD20=-2.73, winner=0.3, failed_fast=0.44, bought=0
- NOISE: n=32, avgD20=-0.41, winner=0.188, failed_fast=0.531, bought=0
- POSITIVE_REVALUATION: n=30, avgD20=-9.62, winner=0.2, failed_fast=0.433, bought=0
- NO_DATA: n=5, avgD20=-0.04, winner=0.0, failed_fast=1.0, bought=0

## LLM Override Comparison
- counts: dropped=5, added=17, kept=100
- avg D5: dropped=-2.36, added=-2.29, kept=-1.27
- avg D20: dropped=-12.21, added=-8.85, kept=-2.62

### Dropped by LLM
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=-29.09 MFE=1.2 MAE=-31.54 lane=strength:STRONG_PASS
- 2026-06-13 MNST WINNER D5=0.49 D20=4.66 MFE=6.35 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB FAILED_FAST D5=3.71 D20=None MFE=13.61 MAE=-23.58 lane=strength:STRONG_PASS
- 2026-06-24 NUVL WATCH D5=0.02 D20=None MFE=0.33 MAE=-0.12 lane=strength:STRONG_PASS
- 2026-06-27 DELL FAILED_FAST D5=0.64 D20=None MFE=11.79 MAE=-8.67 lane=pullback:PASS

### Added by LLM
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=-16.07 MFE=2.6 MAE=-17.13 lane=strength:STRONG_PASS
- 2026-06-04 DAC FAILED_FAST D5=0.09 D20=-3.55 MFE=2.16 MAE=-7.66 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS FAILED_FAST D5=5.88 D20=-21.52 MFE=14.24 MAE=-23.3 lane=pullback:PASS
- 2026-06-12 036570.KS FAILED_FAST D5=5.32 D20=-5.51 MFE=7.41 MAE=-13.5 lane=pullback:STRONG_PASS
- 2026-06-13 KT FAILED_FAST D5=-5.63 D20=-7.96 MFE=0.74 MAE=-9.08 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM FAILED_FAST D5=-2.71 D20=7.23 MFE=25.97 MAE=-10.55 lane=strength:PASS
- 2026-06-16 005940.KS FAILED_FAST D5=-12.48 D20=-9.28 MFE=3.81 MAE=-19.03 lane=pullback:PASS
- 2026-06-17 017670.KS FAILED_FAST D5=-8.08 D20=-14.14 MFE=1.01 MAE=-16.97 lane=pullback:STRONG_PASS
- 2026-06-18 REGN WINNER D5=3.76 D20=None MFE=11.15 MAE=-2.47 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT FAILED_FAST D5=-2.2 D20=None MFE=2.75 MAE=-8.47 lane=pullback:PASS
- 2026-06-20 012330.KS FAILED_FAST D5=-11.78 D20=None MFE=5.45 MAE=-20.56 lane=pullback:PASS
- 2026-06-24 AMGN WATCH D5=2.82 D20=None MFE=6.78 MAE=-1.55 lane=pullback:PASS
- 2026-06-25 KT WATCH D5=-0.67 D20=None MFE=4.88 MAE=-3.82 lane=left_side:STAGE2_PASS
- 2026-06-27 003230.KS FAILED_FAST D5=-5.34 D20=None MFE=7.41 MAE=-10.69 lane=left_side:STAGE2_PASS
- 2026-07-02 IBM FAILED_FAST D5=-0.68 D20=None MFE=7.7 MAE=-27.11 lane=pullback:WAIT
- 2026-07-10 088350.KS PENDING D5=None D20=None MFE=2.8 MAE=-8.49 lane=left_side:WAIT_CONFIRM
- 2026-07-15 426030.KS PENDING D5=None D20=None MFE=0.59 MAE=-1.98 lane=pullback:PASS

## Precision Shadow Comparison
- us_precision_v1: n=0/3, avgD5=None, avgD10=None, avgD20=None

## Recent Candidate Records
- 2026-06-01 IESC WINNER D20=8.45 MFE=18.68 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO FAILED_FAST D20=-1.64 MFE=5.04 MAE=-9.87 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=-16.07 MFE=2.6 MAE=-17.13 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL FAILED_FAST D20=-0.18 MFE=3.91 MAE=-8.75 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=-11.3 MFE=14.87 MAE=-12.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO FAILED_FAST D20=2.93 MFE=10.8 MAE=-8.42 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=12.05 MFE=60.84 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=-33.1 MFE=4.49 MAE=-42.43 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WINNER D20=1.15 MFE=15.22 MAE=-5.91 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=-9.77 MFE=6.19 MAE=-13.83 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=-0.52 MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC FAILED_FAST D20=-3.55 MFE=2.16 MAE=-7.66 bought=False lane=strength catalyst=
- 2026-06-05 IRM FAILED_FAST D20=-7.15 MFE=8.04 MAE=-8.03 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP NEUTRAL D20=-2.11 MFE=7.88 MAE=-3.4 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WINNER D20=4.34 MFE=7.0 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=-1.15 MFE=12.4 MAE=-3.34 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=8.61 MFE=8.84 MAE=-11.84 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=8.8 MFE=16.39 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL FAILED_FAST D20=-0.38 MFE=3.49 MAE=-9.11 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=15.54 MFE=23.79 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=10.03 MFE=18.78 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=-31.6 MFE=3.52 MAE=-32.33 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH WINNER D20=27.74 MFE=28.82 MAE=-0.67 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX NEUTRAL D20=2.72 MFE=4.45 MAE=-2.83 bought=False lane=strength catalyst=
- 2026-06-10 NGG WINNER D20=2.75 MFE=4.63 MAE=-2.02 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS FAILED_FAST D20=-9.4 MFE=32.71 MAE=-12.54 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS FAILED_FAST D20=-17.25 MFE=36.34 MAE=-19.68 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS FAILED_FAST D20=-21.52 MFE=14.24 MAE=-23.3 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS FAILED_FAST D20=-12.94 MFE=22.5 MAE=-18.64 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS FAILED_FAST D20=-10.02 MFE=5.19 MAE=-20.57 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS FAILED_FAST D20=-24.63 MFE=8.57 MAE=-28.58 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI FAILED_FAST D20=5.34 MFE=5.5 MAE=-10.24 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS FAILED_FAST D20=-5.51 MFE=7.41 MAE=-13.5 bought=False lane=pullback catalyst=
- 2026-06-13 KT FAILED_FAST D20=-7.96 MFE=0.74 MAE=-9.08 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM FAILED_FAST D20=7.23 MFE=25.97 MAE=-10.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO FAILED_FAST D20=-6.99 MFE=2.26 MAE=-8.28 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST WINNER D20=4.66 MFE=6.35 MAE=-2.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX WINNER D20=5.68 MFE=5.83 MAE=-1.59 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR WINNER D20=3.09 MFE=8.38 MAE=-1.78 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS FAILED_FAST D20=15.16 MFE=28.4 MAE=-20.77 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS FAILED_FAST D20=-9.28 MFE=3.81 MAE=-19.03 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS FAILED_FAST D20=-21.03 MFE=1.78 MAE=-25.89 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS FAILED_FAST D20=-19.47 MFE=1.44 MAE=-25.6 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS FAILED_FAST D20=-15.23 MFE=6.18 MAE=-24.5 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS FAILED_FAST D20=-14.14 MFE=1.01 MAE=-16.97 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ FAILED_FAST D20=None MFE=17.25 MAE=-40.87 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS FAILED_FAST D20=None MFE=4.8 MAE=-25.28 bought=False lane=pullback catalyst=
- 2026-06-18 REGN WINNER D20=None MFE=11.15 MAE=-2.47 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT FAILED_FAST D20=None MFE=2.75 MAE=-8.47 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV WINNER D20=None MFE=11.18 MAE=-2.45 bought=False lane=strength catalyst=
- 2026-06-19 TRGP WINNER D20=None MFE=6.92 MAE=-3.21 bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ FAILED_FAST D20=None MFE=29.4 MAE=-18.59 bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ FAILED_FAST D20=None MFE=10.62 MAE=-38.44 bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS FAILED_FAST D20=None MFE=5.45 MAE=-20.56 bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS FAILED_FAST D20=None MFE=1.86 MAE=-30.46 bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ FAILED_FAST D20=None MFE=2.5 MAE=-44.87 bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS FAILED_FAST D20=None MFE=4.19 MAE=-15.2 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-23 080220.KQ FAILED_FAST D20=None MFE=20.31 MAE=-37.18 bought=False lane=strength catalyst=NO_DATA
- 2026-06-23 TW FAILED_FAST D20=None MFE=5.6 MAE=-7.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-23 001040.KS FAILED_FAST D20=None MFE=6.6 MAE=-17.3 bought=False lane=left_side catalyst=NOISE
- 2026-06-24 CPRX WATCH D20=None MFE=0.29 MAE=-0.1 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 GH WINNER D20=None MFE=27.1 MAE=-3.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 AMGN WATCH D20=None MFE=6.78 MAE=-1.55 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-25 KT WATCH D20=None MFE=4.88 MAE=-3.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-25 WMB FAILED_FAST D20=None MFE=1.9 MAE=-6.99 bought=False lane=strength catalyst=
- 2026-06-25 TRGP FAILED_FAST D20=None MFE=3.42 MAE=-6.37 bought=False lane=strength catalyst=
- 2026-06-26 HEI WATCH D20=None MFE=7.03 MAE=-2.61 bought=False lane=strength catalyst=
- 2026-06-26 PANW WINNER D20=None MFE=21.03 MAE=-4.67 bought=False lane=strength catalyst=NOISE
- 2026-06-26 ROKU WATCH D20=None MFE=6.03 MAE=-0.77 bought=False lane=strength catalyst=
- 2026-06-27 NU WINNER D20=None MFE=9.52 MAE=-1.45 bought=False lane=left_side catalyst=
- 2026-06-27 APD WINNER D20=None MFE=16.04 MAE=-0.46 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-27 003230.KS FAILED_FAST D20=None MFE=7.41 MAE=-10.69 bought=False lane=left_side catalyst=NO_DATA
- 2026-06-29 AMD FAILED_FAST D20=None MFE=8.39 MAE=-8.18 bought=False lane=strength catalyst=
- 2026-06-29 ASML FAILED_FAST D20=None MFE=6.21 MAE=-8.8 bought=False lane=strength catalyst=
- 2026-06-29 FTNT WINNER D20=None MFE=9.61 MAE=-3.02 bought=False lane=strength catalyst=NOISE
- 2026-06-30 TSM FAILED_FAST D20=None MFE=0.3 MAE=-13.99 bought=False lane=strength catalyst=NOISE
- 2026-06-30 CRWD WINNER D20=None MFE=14.0 MAE=-5.13 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-30 PENG FAILED_FAST D20=None MFE=18.22 MAE=-22.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 009150.KS FAILED_FAST D20=None MFE=3.95 MAE=-47.26 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 TIGO WINNER D20=None MFE=10.6 MAE=-2.75 bought=False lane=strength catalyst=
- 2026-07-01 MRVL FAILED_FAST D20=None MFE=7.52 MAE=-26.03 bought=False lane=strength catalyst=NOISE
- 2026-07-02 F WATCH D20=None MFE=7.6 MAE=-1.05 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 IBM FAILED_FAST D20=None MFE=7.7 MAE=-27.11 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 098460.KQ FAILED_FAST D20=None MFE=10.29 MAE=-19.9 bought=False lane=pullback catalyst=
- 2026-07-03 DDOG WINNER D20=None MFE=8.35 MAE=-2.88 bought=False lane=strength catalyst=
- 2026-07-03 OKTA FAILED_FAST D20=None MFE=5.65 MAE=-9.58 bought=False lane=strength catalyst=
- 2026-07-03 PANW FAILED_FAST D20=None MFE=2.98 MAE=-11.91 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-04 001800.KS WINNER D20=None MFE=9.36 MAE=-3.9 bought=False lane=pullback catalyst=
- 2026-07-04 A WATCH D20=None MFE=4.83 MAE=-2.4 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-04 069960.KS FAILED_FAST D20=None MFE=3.97 MAE=-15.64 bought=False lane=strength catalyst=NOISE
- 2026-07-06 003230.KS WINNER D20=None MFE=13.48 MAE=-5.65 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 PUK WATCH D20=None MFE=3.79 MAE=-3.59 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 029780.KS WATCH D20=None MFE=6.05 MAE=-3.18 bought=False lane=left_side catalyst=NOISE
- 2026-07-07 CPNG WATCH D20=None MFE=5.4 MAE=-6.53 bought=False lane=left_side catalyst=
- 2026-07-07 F WATCH D20=None MFE=6.01 MAE=-2.36 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-07 FLEX WINNER D20=None MFE=10.56 MAE=-5.88 bought=False lane=pullback catalyst=
- 2026-07-08 EQT WATCH D20=None MFE=1.72 MAE=-6.29 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-08 326030.KS FAILED_FAST D20=None MFE=4.14 MAE=-9.87 bought=False lane=left_side catalyst=NOISE
- 2026-07-08 000240.KS WATCH D20=None MFE=3.12 MAE=-6.84 bought=False lane=pullback catalyst=
- 2026-07-09 XPO PENDING D20=None MFE=2.68 MAE=-2.71 bought=False lane=pullback catalyst=
- 2026-07-09 A PENDING D20=None MFE=2.49 MAE=-4.28 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-09 HPE PENDING D20=None MFE=4.01 MAE=-7.41 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-10 AVGO PENDING D20=None MFE=0.62 MAE=-4.14 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-10 EXE PENDING D20=None MFE=3.15 MAE=-2.6 bought=False lane=left_side catalyst=NOISE
- 2026-07-10 088350.KS PENDING D20=None MFE=2.8 MAE=-8.49 bought=False lane=left_side catalyst=NOISE
- 2026-07-11 INTU PENDING D20=None MFE=2.15 MAE=-6.23 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-11 AMZN PENDING D20=None MFE=3.71 MAE=-1.42 bought=False lane=pullback catalyst=NOISE
- 2026-07-11 FOX PENDING D20=None MFE=1.53 MAE=-2.62 bought=False lane=left_side catalyst=
- 2026-07-13 FLEX PENDING D20=None MFE=4.76 MAE=-4.41 bought=False lane=pullback catalyst=
- 2026-07-13 MRVL PENDING D20=None MFE=6.65 MAE=-7.49 bought=False lane=pullback catalyst=NOISE
- 2026-07-13 204320.KS PENDING D20=None MFE=9.87 MAE=-7.98 bought=False lane=left_side catalyst=NOISE
- 2026-07-14 XPO PENDING D20=None MFE=1.73 MAE=-2.93 bought=False lane=pullback catalyst=
- 2026-07-14 AON PENDING D20=None MFE=1.92 MAE=-2.35 bought=False lane=left_side catalyst=
- 2026-07-14 FOXA PENDING D20=None MFE=2.49 MAE=-0.36 bought=False lane=left_side catalyst=
- 2026-07-15 GOOG PENDING D20=None MFE=0.52 MAE=-3.93 bought=False lane=pullback catalyst=
- 2026-07-15 HWM PENDING D20=None MFE=0.21 MAE=-2.86 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-15 426030.KS PENDING D20=None MFE=0.59 MAE=-1.98 bought=False lane=pullback catalyst=
