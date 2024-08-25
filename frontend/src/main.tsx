import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.tsx";
import { Provider } from "./provider.tsx";
import "@/styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Provider>
        <div 
          className="dark text-foreground bg-background"
          style={{ 
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column'
          }}
        >
          <main>
            <App />
          </main>
        </div>
      </Provider>
    </BrowserRouter>
  </React.StrictMode>,
);