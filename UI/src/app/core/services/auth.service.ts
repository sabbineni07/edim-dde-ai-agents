import { Injectable } from '@angular/core';
import { EnvironmentSelectionService } from './environment-selection.service';

export interface User {
  username: string;
  displayName?: string;
}

const AUTH_KEY = 'insights_hub_auth';
const USER_KEY = 'insights_hub_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private token: string | null = null;
  private adminUsernames: string[] = ['admin'];

  constructor(private environmentSelection: EnvironmentSelectionService) {
    this.token = sessionStorage.getItem(AUTH_KEY);
  }

  get isAuthenticated(): boolean {
    return !!this.token || !!sessionStorage.getItem(AUTH_KEY);
  }

  get currentUser(): User | null {
    const raw = sessionStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  }

  setAdminUsernames(usernames: string[]): void {
    this.adminUsernames = (usernames || []).map((u) => u.trim().toLowerCase()).filter(Boolean);
  }

  isAdmin(): boolean {
    const name = (this.currentUser?.username || '').trim().toLowerCase();
    return !!name && this.adminUsernames.includes(name);
  }

  login(username: string, _password: string): Promise<{ user: User; token: string }> {
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        const user: User = { username, displayName: username };
        const token = 'stub-token-' + Date.now();
        sessionStorage.setItem(AUTH_KEY, token);
        sessionStorage.setItem(USER_KEY, JSON.stringify(user));
        this.token = token;
        resolve({ user, token });
      }, 300);
    });
  }

  logout(): void {
    this.token = null;
    sessionStorage.removeItem(AUTH_KEY);
    sessionStorage.removeItem(USER_KEY);
    this.environmentSelection.clearSelected();
  }

  getToken(): string | null {
    return this.token ?? sessionStorage.getItem(AUTH_KEY);
  }
}
