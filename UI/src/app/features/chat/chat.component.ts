import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import {
  ApiService,
  ChatResponse,
  ChatSource,
  EnvironmentConnection,
} from '../../services/api.service';
import { EnvironmentSelectionService } from '../../core/services/environment-selection.service';
import { EnvironmentConnectionCacheService } from '../../core/services/environment-connection-cache.service';
import { parseApiError } from '../../core/api-error.util';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './chat.component.html',
  styleUrls: ['./chat.component.css'],
})
export class ChatComponent implements OnInit, OnDestroy {
  question = '';
  messages: Message[] = [];
  loading = false;
  error = '';

  environmentId = '';
  environmentName = '';

  llmConnections: EnvironmentConnection[] = [];
  ragConnections: EnvironmentConnection[] = [];
  llmConnectionId = '';
  ragConnectionId = '';

  private subs = new Subscription();

  constructor(
    private api: ApiService,
    private environmentSelection: EnvironmentSelectionService,
    private connectionCache: EnvironmentConnectionCacheService
  ) {}

  ngOnInit(): void {
    this.subs.add(
      this.environmentSelection.watchSelectedId().subscribe((id) => {
        this.environmentId = id || '';
        const sel = this.environmentSelection.getSelected();
        this.environmentName = sel?.displayName || this.environmentId;
        this.loadConnections();
      })
    );
    this.environmentId = this.environmentSelection.getSelectedId() || '';
    const sel = this.environmentSelection.getSelected();
    this.environmentName = sel?.displayName || this.environmentId;
    if (this.environmentId) {
      this.loadConnections();
    }
  }

  ngOnDestroy(): void {
    this.subs.unsubscribe();
  }

  loadConnections(): void {
    this.error = '';
    if (!this.environmentId) {
      this.llmConnections = [];
      this.ragConnections = [];
      this.llmConnectionId = '';
      this.ragConnectionId = '';
      return;
    }
    this.subs.add(
      this.api.getEnvironmentConnections(this.environmentId, 'llm').subscribe({
        next: (list) => {
          this.llmConnections = list;
          const picked = this.connectionCache.pickConnection(list, this.llmConnectionId);
          this.llmConnectionId = picked?.id || '';
        },
        error: (err) => {
          this.error = parseApiError(err, 'Failed to load LLM connections');
        },
      })
    );
    this.subs.add(
      this.api.getEnvironmentConnections(this.environmentId, 'rag').subscribe({
        next: (list) => {
          this.ragConnections = list;
          if (this.ragConnectionId && !list.some((c) => c.id === this.ragConnectionId)) {
            this.ragConnectionId = '';
          }
        },
        error: (err) => {
          this.error = parseApiError(err, 'Failed to load knowledge connections');
        },
      })
    );
  }

  get canSend(): boolean {
    return (
      !!this.environmentId &&
      !!this.llmConnectionId &&
      !!(this.question || '').trim() &&
      !this.loading
    );
  }

  send(): void {
    const q = (this.question || '').trim();
    if (!this.canSend) return;

    this.messages.push({ role: 'user', content: q });
    this.question = '';
    this.loading = true;
    this.error = '';

    this.api
      .chat({
        question: q,
        environment_id: this.environmentId,
        llm_connection_id: this.llmConnectionId,
        rag_connection_id: this.ragConnectionId || undefined,
      })
      .subscribe({
        next: (res: ChatResponse) => {
          this.messages.push({
            role: 'assistant',
            content: res.answer,
            sources: res.sources,
          });
          this.loading = false;
        },
        error: (err) => {
          this.error = parseApiError(err, 'Request failed');
          this.loading = false;
        },
      });
  }

  connectionLabel(c: EnvironmentConnection): string {
    const typeLabel =
      c.connection_type === 'ai_foundry'
        ? 'Foundry'
        : c.connection_type === 'ai_search'
          ? 'AI Search'
          : c.connection_type === 'faiss'
            ? 'FAISS'
            : c.connection_type;
    return `${c.name} (${typeLabel})`;
  }
}
