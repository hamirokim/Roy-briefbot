# SCOUT Performance Report

- date: 2026-07-08
- evaluated candidates: 105 / 108
- actually bought: 0
- avg D20 return: -1.59
- verdicts: {'FAILED_FAST': 51, 'WINNER': 23, 'NEUTRAL': 1, 'WATCH': 9, 'PENDING': 21}

## Aggregates

### by_lane
- strength: n=59, avgD20=-1.1, winner=0.254, failed_fast=0.475, bought=0
- pullback: n=30, avgD20=-7.62, winner=0.133, failed_fast=0.633, bought=0
- left_side: n=16, avgD20=-0.48, winner=0.25, failed_fast=0.25, bought=0

### by_lane_status
- STRONG_PASS: n=73, avgD20=-0.2, winner=0.247, failed_fast=0.521, bought=0
- PASS: n=15, avgD20=-33.1, winner=0.067, failed_fast=0.6, bought=0
- STAGE2_PASS: n=11, avgD20=1.15, winner=0.182, failed_fast=0.273, bought=0
- STAGE2_STRONG_PASS: n=5, avgD20=-2.11, winner=0.4, failed_fast=0.2, bought=0
- WAIT: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_theme_industry
- SUPPORT: n=53, avgD20=0.66, winner=0.377, failed_fast=0.34, bought=0
- NO_MAPPING: n=32, avgD20=-10.53, winner=0.0, failed_fast=0.781, bought=0
- STRONG_SUPPORT: n=16, avgD20=-9.9, winner=0.125, failed_fast=0.438, bought=0
- SECTOR_UNSUPPORTED: n=3, avgD20=None, winner=0.333, failed_fast=0.333, bought=0
- SECTOR_NEUTRAL: n=1, avgD20=None, winner=0.0, failed_fast=0.0, bought=0

### by_quality_auditor
- STRONG_QUALITY: n=42, avgD20=-1.45, winner=0.286, failed_fast=0.405, bought=0
- QUALITY_SUPPORT: n=29, avgD20=0.2, winner=0.241, failed_fast=0.483, bought=0
- not_checked: n=19, avgD20=None, winner=0.158, failed_fast=0.526, bought=0
- NEUTRAL: n=13, avgD20=-10.53, winner=0.077, failed_fast=0.615, bought=0
- DATA_LIGHT: n=2, avgD20=None, winner=0.0, failed_fast=1.0, bought=0

### by_catalyst
- unknown: n=43, avgD20=0.46, winner=0.302, failed_fast=0.465, bought=0
- POSITIVE_REVALUATION: n=31, avgD20=-5.43, winner=0.194, failed_fast=0.484, bought=0
- NOISE: n=26, avgD20=2.09, winner=0.154, failed_fast=0.423, bought=0
- NO_DATA: n=5, avgD20=None, winner=0.0, failed_fast=1.0, bought=0

## LLM Override Comparison
- counts: dropped=7, added=17, kept=91
- avg D5: dropped=-2.06, added=-1.67, kept=-0.55
- avg D20: dropped=-12.14, added=-2.17, kept=-1.47

### Dropped by LLM
- 2026-05-28 IRDM FAILED_FAST D5=1.58 D20=-15.1 MFE=5.01 MAE=-20.8 lane=strength:STRONG_PASS
- 2026-05-29 MYRG FAILED_FAST D5=-4.17 D20=7.76 MFE=7.96 MAE=-13.46 lane=strength:STRONG_PASS
- 2026-06-04 AKAM FAILED_FAST D5=-16.68 D20=-29.09 MFE=1.2 MAE=-31.54 lane=strength:STRONG_PASS
- 2026-06-13 MNST WINNER D5=0.49 D20=None MFE=6.35 MAE=-2.43 lane=strength:STRONG_PASS
- 2026-06-19 ALAB FAILED_FAST D5=3.71 D20=None MFE=13.61 MAE=-16.6 lane=strength:STRONG_PASS
- 2026-06-24 NUVL WATCH D5=0.02 D20=None MFE=0.19 MAE=-0.12 lane=strength:STRONG_PASS
- 2026-06-27 DELL FAILED_FAST D5=0.64 D20=None MFE=5.77 MAE=-8.67 lane=pullback:PASS

### Added by LLM
- 2026-05-28 ELV WINNER D5=4.25 D20=0.62 MFE=8.72 MAE=-2.93 lane=strength:STRONG_PASS
- 2026-05-29 VMI WINNER D5=2.69 D20=10.3 MFE=12.68 MAE=-2.84 lane=strength:STRONG_PASS
- 2026-06-01 VIST FAILED_FAST D5=-2.71 D20=-16.07 MFE=2.6 MAE=-17.13 lane=strength:STRONG_PASS
- 2026-06-04 DAC FAILED_FAST D5=0.09 D20=-3.55 MFE=2.16 MAE=-7.66 lane=strength:STRONG_PASS
- 2026-06-11 329180.KS FAILED_FAST D5=5.88 D20=None MFE=14.24 MAE=-18.89 lane=pullback:PASS
- 2026-06-12 036570.KS FAILED_FAST D5=5.32 D20=None MFE=7.41 MAE=-13.5 lane=pullback:STRONG_PASS
- 2026-06-13 KT FAILED_FAST D5=-5.63 D20=None MFE=0.74 MAE=-9.08 lane=left_side:STAGE2_PASS
- 2026-06-13 IRDM FAILED_FAST D5=-2.71 D20=None MFE=25.97 MAE=-10.55 lane=strength:PASS
- 2026-06-16 005940.KS FAILED_FAST D5=-12.48 D20=None MFE=3.81 MAE=-19.03 lane=pullback:PASS
- 2026-06-17 017670.KS FAILED_FAST D5=-8.08 D20=None MFE=1.01 MAE=-15.76 lane=pullback:STRONG_PASS
- 2026-06-18 REGN WINNER D5=3.76 D20=None MFE=11.15 MAE=-2.47 lane=left_side:STAGE2_PASS
- 2026-06-19 WMT FAILED_FAST D5=-2.2 D20=None MFE=2.75 MAE=-8.47 lane=pullback:PASS
- 2026-06-20 012330.KS FAILED_FAST D5=-11.78 D20=None MFE=5.45 MAE=-18.98 lane=pullback:PASS
- 2026-06-24 AMGN WATCH D5=2.82 D20=None MFE=6.78 MAE=-1.55 lane=pullback:PASS
- 2026-06-25 KT WATCH D5=-0.67 D20=None MFE=3.03 MAE=-3.82 lane=left_side:STAGE2_PASS
- 2026-06-27 003230.KS FAILED_FAST D5=-5.34 D20=None MFE=5.6 MAE=-9.48 lane=left_side:STAGE2_PASS
- 2026-07-02 IBM PENDING D5=None D20=None MFE=7.69 MAE=-2.5 lane=pullback:WAIT

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
- 2026-06-03 402340.KS FAILED_FAST D20=12.05 MFE=60.84 MAE=-21.01 bought=False lane=strength catalyst=NOISE
- 2026-06-03 336260.KS FAILED_FAST D20=-33.1 MFE=4.49 MAE=-42.43 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-03 CMCSA WINNER D20=1.15 MFE=15.22 MAE=-5.91 bought=False lane=left_side catalyst=
- 2026-06-04 NVT FAILED_FAST D20=-9.77 MFE=6.19 MAE=-13.83 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-04 CECO WINNER D20=-0.52 MFE=24.83 MAE=-4.96 bought=False lane=strength catalyst=
- 2026-06-04 DAC FAILED_FAST D20=-3.55 MFE=2.16 MAE=-7.66 bought=False lane=strength catalyst=
- 2026-06-05 IRM FAILED_FAST D20=-7.15 MFE=8.04 MAE=-8.03 bought=False lane=strength catalyst=NOISE
- 2026-06-05 MRP NEUTRAL D20=-2.11 MFE=7.88 MAE=-3.4 bought=False lane=left_side catalyst=NOISE
- 2026-06-05 GWW WINNER D20=4.34 MFE=7.0 MAE=-1.27 bought=False lane=strength catalyst=
- 2026-06-06 GTX WINNER D20=None MFE=12.4 MAE=-2.88 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-06 DINO FAILED_FAST D20=None MFE=3.7 MAE=-11.84 bought=False lane=strength catalyst=NOISE
- 2026-06-06 DHC WINNER D20=None MFE=16.39 MAE=-2.41 bought=False lane=strength catalyst=
- 2026-06-08 GOOGL FAILED_FAST D20=None MFE=3.49 MAE=-9.11 bought=False lane=strength catalyst=
- 2026-06-08 CALY WINNER D20=None MFE=23.79 MAE=-6.07 bought=False lane=pullback catalyst=
- 2026-06-08 VIK WINNER D20=None MFE=18.78 MAE=-2.13 bought=False lane=strength catalyst=
- 2026-06-09 AD FAILED_FAST D20=None MFE=3.52 MAE=-31.6 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-09 LTH WINNER D20=None MFE=28.63 MAE=-0.67 bought=False lane=strength catalyst=NOISE
- 2026-06-09 IX WATCH D20=None MFE=4.45 MAE=-2.83 bought=False lane=strength catalyst=
- 2026-06-10 NGG WINNER D20=None MFE=4.63 MAE=-2.02 bought=False lane=pullback catalyst=
- 2026-06-10 088350.KS FAILED_FAST D20=None MFE=32.71 MAE=-12.54 bought=False lane=pullback catalyst=
- 2026-06-10 018880.KS FAILED_FAST D20=None MFE=36.34 MAE=-19.68 bought=False lane=pullback catalyst=
- 2026-06-11 329180.KS FAILED_FAST D20=None MFE=14.24 MAE=-18.89 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-11 005850.KS FAILED_FAST D20=None MFE=22.5 MAE=-18.64 bought=False lane=pullback catalyst=
- 2026-06-11 001800.KS FAILED_FAST D20=None MFE=5.19 MAE=-20.57 bought=False lane=pullback catalyst=
- 2026-06-12 005380.KS FAILED_FAST D20=None MFE=8.57 MAE=-24.71 bought=False lane=pullback catalyst=NOISE
- 2026-06-12 FTI FAILED_FAST D20=None MFE=0.57 MAE=-10.24 bought=False lane=pullback catalyst=
- 2026-06-12 036570.KS FAILED_FAST D20=None MFE=7.41 MAE=-13.5 bought=False lane=pullback catalyst=
- 2026-06-13 KT FAILED_FAST D20=None MFE=0.74 MAE=-9.08 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-13 IRDM FAILED_FAST D20=None MFE=25.97 MAE=-10.55 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-13 CSCO FAILED_FAST D20=None MFE=2.26 MAE=-7.07 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 MNST WINNER D20=None MFE=6.35 MAE=-2.43 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IX WATCH D20=None MFE=5.78 MAE=-1.59 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-15 IR WINNER D20=None MFE=8.38 MAE=-1.13 bought=False lane=left_side catalyst=
- 2026-06-16 010950.KS FAILED_FAST D20=None MFE=12.01 MAE=-20.77 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-16 005940.KS FAILED_FAST D20=None MFE=3.81 MAE=-19.03 bought=False lane=pullback catalyst=NOISE
- 2026-06-16 005387.KS FAILED_FAST D20=None MFE=1.78 MAE=-19.17 bought=False lane=pullback catalyst=
- 2026-06-17 373220.KS FAILED_FAST D20=None MFE=1.44 MAE=-22.36 bought=False lane=pullback catalyst=NOISE
- 2026-06-17 005935.KS FAILED_FAST D20=None MFE=6.18 MAE=-17.26 bought=False lane=strength catalyst=NO_DATA
- 2026-06-17 017670.KS FAILED_FAST D20=None MFE=1.01 MAE=-15.76 bought=False lane=pullback catalyst=
- 2026-06-18 080220.KQ FAILED_FAST D20=None MFE=17.25 MAE=-32.37 bought=False lane=strength catalyst=NOISE
- 2026-06-18 034220.KS FAILED_FAST D20=None MFE=4.8 MAE=-22.91 bought=False lane=pullback catalyst=
- 2026-06-18 REGN WINNER D20=None MFE=11.15 MAE=-2.47 bought=False lane=left_side catalyst=NOISE
- 2026-06-19 WMT FAILED_FAST D20=None MFE=2.75 MAE=-8.47 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-19 FFIV WINNER D20=None MFE=9.27 MAE=-2.45 bought=False lane=strength catalyst=
- 2026-06-19 TRGP WINNER D20=None MFE=4.25 MAE=-3.21 bought=False lane=strength catalyst=
- 2026-06-20 420770.KQ FAILED_FAST D20=None MFE=29.4 MAE=-18.34 bought=False lane=strength catalyst=
- 2026-06-20 031330.KQ FAILED_FAST D20=None MFE=10.62 MAE=-36.62 bought=False lane=strength catalyst=NOISE
- 2026-06-20 012330.KS FAILED_FAST D20=None MFE=5.45 MAE=-18.98 bought=False lane=pullback catalyst=NOISE
- 2026-06-22 294400.KS FAILED_FAST D20=None MFE=1.86 MAE=-19.78 bought=False lane=strength catalyst=
- 2026-06-22 440110.KQ FAILED_FAST D20=None MFE=2.5 MAE=-41.24 bought=False lane=pullback catalyst=
- 2026-06-22 003550.KS FAILED_FAST D20=None MFE=4.19 MAE=-15.2 bought=False lane=pullback catalyst=NO_DATA
- 2026-06-23 080220.KQ FAILED_FAST D20=None MFE=20.31 MAE=-28.16 bought=False lane=strength catalyst=NO_DATA
- 2026-06-23 TW FAILED_FAST D20=None MFE=5.6 MAE=-7.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-23 001040.KS WATCH D20=None MFE=6.6 MAE=-6.73 bought=False lane=left_side catalyst=NOISE
- 2026-06-24 CPRX WATCH D20=None MFE=0.25 MAE=-0.1 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 GH WINNER D20=None MFE=27.1 MAE=-3.18 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-24 AMGN WATCH D20=None MFE=6.78 MAE=-1.55 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-25 KT WATCH D20=None MFE=3.03 MAE=-3.82 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-06-25 WMB FAILED_FAST D20=None MFE=1.9 MAE=-6.99 bought=False lane=strength catalyst=
- 2026-06-25 TRGP FAILED_FAST D20=None MFE=0.84 MAE=-6.37 bought=False lane=strength catalyst=
- 2026-06-26 HEI WATCH D20=None MFE=7.03 MAE=-2.61 bought=False lane=strength catalyst=
- 2026-06-26 PANW WINNER D20=None MFE=21.03 MAE=-4.67 bought=False lane=strength catalyst=NOISE
- 2026-06-26 ROKU WATCH D20=None MFE=5.61 MAE=-0.77 bought=False lane=strength catalyst=
- 2026-06-27 NU WINNER D20=None MFE=9.52 MAE=-1.45 bought=False lane=left_side catalyst=
- 2026-06-27 APD WINNER D20=None MFE=16.04 MAE=-0.46 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-06-27 003230.KS FAILED_FAST D20=None MFE=5.6 MAE=-9.48 bought=False lane=left_side catalyst=NO_DATA
- 2026-06-29 AMD FAILED_FAST D20=None MFE=8.39 MAE=-8.18 bought=False lane=strength catalyst=
- 2026-06-29 ASML FAILED_FAST D20=None MFE=6.21 MAE=-8.8 bought=False lane=strength catalyst=
- 2026-06-29 FTNT WATCH D20=None MFE=5.24 MAE=-3.02 bought=False lane=strength catalyst=NOISE
- 2026-06-30 TSM PENDING D20=None MFE=0.3 MAE=-10.35 bought=False lane=strength catalyst=NOISE
- 2026-06-30 CRWD PENDING D20=None MFE=9.81 MAE=-4.08 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-06-30 PENG PENDING D20=None MFE=1.79 MAE=-22.87 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 009150.KS PENDING D20=None MFE=3.95 MAE=-27.35 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-01 TIGO PENDING D20=None MFE=5.81 MAE=-2.75 bought=False lane=strength catalyst=
- 2026-07-01 MRVL PENDING D20=None MFE=7.52 MAE=-18.05 bought=False lane=strength catalyst=NOISE
- 2026-07-02 F PENDING D20=None MFE=4.79 MAE=-1.05 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 IBM PENDING D20=None MFE=7.69 MAE=-2.5 bought=False lane=pullback catalyst=NOISE
- 2026-07-02 098460.KQ PENDING D20=None MFE=10.29 MAE=-12.14 bought=False lane=pullback catalyst=
- 2026-07-03 DDOG PENDING D20=None MFE=5.71 MAE=-2.88 bought=False lane=strength catalyst=
- 2026-07-03 OKTA PENDING D20=None MFE=3.09 MAE=-4.07 bought=False lane=strength catalyst=
- 2026-07-03 PANW PENDING D20=None MFE=2.98 MAE=-6.02 bought=False lane=strength catalyst=POSITIVE_REVALUATION
- 2026-07-04 001800.KS PENDING D20=None MFE=3.12 MAE=-2.14 bought=False lane=pullback catalyst=
- 2026-07-04 A PENDING D20=None MFE=1.68 MAE=-1.95 bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-04 069960.KS PENDING D20=None MFE=3.97 MAE=-6.52 bought=False lane=strength catalyst=NOISE
- 2026-07-06 003230.KS PENDING D20=None MFE=11.48 MAE=-4.37 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 PUK PENDING D20=None MFE=0.04 MAE=-2.01 bought=False lane=left_side catalyst=NOISE
- 2026-07-06 029780.KS PENDING D20=None MFE=3.18 MAE=-1.54 bought=False lane=left_side catalyst=NOISE
- 2026-07-07 CPNG PENDING D20=None MFE=5.34 MAE=-1.24 bought=False lane=left_side catalyst=
- 2026-07-07 F PENDING D20=None MFE=1.77 MAE=-0.07 bought=False lane=pullback catalyst=POSITIVE_REVALUATION
- 2026-07-07 FLEX PENDING D20=None MFE=2.31 MAE=-4.7 bought=False lane=pullback catalyst=
- 2026-07-08 EQT PENDING D20=None MFE=None MAE=None bought=False lane=left_side catalyst=POSITIVE_REVALUATION
- 2026-07-08 326030.KS PENDING D20=None MFE=None MAE=None bought=False lane=left_side catalyst=NOISE
- 2026-07-08 000240.KS PENDING D20=None MFE=None MAE=None bought=False lane=pullback catalyst=
