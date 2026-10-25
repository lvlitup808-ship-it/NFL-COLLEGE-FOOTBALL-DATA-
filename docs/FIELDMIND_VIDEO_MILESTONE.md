# First real-video milestone — acceptance gate

**Not complete.** The repository now includes manually supplied four-point planar homography mathematics and detector/tracker interfaces. These are not a functioning video-to-calibrated-detections pipeline.

Acceptance requires: (1) authorized clip and explicit processing permission; (2) pinned detector weights and reproducible inference runtime; (3) decoded frames with known dimensions, FPS and timestamps; (4) four or more annotated visible field landmarks with reprojection error reported in field units; (5) tracked detections with stable IDs, confidence and calibration provenance; (6) reviewer UI that corrects IDs and accepts/rejects each observation; (7) durable job queue, object storage, status transitions and failure retry; (8) tests with real footage and no fabricated accuracy claims.

Keep synthetic tactical scenarios isolated from observations and avoid inferring coverage, personnel, formation, motion, or play family automatically.
