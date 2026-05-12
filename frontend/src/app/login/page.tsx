/**
 * AutoJob AI — Login Page
 * Split-screen layout with email/password + Google OAuth login.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { authApi } from "@/lib/api";
import { config } from "@/lib/config";
import AuthLayout from "@/components/layout/AuthLayout";
import { Eye, EyeOff } from "lucide-react";
import styles from "@/styles/auth.module.css";

/** Build the Google OAuth consent URL */
function getGoogleOAuthUrl() {
    const redirectUri = `${window.location.origin}/auth/google/callback`;
    const params = new URLSearchParams({
        client_id: config.googleClientId,
        redirect_uri: redirectUri,
        response_type: "code",
        scope: "openid email profile",
        access_type: "offline",
        prompt: "select_account",
    });
    return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
}

export default function LoginPage() {
    const router = useRouter();
    const { login } = useAuth();

    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [showPassword, setShowPassword] = useState(false);

    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email || !password) {
            setError("Please fill in all fields.");
            return;
        }

        setIsLoading(true);
        setError("");

        try {
            const { access_token, user } = await authApi.login({ email, password });
            login(access_token, user);
            router.push("/dashboard");
        } catch (err: any) {
            setError(err?.message || "Invalid email or password.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleGoogleLogin = () => {
        if (!config.googleClientId) {
            setError("Google login is not configured.");
            return;
        }
        window.location.href = getGoogleOAuthUrl();
    };

    return (
        <AuthLayout>
            <div className={styles.header}>
                <h2 className={styles.title}>Sign In</h2>
                <p className={styles.subtitle}>Welcome back! Sign in to your account.</p>
            </div>

            <form className={styles.form} onSubmit={handleSubmit}>
                {error && <div className={styles.serverError}>{error}</div>}

                <div className={styles.inputGroup}>
                    <input
                        id="email"
                        type="email"
                        className={styles.input}
                        placeholder="E-mail"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        disabled={isLoading}
                        required
                    />
                </div>

                <div className={styles.inputGroup}>
                    <div style={{ position: "relative" }}>
                        <input
                            id="password"
                            type={showPassword ? "text" : "password"}
                            className={styles.input}
                            placeholder="Password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            disabled={isLoading}
                            required
                            style={{ paddingRight: "40px", width: "100%" }}
                        />
                        <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            style={{ position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", display: "flex", padding: "4px" }}
                        >
                            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>
                    <div className={styles.forgotPasswordText}>
                        Forgot password? Use Google to sign in.
                    </div>
                </div>

                <button type="submit" className={styles.submitBtn} disabled={isLoading}>
                    {isLoading ? "Authenticating..." : "Sign In"}
                </button>
            </form>

            {/* Divider */}
            <div className={styles.divider}>
                <span>or</span>
            </div>

            {/* Google OAuth Button */}
            <button
                type="button"
                className={styles.googleBtn}
                onClick={handleGoogleLogin}
                disabled={isLoading}
            >
                <svg className={styles.googleIcon} viewBox="0 0 24 24" width="20" height="20">
                    <path
                        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                        fill="#4285F4"
                    />
                    <path
                        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                        fill="#34A853"
                    />
                    <path
                        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                        fill="#FBBC05"
                    />
                    <path
                        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                        fill="#EA4335"
                    />
                </svg>
                Continue with Google
            </button>

            <div className={styles.footer}>
                Don&apos;t have an account? <Link href="/signup" className={styles.link}>Sign Up here</Link>
            </div>
        </AuthLayout>
    );
}
