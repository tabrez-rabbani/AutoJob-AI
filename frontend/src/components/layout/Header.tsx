/**
 * AutoJob AI — Header Bar
 * Top header with page title, search, and quick actions.
 */

"use client";

import { useAuth } from "@/context/AuthContext";
import styles from "./Header.module.css";

interface HeaderProps {
    title: string;
    subtitle?: string;
}

export default function Header({ title, subtitle }: HeaderProps) {
    const { user } = useAuth();

    return (
        <header className={styles.header}>
            <div className={styles.left}>
                <h1 className={styles.title}>{title}</h1>
                {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
            </div>

            <div className={styles.right}>
                {/* Greeting */}
                <div className={styles.greeting}>
                    <p className={styles.greetingText}>
                        Welcome back, <span className={styles.greetingName}>{user?.full_name?.split(" ")[0] || "User"}</span>
                    </p>
                </div>
            </div>
        </header>
    );
}
