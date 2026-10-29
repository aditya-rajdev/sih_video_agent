import json
import time
from pathlib import Path


class PipelineTimer:

    def __init__(self):
        self.pipeline_start = None
        self.pipeline_end = None

        self.stages = {}

        self.output_file = Path("output/pipeline_timing.json")

    # ========================================================
    # PIPELINE START
    # ========================================================

    def start_pipeline(self):

        self.pipeline_start = time.perf_counter()

        print("\nPipeline timer started.")

    # ========================================================
    # STAGE START
    # ========================================================

    def start_stage(self, stage_name):

        self.stages[stage_name] = {
            "start": time.perf_counter(),
            "end": None,
            "duration_seconds": None,
            "status": "running"
        }

        print(f"\n[START] {stage_name}")

    # ========================================================
    # STAGE END
    # ========================================================

    def end_stage(self, stage_name, success=True):

        if stage_name not in self.stages:
            return

        end_time = time.perf_counter()

        stage = self.stages[stage_name]

        stage["end"] = end_time

        stage["duration_seconds"] = round(
            end_time - stage["start"],
            3
        )

        stage["status"] = (
            "success"
            if success
            else "failed"
        )

        print(
            f"[END] {stage_name} "
            f"({stage['duration_seconds']}s)"
        )

    # ========================================================
    # PIPELINE END
    # ========================================================

    def end_pipeline(self, success=True):

        self.pipeline_end = time.perf_counter()

        if self.pipeline_start is None:
            return

        total_duration = round(
            self.pipeline_end - self.pipeline_start,
            3
        )

        # ====================================================
        # BUILD RESULT
        # ====================================================

        result = {
            "pipeline": {
                "status": (
                    "success"
                    if success
                    else "failed"
                ),
                "total_duration_seconds": total_duration
            },
            "stages": {}
        }

        # ====================================================
        # CLEAN STAGE DATA
        # ====================================================

        for stage_name, stage in self.stages.items():

            result["stages"][stage_name] = {
                "duration_seconds": stage[
                    "duration_seconds"
                ],
                "status": stage["status"]
            }

        # ====================================================
        # SAVE JSON
        # ====================================================

        self.output_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(
            self.output_file,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                result,
                file,
                indent=4
            )

        # ====================================================
        # PRINT RESULT
        # ====================================================

        print("\n========================================")
        print("PIPELINE TIMING")
        print("========================================")

        print(
            f"\nTotal pipeline time: "
            f"{total_duration} seconds"
        )

        for stage_name, stage in result["stages"].items():

            duration = stage["duration_seconds"]

            status = stage["status"]

            print(
                f"{stage_name}: "
                f"{duration}s "
                f"[{status}]"
            )

        print("\nTiming saved to:")
        print(self.output_file)

        print("========================================\n")