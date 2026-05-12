/**
 * AutoJob AI — All Scraped Jobs Page
 * Fetches all jobs from backend API.
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

export default function JobsPage() {
    const [jobs, setJobs] = useState<JobListing[]>([]);
    const [loading, setLoading] = useState(true);
    const [totalCount, setTotalCount] = useState(0);
    const [currentPage, setCurrentPage] = useState(1);
    const [filters, setFilters] = useState<FilterParams>({});
    const limit = 20;

    useEffect(() => {
        async function fetchJobs() {
            setLoading(true);
            try {
                const offset = (currentPage - 1) * limit;
                const data = await dashboardApi.getJobs(limit, offset, filters);
                setJobs(data.jobs.map(toJobListing));
                setTotalCount(data.count);
            } catch {
                // API error — UI shows empty state
            } finally {
                setLoading(false);
            }
        }
        fetchJobs();
    }, [currentPage, filters]);

    const handleFilterChange = (newFilters: FilterParams) => {
        setFilters(newFilters);
        setCurrentPage(1); // Reset to page 1 on filter change
    };

    const totalPages = Math.ceil(totalCount / limit);

    return (
        <>
            <Header
                title="All Scraped Jobs"
                subtitle="Every job the AI has scraped from your LinkedIn feed."
            />
            <div style={{ marginTop: "24px" }}>
                <SearchFilters onFilterChange={handleFilterChange} />
                {loading ? (
                    <div style={{ textAlign: "center", padding: "60px 0", color: "var(--text-secondary)" }}>
                        <Loader2 size={24} style={{ animation: "spin 1s linear infinite", marginBottom: "8px" }} />
                        <p>Loading jobs...</p>
                    </div>
                ) : (
                    <>
                        <JobsTable jobs={jobs} emptyMessage="No jobs have been scraped yet. Run the automation to start." />
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
