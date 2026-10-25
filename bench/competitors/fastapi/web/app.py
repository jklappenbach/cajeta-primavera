"""FastAPI competitor for the primavera benchmark (bench/contract/README.md).

Run: <venv>/bin/python -m uvicorn app:app --host 127.0.0.1 --port N --workers 1
     --no-access-log --log-level warning
"""
import json
import os

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, StrictStr

TOKEN = b"Bearer bench-7f3c9a1e"
UNAUTHORIZED = b'{"error":"unauthorized"}'

USERNAME_REQUIRED = "username is required"
PASSWORD_REQUIRED = "password is required"
USERNAME_LENGTH = "username must be 3 to 64 characters"
PASSWORD_LENGTH = "password must be at least 8 characters"
ORDER = [USERNAME_REQUIRED, PASSWORD_REQUIRED, USERNAME_LENGTH, PASSWORD_LENGTH]


class CompactJSON(Response):
    """JSON with no whitespace, members in insertion order."""
    media_type = "application/json"

    def render(self, content) -> bytes:
        return json.dumps(content, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ---- the authentication filter: a pure ASGI middleware guarding /users ----

class AuthFilter:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and (scope["path"] == "/users" or scope["path"].startswith("/users/")):
            auth = None
            for k, v in scope["headers"]:
                if k == b"authorization":
                    auth = v
                    break
            if auth != TOKEN:
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"),
                                        (b"content-length", str(len(UNAUTHORIZED)).encode())]})
                await send({"type": "http.response.body", "body": UNAUTHORIZED})
                return
            scope.setdefault("state", {})["principal"] = "bench-client"
        await self.app(scope, receive, send)


# ---- components -------------------------------------------------------------

class IdMinter:
    def mint(self, username: str) -> str:
        h = 0x811C9DC5
        for b in username.encode("utf-8"):
            h ^= b
            h = (h * 16777619) & 0xFFFFFFFF
        return f"u-{h:08x}"


class UserService:
    def __init__(self, minter: IdMinter):
        self.minter = minter

    def register(self, username: str, principal: str) -> dict:
        return {"id": self.minter.mint(username), "username": username,
                "confirmed": False, "registeredBy": principal}


class FortuneRepository:
    def __init__(self):
        self.rows = [
            {"id": 1, "message": "fortune: No such file or directory"},
            {"id": 2, "message": "A computer scientist is someone who fixes things that aren't broken."},
            {"id": 3, "message": "After enough decimal places, nobody gives a damn."},
            {"id": 4, "message": "A bad random number generator: 1, 1, 1, 1, 1, 4.33e+67, 1, 1, 1"},
            {"id": 5, "message": "A computer program does what you tell it to do, not what you want it to do."},
            {"id": 6, "message": "Emacs is a nice operating system, but I prefer UNIX. — Tom Christaensen"},
            {"id": 7, "message": "Any program that runs right is obsolete."},
            {"id": 8, "message": "A list is only as strong as its weakest link. — Donald Knuth"},
            {"id": 9, "message": "Feature: A bug with seniority."},
            {"id": 10, "message": "Computers make very fast, very accurate mistakes."},
            {"id": 11, "message": "<script>alert(\"This should not be displayed in a browser alert box.\");</script>"},
            {"id": 12, "message": "フレームワークのベンチマーク"},
        ]

    def all(self):
        return list(self.rows)


_minter = IdMinter()
_users = UserService(_minter)
_fortunes = FortuneRepository()


def user_service() -> UserService:   # singleton
    return _users


def fortune_repository() -> FortuneRepository:   # singleton
    return _fortunes


class RequestPrincipal:
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name


def request_principal(request: Request) -> RequestPrincipal:
    """Request-scoped: FastAPI resolves it once per request, from what the filter stored."""
    return RequestPrincipal(request.state.principal)


# ---- validation -------------------------------------------------------------

class Signup(BaseModel):
    username: StrictStr = Field(min_length=3, max_length=64)
    password: StrictStr = Field(min_length=8)


def _message(err) -> str | None:
    loc = [p for p in err.get("loc", ()) if p != "body"]
    field = loc[0] if loc else None
    kind = err.get("type", "")
    if field == "username":
        return USERNAME_LENGTH if kind in ("string_too_short", "string_too_long") else USERNAME_REQUIRED
    if field == "password":
        return PASSWORD_LENGTH if kind == "string_too_short" else PASSWORD_REQUIRED
    return None


# ---- the app ----------------------------------------------------------------

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(AuthFilter)
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))


@app.exception_handler(RequestValidationError)
async def validation_failed(request: Request, exc: RequestValidationError):
    found = {_message(e) for e in exc.errors()}
    first = next((m for m in ORDER if m in found), "invalid request")
    return CompactJSON({"error": first}, status_code=400)


@app.get("/health")
def health():
    return CompactJSON({"status": "up"})


@app.post("/users")
def register(body: Signup, users: UserService = Depends(user_service),
             principal: RequestPrincipal = Depends(request_principal)):
    return CompactJSON(users.register(body.username, principal.name), status_code=201)


@app.get("/fortunes")
def fortunes(request: Request, repo: FortuneRepository = Depends(fortune_repository)):
    rows = repo.all()
    rows.sort(key=lambda r: r["message"])
    return templates.TemplateResponse(request, "fortunes.html", {"fortunes": rows},
                                      media_type="text/html; charset=utf-8")
