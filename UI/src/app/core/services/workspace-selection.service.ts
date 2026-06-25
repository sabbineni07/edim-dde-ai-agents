import { Injectable } from '@angular/core';

const LAST_WORKSPACE_KEY = 'edim_last_workspace_id';

@Injectable({ providedIn: 'root' })
export class WorkspaceSelectionService {
  getLastWorkspaceId(): string | null {
    try {
      return localStorage.getItem(LAST_WORKSPACE_KEY)?.trim() || null;
    } catch {
      return null;
    }
  }

  setLastWorkspaceId(workspaceId: string): void {
    try {
      localStorage.setItem(LAST_WORKSPACE_KEY, workspaceId.trim());
    } catch {
      // ignore storage errors (private browsing, quota, etc.)
    }
  }
}
