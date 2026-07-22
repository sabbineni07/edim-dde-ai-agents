/**
 * TEMPORARY: SQL executor feature.
 * Remove later: this folder + route in app.routes.ts + admin menu link in shell.
 */
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface TempSqlExecuteRequest {
  sql: string;
  max_rows?: number;
}

export interface TempSqlExecuteResponse {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  returns_rows: boolean;
  elapsed_ms: number;
  message: string;
}

@Injectable({ providedIn: 'root' })
export class TempSqlExecutorApi {
  constructor(private http: HttpClient) {}

  execute(body: TempSqlExecuteRequest): Observable<TempSqlExecuteResponse> {
    return this.http.post<TempSqlExecuteResponse>('/api/temp/sql/execute', body);
  }
}
