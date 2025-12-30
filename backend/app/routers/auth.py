import os
import secrets
import time
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth

router = APIRouter(prefix="/auth", tags=["auth"])

# Frontend URL for redirects after auth
FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3008')

# Simple token store (in production, use Redis)
# Maps token -> {user_info, expires}
auth_tokens: dict = {}

# OAuth setup
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Load allowed users from environment
def get_allowed_users() -> set[str]:
    users = os.getenv('ALLOWED_USERS', '')
    return {email.strip().lower() for email in users.split(',') if email.strip()}


@router.get('/login')
async def login(request: Request):
    """Redirect to Google OAuth."""
    # Use fixed redirect URI to avoid Docker internal hostname issues
    redirect_uri = os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:3008/api/auth/callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get('/callback')
async def auth_callback(request: Request):
    """Handle Google OAuth callback."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")

    user_info = token.get('userinfo')
    if not user_info:
        raise HTTPException(status_code=400, detail="Failed to get user info")

    email = user_info.get('email', '').lower()
    allowed_users = get_allowed_users()

    # Debug logging
    print(f"[AUTH] Email from Google: '{email}'")
    print(f"[AUTH] Allowed users: {allowed_users}")
    print(f"[AUTH] Email in allowed: {email in allowed_users}")

    if allowed_users and email not in allowed_users:
        # Clear any session and redirect with error
        request.session.clear()
        return RedirectResponse(url=f'{FRONTEND_URL}?error=not_authorized')

    # Store user in session (for desktop browsers with working cookies)
    user_data = {
        'email': email,
        'name': user_info.get('name', ''),
        'picture': user_info.get('picture', '')
    }
    request.session['user'] = user_data

    # Also generate a one-time token for mobile browsers (iOS Safari blocks cross-site cookies)
    token = secrets.token_urlsafe(32)
    auth_tokens[token] = {
        'user': user_data,
        'expires': time.time() + 60  # 1 minute expiry
    }

    # Redirect with token in URL
    return RedirectResponse(url=f'{FRONTEND_URL}?auth_token={token}')


@router.get('/logout')
async def logout(request: Request):
    """Clear session and logout."""
    request.session.clear()
    return RedirectResponse(url=FRONTEND_URL)


@router.get('/me')
async def get_current_user(request: Request):
    """Get current logged-in user."""
    # First try session (desktop browsers)
    user = request.session.get('user')
    if user:
        return user

    # Then try Authorization header (mobile browsers using localStorage)
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        token_data = auth_tokens.get(token)
        if token_data and token_data.get('expires', 0) > time.time():
            return token_data['user']

    raise HTTPException(status_code=401, detail="Not authenticated")


@router.post('/exchange-token')
async def exchange_token(request: Request):
    """Exchange one-time auth token for a persistent token."""
    body = await request.json()
    token = body.get('token')

    if not token:
        raise HTTPException(status_code=400, detail="Token required")

    token_data = auth_tokens.pop(token, None)  # Remove after use (one-time)

    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if token_data.get('expires', 0) < time.time():
        raise HTTPException(status_code=401, detail="Token expired")

    # Generate a long-lived token for localStorage
    persistent_token = secrets.token_urlsafe(32)
    auth_tokens[persistent_token] = {
        'user': token_data['user'],
        'expires': time.time() + 86400 * 7  # 7 days
    }

    return {'token': persistent_token, 'user': token_data['user']}
