import numpy as np

from core.geometry import Homography


def test_homography_table_to_pixel_roundtrip():
    H = np.array([[0.5, 0.0, 10.0], [0.0, 0.5, 20.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    hg = Homography(H=H)
    px = (100.0, 200.0)
    m = hg.to_table(px)
    back = hg.to_pixel(m)
    assert abs(back[0] - px[0]) < 1e-6
    assert abs(back[1] - px[1]) < 1e-6
