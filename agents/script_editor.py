from __future__ import annotations

"""
Script Editor Agent

Purpose:
    Edit an existing VideoScript using a natural-language user instruction.

Important:
    - This module does NOT generate video.
    - This module does NOT modify scene HTML.
    - The edited script remains the source of truth for later Scene Planning.
    - Scene IDs and total duration are protected by deterministic validation.
"""

from typing import List
from pydantic import BaseModel


# ============================================================
# SCRIPT MODELS
# ============================================================

class Dialogue(BaseModel):
    character: str
    line: str


class ScriptScene(BaseModel):
    scene_id: int
    duration: int
    narration: str
    dialogues: List[Dialogue]
    visual_direction: str
    on_screen_text: str


class VideoScript(BaseModel):
    title: str
    hook: str
    tone: str
    audience: str
    total_duration: int
    scenes: List[ScriptScene]
    cta: str


# ============================================================
# RESPONSE EXTRACTION
# ============================================================

def extract_text_from_response(response) -> str:
    """Extract text safely from LangChain-style LLM responses."""

    content = response.content

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for block in content:
            if isinstance(block, str):
                parts.append(block)

            elif isinstance(block, dict):
                text = block.get("text")

                if isinstance(text, str):
                    parts.append(text)

        return "\n".join(parts).strip()

    return str(content).strip()


# ============================================================
# SCRIPT VALIDATION
# ============================================================

def validate_script(
    script: VideoScript,
    expected_duration: int,
    original_script: VideoScript | None = None,
) -> None:
    """
    Deterministically validate an edited script.

    Rules:
        1. Script must contain scenes.
        2. Total duration must remain exact.
        3. Scene duration sum must remain exact.
        4. Scene IDs must remain unique and sequential.
        5. Scene count may change only if the user explicitly requested
           adding/removing/restructuring scenes. The LLM prompt controls this;
           this validator does not silently reject legitimate restructuring.
    """

    if expected_duration <= 0:
        raise ValueError("Expected duration must be greater than 0.")

    if not script.scenes:
        raise ValueError("Edited script contains no scenes.")

    if script.total_duration != expected_duration:
        raise ValueError(
            f"Edited script duration mismatch: expected "
            f"{expected_duration}s, got {script.total_duration}s."
        )

    scene_sum = sum(scene.duration for scene in script.scenes)

    if scene_sum != expected_duration:
        raise ValueError(
            f"Edited scene durations must sum to exactly "
            f"{expected_duration}s, got {scene_sum}s."
        )

    if any(scene.duration <= 0 for scene in script.scenes):
        raise ValueError("Every scene duration must be greater than 0.")

    scene_ids = [scene.scene_id for scene in script.scenes]

    if len(scene_ids) != len(set(scene_ids)):
        raise ValueError("Scene IDs must be unique.")

    expected_ids = list(range(1, len(scene_ids) + 1))

    if sorted(scene_ids) != expected_ids:
        raise ValueError(
            f"Scene IDs must be sequential starting at 1. "
            f"Got: {scene_ids}"
        )

    for scene in script.scenes:
        if not scene.narration.strip() and not scene.dialogues:
            raise ValueError(
                f"Scene {scene.scene_id} has neither narration nor dialogue."
            )

        for dialogue in scene.dialogues:
            if not dialogue.character.strip():
                raise ValueError(
                    f"Scene {scene.scene_id} contains a dialogue "
                    "with an empty character name."
                )

            if not dialogue.line.strip():
                raise ValueError(
                    f"Scene {scene.scene_id} contains an empty dialogue line."
                )


# ============================================================
# LLM EDITOR
# ============================================================

def edit_video_script(
    script: VideoScript,
    user_instruction: str,
    llm,
) -> VideoScript:
    """
    Edit a VideoScript according to a natural-language instruction.

    Example instructions:
        "Make the hook stronger."
        "Add a scientist dialogue to scene 2."
        "Make scene 3 easier to understand."
        "Remove unnecessary repetition."
        "Change the tone to conversational."
    """

    if not user_instruction or not user_instruction.strip():
        raise ValueError("Edit instruction cannot be empty.")

    expected_duration = script.total_duration

    prompt = f"""
You are a professional script editor for short-form informational videos.

You are editing an EXISTING script.

The user wants this change:

{user_instruction}

CURRENT SCRIPT:

{script.model_dump_json(indent=2)}

IMPORTANT RULES:

1. Return a complete VideoScript.
2. Do NOT return explanations outside the structured output.
3. Preserve the requested total video duration exactly:
   {expected_duration} seconds.
4. The sum of all scene durations MUST equal exactly
   {expected_duration} seconds.
5. Scene IDs must remain sequential starting from 1.
6. Do not change scene duration unless the user's instruction
   explicitly requires a timing change.
7. If timing is changed, redistribute durations while keeping the
   total exactly {expected_duration} seconds.
8. Do not add filler just to increase duration.
9. Do not remove important information unless the user asks for it.
10. Preserve the original topic and factual meaning unless the user
    explicitly asks to change the content.
11. Characters are optional.
12. Add, remove, or modify dialogue only when requested or when
    necessary to satisfy the user's editing instruction.
13. Keep dialogue natural and concise.
14. Do not duplicate dialogue and narration unnecessarily.
15. Keep on-screen text short and suitable for a vertical video.
16. Keep visual_direction focused on what should be visually shown.
17. The script is the source of truth for the later Scene Planner.
18. Do not write HTML, CSS, JavaScript, or video-generation code.

EDITING PRIORITY:

First satisfy the user's explicit instruction.
Then preserve the existing script structure and meaning as much as
possible.
Finally validate the exact duration constraint.

Return only the complete structured VideoScript.
"""

    edited = llm.with_structured_output(VideoScript).invoke(prompt)

    validate_script(
        edited,
        expected_duration=expected_duration,
        original_script=script,
    )

    return edited


# ============================================================
# SCRIPT DIFF / SUMMARY
# ============================================================

def summarize_changes(
    old_script: VideoScript,
    new_script: VideoScript,
) -> str:
    """Create a simple deterministic summary of major script changes."""

    changes = []

    if old_script.title != new_script.title:
        changes.append("Title changed.")

    if old_script.hook != new_script.hook:
        changes.append("Hook changed.")

    if old_script.tone != new_script.tone:
        changes.append("Tone changed.")

    if old_script.audience != new_script.audience:
        changes.append("Audience changed.")

    if len(old_script.scenes) != len(new_script.scenes):
        changes.append(
            f"Scene count changed: "
            f"{len(old_script.scenes)} → {len(new_script.scenes)}."
        )

    old_by_id = {scene.scene_id: scene for scene in old_script.scenes}
    new_by_id = {scene.scene_id: scene for scene in new_script.scenes}

    for scene_id in sorted(set(old_by_id) | set(new_by_id)):
        old_scene = old_by_id.get(scene_id)
        new_scene = new_by_id.get(scene_id)

        if old_scene is None:
            changes.append(f"Scene {scene_id} added.")
            continue

        if new_scene is None:
            changes.append(f"Scene {scene_id} removed.")
            continue

        if old_scene.duration != new_scene.duration:
            changes.append(
                f"Scene {scene_id} duration changed: "
                f"{old_scene.duration}s → {new_scene.duration}s."
            )

        if old_scene.narration != new_scene.narration:
            changes.append(f"Scene {scene_id} narration changed.")

        if old_scene.dialogues != new_scene.dialogues:
            changes.append(f"Scene {scene_id} dialogue changed.")

        if old_scene.visual_direction != new_scene.visual_direction:
            changes.append(f"Scene {scene_id} visual direction changed.")

        if old_scene.on_screen_text != new_scene.on_screen_text:
            changes.append(f"Scene {scene_id} on-screen text changed.")

    if old_script.cta != new_script.cta:
        changes.append("CTA changed.")

    if not changes:
        return "No changes detected."

    return "\n".join(f"- {change}" for change in changes)


# ============================================================
# SAVE SCRIPT
# ============================================================

def save_edited_script(
    script: VideoScript,
    output_dir: str = "output/scripts",
):
    """Save the latest edited script as JSON and TXT."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / "edited_script.json"
    txt_path = directory / "edited_script.txt"

    json_path.write_text(
        script.model_dump_json(indent=2),
        encoding="utf-8",
    )

    lines = [
        f"TITLE: {script.title}",
        f"HOOK: {script.hook}",
        f"TONE: {script.tone}",
        f"AUDIENCE: {script.audience}",
        f"DURATION: {script.total_duration}s",
        "",
    ]

    for scene in script.scenes:
        lines.append(
            f"SCENE {scene.scene_id} — {scene.duration}s"
        )
        lines.append(
            f"NARRATION: {scene.narration}"
        )

        if scene.dialogues:
            lines.append("DIALOGUE:")

            for dialogue in scene.dialogues:
                lines.append(
                    f"{dialogue.character}: {dialogue.line}"
                )

        lines.append(
            f"VISUAL DIRECTION: {scene.visual_direction}"
        )
        lines.append(
            f"ON-SCREEN TEXT: {scene.on_screen_text}"
        )
        lines.append("")

    lines.append(f"CTA: {script.cta}")

    txt_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return json_path, txt_path


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":
    demo_script = VideoScript(
        title="Demo",
        hook="This is a demo hook.",
        tone="educational",
        audience="general audience",
        total_duration=10,
        scenes=[
            ScriptScene(
                scene_id=1,
                duration=5,
                narration="This is the first scene.",
                dialogues=[],
                visual_direction="Show a clean opening graphic.",
                on_screen_text="FIRST SCENE",
            ),
            ScriptScene(
                scene_id=2,
                duration=5,
                narration="This is the second scene.",
                dialogues=[
                    Dialogue(
                        character="Scientist",
                        line="Here is the key idea."
                    )
                ],
                visual_direction="Show a simple explanatory diagram.",
                on_screen_text="KEY IDEA",
            ),
        ],
        cta="Learn more.",
    )

    validate_script(
        demo_script,
        expected_duration=10,
    )

    print("SCRIPT EDITOR")
    print("Script editor module loaded successfully.")
    print("Validation: PASS")
    print("LLM editor: READY")
    print("Dialogue support: READY")
    print("Duration protection: READY")
    print("Provider-aware: LLM supplied by caller.")
