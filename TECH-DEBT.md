# Tech Debt

## Duplicated vesting math

Vesting math is duplicated. `src/services/flowgateEngine.ts` mirrors `app/captable.py`. Any formula change must be made in both files in the same commit. Long-term fix: route the dashboard's cap table reads through the backend and delete the client engine's vesting math.

(Flagged in both files — see the mirror notice at the top of `src/services/flowgateEngine.ts`.)

## Assistant prompt size

The assistant loads ~44k characters (~11k tokens) of markdown into every
system prompt. That's ~$0.10/question on Sonnet. At pilot scale, consider:
(a) trimming the curated file list, (b) chunking and retrieving only
relevant sections, or (c) a two-tier approach — a small knowledge base for
common questions, retrieval for the long tail. None of this is urgent for
a demo, but it caps unit economics at pilot scale.
