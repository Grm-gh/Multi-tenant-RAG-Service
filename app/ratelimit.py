"""Token-bucket rate limiter in Redis. A Lua script makes read-refill-consume atomic across API instances."""
import time
from fastapi import Depends, HTTPException

from . import config
from .auth import current_user
from .queue import redis_conn

LUA = """
local key, capacity, rate, now, cost = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3]), tonumber(ARGV[4])
local d = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(d[1]); local ts = tonumber(d[2])
if tokens == nil then tokens = capacity; ts = now end
tokens = math.min(capacity, tokens + (now - ts) * rate)
local allowed = 0
if tokens >= cost then tokens = tokens - cost; allowed = 1 end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(capacity / rate) + 1)
return allowed
"""
_script = redis_conn.register_script(LUA)


def allow(user_id: int, cost: int = 1) -> bool:
    return bool(_script(keys=[f"rl:{user_id}"],
                        args=[config.RATE_CAPACITY, config.RATE_REFILL_PER_SEC, time.time(), cost]))


def rate_limited_user(user=Depends(current_user)):
    if not allow(user["id"]):
        raise HTTPException(status_code=429, detail="rate limit exceeded", headers={"Retry-After": "2"})
    return user
