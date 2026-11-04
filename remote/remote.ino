// UtilWatch media remote: the 3 buttons control Spotify (or any media app) on a
// phone over Bluetooth LE, as a HID "consumer control" device, the same kind of
// device as headset buttons. No app needed on the phone; works on Android and iPhone.
//
// Button grammar, the same in every UtilWatch app: tap = the app's action, hold ~600 ms =
// the secondary axis, and holding SELECT always means Back / exit to home. Double-tap
// SELECT is reserved as a quick-action slot (not implemented: it costs ~250 ms of tap latency).
//   UP   tap = previous track, hold = volume up (ramps)
//   DOWN tap = next track,     hold = volume down (ramps)
//   SELECT tap = play/pause,   hold = Back (nothing to go back to here, so no-op)
// Wiring: GPIO 4/5/6 to GND (UP, DOWN, SELECT) + the OLED on 19/20.
// The phone bonds once; the bond is saved in flash, so it reconnects after reboots.

#include <Arduino.h>
#include <U8g2lib.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEHIDDevice.h>
#include <BLESecurity.h>

#define SDA_PIN 19
#define SCL_PIN 20

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, SCL_PIN, SDA_PIN);

const uint8_t PINS[3] = {4, 5, 6};  // UP, DOWN, SELECT
enum { UP, DOWN, SEL };
const uint32_t DEBOUNCE_MS = 25;
const uint32_t HOLD_MS = 600;  // shorter is a tap (sent on release), longer is a hold
const uint32_t RAMP_MS = 150;  // one volume step per this while UP/DOWN stays held

// The phone reads this map once when pairing. iOS ignores media keys from a device
// that's only a media remote, so it also declares a standard keyboard (report 2),
// like camera-shutter remotes do. The keyboard report is never sent.
// Media keys (report 1): one bit per key, in this order.
enum Key : uint8_t { VOL_UP = 1, VOL_DOWN = 2, PLAY_PAUSE = 4, NEXT = 8, PREV = 16 };
const uint8_t REPORT_MAP[] = {
  0x05, 0x01,  // Usage Page (Generic Desktop)
  0x09, 0x06,  // Usage (Keyboard)
  0xA1, 0x01,  // Collection (Application)
  0x85, 0x02,  //   Report ID (2)
  0x05, 0x07,  //   Usage Page (Keyboard): 8 modifier bits
  0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x08, 0x81, 0x02,
  0x95, 0x01, 0x75, 0x08, 0x81, 0x01,  //   reserved byte
  0x95, 0x06, 0x75, 0x08, 0x15, 0x00, 0x25, 0x65,  //   6 key codes
  0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00,
  0xC0,        // End Collection
  0x05, 0x0C,  // Usage Page (Consumer)
  0x09, 0x01,  // Usage (Consumer Control)
  0xA1, 0x01,  // Collection (Application)
  0x85, 0x01,  //   Report ID (1)
  0x15, 0x00,  //   Logical Minimum (0)
  0x25, 0x01,  //   Logical Maximum (1)
  0x75, 0x01,  //   Report Size (1 bit)
  0x95, 0x05,  //   Report Count (5)
  0x09, 0xE9,  //   Usage (Volume Increment)
  0x09, 0xEA,  //   Usage (Volume Decrement)
  0x09, 0xCD,  //   Usage (Play/Pause)
  0x09, 0xB5,  //   Usage (Scan Next Track)
  0x09, 0xB6,  //   Usage (Scan Previous Track)
  0x81, 0x02,  //   Input (Data, Variable, Absolute)
  0x95, 0x03,  //   Report Count (3)
  0x81, 0x01,  //   Input (Constant): pad to a full byte
  0xC0         // End Collection
};

BLECharacteristic *input;
volatile bool connected = false;
const char *lastCmd = "-";

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

class SecurityCallbacks : public BLESecurityCallbacks {
  void onAuthenticationComplete(ble_gap_conn_desc *desc) override {
    Serial.printf("pairing %s (bonded: %d)\n", desc->sec_state.encrypted ? "ok, encrypted" : "FAILED", desc->sec_state.bonded);
  }
};

// Says whether each key report reached the phone. The phone only receives them
// after it subscribes to the report, which it does once pairing is encrypted.
class ReportCallbacks : public BLECharacteristicCallbacks {
  void onStatus(BLECharacteristic *, Status s, uint32_t code) override {
    const char *names[] = {"ok (indicate)", "ok", "indicate disabled", "phone not subscribed (notify disabled)",
                           "GATT error", "no client", "phone not subscribed", "indicate timeout", "indicate failed"};
    if (s != SUCCESS_NOTIFY) Serial.printf("  report not delivered: %s, code %lu\n", names[s], (unsigned long)code);
  }
};

// Send the keys as held (bits set) or released (0). Over BLE the report ID isn't
// part of the value; the phone knows it from the characteristic.
void sendKeys(uint8_t keys) {
  if (!connected) return;
  input->setValue(&keys, 1);
  input->notify();
}

void tap(Key k, const char *name) {
  sendKeys(k);
  delay(15);  // iOS can miss a press whose release arrives in the same radio slot
  sendKeys(0);
  lastCmd = name;
  Serial.printf("sent %s\n", name);
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);  // don't block on prints when nothing is reading the port
  while (!Serial && millis() < 3000) delay(10);  // up to 3 s for the Mac to open the port, so boot logs aren't lost
  for (int i = 0; i < 3; i++) pinMode(PINS[i], INPUT_PULLUP);
  u8g2.begin();

  BLEDevice::init("UtilWatch");
  BLESecurity *security = new BLESecurity();
  security->setCapability(ESP_IO_CAP_NONE);          // "Just Works": no PIN on a watch
  security->setAuthenticationMode(true, false, true);  // bond, no MITM, secure connections
  BLEDevice::setSecurityCallbacks(new SecurityCallbacks());

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCallbacks());

  BLEHIDDevice *hid = new BLEHIDDevice(server);
  hid->manufacturer()->setValue("UtilWatch");
  hid->pnp(0x02, 0xE502, 0xA111, 0x0210);  // USB vendor/product IDs; arbitrary for a DIY device
  hid->hidInfo(0x00, 0x01);
  hid->reportMap((uint8_t *)REPORT_MAP, sizeof(REPORT_MAP));
  // ponytail: one report characteristic only. On NimBLE the core's BLE library drops every
  // characteristic after the first with the same UUID (BLEService::addCharacteristic), and
  // all HID reports share UUID 0x2A4D. Switch to the NimBLE-Arduino library if we ever need
  // to actually send keyboard keys.
  input = hid->inputReport(1);
  input->setCallbacks(new ReportCallbacks());
  hid->setBatteryLevel(100);  // ponytail: fixed until the battery step adds a real reading
  hid->startServices();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->setAppearance(0x03C1);  // keyboard: what iOS expects (it may hide the on-screen keyboard while connected)
  adv->addServiceUUID(hid->hidService()->getUUID());
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("Advertising as UtilWatch");
}

void loop() {
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
      if (i == UP) tap(PREV, "Previous");
      if (i == DOWN) tap(NEXT, "Next");
      if (i == SEL) tap(PLAY_PAUSE, "Play/Pause");
    } else if (hold && i != SEL && now - lastRamp >= RAMP_MS) {  // SELECT hold = Back: no-op here
      tap(i == UP ? VOL_UP : VOL_DOWN, i == UP ? "Vol +" : "Vol -");
      lastRamp = now;
    }
  }

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_6x10_tr);
  u8g2.drawStr(0, 10, "UtilWatch remote");
  u8g2.drawHLine(0, 13, 128);
  u8g2.drawStr(0, 28, connected ? "Connected" : "Pairing... open");
  if (!connected) u8g2.drawStr(0, 40, "phone's Bluetooth");
  u8g2.setFont(u8g2_font_helvB12_tr);
  u8g2.drawStr(0, 62, lastCmd);
  u8g2.sendBuffer();
}
