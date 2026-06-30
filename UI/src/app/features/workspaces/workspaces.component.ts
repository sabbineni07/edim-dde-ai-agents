import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { Subject, Subscription, of } from 'rxjs';
import { catchError, finalize, switchMap, timeout } from 'rxjs/operators';
import {
  ApiService,
  EnvironmentConnection,
  EnvironmentDataset,
  Workspace,
} from '../../services/api.service';
import { WorkspaceSelectionService } from '../../core/services/workspace-selection.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { EnvironmentConnectionCacheService } from '../../core/services/environment-connection-cache.service';
import { EnvironmentDatasetCacheService } from '../../core/services/environment-dataset-cache.service';
import { BrowseDataCacheService } from '../../core/services/browse-data-cache.service';
import { parseApiError } from '../../core/api-error.util';

interface WorkspacesLoadResult {
  workspaces: Workspace[];
  error: string;
}

import { PageHeaderComponent } from '../../shared/page-header/page-header.component';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';
import { LoadingCardComponent } from '../../shared/loading-card/loading-card.component';

@Component({
  selector: 'app-workspaces',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    PageHeaderComponent,
    EmptyStateComponent,
    LoadingCardComponent,
  ],
  templateUrl: './workspaces.component.html',
  styleUrls: ['./workspaces.component.css'],
})
export class WorkspacesComponent implements OnInit, OnDestroy {
  workspaces: Workspace[] = [];
  loading = false;
  error = '';
  errorDismissed = false;
  environmentName = '';
  environmentId = '';
  metricsDatasetName = '';
  metricsDatasetRef = '';
  isLocalEnvironment = false;
  databricksConnections: EnvironmentConnection[] = [];
  selectedConnectionId = '';
  showConnectionPicker = false;
  datasets: EnvironmentDataset[] = [];
  selectedDatasetId = '';
  showDatasetPicker = false;
  private subs = new Subscription();
  private readonly loadWorkspaces$ = new Subject<boolean>();
  private lastLoadedEnvId = '';

  constructor(
    private api: ApiService,
    private router: Router,
    private workspaceSelection: WorkspaceSelectionService,
    private environmentSelection: EnvironmentSelectionService,
    private connectionCache: EnvironmentConnectionCacheService,
    private datasetCache: EnvironmentDatasetCacheService,
    private browseCache: BrowseDataCacheService
  ) {}

  ngOnInit(): void {
    this.subs.add(
      this.loadWorkspaces$.pipe(
        switchMap((force) => this.runWorkspacesFetch(force))
      ).subscribe((result) => {
        this.workspaces = result.workspaces;
        this.error = result.error;
        if (result.error) {
          this.errorDismissed = false;
        }
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
        const env = this.environmentSelection.getEnvironmentRecord(envId);
        this.metricsDatasetName = env?.default_dataset_name?.trim() || '';
        this.metricsDatasetRef =
          env?.default_dataset_ref?.trim() || env?.table_fqn?.trim() || '';
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

    this.subs.add(
      this.environmentSelection.watchSelectedDatasetId().subscribe((datasetId) => {
        this.selectedDatasetId = datasetId || '';
      })
    );
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
    this.loadWorkspaces$.complete();
  }

  private bootstrapForEnvironment(): void {
    this.loadDatasetsAndContinue(() => {
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
    });
  }

  private loadDatasetsAndContinue(next: () => void): void {
    const storedDatasetId = this.environmentSelection.getSelectedDatasetId();
    const cached = this.datasetCache.getCached(this.environmentId);
    if (cached) {
      this.applyDatasets(cached, storedDatasetId);
      next();
      return;
    }

    this.datasetCache.getDatasets(this.environmentId).subscribe({
      next: (list) => {
        this.applyDatasets(list, storedDatasetId);
        next();
      },
      error: () => {
        this.datasets = [];
        this.showDatasetPicker = false;
        next();
      },
    });
  }

  private applyDatasets(list: EnvironmentDataset[], preferredId: string | null): void {
    this.datasets = list;
    this.showDatasetPicker = list.length > 1;
    const ds = this.datasetCache.pickDataset(list, preferredId);
    if (ds) {
      this.selectedDatasetId = ds.id;
      this.metricsDatasetName = ds.name;
      this.metricsDatasetRef = ds.table_ref || ds.table_fqn || ds.local_path || '';
      this.environmentSelection.setSelectedDataset(ds.id);
    }
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

  dismissError(): void {
    this.errorDismissed = true;
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

  onDatasetChange(datasetId: string): void {
    if (!datasetId) return;
    const ds = this.datasets.find((d) => d.id === datasetId) ?? null;
    this.selectedDatasetId = datasetId;
    this.error = '';
    if (ds) {
      this.metricsDatasetName = ds.name;
      this.metricsDatasetRef = ds.table_ref || ds.table_fqn || ds.local_path || '';
      this.environmentSelection.setSelectedDataset(ds.id);
    }
    this.requestWorkspacesLoad();
  }

  refreshWorkspaces(): void {
    this.requestWorkspacesLoad(true);
  }

  private requestWorkspacesLoad(force = false): void {
    this.loadWorkspaces$.next(force);
  }

  private runWorkspacesFetch(force = false) {
    const envId = this.environmentId || this.environmentSelection.getSelectedId();
    if (!envId) {
      this.loading = false;
      return of({ workspaces: [], error: '' });
    }

    const connId = this.isLocalEnvironment
      ? null
      : this.selectedConnectionId || this.environmentSelection.getSelectedConnectionId();
    const datasetId = this.selectedDatasetId || this.environmentSelection.getSelectedDatasetId();

    const cacheKey = this.browseCache.workspacesKey(envId, connId, datasetId);
    const cached = !force && this.browseCache.peek<Workspace[]>(cacheKey);
    this.loading = !cached;
    this.error = '';
    if (!cached) {
      this.workspaces = [];
    }

    return this.browseCache
      .get(cacheKey, () => this.api.browseWorkspaces(envId, connId, datasetId), force)
      .pipe(
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
      queryParams: { tab: 'agents' },
    });
  }
}
