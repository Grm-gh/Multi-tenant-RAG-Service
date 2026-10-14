import time
import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config, db

bearer = HTTPBearer(auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def make_token(user_id: int) -> str:
    return jwt.encode({"sub": str(user_id), "exp": int(time.time()) + config.JWT_TTL_SECONDS},
                      config.JWT_SECRET, algorithm="HS256")


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(status_code=401, detail="missing token")
    try:
        user_id = int(jwt.decode(creds.credentials, config.JWT_SECRET, algorithms=["HS256"])["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    with db.get_pool().connection() as conn:
        row = conn.execute("SELECT id, email FROM users WHERE id=%s", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="unknown user")
    return row
