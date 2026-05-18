"""
main.py
───────
프로덕션 진입점.

PyQt6 가 메인 스레드를 점유하고,
PoseAnalyzer(Thread 1) 는 daemon 스레드로 실행.

사용법:
  OPENCV_AVFOUNDATION_SKIP_AUTH=1 python vision/main.py
  python main.py --cam 1
"""

import argparse
import sys
import threading

from PyQt6.QtWidgets import QApplication

from calibrator import Calibrator
from desktop_pet import DesktopPet
from pose_analyzer import PoseAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser(description="Project Soma — 데스크탑 펫 모드")
    parser.add_argument("--cam", type=int, default=0, help="카메라 인덱스 (기본 0)")
    args = parser.parse_args()

    calibrator = Calibrator()
    analyzer   = PoseAnalyzer(camera_index=args.cam)
    stop_event = threading.Event()

    if not calibrator.is_done():
        calibrator.start()

    t_pose = threading.Thread(
        target=analyzer.run,
        args=(stop_event, calibrator),
        name="Thread-1-Cam",
        daemon=True,
    )
    t_pose.start()

    # PyQt6 는 메인 스레드 전용
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    pet = DesktopPet(calibrator=calibrator)
    pet.show()

    exit_code = app.exec()

    stop_event.set()
    t_pose.join(timeout=3.0)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
