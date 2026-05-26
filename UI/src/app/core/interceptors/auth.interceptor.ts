import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const token = auth.getToken();
  const user = auth.currentUser;
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const userName = user?.displayName || user?.username;
  if (userName) {
    headers['X-User-Name'] = userName;
  }
  if (Object.keys(headers).length > 0) {
    req = req.clone({ setHeaders: headers });
  }
  return next(req);
};
