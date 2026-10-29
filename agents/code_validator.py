from pathlib import Path
from html.parser import HTMLParser
import re


# ============================================================
# CONFIGURATION
# ============================================================

GENERATED_SCENES_DIR = Path("output/generated_scenes")


# ============================================================
# HTML STRUCTURE PARSER
# ============================================================

class HTMLStructureParser(HTMLParser):
    def __init__(self):
        super().__init__()

        self.has_html = False
        self.has_head = False
        self.has_body = False

        self.tags = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        self.tags.append(tag)

        if tag == "html":
            self.has_html = True

        elif tag == "head":
            self.has_head = True

        elif tag == "body":
            self.has_body = True


# ============================================================
# VALIDATE ONE SCENE
# ============================================================

def validate_scene_file(scene_file):
    """
    Validate a single generated HTML scene.

    Returns:
        {
            "passed": bool,
            "errors": list,
            "warnings": list,
            "file": str
        }
    """

    scene_file = Path(scene_file)

    errors = []
    warnings = []

    # --------------------------------------------------------
    # FILE EXISTENCE
    # --------------------------------------------------------

    if not scene_file.exists():
        errors.append(
            f"File does not exist: {scene_file}"
        )

        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
            "file": str(scene_file),
        }

    # --------------------------------------------------------
    # READ FILE
    # --------------------------------------------------------

    try:
        code = scene_file.read_text(
            encoding="utf-8"
        )

    except Exception as e:
        errors.append(
            f"Could not read file: {e}"
        )

        return {
            "passed": False,
            "errors": errors,
            "warnings": warnings,
            "file": str(scene_file),
        }

    # --------------------------------------------------------
    # EMPTY FILE
    # --------------------------------------------------------

    if not code.strip():
        errors.append(
            "HTML file is empty."
        )

    # --------------------------------------------------------
    # MARKDOWN CODE FENCES
    # --------------------------------------------------------

    code_lower = code.lower()

    if "```html" in code_lower:
        errors.append(
            "Markdown code fence ```html detected."
        )

    elif "```" in code:
        errors.append(
            "Markdown code fences detected."
        )

    # --------------------------------------------------------
    # BASIC HTML STRUCTURE
    # --------------------------------------------------------

    parser = HTMLStructureParser()

    try:
        parser.feed(code)

    except Exception as e:
        errors.append(
            f"HTML parser error: {e}"
        )

    # HTML
    if not parser.has_html:
        errors.append(
            "Missing <html> element."
        )

    # HEAD
    if not parser.has_head:
        warnings.append(
            "Missing <head> element."
        )

    # BODY
    if not parser.has_body:
        errors.append(
            "Missing <body> element."
        )

    # --------------------------------------------------------
    # CSS
    # --------------------------------------------------------

    if "<style" not in code_lower:
        warnings.append(
            "No <style> block found."
        )

    # --------------------------------------------------------
    # JAVASCRIPT
    # --------------------------------------------------------

    if "<script" not in code_lower:
        warnings.append(
            "No <script> block found."
        )

    # --------------------------------------------------------
    # VIEWPORT / VIDEO DIMENSIONS
    # --------------------------------------------------------

    if "1080px" not in code:
        warnings.append(
            "1080px dimension not detected."
        )

    if "1920px" not in code:
        warnings.append(
            "1920px dimension not detected."
        )

    # --------------------------------------------------------
    # EXTERNAL RESOURCES
    # --------------------------------------------------------

    external_patterns = [

        # External script
        r'<script[^>]+src\s*=\s*["\']https?://',

        # External stylesheet
        r'<link[^>]+href\s*=\s*["\']https?://',

        # CSS background/image URL
        r'url\s*\(\s*["\']?https?://',

        # External CSS import
        r'@import\s+["\']https?://',
    ]

    external_resource_found = False

    for pattern in external_patterns:

        if re.search(
            pattern,
            code,
            re.IGNORECASE
        ):
            external_resource_found = True
            break

    if external_resource_found:
        errors.append(
            "External URL/resource detected."
        )

    # --------------------------------------------------------
    # VIDEO GENERATION API / SERVICE
    # --------------------------------------------------------

    forbidden_terms = [

        "runway",
        "pika",
        "kling",
        "sora",

        "video generation api",

        "text-to-video",

        "text to video",
    ]

    video_generation_found = False

    for term in forbidden_terms:

        if term in code_lower:

            video_generation_found = True

            errors.append(
                "Forbidden video-generation reference "
                f"detected: {term}"
            )

            break

    # --------------------------------------------------------
    # BASIC NETWORK / EXTERNAL JAVASCRIPT SAFETY
    # --------------------------------------------------------

    suspicious_patterns = [

        # fetch(...)
        r'\bfetch\s*\(',

        # axios.get(...)
        # axios.post(...)
        # axios(...)
        r'\baxios\s*\.',

        r'\baxios\s*\(',

        # XMLHttpRequest
        r'\bXMLHttpRequest\b',

        # WebSocket(...)
        r'\bWebSocket\s*\(',
    ]

    network_request_found = False

    for pattern in suspicious_patterns:

        if re.search(
            pattern,
            code,
            re.IGNORECASE
        ):
            network_request_found = True
            break

    if network_request_found:
        errors.append(
            "External/network JavaScript request detected."
        )

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    passed = len(errors) == 0

    return {
        "passed": passed,
        "errors": errors,
        "warnings": warnings,
        "file": str(scene_file),
    }


# ============================================================
# VALIDATE ALL SCENES
# ============================================================

def validate_all_scenes(scene_files=None):
    """
    Validate all generated scene HTML files.

    If scene_files is None:
        automatically searches output/generated_scenes/
    """

    if scene_files is None:

        scene_files = sorted(
            GENERATED_SCENES_DIR.glob(
                "scene_*.html"
            )
        )

    scene_files = [
        Path(file)
        for file in scene_files
    ]

    print()
    print("========================================")
    print("CODE VALIDATOR")
    print("========================================")

    # --------------------------------------------------------
    # NO SCENES
    # --------------------------------------------------------

    if not scene_files:

        print(
            "❌ No generated scene files found."
        )

        return {
            "passed": False,
            "errors": [
                "No generated scene files found."
            ],
            "warnings": [],
            "scenes": [],
        }

    # --------------------------------------------------------
    # VALIDATE EACH SCENE
    # --------------------------------------------------------

    results = []

    overall_passed = True

    for scene_file in scene_files:

        print()
        print(
            f"Validating: {scene_file.name}"
        )

        result = validate_scene_file(
            scene_file
        )

        results.append(result)

        # ----------------------------------------------------
        # PASS
        # ----------------------------------------------------

        if result["passed"]:

            print(
                f"✅ {scene_file.name} PASS"
            )

        # ----------------------------------------------------
        # FAIL
        # ----------------------------------------------------

        else:

            overall_passed = False

            print(
                f"❌ {scene_file.name} FAIL"
            )

            for error in result["errors"]:

                print(
                    f"   ERROR: {error}"
                )

        # ----------------------------------------------------
        # WARNINGS
        # ----------------------------------------------------

        for warning in result["warnings"]:

            print(
                f"   WARNING: {warning}"
            )

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print()
    print("========================================")

    if overall_passed:

        print(
            "✅ CODE VALIDATION PASSED"
        )

    else:

        print(
            "❌ CODE VALIDATION FAILED"
        )

    print("========================================")

    # --------------------------------------------------------
    # RETURN RESULT
    # --------------------------------------------------------

    return {
        "passed": overall_passed,

        "errors": [
            {
                "file": result["file"],
                "errors": result["errors"],
            }

            for result in results

            if result["errors"]
        ],

        "warnings": [
            {
                "file": result["file"],
                "warnings": result["warnings"],
            }

            for result in results

            if result["warnings"]
        ],

        "scenes": results,
    }


# ============================================================
# SINGLE FILE TEST / DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    result = validate_all_scenes()

    print()
    print("Result:")

    print(
        "PASS"
        if result["passed"]
        else
        "FAIL"
    )