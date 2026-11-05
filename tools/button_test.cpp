// Checks music/button.h against taps, holds, bouncy contacts and a press that only wakes the screen.
//   clang++ -std=c++17 tools/button_test.cpp -o /tmp/button_test && /tmp/button_test
#include "../music/button.h"
#include <cassert>
#include <cstdio>
#include <vector>

static uint32_t t = 1000;
static Button b;
static std::vector<ButtonEvent> events;

static void run(bool pressed, uint32_t ms) {
  for (uint32_t i = 0; i < ms; i++) {
    t++;
    ButtonEvent e = b.update(pressed, t);
    if (e != NO_EVENT) events.push_back(e);
  }
}

static int count(ButtonEvent want) {
  int n = 0;
  for (ButtonEvent e : events) n += e == want;
  return n;
}

static void press(uint32_t ms) {
  events.clear();
  run(true, ms);
  run(false, 100);
}

int main() {
  press(100);  // a tap
  assert(count(PRESSED) == 1 && count(TAPPED) == 1 && count(HELD) == 0);

  press(590);  // just under a hold is still a tap
  assert(count(TAPPED) == 1 && count(HELD) == 0);

  press(1000);  // a hold repeats and never taps: HELD at 600, 750 and 900 ms
  assert(count(TAPPED) == 0 && count(HELD) == 3);

  events.clear();  // a bouncy press and release count once
  for (int i = 0; i < 6; i++) run(i % 2 == 0, 2);
  run(true, 100);
  for (int i = 0; i < 6; i++) run(i % 2 == 1, 2);
  run(false, 100);
  assert(count(PRESSED) == 1 && count(TAPPED) == 1);

  events.clear();  // a press that only woke the screen: no tap, no hold, not even a long one
  run(true, 50);
  assert(count(PRESSED) == 1);
  b.ignored = true;
  run(true, 1000);
  run(false, 100);
  assert(count(TAPPED) == 0 && count(HELD) == 0);

  press(100);  // and the next press works normally
  assert(count(TAPPED) == 1);

  puts("button.h: all checks passed");
}
