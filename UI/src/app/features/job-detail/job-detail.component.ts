import { Component, OnInit, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ApiService, JobMetricsResponse, RecommendationHistoryEntry } from '../../services/api.service';

@Component({
  selector: 'app-job-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, FormsModule],
  templateUrl: './job-detail.component.html',
  styleUrls: ['./job-detail.component.css'],
})
export class JobDetailComponent implements OnInit {
  workspaceId = input.required<string>();
  jobId = input.required<string>();

  metricsData: JobMetricsResponse | null = null;
  recommendations: RecommendationHistoryEntry[] = [];
  loadingMetrics = true;
  loadingRecs = true;
  runningRecommendation = false;
  error = '';
  startDate = '';
  endDate = '';

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.setDefaultDates();
    this.loadMetrics();
    this.loadRecommendations();
  }

  setDefaultDates(): void {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 30);
    this.endDate = end.toISOString().slice(0, 10);
    this.startDate = start.toISOString().slice(0, 10);
  }

  loadMetrics(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    this.loadingMetrics = true;
    this.api.getJobMetrics(ws, j, this.startDate || undefined, this.endDate || undefined).subscribe({
      next: (data) => {
        this.metricsData = data;
        this.loadingMetrics = false;
      },
      error: () => {
        this.loadingMetrics = false;
        this.metricsData = null;
      },
    });
  }

  loadRecommendations(): void {
    const ws = this.workspaceId();
    const j = this.jobId();
    this.loadingRecs = true;
    this.api.getRecommendations(ws, j, 5).subscribe({
      next: (list) => {
        this.recommendations = list;
        this.loadingRecs = false;
      },
      error: () => {
        this.loadingRecs = false;
        this.recommendations = [];
      },
    });
  }

  formatCost(summary: Record<string, unknown>): string {
    const usd = summary['total_cost_usd'];
    const tokens = summary['total_tokens'];
    const usdStr = typeof usd === 'number' ? usd.toFixed(4) : '–';
    const tokStr = tokens != null ? String(tokens) : '–';
    return `${usdStr} USD, ${tokStr} tokens`;
  }

  runRecommendation(): void {
    const j = this.jobId();
    this.runningRecommendation = true;
    this.error = '';
    this.api
      .generateRecommendation({
        job_id: j,
        start_date: this.startDate || this.metricsData?.start_date || '',
        end_date: this.endDate || this.metricsData?.end_date || '',
      })
      .subscribe({
        next: () => {
          this.runningRecommendation = false;
          this.loadRecommendations();
        },
        error: (err) => {
          this.runningRecommendation = false;
          this.error = err?.error?.detail || err?.message || 'Recommendation failed';
        },
      });
  }
}
