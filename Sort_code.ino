#include <Wire.h>
#include "Adafruit_VL53L0X.h"

/*
  FSR 406 압력센서 4개 + VL53L0X V2 거리센서 1개 (2번 센서 제거됨)
  Arduino UNO R3
*/

// =======================
// FSR 압력센서 핀
// =======================
const int leftFrontPin  = A0;
const int rightFrontPin = A1;
const int leftBackPin   = A2;
const int rightBackPin  = A3;

// =======================
// VL53L0X XSHUT 핀 (1번만 사용)
// =======================
const int xshut1 = 2;

Adafruit_VL53L0X tof1 = Adafruit_VL53L0X();
#define TOF1_ADDRESS 0x30

// =======================
// 압력센서 변수
// =======================
int leftFrontValue = 0;
int rightFrontValue = 0;
int leftBackValue = 0;
int rightBackValue = 0;

float LEFT_FRONT = 0.0;
float RIGHT_FRONT = 0.0;
float LEFT_BACK = 0.0;
float RIGHT_BACK = 0.0;

float LEFT_TOTAL = 0.0;
float RIGHT_TOTAL = 0.0;
float FRONT_TOTAL = 0.0;
float BACK_TOTAL = 0.0;

float leftRightDiff = 0.0;
float frontBackDiff = 0.0;

const char* leftRightBias = "";
const char* frontBackBias = "";

// =======================
// 적외선 거리센서 변수
// =======================
int distance1 = 0;

void setup() {
  Serial.begin(9600);
  Wire.begin();

  pinMode(xshut1, OUTPUT);

  // VL53L0X 리셋 (OFF)
  digitalWrite(xshut1, LOW);
  delay(10);

  // 1번 센서 ON 후 주소 변경
  digitalWrite(xshut1, HIGH);
  delay(10);

  if (!tof1.begin(TOF1_ADDRESS)) {
    Serial.println(F("VL53L0X_1 연결 실패")); 
    while (1);
  }

  Serial.println(F("Sensor System Started")); 
}

void loop() {

  // =======================
  // 1. 압력센서 4개 읽기
  // =======================
  leftFrontValue  = analogRead(leftFrontPin);
  rightFrontValue = analogRead(rightFrontPin);
  leftBackValue   = analogRead(leftBackPin);
  rightBackValue  = analogRead(rightBackPin);

  // 임시 kg 변환
  LEFT_FRONT  = (leftFrontValue / 1023.0) * 10.0;
  RIGHT_FRONT = (rightFrontValue / 1023.0) * 10.0;
  LEFT_BACK   = (leftBackValue / 1023.0) * 10.0;
  RIGHT_BACK  = (rightBackValue / 1023.0) * 10.0;

  // =======================
  // 2. 좌우 / 앞뒤 균형 계산
  // =======================
  LEFT_TOTAL  = LEFT_FRONT + LEFT_BACK;
  RIGHT_TOTAL = RIGHT_FRONT + RIGHT_BACK;

  FRONT_TOTAL = LEFT_FRONT + RIGHT_FRONT;
  BACK_TOTAL  = LEFT_BACK + RIGHT_BACK;

  leftRightDiff = LEFT_TOTAL - RIGHT_TOTAL;
  frontBackDiff = FRONT_TOTAL - BACK_TOTAL;

  // 좌우 균형 판단
  if (leftRightDiff > 1.0) {
    leftRightBias = "LEFT";
  }
  else if (leftRightDiff < -1.0) {
    leftRightBias = "RIGHT";
  }
  else {
    leftRightBias = "CENTER";
  }

  // 앞뒤 균형 판단
  if (frontBackDiff > 1.0) {
    frontBackBias = "FRONT";
  }
  else if (frontBackDiff < -1.0) {
    frontBackBias = "BACK";
  }
  else {
    frontBackBias = "CENTER";
  }

  // =======================
  // 3. 적외선 거리센서 1개 읽기
  // =======================
  VL53L0X_RangingMeasurementData_t measure1;
  tof1.rangingTest(&measure1, false);

  if (measure1.RangeStatus != 4) {
    distance1 = measure1.RangeMilliMeter;
  } else {
    distance1 = -1;
  }

  // =======================
  // 4. 결과 출력 (CSV 포맷 유지)
  // 데이터 순서: FL,FR,BL,BR,dist1,dist2(더미값)
  // =======================
  
  // 압력센서 4개 출력
  Serial.print(leftFrontValue);   Serial.print(F(","));
  Serial.print(rightFrontValue);  Serial.print(F(","));
  Serial.print(leftBackValue);    Serial.print(F(","));
  Serial.print(rightBackValue);   Serial.print(F(","));

  // 1번 거리센서 출력
  Serial.print(distance1);        Serial.print(F(" "));
  
  // [핵심] 파이썬 백엔드 호환성을 위해 삭제된 2번 센서 자리에 -1 고정 출력
  Serial.print(" ");

  // 줄바꿈으로 한 세트 종료
  Serial.println();

  delay(1000);
}
