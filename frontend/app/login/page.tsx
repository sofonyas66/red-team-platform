'use client';

import { useState } from 'react';
import { ShieldCheck, Lock, Mail, Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth-context';

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      await login({ username: email, password });
    } catch (err: any) {
      console.error('Login error:', err);
      setError(err.response?.data?.detail || 'Invalid credentials. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen app-shell flex items-center justify-center p-4">
      <div className="w-full max-w-md animate-in fade-in zoom-in duration-300">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center gap-3 mb-4">
            <div className="brand-mark h-8 gap-1">
              <span className="h-4 opacity-50 w-1.5" />
              <span className="h-7 w-1.5" />
              <span className="h-5 opacity-80 w-1.5" />
            </div>
            <div className="text-left">
              <strong className="block text-xl tracking-[0.2em] font-bold">ETHIO</strong>
              <span className="block text-xs tracking-[0.3em] text-[#35d399] -mt-1">RTAP</span>
            </div>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-white">System Authentication</h1>
          <p className="text-sm text-[#718096] mt-2">Enter your credentials to access the security portal</p>
        </div>

        <div className="panel p-8">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label className="text-[10px] font-bold uppercase tracking-wider text-[#465668] px-1">
                Access Identifier
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#465668]">
                  <Mail size={16} />
                </div>
                <input
                  type="email"
                  required
                  placeholder="name@agency.gov.et"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full bg-[#14202d] border border-[#1d2a39] rounded-lg pl-10 pr-3 py-2.5 text-sm focus:border-[#35d399] outline-none transition-all placeholder:text-[#334355]"
                />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between px-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-[#465668]">
                  Security Key
                </label>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#465668]">
                  <Lock size={16} />
                </div>
                <input
                  type="password"
                  required
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full bg-[#14202d] border border-[#1d2a39] rounded-lg pl-10 pr-3 py-2.5 text-sm focus:border-[#35d399] outline-none transition-all placeholder:text-[#334355]"
                />
              </div>
            </div>

            {error && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg flex gap-3 items-center animate-in slide-in-from-top-1">
                <AlertCircle className="text-red-500 shrink-0" size={16} />
                <div className="text-xs text-red-400 font-medium">{error}</div>
              </div>
            )}

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-11 bg-[#35d399] hover:bg-[#2dbb87] text-[#082118] font-bold tracking-wide transition-colors"
            >
              {loading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <div className="flex items-center gap-2">
                  <ShieldCheck size={18} />
                  <span>INITIALIZE SESSION</span>
                </div>
              )}
            </Button>
          </form>
        </div>

        <div className="mt-8 flex items-center justify-center gap-6 grayscale opacity-40">
          <div className="h-[1px] flex-1 bg-[#1d2a39]" />
          <span className="text-[10px] font-bold tracking-[0.2em] text-[#465668] whitespace-nowrap">
            SECURE ACCESS GATEWAY
          </span>
          <div className="h-[1px] flex-1 bg-[#1d2a39]" />
        </div>
      </div>
    </div>
  );
}
