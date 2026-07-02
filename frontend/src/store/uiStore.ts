import { useState } from "react";

export function useUiState() {
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [apiBase, setApiBase] = useState<string>(import.meta.env.VITE_API_BASE_URL ?? "");

  return { theme, setTheme, apiBase, setApiBase };
}
