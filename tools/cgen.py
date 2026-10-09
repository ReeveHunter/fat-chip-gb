"""Small helpers for emitting C source from the Python data generators."""


def c_array(name, data, ctype="uint8_t", per_line=16, fmt="0x{:02X}", const=True):
    data = list(data)
    out = []
    out.append(f"{'const ' if const else ''}{ctype} {name}[{len(data)}] = {{")
    for i in range(0, len(data), per_line):
        chunk = data[i:i + per_line]
        out.append("    " + ", ".join(fmt.format(v) for v in chunk) + ",")
    out.append("};")
    return "\n".join(out) + "\n"


def c_strings(name, strings, width):
    """Fixed-width, space padded, not NUL terminated."""
    flat = []
    for s in strings:
        s = s.upper()[:width].ljust(width)
        flat.extend(ord(c) for c in s)
    return c_array(name, flat, fmt="{:d}", per_line=width)


def header(bank=None):
    lines = ["/* Generated file - do not edit. See tools/. */"]
    if bank is not None:
        lines.append(f"#pragma bank {bank}")
    lines.append("#include <stdint.h>")
    lines.append("#include <gbdk/platform.h>")
    return "\n".join(lines) + "\n\n"


def pack_nibbles(samples):
    """samples: iterable of ints 0..15, even length. High nibble first (GB wave RAM order)."""
    s = list(samples)
    assert len(s) % 2 == 0
    return [((s[i] & 15) << 4) | (s[i + 1] & 15) for i in range(0, len(s), 2)]


def quantize4(x):
    """x: array in [-1, 1] -> ints 0..15."""
    import numpy as np
    x = np.clip(np.asarray(x, dtype=float), -1.0, 1.0)
    return np.clip(np.round((x + 1.0) * 7.5), 0, 15).astype(int).tolist()
