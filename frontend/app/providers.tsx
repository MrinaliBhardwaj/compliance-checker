"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { AuthProvider } from "@/lib/auth";
import { ThemeProvider } from "@/lib/theme";
import { ToastProvider } from "@/lib/toast";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () => new QueryClient({
      defaultOptions: {
        queries: {
          retry: (count, error) => {
            // Never retry a permission or not-found error — retrying a 403 just
            // makes the user wait longer for the same answer.
            const status = (error as { status?: number })?.status;
            if (status === 401 || status === 403 || status === 404) return false;
            return count < 1;
          },
          refetchOnWindowFocus: false,
          staleTime: 10_000,
        },
      },
    }),
  );
  return (
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <AuthProvider>
          <ToastProvider>{children}</ToastProvider>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
