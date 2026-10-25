"""Optional computer-vision pipeline adapters; no model is silently downloaded.

RF-DETR, MMPose/RTMPose, ByteTrack and temporal ball heatmaps require
separately installed, pinned runtimes and approved model weights.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Protocol, Sequence, Any
import math

@dataclass(frozen=True)
class Detection:
    frame: int
    label: str
    confidence: float
    xyxy: tuple[float, float, float, float]
    track_id: int | None = None

    def __post_init__(self):
        if self.frame < 0 or not self.label or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("invalid detection")
        if len(self.xyxy) != 4 or not all(math.isfinite(v) for v in self.xyxy):
            raise ValueError("invalid bounding box")
        x1,y1,x2,y2 = self.xyxy
        if x2 <= x1 or y2 <= y1 or x1 < 0 or y1 < 0:
            raise ValueError("invalid bounding box")

class Detector(Protocol):
    def detect(self, frame: Any, frame_index: int) -> Sequence[Detection]: ...

class Tracker(Protocol):
    def update(self, detections: Sequence[Detection]) -> Sequence[Detection]: ...

class PoseEstimator(Protocol):
    def estimate(self, frame: Any, people: Sequence[Detection]) -> list[dict]: ...

class BallEstimator(Protocol):
    def estimate(self, frames: Sequence[Any]) -> list[dict]: ...

class VisionPipeline:
    def __init__(self, detector: Detector, tracker: Tracker,
                 pose: PoseEstimator | None = None, ball: BallEstimator | None = None):
        self.detector, self.tracker, self.pose, self.ball = detector, tracker, pose, ball

    def process(self, frames: Sequence[Any], start_frame: int = 0) -> dict:
        if not 0 <= len(frames) <= 300 or start_frame < 0:
            raise ValueError("process at most 300 frames per chunk")
        observations = []
        for i, frame in enumerate(frames):
            detections = list(self.detector.detect(frame, start_frame + i))
            if any(d.frame != start_frame + i for d in detections):
                raise ValueError("detector frame index mismatch")
            tracked = list(self.tracker.update(detections))
            poses = self.pose.estimate(frame, tracked) if self.pose else []
            observations.append({"frame": start_frame+i,
                                 "detections": [asdict(d) for d in tracked],
                                 "poses": poses})
        ball = self.ball.estimate(frames) if self.ball and frames else []
        return {"schema_version": "vision.v1", "observations": observations,
                "ball_observations": ball, "coordinate_system": "image_pixels",
                "status": "unverified_model_outputs",
                "limitations": ["No field calibration or 3D reconstruction",
                                "Track IDs are not verified jersey identities",
                                "Missing or occluded ball must remain unknown"]}

def validate_ball_heatmap(heatmap: Sequence[Sequence[float]], threshold: float = 0.5) -> dict:
    """Extract a peak from a model-provided heatmap; not itself a ball model."""
    if not 0 <= threshold <= 1:
        raise ValueError("invalid threshold")
    if not heatmap or not heatmap[0]:
        return {"visible": False, "reason": "empty_heatmap"}
    width = len(heatmap[0])
    if any(len(row) != width for row in heatmap):
        raise ValueError("ragged heatmap")
    peak = (-1.0, 0, 0)
    for y, row in enumerate(heatmap):
        for x, value in enumerate(row):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("heatmap values must be probabilities")
            if value > peak[0]:
                peak = (value, x, y)
    if peak[0] < threshold:
        return {"visible": False, "reason": "low_confidence", "confidence": peak[0]}
    return {"visible": True, "x": peak[1], "y": peak[2], "confidence": peak[0]}
