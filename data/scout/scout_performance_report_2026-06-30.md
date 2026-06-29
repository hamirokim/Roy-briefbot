# SCOUT Performance Report

- date: 2026-06-30
- evaluated candidates: 84 / 87
- actually bought: 0
- avg D20 return: -2.97
- verdicts: {'FAILED_FAST': 41, 'WINNER': 15, 'WATCH': 10, 'PENDING': 18}

## Aggregates

### by_lane
- strength: n=49, avgD20=-2.97, winner=0.224, failed_fast=0.429, bought=0
- pullback: n=24, avgD20=None, winner=0.125, failed_fast=0.75, bought=0
- left_side: n=11, avgD20=None, winner=0.091, failed_fast=0.182, bought=0

### by_lane_status
- STRONG_PASS: n=62, avgD20=-2.97, winner=0.226, failed_fast=0.5, bought=0
- PASS: n=11, avgD20=None, winner=0.0, failed_fast=0.727, bought=0
- STAGE2_PASS: n=7, avgD20=None, winner=0.143, failed_fast=0.143, bought=0
- STAGE2_STRONG_PASS: n=4, avgD20=None, winner=0.0, failed_fast=0.25, bought=0

### by_theme_industry
- SUPPORT: n=45, avgD20=2.92, winner=0.333, failed_fast=0.289, bought=0
- NO_MAPPING: n=26, avgD20=None, winner=0.0, failed_fast=0.885, bought=0
- STRONG_SUPPORT: n=11, avgD20=-14.75, winner=0.0, failed_fast=0.455, bought=0
- SECTOR_UNSUPPORTED: n=2, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=35, avgD20=-5.81, winner=0.257, failed_fast=0.343, bought=0
- QUALITY_SUPPORT: n=23, avgD20=2.7, winner=0.217, failed_fast=0.522, bought=0
- not_checked: n=15, avgD20=None, winner=0.067, failed_fast=0.533, bought=0
- NEUTRAL: n=9, avgD20=None, winner=0.0, failed_fast=0.778, bought=0
- DATA_LIGHT: n=2, avgD20=None, winner=0.0, failed_fast=1.0, bought=0

### by_catalyst
- unknown: n=36, avgD20=0.62, winner=0.25, failed_fast=0.444, bought=0
- POSITIVE_REVALUATION: n=25, avgD20=-3.69, winner=0.12, failed_fast=0.48, bought=0
- NOISE: n=18, avgD20=None, winner=0.167, failed_fast=0.556, bought=0
- NO_DATA: n=5, avgD20=None, winner=0.0, failed_fast=0.6, bought=0

## LLM Override Comparison
- counts: dropped=7, added=16, kept=71
- avg D5: dropped=-3.01, added=-1.82, kept=-1.47
- avg D20: dropped=-3.67, added=5.46, kept=-7.19

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=-15.1 MFE=5.01 MAE=-20.8 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=7.76 MFE=7.96 MAE=-13.46 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=None MFE=1.2 MAE=-31.54 lane=strength:STRONG_PASS
- 2026-06-13 MNST WATCH D5=0.49 D20=None MFE=4.98 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB FAILED_FAST D5=3.71 D20=None MFE=3.89 MAE=-15.28 lane=strength:STRONG_PASS
- 2026-06-24 NUVL PENDING D5=None D20=None MFE=0.09 MAE=-0.11 lane=strength:STRONG_PASS
- 2026-06-27 DELL PENDING D5=None D20=None MFE=0.44 MAE=-8.67 lane=pullback:PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=0.62 MFE=8.72 MAE=-2.93 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=2.69 D20=10.3 MFE=12.68 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=None MFE=2.6 MAE=-17.13 lane=strength:STRONG_PASS
- 2026-06-04 DAC FAILED_FAST D5=0.09 D20=None MFE=2.16 MAE=-7.66 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS FAILED_FAST D5=5.88 D20=None MFE=14.24 MAE=-15.02 lane=pullback:PASS
- 2026-06-12 036570.KS FAILED_FAST D5=5.32 D20=None MFE=7.41 MAE=-13.5 lane=pullback:STRONG_PASS
- 2026-06-13 KT FAILED_FAST D5=-5.63 D20=None MFE=0.74 MAE=-8.65 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM FAILED_FAST D5=-2.71 D20=None MFE=21.55 MAE=-10.55 lane=strength:PASS
- 2026-06-16 005940.KS FAILED_FAST D5=-12.48 D20=None MFE=2.28 MAE=-19.03 lane=pullback:PASS
- 2026-06-17 017670.KS FAILED_FAST D5=-8.08 D20=None MFE=1.01 MAE=-12.12 lane=pullback:STRONG_PASS
- 2026-06-18 REGN WATCH D5=3.76 D20=None MFE=4.73 MAE=-2.47 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT WATCH D5=-2.2 D20=None MFE=2.75 MAE=-2.54 lane=pullback:PASS
- 2026-06-20 012330.KS FAILED_FAST D5=-11.78 D20=None MFE=5.45 MAE=-18.72 lane=pullback:PASS
- 2026-06-24 AMGN PENDING D5=None D20=None MFE=3.32 MAE=-1.55 lane=pullback:PASS
- 2026-06-25 KT PENDING D5=None D20=None MFE=1.97 MAE=-3.37 lane=left_side:STAGE2_PASS
- 2026-06-27 003230.KS PENDING D5=None D20=None MFE=2.41 MAE=-5.43 lane=left_side:STAGE2_PASS

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=-15.08 MFE=0.27 MAE=-17.68 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=-14.43 MFE=16.04 MAE=-14.71 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=0.62 MFE=8.72 MAE=-2.93 bought=False lane=strength catalyst=
- 2026-05-29 DTM WINNER D20=5.64 MFE=8.59 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC FAILED_FAST D20=-4.9 MFE=4.63 MAE=-7.74 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WINNER D20=10.3 MFE=12.68 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=None MFE=11.61 MAE=-10.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=None MFE=15.38 MAE=-10.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=None MFE=16.28 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=None MFE=18.68 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO FAILED_FAST D20=None MFE=5.04 MAE=-9.87 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=None MFE=2.6 MAE=-17.13 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL FAILED_FAST D20=None MFE=3.91 MAE=-8.75 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=None MFE=14.87 MAE=-12.03 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO FAILED_FAST D20=None MFE=10.8 MAE=-8.42 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=None MFE=60.84 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=None MFE=4.49 MAE=-42.43 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WINNER D20=None MFE=15.21 MAE=-5.91 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=None MFE=6.19 MAE=-12.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=None MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC FAILED_FAST D20=None MFE=2.16 MAE=-7.66 bought=False lane=strength catalyst=
- 2026-06-05 IRM WINNER D20=None MFE=8.04 MAE=-1.82 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP WATCH D20=None MFE=7.88 MAE=-3.4 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WINNER D20=None MFE=7.0 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=None MFE=9.8 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=None MFE=2.11 MAE=-11.84 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=None MFE=16.02 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL FAILED_FAST D20=None MFE=3.49 MAE=-9.11 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=None MFE=23.79 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=None MFE=18.78 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=None MFE=3.52 MAE=-30.6 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH WINNER D20=None MFE=28.11 MAE=-0.67 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX WATCH D20=None MFE=4.45 MAE=-2.83 bought=False lane=strength catalyst=
- 2026-06-10 NGG WINNER D20=None MFE=4.63 MAE=-2.02 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS FAILED_FAST D20=None MFE=32.71 MAE=-11.08 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS FAILED_FAST D20=None MFE=36.34 MAE=-19.68 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS FAILED_FAST D20=None MFE=14.24 MAE=-15.02 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS FAILED_FAST D20=None MFE=22.5 MAE=-18.64 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS FAILED_FAST D20=None MFE=5.19 MAE=-20.57 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS FAILED_FAST D20=None MFE=8.57 MAE=-24.14 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI FAILED_FAST D20=None MFE=0.57 MAE=-10.24 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS FAILED_FAST D20=None MFE=7.41 MAE=-13.5 bought=False lane=pullback catalyst=
- 2026-06-13 KT FAILED_FAST D20=None MFE=0.74 MAE=-8.65 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM FAILED_FAST D20=None MFE=21.55 MAE=-10.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO WATCH D20=None MFE=2.26 MAE=-6.08 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST WATCH D20=None MFE=4.98 MAE=-2.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX WATCH D20=None MFE=5.78 MAE=-1.59 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR WATCH D20=None MFE=7.61 MAE=-1.13 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS FAILED_FAST D20=None MFE=1.49 MAE=-20.77 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS FAILED_FAST D20=None MFE=2.28 MAE=-19.03 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS FAILED_FAST D20=None MFE=1.78 MAE=-19.17 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS FAILED_FAST D20=None MFE=1.44 MAE=-22.36 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS FAILED_FAST D20=None MFE=6.18 MAE=-10.6 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS FAILED_FAST D20=None MFE=1.01 MAE=-12.12 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ FAILED_FAST D20=None MFE=17.25 MAE=-23.11 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS FAILED_FAST D20=None MFE=4.8 MAE=-19.14 bought=False lane=pullback catalyst=
- 2026-06-18 REGN WATCH D20=None MFE=4.73 MAE=-2.47 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT WATCH D20=None MFE=2.75 MAE=-2.54 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV WATCH D20=None MFE=5.81 MAE=-2.45 bought=False lane=strength catalyst=
- 2026-06-19 TRGP WATCH D20=None MFE=4.09 MAE=-3.07 bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ FAILED_FAST D20=None MFE=10.43 MAE=-11.43 bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ FAILED_FAST D20=None MFE=10.62 MAE=-27.5 bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS FAILED_FAST D20=None MFE=5.45 MAE=-18.72 bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS FAILED_FAST D20=None MFE=1.86 MAE=-11.48 bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ FAILED_FAST D20=None MFE=2.5 MAE=-30.89 bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS FAILED_FAST D20=None MFE=4.19 MAE=-14.56 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-23 080220.KQ PENDING D20=None MFE=20.31 MAE=-18.32 bought=False lane=strength catalyst=NO_DATA
- 2026-06-23 TW PENDING D20=None MFE=1.6 MAE=-7.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-23 001040.KS PENDING D20=None MFE=6.6 MAE=-6.73 bought=False lane=left_side catalyst=NOISE
- 2026-06-24 CPRX PENDING D20=None MFE=0.25 MAE=-0.1 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 GH PENDING D20=None MFE=12.41 MAE=-3.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 AMGN PENDING D20=None MFE=3.32 MAE=-1.55 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-25 KT PENDING D20=None MFE=1.97 MAE=-3.37 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-25 WMB PENDING D20=None MFE=1.9 MAE=-4.88 bought=False lane=strength catalyst=
- 2026-06-25 TRGP PENDING D20=None MFE=0.68 MAE=-2.9 bought=False lane=strength catalyst=
- 2026-06-26 HEI PENDING D20=None MFE=2.09 MAE=-2.61 bought=False lane=strength catalyst=
- 2026-06-26 PANW PENDING D20=None MFE=9.4 MAE=-4.67 bought=False lane=strength catalyst=NOISE
- 2026-06-26 ROKU PENDING D20=None MFE=1.55 MAE=-0.77 bought=False lane=strength catalyst=
- 2026-06-27 NU PENDING D20=None MFE=1.29 MAE=-1.07 bought=False lane=left_side catalyst=
- 2026-06-27 APD PENDING D20=None MFE=2.89 MAE=-0.46 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-27 003230.KS PENDING D20=None MFE=2.41 MAE=-5.43 bought=False lane=left_side catalyst=NO_DATA
- 2026-06-29 AMD PENDING D20=None MFE=0.5 MAE=-8.18 bought=False lane=strength catalyst=
- 2026-06-29 ASML PENDING D20=None MFE=0.16 MAE=-5.87 bought=False lane=strength catalyst=
- 2026-06-29 FTNT PENDING D20=None MFE=2.33 MAE=-2.12 bought=False lane=strength catalyst=NOISE
- 2026-06-30 TSM PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=NOISE
- 2026-06-30 CRWD PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-30 PENG PENDING D20=None MFE=None MAE=None bought=False lane=strength catalyst=POSITIVE_REVALUATION
