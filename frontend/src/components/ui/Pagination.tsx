import { ChevronLeft, ChevronRight } from "lucide-react";
import styles from "./Pagination.module.css";

interface PaginationProps {
    currentPage: number;
    totalPages: number;
    onPageChange: (page: number) => void;
}

export default function Pagination({ currentPage, totalPages, onPageChange }: PaginationProps) {
    if (totalPages <= 1) return null;

    // Helper to generate page numbers to display
    const getPageNumbers = () => {
        const pages = [];
        const showMax = 5;
        let start = Math.max(1, currentPage - 2);
        let end = Math.min(totalPages, start + showMax - 1);

        if (end - start + 1 < showMax) {
            start = Math.max(1, end - showMax + 1);
        }

        for (let i = start; i <= end; i++) {
            pages.push(i);
        }
        return pages;
    };

    return (
        <div className={styles.container}>
            <button
                className={styles.navButton}
                onClick={() => onPageChange(currentPage - 1)}
                disabled={currentPage === 1}
                aria-label="Previous Page"
            >
                <ChevronLeft size={18} />
            </button>

            <div className={styles.pageNumbers}>
                {getPageNumbers().map(page => (
                    <button
                        key={page}
                        className={`${styles.pageButton} ${page === currentPage ? styles.active : ""}`}
                        onClick={() => onPageChange(page)}
                    >
                        {page}
                    </button>
                ))}
            </div>

            <button
                className={styles.navButton}
                onClick={() => onPageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                aria-label="Next Page"
            >
                <ChevronRight size={18} />
            </button>
        </div>
    );
}
