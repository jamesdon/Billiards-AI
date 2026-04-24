#!/usr/bin/env python3
"""Print WAV stats (16-bit PCM). Stdlib only — for headless mic checks without speakers."""

from __future__ import annotations

import argparse
import math
import struct
import sys
import wave


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("wav", help="Path to a .wav file")
    ap.add_argument(
        "--min-peak",
        type=int,
        default=0,
        metavar="N",
        help="If >0, exit 2 when max |sample| < N (likely silence or bad device)",
    )
    args = ap.parse_args()

    try:
        w = wave.open(args.wav, "rb")
    except OSError as e:
        print(f"open-fail: {e}", file=sys.stderr)
        return 2
    try:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        nf = w.getnframes()
        sr = w.getframerate()
        if sw != 2:
            print(f"expected 16-bit PCM; sampwidth={sw}", file=sys.stderr)
            return 2
        data = w.readframes(nf)
    finally:
        w.close()

    if not data:
        print("empty-audio")
        return 1

    peak = 0
    sum_sq = 0.0
    count = 0
    stride = 2 * ch
    for i in range(0, len(data), stride):
        for c in range(ch):
            sample = struct.unpack_from("<h", data, i + 2 * c)[0]
            a = abs(sample)
            if a > peak:
                peak = a
            sum_sq += float(sample) * float(sample)
            count += 1

    rms = math.sqrt(sum_sq / count) if count else 0.0
    dur_s = count / float(sr * ch) if sr and ch else 0.0
    print(f"channels={ch} rate_hz={sr} frames={nf} duration_s={dur_s:.3f} peak_abs={peak} rms={rms:.1f}")
    if args.min_peak > 0 and peak < args.min_peak:
        print(f"fail: peak {peak} < --min-peak {args.min_peak}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
