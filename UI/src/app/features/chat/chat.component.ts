import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, ChatResponse } from '../../services/api.service';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  context?: Record<string, unknown>;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.css'],
})
export class ChatComponent {
  question = '';
  messages: Message[] = [];
  loading = false;
  error = '';
  workspaceId = '';
  jobId = '';

  constructor(private api: ApiService) {}

  send(): void {
    const q = (this.question || '').trim();
    if (!q || this.loading) return;
    this.messages.push({ role: 'user', content: q });
    this.question = '';
    this.loading = true;
    this.error = '';

    this.api
      .chat({
        question: q,
        workspace_id: this.workspaceId || undefined,
        job_id: this.jobId || undefined,
        start_date: undefined,
        end_date: undefined,
      })
      .subscribe({
        next: (res: ChatResponse) => {
          this.messages.push({
            role: 'assistant',
            content: res.answer,
            context: res.context_summary,
          });
          this.loading = false;
        },
        error: (err) => {
          this.error = err?.error?.detail || err?.message || 'Request failed';
          this.loading = false;
        },
      });
  }
}
