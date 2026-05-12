/**
 * AutoJob AI — Type Definitions
 * Shared TypeScript interfaces used across components.
 */

export type StatusVariant =
    | "applied"
    | "external_apply"
    | "qualified"
    | "skipped"
    | "failed"
    | "queued"
    | "scraped"
    | "offer"
    | "interview"
    | "rejected";

export interface NavItem {
    label: string;
    href: string;
    icon: React.ReactNode;
}

export interface StatCardData {
    label: string;
    value: number;
    icon: React.ReactNode;
    variant: "primary" | "success" | "warning" | "error" | "info";
}

export interface JobListing {
    id: string;
    title: string;
    company: string;
    location: string;
    status: StatusVariant;
    matchScore: number;
    dateScraped: string;
    dateApplied?: string;
    linkedinUrl: string;
}
