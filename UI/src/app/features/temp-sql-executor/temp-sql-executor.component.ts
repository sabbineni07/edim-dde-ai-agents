/**
 * TEMPORARY: ad-hoc Postgres SQL console (admin only).
 * Remove later with this folder + API route temp_sql_executor + shell menu link.
 */
import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';
import { parseApiError } from '../../core/api-error.util';
import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { ErrorAlertComponent } from '../../shared/error-alert/error-alert.component';
import {
  TempSqlExecutorApi,
  TempSqlExecuteResponse,
} from './temp-sql-executor.api';

@Component({
  selector: 'app-temp-sql-executor',
  standalone: true,
  imports: [CommonModule, FormsModule, PageHeaderComponent, ErrorAlertComponent],
  templateUrl: './temp-sql-executor.component.html',
  styleUrls: ['./temp-sql-executor.component.css'],
})
export class TempSqlExecutorComponent implements OnInit {
  sql = 'SELECT NOW() AS server_time;';
  maxRows = 200;
  running = false;
  error = '';
  result: TempSqlExecuteResponse | null = null;

  constructor(
    private api: TempSqlExecutorApi,
    private auth: AuthService,
    private router: Router
  ) {}

  ngOnInit(): void {
    if (!this.auth.isAdmin()) {
      void this.router.navigate(['/app/workspaces']);
    }
  }

  get canRun(): boolean {
    return Boolean(this.sql.trim()) && !this.running;
  }

  run(): void {
    const sql = this.sql.trim();
    if (!sql) return;
    this.running = true;
    this.error = '';
    this.result = null;
    this.api.execute({ sql, max_rows: this.maxRows }).subscribe({
      next: (res) => {
        this.result = res;
        this.running = false;
      },
      error: (err) => {
        this.error = parseApiError(err, 'SQL execution failed');
        this.running = false;
      },
    });
  }

  onKeydown(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      if (this.canRun) this.run();
    }
  }

  cellDisplay(value: unknown): string {
    if (value === null || value === undefined) return 'NULL';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }
}
