/**
 * AutoJob AI — Dashboard Sidebar Update
 * Updating icons from emojis to lucide-react.
 */

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import styles from "./Sidebar.module.css";
import { LayoutDashboard, Briefcase, CheckSquare, Settings, LogOut, X } from "lucide-react";

interface SidebarProps {
    isOpen?: boolean;
    onClose?: () => void;
}

const navItems = [
    { label: "Dashboard", href: "/dashboard", icon: <LayoutDashboard size={20} /> },
    { label: "Jobs", href: "/dashboard/jobs", icon: <Briefcase size={20} /> },
    { label: "Qualified", href: "/dashboard/qualified", icon: <CheckSquare size={20} /> },
    { label: "Applied", href: "/dashboard/applied", icon: <CheckSquare size={20} /> },
    { label: "Settings", href: "/dashboard/settings", icon: <Settings size={20} /> },
];

export default function Sidebar({ isOpen = false, onClose }: SidebarProps) {
    const pathname = usePathname();
    const { user, logout } = useAuth();

    return (
        <aside className={`${styles.sidebar} ${isOpen ? styles.open : ""}`}>
            {/* Brand */}
            <div className={styles.brand}>
                <div>
                    <h1 className={styles.brandName}>AutoJob AI</h1>
                    <p className={styles.brandTag}>Smart Automation</p>
                </div>
                {onClose && (
                    <button className={styles.closeBtnMobile} onClick={onClose}>
                        <X size={20} />
                    </button>
                )}
            </div>

            {/* Navigation */}
            <nav className={styles.nav}>
                <p className={styles.navLabel}>MENU</p>
                {navItems.map((item) => {
                    const isActive =
                        item.href === "/dashboard"
                            ? pathname === "/dashboard"
                            : pathname === item.href; // Exact match for subpages so they don't overlap

                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`${styles.navLink} ${isActive ? styles.active : ""}`}
                        >
                            <span className={styles.navIcon}>{item.icon}</span>
                            <span>{item.label}</span>
                            {isActive && <span className={styles.activeIndicator} />}
                        </Link>
                    );
                })}
            </nav>

            {/* User Section */}
            <div className={styles.userSection}>
                <div className={styles.userAvatar}>
                    {user?.full_name?.charAt(0).toUpperCase() || "U"}
                </div>
                <div className={styles.userInfo}>
                    <p className={styles.userName}>{user?.full_name || "Guest User"}</p>
                    <p className={styles.userEmail}>{user?.email || "Not logged in"}</p>
                </div>
                <button
                    onClick={() => {
                        logout();
                        window.location.href = "/login"; // Force full reload & redirect to ensure clean state
                    }}
                    className={styles.logoutBtn}
                    title="Logout"
                >
                    <LogOut size={16} />
                </button>
            </div>
        </aside>
    );
}
