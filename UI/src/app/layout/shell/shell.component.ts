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
    });

    this.fetchEnvironments();

    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => {
        const active = this.resolveActiveMenuItem(e.urlAfterRedirects);
        if (active) this.activeMenuItem = active;
      });

    const active = this.resolveActiveMenuItem(this.router.url);
    if (active) this.activeMenuItem = active;
  }

  get themeLabel(): string {
    return this.theme.current === 'light' ? 'Dark mode' : 'Light mode';
  }

  selectEnvironment(env: PlatformEnvironment): void {
    this.environmentSelection.setSelected({
      id: env.id,
      displayName: env.display_name,
    });
    this.environmentSelection.setSelectedConnection(null);
    this.showEnvPicker = false;
    if (env.id !== 'local') {
      this.connectionCache.getDatabricksConnections(env.id).subscribe();
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
        const selected = this.environmentSelection.getSelected();
        if (selected && selected.id !== 'local') {
          this.connectionCache.getDatabricksConnections(selected.id).subscribe();
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
