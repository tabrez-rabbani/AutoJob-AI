/**
 * AutoJob AI — API Service Layer
 * Centralized API client for all backend communication.
 */

import { config } from "./config";

const API_BASE = config.apiUrl;

/**
 * Core fetch wrapper with auth token and error handling.
 */
async function apiFetch<T>(
    endpoint: string,
    options: RequestInit = {}
): Promise<T> {
    const token =
        typeof window !== "undefined" ? localStorage.getItem("token") : null;

    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...((options.headers as Record<string, string>) || {}),
    };

    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
    });

    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }));

        let errorMessage = "Something went wrong";
        if (Array.isArray(error.detail)) {
            // FastAPI 422 validation error array
            errorMessage = error.detail.map((err: any) => `${err.loc.slice(-1)[0]}: ${err.msg}`).join(", ");
        } else if (typeof error.detail === "string") {
            errorMessage = error.detail;
        }

        throw new ApiError(res.status, errorMessage);
    }

    return res.json();
}

/** Custom error class for API errors */
export class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
        this.name = "ApiError";
    }
}

// ── Auth ────────────────────────────────────────────

export interface SignupPayload {
    email: string;
    password: string;
    full_name: string;
}

export interface LoginPayload {
    email: string;
    password: string;
}

export interface TokenResponse {
    access_token: string;
    token_type: string;
    user: UserProfile;
}

export interface UserProfile {
    id: string;
    email: string;
    full_name: string;
    resume_url: string | null;
    skills: string[] | null;
    preferred_roles: string[] | null;
    preferred_locations: string[] | null;
    preferred_country: string | null;
    experience_years: number | null;
    current_ctc: number | null;
    expected_ctc: number | null;
    notice_period_days: number | null;
    current_city: string | null;
    subscription_tier: string;
    // SMTP
    smtp_email: string | null;
    smtp_configured: boolean;
    smtp_host: string | null;
    smtp_port: number | null;
    // Naukri
    naukri_email: string | null;
    naukri_configured: boolean;
    // LinkedIn
    linkedin_email: string | null;
    linkedin_configured: boolean;
}

export type UpdateProfilePayload = Partial<UserProfile> & {
    smtp_password?: string;
    naukri_password?: string;
    linkedin_password?: string;
};

export const authApi = {
    signup: (data: SignupPayload) =>
        apiFetch<TokenResponse>("/auth/signup", {
            method: "POST",
            body: JSON.stringify(data),
        }),

    login: (data: LoginPayload) =>
        apiFetch<TokenResponse>("/auth/login", {
            method: "POST",
            body: JSON.stringify(data),
        }),

    googleLogin: (data: { code: string; redirect_uri: string }) =>
        apiFetch<TokenResponse>("/auth/google", {
            method: "POST",
            body: JSON.stringify(data),
        }),

    getMe: () => apiFetch<UserProfile>("/auth/me"),

    updateProfile: (data: UpdateProfilePayload) =>
        apiFetch<UserProfile>("/auth/me", {
            method: "PUT",
            body: JSON.stringify(data),
        }),

    uploadResume: async (file: File) => {
        const token =
            typeof window !== "undefined" ? localStorage.getItem("token") : null;
        const formData = new FormData();
        formData.append("file", file);

        const res = await fetch(`${API_BASE}/auth/upload-resume`, {
            method: "POST",
            headers: token ? { Authorization: `Bearer ${token}` } : {},
            body: formData, // No Content-Type header — browser sets it with boundary
        });

        if (!res.ok) {
            const error = await res.json().catch(() => ({ detail: res.statusText }));
            throw new ApiError(res.status, error.detail || "Upload failed");
        }

        return res.json() as Promise<{ message: string; resume_url: string; filename: string }>;
    },

    extractResumeProfile: () =>
        apiFetch<{
            full_name: string;
            skills: string[];
            experience_years: number;
            preferred_roles: string[];
            summary: string;
            education: string;
            technologies: string[];
        }>("/auth/extract-resume-profile", { method: "POST" }),
};

// ── Dashboard ───────────────────────────────────────

export interface DashboardStats {
    total_scraped: number;
    total_qualified: number;
    total_applied: number;
    total_external: number;
    total_skipped: number;
    total_failed: number;
}

export interface DashboardJob {
    id: string;
    title: string;
    company: string;
    location: string | null;
    job_type: string | null;
    apply_url: string;
    application_status: string | null;
    match_score: number | null;
    scraped_at: string | null;
}

export interface DashboardApplication {
    id: string;
    job_id: string;
    job_title: string;
    company: string;
    status: string;
    match_score: number | null;
    applied_at: string | null;
    notes: string | null;
}

export interface FilterParams {
    search?: string;
    status?: string;
    min_score?: number;
    max_score?: number;
    date_from?: string;
    date_to?: string;
}

function buildFilterQuery(filters?: FilterParams): string {
    if (!filters) return "";
    const params = new URLSearchParams();
    if (filters.search) params.set("search", filters.search);
    if (filters.status) params.set("status", filters.status);
    if (filters.min_score !== undefined) params.set("min_score", String(filters.min_score));
    if (filters.max_score !== undefined) params.set("max_score", String(filters.max_score));
    if (filters.date_from) params.set("date_from", filters.date_from);
    if (filters.date_to) params.set("date_to", filters.date_to);
    const str = params.toString();
    return str ? `&${str}` : "";
}

export interface DailyActivity {
    date: string;
    count: number;
}

export interface SourceCount {
    platform: string;
    count: number;
}

export interface AnalyticsData {
    daily_activity: DailyActivity[];
    source_distribution: SourceCount[];
    heatmap: DailyActivity[];
}

export const dashboardApi = {
    getStats: () => apiFetch<DashboardStats>("/dashboard/stats"),

    getAnalytics: () => apiFetch<AnalyticsData>("/dashboard/analytics"),

    getJobs: (limit = 50, offset = 0, filters?: FilterParams) =>
        apiFetch<{ count: number; jobs: DashboardJob[] }>(
            `/dashboard/jobs?limit=${limit}&offset=${offset}${buildFilterQuery(filters)}`
        ),

    getQualified: (limit = 50, offset = 0, filters?: FilterParams) =>
        apiFetch<{ count: number; jobs: DashboardJob[] }>(
            `/dashboard/qualified?limit=${limit}&offset=${offset}${buildFilterQuery(filters)}`
        ),

    getApplied: (limit = 50, offset = 0, filters?: FilterParams) =>
        apiFetch<{ count: number; applications: DashboardApplication[] }>(
            `/dashboard/applied?limit=${limit}&offset=${offset}${buildFilterQuery(filters)}`
        ),

    getJobDetail: (jobId: string) =>
        apiFetch<JobDetail>(`/dashboard/jobs/${jobId}`),
};

export interface JobDetail {
    id: string;
    title: string;
    company: string;
    location: string | null;
    description: string | null;
    salary_range: string | null;
    job_type: string | null;
    platform: string;
    platform_job_id: string;
    apply_url: string;
    posted_date: string | null;
    scraped_at: string | null;
    is_active: boolean;
    application_status: string | null;
    match_score: number | null;
    applied_at: string | null;
    application_notes: string | null;
}

// ── Jobs ────────────────────────────────────────────

export interface AutoApplyPayload {
    linkedin_email: string;
    linkedin_password: string;
    keywords: string;
    location: string;
    phone: string;
    max_applications: number;
    delay_seconds: number;
    dry_run: boolean;
}

export interface AutoApplyResult {
    job_id: string;
    job_title: string;
    company: string;
    apply_url: string;
    status: string;
    message: string;
}

export interface AutoApplyResponse {
    status: string;
    message: string;
    total_attempted: number;
    applied: number;
    external_apply: number;
    skipped: number;
    failed: number;
    dry_run: boolean;
    results: AutoApplyResult[];
}

export const jobsApi = {
    autoApply: (data: AutoApplyPayload) =>
        apiFetch<AutoApplyResponse>("/jobs/auto-apply", {
            method: "POST",
            body: JSON.stringify(data),
        }),
};


// ── Background Automation API (Phase 6) ─────────────

export interface StartAutomationPayload {
    linkedin_email?: string;
    linkedin_password?: string;
    naukri_email?: string;
    naukri_password?: string;
    platforms: string[];
    keywords: string;
    location: string;
    country: string;
    phone: string;
    max_applications: number;
    delay_seconds: number;
    dry_run: boolean;
}

export interface StartAutomationResponse {
    task_id: string;
    status: string;
    message: string;
}

export interface TaskStatusResponse {
    task_id: string;
    status: string;
    stage: string;
    stage_message: string;
    jobs_scraped: number;
    jobs_matched: number;
    jobs_qualified: number;
    jobs_applied: number;
    jobs_failed: number;
    jobs_skipped: number;
    current_job_index: number;
    total_jobs: number;
    result: any | null;
    error: string | null;
}

export interface SSEProgressEvent {
    stage: string;
    message: string;
    timestamp?: string;
    status?: string;
    result?: any;
    error?: string;
    jobs_scraped?: number;
    jobs_matched?: number;
    jobs_qualified?: number;
    jobs_applied?: number;
    jobs_failed?: number;
    jobs_skipped?: number;
}

export const automationApi = {
    /** Start automation pipeline in background — returns task_id immediately */
    start: (data: StartAutomationPayload) =>
        apiFetch<StartAutomationResponse>("/automation/start", {
            method: "POST",
            body: JSON.stringify(data),
        }),

    /** Start feed scanner pipeline — returns task_id immediately */
    startFeedScan: (data: StartFeedScanPayload) =>
        apiFetch<StartAutomationResponse>("/automation/feed-scan/start", {
            method: "POST",
            body: JSON.stringify(data),
        }),

    /** Poll-based status check (fallback if SSE doesn't work) */
    getStatus: (taskId: string) =>
        apiFetch<TaskStatusResponse>(`/automation/${taskId}/status`),

    /** SSE stream URL for real-time progress (token via query param — EventSource can't send headers) */
    getStreamUrl: (taskId: string) => {
        const token = typeof window !== "undefined" ? localStorage.getItem("token") : "";
        return `${API_BASE}/automation/${taskId}/stream?token=${encodeURIComponent(token || "")}`;
    },
};

export interface StartFeedScanPayload {
    linkedin_email?: string;
    linkedin_password?: string;
    max_emails: number;
    dry_run: boolean;
}
