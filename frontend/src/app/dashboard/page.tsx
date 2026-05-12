/**
 * AutoJob AI — Dashboard Home Page
 * Fetches real stats and recent jobs from the backend API.
 * Integrates the Run Automation modal.
 */

"use client";

import { useEffect, useState, useCallback } from "react";
import Header from "@/components/layout/Header";
import StatCard from "@/components/ui/StatCard";
import JobsTable from "@/components/ui/JobsTable";
import AutomationModal from "@/components/ui/AutomationModal";
import DashboardCharts from "@/components/ui/DashboardCharts";
import ActivityHeatmap from "@/components/ui/ActivityHeatmap";
import { dashboardApi, type DashboardStats, type AnalyticsData } from "@/lib/api";
import { toJobListing } from "@/lib/transforms";
import { JobListing } from "@/types";
import styles from "./page.module.css";
import { Search, CheckCircle, Send, XCircle, Zap, Loader2 } from "lucide-react";

export default function DashboardPage() {
    const [stats, setStats] = useState<DashboardStats | null>(null);
    const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
    const [recentJobs, setRecentJobs] = useState<JobListing[]>([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);

    const fetchDashboard = useCallback(async () => {
        try {
            const [statsData, jobsData, analyticsData] = await Promise.all([
                dashboardApi.getStats(),
                dashboardApi.getJobs(5, 0),
                dashboardApi.getAnalytics(),
            ]);
            setStats(statsData);
            setRecentJobs(jobsData.jobs.map(toJobListing));
            setAnalytics(analyticsData);
        } catch {
            // API error — UI shows empty state
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchDashboard();
    }, [fetchDashboard]);

    return (
        <>
            <Header
                title="Dashboard"
                subtitle="Overview of your job search automation"
            />

            {/* Action Banner */}
            <div className={styles.actionBanner}>
                <div className={styles.bannerText}>
                    <h2>Automate Your Job Search</h2>
                    <p>Scrape, analyze, and apply to new matching jobs instantly.</p>
                    <div className={styles.timeSavedBlock}>
                        <span className={styles.timeSavedLabel}>Estimated Time Saved:</span>
                        <span className={styles.timeSavedValue}>
                            {stats?.total_applied ? Math.round(stats.total_applied * 10 / 60) : 0} Hours
                        </span>
                    </div>
                </div>
                <button className={styles.runBtn} onClick={() => setShowModal(true)}>
                    <Zap size={18} />
                    Run Automation
                </button>
            </div>

            {/* Stat Cards */}
            {loading ? (
                <div className={styles.loadingState}>
                    <Loader2 size={24} className={styles.spinner} />
                    <span>Loading stats...</span>
                </div>
            ) : (
                <>
                    <div className={styles.statsGrid}>
                        <StatCard icon={<Search size={22} />} label="Jobs Scraped" value={stats?.total_scraped ?? 0} variant="primary" />
                        <StatCard icon={<CheckCircle size={22} />} label="Qualified" value={stats?.total_qualified ?? 0} variant="success" />
                        <StatCard icon={<Send size={22} />} label="Applied" value={stats?.total_applied ?? 0} variant="info" />
                        <StatCard icon={<XCircle size={22} />} label="Failed" value={stats?.total_failed ?? 0} variant="error" />
                    </div>
                    
                    {/* Recharts Analytics */}
                    <DashboardCharts stats={stats} analytics={analytics} />
                    
                    {/* GitHub Style Heatmap */}
                    <ActivityHeatmap heatmapData={analytics?.heatmap ?? []} totalApplied={stats?.total_applied ?? 0} />
                </>
            )}

            {/* Recent Activity */}
            <div className={styles.section}>
                <JobsTable
                    jobs={recentJobs}
                    title="Recent Activity"
                    emptyMessage="No recent activity to show. Run the automation to start scraping jobs."
                />
            </div>

            {/* Automation Modal */}
            <AutomationModal
                isOpen={showModal}
                onClose={() => setShowModal(false)}
                onComplete={fetchDashboard}
            />
        </>
    );
}
