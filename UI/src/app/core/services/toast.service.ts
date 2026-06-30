import { Injectable } from '@angular/core';
import { ToastrService } from 'ngx-toastr';

@Injectable({ providedIn: 'root' })
export class ToastService {
  constructor(private toastr: ToastrService) {}

  success(message: string, title = ''): void {
    this.toastr.success(message, title, { timeOut: 3000 });
  }

  error(message: string, title = ''): void {
    this.toastr.error(message, title, { timeOut: 5000 });
  }

  info(message: string, title = ''): void {
    this.toastr.info(message, title, { timeOut: 3500 });
  }

  warning(message: string, title = ''): void {
    this.toastr.warning(message, title, { timeOut: 4000 });
  }
}
