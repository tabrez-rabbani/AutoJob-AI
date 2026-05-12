/**
 * AutoJob AI — Empty State
 * Placeholder shown when there is no data to display.
 */

import styles from "./EmptyState.module.css";

interface EmptyStateProps {
    icon?: string;
    title: string;
    message: string;
    action?: {
        label: string;
        onClick: () => void;
    };
}

export default function EmptyState({
    icon = "📭",
    title,
    message,
    action,
}: EmptyStateProps) {
    return (
        <div className={styles.container}>
            <span className={styles.icon}>{icon}</span>
            <h3 className={styles.title}>{title}</h3>
            <p className={styles.message}>{message}</p>
            {action && (
                <button className={styles.actionBtn} onClick={action.onClick}>
                    {action.label}
                </button>
            )}
        </div>
    );
}
