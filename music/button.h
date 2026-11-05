// One button's tap and hold logic. No Arduino code here, so tools/button_test.cpp can check
// it on the Mac. A tap is decided on release, so a hold never fires a tap as well.
#pragma once
#include <cstdint>

const uint32_t DEBOUNCE_MS = 25;
const uint32_t HOLD_MS = 600;    // shorter is a tap, longer is a hold
const uint32_t REPEAT_MS = 150;  // HELD repeats this often while the button stays down

enum ButtonEvent { NO_EVENT, PRESSED, TAPPED, HELD };

struct Button {
  bool down = false;
  bool ignored = false;  // set after PRESSED to make this press do nothing more, until it's released
  uint32_t changedAt = 0, lastHeld = 0;

  // Call often with the pin's state. Returns at most one event per call.
  ButtonEvent update(bool pressed, uint32_t now) {
    bool hold = down && now - changedAt >= HOLD_MS;
    if (pressed != down && now - changedAt > DEBOUNCE_MS) {
      down = pressed;
      changedAt = now;
      if (pressed) return PRESSED;
      bool tap = !hold && !ignored;
      ignored = false;
      return tap ? TAPPED : NO_EVENT;
    }
    if (hold && !ignored && now - lastHeld >= REPEAT_MS) {
      lastHeld = now;
      return HELD;
    }
    return NO_EVENT;
  }
};
