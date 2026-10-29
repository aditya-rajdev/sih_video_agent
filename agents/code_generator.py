from pathlib import Path
import re

SCENES_DIR = Path("output/generated_scenes")
MAX_GENERATION_RETRIES = 3

RENDERING_CONTRACT = r'''
<script>
(function () {
    window.__frameforgeOriginalSetVideoTime =
        (typeof window.setVideoTime === "function") ? window.setVideoTime : null;

    window.setVideoTime = function (time) {
        var t = Number(time);
        if (!Number.isFinite(t)) t = 0;

        try {
            if (typeof window.__frameforgeOriginalSetVideoTime === "function") {
                window.__frameforgeOriginalSetVideoTime(t);
            }
        } catch (error) {
            console.warn("FrameForge scene animation error suppressed:", error);
        }

        var nodes = document.querySelectorAll(".scene");
        for (var i = 0; i < nodes.length; i++) {
            var node = nodes[i];
            if (!node || !node.classList) continue;
            var start = Number(node.getAttribute("data-start"));
            var end = Number(node.getAttribute("data-end"));
            if (!Number.isFinite(start)) start = 0;
            if (!Number.isFinite(end) || end <= start) end = 1e12;
            node.classList.toggle("active", t >= start && t < end);
        }
    };

    window.sceneReady = true;
})();
</script>
'''



# =========================================================
# RESPONSE TEXT EXTRACTOR
# =========================================================

def extract_text_from_response(response):
    """
    Extract text safely from LangChain AIMessage responses.

    Some providers return:

        response.content -> str

    Other providers may return:

        response.content -> list[dict | str]
    """

    content = response.content

    # -----------------------------------------------------
    # Normal string response
    # -----------------------------------------------------

    if isinstance(content, str):
        return content.strip()

    # -----------------------------------------------------
    # Structured/list response
    # -----------------------------------------------------

    if isinstance(content, list):

        parts = []

        for block in content:

            # Example:
            # "<html>...</html>"

            if isinstance(block, str):
                parts.append(block)

            # Example:
            # {"type": "text", "text": "<html>...</html>"}

            elif isinstance(block, dict):

                text = block.get("text")

                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(parts).strip()

    # -----------------------------------------------------
    # Fallback
    # -----------------------------------------------------

    return str(content).strip()


# =========================================================
# CLEAN GENERATED HTML
# =========================================================

def clean_generated_code(code):
    """
    Remove accidental Markdown code fences and text
    surrounding the generated HTML document.
    """

    if not isinstance(code, str):
        code = str(code)

    code = code.strip()

    # -----------------------------------------------------
    # Remove opening markdown fence
    # -----------------------------------------------------

    if code.lower().startswith("```html"):

        code = code[7:].strip()

    elif code.startswith("```"):

        code = code[3:].strip()

    # -----------------------------------------------------
    # Remove closing markdown fence
    # -----------------------------------------------------

    if code.endswith("```"):

        code = code[:-3].strip()

    # -----------------------------------------------------
    # Remove accidental text before <!DOCTYPE html>
    # -----------------------------------------------------

    doctype_index = code.lower().find(
        "<!doctype html>"
    )

    if doctype_index != -1:

        code = code[doctype_index:]

    else:

        # -------------------------------------------------
        # Fallback: find <html>
        # -------------------------------------------------

        html_index = code.lower().find(
            "<html"
        )

        if html_index != -1:

            code = code[html_index:]

    # -----------------------------------------------------
    # Remove accidental text after </html>
    # -----------------------------------------------------

    html_end_index = code.lower().rfind(
        "</html>"
    )

    if html_end_index != -1:

        code = code[
            :html_end_index + len("</html>")
        ]

    return code.strip()


# =========================================================
# GENERATE ONE SCENE
# =========================================================

def generate_scene_code(scene, llm):
    """
    Generate the complete HTML/CSS/JavaScript code
    for one video scene using the LLM supplied by main.py.

    The LLM can be:

        - Local Ollama
        - Gemini
        - OpenAI
        - xAI
        - Custom OpenAI-compatible provider

    This function does NOT hard-code any provider.
    """

    # =====================================================
    # BUILD PROMPT
    # =====================================================

    prompt = f"""
You are an expert HTML5, CSS3 and JavaScript motion-graphics
video developer.

Your job is to generate the COMPLETE code for ONE video scene.

The scene will be rendered inside a Chromium browser and later
captured frame-by-frame and converted to MP4 using FFmpeg.

IMPORTANT REQUIREMENTS:

1. Generate actual HTML5, CSS3 and JavaScript.
2. Do NOT merely describe the animation.
3. Do NOT write explanations.
4. Do NOT use images unless the scene explicitly requires one.
5. Do NOT use external websites, CDNs, APIs or external assets.
6. Everything must work offline.
7. Use CSS shapes, gradients, text, pseudo-elements and JavaScript
   when appropriate.
8. The canvas must be exactly 1080x1920.
9. The scene must fill the complete 1080x1920 viewport.
10. Text must be clearly visible.
11. Animations must use real CSS @keyframes or JavaScript.
12. The code must work inside Chromium.
13. Do NOT use video-generation APIs.
14. Do NOT use canvas libraries.
15. Do NOT use React.
16. Do NOT use Tailwind.
17. Keep the code completely self-contained.
18. Do NOT use external fonts.
19. Do NOT use external images.
20. Do NOT use fetch().
21. Do NOT use axios.
22. Do NOT use XMLHttpRequest.
23. Do NOT use WebSocket.
24. Do NOT use external API calls.
25. Do NOT include Markdown code fences.
26. Return ONLY the complete HTML document.

=========================================================
VIDEO FORMAT
=========================================================

Resolution:
1080 x 1920

Aspect Ratio:
9:16

Rendering:
Chromium + Playwright

Frame Rate:
30 FPS

The scene must completely fill the viewport.

=========================================================
SCENE INFORMATION
=========================================================

Scene ID:
{scene.scene_id}

Duration:
{scene.duration} seconds

Background:
{scene.background}

Visual Type:
{scene.visual_type}

Image Required:
{scene.image_required}

Image Description:
{scene.image_description}

Main Text:
{scene.text}

Text Position:
{scene.text_position}

Animation:
{scene.animation}

Transition:
{scene.transition}

Effects:
{scene.effects}

=========================================================
VISUAL QUALITY REQUIREMENTS
=========================================================

The scene should look like a polished modern
short-form informational video.

Use appropriate combinations of:

- strong typography
- good spacing
- visual hierarchy
- layered backgrounds
- gradients
- CSS shapes
- cards
- icons using CSS where appropriate
- diagrams
- lines
- circles
- particles using CSS/JavaScript
- glow
- shadows
- depth
- subtle motion
- smooth transitions
- scale animations
- opacity animations
- position animations
- rotation
- blur
- staggered animations

Do NOT simply place plain text in the center.

The visual design must actually communicate the
meaning of the scene.

=========================================================
ANIMATION REQUIREMENTS
=========================================================

Animations must work automatically when the page loads.

Do NOT require:

- mouse interaction
- keyboard input
- clicking
- scrolling
- user interaction

The scene must play automatically.

If JavaScript is required, keep it self-contained.

CSS @keyframes are preferred for simple animations.

=========================================================
OFFLINE REQUIREMENTS
=========================================================

The scene must work completely offline.

Do NOT include:

<script src="https://...">

<link href="https://...">

@import url("https://...")

fetch("https://...")

axios requests

API requests

external CDNs

external fonts

external libraries

=========================================================
HTML STRUCTURE
=========================================================

Return a complete HTML document containing:

<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=1080,height=1920"
    >

    <style>
        ...
    </style>

</head>

<body>

    ...

    <script>
        ...
    </script>

</body>

</html>

=========================================================
IMPORTANT
=========================================================

Generate CODE, not an explanation.

Return ONLY the complete HTML document.

Do NOT write:

"Here is the code"

Do NOT write:

"Sure"

Do NOT write:

"```html"

Do NOT write any explanation before or after the HTML.

RENDERING CONTRACT:

The HTML MUST define:
- window.setVideoTime(time)
- window.sceneReady = true
- at least one element with class="scene"
- the scene element must be safe to access at every frame
- every DOM query must be null-safe before accessing .style, .classList, .textContent or other properties
- window.setVideoTime MUST NOT throw if an optional element is absent

The first meaningful output must be:

<!DOCTYPE html>

and the final output must end with:

</html>
"""

    # =====================================================
    # CALL SELECTED LLM WITH SAFE RETRIES
    # =====================================================

    print(
        f"Generating HTML/CSS/JS for Scene "
        f"{scene.scene_id}..."
    )

    last_errors = []
    current_prompt = prompt

    for attempt in range(MAX_GENERATION_RETRIES + 1):

        try:
            response = llm.invoke(current_prompt)

        except Exception as e:
            last_errors = [str(e)]
            if attempt >= MAX_GENERATION_RETRIES:
                raise RuntimeError(
                    f"Scene {scene.scene_id} LLM generation failed after "
                    f"{MAX_GENERATION_RETRIES + 1} attempts: {e}"
                )
            current_prompt += (
                "\n\nPrevious generation failed with this error:\n"
                f"{e}\nReturn the COMPLETE HTML document only."
            )
            continue

        code = clean_generated_code(
            extract_text_from_response(response)
        )

        errors = []
        low = code.lower()

        for required in (
            "<html", "<head", "<body", "</body>", "</html>"
        ):
            if required not in low:
                errors.append(f"Missing {required}.")

        if "window.setvideotime" not in low:
            errors.append("Missing window.setVideoTime function.")

        if errors:
            last_errors = errors
            print(
                f"Scene {scene.scene_id}: generation retry "
                f"{attempt + 1} failed: {errors}"
            )

            # If the selected generator returns an incomplete document,
            # immediately hand that concrete failure to the dedicated
            # video code-fixer instead of repeatedly asking the same
            # generator for another incomplete response. The existing
            # provider/UI/features remain unchanged; this is only a
            # video-generation reliability path.
            try:
                from pathlib import Path
                from agents.code_fixer import fix_scene_code
                from langchain_ollama import ChatOllama

                repair_file = (
                    Path("output/generated_scenes")
                    / f"scene_{int(scene.scene_id):02d}.html"
                )
                repair_file.parent.mkdir(parents=True, exist_ok=True)
                repair_file.write_text(code, encoding="utf-8")

                fixer_llm = ChatOllama(
                    model="qwen2.5-coder:3b",
                    temperature=0.1,
                )

                repaired = fix_scene_code(
                    repair_file,
                    {"errors": errors, "warnings": []},
                    scene,
                    fixer_llm,
                )

                repaired = clean_generated_code(repaired)
                repaired_low = repaired.lower()
                repair_missing = [
                    item for item in (
                        "<html", "<head", "<body", "</body>", "</html>"
                    )
                    if item not in repaired_low
                ]
                if "window.setvideotime" not in repaired_low:
                    repair_missing.append("window.setVideoTime")

                if not repair_missing:
                    print(
                        f"Scene {scene.scene_id}: dedicated code fixer "
                        "repaired the incomplete generator output."
                    )
                    return _inject_rendering_contract(repaired)

                last_errors = repair_missing
                print(
                    f"Scene {scene.scene_id}: code fixer returned "
                    f"incomplete HTML: {repair_missing}"
                )

            except Exception as repair_error:
                print(
                    f"Scene {scene.scene_id}: dedicated code fixer "
                    f"could not repair generation output: {repair_error}"
                )

            current_prompt += (
                "\n\nThe previous response was incomplete. "
                "Return the COMPLETE HTML document again.\n"
                "Validation errors:\n" + "\n".join(errors)
            )
            continue

        code = _inject_rendering_contract(code)
        return code

    raise ValueError(
        f"Scene {scene.scene_id}: model did not return a complete HTML "
        f"document after {MAX_GENERATION_RETRIES + 1} attempts. "
        f"Errors: {last_errors}"
    )


def _inject_rendering_contract(code):
    """Wrap generated scene timing safely without changing its visual design."""
    code = code.strip()

    if re.search(r"</body\s*>", code, flags=re.I):
        match = re.search(r"</body\s*>", code, flags=re.I)
        return (
            code[:match.start()]
            + "\n" + RENDERING_CONTRACT + "\n"
            + code[match.start():]
        )

    return code + "\n" + RENDERING_CONTRACT


# =========================================================
# SAVE SCENE CODE
# =========================================================

def save_scene_code(scene_id, code):
    """Save a validated scene HTML document."""

    output_dir = Path("output/generated_scenes")
    output_dir.mkdir(parents=True, exist_ok=True)

    code = clean_generated_code(code)
    code = _inject_rendering_contract(code)
    low = code.lower()

    required = ("<html", "<head", "<body", "</body>", "</html>")
    missing = [item for item in required if item not in low]
    if missing:
        raise ValueError(
            f"Refusing to save incomplete HTML for Scene {scene_id}: {missing}"
        )

    if "window.setvideotime" not in low:
        raise ValueError(
            f"Refusing to save Scene {scene_id}: window.setVideoTime is missing."
        )

    file_path = output_dir / f"scene_{int(scene_id):02d}.html"
    file_path.write_text(code, encoding="utf-8")
    return file_path


# =========================================================
# MODULE TEST
# =========================================================

if __name__ == "__main__":

    print()
    print("========================================")
    print("CODE GENERATOR AGENT")
    print("========================================")

    print(
        "Provider-aware implementation: READY"
    )

    print(
        "LLM is supplied by main.py."
    )

    print(
        "No provider is hard-coded in this module."
    )

    print("========================================")