// Core fidelity check: drive MAME's original Astrocade core (reference/, built
// through shim/emu.h) and Furnace's port (src/engine/platform/sound/astrocade.cpp)
// with the same register writes and require identical output, sample for sample,
// at the chip clock. Prints PASS/FAIL and exits non-zero on a mismatch.

#include "emu.h"
#include "astrocde.h"
#include "../../../src/engine/platform/sound/astrocade.h"

#include <cmath>
#include <cstdio>
#include <random>

struct Reference: public astrocade_io_device {
  Reference(): astrocade_io_device(machine_config(),"ref",nullptr,1789773) {}
  using astrocade_io_device::device_start;
  using astrocade_io_device::sound_stream_update;
};

int main(int argc, char** argv) {
  unsigned seed=argc>1?atoi(argv[1]):1;
  const long total=argc>2?atol(argv[2]):1789773L*20; // 20 seconds of chip time
  std::mt19937 rng(seed);

  Reference ref;
  ref.device_start();
  sound_stream stream;
  astrocade_sound port;

  std::vector<float> a;
  std::vector<int16_t> b;
  long done=0, mismatches=0, writes=0, firstBad=-1;
  int nonzero=0;
  while (done<total) {
    // a burst of writes, biased like a song: pitches, volumes, sometimes the
    // master oscillator, vibrato and noise controls
    int n=rng()%4;
    for (int i=0; i<n; i++) {
      int reg=rng()%8;
      uint8_t val=rng()&0xff;
      ref.write(reg,val);
      port.write(reg,val);
      writes++;
    }
    // then render a stretch between 1 sample and about 1/60 s
    int len=1+rng()%30000;
    if (done+len>total) len=total-done;
    a.resize(len);
    b.resize(len);
    stream.buf=a.data();
    stream.len=len;
    ref.sound_stream_update(stream);
    port.update(b.data(),len);
    for (int i=0; i<len; i++) {
      int want=(int)lround(a[i]*60.0f);
      if (want!=b[i]) {
        if (firstBad<0) firstBad=done+i;
        mismatches++;
      }
      if (b[i]) nonzero++;
    }
    done+=len;
  }
  printf("seed %u: %ld samples, %ld register writes, %ld mismatches",seed,done,writes,mismatches);
  if (firstBad>=0) printf(" (first at sample %ld)",firstBad);
  printf(", %s\n",(mismatches==0 && nonzero>0)?"PASS":"FAIL");
  return (mismatches==0 && nonzero>0)?0:1;
}
