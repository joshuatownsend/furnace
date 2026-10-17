// Just enough of MAME's device framework to compile reference/astrocde.cpp
// unmodified. Only the parts the Astrocade core touches are here.
#pragma once

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <vector>

typedef uint8_t u8;
typedef int32_t s32;
typedef uint32_t offs_t;

#define ATTR_COLD
#define NAME(x) x
#define DECLARE_DEVICE_TYPE(type, cls)
#define DEFINE_DEVICE_TYPE(type, cls, shortname, fullname)

template <int N> inline uint8_t bitswap(uint8_t v, int b7, int b6, int b5, int b4, int b3, int b2, int b1, int b0) {
  const int bits[8]={b7,b6,b5,b4,b3,b2,b1,b0};
  uint8_t r=0;
  for (int i=0; i<8; i++) r=(r<<1)|((v>>bits[i])&1);
  return r;
}

struct machine_config {};
struct running_machine { bool side_effects_disabled() const { return true; } };

class device_t {
  uint32_t m_clock;
  running_machine m_machine;
public:
  device_t(const machine_config&, int, const char*, device_t*, uint32_t clock): m_clock(clock) {}
  virtual ~device_t() {}
  uint32_t clock() const { return m_clock; }
  running_machine& machine() { return m_machine; }
  template <typename T> void save_item(T&) {}
protected:
  virtual void device_start() {}
  virtual void device_reset() {}
};

// one output channel; fill() writes into the buffer the test supplies
class sound_stream {
public:
  typedef float sample_t;
  float* buf=nullptr;
  int len=0;
  int samples() const { return len; }
  void fill(int, sample_t v, int start, int count) { for (int i=0; i<count; i++) buf[start+i]=v; }
  void update() {}
};

class device_sound_interface {
  sound_stream m_s;
public:
  device_sound_interface(const machine_config&, device_t&) {}
  virtual ~device_sound_interface() {}
  sound_stream* stream_alloc(int, int, uint32_t) { return &m_s; }
protected:
  virtual void sound_stream_update(sound_stream& stream)=0;
};

struct devcb_read8 {
  devcb_read8(device_t&, int=0) {}
  int bind() { return 0; }
  u8 operator()(offs_t) { return 0; }
  u8 operator()() { return 0; }
  template <int N> struct array_t {
    devcb_read8* d[N];
    array_t(device_t& o, int v=0) { for (int i=0; i<N; i++) d[i]=new devcb_read8(o,v); }
    devcb_read8& operator[](int i) { return *d[i]; }
  };
  template <int N> using array=array_t<N>;
};

struct devcb_write8 {
  devcb_write8(device_t&) {}
  int bind() { return 0; }
  void operator()(offs_t, u8) {}
  template <int N> struct array_t {
    devcb_write8* d[N];
    array_t(device_t& o) { for (int i=0; i<N; i++) d[i]=new devcb_write8(o); }
    devcb_write8& operator[](int i) { return *d[i]; }
  };
  template <int N> using array=array_t<N>;
};

enum { ASTROCADE_IO=0 };
