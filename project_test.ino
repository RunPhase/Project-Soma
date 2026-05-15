/*
  FSR 406 압력센서 2개 테스트
  Arduino UNO R3
*/

const int fsrPin1 = A0;
const int fsrPin2 = A1;

int fsrValue1 = 0;
int fsrValue2 = 0;

float weight1 = 0;
float weight2 = 0;

void setup() {

  Serial.begin(9600);

}

void loop() {

  // 센서값 읽기
  fsrValue1 = analogRead(fsrPin1);
  fsrValue2 = analogRead(fsrPin2);

  // 임시 kg 변환
  weight1 = (fsrValue1 / 1023.0) * 10.0;
  weight2 = (fsrValue2 / 1023.0) * 10.0;

  // 출력
  Serial.print("Sensor1 : ");
  Serial.print(fsrValue1);

  Serial.print("   Weight1 : ");
  Serial.print(weight1);
  Serial.print(" kg");

  Serial.print("    |    ");

  Serial.print("Sensor2 : ");
  Serial.print(fsrValue2);

  Serial.print("   Weight2 : ");
  Serial.print(weight2);
  Serial.println(" kg");

  delay(1000);
}