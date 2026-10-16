# command line usage

## NAME

Furnace - a chiptune tracker

## SYNOPSIS

`furnace [params...] [file]`

## DESCRIPTION

Furnace is a chiptune tracker that supports many systems and sound chips from the 8/16-bit era.
even though it is primarily controlled by using its graphical user interface, Furnace also offers a command line interface, which is described here.

## USAGE

starting Furnace without arguments will start the graphical user interface (GUI), as long as Furnace has been compiled with GUI enabled.

passing the path to a file will open that file at start-up. if Furnace cannot open that file, it will report an error and quit.

the following parameters may be used:

**general**

- `-help`: display the following help.
- `-console`: enable command-line interface (CLI) player.
  - see the COMMAND LINE INTERFACE section for more information
- `-nostatus`: disable playback status in the CLI player.
- `-nocontrols`: disable standard input controls in the CLI player.
- `-loglevel <level>`: set the logging level to one of the following:
  - `error`: critical errors only
  - `warning`: errors and warnings
  - `info`: errors, warnings, and useful information
  - `debug`: all of the above, including debug information
  - `trace`: like debug, but with even more details (default)

- `-info`: get information about a song.
  - you must provide a file, otherwise Furnace will quit.
  - this includes the song's duration, tick and row counts, and loop region.
- `-noreport`: do not display a message box on error.

- `-version`: display version information.
- `-warranty`: view warranty disclaimer.

**engine**

- `-audio sdl|jack|portaudio|pipe`: override audio backend to one of the following:
  - `sdl`: SDL (default)
  - `jack`: JACK Audio Connection Kit
  - `portaudio`: PortAudio
  - `pipe`: write audio to standard output
- `-view <type>`: set visualization of data to one of the following:
  - `pattern`: order and pattern
  - `commands`: engine commands
  - `nothing`: guess (default)
- `-loops <count>`: set number of loops
  - `-1` means loop forever.
- `-subsong <number>`: set sub-song to play.
- `-safemode`: enable safe mode (software rendering without audio).
- `-safeaudio`: enable safe mode (software rendering with audio).
- `-benchmark render|seek|walk`: run performance test and output total time.
  - `render`: measure render time
  - `seek`: measure time to seek through the entire song
  - `walk`: measure time to calculate song timestamps
  - you must provide a file, otherwise Furnace will quit.

**audio export**

- `-output path`: export audio to `path`.
  - you must provide a file, otherwise Furnace will quit.
  - the format is chosen from the file extension (.wav, .opus, .flac, .mp3) unless `-outformat` is given.
  - .ogg also selects Opus. use `-outformat vorbis` for Vorbis.
- `-outformat u8|s16|f32|opus|flac|vorbis|mp3`: set audio export format.
  - `u8`, `s16` and `f32` are .wav sample formats.
- `-bitrate rate`: set bit rate (lossy formats only).
- `-ratemode constant|variable|average`: set bit rate mode (MP3 only).
- `-compression level`: set quality/compression level from 0 to 10 (Vorbis, FLAC and MP3 VBR only).
- `-outmode one|persys|perchan`: set audio export output mode.
  - this option has no short form.
  - `one`: single file (default)
  - `persys`: one file per chip (`_sXX` will be appended to file name, where `XX` is the chip number)
  - `perchan`: one file per channel (`_cXX` will be appended to file name, where `XX` is the channel number)

**VGM export**

- `-vgmout path`: output VGM data to `path`.
  - you must provide a file, otherwise Furnace will quit.
- `-direct`: enable VGM export direct stream mode.
  - this mode is useful for DualPCM export.
  - note that this will increase file size by a huge amount!
- `-vgmver 150|151|160|161|170|171|172`: set VGM version (`171` by default).
- `-vgmhints`: add pattern hints to VGM output.
- `-noloop`: do not loop VGM or S98 output.

**S98 export**

- `-s98out path`: output S98 data to `path`.
  - you must provide a file, otherwise Furnace will quit.
  - `-noloop` applies here too.

**export (other)**

- `-furout path`: save the song as an uncompressed .fur file to `path`.
  - useful for converting imported modules (.mod, .xm, .dmf and others) to .fur.

- `-jsonout path`: export song data as JSON to `path`.
  - only available if Furnace was built with JSON support (on by default).
  - compatibility flags are included.
  - Furnace can open these JSON files like any other song, so a song can be exported, edited as text and loaded back.
- `-jsonpretty`: indent JSON output.

- `-cmdout path`: output command stream dump to `path`.
  - you must provide a file, otherwise Furnace will quit.

- `-romout path`: output ROM file export to `path`.
  - you must provide a file, otherwise Furnace will quit.
  - there must be an available ROM export target for the system.

- `-romconf key=value`: set a configuration parameter for `-romout`.
  - you may use this multiple times to set multiple parameters.
  - Amiga Validation
    - no parameters.
  - Commander X16 ZSM
    - `zsmrate`: tick rate (Hz), default: `60`
    - `loop`: loop song, default: `true`
    - `optimize`: optimize size, default: `true`
  - Atari 2600 (TIunA)
    - `baseLabel`: base song label name, default: `song`
    - `firstBankSize`: max size in first bank, default: `3072`
    - `otherBankSize`: max size in other banks, default: `4048`
    - `sysToExport`: TIA chip index, default: `-1` (find first)
  - Atari 8-bit SAP-R
    - no parameters.

- `-txtout path`: output text file export to `path`.
  - you must provide a file, otherwise Furnace will quit.

## COMMAND LINE INTERFACE

Furnace provides a command-line interface (CLI) player which may be activated through the `-console` option.

the following controls may be used:

- `Left`/`H`: go to previous order.
- `Right`/`L`: go to next order.
- `Space`: pause/resume playback.

## SEE ALSO

the Furnace user manual in the `manual.pdf` file.
