from pathlib import Path


def asset_verifier(state):

    image_requirements = state["image_requirements"]

    images_folder = Path("assets/images")

    print("\n\n========================================")
    print("ASSET VERIFICATION")
    print("========================================")

    # ========================================================
    # NO IMAGES REQUIRED
    # ========================================================

    if not image_requirements.images:

        print("\nNo external images required.")

        print("\n========================================")
        print("ALL REQUIRED ASSETS FOUND")
        print("========================================")

        print("\nVideo rendering can continue.")

        return {
            "asset_verification": {
                "passed": True,
                "found_files": [],
                "missing_files": []
            }
        }

    # ========================================================
    # IMAGE FOLDER CHECK
    # ========================================================

    if not images_folder.exists():

        print("\n❌ assets/images folder does not exist.")

        missing_files = [
            image.file_name
            for image in image_requirements.images
            if image.required
        ]

        return {
            "asset_verification": {
                "passed": False,
                "found_files": [],
                "missing_files": missing_files
            }
        }

    # ========================================================
    # CHECK REQUIRED IMAGES
    # ========================================================

    found_files = []
    missing_files = []

    for image in image_requirements.images:

        if not image.required:
            continue

        file_path = images_folder / image.file_name

        if file_path.exists():

            print(
                f"\n{image.file_name}   ✅ FOUND"
            )

            found_files.append(
                image.file_name
            )

        else:

            print(
                f"\n{image.file_name}   ❌ MISSING"
            )

            missing_files.append(
                image.file_name
            )

    # ========================================================
    # FINAL RESULT
    # ========================================================

    if missing_files:

        print("\n========================================")
        print("ASSET VERIFICATION FAILED")
        print("========================================")

        print("\nMissing files:")

        for file_name in missing_files:

            print(
                f"❌ {file_name}"
            )

        print(
            "\nVideo rendering must STOP."
        )

        passed = False

    else:

        print("\n========================================")
        print("ALL REQUIRED ASSETS FOUND")
        print("========================================")

        print(
            "\nVideo rendering can continue."
        )

        passed = True

    return {

        "asset_verification": {

            "passed": passed,

            "found_files": found_files,

            "missing_files": missing_files

        }

    }