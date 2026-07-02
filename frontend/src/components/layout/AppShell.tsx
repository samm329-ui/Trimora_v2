import type { ReactNode } from "react";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 py-6">
        <header className="mb-6 flex items-center justify-between rounded-2xl border border-slate-800 bg-slate-900/80 px-5 py-4 shadow-lg">
          <div>
            <div className="text-2xl font-semibold tracking-tight">Trimora</div>
            <div className="text-sm text-slate-400">Long video to short-form pipeline</div>
          </div>
          <div className="rounded-full border border-slate-700 px-3 py-1 text-xs uppercase tracking-wide text-slate-300">
            Frontend
          </div>
        </header>
        <main className="flex-1">{children}</main>
      </div>
    </div>
  );
}
