from pathlib import Path

from agents.code_generator import _inject_rendering_contract


# ============================================================
# RESPONSE TEXT EXTRACTOR
# ============================================================

def extract_text_from_response(response):
    """
    Extract text safely from LangChain AIMessage responses.

    Some providers return:

        response.content -> str

    Other providers, especially Gemini, may return:

        response.content -> list[dict | str]
    """

    content = response.content

    # --------------------------------------------------------
    # NORMAL STRING RESPONSE
    # --------------------------------------------------------

    if isinstance(content, str):
        return content.strip()

    # --------------------------------------------------------
    # LIST / STRUCTURED RESPONSE
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    return str(content).strip()


# ============================================================
# CLEAN GENERATED HTML
# ============================================================

def clean_code_output(code):
    """
    Clean accidental Markdown/code-fence text from
    an LLM response.

    Expected final output:

        <!DOCTYPE html>
        <html>
        ...
        </html>
    """

    # --------------------------------------------------------
    # SAFETY
    # --------------------------------------------------------

    if not isinstance(code, str):
        code = str(code)

    code = code.strip()

    # --------------------------------------------------------
    # REMOVE MARKDOWN CODE FENCES
    # --------------------------------------------------------

    if code.lower().startswith("```html"):

        code = code[7:].strip()

    elif code.lower().startswith("```"):

        code = code[3:].strip()

    # --------------------------------------------------------
    # REMOVE CLOSING CODE FENCE
    # --------------------------------------------------------

    if code.endswith("```"):

        code = code[:-3].strip()

    # --------------------------------------------------------
    # REMOVE TEXT BEFORE DOCTYPE
    # --------------------------------------------------------

    doctype_index = code.lower().find(
        "<!doctype html>"
    )

    if doctype_index != -1:

        code = code[doctype_index:]

    else:

        # ----------------------------------------------------
        # FALLBACK: FIND <HTML>
        # ----------------------------------------------------

        html_index = code.lower().find(
            "<html"
        )

        if html_index != -1:

            code = code[html_index:]

    # --------------------------------------------------------
    # REMOVE TEXT AFTER </HTML>
    # --------------------------------------------------------

    html_end_index = code.lower().rfind(
        "</html>"
    )

    if html_end_index != -1:

        code = code[
            :html_end_index + len("</html>")
        ]

    return code.strip()


# ============================================================
# FIX ONE SCENE
# ============================================================

def fix_scene_code(
    scene_file,
    validation_result,
    scene_plan,
    llm=None
):
    """
    Repair one failed HTML scene using the selected LLM.

    The LLM is supplied by main.py, so this function does NOT
    hard-code Gemini, OpenAI, xAI or Ollama.
    """

    scene_file = Path(scene_file)

    # ========================================================
    # CHECK FILE
    # ========================================================

    if not scene_file.exists():

        raise FileNotFoundError(
            f"Scene file does not exist: {scene_file}"
        )

    # ========================================================
    # READ CURRENT CODE
    # ========================================================

    try:

        current_code = scene_file.read_text(
            encoding="utf-8"
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not read scene file: {e}"
        )

    # ========================================================
    # COLLECT VALIDATION ERRORS
    # ========================================================

    errors = validation_result.get(
        "errors",
        []
    )

    warnings = validation_result.get(
        "warnings",
        []
    )

    # ========================================================
    # ERROR TEXT
    # ========================================================

    if errors:

        error_text = "\n".join(
            f"- {error}"
            for error in errors
        )

    else:

        error_text = "No validation errors."

    # ========================================================
    # WARNING TEXT
    # ========================================================

    if warnings:

        warning_text = "\n".join(
            f"- {warning}"
            for warning in warnings
        )

    else:

        warning_text = "No validation warnings."

    # ========================================================
    # SCENE PLAN INFORMATION
    # ========================================================

    try:

        scene_id = scene_plan.scene_id
        duration = scene_plan.duration
        background = scene_plan.background
        visual_type = scene_plan.visual_type
        image_required = scene_plan.image_required
        image_description = scene_plan.image_description
        text = scene_plan.text
        text_position = scene_plan.text_position
        animation = scene_plan.animation
        transition = scene_plan.transition
        effects = scene_plan.effects

    except AttributeError:

        # ----------------------------------------------------
        # FALLBACK IF scene_plan IS A DICTIONARY
        # ----------------------------------------------------

        scene_id = scene_plan.get(
            "scene_id",
            "unknown"
        )

        duration = scene_plan.get(
            "duration",
            "unknown"
        )

        background = scene_plan.get(
            "background",
            ""
        )

        visual_type = scene_plan.get(
            "visual_type",
            ""
        )

        image_required = scene_plan.get(
            "image_required",
            False
        )

        image_description = scene_plan.get(
            "image_description",
            ""
        )

        text = scene_plan.get(
            "text",
            ""
        )

        text_position = scene_plan.get(
            "text_position",
            ""
        )

        animation = scene_plan.get(
            "animation",
            ""
        )

        transition = scene_plan.get(
            "transition",
            ""
        )

        effects = scene_plan.get(
            "effects",
            ""
        )

    # ========================================================
    # BUILD SCENE PLAN TEXT
    # ========================================================

    scene_plan_text = f"""
Scene ID:
{scene_id}

Duration:
{duration} seconds

Background:
{background}

Visual Type:
{visual_type}

Image Required:
{image_required}

Image Description:
{image_description}

Main Text:
{text}

Text Position:
{text_position}

Animation:
{animation}

Transition:
{transition}

Effects:
{effects}
"""

    # ========================================================
    # FIX PROMPT
    # ========================================================

    prompt = f"""
You are an expert HTML5, CSS3 and JavaScript debugging
agent working inside an automated video-generation pipeline.

You are repairing ONE generated HTML video scene.

The scene will be rendered completely offline using:

- Chromium
- Playwright
- FFmpeg

The final video format is:

- 1080 x 1920 pixels
- 9:16 portrait
- 30 FPS


============================================================
SCENE PLAN
============================================================

{scene_plan_text}


============================================================
VALIDATOR ERRORS
============================================================

{error_text}


============================================================
VALIDATOR WARNINGS
============================================================

{warning_text}


============================================================
CURRENT HTML CODE
============================================================

{current_code}


============================================================
TASK
============================================================

Repair the current HTML scene so that it passes the
code validator while preserving the original visual
concept, layout, text, animation and overall design
whenever possible.

Make the smallest necessary changes.

Do NOT redesign the scene unnecessarily.

If the validator error is a browser JavaScript runtime error,
make every DOM lookup null-safe before accessing properties such as
.style, .classList, .textContent, innerHTML or dataset.
window.setVideoTime(time) MUST NEVER throw even when an optional
element is missing. Preserve the visual concept while preventing
uncaught browser exceptions.


============================================================
STRICT OUTPUT REQUIREMENTS
============================================================

1. Return ONLY the complete HTML document.

2. Do NOT write any explanation.

3. Do NOT write anything before the HTML.

4. Do NOT write anything after the HTML.

5. Do NOT use Markdown.

6. Do NOT use Markdown code fences.

7. The response must start with either:

<!DOCTYPE html>

or:

<html

8. The response must end with:

</html>
"""

    # ========================================================
    # CALL SELECTED LLM
    # ========================================================

    print()
    print("========================================")
    print("CODE FIXER")
    print("========================================")

    print(
        f"Scene: {scene_file.name}"
    )

    print(
        "Sending failed scene to selected LLM..."
    )

    if llm is None:
        raise RuntimeError(
            "Code fixer requires the selected LLM instance from main.py."
        )

    try:

        response = llm.invoke(
            prompt
        )

    except Exception as e:

        raise RuntimeError(
            f"Code fixer LLM call failed: {e}"
        )

    # ========================================================
    # EXTRACT RESPONSE
    # ========================================================

    fixed_code = extract_text_from_response(
        response
    )

    # ========================================================
    # CLEAN RESPONSE
    # ========================================================

    fixed_code = clean_code_output(
        fixed_code
    )

    # ========================================================
    # VALIDATE LLM RESPONSE
    # ========================================================

    if not fixed_code.strip():

        raise RuntimeError(
            "Code fixer returned empty HTML."
        )

    if "<html" not in fixed_code.lower():

        raise RuntimeError(
            "Code fixer response does not contain <html>."
        )

    if "<head" not in fixed_code.lower():

        raise RuntimeError(
            "Code fixer response does not contain <head>."
        )

    if "<body" not in fixed_code.lower():

        raise RuntimeError(
            "Code fixer response does not contain <body>."
        )

    if "</html>" not in fixed_code.lower():

        raise RuntimeError(
            "Code fixer response does not contain </html>."
        )

    # ========================================================
    # RE-APPLY SAFE RENDERING CONTRACT
    # ========================================================

    fixed_code = _inject_rendering_contract(fixed_code)

    # ========================================================
    # SAVE FIXED HTML
    # ========================================================

    try:

        scene_file.write_text(
            fixed_code,
            encoding="utf-8"
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not save repaired scene: {e}"
        )

    # ========================================================
    # SUCCESS
    # ========================================================

    print(
        f"Scene repaired: {scene_file}"
    )

    print("========================================")

    return fixed_code


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("========================================")
    print("CODE FIXER")
    print("========================================")

    print(
        "Code fixer module loaded successfully."
    )

    print(
        "Provider-aware implementation: READY"
    )

    print(
        "LLM is supplied by main.py."
    )

    print("========================================")