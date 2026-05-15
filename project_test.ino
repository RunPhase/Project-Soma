/*
  FSR 406 압력센서 2개
  좌우 압력 편향 감지 코드
  Arduino UNO R3
*/

const int leftPin = A0;
const int rightPin = A1;

int leftValue = 0;
int rightValue = 0;

float LEFT = 0.0;
float RIGHT = 0.0;

float difference = 0.0;

String direction = "";

void setup() {

  Serial.begin(9600);

}

void loop() {

  // 센서값 읽기
  leftValue = analogRead(leftPin);
  rightValue = analogRead(rightPin);

  // 임시 kg 변환
  LEFT = (leftValue / 1023.0) * 10.0;
  RIGHT = (rightValue / 1023.0) * 10.0;

  // 차이값 계산
  // 양수면 LEFT 압력이 더 큼
  // 음수면 RIGHT 압력이 더 큼
  difference = LEFT - RIGHT;

  // 방향 판단
  if (difference > 0.5) {

    direction = "LEFT";

  }
  else if (difference < -0.5) {

    direction = "RIGHT";

  }
  else {

    direction = "CENTER";

  }

  // 출력
  Serial.print("LEFT : ");
  Serial.print(LEFT, 2);
  Serial.print(" kg");

  Serial.print("    |    ");

  Serial.print("RIGHT : ");
  Serial.print(RIGHT, 2);
  Serial.print(" kg");

  Serial.print("    |    ");

  Serial.print("DIFF : ");
  Serial.print(difference, 2);
  Serial.print(" kg");

  Serial.print("    |    ");

  Serial.print("BIAS : ");
  Serial.println(direction);

  delay(1000);
}
