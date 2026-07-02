from __future__ import annotations

import subprocess
from pathlib import Path

from backend.models.clip import ClipCandidate


class RenderingService:
    def render_clip(self, source_video: Path, output_path: Path, clip: ClipCandidate) -> Path:
        """Render a clip by stitching hook, body, and ending segments."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        segments = [
            (clip.hook_start, clip.hook_end),
            (clip.body_start, clip.body_end),
            (clip.ending_start, clip.ending_end),
        ]

        input_args: list[str] = []
        filter_inputs: list[str] = []

        for i, (start, end) in enumerate(segments):
            input_args.extend(["-ss", str(start), "-to", str(end), "-i", str(source_video)])
            filter_inputs.append(f"[{i}:v][{i}:a]")

        concat_filter = f"concat=n={len(segments)}:v=1:a=1[outv][outa]"
        filter_complex = "".join(filter_inputs) + concat_filter

        cmd = [
            "ffmpeg", "-y",
            *input_args,
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg stitch failed: {e.stderr.decode()}") from e

        return output_path
