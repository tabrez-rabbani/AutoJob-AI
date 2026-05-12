/**
 * AutoJob AI — Search & Filters Component
 * Reusable filter bar for Jobs, Qualified, and Applied pages.
 */

"use client";

import { useState, useEffect, useRef } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import styles from "./SearchFilters.module.css";
import type { FilterParams } from "@/lib/api";

interface SearchFiltersProps {
    onFilterChange: (filters: FilterParams) => void;
    statusOptions?: string[];
    placeholder?: string;
}

export default function SearchFilters({
    onFilterChange,
    statusOptions = ["applied", "external_apply", "skipped", "failed", "qualified"],
    placeholder = "Search by job title or company...",
}: SearchFiltersProps) {
    const [search, setSearch] = useState("");
    const [status, setStatus] = useState("");
    const [minScore, setMinScore] = useState("");
    const [maxScore, setMaxScore] = useState("");
    const [dateFrom, setDateFrom] = useState("");
    const [dateTo, setDateTo] = useState("");
    const [showFilters, setShowFilters] = useState(false);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Build filters object and notify parent
    const emitFilters = (overrides?: Partial<{
        search: string; status: string; minScore: string; maxScore: string; dateFrom: string; dateTo: string;
    }>) => {
        const s = overrides?.search ?? search;
        const st = overrides?.status ?? status;
        const mn = overrides?.minScore ?? minScore;
        const mx = overrides?.maxScore ?? maxScore;
        const df = overrides?.dateFrom ?? dateFrom;
        const dt = overrides?.dateTo ?? dateTo;

        const filters: FilterParams = {};
        if (s.trim()) filters.search = s.trim();
        if (st) filters.status = st;
        if (mn !== "") filters.min_score = Number(mn);
        if (mx !== "") filters.max_score = Number(mx);
        if (df) filters.date_from = df;
        if (dt) filters.date_to = dt;
        onFilterChange(filters);
    };

    // Debounced search
    const handleSearchChange = (value: string) => {
        setSearch(value);
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            emitFilters({ search: value });
        }, 400);
    };

    // Immediate filters (dropdowns, dates)
    const handleStatusChange = (value: string) => {
        setStatus(value);
        emitFilters({ status: value });
    };

    const handleMinScoreChange = (value: string) => {
        setMinScore(value);
        emitFilters({ minScore: value });
    };

    const handleMaxScoreChange = (value: string) => {
        setMaxScore(value);
        emitFilters({ maxScore: value });
    };

    const handleDateFromChange = (value: string) => {
        setDateFrom(value);
        emitFilters({ dateFrom: value });
    };

    const handleDateToChange = (value: string) => {
        setDateTo(value);
        emitFilters({ dateTo: value });
    };

    const clearAllFilters = () => {
        setSearch("");
        setStatus("");
        setMinScore("");
        setMaxScore("");
        setDateFrom("");
        setDateTo("");
        onFilterChange({});
    };

    const hasActiveFilters = search || status || minScore || maxScore || dateFrom || dateTo;

    const statusLabels: Record<string, string> = {
        applied: "Applied",
        external_apply: "External",
        skipped: "Skipped",
        failed: "Failed",
        qualified: "Qualified",
    };

    return (
        <div className={styles.container}>
            {/* Search Row */}
            <div className={styles.searchRow}>
                <div className={styles.searchBox}>
                    <Search size={18} className={styles.searchIcon} />
                    <input
                        type="text"
                        className={styles.searchInput}
                        placeholder={placeholder}
                        value={search}
                        onChange={(e) => handleSearchChange(e.target.value)}
                    />
                    {search && (
                        <button
                            className={styles.clearBtn}
                            onClick={() => handleSearchChange("")}
                        >
                            <X size={16} />
                        </button>
                    )}
                </div>

                <button
                    className={`${styles.filterToggle} ${showFilters ? styles.filterToggleActive : ""}`}
                    onClick={() => setShowFilters(!showFilters)}
                >
                    <SlidersHorizontal size={18} />
                    Filters
                </button>

                {hasActiveFilters && (
                    <button className={styles.clearAllBtn} onClick={clearAllFilters}>
                        Clear All
                    </button>
                )}
            </div>

            {/* Filter Panel */}
            {showFilters && (
                <div className={styles.filterPanel}>
                    <div className={styles.filterGroup}>
                        <label className={styles.filterLabel}>Status</label>
                        <select
                            className={styles.filterSelect}
                            value={status}
                            onChange={(e) => handleStatusChange(e.target.value)}
                        >
                            <option value="">All Statuses</option>
                            {statusOptions.map((s) => (
                                <option key={s} value={s}>
                                    {statusLabels[s] || s}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className={styles.filterGroup}>
                        <label className={styles.filterLabel}>Min Score</label>
                        <input
                            type="number"
                            className={styles.filterInput}
                            placeholder="0"
                            min={0}
                            max={100}
                            value={minScore}
                            onChange={(e) => handleMinScoreChange(e.target.value)}
                        />
                    </div>

                    <div className={styles.filterGroup}>
                        <label className={styles.filterLabel}>Max Score</label>
                        <input
                            type="number"
                            className={styles.filterInput}
                            placeholder="100"
                            min={0}
                            max={100}
                            value={maxScore}
                            onChange={(e) => handleMaxScoreChange(e.target.value)}
                        />
                    </div>

                    <div className={styles.filterGroup}>
                        <label className={styles.filterLabel}>From</label>
                        <input
                            type="date"
                            className={styles.filterInput}
                            value={dateFrom}
                            onChange={(e) => handleDateFromChange(e.target.value)}
                        />
                    </div>

                    <div className={styles.filterGroup}>
                        <label className={styles.filterLabel}>To</label>
                        <input
                            type="date"
                            className={styles.filterInput}
                            value={dateTo}
                            onChange={(e) => handleDateToChange(e.target.value)}
                        />
                    </div>
                </div>
            )}
        </div>
    );
}
