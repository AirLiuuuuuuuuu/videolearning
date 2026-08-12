from pathlib import Path

from videolearn_demo.preprocess.__main__ import derive_video_id


def test_derive_video_id() -> None:
    assert derive_video_id(Path("课程 第一讲.mp4")) == "课程_第一讲"
    assert derive_video_id(Path("Lecture 001!.mp4")) == "lecture_001"
