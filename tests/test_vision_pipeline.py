import pytest
from app.vision_pipeline import Detection, VisionPipeline, validate_ball_heatmap

class FakeDetector:
    def detect(self, frame, frame_index):
        return [Detection(frame_index, "player", 0.9, (1, 2, 11, 22))]

class FakeTracker:
    def update(self, detections):
        return [Detection(d.frame, d.label, d.confidence, d.xyxy, 7) for d in detections]

def test_pipeline_contract():
    result = VisionPipeline(FakeDetector(), FakeTracker()).process([object(), object()])
    assert result["schema_version"] == "vision.v1"
    assert [o["detections"][0]["track_id"] for o in result["observations"]] == [7, 7]
    assert result["coordinate_system"] == "image_pixels"

def test_invalid_detection():
    with pytest.raises(ValueError):
        Detection(0, "player", 1.5, (1, 2, 11, 22))

def test_ball_peak():
    assert validate_ball_heatmap([[0.1, 0.8], [0.2, 0.1]])["x"] == 1
    assert not validate_ball_heatmap([[0.1]], 0.5)["visible"]

def test_chunk_limit():
    with pytest.raises(ValueError):
        VisionPipeline(FakeDetector(), FakeTracker()).process([None] * 301)
