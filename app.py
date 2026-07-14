import eventlet
eventlet.monkey_patch()

import socketio
import psycopg2
import json
import time

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

# 트래픽 제어를 위한 전역 변수 설정
last_db_save_time = {}   
DB_SAVE_INTERVAL = 5.0   

@sio.event
def connect(sid, environ):
    print(f"클라이언트 접속됨: {sid}")

@sio.event
def sensor_data(sid, data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        
        device_id = data.get("device_id", "smart_chair_01")
        
        # 🌟 페이로드에서 사용자 이름 추출
        user_name = data["data_payload"].get("user_name", "guest")
        
        pressure = data["data_payload"]["chair"]["pressure"]
        distances = data["data_payload"]["vision"]["distances"]
        
        # ① balance_status: 좌우 균형 판정
        left_side = pressure[0] + pressure[2]
        right_side = pressure[1] + pressure[3]
        balance_status = "LEFT" if left_side > right_side + 50 else ("RIGHT" if right_side > left_side + 50 else "CENTER")

        # ② posture_status: 거리 + 압력 센서 융합 자세 판정
        dist_val = distances[0]
        total_pressure = sum(pressure)  
        is_pressure_active = total_pressure > 10  
        
        if dist_val == -1 and not is_pressure_active:
            posture_status = "Empty"
        elif is_pressure_active and (dist_val > 500 or dist_val == -1):
            posture_status = "Leaning Forward"
        elif is_pressure_active and 0 <= dist_val <= 500:
            posture_status = "Seated"
        else:
            posture_status = "Empty"

        print(f"[{device_id} ({user_name})] 균형: {balance_status} | 자세: {posture_status}")

        # ③ 스로틀링 및 DB 적재 로직
        current_time = time.time()
        last_save = last_db_save_time.get(device_id, 0)

        if current_time - last_save >= DB_SAVE_INTERVAL:
            last_db_save_time[device_id] = current_time 
            
            print(f"▶ [{DB_SAVE_INTERVAL}초 경과] 클라우드 DB 저장 시도 중...")
            
            conn = get_db_connection()
            cur = conn.cursor()
            
            # 🌟 [핵심 변경] 새로 수정한 테이블 컬럼명(user_name 등)으로 매칭
            query = """
                INSERT INTO sensor_logs 
                (user_name, raw_data, balance_status, posture_status) 
                VALUES (%s, %s, %s, %s)
            """
            
            # user_name 컬럼에 정확히 user_name 변수만 삽입하도록 수정
            cur.execute(query, (
                user_name, 
                json.dumps(data['data_payload']), 
                balance_status, 
                posture_status
            ))
            
            conn.commit()
            cur.close()
            conn.close()
            
            print(">>> Supabase 클라우드 DB 저장 완료 <<<")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == '__main__':
    print(f"서버 시작 (포트: 5000) / DB 저장 주기: {DB_SAVE_INTERVAL}초")
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 5000)), app)
