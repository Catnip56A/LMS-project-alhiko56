"""
Video frame extraction and perceptual-hash analysis for vision-captioning candidate moments
(Phase 6 addendum, video moment highlighting). No Flask/DB dependency — mirrors
transcription.py's split, so this module can be used directly by dev scripts or the RQ
worker without an app context.

PyAV bundles the FFmpeg libraries (same reason transcription.py needs no system ffmpeg
install), so this is the first code in the repo to decode a video *stream* — transcription.py
decodes only the audio stream from the same containers.

Whole-video download to grab a few frames (see moment_service._download_content_bytes reuse)
is an accepted tradeoff: this only ever runs from the background promotion sweep, never a
live request, and pays the same cost profile Whisper transcription already does.
"""
import base64
import io
import logging

import av
import imagehash
from PIL import Image, ImageFilter, ImageStat

logger = logging.getLogger(__name__)

# Hamming distance thresholds for 64-bit phash, reasoned starting points (not yet validated
# against this project's real lecture content — log the observed distribution on the first
# batch of real promotions so these can be tuned from data rather than guessed twice).
PHASH_NEAR_DUPLICATE_DISTANCE = 6   # <= this: same visual state
PHASH_DISTINCT_DISTANCE = 14        # >= this: a real transition (e.g. a slide change)
MAX_MOMENTS_PER_PROMOTION = 2

THUMBNAIL_SIZE = (640, 640)
JPEG_QUALITY = 80


def sample_frames(path: str, center_seconds: float, *, before: float = 8.0, after: float = 4.0, step: float = 2.0) -> list[tuple[float, Image.Image]]:
    """Decode a small window of frames around center_seconds. Deliberately backward-weighted
    (more `before` than `after`): both signal sources that produce a candidate moment — the
    auto keyword trigger firing while a phrase is spoken, and a student clicking after
    reacting — are systematically late relative to when the visual actually appeared.

    Returns [] on any failure (corrupt/unusual container, audio-only file, etc.) — a
    frame-extraction failure must degrade to "skip this moment", never crash the sweep.
    """
    try:
        container = av.open(path)
    except Exception as e:
        logger.error(f'Could not open video container {path}: {e}')
        return []

    try:
        if not container.streams.video:
            return []
        stream = container.streams.video[0]
        stream.thread_type = 'AUTO'

        start = max(0.0, center_seconds - before)
        # seek() takes the target in the stream's own time_base units, and the stream may
        # have a nonzero start_time offset (common in some MP4/MPEG-TS files) that must be
        # added, or every seek lands early by that offset.
        offset = stream.start_time or 0
        target = int(start / stream.time_base) + offset
        container.seek(target, stream=stream, backward=True, any_frame=False)

        wanted = [start + i * step for i in range(int((before + after) / step) + 1)]
        out: list[tuple[float, Image.Image]] = []
        wi = 0
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            while wi < len(wanted) and frame.time >= wanted[wi]:
                img = frame.to_image()
                img.thumbnail(THUMBNAIL_SIZE)
                out.append((float(frame.time), img))
                wi += 1
            if wi >= len(wanted):
                break
        return out
    except Exception as e:
        logger.error(f'Frame sampling failed for {path} at {center_seconds}s: {e}')
        return []
    finally:
        container.close()


def sharpness(img: Image.Image) -> float:
    """Edge energy — higher is sharper. Motion blur and mid-transition cross-fades flatten
    edges, so this reliably picks the settled frame out of a near-duplicate cluster."""
    return ImageStat.Stat(img.convert('L').filter(ImageFilter.FIND_EDGES)).stddev[0]


def image_to_jpeg_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG', quality=JPEG_QUALITY)
    return buf.getvalue()


def image_to_base64(img: Image.Image) -> str:
    return base64.b64encode(image_to_jpeg_bytes(img)).decode('ascii')


def phash_distance(hex_a: str, hex_b: str) -> int:
    return imagehash.hex_to_hash(hex_a) - imagehash.hex_to_hash(hex_b)


def analyze_frames(frames: list[tuple[float, Image.Image]]) -> list[tuple[float, Image.Image, str]]:
    """Perceptual-hash frame diffing: decides how many captioning calls a promoted moment is
    worth (0, 1, or 2) before any API cost is incurred. Returns
    [(timestamp, frame, phash_hex), ...], at most MAX_MOMENTS_PER_PROMOTION entries.

    Classifies the sampled window by consecutive Hamming distances between frames:
      - all near-duplicate           -> one visual state, caption the sharpest frame,
                                         timestamped at the window's first frame (when the
                                         visual first appeared, not when it looked sharpest).
      - one or two large jumps       -> a real transition (e.g. slide change); split into
                                         clusters at the jump(s), caption the sharpest frame
                                         of each of the two largest clusters.
      - distances sustained in the   -> continuous change (drawing, scrolling); caption only
        middle band                     the *last* frame (most complete state), not the
                                         sharpest, since sharpness would pick an arbitrary
                                         mid-change frame.
    """
    if not frames:
        return []
    if len(frames) == 1:
        t, img = frames[0]
        return [(t, img, str(imagehash.phash(img)))]

    hashes = [imagehash.phash(img) for _, img in frames]
    distances = [hashes[i] - hashes[i + 1] for i in range(len(hashes) - 1)]

    def sharpest(idxs):
        return max(idxs, key=lambda i: sharpness(frames[i][1]))

    big_jumps = [i for i, d in enumerate(distances) if d >= PHASH_DISTINCT_DISTANCE]
    all_near = all(d <= PHASH_NEAR_DUPLICATE_DISTANCE for d in distances)

    if all_near:
        idx = sharpest(range(len(frames)))
        t0, img0 = frames[0]
        return [(t0, frames[idx][1], str(hashes[idx]))]

    if 1 <= len(big_jumps) <= MAX_MOMENTS_PER_PROMOTION and all(
        d <= PHASH_NEAR_DUPLICATE_DISTANCE or d >= PHASH_DISTINCT_DISTANCE for d in distances
    ):
        bounds = [0] + [j + 1 for j in big_jumps] + [len(frames)]
        clusters = [range(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
        clusters.sort(key=len, reverse=True)
        chosen = []
        for cluster in clusters[:MAX_MOMENTS_PER_PROMOTION]:
            idx = sharpest(cluster)
            t_first = frames[list(cluster)[0]][0]
            chosen.append((t_first, frames[idx][1], str(hashes[idx])))
        chosen.sort(key=lambda c: c[0])
        return chosen

    # Continuous change (sustained middle-band distances): the latest/most complete frame.
    t_last, img_last = frames[-1]
    return [(t_last, img_last, str(hashes[-1]))]
