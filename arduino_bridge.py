# arduino_bridge.py
import eventlet
eventlet.monkey_patch()

import serial
import socketio
import time

# 1. 아두이노 연결 설정 (포트 번호는 아두이노 연결 후 확인하여 수정)
# 예: Windows는 'COM3', 'COM4' 등 / Mac은 '/dev/tty.usbmodem...' 형태
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
                # 아두이노가 보낸 한 줄 읽기 (예: "900,700,1000,910,250,300\n")
                line = py_serial.readline().decode('utf-8').strip()
                
                if line:
                    # 콤마로 데이터 분리
                    data_fields = line.split(',')
                    
                    # 정상적인 데이터 세트(데이터 6개)가 들어왔는지 검증
                    if len(data_fields) == 6:
                        try:
                            # 문자열을 정수형 숫자로 변환
                            raw_numbers = list(map(int, data_fields))
                            
                            pressure_data = raw_numbers[0:4]  # FL, FR, BL, BR
                            distance_data = raw_numbers[4:6]   # dist1, dist2
                            
                            # app.py 규격에 맞게 포장
                            payload = {
                                "device_id": "smart_chair_01",
                                "data_payload": {
                                    "chair": {
                                        "pressure": pressure_data
                                    },
                                    "vision": {
                                        "blink_count": 0, # 시선 추적 연동 전까지 임시값
                                        "distances": distance_data # 거리 데이터 확장 확장
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