# test_client.py 맨 윗줄에 이 두 줄을 반드시 추가하세요!
import eventlet
eventlet.monkey_patch()

import socketio
import time

sio = socketio.Client()

@sio.event
def connect():
    print("★ 백엔드 서버 연결 성공!")
    
    mock_data = {
        "device_id": "user_01",
        "data_payload": {
            "chair": {
                "pressure": [900, 700, 1000, 910]
            },
            "vision": {
                "blink_count": 12
            }
        }
    }
    
    print("가상 센서 데이터를 전송합니다...")
    sio.emit('sensor_data', mock_data)
    
    time.sleep(1)
    sio.disconnect()

# test_client.py 맨 아랫줄 수정
if __name__ == '__main__':
    # localhost 대신 명확한 로컬 루프백 IP로 변경합니다.
    sio.connect('http://127.0.0.1:5000')