import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor, require_permission
from app.models.rbac import PermissionAction, PermissionDomain
from app.models.user import User
from app.schemas.user import UserCreateRequest, UserResponse
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users(
    actor: CurrentActor = Depends(require_permission(PermissionDomain.USER, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
) -> list[User]:
    # organization_id ALWAYS comes from the authenticated actor. There is
    # no organization_id query parameter on this route, on purpose — see
    # tests/test_tenant_isolation.py for what this is defending against.
    return db.query(User).filter(User.organization_id == actor.organization_id).order_by(User.created_at).all()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: uuid.UUID,
    actor: CurrentActor = Depends(require_permission(PermissionDomain.USER, PermissionAction.VIEW)),
    db: Session = Depends(get_db),
) -> User:
    user = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == actor.organization_id)
        .first()
    )
    if user is None:
        # Same 404 whether the user doesn't exist or belongs to another
        # tenant — a 403 would leak that the id is valid *somewhere*.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    actor: CurrentActor = Depends(require_permission(PermissionDomain.USER, PermissionAction.CREATE)),
    db: Session = Depends(get_db),
) -> User:
    return user_service.create_user(
        db,
        organization_id=actor.organization_id,
        email=payload.email,
        name=payload.name,
        password=payload.password,
        department=payload.department,
        job_title=payload.job_title,
        created_by=actor.user_id,
    )
