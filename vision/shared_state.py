"""
shared_state.py
───────────────
멀티스레드 공유 상태 정의.

모든 스레드는 state_lock 을 획득한 뒤에만 shared_state 를 읽거나 쓴다.

사용 예:
    from shared_state import shared_state, state_lock

    with state_lock:
        shared_state["head_lateral_tilt"] = 12.3
        shared_state["cam_timestamp"] = time.time()
"""

import threading

# ── 락 ────────────────────────────────────────────────────────────────────────
state_lock = threading.Lock()

# ── 공유 상태 딕셔너리 ─────────────────────────────────────────────────────────
shared_state: dict = {
    # ── Thread 1 — 캠 분석 (내 파트) ───────────────────────────────────────────
    "head_lateral_tilt": 0.0,  # 머리 좌우 기울기 (도°). 어깨 중심 기준 수직 편차.
    "neck_compression":  0.0,  # 코-어깨 거리/face_width 비율. 작을수록 거북목.
    "head_pitch":        0.0,  # 머리 앞뒤 숙임 각도 (도°). PnP 기반.
    "face_width":        0.0,  # 귀 간 픽셀 거리. 카메라 거리 근사치.
    "shoulder_tilt":     0.0,  # 어깨 좌우 기울기 비율 (0 ~ 1). 해상도 독립.

    "cam_timestamp": 0.0,   # 마지막 캠 업데이트 unix timestamp
    "cam_valid":     False, # 현재 프레임에서 랜드마크를 감지했는지 여부
    "calibrated":    False, # 캘리브레이션 완료 여부

    # ── Thread 2 — 압력 분석 (팀원 파트, 자리만 예약) ───────────────────────────
    "pressure_left":      0.0,   # 왼쪽 압력 합산
    "pressure_right":     0.0,   # 오른쪽 압력 합산
    "pressure_total":     0.0,   # 전체 압력 합산 (≈ 0 이면 자리 이탈)
    "pressure_ratio":     1.0,   # 좌우 편중 비율
    "pressure_timestamp": 0.0,   # 마지막 압력 업데이트 unix timestamp
    "pressure_valid":     False, # 압력 데이터 유효 여부
}
