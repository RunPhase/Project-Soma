"""
make_transparent.py
───────────────────
Gemini 등이 알파 채널 없이 체커보드 패턴을 픽셀로 그려넣은 PNG 를 후처리.

체커보드 두 가지 회색만 정밀하게 매칭해 알파=0 으로 변환.
원본은 *.orig.png 로 백업.

사용:
  python vision/tools/make_transparent.py vision/assets/cat.png
"""

import sys
import shutil
from pathlib import Path

import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QImage

# 체커보드 중심 색 (관찰값) + 허용 오차
_CHECKER_COLORS = [
    np.array([135, 145, 148], dtype=np.int16),  # 어두운 회색
    np.array([197, 200, 205], dtype=np.int16),  # 밝은 회색
]
_TOLERANCE = 14


def make_transparent(src: Path) -> None:
    backup = src.with_suffix(".orig.png")
    if not backup.exists():
        shutil.copy(src, backup)
        print(f"백업: {backup}")

    # 안정적인 RGBA8888 포맷으로 로드
    img = QImage(str(src)).convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    print(f"원본: {w}x{h}, alpha={img.hasAlphaChannel()}")

    ptr = img.bits()
    ptr.setsize(h * w * 4)
    arr = np.frombuffer(ptr, np.uint8).reshape(h, w, 4).copy()

    rgb = arr[:, :, :3].astype(np.int16)
    mask = np.zeros((h, w), dtype=bool)
    for col in _CHECKER_COLORS:
        mask |= np.all(np.abs(rgb - col) <= _TOLERANCE, axis=2)

    removed = int(mask.sum())
    total = w * h
    print(f"제거 대상: {removed:,} / {total:,} px ({removed/total*100:.1f}%)")

    arr[mask, :] = 0  # RGBA 전체 0 (알파 + 색)

    out = QImage(arr.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    out.save(str(src))
    print(f"저장 완료: {src}")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("vision/assets/cat.png")
    app = QApplication(sys.argv)
    make_transparent(target)
