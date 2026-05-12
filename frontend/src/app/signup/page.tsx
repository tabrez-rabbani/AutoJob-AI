/**
 * AutoJob AI — Signup Page
 * Split-screen layout with email/password registration + Google OAuth.
 */

"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { config } from "@/lib/config";
import AuthLayout from "@/components/layout/AuthLayout";
import { Eye, EyeOff, Check, X as XIcon } from "lucide-react";
import styles from "@/styles/auth.module.css";

/** Password strength calculator */
function getPasswordStrength(pwd: string) {
    let score = 0;
    const checks = {
        length: pwd.length >= 8,
        uppercase: /[A-Z]/.test(pwd),
        lowercase: /[a-z]/.test(pwd),
        number: /[0-9]/.test(pwd),
        special: /[^A-Za-z0-9]/.test(pwd),
    };
    if (checks.length) score++;
    if (checks.uppercase) score++;
    if (checks.lowercase) score++;
    if (checks.number) score++;
    if (checks.special) score++;

    let label = "";
    let color = "";
    if (score <= 1) { label = "Very Weak"; color = "#ef4444"; }
    else if (score === 2) { label = "Weak"; color = "#f97316"; }
    else if (score === 3) { label = "Fair"; color = "#eab308"; }
    else if (score === 4) { label = "Good"; color = "#22c55e"; }
    else { label = "Strong"; color = "#10b981"; }

    return { score, checks, label, color, percent: (score / 5) * 100 };
}

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

export default function SignupPage() {
    const router = useRouter();

    const [fullName, setFullName] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirmPassword, setConfirmPassword] = useState("");
    
    const [showPassword, setShowPassword] = useState(false);
    const [showConfirmPassword, setShowConfirmPassword] = useState(false);

    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState("");

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!fullName || !email || !password || !confirmPassword) {
            setError("Please fill in all fields.");
            return;
        }

        if (password !== confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        if (password.length < 8) {
            setError("Password must be at least 8 characters.");
            return;
        }

        const strength = getPasswordStrength(password);
        if (strength.score < 3) {
            setError("Password is too weak. Please add uppercase, lowercase, numbers, or special characters.");
            return;
        }

        setIsLoading(true);
        setError("");

        try {
            await authApi.signup({ email, password, full_name: fullName.trim() });
            router.push("/login?registered=true");
        } catch (err: any) {
            setError(err?.message || "Failed to create account. Email may already exist.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleGoogleSignup = () => {
        if (!config.googleClientId) {
            setError("Google login is not configured.");
            return;
        }
        window.location.href = getGoogleOAuthUrl();
    };

    return (
        <AuthLayout>
            <div className={styles.header}>
                <h2 className={styles.title}>Create Account</h2>
                <p className={styles.subtitle}>Get started with your free account.</p>
            </div>

            <form className={styles.form} onSubmit={handleSubmit}>
                {error && <div className={styles.serverError}>{error}</div>}

                <div className={styles.inputGroup}>
                    <input
                        type="text"
                        className={styles.input}
                        placeholder="Full Name"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        disabled={isLoading}
                        required
                    />
                </div>

                <div className={styles.inputGroup}>
                    <input
                        type="email"
                        className={styles.input}
                        placeholder="Email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        disabled={isLoading}
                        required
                    />
                </div>

                <div className={styles.inputGroup}>
                    <div style={{ position: "relative" }}>
                        <input
                            type={showPassword ? "text" : "password"}
                            className={styles.input}
                            placeholder="Password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            disabled={isLoading}
                            minLength={8}
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

                    {/* Password Strength Meter */}
                    {password.length > 0 && (() => {
                        const s = getPasswordStrength(password);
                        return (
                            <div className={styles.strengthContainer}>
                                <div className={styles.strengthBarBg}>
                                    <div
                                        className={styles.strengthBarFill}
                                        style={{ width: `${s.percent}%`, background: s.color }}
                                    />
                                </div>
                                <span className={styles.strengthLabel} style={{ color: s.color }}>
                                    {s.label}
                                </span>
                                <div className={styles.strengthChecks}>
                                    {[
                                        [s.checks.length, "8+ characters"],
                                        [s.checks.uppercase, "Uppercase (A-Z)"],
                                        [s.checks.lowercase, "Lowercase (a-z)"],
                                        [s.checks.number, "Number (0-9)"],
                                        [s.checks.special, "Special (!@#$)"],
                                    ].map(([ok, text], i) => (
                                        <span key={i} className={styles.strengthCheck} style={{ color: ok ? "#22c55e" : "#94a3b8" }}>
                                            {ok ? <Check size={12} /> : <XIcon size={12} />}
                                            {text as string}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        );
                    })()}
                </div>

                <div className={styles.inputGroup}>
                    <div style={{ position: "relative" }}>
                        <input
                            type={showConfirmPassword ? "text" : "password"}
                            className={styles.input}
                            placeholder="Confirm Password"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            disabled={isLoading}
                            minLength={8}
                            required
                            style={{ paddingRight: "40px", width: "100%" }}
                        />
                        <button
                            type="button"
                            onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                            style={{ position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", display: "flex", padding: "4px" }}
                        >
                            {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>
                </div>

                <button type="submit" className={styles.submitBtn} disabled={isLoading}>
                    {isLoading ? "Creating..." : "Create Account"}
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
                onClick={handleGoogleSignup}
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
                Already have an account? <Link href="/login" className={styles.link}>Sign In here</Link>
            </div>
        </AuthLayout>
    );
}
