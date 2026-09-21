from pathlib import Path

from frame.gestures import GestureClassifier, hand_centroid
from frame.matrix import DepthFrame, parse_ascii_matrix


def _hand_blob(x0: int, x1: int, depth: int = 400) -> DepthFrame:
    values = [2000] * 64
    for y in range(3, 6):
        for x in range(x0, x1):
            values[y * 8 + x] = depth
    return DepthFrame(tuple(values))


def test_pop_usb_frames_lowercase_wrap() -> None:
    dump = (
        "y0:2415,4000,4000,4000,146,16,9,4000, \r\n"
        "y1:4000,4000,2016,117,130,18,15,4000, \r\n"
        "y2:4000,4000,4000,157,133,23,19,4000, \r\n"
        "y3:4000,4000,4000,174,147,35,21,4000, \r\n"
        "y4:4000,4000,4000,175,143,40,23,4000, \r\n"
        "y5:4000,426,404,172,148,45,4000,49, \r\n"
        "y6:398,361,314,189,135,59,4000,48, \r\n"
        "y7:355,336,325,210,4000,122,4000,45, \r\n"
        "y0:10,20,30,40,50,60,70,80,\r\n"
    )
    from frame.matrix import pop_usb_frames

    frames, rest = pop_usb_frames(dump)
    assert len(frames) == 1
    assert frames[0].at(0, 0) == 2415
    assert frames[0].at(7, 7) == 45
    assert rest.startswith("y0:10,20,30,40,50,60,70,80")


def test_parse_ascii_matrix() -> None:
    dump = "\n".join(
        f"Y{y}: " + ",".join(str(100 + y * 8 + x) for x in range(8)) + ","
        for y in range(8)
    )
    dump += "\n------------------------------\n"
    frame = parse_ascii_matrix(dump)
    assert frame is not None
    assert frame.at(0, 0) == 100
    assert frame.at(7, 7) == 100 + 63


def test_centroid_tracks_blob() -> None:
    left = _hand_blob(0, 3)
    right = _hand_blob(5, 8)
    lx, _, _ = hand_centroid(left)  # type: ignore[misc]
    rx, _, _ = hand_centroid(right)  # type: ignore[misc]
    assert lx < 3
    assert rx > 4


def _empty() -> DepthFrame:
    return DepthFrame(tuple([2000] * 64))


def _warmup(classifier: GestureClassifier, t: float = 0.0, frame: DepthFrame | None = None) -> float:
    empty = frame or _empty()
    for _ in range(18):
        classifier.update(t, empty)
        t += 0.05
    assert classifier.background_ready
    return t


def _arm(classifier: GestureClassifier, t: float, blob: DepthFrame) -> float:
    if not classifier.background_ready:
        t = _warmup(classifier, t)
    end = t + 0.22
    while t <= end:
        classifier.update(t, blob)
        t += 0.05
    assert classifier.armed
    return t


def test_swipe_left() -> None:
    classifier = GestureClassifier()
    t = _arm(classifier, 0.0, _hand_blob(5, 8))
    events = []
    for x0 in (5, 4, 3, 2, 1, 0):
        event = classifier.update(t, _hand_blob(x0, x0 + 3))
        if event is not None:
            events.append(event)
        t += 0.07
    assert events and events[0].gesture.value == "swipe_left"


def test_swipe_after_hover() -> None:
    classifier = GestureClassifier()
    t = _arm(classifier, 0.0, _hand_blob(5, 8))
    for _ in range(6):
        assert classifier.update(t, _hand_blob(5, 8)) is None
        t += 0.07
    events = []
    for x0 in (5, 4, 3, 2, 1, 0):
        event = classifier.update(t, _hand_blob(x0, x0 + 3))
        if event is not None:
            events.append(event)
        t += 0.07
    assert events and events[0].gesture.value == "swipe_left"


def test_swipe_completes_when_hand_leaves() -> None:
    classifier = GestureClassifier()
    t = _arm(classifier, 0.0, _hand_blob(5, 8))
    for x0 in (5, 4):
        classifier.update(t, _hand_blob(x0, x0 + 3))
        t += 0.07
    event = None
    for _ in range(3):
        found = classifier.update(t, _empty())
        if found is not None:
            event = found
        t += 0.05
    assert event is not None and event.gesture.value == "swipe_left"


def test_unarmed_swipe_does_not_fire() -> None:
    classifier = GestureClassifier()
    events = []
    t = 0.0
    for x0 in (5, 4, 3, 2, 1, 0):
        event = classifier.update(t, _hand_blob(x0, x0 + 3))
        if event is not None:
            events.append(event)
        t += 0.02
    assert events == []
    assert not classifier.armed


def test_debounce_blocks_second_command() -> None:
    classifier = GestureClassifier()
    t = _arm(classifier, 0.0, _hand_blob(5, 8))
    first = None
    for x0 in (5, 4, 3, 2, 1, 0):
        event = classifier.update(t, _hand_blob(x0, x0 + 3))
        if event is not None:
            first = event
        t += 0.07
    assert first is not None
    second = None
    for x0 in (0, 1, 2, 3, 4, 5):
        event = classifier.update(t, _hand_blob(x0, x0 + 3))
        if event is not None:
            second = event
        t += 0.04
    assert second is None
    t += 0.65
    third = None
    for x0 in (0, 1, 2, 3, 4, 5):
        event = classifier.update(t, _hand_blob(x0, x0 + 3))
        if event is not None:
            third = event
        t += 0.07
    assert third is not None and third.gesture.value == "swipe_right"


def test_hold_does_not_fire() -> None:
    classifier = GestureClassifier()
    t = _arm(classifier, 0.0, _hand_blob(3, 6))
    events = []
    for _ in range(16):
        event = classifier.update(t, _hand_blob(3, 6, depth=400))
        if event is not None:
            events.append(event)
        t += 0.07
    assert events == []


def test_push_plays() -> None:
    classifier = GestureClassifier()
    t = _arm(classifier, 0.0, _hand_blob(3, 6, depth=520))
    events = []
    for depth in (480, 400, 320, 250):
        event = classifier.update(t, _hand_blob(3, 6, depth=depth))
        if event is not None:
            events.append(event)
        t += 0.07
    assert events and events[0].gesture.value == "play"


def test_withdraw_emits_stop() -> None:
    classifier = GestureClassifier()
    t = _arm(classifier, 0.0, _hand_blob(3, 6))
    events = []
    for _ in range(8):
        event = classifier.update(t, _empty())
        if event is not None:
            events.append(event)
        t += 0.07
    assert events and events[0].gesture.value == "stop"
    assert not classifier.armed


def test_static_background_is_not_a_hand() -> None:
    classifier = GestureClassifier()
    desk = _hand_blob(2, 6, depth=400)
    t = 0.0
    for _ in range(40):
        event = classifier.update(t, desk)
        assert event is None
        t += 0.07
    assert classifier.background_ready
    assert not classifier.armed
    assert hand_centroid(desk, tuple(classifier._background)) is None


def test_recorded_empty_scene_does_not_arm() -> None:
    dump = (
        "y0:2415,4000,4000,4000,146,16,9,4000, \r\n"
        "y1:4000,4000,2016,117,130,18,15,4000, \r\n"
        "y2:4000,4000,4000,157,133,23,19,4000, \r\n"
        "y3:4000,4000,4000,174,147,35,21,4000, \r\n"
        "y4:4000,4000,4000,175,143,40,23,4000, \r\n"
        "y5:4000,426,404,172,148,45,4000,49, \r\n"
        "y6:398,361,314,189,135,59,4000,48, \r\n"
        "y7:355,336,325,210,4000,122,4000,45, \r\n"
    )
    from frame.matrix import pop_usb_frames

    frames, _ = pop_usb_frames(dump)
    scene = frames[0]
    classifier = GestureClassifier()
    t = 0.0
    for _ in range(40):
        classifier.update(t, scene)
        t += 0.07
    assert classifier.background_ready
    assert not classifier.armed


def test_stop_restarts_ken_burns_timer() -> None:
    from frame.player import Slide, Slideshow

    slides = [
        Slide(Path("a-still.jpg"), Path("a.gif"), "A", "landscape", kind="gif", token="a"),
        Slide(Path("b-still.jpg"), Path("b.gif"), "B", "landscape", kind="gif", token="b"),
    ]
    show = Slideshow(slides, dwell_seconds=5)
    show.play("push")
    generation = show.generation
    show.stop("withdraw")
    snap = show.snapshot()
    assert snap["playing"] is False
    assert snap["generation"] == generation + 1
    assert snap["cue"] == "pause"
    assert snap["remaining"] > 4.5


def test_pair_live_photos_and_mixed_library() -> None:
    import tempfile

    from frame.library import scan_library

    root = Path(tempfile.mkdtemp())
    (root / "IMG_100.HEIC").write_bytes(b"heic")
    (root / "IMG_100.MOV").write_bytes(b"mov")
    (root / "Holiday.JPG").write_bytes(b"jpg")
    (root / "Holiday.MP4").write_bytes(b"x" * (13 * 1024 * 1024))
    (root / "Loop.GIF").write_bytes(b"gif89")
    assets = scan_library(root)
    by_title = {}
    for asset in assets:
        by_title.setdefault(asset.title, []).append(asset)
    assert len(by_title["IMG 100"]) == 1
    assert by_title["IMG 100"][0].kind == "live"
    assert by_title["IMG 100"][0].playable
    kinds = {asset.kind for asset in by_title["Holiday"]}
    assert kinds == {"photo", "video"}
    assert by_title["Loop"][0].kind == "gif"


def test_motion_photo_extract() -> None:
    import tempfile

    from frame.derive import extract_embedded_motion

    payload = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 12
    jpeg = b"\xff\xd8\xff\xe1MicroVideoOffset:" + str(len(payload)).encode("ascii") + b";" + payload
    source = Path(tempfile.mkdtemp()) / "motion.jpg"
    dest = source.with_name("out.mp4")
    source.write_bytes(jpeg)
    assert extract_embedded_motion(source, dest)
    assert dest.read_bytes() == payload


def test_scan_skips_cache_dir() -> None:
    import tempfile

    from frame.library import scan_library

    root = Path(tempfile.mkdtemp())
    (root / "Keep.JPG").write_bytes(b"jpg")
    cache = root / ".frame-cache"
    cache.mkdir()
    (cache / "derived.jpg").write_bytes(b"nope")
    assets = scan_library(root)
    assert [asset.title for asset in assets] == ["Keep"]


def test_orientation_honors_exif_rotation() -> None:
    import tempfile

    from PIL import Image

    from frame.derive import _orientation

    root = Path(tempfile.mkdtemp())
    rotated = root / "rotated.jpg"
    plain = root / "plain.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (400, 300)).save(rotated, exif=exif)
    Image.new("RGB", (400, 300)).save(plain)
    assert _orientation(rotated) == "portrait"
    assert _orientation(plain) == "landscape"


def test_gcamera_marker_alone_is_not_motion() -> None:
    import tempfile

    from frame.library import has_embedded_motion

    root = Path(tempfile.mkdtemp())
    still = root / "PXL_0001.jpg"
    still.write_bytes(b"\xff\xd8\xff\xe1<x:xmpmeta xmlns:GCamera='http://ns.google.com/photos/1.0/camera/'/>")
    assert not has_embedded_motion(still)
    motion = root / "PXL_0002.jpg"
    motion.write_bytes(b"\xff\xd8\xff\xe1GCamera:MicroVideoOffset=\"12\"")
    assert has_embedded_motion(motion)


def test_failed_motion_extract_falls_back_to_photo() -> None:
    import tempfile

    from frame.derive import prepare_slide
    from frame.library import MediaAsset

    root = Path(tempfile.mkdtemp())
    still = root / "fake-live.jpg"
    from PIL import Image

    Image.new("RGB", (64, 48)).save(still)
    asset = MediaAsset(kind="live", title="Fake", still_source=still, motion_source=None, embedded_motion=True)
    slide = prepare_slide(asset, root / ".frame-cache")
    assert slide is not None
    assert slide.kind == "photo"
    assert not slide.playable


def test_scan_skips_zero_byte_media() -> None:
    import tempfile

    from frame.library import scan_library

    root = Path(tempfile.mkdtemp())
    (root / "Live.JPG").write_bytes(b"jpg")
    (root / "Live.MOV").write_bytes(b"")
    (root / "Empty.mp4").write_bytes(b"")
    assets = scan_library(root)
    assert [(asset.kind, asset.title) for asset in assets] == [("photo", "Live")]


def test_parse_range() -> None:
    from frame.preview import _parse_range

    assert _parse_range("bytes=0-99", 1000) == (0, 99)
    assert _parse_range("bytes=900-", 1000) == (900, 999)
    assert _parse_range("bytes=-100", 1000) == (900, 999)
    assert _parse_range("bytes=0-5000", 1000) == (0, 999)
    assert _parse_range("bytes=abc-", 1000) is None
    assert _parse_range("bytes=-", 1000) is None
    assert _parse_range("bytes=1000-", 1000) is None
    assert _parse_range("bytes=50-10", 1000) is None
    assert _parse_range("items=0-1", 1000) is None


if __name__ == "__main__":
    test_parse_ascii_matrix()
    test_pop_usb_frames_lowercase_wrap()
    test_centroid_tracks_blob()
    test_swipe_left()
    test_swipe_after_hover()
    test_swipe_completes_when_hand_leaves()
    test_unarmed_swipe_does_not_fire()
    test_debounce_blocks_second_command()
    test_hold_does_not_fire()
    test_push_plays()
    test_withdraw_emits_stop()
    test_static_background_is_not_a_hand()
    test_recorded_empty_scene_does_not_arm()
    test_stop_restarts_ken_burns_timer()
    test_pair_live_photos_and_mixed_library()
    test_motion_photo_extract()
    test_scan_skips_cache_dir()
    test_orientation_honors_exif_rotation()
    test_gcamera_marker_alone_is_not_motion()
    test_failed_motion_extract_falls_back_to_photo()
    test_scan_skips_zero_byte_media()
    test_parse_range()
    print("ok")
