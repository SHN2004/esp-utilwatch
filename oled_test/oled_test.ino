// OLED test for ESP32-C6 SuperMini (purple board, 10 pins per side)
// Wiring: 3V3->VCC, GND->GND, GPIO19->SDA, GPIO20->SCL
//
// Arduino IDE setup:
//   Board: "ESP32C6 Dev Module" (needs esp32 board package v3.x)
//   Tools > USB CDC On Boot: "Enabled"
//   Library: U8g2 (by olikraus) from Library Manager
//
// Step 1: it scans the I2C bus and prints what it finds to Serial Monitor (115200 baud).
//         You should see "Found device at 0x3C" (sometimes 0x3D).
// Step 2: it draws text and a counter on the screen.

#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>

#define SDA_PIN 19
#define SCL_PIN 20

// ---- Pick the line that matches your screen's driver chip ----
// 1.3" screens are usually SH1106. 0.96" screens are usually SSD1306.
// If the image looks shifted, has a 2-pixel garbage strip on one side, or is
// scrambled, comment this line out and use the other one.
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, SCL_PIN, SDA_PIN);
// U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, SCL_PIN, SDA_PIN);

void scanI2C() {
  Wire.begin(SDA_PIN, SCL_PIN);
  Serial.println("Scanning I2C bus...");
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.printf("Found device at 0x%02X\n", addr);
      found++;
    }
  }
  if (found == 0) {
    Serial.println("Nothing found. Check wiring: SDA/SCL swapped? VCC/GND swapped? Loose jumper?");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);  // give the USB serial a moment to connect
  scanI2C();

  u8g2.begin();
  Serial.println("Display started.");
}

void loop() {
  static uint32_t count = 0;

  u8g2.clearBuffer();
  u8g2.drawFrame(0, 0, 128, 64);
  u8g2.setFont(u8g2_font_ncenB10_tr);
  u8g2.drawStr(8, 20, "Hello, watch!");
  u8g2.setFont(u8g2_font_logisoso20_tn);
  char buf[12];
  snprintf(buf, sizeof(buf), "%lu", (unsigned long)count++);
  u8g2.drawStr(8, 54, buf);
  u8g2.sendBuffer();

  delay(1000);
}
