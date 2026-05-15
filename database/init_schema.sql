DROP TABLE IF EXISTS Feedback_Logs CASCADE;
DROP TABLE IF EXISTS Health_Reports CASCADE;
DROP TABLE IF EXISTS Fatigue_Logs CASCADE;
DROP TABLE IF EXISTS User_Settings CASCADE;
DROP TABLE IF EXISTS Users CASCADE;

DROP TYPE IF EXISTS user_status CASCADE;
DROP TYPE IF EXISTS report_period CASCADE;
DROP TYPE IF EXISTS feedback_method CASCADE;

-- 1. 사용자 상태 및 리포트 주기 정의 (ENUM) 
CREATE TYPE user_status AS ENUM ('NORMAL', 'CAUTION', 'DANGER');
CREATE TYPE report_period AS ENUM ('DAILY', 'WEEKLY');

-- 2. Users 테이블 (사용자 기본 정보 관리)
CREATE TABLE Users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(), -- 고유 식별자 
    name VARCHAR(50) NOT NULL, -- 사용자 이름
    age INT, -- 나이
    job_type VARCHAR(50), -- 직업군 (예: 개발자, 프로게이머 등)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 계정 생성일
);

-- 3. User_Settings 테이블 (개인화 설정 저장) 
CREATE TABLE User_Settings (
    user_id UUID PRIMARY KEY REFERENCES Users(user_id) ON DELETE CASCADE,
    default_pressure_value JSONB, -- 초기 기준 압력값 (유연한 확장을 위해 JSONB 사용) 
    notification_method VARCHAR(50), -- 알림 방식 (진동, 화면 조정 등)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 최종 수정일 
);

-- 4. Fatigue_Logs 테이블 (핵심 시계열 피로도 데이터) 
CREATE TABLE Fatigue_Logs (
    log_id BIGSERIAL PRIMARY KEY, -- 대용량 로그를 위한 BIGSERIAL 
    user_id UUID REFERENCES Users(user_id) ON DELETE CASCADE,
    timestamp TIMESTAMP NOT NULL, -- 데이터 수집 시점 (시간축 동기화용)
    status user_status NOT NULL, -- 현재 상태 (정상/주의/위험)
    fatigue_score FLOAT, -- 분석된 통합 피로도 점수
    raw_data_summary JSONB -- 컴퓨터와 사용자 간 거리, 눈 깜빡임 등 가변 수치 통합 저장 
);

-- 시계열 데이터 조회 최적화를 위한 인덱스 생성 
CREATE INDEX idx_fatigue_logs_timestamp ON Fatigue_Logs(timestamp);

-- 5. 피드백 종류 정의
CREATE TYPE feedback_method AS ENUM (
    'UI_ALERT',         
    'AMBIENT_LIGHT',    
    'CURSOR_CHANGE',    
    'KEYBOARD_FILTER',  
    'MOUSE_VIBRATION'   
);

-- 6. 피드백 이력 및 휴식 여부 추적 테이블 
CREATE TABLE Feedback_Logs (
    feedback_id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES Users(user_id) ON DELETE CASCADE,
    trigger_log_id BIGINT REFERENCES Fatigue_Logs(log_id) ON DELETE SET NULL, -- 어떤 피로도 로그(위험 상태) 때문에 이 피드백이 발생했는지 추적 
    timestamp TIMESTAMP NOT NULL,
    method feedback_method NOT NULL,
    is_break_taken BOOLEAN DEFAULT FALSE  -- 휴식을 취했는지 여부
);

-- 인덱스 생성
CREATE INDEX idx_feedback_logs_timestamp ON Feedback_Logs(timestamp);
CREATE INDEX idx_feedback_logs_user_id ON Feedback_Logs(user_id);