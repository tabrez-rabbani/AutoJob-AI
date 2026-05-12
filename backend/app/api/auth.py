"""
AutoJob AI — Auth API
User registration, login, Google OAuth, and profile management.
"""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    SignupRequest,
    LoginRequest,
    GoogleAuthRequest,
    TokenResponse,
    UserResponse,
    UpdateProfileRequest,
)
from app.utils.auth import get_current_user
from app.utils.security import hash_password, verify_password, create_access_token, decrypt_credential

logger = logging.getLogger("autojob.api.auth")

router = APIRouter(tags=["Auth"])


def _decrypt_or_none(encrypted_val: str | None) -> str | None:
    """Safely decrypt a stored credential, returning None if not set."""
    if not encrypted_val:
        return None
    try:
        return decrypt_credential(encrypted_val)
    except Exception:
        return None


@router.post("/auth/signup", response_model=TokenResponse, status_code=201)
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user
    user = User(
        email=request.email,
        full_name=request.full_name,
        hashed_password=hash_password(request.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Generate JWT
    token = create_access_token(data={"sub": user.email})

    logger.info(f"New user registered: {user.email}")

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            resume_url=user.resume_url,
            skills=user.skills,
            preferred_roles=user.preferred_roles,
            preferred_locations=user.preferred_locations,
            preferred_country=user.preferred_country,
            experience_years=user.experience_years,
            current_ctc=user.current_ctc,
            expected_ctc=user.expected_ctc,
            notice_period_days=user.notice_period_days,
            current_city=user.current_city,
            subscription_tier=user.subscription_tier,
            smtp_email=_decrypt_or_none(user.smtp_email_enc),
            smtp_configured=bool(user.smtp_email_enc and user.smtp_password_enc),
            smtp_host=user.smtp_host,
            smtp_port=user.smtp_port,
            naukri_email=_decrypt_or_none(user.naukri_email_enc),
            naukri_configured=bool(user.naukri_email_enc and user.naukri_password_enc),
            linkedin_email=_decrypt_or_none(user.linkedin_email_enc),
            linkedin_configured=bool(user.linkedin_email_enc and user.linkedin_password_enc),
        ),
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login with email and password."""
    # Find user
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate JWT
    token = create_access_token(data={"sub": user.email})

    logger.info(f"User logged in: {user.email}")

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            resume_url=user.resume_url,
            skills=user.skills,
            preferred_roles=user.preferred_roles,
            preferred_locations=user.preferred_locations,
            preferred_country=user.preferred_country,
            experience_years=user.experience_years,
            current_ctc=user.current_ctc,
            expected_ctc=user.expected_ctc,
            notice_period_days=user.notice_period_days,
            current_city=user.current_city,
            subscription_tier=user.subscription_tier,
            smtp_email=_decrypt_or_none(user.smtp_email_enc),
            smtp_configured=bool(user.smtp_email_enc and user.smtp_password_enc),
            smtp_host=user.smtp_host,
            smtp_port=user.smtp_port,
            naukri_email=_decrypt_or_none(user.naukri_email_enc),
            naukri_configured=bool(user.naukri_email_enc and user.naukri_password_enc),
            linkedin_email=_decrypt_or_none(user.linkedin_email_enc),
            linkedin_configured=bool(user.linkedin_email_enc and user.linkedin_password_enc),
        ),
    )


# ── Google OAuth ─────────────────────────────────────

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.post("/auth/google", response_model=TokenResponse)
async def google_auth(request: GoogleAuthRequest, db: AsyncSession = Depends(get_db)):
    """
    Login or register via Google OAuth 2.0.
    Frontend sends the authorization code received from Google's consent screen.
    """
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google OAuth is not configured on this server.",
        )

    # Step 1: Exchange authorization code for access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": request.code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": request.redirect_uri,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        logger.warning(f"Google token exchange failed: {token_resp.text}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication failed. Please try again.",
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid response from Google.",
        )

    # Step 2: Fetch user info from Google
    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Failed to fetch Google user info.",
        )

    google_user = userinfo_resp.json()
    google_id = google_user.get("id")
    email = google_user.get("email")
    full_name = google_user.get("name", "")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account does not have an email address.",
        )

    # Step 3: Find existing user by google_id OR email
    result = await db.execute(
        select(User).where((User.google_id == google_id) | (User.email == email))
    )
    user = result.scalar_one_or_none()

    if user:
        # Link google_id if not already set (user previously signed up with email/password)
        if not user.google_id:
            user.google_id = google_id
            await db.flush()
        logger.info(f"Google login: {user.email}")
    else:
        # Create new user (no password — Google-only account)
        user = User(
            email=email,
            full_name=full_name,
            hashed_password=None,
            google_id=google_id,
        )
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info(f"New Google user registered: {user.email}")

    # Step 4: Issue JWT
    jwt_token = create_access_token(data={"sub": user.email})

    return TokenResponse(
        access_token=jwt_token,
        user=UserResponse(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            resume_url=user.resume_url,
            skills=user.skills,
            preferred_roles=user.preferred_roles,
            preferred_locations=user.preferred_locations,
            preferred_country=user.preferred_country,
            experience_years=user.experience_years,
            current_ctc=user.current_ctc,
            expected_ctc=user.expected_ctc,
            notice_period_days=user.notice_period_days,
            current_city=user.current_city,
            subscription_tier=user.subscription_tier,
            smtp_email=_decrypt_or_none(user.smtp_email_enc),
            smtp_configured=bool(user.smtp_email_enc and user.smtp_password_enc),
            smtp_host=user.smtp_host,
            smtp_port=user.smtp_port,
            naukri_email=_decrypt_or_none(user.naukri_email_enc),
            naukri_configured=bool(user.naukri_email_enc and user.naukri_password_enc),
            linkedin_email=_decrypt_or_none(user.linkedin_email_enc),
            linkedin_configured=bool(user.linkedin_email_enc and user.linkedin_password_enc),
        ),
    )


@router.get("/auth/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        resume_url=user.resume_url,
        skills=user.skills,
        preferred_roles=user.preferred_roles,
        preferred_locations=user.preferred_locations,
        preferred_country=user.preferred_country,
        experience_years=user.experience_years,
        current_ctc=user.current_ctc,
        expected_ctc=user.expected_ctc,
        notice_period_days=user.notice_period_days,
        current_city=user.current_city,
        subscription_tier=user.subscription_tier,
        smtp_email=_decrypt_or_none(user.smtp_email_enc),
        smtp_configured=bool(user.smtp_email_enc and user.smtp_password_enc),
        smtp_host=user.smtp_host,
        smtp_port=user.smtp_port,
        naukri_email=_decrypt_or_none(user.naukri_email_enc),
        naukri_configured=bool(user.naukri_email_enc and user.naukri_password_enc),
        linkedin_email=_decrypt_or_none(user.linkedin_email_enc),
        linkedin_configured=bool(user.linkedin_email_enc and user.linkedin_password_enc),
    )


@router.put("/auth/me", response_model=UserResponse)
async def update_profile(
    request: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile."""
    if request.full_name is not None:
        user.full_name = request.full_name
    if request.skills is not None:
        user.skills = request.skills
    if request.preferred_roles is not None:
        user.preferred_roles = request.preferred_roles
    if request.preferred_locations is not None:
        user.preferred_locations = request.preferred_locations
    if request.preferred_country is not None:
        user.preferred_country = request.preferred_country
    if request.experience_years is not None:
        user.experience_years = request.experience_years
    if request.current_ctc is not None:
        user.current_ctc = request.current_ctc
    if request.expected_ctc is not None:
        user.expected_ctc = request.expected_ctc
    if request.notice_period_days is not None:
        user.notice_period_days = request.notice_period_days
    if request.current_city is not None:
        user.current_city = request.current_city
    # Contact info
    if request.phone is not None:
        user.phone = request.phone
    if request.linkedin_url is not None:
        user.linkedin_url = request.linkedin_url
    if request.github_url is not None:
        user.github_url = request.github_url
    if request.portfolio_url is not None:
        user.portfolio_url = request.portfolio_url
    # SMTP settings
    if request.smtp_email is not None:
        from app.utils.security import encrypt_credential
        user.smtp_email_enc = encrypt_credential(request.smtp_email)
    if request.smtp_password is not None:
        from app.utils.security import encrypt_credential
        user.smtp_password_enc = encrypt_credential(request.smtp_password)
    if request.smtp_host is not None:
        user.smtp_host = request.smtp_host
    if request.smtp_port is not None:
        user.smtp_port = request.smtp_port
    # Naukri.com credentials
    if request.naukri_email is not None:
        from app.utils.security import encrypt_credential
        user.naukri_email_enc = encrypt_credential(request.naukri_email)
    if request.naukri_password is not None:
        from app.utils.security import encrypt_credential
        user.naukri_password_enc = encrypt_credential(request.naukri_password)
    # LinkedIn credentials
    if request.linkedin_email is not None:
        from app.utils.security import encrypt_credential
        user.linkedin_email_enc = encrypt_credential(request.linkedin_email)
    if request.linkedin_password is not None:
        from app.utils.security import encrypt_credential
        user.linkedin_password_enc = encrypt_credential(request.linkedin_password)

    await db.flush()
    await db.refresh(user)

    logger.info(f"Profile updated: {user.email}")

    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        resume_url=user.resume_url,
        skills=user.skills,
        preferred_roles=user.preferred_roles,
        preferred_locations=user.preferred_locations,
        preferred_country=user.preferred_country,
        experience_years=user.experience_years,
        current_ctc=user.current_ctc,
        expected_ctc=user.expected_ctc,
        notice_period_days=user.notice_period_days,
        current_city=user.current_city,
        subscription_tier=user.subscription_tier,
        smtp_email=_decrypt_or_none(user.smtp_email_enc),
        smtp_configured=bool(user.smtp_email_enc and user.smtp_password_enc),
        smtp_host=user.smtp_host,
        smtp_port=user.smtp_port,
        naukri_email=_decrypt_or_none(user.naukri_email_enc),
        naukri_configured=bool(user.naukri_email_enc and user.naukri_password_enc),
        linkedin_email=_decrypt_or_none(user.linkedin_email_enc),
        linkedin_configured=bool(user.linkedin_email_enc and user.linkedin_password_enc),
    )


# ── Resume Upload ────────────────────────────────────

import os
import uuid as uuid_mod
from fastapi import UploadFile, File

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "resumes")
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/auth/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a resume file (PDF or DOCX). Max 5 MB."""

    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and validate size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5 MB.")

    # Ensure upload directory exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Generate unique filename: user_id_uuid.ext
    unique_name = f"{user.id}_{uuid_mod.uuid4().hex[:8]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # Delete old resume file if exists
    if user.resume_url and os.path.exists(user.resume_url):
        try:
            os.remove(user.resume_url)
        except OSError:
            pass

    # Save file
    with open(file_path, "wb") as f:
        f.write(contents)

    # Update user record
    user.resume_url = file_path
    await db.flush()
    await db.refresh(user)

    logger.info(f"Resume uploaded for {user.email}: {file_path}")

    return {
        "message": "Resume uploaded successfully",
        "resume_url": f"/uploads/resumes/{unique_name}",
        "filename": file.filename,
    }


# ── Resume Profile Extraction (AI Auto-Fill) ─────────

@router.post("/auth/extract-resume-profile")
async def extract_resume_profile(
    user: User = Depends(get_current_user),
):
    """
    Extract structured profile data from the user's uploaded resume using AI.
    Returns name, skills, experience, preferred_roles etc. for auto-filling Settings.
    """
    if not user.resume_url or not os.path.exists(user.resume_url):
        raise HTTPException(status_code=400, detail="No resume uploaded yet. Please upload your resume first.")

    # Step 1: Extract text from resume
    from app.utils.resume_parser import extract_resume_text
    resume_text = await extract_resume_text(user.resume_url)

    if not resume_text or len(resume_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="Could not extract text from resume. Try uploading a different file.")

    # Step 2: Run AI Profile Analyzer
    from app.agents.profile_analyzer import analyze_profile
    try:
        profile = await analyze_profile({"resume_text": resume_text})
    except Exception as e:
        logger.error(f"AI profile extraction failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")

    logger.info(f"Resume profile extracted for {user.email}: {profile.get('name', '?')} | {len(profile.get('skills', []))} skills")

    return {
        "full_name": profile.get("name", ""),
        "skills": profile.get("skills", []),
        "experience_years": profile.get("experience_years", 0),
        "preferred_roles": profile.get("preferred_roles", []),
        "summary": profile.get("summary", ""),
        "education": profile.get("education", ""),
        "technologies": profile.get("technologies", []),
        "contact_email": profile.get("email"),
        "phone": profile.get("phone"),
        "linkedin_url": profile.get("linkedin_url"),
        "github_url": profile.get("github_url"),
        "portfolio_url": profile.get("portfolio_url"),
    }

