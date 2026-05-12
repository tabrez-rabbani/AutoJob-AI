"use client";

import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
  BarChart, Bar
} from 'recharts';
import type { AnalyticsData } from '@/lib/api';
import styles from './DashboardCharts.module.css';

interface DashboardChartsProps {
  stats: {
    total_scraped?: number;
    total_qualified?: number;
    total_applied?: number;
    total_failed?: number;
  } | null;
  analytics: AnalyticsData | null;
}

const SOURCE_COLORS: Record<string, string> = {
  Naukri: '#59A6CB',
  LinkedIn: '#2563eb',
  Indeed: '#6366f1',
  Wellfound: '#f59e0b',
};

export default function DashboardCharts({ stats, analytics }: DashboardChartsProps) {
  const scraped = stats?.total_scraped || 0;
  const qualified = stats?.total_qualified || 0;
  const applied = stats?.total_applied || 0;

  // ── 1. Activity Data (Last 7 Days) — DYNAMIC from backend ──
  const activityData = (analytics?.daily_activity || []).map(d => ({
    name: new Date(d.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short' }),
    Jobs: d.count,
  }));

  // ── 2. Conversion Funnel — DYNAMIC from stats ──
  const funnelData = [
    { name: 'Scraped', value: scraped, fill: '#3b82f6' },
    { name: 'Qualified', value: qualified, fill: '#8b5cf6' },
    { name: 'Applied', value: applied, fill: '#10b981' }
  ];

  // ── 3. Source Distribution — DYNAMIC from backend ──
  const sourcesData = (analytics?.source_distribution || []).map(s => ({
    name: s.platform,
    value: s.count,
  }));
  const sourceColors = sourcesData.map(s => SOURCE_COLORS[s.name] || '#64748b');

  // Custom Tooltip for Area Chart
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className={styles.customTooltip}>
          <p className={styles.tooltipLabel}>{label}</p>
          <p className={styles.tooltipValue}>
            <span className={styles.tooltipDot} style={{ background: payload[0].color }}></span>
            {payload[0].value} Applications
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className={styles.chartsGrid}>
      
      {/* Main Chart: Application Activity */}
      <div className={`${styles.chartCard} ${styles.colSpan2}`}>
        <div className={styles.chartHeader}>
          <div>
            <h3 className={styles.chartTitle}>Application Activity</h3>
            <p className={styles.chartSubtitle}>Jobs applied over the last 7 days</p>
          </div>
        </div>
        <div className={styles.chartContainer}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={activityData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorJobs" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#59A6CB" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#59A6CB" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
              <XAxis 
                dataKey="name" 
                axisLine={false} 
                tickLine={false} 
                tick={{ fill: '#94a3b8', fontSize: 12 }} 
                dy={10}
              />
              <YAxis 
                axisLine={false} 
                tickLine={false} 
                tick={{ fill: '#94a3b8', fontSize: 12 }} 
                allowDecimals={false}
              />
              <RechartsTooltip content={<CustomTooltip />} />
              <Area 
                type="monotone" 
                dataKey="Jobs" 
                stroke="#59A6CB" 
                strokeWidth={3}
                fillOpacity={1} 
                fill="url(#colorJobs)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Side Charts Container */}
      <div className={styles.sideCharts}>
        
        {/* Source Distribution */}
        <div className={styles.chartCard}>
          <div className={styles.chartHeader}>
             <h3 className={styles.chartTitle}>Top Sources</h3>
          </div>
          <div className={styles.pieContainer}>
            {sourcesData.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height="100%" minHeight={160}>
                  <PieChart>
                    <Pie
                      data={sourcesData}
                      cx="50%"
                      cy="50%"
                      innerRadius={50}
                      outerRadius={70}
                      paddingAngle={5}
                      dataKey="value"
                      stroke="none"
                    >
                      {sourcesData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={sourceColors[index]} />
                      ))}
                    </Pie>
                    <RechartsTooltip 
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                      itemStyle={{ color: '#fff' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                
                {/* Dynamic Legend */}
                <div className={styles.legend}>
                  {sourcesData.map((entry, idx) => (
                    <div key={entry.name} className={styles.legendItem}>
                      <div className={styles.legendColor} style={{ backgroundColor: sourceColors[idx] }}></div>
                      <span className={styles.legendName}>{entry.name}</span>
                      <span className={styles.legendValue}>{entry.value}</span>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <div className={styles.emptyState}>No data yet</div>
            )}
          </div>
        </div>

        {/* Conversion Funnel */}
        <div className={styles.chartCard} style={{ marginTop: '16px', flex: 1, minHeight: '200px' }}>
          <div className={styles.chartHeader}>
             <h3 className={styles.chartTitle}>Conversion Funnel</h3>
          </div>
          <div className={styles.funnelContainer} style={{ width: '100%', height: '140px', minHeight: '140px' }}>
            <ResponsiveContainer width="100%" height="100%" minHeight={140}>
              <BarChart
                data={funnelData}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
              >
                <XAxis type="number" hide />
                <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} tick={{ fill: '#e2e8f0', fontSize: 13, fontWeight: 500 }} width={80} />
                <RechartsTooltip 
                  cursor={{fill: 'rgba(255,255,255,0.05)'}}
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                  itemStyle={{ color: '#fff' }}
                />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={24}>
                  {funnelData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>

    </div>
  );
}
