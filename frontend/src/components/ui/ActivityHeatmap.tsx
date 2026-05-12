"use client";

import React from 'react';
import type { DailyActivity } from '@/lib/api';
import styles from './ActivityHeatmap.module.css';

interface ActivityHeatmapProps {
  heatmapData: DailyActivity[];
  totalApplied: number;
}

export default function ActivityHeatmap({ heatmapData, totalApplied }: ActivityHeatmapProps) {
  // Build a lookup map from the real backend data
  const dataMap = new Map<string, number>();
  let maxCount = 1;
  for (const entry of heatmapData) {
    dataMap.set(entry.date, entry.count);
    if (entry.count > maxCount) maxCount = entry.count;
  }

  // Generate 364 squares (52 weeks * 7 days) using real data
  const today = new Date();
  const squares: number[] = [];
  for (let i = 363; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = d.toISOString().split('T')[0]; // "2026-04-14"
    const count = dataMap.get(key) || 0;

    // Convert count to level 0-4 based on the user's max
    let level = 0;
    if (count > 0) {
      const ratio = count / maxCount;
      if (ratio <= 0.25) level = 1;
      else if (ratio <= 0.5) level = 2;
      else if (ratio <= 0.75) level = 3;
      else level = 4;
    }
    squares.push(level);
  }

  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const days = ['Mon', 'Wed', 'Fri'];

  return (
    <div className={styles.heatmapCard}>
      <div className={styles.header}>
        <h3 className={styles.title}>Automation Heatmap</h3>
        <span className={styles.subtitle}>{totalApplied} applications in the last year</span>
      </div>
      
      <div className={styles.heatmapWrapper}>
        <div className={styles.dayLabels}>
          {days.map(d => <span key={d}>{d}</span>)}
        </div>
        
        <div className={styles.gridContainer}>
          <div className={styles.monthLabels}>
            {months.map(m => <span key={m}>{m}</span>)}
          </div>
          <div className={styles.squaresGrid}>
             {squares.map((level, i) => (
                <div key={i} className={`${styles.square} ${styles[`level${level}`]}`} title={`Activity level: ${level}`}></div>
             ))}
          </div>
        </div>
      </div>
      
      <div className={styles.legend}>
        <span>Less</span>
        <div className={`${styles.square} ${styles.level0}`}></div>
        <div className={`${styles.square} ${styles.level1}`}></div>
        <div className={`${styles.square} ${styles.level2}`}></div>
        <div className={`${styles.square} ${styles.level3}`}></div>
        <div className={`${styles.square} ${styles.level4}`}></div>
        <span>More</span>
      </div>
    </div>
  );
}
