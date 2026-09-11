"""Permission-matrix coverage for the role system (student/admin/psychologist)
introduced alongside `User.role` — previously `get_current_admin_user`'s 403
path had zero test coverage at all. Exercises the dependency functions
directly rather than through the app, since `require_role` has no route
consumer yet (its first real caller is the psychologist router, a later
milestone)."""

import pytest
from fastapi import HTTPException

from app.dependencies import get_current_admin_user, require_role
from app.models.user import User, UserRole


async def test_get_current_admin_user_accepts_admin(admin_user: User) -> None:
    result = await get_current_admin_user(current_user=admin_user)
    assert result is admin_user


async def test_get_current_admin_user_rejects_student(test_user: User) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_admin_user(current_user=test_user)
    assert exc_info.value.status_code == 403


async def test_get_current_admin_user_rejects_psychologist(psychologist_user: User) -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_admin_user(current_user=psychologist_user)
    assert exc_info.value.status_code == 403


async def test_require_role_accepts_matching_role(psychologist_user: User) -> None:
    check = require_role(UserRole.psychologist)
    result = await check(current_user=psychologist_user)
    assert result is psychologist_user


async def test_require_role_rejects_student(test_user: User) -> None:
    check = require_role(UserRole.psychologist)
    with pytest.raises(HTTPException) as exc_info:
        await check(current_user=test_user)
    assert exc_info.value.status_code == 403


async def test_require_role_rejects_admin_when_only_psychologist_allowed(admin_user: User) -> None:
    check = require_role(UserRole.psychologist)
    with pytest.raises(HTTPException) as exc_info:
        await check(current_user=admin_user)
    assert exc_info.value.status_code == 403


async def test_require_role_accepts_any_of_multiple_roles(admin_user: User) -> None:
    check = require_role(UserRole.admin, UserRole.psychologist)
    result = await check(current_user=admin_user)
    assert result is admin_user


async def test_is_admin_matches_role_for_student(test_user: User) -> None:
    assert test_user.is_admin == (test_user.role == UserRole.admin)


async def test_is_admin_matches_role_for_admin(admin_user: User) -> None:
    assert admin_user.is_admin == (admin_user.role == UserRole.admin)


async def test_is_admin_matches_role_for_psychologist(psychologist_user: User) -> None:
    assert psychologist_user.is_admin == (psychologist_user.role == UserRole.admin)
