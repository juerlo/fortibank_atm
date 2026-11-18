#!/usr/bin/env python3
# Enforce AHUB_I2S1_CLKD BCLKDIV = 0x7 (48 kHz) on Allwinner H618 HDMI audio.
# snd_sunxi_ahub resets 0x0509730c to BCLKDIV = 0x9 whenever a stream inits,
# which halves LRCK to 24 kHz and mutes HDMI audio. This daemon re-patches it.
import mmap
import os
import struct
import time

fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
mm = mmap.mmap(fd, 4096, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=0x05097000)

while True:
    val = struct.unpack("<I", mm[0x30c:0x310])[0]
    if (val & 0xF0) == 0x90:
        mm[0x30c:0x310] = struct.pack("<I", (val & ~0xF0) | 0x70)
    time.sleep(0.05)
