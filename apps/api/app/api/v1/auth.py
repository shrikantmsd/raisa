from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentActor, get_current_actor, get_current_user
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        result = auth_service.login(
            db,
            organization_slug=payload.organization_slug,
            email=payload.email,
            password=payload.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except auth_service.LoginError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return TokenResponse(access_token=result.access_token)


@router.post("/logout")
def logout(actor: CurrentActor = Depends(get_current_actor), db: Session = Depends(get_db)) -> dict:
    auth_service.logout(
        db, session_id=actor.session_id, user_id=actor.user_id, organization_id=actor.organization_id
    )
    return {"status": "logged_out"}


@router.get("/me", response_model=CurrentUserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
