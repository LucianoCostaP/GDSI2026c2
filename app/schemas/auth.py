from typing import Annotated

from pydantic import BaseModel, StringConstraints

from ..models import Role, User

Name = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class CodeSent(BaseModel):
    """Respuesta al pedir un código: `challenge` vuelve con el código en la verificación."""

    challenge: str
    email_hint: str


class CodeVerification(BaseModel):
    challenge: str
    code: Annotated[str, StringConstraints(strip_whitespace=True, max_length=6)]


class UserOut(BaseModel):
    id: int
    member_id: str | None
    name: str
    email: str
    role: Role

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            member_id=user.member_id,
            name=user.name,
            email=user.email,
            role=user.role,
        )


class LoginResponse(BaseModel):
    token: str
    user: UserOut
