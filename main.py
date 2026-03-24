"""Roy-브리프봇 — 메인 오케스트레이션.

현재: M2(섹터 로테이션 맵) + M3(역발상 필터) 실행.
향후: M1 → M2 → M3 순으로 체이닝.
"""

from __future__ import annotations

import json
import os
import sys

from src.state import load_state, save_state, prune_m2_history
from src.modules.m2_rotation import run_m2
from src.modules.m3_contrarian import run_m3
from src.telegram import send_telegram
from src.utils import now_kst, today_kst_str

# 프로젝트 루트
ROOT = os.path.dirname(os.path.abspath(__file__))
ETF_MAP_PATH = os.path.join(ROOT, "config", "etf_map.json")


def main() -> None:
    print(f"[INFO] Roy-브리프봇 시작: {now_kst().strftime('%Y-%m-%d %H:%M:%S')} KST")

    # 1. etf_map 로드
    if not os.path.exists(ETF_MAP_PATH):
        print(f"[ERROR] etf_map.json 없음: {ETF_MAP_PATH}")
        sys.exit(1)

    with open(ETF_MAP_PATH, "r", encoding="utf-8") as f:
        etf_map = json.load(f)

    # 2. state 로드
    state = load_state()

    # ── M2 실행 ──
    print("[INFO] M2 섹터 로테이션 맵 실행 중...")
    m2_result = run_m2(etf_map, state)

    # state에 M2 히스토리 저장 (M3가 이중확인에 사용)
    today_str = today_kst_str()
    if m2_result["today_snapshot"]:
        state.setdefault("m2_history", {})[today_str] = m2_result["today_snapshot"]
    prune_m2_history(state)

    # ── M3 실행 (M2 state 반영 후) ──
    print("[INFO] M3 역발상 필터 실행 중...")
    m3_result = run_m3(state)

    # 3. state 저장
    save_state(state)

    # 4. 텔레그램 전송 — M2 + M3 합산
    tg_parts = []
    if m2_result["telegram_text"]:
        tg_parts.append(m2_result["telegram_text"])
    if m3_result["telegram_text"]:
        tg_parts.append(m3_result["telegram_text"])

    if tg_parts:
        tg_text = "\n\n━━━━━━━━━━━━━━━\n\n".join(tg_parts)
        print("[INFO] 텔레그램 전송 중...")
        ok = send_telegram(tg_text)
        print(f"[INFO] 텔레그램 전송 {'성공' if ok else '실패'}")
    else:
        print("[WARN] 전송할 텍스트 없음")

    # 5. LLM 컨텍스트 텍스트 (로그 + 나중에 M1이 사용)
    print(f"\n{'='*60}")
    print("[M2 LLM Context]")
    print(m2_result["context_text"])
    print(f"\n{'='*60}")
    print("[M3 LLM Context]")
    print(m3_result["context_text"])
    print(f"{'='*60}")

    # 전환 이벤트 로그 (M2)
    if m2_result["transitions"]:
        print(f"\n[INFO] M2 분면 전환 {len(m2_result['transitions'])}건 감지:")
        for t in m2_result["transitions"]:
            print(f"  - {t['ticker']} ({t['label']}): {t['transition']}")
    else:
        print("\n[INFO] M2 분면 전환 없음")

    # M3 결과 로그
    if m3_result["candidates"]:
        print(f"\n[INFO] M3 역발상 후보 {len(m3_result['candidates'])}개:")
        for c in m3_result["candidates"]:
            dc = " ⚡M2" if c["double_confirmed"] else ""
            print(f"  - {c['ticker']} ({c['label']}): DD {c['dd_pct']}% [{c['dd_grade']}]{dc}")
    else:
        print("\n[INFO] M3 역발상 후보 없음")

    print(f"\n[INFO] 완료: {now_kst().strftime('%H:%M:%S')} KST")


if __name__ == "__main__":
    main()
