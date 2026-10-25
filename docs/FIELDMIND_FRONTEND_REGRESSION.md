# Studio regression checklist

1. Open Studio, select player p1, leave X blank and Y=40; click Add waypoint; confirm rejection and no new route.
2. Leave Y blank and X=40; confirm rejection and no new route.
3. Enter X=0, Y=0; confirm valid waypoint.
4. Enter X=101 or Y=-1; confirm rejection.
5. Add two valid waypoints to p1; confirm the count is 2.
6. Play and scrub; confirm p1 follows both waypoints.
7. Export JSON; confirm version field is fieldmind-synthetic-v1 and synthetic is true.
8. Import exported JSON; confirm routes and waypoint order restored.
9. Try malformed JSON, wrong version, and invalid coordinates; confirm existing routes remain intact.
10. Try a file larger than 1 MiB; confirm rejection without mutation.
11. Clear p1; confirm p2 routes are unaffected.
12. Verify the page still labels playback and video preview synthetic/local-only.

Manual browser execution has not been independently verified. Do not mark this checklist passed without running it.
