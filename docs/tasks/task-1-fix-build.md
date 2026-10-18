TASK 1 (Frontend Engineer): fix the build.
Goal: pnpm build fails at app/page.tsx:366 ("Expected '</', got 'jsx text'", a mismatched closing tag). Fix only that.
Allowed file: /home/klythron/Documents/projects/red-team-platform/frontend/app/page.tsx. Forbidden: everything else, no new features, no refactors, no other panels.
Steps: copy the file to /tmp, make a targeted edit, run pnpm build from frontend/.
Acceptance: pnpm build exits 0 (paste the output), and git diff shows only the lines that fix the tag balance (paste it).
Stop if the fix needs changes outside this file.
