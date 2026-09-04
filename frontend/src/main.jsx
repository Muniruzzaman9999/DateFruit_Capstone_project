import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.jsx";
import { AuthProvider } from "./context/AuthContext.jsx";
import "./index.css";

/**
 * The two wrappers matter, and the order matters:
 *
 * <BrowserRouter>  makes the URL available, so components can use links and
 *                  redirects.
 * <AuthProvider>   makes the logged-in user available to every page. It sits
 *                  inside the router because it needs to be able to redirect.
 */
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);
