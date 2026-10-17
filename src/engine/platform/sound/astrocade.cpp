// license:BSD-3-Clause
// copyright-holders:Aaron Giles,Frank Palazzolo
/***********************************************************

    Astrocade custom 'IO' chip sound chip driver
    Aaron Giles
    based on original work by Frank Palazzolo

************************************************************

    Register Map
    ============

    Register 0:
        D7..D0: Master oscillator frequency

    Register 1:
        D7..D0: Tone generator A frequency

    Register 2:
        D7..D0: Tone generator B frequency

    Register 3:
        D7..D0: Tone generator C frequency

    Register 4:
        D7..D6: Vibrato speed
        D5..D0: Vibrato depth

    Register 5:
            D5: Noise AM enable
            D4: Mux source (0=vibrato, 1=noise)
        D3..D0: Tone generator C volume

    Register 6:
        D7..D4: Tone generator B volume
        D3..D0: Tone generator A volume

    Register 7:
        D7..D0: Noise volume

***********************************************************/

#include "astrocade.h"
#include <string.h>
#include <algorithm>

// MAME's bitswap<8>(i, 0,1,2,3,4,5,6,7): reverse the bit order
static uint8_t reverse_bits(uint8_t v)
{
	uint8_t r = 0;
	for (int i = 0; i < 8; i++)
		if (v & (1 << i))
			r |= 0x80 >> i;
	return r;
}

astrocade_sound::astrocade_sound()
{
	/* generate a bitswap table for the noise */
	for (int i = 0; i < 256; i++)
		m_bitswap[i] = reverse_bits(i);

	reset();
}

void astrocade_sound::update(int16_t *out, int samples)
{
	uint16_t noise_state;
	uint8_t master_count;
	uint8_t noise_clock;

	/* load some locals */
	master_count = m_master_count;
	noise_clock = m_noise_clock;
	noise_state = m_noise_state;

	/* loop over samples */
	int samples_this_time;
	for (int sampindex = 0; sampindex < samples; sampindex += samples_this_time)
	{
		int32_t cursample = 0;

		/* compute the number of cycles until the next master oscillator reset */
		/* or until the next noise boundary */
		samples_this_time = std::min<int>(samples - sampindex, 256 - master_count);
		samples_this_time = std::min(samples_this_time, 64 - noise_clock);

		/* sum the output of the tone generators */
		chout[0] = m_a_state ? (m_reg[6] & 0x0f) : 0;
		chout[1] = m_b_state ? (m_reg[6] >> 4) : 0;
		chout[2] = m_c_state ? (m_reg[5] & 0x0f) : 0;
		cursample += chout[0] + chout[1] + chout[2];

		/* add in the noise if it is enabled, based on the top bit of the LFSR */
		chout[3] = ((m_reg[5] & 0x20) && (noise_state & 0x4000)) ? (m_reg[7] >> 4) : 0;
		cursample += chout[3];

		/* output (MAME scales to 0..1 here by dividing by 60) */
		for (int i = 0; i < samples_this_time; i++)
			out[sampindex + i] = cursample;

		/* clock the noise; a 2-bit counter clocks a 4-bit counter which clocks the LFSR */
		noise_clock += samples_this_time;
		if (noise_clock >= 64)
		{
			/* update the noise state; this is a 15-bit LFSR with feedback from */
			/* the XOR of the top two bits */
			noise_state = (noise_state << 1) | (~((noise_state >> 14) ^ (noise_state >> 13)) & 1);
			noise_clock -= 64;

			/* the same clock also controls the vibrato clock, which is a 13-bit counter */
			m_vibrato_clock++;
		}

		/* clock the master oscillator; this is an 8-bit up counter */
		master_count += samples_this_time;
		if (master_count == 0)
		{
			/* reload based on mux value -- the value from the register is negative logic */
			master_count = ~m_reg[0];

			/* mux value 0 means reload based on the vibrato control */
			if ((m_reg[5] & 0x10) == 0)
			{
				/* vibrato speed (register 4 bits 6-7) selects one of the top 4 bits */
				/* of the 13-bit vibrato clock to use (0=highest freq, 3=lowest) */
				if (!((m_vibrato_clock >> (m_reg[4] >> 6)) & 0x0200))
				{
					/* if the bit is clear, we add the vibrato volume to the counter */
					master_count += m_reg[4] & 0x3f;
				}
			}

			/* mux value 1 means reload based on the noise control */
			else
			{
				/* the top 8 bits of the noise LFSR are ANDed with the noise volume */
				/* register and added to the count */
				master_count += m_bitswap[(noise_state >> 7) & 0xff] & m_reg[7];
			}

			/* clock tone A */
			if (++m_a_count == 0)
			{
				m_a_state ^= 1;
				m_a_count = ~m_reg[1];
			}

			/* clock tone B */
			if (++m_b_count == 0)
			{
				m_b_state ^= 1;
				m_b_count = ~m_reg[2];
			}

			/* clock tone C */
			if (++m_c_count == 0)
			{
				m_c_state ^= 1;
				m_c_count = ~m_reg[3];
			}
		}
	}

	/* put back the locals */
	m_master_count = master_count;
	m_noise_clock = noise_clock;
	m_noise_state = noise_state;
}

void astrocade_sound::reset()
{
	memset(m_reg, 0, sizeof(m_reg));
	memset(chout, 0, sizeof(chout));

	m_master_count = 0;
	m_vibrato_clock = 0;

	m_noise_clock = 0;
	m_noise_state = 0;

	m_a_count = 0;
	m_a_state = 0;

	m_b_count = 0;
	m_b_state = 0;

	m_c_count = 0;
	m_c_state = 0;
}

void astrocade_sound::write(int offset, uint8_t data)
{
	/* stash the new register value */
	m_reg[offset & 7] = data;
}
