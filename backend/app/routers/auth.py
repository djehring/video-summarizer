import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth

router = APIRouter(prefix="/auth", tags=["auth"])

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

    if allowed_users and email not in allowed_users:
        # Clear any session and redirect with error
        request.session.clear()
        return RedirectResponse(url='/?error=not_authorized')

    # Store user in session
    request.session['user'] = {
        'email': email,
        'name': user_info.get('name', ''),
        'picture': user_info.get('picture', '')
    }

    return RedirectResponse(url='/')


@router.get('/logout')
async def logout(request: Request):
    """Clear session and logout."""
    request.session.clear()
    return RedirectResponse(url='/')


@router.get('/me')
async def get_current_user(request: Request):
    """Get current logged-in user."""
    user = request.session.get('user')
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
