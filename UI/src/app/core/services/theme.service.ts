import { Injectable } from '@angular/core';

export type ThemeMode = 'light' | 'dark';

const STORAGE_KEY = 'insights-hub-theme';

@Injectable({ providedIn: 'root' })
export class ThemeService {
  private mode: ThemeMode = 'light';

  constructor() {
    this.mode = this.readStored();
    this.apply(this.mode);
  }

  get current(): ThemeMode {
    return this.mode;
  }

  setTheme(mode: ThemeMode): void {
    this.mode = mode;
    localStorage.setItem(STORAGE_KEY, mode);
    this.apply(mode);
  }

  toggle(): void {
    this.setTheme(this.mode === 'light' ? 'dark' : 'light');
  }

  private readStored(): ThemeMode {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'dark' ? 'dark' : 'light';
  }

  private apply(mode: ThemeMode): void {
    document.documentElement.setAttribute('data-theme', mode);
  }
}
