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