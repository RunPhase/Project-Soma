# 자세교정 시스템 구현 계획서

> 작성일: 2026-05-15  
> 담당 파트: 캠 기반 자세 분석 + Unity 렌더링

---

## 1. 프로젝트 개요

### 목표
압력센서(아두이노)와 카메라(MediaPipe)를 병합하여 사용자의 자세를 실시간 분석하고, Unity 캐릭터로 시각적 피드백을 제공하는 자세교정 시스템

### 전체 시스템 구성도

```
[하드웨어]
 아두이노 (압력센서) ──── USB Serial ────┐
 노트북/외장 웹캠 ─────── OpenCV ────────┤
                                         ▼
[Python 분석층]                   ┌─────────────┐
 Thread 1: 캠 분석 (내 파트) ────→│  공유 상태   │
 Thread 2: 압력 분석 (팀원) ─────→│  (dict/lock) │
                                  └──────┬──────┘
                                         │
                                    Main Thread
                                    (병합 + 판정)
                                         │
                                    ZeroMQ PUB
                                         │
                                         ▼
[Unity]
 ZeroMQ SUB → 캐릭터 본 제어 → PiP 렌더링 (우측 하단)
```

---

## 2. 역할 분담

| 파트 | 담당 | 내용 |
|------|------|------|
| 캠 분석 (Thread 1) | **나** | MediaPipe Pose, 각도 계산 |
| Unity 렌더링 | **나** | 캐릭터 본 제어, PiP UI |
| 아두이노 압력 분석 (Thread 2) | 팀원 A | 시리얼 수신, 압력 분석 |
| 병합 + 피드백 판정 (Main) | 팀원 B | 복합 조건 판정 로직 |
| 분석 UI / 대시보드 | 팀원 C | 자세 이력, 통계 표시 |

> ⚠️ **팀 협의 필요**: 역할 분담 및 Main 판정 담당자 확정 필요

---

## 3. 내 파트 상세 설계

### 3-1. Python 캠 분석 (Thread 1)

#### 사용 기술
- `mediapipe` — Pose 랜드마크 추출
- `opencv-python` — 캠 캡처
- `numpy` — 각도 계산

#### 사용 랜드마크 (Pose 내장 7개, 추가 모델 불필요)

| 랜드마크 | 용도 |
|---------|------|
| `nose` | neck_angle 계산 기준점 |
| `left_ear`, `right_ear` | 얼굴 너비(거리 근사), head_pitch 보조 |
| `left_eye`, `right_eye` | PnP head pose 보조점 |
| `mouth_left`, `mouth_right` | PnP head pose 보조점 |
| `left_shoulder`, `right_shoulder` | 어깨 기울기, neck_angle 기준 |

> Face Mesh(468개)는 오버스펙 — Pose 내장 7개로 충분히 대응 가능

#### 추출 지표

| 지표 | 사용 랜드마크 | 설명 |
|------|-------------|------|
| `neck_angle` | nose, left_shoulder, right_shoulder | 목 전방 기울기 |
| `head_pitch` | nose, left_ear, right_ear, eyes, mouth (PnP) | 머리 앞뒤 숙임 각도 |
| `face_width` | left_ear ↔ right_ear 거리 | 카메라 거리 근사 (좌우 회전에 강건) |
| `shoulder_tilt` | left_shoulder.y, right_shoulder.y | 어깨 좌우 기울기 |

#### 계산 방식

```
neck_angle:
  mid_shoulder = (left_shoulder + right_shoulder) / 2
  vector = nose - mid_shoulder
  angle = arctan2(vector.x, vector.y) → 수직 기준 편차

head_pitch:
  6개 얼굴 랜드마크로 PnP(Perspective-n-Point) 알고리즘 적용
  → pitch(앞뒤), yaw(좌우), roll(기울기) 추출
  → pitch 값을 거북목 보조 지표로 사용

face_width:
  dist = distance(left_ear, right_ear)
  → 단순 bounding box보다 좌우 회전 시 안정적

shoulder_tilt:
  diff = abs(left_shoulder.y - right_shoulder.y)
  → 정규화 필요 (해상도 독립적으로 만들기 위해 어깨 너비로 나눔)
  tilt_ratio = diff / distance(left_shoulder, right_shoulder)
```

#### 캘리브레이션

```
시작 시 "올바른 자세로 앉으세요" → 3초 측정 → 평균값 저장

baseline = {
  "neck_angle": float,
  "head_pitch": float,
  "face_width": float,    # 기준 거리에서의 귀 간 거리
  "shoulder_tilt": float
}

이후 판정은 절대값이 아닌 baseline 대비 편차로 계산
→ 체형 차이, 카메라 위치 차이 흡수 가능

⚠️ 재캘리브레이션 기능 필수
  (의자 높이 변경, 자리 이동 시 기준값 틀어짐)
```

#### 거북목 복합 판정 로직

```
neck_deviation  = current_neck_angle - baseline_neck_angle
pitch_deviation = current_head_pitch - baseline_head_pitch
face_deviation  = (current_face_width - baseline_face_width) / baseline_face_width

거북목(BAD_NECK) =
  neck_deviation  > 15°     # 목이 앞으로 기울어짐
  AND head_pitch  > 10°     # 머리가 앞으로 숙여짐
  AND face_deviation > 0.15 # 모니터에 15% 이상 가까워짐

→ 3조건 AND → 오판정 최소화
→ 단일 조건만 충족 시 WARNING 수준으로 별도 처리 가능
```

#### 공유 상태 업데이트 구조

```python
# 공유 딕셔너리 (threading.Lock으로 보호)
shared_state = {
    "neck_angle": 0.0,
    "head_pitch": 0.0,
    "face_width": 0.0,
    "shoulder_tilt": 0.0,
    "cam_timestamp": 0.0,
    "cam_valid": False,
    "calibrated": False
}
```

#### 파일 구조

```
python/
├── main.py            # 스레드 실행, 병합, ZeroMQ 전송
├── pose_analyzer.py   # MediaPipe 래핑, 각도/head pose 계산
├── calibrator.py      # 캘리브레이션 로직, baseline 저장/로드
├── sender.py          # ZeroMQ PUB 소켓 관리
└── shared_state.py    # 공유 상태 정의, Lock
```

---

### 3-2. Unity 렌더링

#### 사용 기술
- Unity 2022 LTS (Humanoid Rig)
- `AsyncTcpClient` 또는 NativeWebSocket (ZeroMQ 대안으로 TCP 고려)
- Mixamo 또는 Ready Player Me 캐릭터

#### 데이터 수신 → 본 제어 흐름

```
ZeroMQ SUB 수신 (JSON)
  └→ JsonUtility.FromJson<PostureData>()
       └→ SpineController.Apply(neck_angle, shoulder_tilt)
            └→ transform.localRotation = Quaternion.Euler(...)
```

#### 제어할 본 (Humanoid 기준)

| Unity Bone | 제어 값 | 설명 |
|------------|--------|------|
| Neck / Head | neck_angle, head_pitch | 앞뒤 기울기 (복합) |
| LeftShoulder / RightShoulder | shoulder_tilt | 좌우 높이 차 |
| Spine | posture_state 기반 | 전체 자세 보정 |

#### PiP (Picture-in-Picture) 구조

```
Main Camera → RenderTexture (512x512)
  └→ Canvas → RawImage (우측 하단, 200x200px)
       └→ 반투명 배경 패널 위에 렌더링
```

#### 파일 구조 (C# 스크립트)

```
Unity/Assets/Scripts/
├── PostureReceiver.cs     # ZeroMQ/TCP 수신, JSON 파싱
├── PostureData.cs         # 데이터 구조체 정의
├── SpineController.cs     # Humanoid 본 회전 적용
└── PiPController.cs       # RenderTexture → UI 관리
```

---

## 4. 통신 인터페이스 (팀 전체 합의 필요)

### 4-1. Python → Unity 전송 포맷 (JSON)

```json
{
  "neck_angle": 15.3,
  "head_pitch": 8.2,
  "face_width": 0.18,
  "shoulder_tilt": 3.2,
  "posture_state": "GOOD",
  "calibrated": true,
  "timestamp": 1715123456.789
}
```

### 4-2. posture_state 값 정의

| 값 | 의미 |
|----|------|
| `GOOD` | 정상 자세 |
| `BAD_NECK` | 거북목 감지 |
| `BAD_SHOULDER` | 어깨 기울임 |
| `BAD_COMPLEX` | 복합 불량 (압력+캠) |
| `ABSENT` | 자리 이탈 |

> ⚠️ **팀 협의 필요**: posture_state 항목 및 복합 판정 조건 확정

### 4-3. 통신 방식

| 구간 | 방식 | 포트 |
|------|------|------|
| Python → Unity | ZeroMQ PUB/SUB | 5555 |
| 아두이노 → Python | USB Serial (115200 baud) | COM / /dev/tty |

> ⚠️ **팀 협의 필요**: Unity가 Windows인지 macOS인지에 따라 ZeroMQ 플러그인 선택 달라짐

---

## 5. 피드백 판정 기준 (초안)

> ⚠️ **팀 전체 협의 필요**: 아래는 초안이며 임계값은 캘리브레이션 + 실험 후 튜닝 필요

### 캘리브레이션 기반 편차 판정 원칙

```
모든 판정은 절대값이 아닌 baseline 대비 편차로 수행
→ 체형/카메라 위치 차이 흡수
→ 앱 시작 시 캘리브레이션 필수, 재캘리브레이션 기능 제공
```

### 단일 조건 판정

| 상태 | 캠 조건 | 압력 조건 |
|------|---------|----------|
| 거북목 (복합) | neck편차 > 15° AND head_pitch편차 > 10° AND face 15% 증가 | - |
| 어깨 기울임 | shoulder_tilt_ratio 편차 > 0.1 | - |
| 체중 편중 | - | 좌우 압력비 > 1.4 |
| 자리 이탈 | 랜드마크 미감지 | 전체 압력 ≈ 0 |

### 복합 조건 (캠 + 압력 AND)

| 상태 | 조건 |
|------|------|
| 척추 측만 의심 | shoulder_tilt 편차 > 0.1 AND 압력 편중 > 1.4x |
| 심각 불량 | 거북목 조건 충족 AND 체중 편중 동시 |

### 시간 필터링 (노이즈 방지)

```
불량 자세가 3초 이상 지속될 때만 피드백 트리거
→ 순간적인 움직임 / 1프레임 튀는 값 무시
```

---

## 6. 개발 단계

### Phase 1 — MVP (현재 목표)
- [ ] Python: MediaPipe 랜드마크 추출 (7개 얼굴 + 어깨)
- [ ] Python: neck_angle / head_pitch (PnP) / face_width / shoulder_tilt 계산
- [ ] Python: 캘리브레이션 로직 (3초 baseline 측정 + 저장)
- [ ] Python: 재캘리브레이션 트리거 기능
- [ ] Python: 거북목 복합 판정 (3조건 AND + 시간 필터링)
- [ ] Python: ZeroMQ PUB 전송
- [ ] Unity: ZeroMQ SUB 수신 + JSON 파싱
- [ ] Unity: Humanoid 캐릭터 본 회전 적용 (neck_angle + head_pitch)
- [ ] Unity: PiP RenderTexture UI

### Phase 2 — 통합
- [ ] 아두이노 시리얼 수신 연동 (팀원 파트)
- [ ] 공유 상태 병합 + 판정 로직 연결
- [ ] posture_state → Unity 피드백 애니메이션

### Phase 3 — 완성
- [ ] 임계값 튜닝 (실제 외장 웹캠 + 의자 세팅)
- [ ] 분석 UI 대시보드 연동 (팀원 파트)
- [ ] 발표용 시나리오 테스트

---

## 7. 팀 협의 필요 항목 요약

| # | 항목 | 현재 상태 |
|---|------|----------|
| 1 | 역할 분담 최종 확정 | 미정 |
| 2 | Main 판정 담당자 | 미정 |
| 3 | posture_state 항목 정의 | 초안 |
| 4 | 피드백 판정 임계값 | 미정 |
| 5 | Unity 실행 OS (Windows/macOS) | 미정 |
| 6 | ZeroMQ vs TCP 소켓 최종 선택 | 미정 |
| 7 | 아두이노 무선/유선 통신 방식 | 미정 |
| 8 | 외장 웹캠 구매 시기 및 사양 | 미정 |
| 9 | 캘리브레이션 UI 담당 (분석 UI 팀원?) | 미정 |
| 10 | 재캘리브레이션 트리거 방식 (버튼/단축키) | 미정 |

---

## 8. 장비 및 환경

| 항목 | MVP | 최종 |
|------|-----|------|
| 카메라 | 노트북 내장 캠 | 외장 웹캠 (모니터 상단) |
| 개발 OS | macOS | - |
| Python | 3.10+ | - |
| Unity | 2022 LTS | - |
| 아두이노 | - | UNO / Nano (팀원 결정) |

---

## 9. 의존성

### Python
```
mediapipe
opencv-python        # 캠 캡처
opencv-contrib-python  # PnP solvePnP 활용 시
numpy
pyzmq
```

### Unity
```
NuGetForUnity → NetMQ (ZeroMQ C# 클라이언트)
Newtonsoft.Json (또는 기본 JsonUtility)
```
