import { Injectable } from '@angular/core';

export interface User {
  username: string;
  displayName?: string;
}

const AUTH_KEY = 'cluster_advisor_auth';
const USER_KEY = 'cluster_advisor_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private token: string | null = null;

  constructor() {
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
  }

  getToken(): string | null {
    return this.token ?? sessionStorage.getItem(AUTH_KEY);
  }
}
