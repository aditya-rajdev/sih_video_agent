from pathlib import Path
import json
import shutil
import subprocess
from fractions import Fraction
import re

# ============================================================
# CONFIG
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

FRAMES_DIR = Path("output/frames")
VIDEOS_DIR = Path("output/videos")
REPORTS_DIR = Path("output/render_reports")

FFMPEG_COMMAND = "ffmpeg"
FFPROBE_COMMAND = "ffprobe"

CRF = 18
PRESET = "medium"

FINAL_VIDEO_DEFAULT = "final_video.mp4"


# ============================================================
# DIRECTORY HELPERS
# ============================================================

def ensure_directories():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# TOOL CHECKS
# ============================================================

def check_ffmpeg():
    """
    Check that FFmpeg is available in PATH.
    Returns the resolved executable path.
    """

    ffmpeg_path = shutil.which(FFMPEG_COMMAND)

    if not ffmpeg_path:
        raise RuntimeError(
            "FFmpeg was not found in PATH. "
            "Install FFmpeg and make sure `ffmpeg` works "
            "from PowerShell."
        )

    return ffmpeg_path


def check_ffprobe():
    """
    Check that FFprobe is available in PATH.
    """

    ffprobe_path = shutil.which(FFPROBE_COMMAND)

    if not ffprobe_path:
        raise RuntimeError(
            "FFprobe was not found in PATH. "
            "FFprobe normally comes with FFmpeg."
        )

    return ffprobe_path


# ============================================================
# FRAME HELPERS
# ============================================================

def get_frame_files(frames_dir: Path):
    """
    Return all PNG frames in deterministic filename order.
    """

    frames_dir = Path(frames_dir)

    if not frames_dir.exists():
        raise FileNotFoundError(
            f"Frame directory does not exist: {frames_dir}"
        )

    frames = sorted(
        frames_dir.glob("frame_*.png")
    )

    if not frames:
        raise FileNotFoundError(
            f"No PNG frames found in: {frames_dir}"
        )

    return frames


def validate_frame_sequence(frames_dir: Path):
    """
    Validate:
    - frames exist
    - frames are non-empty
    - numbering starts at frame_000000.png
    - numbering has no gaps
    """

    frames = get_frame_files(frames_dir)

    expected_index = 0

    for frame in frames:
        if not frame.exists():
            raise RuntimeError(
                f"Frame does not exist: {frame}"
            )

        if frame.stat().st_size == 0:
            raise RuntimeError(
                f"Frame is empty: {frame}"
            )

        match = re.fullmatch(
            r"frame_(\d{6})\.png",
            frame.name,
        )

        if not match:
            raise RuntimeError(
                f"Invalid frame filename: {frame.name}. "
                "Expected frame_000000.png style filenames."
            )

        frame_index = int(match.group(1))

        if frame_index != expected_index:
            raise RuntimeError(
                f"Frame sequence gap/mismatch in {frames_dir}: "
                f"expected frame_{expected_index:06d}.png, "
                f"found {frame.name}"
            )

        expected_index += 1

    return frames


def validate_frames(frames_dir: Path):
    """
    Backward-compatible frame validation function.
    """

    return validate_frame_sequence(
        frames_dir
    )


# ============================================================
# FFMPEG EXECUTION
# ============================================================

def run_ffmpeg(command):
    """
    Run FFmpeg and raise a useful error on failure.
    """

    print("\n----------------------------------------")
    print("Running FFmpeg")
    print("----------------------------------------")

    print(
        " ".join(
            f'"{arg}"' if " " in str(arg) else str(arg)
            for arg in command
        )
    )

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if process.returncode != 0:
        print(process.stderr)

        raise RuntimeError(
            f"FFmpeg failed with exit code "
            f"{process.returncode}"
        )

    return process


# ============================================================
# FFPROBE EXECUTION
# ============================================================

def run_ffprobe(video_file: Path):
    """
    Return ffprobe JSON metadata for a video.
    """

    check_ffprobe()

    video_file = Path(video_file)

    if not video_file.exists():
        raise FileNotFoundError(
            f"Video file not found: {video_file}"
        )

    command = [
        FFPROBE_COMMAND,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(video_file),
    ]

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if process.returncode != 0:
        raise RuntimeError(
            f"FFprobe failed for {video_file}:\n"
            f"{process.stderr}"
        )

    try:
        return json.loads(
            process.stdout
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Could not parse FFprobe output "
            f"for {video_file}: {exc}"
        )


# ============================================================
# VIDEO METADATA HELPERS
# ============================================================

def _parse_frame_rate(value):
    """
    Convert FFprobe frame-rate strings such as:
        30/1
        30000/1001
        30
    into float.
    """

    if value is None:
        return None

    try:
        return float(
            Fraction(str(value))
        )
    except (
        ValueError,
        ZeroDivisionError,
    ):
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None


def get_primary_video_stream(probe_data):
    """
    Return the first video stream from FFprobe data.
    """

    for stream in probe_data.get(
        "streams",
        [],
    ):
        if stream.get("codec_type") == "video":
            return stream

    raise RuntimeError(
        "No video stream found in generated video."
    )


def get_video_duration(video_file: Path):
    """
    Return duration in seconds using FFprobe.
    """

    probe = run_ffprobe(
        video_file
    )

    format_info = probe.get(
        "format",
        {},
    )

    duration = format_info.get(
        "duration"
    )

    if duration is None:
        stream = get_primary_video_stream(
            probe
        )
        duration = stream.get(
            "duration"
        )

    if duration is None:
        raise RuntimeError(
            f"Could not determine video duration: "
            f"{video_file}"
        )

    return float(duration)


# ============================================================
# VIDEO VALIDATION
# ============================================================

def validate_video_file(
    video_file: Path,
    expected_duration=None,
    duration_tolerance=0.15,
):
    """
    Validate the generated MP4.

    Required:
        - file exists
        - non-zero size
        - video stream exists
        - width = 1080
        - height = 1920
        - codec = H.264
        - pixel format = yuv420p
        - FPS approximately 30
        - optional duration matches expected duration
    """

    video_file = Path(video_file)

    if not video_file.exists():
        raise RuntimeError(
            f"Video file does not exist: {video_file}"
        )

    if video_file.stat().st_size == 0:
        raise RuntimeError(
            f"Video file is empty: {video_file}"
        )

    probe = run_ffprobe(
        video_file
    )

    stream = get_primary_video_stream(
        probe
    )

    width = int(
        stream.get("width", 0)
    )

    height = int(
        stream.get("height", 0)
    )

    codec_name = (
        stream.get("codec_name")
        or ""
    ).lower()

    pixel_format = (
        stream.get("pix_fmt")
        or ""
    ).lower()

    fps_value = _parse_frame_rate(
        stream.get("r_frame_rate")
    )

    duration = get_video_duration(
        video_file
    )

    errors = []

    if width != WIDTH:
        errors.append(
            f"width={width}, expected {WIDTH}"
        )

    if height != HEIGHT:
        errors.append(
            f"height={height}, expected {HEIGHT}"
        )

    if codec_name != "h264":
        errors.append(
            f"codec={codec_name}, expected h264"
        )

    if pixel_format != "yuv420p":
        errors.append(
            f"pix_fmt={pixel_format}, "
            f"expected yuv420p"
        )

    if fps_value is None:
        errors.append(
            "FPS could not be determined"
        )

    elif abs(fps_value - FPS) > 0.01:
        errors.append(
            f"fps={fps_value:.6f}, expected {FPS}"
        )

    if (
        expected_duration is not None
        and abs(
            duration -
            float(expected_duration)
        ) > duration_tolerance
    ):
        errors.append(
            f"duration={duration:.3f}s, "
            f"expected approximately "
            f"{float(expected_duration):.3f}s"
        )

    result = {
        "file": str(video_file),
        "width": width,
        "height": height,
        "fps": fps_value,
        "codec": codec_name,
        "pixel_format": pixel_format,
        "duration": duration,
        "size_bytes": video_file.stat().st_size,
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
    }

    if errors:
        raise RuntimeError(
            "Video validation failed for "
            f"{video_file}:\n- "
            + "\n- ".join(errors)
        )

    return result


# ============================================================
# RENDER ONE SCENE
# ============================================================

def render_scene_video(
    scene_id,
    duration=None,
):
    """
    Convert one scene's PNG frames into an MP4.

    Example:
        output/frames/scene_01/frame_000000.png
        ...
        output/videos/scene_01.mp4
    """

    ensure_directories()
    check_ffmpeg()

    scene_id = str(scene_id)

    frames_dir = (
        FRAMES_DIR /
        scene_id
    )

    frames = validate_frame_sequence(
        frames_dir
    )

    output_file = (
        VIDEOS_DIR /
        f"{scene_id}.mp4"
    )

    # --------------------------------------------------------
    # Calculate expected duration from frames if not supplied.
    # --------------------------------------------------------

    expected_duration = (
        float(duration)
        if duration is not None
        else len(frames) / FPS
    )

    if expected_duration <= 0:
        raise ValueError(
            f"Invalid duration for {scene_id}: "
            f"{expected_duration}"
        )

    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    print(
        "\n========================================"
    )
    print(
        f"FFMPEG SCENE RENDER: {scene_id}"
    )
    print(
        "========================================"
    )

    print(
        f"Frames     : {len(frames)}"
    )

    print(
        f"Duration   : "
        f"{expected_duration:.3f}s"
    )

    print(
        f"Resolution : "
        f"{WIDTH}x{HEIGHT}"
    )

    print(
        f"FPS        : {FPS}"
    )

    print(
        f"Output     : {output_file}"
    )

    # --------------------------------------------------------
    # frame_%06d.png matches:
    #
    # frame_000000.png
    # frame_000001.png
    # frame_000002.png
    # ...
    # --------------------------------------------------------

    command = [
        FFMPEG_COMMAND,

        "-y",

        "-framerate",
        str(FPS),

        "-start_number",
        "0",

        "-i",
        str(
            frames_dir /
            "frame_%06d.png"
        ),

        # Force exact output dimensions.
        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=disable"
        ),

        # Explicit constant frame rate.
        "-r",
        str(FPS),

        # H.264.
        "-c:v",
        "libx264",

        # High compatibility.
        "-pix_fmt",
        "yuv420p",

        # Quality.
        "-crf",
        str(CRF),

        # Encoding preset.
        "-preset",
        PRESET,

        # Fast-start MP4 metadata.
        "-movflags",
        "+faststart",

        str(output_file),
    ]

    run_ffmpeg(
        command
    )

    # --------------------------------------------------------
    # Validate output
    # --------------------------------------------------------

    validation = validate_video_file(
        output_file,
        expected_duration=expected_duration,
    )

    size_mb = (
        output_file.stat().st_size /
        (1024 * 1024)
    )

    print(
        "\n✅ Scene video created"
    )

    print(
        f"File size : {size_mb:.2f} MB"
    )

    print(
        f"Duration  : "
        f"{validation['duration']:.3f}s"
    )

    return output_file


# ============================================================
# GET VIDEO INFORMATION
# ============================================================

def get_video_info(video_file):
    """
    Backward-compatible helper.

    Returns FFmpeg-style media information text.
    """

    check_ffmpeg()

    video_file = Path(video_file)

    if not video_file.exists():
        raise FileNotFoundError(
            f"Video file not found: {video_file}"
        )

    command = [
        FFMPEG_COMMAND,
        "-i",
        str(video_file),
    ]

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    # FFmpeg writes media information to stderr.
    return process.stderr


# ============================================================
# RENDER ALL SCENE VIDEOS
# ============================================================

def render_all_scene_videos(
    scene_ids,
    durations=None,
):
    """
    Convert all rendered PNG scene folders into MP4 files.
    """

    ensure_directories()

    if not scene_ids:
        raise ValueError(
            "No scenes supplied."
        )

    if durations is not None:

        if len(scene_ids) != len(durations):
            raise ValueError(
                "Scene/duration mismatch."
            )

    results = []

    print(
        "\n========================================"
    )

    print(
        "MULTI-SCENE FFMPEG RENDERER"
    )

    print(
        "========================================"
    )

    print(
        f"Scenes : {len(scene_ids)}"
    )

    print(
        f"FPS    : {FPS}"
    )

    for index, scene_id in enumerate(
        scene_ids
    ):

        duration = (
            durations[index]
            if durations is not None
            else None
        )

        output_file = render_scene_video(
            scene_id=scene_id,
            duration=duration,
        )

        # Validate once more after creation.
        validation = validate_video_file(
            output_file,
            expected_duration=duration,
        )

        results.append(
            {
                "scene_id": str(scene_id),
                "video_file": str(
                    output_file
                ),
                "duration": validation[
                    "duration"
                ],
                "fps": validation[
                    "fps"
                ],
                "width": validation[
                    "width"
                ],
                "height": validation[
                    "height"
                ],
                "codec": validation[
                    "codec"
                ],
                "pixel_format": validation[
                    "pixel_format"
                ],
                "status": "PASS",
            }
        )

    return results


# ============================================================
# CONCAT FILE
# ============================================================

def create_concat_file(
    video_files,
):
    """
    Create FFmpeg concat-demuxer input file.
    """

    ensure_directories()

    if not video_files:
        raise ValueError(
            "No video files supplied "
            "for concat list."
        )

    concat_file = (
        VIDEOS_DIR /
        "concat_list.txt"
    )

    lines = []

    for video_file in video_files:

        absolute_path = (
            Path(video_file)
            .resolve()
        )

        if not absolute_path.exists():
            raise FileNotFoundError(
                f"Video for concat not found: "
                f"{absolute_path}"
            )

        # FFmpeg concat format:
        # file 'path'
        #
        # Escape single quotes for the
        # concat demuxer.
        path_string = str(
            absolute_path
        ).replace(
            "'",
            "'\\''",
        )

        lines.append(
            f"file '{path_string}'"
        )

    concat_file.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return concat_file


# ============================================================
# CONCATENATE SCENE VIDEOS
# ============================================================

def concatenate_scene_videos(
    video_files,
    output_name=FINAL_VIDEO_DEFAULT,
    expected_duration=None,
):
    """
    Concatenate scene MP4 files into the final MP4.

    The scene videos are encoded with identical:
        - resolution
        - FPS
        - H.264 codec
        - yuv420p pixel format

    Therefore the concat demuxer can use stream copy.
    """

    ensure_directories()
    check_ffmpeg()

    if not video_files:
        raise ValueError(
            "No scene videos supplied."
        )

    # --------------------------------------------------------
    # Validate every scene video before concatenation.
    # --------------------------------------------------------

    validated_videos = []

    total_expected_duration = 0.0

    for video_file in video_files:

        video_file = Path(
            video_file
        )

        if not video_file.exists():
            raise FileNotFoundError(
                f"Scene video not found: "
                f"{video_file}"
            )

        validation = validate_video_file(
            video_file
        )

        validated_videos.append(
            validation
        )

        total_expected_duration += (
            validation["duration"]
        )

    # --------------------------------------------------------
    # Create concat file.
    # --------------------------------------------------------

    concat_file = create_concat_file(
        video_files
    )

    output_file = (
        VIDEOS_DIR /
        output_name
    )

    # --------------------------------------------------------
    # Logging.
    # --------------------------------------------------------

    print(
        "\n========================================"
    )

    print(
        "CONCATENATING SCENE VIDEOS"
    )

    print(
        "========================================"
    )

    print(
        f"Scenes   : {len(video_files)}"
    )

    print(
        f"Duration : "
        f"{total_expected_duration:.3f}s"
    )

    print(
        f"Output   : {output_file}"
    )

    # --------------------------------------------------------
    # Concat using stream copy.
    # --------------------------------------------------------

    command = [
        FFMPEG_COMMAND,

        "-y",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        str(concat_file),

        "-c",
        "copy",

        "-movflags",
        "+faststart",

        str(output_file),
    ]

    run_ffmpeg(
        command
    )

    # --------------------------------------------------------
    # Validate final output.
    # --------------------------------------------------------

    if not output_file.exists():
        raise RuntimeError(
            "Final video was not created."
        )

    if output_file.stat().st_size == 0:
        raise RuntimeError(
            "Final video is empty."
        )

    validation = validate_video_file(
        output_file,
        expected_duration=(
            expected_duration
            if expected_duration is not None
            else total_expected_duration
        ),
        duration_tolerance=0.25,
    )

    size_mb = (
        output_file.stat().st_size /
        (1024 * 1024)
    )

    print(
        "\n✅ FINAL VIDEO CREATED"
    )

    print(
        f"File     : {output_file}"
    )

    print(
        f"Size     : {size_mb:.2f} MB"
    )

    print(
        f"Duration : "
        f"{validation['duration']:.3f}s"
    )

    return output_file


# ============================================================
# COMPLETE FRAME → FINAL VIDEO PIPELINE
# ============================================================

def render_final_video(
    scene_ids,
    durations=None,
    output_name=FINAL_VIDEO_DEFAULT,
):
    """
    Complete pipeline:

        PNG frames
            ↓
        scene MP4
            ↓
        final MP4
            ↓
        metadata validation
            ↓
        JSON report
    """

    print(
        "\n========================================"
    )

    print(
        "FRAME → VIDEO PIPELINE"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # Render every scene.
    # --------------------------------------------------------

    scene_results = render_all_scene_videos(
        scene_ids=scene_ids,
        durations=durations,
    )

    # --------------------------------------------------------
    # Extract scene video paths.
    # --------------------------------------------------------

    video_files = [
        result["video_file"]
        for result in scene_results
    ]

    # --------------------------------------------------------
    # Expected final duration.
    # --------------------------------------------------------

    expected_final_duration = sum(
        result["duration"]
        for result in scene_results
    )

    # --------------------------------------------------------
    # Concatenate scenes.
    # --------------------------------------------------------

    final_video = concatenate_scene_videos(
        video_files=video_files,
        output_name=output_name,
        expected_duration=expected_final_duration,
    )

    # --------------------------------------------------------
    # Final validation.
    # --------------------------------------------------------

    final_validation = validate_video_file(
        final_video,
        expected_duration=expected_final_duration,
        duration_tolerance=0.25,
    )

    # --------------------------------------------------------
    # Report.
    # --------------------------------------------------------

    report = {
        "status": "PASS",
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "codec": "h264",
        "pixel_format": "yuv420p",
        "expected_duration": expected_final_duration,
        "actual_duration": final_validation[
            "duration"
        ],
        "scenes": scene_results,
        "final_video": str(
            final_video
        ),
        "final_validation": final_validation,
    }

    report_file = (
        REPORTS_DIR /
        "ffmpeg_render_report.json"
    )

    report_file.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"Report: {report_file}"
    )

    return final_video


# ============================================================
# MAIN.PY COMPATIBILITY WRAPPER
# ============================================================

def render_video_from_frames(
    scene_ids=None,
    durations=None,
    output_name=FINAL_VIDEO_DEFAULT,
):
    """
    Compatibility wrapper for the existing main.py.

    Existing main.py may call:

        render_video_from_frames()

    If scene_ids are not supplied, automatically discover
    scene_* frame directories.
    """

    if scene_ids is None:

        if not FRAMES_DIR.exists():
            raise FileNotFoundError(
                f"Frames directory does not exist: "
                f"{FRAMES_DIR}"
            )

        scene_ids = sorted(
            [
                folder.name
                for folder in FRAMES_DIR.iterdir()
                if (
                    folder.is_dir()
                    and folder.name.startswith(
                        "scene_"
                    )
                )
            ]
        )

    if not scene_ids:
        raise ValueError(
            "No rendered scene directories found."
        )

    # --------------------------------------------------------
    # If durations are not supplied, derive them from frame
    # counts. This keeps the wrapper compatible with the
    # existing main.py.
    # --------------------------------------------------------

    if durations is None:

        durations = []

        for scene_id in scene_ids:

            frames = validate_frame_sequence(
                FRAMES_DIR /
                scene_id
            )

            durations.append(
                len(frames) / FPS
            )

    return render_final_video(
        scene_ids=scene_ids,
        durations=durations,
        output_name=output_name,
    )


# ============================================================
# STANDALONE TEST
# ============================================================

def main():

    if not FRAMES_DIR.exists():

        print(
            f"No scene frame directories found "
            f"in {FRAMES_DIR}"
        )

        return

    scene_ids = sorted(
        [
            folder.name
            for folder in FRAMES_DIR.iterdir()
            if (
                folder.is_dir()
                and folder.name.startswith(
                    "scene_"
                )
            )
        ]
    )

    if not scene_ids:

        print(
            f"No scene frame directories found "
            f"in {FRAMES_DIR}"
        )

        return

    render_final_video(
        scene_ids=scene_ids,
        output_name=FINAL_VIDEO_DEFAULT,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
