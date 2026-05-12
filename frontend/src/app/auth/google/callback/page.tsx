/**
 * AutoJob AI — Google OAuth Callback Page
 * Captures the authorization code from Google's redirect and exchanges it for a JWT.
 */

"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useAuth } from "@/context/AuthContext";
import { authApi } from "@/lib/api";

function GoogleCallbackContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { login } = useAuth();
    const [error, setError] = useState("");

    useEffect(() => {
        const code = searchParams.get("code");
        const errorParam = searchParams.get("error");

        if (errorParam) {
            setError("Google login was cancelled.");
            setTimeout(() => router.push("/login"), 2000);
            return;
        }

        if (!code) {
            setError("No authorization code received.");
            setTimeout(() => router.push("/login"), 2000);
            return;
        }

        // Exchange code for JWT
        const redirectUri = `${window.location.origin}/auth/google/callback`;

        authApi
            .googleLogin({ code, redirect_uri: redirectUri })
            .then(({ access_token, user }) => {
                login(access_token, user);
                router.push("/dashboard");
            })
            .catch((err: any) => {
                setError(err?.message || "Google login failed. Please try again.");
                setTimeout(() => router.push("/login"), 3000);
            });
    }, [searchParams, login, router]);

    return (
        <div
            style={{
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "#f8fafc",
                fontFamily: "system-ui, sans-serif",
            }}
        >
            <div style={{ textAlign: "center" }}>
                {error ? (
                    <>
                        <p style={{ color: "#ef4444", fontSize: "16px", marginBottom: "8px" }}>
                            {error}
                        </p>
                        <p style={{ color: "#94a3b8", fontSize: "14px" }}>
                            Redirecting to login...
                        </p>
                    </>
                ) : (
                    <>
                        <div
                            style={{
                                width: "40px",
                                height: "40px",
                                border: "3px solid #e2e8f0",
                                borderTopColor: "#4A90E2",
                                borderRadius: "50%",
                                animation: "spin 0.8s linear infinite",
                                margin: "0 auto 16px",
                            }}
                        />
                        <p style={{ color: "#334155", fontSize: "16px", fontWeight: 600 }}>
                            Signing you in with Google...
                        </p>
                    </>
                )}
            </div>

            <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
    );
}

export default function GoogleCallbackPage() {
    return (
        <Suspense
            fallback={
                <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <p>Loading...</p>
                </div>
            }
        >
            <GoogleCallbackContent />
        </Suspense>
    );
}
