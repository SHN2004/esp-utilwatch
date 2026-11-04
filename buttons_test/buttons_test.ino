// Button test for the UtilWatch: 3 tactile buttons + the SH1106 OLED.
// Wiring: each button between a GPIO and GND (no resistors, internal pull-ups):
//   GPIO 4 = UP, GPIO 5 = DOWN, GPIO 6 = SELECT
// Each button shows as a box on screen that fills while held, with a press count.
// Serial Monitor (115200) prints every press and release.
// A box that's filled before you touch anything = that button is wired to two legs
// of the same pair (always connected). Move one wire to the diagonal leg.
// Wiring diagram: wiring.svg in this folder.

#include <Arduino.h>
#include <U8g2lib.h>

#define SDA_PIN 19
#define SCL_PIN 20

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, SCL_PIN, SDA_PIN);

const uint8_t PINS[3] = {4, 5, 6};
const char *NAMES[3] = {"UP", "DOWN", "SEL"};
const uint32_t DEBOUNCE_MS = 25;  // raise if one press counts as two

bool held[3];
uint32_t changedAt[3], presses[3];

void setup() {
  Serial.begin(115200);
  // Drop serial output instead of waiting when nothing on the Mac is reading the port.
  // Otherwise each print blocks up to 2 s once the 256-byte USB buffer fills.
  Serial.setTxTimeoutMs(0);
  for (int i = 0; i < 3; i++) pinMode(PINS[i], INPUT_PULLUP);  // unpressed reads HIGH
  u8g2.begin();

  delay(1500);  // give the USB serial a moment to connect
  for (int i = 0; i < 3; i++)
    if (digitalRead(PINS[i]) == LOW)
      Serial.printf("WARNING: %s (GPIO %d) reads pressed with nothing touched. Check it's wired to diagonal legs.\n", NAMES[i], PINS[i]);
  Serial.println("Ready. Press each button.");
}

void loop() {
  uint32_t now = millis();
  for (int i = 0; i < 3; i++) {
    bool down = digitalRead(PINS[i]) == LOW;  // pressed connects the pin to GND
    // Debounce: ignore changes until the contact has settled.
    if (down != held[i] && now - changedAt[i] > DEBOUNCE_MS) {
      held[i] = down;
      changedAt[i] = now;
      if (down) presses[i]++;
      Serial.printf("%s %s (GPIO %d, presses: %lu)\n", NAMES[i], down ? "pressed" : "released", PINS[i], presses[i]);
    }
  }

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tr);
  for (int i = 0; i < 3; i++) {
    int x = 10 + i * 40;
    if (held[i]) u8g2.drawBox(x, 4, 28, 28);
    else u8g2.drawFrame(x, 4, 28, 28);
    u8g2.drawStr(x + (28 - u8g2.getStrWidth(NAMES[i])) / 2, 46, NAMES[i]);
    char n[8];
    snprintf(n, sizeof(n), "%lu", (unsigned long)presses[i]);
    u8g2.drawStr(x + (28 - u8g2.getStrWidth(n)) / 2, 60, n);
  }
  u8g2.sendBuffer();
}
