// UtilWatch firmware: ESP32-C6 SuperMini + 1.3" SH1106 OLED (SDA 19, SCL 20)
// Boot animation: heartbeat -> heart burst -> "booting with love" -> photo zooms out
// from the middle -> hearts float up over it. Press RST on the board to replay.
// Preview on the Mac without flashing: python3 tools/preview/preview.py

#include <Arduino.h>
#include <U8g2lib.h>
#include "couple.h"  // regenerate with tools/img2xbm.py

#define SDA_PIN 19
#define SCL_PIN 20

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE, SCL_PIN, SDA_PIN);

// Types live up here: the Arduino IDE declares every function above the first one,
// so a type used in a function signature must be defined before that.
struct Shape { uint8_t w, h; const char *const *rows; };
struct Floater { float x, y, speed, phase; bool big; };

// ---- Pixel-art hearts. '#' = lit; the gap near the top left is the shine. ----

static const char *const HEART_S_ROWS[] = {
  ".##.##.",
  "#######",
  "#######",
  ".#####.",
  "..###..",
  "...#...",
};
static const char *const HEART_M_ROWS[] = {
  "..###.###..",
  ".#########.",
  "##.########",
  "###########",
  "###########",
  ".#########.",
  "..#######..",
  "...#####...",
  "....###....",
  ".....#.....",
};
static const char *const HEART_L_ROWS[] = {
  "...####...####...",
  "..######.######..",
  ".##.############.",
  "##.##############",
  "#################",
  "#################",
  ".###############.",
  "..#############..",
  "...###########...",
  "....#########....",
  ".....#######.....",
  "......#####......",
  ".......###.......",
  "........#........",
};
static const Shape HEART_S = {7, 6, HEART_S_ROWS};
static const Shape HEART_M = {11, 10, HEART_M_ROWS};
static const Shape HEART_L = {17, 14, HEART_L_ROWS};

static bool shapeAt(const Shape &s, int x, int y) {
  return x >= 0 && y >= 0 && x < s.w && y < s.h && s.rows[y][x] == '#';
}

enum HeartStyle { FILLED, OUTLINE, HALO };  // HALO = filled with a black ring, for drawing over the photo

// Draws a heart centered on (cx, cy).
void drawHeart(int cx, int cy, const Shape &s, HeartStyle style = FILLED) {
  int x0 = cx - s.w / 2, y0 = cy - s.h / 2;
  if (style == HALO) {
    u8g2.setDrawColor(0);
    for (int y = -1; y <= s.h; y++)
      for (int x = -1; x <= s.w; x++)
        if (shapeAt(s, x, y) || shapeAt(s, x - 1, y) || shapeAt(s, x + 1, y) || shapeAt(s, x, y - 1) || shapeAt(s, x, y + 1))
          u8g2.drawPixel(x0 + x, y0 + y);
    u8g2.setDrawColor(1);
  }
  for (int y = 0; y < s.h; y++)
    for (int x = 0; x < s.w; x++) {
      if (!shapeAt(s, x, y)) continue;
      bool edge = !shapeAt(s, x - 1, y) || !shapeAt(s, x + 1, y) || !shapeAt(s, x, y - 1) || !shapeAt(s, x, y + 1);
      if (style != OUTLINE || edge) u8g2.drawPixel(x0 + x, y0 + y);
    }
}

// ---- Timing helpers: animations run on the clock, not on frame count, ----
// ---- so they keep the same speed whatever the I2C bus speed is.       ----
static float clamp01(float x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
static float easeOut(float x) { x = 1 - x; return 1 - x * x * x; }
static float easeOutBack(float x) {  // overshoots a little, then settles
  const float c1 = 1.70158f, c3 = c1 + 1;
  x -= 1;
  return 1 + c3 * x * x * x + c1 * x * x;
}

// Calls draw(t) for each frame until `ms` have passed. t runs 0..1.
template <typename F> void animate(uint32_t ms, F draw) {
  uint32_t start = millis();
  for (;;) {
    float t = clamp01((millis() - start) / (float)ms);
    u8g2.clearBuffer();
    draw(t);
    u8g2.sendBuffer();
    if (t >= 1) break;
  }
}

// ---- Scenes ----

// Lub-dub, lub-dub: the heart jumps to the big size on each beat.
void heartbeat() {
  animate(1700, [](float t) {
    int ms = t * 1700;
    bool beat = (ms > 250 && ms < 370) || (ms > 470 && ms < 570) ||
                (ms > 1050 && ms < 1170) || (ms > 1270 && ms < 1370);
    drawHeart(64, 32, beat ? HEART_L : HEART_M);
  });
}

// The heart pops into ten little hearts that fly out to the edges.
void heartBurst() {
  animate(650, [](float t) {
    float r = 70 * easeOut(t);
    for (int i = 0; i < 10; i++) {
      float a = i * 0.6283f + 0.3f;  // 36 degrees apart
      drawHeart(64 + cosf(a) * r, 32 + sinf(a) * r * 0.6f, HEART_S);
    }
    if (t < 0.15f) drawHeart(64, 32, HEART_L);
  });
}

// Five hearts fill in one by one; each pops big for a moment when it fills.
void lovingBar() {
  animate(2200, [](float t) {
    const int N = 5, GAP = 17, x0 = 64 - (N - 1) * GAP / 2;
    float filled = t * 1.15f * N;  // finishes a little early, then holds
    for (int i = 0; i < N; i++) {
      float since = filled - i;  // how long ago (in hearts) this one filled
      if (since < 0) drawHeart(x0 + i * GAP, 24, HEART_M, OUTLINE);
      else drawHeart(x0 + i * GAP, 24, since < 0.25f ? HEART_L : HEART_M);
    }
    u8g2.setFont(u8g2_font_minicute_tr);
    const char *msg = "booting with love";
    int w = u8g2.getStrWidth(msg), x = 64 - w / 2;
    u8g2.drawStr(x, 50, msg);
    int dots = (int)(t * 9) % 4;
    for (int d = 0; d < dots; d++) u8g2.drawBox(x + w + 2 + d * 3, 49, 1, 1);
  });
}

static bool photoPixel(int x, int y) {
  return (pgm_read_byte(&couple_bits[y * (couple_W / 8) + x / 8]) >> (x & 7)) & 1;
}

// PowerPoint-style zoom: the photo grows out of the center, overshoots, settles.
void photoZoom() {
  animate(900, [](float t) {
    float s = easeOutBack(t);
    if (s < 0.02f) return;
    for (int y = 0; y < 64; y++) {
      int sy = 32 + (y - 32) / s;
      if (sy < 0 || sy >= couple_H) continue;
      for (int x = 0; x < 128; x++) {
        int sx = 64 + (x - 64) / s;
        if (sx >= 0 && sx < couple_W && photoPixel(sx, sy)) u8g2.drawPixel(x, y);
      }
    }
  });
}

// ---- Floating hearts over the photo, forever ----
static Floater floaters[6];

// Columns where hearts may rise without covering a face. Tuned for couple.h:
// left edge, the gap between the two of them, right edge.
static const int LANES[] = {6, 76, 121};

void respawn(Floater &f) {
  f.x = LANES[random(0, 3)] + random(-2, 3);
  f.y = 72;  // just below the screen
  f.speed = random(12, 26);  // pixels per second
  f.phase = random(0, 628) / 100.0f;
  f.big = random(0, 4) == 0;
}

void setup() {
  u8g2.begin();
  randomSeed(esp_random());

  heartbeat();
  heartBurst();
  lovingBar();
  photoZoom();

  for (int i = 0; i < 6; i++) {
    respawn(floaters[i]);
    floaters[i].y += i * 14;  // stagger the first wave
  }
}

void loop() {
  static uint32_t last = millis();
  uint32_t now = millis();
  float dt = (now - last) / 1000.0f;
  last = now;

  u8g2.clearBuffer();
  u8g2.drawXBMP(0, 0, couple_W, couple_H, couple_bits);
  for (auto &f : floaters) {
    f.y -= f.speed * dt;
    if (f.y < -10) respawn(f);
    float wobble = sinf(now / 400.0f + f.phase) * 3;
    drawHeart(f.x + wobble, f.y, f.big ? HEART_M : HEART_S, HALO);
  }
  u8g2.sendBuffer();
}
