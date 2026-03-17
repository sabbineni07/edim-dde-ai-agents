import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterOutlet, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AuthService } from '../../core/services/auth.service';
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
  sidebarOpen = true;
  menuItems: MenuItem[] = [
    { label: 'Workspaces', route: '/app/workspaces', icon: 'building' },
    { label: 'Jobs', route: '/app/jobs', icon: 'list-task' },
    { label: 'Chat', route: '/app/chat', icon: 'chat-dots' },
    { label: 'Agents', route: '/app/agents', icon: 'robot' },
  ];
  activeMenuItem: MenuItem = this.menuItems[0];

  constructor(
    private router: Router,
    private auth: AuthService
  ) {}

  ngOnInit(): void {
    const user = this.auth.currentUser;
    this.username = user?.displayName || user?.username || 'User';

    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => {
        const url = e.urlAfterRedirects;
        const active = this.menuItems.find(
          (item) => url === item.route || url.startsWith(item.route + '/')
        );
        if (active) this.activeMenuItem = active;
      });

    const current = this.router.url;
    const initial = this.menuItems.find(
      (item) => current === item.route || current.startsWith(item.route + '/')
    );
    if (initial) this.activeMenuItem = initial;
  }

  onMenuItemClick(item: MenuItem): void {
    this.activeMenuItem = item;
    this.router.navigateByUrl(item.route);
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
