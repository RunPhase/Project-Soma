-- 김민준 씨의 피로도 로그와 피드백 결과 한눈에 보기
SELECT 
    u.name AS "사용자",
    fl.status AS "상태",
    fb.method AS "피드백",
    fb.is_break_taken AS "휴식여부"
FROM Users u
JOIN Fatigue_Logs fl ON u.user_id = fl.user_id
JOIN Feedback_Logs fb ON fl.log_id = fb.trigger_log_id;