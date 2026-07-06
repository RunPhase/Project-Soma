import eventlet
eventlet.monkey_patch()

import socketio
import psycopg2
import json
import time  # 🌟 [추가됨] 시간 계산을 위한 모듈

# 1. 서버 설정
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

# 2. Supabase 클라우드 DB 설정 (도메인 + 딕셔너리)
DB_CONFIG = {
    "host": "db.dzkionspeweesqwlrxex.supabase.co", 
    "database": "postgres",
    "user": "postgres",
    "password": "XtpXL52,QHS/7nN", 
    "port": "5432"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, connect_timeout=5)

# 🌟 [핵심] 트래픽 제어를 위한 전역 변수 설정
last_db_save_time = {}   # 디바이스별 마지막 DB 저장 시간을 기록
DB_SAVE_INTERVAL = 5.0   # DB 저장 주기 (단위: 초). 데모 시 3~5초, 실생활 60초 등 자유롭게 변경!

@sio.event
def connect(sid, environ):
    print(f"클라이언트 접속됨: {sid}")

@sio.event
def sensor_data(sid, data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        
        device_id = data.get("device_id", "smart_chair_01")
        pressure = data["data_payload"]["chair"]["pressure"]
        blink = data["data_payload"]["vision"]["blink_count"]
        
        # 좌우 균형 판정 알고리즘
        left_side = pressure[0] + pressure[2]
        right_side = pressure[1] + pressure[3]
        balance = "LEFT" if left_side > right_side + 50 else ("RIGHT" if right_side > left_side + 50 else "CENTER")

        # 터미널 실시간 모니터링은 1초마다 계속 출력
        print(f"[{device_id}] 실시간 상태: {balance}, 눈 깜빡임: {blink}")

        current_time = time.time()
        last_save = last_db_save_time.get(device_id, 0)

        if current_time - last_save >= DB_SAVE_INTERVAL:
            # 🌟 [레이스 컨디션 방어] DB 연결 대기 상태로 들어가기 전에 시간부터 즉시 갱신!
            # 이렇게 해야 인터넷 대기 시간 동안 들어오는 다른 패킷들이 이 문을 통과하지 못합니다.
            last_db_save_time[device_id] = current_time
            
            print(f"▶ [{DB_SAVE_INTERVAL}초 경과] 클라우드 DB 저장 시도 중...")
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            query = "INSERT INTO sensor_logs (chair_id, raw_data, status) VALUES (%s, %s, %s)"
            cur.execute(query, (device_id, json.dumps(data['data_payload']), balance))
            
            conn.commit()
            cur.close()
            conn.close()
            
            print(">>> Supabase 클라우드 DB 저장 완료 <<<")
        else:
            # 5초가 지나지 않았다면 로그를 남기지 않고 조용히 패스
            pass

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == '__main__':
    print(f"서버 시작 (포트: 5000) / DB 저장 주기: {DB_SAVE_INTERVAL}초")
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 5000)), app)
