# 预处理数据约定

这一阶段只处理一个目标：把原始视频转为可追溯的文字、画面信息和时间信息。

## 文件位置

- `data/raw/`：手动放入原始视频；文件不提交到 Git。
- `data/interim/<video_id>/`：自动生成的音频、抽帧、识别原始结果；不提交到 Git。
- `artifacts/<video_id>/`：供检查或演示使用的最终预处理结果；不提交到 Git。

`video_id` 使用文件名去掉扩展名后的安全名称，例如 `lecture_001.mp4` 对应 `lecture_001`。

## 最小元数据格式

每个视频最终应生成 `artifacts/<video_id>/metadata.json`：

```json
{
  "video_id": "lecture_001",
  "source_file": "lecture_001.mp4",
  "duration_seconds": 600.0,
  "language": "zh",
  "preprocess_version": "0.1"
}
```

## 文字片段格式

语音识别和 OCR 均保存为 JSON Lines（每行一个时间片段），方便后续合并、索引和增量处理：

```json
{"video_id":"lecture_001","start_sec":12.5,"end_sec":18.2,"text":"欢迎来到课程。","source":"asr"}
```

字段含义：

- `start_sec` / `end_sec`：片段在视频中的起止秒数。
- `text`：识别出的文字。
- `source`：文字来源，当前为 `asr`（听）或 `ocr`（看）。

后续“编目录”阶段只读取这些结构化文件，不直接依赖原始视频。

## 本阶段的命令

将视频放入 `data/raw/` 后运行：

```powershell
.\.venv\Scripts\python.exe -m videolearn_demo.preprocess data/raw/lecture_001.mp4
```

执行后会产生：

- `data/interim/<video_id>/audio.wav`：16 kHz 单声道音频，供 Whisper 使用。
- `artifacts/<video_id>/transcript.jsonl`：带时间戳的语音字幕。
- `artifacts/<video_id>/frames/`：按配置时间间隔抽取的 JPEG 关键帧。
- `artifacts/<video_id>/frames.jsonl`：每张关键帧的时间戳及相对路径。
- `artifacts/<video_id>/metadata.json`：视频和本次处理的基本信息。
