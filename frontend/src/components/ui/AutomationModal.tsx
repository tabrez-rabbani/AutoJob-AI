/**
 * AutoJob AI — Automation Modal (Premium Horizontal Layout)
 * Modified to match the strict UI specifications from the screenshot.
 */

"use client";

import { useState, useRef, useEffect } from "react";
import { jobsApi, authApi, automationApi } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import type { AutoApplyResponse, SSEProgressEvent } from "@/lib/api";
import styles from "./AutomationModal.module.css";
import { X, CheckCircle, AlertTriangle, Loader2, Upload, FileText, Sparkles, Linkedin, Briefcase } from "lucide-react";

interface AutomationModalProps {
    isOpen: boolean;
    onClose: () => void;
    onComplete: () => void;
}

type ModalStep = "form" | "running" | "results";

export default function AutomationModal({ isOpen, onClose, onComplete }: AutomationModalProps) {
    const { user, refreshUser } = useAuth();
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Form state
    const [linkedinEmail, setLinkedinEmail] = useState("");
    const [linkedinPassword, setLinkedinPassword] = useState("");
    const [keywords, setKeywords] = useState("");
    const [location, setLocation] = useState("");
    const [country, setCountry] = useState("India");
    const [phone, setPhone] = useState("");
    const [yearsOfExperience, setYearsOfExperience] = useState("");
    const [currentCtc, setCurrentCtc] = useState("");
    const [expectedCtc, setExpectedCtc] = useState("");
    const [noticePeriodDays, setNoticePeriodDays] = useState("");
    const [maxApplications, setMaxApplications] = useState(5);
    const [delaySeconds, setDelaySeconds] = useState(15);
    const [dryRun, setDryRun] = useState(true);
    const [scanMode, setScanMode] = useState<"job_search" | "feed_scanner">("job_search");
    const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(["linkedin"]);
    const [naukriEmail, setNaukriEmail] = useState("");
    const [naukriPassword, setNaukriPassword] = useState("");

    // Auto-fill from user's Settings profile
    useEffect(() => {
        if (user) {
            // Pre-fill keywords from preferred roles (join all roles as comma-separated)
            if (user.preferred_roles?.length && !keywords) {
                setKeywords(user.preferred_roles.join(", "));
            }
            // Pre-fill location from preferred locations (join all as comma-separated)
            if (user.preferred_locations?.length && !location) {
                setLocation(user.preferred_locations.join(", "));
            }
            // Pre-fill years of experience
            if (user.experience_years !== undefined && user.experience_years !== null && !yearsOfExperience) {
                setYearsOfExperience(user.experience_years.toString());
            }
            if (user.current_ctc !== undefined && user.current_ctc !== null && !currentCtc) {
                setCurrentCtc(user.current_ctc.toString());
            }
            if (user.expected_ctc !== undefined && user.expected_ctc !== null && !expectedCtc) {
                setExpectedCtc(user.expected_ctc.toString());
            }
            if (user.notice_period_days !== undefined && user.notice_period_days !== null && !noticePeriodDays) {
                setNoticePeriodDays(user.notice_period_days.toString());
            }
            // Pre-fill country from Settings
            if (user.preferred_country) {
                setCountry(user.preferred_country);
            }
        }
    }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

    // Auto-update max applications and delay based on selected platforms
    useEffect(() => {
        if (selectedPlatforms.includes("naukri") && !selectedPlatforms.includes("linkedin")) {
            setMaxApplications(25);
            setDelaySeconds(7);
        } else if (selectedPlatforms.includes("linkedin")) {
            setMaxApplications(10);
            setDelaySeconds(15);
        }
        // Feed Scanner is LinkedIn-only — reset to job_search if LinkedIn deselected
        if (!selectedPlatforms.includes("linkedin") && scanMode === "feed_scanner") {
            setScanMode("job_search");
        }
    }, [selectedPlatforms]);

    // Resume state
    const [resumeFile, setResumeFile] = useState<File | null>(null);
    const [uploading, setUploading] = useState(false);
    const [extracting, setExtracting] = useState(false);

    // UI state
    const [step, setStep] = useState<ModalStep>("form");
    const [error, setError] = useState("");
    const [results, setResults] = useState<AutoApplyResponse | null>(null);
    const [aiSummary, setAiSummary] = useState("");

    // SSE progress state
    const [progress, setProgress] = useState<SSEProgressEvent | null>(null);
    const [taskId, setTaskId] = useState<string | null>(null);

    const hasResume = !!(user?.resume_url || resumeFile);

    const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const ext = file.name.split(".").pop()?.toLowerCase();
        if (!["pdf", "docx", "doc"].includes(ext || "")) {
            setError("Only PDF and DOCX files are allowed.");
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            setError("File too large. Maximum size is 5 MB.");
            return;
        }

        setError("");
        setUploading(true);

        try {
            // Step 1: Upload resume to backend
            await authApi.uploadResume(file);
            setResumeFile(file);
            setUploading(false);

            // Step 2: AI extract profile from resume → save to Settings
            setExtracting(true);
            try {
                const profile = await authApi.extractResumeProfile();

                // Save extracted data to user profile (syncs with Settings page)
                await authApi.updateProfile({
                    full_name: profile.full_name || undefined,
                    experience_years: profile.experience_years || undefined,
                    skills: profile.skills?.length ? profile.skills : undefined,
                    preferred_roles: profile.preferred_roles?.length ? profile.preferred_roles : undefined,
                });

                // Auto-fill modal fields from extracted data
                if (profile.preferred_roles?.length && !keywords.trim()) {
                    setKeywords(profile.preferred_roles.join(", "));
                }

                // Show AI summary to user
                const skillCount = profile.skills?.length || 0;
                const roleCount = profile.preferred_roles?.length || 0;
                setAiSummary(`✨ Found ${skillCount} skills, ${roleCount} roles — Keywords auto-filled!`);
            } catch {
                // AI extraction failed — resume still uploaded, just no auto-fill
                setAiSummary("");
            } finally {
                setExtracting(false);
            }

            await refreshUser();
        } catch (err: any) {
            setError(err?.message || "Failed to upload resume.");
            setUploading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (!selectedPlatforms.includes("linkedin") && !selectedPlatforms.includes("naukri")) {
            setError("Please select at least one platform.");
            return;
        }
        if (selectedPlatforms.includes("linkedin") && !user?.linkedin_configured && (!linkedinEmail || !linkedinPassword)) {
            setError("Please enter your LinkedIn credentials or save them in Settings.");
            return;
        }
        if (selectedPlatforms.includes("naukri") && !user?.naukri_configured && (!naukriEmail || !naukriPassword)) {
            setError("Please enter your Naukri credentials or save them in Settings.");
            return;
        }

        if (scanMode === "job_search" && !keywords.trim()) {
            setError("Please enter job search keywords (e.g. 'React Developer').");
            return;
        }

        if (!hasResume) {
            setError("Please upload your resume before running automation.");
            return;
        }

        if (scanMode === "feed_scanner" && !user?.smtp_configured) {
            setError("Please configure your Email Settings in the Settings page first.");
            return;
        }

        setError("");
        setStep("running");

        try {
            // Auto-sync Years of Experience back to user profile (Settings)
            if (yearsOfExperience && !isNaN(Number(yearsOfExperience))) {
                try {
                    await authApi.updateProfile({ experience_years: Number(yearsOfExperience) });
                } catch {
                    // Silent — experience sync is optional
                }
            }
            // Auto-sync CTC and Notice Period
            try {
                const profileUpdates: Record<string, any> = {};
                let hasUpdates = false;
                if (currentCtc && !isNaN(Number(currentCtc))) { profileUpdates.current_ctc = Number(currentCtc); hasUpdates = true; }
                if (expectedCtc && !isNaN(Number(expectedCtc))) { profileUpdates.expected_ctc = Number(expectedCtc); hasUpdates = true; }
                if (noticePeriodDays && !isNaN(Number(noticePeriodDays))) { profileUpdates.notice_period_days = Number(noticePeriodDays); hasUpdates = true; }
                
                if (hasUpdates) {
                    await authApi.updateProfile(profileUpdates);
                }
            } catch {
                // Silent
            }

            let response;
            if (scanMode === "job_search") {
                response = await automationApi.start({
                    linkedin_email: linkedinEmail || undefined,
                    linkedin_password: linkedinPassword || undefined,
                    naukri_email: naukriEmail || undefined,
                    naukri_password: naukriPassword || undefined,
                    platforms: selectedPlatforms,
                    keywords: keywords.trim(),
                    location: location.trim(),
                    country,
                    phone,
                    max_applications: maxApplications,
                    delay_seconds: delaySeconds,
                    dry_run: dryRun,
                });
            } else {
                response = await automationApi.startFeedScan({
                    linkedin_email: linkedinEmail || undefined,
                    linkedin_password: linkedinPassword || undefined,
                    max_emails: maxApplications,
                    dry_run: dryRun,
                });
            }

            if (response.status === "error") {
                setError(response.message);
                setStep("form");
                return;
            }

            setTaskId(response.task_id);
            // The useEffect will hook up the SSE stream now
        } catch (err: any) {
            setError(err?.message || "Automation failed to start. Check your credentials.");
            setStep("form");
        }
    };

    // ── SSE Stream Effect ─────────────────────────────
    useEffect(() => {
        if (step !== "running" || !taskId) return;

        const eventSource = new EventSource(automationApi.getStreamUrl(taskId));

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data) as SSEProgressEvent;
                setProgress(data);

                if (data.stage === "done" && data.result) {
                    setResults(data.result);
                    setStep("results");
                    eventSource.close();
                    onComplete();
                } else if (data.stage === "error") {
                    setError(data.message || "Automation background task failed.");
                    setStep("form");
                    eventSource.close();
                }
            } catch {
                // SSE parse error — skip this message
            }
        };

        eventSource.onerror = () => {
            // EventSource auto-reconnects on temporary network drops
        };

        return () => {
            eventSource.close();
        };
    }, [step, taskId, onComplete]);

    const handleClose = () => {
        // Reset all form state (keywords/location reset to Settings defaults)
        setLinkedinEmail("");
        setLinkedinPassword("");
        setKeywords(user?.preferred_roles?.join(", ") || "");
        setLocation(user?.preferred_locations?.join(", ") || "");
        setCountry(user?.preferred_country || "India");
        setYearsOfExperience(user?.experience_years?.toString() || "");
        setCurrentCtc(user?.current_ctc?.toString() || "");
        setExpectedCtc(user?.expected_ctc?.toString() || "");
        setNoticePeriodDays(user?.notice_period_days?.toString() || "");
        setPhone("");
        setMaxApplications(5);
        setDelaySeconds(60);
        setDryRun(true);
        setScanMode("job_search");
        setSelectedPlatforms(["linkedin"]);
        setNaukriEmail("");
        setNaukriPassword("");
        setResumeFile(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }

        // Reset UI state
        setStep("form");
        setError("");
        setResults(null);
        setProgress(null);
        setTaskId(null);
        onClose();
    };

    if (!isOpen) return null;

    // The backend saves files as `resumes/<user_id>_<uuid>.ext`. 
    // This logic extracts just the extension, or uses a clean generic name if no file is selected.
    const extractCleanFilename = (url: string) => {
        const fullFileName = url.split(/[/\\]/).pop() || "resume.pdf";
        // Attempt to clean up <user_id>_<uuid>.pdf -> We don't have the original name stored in DB,
        // so if there is an active `user.resume_url` but no client `resumeFile.name`, we just show a friendly name
        const ext = fullFileName.split('.').pop() || 'pdf';
        return `My_Resume.${ext}`;
    };

    const resumeDisplayName = resumeFile?.name || (user?.resume_url ? extractCleanFilename(user.resume_url) : null);

    return (
        <div className={styles.overlay} onClick={handleClose}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()}>

                <div className={styles.modalInner}>
                    <div className={styles.header}>
                        <div className={styles.headerTitle}>
                            <h2>Automation Configuration</h2>
                        </div>
                        <div className={styles.headerActions}>
                            {step === "form" && (
                                <button type="button" className={styles.submitBtn} onClick={handleSubmit} disabled={!hasResume || selectedPlatforms.length === 0}>
                                    Start Run
                                </button>
                            )}
                            <button className={styles.closeBtn} onClick={handleClose}>
                                <X size={22} />
                            </button>
                        </div>
                    </div>

                    {step === "form" && (
                        <form className={styles.form} onSubmit={handleSubmit} id="automationForm">
                            {error && (
                                <div className={styles.errorBanner}>
                                    <AlertTriangle size={16} />
                                    {error}
                                </div>
                            )}

                            {/* Mode Toggle — Only shown when LinkedIn is selected (Feed Scanner is LinkedIn-only) */}
                            {selectedPlatforms.includes("linkedin") && (
                                <div className={styles.modeWrapper}>
                                    <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-muted)", whiteSpace: "nowrap" }}>Mode:</span>
                                    <div style={{ display: "flex", gap: "8px", background: "rgba(255,255,255,0.04)", padding: "4px", borderRadius: "10px", border: "1px solid var(--border)" }}>
                                        <button
                                            type="button"
                                            style={{
                                                padding: "7px 18px", borderRadius: "8px", border: "none",
                                                background: scanMode === "job_search" ? "#59a6cb" : "transparent",
                                                color: scanMode === "job_search" ? "#fff" : "var(--text-muted)",
                                                fontWeight: scanMode === "job_search" ? 600 : 400,
                                                fontSize: "13px",
                                                cursor: "pointer", transition: "all 0.2s",
                                                boxShadow: scanMode === "job_search" ? "0 2px 8px rgba(89, 166, 203, 0.4)" : "none",
                                            }}
                                            onClick={() => setScanMode("job_search")}
                                        >
                                            Job Search
                                        </button>
                                        <button
                                            type="button"
                                            style={{
                                                padding: "7px 18px", borderRadius: "8px", border: "none",
                                                background: scanMode === "feed_scanner" ? "#59a6cb" : "transparent",
                                                color: scanMode === "feed_scanner" ? "#fff" : "var(--text-muted)",
                                                fontWeight: scanMode === "feed_scanner" ? 600 : 400,
                                                fontSize: "13px",
                                                cursor: "pointer", transition: "all 0.2s",
                                                boxShadow: scanMode === "feed_scanner" ? "0 2px 8px rgba(89, 166, 203, 0.4)" : "none",
                                            }}
                                            onClick={() => setScanMode("feed_scanner")}
                                        >
                                            Feed Scanner <span style={{ fontSize: "10px", opacity: 0.7, marginLeft: "4px" }}>(LinkedIn Only)</span>
                                        </button>
                                    </div>
                                </div>
                            )}

                            {scanMode === "feed_scanner" && selectedPlatforms.includes("linkedin") && (
                                <div style={{ marginBottom: "16px" }}>
                                    <div style={{ fontSize: "13px", color: user?.smtp_configured ? "#10b981" : "var(--danger)", padding: "8px 12px", background: "rgba(0,0,0,0.15)", borderRadius: "8px", marginBottom: "10px" }}>
                                        {user?.smtp_configured ? "✅ SMTP Configured & Ready" : "❌ Email Settings missing! Setup in Dashboard → Settings."}
                                    </div>
                                    <div style={{ padding: "12px", background: "rgba(99, 102, 241, 0.06)", borderRadius: "8px", border: "1px solid rgba(99, 102, 241, 0.15)" }}>
                                        <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "8px" }}>🔗 LinkedIn Credentials (required for Feed Scanner)</div>
                                        <div className={styles.credentialsGrid}>
                                            <input
                                                type="email"
                                                placeholder="LinkedIn Email"
                                                value={linkedinEmail}
                                                onChange={(e) => setLinkedinEmail(e.target.value)}
                                                className={styles.input}
                                                style={{ fontSize: "13px" }}
                                            />
                                            <input
                                                type="password"
                                                placeholder="LinkedIn Password"
                                                value={linkedinPassword}
                                                onChange={(e) => setLinkedinPassword(e.target.value)}
                                                className={styles.input}
                                                style={{ fontSize: "13px" }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Platform Selection (only for job_search mode) */}
                            {scanMode === "job_search" && (
                                <div className={styles.platformsSection}>
                                    <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px", fontSize: "15px" }}>Select Platforms</div>
                                    <div className={styles.platformGrid}>
                                        <label style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", padding: "10px 16px", borderRadius: "8px", border: `1px solid ${selectedPlatforms.includes("linkedin") ? "rgba(99, 102, 241, 0.6)" : "var(--border-default)"}`, background: selectedPlatforms.includes("linkedin") ? "rgba(99, 102, 241, 0.1)" : "var(--card-bg)", transition: "all 0.2s" }}>
                                            <input
                                                type="checkbox"
                                                checked={selectedPlatforms.includes("linkedin")}
                                                onChange={(e) => {
                                                    setSelectedPlatforms(prev =>
                                                        e.target.checked ? [...prev, "linkedin"] : prev.filter(p => p !== "linkedin")
                                                    );
                                                }}
                                                style={{ accentColor: "#59A6CB", width: "16px", height: "16px", cursor: "pointer" }}
                                            />
                                            <span style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 600, color: selectedPlatforms.includes("linkedin") ? "#ffffff" : "var(--text-primary)" }}>
                                                <Linkedin size={16} strokeWidth={2.5} color={selectedPlatforms.includes("linkedin") ? "#59A6CB" : "var(--text-secondary)"} />
                                                LinkedIn
                                            </span>
                                            <span style={{ fontSize: "12px", color: "var(--text-muted)", marginLeft: "2px" }}>(10/day)</span>
                                        </label>

                                        <label style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", padding: "10px 16px", borderRadius: "8px", border: `1px solid ${selectedPlatforms.includes("naukri") ? "rgba(16, 185, 129, 0.6)" : "var(--border-default)"}`, background: selectedPlatforms.includes("naukri") ? "rgba(16, 185, 129, 0.1)" : "var(--card-bg)", transition: "all 0.2s" }}>
                                            <input
                                                type="checkbox"
                                                checked={selectedPlatforms.includes("naukri")}
                                                onChange={(e) => {
                                                    setSelectedPlatforms(prev =>
                                                        e.target.checked ? [...prev, "naukri"] : prev.filter(p => p !== "naukri")
                                                    );
                                                }}
                                                style={{ accentColor: "#10b981", width: "16px", height: "16px", cursor: "pointer" }}
                                            />
                                            <span style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 600, color: selectedPlatforms.includes("naukri") ? "#ffffff" : "var(--text-primary)" }}>
                                                <Briefcase size={16} strokeWidth={2.5} color={selectedPlatforms.includes("naukri") ? "#10b981" : "var(--text-secondary)"} />
                                                Naukri.com
                                            </span>
                                            <span style={{ fontSize: "12px", color: "var(--text-muted)", marginLeft: "2px" }}>(25/day)</span>
                                        </label>
                                    </div>

                                    {/* LinkedIn Credentials (only when LinkedIn selected and not configured in Settings) */}
                                    {selectedPlatforms.includes("linkedin") && !user?.linkedin_configured && (
                                        <div className={styles.credsSectionLinkedin}>
                                            <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px", letterSpacing: "0.2px" }}>LinkedIn Credentials</div>
                                            <div className={styles.credentialsGrid}>
                                                <input
                                                    type="email"
                                                    placeholder="LinkedIn Email"
                                                    value={linkedinEmail}
                                                    onChange={(e) => setLinkedinEmail(e.target.value)}
                                                    className={styles.input}
                                                    style={{ fontSize: "13px" }}
                                                />
                                                <input
                                                    type="password"
                                                    placeholder="LinkedIn Password"
                                                    value={linkedinPassword}
                                                    onChange={(e) => setLinkedinPassword(e.target.value)}
                                                    className={styles.input}
                                                    style={{ fontSize: "13px" }}
                                                />
                                            </div>
                                        </div>
                                    )}
                                    {selectedPlatforms.includes("linkedin") && user?.linkedin_configured && (
                                        <div style={{ marginTop: "10px", fontSize: "12px", color: "#10b981", padding: "8px 12px", background: "rgba(16, 185, 129, 0.06)", borderRadius: "6px" }}>✅ LinkedIn credentials saved in Settings</div>
                                    )}

                                    {/* Naukri Credentials (only when Naukri selected) */}
                                    {selectedPlatforms.includes("naukri") && !user?.naukri_configured && (
                                        <div className={styles.credsSectionNaukri}>
                                            <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)", marginBottom: "12px", letterSpacing: "0.2px" }}>Naukri.com Credentials</div>
                                            <div className={styles.credentialsGrid}>
                                                <input
                                                    type="email"
                                                    placeholder="Naukri Email"
                                                    value={naukriEmail}
                                                    onChange={(e) => setNaukriEmail(e.target.value)}
                                                    className={styles.input}
                                                    style={{ fontSize: "13px" }}
                                                />
                                                <input
                                                    type="password"
                                                    placeholder="Naukri Password"
                                                    value={naukriPassword}
                                                    onChange={(e) => setNaukriPassword(e.target.value)}
                                                    className={styles.input}
                                                    style={{ fontSize: "13px" }}
                                                />
                                            </div>
                                        </div>
                                    )}
                                    {selectedPlatforms.includes("naukri") && user?.naukri_configured && (
                                        <div style={{ marginTop: "10px", fontSize: "12px", color: "#10b981", padding: "8px 12px", background: "rgba(16, 185, 129, 0.06)", borderRadius: "6px" }}>✅ Naukri credentials saved in Settings</div>
                                    )}
                                </div>
                            )}

                            {/* Only show rest of form when at least one platform is selected */}
                            {selectedPlatforms.length === 0 && (
                                <div style={{ textAlign: "center", padding: "30px 20px", color: "var(--text-muted)", fontSize: "14px", opacity: 0.7 }}>
                                    ☝️ Please select at least one platform above to configure automation.
                                </div>
                            )}

                            {selectedPlatforms.length > 0 && (
                            <>
                            {/* Banner Status (Dry Run Toggle) */}
                            <div className={styles.toggleRow}>
                                <div className={styles.toggleLabelWrap}>
                                    <div className={styles.toggleLabel}>Live Mode :</div>
                                    <label className={styles.toggleSwitch}>
                                        <input
                                            type="checkbox"
                                            checked={!dryRun} /* Invert so "on" = live mode */
                                            onChange={(e) => setDryRun(!e.target.checked)}
                                        />
                                        <span className={styles.slider}></span>
                                    </label>
                                </div>
                                <span className={styles.fieldHint}>
                                    {!dryRun
                                        ? "(ON: Real applications will be submitted)"
                                        : "(OFF default: Testing Mode. Bot will only find jobs but NOT apply)"}
                                </span>
                            </div>

                            {/* ── Resume Upload (TOP — auto-fills other fields) ── */}
                            <div className={styles.inputGroup}>
                                <label className={styles.label}>Resume Upload :</label>
                                <div className={styles.inputContainer}>
                                    <div
                                        className={`${styles.uploadZone} ${hasResume ? styles.uploadZoneSuccess : ""}`}
                                        onClick={() => !uploading && !extracting && fileInputRef.current?.click()}
                                    >
                                        <input
                                            ref={fileInputRef}
                                            type="file"
                                            accept=".pdf,.docx,.doc"
                                            className={styles.fileInput}
                                            onChange={handleFileSelect}
                                        />
                                        {uploading ? (
                                            <>
                                                <Loader2 size={20} className={styles.spinner} />
                                                <span>Uploading...</span>
                                            </>
                                        ) : extracting ? (
                                            <>
                                                <Sparkles size={20} className={styles.spinner} />
                                                <span>🧠 AI analyzing resume...</span>
                                            </>
                                        ) : hasResume ? (
                                            <>
                                                <FileText size={20} className={styles.uploadIconSuccess} />
                                                <span className={styles.uploadFileName}>{resumeDisplayName}</span>
                                            </>
                                        ) : (
                                            <>
                                                <Upload size={20} className={styles.uploadIcon} />
                                                <span>Click to upload PDF or DOCX</span>
                                            </>
                                        )}
                                    </div>
                                    {aiSummary && (
                                        <span className={styles.fieldHint} style={{ color: '#10b981' }}>{aiSummary}</span>
                                    )}
                                </div>
                            </div>



                            {scanMode === "job_search" && (
                                <>
                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Job Keywords * :</label>
                                        <div className={styles.inputContainer}>
                                            <input
                                                type="text"
                                                className={styles.input}
                                                placeholder="e.g. React Developer, Python Backend"
                                                value={keywords}
                                                onChange={(e) => setKeywords(e.target.value)}
                                                required
                                            />
                                            <span className={styles.fieldHint}>What job role to search for</span>
                                        </div>
                                    </div>

                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Location :</label>
                                        <div className={styles.inputContainer}>
                                            <input
                                                type="text"
                                                className={styles.input}
                                                placeholder="e.g. Bangalore, Remote, India"
                                                value={location}
                                                onChange={(e) => setLocation(e.target.value)}
                                            />
                                            <span className={styles.fieldHint}>Leave empty for all locations</span>
                                        </div>
                                    </div>

                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Years of Experience :</label>
                                        <div className={styles.inputContainer}>
                                            <input
                                                type="number"
                                                min="0"
                                                step="0.5"
                                                className={styles.input}
                                                placeholder="e.g. 2.5"
                                                value={yearsOfExperience}
                                                onChange={(e) => setYearsOfExperience(e.target.value)}
                                            />
                                            <span className={styles.fieldHint}>Will auto-sync to your Settings</span>
                                        </div>
                                    </div>

                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Current CTC (in LPA) :</label>
                                        <div className={styles.inputContainer}>
                                            <input
                                                type="number"
                                                min="0"
                                                step="0.1"
                                                className={styles.input}
                                                placeholder="e.g. 3.5"
                                                value={currentCtc}
                                                onChange={(e) => setCurrentCtc(e.target.value)}
                                            />
                                            <span className={styles.fieldHint}>Will auto-sync to your Settings</span>
                                        </div>
                                    </div>

                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Expected CTC (in LPA) :</label>
                                        <div className={styles.inputContainer}>
                                            <input
                                                type="number"
                                                min="0"
                                                step="0.1"
                                                className={styles.input}
                                                placeholder="e.g. 6"
                                                value={expectedCtc}
                                                onChange={(e) => setExpectedCtc(e.target.value)}
                                            />
                                            <span className={styles.fieldHint}>Will auto-sync to your Settings</span>
                                        </div>
                                    </div>

                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Notice Period (in days) :</label>
                                        <div className={styles.inputContainer}>
                                            <input
                                                type="number"
                                                min="0"
                                                max="180"
                                                className={styles.input}
                                                placeholder="e.g. 0 or 30"
                                                value={noticePeriodDays}
                                                onChange={(e) => setNoticePeriodDays(e.target.value)}
                                            />
                                            <span className={styles.fieldHint}>Will auto-sync to your Settings</span>
                                        </div>
                                    </div>

                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Country :</label>
                                        <div className={styles.inputContainer}>
                                            <select
                                                className={styles.input}
                                                value={country}
                                                onChange={(e) => setCountry(e.target.value)}
                                            >
                                                <option value="India">🇮🇳 India</option>
                                                <option value="USA">🇺🇸 USA</option>
                                                <option value="UK">🇬🇧 UK</option>
                                                <option value="Canada">🇨🇦 Canada</option>
                                                <option value="Germany">🇩🇪 Germany</option>
                                                <option value="Australia">🇦🇺 Australia</option>
                                                <option value="Singapore">🇸🇬 Singapore</option>
                                                <option value="UAE">🇦🇪 UAE</option>
                                                <option value="Remote">Remote / Worldwide</option>
                                            </select>
                                            <span className={styles.fieldHint}>Only jobs from this country will be searched</span>
                                        </div>
                                    </div>

                                    <div className={styles.inputGroup}>
                                        <label className={styles.label}>Phone Number :</label>
                                        <div className={styles.inputContainer}>
                                            <input
                                                type="tel"
                                                className={styles.input}
                                                placeholder="Phone Number"
                                                value={phone}
                                                onChange={(e) => setPhone(e.target.value)}
                                            />
                                        </div>
                                    </div>
                                </>
                            )}

                            <div className={styles.inputGroup}>
                                <label className={styles.label}>
                                    {scanMode === "job_search" ? "Max Applications :" : "Max Emails (Daily Limit: 10) :"}
                                </label>
                                <div className={styles.inputContainer}>
                                    <input
                                        type="number"
                                        className={styles.input}
                                        min={1}
                                        max={scanMode === "job_search" ? (selectedPlatforms.includes("naukri") ? 25 : 10) : 10}
                                        value={maxApplications}
                                        onChange={(e) => setMaxApplications(Number(e.target.value))}
                                    />
                                    <span className={styles.fieldHint}>
                                        {scanMode === "job_search"
                                            ? `How many jobs to apply in one run (Daily limit: ${selectedPlatforms.includes("linkedin") ? "LinkedIn 10" : ""}${selectedPlatforms.includes("linkedin") && selectedPlatforms.includes("naukri") ? " | " : ""}${selectedPlatforms.includes("naukri") ? "Naukri 25" : ""}/day)`
                                            : "Emails to send (Max 10 per day to avoid spam)"}
                                    </span>
                                </div>
                            </div>

                            <div className={styles.inputGroup}>
                                <label className={styles.label}>Delay (Seconds) :</label>
                                <div className={styles.inputContainer}>
                                    <input
                                        type="number"
                                        className={styles.input}
                                        min={selectedPlatforms.includes("linkedin") ? 15 : 5}
                                        max={300}
                                        value={delaySeconds}
                                        onChange={(e) => setDelaySeconds(Number(e.target.value))}
                                    />
                                    <span className={styles.fieldHint}>
                                        Wait time between each application ({selectedPlatforms.includes("linkedin") ? "15" : "5"}–300s)
                                    </span>
                                </div>
                            </div>
                            </>
                            )}


                        </form>
                    )}

                    {step === "running" && (
                        <div className={styles.runningState}>
                            <Loader2 size={40} className={styles.spinner} />
                            <h3>{progress?.message || "Starting Automation Pipeline..."}</h3>
                            
                            {progress && (
                                <div className={styles.progressStatsRow}>
                                    <div className={styles.progressStat}>
                                        <span>Scraped</span>
                                        <strong>{progress.jobs_scraped || 0}</strong>
                                    </div>
                                    <div className={styles.progressStat}>
                                        <span>Qualified</span>
                                        <strong>{progress.jobs_qualified || 0}</strong>
                                    </div>
                                    <div className={styles.progressStat}>
                                        <span>Applied</span>
                                        <strong style={{ color: '#10b981' }}>{progress.jobs_applied || 0}</strong>
                                    </div>
                                    <div className={styles.progressStat}>
                                        <span>Failed</span>
                                        <strong style={{ color: '#ef4444' }}>{progress.jobs_failed || 0}</strong>
                                    </div>
                                </div>
                            )}

                            <p className={styles.runningHint}>
                                You can safely close this window. Automation will continue in the background.
                            </p>
                        </div>
                    )}

                    {step === "results" && results && (
                        <div className={styles.resultsState}>
                            <CheckCircle size={40} className={styles.successIcon} />
                            <h3>Automation Complete!</h3>
                            <p className={styles.resultMessage}>{results.message}</p>

                            <div className={styles.statsRow}>
                                <div className={styles.statItem}>
                                    <span className={styles.statValue}>{results.total_attempted}</span>
                                    <span className={styles.statLabel}>Attempted</span>
                                </div>
                                <div className={styles.statItem}>
                                    <span className={styles.statValue}>{results.applied}</span>
                                    <span className={styles.statLabel}>Applied</span>
                                </div>
                                <div className={styles.statItem}>
                                    <span className={styles.statValue}>{results.skipped}</span>
                                    <span className={styles.statLabel}>Skipped</span>
                                </div>
                            </div>

                            <button className={styles.submitBtn} style={{ margin: "0 auto" }} onClick={handleClose}>
                                Close
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
