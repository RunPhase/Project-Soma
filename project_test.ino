#include <Wire.h>
#include "Adafruit_VL53L0X.h"

/*
  FSR 406 압력센서 4개 + VL53L0X V2 거리센서 2개
  Arduino UNO R3

  출력 결과:
  1. LEFT_FRONT 압력
  2. RIGHT_FRONT 압력
  3. LEFT_BACK 압력
  4. RIGHT_BACK 압력
  5. 좌우 균형 결과
  6. 앞뒤 균형 결과
  7. VL53L0X_1 거리
  8. VL53L0X_2 거리
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

String leftRightBias = "";
String frontBackBias = "";

// =======================
// 적외선 거리센서 변수
// =======================
int distance1 = 0;
int distance2 = 0;

void setup() {
  Serial.begin(9600);
  Wire.begin();

  pinMode(xshut1, OUTPUT);
  pinMode(xshut2, OUTPUT);

  // VL53L0X 두 개 모두 OFF
  digitalWrite(xshut1, LOW);
  digitalWrite(xshut2, LOW);
  delay(10);

  // 1번 센서 ON 후 주소 변경
  digitalWrite(xshut1, HIGH);
  delay(10);

  if (!tof1.begin(TOF1_ADDRESS)) {
    Serial.println("VL53L0X_1 연결 실패");
    while (1);
  }

  // 2번 센서 ON 후 주소 변경
  digitalWrite(xshut2, HIGH);
  delay(10);

  if (!tof2.begin(TOF2_ADDRESS)) {
    Serial.println("VL53L0X_2 연결 실패");
    while (1);
  }

  Serial.println("Sensor System Started");
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
  VL53L0X_RangingMeasurementData_t measure2;

  tof1.rangingTest(&measure1, false);
  tof2.rangingTest(&measure2, false);

  if (measure1.RangeStatus != 4) {
    distance1 = measure1.RangeMilliMeter;
  } else {
    distance1 = -1;
  }

  if (measure2.RangeStatus != 4) {
    distance2 = measure2.RangeMilliMeter;
  } else {
    distance2 = -1;
  }

  // =======================
  // 4. 결과 출력
  // =======================
  Serial.println("================================");

  Serial.print("LEFT_FRONT_PRESSURE : ");
  Serial.print(LEFT_FRONT, 2);
  Serial.println(" kg");

  Serial.print("RIGHT_FRONT_PRESSURE : ");
  Serial.print(RIGHT_FRONT, 2);
  Serial.println(" kg");

  Serial.print("LEFT_BACK_PRESSURE : ");
  Serial.print(LEFT_BACK, 2);
  Serial.println(" kg");

  Serial.print("RIGHT_BACK_PRESSURE : ");
  Serial.print(RIGHT_BACK, 2);
  Serial.println(" kg");

  Serial.print("LEFT_RIGHT_BALANCE : ");
  Serial.println(leftRightBias);

  Serial.print("FRONT_BACK_BALANCE : ");
  Serial.println(frontBackBias);

  Serial.print("VL53L0X_1_DISTANCE : ");
  if (distance1 == -1) {
    Serial.println("Out of range");
  } else {
    Serial.print(distance1);
    Serial.println(" mm");
  }

  Serial.print("VL53L0X_2_DISTANCE : ");
  if (distance2 == -1) {
    Serial.println("Out of range");
  } else {
    Serial.print(distance2);
    Serial.println(" mm");
  }

  delay(1000);
}
