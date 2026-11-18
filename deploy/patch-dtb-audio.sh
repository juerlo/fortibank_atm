#!/bin/bash
# Patch the Orange Pi Zero 3 DTB so ahub1_mach uses mclk-fs = 256 (0x100).
# Required for 48 kHz HDMI audio on the H618.
set -e
DTB=$(find /boot/dtb* -name "*zero3*.dtb" | head -n 1)
echo "Patching DTB: $DTB"
sudo cp -n "$DTB" "${DTB}.bak"

dtc -I dtb -O dts -o /tmp/zero3.dts "$DTB"
sed -i '/ahub1_mach {/,/};/ s/soundcard-mach,mclk-fs = <0x00>;/soundcard-mach,mclk-fs = <0x100>;/' /tmp/zero3.dts
sudo dtc -I dts -O dtb -o "$DTB" /tmp/zero3.dts

echo "Verifying:"
dtc -I dtb -O dts "$DTB" 2>/dev/null | grep -A 20 "ahub1_mach {"
