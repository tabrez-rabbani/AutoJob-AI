"""
AutoJob AI — Browser Stealth Configuration (Advanced)
Production-grade anti-detection measures for Playwright.

Covers:
- User-Agent rotation (latest Chrome versions)
- Viewport randomization (real monitor sizes)
- WebGL/Canvas/AudioContext fingerprint noise
- navigator property spoofing (webdriver, plugins, languages, hardwareConcurrency)
- Chrome runtime spoofing
- Permission API spoofing
- Human-like delay generators
"""

import random

# ── Viewport sizes (common real monitors) ────────────
VIEWPORT_SIZES = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
    {"width": 2560, "height": 1440},
    {"width": 1680, "height": 1050},
]

# ── User-Agents (2025-2026 Chrome on Windows/Mac) ────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
]

# ── Timezone/Locale pairs (all English to ensure selectors work) ───
TIMEZONE_LOCALES = [
    {"timezone_id": "America/New_York", "locale": "en-US"},
    {"timezone_id": "America/Chicago", "locale": "en-US"},
    {"timezone_id": "America/Los_Angeles", "locale": "en-US"},
    {"timezone_id": "America/Denver", "locale": "en-US"},
    {"timezone_id": "Europe/London", "locale": "en-GB"},
    {"timezone_id": "Asia/Kolkata", "locale": "en-IN"},
    {"timezone_id": "Asia/Singapore", "locale": "en-SG"},
    {"timezone_id": "Australia/Sydney", "locale": "en-AU"},
    {"timezone_id": "Pacific/Auckland", "locale": "en-NZ"},
]

# ── Stealth JS Scripts (injected on every page) ──────

STEALTH_SCRIPTS = [
    # ① Remove navigator.webdriver flag
    """
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });
    """,

    # ② Fake plugins array (Chrome has ~5 default plugins)
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                { name: 'Native Client', filename: 'internal-nacl-plugin' },
            ];
            plugins.length = 3;
            return plugins;
        },
    });
    """,

    # ③ Fake languages
    """
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en', 'hi'],
    });
    """,

    # ④ Chrome runtime object (real Chrome has this)
    """
    window.chrome = {
        runtime: {
            PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
            PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformNaclArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
            RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
            connect: () => {},
            sendMessage: () => {},
        },
        loadTimes: () => ({}),
        csi: () => ({}),
        app: { isInstalled: false },
    };
    """,

    # ⑤ Hardware concurrency spoofing (random 4-16 cores)
    """
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => [4, 6, 8, 12, 16][Math.floor(Math.random() * 5)],
    });
    """,

    # ⑥ Device memory spoofing (random 4-16 GB)
    """
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => [4, 8, 16][Math.floor(Math.random() * 3)],
    });
    """,

    # ⑦ WebGL vendor/renderer spoofing
    """
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Intel Inc.';
        if (param === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter.call(this, param);
    };
    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
    WebGL2RenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Intel Inc.';
        if (param === 37446) return 'Intel Iris OpenGL Engine';
        return getParameter2.call(this, param);
    };
    """,

    # ⑧ Canvas fingerprint noise injection
    """
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type) {
        const ctx = this.getContext('2d');
        if (ctx) {
            const noise = Math.random() * 0.01;
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] += noise * 255;
            }
            ctx.putImageData(imageData, 0, 0);
        }
        return originalToDataURL.call(this, type);
    };
    """,

    # ⑨ AudioContext fingerprint noise
    """
    const origGetFloatFrequencyData = AnalyserNode.prototype.getFloatFrequencyData;
    AnalyserNode.prototype.getFloatFrequencyData = function(array) {
        origGetFloatFrequencyData.call(this, array);
        for (let i = 0; i < array.length; i++) {
            array[i] += Math.random() * 0.1 - 0.05;
        }
    };
    """,

    # ⑩ Permission API spoofing
    """
    const origQuery = window.Permissions?.prototype?.query;
    if (origQuery) {
        window.Permissions.prototype.query = function(params) {
            if (params.name === 'notifications') {
                return Promise.resolve({ state: Notification.permission });
            }
            return origQuery.call(this, params);
        };
    }
    """,

    # ⑪ Prevent iframe detection of parent automation
    """
    try {
        Object.defineProperty(document, 'hidden', { get: () => false });
        Object.defineProperty(document, 'visibilityState', { get: () => 'visible' });
    } catch(e) {}
    """,
]

# ── Chrome Launch Arguments ──────────────────────────
CHROME_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-infobars",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-features=TranslateUI",
    "--disable-ipc-flooding-protection",
    "--disable-hang-monitor",
]

# Additional args that rotate randomly (some subset)
OPTIONAL_CHROME_ARGS = [
    "--disable-extensions",
    "--disable-component-extensions-with-background-pages",
    "--disable-default-apps",
    "--mute-audio",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--disable-breakpad",
]


# ── Public API ───────────────────────────────────────

def get_random_viewport() -> dict:
    """Return a random realistic viewport size."""
    return random.choice(VIEWPORT_SIZES)


def get_random_user_agent() -> str:
    """Return a random realistic user-agent string."""
    return random.choice(USER_AGENTS)


def get_random_timezone_locale() -> dict:
    """Return a random timezone/locale pair."""
    return random.choice(TIMEZONE_LOCALES)


def get_random_delay(min_sec: float = 1.5, max_sec: float = 5.0) -> float:
    """Human-like random delay between actions."""
    return random.uniform(min_sec, max_sec)


def get_typing_delay() -> int:
    """Random delay between keystrokes in milliseconds (human-like)."""
    return random.randint(50, 180)


def get_chrome_args() -> list[str]:
    """Return Chrome launch arguments with some randomization."""
    # Always include core args + random subset of optional args
    extra = random.sample(OPTIONAL_CHROME_ARGS, k=random.randint(2, 5))
    return CHROME_ARGS + extra
