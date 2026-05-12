/**
 * AutoJob AI — Environment Configuration
 * Single source for all environment-dependent values.
 */

export const config = {
    apiUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api",
    appName: "AutoJob AI",
    appDescription: "AI-powered job application automation platform",
    googleClientId: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "",
} as const;
