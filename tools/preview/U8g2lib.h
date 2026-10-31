// Stand-in for U8g2's Arduino class: same method names, backed by the real U8g2 C
// library, but sendBuffer() records a frame instead of talking I2C.
#pragma once
#include "u8g2.h"
#include <vector>

#define U8X8_PIN_NONE 255

struct Frame { uint32_t ms; std::vector<uint8_t> buf; };
extern std::vector<Frame> frames;
extern uint32_t fake_ms, frame_ms;

class U8G2 {
 protected:
  u8g2_t u;
  static uint8_t nop(u8x8_t *, uint8_t, uint8_t, void *) { return 1; }

 public:
  void begin() {}
  void clearBuffer() { u8g2_ClearBuffer(&u); }
  void sendBuffer() {
    uint8_t *b = u8g2_GetBufferPtr(&u);
    frames.push_back({fake_ms, std::vector<uint8_t>(b, b + 1024)});
    fake_ms += frame_ms;
  }
  void setFont(const uint8_t *f) { u8g2_SetFont(&u, f); }
  int getStrWidth(const char *s) { return u8g2_GetStrWidth(&u, s); }
  void drawStr(int x, int y, const char *s) { u8g2_DrawStr(&u, x, y, s); }
  void drawPixel(int x, int y) { if (x >= 0 && y >= 0 && x < 128 && y < 64) u8g2_DrawPixel(&u, x, y); }
  void drawBox(int x, int y, int w, int h) { u8g2_DrawBox(&u, x, y, w, h); }
  void drawFrame(int x, int y, int w, int h) { u8g2_DrawFrame(&u, x, y, w, h); }
  void drawHLine(int x, int y, int w) { u8g2_DrawHLine(&u, x, y, w); }
  void drawXBMP(int x, int y, int w, int h, const uint8_t *b) { u8g2_DrawXBMP(&u, x, y, w, h, b); }
  void setDrawColor(int c) { u8g2_SetDrawColor(&u, c); }
  void setClipWindow(int x0, int y0, int x1, int y1) { u8g2_SetClipWindow(&u, x0, y0, x1, y1); }
  void setMaxClipWindow() { u8g2_SetMaxClipWindow(&u); }
  void setContrast(int) {}
};

class U8G2_SH1106_128X64_NONAME_F_HW_I2C : public U8G2 {
 public:
  U8G2_SH1106_128X64_NONAME_F_HW_I2C(const u8g2_cb_t *r, int, int, int) {
    u8g2_Setup_sh1106_128x64_noname_f(&u, r, nop, nop);
  }
};
