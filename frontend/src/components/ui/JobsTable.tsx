/**
 * AutoJob AI — Jobs Table Component
 * Reusable data table for displaying scraped, qualified, or applied jobs.
 */

import { JobListing } from "@/types";
import StatusBadge from "./StatusBadge";
import styles from "./JobsTable.module.css";
import { ExternalLink } from "lucide-react";
import EmptyState from "./EmptyState";
import { useRouter } from "next/navigation";

interface JobsTableProps {
    jobs: JobListing[];
    title?: string;
    emptyMessage?: string;
}

export default function JobsTable({
    jobs,
    title,
    emptyMessage = "No jobs found.",
}: JobsTableProps) {
    const router = useRouter();
    if (jobs.length === 0) {
        return (
            <div className={styles.tableWrapper}>
                {title && <h2 className={styles.tableTitle}>{title}</h2>}
                <EmptyState title="No Data" message={emptyMessage} icon="📭" />
            </div>
        );
    }

    return (
        <div className={styles.tableWrapper}>
            {title && <h2 className={styles.tableTitle}>{title}</h2>}
            <div className={styles.overflowContainer}>
                <table className={styles.table}>
                    <thead>
                        <tr>
                            <th>Role & Company</th>
                            <th>Location</th>
                            <th>Match Score</th>
                            <th>Status</th>
                            <th>Date</th>
                            <th className={styles.alignRight}>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {jobs.map((job) => (
                            <tr
                                key={job.id}
                                className={styles.row}
                                onClick={() => router.push(`/dashboard/jobs/${job.id}`)}
                                style={{ cursor: "pointer" }}
                            >
                                {/* Role & Company */}
                                <td data-label="Role & Company">
                                    <div className={styles.roleCell}>
                                        <p className={styles.jobTitle}>{job.title}</p>
                                        <p className={styles.company}>{job.company}</p>
                                    </div>
                                </td>

                                {/* Location */}
                                <td data-label="Location">
                                    <p className={styles.textSecondary}>{job.location}</p>
                                </td>

                                {/* Match Score */}
                                <td data-label="Match Score">
                                    <div className={styles.scoreWrap}>
                                        <div className={styles.scoreBarBg}>
                                            <div
                                                className={styles.scoreBarFill}
                                                style={{
                                                    width: `${job.matchScore}%`,
                                                    backgroundColor:
                                                        job.matchScore >= 80
                                                            ? "var(--color-success)"
                                                            : job.matchScore >= 50
                                                                ? "var(--color-warning)"
                                                                : "var(--color-error)",
                                                }}
                                            />
                                        </div>
                                        <span className={styles.scoreText}>{job.matchScore}%</span>
                                    </div>
                                </td>

                                {/* Status */}
                                <td data-label="Status">
                                    <StatusBadge status={job.status} />
                                </td>

                                {/* Date */}
                                <td data-label="Date">
                                    <p className={styles.textSecondary}>{job.dateScraped}</p>
                                </td>

                                {/* Actions */}
                                <td className={styles.alignRight} data-label="Action">
                                    <a
                                        href={job.linkedinUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className={styles.actionBtn}
                                        title="View on LinkedIn"
                                        onClick={(e) => e.stopPropagation()}
                                    >
                                        <ExternalLink size={16} />
                                    </a>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
