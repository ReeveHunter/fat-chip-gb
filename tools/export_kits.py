#!/usr/bin/env python3
"""Export the drum kits as the ROM holds them -> a JSON file for web pages
(the Fat Chip beats page plays them as the Game Boy does).
  python3 tools/export_kits.py [out.json]
Each kit: 18 sounds, 4-bit samples packed two per byte (high nibble first),
base64; plus the two-hit mix table and the sample rate."""
import base64
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_drums as gd  # noqa: E402
import drum_synth  # noqa: E402,F401  (gen_drums needs it importable)

ROM = os.path.join(HERE, "..", "fat-chip-gb.gb")


def main():
    rom = open(ROM, "rb").read()
    names = ["FC CHIP", "FC 808", "808", "909", "CR-78", "CHIP SQ", "CHIP LFSR"]
    kits = []
    for k, name in enumerate(names):
        first = gd.FIRST_BANK + 2 * k
        sounds = []
        for s in range(len(gd.SLOTS)):
            o = first * 16384 + s * 4
            bank, lo, hi, chunks = rom[o:o + 4]
            p = bank * 16384 + ((lo | hi << 8) - 0x4000)
            sounds.append(base64.b64encode(rom[p:p + chunks * 16]).decode())
        kits.append(dict(name=name, sounds=sounds))
    out = dict(rate=524288 / 48, slots=gd.SLOTS, mix=gd.mix_table(), kits=kits)
    path = sys.argv[1] if len(sys.argv) > 1 else "gbkits.json"
    json.dump(out, open(path, "w"))
    print(path, os.path.getsize(path), "bytes")


if __name__ == "__main__":
    main()
