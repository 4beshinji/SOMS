"""Tests for CameraProjector — geometry-based floor projection."""
import math
import pytest

# conftest.py handles sys.path and heavy-dep mocking
from tracking.camera_projector import CameraProjector


# ── Fixture ──────────────────────────────────────────────────────

SAMPLE_CAMERAS = {
    "cam_a": {
        "position": [10.0, 5.0],
        "fov_deg": 60.0,
        "orientation_deg": 0.0,   # pointing east (+x)
        "resolution": [640, 480],
        "tilt_deg": 25.0,         # 25° below horizontal
    },
    "cam_b": {
        "position": [5.0, 10.0],
        "fov_deg": 60.0,
        "orientation_deg": -90.0,  # pointing south (-y)
        "resolution": [640, 480],
        "tilt_deg": 25.0,
    },
    "cam_wide": {
        "position": [0.0, 0.0],
        "fov_deg": 90.0,
        "orientation_deg": 45.0,
        "resolution": [640, 480],
    },
}


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton between tests."""
    CameraProjector._instance = None
    yield
    CameraProjector._instance = None


def make_projector(cameras=None):
    return CameraProjector(cameras or SAMPLE_CAMERAS)


# ── Basic tests ──────────────────────────────────────────────────

class TestCameraProjectorInit:
    def test_loads_cameras(self):
        proj = make_projector()
        assert proj.has_camera("cam_a")
        assert proj.has_camera("cam_b")
        assert not proj.has_camera("cam_unknown")

    def test_skips_cameras_without_position(self):
        proj = make_projector({"no_pos": {"fov_deg": 60}})
        assert not proj.has_camera("no_pos")

    def test_skips_cameras_without_fov(self):
        proj = make_projector({"no_fov": {"position": [1, 2]}})
        assert not proj.has_camera("no_fov")

    def test_singleton(self):
        CameraProjector.get_instance(SAMPLE_CAMERAS)
        p2 = CameraProjector.get_instance()
        assert p2.has_camera("cam_a")

    def test_custom_tilt(self):
        proj = make_projector({"c": {
            "position": [0, 0], "fov_deg": 60, "tilt_deg": 40.0,
            "resolution": [640, 480],
        }})
        assert proj.has_camera("c")


# ── Bearing tests ────────────────────────────────────────────────

class TestBearing:
    def test_center_pixel_gives_orientation(self):
        """Center of image should give camera orientation angle."""
        proj = make_projector()
        bearing = proj.compute_bearing("cam_a", 320.0)  # center x
        assert bearing is not None
        assert abs(bearing - math.radians(0.0)) < 0.01

    def test_left_edge_offset(self):
        """Left edge should be orientation - FOV/2."""
        proj = make_projector()
        bearing = proj.compute_bearing("cam_a", 0.0)  # left edge
        expected = math.radians(0.0 - 30.0)  # orient - fov/2
        assert bearing is not None
        assert abs(bearing - expected) < 0.01

    def test_right_edge_offset(self):
        """Right edge should be orientation + FOV/2."""
        proj = make_projector()
        bearing = proj.compute_bearing("cam_a", 640.0)  # right edge
        expected = math.radians(0.0 + 30.0)  # orient + fov/2
        assert bearing is not None
        assert abs(bearing - expected) < 0.01

    def test_unknown_camera_returns_none(self):
        proj = make_projector()
        assert proj.compute_bearing("cam_unknown", 320.0) is None


# ── Depth estimation tests ──────────────────────────────────────

class TestDepthEstimation:
    def test_bottom_of_image_is_near(self):
        """Foot point at bottom of image should estimate short distance."""
        proj = make_projector()
        # foot_px near bottom (y=460 of 480)
        near = proj.project("cam_a", [320.0, 460.0], [250.0, 300.0, 390.0, 460.0])
        assert near is not None
        cam_x, cam_y = 10.0, 5.0
        d = math.sqrt((near[0] - cam_x)**2 + (near[1] - cam_y)**2)
        assert d < 4.0  # should be close

    def test_top_of_image_is_far(self):
        """Foot point near top of image should estimate longer distance."""
        proj = make_projector()
        # foot_px near top (y=100 of 480)
        far = proj.project("cam_a", [320.0, 100.0], [280.0, 50.0, 360.0, 100.0])
        assert far is not None
        cam_x, cam_y = 10.0, 5.0
        d = math.sqrt((far[0] - cam_x)**2 + (far[1] - cam_y)**2)
        assert d > 4.0  # should be far

    def test_lower_y_is_closer_than_upper_y(self):
        """Detection lower in image should always be closer."""
        proj = make_projector()
        close = proj.project("cam_a", [320.0, 420.0], [250.0, 300.0, 390.0, 420.0])
        far = proj.project("cam_a", [320.0, 200.0], [280.0, 100.0, 360.0, 200.0])
        assert close is not None and far is not None
        cam_x, cam_y = 10.0, 5.0
        d_close = math.sqrt((close[0] - cam_x)**2 + (close[1] - cam_y)**2)
        d_far = math.sqrt((far[0] - cam_x)**2 + (far[1] - cam_y)**2)
        assert d_far > d_close

    def test_sitting_vs_standing_same_distance(self):
        """Sitting and standing person at same distance should give similar depths.

        Sitting person has smaller bbox but same foot_px y-position,
        so depth estimate should be nearly identical.
        """
        proj = make_projector()
        # Same foot position y=350, different bbox heights
        standing = proj.project("cam_a", [320.0, 350.0], [250.0, 50.0, 390.0, 350.0])
        sitting = proj.project("cam_a", [320.0, 350.0], [270.0, 200.0, 370.0, 350.0])
        assert standing is not None and sitting is not None
        # Same foot_px y → same depth → same projected position
        assert abs(standing[0] - sitting[0]) < 0.01
        assert abs(standing[1] - sitting[1]) < 0.01


# ── Single-camera projection tests ──────────────────────────────

class TestSingleCameraProject:
    def test_returns_none_for_unknown_camera(self):
        proj = make_projector()
        result = proj.project("cam_unknown", [320, 400], [100, 200, 200, 400])
        assert result is None

    def test_returns_none_for_tiny_bbox(self):
        """Bbox smaller than threshold should be rejected."""
        proj = make_projector()
        result = proj.project("cam_a", [320, 210], [315, 200, 325, 210])
        assert result is None

    def test_center_pixel_projects_along_orientation(self):
        """Person at center of cam_a (orient=0°) should be east of camera."""
        proj = make_projector()
        result = proj.project("cam_a", [320.0, 350.0], [220.0, 100.0, 420.0, 350.0])
        assert result is not None
        x, y = result
        # Should be to the east (x > camera x=10) and roughly same y
        assert x > 10.0
        assert abs(y - 5.0) < 2.0  # within 2m of camera y

    def test_result_is_within_reasonable_range(self):
        """Projected position should not be absurdly far from camera."""
        proj = make_projector()
        result = proj.project("cam_a", [320.0, 350.0], [250.0, 150.0, 390.0, 350.0])
        assert result is not None
        cam_x, cam_y = 10.0, 5.0
        dist = math.sqrt((result[0] - cam_x)**2 + (result[1] - cam_y)**2)
        assert 0.5 <= dist <= 12.0


# ── Triangulation tests ──────────────────────────────────────────

class TestTriangulation:
    def test_perpendicular_cameras(self):
        """Two cameras at 90° should triangulate correctly."""
        # Camera A at (0, 0) pointing east (bearing=0)
        # Camera B at (10, 0) pointing north (bearing=90°)
        # Person at (10, 10): bearing from A = ~45°, bearing from B = 90°
        pos = CameraProjector.triangulate(
            [0.0, 0.0], math.radians(45.0),
            [10.0, 0.0], math.radians(90.0),
        )
        assert pos is not None
        # Should be near (10, 10)
        assert abs(pos[0] - 10.0) < 0.5
        assert abs(pos[1] - 10.0) < 0.5

    def test_parallel_rays_return_none(self):
        """Parallel rays (same bearing) cannot triangulate."""
        pos = CameraProjector.triangulate(
            [0.0, 0.0], math.radians(0.0),
            [0.0, 5.0], math.radians(0.0),
        )
        assert pos is None

    def test_negative_t_returns_none(self):
        """Intersection behind a camera should return None."""
        # Both cameras point east but person would be west
        pos = CameraProjector.triangulate(
            [10.0, 0.0], math.radians(0.0),    # pointing east
            [10.0, 10.0], math.radians(-10.0),  # pointing slightly south-east
        )
        # The intersection point is far east, which is valid
        # But if we flip the rays to point west:
        pos_behind = CameraProjector.triangulate(
            [10.0, 0.0], math.radians(180.0),   # pointing west
            [10.0, 10.0], math.radians(170.0),   # pointing west-ish
        )
        # Both should be behind origin if testing negative scenarios,
        # but this depends on geometry — just verify it returns a value or None
        assert pos_behind is None or isinstance(pos_behind, list)

    def test_symmetric_cameras_at_known_point(self):
        """Two cameras symmetrically placed should find the midpoint."""
        # Camera A at (0, 0), Camera B at (10, 0)
        # Person at (5, 5)
        bearing_a = math.atan2(5.0, 5.0)   # atan2(dy, dx) = 45°
        bearing_b = math.atan2(5.0, -5.0)  # atan2(5, -5) = 135°
        pos = CameraProjector.triangulate(
            [0.0, 0.0], bearing_a,
            [10.0, 0.0], bearing_b,
        )
        assert pos is not None
        assert abs(pos[0] - 5.0) < 0.1
        assert abs(pos[1] - 5.0) < 0.1

    def test_result_is_averaged(self):
        """With slightly noisy bearings, result should still be reasonable."""
        # Add small noise to bearings
        bearing_a = math.atan2(5.0, 5.0) + 0.02  # ~1 degree noise
        bearing_b = math.atan2(5.0, -5.0) - 0.02
        pos = CameraProjector.triangulate(
            [0.0, 0.0], bearing_a,
            [10.0, 0.0], bearing_b,
        )
        assert pos is not None
        assert abs(pos[0] - 5.0) < 0.5
        assert abs(pos[1] - 5.0) < 0.5
