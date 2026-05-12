/**
 * AutoJob AI — Dashboard Layout
 * Wraps all /dashboard/* pages with Sidebar + main content area.
 * Redirects to /login if the user is not authenticated.
 */

"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import Sidebar from "@/components/layout/Sidebar";
import styles from "./DashboardLayout.module.css";
import { AlignLeft } from "lucide-react";

interface DashboardLayoutProps {
    children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
    const { isAuthenticated, isLoading } = useAuth();
    const router = useRouter();
    const [isSidebarOpen, setIsSidebarOpen] = useState(false);

    useEffect(() => {
        if (!isLoading && !isAuthenticated) {
            router.replace("/login");
        }
    }, [isLoading, isAuthenticated, router]);

    // Show nothing while checking auth (prevents dashboard flash)
    if (isLoading || !isAuthenticated) {
        return null;
    }

    return (
        <div className={styles.wrapper}>
            {/* Mobile Overlay */}
            {isSidebarOpen && (
                <div 
                    className={styles.overlay} 
                    onClick={() => setIsSidebarOpen(false)} 
                />
            )}
            
            <Sidebar isOpen={isSidebarOpen} onClose={() => setIsSidebarOpen(false)} />
            
            <main className={styles.main}>
                {/* Mobile Header Bar */}
                <div className={styles.mobileHeader}>
                    <button 
                        className={styles.menuBtn} 
                        onClick={() => setIsSidebarOpen(true)}
                        title="Open Menu"
                    >
                        <AlignLeft size={24} />
                    </button>
                </div>
                
                {children}
            </main>
        </div>
    );
}
