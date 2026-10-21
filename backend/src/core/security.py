from fastapi.security import HTTPBearer

# auto_error=False: a missing header is turned into our own 401 by the token
# dependency instead of FastAPI's default response.
bearer_security = HTTPBearer(scheme_name="BearerJWT", auto_error=False)
