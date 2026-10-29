from pathlib import Path
import asyncio
import json
import re

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


class RuntimeSceneError(RuntimeError):
    """
    Structured browser/runtime error.

    main.py uses this to identify the failed scene and send the
    runtime failure to the LLM code fixer.
    """

    def __init__(
        self,
        message,
        scene_file=None,
        scene_id=None,
        current_time=None,
        frame_number=None,
    ):
        super().__init__(message)

        self.message = str(message)
        self.scene_file = (
            str(scene_file)
            if scene_file is not None
            else ""
        )
        self.scene_id = (
            str(scene_id)
            if scene_id is not None
            else ""
        )
        self.current_time = current_time
        self.frame_number = frame_number

        match = re.search(
            r"(\d+)",
            self.scene_id,
        )

        self.scene_id_number = (
            int(match.group(1))
            if match
            else None
        )


# ============================================================
# CONFIG
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

SCENES_DIR = Path(
    "output/generated_scenes"
)

FRAMES_DIR = Path(
    "output/frames"
)

REPORTS_DIR = Path(
    "output/render_reports"
)

PAGE_LOAD_TIMEOUT = 30_000
SCENE_READY_TIMEOUT = 10_000


# ============================================================
# DIRECTORY HELPERS
# ============================================================

def ensure_directories():
    """
    Create required output directories.
    """

    FRAMES_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def clear_scene_frames(
    scene_id: str,
) -> Path:
    """
    Remove previously generated frames
    for a scene and create a clean directory.
    """

    folder = (
        FRAMES_DIR /
        scene_id
    )

    if folder.exists():

        for file in folder.glob(
            "frame_*.png"
        ):

            try:
                file.unlink()

            except OSError as exc:

                print(
                    f"Warning: could not delete "
                    f"{file}: {exc}"
                )

    folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    return folder


# ============================================================
# HTML VALIDATION
# ============================================================

def validate_scene_file(
    scene_file: Path,
):
    """
    Validate generated HTML before rendering.
    """

    if not scene_file.exists():

        raise FileNotFoundError(
            f"Scene HTML not found: "
            f"{scene_file}"
        )

    if not scene_file.is_file():

        raise ValueError(
            f"Scene path is not a file: "
            f"{scene_file}"
        )

    content = scene_file.read_text(
        encoding="utf-8",
        errors="replace",
    )

    if not content.strip():

        raise ValueError(
            f"Scene HTML is empty: "
            f"{scene_file}"
        )

    content_lower = (
        content.lower()
    )

    if "<html" not in content_lower:

        raise ValueError(
            f"Invalid HTML scene: "
            f"<html> not found in "
            f"{scene_file}"
        )

    if "<body" not in content_lower:

        raise ValueError(
            f"Invalid HTML scene: "
            f"<body> not found in "
            f"{scene_file}"
        )

    return content


# ============================================================
# BROWSER HELPERS
# ============================================================

async def wait_for_scene_ready(
    page,
):
    """
    Wait for optional sceneReady contract.

    Generated HTML can expose:

        window.sceneReady = true

    If sceneReady is not defined,
    rendering continues after DOM load.
    """

    try:

        await page.wait_for_function(
            """
            () => {
                return (
                    window.sceneReady === true ||
                    window.sceneReady === undefined
                );
            }
            """,
            timeout=SCENE_READY_TIMEOUT,
        )

    except PlaywrightTimeoutError:

        raise RuntimeError(
            "Scene did not become ready "
            "within the expected time."
        )


async def check_renderer_contract(
    page,
):
    """
    Verify deterministic rendering contract.

    Required:

        window.setVideoTime(time)
    """

    result = await page.evaluate(
        """
        () => ({
            hasSetVideoTime:
                typeof window.setVideoTime === "function",

            hasSceneReady:
                window.sceneReady !== undefined,

            sceneReady:
                window.sceneReady === true
        })
        """
    )

    if not result[
        "hasSetVideoTime"
    ]:

        raise RuntimeError(
            "Rendering contract violation: "
            "window.setVideoTime(time) "
            "is missing."
        )

    return result


async def set_video_time(
    page,
    current_time: float,
    scene_file=None,
    scene_id=None,
    frame_number=None,
):
    """
    Execute window.setVideoTime safely.

    Browser JavaScript errors are converted into RuntimeSceneError
    so main.py can automatically repair the failed scene.
    """

    try:

        await page.evaluate(
            """
            (time) => {

                if (
                    typeof window.setVideoTime !==
                    "function"
                ) {
                    throw new Error(
                        "window.setVideoTime is not a function."
                    );
                }

                window.setVideoTime(time);
            }
            """,
            current_time,
        )

    except Exception as exc:

        raise RuntimeSceneError(
            message=(
                "JavaScript runtime error while executing "
                f"window.setVideoTime({current_time}): {exc}"
            ),
            scene_file=scene_file,
            scene_id=scene_id,
            current_time=current_time,
            frame_number=frame_number,
        ) from exc


# ============================================================
# FRAME VALIDATION
# ============================================================

def validate_frame_file(
    frame_path: Path,
):
    """
    Verify that a frame exists and is non-empty.
    """

    if not frame_path.exists():

        raise RuntimeError(
            f"Expected frame was not created: "
            f"{frame_path}"
        )

    if frame_path.stat().st_size == 0:

        raise RuntimeError(
            f"Frame is empty: "
            f"{frame_path}"
        )


def count_rendered_frames(
    frames_dir: Path,
) -> int:
    """
    Count PNG frames.
    """

    return len(
        list(
            frames_dir.glob(
                "frame_*.png"
            )
        )
    )


# ============================================================
# SCENE RENDERER
# ============================================================

async def render_scene(
    page,
    scene_file,
    duration,
):
    """
    Render one HTML scene into PNG frames.
    """

    scene_file = Path(
        scene_file
    )

    # --------------------------------------------------------
    # Validate HTML
    # --------------------------------------------------------

    validate_scene_file(
        scene_file
    )

    scene_id = (
        scene_file.stem
    )

    # --------------------------------------------------------
    # Browser runtime error collection
    # --------------------------------------------------------

    browser_errors = []

    def _on_page_error(error):
        try:
            browser_errors.append(
                str(error)
            )
        except Exception:
            browser_errors.append(
                repr(error)
            )

    def _on_console(message):
        try:
            if message.type == "error":
                browser_errors.append(
                    f"Console error: {message.text}"
                )
        except Exception:
            pass

    page.on(
        "pageerror",
        _on_page_error,
    )

    page.on(
        "console",
        _on_console,
    )

    # --------------------------------------------------------
    # Validate duration
    # --------------------------------------------------------

    try:

        duration = float(
            duration
        )

    except (
        TypeError,
        ValueError,
    ):

        raise ValueError(
            f"Invalid duration for "
            f"{scene_id}: {duration}"
        )

    if duration <= 0:

        raise ValueError(
            f"Scene duration must be > 0: "
            f"{scene_id}"
        )

    # --------------------------------------------------------
    # Prepare frames directory
    # --------------------------------------------------------

    frames_dir = (
        clear_scene_frames(
            scene_id
        )
    )

    total_frames = max(
        1,
        int(
            round(
                duration * FPS
            )
        ),
    )

    # ========================================================
    # INFORMATION
    # ========================================================

    print(
        "\n========================================"
    )

    print(
        f"RENDERING {scene_id}"
    )

    print(
        "========================================"
    )

    print(
        f"File       : {scene_file}"
    )

    print(
        f"Duration   : {duration:.3f}s"
    )

    print(
        f"FPS        : {FPS}"
    )

    print(
        f"Resolution : "
        f"{WIDTH}x{HEIGHT}"
    )

    print(
        f"Frames     : "
        f"{total_frames}"
    )

    # ========================================================
    # LOAD HTML
    # ========================================================

    try:

        await page.goto(
            scene_file.resolve().as_uri(),
            wait_until="load",
            timeout=PAGE_LOAD_TIMEOUT,
        )

    except PlaywrightTimeoutError:

        raise RuntimeSceneError(
            message=(
                f"Page load timeout: {scene_file}"
            ),
            scene_file=scene_file,
            scene_id=scene_id,
        )

    except Exception as exc:

        raise RuntimeSceneError(
            message=(
                f"Browser failed to load scene: {exc}"
            ),
            scene_file=scene_file,
            scene_id=scene_id,
        ) from exc

    await page.wait_for_timeout(100)

    if browser_errors:

        raise RuntimeSceneError(
            message=(
                "Browser JavaScript error during scene load: "
                + " | ".join(browser_errors[-5:])
            ),
            scene_file=scene_file,
            scene_id=scene_id,
        )

    # ========================================================
    # INITIAL WAIT
    # ========================================================

    await page.wait_for_timeout(
        250
    )

    # --------------------------------------------------------
    # Wait for browser fonts.
    # --------------------------------------------------------

    try:

        await page.evaluate(
            """
            async () => {

                if (
                    document.fonts &&
                    document.fonts.ready
                ) {

                    await document.fonts.ready;
                }
            }
            """
        )

    except Exception as exc:

        raise RuntimeSceneError(
            message=(
                f"JavaScript error while preparing fonts: {exc}"
            ),
            scene_file=scene_file,
            scene_id=scene_id,
        ) from exc

    # --------------------------------------------------------
    # Wait for optional scene readiness.
    # --------------------------------------------------------

    await wait_for_scene_ready(
        page
    )

    # ========================================================
    # CHECK CONTRACT
    # ========================================================

    try:

        contract = (
            await check_renderer_contract(
                page
            )
        )

    except Exception as exc:

        raise RuntimeSceneError(
            message=(
                f"Rendering contract/runtime error: {exc}"
            ),
            scene_file=scene_file,
            scene_id=scene_id,
        ) from exc

    print(
        "setVideoTime : "
        f"{'OK' if contract['hasSetVideoTime'] else 'MISSING'}"
    )

    # ========================================================
    # FORCE VIEWPORT / BODY
    # ========================================================

    try:

        await page.evaluate(
            """
            () => {

                if (!document.documentElement) {
                    throw new Error(
                        "document.documentElement is missing."
                    );
                }

                if (!document.body) {
                    throw new Error(
                        "document.body is missing."
                    );
                }

                document.documentElement.style.overflow =
                    "hidden";

                document.body.style.overflow =
                    "hidden";

                document.documentElement.style.width =
                    "1080px";

                document.documentElement.style.height =
                    "1920px";

                document.body.style.width =
                    "1080px";

                document.body.style.height =
                    "1920px";

                document.body.style.margin =
                    "0";
            }
            """
        )

    except Exception as exc:

        raise RuntimeSceneError(
            message=(
                f"JavaScript error while configuring viewport: {exc}"
            ),
            scene_file=scene_file,
            scene_id=scene_id,
        ) from exc

    # ========================================================
    # CAPTURE FRAMES
    # ========================================================

    print(
        "Capturing frames..."
    )

    for frame_number in range(
        total_frames
    ):

        # ----------------------------------------------------
        # Calculate deterministic time.
        # ----------------------------------------------------

        current_time = (
            frame_number / FPS
        )

        # ----------------------------------------------------
        # Update animation.
        # ----------------------------------------------------

        await set_video_time(
            page,
            current_time,
            scene_file=scene_file,
            scene_id=scene_id,
            frame_number=frame_number,
        )

        if browser_errors:

            raise RuntimeSceneError(
                message=(
                    "Browser JavaScript runtime error: "
                    + " | ".join(browser_errors[-5:])
                ),
                scene_file=scene_file,
                scene_id=scene_id,
                current_time=current_time,
                frame_number=frame_number,
            )

        # ----------------------------------------------------
        # Wait one browser render cycle.
        # ----------------------------------------------------

        try:

            await page.evaluate(
                """
                () =>
                    new Promise(
                        resolve =>
                            requestAnimationFrame(
                                resolve
                            )
                    )
                """
            )

        except Exception as exc:

            raise RuntimeSceneError(
                message=(
                    f"JavaScript/render-frame error: {exc}"
                ),
                scene_file=scene_file,
                scene_id=scene_id,
                current_time=current_time,
                frame_number=frame_number,
            ) from exc

        # ----------------------------------------------------
        # Frame path.
        # ----------------------------------------------------

        frame_path = (
            frames_dir /
            f"frame_{frame_number:06d}.png"
        )

        # ----------------------------------------------------
        # Screenshot.
        # ----------------------------------------------------

        try:
            # The scene is already deterministic via setVideoTime().
            # Fonts are awaited once before frame capture.
            await page.screenshot(
                path=str(frame_path),
                type="png",
                animations="disabled",
                timeout=10_000,
            )

        except PlaywrightTimeoutError as exc:
            raise RuntimeSceneError(
                message=(
                    f"Screenshot timeout while capturing "
                    f"frame {frame_number + 1}/{total_frames}: {exc}"
                ),
                scene_file=scene_file,
                scene_id=scene_id,
                current_time=current_time,
                frame_number=frame_number,
            ) from exc

        except Exception as exc:
            raise RuntimeSceneError(
                message=(
                    f"Screenshot error while capturing "
                    f"frame {frame_number + 1}/{total_frames}: {exc}"
                ),
                scene_file=scene_file,
                scene_id=scene_id,
                current_time=current_time,
                frame_number=frame_number,
            ) from exc

        # ----------------------------------------------------
        # Validate frame.
        # ----------------------------------------------------

        validate_frame_file(
            frame_path
        )

        if browser_errors:

            raise RuntimeSceneError(
                message=(
                    "Browser JavaScript runtime error after "
                    "frame capture: "
                    + " | ".join(browser_errors[-5:])
                ),
                scene_file=scene_file,
                scene_id=scene_id,
                current_time=current_time,
                frame_number=frame_number,
            )

        # ----------------------------------------------------
        # Progress.
        # ----------------------------------------------------

        if (
            frame_number == 0
            or frame_number % FPS == 0
            or frame_number ==
            total_frames - 1
        ):

            print(
                f"Frame "
                f"{frame_number + 1}/"
                f"{total_frames}"
            )

    # ========================================================
    # VALIDATE FRAME COUNT
    # ========================================================

    rendered_frames = (
        count_rendered_frames(
            frames_dir
        )
    )

    if (
        rendered_frames !=
        total_frames
    ):

        raise RuntimeError(
            f"Frame count mismatch "
            f"for {scene_id}: "
            f"expected {total_frames}, "
            f"got {rendered_frames}"
        )

    # ========================================================
    # SUCCESS
    # ========================================================

    try:
        page.remove_listener(
            "pageerror",
            _on_page_error,
        )
        page.remove_listener(
            "console",
            _on_console,
        )
    except Exception:
        pass

    print(
        "Frame validation : PASS"
    )

    print(
        f"Frames rendered  : "
        f"{rendered_frames}"
    )

    print(
        f"Output directory : "
        f"{frames_dir}"
    )

    return {
        "scene_id": scene_id,
        "scene_file": str(
            scene_file
        ),
        "duration": duration,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "expected_frames": total_frames,
        "rendered_frames": rendered_frames,
        "frames_dir": str(
            frames_dir
        ),
        "status": "PASS",
    }


# ============================================================
# RENDER ALL SCENES
# ============================================================

async def render_all_scenes(
    scene_files,
    durations,
):
    """
    Render all scenes sequentially.
    """

    ensure_directories()

    # --------------------------------------------------------
    # Validate input.
    # --------------------------------------------------------

    if len(scene_files) != len(
        durations
    ):

        raise ValueError(
            f"Scene/duration mismatch: "
            f"{len(scene_files)} files, "
            f"{len(durations)} durations."
        )

    if not scene_files:

        raise ValueError(
            "No scene files supplied "
            "for rendering."
        )

    # --------------------------------------------------------
    # Header.
    # --------------------------------------------------------

    print(
        "\n========================================"
    )

    print(
        "MULTI-SCENE BROWSER RENDERER"
    )

    print(
        "========================================"
    )

    print(
        f"Total scenes : "
        f"{len(scene_files)}"
    )

    print(
        f"Resolution   : "
        f"{WIDTH}x{HEIGHT}"
    )

    print(
        f"FPS          : "
        f"{FPS}"
    )

    results = []

    # ========================================================
    # PLAYWRIGHT
    # ========================================================

    async with async_playwright() as p:

        # ----------------------------------------------------
        # Launch Chromium.
        # ----------------------------------------------------

        browser = (
            await p.chromium.launch(
                headless=True
            )
        )

        # ----------------------------------------------------
        # Browser context.
        # ----------------------------------------------------

        context = (
            await browser.new_context(
                viewport={
                    "width": WIDTH,
                    "height": HEIGHT,
                },
                device_scale_factor=1,
            )
        )

        # ----------------------------------------------------
        # Single page reused for all scenes.
        # ----------------------------------------------------

        page = (
            await context.new_page()
        )

        try:

            for (
                scene_file,
                duration,
            ) in zip(
                scene_files,
                durations,
            ):

                result = (
                    await render_scene(
                        page,
                        scene_file,
                        duration,
                    )
                )

                results.append(
                    result
                )

        finally:

            await context.close()

            await browser.close()

    # ========================================================
    # REPORT
    # ========================================================

    report = {
        "status": "PASS",
        "width": WIDTH,
        "height": HEIGHT,
        "fps": FPS,
        "total_scenes": len(
            results
        ),
        "scenes": results,
    }

    report_file = (
        REPORTS_DIR /
        "browser_render_report.json"
    )

    report_file.write_text(
        json.dumps(
            report,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # COMPLETE
    # ========================================================

    print(
        "\n========================================"
    )

    print(
        "ALL SCENES RENDERED"
    )

    print(
        "========================================"
    )

    print(
        f"Report: {report_file}"
    )

    return report


# ============================================================
# RENDER FROM VIDEO PLAN
# ============================================================

async def render_from_plan(
    video_plan,
):
    """
    Render scenes according to VideoPlan.

    Required scene fields:

        scene_id
        duration
    """

    if video_plan is None:

        raise ValueError(
            "Video plan is None."
        )

    scenes = sorted(
        video_plan.scenes,
        key=lambda x: x.scene_id,
    )

    if not scenes:

        raise ValueError(
            "Video plan contains no scenes."
        )

    # --------------------------------------------------------
    # Validate scene IDs.
    # --------------------------------------------------------

    scene_ids = [
        scene.scene_id
        for scene in scenes
    ]

    if len(scene_ids) != len(
        set(scene_ids)
    ):

        raise ValueError(
            f"Duplicate scene IDs found: "
            f"{scene_ids}"
        )

    # --------------------------------------------------------
    # Find generated HTML files.
    # --------------------------------------------------------

    scene_files = []

    for scene in scenes:

        path = (
            SCENES_DIR /
            f"scene_{scene.scene_id:02d}.html"
        )

        if not path.exists():

            raise FileNotFoundError(
                f"Generated scene HTML "
                f"not found: {path}"
            )

        scene_files.append(
            path
        )

    # --------------------------------------------------------
    # Get actual plan durations.
    # --------------------------------------------------------

    durations = [
        float(scene.duration)
        for scene in scenes
    ]

    # --------------------------------------------------------
    # Render.
    # --------------------------------------------------------

    return await render_all_scenes(
        scene_files,
        durations,
    )


# ============================================================
# STANDALONE TEST
# ============================================================

async def main():
    """
    Standalone browser renderer test.

    Actual pipeline should use:

        render_from_plan(video_plan)
    """

    scene_files = sorted(
        SCENES_DIR.glob(
            "scene_*.html"
        )
    )

    if not scene_files:

        print(
            f"No generated scenes found "
            f"in {SCENES_DIR}"
        )

        return

    # --------------------------------------------------------
    # Standalone test duration only.
    # --------------------------------------------------------

    durations = [
        5.0
        for _ in scene_files
    ]

    await render_all_scenes(
        scene_files,
        durations,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )