import uuid

from pydantic import BaseModel, Field


class AnswerItem(BaseModel):
    question_id: uuid.UUID
    # 1..5 for every Likert instrument. PRO-338 Ф0.5: eysenck/elers are
    # Да/Нет (binary) instruments reusing this same field/range rather than
    # a separate 2-point type — decided semantics is 1=Нет, 2=Да (not a
    # "collapsed" 1..5 scale), enforced client-side by the 2-option
    # YES_NO_SCALE in LikertPage.tsx. Their own scoring services (Ф1) read
    # answer_value directly against that convention.
    # Floor widened to 0 for PRO-338 Ф1.2: professional_types_abilities is
    # a genuine 0-3 scale ("совсем не выражено".."ярко выражено", source
    # spec), stored as its literal raw value (no +1 shift) — enforced
    # client-side by ABILITIES_LIKERT_SCALE in LikertPage.tsx. No existing
    # instrument ever sent 0 before, so this is a pure widening, not a
    # semantics change for anything else.
    value: int = Field(ge=0, le=5)


class SubmitAnswersRequest(BaseModel):
    answers: list[AnswerItem]


class SubmitAnswersResponse(BaseModel):
    answered_count: int
    total: int
    completed: bool
