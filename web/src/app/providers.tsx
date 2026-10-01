import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "@/components/ui";
import { ApiError } from "@/lib/api/client";
import { AuthProvider } from "@/lib/auth/AuthProvider";

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Don't retry client errors (403/404/422); retry transient ones once.
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
      },
    },
  });
}

export function AppProviders({ children, queryClient }: { children: ReactNode; queryClient?: QueryClient }) {
  const [client] = useState(() => queryClient ?? makeQueryClient());
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <AuthProvider>{children}</AuthProvider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
