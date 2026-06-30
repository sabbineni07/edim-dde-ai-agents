import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterLinkActive } from '@angular/router';

export interface MenuItem {
  label: string;
  route: string;
  icon: string;
  group?: 'setup' | 'workloads' | 'ai';
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive],
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
})
export class SidebarComponent {
  @Input() menuItems: MenuItem[] = [];
  @Input() activeMenuItem: MenuItem | null = null;
  @Input() expanded = true;
  @Output() menuItemClick = new EventEmitter<MenuItem>();

  readonly groups: { key: MenuItem['group']; label: string }[] = [
    { key: 'setup', label: 'Setup' },
    { key: 'workloads', label: 'Workloads' },
    { key: 'ai', label: 'AI' },
  ];

  getIconClass(icon: string): string {
    const map: Record<string, string> = {
      plug: 'bi-plug',
      table: 'bi-table',
      building: 'bi-building',
      'list-task': 'bi-list-task',
      'chat-dots': 'bi-chat-dots',
      robot: 'bi-robot',
      house: 'bi-house-door',
      gear: 'bi-gear',
      person: 'bi-person-circle',
    };
    return 'bi ' + (map[icon] || 'bi-circle');
  }

  itemsForGroup(group: MenuItem['group']): MenuItem[] {
    return this.menuItems.filter((item) => item.group === group);
  }

  onItemClick(item: MenuItem): void {
    this.menuItemClick.emit(item);
  }
}
