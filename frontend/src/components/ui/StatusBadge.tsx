/**
 * AutoJob AI — Status Badge
 * Colored badge for job/application status display.
 */

import styles from "./StatusBadge.module.css";

interface StatusBadgeProps {
    status: string;
}

const statusConfig: Record<string, { label: string; variant: string }> = {
    applied: { label: "Applied", variant: "success" },
    external_apply: { label: "External", variant: "warning" },
    qualified: { label: "Qualified", variant: "info" },
    queued: { label: "Queued", variant: "primary" },
    skipped: { label: "Skipped", variant: "muted" },
    failed: { label: "Failed", variant: "error" },
    interview: { label: "Interview", variant: "accent" },
    offer: { label: "Offer", variant: "success" },
    rejected: { label: "Rejected", variant: "error" },
};

export default function StatusBadge({ status }: StatusBadgeProps) {
    const config = statusConfig[status] || {
        label: status,
        variant: "muted",
    };

    return (
        <span className={`${styles.badge} ${styles[config.variant]}`}>
            {config.label}
        </span>
    );
}
