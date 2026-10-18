/**
 * Furnace Tracker - multi-system chiptune tracker
 * Copyright (C) 2021-2026 tildearrow and contributors
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

#ifndef _WAVE_HARMONICS_H
#define _WAVE_HARMONICS_H

#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define WAVE_HARMONICS_MAX 128

// harmonic content of one wavetable cycle.
// amp and phase use the same units as the Shapes generator's Amplitude/Phase
// sliders (sine base shape), so harmonics 1-16 can be copied straight into it.
struct WaveHarmonics {
  // number of valid entries in amp/phase (len/2)
  int count;
  // amp[0] is harmonic 1; 1.0 is a full-scale sine
  float amp[WAVE_HARMONICS_MAX];
  float phase[WAVE_HARMONICS_MAX];
  // share of the wave's energy above harmonic 16 (0 to 1)
  float energyAbove16;
};

// data: wave samples from 0 to max. len: 2 to 256.
static inline void analyzeWaveHarmonics(const int* data, int len, int max, WaveHarmonics& out) {
  out.count=0;
  out.energyAbove16=0.0f;
  if (len<2 || max<1) return;
  out.count=len/2;
  if (out.count>WAVE_HARMONICS_MAX) out.count=WAVE_HARMONICS_MAX;

  // the generator maps -1..1 to 0..max
  double x[256];
  double mean=0.0;
  for (int i=0; i<len && i<256; i++) {
    x[i]=((double)data[i]/(double)max)*2.0-1.0;
    mean+=x[i];
  }
  mean/=len;

  double total=0.0, above=0.0;
  for (int h=1; h<=out.count; h++) {
    double re=0.0, im=0.0;
    for (int i=0; i<len; i++) {
      double a=2.0*M_PI*(double)h*(double)i/(double)len;
      re+=(x[i]-mean)*cos(a);
      im-=(x[i]-mean)*sin(a);
    }
    // the Nyquist bin isn't doubled
    double scale=(h*2==len)?1.0:2.0;
    double a=scale*sqrt(re*re+im*im)/(double)len;
    // x[i] ~ a*sin(2*pi*h*i/len + p), with p = arg(X) + pi/2.
    // the generator draws sin(2*pi*phase + 2*pi*h*i/len + pi/len).
    double p=atan2(im,re)+M_PI*0.5-M_PI/(double)len;
    double ph=fmod(p/(2.0*M_PI),1.0);
    if (ph<0.0) ph+=1.0;
    out.amp[h-1]=a;
    out.phase[h-1]=(a<1e-6)?0.0f:ph;
    total+=a*a;
    if (h>16) above+=a*a;
  }
  out.energyAbove16=(total>0.0)?(above/total):0.0f;
}

#endif
