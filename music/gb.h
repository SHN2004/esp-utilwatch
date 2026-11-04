// Reads fields out of Gadgetbridge's "Bangle.js" messages. No Arduino code here,
// so tools/gb_test.cpp can check it on the Mac.
// Gadgetbridge sends lines like:  GB({"t":"musicinfo","artist":"...","track":"..."})
// String values are Espruino JavaScript, not strict JSON: they can use \xHH, \uXXXX and
// octal escapes, or arrive base64-encoded as atob("..."). The result is Latin-1 bytes
// (what the OLED's _tf fonts draw); characters above 255 become '?'.
#pragma once
#include <cstdint>
#include <string>
#include <cstring>

inline int gbHex(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

// Decodes base64 up to the closing quote.
inline std::string gbBase64(const char *p) {
  static const char ALPHABET[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string out;
  unsigned acc = 0;
  int bits = 0;
  for (; *p && *p != '"'; p++) {
    const char *f = strchr(ALPHABET, *p);
    if (!f) continue;  // '=' padding
    acc = acc << 6 | (unsigned)(f - ALPHABET);
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      out += (char)(acc >> bits & 0xFF);
    }
  }
  return out;
}

// Finds "key": in the line and decodes its string value into out.
// Returns false if the key is missing or its value isn't a string.
inline bool gbField(const std::string &line, const char *key, std::string &out) {
  // An escaped quote inside another value reads \"key\", so this can't match there.
  std::string pattern = std::string("\"") + key + "\":";
  size_t at = line.find(pattern);
  if (at == std::string::npos) return false;
  const char *p = line.c_str() + at + pattern.size();
  out.clear();
  if (strncmp(p, "atob(\"", 6) == 0) {
    out = gbBase64(p + 6);
    return true;
  }
  if (*p++ != '"') return false;
  while (*p && *p != '"') {
    char c = *p++;
    if (c != '\\') {
      out += c;
      continue;
    }
    c = *p++;
    if (!c) break;  // line cut off after a backslash
    switch (c) {
      case 'n': out += '\n'; break;
      case 't': out += '\t'; break;
      case 'r': out += '\r'; break;
      case 'b': out += '\b'; break;
      case 'v': out += '\v'; break;
      case 'f': out += '\f'; break;
      case 'x':
      case 'u': {
        int v = 0;
        for (int i = 0, n = c == 'x' ? 2 : 4; i < n && gbHex(*p) >= 0; i++) v = v << 4 | gbHex(*p++);
        out += v > 255 ? '?' : (char)v;
        break;
      }
      default:
        if (c >= '0' && c <= '7') {  // octal, e.g. \20 for the DLE byte
          int v = c - '0';
          for (int i = 0; i < 2 && *p >= '0' && *p <= '7'; i++) v = v * 8 + (*p++ - '0');
          out += (char)v;
        } else {
          out += c;  // \" \\ and anything else stand for themselves
        }
    }
  }
  return true;
}

// Finds "key": in the line and reads its whole-number value into out, e.g. "dur":320.
// Returns false, leaving out alone, if the key is missing or its value isn't a number
// (Gadgetbridge sends -1 for "unknown").
inline bool gbNumber(const std::string &line, const char *key, uint32_t &out) {
  std::string pattern = std::string("\"") + key + "\":";
  size_t at = line.find(pattern);
  if (at == std::string::npos) return false;
  const char *p = line.c_str() + at + pattern.size();
  if (*p < '0' || *p > '9') return false;
  uint32_t v = 0;
  while (*p >= '0' && *p <= '9') v = v * 10 + (*p++ - '0');
  out = v;
  return true;
}

// Where the song is now, in seconds. The phone only reports its position now and then,
// so count forward from the last report while playing, stopping at the end of the song.
inline uint32_t gbPosition(uint32_t reported, uint32_t msSinceReport, bool playing, uint32_t duration) {
  uint32_t p = reported + (playing ? msSinceReport / 1000 : 0);
  return p < duration ? p : duration;
}
