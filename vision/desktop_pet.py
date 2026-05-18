"""
desktop_pet.py
──────────────
화면을 돌아다니며 자세 상태를 시각적으로 피드백하는 데스크탑 펫.

스프라이트 추출은 알파 채널 기반 Connected Component 분석으로 자동 처리.
그리드 정렬이나 프레임 좌표를 명시할 필요 없이, 각 고양이 오브젝트가
자동으로 인식되어 행(Y 좌표)별로 그룹핑된다.

자세 상태 전이:
  GOOD ──(임계값 초과)──▶ WARNING ──(5초 지속)──▶ ALERT
  GOOD ◀──(정상 복귀)────────────────────────────
"""

import math
import platform
import random
import time
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QImage, QFont, QPolygon
from PyQt6.QtWidgets import QWidget, QApplication

from shared_state import shared_state, state_lock

# ── 스프라이트 설정 (교체 시 이 블록만 수정) ─────────────────────────────────
SPRITE_CONFIG = {
    "path":      Path(__file__).parent / "assets" / "cat.png",
    "rows":      4,         # 자동 행 분류 대상 수
    "display_w": 96,
    "display_h": 96,
    "min_area":  5000,      # anchor(캐릭터 본체) 최소 픽셀 면적
    "animations": {
        "idle":    {"row": 0, "fps": 6},
        "walk":    {"row": 1, "fps": 10},
        "alert":   {"row": 2, "fps": 8},
        "warning": {"row": 3, "fps": 7},
    },
}

# ── 이동 / 상태 상수 ──────────────────────────────────────────────────────────
_SPEED            = 1.8    # px / frame (30fps ≈ 54px/s)
_IDLE_MIN_MS      = 800
_IDLE_MAX_MS      = 2500
_WARN_TO_ALERT_SEC = 5.0
_FPS_MS           = 33     # ~30fps

_PITCH_THRESH  = 15.0      # head_pitch 절댓값 (도°) 초과 시 경고
_TILT_THRESH   = 0.15      # shoulder_tilt 초과 시 경고
_COMPRESS_DEV  = -0.25     # neck_compression 편차 (캘리브레이션 완료 시)


# ─────────────────────────────────────────────────────────────────────────────
class _State:
    GOOD    = "good"
    WARNING = "warning"
    ALERT   = "alert"


class _SpriteSheet:
    """
    알파 채널 기반 자동 스프라이트 추출기.

    동작:
      1. 알파 채널 이진화 (A > 10 → 고양이 픽셀)
      2. cv2.connectedComponentsWithStats 로 연결된 픽셀 덩어리 탐지
      3. 큰 component(anchor) 와 작은 fragment(X 마크, Z, 눈물 등) 분리
      4. 각 fragment 를 가장 가까운 anchor 에 bbox 병합 (꼬리/이모지 보존)
      5. Y 좌표 기준으로 rows 개 행에 그룹핑 (가장 큰 간격 N-1개로 분할)
      6. 각 행에서 X 좌표로 정렬
      7. 각 오브젝트 bbox 로 crop, display 크기로 비율 유지 스케일링
    """

    _FRAGMENT_MIN_AREA = 200    # 진짜 노이즈(<200px) 만 무시
    _MERGE_DIST_PX     = 50     # fragment 가 anchor 와 이 거리 이내면 흡수

    def __init__(self, config: dict):
        self._anims = config["animations"]
        n_rows   = config["rows"]
        dw       = config["display_w"]
        dh       = config["display_h"]
        min_area = config.get("min_area", 5000)

        # 1) 이미지 로드 → numpy RGBA
        img = QImage(str(config["path"])).convertToFormat(QImage.Format.Format_RGBA8888)
        w, h = img.width(), img.height()
        ptr = img.bits()
        ptr.setsize(h * w * 4)
        arr = np.frombuffer(ptr, np.uint8).reshape(h, w, 4).copy()

        # 2) 알파 이진화 + Connected Components
        mask = (arr[:, :, 3] > 10).astype(np.uint8)
        n_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

        # 3) anchor / fragment 분리
        anchors:   list[list[int]] = []      # 캐릭터 본체
        fragments: list[tuple]     = []      # X·Z·하트·눈물 등 부속물
        for i in range(1, n_labels):
            x, y, bw, bh, area = stats[i]
            if area >= min_area:
                anchors.append([int(x), int(y), int(bw), int(bh)])
            elif area >= self._FRAGMENT_MIN_AREA:
                fragments.append((int(x), int(y), int(bw), int(bh)))

        if len(anchors) < n_rows:
            raise ValueError(
                f"감지된 anchor {len(anchors)} 개 < rows {n_rows}. "
                f"min_area({min_area}) 가 너무 큰지 확인하세요."
            )

        # 4) fragment 흡수
        merged = 0
        for fx, fy, fw, fh in fragments:
            best_i, best_d = -1, float("inf")
            for i, (ax, ay, aw, ah) in enumerate(anchors):
                # bbox 간 최소 거리
                dx = max(0, ax - (fx + fw), fx - (ax + aw))
                dy = max(0, ay - (fy + fh), fy - (ay + ah))
                d = (dx * dx + dy * dy) ** 0.5
                if d < best_d:
                    best_d, best_i = d, i
            if best_d <= self._MERGE_DIST_PX:
                ax, ay, aw, ah = anchors[best_i]
                nx = min(ax, fx); ny = min(ay, fy)
                nw = max(ax + aw, fx + fw) - nx
                nh = max(ay + ah, fy + fh) - ny
                anchors[best_i] = [nx, ny, nw, nh]
                merged += 1

        boxes = [tuple(a) for a in anchors]
        print(f"[SpriteSheet] anchor {len(anchors)}개, fragment {len(fragments)}개 "
              f"(흡수 {merged}개)")

        # 4) Y 중심 기준 정렬 → 가장 큰 간격 N-1 개로 행 분할
        boxes.sort(key=lambda b: b[1] + b[3] // 2)
        y_centers = [b[1] + b[3] // 2 for b in boxes]
        gap_indices = sorted(
            range(len(y_centers) - 1),
            key=lambda i: -(y_centers[i + 1] - y_centers[i]),
        )
        split_points = sorted(gap_indices[: n_rows - 1])

        rows: list[list[tuple]] = []
        start = 0
        for sp in split_points:
            rows.append(boxes[start : sp + 1])
            start = sp + 1
        rows.append(boxes[start:])

        # 5) 각 행에서 X 좌표로 정렬
        for r in rows:
            r.sort(key=lambda b: b[0])

        for idx, r in enumerate(rows):
            print(f"  row {idx}: {len(r)} 프레임")

        # 6) bbox 별로 crop + 스케일링
        sheet_pixmap = QPixmap(str(config["path"]))
        self._frames: dict[str, list[QPixmap]] = {}
        for name, anim in self._anims.items():
            row_idx = anim["row"]
            row_boxes = rows[row_idx]
            frames = []
            for (x, y, bw, bh) in row_boxes:
                crop = sheet_pixmap.copy(x, y, bw, bh)
                scaled = crop.scaled(
                    dw, dh,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
                frames.append(scaled)
            self._frames[name] = frames

    def get_frame(self, anim: str, tick: int) -> QPixmap:
        """tick (30fps 기준) 과 애니메이션 fps 로 현재 프레임 반환."""
        frames = self._frames[anim]
        ticks_per_frame = max(1, 30 // self._anims[anim]["fps"])
        return frames[(tick // ticks_per_frame) % len(frames)]


# ─────────────────────────────────────────────────────────────────────────────
class DesktopPet(QWidget):
    """
    화면 위를 돌아다니는 자세 피드백 데스크탑 펫.

    SPRITE_CONFIG 의 PNG 파일이 있으면 스프라이트 렌더링,
    없으면 QPainter 폴백으로 자동 전환.
    """

    def __init__(self, calibrator=None):
        super().__init__()
        self._calibrator = calibrator

        self._state      = _State.GOOD
        self._warn_since = 0.0
        self._anim_tick  = 0
        self._moving     = True
        self._facing_right = True

        # 스프라이트 로드 시도
        self._sprite: _SpriteSheet | None = None
        if SPRITE_CONFIG["path"].exists():
            self._sprite = _SpriteSheet(SPRITE_CONFIG)
            pet_w = SPRITE_CONFIG["display_w"]
            pet_h = SPRITE_CONFIG["display_h"]
        else:
            print("[DesktopPet] 스프라이트 없음 → QPainter 폴백")
            pet_w, pet_h = 64, 80

        self._pet_w = pet_w
        self._pet_h = pet_h

        self._setup_window()

        screen = QApplication.primaryScreen().availableGeometry()
        self._screen  = screen
        self._float_x = float(screen.width() // 2)
        self._float_y = float(self._dock_y())
        self._target  = self._random_target()
        self.move(int(self._float_x), int(self._float_y))

        self._move_timer = QTimer(self)
        self._move_timer.timeout.connect(self._tick)
        self._move_timer.start(_FPS_MS)

        self._posture_timer = QTimer(self)
        self._posture_timer.timeout.connect(self._check_posture)
        self._posture_timer.start(500)

    # ── 창 설정 ───────────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        # Tool 플래그 제거 — Tool 은 macOS 에서 NSPanel 을 만들고,
        # NSPanel 은 앱 비활성화 시 강제 숨김되어 Space 이동 시 사라짐.
        # Dock 아이콘은 NSApplicationActivationPolicyAccessory 로 처리.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)   # 시스템 배경 차단
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setFixedSize(self._pet_w, self._pet_h + 36)

        self._floating_applied = False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._floating_applied:
            self._apply_macos_always_visible()
            self._floating_applied = True

    def _apply_macos_always_visible(self) -> None:
        """
        macOS 전용: NSWindow collectionBehavior 를 설정해
        모든 Space 와 앱 위에서 펫이 계속 보이도록 함.

        winId() 로 이 위젯의 NSView → NSWindow 를 직접 얻어 설정 (NSApp.windows() 대신).
        QTimer 로 약간 지연시켜 Qt 가 윈도우 속성을 다 설정한 뒤에 덮어쓴다.
        """
        if platform.system() != "Darwin":
            return
        try:
            import objc
            from AppKit import (
                NSApp,
                NSApplicationActivationPolicyAccessory,
                NSWindowCollectionBehaviorCanJoinAllSpaces,
                NSWindowCollectionBehaviorStationary,
                NSWindowCollectionBehaviorFullScreenAuxiliary,
                NSStatusWindowLevel,
            )

            # Dock 아이콘 숨김
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

            view = objc.objc_object(c_void_p=int(self.winId()))
            nswindow = view.window()
            if nswindow is None:
                print("[DesktopPet] NSWindow 가져오기 실패")
                return

            behavior = (
                NSWindowCollectionBehaviorCanJoinAllSpaces
                | NSWindowCollectionBehaviorStationary
                | NSWindowCollectionBehaviorFullScreenAuxiliary
            )
            nswindow.setCollectionBehavior_(behavior)
            nswindow.setLevel_(NSStatusWindowLevel)
            print(
                f"[DesktopPet] macOS floating 적용 — class={nswindow.className()} "
                f"behavior={nswindow.collectionBehavior():#x} level={nswindow.level()}"
            )
        except ImportError:
            print(
                "[DesktopPet] pyobjc 미설치 — Space 전환 시 펫이 사라집니다.\n"
                "             설치: pip install pyobjc-framework-Cocoa"
            )
        except Exception as e:
            print(f"[DesktopPet] macOS floating 설정 실패: {e}")
            import traceback
            traceback.print_exc()

    # ── 이동 로직 ─────────────────────────────────────────────────────────────

    def _dock_y(self) -> int:
        """Dock 바로 위 Y 좌표 — availableGeometry 하단이 Dock 경계."""
        return self._screen.bottom() - self._pet_h - 36  # 36 = 말풍선 공간

    def _random_target(self) -> QPoint:
        """X만 랜덤, Y는 항상 Dock 위로 고정."""
        pad = self._pet_w
        x = random.randint(self._screen.left() + pad, self._screen.right() - pad)
        return QPoint(x, self._dock_y())

    def _tick(self) -> None:
        self._anim_tick += 1
        base_y = self._dock_y()

        # ALERT (화남): 제자리 X축 셰이크
        if self._state == _State.ALERT:
            offset = random.randint(-4, 4) if self._anim_tick % 4 < 2 else 0
            self.move(int(self._float_x) + offset, base_y)
            self.update()
            return

        # WARNING (잠) : 제자리, 호흡처럼 매우 느린 호버만
        if self._state == _State.WARNING:
            hover = math.sin(self._anim_tick * 0.05) * 1.2
            self.move(int(self._float_x), int(base_y + hover))
            self.update()
            return

        # 이하 GOOD 상태 전용 — idle(앉기) 또는 walk(걷기)
        if not self._moving:
            # 앉아있기: 꼬리 흔들기 느낌의 미세 호버
            hover = math.sin(self._anim_tick * 0.10) * 1.5
            self.move(int(self._float_x), int(base_y + hover))
            self.update()
            return

        # 걷는 중 — X축 이동
        dx = self._target.x() - self._float_x
        dist = abs(dx)

        if dist < _SPEED * 2:
            self._moving = False
            QTimer.singleShot(random.randint(_IDLE_MIN_MS, _IDLE_MAX_MS), self._resume_moving)
            return

        self._float_x += (dx / dist) * _SPEED
        self._facing_right = dx > 0
        bounce = math.sin(self._anim_tick * 0.4) * 2.0
        self.move(int(self._float_x), int(base_y + bounce))
        self.update()

    def _resume_moving(self) -> None:
        """GOOD 상태일 때만 다시 걷기 시작. WARNING/ALERT 중에는 안 움직임."""
        if self._state == _State.GOOD:
            self._target = self._random_target()
            self._moving = True

    def _current_anim(self) -> str:
        """현재 상태 + 이동 여부 → 재생할 애니메이션 이름."""
        if self._state == _State.ALERT:
            return "alert"
        if self._state == _State.WARNING:
            return "warning"
        if self._moving:
            return "walk"
        return "idle"

    # ── 자세 판정 ─────────────────────────────────────────────────────────────

    def _check_posture(self) -> None:
        with state_lock:
            valid       = shared_state["cam_valid"]
            calibrated  = shared_state["calibrated"]
            pitch       = shared_state["head_pitch"]
            tilt        = shared_state["shoulder_tilt"]
            compression = shared_state["neck_compression"]

        if not valid:
            return

        if calibrated and self._calibrator is not None:
            devs = self._calibrator.deviations({
                "head_pitch":       pitch,
                "shoulder_tilt":    tilt,
                "neck_compression": compression,
            })
            is_bad = (
                devs["compression_deviation"] < _COMPRESS_DEV
                or devs["pitch_deviation"]     > _PITCH_THRESH
                or devs["tilt_deviation"]      > _TILT_THRESH
            )
        else:
            is_bad = abs(pitch) > _PITCH_THRESH or tilt > _TILT_THRESH

        now = time.time()
        prev_state = self._state

        if is_bad:
            if self._state == _State.GOOD:
                self._state = _State.WARNING
                self._warn_since = now
                self._moving = False    # 잠들기 — 걷기 즉시 중단
            elif (
                self._state == _State.WARNING
                and now - self._warn_since >= _WARN_TO_ALERT_SEC
            ):
                self._state = _State.ALERT
                self._moving = False    # 화난 상태도 제자리
        else:
            self._state = _State.GOOD
            if prev_state != _State.GOOD:
                # WARNING/ALERT 에서 GOOD 복귀 → 다시 걷기 시작
                self._target = self._random_target()
                self._moving = True

        self.update()

    # ── 렌더링 ────────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 매 프레임 투명으로 초기화 (이게 없으면 이전 프레임이 남아 배경이 생김)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        sprite_y_offset = 36

        if self._state == _State.ALERT:
            self._draw_bubble(p)

        if self._sprite:
            frame = self._sprite.get_frame(self._current_anim(), self._anim_tick)
            if not self._facing_right:
                from PyQt6.QtGui import QTransform
                frame = frame.transformed(QTransform().scale(-1, 1))
            # 비율 유지로 작아진 프레임은 디스플레이 박스 중앙 + 하단 정렬
            # (지면에 발이 닿도록 bottom 기준 정렬)
            x_off = (self._pet_w - frame.width()) // 2
            y_off = sprite_y_offset + (self._pet_h - frame.height())
            p.drawPixmap(x_off, y_off, frame)
        else:
            p.translate(0, sprite_y_offset)
            if not self._facing_right:
                p.translate(self._pet_w, 0)
                p.scale(-1.0, 1.0)
            self._draw_fallback(p)

    def _draw_bubble(self, p: QPainter) -> None:
        bx, by, bw, bh = 0, 2, self._pet_w, 26
        p.setBrush(QBrush(QColor(255, 255, 255, 220)))
        p.setPen(QPen(QColor(200, 80, 80), 1))
        p.drawRoundedRect(bx, by, bw, bh, 6, 6)

        tail = QPolygon()
        tail.append(QPoint(bx + bw // 2 - 5, by + bh))
        tail.append(QPoint(bx + bw // 2 + 5, by + bh))
        tail.append(QPoint(bx + bw // 2,     by + bh + 7))
        p.drawPolygon(tail)

        p.setPen(QPen(QColor(180, 60, 60)))
        p.setFont(QFont("Arial", 9, QFont.Weight.Bold))
        p.drawText(QRect(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, "자세 바르게!")

    def _draw_fallback(self, p: QPainter) -> None:
        """스프라이트 파일 없을 때 QPainter 로 간단한 캐릭터 표시."""
        s = self._state
        if s == _State.GOOD:
            col = QColor(110, 210, 120)
        elif s == _State.WARNING:
            col = QColor(240, 195, 60)
        else:
            col = QColor(225, 85, 85)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(col))
        p.drawEllipse(12, 2, 40, 38)   # 머리
        p.drawRoundedRect(8, 36, 48, 36, 10, 10)  # 몸통

        p.setBrush(QBrush(QColor(50, 40, 40)))
        p.drawEllipse(20, 14, 8, 8)    # 왼쪽 눈
        p.drawEllipse(36, 14, 8, 8)    # 오른쪽 눈

    # ── 마우스 ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._target = self._random_target()
            self._moving = True
