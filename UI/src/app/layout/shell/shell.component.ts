import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterOutlet, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AuthService } from '../../core/services/auth.service';
import {
  EnvironmentSelectionService,
  SelectedEnvironment,
} from '../../core/services/environment-selection.service';
import { ApiService, PlatformEnvironment } from '../../services/api.service';
import { EnvironmentConnectionCacheService } from '../../core/services/environment-connection-cache.service';
import { ThemeService } from '../../core/services/theme.service';
import { parseApiError } from '../../core/api-error.util';
import { SidebarComponent, MenuItem } from '../sidebar/sidebar.component';
import { ContextBarComponent } from '../../shared/context-bar/context-bar.component';

/** Routes where session context chips add little value (setup/admin). */
const CONTEXT_BAR_HIDDEN_PREFIXES = [
  '/app/admin/environments',
  '/app/environments',
  '/app/connections',
  '/app/datasets',
];

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, SidebarComponent, RouterOutlet, ContextBarComponent],
  templateUrl: './shell.component.html',
  styleUrls: ['./shell.component.css'],
})
export class ShellComponent implements OnInit {
  username = '';
  isAdmin = false;
  environments: PlatformEnvironment[] = [];
  selectedEnvironment: SelectedEnvironment | null = null;
  contextDatasetName = '';
  contextConnectionName = '';
  currentUrl = '';
  showEnvPicker = false;
  environmentsLoadError = '';
  environmentsLoadFailed = false;
  environmentsLoadErrorDismissed = false;
  sidebarExpanded = true;
  menuItems: MenuItem[] = [
    { label: 'Connections', route: '/app/connections', icon: 'plug', group: 'setup' },
    { label: 'Datasets', route: '/app/datasets', icon: 'table', group: 'setup' },
    { label: 'Workspaces', route: '/app/workspaces', icon: 'building', group: 'workloads' },
    { label: 'Jobs', route: '/app/jobs', icon: 'list-task', group: 'workloads' },
    { label: 'Agents', route: '/app/agents', icon: 'robot', group: 'ai' },
    { label: 'Chat', route: '/app/chat', icon: 'chat-dots', group: 'ai' },
  ];
  activeMenuItem: MenuItem = this.menuItems[0];

  constructor(
    private router: Router,
    private auth: AuthService,
    private environmentSelection: EnvironmentSelectionService,
    private connectionCache: EnvironmentConnectionCacheService,
    private api: ApiService,
    public theme: ThemeService
  ) {}

  ngOnInit(): void {
    const user = this.auth.currentUser;
    this.username = user?.displayName || user?.username || 'User';

    this.environmentSelection.initializeForCurrentUser();

    this.api.getUiHints().subscribe({
      next: (hints) => {
        if (hints.admin_usernames?.length) {
          this.auth.setAdminUsernames(hints.admin_usernames);
        }
        this.isAdmin = this.auth.isAdmin();
      },
    });

    this.environmentSelection.watchSelected().subscribe((sel) => {
      this.selectedEnvironment = sel;
      this.refreshSessionContext();
      if (sel?.id && sel.id !== 'local') {
        this.connectionCache.getDatabricksConnections(sel.id).subscribe({
          next: () => this.refreshSessionContext(),
        });
      }
    });

    this.environmentSelection.watchSelectedConnection().subscribe(() => {
      this.refreshSessionContext();
    });

    this.fetchEnvironments();

    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => {
        this.currentUrl = e.urlAfterRedirects.split('?')[0].split('#')[0];
        const active = this.resolveActiveMenuItem(this.currentUrl);
        if (active) this.activeMenuItem = active;
      });

    this.currentUrl = this.router.url.split('?')[0].split('#')[0];
    const active = this.resolveActiveMenuItem(this.currentUrl);
    if (active) this.activeMenuItem = active;
  }

  get themeLabel(): string {
    return this.theme.current === 'light' ? 'Dark mode' : 'Light mode';
  }

  get selectedEnvRecord(): PlatformEnvironment | null {
    const id = this.selectedEnvironment?.id;
    if (!id) return null;
    return this.environments.find((e) => e.id === id) ?? null;
  }

  get selectedEnvironmentTier(): string {
    return this.selectedEnvRecord?.environment_tier?.trim() || '';
  }

  get selectedEnvironmentShortName(): string {
    return this.selectedEnvironment?.displayName?.trim() || 'Select environment';
  }

  get userInitials(): string {
    const name = this.username.trim();
    if (!name) return '?';
    const parts = name.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }

  get showContextBar(): boolean {
    if (this.isContextBarHiddenRoute(this.currentUrl)) {
      return false;
    }
    return !!(this.contextDatasetName || this.contextConnectionName);
  }

  selectEnvironment(env: PlatformEnvironment): void {
    this.environmentSelection.setSelected({
      id: env.id,
      displayName: env.display_name,
    });
    this.environmentSelection.setSelectedConnection(null);
    this.showEnvPicker = false;
    if (env.id !== 'local') {
      this.connectionCache.getDatabricksConnections(env.id).subscribe({
        next: () => this.refreshSessionContext(),
      });
    } else {
      this.refreshSessionContext();
    }
  }

  dismissEnvironmentsLoadError(): void {
    this.environmentsLoadErrorDismissed = true;
  }

  dismissEnvPicker(): void {
    this.showEnvPicker = false;
  }

  retryLoadEnvironments(): void {
    this.environmentsLoadErrorDismissed = false;
    this.fetchEnvironments();
  }

  toggleTheme(): void {
    this.theme.toggle();
  }

  private fetchEnvironments(): void {
    this.environmentSelection.loadEnvironments().subscribe({
      next: (list) => {
        this.environmentsLoadError = '';
        this.environmentsLoadFailed = false;
        this.environmentsLoadErrorDismissed = false;
        this.environments = list.filter((e) => e.is_enabled !== false);
        this.refreshSessionContext();
        const selected = this.environmentSelection.getSelected();
        if (selected && selected.id !== 'local') {
          this.connectionCache.getDatabricksConnections(selected.id).subscribe({
            next: () => this.refreshSessionContext(),
          });
        }
        if (!selected && this.environments.length) {
          this.showEnvPicker = true;
        }
        if (!this.environments.length) {
          this.environmentsLoadError = 'No environments are available.';
        }
      },
      error: (err) => {
        console.error('loadEnvironments error', err);
        this.environments = [];
        this.environmentsLoadFailed = true;
        this.environmentsLoadError = parseApiError(
          err,
          'Failed to load environments from the API. Is the backend running on port 8000?'
        );
      },
    });
  }

  manageEnvironments(): void {
    void this.router.navigate(['/app/admin/environments']);
  }

  private refreshSessionContext(): void {
    const envRecord = this.selectedEnvRecord;
    const envId = this.selectedEnvironment?.id;

    if (envRecord?.default_dataset_name?.trim()) {
      this.contextDatasetName = envRecord.default_dataset_name.trim();
    } else if (envRecord?.source_type === 'local_csv') {
      const localName = envRecord.local_dataset?.filename?.trim();
      this.contextDatasetName = localName
        ? localName.replace(/\.csv$/i, '')
        : 'Sample CSV';
    } else {
      this.contextDatasetName = '';
    }

    const selectedConn = this.environmentSelection.getSelectedConnection();
    if (selectedConn?.name?.trim()) {
      this.contextConnectionName = selectedConn.name.trim();
      return;
    }

    if (envId && envId !== 'local') {
      const cached = this.connectionCache.getCachedDatabricksConnections(envId);
      const preferredId = this.environmentSelection.getSelectedConnectionId();
      const picked = cached
        ? this.connectionCache.pickConnection(cached, preferredId)
        : null;
      this.contextConnectionName = picked?.name?.trim() || '';
    } else {
      this.contextConnectionName = '';
    }
  }

  private isContextBarHiddenRoute(url: string): boolean {
    const path = url.split('?')[0].split('#')[0];
    return CONTEXT_BAR_HIDDEN_PREFIXES.some(
      (prefix) => path === prefix || path.startsWith(prefix + '/')
    );
  }

  private resolveActiveMenuItem(url: string): MenuItem | undefined {
    const path = url.split('?')[0].split('#')[0];
    return this.menuItems.find(
      (item) => path === item.route || path.startsWith(item.route + '/')
    );
  }

  onMenuItemClick(item: MenuItem): void {
    this.activeMenuItem = item;
    this.showEnvPicker = false;
  }

  toggleSidebar(): void {
    this.sidebarExpanded = !this.sidebarExpanded;
  }

  logout(): void {
    this.environmentSelection.clearSession();
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
