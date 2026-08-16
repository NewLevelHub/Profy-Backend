import uuid
from typing import Literal, Union, Optional
from pydantic import BaseModel
from app.models.assessment import AssessmentGoal
from app.schemas.gap import GapAnalysisResponse


class ScenarioAData(BaseModel):
    top_spheres: list[str]
    roadmap_summary: str
    roadmap_id: Optional[uuid.UUID] = None


class BridgeScenario(BaseModel):
    what_works: list[str]
    what_to_check: list[str]


class ScenarioBData(BaseModel):
    top_directions: list[str] = []


class ScenarioCData(BaseModel):
    selected_program_id: Optional[uuid.UUID] = None
    selected_program_name: Optional[str] = None
    selected_university_name: Optional[str] = None
    gap_analysis: Optional[GapAnalysisResponse] = None
    admission_roadmap_ref: Optional[uuid.UUID] = None


class GoalAlignmentBlock(BaseModel):
    target_selected: bool
    target_name: Optional[str] = None
    alignment: Literal["match", "partial", "bridge", "not_applicable"]
    match_explanation: Optional[str] = None
    bridge_scenario: Optional[BridgeScenario] = None
    adjacent_directions: list[str] = []


class GoalOverlayResponse(BaseModel):
    assessment_id: uuid.UUID
    primary_goal: AssessmentGoal
    effective_goal: Optional[AssessmentGoal] = None  # None if needs_goal_selection is True
    scenario: Optional[Literal["A", "B", "C"]] = None  # None if needs_goal_selection is True
    secondary_goals: list[AssessmentGoal] = []
    redirected: bool = False
    admission_info_note: Optional[str] = None
    needs_goal_selection: bool = False
    suggested_goals: list[AssessmentGoal] = []
    alignment_block: Optional[GoalAlignmentBlock] = None
    overlay_data: Optional[Union[ScenarioAData, ScenarioBData, ScenarioCData]] = None

    model_config = {"from_attributes": True}
