"""
demo.py
───────
캠 분석 레이어 단독 테스트 스크립트.
Main Thread / 아두이노 연동 없이 Thread 1 파트만 돌려볼 수 있다.

사용법:
  OPENCV_AVFOUNDATION_SKIP_AUTH=1 python vision/demo.py --debug  
  python demo.py          # 카메라 0, 디버그 창 없음
  python demo.py --debug  # OpenCV 미리보기 창 표시 (q 로 종료)
  python demo.py --cam 1  # 카메라 인덱스 지정

캘리브레이션:
  실행 후 콘솔에서 c + Enter → 재캘리브레이션 시작
  q + Enter → 종료
"""

import argparse
import queue
import threading
import time

import cv2

from calibrator import Calibrator
from pose_analyzer import PoseAnalyzer
from shared_state import shared_state, state_lock


def print_state_loop(stop_event: threading.Event) -> None:
    """1초마다 shared_state 를 콘솔에 출력 (모니터링용)."""
    while not stop_event.is_set():
        time.sleep(1.0)
        with state_lock:
            valid    = shared_state["cam_valid"]
            calib    = shared_state["calibrated"]
            lateral  = shared_state["head_lateral_tilt"]
            compress = shared_state["neck_compression"]
            pitch    = shared_state["head_pitch"]
            faceW    = shared_state["face_width"]
            tilt     = shared_state["shoulder_tilt"]
            ts       = shared_state["cam_timestamp"]

        status = "OK" if valid else "NO POSE"
        calib_str = "calibrated" if calib else "NOT calibrated"
        print(
            f"[{time.strftime('%H:%M:%S')}] {status} | {calib_str} | "
            f"lateral={lateral:5.1f}° compress={compress:.3f} "
            f"pitch={pitch:5.1f}° faceW={faceW:5.1f}px tilt={tilt:.3f}"
        )


def keyboard_input_loop(calibrator: Calibrator, stop_event: threading.Event) -> None:
    """
    콘솔 입력 대기.
      c → 재캘리브레이션
      q → 전체 종료
    """
    print("\n[입력] c: 재캘리브레이션  |  q: 종료\n")
    while not stop_event.is_set():
        try:
            cmd = input().strip().lower()
        except EOFError:
            break
        if cmd == "c":
            calibrator.recalibrate()
        elif cmd == "q":
            stop_event.set()


def main() -> None:
    parser = argparse.ArgumentParser(description="캠 분석 레이어 단독 테스트")
    parser.add_argument("--cam",   type=int, default=0, help="카메라 인덱스 (기본 0)")
    parser.add_argument("--debug", action="store_true",  help="OpenCV 미리보기 창 표시")
    args = parser.parse_args()

    # ── 초기화 ────────────────────────────────────────────────────────────────
    calibrator  = Calibrator()
    analyzer    = PoseAnalyzer(camera_index=args.cam)
    stop_event  = threading.Event()
    debug_queue = queue.Queue(maxsize=2) if args.debug else None

    # baseline 없으면 즉시 캘리브레이션 시작
    if not calibrator.is_done():
        calibrator.start()

    # ── 스레드 시작 ───────────────────────────────────────────────────────────
    t_pose = threading.Thread(
        target=analyzer.run,
        args=(stop_event, calibrator),
        kwargs={"debug_queue": debug_queue},
        name="Thread-1-Cam",
        daemon=True,
    )
    t_monitor = threading.Thread(
        target=print_state_loop,
        args=(stop_event,),
        name="Thread-Monitor",
        daemon=True,
    )
    t_input = threading.Thread(
        target=keyboard_input_loop,
        args=(calibrator, stop_event),
        name="Thread-Input",
        daemon=True,
    )

    t_pose.start()
    t_monitor.start()
    t_input.start()

    # ── 메인 스레드: imshow 루프 (macOS는 GUI를 메인 스레드에서만 허용) ──────
    try:
        while not stop_event.is_set():
            if debug_queue is not None:
                try:
                    frame, _ = debug_queue.get(timeout=0.05)
                    cv2.imshow("PoseDebug", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        stop_event.set()
                except queue.Empty:
                    pass
            else:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n[demo] Ctrl+C — 종료 중...")
        stop_event.set()
    finally:
        if args.debug:
            cv2.destroyAllWindows()

    t_pose.join(timeout=3.0)
    print("[demo] 종료 완료")


if __name__ == "__main__":
    main()
