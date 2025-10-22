"""
Supabase JWT authentication service with JWKS support.

This module provides JWT token verification using Supabase's JWKS endpoint,
supporting automatic key rotation and ES256 algorithm.
"""
import jwt
import requests
import time
import logging
from jwt.algorithms import ECAlgorithm
from fastapi import Request, HTTPException, status
from typing import Optional

logger = logging.getLogger(__name__)

JWKS_URL = "https://waqzrjsczmlvkapbkcno.supabase.co/auth/v1/.well-known/jwks.json"

# Cache for JWKS to avoid re-fetching each request
_jwks_cache = {"keys": None, "timestamp": 0}


def _get_jwks():
    """
    Fetch and cache JWKS from Supabase.

    The JWKS is cached for 10 minutes to reduce API calls while still
    allowing for key rotation.

    Returns:
        List of JWK keys from Supabase

    Raises:
        HTTPException: If JWKS fetch fails
    """
    global _jwks_cache
    now = time.time()
    # Refresh JWKS every 10 minutes
    if not _jwks_cache["keys"] or (now - _jwks_cache["timestamp"] > 600):
        try:
            logger.info("Fetching JWKS from Supabase...")
            resp = requests.get(JWKS_URL, timeout=10)
            resp.raise_for_status()
            _jwks_cache["keys"] = resp.json()["keys"]
            _jwks_cache["timestamp"] = now
            logger.info(f"✅ JWKS fetched successfully ({len(_jwks_cache['keys'])} keys)")
        except Exception as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch JWKS: {e}"
            )
    return _jwks_cache["keys"]


def verify_token(request: Request) -> str:
    """
    Verify Supabase JWT token using JWKS.

    This function:
    1. Extracts Bearer token from Authorization header
    2. Fetches JWKS from Supabase (cached)
    3. Verifies JWT signature using ES256 algorithm
    4. Extracts user ID from token payload
    5. Attaches user_id to request.state for downstream use

    Args:
        request: FastAPI request object

    Returns:
        User ID (sub claim) from token

    Raises:
        HTTPException 401: If token is missing, invalid, or expired
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        logger.warning("Missing Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Please provide a valid JWT token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not auth_header.startswith("Bearer "):
        logger.warning("Invalid Authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Use 'Bearer <token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ")[1]

    try:
        # Get unverified header to extract kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            logger.error("Missing 'kid' in token header")
            raise Exception("Missing 'kid' in token header")

        # Fetch JWKS
        jwks = _get_jwks()

        # Find matching key
        key = next((k for k in jwks if k["kid"] == kid), None)
        if not key:
            logger.error(f"Matching key not found in JWKS for kid: {kid}")
            raise Exception("Matching key not found in JWKS")

        # Convert JWK to public key
        public_key = ECAlgorithm.from_jwk(key)

        # Verify and decode token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated"
        )

        # Extract user ID
        user_id = payload.get("sub")
        if not user_id:
            logger.error("Token payload missing 'sub' claim")
            raise Exception("Token payload missing 'sub' claim")

        # Attach to request state
        request.state.user_id = user_id

        logger.info(f"✅ User authenticated: {user_id[:8]}...")
        return user_id

    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again."
        )
    except jwt.InvalidTokenError as e:
        logger.error(f"Invalid token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}"
        )
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Verification failed: {e}"
        )


def get_optional_user_id(request: Request) -> Optional[str]:
    """
    Extract user ID from request if authenticated, otherwise return None.

    Use this for endpoints that support both authenticated and anonymous access.

    Args:
        request: FastAPI request object

    Returns:
        User ID if authenticated, None otherwise
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            return None

        jwks = _get_jwks()
        key = next((k for k in jwks if k["kid"] == kid), None)

        if not key:
            return None

        public_key = ECAlgorithm.from_jwk(key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated"
        )

        return payload.get("sub")

    except Exception as e:
        logger.debug(f"Optional auth failed: {str(e)}")
        return None


def require_admin(request: Request) -> str:
    """
    Verify token and check for admin role.

    Args:
        request: FastAPI request object

    Returns:
        User ID if admin

    Raises:
        HTTPException 403: If user is not an admin
    """
    # First verify token
    user_id = verify_token(request)

    # Check for admin role in JWT payload
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1]

    try:
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        jwks = _get_jwks()
        key = next((k for k in jwks if k["kid"] == kid), None)

        if not key:
            raise Exception("Key not found")

        public_key = ECAlgorithm.from_jwk(key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["ES256"],
            audience="authenticated"
        )

        # Check app_metadata or user_metadata for admin role
        app_metadata = payload.get("app_metadata", {})
        user_metadata = payload.get("user_metadata", {})

        is_admin = (
            app_metadata.get("role") == "admin" or
            user_metadata.get("role") == "admin" or
            payload.get("role") == "admin"
        )

        if not is_admin:
            logger.warning(f"User {user_id[:8]}... attempted admin access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required",
            )

        logger.info(f"✅ Admin access granted: {user_id[:8]}...")
        return user_id

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin verification failed",
        )
