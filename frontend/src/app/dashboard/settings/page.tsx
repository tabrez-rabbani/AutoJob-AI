/**
 * AutoJob AI — Settings Page
 * Resume-first approach: Upload resume → AI auto-fills profile → User edits/saves.
 */

"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { authApi, ApiError } from "@/lib/api";
import {
    Loader, X, CheckCircle, AlertTriangle, Save, Sparkles, Info, Upload, Eye, EyeOff
} from "lucide-react";
import styles from "./settings.module.css";

export default function SettingsPage() {
    const { user, refreshUser } = useAuth();
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Profile form state
    const [fullName, setFullName] = useState("");
    const [experienceYears, setExperienceYears] = useState<number | "">("");
    const [currentCtc, setCurrentCtc] = useState<number | "">("");
    const [expectedCtc, setExpectedCtc] = useState<number | "">("");
    const [noticePeriodDays, setNoticePeriodDays] = useState<number | "">("")
    const [currentCity, setCurrentCity] = useState("");

    // Tag-based fields
    const [skills, setSkills] = useState<string[]>([]);
    const [newSkill, setNewSkill] = useState("");
    const [preferredRoles, setPreferredRoles] = useState<string[]>([]);
    const [newRole, setNewRole] = useState("");
    const [preferredLocations, setPreferredLocations] = useState<string[]>([]);
    const [newLocation, setNewLocation] = useState("");
    const [preferredCountry, setPreferredCountry] = useState("India");

    // SMTP / Email settings
    const [smtpEmail, setSmtpEmail] = useState("");
    const [smtpPassword, setSmtpPassword] = useState("");
    const [smtpHost, setSmtpHost] = useState("smtp.gmail.com");
    const [smtpPort, setSmtpPort] = useState(587);

    // Naukri.com credentials
    const [naukriEmail, setNaukriEmail] = useState("");
    const [naukriPassword, setNaukriPassword] = useState("");

    // LinkedIn credentials
    const [linkedinEmail, setLinkedinEmail] = useState("");
    const [linkedinPassword, setLinkedinPassword] = useState("");

    // Resume
    const [resumeUploading, setResumeUploading] = useState(false);
    const [uploadedFileName, setUploadedFileName] = useState<string | null>(null);
    const [extracting, setExtracting] = useState(false);

    // UI state
    const [saving, setSaving] = useState(false);
    const [successMsg, setSuccessMsg] = useState("");
    const [errorMsg, setErrorMsg] = useState("");
    
    // Password visibility state
    const [showSmtpPwd, setShowSmtpPwd] = useState(false);
    const [showNaukriPwd, setShowNaukriPwd] = useState(false);
    const [showLinkedinPwd, setShowLinkedinPwd] = useState(false);

    // Load current user data into form
    useEffect(() => {
        if (user) {
            setFullName(user.full_name || "");
            setExperienceYears(user.experience_years ?? "");
            setCurrentCtc(user.current_ctc ?? "");
            setExpectedCtc(user.expected_ctc ?? "");
            setNoticePeriodDays(user.notice_period_days ?? "");
            setSkills(user.skills || []);
            setPreferredRoles(user.preferred_roles || []);
            setPreferredLocations(user.preferred_locations || []);
            setPreferredCountry(user.preferred_country || "India");
            setCurrentCity(user.current_city || "");
            setSmtpEmail(user.smtp_email || "");
            setSmtpHost(user.smtp_host || "smtp.gmail.com");
            setSmtpPort(user.smtp_port || 587);
            setNaukriEmail(user.naukri_email || "");
            setLinkedinEmail(user.linkedin_email || "");
        }
    }, [user]);

    // ── Tag Helpers ──────────────────────────────
    const addTag = (
        value: string,
        list: string[],
        setList: (v: string[]) => void,
        setInput: (v: string) => void
    ) => {
        const trimmed = value.trim();
        if (trimmed && !list.includes(trimmed)) {
            setList([...list, trimmed]);
        }
        setInput("");
    };

    const removeTag = (
        index: number,
        list: string[],
        setList: (v: string[]) => void
    ) => {
        setList(list.filter((_, i) => i !== index));
    };

    const handleKeyDown = (
        e: React.KeyboardEvent,
        value: string,
        list: string[],
        setList: (v: string[]) => void,
        setInput: (v: string) => void
    ) => {
        if (e.key === "Enter") {
            e.preventDefault();
            addTag(value, list, setList, setInput);
        }
    };

    // ── Save Profile ─────────────────────────────
    const handleSave = async () => {
        setSaving(true);
        setErrorMsg("");
        setSuccessMsg("");

        try {
            await authApi.updateProfile({
                full_name: fullName,
                experience_years: experienceYears === "" ? null : Number(experienceYears),
                current_ctc: currentCtc === "" ? null : Number(currentCtc),
                expected_ctc: expectedCtc === "" ? null : Number(expectedCtc),
                notice_period_days: noticePeriodDays === "" ? null : Number(noticePeriodDays),
                skills: skills,
                preferred_roles: preferredRoles,
                preferred_locations: preferredLocations,
                preferred_country: preferredCountry,
                current_city: currentCity || undefined,
                smtp_email: smtpEmail || undefined,
                smtp_password: smtpPassword || undefined,
                smtp_host: smtpHost || undefined,
                smtp_port: smtpPort || undefined,
                naukri_email: naukriEmail || undefined,
                naukri_password: naukriPassword || undefined,
                linkedin_email: linkedinEmail || undefined,
                linkedin_password: linkedinPassword || undefined,
            });

            await refreshUser();
            setSuccessMsg("Profile updated successfully!");
            setTimeout(() => setSuccessMsg(""), 4000);
        } catch (err: any) {
            setErrorMsg(err?.message || "Failed to save profile.");
        } finally {
            setSaving(false);
        }
    };

    // ── Resume Upload + AI Auto-Fill ─────────────
    const handleResumeUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const ext = file.name.split(".").pop()?.toLowerCase();
        if (!["pdf", "docx", "doc"].includes(ext || "")) {
            setErrorMsg("Only PDF and DOCX files are allowed.");
            return;
        }
        if (file.size > 5 * 1024 * 1024) {
            setErrorMsg("File too large. Maximum size is 5 MB.");
            return;
        }

        // Step 1: Upload the file
        setResumeUploading(true);
        setErrorMsg("");

        try {
            const result = await authApi.uploadResume(file);
            setUploadedFileName(result.filename || file.name);
            await refreshUser();
        } catch (err: any) {
            setErrorMsg(err?.message || "Resume upload failed.");
            setResumeUploading(false);
            return;
        } finally {
            setResumeUploading(false);
            if (fileInputRef.current) fileInputRef.current.value = "";
        }

        // Step 2: AI Auto-Fill from resume
        setExtracting(true);
        setSuccessMsg("Resume uploaded! AI is analyzing your resume...");

        try {
            const profile = await authApi.extractResumeProfile();

            // Auto-fill fields from AI extraction
            if (profile.full_name) setFullName(profile.full_name);
            if (profile.experience_years) setExperienceYears(profile.experience_years);
            if (profile.skills?.length) setSkills(profile.skills);
            if (profile.preferred_roles?.length) setPreferredRoles(profile.preferred_roles);

            setSuccessMsg(`✨ AI filled your profile from resume! Found ${profile.skills?.length || 0} skills. Review and Save.`);
            setTimeout(() => setSuccessMsg(""), 8000);
        } catch (err: any) {
            // AI extraction failed — resume still uploaded, just no auto-fill
            setSuccessMsg("Resume uploaded! Auto-fill couldn't run, please fill fields manually.");
            setTimeout(() => setSuccessMsg(""), 5000);
        } finally {
            setExtracting(false);
        }
    };

    // Clean filename for display
    const resumeDisplayName = (() => {
        if (uploadedFileName) return uploadedFileName;
        if (!user?.resume_url) return null;
        const pathParts = user.resume_url.replace(/\\/g, "/").split("/");
        const serverFilename = pathParts[pathParts.length - 1] || "";
        const match = serverFilename.match(/_[a-f0-9]{8}(\.[a-z]+)$/i);
        return match ? `Resume${match[1]}` : serverFilename;
    })();

    const hasResume = !!user?.resume_url;

    if (!user) {
        return (
            <div className={styles.loadingState}>
                <Loader size={20} className={styles.spinner} />
                Loading settings...
            </div>
        );
    }

    return (
        <div className={styles.container}>


            {/* ══════════════════════════════════════════════ */}
            {/* ── STEP 1: Resume Upload (TOP — Primary) ──── */}
            {/* ══════════════════════════════════════════════ */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>
                            Upload Your Resume
                            <span className={styles.stepBadge}>Step 1</span>
                        </div>
                        <div className={styles.cardDescription}>
                            Upload your resume and AI will automatically fill your profile below
                        </div>
                    </div>
                </div>

                <input
                    type="file"
                    ref={fileInputRef}
                    className={styles.fileInput}
                    accept=".pdf,.docx,.doc"
                    onChange={handleResumeUpload}
                />

                <div
                    className={`${styles.resumeZone} ${hasResume ? styles.resumeZoneUploaded : ""}`}
                    onClick={() => !resumeUploading && !extracting && fileInputRef.current?.click()}
                >
                    <div className={styles.resumeIcon}>
                        {resumeUploading ? (
                            <Loader size={22} className={styles.spinner} />
                        ) : extracting ? (
                            <Sparkles size={22} className={styles.sparkle} />
                        ) : (
                            <Upload size={22} />
                        )}
                    </div>
                    <div className={styles.resumeInfo}>
                        {resumeUploading ? (
                            <div className={styles.resumeName}>Uploading resume...</div>
                        ) : extracting ? (
                            <>
                                <div className={styles.resumeName}>🧠 AI is reading your resume...</div>
                                <div className={styles.resumeHint}>Extracting skills, experience, and roles</div>
                            </>
                        ) : hasResume ? (
                            <>
                                <div className={styles.resumeName}>{resumeDisplayName}</div>
                                <div className={styles.resumeStatus}>✓ Uploaded — Click to replace</div>
                            </>
                        ) : (
                            <>
                                <div className={styles.resumeName}>Click to upload your resume</div>
                                <div className={styles.resumeHint}>PDF or DOCX, max 5 MB — AI will auto-fill your profile</div>
                            </>
                        )}
                    </div>
                </div>

                {!hasResume && (
                    <div className={styles.infoTip}>
                        <Info size={16} />
                        <span>No resume? No problem! You can fill in all fields manually below.</span>
                    </div>
                )}
            </div>

            {/* ══════════════════════════════════════════════ */}
            {/* ── STEP 2: Profile Fields (Auto-filled or Manual) */}
            {/* ══════════════════════════════════════════════ */}

            {/* ── Profile Information ── */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>
                            Profile Information
                            <span className={styles.stepBadge}>Step 2</span>
                        </div>
                        <div className={styles.cardDescription}>
                            {hasResume ? "Auto-filled from resume — edit if needed" : "Fill in your basic details"}
                        </div>
                    </div>
                </div>

                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Full Name</label>
                        <input
                            type="text"
                            className={styles.input}
                            placeholder="Your full name"
                            value={fullName}
                            onChange={(e) => setFullName(e.target.value)}
                        />
                    </div>

                    <div className={styles.formGroup}>
                        <label className={styles.label}>Years of Experience</label>
                        <input
                            type="number"
                            className={styles.input}
                            placeholder="e.g. 3"
                            min={0}
                            max={50}
                            value={experienceYears}
                            onChange={(e) => setExperienceYears(e.target.value === "" ? "" : parseInt(e.target.value))}
                        />
                    </div>
                </div>

                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Current CTC (in LPA)</label>
                        <input
                            type="number"
                            className={styles.input}
                            placeholder="e.g. 3.5"
                            min={0}
                            step={0.1}
                            value={currentCtc}
                            onChange={(e) => setCurrentCtc(e.target.value === "" ? "" : parseFloat(e.target.value))}
                        />
                    </div>

                    <div className={styles.formGroup}>
                        <label className={styles.label}>Expected CTC (in LPA)</label>
                        <input
                            type="number"
                            className={styles.input}
                            placeholder="e.g. 6"
                            min={0}
                            step={0.1}
                            value={expectedCtc}
                            onChange={(e) => setExpectedCtc(e.target.value === "" ? "" : parseFloat(e.target.value))}
                        />
                    </div>
                </div>

                <div className={styles.formGrid}>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Notice Period (in days)</label>
                        <input
                            type="number"
                            className={styles.input}
                            placeholder="e.g. 0 for immediate, 30, 60"
                            min={0}
                            max={180}
                            value={noticePeriodDays}
                            onChange={(e) => setNoticePeriodDays(e.target.value === "" ? "" : parseInt(e.target.value))}
                        />
                    </div>
                    <div className={styles.formGroup}>
                        <label className={styles.label}>Current City</label>
                        <input
                            type="text"
                            className={styles.input}
                            placeholder="e.g. Delhi, Mumbai, Bangalore"
                            value={currentCity}
                            onChange={(e) => setCurrentCity(e.target.value)}
                        />
                    </div>
                </div>
            </div>

            {/* ── Skills ── */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>Skills</div>
                        <div className={styles.cardDescription}>
                            {skills.length > 0 ? `${skills.length} skills found — add or remove as needed` : "Add your technical and professional skills"}
                        </div>
                    </div>
                </div>

                <div className={styles.tagsContainer}>
                    {skills.map((skill, i) => (
                        <span key={i} className={styles.tag}>
                            {skill}
                            <button className={styles.tagRemove} onClick={() => removeTag(i, skills, setSkills)}>
                                <X size={14} />
                            </button>
                        </span>
                    ))}
                </div>

                <div className={styles.tagInput} style={{ marginTop: skills.length ? "12px" : "0" }}>
                    <input
                        type="text"
                        className={styles.input}
                        placeholder="e.g. React, Python, AWS..."
                        value={newSkill}
                        onChange={(e) => setNewSkill(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, newSkill, skills, setSkills, setNewSkill)}
                    />
                    <button className={styles.addBtn} onClick={() => addTag(newSkill, skills, setSkills, setNewSkill)}>
                        Add
                    </button>
                </div>
                <span className={styles.inputHint}>Press Enter or click Add</span>
            </div>

            {/* ── Preferred Roles ── */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>Preferred Roles</div>
                        <div className={styles.cardDescription}>
                            {preferredRoles.length > 0 ? "Edit the roles you're targeting" : "What job roles are you looking for?"}
                        </div>
                    </div>
                </div>

                <div className={styles.tagsContainer}>
                    {preferredRoles.map((role, i) => (
                        <span key={i} className={styles.tag}>
                            {role}
                            <button className={styles.tagRemove} onClick={() => removeTag(i, preferredRoles, setPreferredRoles)}>
                                <X size={14} />
                            </button>
                        </span>
                    ))}
                </div>

                <div className={styles.tagInput} style={{ marginTop: preferredRoles.length ? "12px" : "0" }}>
                    <input
                        type="text"
                        className={styles.input}
                        placeholder="e.g. Frontend Developer, Product Manager..."
                        value={newRole}
                        onChange={(e) => setNewRole(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, newRole, preferredRoles, setPreferredRoles, setNewRole)}
                    />
                    <button className={styles.addBtn} onClick={() => addTag(newRole, preferredRoles, setPreferredRoles, setNewRole)}>
                        Add
                    </button>
                </div>
            </div>

            {/* ── Preferred Locations (Always Manual) ── */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>
                            Preferred Locations
                            <span className={styles.manualBadge}>Manual</span>
                        </div>
                        <div className={styles.cardDescription}>Where you&apos;d like to work — this is not in your resume, add manually</div>
                    </div>
                </div>

                <div className={styles.tagsContainer}>
                    {preferredLocations.map((loc, i) => (
                        <span key={i} className={styles.tag}>
                            {loc}
                            <button className={styles.tagRemove} onClick={() => removeTag(i, preferredLocations, setPreferredLocations)}>
                                <X size={14} />
                            </button>
                        </span>
                    ))}
                </div>

                <div className={styles.tagInput} style={{ marginTop: preferredLocations.length ? "12px" : "0" }}>
                    <input
                        type="text"
                        className={styles.input}
                        placeholder="e.g. Remote, Bangalore, Delhi NCR..."
                        value={newLocation}
                        onChange={(e) => setNewLocation(e.target.value)}
                        onKeyDown={(e) => handleKeyDown(e, newLocation, preferredLocations, setPreferredLocations, setNewLocation)}
                    />
                    <button className={styles.addBtn} onClick={() => addTag(newLocation, preferredLocations, setPreferredLocations, setNewLocation)}>
                        Add
                    </button>
                </div>

                <div className={styles.formGroup} style={{ marginTop: "16px" }}>
                    <label className={styles.label}>Preferred Country</label>
                    <select
                        className={styles.input}
                        value={preferredCountry}
                        onChange={(e) => setPreferredCountry(e.target.value)}
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
                    <span className={styles.inputHint}>Only jobs from this country will be scraped</span>
                </div>
            </div>

            {/* ── Email Settings (Feed Scanner) ── */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>Email Settings (Feed Scanner)</div>
                        <div className={styles.cardDescription}>Configure SMTP to allow AutoJob to send cover letters for feed jobs</div>
                    </div>
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Sender Email</label>
                    <input
                        type="email"
                        className={styles.input}
                        placeholder="your.email@gmail.com"
                        value={smtpEmail}
                        onChange={(e) => setSmtpEmail(e.target.value)}
                    />
                    <span className={styles.inputHint}>The email address applications will be sent from</span>
                </div>

                <div className={styles.formGroup} style={{ marginTop: "16px" }}>
                    <label className={styles.label}>App Password</label>
                    <div style={{ position: "relative" }}>
                        <input
                            type={showSmtpPwd ? "text" : "password"}
                            className={styles.input}
                            placeholder={user.smtp_configured ? "•••••••••••••••• (Configured)" : "e.g. abcd efgh ijkl mnop"}
                            value={smtpPassword}
                            onChange={(e) => setSmtpPassword(e.target.value)}
                            style={{ paddingRight: "40px" }}
                        />
                        <button
                            type="button"
                            onClick={() => setShowSmtpPwd(!showSmtpPwd)}
                            style={{ position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", display: "flex", padding: "4px" }}
                        >
                            {showSmtpPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>
                    
                    {/* Step-by-Step Guide for non-technical users */}
                    <div style={{ marginTop: "12px", padding: "12px", background: "rgba(99, 102, 241, 0.05)", borderRadius: "8px", border: "1px solid rgba(99, 102, 241, 0.2)", fontSize: "13px", color: "var(--text-muted)", lineHeight: "1.6" }}>
                        <strong style={{ color: "var(--text)", display: "block", marginBottom: "8px" }}>🔐 How to get a Gmail App Password (Required):</strong>
                        <ol style={{ paddingLeft: "16px", margin: 0 }}>
                            <li>Go to your <a href="https://myaccount.google.com/security" target="_blank" rel="noreferrer" style={{color: "var(--primary)", textDecoration: "underline"}}>Google Account Security</a> page.</li>
                            <li>Ensure <strong>2-Step Verification</strong> is turned ON.</li>
                            <li>Search for <strong>"App passwords"</strong> in the top search bar.</li>
                            <li>Enter an app name (e.g., "AutoJob") and click <strong>Create</strong>.</li>
                            <li>Copy the 16-character password and paste it here (no spaces needed).</li>
                        </ol>
                        <div style={{ marginTop: "8px", fontSize: "12px", color: "var(--danger)", fontWeight: 500 }}>
                            ⚠️ Note: Do NOT use your normal Gmail password. It will not work.
                        </div>
                    </div>
                </div>

                <div className={styles.formRow} style={{ marginTop: "16px", display: "flex", gap: "16px" }}>
                    <div className={styles.formGroup} style={{ flex: 2 }}>
                        <label className={styles.label}>SMTP Host</label>
                        <input
                            type="text"
                            className={styles.input}
                            placeholder="smtp.gmail.com"
                            value={smtpHost}
                            onChange={(e) => setSmtpHost(e.target.value)}
                        />
                    </div>
                    <div className={styles.formGroup} style={{ flex: 1 }}>
                        <label className={styles.label}>SMTP Port</label>
                        <input
                            type="number"
                            className={styles.input}
                            placeholder="587"
                            value={smtpPort}
                            onChange={(e) => setSmtpPort(Number(e.target.value))}
                        />
                    </div>
                </div>
            </div>

            {/* ── Naukri.com Credentials ── */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>Naukri.com Credentials</div>
                        <div className={styles.cardDescription}>Login credentials for Naukri.com auto-apply (AES-256 encrypted)</div>
                    </div>
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>Naukri Email</label>
                    <input
                        type="email"
                        className={styles.input}
                        placeholder="your.email@example.com"
                        value={naukriEmail}
                        onChange={(e) => setNaukriEmail(e.target.value)}
                    />
                </div>

                <div className={styles.formGroup} style={{ marginTop: "16px" }}>
                    <label className={styles.label}>Naukri Password</label>
                    <div style={{ position: "relative" }}>
                        <input
                            type={showNaukriPwd ? "text" : "password"}
                            className={styles.input}
                            placeholder={user.naukri_configured ? "•••••••••••••••• (Configured)" : "Enter your Naukri password"}
                            value={naukriPassword}
                            onChange={(e) => setNaukriPassword(e.target.value)}
                            style={{ paddingRight: "40px" }}
                        />
                        <button
                            type="button"
                            onClick={() => setShowNaukriPwd(!showNaukriPwd)}
                            style={{ position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", display: "flex", padding: "4px" }}
                        >
                            {showNaukriPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>
                    <span className={styles.inputHint}>Your password is encrypted with AES-256 before storage. Never stored in plain text.</span>
                </div>
            </div>

            {/* ── LinkedIn Credentials ── */}
            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>LinkedIn Credentials</div>
                        <div className={styles.cardDescription}>Login credentials for LinkedIn auto-apply (AES-256 encrypted)</div>
                    </div>
                </div>

                <div className={styles.formGroup}>
                    <label className={styles.label}>LinkedIn Email</label>
                    <input
                        type="email"
                        className={styles.input}
                        placeholder="your.email@example.com"
                        value={linkedinEmail}
                        onChange={(e) => setLinkedinEmail(e.target.value)}
                    />
                </div>

                <div className={styles.formGroup} style={{ marginTop: "16px" }}>
                    <label className={styles.label}>LinkedIn Password</label>
                    <div style={{ position: "relative" }}>
                        <input
                            type={showLinkedinPwd ? "text" : "password"}
                            className={styles.input}
                            placeholder={user.linkedin_configured ? "•••••••••••••••• (Configured)" : "Enter your LinkedIn password"}
                            value={linkedinPassword}
                            onChange={(e) => setLinkedinPassword(e.target.value)}
                            style={{ paddingRight: "40px" }}
                        />
                        <button
                            type="button"
                            onClick={() => setShowLinkedinPwd(!showLinkedinPwd)}
                            style={{ position: "absolute", right: "12px", top: "50%", transform: "translateY(-50%)", background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", display: "flex", padding: "4px" }}
                        >
                            {showLinkedinPwd ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </div>
                    <span className={styles.inputHint}>Your password is encrypted with AES-256 before storage. Never stored in plain text.</span>
                </div>
            </div>

            <div className={styles.card}>
                <div className={styles.cardHeader}>
                    <div>
                        <div className={styles.cardTitle}>Account</div>
                        <div className={styles.cardDescription}>Your account details</div>
                    </div>
                </div>

                <div>
                    <div className={styles.accountRow}>
                        <span className={styles.accountLabel}>Email</span>
                        <span className={styles.accountValue}>{user.email}</span>
                    </div>
                    <div className={styles.accountRow}>
                        <span className={styles.accountLabel}>Subscription</span>
                        <span className={styles.tierBadge}>{user.subscription_tier || "Free"}</span>
                    </div>
                </div>
            </div>

            {/* ── Save Button ── */}
            <div className={styles.saveRow}>
                <div style={{ flex: 1, display: "flex", alignItems: "center" }}>
                    {successMsg && (
                        <div className={styles.successMsg} style={{ padding: "8px 12px", border: "none", background: "transparent" }}>
                            <CheckCircle size={18} />
                            {successMsg}
                        </div>
                    )}
                    {errorMsg && (
                        <div className={styles.errorMsg} style={{ padding: "8px 12px", border: "none", background: "transparent" }}>
                            <AlertTriangle size={18} />
                            {errorMsg}
                        </div>
                    )}
                </div>
                <button
                    className={styles.saveBtn}
                    onClick={handleSave}
                    disabled={saving}
                >
                    {saving ? (
                        <Loader size={18} className={styles.spinner} />
                    ) : (
                        <Save size={18} />
                    )}
                    {saving ? "Saving..." : "Save Changes"}
                </button>
            </div>
        </div>
    );
}
