/**
 * AutoJob AI — Data Transformers
 * Converts backend API response shapes into frontend component types.
 */

import { DashboardJob } from "@/lib/api";
import { JobListing, StatusVariant } from "@/types";

/**
 * Transforms a backend DashboardJob into the frontend JobListing shape
 * consumed by the JobsTable component.
 */
export function toJobListing(job: DashboardJob): JobListing {
    return {
        id: job.id,
        title: job.title,
        company: job.company,
        location: job.location || "Remote",
        status: (job.application_status as StatusVariant) || "scraped",
        matchScore: job.match_score ?? 0,
        dateScraped: job.scraped_at
            ? new Date(job.scraped_at).toLocaleDateString("en-IN", {
                day: "2-digit",
                month: "short",
                year: "numeric",
            })
            : "—",
        linkedinUrl: job.apply_url,
    };
}
