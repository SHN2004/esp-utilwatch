// UtilWatch music watch for Android: shows what's playing and controls it, through
// the UtilWatch phone app in android/ (works with Spotify, YouTube Music, any app with
// media controls). The messages are Bangle.js's protocol, text lines over the Nordic UART
// Bluetooth service, so Gadgetbridge works too, minus the cover and player logo.
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
#include "logos.h"

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
std::string source;                // the playing app's package name; only the UtilWatch app sends this
std::string art;                   // the cover: 288 bytes of 48x48 XBM, or empty; only the UtilWatch app sends this
uint32_t duration, reportedPosition, reportedAt;  // seconds; 0 duration = not known yet (bar hidden)
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

void setPosition(uint32_t seconds) {
  reportedPosition = seconds;
  reportedAt = millis();
}

void handleLine(std::string &line) {
  if (!line.empty() && line[0] == 0x10) line.erase(0, 1);  // DLE prefix: tells a real Bangle.js not to echo
  if (line.compare(0, 3, "GB(") != 0) return;              // e.g. setTime(...): not needed yet
  std::string t;
  if (!gbField(line, "t", t)) return;
  if (t == "musicinfo") {
    std::string oldArtist = artist, oldTrack = track;
    gbField(line, "artist", artist);
    gbField(line, "track", track);
    gbField(line, "source", source);
    gbNumber(line, "dur", duration);
    if (artist != oldArtist || track != oldTrack) setPosition(0);  // a new song doesn't always come with a position
  } else if (t == "musicstate") {
    gbField(line, "state", state);
    uint32_t position;
    if (gbNumber(line, "position", position)) setPosition(position);
  } else if (t == "musicart") {
    gbField(line, "art", art);
    Serial.printf("got cover, %u bytes\n", (unsigned)art.size());
    return;
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
      if (i == SEL) send("playpause", state == "play" ? "Pause" : "Play");
      if (i != SEL && connected) setPosition(0);  // a skip starts at 0, and the phone doesn't always say so
    } else if (hold && i != SEL && now - lastRamp >= RAMP_MS) {  // SELECT hold = Back: no-op here
      send(i == UP ? "volumeup" : "volumedown", i == UP ? "Vol +" : "Vol -");
      lastRamp = now;
    }
  }
}

const int COVER_SIZE = 48;
const int COL_X = COVER_SIZE + 4;    // the column of text right of the cover
const int WAVE_Y = 57, WAVE_AMP = 6;  // the waveform strip along the bottom: centre line, tallest bar
const int SCROLL_REST = 50;          // scroll steps (30 ms each) to rest at the start, so the title can be read

// Draws the title, scrolling it sideways if it's wider than the column.
// The cover is drawn after it, which hides the text scrolling off to the left.
void drawTitle() {
  const char *s = track.c_str();
  int w = u8g2.getStrWidth(s);
  if (w <= 128 - COL_X) {
    u8g2.drawStr(COL_X, 28, s);
    return;
  }
  int span = w + 30;  // gap before the text comes round again
  int step = millis() / 30 % (span + SCROLL_REST);
  int x = COL_X - max(0, step - SCROLL_REST);
  u8g2.drawStr(x, 28, s);
  u8g2.drawStr(x + span, 28, s);
}

// The cover, or the player's logo in a frame if there isn't one, with one corner cut off.
void drawCover(const uint8_t *logo) {
  u8g2.setDrawColor(0);
  u8g2.drawBox(0, 0, COL_X, 30);
  u8g2.setDrawColor(1);
  if (art.size() == COVER_SIZE * COVER_SIZE / 8) {
    u8g2.drawXBM(0, 0, COVER_SIZE, COVER_SIZE, (const uint8_t *)art.data());
  } else {
    u8g2.drawFrame(0, 0, COVER_SIZE, COVER_SIZE);
    u8g2.drawXBM((COVER_SIZE - LOGO_SIZE) / 2, (COVER_SIZE - LOGO_SIZE) / 2, LOGO_SIZE, LOGO_SIZE, logo);
  }
  u8g2.setDrawColor(0);
  for (int i = 0; i < 6; i++) u8g2.drawHLine(COVER_SIZE - 1 - i, COVER_SIZE - 6 + i, i + 1);
  u8g2.setDrawColor(1);
  if (art.empty()) u8g2.drawLine(COVER_SIZE - 1, COVER_SIZE - 7, COVER_SIZE - 7, COVER_SIZE - 1);  // closes the frame
}

// The progress bar, solid up to the playhead. It only looks like a waveform: the watch never
// gets the audio, so the shape is made up from the song's name, the same each time for one song.
// While playing, the bars just behind the playhead move; that's what says "playing" on this screen.
void drawWave(int head, bool playing) {
  uint32_t h = 2166136261u;
  for (char c : track) h = (h ^ (uint8_t)c) * 16777619u;
  for (int x = 0; x < 126; x += 3) {
    h = h * 1664525u + 1013904223u;
    float envelope = sin(x * .05f + 1) * .35f + .65f;
    int amp = min(WAVE_AMP, 1 + (int)(envelope * ((h >> 24) % 5 + 2)));
    if (x >= head) {
      u8g2.drawHLine(x, WAVE_Y, 2);
      continue;
    }
    if (playing && head - x < 15) amp = max(1, amp - (int)((millis() / 90 + x) % 4));
    u8g2.drawBox(x, WAVE_Y - amp, 2, 2 * amp + 1);
  }
  u8g2.drawVLine(head, WAVE_Y - WAVE_AMP - 1, 2 * WAVE_AMP + 2);
}

void drawSong() {
  bool spotify = source == "com.spotify.music";
  // Match the end only: patched YouTube Music builds start with something else.
  bool ytMusic = source.size() >= 13 && source.compare(source.size() - 13, 13, "youtube.music") == 0;
  const uint8_t *logo = spotify ? LOGO_SPOTIFY : ytMusic ? LOGO_YT_MUSIC : LOGO_MUSIC;

  u8g2.setFont(u8g2_font_6x13B_tf);
  drawTitle();
  drawCover(logo);
  u8g2.drawXBM(COL_X, 0, LOGO_SIZE, LOGO_SIZE, logo);
  u8g2.setFont(u8g2_font_5x8_tf);
  u8g2.drawStr(COL_X + LOGO_SIZE + 3, 10, spotify ? "SPOTIFY" : ytMusic ? "YT MUSIC" : "MUSIC");
  if (state == "pause") {
    u8g2.drawBox(120, 2, 3, 9);
    u8g2.drawBox(125, 2, 3, 9);
  }
  u8g2.drawStr(COL_X, 38, artist.c_str());  // ponytail: long artists run off the edge; only the title moves

  bool playing = state == "play";
  uint32_t position = duration ? gbPosition(reportedPosition, millis() - reportedAt, playing, duration) : 0;
  drawWave(duration ? 128 * position / duration : 0, playing && duration);
  if (duration && millis() - lastCmdAt >= 1000) {
    char times[24];
    snprintf(times, sizeof times, "%02lu:%02lu/%02lu:%02lu", (unsigned long)position / 60, (unsigned long)position % 60,
             (unsigned long)duration / 60, (unsigned long)duration % 60);
    u8g2.drawStr(COL_X, 47, times);
  }
}

// Nothing to show: a flat line, and while looking for the phone the playhead sweeps across it.
void drawIdle() {
  u8g2.setFont(u8g2_font_spleen8x16_mf);
  u8g2.drawStr(0, 14, connected ? "Nothing playing" : "Connecting");
  u8g2.setFont(u8g2_font_5x8_tf);
  if (!connected) u8g2.drawStr(0, 25, "Open the phone app");
  for (int x = 0; x < 126; x += 3) u8g2.drawHLine(x, WAVE_Y, 2);
  if (!connected) u8g2.drawVLine(millis() / 20 % 128, WAVE_Y - WAVE_AMP - 1, 2 * WAVE_AMP + 2);
}

void draw() {
  u8g2.clearBuffer();
  bool hasSong = connected && !track.empty();
  if (hasSong) drawSong();
  else drawIdle();
  if (millis() - lastCmdAt < 1000) u8g2.drawStr(hasSong ? COL_X : 0, 47, lastCmd);  // where the times go
  u8g2.sendBuffer();
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);  // don't block on prints when nothing is reading the port
  while (!Serial && millis() < 3000) delay(10);  // up to 3 s for the Mac to open the port, so boot logs aren't lost
  for (int i = 0; i < 3; i++) pinMode(PINS[i], INPUT_PULLUP);
  u8g2.begin();
  u8g2.setFontMode(1);  // transparent, so one line of text can't blank part of another
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
