/**
 * AutoJob AI — Job Detail Page
 * Shows full details for a single job including description, application status, etc.
 */

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { dashboardApi, type JobDetail } from "@/lib/api";
import Header from "@/components/layout/Header";
import StatusBadge from "@/components/ui/StatusBadge";
import { StatusVariant } from "@/types";
import {
    Loader2,
    ArrowLeft,
    MapPin,
    Briefcase,
    DollarSign,
    Calendar,
    ExternalLink,
    Globe,
} from "lucide-react";
import styles from "./JobDetail.module.css";

export default function JobDetailPage() {
    const params = useParams();
    const router = useRouter();
    const [job, setJob] = useState<JobDetail | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        async function fetchJob() {
            try {
                const data = await dashboardApi.getJobDetail(params.id as string);
                setJob(data);
            } catch {
                setError("Failed to load job details.");
            } finally {
                setLoading(false);
            }
        }
        if (params.id) fetchJob();
    }, [params.id]);

    if (loading) {
        return (
            <>
                <Header title="Job Details" subtitle="Loading..." />
                <div className={styles.loadingState}>
                    <Loader2 size={24} className={styles.spinner} />
                    <p>Loading job details...</p>
                </div>
            </>
        );
    }

    if (error || !job) {
        return (
            <>
                <Header title="Job Details" subtitle="" />
                <div className={styles.errorState}>
                    <p>{error || "Job not found."}</p>
                    <button className={styles.backBtn} onClick={() => router.back()}>
                        <ArrowLeft size={18} /> Go Back
                    </button>
                </div>
            </>
        );
    }

    const formatDate = (dateStr: string | null) => {
        if (!dateStr) return "—";
        return new Date(dateStr).toLocaleDateString("en-IN", {
            day: "2-digit",
            month: "short",
            year: "numeric",
        });
    };

    const scoreColor =
        (job.match_score ?? 0) >= 80
            ? "var(--color-success)"
            : (job.match_score ?? 0) >= 50
                ? "var(--color-warning)"
                : "var(--color-error)";

    return (
        <>
            <Header title="Job Details" subtitle={`${job.title} at ${job.company}`} />

            <div className={styles.container}>
                {/* Back Button */}
                <button className={styles.backBtn} onClick={() => router.back()}>
                    <ArrowLeft size={18} /> Back to Jobs
                </button>

                {/* Main Card */}
                <div className={styles.mainCard}>
                    {/* Header Section */}
                    <div className={styles.jobHeader}>
                        <div className={styles.jobTitleSection}>
                            <h1 className={styles.jobTitle}>{job.title}</h1>
                            <p className={styles.companyName}>{job.company}</p>
                        </div>
                        <div className={styles.headerActions}>
                            {job.application_status && (
                                <StatusBadge status={job.application_status as StatusVariant} />
                            )}
                            <a
                                href={job.apply_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className={styles.applyBtn}
                            >
                                <ExternalLink size={16} /> View on {job.platform === "linkedin" ? "LinkedIn" : job.platform}
                            </a>
                        </div>
                    </div>

                    {/* Meta Tags */}
                    <div className={styles.metaTags}>
                        {job.location && (
                            <div className={styles.metaTag}>
                                <MapPin size={15} />
                                <span>{job.location}</span>
                            </div>
                        )}
                        {job.job_type && (
                            <div className={styles.metaTag}>
                                <Briefcase size={15} />
                                <span>{job.job_type.replace("_", " ")}</span>
                            </div>
                        )}
                        {job.salary_range && (
                            <div className={styles.metaTag}>
                                <DollarSign size={15} />
                                <span>{job.salary_range}</span>
                            </div>
                        )}
                        <div className={styles.metaTag}>
                            <Calendar size={15} />
                            <span>Scraped {formatDate(job.scraped_at)}</span>
                        </div>
                        <div className={styles.metaTag}>
                            <Globe size={15} />
                            <span>{job.platform}</span>
                        </div>
                    </div>

                    {/* Match Score */}
                    {job.match_score !== null && (
                        <div className={styles.scoreSection}>
                            <div className={styles.scoreHeader}>
                                <span className={styles.scoreLabel}>Match Score</span>
                                <span className={styles.scoreValue} style={{ color: scoreColor }}>
                                    {job.match_score}%
                                </span>
                            </div>
                            <div className={styles.scoreBarBg}>
                                <div
                                    className={styles.scoreBarFill}
                                    style={{
                                        width: `${job.match_score}%`,
                                        backgroundColor: scoreColor,
                                    }}
                                />
                            </div>
                        </div>
                    )}
                </div>

                {/* Description Section */}
                <div className={styles.sectionCard}>
                    <h2 className={styles.sectionTitle}>Job Description</h2>
                    {job.description ? (
                        <div className={styles.description}>
                            {job.description.split("\n").map((line, i) => (
                                <p key={i}>{line || "\u00A0"}</p>
                            ))}
                        </div>
                    ) : (
                        <p className={styles.noData}>
                            No description available. View the full listing on the platform.
                        </p>
                    )}
                </div>

                {/* Application Info Section */}
                {job.application_status && (
                    <div className={styles.sectionCard}>
                        <h2 className={styles.sectionTitle}>Application Info</h2>
                        <div className={styles.infoGrid}>
                            <div className={styles.infoItem}>
                                <span className={styles.infoLabel}>Status</span>
                                <StatusBadge status={job.application_status as StatusVariant} />
                            </div>
                            {job.applied_at && (
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Applied On</span>
                                    <span className={styles.infoValue}>{formatDate(job.applied_at)}</span>
                                </div>
                            )}
                            {job.application_notes && (
                                <div className={styles.infoItem}>
                                    <span className={styles.infoLabel}>Notes</span>
                                    <span className={styles.infoValue}>{job.application_notes}</span>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </>
    );
}
