// UtilWatch firmware for Android: a watch face and a music player, reached from a home
// screen. The UtilWatch phone app in android/ sends the time, weather, phone battery and
// what's playing (Spotify, YouTube Music, any app with media controls), and takes back music
// commands. The messages are Bangle.js's protocol, text lines over the Nordic UART Bluetooth
// service, so Gadgetbridge can drive the player too, minus the cover and player logo.
//
// Button grammar, the same in every UtilWatch app: tap = the app's action, hold ~600 ms =
// the secondary axis, and holding SELECT always means Back / exit to home. Double-tap
// SELECT is reserved as a quick-action slot (not implemented: it costs ~250 ms of tap latency).
//   Home:   UP/DOWN tap = scroll, SELECT tap = open
//   Player: UP   tap = previous track, hold = volume up (ramps)
//           DOWN tap = next track,     hold = volume down (ramps)
//           SELECT tap = play/pause
// Left alone, it goes to the watch face and dims, then turns the screen off. The first
// press after that only wakes it.
// Wiring: same as buttons_test (GPIO 4/5/6 to GND) + the OLED on 19/20.

#include <Arduino.h>
#include <U8g2lib.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLESecurity.h>
#include <freertos/stream_buffer.h>
#include <time.h>
#include "button.h"
#include "gb.h"
#include "logos.h"

#define SDA_PIN 19
#define SCL_PIN 20

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, SCL_PIN, SDA_PIN);

const uint8_t PINS[3] = {4, 5, 6};  // UP, DOWN, SELECT
enum { UP, DOWN, SEL };
Button buttons[3];

const uint32_t DIM_MS = 15000;    // left alone this long: watch face, dimmed
const uint32_t SLEEP_MS = 60000;  // left alone this long: screen off
const uint8_t BRIGHT_CONTRAST = 255, DIM_CONTRAST = 1;  // tune to the panel: the SH1106's range is narrow

// Nordic UART service. The phone writes to RX and listens to TX.
#define UART_SERVICE "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define UART_RX "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
#define UART_TX "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

BLECharacteristic *tx;
StreamBufferHandle_t rxStream;  // bytes from the phone, handed from the BLE task to loop()
volatile bool connected = false;

std::string artist, track, state;  // Latin-1, straight from the phone
std::string source;                // the playing app's package name; only the UtilWatch app sends this
std::string art;                   // the cover: 288 bytes of 48x48 XBM, or empty; only the UtilWatch app sends this
uint32_t duration, reportedPosition, reportedAt;  // seconds; 0 duration = not known yet (bar hidden)
const char *lastCmd = "";
uint32_t lastCmdAt;

// The rest only the UtilWatch app sends.
uint32_t clockLocal, clockAt;  // the phone's wall clock in seconds, and millis() when it said so; 0 = not known yet
uint32_t phoneBattery;
bool hasPhoneBattery = false;
std::string weatherTemp, weatherKind;
uint32_t weatherAt;

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
  if (line.compare(0, 3, "GB(") != 0) return;              // e.g. Gadgetbridge's setTime(...): not used
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
  } else if (t == "time") {
    if (gbNumber(line, "local", clockLocal)) clockAt = millis();
  } else if (t == "battery") {
    if (gbNumber(line, "level", phoneBattery)) hasPhoneBattery = true;
  } else if (t == "weather") {
    gbField(line, "temp", weatherTemp);
    gbField(line, "kind", weatherKind);
    weatherAt = millis();
  } else {
    return;  // notifications, ...
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

enum Screen { HOME, FACE, PLAYER };
const int CARDS = 2;  // home's cards, in order: the face, the player
Screen screen = HOME;
int card = 0, prevCard = 0, scrollDir = 1;
uint32_t scrolledAt;
const uint32_t SCROLL_MS = 180;

const int COVER_SIZE = 48;
const int COL_X = COVER_SIZE + 4;    // the column of text right of the cover
const int WAVE_Y = 57, WAVE_AMP = 6;  // the waveform strip along the bottom: centre line, tallest bar
const int SCROLL_REST = 50;          // scroll steps (30 ms each) to rest at the start, so the title can be read
const uint32_t WEATHER_STALE_MS = 3 * 3600000UL;

const uint8_t *playerLogo() {
  if (source == "com.spotify.music") return LOGO_SPOTIFY;
  // Match the end only: patched YouTube Music builds start with something else.
  if (source.size() >= 13 && source.compare(source.size() - 13, 13, "youtube.music") == 0) return LOGO_YT_MUSIC;
  return LOGO_MUSIC;
}

const uint8_t *weatherIcon() {
  if (weatherKind == "clear") return LOGO_CLEAR;
  if (weatherKind == "cloud") return LOGO_CLOUD;
  if (weatherKind == "rain") return LOGO_RAIN;
  if (weatherKind == "snow") return LOGO_SNOW;
  if (weatherKind == "storm") return LOGO_STORM;
  if (weatherKind == "fog") return LOGO_FOG;
  return nullptr;
}

bool hasWeather() { return !weatherTemp.empty() && millis() - weatherAt < WEATHER_STALE_MS; }

// Draws text from x to the right edge at y, scrolling it sideways if it doesn't fit. Whatever
// is drawn afterwards on its left hides the text scrolling off that way.
void drawScrolling(const std::string &text, int x, int y, int right) {
  const char *s = text.c_str();
  int w = u8g2.getStrWidth(s);
  if (w <= right - x) {
    u8g2.drawStr(x, y, s);
    return;
  }
  int span = w + 30;  // gap before the text comes round again
  int step = millis() / 30 % (span + SCROLL_REST);
  int left = x - max(0, step - SCROLL_REST);
  u8g2.drawStr(left, y, s);
  u8g2.drawStr(left + span, y, s);
}

// The cover, or the player's logo in a frame if there isn't one, with one corner cut off.
void drawCover(int x, int y) {
  int far = COVER_SIZE - 1;
  if (art.size() == COVER_SIZE * COVER_SIZE / 8) {
    u8g2.drawXBM(x, y, COVER_SIZE, COVER_SIZE, (const uint8_t *)art.data());
  } else {
    u8g2.drawFrame(x, y, COVER_SIZE, COVER_SIZE);
    u8g2.drawXBM(x + (COVER_SIZE - LOGO_SIZE) / 2, y + (COVER_SIZE - LOGO_SIZE) / 2, LOGO_SIZE, LOGO_SIZE, playerLogo());
  }
  u8g2.setDrawColor(0);
  for (int i = 0; i < 6; i++) u8g2.drawHLine(x + far - i, y + far - 5 + i, i + 1);
  u8g2.setDrawColor(1);
  if (art.size() != COVER_SIZE * COVER_SIZE / 8) u8g2.drawLine(x + far, y + far - 6, x + far - 6, y + far);  // closes the frame
}

// A strip that looks like a waveform, solid up to the playhead. Nothing here hears audio: the
// shape only comes from the seed. While moving, the bars just behind the playhead jump.
void drawWave(uint32_t seed, int head, bool moving) {
  uint32_t h = seed;
  for (int x = 0; x < 126; x += 3) {
    h = h * 1664525u + 1013904223u;
    float envelope = sin(x * .05f + 1) * .35f + .65f;
    int amp = min(WAVE_AMP, 1 + (int)(envelope * ((h >> 24) % 5 + 2)));
    if (x >= head) {
      u8g2.drawHLine(x, WAVE_Y, 2);
      continue;
    }
    if (moving && head - x < 15) amp = max(1, amp - (int)((millis() / 90 + x) % 4));
    u8g2.drawBox(x, WAVE_Y - amp, 2, 2 * amp + 1);
  }
  u8g2.drawVLine(head, WAVE_Y - WAVE_AMP - 1, 2 * WAVE_AMP + 2);
}

uint32_t songPosition() {
  return duration ? gbPosition(reportedPosition, millis() - reportedAt, state == "play", duration) : 0;
}

// The song's waveform up to where it's got to, the same on every screen that shows it.
void drawSongWave() {
  uint32_t seed = 2166136261u;  // one song always gets the same shape
  for (char c : track) seed = (seed ^ (uint8_t)c) * 16777619u;
  drawWave(seed, duration ? 128 * songPosition() / duration : 0, state == "play" && duration);
}

void drawFlatWave() {
  for (int x = 0; x < 126; x += 3) u8g2.drawHLine(x, WAVE_Y, 2);
}

// The local date and time, or false if the phone hasn't said yet. ESP32's millis() runs on
// through a screen-off, and the phone corrects any drift every 30 minutes while connected.
bool localTime(struct tm *out) {
  if (!clockLocal) return false;
  time_t t = clockLocal + (millis() - clockAt) / 1000;
  gmtime_r(&t, out);  // clockLocal already has the timezone in it
  return true;
}

// "TUE 04 NOV"
void formatDate(const struct tm &tm, char *out, size_t size) {
  strftime(out, size, "%a %d %b", &tm);
  for (char *c = out; *c; c++) *c = toupper(*c);
}

// A phone outline filled up to its battery level, then the percent.
void drawPhoneBattery(int x, int baseline) {
  int top = baseline - 8;
  u8g2.drawFrame(x, top, 6, 9);
  u8g2.drawBox(x + 1, top + 1 + 7 - min(phoneBattery, 100ul) * 7 / 100, 4, min(phoneBattery, 100ul) * 7 / 100);
  char s[6];
  snprintf(s, sizeof s, "%lu%%", (unsigned long)phoneBattery);
  u8g2.drawStr(x + 8, baseline, s);
}

void drawFace() {
  struct tm tm;
  bool known = localTime(&tm);
  u8g2.setFont(u8g2_font_5x8_tf);
  if (known) {
    char date[16];
    formatDate(tm, date, sizeof date);
    u8g2.drawStr(0, 8, date);
  }
  if (!connected) {
    u8g2.drawStr(128 - u8g2.getStrWidth("NO LINK"), 8, "NO LINK");
  } else if (hasPhoneBattery) {
    drawPhoneBattery(98, 8);
  }

  char hhmm[6] = "--:--";
  if (known) snprintf(hhmm, sizeof hhmm, "%02d:%02d", tm.tm_hour, tm.tm_min);
  u8g2.setFont(u8g2_font_spleen16x32_mn);
  u8g2.drawStr(0, 41, hhmm);

  if (hasWeather()) {
    const uint8_t *icon = weatherIcon();
    if (icon) u8g2.drawXBM(92, 14, LOGO_SIZE, LOGO_SIZE, icon);
    std::string temp = weatherTemp + "\xB0";  // a degree sign, in Latin-1
    u8g2.setFont(u8g2_font_6x13B_tf);
    u8g2.drawStr(92, 40, temp.c_str());
  }

  if (connected && !track.empty()) drawSongWave();
  else drawFlatWave();
}

void drawSong() {
  bool spotify = playerLogo() == LOGO_SPOTIFY, ytMusic = playerLogo() == LOGO_YT_MUSIC;

  u8g2.setFont(u8g2_font_6x13B_tf);
  drawScrolling(track, COL_X, 28, 128);
  u8g2.setDrawColor(0);
  u8g2.drawBox(0, 0, COL_X, 30);
  u8g2.setDrawColor(1);
  drawCover(0, 0);
  u8g2.drawXBM(COL_X, 0, LOGO_SIZE, LOGO_SIZE, playerLogo());
  u8g2.setFont(u8g2_font_5x8_tf);
  u8g2.drawStr(COL_X + LOGO_SIZE + 3, 10, spotify ? "SPOTIFY" : ytMusic ? "YT MUSIC" : "MUSIC");
  if (state == "pause") {
    u8g2.drawBox(120, 2, 3, 9);
    u8g2.drawBox(125, 2, 3, 9);
  }
  u8g2.drawStr(COL_X, 38, artist.c_str());  // ponytail: long artists run off the edge; only the title moves

  drawSongWave();
  if (duration && millis() - lastCmdAt >= 1000) {
    uint32_t position = songPosition();
    char times[24];
    snprintf(times, sizeof times, "%02lu:%02lu/%02lu:%02lu", (unsigned long)position / 60, (unsigned long)position % 60,
             (unsigned long)duration / 60, (unsigned long)duration % 60);
    u8g2.drawStr(COL_X, 47, times);
  }
}

// No song: a flat line, and while looking for the phone the playhead sweeps across it.
void drawNoSong() {
  u8g2.setFont(u8g2_font_spleen8x16_mf);
  u8g2.drawStr(0, 14, connected ? "Nothing playing" : "Connecting");
  u8g2.setFont(u8g2_font_5x8_tf);
  if (!connected) u8g2.drawStr(0, 25, "Open the phone app");
  drawFlatWave();
  if (!connected) u8g2.drawVLine(millis() / 20 % 128, WAVE_Y - WAVE_AMP - 1, 2 * WAVE_AMP + 2);
}

void drawPlayer() {
  bool hasSong = connected && !track.empty();
  if (hasSong) drawSong();
  else drawNoSong();
  if (millis() - lastCmdAt < 1000) u8g2.drawStr(hasSong ? COL_X : 0, 47, lastCmd);  // where the times go
}

const int SPINE_W = 13, CARD_X = SPINE_W + 5, DOTS_X = 118;

// The solid strip down a card's left side: hazard stripes, and the card's name read sideways.
void drawSpine(const char *name, int dy) {
  u8g2.drawBox(0, dy, SPINE_W, 64);
  u8g2.setDrawColor(0);
  for (int k = 0; k < 4; k++)
    for (int i = 0; i < SPINE_W; i++) u8g2.drawHLine(i, dy + k * 5 + i / 3, 1);
  u8g2.setFont(u8g2_font_spleen6x12_mf);  // bold fills in the M and W when small
  u8g2.setFontDirection(3);
  u8g2.drawStr(10, dy + 62, name);
  u8g2.setFontDirection(0);
  u8g2.setDrawColor(1);
}

void drawFaceCard(int dy) {
  struct tm tm;
  bool known = localTime(&tm);
  char hhmm[6] = "--:--";
  if (known) snprintf(hhmm, sizeof hhmm, "%02d:%02d", tm.tm_hour, tm.tm_min);
  u8g2.setFont(u8g2_font_spleen12x24_mn);
  u8g2.drawStr(CARD_X, dy + 22, hhmm);
  u8g2.setFont(u8g2_font_5x8_tf);
  if (known) {
    char date[16];
    formatDate(tm, date, sizeof date);
    u8g2.drawStr(CARD_X, dy + 36, date);
  }
  if (hasWeather()) {
    const uint8_t *icon = weatherIcon();
    if (icon) u8g2.drawXBM(CARD_X, dy + 46, LOGO_SIZE, LOGO_SIZE, icon);
    std::string temp = weatherTemp + "\xB0";
    u8g2.drawStr(CARD_X + LOGO_SIZE + 3, dy + 56, temp.c_str());
  }
  if (connected && hasPhoneBattery) drawPhoneBattery(CARD_X + 50, dy + 56);
  drawSpine("WATCH", dy);
}

void drawPlayerCard(int dy) {
  bool hasSong = connected && !track.empty();
  int textX = CARD_X + COVER_SIZE + 4;
  u8g2.setFont(u8g2_font_6x13B_tf);
  drawScrolling(hasSong ? track : std::string(connected ? "No music" : "No phone"), textX, dy + 26, DOTS_X);
  u8g2.setDrawColor(0);
  u8g2.drawBox(0, dy, textX, 30);
  u8g2.setDrawColor(1);
  if (hasSong) drawCover(CARD_X, dy + 8);
  else u8g2.drawXBM(CARD_X + (COVER_SIZE - LOGO_SIZE) / 2, dy + 25, LOGO_SIZE, LOGO_SIZE, LOGO_MUSIC);
  u8g2.setFont(u8g2_font_5x8_tf);
  if (hasSong) {
    u8g2.drawStr(textX, dy + 37, artist.c_str());
    u8g2.drawStr(textX, dy + 50, state == "play" ? "PLAYING" : state == "pause" ? "PAUSED" : "");
  }
  drawSpine("MUSIC", dy);
}

void drawCard(int which, int dy) {
  if (which == 0) drawFaceCard(dy);
  else drawPlayerCard(dy);
}

void drawHome() {
  uint32_t elapsed = millis() - scrolledAt;
  if (elapsed < SCROLL_MS) {  // the new card slides in over 180 ms, slowing as it lands
    uint32_t left = SCROLL_MS - elapsed;
    int dy = scrollDir * 64 * (int)(left * left / SCROLL_MS) / (int)SCROLL_MS;
    drawCard(prevCard, dy - scrollDir * 64);
    drawCard(card, dy);
  } else {
    drawCard(card, 0);
  }
  u8g2.setDrawColor(0);  // text running long stops short of the position marks
  u8g2.drawBox(DOTS_X, 0, 128 - DOTS_X, 64);
  u8g2.setDrawColor(1);
  for (int i = 0; i < CARDS; i++) {
    if (i == card) u8g2.drawBox(122, 24 + i * 10, 5, 5);
    else u8g2.drawFrame(122, 24 + i * 10, 5, 5);
  }
}

void draw() {
  u8g2.clearBuffer();
  if (screen == FACE) drawFace();
  else if (screen == PLAYER) drawPlayer();
  else drawHome();
  u8g2.sendBuffer();
}

bool dimmed = false, screenOff = false;
uint32_t lastInputAt;

void wake() {
  u8g2.setPowerSave(0);
  u8g2.setContrast(BRIGHT_CONTRAST);
  dimmed = screenOff = false;
}

// ponytail: only the screen sleeps. The CPU and radio stay fully on so the phone stays connected;
// use light sleep between frames when battery life on the LiPo becomes the problem.
void pollIdle() {
  uint32_t idle = millis() - lastInputAt;
  if (idle >= SLEEP_MS && !screenOff) {
    u8g2.setPowerSave(1);
    screenOff = true;
  } else if (idle >= DIM_MS && !dimmed) {
    screen = FACE;
    card = prevCard = 0;
    u8g2.setContrast(DIM_CONTRAST);
    dimmed = true;
  }
}

void scrollHome(int dir) {
  prevCard = card;
  card = (card + dir + CARDS) % CARDS;
  scrollDir = dir;
  scrolledAt = millis();
}

void onTap(int i) {
  if (screen == HOME) {
    if (i == UP) scrollHome(-1);
    if (i == DOWN) scrollHome(1);
    if (i == SEL) screen = card == 0 ? FACE : PLAYER;
  } else if (screen == PLAYER) {
    if (i == UP) send("previous", "Previous");
    if (i == DOWN) send("next", "Next");
    if (i == SEL) send("playpause", state == "play" ? "Pause" : "Play");
    if (i != SEL && connected) setPosition(0);  // a skip starts at 0, and the phone doesn't always say so
  }
}

void onHold(int i) {
  if (i == SEL) screen = HOME;
  else if (screen == PLAYER) send(i == UP ? "volumeup" : "volumedown", i == UP ? "Vol +" : "Vol -");
}

void pollButtons() {
  uint32_t now = millis();
  for (int i = 0; i < 3; i++) {
    ButtonEvent e = buttons[i].update(digitalRead(PINS[i]) == LOW, now);
    if (e == NO_EVENT) continue;
    lastInputAt = now;
    if (e == PRESSED && dimmed) {  // this press only wakes the screen
      wake();
      buttons[i].ignored = true;
    }
    if (e == TAPPED) onTap(i);
    if (e == HELD) onHold(i);
  }
}

void setup() {
  Serial.begin(115200);
  Serial.setTxTimeoutMs(0);  // don't block on prints when nothing is reading the port
  while (!Serial && millis() < 3000) delay(10);  // up to 3 s for the Mac to open the port, so boot logs aren't lost
  for (int i = 0; i < 3; i++) pinMode(PINS[i], INPUT_PULLUP);
  u8g2.begin();
  u8g2.setFontMode(1);  // transparent, so one line of text can't blank part of another
  rxStream = xStreamBufferCreate(2048, 1);
  lastInputAt = millis();

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
  pollIdle();
  if (!screenOff) draw();
}
