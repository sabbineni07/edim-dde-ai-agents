import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-error-alert',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './error-alert.component.html',
  styleUrls: ['./error-alert.component.css'],
})
export class ErrorAlertComponent {
  @Input() message: string | null | undefined = '';
  @Input() variant: 'danger' | 'warning' = 'danger';
  @Input() dismissible = true;
  @Output() dismiss = new EventEmitter<void>();

  onDismiss(): void {
    this.dismiss.emit();
  }
}
