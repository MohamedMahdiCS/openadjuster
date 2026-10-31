# ADR 0005: Accept missing some hidden text

- **Status:** Accepted
- **Date:** 2026-10-31

## Context

On dev, OpenAdjuster flags 61% of planted injection attempts and no attack changes a decision. The
ones it misses are mostly instructions printed in 6 px near-white text on white. After the page is
scanned and compressed, that text has about 12 to 16 grey levels of contrast.

I tried autocontrast, inversion, edge detection, 8x upscaling and pixel variance. None recovered the
text reliably, and the more aggressive filters would have brought JPEG noise into OCR.

## Decision

Don't chase this. Text OCR can't read also can't reach the model, and the model doesn't make the
decision anyway. Detection helps the reviewer but isn't the defence. The defence is that document
text only enters a prompt as data, and code makes the decision.

## Consequences

The headline security number is attack success (0% on dev), not detection recall. Detection recall is
still reported, so the gap stays visible. An attack on a text PDF, where the hidden text is in the
file itself, would need separate handling. The system only reads page images today.
