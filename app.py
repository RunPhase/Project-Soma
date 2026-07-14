import eventlet
eventlet.monkey_patch()

import socketio
import psycopg2
import json
import time  # 1. 시간 기반 주기 제어를 위해 추가

# 1. 서버 설정
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

# 2. Supabase 클라우드 DB 설정
DB_CONFIG = {
    "host": "db.dzkionspeweesqwlrxex.supabase.co", 
    "database": "postgres",
    "user": "postgres",
    "password": "XtpXL52,QHS/7nN", 
    "port": "5432"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, connect_timeout=5)

# 2. 의자 데이터 전송 주기 제어용 변수 추가
last_db_save_time = {}   # 디바이스별 마지막 DB 저장 시간 기록
DB_SAVE_INTERVAL = 5.0   # DB 저장 주기 (초 단위)

@sio.event
def connect(sid, environ):
    print(f"클라이언트 접속됨: {sid}")

@sio.event
def sensor_data(sid, data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        
        device_id = data.get("device_id", "smart_chair_01")
        
        # ========================================================
        # [의자 핵심 기능: 데이터 추출 및 판정 로직 추가]
        # ========================================================
        pressure = data["data_payload"]["chair"]["pressure"]
        distances = data["data_payload"]["vision"]["distances"]
        
        # ① 압력 센서 기반 좌우 균형 판정
        left_side = pressure[0] + pressure[2]
        right_side = pressure[1] + pressure[3]
        balance = "LEFT" if left_side > right_side + 50 else ("RIGHT" if right_side > left_side + 50 else "CENTER")

        # ② 거리 + 압력 센서 융합 자세 판정
        dist_val = distances[0]
        total_pressure = sum(pressure)  
        is_pressure_active = total_pressure > 10  # 누적 압력이 10 이상일 때 유효 착석으로 간주
        
        if dist_val == -1 and not is_pressure_active:
            seat_status = "Empty"
        elif is_pressure_active and (dist_val > 500 or dist_val == -1):
            seat_status = "Leaning Forward"  # 모니터 쪽으로 상체가 숙여진 상태
        elif is_pressure_active and 0 <= dist_val <= 500:
            seat_status = "Seated"
        else:
            seat_status = "Empty"

        # 터미널 실시간 모니터링 출력 포맷 변경
        print(f"[{device_id}] 실시간 상태: {balance}, 자세 판정: {seat_status}")

        # ③ 5초 스로틀링 및 DB 적재 로직 (레이스 컨디션 방어 포함)
        current_time = time.time()
        last_save = last_db_save_time.get(device_id, 0)

        if current_time - last_save >= DB_SAVE_INTERVAL:
            last_db_save_time[device_id] = current_time  # 중복 진입 방지를 위해 시간 먼저 갱신
            
            print(f"▶ [{DB_SAVE_INTERVAL}초 경과] 클라우드 DB 저장 시도 중...")
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # DB의 status 컬럼에 좌우 균형과 자세 상태를 조합하여 저장
            query = "INSERT INTO sensor_logs (chair_id, raw_data, status) VALUES (%s, %s, %s)"
            cur.execute(query, (device_id, json.dumps(data['data_payload']), f"{balance} / {seat_status}"))
            
            conn.commit()
            cur.close()
            conn.close()
            
            print(">>> Supabase 클라우드 DB 저장 완료 <<<")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == '__main__':
    print(f"서버 시작 (포트: 5000) / DB 저장 주기: {DB_SAVE_INTERVAL}초")
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 5000)), app)
