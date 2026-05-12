/**
 * AutoJob AI — Applied Jobs Page
 * Fetches applications from backend API.
 */

"use client";

import { useEffect, useState } from "react";
import Header from "@/components/layout/Header";
import JobsTable from "@/components/ui/JobsTable";
import { dashboardApi, type DashboardApplication, type FilterParams } from "@/lib/api";
import { JobListing, StatusVariant } from "@/types";
import { Loader2 } from "lucide-react";
import Pagination from "@/components/ui/Pagination";
import SearchFilters from "@/components/ui/SearchFilters";

/** Transform backend DashboardApplication → frontend JobListing */
function toAppliedJobListing(app: DashboardApplication): JobListing {
    return {
        id: app.job_id,
        title: app.job_title,
        company: app.company,
        location: "—",
        status: (app.status as StatusVariant) || "applied",
        matchScore: app.match_score ?? 0,
        dateScraped: app.applied_at
            ? new Date(app.applied_at).toLocaleDateString("en-IN", {
                day: "2-digit",
                month: "short",
                year: "numeric",
            })
            : "—",
        linkedinUrl: "#",
    };
}

export default function AppliedJobsPage() {
    const [jobs, setJobs] = useState<JobListing[]>([]);
    const [loading, setLoading] = useState(true);
    const [totalCount, setTotalCount] = useState(0);
    const [currentPage, setCurrentPage] = useState(1);
    const [filters, setFilters] = useState<FilterParams>({});
    const limit = 20;

    useEffect(() => {
        async function fetchApplied() {
            setLoading(true);
            try {
                const offset = (currentPage - 1) * limit;
                const data = await dashboardApi.getApplied(limit, offset, filters);
                setJobs(data.applications.map(toAppliedJobListing));
                setTotalCount(data.count);
            } catch {
                // API error — UI shows empty state
            } finally {
                setLoading(false);
            }
        }
        fetchApplied();
    }, [currentPage, filters]);

    const handleFilterChange = (newFilters: FilterParams) => {
        setFilters(newFilters);
        setCurrentPage(1);
    };

    const totalPages = Math.ceil(totalCount / limit);

    return (
        <>
            <Header
                title="Application History"
                subtitle="Track the status of jobs you have applied to."
            />
            <div style={{ marginTop: "24px" }}>
                <SearchFilters
                    onFilterChange={handleFilterChange}
                    statusOptions={["applied", "external_apply", "skipped", "failed"]}
                    placeholder="Search by job title or company..."
                />
                {loading ? (
                    <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text-secondary)" }}>
                        <Loader2 size={24} style={{ animation: "spin 1s linear infinite", marginBottom: "8px" }} />
                        <p>Loading applications...</p>
                    </div>
                ) : (
                    <>
                        <JobsTable
                            jobs={jobs}
                            emptyMessage="You haven't applied to any jobs yet."
                        />
                        <Pagination 
                            currentPage={currentPage}
                            totalPages={totalPages}
                            onPageChange={(page) => setCurrentPage(page)}
                        />
                    </>
                )}
            </div>
        </>
    );
}
