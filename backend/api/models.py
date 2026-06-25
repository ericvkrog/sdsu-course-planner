from pydantic import BaseModel, Field
from typing import Optional


class CourseOut(BaseModel):
    course_code: str
    title: str
    units: int
    department: str
    description: Optional[str]
    grading_method: Optional[str]
    offered_fall: bool
    offered_spring: bool
    max_credits: Optional[int]
    notes: Optional[str]
    role: Optional[str] = None   # requirement | elective | ge | grad | free (slot classification)
    fills: Optional[str] = None  # the slot this course occupies (e.g. "GE 1A") if it replaced a placeholder


class PrereqOut(BaseModel):
    prereq_code: Optional[str]
    prereq_type: str
    min_standing: Optional[str]
    prereq_group: Optional[str] = None   # OR-group key; rows sharing it are alternatives


class CourseDetailOut(CourseOut):
    prerequisites: list[PrereqOut]


class GraphNode(BaseModel):
    id: str
    label: str
    units: int


class GraphEdge(BaseModel):
    source: str
    target: str


class PrereqGraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class SemesterOut(BaseModel):
    semester: str        # "Fall" or "Spring"
    year: int
    courses: list[CourseOut]
    total_units: int


class PlanConflict(BaseModel):
    course_code: str
    reason: str
    severity: str = "error"   # "error" = academically invalid; "warning" = soft (e.g. over unit target)


class PlanResponse(BaseModel):
    semesters: list[SemesterOut]
    conflicts: list[PlanConflict]


class GeneratePlanRequest(BaseModel):
    major: str
    completed_courses: list[str] = Field(default_factory=list)
    target_graduation: str = "Spring 2029"
    max_units_per_semester: int = 15
    start_semester: str = "Fall"
    start_year: int = 2025
    required_courses: list[str] = Field(default_factory=list)
    include_ge: bool = True
    include_ai: bool = True


class AdjustPlanRequest(BaseModel):
    plan: PlanResponse
    course_code: str
    from_semester: str
    from_year: int
    to_semester: str
    to_year: int
    completed_courses: list[str] = Field(default_factory=list)
    max_units_per_semester: int = 15  # must match the cap the plan was generated with
    major: Optional[str] = None       # when set, re-tag course roles after the move


class SwapOptionsRequest(BaseModel):
    major: str
    plan: PlanResponse
    course_code: str          # the slot currently in the plan (elective / GR / GE / FREE)
    semester: str             # which semester the slot is in
    year: int
    completed_courses: list[str] = Field(default_factory=list)
    max_units_per_semester: int = 15
    query: Optional[str] = None   # search text for open slots (FREE / GWAR) over the catalog


class SwapOption(BaseModel):
    course_code: str
    title: str
    units: int
    department: str
    offered_fall: bool
    offered_spring: bool
    fits_budget: bool         # soft: does swapping keep the semester within the unit target
    eligible: bool = True     # passes prereq/standing/offering for this slot right now
    note: Optional[str] = None  # why not eligible (needs prereq / standing / not offered this term)


class SwapOptionsResponse(BaseModel):
    area: Optional[str]       # the area/label of the slot, or null if it isn't a fillable slot
    slot_type: str = "requirement"  # elective | grad | free | ge | requirement
    course_code: str          # the slot being filled/swapped
    semester: str
    year: int
    options: list[SwapOption] # legal alternatives
    excluded: int             # candidates that were not legal (already taken / prereq / offering)
    needs_data: bool = False  # true for GE slots: picking needs the (not-yet-scraped) GE course lists
    search: bool = False      # true when this slot is search-driven (FREE / GWAR) — send `query`
    hint: Optional[str] = None  # human guidance (e.g. example courses, "type to search")


class SwapApplyRequest(BaseModel):
    plan: PlanResponse
    from_code: str            # elective currently in the slot
    to_code: str              # the alternative the student chose
    semester: str
    year: int
    completed_courses: list[str] = Field(default_factory=list)
    max_units_per_semester: int = 15
    major: Optional[str] = None   # when set, re-tag course roles after the swap
