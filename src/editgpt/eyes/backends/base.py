from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from ..types import FramePacket


class CaptureBackend(ABC):
    """Source of timestamped live frames."""

    @abstractmethod
    def frames(self, *, fps: int) -> Iterator[FramePacket]:
        raise NotImplementedError

    def close(self) -> None:
        pass
