import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface MenuItem {
  label: string;
  route: string;
  icon: string;
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
})
export class SidebarComponent {
  @Input() menuItems: MenuItem[] = [];
  @Input() activeMenuItem: MenuItem | null = null;
  @Input() isOpen = true;
  @Output() menuItemClick = new EventEmitter<MenuItem>();

  getIconClass(icon: string): string {
    const map: Record<string, string> = {
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

  onItemClick(item: MenuItem): void {
    this.menuItemClick.emit(item);
  }
}
