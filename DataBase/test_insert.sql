-- 1. 사용자(Users) 추가: 페르소나 1 김민준 씨 [cite: 799]
INSERT INTO Users (user_id, name, age, job_type) 
VALUES ('202210866', '김민준', 32, '프로그래머');

-- 2. 사용자 설정(User_Settings) 추가 [cite: 942]
INSERT INTO User_Settings (user_id, sensitivity_level, notification_method)
VALUES ('202210866', 7, 'MOUSE_VIBRATION');

-- 3. 피로도 로그(Fatigue_Logs) 추가: 전송 규약(JSON) 데이터 적재 [cite: 1103, 1155]
INSERT INTO Fatigue_Logs (user_id, timestamp, status, fatigue_score, raw_data_summary)
VALUES (
    '202210866', 
    '2026-05-08 21:45:00', 
    'CAUTION', 
    75.5, 
    '{
      "chair": { "pressure_point": [10, 20, 80, 15], "balance": true },
      "cam": { "distance": 15.2, "blink_count": 5 }
    }'
);

-- 4. 피드백 이력(Feedback_Logs) 추가: 휴식 권고 발생 기록 [cite: 1143, 1147]
-- (currval을 사용하여 방금 들어간 log_id를 참조합니다)
INSERT INTO Feedback_Logs (user_id, trigger_log_id, timestamp, method, is_break_taken)
VALUES (
    '202210866', 
    currval('fatigue_logs_log_id_seq'), 
    '2026-05-08 21:46:00', 
    'MOUSE_VIBRATION', 
    true -- 피드백을 받고 실제로 휴식을 취함 [cite: 1145]
);