from __future__ import annotations

import json
import math
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from .semantic import LocalQwenVLClient
from .source import VideoSourceReader


@dataclass(slots=True, frozen=True)
class TemporalCandidate:
    event_type: str
    frame_index: int
    timestamp_s: float
    score: float
    confidence: float
    backend: str
    details: dict[str, Any] = field(default_factory=dict, compare=False)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(slots=True)
class TemporalProfile:
    path: str
    fps: float
    frame_count: int
    duration_s: float
    backend: str
    decode_s: float
    analysis_s: float
    transition_probabilities: np.ndarray = field(repr=False)
    mean_abs_delta: np.ndarray = field(repr=False)
    changed_fraction: np.ndarray = field(repr=False)
    flow_mean: np.ndarray = field(repr=False)
    acceleration: np.ndarray = field(repr=False)
    luma: np.ndarray = field(repr=False)
    timestamps_s: np.ndarray = field(repr=False)
    transition_error: str | None = None

    def _candidate(self, event_type: str, index: int, score: float, *, backend: str, confidence: float | None = None) -> TemporalCandidate:
        return TemporalCandidate(
            event_type=event_type,
            frame_index=int(index),
            timestamp_s=float(self.timestamps_s[index]),
            score=float(score),
            confidence=float(np.clip(score if confidence is None else confidence, 0.0, 1.0)),
            backend=backend,
        )

    def top_transitions(self, limit: int = 12, threshold: float = 0.5) -> list[TemporalCandidate]:
        peaks = _local_peaks(self.transition_probabilities, threshold=threshold, min_distance=max(1, int(round(self.fps * 0.12))))
        ordered = sorted(peaks, key=lambda i: float(self.transition_probabilities[i]), reverse=True)[: max(1, limit)]
        return [self._candidate("transition", i, float(self.transition_probabilities[i]), backend=self.backend) for i in ordered]

    def top_motion(self, limit: int = 12, *, min_distance_s: float = 0.20) -> list[TemporalCandidate]:
        score = _robust_unit_score(self.flow_mean) * 0.65 + _robust_unit_score(self.mean_abs_delta) * 0.35
        peaks = _local_peaks(score, threshold=0.15, min_distance=max(1, int(round(self.fps * min_distance_s))))
        ordered = sorted(peaks, key=lambda i: float(score[i]), reverse=True)[: max(1, limit)]
        return [self._candidate("motion_peak", i, float(score[i]), backend="optical_flow+delta") for i in ordered]

    def top_acceleration(self, limit: int = 12, *, min_distance_s: float = 0.20) -> list[TemporalCandidate]:
        score = _robust_unit_score(np.maximum(self.acceleration, 0.0))
        peaks = _local_peaks(score, threshold=0.10, min_distance=max(1, int(round(self.fps * min_distance_s))))
        ordered = sorted(peaks, key=lambda i: float(score[i]), reverse=True)[: max(1, limit)]
        return [self._candidate("acceleration_peak", i, float(score[i]), backend="optical_flow_derivative") for i in ordered]

    def summary(self, *, limit: int = 8) -> dict[str, Any]:
        return {
            "path": self.path,
            "fps": self.fps,
            "frame_count": self.frame_count,
            "duration_s": self.duration_s,
            "transition_backend": self.backend,
            "transition_error": self.transition_error,
            "decode_s": self.decode_s,
            "analysis_s": self.analysis_s,
            "top_transitions": [c.as_dict() for c in self.top_transitions(limit)],
            "top_motion": [c.as_dict() for c in self.top_motion(limit)],
            "top_acceleration": [c.as_dict() for c in self.top_acceleration(limit)],
            "luma_min": float(np.min(self.luma)) if self.luma.size else 0.0,
            "luma_max": float(np.max(self.luma)) if self.luma.size else 0.0,
        }


@dataclass(slots=True, frozen=True)
class TemporalEventResult:
    event_type: str
    found: bool
    description: str | None
    frame_index: int | None
    timestamp_s: float | None
    confidence: float
    evidence_indices: tuple[int, ...]
    bracket: tuple[int, int] | None
    backend: str
    reason: str
    uncertainty: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class SemanticClient(Protocol):
    def observe_images(
        self,
        images: list[np.ndarray],
        *,
        prompt: str,
        labels: list[str] | None = None,
        source: str = "frame_sequence",
        max_tokens: int = 480,
        max_width: int = 960,
        jpeg_quality: int = 88,
    ) -> Any: ...


def _robust_unit_score(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float32)
    if not values.size:
        return values.copy()
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = max(mad * 6.0, float(np.percentile(values, 99)) - median, 1e-6)
    return np.clip((values - median) / scale, 0.0, 1.0)


def _local_peaks(values: np.ndarray, *, threshold: float, min_distance: int) -> list[int]:
    values = np.asarray(values, dtype=np.float32).reshape(-1)
    if values.size == 0:
        return []
    raw: list[int] = []
    for i, value in enumerate(values):
        if float(value) < threshold:
            continue
        left = float(values[i - 1]) if i > 0 else -math.inf
        right = float(values[i + 1]) if i + 1 < values.size else -math.inf
        if float(value) >= left and float(value) >= right:
            raw.append(i)
    raw.sort(key=lambda i: float(values[i]), reverse=True)
    chosen: list[int] = []
    for index in raw:
        if all(abs(index - prior) >= min_distance for prior in chosen):
            chosen.append(index)
    return sorted(chosen)


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("semantic event response did not contain a JSON object")
        value = json.loads(stripped[start : end + 1])
    if isinstance(value, list):
        value = {"frames": value}
    if not isinstance(value, dict):
        raise ValueError("semantic event response must be a JSON object or frame array")
    return value


class TemporalAnalyzer:
    """Read-only source-video temporal evidence with cached machine signals."""

    def __init__(
        self,
        *,
        prefer_transnet: bool = True,
        semantic_client: SemanticClient | None = None,
    ) -> None:
        self.prefer_transnet = prefer_transnet
        self.semantic_client = semantic_client
        self._profiles: dict[tuple[str, int, int], TemporalProfile] = {}
        self._transnet_model: Any | None = None
        self._transnet_device: str | None = None
        self._transnet_error: str | None = None
        self._semantic_cache: dict[tuple[str, int, int, str, int], tuple[bool, float, str]] = {}

    def _cache_key(self, path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return str(path), int(stat.st_size), int(stat.st_mtime_ns)

    def profile(self, reader: VideoSourceReader, *, force: bool = False) -> TemporalProfile:
        path = Path(reader.metadata.path).resolve()
        key = self._cache_key(path)
        if not force and key in self._profiles:
            return self._profiles[key]
        profile = self._build_profile(path, fps_hint=reader.metadata.fps)
        self._profiles = {cached_key: value for cached_key, value in self._profiles.items() if cached_key[0] != str(path)}
        self._profiles[key] = profile
        return profile

    def _build_profile(self, path: Path, *, fps_hint: float | None) -> TemporalProfile:
        try:
            import av  # type: ignore
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PyAV and OpenCV are required for temporal source analysis") from exc

        decode_started = time.perf_counter()
        small_frames: list[np.ndarray] = []
        timestamps: list[float] = []
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            fps = float(stream.average_rate) if stream.average_rate else float(fps_hint or 0.0)
            if fps <= 0:
                raise RuntimeError("source frame rate is unavailable")
            for index, frame in enumerate(container.decode(stream)):
                rgb = frame.reformat(width=96, height=54, format="rgb24").to_ndarray()
                small_frames.append(np.array(rgb, copy=True))
                if frame.time is not None:
                    timestamps.append(float(frame.time))
                elif frame.pts is not None and frame.time_base is not None:
                    timestamps.append(float(frame.pts * frame.time_base))
                else:
                    timestamps.append(index / fps)
        if not small_frames:
            raise ValueError(f"source has no decoded video frames: {path}")
        frames = np.stack(small_frames).astype(np.uint8, copy=False)
        times = np.asarray(timestamps, dtype=np.float64)
        decode_s = time.perf_counter() - decode_started

        analysis_started = time.perf_counter()
        count = int(frames.shape[0])
        mean_abs_delta = np.zeros(count, dtype=np.float32)
        changed_fraction = np.zeros(count, dtype=np.float32)
        if count > 1:
            delta = np.abs(frames[1:].astype(np.int16) - frames[:-1].astype(np.int16))
            per_pixel = delta.mean(axis=3)
            mean_abs_delta[1:] = per_pixel.mean(axis=(1, 2)).astype(np.float32) / 255.0
            changed_fraction[1:] = (per_pixel >= 12.0).mean(axis=(1, 2)).astype(np.float32)

        gray = np.stack([cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY) for frame in frames])
        luma = gray.mean(axis=(1, 2)).astype(np.float32) / 255.0
        flow_mean = np.zeros(count, dtype=np.float32)
        for index in range(1, count):
            flow = cv2.calcOpticalFlowFarneback(
                gray[index - 1], gray[index], None,
                pyr_scale=0.5, levels=2, winsize=9, iterations=2,
                poly_n=5, poly_sigma=1.1, flags=0,
            )
            magnitude = cv2.magnitude(flow[..., 0], flow[..., 1])
            flow_mean[index] = float(np.mean(magnitude))
        acceleration = np.zeros(count, dtype=np.float32)
        if count > 1:
            acceleration[1:] = np.diff(flow_mean)

        fallback_transition = self._content_transition_score(frames)
        transition_probabilities, backend, transition_error = self._transition_score(frames, fallback_transition)
        analysis_s = time.perf_counter() - analysis_started

        duration_s = float(times[-1]) if count == 1 else float(times[-1] + max(1.0 / fps, times[-1] - times[-2]))
        return TemporalProfile(
            path=str(path),
            fps=fps,
            frame_count=count,
            duration_s=duration_s,
            backend=backend,
            decode_s=decode_s,
            analysis_s=analysis_s,
            transition_probabilities=transition_probabilities,
            mean_abs_delta=mean_abs_delta,
            changed_fraction=changed_fraction,
            flow_mean=flow_mean,
            acceleration=acceleration,
            luma=luma,
            timestamps_s=times,
            transition_error=transition_error,
        )

    @staticmethod
    def _content_transition_score(frames: np.ndarray) -> np.ndarray:
        import cv2  # type: ignore

        count = int(frames.shape[0])
        raw = np.zeros(count, dtype=np.float32)
        if count <= 1:
            return raw
        previous = cv2.cvtColor(frames[0], cv2.COLOR_RGB2HSV).astype(np.int16)
        for index in range(1, count):
            current = cv2.cvtColor(frames[index], cv2.COLOR_RGB2HSV).astype(np.int16)
            raw[index] = float(np.abs(current - previous).mean()) / 255.0
            previous = current
        return _robust_unit_score(raw)

    def _load_transnet(self) -> tuple[Any, str]:
        if self._transnet_model is not None and self._transnet_device is not None:
            return self._transnet_model, self._transnet_device
        if self._transnet_error is not None:
            raise RuntimeError(self._transnet_error)
        try:
            import torch  # type: ignore
            from transnetv2_pytorch import TransNetV2  # type: ignore

            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = TransNetV2(device=device)
            model.eval()
        except Exception as exc:
            self._transnet_error = f"{type(exc).__name__}: {exc}"
            raise RuntimeError(self._transnet_error) from exc
        self._transnet_model = model
        self._transnet_device = device
        return model, device

    def _transition_score(self, frames: np.ndarray, fallback: np.ndarray) -> tuple[np.ndarray, str, str | None]:
        if not self.prefer_transnet:
            return fallback, "hsv_content_fallback", "TransNetV2 disabled by caller"
        try:
            import cv2  # type: ignore
            import torch  # type: ignore

            model, device = self._load_transnet()
            model_frames = np.stack([
                cv2.resize(frame, (48, 27), interpolation=cv2.INTER_AREA)
                for frame in frames
            ]).astype(np.uint8, copy=False)
            tensor = torch.from_numpy(model_frames).to(device)
            with torch.inference_mode():
                single, _many = model.predict_frames(tensor, quiet=True)
            probabilities = single.detach().cpu().numpy().astype(np.float32).reshape(-1)
            if probabilities.size != frames.shape[0]:
                raise RuntimeError("TransNetV2 returned an unexpected frame count")
            return probabilities, f"transnetv2-pytorch:{device}", None
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            return fallback, "hsv_content_fallback", error

    @staticmethod
    def _frame_bounds(profile: TemporalProfile, start_s: float, end_s: float | None) -> tuple[int, int]:
        if start_s < 0:
            raise ValueError("start_s must be non-negative")
        effective_end = profile.duration_s if end_s is None else float(end_s)
        if effective_end < start_s:
            raise ValueError("end_s must be greater than or equal to start_s")
        start = int(np.searchsorted(profile.timestamps_s, start_s, side="left"))
        end = int(np.searchsorted(profile.timestamps_s, effective_end, side="right") - 1)
        start = min(max(start, 0), profile.frame_count - 1)
        end = min(max(end, start), profile.frame_count - 1)
        return start, end

    def find_event(
        self,
        reader: VideoSourceReader,
        *,
        event_type: str,
        description: str | None = None,
        start_s: float = 0.0,
        end_s: float | None = None,
        tolerance_frames: int = 2,
    ) -> TemporalEventResult:
        profile = self.profile(reader)
        start, end = self._frame_bounds(profile, start_s, end_s)
        kind = event_type.strip().lower().replace("-", "_").replace(" ", "_")
        if kind in {"transition", "cut", "shot_change"}:
            return self._signal_event(profile, "transition", profile.transition_probabilities, start, end, threshold=0.5, backend=profile.backend)
        if kind in {"motion_peak", "motion_extremum", "extremum"}:
            score = _robust_unit_score(profile.flow_mean) * 0.65 + _robust_unit_score(profile.mean_abs_delta) * 0.35
            return self._signal_event(profile, "motion_peak", score, start, end, threshold=0.05, backend="optical_flow+delta")
        if kind in {"acceleration", "acceleration_peak"}:
            score = _robust_unit_score(np.maximum(profile.acceleration, 0.0))
            return self._signal_event(profile, "acceleration_peak", score, start, end, threshold=0.05, backend="optical_flow_derivative")
        if kind == "impact":
            return self._find_impact(reader, profile, start, end, description)
        if kind in {"appearance", "action_start", "start", "occlusion"}:
            if not description:
                raise ValueError(f"description is required for semantic event type {kind}")
            return self._find_semantic_boundary(reader, profile, start, end, description, target=True, event_type=kind, tolerance_frames=tolerance_frames)
        if kind in {"disappearance", "action_end", "end"}:
            if not description:
                raise ValueError(f"description is required for semantic event type {kind}")
            return self._find_semantic_boundary(reader, profile, start, end, description, target=False, event_type=kind, tolerance_frames=tolerance_frames)
        raise ValueError(
            "event_type must be transition, motion_peak, acceleration_peak, impact, "
            "appearance/action_start/occlusion, or disappearance/action_end"
        )

    @staticmethod
    def _signal_event(
        profile: TemporalProfile,
        event_type: str,
        score: np.ndarray,
        start: int,
        end: int,
        *,
        threshold: float,
        backend: str,
    ) -> TemporalEventResult:
        view = np.asarray(score[start : end + 1], dtype=np.float32)
        local = int(np.argmax(view))
        index = start + local
        value = float(view[local])
        found = bool(value >= threshold)
        return TemporalEventResult(
            event_type=event_type,
            found=found,
            description=None,
            frame_index=index if found else None,
            timestamp_s=float(profile.timestamps_s[index]) if found else None,
            confidence=float(np.clip(value, 0.0, 1.0)),
            evidence_indices=(index,),
            bracket=None,
            backend=backend,
            reason=(
                f"Strongest {event_type} signal in requested range scored {value:.3f}."
                if found
                else f"Strongest {event_type} signal in requested range scored only {value:.3f}."
            ),
            uncertainty=None if found else "No signal exceeded the event threshold in the requested range.",
        )

    def _semantic(self) -> SemanticClient:
        if self.semantic_client is None:
            self.semantic_client = LocalQwenVLClient()
        return self.semantic_client

    def _classify_indices(
        self,
        reader: VideoSourceReader,
        indices: list[int],
        description: str,
        *,
        profile: TemporalProfile | None = None,
    ) -> tuple[dict[int, tuple[bool, float, str]], tuple[int, ...], str | None]:
        unique = sorted(set(int(index) for index in indices))
        path = Path(reader.metadata.path).resolve()
        source_key = self._cache_key(path)
        normalized = " ".join(description.strip().lower().split())
        cached = {i: self._semantic_cache[(source_key[0], source_key[1], source_key[2], normalized, i)] for i in unique if (source_key[0], source_key[1], source_key[2], normalized, i) in self._semantic_cache}
        missing = [i for i in unique if i not in cached]
        if not missing:
            return cached, tuple(unique), None
        guided = getattr(reader, "read_frames_at_timestamps", None)
        if profile is not None and callable(guided):
            frames = guided(missing, [float(profile.timestamps_s[i]) for i in missing])
        else:
            frames = reader.read_frames(missing)
        labels = [f"index={frame.frame_id} time={frame.metadata.get('source_time_s', 0.0):.6f}s" for frame in frames]
        prompt = f'''For each supplied exact source-video frame independently decide whether this complete visible statement is true:
"{description}"
Use only visible evidence in that frame. The complete statement must be visibly established; do not infer a person or subject from clothing, colors, objects, context, adjacent frames, or partial details alone.
Return JSON only as {{"frames":[{{"index":123,"match":true,"confidence":0.95}}],"uncertainty":null}}. Include exactly one item for every supplied index in chronological order. Do not return per-frame reason text.'''
        observation = self._semantic().observe_images(
            [frame.image for frame in frames],
            prompt=prompt,
            labels=labels,
            source=reader.metadata.path,
            max_tokens=max(128, 18 * len(frames) + 40),
            max_width=384,
            jpeg_quality=80,
        )
        payload = _extract_json_object(str(observation.text))
        items = payload.get("frames")
        if not isinstance(items, list):
            raise ValueError("semantic event response is missing a frames array")
        result: dict[int, tuple[bool, float, str]] = {}
        for item in items:
            if not isinstance(item, dict) or "index" not in item or "match" not in item:
                continue
            index = int(item["index"])
            if index not in unique:
                continue
            match = bool(item["match"])
            confidence = float(np.clip(float(item.get("confidence", 0.5)), 0.0, 1.0))
            reason = str(item.get("reason", "")).strip()
            result[index] = (match, confidence, reason)
        omitted = [index for index in missing if index not in result]
        if omitted:
            raise ValueError(f"semantic event response omitted requested indices: {omitted}")
        result.update(cached)
        for index in missing:
            self._semantic_cache[(source_key[0], source_key[1], source_key[2], normalized, index)] = result[index]
        uncertainty_value = payload.get("uncertainty")
        uncertainty = None if uncertainty_value in (None, "", "null") else str(uncertainty_value)
        return result, tuple(unique), uncertainty

    @staticmethod
    def _semantic_anchors(profile: TemporalProfile, start: int, end: int) -> list[int]:
        transitions = _local_peaks(
            profile.transition_probabilities,
            threshold=0.35,
            min_distance=max(1, int(round(profile.fps * 0.10))),
        )
        boundaries = [start]
        boundaries.extend(index for index in transitions if start < index < end)
        boundaries.append(end)
        anchors = {start, end}
        for left, right in zip(boundaries, boundaries[1:]):
            if right > left:
                anchors.add((left + right) // 2)

        ordered = sorted(index for index in anchors if start <= index <= end)
        if len(ordered) <= 32:
            return ordered
        positions = np.linspace(0, len(ordered) - 1, 32, dtype=int)
        return sorted({ordered[int(position)] for position in positions})

    def _find_semantic_boundary(
        self,
        reader: VideoSourceReader,
        profile: TemporalProfile,
        start: int,
        end: int,
        description: str,
        *,
        target: bool,
        event_type: str,
        tolerance_frames: int,
    ) -> TemporalEventResult:
        anchors = self._semantic_anchors(profile, start, end)
        classified: dict[int, tuple[bool, float, str]] = {}
        evidence: set[int] = set()
        uncertainty: str | None = None
        boundary: tuple[int, int] | None = None
        previous_index: int | None = None

        offset = 0
        batch_size = 12
        while offset < len(anchors):
            batch = anchors[offset : offset + batch_size]
            values, checked, note = self._classify_indices(reader, batch, description, profile=profile)
            classified.update(values)
            evidence.update(checked)
            uncertainty = uncertainty or note
            ordered = sorted(values)
            if previous_index is not None:
                ordered.insert(0, previous_index)
            for left, right in zip(ordered, ordered[1:]):
                if classified[left][0] is (not target) and classified[right][0] is target:
                    boundary = (left, right)
                    break
            if boundary is not None:
                break
            previous_index = batch[-1]
            offset += len(batch)
            batch_size = 4

        if boundary is None:
            return TemporalEventResult(
                event_type=event_type,
                found=False,
                description=description,
                frame_index=None,
                timestamp_s=None,
                confidence=0.0,
                evidence_indices=tuple(sorted(evidence)),
                bracket=None,
                backend="semantic:qwen3-vl",
                reason="No semantic boundary matching the requested state change was found.",
                uncertainty=uncertainty or "Visible evidence did not establish the requested boundary.",
            )

        low, high = boundary
        while high - low > max(1, tolerance_frames):
            sample_count = min(4, max(2, high - low - 1))
            samples = sorted({
                int(round(value))
                for value in np.linspace(low + 1, high - 1, sample_count)
                if low < int(round(value)) < high
            })
            if not samples:
                break
            values, checked, note = self._classify_indices(reader, samples, description, profile=profile)
            classified.update(values)
            evidence.update(checked)
            uncertainty = uncertainty or note
            sequence = [low] + samples + [high]
            refined: tuple[int, int] | None = None
            for left, right in zip(sequence, sequence[1:]):
                if classified[left][0] is (not target) and classified[right][0] is target:
                    refined = (left, right)
                    break
            if refined is None:
                break
            low, high = refined

        neighborhood = sorted({
            index
            for index in range(max(start, low - 1), min(end, high + 1) + 1)
        })
        values, checked, note = self._classify_indices(reader, neighborhood, description, profile=profile)
        classified.update(values)
        evidence.update(checked)
        uncertainty = uncertainty or note
        index = high
        if classified.get(index, (not target, 0.0, ""))[0] is not target:
            raise RuntimeError("semantic refinement lost its target-state bracket invariant")
        confidence = classified[index][1]
        return TemporalEventResult(
            event_type=event_type,
            found=True,
            description=description,
            frame_index=index,
            timestamp_s=float(profile.timestamps_s[index]),
            confidence=confidence,
            evidence_indices=tuple(sorted(evidence)),
            bracket=(low, high),
            backend="semantic:qwen3-vl+batched_refinement",
            reason=f"Semantic state changed to {target} within refined frame bracket {low}-{high}.",
            uncertainty=uncertainty,
        )

    def _find_impact(
        self,
        reader: VideoSourceReader,
        profile: TemporalProfile,
        start: int,
        end: int,
        description: str | None,
    ) -> TemporalEventResult:
        statement = description or (
            "A visible physical impact, collision, landing, hit, abrupt contact, "
            "or similarly abrupt action culmination is occurring in this exact frame."
        )
        score = _robust_unit_score(profile.flow_mean) * 0.65 + _robust_unit_score(profile.mean_abs_delta) * 0.35
        peaks = [
            index for index in _local_peaks(
                score,
                threshold=0.12,
                min_distance=max(1, int(round(profile.fps * 0.20))),
            )
            if start <= index <= end
        ]
        candidates = sorted(peaks, key=lambda index: float(score[index]), reverse=True)[:6]
        candidates.sort()
        if not candidates:
            return TemporalEventResult(
                event_type="impact", found=False, description=statement,
                frame_index=None, timestamp_s=None, confidence=0.0,
                evidence_indices=(), bracket=None, backend="optical_flow+delta",
                reason="No strong motion candidate was available for semantic impact confirmation.",
                uncertainty="The requested range did not contain a strong machine-motion peak.",
            )
        classified, used, uncertainty = self._classify_indices(reader, candidates, statement)
        matches = [index for index in candidates if classified[index][0]]
        if not matches:
            return TemporalEventResult(
                event_type="impact", found=False, description=statement,
                frame_index=None, timestamp_s=None,
                confidence=max((classified[index][1] for index in candidates), default=0.0),
                evidence_indices=used, bracket=None, backend="optical_flow+delta+qwen",
                reason="Qwen did not confirm an impact at any of the strongest machine-motion candidates.",
                uncertainty=uncertainty or "A subtle impact outside the strongest motion candidates could be missed.",
            )
        best = max(matches, key=lambda index: float(score[index]) * classified[index][1])
        semantic_confidence = classified[best][1]
        combined = float(np.clip(0.5 * float(score[best]) + 0.5 * semantic_confidence, 0.0, 1.0))
        return TemporalEventResult(
            event_type="impact",
            found=True,
            description=statement,
            frame_index=best,
            timestamp_s=float(profile.timestamps_s[best]),
            confidence=combined,
            evidence_indices=used,
            bracket=(max(start, best - 1), min(end, best + 1)),
            backend="optical_flow+delta+qwen",
            reason="A strong machine-motion peak was semantically confirmed as the requested impact.",
            uncertainty=uncertainty,
        )
