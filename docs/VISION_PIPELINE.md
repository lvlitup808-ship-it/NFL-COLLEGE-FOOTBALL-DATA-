# FIELDMIND Video Intelligence — integration scaffold

This branch adds an independent typed inference contract for an eventual
RF-DETR -> ByteTrack -> RTMPose -> temporal ball heatmap processing pipeline.

## References
- https://github.com/roboflow/rf-detr
- https://github.com/open-mmlab/mmpose
- https://github.com/ifzhang/ByteTrack
- https://arxiv.org/abs/2311.05237

## Actual implementation
- Model-independent detector/tracker/pose/ball interfaces
- Bounded chunk processing and schema-tagged JSON-compatible observations
- Strict bounding-box, frame-index and confidence validation
- Ball heatmap peak extraction with low-confidence abstention
- Unit tests using synthetic fake adapters

## Not implemented
- RF-DETR weight loading/inference
- RTMPose runtime, ByteTrack association, TrackNet/WASB model inference
- Frame decoding, video upload, GPU worker, camera calibration, jersey OCR
- Program-scoped persistence, web UI, benchmarks on actual football footage
- End-to-end deployment

## Next integration sequence
1. Pin model dependencies and review each exact model weight license.
2. Build a separate GPU worker with bounded authorized-video input and no arbitrary URLs.
3. Implement real RF-DETR inference adapter with football-trained weights.
4. Add ByteTrack tracking, RTMPose pose and a separately trained temporal ball model.
5. Evaluate held-out footage; report mAP, IDF1/HOTA, PCK and ball error.
6. Add program-scoped storage and authorization, then integrate reviewed tracks with
   the hypothetical tactical simulator; never conflate predictions with ground truth.

Run: `pytest -q tests/test_vision_pipeline.py`

Do not download third-party code or weights on API startup. Do not alter
`app.pilot:app`, the current database migrations or the Thursday freeze.
