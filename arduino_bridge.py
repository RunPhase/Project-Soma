# arduino_bridge.py
import eventlet
eventlet.monkey_patch()

import serial
import socketio
import time

# 1. 아두이노 연결 설정 (포트 번호 유효성 확인 필수)
ARDUINO_PORT = 'COM3' 
BAUD_RATE = 9600

try:
    py_serial = serial.Serial(port=ARDUINO_PORT, baudrate=BAUD_RATE, timeout=1)
    print(f"✅ 아두이노 연결 성공 ({ARDUINO_PORT})")
except Exception as e:
    print(f"❌ 아두이노 포트를 열 수 없습니다. 포트 번호나 케이블을 확인하세요: {e}")
    exit()

# 2. 로컬 백엔드 서버(app.py)와 통신할 Socket.io 클라이언트 설정
sio = socketio.Client()

@sio.event
def connect():
    print("⚡ 로컬 백엔드 서버(app.py)에 연결되었습니다.")

if __name__ == '__main__':
    try:
        # 내 컴퓨터에서 구동 중인 app.py 서버에 접속
        sio.connect('http://127.0.0.1:5000')
        print("🚀 실시간 아두이노 데이터 중계 시작...")
        
        # 프로그램 구동 즉시 사용자 식별 정보 수집
        user_name = input("👤 현재 의자에 앉을 사용자의 이름을 입력하세요: ").strip()
        if not user_name:
            user_name = "guest"  # 미입력 시 익명 처리
        
        while True:
            if py_serial.readable():
                line = py_serial.readline().decode('utf-8').strip()
                
                if line:
                    data_fields = line.split(',')
                    
                    # 개조된 5개 데이터 규격(압력 4개 + 거리 1개) 파싱 검증
                    if len(data_fields) >= 5:
                        try:
                            # 스트림 노이즈 방지를 위해 상위 5개 필드만 추출 후 정수 변환
                            raw_numbers = [int(x.strip()) for x in data_fields[:5]]
                            
                            pressure_data = raw_numbers[0:4]  
                            distance_data = [raw_numbers[4]]  # app.py 스키마 호환을 위해 리스트 구조화
                            
                            # 데이터 묶음 포장
                            payload = {
                                "device_id": "smart_chair_01",
                                "data_payload": {
                                    "user_name": user_name,   # 데이터 블록 내부에 이름 탑재
                                    "chair": {
                                        "pressure": pressure_data
                                    },
                                    "vision": {
                                        "blink_count": 0, 
                                        "distances": distance_data
                                    }
                                }
                            }
                            
                            # 서버측 전송 및 중계 모니터링 로그 출력
                            sio.emit('sensor_data', payload)
                            print(f"[{user_name}] 데이터 토스 ➡️ 압력: {pressure_data} | 거리: {distance_data}")
                            
                        except ValueError:
                            print(f"⚠️ 데이터 변환 실패 (숫자가 아님): {line}")
                            
            time.sleep(0.1) # 자원 독점 방지용 타임 슬롯
            
    except KeyboardInterrupt:
        print("\n⏹️ 중계 프로그램이 사용자에 의해 종료되었습니다.")
        py_serial.close()
        sio.disconnect()
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
