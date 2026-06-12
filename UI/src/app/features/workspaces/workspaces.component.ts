import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Subject, Subscription, of } from 'rxjs';
import { catchError, finalize, switchMap, timeout } from 'rxjs/operators';
import { ApiService, EnvironmentConnection, Workspace } from '../../services/api.service';
import { WorkspaceSelectionService } from '../../core/services/workspace-selection.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { EnvironmentConnectionCacheService } from '../../core/services/environment-connection-cache.service';
import { parseApiError } from '../../core/api-error.util';

interface WorkspacesLoadResult {
  workspaces: Workspace[];
  error: string;
}

@Component({
  selector: 'app-workspaces',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './workspaces.component.html',
  styleUrls: ['./workspaces.component.css'],
})
export class WorkspacesComponent implements OnInit, OnDestroy {
  workspaces: Workspace[] = [];
  loading = false;
  error = '';
  environmentName = '';
  environmentId = '';
  isLocalEnvironment = false;
  databricksConnections: EnvironmentConnection[] = [];
  selectedConnectionId = '';
  showConnectionPicker = false;
  private subs = new Subscription();
  private readonly loadWorkspaces$ = new Subject<void>();
  private lastLoadedEnvId = '';

  constructor(
    private api: ApiService,
    private router: Router,
    private workspaceSelection: WorkspaceSelectionService,
    private environmentSelection: EnvironmentSelectionService,
    private connectionCache: EnvironmentConnectionCacheService
  ) {}

  ngOnInit(): void {
    this.subs.add(
      this.loadWorkspaces$.pipe(
        switchMap(() => this.runWorkspacesFetch())
      ).subscribe((result) => {
        this.workspaces = result.workspaces;
        this.error = result.error;
      })
    );

    this.subs.add(
      this.environmentSelection.watchSelectedId().subscribe((envId) => {
        if (!envId) {
          this.loading = false;
          this.error = '';
          this.workspaces = [];
          return;
        }
        const sel = this.environmentSelection.getSelected();
        this.environmentId = envId;
        this.environmentName = sel?.displayName || envId;
        this.isLocalEnvironment = envId === 'local';
        if (envId !== this.lastLoadedEnvId) {
          this.lastLoadedEnvId = envId;
          this.bootstrapForEnvironment();
        }
      })
    );

    this.subs.add(
      this.environmentSelection.watchSelectedConnectionId().subscribe((connId) => {
        this.selectedConnectionId = connId || '';
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.loadWorkspaces$.complete();
  }

  private bootstrapForEnvironment(): void {
    if (this.isLocalEnvironment) {
      this.databricksConnections = [];
      this.showConnectionPicker = false;
      this.requestWorkspacesLoad();
      return;
    }

    const storedConnId = this.environmentSelection.getSelectedConnectionId();
    const cached = this.connectionCache.getCachedDatabricksConnections(this.environmentId);
    if (cached) {
      this.startWorkspacesWithConnections(cached, storedConnId, false);
      return;
    }

    if (storedConnId) {
      this.selectedConnectionId = storedConnId;
      this.requestWorkspacesLoad();
    } else {
      this.loading = true;
    }

    this.connectionCache.getDatabricksConnections(this.environmentId).subscribe({
      next: (list) => this.startWorkspacesWithConnections(list, storedConnId, !!storedConnId),
      error: () => {
        this.databricksConnections = [];
        this.showConnectionPicker = false;
        if (!storedConnId) {
          this.loading = false;
          this.error = 'Failed to load Databricks connections for this environment.';
        }
      },
    });
  }

  /** Apply connection list and fetch workspaces when we know which connection to use. */
  private startWorkspacesWithConnections(
    list: EnvironmentConnection[],
    preferredConnId: string | null,
    alreadyFetching: boolean
  ): void {
    this.applyDatabricksConnections(list);
    const conn = this.connectionCache.pickConnection(list, preferredConnId);
    if (conn) {
      this.selectedConnectionId = conn.id;
      this.environmentSelection.setSelectedConnection(conn);
    }
    if (!conn) {
      this.loading = false;
      this.error = 'No Databricks connection configured. Add one in Connections.';
      return;
    }
    const connChanged = conn.id !== (preferredConnId || '');
    if (!alreadyFetching || connChanged) {
      this.requestWorkspacesLoad();
    }
  }

  private applyDatabricksConnections(list: EnvironmentConnection[]): void {
    this.databricksConnections = list;
    this.showConnectionPicker = list.length > 1;
  }

  onConnectionChange(connectionId: string): void {
    if (!connectionId) return;
    const conn = this.databricksConnections.find((c) => c.id === connectionId) ?? null;
    this.selectedConnectionId = connectionId;
    this.error = '';
    if (conn) {
      this.environmentSelection.setSelectedConnection(conn);
    }
    this.requestWorkspacesLoad();
  }

  refreshWorkspaces(): void {
    this.requestWorkspacesLoad();
  }

  private requestWorkspacesLoad(): void {
    this.loadWorkspaces$.next();
  }

  private runWorkspacesFetch() {
    const envId = this.environmentId || this.environmentSelection.getSelectedId();
    if (!envId) {
      this.loading = false;
      return of({ workspaces: [], error: '' });
    }

    const connId = this.isLocalEnvironment
      ? null
      : this.selectedConnectionId || this.environmentSelection.getSelectedConnectionId();

    this.loading = true;
    this.error = '';
    this.workspaces = [];

    return this.api.browseWorkspaces(envId, connId).pipe(
      timeout(30_000),
      switchMap((list) => of({ workspaces: list, error: '' })),
      catchError((err) =>
        of({
          workspaces: [] as Workspace[],
          error: parseApiError(
            err,
            'Failed to load workspaces. Check the Databricks connection configuration.'
          ),
        })
      ),
      finalize(() => {
        this.loading = false;
      })
    );
  }

  openJobs(w: Workspace): void {
    this.workspaceSelection.setLastWorkspaceId(w.workspace_id);
    this.router.navigate(['/app/jobs'], {
      queryParams: { workspaceId: w.workspace_id },
    });
  }

  openWorkspaceSetup(w: Workspace): void {
    this.router.navigate(['/app/workspaces', w.workspace_id], {
      queryParams: { tab: 'connections' },
    });
  }
}
