import { Button } from "../components/shared/Button";

export function SettingsPage({
  apiBase,
  onApiBaseChange
}: {
  apiBase: string;
  onApiBaseChange: (value: string) => void;
}) {
  return (
    <div className="max-w-2xl rounded-2xl border border-slate-800 bg-slate-900/60 p-5 shadow-lg">
      <h2 className="mb-4 text-xl font-semibold">Settings</h2>
      <label className="mb-2 block text-sm text-slate-300">API base URL</label>
      <input
        className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-2 text-sm text-slate-100 outline-none"
        value={apiBase}
        onChange={(e) => onApiBaseChange(e.target.value)}
        placeholder="http://localhost:8000"
      />
      <p className="mt-3 text-sm text-slate-400">
        The frontend reads backend data only and does not infer progress locally.
      </p>
    </div>
  );
}
