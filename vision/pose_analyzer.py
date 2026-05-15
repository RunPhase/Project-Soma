"""
pose_analyzer.py
────────────────
Thread 1 — 캠 분석 파트 (내 담당)

책임:
  - OpenCV 로 웹캠 프레임 캡처
  - MediaPipe Pose 로 랜드마크 추출
  - neck_angle / head_pitch(PnP) / face_width / shoulder_tilt 계산
  - Calibrator 와 연동해 캘리브레이션 샘플 공급
  - shared_state 업데이트 (state_lock 보호)

사용 랜드마크 (Pose 내장, 추가 모델 불필요):
  nose(0), left_eye(2), right_eye(5),
  left_ear(7), right_ear(8),
  mouth_left(9), mouth_right(10),
  left_shoulder(11), right_shoulder(12)
"""

import math
import time
import threading
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

from shared_state import shared_state, state_lock

# ── MediaPipe Pose 랜드마크 인덱스 ────────────────────────────────────────────
LM = {
    "nose":           0,
    "left_eye":       2,
    "right_eye":      5,
    "left_ear":       7,
    "right_ear":      8,
    "mouth_left":     9,
    "mouth_right":   10,
    "left_shoulder": 11,
    "right_shoulder":12,
}

# ── PnP 3D 기준 얼굴 모델 포인트 (mm, 코 끝 원점) ────────────────────────────
# 순서: nose, left_eye, right_eye, left_ear, right_ear, mouth_left, mouth_right
# 참고: 얇은 얼굴 근사 모델 — MVP 수준에서 pitch 추출에 충분
_FACE_3D = np.array([
    (  0.0,   0.0,   0.0),   # 코 끝
    (-30.0, -30.0, -30.0),   # 왼쪽 눈
    ( 30.0, -30.0, -30.0),   # 오른쪽 눈
    (-65.0,   0.0, -65.0),   # 왼쪽 귀
    ( 65.0,   0.0, -65.0),   # 오른쪽 귀
    (-25.0,  30.0, -30.0),   # 왼쪽 입꼬리
    ( 25.0,  30.0, -30.0),   # 오른쪽 입꼬리
], dtype=np.float64)

_PNP_KEYS = ["nose", "left_eye", "right_eye",
             "left_ear", "right_ear", "mouth_left", "mouth_right"]

_DIST_COEFFS = np.zeros((4, 1), dtype=np.float64)  # 렌즈 왜곡 없다고 가정


# ─────────────────────────────────────────────────────────────────────────────
class PoseAnalyzer:
    """
    MediaPipe Pose 기반 자세 분석기.

    사용 흐름:
        analyzer = PoseAnalyzer()
        stop_event = threading.Event()
        t = threading.Thread(target=analyzer.run,
                             args=(stop_event, calibrator), daemon=True)
        t.start()
        ...
        stop_event.set()
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index

        # MediaPipe Pose 초기화
        self._mp_pose = mp.solutions.pose
        self._pose = self._mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,       # 0=lite, 1=full, 2=heavy
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        # 카메라 내부 파라미터 (첫 프레임에서 해상도 확인 후 초기화)
        self._camera_matrix: Optional[np.ndarray] = None

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _init_camera_matrix(self, width: int, height: int) -> None:
        """이미지 해상도 기반 카메라 행렬 근사 (캘리브레이션 없는 MVP 용)."""
        focal = float(width)          # fx ≈ fy ≈ image width (경험적 근사)
        cx, cy = width / 2.0, height / 2.0
        self._camera_matrix = np.array([
            [focal, 0.0, cx],
            [0.0, focal, cy],
            [0.0, 0.0,  1.0],
        ], dtype=np.float64)

    @staticmethod
    def _lm_px(landmarks, key: str, w: int, h: int) -> tuple:
        """랜드마크 → 픽셀 좌표 변환."""
        lm = landmarks[LM[key]]
        return lm.x * w, lm.y * h

    # ── 지표 계산 ──────────────────────────────────────────────────────────────

    def _neck_angle(self, lms, w: int, h: int) -> float:
        """
        목 전방 기울기 (도°).

        계산:
          mid_shoulder = (left_shoulder + right_shoulder) / 2
          vector = nose - mid_shoulder  (이미지 좌표)
          angle = arctan2(|dx|, -dy)
            → 코가 어깨 중심 바로 위: 0°
            → 코가 좌우로 치우치거나 목이 앞으로 숙을수록 증가

        이미지 좌표는 y 가 아래로 증가하므로 -dy 로 뒤집어 "위" 방향을 양수 처리.
        """
        nx, ny = self._lm_px(lms, "nose", w, h)
        lsx, lsy = self._lm_px(lms, "left_shoulder", w, h)
        rsx, rsy = self._lm_px(lms, "right_shoulder", w, h)

        mid_x = (lsx + rsx) / 2.0
        mid_y = (lsy + rsy) / 2.0

        dx = nx - mid_x
        dy = ny - mid_y   # 코가 어깨보다 위 → 음수

        return math.degrees(math.atan2(abs(dx), -dy))

    def _head_pitch(self, lms, w: int, h: int) -> Optional[float]:
        """
        PnP(Perspective-n-Point) 로 head pitch 추출 (도°).

        양수: 머리가 앞으로 숙어짐 (거북목 보조 지표).
        None: solvePnP 실패 시.
        """
        if self._camera_matrix is None:
            return None

        img_pts = np.array(
            [self._lm_px(lms, k, w, h) for k in _PNP_KEYS],
            dtype=np.float64,
        )

        ok, rvec, _ = cv2.solvePnP(
            _FACE_3D, img_pts,
            self._camera_matrix, _DIST_COEFFS,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return None

        rot, _ = cv2.Rodrigues(rvec)

        # ZYX Euler angle 추출
        sy = math.sqrt(rot[0, 0] ** 2 + rot[1, 0] ** 2)
        if sy > 1e-6:
            pitch = math.atan2(rot[2, 1], rot[2, 2])
        else:
            pitch = math.atan2(-rot[1, 2], rot[1, 1])

        return math.degrees(pitch)

    def _face_width(self, lms, w: int, h: int) -> float:
        """
        귀 간 유클리드 거리 (픽셀).
        카메라 거리 근사치로 사용. 좌우 회전에도 비교적 안정적.
        """
        lx, ly = self._lm_px(lms, "left_ear", w, h)
        rx, ry = self._lm_px(lms, "right_ear", w, h)
        return math.hypot(rx - lx, ry - ly)

    def _shoulder_tilt(self, lms, w: int, h: int) -> float:
        """
        어깨 좌우 기울기 비율 (0 ~ 1, 해상도 독립).

        tilt_ratio = |left_y - right_y| / shoulder_width
          → 0: 완전 수평
          → 클수록 기울어짐
        """
        lx, ly = self._lm_px(lms, "left_shoulder", w, h)
        rx, ry = self._lm_px(lms, "right_shoulder", w, h)

        diff_y = abs(ly - ry)
        width = math.hypot(rx - lx, ry - ly)

        return diff_y / width if width > 1e-6 else 0.0

    # ── 프레임 분석 ────────────────────────────────────────────────────────────

    def analyze_frame(self, frame: np.ndarray) -> Optional[dict]:
        """
        단일 프레임 분석 → 지표 dict 반환. 랜드마크 미감지 시 None.

        Returns:
            {
                "neck_angle":    float,  # 도°
                "head_pitch":    float,  # 도° (PnP 실패 시 0.0 대체)
                "face_width":    float,  # 픽셀
                "shoulder_tilt": float,  # 0~1 비율
            }
        """
        h, w = frame.shape[:2]

        if self._camera_matrix is None:
            self._init_camera_matrix(w, h)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)

        if not result.pose_landmarks:
            return None

        lms = result.pose_landmarks.landmark

        return {
            "neck_angle":    self._neck_angle(lms, w, h),
            "head_pitch":    self._head_pitch(lms, w, h) or 0.0,
            "face_width":    self._face_width(lms, w, h),
            "shoulder_tilt": self._shoulder_tilt(lms, w, h),
        }

    # ── Thread 1 진입점 ────────────────────────────────────────────────────────

    def run(
        self,
        stop_event: threading.Event,
        calibrator=None,       # calibrator.Calibrator 인스턴스 (선택)
        debug: bool = False,   # True 시 OpenCV 미리보기 창 표시 (개발용)
    ) -> None:
        """
        Thread 1 메인 루프.

        - OpenCV 로 프레임 캡처
        - analyze_frame() 호출
        - calibrator.add_sample() 에 샘플 공급
        - shared_state 업데이트 (state_lock 보호)
        - stop_event.set() 으로 종료

        Args:
            stop_event:  threading.Event — set() 시 루프 종료
            calibrator:  Calibrator 인스턴스, None 이면 캘리브레이션 없이 동작
            debug:       True 면 "PoseDebug" 창에 지표 오버레이 표시
        """
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            print(f"[PoseAnalyzer] 카메라 {self.camera_index} 열기 실패")
            return

        print(f"[PoseAnalyzer] 카메라 {self.camera_index} 시작")

        try:
            while not stop_event.is_set():
                ret, frame = cap.read()
                if not ret:
                    print("[PoseAnalyzer] 프레임 수신 실패, 재시도...")
                    time.sleep(0.033)
                    continue

                metrics = self.analyze_frame(frame)
                ts = time.time()

                # ── 캘리브레이션 샘플 공급 ──────────────────────────────────
                if calibrator is not None and calibrator.is_calibrating():
                    if metrics:
                        calibrator.add_sample(metrics)

                # ── shared_state 업데이트 ────────────────────────────────────
                with state_lock:
                    if metrics:
                        shared_state["neck_angle"]    = metrics["neck_angle"]
                        shared_state["head_pitch"]    = metrics["head_pitch"]
                        shared_state["face_width"]    = metrics["face_width"]
                        shared_state["shoulder_tilt"] = metrics["shoulder_tilt"]
                        shared_state["cam_valid"]     = True
                    else:
                        shared_state["cam_valid"] = False

                    shared_state["cam_timestamp"] = ts
                    shared_state["calibrated"] = (
                        calibrator.is_done() if calibrator else False
                    )

                # ── 디버그 창 ────────────────────────────────────────────────
                if debug:
                    self._draw_debug(frame, metrics)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        stop_event.set()
                        break

        finally:
            cap.release()
            if debug:
                cv2.destroyAllWindows()
            print("[PoseAnalyzer] 스레드 종료")

    # ── 디버그 헬퍼 ────────────────────────────────────────────────────────────

    @staticmethod
    def _draw_debug(frame: np.ndarray, metrics: Optional[dict]) -> None:
        """프레임에 지표 텍스트 오버레이 후 imshow."""
        if metrics:
            lines = [
                f"neck  : {metrics['neck_angle']:6.1f} deg",
                f"pitch : {metrics['head_pitch']:6.1f} deg",
                f"faceW : {metrics['face_width']:6.1f} px",
                f"shld  : {metrics['shoulder_tilt']:6.3f}",
            ]
        else:
            lines = ["[No pose detected]"]

        y = 30
        for line in lines:
            cv2.putText(frame, line, (10, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 80), 2)
            y += 28

        cv2.imshow("PoseDebug", frame)
