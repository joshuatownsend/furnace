// license:BSD-3-Clause
// copyright-holders:Aaron Giles,Frank Palazzolo
/***********************************************************

    Astrocade custom 'IO' chip sound chip driver
    Aaron Giles
    based on original work by Frank Palazzolo

    Ported to Furnace from MAME src/devices/sound/astrocde.cpp:
    the device, stream, save state and I/O port plumbing is removed.
    The sound generation loop is unchanged.

***********************************************************/

#ifndef _ASTROCADE_SOUND_H
#define _ASTROCADE_SOUND_H

#include <stdint.h>

class astrocade_sound
{
public:
	astrocade_sound();

	void reset();
	void write(int offset, uint8_t data);
	uint8_t read_reg(int offset) const { return m_reg[offset & 7]; }

	// renders samples at the chip clock: one sample per input clock.
	// each sample is the sum of the four voices, 0 to 60.
	void update(int16_t *out, int samples);

	// level of each voice (A, B, C, noise) after the last update, 0 to 15
	uint8_t chout[4];

private:
	uint8_t       m_reg[8];         /* 8 control registers */
	uint8_t       m_master_count;   /* current master oscillator count */
	uint16_t      m_vibrato_clock;  /* current vibrato clock */
	uint8_t       m_noise_clock;    /* current noise generator clock */
	uint16_t      m_noise_state;    /* current noise LFSR state */
	uint8_t       m_a_count;        /* current tone generator A count */
	uint8_t       m_a_state;        /* current tone generator A state */
	uint8_t       m_b_count;        /* current tone generator B count */
	uint8_t       m_b_state;        /* current tone generator B state */
	uint8_t       m_c_count;        /* current tone generator C count */
	uint8_t       m_c_state;        /* current tone generator C state */
	uint8_t       m_bitswap[256];   /* bitswap table */
};

#endif
