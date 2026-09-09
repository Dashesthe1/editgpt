from __future__ import annotations

import base64

import cv2
import numpy as np

from editgpt.eyes.semantic import encode_jpeg_data_url


def test_semantic_image_encoding_returns_decodable_data_url() -> None:
    image = np.zeros((12, 20, 3), dtype=np.uint8)
    image[:, :10] = 255
    data_url = encode_jpeg_data_url(image, max_width=10, quality=90)

    prefix = "data:image/jpeg;base64,"
    assert data_url.startswith(prefix)
    raw = base64.b64decode(data_url[len(prefix):])
    decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[1] == 10
    assert decoded.shape[0] == 6
