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

#include "astrocade.h"
#include "../engine.h"
#include <math.h>

#define rWrite(a,v) if (!skipRegisterWrites) {writes.push(QueuedWrite(a,v)); regPool[(a)&7]=(v); if (dumpWrites) {addWrite(a,v);} }

// a tone's frequency is clock/(2*(master+1)*(tone+1)), where master and tone
// are registers 0 and 1-3. The pitch table works in periods of tone+1. Its
// period mode already counts a half-cycle per period step, so the divider
// leaves out the 2 (measured: 2*(master+1) played an octave high).
#define CHIP_DIVIDER (1.0*(masterOsc+1))

// the core runs at the chip clock; each output sample averages this many
#define CORE_STEP 16

// master oscillator after reset: the lowest note is about A-2 at the stock clock
#define DEFAULT_MASTER_OSC 0x1f

const char* regCheatSheetAstrocade[]={
  "MasterOsc", "0",
  "ToneA", "1",
  "ToneB", "2",
  "ToneC", "3",
  "Vibrato", "4",
  "VolC_Mux_NoiseOn", "5",
  "VolB_VolA", "6",
  "NoiseVol", "7",
  NULL
};

const char** DivPlatformAstrocade::getRegisterSheet() {
  return regCheatSheetAstrocade;
}

void DivPlatformAstrocade::acquire(short** buf, size_t len) {
  for (int i=0; i<4; i++) {
    oscBuf[i]->begin(len);
  }

  for (size_t h=0; h<len; h++) {
    while (!writes.empty()) {
      QueuedWrite w=writes.front();
      core.write(w.addr,w.val);
      writes.pop();
    }
    core.update(coreBuf,CORE_STEP);
    int sum=0;
    for (int i=0; i<CORE_STEP; i++) sum+=coreBuf[i];
    // the voices add up to 60 at most, so this peaks at 29760
    buf[0][h]=sum*31;
    for (int i=0; i<4; i++) {
      oscBuf[i]->putSample(h,core.chout[i]<<11);
    }
  }

  for (int i=0; i<4; i++) {
    oscBuf[i]->end(len);
  }
}

// volumes and the noise switch share registers 5 to 7, so they're written together
void DivPlatformAstrocade::updateLevels() {
  unsigned char lv[4];
  for (int i=0; i<4; i++) {
    lv[i]=(chan[i].active && !isMuted[i])?(chan[i].outVol&15):0;
  }
  rWrite(6,lv[0]|(lv[1]<<4));
  rWrite(5,lv[2]|(noiseMod?0x10:0)|(lv[3]?0x20:0));
  // the noise volume register is also the depth of the noise modulation
  // (12xx), so it follows the noise channel's volume even while it is silent
  rWrite(7,(chan[3].outVol&15)*0x11);
}

void DivPlatformAstrocade::tick(bool sysTick) {
  bool levelsChanged=false;
  for (int i=0; i<4; i++) {
    chan[i].std.next();
    if (chan[i].std.vol.had) {
      chan[i].outVol=VOL_SCALE_LINEAR(chan[i].vol&15,MIN(15,chan[i].std.vol.val),15);
      levelsChanged=true;
    }
    if (NEW_ARP_STRAT) {
      chan[i].handleArp();
    } else if (chan[i].std.arp.had && !chan[i].rawFreq) {
      if (!chan[i].inPorta) {
        chan[i].baseFreq=chan[i].calcBaseFreq(parent->calcArp(chan[i].note,chan[i].std.arp.val));
      }
      chan[i].freqChanged=true;
    }
    if (chan[i].std.pitch.had) {
      if (chan[i].std.pitch.mode) {
        chan[i].pitch2+=chan[i].std.pitch.val;
        CLAMP_VAR(chan[i].pitch2,-32768,32767);
      } else {
        chan[i].pitch2=chan[i].std.pitch.val;
      }
      chan[i].freqChanged=true;
    }
    if (chan[i].freqChanged || chan[i].keyOn || chan[i].keyOff) {
      // the noise runs at a fixed rate; only the tones have a pitch
      if (i<3) {
        chan[i].freq=chan[i].calcFreq();
        if (chan[i].freq<1) chan[i].freq=1;
        if (chan[i].freq>256) chan[i].freq=256;
        rWrite(1+i,chan[i].freq-1);
      }
      if (chan[i].keyOn || chan[i].keyOff) levelsChanged=true;
      chan[i].keyOn=false;
      chan[i].keyOff=false;
      chan[i].freqChanged=false;
    }
  }
  if (levelsChanged) updateLevels();
}

int DivPlatformAstrocade::dispatch(DivCommand c) {
  switch (c.cmd) {
    case DIV_CMD_NOTE_ON: {
      DivInstrument* ins=parent->getIns(chan[c.chan].ins,DIV_INS_STD);
      if (c.value!=DIV_NOTE_NULL) {
        chan[c.chan].baseFreq=chan[c.chan].calcBaseFreq(c.value);
        chan[c.chan].freqChanged=true;
        chan[c.chan].note=c.value;
      }
      chan[c.chan].active=true;
      chan[c.chan].keyOn=true;
      chan[c.chan].macroInit(ins);
      if (!parent->song.compatFlags.brokenOutVol && !chan[c.chan].std.vol.will) {
        chan[c.chan].outVol=chan[c.chan].vol;
      }
      break;
    }
    case DIV_CMD_NOTE_OFF:
      chan[c.chan].active=false;
      chan[c.chan].keyOff=true;
      chan[c.chan].macroInit(NULL);
      break;
    case DIV_CMD_NOTE_OFF_ENV:
    case DIV_CMD_ENV_RELEASE:
      chan[c.chan].std.release();
      break;
    case DIV_CMD_INSTRUMENT:
      if (chan[c.chan].ins!=c.value || c.value2==1) {
        chan[c.chan].ins=c.value;
      }
      break;
    case DIV_CMD_VOLUME:
      if (chan[c.chan].vol!=c.value) {
        chan[c.chan].vol=c.value;
        if (!chan[c.chan].std.vol.has) {
          chan[c.chan].outVol=c.value;
          updateLevels();
        }
      }
      break;
    case DIV_CMD_GET_VOLUME:
      return chan[c.chan].vol;
      break;
    case DIV_CMD_PITCH:
      chan[c.chan].pitch=c.value;
      chan[c.chan].freqChanged=true;
      break;
    case DIV_CMD_STD_NOISE_FREQ: // 10xx: master oscillator
      masterOsc=c.value;
      rWrite(0,masterOsc);
      // every tone divides the master oscillator, so every note moves
      notifyPitchTable();
      for (int i=0; i<3; i++) {
        if (!chan[i].rawFreq && !chan[i].inPorta) {
          chan[i].baseFreq=chan[i].calcBaseFreq(chan[i].note);
        }
        chan[i].freqChanged=true;
      }
      break;
    case DIV_CMD_FM_LFO: // 11xx: vibrato speed and depth
      vibrato=c.value;
      rWrite(4,vibrato);
      break;
    case DIV_CMD_PCE_LFO_MODE: // 12xx: master oscillator modulation source
      noiseMod=c.value&1;
      updateLevels();
      break;
    case DIV_CMD_NOTE_PORTA: {
      int destFreq=chan[c.chan].calcBaseFreq(c.value2);
      bool return2=false;
      if (destFreq>chan[c.chan].baseFreq) {
        chan[c.chan].baseFreq+=c.value;
        if (chan[c.chan].baseFreq>=destFreq) {
          chan[c.chan].baseFreq=destFreq;
          return2=true;
        }
      } else {
        chan[c.chan].baseFreq-=c.value;
        if (chan[c.chan].baseFreq<=destFreq) {
          chan[c.chan].baseFreq=destFreq;
          return2=true;
        }
      }
      chan[c.chan].freqChanged=true;
      if (return2) {
        chan[c.chan].inPorta=false;
        return 2;
      }
      break;
    }
    case DIV_CMD_LEGATO:
      chan[c.chan].baseFreq=chan[c.chan].calcBaseFreq(c.value+((HACKY_LEGATO_MESS)?(chan[c.chan].std.arp.val):(0)));
      chan[c.chan].freqChanged=true;
      chan[c.chan].note=c.value;
      break;
    case DIV_CMD_PRE_PORTA:
      if (chan[c.chan].active && c.value2) {
        if (parent->song.compatFlags.resetMacroOnPorta) chan[c.chan].macroInit(parent->getIns(chan[c.chan].ins,DIV_INS_STD));
      }
      if (!chan[c.chan].inPorta && c.value && !parent->song.compatFlags.brokenPortaArp && chan[c.chan].std.arp.will && !NEW_ARP_STRAT) chan[c.chan].baseFreq=chan[c.chan].calcBaseFreq(chan[c.chan].note);
      chan[c.chan].inPorta=c.value;
      break;
    case DIV_CMD_GET_VOLMAX:
      return 15;
      break;
    case DIV_CMD_MACRO_OFF:
      chan[c.chan].std.mask(c.value,true);
      break;
    case DIV_CMD_MACRO_ON:
      chan[c.chan].std.mask(c.value,false);
      break;
    case DIV_CMD_MACRO_RESTART:
      chan[c.chan].std.restart(c.value);
      break;
    default:
      break;
  }
  return 1;
}

void DivPlatformAstrocade::muteChannel(int ch, bool mute) {
  isMuted[ch]=mute;
  updateLevels();
}

void DivPlatformAstrocade::forceIns() {
  for (int i=0; i<4; i++) {
    chan[i].insChanged=true;
    chan[i].freqChanged=true;
  }
  rWrite(0,masterOsc);
  rWrite(4,vibrato);
  updateLevels();
}

SharedChannel* DivPlatformAstrocade::getChanState(int ch) {
  return &chan[ch];
}

DivMacroInt* DivPlatformAstrocade::getChanMacroInt(int ch) {
  return &chan[ch].std;
}

DivDispatchOscBuffer* DivPlatformAstrocade::getOscBuffer(int ch) {
  return oscBuf[ch];
}

unsigned char* DivPlatformAstrocade::getRegisterPool() {
  return regPool;
}

int DivPlatformAstrocade::getRegisterPoolSize() {
  return 8;
}

void DivPlatformAstrocade::reset() {
  writes.clear();
  memset(regPool,0,8);
  masterOsc=DEFAULT_MASTER_OSC;
  vibrato=0;
  noiseMod=false;
  notifyPitchTable();
  for (int i=0; i<4; i++) {
    chan[i]=Channel();
    chan[i].pitchTable=&pitchTable;
    chan[i].std.setEngine(parent);
  }
  core.reset();
  rWrite(0,masterOsc);
  rWrite(4,vibrato);
  updateLevels();
}

int DivPlatformAstrocade::getOutputCount() {
  return 1;
}

bool DivPlatformAstrocade::keyOffAffectsArp(int ch) {
  return true;
}

void DivPlatformAstrocade::notifyInsDeletion(void* ins) {
  for (int i=0; i<4; i++) {
    chan[i].std.notifyInsDeletion((DivInstrument*)ins);
  }
}

void DivPlatformAstrocade::notifyPitchTable(int sample) {
  pitchTable.init(parent->song.tuning,chipClock,CHIP_DIVIDER,256,true,parent->song.compatFlags.linearPitch);
}

unsigned int DivPlatformAstrocade::getMaxFreq(int ch) {
  return 256;
}

void DivPlatformAstrocade::setFlags(const DivConfig& flags) {
  // 14.31818 MHz / 8, in both the home console and the arcade boards
  chipClock=COLOR_NTSC/2.0;
  CHECK_CUSTOM_CLOCK;
  rate=chipClock/CORE_STEP;
  for (int i=0; i<4; i++) {
    oscBuf[i]->setRate(rate);
  }
  notifyPitchTable();
}

void DivPlatformAstrocade::poke(unsigned int addr, unsigned short val) {
  rWrite(addr&7,val);
}

void DivPlatformAstrocade::poke(std::vector<DivRegWrite>& wlist) {
  for (DivRegWrite& i: wlist) rWrite(i.addr&7,i.val);
}

bool DivPlatformAstrocade::getDCOffRequired() {
  return true;
}

int DivPlatformAstrocade::init(DivEngine* p, int channels, int sugRate, const DivConfig& flags) {
  parent=p;
  dumpWrites=false;
  skipRegisterWrites=false;
  masterOsc=DEFAULT_MASTER_OSC;
  for (int i=0; i<4; i++) {
    isMuted[i]=false;
    oscBuf[i]=new DivDispatchOscBuffer;
  }
  setFlags(flags);
  reset();
  return 4;
}

void DivPlatformAstrocade::quit() {
  for (int i=0; i<4; i++) {
    delete oscBuf[i];
  }
}

DivPlatformAstrocade::~DivPlatformAstrocade() {
}
