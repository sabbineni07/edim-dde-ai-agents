import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-context-bar',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './context-bar.component.html',
  styleUrls: ['./context-bar.component.css'],
})
export class ContextBarComponent {
  @Input() datasetName = '';
  @Input() connectionName = '';
  @Input() datasetLink = '/app/datasets';
  @Input() connectionLink = '/app/connections';

  get hasContent(): boolean {
    return !!(this.datasetName || this.connectionName);
  }
}
