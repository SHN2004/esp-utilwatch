// UtilWatch music watch for Android: shows what's playing and controls it, through
// the Gadgetbridge app (works with Spotify, YouTube Music, any app with media controls).
// The watch pretends to be a Bangle.js, a watch Gadgetbridge supports: it speaks
// Bangle.js's protocol, text lines over the Nordic UART Bluetooth service.
//
// Button grammar, the same in every UtilWatch app: tap = the app's action, hold ~600 ms =
// the secondary axis, and holding SELECT always means Back / exit to home. Double-tap
// SELECT is reserved as a quick-action slot (not implemented: it costs ~250 ms of tap latency).
//   UP   tap = previous track, hold = volume up (ramps)
//   DOWN tap = next track,     hold = volume down (ramps)
//   SELECT tap = play/pause,   hold = Back (nothing to go back to here, so no-op)
// Wiring: same as buttons_test (GPIO 4/5/6 to GND) + the OLED on 19/20.

#include <Arduino.h>
#include <U8g2lib.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLESecurity.h>
#include <freertos/stream_buffer.h>
#include "gb.h"

#define SDA_PIN 19
#define SCL_PIN 20

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, SCL_PIN, SDA_PIN);

const uint8_t PINS[3] = {4, 5, 6};  // UP, DOWN, SELECT
enum { UP, DOWN, SEL };
const uint32_t DEBOUNCE_MS = 25;
const uint32_t HOLD_MS = 600;  // shorter is a tap (sent on release), longer is a hold
const uint32_t RAMP_MS = 150;  // one volume step per this while UP/DOWN stays held

// Nordic UART service. Gadgetbridge writes to RX and listens to TX.
#define UART_SERVICE "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define UART_RX "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
#define UART_TX "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

BLECharacteristic *tx;
StreamBufferHandle_t rxStream;  // bytes from the phone, handed from the BLE task to loop()
volatile bool connected = false;

std::string artist, track, state;  // Latin-1, straight from Gadgetbridge
const char *lastCmd = "";
uint32_t lastCmdAt;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override {
    connected = true;
    Serial.println("phone connected");
  }
  void onDisconnect(BLEServer *) override {
    connected = false;
    Serial.println("phone disconnected");
    BLEDevice::startAdvertising();  // so the phone can come back
  }
};

class RxCallbacks : public BLECharacteristicCallbacks {
  // Runs in the Bluetooth task: just queue the bytes, loop() does the work.
  void onWrite(BLECharacteristic *c) override { xStreamBufferSend(rxStream, c->getData(), c->getLength(), 0); }
};

// Sends a music command: playpause, next, previous, volumeup or volumedown.
// Gadgetbridge rejects anything else, and drops the character before '\n', hence "\r\n".
void send(const char *cmd, const char *label) {
  lastCmd = label;
  lastCmdAt = millis();
  Serial.printf("sent %s\n", cmd);
  if (!connected) return;
  char msg[48];
  int len = snprintf(msg, sizeof msg, "{\"t\":\"music\",\"n\":\"%s\"}\r\n", cmd);
  for (int i = 0; i < len; i += 20) {  // 20 bytes fits the smallest Bluetooth packet; Gadgetbridge rejoins lines
    tx->setValue((uint8_t *)msg + i, min(20, len - i));
    tx->notify();
  }
}

void handleLine(std::string &line) {
  if (!line.empty() && line[0] == 0x10) line.erase(0, 1);  // DLE prefix: tells a real Bangle.js not to echo
  if (line.compare(0, 3, "GB(") != 0) return;              // e.g. setTime(...): not needed yet
  std::string t;
  if (!gbField(line, "t", t)) return;
  if (t == "musicinfo") {
    gbField(line, "artist", artist);
    gbField(line, "track", track);
  } else if (t == "musicstate") {
    gbField(line, "state", state);
  } else {
    return;  // notifications, weather, ...
  }
  Serial.printf("got %s\n", line.substr(0, 120).c_str());
}

// Joins the phone's bytes into lines.
void pollPhone() {
  static std::string line;
  static bool tooLong = false;
  uint8_t buf[64];
  size_t n;
  while ((n = xStreamBufferReceive(rxStream, buf, sizeof buf, 0)) > 0) {
    for (size_t i = 0; i < n; i++) {
      if (buf[i] != '\n') {
        if (line.size() < 1024) line += (char)buf[i];
        else tooLong = true;  // drop this line (e.g. a huge notification), keep going
        continue;
      }
      if (!tooLong) handleLine(line);
      line.clear();
      tooLong = false;
    }
  }
}

void pollButtons() {
  static bool held[3];
  static uint32_t changedAt[3], lastRamp;
  uint32_t now = millis();

  for (int i = 0; i < 3; i++) {
    bool down = digitalRead(PINS[i]) == LOW;
    bool hold = held[i] && now - changedAt[i] >= HOLD_MS;
    if (down != held[i] && now - changedAt[i] > DEBOUNCE_MS) {  // press or release edge
      held[i] = down;
      changedAt[i] = now;
      if (down || hold) continue;  // a press is decided on release; a hold already acted
      if (i == UP) send("previous", "Previous");
      if (i == DOWN) send("next", "Next");
      if (i == SEL) send("playpause", "Play/Pause");
    } else if (hold && i != SEL && now - lastRamp >= RAMP_MS) {  // SELECT hold = Back: no-op here
      send(i == UP ? "volumeup" : "volumedown", i == UP ? "Vol +" : "Vol -");
      lastRamp = now;
    }
  }
}

// Draws text at y, scrolling it sideways if it's wider than the screen.
void drawScrolling(const std::string &s, int y) {
  int w = u8g2.getStrWidth(s.c_str());
  if (w <= 128) {
    u8g2.drawStr(0, y, s.c_str());
    return;
  }
  int span = w + 30;  // gap before the text comes round again
  int x = -(int)(millis() / 30 % span);
  u8g2.drawStr(x, y, s.c_str());
  u8g2.drawStr(x + span, y, s.c_str());
}

void draw() {
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tf);
  u8g2.drawStr(0, 10, connected ? "Phone connected" : "Waiting for phone");
  if (state == "play") {
    u8g2.drawTriangle(120, 2, 120, 10, 127, 6);
  } else if (state == "pause") {
    u8g2.drawBox(120, 2, 3, 9);
    u8g2.drawBox(125, 2, 3, 9);
  }
  u8g2.drawHLine(0, 13, 128);

  if (track.empty()) {
    u8g2.drawStr(0, 32, connected ? "Play some music" : "Open Gadgetbridge");
  } else {
    u8g2.setFont(u8g2_font_helvB10_tf);
    drawScrolling(track, 32);
    u8g2.setFont(u8g2_font_6x10_tf);
    drawScrolling(artist, 46);
  }
  if (millis() - lastCmdAt < 1000) u8g2.drawStr(0, 62, lastCmd);
  u8g2.sendBuffer();
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);  // don't block on prints when nothing is reading the port
  while (!Serial && millis() < 3000) delay(10);  // up to 3 s for the Mac to open the port, so boot logs aren't lost
  for (int i = 0; i < 3; i++) pinMode(PINS[i], INPUT_PULLUP);
  u8g2.begin();
  rxStream = xStreamBufferCreate(2048, 1);

  BLEDevice::init("Bangle.js UtilWatch");  // Gadgetbridge recognizes Bangle.js by its name
  BLESecurity *security = new BLESecurity();
  security->setCapability(ESP_IO_CAP_NONE);            // "Just Works", if you choose to pair in Gadgetbridge
  security->setAuthenticationMode(true, false, true);  // bond, no MITM, secure connections

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());
  BLEService *uart = server->createService(UART_SERVICE);
  BLECharacteristic *rx = uart->createCharacteristic(UART_RX, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  rx->setCallbacks(new RxCallbacks());
  tx = uart->createCharacteristic(UART_TX, BLECharacteristic::PROPERTY_NOTIFY);
  uart->start();

  // Name only: the name plus a 128-bit service UUID doesn't fit in one advertisement,
  // and Gadgetbridge goes by the name.
  BLEDevice::startAdvertising();
  Serial.println("Advertising as Bangle.js UtilWatch");
}

void loop() {
  pollPhone();
  pollButtons();
  draw();
}
