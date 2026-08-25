// Hanok Editorial: keep the app shell calm, typographic, and action-led.
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import Home from "./pages/Home";

function Router() {
  return (
    <Switch>
      <Route path="/" component={Home} />
      {/* Hugging Face의 static Space는 첫 페이지를 "/" 가 아니라 "/index.html" 주소로
          내보낸다. 그 경로를 첫 화면으로 받지 않으면 배포본에서만 404가 뜬다
          (로컬 개발 서버는 "/" 로 열려서 이 문제가 안 보인다). */}
      <Route path="/index.html" component={Home} />
      <Route path="/404" component={NotFound} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light">
        <TooltipProvider>
          <Toaster />
          <Router />
        </TooltipProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
