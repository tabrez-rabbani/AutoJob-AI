/**
 * AutoJob AI — Auth Layout
 * Refined center card layout matching the e-commerce reference.
 */

import { BriefcaseBusiness, Plus } from "lucide-react";
import styles from "./AuthLayout.module.css";
export default function AuthLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className={styles.container}>
            {/* Left Side: Premium Branding & Visuals (Razorpay Style) */}
            <div className={styles.visualPanel}>
                <div className={styles.lightBeams}></div>
                
                <div className={styles.brandRow}>
                    <h1 className={styles.brandName}>AUTOJOB</h1>
                </div>
                
                <div className={styles.bottomContent}>
                    <h2 className={styles.heroText}>
                        Join thousands of professionals that Trust AutoJob AI to Supercharge their Career
                    </h2>

                    <div className={styles.featureList}>
                        <div className={styles.featureItem}>
                            <Plus className={styles.featureIcon} size={18} />
                            <span>100+ Daily Applications</span>
                        </div>
                        <div className={styles.featureItem}>
                            <Plus className={styles.featureIcon} size={18} />
                            <span>Smart AI Matchmaking</span>
                        </div>
                        <div className={styles.featureItem}>
                            <Plus className={styles.featureIcon} size={18} />
                            <span>Powerful Dashboard</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Right Side: Auth Form */}
            <div className={styles.formPanel}>
                <div className={styles.card}>{children}</div>
            </div>
        </div>
    );
}

