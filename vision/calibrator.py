"""
calibrator.py
─────────────
캘리브레이션 로직.

동작 흐름:
  1. calibrator.start()  →  "올바른 자세" 안내 후 측정 시작
  2. Thread 1 이 매 프레임마다 calibrator.add_sample(metrics) 호출
  3. CALIB_DURATION 초 경과 → 평균 baseline 자동 산출 + 저장
  4. calibrator.is_done() == True 가 되면 판정 활성화

재캘리브레이션:
  calibrator.recalibrate()  →  start() 재호출과 동일

저장:
  baseline.json (스크립트 위치 기준)
  앱 재시작 시 자동 불러오기
"""

import json
import math
import threading
import time
from pathlib import Path
from typing import Optional

# ── 상수 ──────────────────────────────────────────────────────────────────────
CALIB_DURATION = 3.0  # 초 — 계획서 스펙
_BASELINE_FILE = Path(__file__).parent / "baseline.json"
_METRIC_KEYS = ("head_lateral_tilt", "neck_compression", "head_pitch", "face_width", "shoulder_tilt")


# ─────────────────────────────────────────────────────────────────────────────
class Calibrator:
    """
    캘리브레이션 관리자.

    Thread-safe: 내부 Lock 으로 모든 상태 보호.
    """

    def __init__(self, baseline_path: Optional[Path] = None):
        self._lock = threading.Lock()
        self._baseline_path = baseline_path or _BASELINE_FILE

        self._calibrating: bool = False
        self._done: bool = False
        self._start_time: Optional[float] = None
        self._samples: list = []
        self._baseline: dict = {}

        # 앱 시작 시 저장된 baseline 자동 불러오기
        self._load()

    # ── 상태 조회 (외부에서 락 없이 호출 가능) ────────────────────────────────

    def is_calibrating(self) -> bool:
        with self._lock:
            return self._calibrating

    def is_done(self) -> bool:
        with self._lock:
            return self._done

    def progress(self) -> float:
        """캘리브레이션 진행률 0.0 ~ 1.0."""
        with self._lock:
            if not self._calibrating or self._start_time is None:
                return 0.0
            elapsed = time.time() - self._start_time
            return min(elapsed / CALIB_DURATION, 1.0)

    def get_baseline(self) -> dict:
        """현재 baseline 딕셔너리 복사본 반환."""
        with self._lock:
            return dict(self._baseline)

    # ── 캘리브레이션 시작 ─────────────────────────────────────────────────────

    def start(self) -> None:
        """
        캘리브레이션 시작.
        이전 샘플 초기화, calibrated 플래그 False 로 복원.
        캘리브레이션 중에는 shared_state["calibrated"] 가 False 이므로
        Main Thread 판정이 자동 차단됨.
        """
        with self._lock:
            self._calibrating = True
            self._done = False
            self._start_time = time.time()
            self._samples = []
        print("[Calibrator] 시작 — 올바른 자세로 3초간 앉아주세요")

    def recalibrate(self) -> None:
        """재캘리브레이션 트리거 (단축키 / UI 버튼에서 호출)."""
        print("[Calibrator] 재캘리브레이션 시작")
        self.start()

    # ── 샘플 수집 ─────────────────────────────────────────────────────────────

    def add_sample(self, metrics: dict) -> None:
        """
        Thread 1 에서 매 프레임 호출.

        CALIB_DURATION 경과 시 자동으로 baseline 산출 후 저장.
        락 밖에서 파일 I/O 를 수행해 Thread 1 블로킹을 최소화.
        """
        need_save = False

        with self._lock:
            if not self._calibrating or self._start_time is None:
                return

            elapsed = time.time() - self._start_time

            # 숫자 지표만 필터링해서 저장
            filtered = {k: float(metrics[k]) for k in _METRIC_KEYS if k in metrics}
            self._samples.append(filtered)

            if elapsed >= CALIB_DURATION:
                self._finalize_locked()
                need_save = self._done  # 성공 시에만 저장

        # 락 해제 후 파일 저장 (Thread 1 블로킹 최소화)
        if need_save:
            self._save()

    def _finalize_locked(self) -> None:
        """
        락 보유 상태에서 호출. baseline 평균 계산.
        샘플이 없으면 실패 처리.
        """
        if not self._samples:
            print("[Calibrator] 샘플 없음 — 캘리브레이션 실패 (다시 시도해주세요)")
            self._calibrating = False
            return

        baseline = {}
        for k in _METRIC_KEYS:
            vals = [s[k] for s in self._samples if k in s]
            baseline[k] = sum(vals) / len(vals) if vals else 0.0

        self._baseline = baseline
        self._calibrating = False
        self._done = True

        print(
            f"[Calibrator] 완료 ({len(self._samples)} 샘플)\n"
            f"  head_lateral_tilt = {baseline.get('head_lateral_tilt', 0):.2f}°\n"
            f"  neck_compression  = {baseline.get('neck_compression', 0):.4f}\n"
            f"  head_pitch        = {baseline.get('head_pitch', 0):.2f}°\n"
            f"  face_width        = {baseline.get('face_width', 0):.1f} px\n"
            f"  shoulder_tilt     = {baseline.get('shoulder_tilt', 0):.4f}"
        )

    # ── 편차 계산 헬퍼 (Main Thread 판정 보조) ────────────────────────────────

    def deviations(self, current: dict) -> dict:
        """
        현재 지표와 baseline 의 편차 딕셔너리 반환.

        Returns:
            {
                "lateral_deviation":     float,  # 도° — 좌우 기울기 편차
                "compression_deviation": float,  # 비율 — 음수면 거북목 방향
                "pitch_deviation":       float,  # 도° — 앞뒤 기울기 편차
                "face_deviation":        float,  # 비율 (+ 면 카메라에 가까워짐)
                "tilt_deviation":        float,  # 비율 — 어깨 기울기 편차
            }

        캘리브레이션 미완료 시 모든 값 0.0.
        """
        with self._lock:
            if not self._done or not self._baseline:
                return {
                    "lateral_deviation":     0.0,
                    "compression_deviation": 0.0,
                    "pitch_deviation":       0.0,
                    "face_deviation":        0.0,
                    "tilt_deviation":        0.0,
                }
            b = self._baseline

        face_base = b.get("face_width", 1.0) or 1.0  # 0 나누기 방지

        return {
            "lateral_deviation":     current.get("head_lateral_tilt", 0.0) - b.get("head_lateral_tilt", 0.0),
            "compression_deviation": current.get("neck_compression", 0.0)  - b.get("neck_compression", 0.0),
            "pitch_deviation":       current.get("head_pitch", 0.0)         - b.get("head_pitch", 0.0),
            "face_deviation":        (current.get("face_width", 0.0)        - face_base) / face_base,
            "tilt_deviation":        current.get("shoulder_tilt", 0.0)      - b.get("shoulder_tilt", 0.0),
        }

    # ── 파일 I/O ──────────────────────────────────────────────────────────────

    def _save(self) -> None:
        """baseline 을 JSON 파일로 저장."""
        try:
            with open(self._baseline_path, "w", encoding="utf-8") as f:
                json.dump(self._baseline, f, indent=2, ensure_ascii=False)
            print(f"[Calibrator] baseline 저장 완료: {self._baseline_path}")
        except OSError as e:
            print(f"[Calibrator] 저장 실패: {e}")

    def _load(self) -> None:
        """저장된 baseline JSON 불러오기."""
        if not self._baseline_path.exists():
            print("[Calibrator] 저장된 baseline 없음 — 캘리브레이션이 필요합니다")
            return
        try:
            with open(self._baseline_path, encoding="utf-8") as f:
                data = json.load(f)
            # 필수 키 검증
            missing = [k for k in _METRIC_KEYS if k not in data]
            if missing:
                print(f"[Calibrator] baseline 키 누락 {missing} — 재캘리브레이션 필요")
                return
            self._baseline = data
            self._done = True
            print(
                f"[Calibrator] baseline 불러오기 완료\n"
                f"  lateral={data['head_lateral_tilt']:.2f}°  "
                f"compress={data['neck_compression']:.4f}  "
                f"pitch={data['head_pitch']:.2f}°  "
                f"faceW={data['face_width']:.1f}px  "
                f"tilt={data['shoulder_tilt']:.4f}"
            )
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"[Calibrator] 불러오기 실패: {e}")
