// Checks music/gb.h against the kinds of lines Gadgetbridge sends.
//   clang++ -std=c++17 tools/gb_test.cpp -o /tmp/gb_test && /tmp/gb_test
#include "../music/gb.h"
#include <cassert>
#include <cstdio>

static std::string field(const char *line, const char *key) {
  std::string out;
  assert(gbField(line, key, out));
  return out;
}

int main() {
  const char *info = "GB({\"t\":\"musicinfo\",\"artist\":\"Daft Punk\",\"track\":\"One More Time\",\"dur\":320})";
  assert(field(info, "t") == "musicinfo");
  assert(field(info, "artist") == "Daft Punk");
  assert(field(info, "track") == "One More Time");

  std::string out = "old";
  assert(!gbField(info, "album", out));  // missing key
  assert(!gbField(info, "dur", out));    // number, not a string

  assert(field("{\"track\":\"Say \\\"Hi\\\" \\xE9t\\xE9\"}", "track") == "Say \"Hi\" \xE9t\xE9");
  assert(field("{\"track\":\"\\u3042b\\u00e9\"}", "track") == "?b\xE9");    // above Latin-1 -> '?'
  assert(field("{\"track\":atob(\"SGVsbG8=\")}", "track") == "Hello");
  assert(field("{\"track\":\"a\\20b\\5\"}", "track") == std::string("a\x10" "b\x05"));
  assert(field("{\"track\":\"x\\\"artist\\\":y\",\"artist\":\"Z\"}", "artist") == "Z");  // key text inside a value
  assert(field("{\"track\":\"cut\\", "track") == "cut");                      // truncated line

  assert(field("{\"art\":atob(\"AAEC\")}", "art") == std::string("\0\1\2", 3));  // a cover can contain zero bytes

  uint32_t n = 7;
  assert(gbNumber(info, "dur", n) && n == 320);
  assert(gbNumber("{\"position\":0,\"shuffle\":-1}", "position", n) && n == 0);
  n = 7;
  assert(!gbNumber("{\"position\":0,\"shuffle\":-1}", "shuffle", n) && n == 7);  // -1 = unknown
  assert(!gbNumber(info, "artist", n) && n == 7);                                // string, not a number
  assert(!gbNumber(info, "position", n) && n == 7);                              // missing key
  assert(gbNumber("GB({\"t\":\"time\",\"local\":1793772904})", "local", n) && n == 1793772904);

  assert(gbPosition(10, 5999, true, 200) == 15);   // counts whole seconds while playing
  assert(gbPosition(10, 5999, false, 200) == 10);  // holds still while paused
  assert(gbPosition(198, 5000, true, 200) == 200);  // stops at the end of the song
  assert(gbPosition(50, 0, false, 31) == 31);       // a report past the end

  puts("gb.h: all checks passed");
}
