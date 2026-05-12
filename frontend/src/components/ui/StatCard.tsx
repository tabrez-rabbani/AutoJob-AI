/**
 * AutoJob AI — Stat Card
 * Dashboard overview stat card with icon, value, and label.
 */

import { ReactNode } from "react";
import styles from "./StatCard.module.css";

interface StatCardProps {
    label: string;
    value: number | string;
    icon: ReactNode;
    variant?: "primary" | "success" | "warning" | "error" | "info";
}

export default function StatCard({
    label,
    value,
    icon,
    variant = "primary",
}: StatCardProps) {
    return (
        <div className={`${styles.card} ${styles[variant]}`}>
            <div className={styles.leftSection}>
                <div className={styles.accentBar}></div>
                <div className={styles.content}>
                    <p className={styles.label}>{label}</p>
                    <p className={styles.value}>{value}</p>
                </div>
            </div>

            {/* Icon on the right */}
            <div className={styles.iconWrap}>
                {icon}
            </div>
        </div>
    );
}
