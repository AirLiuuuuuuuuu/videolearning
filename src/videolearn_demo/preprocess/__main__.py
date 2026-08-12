"""Command-line entry point for video preprocessing."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import imageio_ffmpeg
import yaml


def derive_video_id(video_path: Path) -> str:
    """Create a stable, filesystem-safe identifier from a video filename."""
    normalized = re.sub(r"[^\w-]+", "_", video_path.stem).strip("_-")
    return normalized.lower() or "video"


def load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def extract_audio(video_path: Path, audio_path: Path, sample_rate: int) -> None:
    """Extract a Whisper-friendly mono WAV file using the bundled FFmpeg binary."""
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)


def read_video_metadata(video_path: Path) -> dict[str, float | int]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"无法读取视频：{video_path}")
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps else 0.0
        return {"fps": round(fps, 3), "frame_count": frame_count, "duration_seconds": round(duration, 3)}
    finally:
        capture.release()


def write_transcript(audio_path: Path, output_path: Path, language: str, model_name: str) -> int:
    """Run local Whisper and write each recognized segment as one JSONL record."""
    import torch
    import whisper
    import whisper.audio

    # imageio-ffmpeg ships a versioned executable (rather than `ffmpeg.exe`),
    # so make Whisper invoke that exact file on Windows.
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    whisper_run = whisper.audio.run

    def run_with_bundled_ffmpeg(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        if command and command[0] == "ffmpeg":
            command = [ffmpeg_path, *command[1:]]
        return whisper_run(command, **kwargs)

    whisper.audio.run = run_with_bundled_ffmpeg

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = whisper.load_model(model_name, device=device)
    result = model.transcribe(str(audio_path), language=language, fp16=device == "cuda")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as transcript_file:
        for segment in result["segments"]:
            record = {
                "start_sec": round(segment["start"], 3),
                "end_sec": round(segment["end"], 3),
                "text": segment["text"].strip(),
                "source": "asr",
            }
            transcript_file.write(json.dumps(record, ensure_ascii=False) + "\n")
    return len(result["segments"])


def extract_keyframes(video_path: Path, frames_dir: Path, manifest_path: Path, interval_seconds: float) -> int:
    """Save one JPEG frame per interval and record its exact video timestamp."""
    if interval_seconds <= 0:
        raise ValueError("frame_interval_seconds 必须大于 0")

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"无法读取视频：{video_path}")

    frames_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    timestamp = 0.0
    try:
        duration = read_video_metadata(video_path)["duration_seconds"]
        with manifest_path.open("w", encoding="utf-8") as manifest_file:
            while timestamp <= float(duration):
                capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
                success, frame = capture.read()
                if success:
                    frame_name = f"frame_{timestamp:010.3f}.jpg"
                    frame_path = frames_dir / frame_name
                    cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
                    manifest_file.write(json.dumps({"timestamp_sec": round(timestamp, 3), "file": f"frames/{frame_name}"}) + "\n")
                    count += 1
                timestamp += interval_seconds
    finally:
        capture.release()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="提取视频音频、Whisper 字幕和时间关键帧。")
    parser.add_argument("video", type=Path, help="待处理的视频文件路径")
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"), help="YAML 配置文件路径")
    args = parser.parse_args()

    if not args.video.is_file():
        parser.error(f"视频文件不存在：{args.video}")
    if not args.config.is_file():
        parser.error(f"配置文件不存在：{args.config}")

    config = load_config(args.config)
    preprocess = config.get("preprocess", {})
    data_dir = Path(config.get("project", {}).get("data_dir", "data"))
    video_id = derive_video_id(args.video)
    interim_dir = data_dir / "interim" / video_id
    artifact_dir = Path("artifacts") / video_id
    audio_path = interim_dir / "audio.wav"
    metadata = read_video_metadata(args.video)

    print(f"正在处理：{args.video.name}（ID: {video_id}）")
    extract_audio(args.video, audio_path, int(preprocess.get("audio_sample_rate", 16000)))
    print(f"已提取音频：{audio_path}")

    segment_count = write_transcript(
        audio_path,
        artifact_dir / "transcript.jsonl",
        str(preprocess.get("language", "zh")),
        str(preprocess.get("whisper_model", "base")),
    )
    print(f"已生成字幕：{segment_count} 个片段")

    frame_count = extract_keyframes(
        args.video,
        artifact_dir / "frames",
        artifact_dir / "frames.jsonl",
        float(preprocess.get("frame_interval_seconds", 5)),
    )
    print(f"已生成关键帧：{frame_count} 张")

    metadata.update(
        {
            "video_id": video_id,
            "source_file": args.video.name,
            "language": preprocess.get("language", "zh"),
            "whisper_model": preprocess.get("whisper_model", "base"),
            "preprocess_version": "0.1",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"完成。结果目录：{artifact_dir}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        print(error.stderr, file=sys.stderr)
        raise SystemExit("音频提取失败，请检查视频文件是否包含有效音轨。") from error
