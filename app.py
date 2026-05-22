import socketio
import eventlet
import psycopg2
import json

# 1. 서버 설정
sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

# 2. Supabase 클라우드 DB 주소 설정 (안전한 딕셔너리 방식)
# postgresql://postgres:XtpXL52,QHS/7nN@db.dzkionspeweesqwlrxex.supabase.co:5432/postgres
DB_CONFIG = {
    "host": "db.dzkionspeweesqwlrxex.supabase.co",
    "database": "postgres",
    "user": "postgres",
    "password": "XtpXL52,QHS/7nN",  # <-- 여기에 대괄호 없이 실제 DB 비밀번호를 적으세요!
    "port": "5432"
}

def get_db_connection():
    # 주소 쪼개기 방식으로 안전하게 연결
    return psycopg2.connect(**DB_CONFIG)

@sio.event
def connect(sid, environ):
    print(f"클라이언트 접속됨: {sid}")

@sio.event
def sensor_data(sid, data):
    try:
        if isinstance(data, str):
            data = json.loads(data)
        
        device_id = data.get("device_id")
        pressure = data["data_payload"]["chair"]["pressure"]
        blink = data["data_payload"]["vision"]["blink_count"]
        
        # 좌우 균형 판정 알고리즘
        left_side = pressure[0] + pressure[2]
        right_side = pressure[1] + pressure[3]
        balance = "LEFT" if left_side > right_side + 50 else ("RIGHT" if right_side > left_side + 50 else "CENTER")

        print(f"[{device_id}] 상태: {balance}, 눈 깜빡임: {blink}")

        # Supabase 클라우드 DB에 데이터 저장
        conn = get_db_connection()
        cur = conn.cursor()
        query = "INSERT INTO sensor_logs (chair_id, raw_data, status) VALUES (%s, %s, %s)"
        cur.execute(query, (device_id, json.dumps(data['data_payload']), balance))
        conn.commit()
        cur.close()
        conn.close()
        print(">>> Supabase 클라우드 DB 저장 완료 <<<")

    except Exception as e:
        print(f"에러 발생: {e}")

if __name__ == '__main__':
    print("서버가 5000번 포트에서 시작되었습니다 (로컬 네트워크 접속 가능)")
    eventlet.wsgi.server(eventlet.listen(('0.0.0.0', 5000)), app)