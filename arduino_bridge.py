# arduino_bridge.py
import eventlet
eventlet.monkey_patch()

import serial
import socketio
import time

# 1. 아두이노 연결 설정 (포트 번호는 장치관리자에서 확인한 번호 유지)
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
        
        while True:
            if py_serial.readable():
                # 아두이노가 보낸 한 줄 읽기
                line = py_serial.readline().decode('utf-8').strip()
                
                if line:
                    # 콤마로 데이터 분리
                    data_fields = line.split(',')
                    
                    # 🌟 [핵심 변경] 데이터 5개 규격으로 검증 조건 완화
                    if len(data_fields) >= 5:
                        try:
                            # 혹시 모를 공백이나 줄바꿈 문자를 제거하고 5개만 정확히 숫자로 변환
                            raw_numbers = [int(x.strip()) for x in data_fields[:5]]
                            
                            pressure_data = raw_numbers[0:4]  # 인덱스 0~3: 압력 센서 4개
                            
                            # 🌟 [핵심 변경] app.py가 에러를 뿜지 않도록 대괄호[]로 감싸서 리스트로 만듦
                            distance_data = [raw_numbers[4]]  # 인덱스 4: 거리 센서 1개
                            
                            # app.py 규격에 맞게 포장
                            payload = {
                                "device_id": "smart_chair_01",
                                "data_payload": {
                                    "chair": {
                                        "pressure": pressure_data
                                    },
                                    "vision": {
                                        "blink_count": 0, 
                                        "distances": distance_data
                                    }
                                }
                            }
                            
                            # app.py 서버의 'sensor_data' 이벤트로 전송
                            sio.emit('sensor_data', payload)
                            print(f" 데이터 토스 ➡️ 압력: {pressure_data} | 거리: {distance_data}")
                            
                        except ValueError:
                            print(f"⚠️ 데이터 변환 실패 (숫자가 아님): {line}")
                            
            time.sleep(0.1) # CPU 과부하 방지
            
    except KeyboardInterrupt:
        print("\n⏹️ 중계 프로그램이 사용자에 의해 종료되었습니다.")
        py_serial.close()
        sio.disconnect()
    except Exception as e:
        print(f"❌ 에러 발생: {e}")
