# SCOUT Performance Report

- date: 2026-07-02
- evaluated candidates: 90 / 93
- actually bought: 0
- avg D20 return: 0.03
- verdicts: {'FAILED_FAST': 44, 'WINNER': 19, 'WATCH': 9, 'PENDING': 18}

## Aggregates

### by_lane
- strength: n=55, avgD20=-1.24, winner=0.255, failed_fast=0.4, bought=0
- pullback: n=24, avgD20=17.86, winner=0.125, failed_fast=0.792, bought=0
- left_side: n=11, avgD20=None, winner=0.182, failed_fast=0.273, bought=0

### by_lane_status
- STRONG_PASS: n=68, avgD20=0.03, winner=0.25, failed_fast=0.471, bought=0
- PASS: n=11, avgD20=None, winner=0.0, failed_fast=0.818, bought=0
- STAGE2_PASS: n=7, avgD20=None, winner=0.143, failed_fast=0.286, bought=0
- STAGE2_STRONG_PASS: n=4, avgD20=None, winner=0.25, failed_fast=0.25, bought=0

### by_theme_industry
- SUPPORT: n=48, avgD20=2.52, winner=0.375, failed_fast=0.312, bought=0
- NO_MAPPING: n=27, avgD20=None, winner=0.0, failed_fast=0.889, bought=0
- STRONG_SUPPORT: n=13, avgD20=-9.9, winner=0.0, failed_fast=0.385, bought=0
- SECTOR_UNSUPPORTED: n=2, avgD20=None, winner=0.5, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=36, avgD20=-1.44, winner=0.306, failed_fast=0.389, bought=0
- QUALITY_SUPPORT: n=26, avgD20=2.98, winner=0.269, failed_fast=0.462, bought=0
- not_checked: n=16, avgD20=None, winner=0.062, failed_fast=0.5, bought=0
- NEUTRAL: n=10, avgD20=None, winner=0.0, failed_fast=0.8, bought=0
- DATA_LIGHT: n=2, avgD20=None, winner=0.0, failed_fast=1.0, bought=0

### by_catalyst
- unknown: n=37, avgD20=0.56, winner=0.297, failed_fast=0.432, bought=0
- POSITIVE_REVALUATION: n=28, avgD20=-1.43, winner=0.179, failed_fast=0.5, bought=0
- NOISE: n=20, avgD20=3.25, winner=0.15, failed_fast=0.5, bought=0
- NO_DATA: n=5, avgD20=None, winner=0.0, failed_fast=0.8, bought=0

## LLM Override Comparison
- counts: dropped=7, added=17, kept=76
- avg D5: dropped=-2.51, added=-1.48, kept=-1.06
- avg D20: dropped=-3.67, added=-1.72, kept=0.47

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=-15.1 MFE=5.01 MAE=-20.8 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=7.76 MFE=7.96 MAE=-13.46 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=None MFE=1.2 MAE=-31.54 lane=strength:STRONG_PASS
- 2026-06-13 MNST WINNER D5=0.49 D20=None MFE=5.44 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB FAILED_FAST D5=3.71 D20=None MFE=13.61 MAE=-15.28 lane=strength:STRONG_PASS
- 2026-06-24 NUVL WATCH D5=0.02 D20=None MFE=0.09 MAE=-0.12 lane=strength:STRONG_PASS
- 2026-06-27 DELL PENDING D5=None D20=None MFE=5.76 MAE=-8.67 lane=pullback:PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=0.62 MFE=8.72 MAE=-2.93 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=2.69 D20=10.3 MFE=12.68 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=-16.07 MFE=2.6 MAE=-17.13 lane=strength:STRONG_PASS
- 2026-06-04 DAC FAILED_FAST D5=0.09 D20=None MFE=2.16 MAE=-7.66 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS FAILED_FAST D5=5.88 D20=None MFE=14.24 MAE=-15.02 lane=pullback:PASS
- 2026-06-12 036570.KS FAILED_FAST D5=5.32 D20=None MFE=7.41 MAE=-13.5 lane=pullback:STRONG_PASS
- 2026-06-13 KT FAILED_FAST D5=-5.63 D20=None MFE=0.74 MAE=-9.1 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM FAILED_FAST D5=-2.71 D20=None MFE=24.72 MAE=-10.55 lane=strength:PASS
- 2026-06-16 005940.KS FAILED_FAST D5=-12.48 D20=None MFE=2.28 MAE=-19.03 lane=pullback:PASS
- 2026-06-17 017670.KS FAILED_FAST D5=-8.08 D20=None MFE=1.01 MAE=-13.43 lane=pullback:STRONG_PASS
- 2026-06-18 REGN WATCH D5=3.76 D20=None MFE=4.73 MAE=-2.47 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT FAILED_FAST D5=-2.2 D20=None MFE=2.75 MAE=-8.47 lane=pullback:PASS
- 2026-06-20 012330.KS FAILED_FAST D5=-11.78 D20=None MFE=5.45 MAE=-18.72 lane=pullback:PASS
- 2026-06-24 AMGN WATCH D5=2.82 D20=None MFE=3.58 MAE=-1.55 lane=pullback:PASS
- 2026-06-25 KT PENDING D5=None D20=None MFE=1.97 MAE=-3.85 lane=left_side:STAGE2_PASS
- 2026-06-27 003230.KS PENDING D5=None D20=None MFE=2.41 MAE=-5.43 lane=left_side:STAGE2_PASS
- 2026-07-02 IBM PENDING D5=None D20=None MFE=None MAE=None lane=pullback:WAIT

## Recent Candidate Records
- 2026-05-28 AMZN FAILED_FAST D20=-15.08 MFE=0.27 MAE=-17.68 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 AVGO FAILED_FAST D20=-14.43 MFE=16.04 MAE=-14.71 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-28 ELV WINNER D20=0.62 MFE=8.72 MAE=-2.93 bought=False lane=strength catalyst=
- 2026-05-29 DTM WINNER D20=5.64 MFE=8.59 MAE=-1.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 WCC FAILED_FAST D20=-4.9 MFE=4.63 MAE=-7.74 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-29 VMI WINNER D20=10.3 MFE=12.68 MAE=-2.84 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 MYRG FAILED_FAST D20=11.24 MFE=11.94 MAE=-10.53 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 ROKU FAILED_FAST D20=7.06 MFE=15.38 MAE=-10.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-05-30 RRX WINNER D20=17.86 MFE=18.26 MAE=-5.59 bought=False lane=pullback catalyst=
- 2026-06-01 IESC WINNER D20=8.45 MFE=18.68 MAE=-2.75 bought=False lane=strength catalyst=NOISE
- 2026-06-01 DINO FAILED_FAST D20=-1.64 MFE=5.04 MAE=-9.87 bought=False lane=strength catalyst=NOISE
- 2026-06-01 VIST FAILED_FAST D20=-16.07 MFE=2.6 MAE=-17.13 bought=False lane=strength catalyst=
- 2026-06-02 GOOGL FAILED_FAST D20=-0.18 MFE=3.91 MAE=-8.75 bought=False lane=strength catalyst=
- 2026-06-02 STRL FAILED_FAST D20=-11.3 MFE=14.87 MAE=-12.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-02 RXO FAILED_FAST D20=2.93 MFE=10.8 MAE=-8.42 bought=False lane=strength catalyst=NOISE
- 2026-06-03 402340.KS FAILED_FAST D20=None MFE=60.84 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=None MFE=4.49 MAE=-42.43 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WINNER D20=None MFE=15.22 MAE=-5.91 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=None MFE=6.19 MAE=-12.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=None MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC FAILED_FAST D20=None MFE=2.16 MAE=-7.66 bought=False lane=strength catalyst=
- 2026-06-05 IRM WINNER D20=None MFE=8.04 MAE=-2.74 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP WATCH D20=None MFE=7.88 MAE=-3.4 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WINNER D20=None MFE=7.0 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=None MFE=12.4 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=None MFE=2.11 MAE=-11.84 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=None MFE=16.39 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL FAILED_FAST D20=None MFE=3.49 MAE=-9.11 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=None MFE=23.79 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=None MFE=18.78 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=None MFE=3.52 MAE=-30.85 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
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
- 2026-06-13 KT FAILED_FAST D20=None MFE=0.74 MAE=-9.1 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM FAILED_FAST D20=None MFE=24.72 MAE=-10.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO WATCH D20=None MFE=2.26 MAE=-6.08 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST WINNER D20=None MFE=5.44 MAE=-2.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX WATCH D20=None MFE=5.78 MAE=-1.59 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR WINNER D20=None MFE=8.38 MAE=-1.13 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS FAILED_FAST D20=None MFE=1.49 MAE=-20.77 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS FAILED_FAST D20=None MFE=2.28 MAE=-19.03 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS FAILED_FAST D20=None MFE=1.78 MAE=-19.17 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS FAILED_FAST D20=None MFE=1.44 MAE=-22.36 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS FAILED_FAST D20=None MFE=6.18 MAE=-11.96 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS FAILED_FAST D20=None MFE=1.01 MAE=-13.43 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ FAILED_FAST D20=None MFE=17.25 MAE=-23.11 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS FAILED_FAST D20=None MFE=4.8 MAE=-19.14 bought=False lane=pullback catalyst=
- 2026-06-18 REGN WATCH D20=None MFE=4.73 MAE=-2.47 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT FAILED_FAST D20=None MFE=2.75 MAE=-8.47 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV WINNER D20=None MFE=9.27 MAE=-2.45 bought=False lane=strength catalyst=
- 2026-06-19 TRGP WATCH D20=None MFE=4.19 MAE=-3.07 bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ FAILED_FAST D20=None MFE=29.4 MAE=-11.43 bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ FAILED_FAST D20=None MFE=10.62 MAE=-27.5 bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS FAILED_FAST D20=None MFE=5.45 MAE=-18.72 bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS FAILED_FAST D20=None MFE=1.86 MAE=-11.48 bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ FAILED_FAST D20=None MFE=2.5 MAE=-31.06 bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS FAILED_FAST D20=None MFE=4.19 MAE=-14.74 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-23 080220.KQ FAILED_FAST D20=None MFE=20.31 MAE=-18.32 bought=False lane=strength catalyst=NO_DATA
- 2026-06-23 TW FAILED_FAST D20=None MFE=3.43 MAE=-7.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-23 001040.KS WATCH D20=None MFE=6.6 MAE=-6.73 bought=False lane=left_side catalyst=NOISE
- 2026-06-24 CPRX WATCH D20=None MFE=0.25 MAE=-0.1 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 GH WINNER D20=None MFE=26.03 MAE=-3.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 AMGN WATCH D20=None MFE=3.58 MAE=-1.55 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-25 KT PENDING D20=None MFE=1.97 MAE=-3.85 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-25 WMB PENDING D20=None MFE=1.9 MAE=-6.78 bought=False lane=strength catalyst=
- 2026-06-25 TRGP PENDING D20=None MFE=0.78 MAE=-5.74 bought=False lane=strength catalyst=
- 2026-06-26 HEI PENDING D20=None MFE=5.47 MAE=-2.61 bought=False lane=strength catalyst=
- 2026-06-26 PANW PENDING D20=None MFE=17.72 MAE=-4.67 bought=False lane=strength catalyst=NOISE
- 2026-06-26 ROKU PENDING D20=None MFE=4.73 MAE=-0.77 bought=False lane=strength catalyst=
- 2026-06-27 NU PENDING D20=None MFE=6.09 MAE=-1.45 bought=False lane=left_side catalyst=
- 2026-06-27 APD PENDING D20=None MFE=13.42 MAE=-0.46 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-27 003230.KS PENDING D20=None MFE=2.41 MAE=-5.43 bought=False lane=left_side catalyst=NO_DATA
- 2026-06-29 AMD PENDING D20=None MFE=8.39 MAE=-8.18 bought=False lane=strength catalyst=
- 2026-06-29 ASML PENDING D20=None MFE=6.21 MAE=-5.87 bought=False lane=strength catalyst=
- 2026-06-29 FTNT PENDING D20=None MFE=2.82 MAE=-3.02 bought=False lane=strength catalyst=NOISE
- 2026-06-30 TSM PENDING D20=None MFE=0.3 MAE=-7.14 bought=False lane=strength catalyst=NOISE
- 2026-06-30 CRWD PENDING D20=None MFE=1.72 MAE=-1.0 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-30 PENG PENDING D20=None MFE=1.79 MAE=-11.91 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 009150.KS PENDING D20=None MFE=3.95 MAE=-3.45 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 TIGO PENDING D20=None MFE=1.39 MAE=-2.75 bought=False lane=strength catalyst=
- 2026-07-01 MRVL PENDING D20=None MFE=7.52 MAE=-0.26 bought=False lane=strength catalyst=NOISE
- 2026-07-02 F PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=NOISE
- 2026-07-02 IBM PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=NOISE
- 2026-07-02 098460.KQ PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=
