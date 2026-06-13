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
import { parseApiError } from '../../core/api-error.util';
import { SidebarComponent, MenuItem } from '../sidebar/sidebar.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [CommonModule, SidebarComponent, RouterOutlet],
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
  sidebarOpen = true;
  menuItems: MenuItem[] = [
    { label: 'Connections', route: '/app/connections', icon: 'plug' },
    { label: 'Datasets', route: '/app/datasets', icon: 'table' },
    { label: 'Workspaces', route: '/app/workspaces', icon: 'building' },
    { label: 'Jobs', route: '/app/jobs', icon: 'list-task' },
    { label: 'Agents', route: '/app/agents', icon: 'robot' },
    { label: 'Chat', route: '/app/chat', icon: 'chat-dots' },
  ];
  activeMenuItem: MenuItem = this.menuItems[0];

  constructor(
    private router: Router,
    private auth: AuthService,
    private environmentSelection: EnvironmentSelectionService,
    private connectionCache: EnvironmentConnectionCacheService,
    private api: ApiService
  ) {}

  ngOnInit(): void {
    const user = this.auth.currentUser;
    this.username = user?.displayName || user?.username || 'User';

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

    this.environmentSelection.loadEnvironments().subscribe({
      next: (list) => {
        this.environmentsLoadError = '';
        this.environmentsLoadFailed = false;
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
          'Failed to load environments from the API.'
        );
      },
    });

    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => {
        const active = this.resolveActiveMenuItem(e.urlAfterRedirects);
        if (active) this.activeMenuItem = active;
      });

    const active = this.resolveActiveMenuItem(this.router.url);
    if (active) this.activeMenuItem = active;
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
    this.router.navigateByUrl(item.route);
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  logout(): void {
    this.environmentSelection.clearSelected();
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
