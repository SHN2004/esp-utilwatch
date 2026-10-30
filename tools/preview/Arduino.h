// Just enough of Arduino for watch.ino to run on the Mac (see preview.py).
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <math.h>

#define PROGMEM
#define pgm_read_byte(p) (*(const uint8_t *)(p))

extern uint32_t fake_ms;  // virtual clock, advanced by sendBuffer() and delay()
inline uint32_t millis() { return fake_ms; }
inline void delay(uint32_t ms) { fake_ms += ms; }
inline long random(long lo, long hi) { return lo + rand() % (hi - lo); }
inline void randomSeed(unsigned long s) { srand(s); }
inline uint32_t esp_random() { return 42; }
