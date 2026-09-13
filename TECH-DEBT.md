# Tech Debt

## Duplicated vesting math

Vesting math is duplicated. `src/services/flowgateEngine.ts` mirrors `app/captable.py`. Any formula change must be made in both files in the same commit. Long-term fix: route the dashboard's cap table reads through the backend and delete the client engine's vesting math.

(Flagged in both files — see the mirror notice at the top of `src/services/flowgateEngine.ts`.)
