import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-context-bar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './context-bar.component.html',
  styleUrls: ['./context-bar.component.css'],
})
export class ContextBarComponent {
  @Input() environmentName = '';
  @Input() datasetName = '';
  @Input() connectionName = '';

  get hasContent(): boolean {
    return !!(this.environmentName || this.datasetName || this.connectionName);
  }
}
