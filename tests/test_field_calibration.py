import pytest
from app.field_calibration import fit_homography,project

def test_four_point_mapping():
    src=[(0,0),(100,0),(100,50),(0,50)]
    dst=[(0,0),(200,0),(200,100),(0,100)]
    h=fit_homography(src,dst)
    assert project(h,(25,25))==pytest.approx((50,50))

def test_degenerate_landmarks_rejected():
    with pytest.raises(ValueError):
        fit_homography([(0,0)]*4,[(0,0),(1,0),(1,1),(0,1)])
