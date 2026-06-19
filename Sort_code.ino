#include <Wire.h>
#include "Adafruit_VL53L0X.h"

/*
  FSR 406 압력센서 4개 + VL53L0X V2 거리센서 2개
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
// VL53L0X XSHUT 핀
// =======================
const int xshut1 = 2;
const int xshut2 = 3;

Adafruit_VL53L0X tof1 = Adafruit_VL53L0X();
Adafruit_VL53L0X tof2 = Adafruit_VL53L0X();

#define TOF1_ADDRESS 0x30
#define TOF2_ADDRESS 0x31

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

// String 대신 메모리를 차지하지 않는 const char* 포인터 사용
const char* leftRightBias = "";
const char* frontBackBias = "";

// =======================
// 적외선 거리센서 변수
// =======================
int distance1 = 0;
int distance2 = 0;

void setup() {
  Serial.begin(9600);
  Wire.begin();

  pinMode(xshut1, OUTPUT);
  // pinMode(xshut2, OUTPUT);

  // VL53L0X 두 개 모두 OFF
  digitalWrite(xshut1, LOW);
  // digitalWrite(xshut2, LOW);
  delay(10);

  // 1번 센서 ON 후 주소 변경
  digitalWrite(xshut1, HIGH);
  delay(10);

  if (!tof1.begin(TOF1_ADDRESS)) {
    Serial.println(F("VL53L0X_1 연결 실패")); // F() 매크로 적용
    while (1);
  }

  // 2번 센서 ON 후 주소 변경
  // digitalWrite(xshut2, HIGH);
  // delay(10);

  // if (!tof2.begin(TOF2_ADDRESS)) {
  //   Serial.println(F("VL53L0X_2 연결 실패")); // F() 매크로 적용
  //   while (1);
  // }

  Serial.println(F("Sensor System Started")); // F() 매크로 적용
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
  // 3. 적외선 거리센서 2개 읽기
  // =======================
  VL53L0X_RangingMeasurementData_t measure1;
  // VL53L0X_RangingMeasurementData_t measure2;

  tof1.rangingTest(&measure1, false);
  // tof2.rangingTest(&measure2, false);

  if (measure1.RangeStatus != 4) {
    distance1 = measure1.RangeMilliMeter;
  } else {
    distance1 = -1;
  }

  // if (measure2.RangeStatus != 4) {
  //   distance2 = measure2.RangeMilliMeter;
  // } else {
  //   distance2 = -1;
  // }

// =======================
  // 4. 결과 출력 규격 개조 (CSV 포맷)
  // 데이터 순서: FL,FR,BL,BR,dist1,dist2
  // =======================
  
  // 1. 압력센서 4개 날것의 값(analogRead 값인 0~1023) 출력
  Serial.print(leftFrontValue);   Serial.print(F(","));
  Serial.print(rightFrontValue);  Serial.print(F(","));
  Serial.print(leftBackValue);    Serial.print(F(","));
  Serial.print(rightBackValue);   Serial.print(F(","));
  // 결과적으로 LF, RF, LB, RB 순으로 출력됨

  // 2. 거리센서 2개 값 출력 (Out of range인 경우 파이썬 처리를 위해 -1 출력)
  Serial.print(distance1);        
  // Serial.print(F(","));
  // Serial.print(distance2);        
  // 결과적으로 1번, 2번 순으로 출력됨

  // 줄바꿈으로 한 세트 종료 알림
  Serial.println();

  delay(1000);
}
