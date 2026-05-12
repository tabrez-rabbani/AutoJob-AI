/**
 * AutoJob AI — Qualified Jobs Page
 * Fetches jobs from backend and filters by qualified status or high match score.
 */

"use client";

import { useEffect, useState } from "react";
import Header from "@/components/layout/Header";
import JobsTable from "@/components/ui/JobsTable";
import { dashboardApi, type FilterParams } from "@/lib/api";
import { toJobListing } from "@/lib/transforms";
import { JobListing } from "@/types";
import { Loader2 } from "lucide-react";
import Pagination from "@/components/ui/Pagination";
import SearchFilters from "@/components/ui/SearchFilters";

export default function QualifiedJobsPage() {
    const [jobs, setJobs] = useState<JobListing[]>([]);
    const [loading, setLoading] = useState(true);
    const [totalCount, setTotalCount] = useState(0);
    const [currentPage, setCurrentPage] = useState(1);
    const [filters, setFilters] = useState<FilterParams>({});
    const limit = 20;

    useEffect(() => {
        async function fetchQualified() {
            setLoading(true);
            try {
                const offset = (currentPage - 1) * limit;
                const data = await dashboardApi.getQualified(limit, offset, filters);
                setJobs(data.jobs.map(toJobListing));
                setTotalCount(data.count);
            } catch {
                // API error — UI shows empty state
            } finally {
                setLoading(false);
            }
        }
        fetchQualified();
    }, [currentPage, filters]);

    const handleFilterChange = (newFilters: FilterParams) => {
        setFilters(newFilters);
        setCurrentPage(1);
    };

    const totalPages = Math.ceil(totalCount / limit);

    return (
        <>
            <Header
                title="Qualified Matches"
                subtitle="Jobs that match your profile score threshold and are pending application."
            />
            <div style={{ marginTop: "24px" }}>
                <SearchFilters
                    onFilterChange={handleFilterChange}
                    statusOptions={["applied", "external_apply", "qualified"]}
                />
                {loading ? (
                    <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text-secondary)" }}>
                        <Loader2 size={24} style={{ animation: "spin 1s linear infinite", marginBottom: "8px" }} />
                        <p>Loading qualified jobs...</p>
                    </div>
                ) : (
                    <>
                        <JobsTable
                            jobs={jobs}
                            emptyMessage="No qualified jobs found. Try running the automation again."
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
