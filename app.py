import eventlet
eventlet.monkey_patch()

# 🌟 Flask 관련 모듈 추가
from flask import Flask, request, jsonify
import socketio
import psycopg2
import json
import time

# 1. Flask 앱과 Socket.io 서버 설정을 하나로 결합
sio = socketio.Server(cors_allowed_origins='*')
flask_app = Flask(__name__)             # 🌟 HTTP API 요청을 처리할 Flask 인스턴스 생성
app = socketio.WSGIApp(sio, flask_app)  # 🌟 Socket.io와 Flask 앱을 하나로 묶음

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

# =====================================================================
# 🌟 [신규 창구] DB 또는 분석 서버로부터 보고서를 받기 위한 HTTP POST 라우터
# 주소: http://127.0.0.1:5000/api/report
# =====================================================================
@flask_app.route('/api/report', methods=['POST'])
def receive_report():
    try:
        # 상대방이 보낸 JSON 데이터 파싱
        report_data = request.get_json()
        if not report_data:
            return jsonify({"status": "error", "message": "JSON 데이터가 누락되었습니다."}), 400

        # 임시로 터미널에 수신된 보고서 출력
        print("\n==================================================")
        print("📊 [보고서 수신 완료] 새로운 분석 결과가 도착했습니다!")
        print(json.dumps(report_data, indent=4, ensure_ascii=False))
        print("==================================================\n")

        # [다음 단계 대비책]
        # 1. 수신받은 보고서를 새로운 DB 테이블(예: user_reports)에 저장하는 로직
        # 2. Socket.io를 통해 프론트엔드로 즉시 보고서 푸시 알림 전송 (예: sio.emit('new_report', report_data))
        # 등의 후속 처리를 이 아래 공간에서 구현하면 됩니다.

        return jsonify({"status": "success", "message": "보고서가 성공적으로 전달되었습니다."}), 200

    except Exception as e:
        print(f"❌ 보고서 수신 중 에러 발생: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Socket.io 실시간 센서 데이터 처리 (기존 코드 그대로 유지)
@sio.event
def connect(sid, environ):
    print(f"클라이언트 접속됨: {sid}")

@sio.event
def sensor_data(sid, data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        
        device_id = data.get("device_id", "smart_chair_01")
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
            
            query = """
                INSERT INTO sensor_logs 
                (user_name, raw_data, balance_status, posture_status) 
                VALUES (%s, %s, %s, %s)
            """
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
