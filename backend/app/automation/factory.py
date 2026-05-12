"""
AutoJob AI — Platform Adapter Factory
Maps platform name strings to their adapter classes.
Keeps the automation pipeline decoupled from specific imports.
"""

from app.automation.adapters.base import JobPlatformAdapter


def get_adapter(platform: str, headless: bool = True) -> JobPlatformAdapter:
    """
    Instantiate the correct adapter for the given platform name.

    Args:
        platform: One of "linkedin", "naukri" (case-insensitive)
        headless: Whether to run the browser in headless mode

    Returns:
        An instance of the corresponding JobPlatformAdapter subclass.

    Raises:
        ValueError: If the platform is not supported.
    """
    platform = platform.strip().lower()

    if platform == "linkedin":
        from app.automation.adapters.linkedin import LinkedInAdapter
        return LinkedInAdapter(headless=headless)

    if platform == "naukri":
        from app.automation.adapters.naukri import NaukriAdapter
        return NaukriAdapter(headless=headless)

    raise ValueError(
        f"Unknown platform: '{platform}'. Supported: linkedin, naukri"
    )


# List of all supported platforms (used by frontend for validation)
SUPPORTED_PLATFORMS = ["linkedin", "naukri"]
