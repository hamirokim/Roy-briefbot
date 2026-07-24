# SCOUT Performance Report

- date: 2026-07-25
- evaluated candidates: 93 / 93
- actually bought: 0
- avg D20 return: -8.63
- verdicts: {'WINNER': 24, 'FAILED_FAST': 54, 'PENDING': 1, 'NEUTRAL': 1, 'WATCH': 13}

## Aggregates

### by_lane
- pullback: n=38, avgD20=-11.27, winner=0.158, failed_fast=0.711, bought=0
- strength: n=32, avgD20=-8.04, winner=0.344, failed_fast=0.594, bought=0
- left_side: n=23, avgD20=-1.3, winner=0.304, failed_fast=0.348, bought=0

### by_lane_status
- STRONG_PASS: n=47, avgD20=-8.76, winner=0.277, failed_fast=0.638, bought=0
- PASS: n=22, avgD20=-13.14, winner=0.182, failed_fast=0.682, bought=0
- STAGE2_PASS: n=18, avgD20=-2.18, winner=0.278, failed_fast=0.333, bought=0
- STAGE2_STRONG_PASS: n=4, avgD20=3.09, winner=0.5, failed_fast=0.25, bought=0
- WAIT: n=1, avgD20=None, winner=0.0, failed_fast=1.0, bought=0
- WAIT_CONFIRM: n=1, avgD20=None, winner=0.0, failed_fast=1.0, bought=0

### by_theme_industry
- NO_MAPPING: n=35, avgD20=-17.39, winner=0.057, failed_fast=0.886, bought=0
- SUPPORT: n=32, avgD20=1.97, winner=0.438, failed_fast=0.375, bought=0
- STRONG_SUPPORT: n=14, avgD20=7.71, winner=0.429, failed_fast=0.5, bought=0
- SECTOR_UNSUPPORTED: n=10, avgD20=-1.27, winner=0.2, failed_fast=0.4, bought=0
- SECTOR_NEUTRAL: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=30, avgD20=0.42, winner=0.367, failed_fast=0.367, bought=0
- QUALITY_SUPPORT: n=25, avgD20=-13.78, winner=0.24, failed_fast=0.68, bought=0
- not_checked: n=24, avgD20=-6.67, winner=0.25, failed_fast=0.542, bought=0
- NEUTRAL: n=11, avgD20=-17.37, winner=0.091, failed_fast=0.909, bought=0
- DATA_LIGHT: n=3, avgD20=-18.13, winner=0.0, failed_fast=1.0, bought=0

### by_catalyst
- unknown: n=39, avgD20=-9.1, winner=0.231, failed_fast=0.59, bought=0
- POSITIVE_REVALUATION: n=25, avgD20=-0.49, winner=0.36, failed_fast=0.44, bought=0
- NOISE: n=24, avgD20=-17.59, winner=0.25, failed_fast=0.625, bought=0
- NO_DATA: n=5, avgD20=-10.96, winner=0.0, failed_fast=1.0, bought=0

## LLM Override Comparison
- counts: dropped=4, added=15, kept=78
- avg D5: dropped=1.21, added=-3.1, kept=-1.98
- avg D20: dropped=-11.3, added=-4.78, kept=-10.04

### Dropped by LLM
- 2026-06-13 MNST WINNER D5=0.49 D20=4.66 MFE=6.35 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB FAILED_FAST D5=3.71 D20=-27.26 MFE=13.61 MAE=-34.13 lane=strength:STRONG_PASS
- 2026-06-24 NUVL WATCH D5=0.02 D20=None MFE=0.33 MAE=-0.12 lane=strength:STRONG_PASS
- 2026-06-27 DELL FAILED_FAST D5=0.64 D20=None MFE=11.79 MAE=-11.21 lane=pullback:PASS

### Added by LLM
- 2026-06-11 329180.KS FAILED_FAST D5=5.88 D20=-21.52 MFE=14.24 MAE=-23.3 lane=pullback:PASS
- 2026-06-12 036570.KS FAILED_FAST D5=5.32 D20=-5.51 MFE=7.41 MAE=-13.5 lane=pullback:STRONG_PASS
- 2026-06-13 KT FAILED_FAST D5=-5.63 D20=-7.96 MFE=0.74 MAE=-9.08 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM FAILED_FAST D5=-2.71 D20=7.23 MFE=25.97 MAE=-10.55 lane=strength:PASS
- 2026-06-16 005940.KS FAILED_FAST D5=-12.48 D20=-9.28 MFE=3.81 MAE=-19.03 lane=pullback:PASS
- 2026-06-17 017670.KS FAILED_FAST D5=-8.08 D20=-14.14 MFE=1.01 MAE=-16.97 lane=pullback:STRONG_PASS
- 2026-06-18 REGN WINNER D5=3.76 D20=10.2 MFE=13.31 MAE=-2.47 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT FAILED_FAST D5=-2.2 D20=-5.79 MFE=2.75 MAE=-8.47 lane=pullback:PASS
- 2026-06-20 012330.KS FAILED_FAST D5=-11.78 D20=-15.73 MFE=5.45 MAE=-20.56 lane=pullback:PASS
- 2026-06-24 AMGN WINNER D5=2.82 D20=5.71 MFE=7.71 MAE=-1.55 lane=pullback:PASS
- 2026-06-25 KT NEUTRAL D5=-0.67 D20=4.21 MFE=4.88 MAE=-3.82 lane=left_side:STAGE2_PASS
- 2026-06-27 003230.KS FAILED_FAST D5=-5.34 D20=None MFE=7.41 MAE=-11.29 lane=left_side:STAGE2_PASS
- 2026-07-02 IBM FAILED_FAST D5=-0.68 D20=None MFE=7.7 MAE=-31.2 lane=pullback:WAIT
- 2026-07-10 088350.KS FAILED_FAST D5=-7.2 D20=None MFE=2.8 MAE=-9.14 lane=left_side:WAIT_CONFIRM
- 2026-07-15 426030.KS FAILED_FAST D5=-7.44 D20=None MFE=0.59 MAE=-16.8 lane=pullback:PASS

## Precision Shadow Comparison
- us_precision_v1: n=10/11, avgD5=-2.84, avgD10=None, avgD20=None

## Recent Candidate Records
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
- 2026-06-18 080220.KQ FAILED_FAST D20=-30.42 MFE=17.25 MAE=-40.87 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS FAILED_FAST D20=-23.06 MFE=4.8 MAE=-25.28 bought=False lane=pullback catalyst=
- 2026-06-18 REGN WINNER D20=10.2 MFE=13.31 MAE=-2.47 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT FAILED_FAST D20=-5.79 MFE=2.75 MAE=-8.47 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV WINNER D20=4.46 MFE=11.18 MAE=-2.45 bought=False lane=strength catalyst=
- 2026-06-19 TRGP WINNER D20=5.94 MFE=8.22 MAE=-3.21 bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ FAILED_FAST D20=-10.43 MFE=29.4 MAE=-18.59 bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ FAILED_FAST D20=-34.38 MFE=10.62 MAE=-38.44 bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS FAILED_FAST D20=-15.73 MFE=5.45 MAE=-20.56 bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS FAILED_FAST D20=-26.79 MFE=1.86 MAE=-30.76 bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ FAILED_FAST D20=-33.05 MFE=2.5 MAE=-44.87 bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS FAILED_FAST D20=-11.46 MFE=4.19 MAE=-16.2 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-23 080220.KQ FAILED_FAST D20=-32.31 MFE=20.31 MAE=-37.18 bought=False lane=strength catalyst=NO_DATA
- 2026-06-23 TW FAILED_FAST D20=-0.33 MFE=5.6 MAE=-7.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-23 001040.KS FAILED_FAST D20=-17.04 MFE=6.6 MAE=-21.13 bought=False lane=left_side catalyst=NOISE
- 2026-06-24 CPRX PENDING D20=None MFE=0.0 MAE=0.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 GH WINNER D20=9.67 MFE=27.1 MAE=-3.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 AMGN WINNER D20=5.71 MFE=7.71 MAE=-1.55 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-25 KT NEUTRAL D20=4.21 MFE=4.88 MAE=-3.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-25 WMB FAILED_FAST D20=-4.55 MFE=1.9 MAE=-6.99 bought=False lane=strength catalyst=
- 2026-06-25 TRGP FAILED_FAST D20=2.88 MFE=6.3 MAE=-6.37 bought=False lane=strength catalyst=
- 2026-06-26 HEI WATCH D20=None MFE=7.03 MAE=-3.03 bought=False lane=strength catalyst=
- 2026-06-26 PANW WINNER D20=None MFE=21.24 MAE=-4.67 bought=False lane=strength catalyst=NOISE
- 2026-06-26 ROKU WINNER D20=None MFE=7.64 MAE=-0.77 bought=False lane=strength catalyst=
- 2026-06-27 NU WINNER D20=None MFE=10.81 MAE=-1.45 bought=False lane=left_side catalyst=
- 2026-06-27 APD WINNER D20=None MFE=16.04 MAE=-0.46 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-27 003230.KS FAILED_FAST D20=None MFE=7.41 MAE=-11.29 bought=False lane=left_side catalyst=NO_DATA
- 2026-06-29 AMD FAILED_FAST D20=None MFE=8.39 MAE=-14.7 bought=False lane=strength catalyst=
- 2026-06-29 ASML FAILED_FAST D20=None MFE=6.21 MAE=-9.54 bought=False lane=strength catalyst=
- 2026-06-29 FTNT WINNER D20=None MFE=9.61 MAE=-3.02 bought=False lane=strength catalyst=NOISE
- 2026-06-30 TSM FAILED_FAST D20=None MFE=0.3 MAE=-19.17 bought=False lane=strength catalyst=NOISE
- 2026-06-30 CRWD WINNER D20=None MFE=14.0 MAE=-5.13 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-30 PENG FAILED_FAST D20=None MFE=18.22 MAE=-31.57 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 009150.KS FAILED_FAST D20=None MFE=3.95 MAE=-47.26 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 TIGO WINNER D20=None MFE=11.34 MAE=-2.75 bought=False lane=strength catalyst=
- 2026-07-01 MRVL FAILED_FAST D20=None MFE=7.52 MAE=-34.59 bought=False lane=strength catalyst=NOISE
- 2026-07-02 F WINNER D20=None MFE=10.03 MAE=-1.05 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 IBM FAILED_FAST D20=None MFE=7.7 MAE=-31.2 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 098460.KQ FAILED_FAST D20=None MFE=10.29 MAE=-19.9 bought=False lane=pullback catalyst=
- 2026-07-03 DDOG WINNER D20=None MFE=8.35 MAE=-5.56 bought=False lane=strength catalyst=
- 2026-07-03 OKTA FAILED_FAST D20=None MFE=5.65 MAE=-9.97 bought=False lane=strength catalyst=
- 2026-07-03 PANW FAILED_FAST D20=None MFE=3.15 MAE=-11.91 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-04 001800.KS WINNER D20=None MFE=9.36 MAE=-6.04 bought=False lane=pullback catalyst=
- 2026-07-04 A WINNER D20=None MFE=8.69 MAE=-4.29 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-04 069960.KS FAILED_FAST D20=None MFE=3.97 MAE=-27.42 bought=False lane=strength catalyst=NOISE
- 2026-07-06 003230.KS WINNER D20=None MFE=13.48 MAE=-6.28 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 PUK WATCH D20=None MFE=7.75 MAE=-3.59 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 029780.KS WATCH D20=None MFE=6.05 MAE=-5.23 bought=False lane=left_side catalyst=NOISE
- 2026-07-07 CPNG FAILED_FAST D20=None MFE=5.4 MAE=-17.22 bought=False lane=left_side catalyst=
- 2026-07-07 F WINNER D20=None MFE=8.41 MAE=-2.36 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-07 FLEX FAILED_FAST D20=None MFE=10.56 MAE=-15.31 bought=False lane=pullback catalyst=
- 2026-07-08 EQT WINNER D20=None MFE=7.13 MAE=-6.29 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-08 326030.KS FAILED_FAST D20=None MFE=4.14 MAE=-9.87 bought=False lane=left_side catalyst=NOISE
- 2026-07-08 000240.KS WATCH D20=None MFE=3.12 MAE=-6.84 bought=False lane=pullback catalyst=
- 2026-07-09 XPO WATCH D20=None MFE=5.99 MAE=-2.71 bought=False lane=pullback catalyst=
- 2026-07-09 A WATCH D20=None MFE=6.26 MAE=-6.43 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-09 HPE FAILED_FAST D20=None MFE=4.01 MAE=-11.02 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-10 AVGO FAILED_FAST D20=None MFE=0.62 MAE=-10.54 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-10 EXE WINNER D20=None MFE=8.08 MAE=-2.6 bought=False lane=left_side catalyst=NOISE
- 2026-07-10 088350.KS FAILED_FAST D20=None MFE=2.8 MAE=-9.14 bought=False lane=left_side catalyst=NOISE
- 2026-07-11 INTU WATCH D20=None MFE=4.25 MAE=-6.23 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-11 AMZN WATCH D20=None MFE=4.35 MAE=-6.45 bought=False lane=pullback catalyst=NOISE
- 2026-07-11 FOX WATCH D20=None MFE=5.35 MAE=-3.25 bought=False lane=left_side catalyst=
- 2026-07-13 FLEX FAILED_FAST D20=None MFE=4.76 MAE=-13.99 bought=False lane=pullback catalyst=
- 2026-07-13 MRVL FAILED_FAST D20=None MFE=6.65 MAE=-18.2 bought=False lane=pullback catalyst=NOISE
- 2026-07-13 204320.KS FAILED_FAST D20=None MFE=9.87 MAE=-13.24 bought=False lane=left_side catalyst=NOISE
- 2026-07-14 XPO WATCH D20=None MFE=5.01 MAE=-2.94 bought=False lane=pullback catalyst=
- 2026-07-14 AON WATCH D20=None MFE=4.75 MAE=-2.35 bought=False lane=left_side catalyst=
- 2026-07-14 FOXA WATCH D20=None MFE=7.39 MAE=-0.86 bought=False lane=left_side catalyst=
- 2026-07-15 GOOG FAILED_FAST D20=None MFE=1.12 MAE=-14.94 bought=False lane=pullback catalyst=
- 2026-07-15 HWM WATCH D20=None MFE=4.93 MAE=-4.83 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-15 426030.KS FAILED_FAST D20=None MFE=0.59 MAE=-16.8 bought=False lane=pullback catalyst=
